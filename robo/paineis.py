"""Estúdio de Painéis (3º andar): os dashboards da empresa, montados do zero e mantidos a partir do banco REAL.

Quem faz o quê (ninguém aprova o próprio trabalho):
  - Bárbara (bi_powerbi, especialista em Power BI) MONTA os painéis: lê a memória da empresa (logs/trabalho.db), calcula
    cada indicador com a consulta SQL guardada ao lado do número e monta 5 páginas (visão executiva, treino, pessoas e
    andares, conversas e mentorias, operação e rotinas);
  - Heitor (bi_reconciliacao, analista pleno de BI) CONFERE: refaz os totais por OUTRO caminho (contagem direta, soma das
    quebras, taxa recalculada) e só libera a publicação se tudo bater. Painel com divergência não é publicado — o anterior
    continua no ar e o motivo vai para o canal.

Manutenção: a rotina "paineis" roda de hora em hora. Cada versão publicada fica REGISTRADA para sempre na tabela
`paineis_versoes` (imutável): quando, quem montou, quem conferiu, os indicadores e a assinatura do conteúdo. Assim dá
para ver a evolução de qualquer número no tempo — e nada se perde.

O painel publicado fica em logs/paineis/painel.json (o painel web lê dali). As mesmas tabelas viram o modelo estrela
do Power BI (powerbi/exportar_estrela.py) — os dois partem do mesmo banco, então batem.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

from robo.trabalho import Trabalho, _agora

EQUIPE_BI = [
    {"id": "bi_powerbi", "nome": "Bárbara", "cargo": "Especialista Sênior em Power BI — monta e mantém os painéis da empresa",
     "nivel": "especialista", "andar": 3, "cor": "#F2C811",
     "escopo": ["Monta do zero os 5 painéis da empresa a partir do banco real (trabalho.db)",
                "Guarda a consulta SQL de cada indicador ao lado do número (rastreável)",
                "Mantém os painéis de hora em hora e o modelo estrela do Power BI (powerbi/)"],
     "criterios": ["Todo número tem consulta de origem", "Nenhum painel publicado sem conferência de outra pessoa",
                   "Página vazia diz que está vazia (nunca inventa número)"],
     "metodologias": ["Modelo estrela (fato e dimensões)", "Hierarquia visual: KPI → tendência → detalhe",
                      "Storytelling com dados (o que aconteceu, por quê, o que fazer)"]},
    {"id": "bi_reconciliacao", "nome": "Heitor", "cargo": "Analista Pleno de BI — reconciliação dos números",
     "nivel": "pleno", "andar": 3, "cor": "#B45309",
     "escopo": ["Refaz os totais de cada painel por outro caminho e compara",
                "Barra a publicação quando um número não bate e diz qual e por quanto"],
     "criterios": ["Soma das quebras = total", "Taxa recalculada = taxa publicada", "Contagem direta = contagem do painel"],
     "metodologias": ["Reconciliação (dupla contagem independente)", "Tolerância zero para contagens"]},
]
POR_ID = {p["id"]: p for p in EQUIPE_BI}
GESTORES = {"bi_powerbi": "head_bi", "bi_reconciliacao": "bi_powerbi"}
AUTOR, CONFERENTE = "bi_powerbi", "bi_reconciliacao"

PAGINAS = [("executiva", "Visão Executiva"), ("treino", "Treino & Evolução"), ("pessoas", "Pessoas & Andares"),
           ("conversas", "Conversas & Mentorias"), ("operacao", "Operação & Rotinas")]

ESQUEMA = """CREATE TABLE IF NOT EXISTS paineis_versoes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, autor TEXT, conferente TEXT, situacao TEXT, assinatura TEXT,
  paginas INTEGER, indicadores TEXT, divergencias TEXT);
CREATE TRIGGER IF NOT EXISTS paineis_versoes_sem_alterar BEFORE UPDATE ON paineis_versoes
BEGIN SELECT RAISE(ABORT, 'registro permanente: paineis_versoes não pode ser alterado'); END;
CREATE TABLE IF NOT EXISTS paineis_planilhas (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, nome TEXT, origem TEXT, assinatura TEXT, tema TEXT, linhas INTEGER,
  colunas INTEGER, regras_quebradas INTEGER, ancoras TEXT, leitura TEXT);
CREATE INDEX IF NOT EXISTS ix_paineis_planilhas ON paineis_planilhas(nome, assinatura);
CREATE TRIGGER IF NOT EXISTS paineis_planilhas_sem_alterar BEFORE UPDATE ON paineis_planilhas
BEGIN SELECT RAISE(ABORT, 'registro permanente: paineis_planilhas não pode ser alterado'); END;"""


def pasta(cfg) -> Path:
    return Path(cfg.logs) / "paineis"


def _tb(cfg) -> Trabalho:
    from robo.trabalho import proteger
    tb = Trabalho(cfg)
    with tb.tx() as c:
        c.executescript(ESQUEMA)
        proteger(c)
    return tb


def _tabelas(c) -> set[str]:
    return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _ind(valor, sql: str, rotulo: str, formato: str = "inteiro", detalhe: str = "") -> dict:
    return {"rotulo": rotulo, "valor": valor, "formato": formato, "sql": " ".join(sql.split()), "detalhe": detalhe}


def _pct(x: float, casas: int = 1) -> str:
    return f"{x * 100:.{casas}f}%".replace(".", ",")


def _horas_completas(linhas: list[dict]) -> list[dict]:
    """Hora sem tentativa também é informação (a empresa estava parada): entra como zero, para a linha não mentir."""
    if not linhas:
        return []
    fmt = "%Y-%m-%dT%H"
    feitas = {r["hora"]: r["tentativas"] for r in linhas}
    h, fim, saida = datetime.strptime(linhas[0]["hora"], fmt), datetime.strptime(linhas[-1]["hora"], fmt), []
    while h <= fim:
        chave = h.strftime(fmt)
        saida.append({"hora": chave, "tentativas": feitas.get(chave, 0)})
        h += timedelta(hours=1)
    return saida


def _linhas(c, sql: str, *args) -> list[dict]:
    return [dict(r) for r in c.execute(sql, args)]


# =============================================================================== montagem (Bárbara)
def construir(cfg, agora: datetime | None = None) -> dict:
    """Monta as 5 páginas com os números do banco. Não grava nada: quem publica é `rotina`, depois da conferência."""
    from robo import organizacao
    from robo.rotinas import ROTINAS
    from robo.treino_casos import CATALOGO
    agora = agora or datetime.now()
    gente = organizacao.lista(cfg)
    nome = {p["id"]: p["nome"] for p in gente}
    andar_de = {p["id"]: int(p.get("andar") or 0) for p in gente}
    nome_comp = lambda x: CATALOGO[x].nome if x in CATALOGO else x  # noqa: E731
    desde = (agora - timedelta(days=14)).isoformat(timespec="seconds")
    p: dict[str, dict] = {k: {"titulo": t, "indicadores": {}, "graficos": {}, "achados": []} for k, t in PAGINAS}
    with Trabalho(cfg).tx() as c:
        tem = _tabelas(c)
        # ------------------------------------------------------------------ treino (fato principal)
        if "treino_tentativas" in tem:
            sql_total = "SELECT COUNT(*) FROM treino_tentativas"
            total = c.execute(sql_total).fetchone()[0]
            sql_taxa = "SELECT AVG(acertou) FROM treino_tentativas"
            taxa = c.execute(sql_taxa).fetchone()[0]
            sql_ativos = "SELECT COUNT(DISTINCT funcionario) FROM treino_tentativas"
            ativos = c.execute(sql_ativos).fetchone()[0]
            e = p["executiva"]["indicadores"]
            e["tentativas"] = _ind(total, sql_total, "Tentativas de treino")
            e["taxa_acerto"] = _ind(taxa, sql_taxa, "Taxa de acerto", "percentual")
            e["ativos"] = _ind(ativos, sql_ativos, "Funcionários que já treinaram", detalhe=f"de {len(gente)} no quadro")
            sql_dia = ("SELECT substr(data_hora,1,10) AS dia, COUNT(*) AS tentativas, AVG(acertou) AS taxa "
                       "FROM treino_tentativas WHERE data_hora>=? GROUP BY 1 ORDER BY 1")
            p["executiva"]["graficos"]["por_dia"] = {"tipo": "linha", "titulo": "Tentativas por dia (14 dias)",
                                                     "sql": sql_dia, "linhas": _linhas(c, sql_dia, desde)}
            sql_hora = ("SELECT substr(data_hora,1,13) AS hora, COUNT(*) AS tentativas FROM treino_tentativas "
                        "WHERE data_hora>=? GROUP BY 1 ORDER BY 1")
            p["executiva"]["graficos"]["por_hora"] = {
                "tipo": "linha", "titulo": "Ritmo por hora (últimas 48 h · hora sem turno = 0)", "sql": sql_hora,
                "linhas": _horas_completas(_linhas(c, sql_hora, (agora - timedelta(hours=48)).isoformat(timespec="seconds")))}
            sql_nivel = "SELECT nivel, COUNT(*) AS tentativas, AVG(acertou) AS taxa FROM treino_tentativas GROUP BY 1 ORDER BY 1"
            p["executiva"]["graficos"]["por_nivel"] = {"tipo": "colunas", "titulo": "Acerto por nível de dificuldade",
                                                       "sql": sql_nivel, "linhas": _linhas(c, sql_nivel)}
            # andar = andar ATUAL da pessoa (organograma); quem saiu do quadro vai para "fora do quadro"
            por_andar: dict[int, dict] = {}
            for r in c.execute("SELECT funcionario, COUNT(*) n, SUM(acertou) ok FROM treino_tentativas GROUP BY 1"):
                a = andar_de.get(r["funcionario"], 0)
                d = por_andar.setdefault(a, {"andar": a, "tentativas": 0, "acertos": 0})
                d["tentativas"] += r["n"]
                d["acertos"] += r["ok"] or 0
            linhas_andar = []
            for a in sorted(por_andar):
                d = por_andar[a]
                linhas_andar.append({**d, "rotulo": f"{a}º · {organizacao.NOME_ANDAR.get(a, '')}" if a else "Fora do quadro",
                                     "taxa": d["acertos"] / d["tentativas"] if d["tentativas"] else None})
            p["executiva"]["graficos"]["por_andar"] = {
                "tipo": "barras", "titulo": "Taxa de acerto por andar", "linhas": linhas_andar,
                "sql": "SELECT funcionario, COUNT(*), SUM(acertou) FROM treino_tentativas GROUP BY 1  -- + andar atual do organograma"}
            sql_comp = ("SELECT competencia, COUNT(*) AS tentativas, AVG(acertou) AS taxa, AVG(nivel) AS nivel_medio "
                        "FROM treino_tentativas GROUP BY 1 ORDER BY taxa, tentativas DESC")
            comps = [{**r, "rotulo": nome_comp(r["competencia"])} for r in _linhas(c, sql_comp)]
            p["treino"]["graficos"]["por_competencia"] = {"tipo": "barras", "titulo": "Acerto por competência",
                                                          "sql": sql_comp, "linhas": comps}
            sql_erros = ("SELECT tipo_erro, COUNT(*) AS n FROM treino_tentativas WHERE acertou=0 AND tipo_erro<>'' "
                         "GROUP BY 1 ORDER BY n DESC")
            p["treino"]["graficos"]["erros"] = {"tipo": "barras", "titulo": "Erros por tipo (cada um virou lição)",
                                                "sql": sql_erros, "linhas": _linhas(c, sql_erros)}
            sql_garg = ("SELECT competencia, nivel, COUNT(*) AS n, AVG(acertou) AS taxa FROM treino_tentativas "
                        "GROUP BY 1, 2 HAVING n >= 5 AND taxa < 0.8 ORDER BY taxa")
            gargalos = [{**r, "rotulo": f"{nome_comp(r['competencia'])} · nível {r['nivel']}"} for r in _linhas(c, sql_garg)]
            p["treino"]["graficos"]["gargalos"] = {"tipo": "tabela", "titulo": "Gargalos (≥ 5 tentativas e < 80% de acerto)",
                                                   "sql": sql_garg, "linhas": gargalos}
            for g in gargalos[:3]:
                p["treino"]["achados"].append(f"Gargalo: {g['rotulo']} com {_pct(g['taxa'], 0)} de acerto em {g['n']} "
                                              f"tentativas — a Sala de Casos revisa os casos e o dono da ferramenta confere "
                                              f"se o erro é da pessoa ou do código.")
            sql_pessoas = ("SELECT funcionario, COUNT(*) AS tentativas, AVG(acertou) AS taxa, MAX(data_hora) AS ultima "
                           "FROM treino_tentativas GROUP BY 1")
            pessoas = [{**r, "nome": nome.get(r["funcionario"], r["funcionario"]), "andar": andar_de.get(r["funcionario"], 0)}
                       for r in _linhas(c, sql_pessoas)]
            pessoas.sort(key=lambda x: (-(x["taxa"] or 0), -x["tentativas"]))
            p["pessoas"]["graficos"]["ranking"] = {"tipo": "tabela", "titulo": "Pessoas por taxa de acerto", "sql": sql_pessoas,
                                                   "linhas": pessoas}
            sem_treino = sorted(nome[x] for x in nome if x not in {r["funcionario"] for r in pessoas})
            p["pessoas"]["indicadores"]["sem_treino"] = _ind(len(sem_treino), sql_ativos + "  -- comparado ao organograma",
                                                             "Ainda sem nenhuma tentativa",
                                                             detalhe=", ".join(sem_treino[:8]))
        if "treino_niveis" in tem:
            sql_nm = "SELECT AVG(nivel) FROM treino_niveis"
            p["executiva"]["indicadores"]["nivel_medio"] = _ind(c.execute(sql_nm).fetchone()[0], sql_nm, "Nível médio (1–5)", "decimal")
        if "treino_niveis_eventos" in tem:
            sql_ev = ("SELECT substr(data_hora,1,10) AS dia, SUM(para>de) AS subidas, SUM(para<de) AS quedas "
                      "FROM treino_niveis_eventos WHERE de IS NOT NULL GROUP BY 1 ORDER BY 1")
            ev = _linhas(c, sql_ev)
            p["treino"]["graficos"]["evolucao"] = {"tipo": "colunas", "titulo": "Subidas e quedas de nível por dia",
                                                   "sql": sql_ev, "linhas": ev}
            sub, qued = sum(x["subidas"] or 0 for x in ev), sum(x["quedas"] or 0 for x in ev)
            p["treino"]["indicadores"]["subidas"] = _ind(sub, sql_ev, "Subidas de nível")
            p["treino"]["indicadores"]["quedas"] = _ind(qued, sql_ev, "Quedas de nível")
        # ------------------------------------------------------------------ pessoas e andares (organograma)
        headcount = {}
        for x in gente:
            headcount[andar_de[x["id"]]] = headcount.get(andar_de[x["id"]], 0) + 1
        p["pessoas"]["indicadores"]["quadro"] = _ind(len(gente), "organograma (robo/organizacao.py)", "Funcionários no quadro")
        p["pessoas"]["graficos"]["headcount"] = {
            "tipo": "barras", "titulo": "Pessoas por andar", "sql": "organograma (robo/organizacao.py)",
            "linhas": [{"andar": a, "rotulo": f"{a}º · {organizacao.NOME_ANDAR.get(a, '')}", "pessoas": n}
                       for a, n in sorted(headcount.items())]}
        if "rh_movimentos" in tem:
            sql_rh = "SELECT tipo, situacao, COUNT(*) AS n FROM rh_movimentos GROUP BY 1, 2 ORDER BY n DESC"
            p["pessoas"]["graficos"]["rh"] = {"tipo": "tabela", "titulo": "Movimentos de RH", "sql": sql_rh,
                                              "linhas": _linhas(c, sql_rh)}
        # ------------------------------------------------------------------ conversas e mentorias
        if "interacoes" in tem:
            sql_conv = "SELECT COUNT(*) FROM interacoes"
            p["executiva"]["indicadores"]["conversas"] = _ind(c.execute(sql_conv).fetchone()[0], sql_conv, "Conversas registradas")
            sql_tipo = "SELECT tipo, COUNT(*) AS n FROM interacoes GROUP BY 1 ORDER BY n DESC"
            p["conversas"]["graficos"]["por_tipo"] = {"tipo": "barras", "titulo": "Conversas por tipo", "sql": sql_tipo,
                                                      "linhas": _linhas(c, sql_tipo)}
            sql_ult = "SELECT id, data_hora, de, para, tipo, substr(texto,1,240) AS texto FROM interacoes ORDER BY id DESC LIMIT 12"
            p["conversas"]["graficos"]["ultimas"] = {
                "tipo": "conversas", "titulo": "Últimas conversas", "sql": sql_ult,
                "linhas": [{**r, "de_nome": nome.get(r["de"], r["de"]), "para_nome": nome.get(r["para"], r["para"])}
                           for r in _linhas(c, sql_ult)]}
            sql_quem = ("SELECT de, COUNT(*) AS n FROM interacoes GROUP BY 1 ORDER BY n DESC LIMIT 10")
            p["conversas"]["graficos"]["quem_fala"] = {
                "tipo": "barras", "titulo": "Quem mais conversa", "sql": sql_quem,
                "linhas": [{**r, "rotulo": nome.get(r["de"], r["de"])} for r in _linhas(c, sql_quem)]}
        if "mentorias" in tem:
            sql_m = "SELECT situacao, COUNT(*) AS n FROM mentorias GROUP BY 1 ORDER BY n DESC"
            ment = _linhas(c, sql_m)
            p["conversas"]["graficos"]["mentorias"] = {"tipo": "barras", "titulo": "Mentorias por situação", "sql": sql_m,
                                                       "linhas": ment}
            p["conversas"]["indicadores"]["mentorias"] = _ind(sum(x["n"] for x in ment), "SELECT COUNT(*) FROM mentorias",
                                                              "Mentorias abertas a partir de erros")
        # ------------------------------------------------------------------ operação e rotinas
        if "rotinas_execucoes" in tem:
            sql_rot = ("SELECT nome, COUNT(*) AS execucoes, SUM(status='erro') AS erros, AVG(segundos) AS segundos_medio, "
                       "MAX(fim) AS ultima FROM rotinas_execucoes GROUP BY 1 ORDER BY nome")
            rot = []
            for r in _linhas(c, sql_rot):
                resp = (ROTINAS.get(r["nome"]) or ("",))[0]
                rot.append({**r, "responsavel": nome.get(resp, resp)})
            p["operacao"]["graficos"]["rotinas"] = {"tipo": "tabela", "titulo": "Rotinas: execuções, erros e responsável",
                                                    "sql": sql_rot, "linhas": rot}
            sql_er = "SELECT COUNT(*) FROM rotinas_execucoes WHERE status='erro' AND fim>=?"
            p["operacao"]["indicadores"]["erros_24h"] = _ind(
                c.execute(sql_er, ((agora - timedelta(hours=24)).isoformat(timespec="seconds"),)).fetchone()[0], sql_er,
                "Rotinas com erro (24 h)")
        nunca = sorted(set(ROTINAS) - {r["nome"] for r in p["operacao"]["graficos"].get("rotinas", {}).get("linhas", [])})
        p["operacao"]["indicadores"]["sem_registro"] = _ind(len(nunca), "ROTINAS (robo/rotinas.py) sem linha em rotinas_execucoes",
                                                            "Rotinas ainda sem registro", detalhe=", ".join(nunca))
        sql_tab = "SELECT name FROM sqlite_master WHERE type='table'"
        tamanhos = []
        for t in sorted(tem):
            if t.startswith("sqlite_") or t.startswith("paineis_"):  # os próprios registros do painel não entram na conta
                continue
            tamanhos.append({"tabela": t, "linhas": c.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]})
        tamanhos.sort(key=lambda x: -x["linhas"])
        p["operacao"]["graficos"]["tabelas"] = {"tipo": "tabela", "titulo": "Memória: linhas por tabela (maiores)",
                                                "sql": sql_tab + "  -- + COUNT(*) de cada", "linhas": tamanhos[:15]}
        p["operacao"]["indicadores"]["registros"] = _ind(sum(x["linhas"] for x in tamanhos), sql_tab, "Registros na memória",
                                                         detalhe=f"em {len(tamanhos)} tabelas")
    _escrever_achados(p)
    return {"montado_em": agora.isoformat(timespec="seconds"), "autor": AUTOR, "autor_nome": POR_ID[AUTOR]["nome"],
            "paginas": [{"id": k, **p[k]} for k, _ in PAGINAS]}


def _escrever_achados(p: dict) -> None:
    """Frases de leitura executiva, só com o que os números mostram."""
    e = p["executiva"]["indicadores"]
    if "tentativas" in e and e["tentativas"]["valor"]:
        p["executiva"]["achados"].append(
            f"{_pct(e['taxa_acerto']['valor'])} de acerto em {e['tentativas']['valor']} tentativas de treino "
            f"({e['ativos']['valor']} funcionários já treinaram).")
        niveis = p["executiva"]["graficos"]["por_nivel"]["linhas"]
        pior = min(niveis, key=lambda x: x["taxa"]) if niveis else None
        if pior and pior["taxa"] < 0.95:
            p["executiva"]["achados"].append(f"O nível {pior['nivel']} é onde a empresa mais erra ({_pct(pior['taxa'])}): "
                                             f"é ali que o treino mais ensina.")
    else:
        p["executiva"]["achados"].append("Ainda não há tentativas de treino registradas: o painel enche quando o treino rodar.")
    t = p["treino"]["indicadores"]
    if "subidas" in t:
        p["treino"]["achados"].append(f"{t['subidas']['valor']} subidas e {t['quedas']['valor']} quedas de nível registradas.")
    rot = p["operacao"]["indicadores"]
    if rot["sem_registro"]["valor"]:
        p["operacao"]["achados"].append(f"{rot['sem_registro']['valor']} rotina(s) ainda sem registro: "
                                        f"{rot['sem_registro']['detalhe']}.")
    if rot.get("erros_24h", {}).get("valor"):
        p["operacao"]["achados"].append(f"{rot['erros_24h']['valor']} execução(ões) de rotina terminaram em erro nas últimas 24 h.")


# =============================================================================== conferência (Heitor)
def reconciliar(cfg, painel: dict) -> list[str]:
    """Refaz os números por outro caminho. Devolve a lista de divergências (vazia = pode publicar)."""
    pag = {x["id"]: x for x in painel["paginas"]}
    divergencias = []

    def conferir(rotulo, publicado, refeito, tol=0.0):
        if publicado is None and refeito is None:
            return
        if publicado is None or refeito is None or abs(float(publicado) - float(refeito)) > tol:
            divergencias.append(f"{rotulo}: painel {publicado}, conferência {refeito}")

    with Trabalho(cfg).tx() as c:
        tem = _tabelas(c)
        if "treino_tentativas" in tem:
            e = pag["executiva"]
            linhas = c.execute("SELECT acertou, nivel, competencia, funcionario, tipo_erro FROM treino_tentativas").fetchall()
            total = len(linhas)
            acertos = sum(int(r["acertou"] or 0) for r in linhas)
            conferir("Tentativas", e["indicadores"]["tentativas"]["valor"], total)
            conferir("Taxa de acerto", e["indicadores"]["taxa_acerto"]["valor"], acertos / total if total else None, 1e-9)
            conferir("Funcionários que treinaram", e["indicadores"]["ativos"]["valor"], len({r["funcionario"] for r in linhas}))
            conferir("Soma por andar = total", sum(x["tentativas"] for x in e["graficos"]["por_andar"]["linhas"]), total)
            conferir("Acertos por andar = acertos", sum(x["acertos"] for x in e["graficos"]["por_andar"]["linhas"]), acertos)
            conferir("Soma por nível = total", sum(x["tentativas"] for x in e["graficos"]["por_nivel"]["linhas"]), total)
            conferir("Soma por competência = total",
                     sum(x["tentativas"] for x in pag["treino"]["graficos"]["por_competencia"]["linhas"]), total)
            conferir("Soma do ranking de pessoas = total",
                     sum(x["tentativas"] for x in pag["pessoas"]["graficos"]["ranking"]["linhas"]), total)
            erros_com_tipo = sum(1 for r in linhas if not r["acertou"] and (r["tipo_erro"] or "") != "")
            conferir("Soma dos erros por tipo = erros com tipo",
                     sum(x["n"] for x in pag["treino"]["graficos"]["erros"]["linhas"]), erros_com_tipo)
        elif pag["executiva"]["indicadores"].get("tentativas"):
            divergencias.append("O painel mostra tentativas de treino, mas o banco não tem a tabela treino_tentativas")
        if "interacoes" in tem:
            conferir("Conversas", (pag["executiva"]["indicadores"].get("conversas") or {}).get("valor"),
                     len(c.execute("SELECT id FROM interacoes").fetchall()))
            conferir("Soma por tipo de conversa = total",
                     sum(x["n"] for x in pag["conversas"]["graficos"]["por_tipo"]["linhas"]),
                     len(c.execute("SELECT id FROM interacoes").fetchall()))
        if "mentorias" in tem:
            conferir("Mentorias", pag["conversas"]["indicadores"]["mentorias"]["valor"],
                     len(c.execute("SELECT id FROM mentorias").fetchall()))
    from robo import organizacao
    conferir("Pessoas no quadro", pag["pessoas"]["indicadores"]["quadro"]["valor"], len(organizacao.lista(cfg)))
    conferir("Soma de pessoas por andar = quadro",
             sum(x["pessoas"] for x in pag["pessoas"]["graficos"]["headcount"]["linhas"]), len(organizacao.lista(cfg)))
    for x in painel["paginas"]:
        for chave, ind in x["indicadores"].items():
            if not ind.get("sql"):
                divergencias.append(f"{x['titulo']} › {ind['rotulo']}: número sem consulta de origem")
    return divergencias


# =============================================================================== publicação e manutenção
def _assinatura(painel: dict) -> str:
    conteudo = {k: v for k, v in painel.items() if k not in ("montado_em", "conferencia", "versao")}
    return hashlib.sha256(json.dumps(conteudo, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]


def _resumo_indicadores(painel: dict) -> dict:
    return {f"{x['id']}.{k}": v["valor"] for x in painel["paginas"] for k, v in x["indicadores"].items()}


def publicado(cfg) -> dict | None:
    try:
        return json.loads((pasta(cfg) / "painel.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def versoes(cfg, limite: int = 20) -> list[dict]:
    with _tb(cfg).tx() as c:
        return [dict(r) for r in c.execute("SELECT id, data_hora, autor, conferente, situacao, assinatura, paginas, divergencias "
                                           "FROM paineis_versoes ORDER BY id DESC LIMIT ?", (limite,))]


def rotina(cfg) -> dict:
    """Manutenção (de hora em hora): Bárbara monta, Heitor confere, e só então publica. Toda tentativa fica registrada."""
    from robo import leitura_bi
    tb = _tb(cfg)
    painel = construir(cfg)
    divergencias = reconciliar(cfg, painel)
    painel["planilhas"], div_planilhas = leitura_bi.analisar_tudo(cfg)   # Bárbara lê cada planilha; Heitor confere
    divergencias += div_planilhas
    _registrar_planilhas(tb, painel["planilhas"])
    assinatura = _assinatura(painel)
    anterior = publicado(cfg)
    situacao = "reprovado" if divergencias else ("sem_mudanca" if anterior and anterior.get("assinatura") == assinatura
                                                 else "publicado")
    with tb.tx() as c:
        cur = c.execute("INSERT INTO paineis_versoes (data_hora, autor, conferente, situacao, assinatura, paginas, indicadores, "
                        "divergencias) VALUES (?,?,?,?,?,?,?,?)",
                        (_agora(), AUTOR, CONFERENTE, situacao, assinatura, len(painel["paginas"]),
                         json.dumps(_resumo_indicadores(painel), ensure_ascii=False, default=str),
                         json.dumps(divergencias, ensure_ascii=False)))
        versao = cur.lastrowid
    if situacao == "publicado":
        painel.update({"assinatura": assinatura, "versao": versao,
                       "conferencia": {"conferente": CONFERENTE, "conferente_nome": POR_ID[CONFERENTE]["nome"],
                                       "divergencias": 0, "conferido_em": _agora()}})
        destino = pasta(cfg) / "painel.json"
        destino.parent.mkdir(parents=True, exist_ok=True)
        tmp = destino.with_suffix(".tmp")
        tmp.write_text(json.dumps(painel, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        tmp.replace(destino)
    estrela = atualizar_estrela(cfg) if situacao == "publicado" else None
    _avisar(cfg, situacao, painel, divergencias, anterior)
    return {"situacao": situacao, "versao": versao, "divergencias": divergencias, "estrela": estrela}


def _registrar_planilhas(tb, leituras: list[dict]) -> None:
    """Cada leitura nova (planilha nova ou conteúdo diferente) fica registrada para sempre — com o JSON inteiro,
    para treinar modelos no futuro (cabeçalho → tema/papel/regra)."""
    with tb.tx() as c:
        for le in leituras:
            if c.execute("SELECT 1 FROM paineis_planilhas WHERE nome=? AND assinatura=?", (le["nome"], le["assinatura"])).fetchone():
                continue
            c.execute("INSERT INTO paineis_planilhas (data_hora, nome, origem, assinatura, tema, linhas, colunas, regras_quebradas, "
                      "ancoras, leitura) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (_agora(), le["nome"], le["origem"], le["assinatura"], le["tema"]["nome"], le["linhas"], le["colunas_qtd"],
                       sum(1 for r in le["regras"] if r["nivel"] == "erro" and r["violacoes"]),
                       json.dumps(le["ancoras"], ensure_ascii=False, default=str),
                       json.dumps({k: v for k, v in le.items() if k != "amostra"}, ensure_ascii=False, default=str)))


def atualizar_estrela(cfg) -> dict | None:
    """Manutenção do modelo do Power BI: as mesmas tabelas do kit (powerbi/) refeitas em logs/paineis/estrela/.
    É o que o Power BI Desktop lê em "Obter dados → Pasta" para atualizar sem depender do banco na nuvem."""
    import importlib.util
    script = Path(__file__).resolve().parent.parent / "powerbi" / "exportar_estrela.py"
    if not script.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("exportar_estrela", script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.exportar(cfg, Path(cfg.logs) / "trabalho.db", pasta(cfg) / "estrela")
    except Exception as e:
        import logging
        logging.getLogger("robo").warning("Painéis: modelo estrela não atualizado (%s)", e)
        return {"erro": f"{type(e).__name__}: {e}"}


def _avisar(cfg, situacao, painel, divergencias, anterior) -> None:
    """Canal: divergência sempre; primeira publicação; e no máximo um resumo por dia (sem ruído de hora em hora)."""
    try:
        from robo.canal import Canal
        if situacao == "reprovado":
            Canal(cfg).postar(CONFERENTE, f"Segurei a publicação dos painéis: {len(divergencias)} número(s) não bateram — "
                              + "; ".join(divergencias[:3]) + ". O painel anterior continua no ar.", "excel", "alerta")
            return
        if situacao != "publicado":
            return
        ultimo_aviso = (anterior or {}).get("avisado_em")
        if anterior and ultimo_aviso and datetime.now() - datetime.fromisoformat(ultimo_aviso) < timedelta(hours=24):
            painel["avisado_em"] = ultimo_aviso
        else:
            ex = next(x for x in painel["paginas"] if x["id"] == "executiva")
            frase = ex["achados"][0] if ex["achados"] else "painéis atualizados"
            Canal(cfg).postar(AUTOR, f"Painéis atualizados (versão {painel['versao']}, conferida pelo Heitor sem divergência): "
                              f"{frase}", "excel", "entrega")
            painel["avisado_em"] = _agora()
        destino = pasta(cfg) / "painel.json"
        tmp = destino.with_suffix(".tmp")
        tmp.write_text(json.dumps(painel, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        tmp.replace(destino)
    except Exception:
        pass


# =============================================================================== provas do RH
def provas() -> dict:
    """Provas com resposta conhecida: banco montado à mão, números que a gente sabe de cabeça."""
    import tempfile
    from robo.config import Config
    with tempfile.TemporaryDirectory() as d:
        cfg = Config({"pastas": {k: str(Path(d) / k) for k in ("entrada", "logs", "agentes", "habilidades")},
                      "banco": {"habilitado": False}}, Path(d))
        cfg.criar_pastas()
        from robo import treino
        treino._tb(cfg)
        with Trabalho(cfg).tx() as c:
            for i, (pid, ok, nivel) in enumerate([("recepcao", 1, 1), ("recepcao", 0, 4), ("dba", 1, 2), ("dba", 1, 4)]):
                c.execute("INSERT INTO treino_tentativas (data_hora, funcionario, competencia, nivel, acertou, tipo_erro) "
                          "VALUES (?,?,?,?,?,?)", (_agora(), pid, "sql", nivel, ok, "" if ok else "achou outra coisa"))
        painel = construir(cfg)
        ex = next(x for x in painel["paginas"] if x["id"] == "executiva")
        limpo = reconciliar(cfg, painel)
        adulterado = json.loads(json.dumps(painel))
        next(x for x in adulterado["paginas"] if x["id"] == "executiva")["indicadores"]["tentativas"]["valor"] = 5
        pego = reconciliar(cfg, adulterado)
    return {
        "bi_powerbi": [("Conta as tentativas certo (4)", ex["indicadores"]["tentativas"]["valor"] == 4),
                       ("Taxa de acerto certa (75%)", abs(ex["indicadores"]["taxa_acerto"]["valor"] - 0.75) < 1e-9),
                       ("Todo indicador tem consulta de origem", all(i.get("sql") for x in painel["paginas"]
                                                                     for i in x["indicadores"].values())),
                       ("Monta as 5 páginas", len(painel["paginas"]) == 5)],
        "bi_reconciliacao": [("Painel correto passa sem divergência", not limpo),
                             ("Pega o número adulterado", any("Tentativas" in x for x in pego))],
    }
