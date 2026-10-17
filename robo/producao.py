"""Portão de produção: ninguém entra em produção sem conferência independente.

Cada agente confere a PRÓPRIA etapa. Aqui, quem não executou o trabalho confere o CONJUNTO:

  Saulo · Supervisor de Planilhas      conciliação de linhas, integridade fato↔dimensão, chaves e colunas
  Dora  · DBA PostgreSQL               reconciliação dentro do banco ANTES do commit (ver banco.reconciliar)
  Carla · Coordenadora de Engenharia   checklist final de produção do 1º andar (assina a liberação)
  Marcos· Coordenador de Análise       checklist da qualidade das análises do 2º andar (ressalvas, nunca bloqueia)

Princípio de engenharia: "quatro olhos" (four-eyes principle) — quem faz não é quem aprova.
"""

from __future__ import annotations

import re

import pandas as pd

from robo.limpeza import normalizar_nome_coluna

SUPERVISORES = [
    {"id": "supervisor", "nome": "Saulo", "papel": "Supervisor de Planilhas", "cor": "#334155", "andar": 1, "ronda": True,
     "descricao": "Anda pelo 1º andar conferindo o trabalho de todos antes da publicação: toda linha que sumiu precisa "
                  "ter motivo, toda chave da fato precisa existir na dimensão, nenhuma coluna pode estar quebrada."},
    {"id": "dba", "nome": "Dora", "papel": "DBA PostgreSQL", "cor": "#0F766E", "andar": 1, "ronda": False,
     "descricao": "Acompanha tudo o que acontece no banco. Depois de cada carga, confere dentro do PostgreSQL — antes de "
                  "confirmar — se o que entrou bate com o esperado. Se não bater, desfaz a carga inteira."},
    {"id": "coord_engenharia", "nome": "Carla", "papel": "Coordenadora de Engenharia de Dados", "cor": "#1E3A8A", "andar": 1,
     "ronda": True, "descricao": "Circula pelo 1º andar e assina a liberação para produção só quando o checklist completo "
                                "está verde: etapas, provas do RH, conferência do supervisor e do DBA."},
    {"id": "coord_analise", "nome": "Marcos", "papel": "Coordenador de Análise e Ciência de Dados", "cor": "#6D28D9", "andar": 2,
     "ronda": True, "descricao": "Circula pelo 2º andar revisando as análises: todo indicador com base e margem, nenhum "
                                "destaque com base pequena, resumo coerente com os números."},
]

RE_REMOCAO = re.compile(r"(linha|duplicidade)[^.]*removid|removid[^.]*linha", re.IGNORECASE)


def _item(itens, item, ok, detalhe="", bloqueia=True):
    itens.append({"item": item, "ok": bool(ok), "detalhe": detalhe, "bloqueia": bloqueia})


def conferencia_supervisor(t, rel, cfg, arquivo: str) -> list[dict]:
    """Conferência independente do 1º andar. Itens que falham e bloqueiam viram ERRO no relatório."""
    itens: list[dict] = []
    unica = len(t.brutas) == 1
    for aba, bruto in t.brutas.items():
        nome = normalizar_nome_coluna(cfg.saida["nome_aba"]) if unica else normalizar_nome_coluna(aba)
        limpo = t.analisaveis.get(nome)
        if limpo is None:
            continue
        perdidas = len(bruto) - len(limpo)
        explicadas = sum(int(o.quantidade or 0) for o in rel.ocorrencias
                         if o.tabela == nome and o.quantidade and RE_REMOCAO.search(o.mensagem) and "teria" not in o.mensagem)
        _item(itens, f"Conciliação de linhas [{nome}]", perdidas == explicadas,
              f"{len(bruto)} lidas → {len(limpo)} publicadas; {perdidas} removida(s), {explicadas} com motivo registrado")
        _item(itens, f"Tabela com dados [{nome}]", len(limpo) > 0, f"{len(limpo)} linha(s)")
        nomes = list(limpo.columns)
        validos = all(re.fullmatch(r"[a-z_][a-z0-9_]*", c) for c in nomes) and len(set(nomes)) == len(nomes)
        _item(itens, f"Nomes de colunas únicos e padronizados [{nome}]", validos)

    dims = {n: df for n, df in t.tabelas.items() if n.startswith("dim_") and n != "dim_calendario"}
    fatos = {n: df for n, df in t.tabelas.items() if not n.startswith("dim_")}
    for nome_dim, dim in dims.items():
        chave = dim.columns[0]
        _item(itens, f"Chave única na dimensão [{nome_dim}.{chave}]", dim[chave].is_unique and dim[chave].notna().all())
        for nome_fato, fato in fatos.items():
            if chave not in fato.columns:
                continue
            orfas = fato[chave].notna() & ~fato[chave].isin(dim[chave])
            _item(itens, f"Integridade {nome_fato} → {nome_dim}", not orfas.any(),
                  f"{int(orfas.sum())} chave(s) sem correspondência" if orfas.any() else "todas as chaves existem na dimensão")
    if t.modelo and fatos and t.analisaveis:
        base = next(iter(t.analisaveis.values()))
        fato = next(iter(fatos.values()))
        _item(itens, "Modelagem não perdeu nem duplicou linhas", len(fato) == len(base), f"{len(base)} → {len(fato)}")
    if cfg.saida.get("colunas_auditoria", True):
        faltando = [n for n, df in fatos.items() if not {"_arquivo_origem", "_processado_em"} <= set(df.columns)]
        _item(itens, "Colunas de auditoria presentes", not faltando, ", ".join(faltando))

    for i in itens:
        if not i["ok"] and i["bloqueia"]:
            rel.erro(f"Supervisor de planilhas barrou: {i['item']}" + (f" — {i['detalhe']}" if i["detalhe"] else ""))
    if all(i["ok"] for i in itens):
        rel.info(f"Supervisor de planilhas: {len(itens)} conferência(s) independentes aprovadas")
    return itens


def agentes_reprovados_no_rh() -> list[str]:
    from robo import rh
    return [a for a, provas in rh._provas_nativas_cache().items() if not all(p["aprovado"] for p in provas)]


def checklist_engenharia(rel, conferencias: list[dict], equipe, banco_habilitado: bool, banco_ok: bool | None,
                         reprovados: list[str] | None = None, equipe_quadro: list[dict] | None = None) -> dict:
    """Assinatura da Coordenadora de Engenharia: só libera com tudo verde."""
    itens: list[dict] = []
    reprovados = agentes_reprovados_no_rh() if reprovados is None else reprovados
    _item(itens, "Equipe aprovada nas provas técnicas do RH", not reprovados, ", ".join(reprovados))
    problemas = {k: v for k, v in (equipe.problemas or {}).items()}
    _item(itens, "Nenhum agente com configuração inválida", not problemas, ", ".join(problemas))
    _item(itens, "Auditoria sem erros", not [o for o in rel.erros if "Supervisor" not in o.mensagem
                                             and "conferência da equipe" not in o.mensagem],
          f"{len(rel.erros)} erro(s)")
    _item(itens, "Conferência do supervisor aprovada", all(c["ok"] for c in conferencias if c["bloqueia"]),
          f"{sum(c['ok'] for c in conferencias)}/{len(conferencias)} itens")
    if equipe_quadro is not None:
        bloqueios = [f"{x['nome']}: {x['achados'][0]}" for x in equipe_quadro if x["bloqueia"] and not x["ok"]]
        _item(itens, "Conferências dos plenos e juniores aprovadas", not bloqueios,
              "; ".join(bloqueios) or f"{len(equipe_quadro)} conferência(s) independentes")
    if banco_habilitado:
        _item(itens, "Reconciliação do DBA no PostgreSQL", bool(banco_ok), "carga conferida antes do commit" if banco_ok else "")
    liberado = all(i["ok"] for i in itens)
    return {"coordenador": "Carla", "liberado": liberado, "itens": itens}


def checklist_analise(analise: dict | None, base_minima: int, revisao: list[dict] | None = None) -> dict | None:
    """Revisão do Coordenador de Análise: aponta ressalvas, nunca bloqueia (o dado já está publicado)."""
    if not analise:
        return None
    itens: list[dict] = []
    resumo = analise.get("resumo") or []
    _item(itens, "Resumo executivo escrito", bool(resumo), bloqueia=False)
    falhas = [l for l in resumo if "não conseguiu concluir" in l]
    _item(itens, "Todos os analistas concluíram", not falhas, "; ".join(falhas), bloqueia=False)
    indicadores = analise.get("_indicadores") or []
    sem_margem = [i for i in indicadores if i.get("n") is None or i.get("margem") is None]
    _item(itens, "Todo indicador tem base (n) e margem de erro", not sem_margem, bloqueia=False)
    destaques = analise.get("_destaques") or []
    fracos = [d for d in destaques if d.get("significativo") and (d.get("n_grupo") or 0) < base_minima]
    _item(itens, f"Nenhum destaque com base menor que {base_minima}", not fracos, bloqueia=False)
    for x in revisao or []:
        if x["nivel"] != "estagiario":
            _item(itens, f"Conferência de {x['nome']} ({x['cargo'].split(' — ')[-1]})", x["ok"], "; ".join(x["achados"][:3]),
                  bloqueia=False)
    return {"coordenador": "Marcos", "aprovado": all(i["ok"] for i in itens),
            "itens": itens, "ressalvas": [i["item"] for i in itens if not i["ok"]]}


def tabela_checklist(*checklists: dict | None) -> pd.DataFrame:
    linhas = []
    for c in checklists:
        if not c:
            continue
        for i in c["itens"]:
            linhas.append({"responsavel": c["coordenador"], "item": i["item"], "status": "OK" if i["ok"] else "FALHOU",
                           "detalhe": i["detalhe"], "bloqueia": "sim" if i["bloqueia"] else "não"})
    return pd.DataFrame(linhas, columns=["responsavel", "item", "status", "detalhe", "bloqueia"])
