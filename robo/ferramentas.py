"""Ferramentas reais que os funcionários usam no atendimento e nas tarefas.

Cada ferramenta chama código que já existe no robô (pipeline em diagnóstico, análise, calculadora, consulta SQL somente
leitura, ronda de TI…). Nenhuma finge: se faltar dado, banco ou arquivo, devolve `ok=False` com a limitação.

Toda resposta declara a sua NATUREZA, para o dono saber de onde ela veio:
  conhecimento        — texto do conhecimento registrado (manuais .md, base do canal)
  calculo             — cálculo determinístico feito agora sobre os dados
  execucao            — código do robô executado agora (ex.: pipeline em modo diagnóstico)
  ferramenta          — leitura de estado do sistema (histórico, ronda de TI, banco)
  hipotese            — interpretação que ainda não foi comprovada
  precisa_confirmacao — ação que só acontece depois da sua aprovação
  limitacao           — não foi possível fazer (e o motivo)
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd

NATUREZAS = {
    "conhecimento": "Conhecimento registrado",
    "calculo": "Cálculo determinístico",
    "execucao": "Execução de código",
    "ferramenta": "Ferramenta do sistema",
    "hipotese": "Hipótese (não comprovada)",
    "precisa_confirmacao": "Precisa da sua confirmação",
    "limitacao": "Limitação (não foi feito)",
}

EXTENSOES_PLANILHA = {".xlsx", ".xlsm", ".xls", ".csv", ".txt"}


def resultado(ok: bool, natureza: str, texto: str, dados: dict | None = None, artefatos: list | None = None,
              evidencia: str = "") -> dict:
    assert natureza in NATUREZAS, natureza
    return {"ok": ok, "natureza": natureza, "natureza_nome": NATUREZAS[natureza], "texto": texto,
            "dados": dados or {}, "artefatos": [str(a) for a in artefatos or []], "evidencia": evidencia}


@dataclass
class Ferramenta:
    id: str
    nome: str
    descricao: str
    risco: str                      # baixo | medio | alto
    altera_dados: bool
    executar: Callable[..., dict]
    precisa: list = field(default_factory=list)   # parâmetros obrigatórios


# ----------------------------------------------------------------------------- utilidades
def _diagnostico(cfg, arquivo: str):
    from robo.pipeline import processar_arquivo
    return processar_arquivo(arquivo, cfg, gravar=False)


def _tabelas_do_arquivo(cfg, arquivo: str) -> tuple[dict[str, pd.DataFrame], object]:
    """Tabelas limpas (antes do modelo estrela) de uma planilha, sem gravar nada."""
    r = _diagnostico(cfg, arquivo)
    t = r.tratamento
    return (dict(getattr(t, "analisaveis", {}) or {}) if t else {}), r


def _arquivo_valido(arquivo) -> Path | None:
    if not arquivo:
        return None
    p = Path(arquivo)
    return p if p.is_file() and p.suffix.lower() in EXTENSOES_PLANILHA else None


def _pasta_artefatos(cfg, ref: str) -> Path:
    p = Path(cfg.logs) / "trabalho" / "artefatos" / (ref or "avulso")
    p.mkdir(parents=True, exist_ok=True)
    return p


# ----------------------------------------------------------------------------- ferramentas
def f_conhecimento(cfg, pergunta: str = "", **_) -> dict:
    from robo import canal
    t = canal.normalizar(pergunta)
    pont = [(canal._pontuar(t, v["chaves"]), i) for i, v in enumerate(canal.CONHECIMENTO)]
    melhor = max(pont) if pont else (0, -1)
    pontos_md, secao = canal._buscar_markdown(cfg, t)
    if secao and pontos_md >= 4 and pontos_md > melhor[0]:
        corpo = secao["corpo"] if len(secao["corpo"]) <= 1500 else secao["corpo"][:1500].rsplit(" ", 1)[0] + "…"
        return resultado(True, "conhecimento", f"{secao['titulo']}: {corpo}", {"fonte": secao["arquivo"]},
                         evidencia=f"manual {secao['arquivo']}, seção “{secao['titulo']}”")
    aprendido = _buscar_handovers(cfg, t)
    if aprendido and aprendido[0] >= max(4, melhor[0] + 1):
        h = aprendido[1]
        return resultado(True, "conhecimento", f"Já aconteceu antes ({h['recorrencias']}x): {h['erro']}. Causa provável: "
                         f"{h['causa']}. O que fazer: {h['regra']}. Como verificar: {h['como_verificar']}.",
                         {"fonte": h["id"]}, evidencia=f"handover {h['id']} ({h['area']})")
    if melhor[0] >= 2:
        v = canal.CONHECIMENTO[melhor[1]]
        return resultado(True, "conhecimento", v["texto"], {"fonte": "base de conhecimento do canal", "autor": v["autor"]},
                         evidencia="base de conhecimento do canal (robo/canal.py)")
    return resultado(False, "limitacao", "Não tenho isso registrado no conhecimento da empresa (manuais e base do canal). "
                                         "Prefiro dizer que não sei a inventar. Se quiser, escreva a resposta em "
                                         "conhecimento/*.md e eu passo a usar.")


def _buscar_handovers(cfg, t: str):
    """Regras aprendidas com erros (handovers) também são conhecimento da empresa."""
    from robo import canal, memoria
    termos = {w for w in t.split() if len(w) >= 4 and w not in canal.PALAVRAS_VAZIAS}
    melhor = None
    for h in memoria.handovers(cfg, limite=500):
        texto = canal.normalizar(f"{h['erro']} {h['causa']} {h['regra']}")
        pontos = sum(2 if w in canal.normalizar(h["erro"]) else 1 for w in termos if w in texto)
        if pontos and (not melhor or pontos > melhor[0]):
            melhor = (pontos, h)
    return melhor


def f_historico(cfg, limite: int = 10, **_) -> dict:
    from robo import historico
    h = historico.ler(cfg.logs, int(limite))
    if not h:
        return resultado(True, "ferramenta", "Ainda não há execução registrada no histórico.", {"execucoes": []},
                         evidencia=str(historico.arquivo_historico(Path(cfg.logs))))
    linhas = [f"{x.get('data_hora', '')[:16]} — {x.get('arquivo')}: {x.get('status')} "
              f"({x.get('linhas_saida') or 0} linhas, {x.get('erros') or 0} erro(s))" for x in h]
    return resultado(True, "ferramenta", "Últimas execuções:\n" + "\n".join(linhas), {"execucoes": h},
                     evidencia=str(historico.arquivo_historico(Path(cfg.logs))))


def f_calcular(cfg, pergunta: str = "", arquivo: str | None = None, base: str | None = None, **_) -> dict:
    from robo import calculos
    fontes = None
    origem = "bases publicadas em Bases-Tratadas"
    if _arquivo_valido(arquivo):
        tabs, r = _tabelas_do_arquivo(cfg, arquivo)
        if not tabs:
            erros = "; ".join(e.mensagem if hasattr(e, "mensagem") else str(e) for e in r.relatorio.erros[:3])
            return resultado(False, "limitacao", f"Não consegui ler {Path(arquivo).name} para calcular ({erros or 'sem tabela'}).")
        nome = Path(arquivo).stem
        fontes = {(nome if len(tabs) == 1 else f"{nome}_{k}"): (df, Path(arquivo).name) for k, df in tabs.items()}
        origem = f"arquivo {Path(arquivo).name} (lido agora, sem publicar)"
    texto = pergunta if not base or "base" in calculos._norm(pergunta) else f"{pergunta} na base {base}"
    r = calculos.calcular(cfg, texto, fontes=fontes)
    if not r:
        return resultado(False, "limitacao", "Não reconheci um pedido de cálculo. Exemplos: \"nps por região\", "
                                             "\"média de valor por loja onde canal = App\", \"percentual de modalidade\".")
    calculou = "\n" in r["texto"] or " — Base " in r["texto"]
    if not calculou or not r.get("calc"):
        return resultado(calculou, "calculo" if calculou else "limitacao", r["texto"], {"autor": r["autor"], "pergunta": texto},
                         evidencia=origem)
    from robo import conferencia
    conf = conferencia.conferir(cfg, r["calc"])
    natureza = "calculo"
    if conf["status"] == "conferido":
        origem += "; conferido no PostgreSQL por SQL independente"
    elif conf["status"] == "divergente":  # número não confiável: avisa, registra e manda para a DBA
        natureza = "hipotese"
        try:
            from robo import memoria
            memoria.handover(cfg, "Divergência entre calculadora e PostgreSQL: " + "; ".join(conf["diferencas"][:3]),
                             r["calc"]["base"], "dba", texto)
        except Exception:
            pass
    return resultado(True, natureza, r["texto"] + "\n\n" + conferencia.texto(conf),
                     {"autor": r["autor"], "pergunta": texto, "conferencia": conf["status"], "sql": conf["sql"]},
                     evidencia=origem)


def f_diagnosticar(cfg, arquivo: str | None = None, **_) -> dict:
    p = _arquivo_valido(arquivo)
    if not p:
        return resultado(False, "limitacao", "Preciso de uma planilha (.xlsx, .xlsm, .xls, .csv ou .txt) anexada à conversa.")
    r = _diagnostico(cfg, p)
    rel = r.relatorio
    erros = [getattr(e, "mensagem", str(e)) for e in rel.erros]
    avisos = [getattr(a, "mensagem", str(a)) for a in rel.avisos]
    conferencias = []
    t = r.tratamento
    if t and t.analisaveis and not erros:  # mesmas conferências do 1º andar que a produção roda (as que não dependem de publicar)
        from robo import quadro
        ctx = quadro.Contexto(arquivo=p.name, cfg=cfg, regra=t.regra, brutas=t.brutas, analisaveis=t.analisaveis,
                              tabelas=t.tabelas)
        conferencias = [c for c in quadro.conferir("engenharia", ctx) if c["id"] != "eng_pleno_releitura"]
        bloqueios = [f"{c['nome']} ({c['cargo'].split(' — ')[0]}): {a}" for c in conferencias if not c["ok"] and c["bloqueia"]
                     for a in c["achados"]]
        erros += bloqueios
    ok = not erros
    texto = (f"{p.name}: {'passaria' if ok else 'seria barrada'} na engenharia — {r.linhas_entrada} linha(s) lidas, "
             f"{r.linhas_saida} na saída, {len(erros)} erro(s), {len(avisos)} aviso(s).")
    if erros:
        texto += "\nErros:\n" + "\n".join(f"• {e}" for e in erros[:15])
    if avisos:
        texto += "\nAvisos:\n" + "\n".join(f"• {a}" for a in avisos[:10])
    texto += "\n(Modo diagnóstico: nada foi gravado, movido ou carregado no banco.)"
    return resultado(True, "execucao", texto, {"aprovaria": ok, "erros": erros, "avisos": avisos,
                                               "linhas_entrada": r.linhas_entrada, "linhas_saida": r.linhas_saida,
                                               "conferencias": [{k: c[k] for k in ("id", "nome", "ok", "achados")} for c in conferencias]},
                     evidencia=f"pipeline executado em diagnóstico sobre {p}")


def _df_para_analise(cfg, arquivo: str | None, base: str | None) -> tuple[dict, str] | tuple[None, str]:
    if _arquivo_valido(arquivo):
        tabs, r = _tabelas_do_arquivo(cfg, arquivo)
        return (tabs or None), Path(arquivo).name
    from robo import calculos
    bases = calculos.bases_publicadas(cfg)
    if not bases:
        return None, ""
    b = base if base in bases else next(iter(bases))
    df, arq = calculos.carregar_base(cfg, b)
    return {b: df}, arq


def f_perfil_indicadores(cfg, arquivo: str | None = None, base: str | None = None, **_) -> dict:
    from robo.analise import PADRAO_ANALISE, Analise
    tabs, nome = _df_para_analise(cfg, arquivo, base)
    if not tabs:
        return resultado(False, "limitacao", "Não há planilha anexada nem base publicada para analisar.")
    c = {**PADRAO_ANALISE, **(cfg.dados.get("analise") or {})}
    linhas, dados = [], {}
    for tab, df in tabs.items():
        a = Analise(df, tab, nome, tab, c, cfg.limpeza.get("padroes_identificador", []))
        a.fazer_perfil()
        a.fazer_indicadores()
        a.fazer_estatistica()
        a.fazer_resumo()
        linhas += a.resumo
        dados[tab] = {"linhas": len(df), "indicadores": a.indicadores.to_dict("records")[:50],
                      "perfil": a.perfil.to_dict("records")[:60]}
    return resultado(True, "calculo", "\n".join(linhas), dados, evidencia=f"análise do 2º andar executada agora sobre {nome}")


def f_dados_pessoais(cfg, arquivo: str | None = None, base: str | None = None, **_) -> dict:
    from robo import quadro
    tabs, nome = _df_para_analise(cfg, arquivo, base)
    if not tabs:
        return resultado(False, "limitacao", "Não há planilha anexada nem base publicada para verificar.")
    achados = quadro.conf_dados_pessoais(quadro.Contexto(arquivo=nome, cfg=cfg, analisaveis=tabs))
    texto = ("Nenhuma coluna parece dado pessoal (e-mail, CPF, telefone)." if not achados
             else "Colunas que parecem dado pessoal:\n" + "\n".join(f"• {a}" for a in achados))
    return resultado(True, "execucao", texto, {"achados": achados}, evidencia=f"verificação LGPD (amostra de 200 valores) em {nome}")


def f_consulta_sql(cfg, consulta: str | None = None, sql: str | None = None, **_) -> dict:
    from robo import consultas
    from robo.banco import Banco
    if sql:
        if not cfg.banco.get("habilitado"):
            return resultado(False, "limitacao", "O PostgreSQL não está habilitado nas Configurações, então não rodei o SQL.")
        try:
            r = consultas.executar_texto(Banco(cfg.banco, cfg.base), sql)
        except Exception as e:
            return resultado(False, "limitacao", f"O banco recusou o SQL: {consultas.explicar_erro(str(e))}")
        linhas = [" | ".join(map(str, l)) for l in r["linhas"][:30]]
        return resultado(True, "execucao", f"{len(r['linhas'])} linha(s){' (cortado em 1.000)' if r['truncado'] else ''} em "
                         f"{r['duracao']} s, somente leitura.\n" + " | ".join(r["colunas"]) + "\n" + "\n".join(linhas),
                         {"colunas": r["colunas"], "linhas": [list(map(str, l)) for l in r["linhas"][:200]], "sql": sql},
                         evidencia="PostgreSQL, transação READ ONLY (o banco recusa qualquer alteração)")
    if not consulta:
        itens = consultas.listar()
        return resultado(True, "ferramenta", "Consultas disponíveis:\n" + "\n".join(f"• {i['id']} — {i['titulo']}" for i in itens[:40]),
                         {"consultas": itens}, evidencia="pasta consultas_sql/")
    if not cfg.banco.get("habilitado"):
        return resultado(False, "limitacao", "O PostgreSQL não está habilitado nas Configurações, então não rodei a consulta. "
                                             "Nada foi inventado.")
    try:
        r = consultas.executar(Banco(cfg.banco, cfg.base), consulta)
    except Exception as e:
        return resultado(False, "limitacao", f"A consulta não rodou: {consultas.explicar_erro(str(e))}")
    linhas = [", ".join(map(str, l)) for l in r["linhas"][:20]]
    return resultado(True, "ferramenta", f"{consulta}: {len(r['linhas'])} linha(s) em {r['duracao']} s (somente leitura).\n"
                     + " | ".join(r["colunas"]) + "\n" + "\n".join(linhas),
                     {"colunas": r["colunas"], "linhas": [list(map(str, l)) for l in r["linhas"][:200]]},
                     evidencia="PostgreSQL, transação somente leitura")


def f_ronda_ti(cfg, **_) -> dict:
    from robo import ti
    r = ti.ronda(cfg, anunciar=False)
    itens = r.get("itens") or []
    ruins = [i for i in itens if i.get("achados")]
    texto = f"Ronda de TI: {len(itens) - len(ruins)}/{len(itens)} verificações OK."
    for i in ruins:
        texto += f"\n• {i.get('nome', i.get('id'))}: " + "; ".join(i["achados"][:3])
    return resultado(True, "ferramenta", texto, r, evidencia="verificações executadas agora neste computador")


def f_organizacao(cfg, **_) -> dict:
    from robo import organizacao
    lot = organizacao.lotacao(cfg)
    texto = "\n".join(f"{a}º andar ({organizacao.NOME_ANDAR.get(a, '')}): "
                      + ", ".join(f"{len(v)} {n}" for n, v in niveis.items()) for a, niveis in sorted(lot.items()))
    return resultado(True, "ferramenta", texto, {"lotacao": lot}, evidencia="registro único de funcionários")


def f_resumo_executivo(cfg, titulo: str = "Resumo executivo", partes: list | None = None, ref: str = "", **_) -> dict:
    """Escreve um .md com os resultados REAIS das etapas anteriores (não cria número novo)."""
    partes = [p for p in partes or [] if p.get("texto")]
    if not partes:
        return resultado(False, "limitacao", "Não há resultado de etapa anterior para resumir.")
    agora = datetime.now()
    md = [f"# {titulo}", "", f"Gerado em {agora:%d/%m/%Y %H:%M} a partir das etapas executadas (nada inventado).", ""]
    for p in partes:
        md += [f"## {p.get('titulo', 'Etapa')}", "", f"_Natureza: {NATUREZAS.get(p.get('natureza'), p.get('natureza'))}"
               + (f" · Evidência: {p['evidencia']}" if p.get("evidencia") else "") + "_", "", p["texto"], ""]
    arq = _pasta_artefatos(cfg, ref) / f"resumo_{agora:%Y%m%d_%H%M%S}.md"
    arq.write_text("\n".join(md), encoding="utf-8")
    return resultado(True, "execucao", f"Resumo executivo gravado em {arq.name} ({len(partes)} seção(ões)).",
                     {"arquivo": str(arq)}, [arq], evidencia=str(arq))


def f_publicar_planilha(cfg, arquivo: str | None = None, **_) -> dict:
    """Coloca a planilha em Bases-Limpeza: o robô processa com TODAS as conferências de produção."""
    p = _arquivo_valido(arquivo)
    if not p:
        return resultado(False, "limitacao", "Preciso de uma planilha anexada para publicar.")
    destino = Path(cfg.entrada) / p.name
    if destino.exists():
        return resultado(False, "limitacao", f"Já existe {p.name} em Bases-Limpeza esperando processamento; não sobrescrevi.")
    shutil.copy2(p, destino)
    return resultado(True, "execucao", f"{p.name} copiada para Bases-Limpeza. O robô vai processar com todas as conferências "
                                       f"de produção (acompanhe no escritório e no Histórico).", {"destino": str(destino)},
                     [destino], evidencia=str(destino))


REGISTRO: dict[str, Ferramenta] = {f.id: f for f in [
    Ferramenta("conhecimento", "Consultar conhecimento", "Busca nos manuais .md e na base de conhecimento", "baixo", False, f_conhecimento, ["pergunta"]),
    Ferramenta("historico", "Ler histórico", "Últimas execuções do robô", "baixo", False, f_historico),
    Ferramenta("calcular", "Calcular", "Cálculo sobre base publicada ou arquivo da conversa", "baixo", False, f_calcular, ["pergunta"]),
    Ferramenta("diagnosticar_planilha", "Diagnosticar planilha", "Pipeline em modo diagnóstico + conferências do 1º andar",
               "baixo", False, f_diagnosticar, ["arquivo"]),
    Ferramenta("perfil_indicadores", "Perfil e indicadores", "Perfil das colunas, NPS/CSAT/CES com margem e testes",
               "baixo", False, f_perfil_indicadores),
    Ferramenta("dados_pessoais", "Verificar dados pessoais", "Procura e-mail, CPF e telefone (LGPD)", "baixo", False, f_dados_pessoais),
    Ferramenta("consulta_sql", "Consulta SQL", "Consulta da biblioteca em transação somente leitura", "baixo", False, f_consulta_sql),
    Ferramenta("ronda_ti", "Ronda de TI", "Verificações de saúde do computador e do robô", "baixo", False, f_ronda_ti),
    Ferramenta("organizacao", "Organização", "Quem faz o quê, por andar e nível", "baixo", False, f_organizacao),
    Ferramenta("resumo_executivo", "Resumo executivo", "Arquivo .md com os resultados das etapas", "medio", False, f_resumo_executivo),
    Ferramenta("publicar_planilha", "Publicar planilha", "Envia a planilha para o pipeline de produção", "alto", True,
               f_publicar_planilha, ["arquivo"]),
]}


def executar(id_ferramenta: str, cfg, **params) -> dict:
    """Executa uma ferramenta. Exceção vira limitação honesta (nunca 'concluído' de mentira)."""
    f = REGISTRO.get(id_ferramenta)
    if not f:
        return resultado(False, "limitacao", f"Não existe a ferramenta '{id_ferramenta}' no robô.")
    faltando = [p for p in f.precisa if not params.get(p)]
    if faltando:
        return resultado(False, "limitacao", f"{f.nome} precisa de: {', '.join(faltando)}.")
    try:
        return f.executar(cfg, **params)
    except Exception as e:
        return resultado(False, "limitacao", f"{f.nome} falhou ({type(e).__name__}: {e}). Nada foi dado como concluído.")
