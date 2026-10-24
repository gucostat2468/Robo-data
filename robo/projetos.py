"""Projetos entre andares: um trabalho de várias etapas, cada etapa com uma pessoa diferente, dependências e revisão.

Uma demanda comum é uma pessoa e uma ferramenta (mediana de 2 s no turno real). Um projeto de Customer Insights de
verdade passa por várias mãos e uma etapa só começa quando a anterior foi concluída:

  1. Engenharia (1º andar)      diagnostica a planilha original suja                  diagnosticar_planilha
  2. Análise (2º andar)         perfil e indicadores (NPS com margem de erro)          perfil_indicadores   ← 1
  3. Ciência de Dados           drivers do NPS (conferidos com o gabarito da fábrica)  drivers              ← 2
  4. Governança                 dados pessoais (LGPD) na mesma base                    dados_pessoais
  5. Relator (2º andar)         resumo executivo das etapas (.md)                      resumo_executivo     ← 2, 3, 4

Todas as etapas usam a MESMA base (a da fábrica com NPS e atributos). A revisão independente é do gestor do dono do
projeto, que não executa nenhuma etapa. Critérios de aceitação de cada etapa: os mesmos das demandas
(demandas.CATALOGO), mais o primeiro driver verdadeiro guardado pela fábrica. Dados: sintéticos, nunca produção.

Roda dentro do ciclo de demandas (sem agendador novo), no máximo um projeto a cada `projetos_intervalo_horas`.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

DONO_DO_PROJETO = "coord_analise"
INTERVALO_HORAS = 1.0
# etapa: (título, ferramenta, de onde vem a equipe, dependências)
ETAPAS = [
    ("Diagnóstico da planilha original (o que barraria a produção)", "diagnosticar_planilha", {"andar": 1}, []),
    ("Perfil e indicadores (NPS com margem de erro)", "perfil_indicadores", {"prefixos": ("analise_",)}, [1]),
    ("Drivers do NPS (o que mais pesa na nota)", "drivers", {"prefixos": ("cd_", "head_ciencia")}, [2]),
    ("Dados pessoais na base (LGPD)", "dados_pessoais", {"prefixos": ("gov_", "sec_")}, []),
    ("Resumo executivo do projeto (.md)", "resumo_executivo", {"area": "Storytelling e Negócio"}, [2, 3, 4]),
]


def _participacoes(cfg) -> dict[str, int]:
    from robo.trabalho import Trabalho
    with Trabalho(cfg).tx() as c:
        linhas = c.execute("SELECT e.funcionario, COUNT(*) FROM etapas e JOIN solicitacoes s ON s.id=e.solicitacao_id "
                           "WHERE json_extract(s.plano,'$.tipo_demanda')='projeto' GROUP BY e.funcionario").fetchall()
    return {r[0]: r[1] for r in linhas}


def _escolher(cfg, ferramenta: str, origem: dict, ja: set[str], vezes: dict[str, int]) -> str | None:
    """Quem faz a etapa: da área/andar pedido, com a ferramenta no contrato, fora do projeto até aqui; rodízio (quem
    participou menos de projetos vem antes). Sem ninguém na área, qualquer autorizado de fora do projeto."""
    from robo import organizacao
    gente = [p for p in organizacao.lista(cfg) if p["id"] not in ja and organizacao.nivel_de(p["id"], p) != "estagiario"
             and organizacao.pode_usar(p["id"], ferramenta, cfg, producao=True)]
    da_area = [p for p in gente if ("andar" in origem and p["andar"] == origem["andar"])
               or ("area" in origem and organizacao.area_de(p["id"]) == origem["area"])
               or p["id"].startswith(origem.get("prefixos") or ("\0",))]
    pool = da_area or gente
    pool.sort(key=lambda p: (vezes.get(p["id"], 0), p["id"]))
    return pool[0]["id"] if pool else None


def _original_da_mesma_base(cfg, tratada: Path) -> Path | None:
    pasta = Path(cfg.originais) / "_treino"  # a esteira guarda a original numa subpasta do mês
    parecidas = sorted(pasta.rglob(f"*{tratada.stem}*"))  # nome com a data na frente
    return parecidas[-1] if parecidas else None


def montar(cfg) -> dict | str:
    """O plano do projeto ou o motivo de não dar para montar agora (sem base com NPS e atributos, sem equipe)."""
    from robo import demandas, organizacao
    dono = organizacao.por_id(cfg).get(DONO_DO_PROJETO) or {}
    base = demandas._com_indicador(cfg, dono)
    if isinstance(base, str):
        return "projeto NPS sem base: " + base
    params_base, extras_drivers = base
    tratada = Path(params_base["arquivo"])
    original = _original_da_mesma_base(cfg, tratada)
    revisor = organizacao.revisor_de(DONO_DO_PROJETO, cfg)
    ja, vezes = {DONO_DO_PROJETO, revisor}, _participacoes(cfg)
    etapas, crits, mapa = [], {}, {}
    for i, (titulo, ferr, origem, deps) in enumerate(ETAPAS, 1):
        if ferr == "diagnosticar_planilha" and not original:
            continue  # a cópia suja desta base não está na máquina: a etapa não é inventada
        quem = _escolher(cfg, ferr, origem, ja, vezes)
        if not quem:
            return f"ninguém fora do projeto tem '{ferr}' no contrato"
        ja.add(quem)
        mapa[i] = len(etapas) + 1
        params = {"arquivo": str(original)} if ferr == "diagnosticar_planilha" else (
            {} if ferr == "resumo_executivo" else {"arquivo": str(tratada)})
        etapas.append({"titulo": titulo, "ferramenta": ferr, "funcionario": quem, "parametros": params,
                       "depende": [mapa[d] for d in deps if d in mapa]})
        if ferr == "resumo_executivo":
            crits[len(etapas)] = [{"tipo": "ok"}, {"tipo": "artefato"}]
        else:
            crits[len(etapas)] = list(demandas.CATALOGO[ferr].criterios) + (extras_drivers if ferr == "drivers" else [])
    return {"titulo": f"Projeto NPS — {tratada.stem}", "etapas": etapas, "revisor": revisor, "base": str(tratada),
            "criterios_por_etapa": {str(k): v for k, v in crits.items()}}


def criar(cfg) -> tuple[str | None, str]:
    """Cria o projeto (não executa). Devolve (id, '') ou (None, motivo)."""
    from robo import orquestrador, organizacao
    plano = montar(cfg)
    if isinstance(plano, str):
        return None, plano
    gente = organizacao.por_id(cfg)
    linhas = [f"{n}. {e['titulo']} — {(gente.get(e['funcionario']) or {}).get('nome', e['funcionario'])}"
              + (f" (depois de {', '.join(map(str, e['depende']))})" if e["depende"] else "")
              for n, e in enumerate(plano["etapas"], 1)]
    pedido = ("Objetivo: análise NPS completa da base, do diagnóstico ao resumo executivo, passando por várias áreas.\n"
              f"Base: {Path(plano['base']).name} (sintética, da fábrica; nunca produção).\nEtapas:\n" + "\n".join(linhas)
              + f"\nRevisão independente: {plano['revisor']}.")
    sid = orquestrador.criar_demanda(
        cfg, plano["titulo"], pedido, DONO_DO_PROJETO, plano["etapas"], plano["revisor"],
        plano_extra={"tipo_demanda": "projeto", "nivel": "profissional", "dados": "sintetico", "base": plano["base"],
                     "criterios_por_etapa": plano["criterios_por_etapa"], "gerada_por": "dem_gerador",
                     "objetivo": "análise NPS completa entre andares"})
    return sid, ""


def ciclo(cfg, agora: datetime | None = None, intervalo_horas: float = INTERVALO_HORAS) -> dict | None:
    """Um projeto por intervalo, criado e executado dentro do ciclo de demandas. None = ainda não é hora."""
    from robo import demandas
    from robo.trabalho import Trabalho
    agora = agora or datetime.now()
    with Trabalho(cfg).tx() as c:
        ult = c.execute("SELECT MAX(criada_em) FROM solicitacoes WHERE json_extract(plano,'$.tipo_demanda')='projeto'"
                        ).fetchone()[0]
    if ult and agora - datetime.fromisoformat(ult) < timedelta(hours=intervalo_horas):
        return None
    sid, motivo = criar(cfg)
    if not sid:
        return {"projeto": None, "motivo": motivo}
    estado = demandas._executar_com_job(cfg, sid, DONO_DO_PROJETO, "projeto_nps")
    return {"projeto": sid, "estado": estado}


def resumo(cfg, limite: int = 10) -> list[dict]:
    """Os últimos projetos: estado e, por etapa, quem fez e como terminou."""
    from robo.trabalho import Trabalho
    with Trabalho(cfg).tx() as c:
        projs = c.execute("SELECT id, titulo, estado, criada_em FROM solicitacoes WHERE "
                          "json_extract(plano,'$.tipo_demanda')='projeto' ORDER BY criada_em DESC LIMIT ?",
                          (limite,)).fetchall()
        saida = []
        for p in projs:
            et = c.execute("SELECT ordem, titulo, funcionario, estado FROM etapas WHERE solicitacao_id=? ORDER BY ordem",
                           (p["id"],)).fetchall()
            saida.append({**dict(p), "etapas": [dict(e) for e in et]})
    return json.loads(json.dumps(saida, default=str))
