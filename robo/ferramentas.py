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
def f_conhecimento(cfg, pergunta: str = "", quem: str | None = None, registrar_uso: bool = True, **_) -> dict:
    """registrar_uso=False: prova de recuperação do treino — achar a lição não é o mesmo que usá-la no trabalho, então
    não conta como 'aplicada' no caderno."""
    from robo import canal
    t = canal.normalizar(pergunta)
    pont = [(canal._pontuar(t, v["chaves"]), i) for i, v in enumerate(canal.CONHECIMENTO)]
    melhor = max(pont) if pont else (0, -1)
    pontos_md, secao = canal._buscar_markdown(cfg, t)
    if secao and pontos_md >= 3 and pontos_md > melhor[0]:
        from robo import licoes
        if registrar_uso:
            licoes.registrar_uso_por_origem(cfg, "manual", f"{Path(secao['arquivo']).name}#{secao['titulo']}", quem, pergunta)
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
    from robo import licoes
    achadas = licoes.buscar(cfg, pergunta, quem) or licoes.buscar(cfg, pergunta)
    if achadas:
        l = achadas[0]
        if registrar_uso:
            licoes.registrar_uso(cfg, l["id"], quem, pergunta)  # usar a lição numa resposta é a prova de 'aplicada' 
        corpo = l["conteudo"] if len(l["conteudo"]) <= 1500 else l["conteudo"][:1500].rsplit(" ", 1)[0] + "…"
        return resultado(True, "conhecimento", f"{l['titulo']}\n\n{corpo}", {"fonte": l["id"], "versao": l["versao"]},
                         evidencia=f"caderno de lições {l['id']} (v{l['versao']}, origem {l['origem_tipo']})")
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
                         evidencia=origem)  # sem 'calculo' nos dados: não houve conta
    from robo import conferencia
    calc = r["calc"]
    col = (calc["metricas"] or [None])[0]
    try:  # os números que a calculadora deu, por grupo (para quem confere: treino, revisão, auditoria)
        valores = conferencia.valores_pandas(calc["op"], calc["dados"], col, list(calc["por"] or []),
                                             calc.get("escala_csat") or 5)
    except Exception:
        valores = {}
    interpretado = {"op": calc["op"], "metricas": calc["metricas"], "por": calc["por"], "filtros": calc["filtros"],
                    "valores": valores}
    conf = conferencia.conferir(cfg, r["calc"])
    try:  # cada conferência fica registrada: é o indicador de confiabilidade da empresa
        from robo.trabalho import Trabalho
        Trabalho(cfg).lembrar("conferencia_calculo", conf["status"], f"{texto[:200]} → {conf['status']}", "calculadora")
    except Exception:
        pass
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
    return resultado(True, natureza, _organizar_calculo(r, conf), {"autor": r["autor"], "pergunta": texto, "calculo": interpretado,
                     "conferencia": conf["status"], "sql": conf["sql"]}, evidencia=origem)


NOME_OP = {"nps": "NPS", "csat": "CSAT", "media": "média", "mediana": "mediana", "soma": "soma", "contagem": "quantidade",
           "minimo": "mínimo", "maximo": "máximo", "desvio": "desvio padrão", "distintos": "valores distintos"}


def _num(v: float, op: str) -> str:
    if v != v:  # NaN
        return "—"
    if op in ("nps", "contagem", "distintos"):
        return f"{v:.0f}"
    if op == "csat":
        return f"{v:.0f}%"
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _resumo_natural(calc: dict, conclusao: str) -> str:
    """Uma ou duas frases, em português corrido, com o número que importa."""
    from robo import conferencia
    op, por = calc["op"], calc["por"]
    col = (calc["metricas"] or [None])[0]
    nome = NOME_OP.get(op, op)
    sobre = f" de {col}" if col and op not in ("nps", "csat") else ""
    base = f" na base {calc['base']}"
    filtro = (" (só " + ", ".join(f"{c} {s} {v}" for c, s, v in calc["filtros"]) + ")") if calc["filtros"] else ""
    try:
        total = conferencia.valores_pandas(op, calc["dados"], col, [])["(total)"]
        grupos = conferencia.valores_pandas(op, calc["dados"], col, por) if por else {}
    except Exception:
        return ""
    frase = f"O {nome}{sobre} geral é **{_num(total, op)}**{base}{filtro}." if op != "contagem" else \
        f"São **{_num(total, op)}** linhas{base}{filtro}."
    validos = {k: v for k, v in grupos.items() if v == v}
    if len(validos) >= 2:
        alto, baixo = max(validos, key=validos.get), min(validos, key=validos.get)
        frase += (f" Por {', '.join(por)}, o maior é **{alto}** ({_num(validos[alto], op)}) e o menor é **{baixo}** "
                  f"({_num(validos[baixo], op)}).")
        if conclusao:
            frase += " Essa diferença é real (passa no teste estatístico)." if "de fato acima" in conclusao else \
                " Mas essa diferença pode ser acaso: não trate como ranking." if "pode ser acaso" in conclusao else ""
    return frase


def _organizar_calculo(r: dict, conf: dict) -> str:
    """Resposta organizada: frase natural primeiro; detalhes em seções (o painel mostra cada uma recolhível)."""
    from robo import conferencia
    linhas = r["texto"].split("\n")
    cabecalho, corpo = linhas[0], linhas[1:]
    conclusao = next((l for l in corpo if l.startswith("Conclusão:")), "")
    como_ler = next((l for l in corpo if l.startswith("Como ler:")), "")
    # correção do dono aprovada para a empresa: o aviso fica na parte visível, não dentro de uma seção recolhida
    correcao = next((l for l in corpo if l.startswith("(Usei a correção")), "")
    grupos = [l for l in corpo if l and l not in (conclusao, como_ler, correcao)]
    resumo = _resumo_natural(r["calc"], conclusao) or cabecalho
    st = conf["status"]
    if st == "divergente":  # número não confirmado: a abertura não pode afirmar nada
        resumo = ("⛔ DIVERGÊNCIA: a calculadora e o banco deram números diferentes, então não posso afirmar este "
                  "resultado. O que a calculadora mostrou está abaixo, só para investigação.")
    selo = {"conferido": "✅ Conferi o mesmo número no PostgreSQL, por outro caminho.",
            "divergente": "Não use este número até a Dora (DBA) explicar a diferença; já abri um handover para ela.",
            "nao_aplicavel": f"ℹ Não deu para conferir no banco ({conf.get('motivo', '')})."}[st]
    secoes = [("Resultado detalhado", "\n".join([cabecalho] + grupos + ([conclusao] if conclusao else [])))]
    if como_ler:
        secoes.append(("Como ler", como_ler.removeprefix("Como ler: ")))
    if st == "divergente":
        secoes.append(("Onde não bateu", "\n".join(conf["diferencas"][:10])))
    secoes += [("Faça você mesmo no Excel", conf["excel"]), ("A mesma conta em SQL", conf["sql"] or "—")]
    return f"{resumo}\n{selo}" + (f"\n{correcao}" if correcao else "") + "".join(f"\n\n## {t}\n{x}" for t, x in secoes)


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


def f_orquestracao(cfg, **_) -> dict:
    from robo import orquestracao
    r = orquestracao.analisar_sla(cfg)
    return resultado(True, "ferramenta", orquestracao.texto_sla(r), r,
                     evidencia="registros de rotinas_execucoes, rotinas_estado e sessoes deste computador")


def f_organizacao(cfg, **_) -> dict:
    from robo import organizacao
    lot = organizacao.lotacao(cfg)
    texto = "\n".join(f"{a}º andar ({organizacao.NOME_ANDAR.get(a, '')}): "
                      + ", ".join(f"{len(v)} {n}" for n, v in niveis.items()) for a, niveis in sorted(lot.items()))
    return resultado(True, "ferramenta", texto, {"lotacao": lot}, evidencia="registro único de funcionários")


def f_reuniao_andar(cfg, andar: int | None = None, **_) -> dict:
    from robo import reuniao
    r = reuniao.ao_vivo(cfg, andar)
    linhas = []
    for a in r["andares"]:
        p = a["pdca"]
        linhas += [f"{a['andar']}º andar — {a['nome']} (agora, últimos 7 dias):",
                   "Deu certo: " + "; ".join(a["deu_certo"]), "Deu errado: " + "; ".join(x[:200] for x in a["deu_errado"]),
                   "Em andamento agora: " + ("; ".join(a["agora"]) or "nada"),
                   "Plano de ação: " + ("; ".join(f"{x['acao']} ({x.get('quem_precisa_agir') or x['responsavel']}, até {x['prazo']})"
                                                 for x in a["plano_de_acao"]) or "nada novo"),
                   f"PDCA: {p['planejar']} planejar · {p['fazer']} fazendo · {p['checar']} checando · {p['agir']} padronizados "
                   f"({p['boas_praticas']} boas práticas)"]
    if r["em_risco"]:
        linhas.append("Desempenho abaixo do mínimo: " + ", ".join(f"{d['nome']} ({d['taxa']}%)" for d in r["em_risco"]))
    return resultado(True, "ferramenta", "\n".join(linhas), {"reuniao": r},
                     evidencia="histórico, central de solicitações, memória e handovers (calculado agora)")


def f_ideias(cfg, **_) -> dict:
    from robo import ideias
    lista = ideias.gerar(cfg)
    texto = "\n".join(f"{n}. {i['titulo']} — por quê: {i['motivo']}. Primeiro passo: {i['primeiro_passo']} "
                      f"(dono: {i['dono_nome']})" for n, i in enumerate(lista, 1))
    return resultado(True, "ferramenta", texto, {"ideias": lista},
                     evidencia="memória dos funcionários, handovers, solicitações e histórico")


def _base_para_ciencia(cfg, arquivo, base):
    tabs, nome = _df_para_analise(cfg, arquivo, base)
    if not tabs:
        return None, None, None
    tab, df = next(iter(tabs.items()))
    return df, nome, tab


def _secoes(resumo: str, secoes: list[dict]) -> str:
    return resumo + "".join(f"\n\n## {s['titulo']}\n{s['texto']}" for s in secoes)


def f_drivers(cfg, arquivo=None, base=None, pergunta: str = "", **_) -> dict:
    from robo import ciencia
    from robo.calculos import _coluna_indicador
    df, nome, _ = _base_para_ciencia(cfg, arquivo, base)
    if df is None:
        return resultado(False, "limitacao", "Não há planilha anexada nem base publicada para analisar.")
    alvo = _coluna_indicador("nps", df) or _coluna_indicador("csat", df)
    if not alvo:
        return resultado(False, "limitacao", "Não encontrei coluna de NPS ou CSAT nesta base para ser o alvo dos drivers.")
    r = ciencia.drivers(df, alvo)
    resumo, secoes = ciencia.texto_drivers(r)
    return resultado(r["ok"], "calculo" if r["ok"] else "limitacao", _secoes(resumo, secoes), {"drivers": r},
                     evidencia=f"key driver analysis sobre {nome} (correlação + regressão padronizada + VIF)")


def f_segmentacao(cfg, arquivo=None, base=None, **_) -> dict:
    from robo import ciencia
    df, nome, _ = _base_para_ciencia(cfg, arquivo, base)
    if df is None:
        return resultado(False, "limitacao", "Não há planilha anexada nem base publicada para segmentar.")
    r = ciencia.segmentar(df)
    resumo, secoes = ciencia.texto_segmentos(r)
    return resultado(r["ok"], "calculo" if r["ok"] else "limitacao", _secoes(resumo, secoes), {"segmentos": r},
                     evidencia=f"k-means com silhueta sobre {nome}")


def f_anomalias(cfg, arquivo=None, base=None, **_) -> dict:
    from robo import ciencia
    df, nome, _ = _base_para_ciencia(cfg, arquivo, base)
    if df is None:
        return resultado(False, "limitacao", "Não há planilha anexada nem base publicada para verificar.")
    r = ciencia.anomalias(df)
    resumo, secoes = ciencia.texto_anomalias(r)
    return resultado(True, "calculo", _secoes(resumo, secoes), {"anomalias": r}, evidencia=f"regra de Tukey (3×IQR) sobre {nome}")


def f_scorecard(cfg, quem: str = "", andar: int | None = None, **_) -> dict:
    from robo import lideranca
    diretor = quem if quem in lideranca.DIRETOR_DO_ANDAR.values() or quem == "dir_pessoas" else \
        lideranca.DIRETOR_DO_ANDAR.get(int(andar or 1), "dir_operacoes")
    sc = lideranca.scorecard(cfg, diretor)
    cor = {"verde": "🟢", "amarelo": "🟡", "vermelho": "🔴", "cinza": "⚪"}
    linhas = [f"{cor[i['farol']]} {i['indicador']}: {i['valor_texto']} (meta {i['meta']})" for i in sc["indicadores"]]
    return resultado(True, "ferramenta", _secoes(sc["parecer"], [{"titulo": "Indicadores", "texto": "\n".join(linhas)}]),
                     {"scorecard": sc}, evidencia="registros da empresa (histórico, memória, handovers, rotinas), calculado agora")


def f_auditoria(cfg, quem: str = "", andar: int | None = None, **_) -> dict:
    from robo import auditoria, lideranca
    head = quem if quem in auditoria.HEADS else lideranca.HEAD_DO_ANDAR.get(int(andar or 1), "head_engenharia")
    r = auditoria.auditar(cfg, head)
    return resultado(True, "execucao", auditoria.texto(r), {"auditoria": r},
                     evidencia="amostra da semana refeita por outro caminho; registrada em auditorias")


def f_recrutamento(cfg, **_) -> dict:
    from robo import contratacao
    r = contratacao.resumo(cfg)
    linhas = [f"{k}: {v}" for k, v in r.items() if isinstance(v, (int, float, str))]
    for k, v in r.items():
        if isinstance(v, list):
            linhas.append(f"{k}: " + (", ".join(str(x.get('nome', x)) if isinstance(x, dict) else str(x) for x in v[:10]) or "nenhum"))
    return resultado(True, "ferramenta", "Situação das contratações:\n" + "\n".join(linhas), r, evidencia="robo/contratacao.py")


def f_desenvolvimento(cfg, quem: str = "", alvo: str | None = None, **_) -> dict:
    from datetime import datetime, timedelta

    from robo import desenvolvimento, lideranca, memoria, organizacao
    u = desenvolvimento.ultima_rodada(cfg)
    semana = (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds")
    planos = []
    for p in organizacao.lista(cfg):
        if alvo and p["id"] != alvo:
            continue
        erros = [e for e in memoria.experiencias(cfg, p["id"], desde=semana, limite=50) if e["tipo"] == "erro"]
        if erros or alvo:
            itens = lideranca.trilha_individual(erros, memoria.handovers(cfg, p["andar"], abertos=True, limite=5),
                                                memoria.boas_praticas(cfg, p["andar"], 5))
            planos.append(f"{p['nome']} ({p['papel']}):\n" + "\n".join(f"  • {i}" for i in itens))
    resumo = (f"Última rodada de estudo: {u['criada_em'][:16].replace('T', ' ')} — {u['texto']}." if u
              else "Ainda não houve rodada de estudo.")
    resumo += f" {len(planos)} pessoa(s) com plano de desenvolvimento 70-20-10 nesta semana." if not alvo else ""
    return resultado(True, "ferramenta", _secoes(resumo, [{"titulo": "Planos 70-20-10", "texto": "\n".join(planos) or
                                                          "Ninguém com erro na semana: manter estudo e mentoria."}]),
                     {"planos": planos}, evidencia="memória (erros da semana), handovers e boas práticas do andar")


def f_desempenho(cfg, **_) -> dict:
    from robo import memoria
    d = [x for x in memoria.desempenho(cfg, 7) if x["eventos"]]
    nomes = {"ok": "bom", "atencao": "atenção", "insuficiente": "INSUFICIENTE", "sem_dados": "sem dados"}
    linhas = [f"{x['nome']}: {x['acertos']} acerto(s), {x['erros']} erro(s), taxa {x['taxa']}% — {nomes[x['situacao']]}"
              for x in sorted(d, key=lambda x: x["taxa"] if x["taxa"] is not None else 101)]
    insuf = [x["nome"] for x in d if x["situacao"] == "insuficiente"]
    resumo = (f"Na semana, {len(d)} pessoa(s) tiveram trabalho registrado; " +
              (f"{len(insuf)} abaixo do mínimo ({', '.join(insuf)})." if insuf else "ninguém abaixo do mínimo."))
    return resultado(True, "ferramenta", _secoes(resumo, [{"titulo": "Por pessoa (pior para melhor)", "texto": "\n".join(linhas) or "—"}]),
                     {"desempenho": d}, evidencia="memória da semana (regra única de desempenho da política de RH)")


def f_people_analytics(cfg, **_) -> dict:
    from robo import lideranca, organizacao
    r = lideranca.people_analytics(cfg)
    andares = "; ".join(f"{a}º: {n}" for a, n in sorted(r["por_andar"].items()))
    from robo.rh import NOME_NIVEL
    niveis = "; ".join(f"{NOME_NIVEL.get(n, n)}: {q}" for n, q in r["por_nivel"].items())
    resumo = (f"Somos {r['total']} funcionários. {r['pct_aprovados']}% estão aprovados nas provas técnicas e "
              f"{r['pct_com_memoria_30d']}% tiveram trabalho registrado em 30 dias"
              + (f"; acerto médio de {r['acerto_medio_30d']}%." if r["acerto_medio_30d"] is not None else "."))
    return resultado(True, "ferramenta", _secoes(resumo, [{"titulo": "Quadro", "texto": f"Por andar — {andares}\nPor nível — {niveis}"},
                                                         {"titulo": "Abaixo do mínimo", "texto": ", ".join(r["insuficientes"]) or "ninguém"}]),
                     r, evidencia="registro único de funcionários, provas do RH e memória")


def f_raio_x(cfg, **_) -> dict:
    from robo import raio_x
    r = raio_x.montar(cfg)
    return resultado(True, "ferramenta", raio_x.texto(r), {"raio_x": {k: r[k] for k in ("planilhas", "pdca", "solicitacoes")}},
                     evidencia="todos os registros da empresa, lidos agora")


def f_revisao_biblioteca(cfg, quem: str = "", biblioteca: str | None = None, **_) -> dict:
    from robo import bibliotecas, memoria
    alvo = biblioteca or next((n for n, (resp, _) in bibliotecas.BIBLIOTECAS.items() if resp == quem), None)
    nomes = [alvo] if alvo else list(bibliotecas.BIBLIOTECAS)
    linhas, problemas = [], []
    for n in nomes:
        r = bibliotecas.revisar(n)
        linhas.append(f"{n} {r['versao']}: " + ("tudo como o robô espera" if r["ok"] and not r["depreciacoes"] else
                      "; ".join(r["falhas"] + r["depreciacoes"])))
        for f in r["falhas"]:
            problemas.append(f)
            memoria.handover(cfg, f"Revisão da biblioteca {n} {r['versao']}: {f}", n, r["especialista"])
        for d in r["depreciacoes"]:
            memoria.handover(cfg, f"{n}: {d}", n, r["especialista"])
    resumo = ("Revisei " + (alvo or f"as {len(nomes)} bibliotecas") + ": " +
              ("tudo se comporta como o robô espera." if not problemas else f"{len(problemas)} comportamento(s) mudaram."))
    return resultado(True, "execucao", _secoes(resumo, [{"titulo": "Por biblioteca", "texto": "\n".join(linhas)}]),
                     {"problemas": problemas}, evidencia="guardas de comportamento executados agora na versão instalada")


def f_estrategia_python(cfg, **_) -> dict:
    from robo import laboratorio
    r = laboratorio.estrategia_ti(cfg)
    return resultado(True, "calculo", r["texto"], r, evidencia="tempos medidos no laboratório (regressão linear simples)")


def f_laboratorio(cfg, **_) -> dict:
    from robo import laboratorio, organizacao
    r = laboratorio.resumo(cfg)
    gente = organizacao.por_id(cfg)
    nome = lambda x: (gente.get(x) or {}).get("nome", x)  # noqa: E731
    total = sum(p["acertos"] + p["erros"] for p in r["por_pessoa"])
    erros = sum(p["erros"] for p in r["por_pessoa"])
    resumo = (f"Na última semana o laboratório rodou {r['rodadas']} exercício(s) em {len(r['por_area'])} área(s): "
              f"{total - erros} etapa(s) certas e {erros} com erro." if r["rodadas"] else
              "O laboratório ainda não rodou nenhum exercício (ele roda sozinho a cada 10 minutos com o robô aberto).")
    linhas = [f"{nome(p['responsavel'])}: {p['acertos']} certo(s), {p['erros']} erro(s)" for p in r["por_pessoa"]]
    ultimos = [f"{'✅' if u['ok'] else '⛔'} {u['area']} · {nome(u['responsavel'])} · {u['etapa']}: {u['detalhe'][:100]}"
               for u in r["ultimas"][:12]]
    return resultado(True, "ferramenta", _secoes(resumo, [{"titulo": "Por pessoa", "texto": "\n".join(linhas) or "—"},
                                                         {"titulo": "Últimas etapas", "texto": "\n".join(ultimos) or "—"}]),
                     r, evidencia="laboratorio_exercicios (dados sintéticos com resposta conhecida)")


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
    Ferramenta("orquestracao", "SLA das rotinas (Airflow)", "Rotinas atrasadas, com erro ou lentas, pelos registros",
               "baixo", False, f_orquestracao),
    Ferramenta("reuniao_andar", "Reunião ao vivo", "Situação de agora do andar: certo, errado, andamento, plano e PDCA",
               "baixo", False, f_reuniao_andar),
    Ferramenta("ideias", "Ideias para o futuro", "Propostas tiradas da memória de todos, com o dado de origem",
               "baixo", False, f_ideias),
    Ferramenta("drivers", "Drivers do indicador", "O que mais influencia NPS/CSAT (correlação, regressão, VIF)", "baixo", False, f_drivers),
    Ferramenta("segmentacao", "Segmentação", "Grupos de clientes parecidos (k-means com silhueta)", "baixo", False, f_segmentacao),
    Ferramenta("anomalias", "Anomalias", "Valores fora do padrão com a linha de origem", "baixo", False, f_anomalias),
    Ferramenta("scorecard", "Scorecard da diretoria", "Indicadores da área com meta e farol", "baixo", False, f_scorecard),
    Ferramenta("auditoria", "Auditoria por amostragem", "O head refaz por outro caminho uma amostra das entregas", "baixo", False, f_auditoria),
    Ferramenta("recrutamento", "Recrutamento e seleção", "Contratações, experiências e efetivações", "baixo", False, f_recrutamento),
    Ferramenta("desenvolvimento", "Treinamento e desenvolvimento", "Rodada de estudo e planos 70-20-10", "baixo", False, f_desenvolvimento),
    Ferramenta("desempenho", "Desempenho", "Acertos, erros e situação de cada pessoa", "baixo", False, f_desempenho),
    Ferramenta("people_analytics", "People analytics", "Indicadores de pessoas", "baixo", False, f_people_analytics),
    Ferramenta("revisao_biblioteca", "Revisão de biblioteca", "Guardas de comportamento de pandas, numpy, openpyxl…",
               "baixo", False, f_revisao_biblioteca),
    Ferramenta("estrategia_python", "Estratégia Python", "Desempenho por volume, projeção e dívida técnica", "baixo", False,
               f_estrategia_python),
    Ferramenta("laboratorio", "Laboratório", "O que a equipe treinou e errou no laboratório", "baixo", False, f_laboratorio),
    Ferramenta("raio_x", "Raio-X da empresa", "Como a empresa está agora, com números de todos os registros", "baixo", False, f_raio_x),
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
    import time
    inicio = time.perf_counter()
    try:
        r = f.executar(cfg, **params)
    except Exception as e:
        import logging
        logging.getLogger("robo").exception("Ferramenta %s falhou: %s", id_ferramenta, e)  # registro permanente (erros.py)
        r = resultado(False, "limitacao", f"{f.nome} falhou ({type(e).__name__}: {e}). Nada foi dado como concluído.")
        r["excecao"] = type(e).__name__
    _registrar_uso(cfg, id_ferramenta, params.get("quem"), r, time.perf_counter() - inicio)
    return r


USO_ESQUEMA = """CREATE TABLE IF NOT EXISTS uso_ferramentas (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, ferramenta TEXT, quem TEXT, ok INTEGER, natureza TEXT,
  excecao TEXT, segundos REAL);
CREATE INDEX IF NOT EXISTS ix_uso_ferr ON uso_ferramentas(ferramenta, data_hora);"""


def _registrar_uso(cfg, ferramenta: str, quem, r: dict, segundos: float) -> None:
    """Cada uso de ferramenta fica registrado (base da visão de gestão: quanto cada função roda e quanto acerta)."""
    try:
        from robo.trabalho import Trabalho, _agora
        with Trabalho(cfg).tx() as c:
            c.executescript(USO_ESQUEMA)
            from robo.trabalho import proteger
            proteger(c)
            c.execute("INSERT INTO uso_ferramentas (data_hora, ferramenta, quem, ok, natureza, excecao, segundos) "
                      "VALUES (?,?,?,?,?,?,?)", (_agora(), ferramenta, quem, int(bool(r.get("ok"))), r.get("natureza"),
                                                r.get("excecao"), round(segundos, 4)))
    except Exception:  # registrar o uso nunca pode derrubar o trabalho
        import logging
        logging.getLogger("robo").warning("Não consegui registrar o uso da ferramenta %s", ferramenta)
