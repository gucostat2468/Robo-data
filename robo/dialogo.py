"""Conversas entre funcionários — só quando há NECESSIDADE e um FATO registrado (robo/fatos.py). Nada de teatro.

Quando alguém fala com alguém:
  - pedido de ajuda: quem errou a mesma competência 2+ vezes hoje pede a quem já acertou (ou ao gestor);
  - cobrança do superior: rotina que terminou em erro, planilha barrada, fila travada, alerta da ronda de TI;
  - aviso técnico: a fábrica de planilhas mostra que a esteira errou um lote (com gabarito conferido).
Sem fato, o par não fala: o ciclo registra "sem assunto" (transparência, não enchimento).

Cada conversa tem 2 a 4 falas: quem precisa expõe o fato com a evidência, quem sabe responde com o que a empresa já
aprendeu (robo/aprendizados.py) ou admite que não há solução registrada, e o fechamento é sempre um COMPROMISSO
VERIFICÁVEL (refazer o caso, rodar a rotina, conferir o reenvio). A rotina confere depois se o compromisso foi cumprido
e fecha a conversa. Tudo em interacoes (com `dados` = fonte e id do fato), dialogo_conversas e dialogo_ciclos;
o canal do andar recebe a conversa completa.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from robo import organizacao
from robo.trabalho import Trabalho, _agora

PADRAO = {"habilitada": True, "intervalo_minutos": 20, "max_por_dia": 40, "max_por_ciclo": 3}
ESQUEMA = """
CREATE TABLE IF NOT EXISTS dialogo_conversas (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, fato_id TEXT UNIQUE, tipo TEXT, de TEXT, para TEXT, turnos INTEGER,
  compromisso TEXT, situacao TEXT, verificado_em TEXT, prova TEXT);
CREATE TABLE IF NOT EXISTS dialogo_ciclos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, fatos_avaliados INTEGER, conversas INTEGER, sem_assunto INTEGER,
  compromissos_verificados INTEGER);
"""
CONVERSAVEIS = ("erro_repetido_treino", "rotina_erro", "arquivo_reprovado", "alerta_ti", "fabrica_divergencia",
                "erro_recorrente", "fila_travada")
_prontos: set[str] = set()


def _c(cfg) -> dict:
    return {**PADRAO, **((getattr(cfg, "dados", {}) or {}).get("dialogo") or {})}


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    chave = str(Path(cfg.logs).resolve())
    if chave not in _prontos:
        from robo.trabalho import proteger
        with tb.tx() as c:
            c.executescript(ESQUEMA)
            proteger(c)
        _prontos.add(chave)
    return tb


def _nome(gente, pid) -> str:
    return (gente.get(pid) or {}).get("nome", pid or "")


def _nome_comp(comp: str) -> str:
    from robo.treino_casos import CATALOGO
    base = comp.split(":", 1)[-1]
    return CATALOGO[base].nome if base in CATALOGO else base.replace("_", " ")


def _hora(q) -> str:
    try:
        return datetime.fromisoformat(str(q).replace(" ", "T")[:19]).strftime("%H:%M")
    except ValueError:
        return str(q or "")


def _mentor(cfg, aprendiz: str, competencia: str, gente: dict) -> str | None:
    """Quem já ACERTOU essa competência (de preferência no mesmo andar); se ninguém, o gestor."""
    from robo import aprendizados
    with aprendizados._tb(cfg).tx() as c:
        quem = [r[0] for r in c.execute(
            "SELECT funcionario, COUNT(*) n FROM aprendizados WHERE competencia=? AND resultado='acerto' AND origem='treino' "
            "AND funcionario <> ? GROUP BY funcionario ORDER BY n DESC", (competencia, aprendiz))]
    andar = (gente.get(aprendiz) or {}).get("andar")
    mesmo = [q for q in quem if (gente.get(q) or {}).get("andar") == andar]
    escolhido = (mesmo or quem or [None])[0]
    if escolhido is None:
        g = organizacao.gestor_de(aprendiz)
        escolhido = g if g and g != "dono" else None
    return escolhido


def _ultimo_id(cfg, tabela: str) -> int:
    """O compromisso vale para o que acontecer DEPOIS dele: compara pelo id (a hora em segundos pode empatar)."""
    with Trabalho(cfg).tx() as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name=?", (tabela,)).fetchone():
            return 0
        return c.execute(f'SELECT COALESCE(MAX(id), 0) FROM "{tabela}"').fetchone()[0]


def _roteiro(cfg, fato: dict, gente: dict) -> dict | None:
    """Monta as falas e o compromisso de UM fato. None = não há quem fale (fica sem conversa, honestamente)."""
    from robo import aprendizados
    t, quem = fato["tipo"], fato["responsavel"]
    n = lambda pid: _nome(gente, pid)  # noqa: E731
    if t == "erro_repetido_treino":
        comp, _, causa = fato["detalhe"].partition("|")
        mentor = _mentor(cfg, quem, comp, gente)
        if not mentor or mentor == quem:
            return None
        licoes = [x for x in aprendizados.consultar(cfg, comp, {"tipo_erro": causa.split(":")[0]}, n=3, onde="dialogo", quem=mentor)
                  if x.get("correcao")]
        dica = (f"O que me ajudou foi isto: {licoes[0]['correcao']}" if licoes else
                "Não temos uma correção registrada para esse tipo de erro ainda, então eu prefiro olhar o próximo caso junto "
                "com você em vez de te dar uma regra que eu não tenho.")
        return {"de": quem, "para": mentor, "falas": [
            (quem, mentor, "pedido", f"{n(mentor)}, errei {fato['valor']} vezes hoje em {_nome_comp(comp)}. O último erro foi "
                                      f"{causa or 'sem tipo registrado'}. Você já acertou esse tipo de caso, pode me explicar como fez?"),
            (mentor, quem, "resposta", f"Posso sim, {n(quem)}. {dica}"),
            (quem, mentor, "compromisso", f"Combinado. Vou refazer um caso de {_nome_comp(comp)} no próximo treino e o resultado "
                                           "fica registrado."),
            (mentor, quem, "resposta", "Fechado. Eu confiro o resultado quando sair."),
        ], "compromisso": {"tipo": "acerto_treino", "funcionario": quem, "competencia": comp, "desde": _agora(),
                         "depois_de": _ultimo_id(cfg, "aprendizados")},
            "aprendizado": {"funcionario": quem, "competencia": comp, "causa": causa,
                            "correcao": licoes[0]["correcao"] if licoes else ""}}
    if t == "rotina_erro":
        gestor = organizacao.gestor_de(quem) if quem else None
        if not quem or not gestor or gestor == "dono":
            return None
        return {"de": gestor, "para": quem, "falas": [
            (gestor, quem, "cobranca", f"{n(quem)}, a rotina {fato['valor']} terminou em erro às {_hora(fato['quando'])}. "
                                        f"O registro diz: {fato['detalhe'] or 'sem detalhe'}. O que aconteceu e quando ela volta?"),
            (quem, gestor, "compromisso", f"Vi aqui, {n(gestor)}. Vou conferir a causa e a rotina {fato['valor']} roda de novo "
                                          "no próximo ciclo. Quando ela terminar sem erro, fica registrado."),
        ], "compromisso": {"tipo": "rotina_ok", "rotina": fato["valor"], "desde": _agora(),
                         "depois_de": _ultimo_id(cfg, "rotinas_execucoes")}}
    if t == "arquivo_reprovado":
        chefe = "coord_engenharia"
        with aprendizados._tb(cfg).tx() as c:
            motivo = c.execute("SELECT causa, correcao FROM aprendizados WHERE origem='pipeline' AND resultado='erro' "
                               "AND contexto LIKE ? ORDER BY id DESC LIMIT 1", (f'%"{fato["valor"]}"%',)).fetchone()
        explica = (f"O motivo principal foi este: {motivo['causa']}." + (f" {motivo['correcao']}" if motivo["correcao"] else "")
                   if motivo else "O relatório do arquivo está em Bases-Erros com cada linha que barrou.")
        return {"de": chefe, "para": "validacao", "falas": [
            (chefe, "validacao", "cobranca", f"{n('validacao')}, o arquivo {fato['valor']} foi barrado com {fato['detalhe']}. "
                                             "Qual foi o motivo e o que a área de origem precisa corrigir?"),
            ("validacao", chefe, "resposta", explica),
            ("validacao", chefe, "compromisso", "Quando a área reenviar o arquivo, eu confiro de novo e o resultado fica registrado."),
        ], "compromisso": {"tipo": "arquivo_aprovado", "arquivo": fato["valor"], "desde": _agora(),
                         "depois_de": _ultimo_id(cfg, "jobs")}}
    if t == "alerta_ti":
        chefe = organizacao.gestor_de(quem) or "coord_devops"
        if chefe == quem or chefe == "dono":
            chefe = "coord_devops" if quem != "coord_devops" else "ger_ti"
        return {"de": chefe, "para": quem, "falas": [
            (chefe, quem, "cobranca", f"{n(quem)}, a ronda de TI apontou isto na sua verificação: {fato['valor']}. "
                                      "Consegue resolver hoje?"),
            (quem, chefe, "compromisso", "Consigo. Vou corrigir a causa e a próxima ronda confirma se ficou limpo."),
        ], "compromisso": {"tipo": "ronda_limpa", "funcionario": quem, "desde": _agora()}}
    if t == "fabrica_divergencia":
        return {"de": "fab_coordenador", "para": "head_engenharia", "falas": [
            ("fab_coordenador", "head_engenharia", "aviso",
             f"{n('head_engenharia')}, a esteira errou o lote {fato['valor']}. {fato['detalhe']}. O gabarito foi conferido "
             "por outro caminho, então a falha é da esteira e não do lote."),
            ("head_engenharia", "fab_coordenador", "compromisso",
             "Entendido. A engenharia reproduz com a mesma semente, corrige a regra e o próximo lote dessa regra comprova."),
        ], "compromisso": {"tipo": "lote_ok", "regra": fato["detalhe"].split(":")[0], "desde": _agora(),
                         "depois_de": _ultimo_id(cfg, "fabrica_lotes")}}
    if t == "erro_recorrente":
        chefe = organizacao.gestor_de(quem) if quem else None
        if not quem or not chefe or chefe == "dono":
            return None
        return {"de": quem, "para": chefe, "falas": [
            (quem, chefe, "pedido", f"{n(chefe)}, o mesmo erro barrou {fato['valor']} arquivos hoje: {fato['detalhe']}. "
                                    "Preciso que a gente combine a correção com a área de origem."),
            (chefe, quem, "compromisso", "Vou levar para a área de origem e para a reunião do andar. Se o erro parar de "
                                         "aparecer, fica registrado como resolvido."),
        ], "compromisso": {"tipo": "erro_sumiu", "causa": fato["detalhe"], "desde": _agora()}}
    if t == "fila_travada":
        return {"de": "ger_operacoes", "para": "recepcao", "falas": [
            ("ger_operacoes", "recepcao", "cobranca", f"{n('recepcao')}, há {fato['valor']} arquivo(s) parados em Bases-Limpeza "
                                                      f"há mais de 30 minutos: {fato['detalhe']}. O que está travando?"),
            ("recepcao", "ger_operacoes", "compromisso", "Vou conferir se estão abertos no Excel ou ainda sincronizando. Quando a "
                                                         "fila andar, fica registrado."),
        ], "compromisso": {"tipo": "fila_vazia", "desde": _agora()}}
    return None


def _cumprido(cfg, comp: dict) -> tuple[bool, str] | None:
    """True/False quando dá para afirmar; None quando ainda não há como saber."""
    from robo import aprendizados, jobs
    t, desde = comp.get("tipo"), comp.get("desde")
    if t == "acerto_treino":
        with aprendizados._tb(cfg).tx() as c:
            r = c.execute("SELECT id, resultado FROM aprendizados WHERE funcionario=? AND competencia=? AND origem='treino' "
                          "AND id > ? ORDER BY id LIMIT 1", (comp["funcionario"], comp["competencia"], comp.get("depois_de", 0))).fetchone()
        return None if not r else (r["resultado"] == "acerto", f"aprendizados#{r['id']}")
    if t == "rotina_ok":
        with Trabalho(cfg).tx() as c:
            r = c.execute("SELECT id, status FROM rotinas_execucoes WHERE nome=? AND id > ? ORDER BY id LIMIT 1",
                          (comp["rotina"], comp.get("depois_de", 0))).fetchone() if c.execute(
                "SELECT 1 FROM sqlite_master WHERE name='rotinas_execucoes'").fetchone() else None
        return None if not r else (r["status"] == "fez", f"rotinas_execucoes#{r['id']}")
    if t == "arquivo_aprovado":
        with jobs._tb(cfg).tx() as c:
            r = c.execute("SELECT id, estado FROM jobs WHERE tipo='planilha' AND arquivo=? AND id > ? AND fim IS NOT NULL "
                          "ORDER BY id LIMIT 1", (comp["arquivo"], comp.get("depois_de", 0))).fetchone()
        return None if not r else (r["estado"] == "concluido", f"jobs#{r['id']}")
    if t == "lote_ok":
        with Trabalho(cfg).tx() as c:
            r = c.execute("SELECT id, estado FROM fabrica_lotes WHERE regra=? AND id > ? AND estado LIKE 'conferido%' "
                          "ORDER BY id LIMIT 1", (comp["regra"], comp.get("depois_de", 0))).fetchone()
        return None if not r else (r["estado"] == "conferido_ok", f"fabrica_lotes#{r['id']}")
    if t == "fila_vazia":
        from robo.fabrica import _fila_real
        return (True, "Bases-Limpeza vazia") if not _fila_real(cfg) else None
    if t == "ronda_limpa":
        from robo import ti
        ronda = ti.ultima_ronda(cfg) or {}
        if str(ronda.get("data_hora") or "").replace(" ", "T") <= str(desde):
            return None
        item = next((i for i in ronda.get("itens") or [] if i["id"] == comp["funcionario"]), None)
        return None if item is None else (not item.get("achados"), f"ronda {ronda.get('data_hora')}")
    if t == "erro_sumiu":
        dia = (datetime.fromisoformat(desde) + timedelta(days=1)).strftime("%Y-%m-%d")
        if datetime.now().strftime("%Y-%m-%d") <= dia:
            return None
        with aprendizados._tb(cfg).tx() as c:
            n = c.execute("SELECT COUNT(*) FROM aprendizados WHERE origem='pipeline' AND causa=? AND data_hora LIKE ?",
                          (comp["causa"], dia + "%")).fetchone()[0]
        return (n == 0, f"{n} erro(s) iguais em {dia}")
    return None


def verificar_compromissos(cfg) -> int:
    from robo import interacoes
    gente = organizacao.por_id(cfg)
    with _tb(cfg).tx() as c:
        abertos = [dict(r) for r in c.execute("SELECT * FROM dialogo_conversas WHERE situacao='aberto'")]
    feitos = 0
    for a in abertos:
        comp = json.loads(a["compromisso"] or "{}")
        r = _cumprido(cfg, comp)
        if r is None:
            continue
        ok, prova = r
        with _tb(cfg).tx() as c:
            c.execute("UPDATE dialogo_conversas SET situacao=?, verificado_em=?, prova=? WHERE id=? AND situacao='aberto'",
                      ("cumprido" if ok else "nao_cumprido", _agora(), prova, a["id"]))
        texto = (f"{_nome(gente, a['de'])}, o combinado foi cumprido. A prova está em {prova}." if ok else
                 f"{_nome(gente, a['de'])}, o combinado ainda não deu certo. O registro {prova} mostra isso, e eu sigo nisso.")
        interacoes.falar(cfg, a["para"], a["de"], texto, "fechamento", f"dialogo:{a['fato_id']}",
                         dados={"fonte": "dialogo_conversas", "id": a["id"], "prova": prova})
        feitos += 1
    return feitos


def conversar_sobre(cfg, fato: dict) -> dict | None:
    from robo import aprendizados, interacoes, voz
    gente = organizacao.por_id(cfg)
    roteiro = _roteiro(cfg, fato, gente)
    if not roteiro:
        return None
    with _tb(cfg).tx() as c:
        try:
            cid = c.execute("INSERT INTO dialogo_conversas (data_hora, fato_id, tipo, de, para, turnos, compromisso, situacao) "
                            "VALUES (?,?,?,?,?,?,?,?)", (_agora(), fato["id"], fato["tipo"], roteiro["de"], roteiro["para"],
                                                         len(roteiro["falas"]), json.dumps(roteiro["compromisso"], ensure_ascii=False),
                                                         "aberto")).lastrowid
        except Exception:  # fato já conversado (UNIQUE): ninguém fala duas vezes da mesma coisa
            return None
    dados = {"fonte": fato["fonte"], "id": fato["id"], "tipo": fato["tipo"], "conversa": cid}
    for de, para, tipo, texto in roteiro["falas"]:
        interacoes.falar(cfg, de, para, voz.limpar(texto), tipo, f"dialogo:{fato['id']}", dados=dados)
    if roteiro.get("aprendizado"):
        a = roteiro["aprendizado"]
        aprendizados.registrar(cfg, a["funcionario"], a["competencia"], "quase", acao="conversa com quem já acertou",
                               causa=a["causa"], correcao=a["correcao"], evidencia_id=f"dialogo_conversas#{cid}", origem="dialogo",
                               contexto={"mentor": roteiro["para"]})
    return {"conversa": cid, "tipo": fato["tipo"], "de": roteiro["de"], "para": roteiro["para"], "turnos": len(roteiro["falas"])}


def rotina(cfg) -> dict | None:
    from robo import fatos as fonte
    c = _c(cfg)
    if not c["habilitada"]:
        return None
    tb = _tb(cfg)
    with tb.tx() as conn:
        ultimo = conn.execute("SELECT MAX(data_hora) FROM dialogo_ciclos").fetchone()[0]
        hoje = conn.execute("SELECT COUNT(*) FROM dialogo_conversas WHERE data_hora LIKE ?",
                            (datetime.now().strftime("%Y-%m-%d") + "%",)).fetchone()[0]
        conversados = {r[0] for r in conn.execute("SELECT fato_id FROM dialogo_conversas")}
    if ultimo and datetime.now() - datetime.fromisoformat(ultimo) < timedelta(minutes=float(c["intervalo_minutos"])):
        return None
    verificados = verificar_compromissos(cfg)
    lista = [f for f in fonte.fatos_do_dia(cfg) if f["tipo"] in CONVERSAVEIS and f["id"] not in conversados]
    feitas = []
    for f in lista:
        if len(feitas) >= int(c["max_por_ciclo"]) or hoje + len(feitas) >= int(c["max_por_dia"]):
            break
        r = conversar_sobre(cfg, f)
        if r:
            feitas.append(r)
    with tb.tx() as conn:
        conn.execute("INSERT INTO dialogo_ciclos (data_hora, fatos_avaliados, conversas, sem_assunto, compromissos_verificados) "
                     "VALUES (?,?,?,?,?)", (_agora(), len(lista), len(feitas), int(not feitas), verificados))
    # sem assunto o ciclo fica registrado em dialogo_ciclos, mas NÃO conta como trabalho (a rotina fica "em dia")
    return {"conversas": feitas, "verificados": verificados} if (feitas or verificados) else None
