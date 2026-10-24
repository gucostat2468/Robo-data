"""Treino contínuo: todos os funcionários trabalham o tempo todo em casos sintéticos com resposta conhecida, cada um no
seu nível, e a dificuldade sobe com a evolução. Nada do que acontece aqui se perde.

Quem faz o quê (Sala de Casos, 4º andar — responde direto ao dono, para não avaliar quem é seu chefe):
  Otávio (head)            certifica os designers e responde pelo catálogo de competências;
  Lívia, Murilo, Raquel,   designers de casos: geram os casos de treino da sua área. Só geram competência em que estão
  Augusto (designers)      CERTIFICADOS (passaram no exame dos 5 níveis, inclusive o desafio — por isso "sabem mais que
                           todo mundo"). Caso reprovado na revisão conta contra o designer; 2 reprovações nos últimos 10
                           casos suspendem a certificação até refazer o exame;
  Valéria (revisora)       revisa CADA caso antes de ir para alguém: refaz o caso pela semente (tem que dar igual), refaz o
                           gabarito por outro caminho e confirma que a sujeira do nível foi plantada. Ela não gera casos
                           (ninguém aprova o próprio trabalho);
  Yasmin (planejamento)    distribui: quem está há mais tempo sem treinar recebe primeiro, na competência que está há mais
                           tempo sem praticar, no NÍVEL da pessoa.

Níveis (1 básico → 5 desafio), por pessoa e por competência:
  começa pelo cargo (estagiário/júnior 1, pleno/sênior 2, especialista/coordenador/gerente/diretor 3, head 4);
  a cada 5 tentativas no nível: 4 ou 5 certas (≥ 80%) → sobe; 2 ou menos (≤ 40%) → desce. Toda mudança fica registrada
  com as tentativas que a provaram (treino_niveis_eventos).

Cada tentativa (treino_tentativas, imutável): quem, cargo, andar, competência, nível, caso, acertou, nota, tipo de erro,
detalhe, resposta, tempo e a VERSÃO DO CÓDIGO do robô — base pronta para Machine Learning.
Erro vira: experiência de erro na memória da pessoa + lição no caderno dela (aplicada só quando ela acertar a mesma
competência no mesmo nível ou acima) + handover para a área dona da ferramenta quando o mesmo erro se repete 3 vezes.

O que é sintético e o que é real (honestidade): os DADOS dos casos são sintéticos. A ferramenta usada, a correção, os
registros, os níveis e as lições são reais. Os funcionários são papéis que usam o código do robô; o que muda o
comportamento é o código ser corrigido (handover → TI), as regras aprendidas aprovadas por você e o caderno de lições.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import shutil
import threading
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from robo import organizacao
from robo.trabalho import Trabalho, _agora, proteger
from robo.treino_casos import CATALOGO, NIVEIS, conteudo_hash

log = logging.getLogger("robo")

PADRAO = {"habilitado": True, "intervalo_minutos": 2, "por_rodada": 15, "janela_nivel": 5, "sobe_com": 4, "desce_com": 2,
          "erros_para_handover": 3, "max_tentativas_por_caso": 12, "dias_caso_ativo": 7}
# Começa perto do limite do cargo (pedido do dono: treino difícil de verdade). Os níveis 1 a 3 davam quase 100% de
# acerto: não mostravam quem sabe. Daqui o nível sobe ou desce pela evidência (4 de 5 certas sobe; 2 de 5 desce).
NIVEL_INICIAL = {"estagiario": 2, "junior": 3, "pleno": 3, "senior": 4, "especialista": 4, "coordenador": 4, "gerente": 4,
                 "diretor": 4, "head": 5}
RECALIBRACAO = "recalibração: treino endurecido a pedido do dono (começa perto do limite do cargo)"

SALA = {"head": "head_casos", "revisor": "casos_revisor", "planejador": "casos_planejamento",
        "designers": ["casos_engenharia", "casos_analytics", "casos_governanca", "casos_ti"]}
EQUIPE_SALA = {SALA["head"], SALA["revisor"], SALA["planejador"], *SALA["designers"]}

ESQUEMA = """
CREATE TABLE IF NOT EXISTS treino_casos (
  id TEXT PRIMARY KEY, criado_em TEXT, competencia TEXT, nivel INTEGER, semente INTEGER, versao_gerador TEXT, designer TEXT,
  resumo TEXT, parametros TEXT, gabarito TEXT, arquivo TEXT, conteudo_sha256 TEXT, estado TEXT DEFAULT 'proposto',
  revisor TEXT, revisado_em TEXT, revisao TEXT, versao_codigo TEXT, encerrado_em TEXT, arquivo_guardado TEXT);
CREATE INDEX IF NOT EXISTS ix_tc_pool ON treino_casos(competencia, nivel, estado);
CREATE TABLE IF NOT EXISTS treino_tentativas (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, rodada TEXT, caso_id TEXT, funcionario TEXT, andar INTEGER,
  cargo_nivel TEXT, competencia TEXT, nivel INTEGER, ferramenta TEXT, acertou INTEGER, nota REAL, tipo_erro TEXT,
  detalhe TEXT, resposta TEXT, segundos REAL, versao_codigo TEXT);
CREATE INDEX IF NOT EXISTS ix_tt_func ON treino_tentativas(funcionario, competencia, id);
CREATE INDEX IF NOT EXISTS ix_tt_caso ON treino_tentativas(caso_id);
CREATE TRIGGER IF NOT EXISTS treino_tentativas_imutavel BEFORE UPDATE ON treino_tentativas
BEGIN SELECT RAISE(ABORT, 'tentativa de treino não muda depois de gravada'); END;
CREATE TABLE IF NOT EXISTS treino_niveis (
  funcionario TEXT, competencia TEXT, nivel INTEGER, desde TEXT, PRIMARY KEY (funcionario, competencia));
CREATE TABLE IF NOT EXISTS treino_niveis_eventos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, funcionario TEXT, competencia TEXT, de INTEGER, para INTEGER,
  motivo TEXT, evidencia TEXT);
CREATE TRIGGER IF NOT EXISTS treino_niveis_eventos_imutavel BEFORE UPDATE ON treino_niveis_eventos
BEGIN SELECT RAISE(ABORT, 'histórico de nível não muda'); END;
CREATE TABLE IF NOT EXISTS treino_certificacoes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, designer TEXT, competencia TEXT, versao_gerador TEXT, ok INTEGER,
  detalhe TEXT, revisor TEXT);
"""
_prontos: set[str] = set()
_rodando = threading.Lock()
_versao: str | None = None


def _c(cfg) -> dict:
    return {**PADRAO, **((getattr(cfg, "dados", {}) or {}).get("treino") or {})}


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    if str(tb.arquivo) not in _prontos or not tb.arquivo.exists():
        with tb.tx() as c:
            c.executescript(ESQUEMA)
            proteger(c)
        _prontos.add(str(tb.arquivo))
    return tb


def versao_codigo() -> str:
    """Impressão digital do código do robô (todos os .py): diz qual versão produziu cada resultado."""
    global _versao
    if _versao is None:
        h = hashlib.sha256()
        for p in sorted(Path(__file__).parent.rglob("*.py")):
            h.update(p.name.encode())
            h.update(p.read_bytes())
        _versao = h.hexdigest()[:12]
    return _versao


def pasta(cfg) -> Path:
    return Path(cfg.logs) / "treino"


def _sandbox(cfg, destino: Path, banco: bool = False):
    """Computador de teste: pastas próprias, sem regras de produção e (salvo SQL) sem banco. Nada vaza para a produção."""
    from robo.config import Config
    dados = copy.deepcopy(cfg.dados)
    dados["regras"] = []
    dados["pastas"] = {"entrada": str(destino / "entrada"), "logs": str(destino / "logs"), "agentes": str(destino / "agentes"),
                       "habilidades": str(destino / "habilidades")}
    dados["banco"] = {**(dados.get("banco") or {}), "habilitado": bool(banco and (cfg.banco or {}).get("habilitado"))}
    (destino / "entrada").mkdir(parents=True, exist_ok=True)
    return Config(dados, cfg.base)


# =============================================================================== quem treina o quê
def elegiveis(cfg) -> list[dict]:
    """Todo funcionário, de todos os andares — inclusive a Sala de Casos, que treina a revisão de casos."""
    return list(organizacao.lista(cfg))


def competencias_de(pid: str, cfg) -> list[str]:
    """A Sala de Casos treina SÓ a revisão de casos (o resto ela mesma produz e certifica); os demais, o contrato."""
    banco = bool((cfg.banco or {}).get("habilitado"))
    comps = [c.id for c in CATALOGO.values() if organizacao.pode_usar(pid, c.ferramenta, cfg) and (banco or not c.requer_banco)]
    if pid in EQUIPE_SALA:
        return [c for c in comps if CATALOGO[c].ferramenta == "revisar_caso"]
    return [c for c in comps if CATALOGO[c].ferramenta != "revisar_caso"]


def nivel_atual(cfg, pid: str, comp: str, c=None) -> int:
    def ler(conn):
        r = conn.execute("SELECT nivel FROM treino_niveis WHERE funcionario=? AND competencia=?", (pid, comp)).fetchone()
        if r:
            return int(r["nivel"])
        p = organizacao.por_id(cfg).get(pid) or {}
        inicial = NIVEL_INICIAL.get(organizacao.nivel_de(pid, p), 2)
        conn.execute("INSERT INTO treino_niveis (funcionario, competencia, nivel, desde) VALUES (?,?,?,?)",
                     (pid, comp, inicial, _agora()))
        conn.execute("INSERT INTO treino_niveis_eventos (data_hora, funcionario, competencia, de, para, motivo, evidencia) "
                     "VALUES (?,?,?,?,?,?,?)", (_agora(), pid, comp, None, inicial, "nível inicial pelo cargo",
                                                organizacao.nivel_de(pid, p)))
        return inicial
    if c is not None:
        return ler(c)
    with _tb(cfg).tx() as conn:
        return ler(conn)


def recalibrar(cfg) -> int:
    """Uma vez só: quem está abaixo do novo nível inicial do cargo sobe até ele, com o evento registrado (de, para,
    motivo). Nunca desce ninguém. Devolve quantos níveis mudaram."""
    gente = organizacao.por_id(cfg)
    mudou = 0
    with _tb(cfg).tx() as conn:
        if conn.execute("SELECT 1 FROM treino_niveis_eventos WHERE motivo=? LIMIT 1", (RECALIBRACAO,)).fetchone():
            return 0
        for r in conn.execute("SELECT funcionario, competencia, nivel FROM treino_niveis").fetchall():
            p = gente.get(r["funcionario"]) or {}
            alvo = NIVEL_INICIAL.get(organizacao.nivel_de(r["funcionario"], p), 3)
            if int(r["nivel"]) < alvo:
                conn.execute("UPDATE treino_niveis SET nivel=?, desde=? WHERE funcionario=? AND competencia=?",
                             (alvo, _agora(), r["funcionario"], r["competencia"]))
                conn.execute("INSERT INTO treino_niveis_eventos (data_hora, funcionario, competencia, de, para, motivo, "
                             "evidencia) VALUES (?,?,?,?,?,?,?)", (_agora(), r["funcionario"], r["competencia"],
                                                                   int(r["nivel"]), alvo, RECALIBRACAO, "cargo"))
                mudou += 1
        if not mudou:  # marca que já foi feita, mesmo sem nada para subir
            conn.execute("INSERT INTO treino_niveis_eventos (data_hora, funcionario, competencia, de, para, motivo, "
                         "evidencia) VALUES (?,?,?,?,?,?,?)", (_agora(), "", "", None, None, RECALIBRACAO, "nada a subir"))
    return mudou


# =============================================================================== Sala de Casos: certificação e revisão
def certificado(cfg, designer: str, comp: str) -> bool:
    """Certificação válida = exame aprovado na versão atual do gerador e menos de 2 reprovações nos últimos 10 casos."""
    versao = CATALOGO[comp].versao
    with _tb(cfg).tx() as c:
        ult = c.execute("SELECT id, data_hora, ok FROM treino_certificacoes WHERE designer=? AND competencia=? AND versao_gerador=? "
                        "ORDER BY id DESC LIMIT 1", (designer, comp, versao)).fetchone()
        if not ult or not ult["ok"]:
            return False
        estados = [r["estado"] for r in c.execute(
            "SELECT estado FROM treino_casos WHERE designer=? AND competencia=? AND criado_em>=? AND estado IN "
            "('validado','reprovado','encerrado') ORDER BY criado_em DESC LIMIT 10", (designer, comp, ult["data_hora"]))]
    return sum(e == "reprovado" for e in estados) < 2


def certificar(cfg, designer: str, comp: str) -> dict:
    """Exame do designer: um caso de CADA nível (1 a 5), todos revisados pela revisora. Só passa se os 5 passarem."""
    from robo import memoria
    c = CATALOGO[comp]
    if designer != c.designer:
        raise PermissionError(f"{designer} não é o designer de {comp}")
    resultados = []
    for nivel in NIVEIS:
        caso = criar_caso(cfg, comp, nivel, semente=900_000 + 101 * nivel + int(time.time()) % 997, exame=True)
        resultados.append((nivel, caso["estado"], (caso.get("revisao") or {}).get("problemas") or []))
    ok = all(e == "validado" for _, e, _ in resultados)
    detalhe = "; ".join(f"nível {n}: {'ok' if e == 'validado' else 'reprovado — ' + '; '.join(p)[:200]}" for n, e, p in resultados)
    with _tb(cfg).tx() as conn:
        conn.execute("INSERT INTO treino_certificacoes (data_hora, designer, competencia, versao_gerador, ok, detalhe, revisor) "
                     "VALUES (?,?,?,?,?,?,?)", (_agora(), designer, comp, c.versao, int(ok), detalhe, SALA["revisor"]))
    memoria.experiencia(cfg, designer, "acerto" if ok else "erro",
                        f"Exame de certificação em {c.nome} (5 níveis): {'aprovado' if ok else 'reprovado'}", "treino", comp)
    if not ok:
        memoria.handover(cfg, f"Sala de Casos: exame de {c.nome} reprovado ({detalhe[:300]})", f"treino_{comp}",
                         SALA["revisor"], "certificação de designer", responsavel=designer)
    return {"ok": ok, "detalhe": detalhe}


def criar_caso(cfg, comp: str, nivel: int, semente: int | None = None, exame: bool = False) -> dict:
    """Designer gera → revisora confere. Devolve o caso com estado 'validado' ou 'reprovado' (e o motivo)."""
    from robo import memoria
    c = CATALOGO[comp]
    semente = int(semente if semente is not None else time.time_ns() % 1_000_000_007)
    cid = f"CASO-{comp}-n{nivel}-{semente}"
    destino = pasta(cfg) / "casos" / cid
    if destino.exists():
        shutil.rmtree(destino, ignore_errors=True)
    destino.mkdir(parents=True)
    caso = c.gerar(nivel, semente, destino, cfg)
    caso.update({"id": cid, "competencia": comp, "nivel": nivel, "semente": semente})
    sha = conteudo_hash(caso.get("arquivo"), caso["gabarito"])
    with _tb(cfg).tx() as conn:
        conn.execute("INSERT INTO treino_casos (id, criado_em, competencia, nivel, semente, versao_gerador, designer, resumo, "
                     "parametros, gabarito, arquivo, conteudo_sha256, estado, versao_codigo) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (cid, _agora(), comp, nivel, semente, c.versao, c.designer, caso.get("resumo", ""),
                      json.dumps(caso["parametros"], ensure_ascii=False, default=str),
                      json.dumps(caso["gabarito"], ensure_ascii=False, default=str), caso.get("arquivo"), sha, "proposto",
                      versao_codigo()))
    revisao = revisar(cfg, caso, sha)
    caso.update({"estado": "validado" if revisao["ok"] else "reprovado", "revisao": revisao})
    if not exame:
        memoria.experiencia(cfg, c.designer, "acerto" if revisao["ok"] else "erro",
                            f"Caso {cid} {'aprovado' if revisao['ok'] else 'reprovado'} na revisão", "treino", cid)
    if not revisao["ok"]:
        memoria.handover(cfg, f"Sala de Casos: caso de {c.nome} reprovado na revisão — {'; '.join(revisao['problemas'])[:300]}",
                         f"treino_{comp}", SALA["revisor"], cid, responsavel=c.designer)
        _guardar(cfg, cid, destino, motivo="reprovado")
    return caso


def revisar(cfg, caso: dict, sha: str) -> dict:
    """Valéria (revisora, nunca a designer): 1) refaz pela semente e compara; 2) gabarito por outro caminho; 3) plantio."""
    from robo.treino_casos import revisao_independente  # a mesma revisão que a Sala treina (ferramenta revisar_caso)
    problemas = revisao_independente(caso, cfg, sha, pasta(cfg) / "revisao" / caso["id"])["problemas"]
    revisao = {"ok": not problemas, "problemas": problemas, "revisor": SALA["revisor"], "data_hora": _agora()}
    with _tb(cfg).tx() as conn:
        conn.execute("UPDATE treino_casos SET estado=?, revisor=?, revisado_em=?, revisao=? WHERE id=?",
                     ("validado" if not problemas else "reprovado", SALA["revisor"], _agora(),
                      json.dumps(revisao, ensure_ascii=False), caso["id"]))
    return revisao


def _guardar(cfg, cid: str, destino: Path, motivo: str) -> str | None:
    """Caso com erro (de alguém ou da revisão) é guardado compactado para sempre; o resto é refeito pela semente."""
    if not destino.exists():
        return None
    arq = pasta(cfg) / "arquivo" / f"{cid}.zip"
    arq.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(arq, "w", zipfile.ZIP_DEFLATED) as z:
        for p in destino.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(destino))
    shutil.rmtree(destino, ignore_errors=True)
    with _tb(cfg).tx() as conn:
        conn.execute("UPDATE treino_casos SET arquivo_guardado=? WHERE id=?", (str(arq), cid))
    return str(arq)


def _carregar(row) -> dict:
    return {"id": row["id"], "competencia": row["competencia"], "nivel": row["nivel"], "semente": row["semente"],
            "parametros": json.loads(row["parametros"]), "gabarito": json.loads(row["gabarito"]), "arquivo": row["arquivo"],
            "resumo": row["resumo"]}


def obter_caso(cfg, comp: str, nivel: int, pid: str) -> dict | None:
    """Caso validado que esta pessoa ainda não fez (o mesmo caso para todos do nível = comparação justa)."""
    c = CATALOGO[comp]
    with _tb(cfg).tx() as conn:
        row = conn.execute("SELECT * FROM treino_casos WHERE competencia=? AND nivel=? AND versao_gerador=? AND estado='validado' "
                           "AND id NOT IN (SELECT caso_id FROM treino_tentativas WHERE funcionario=?) ORDER BY criado_em LIMIT 1",
                           (comp, nivel, c.versao, pid)).fetchone()
    if row:
        params = json.loads(row["parametros"])
        intacto = (not row["arquivo"] or Path(row["arquivo"]).exists()) and ("logs" not in params or Path(params["logs"]).exists())
        if intacto:
            caso = _carregar(row)
            problemas = _ainda_vale(c, caso, row, cfg)
            if not problemas:
                return caso
            motivo = "caso desatualizado na reconferência: " + "; ".join(problemas)[:500]
        else:
            motivo = "arquivos do caso sumiram (refazível pela semente)"
        with _tb(cfg).tx() as conn:  # sai da fila com o motivo; não trava nem reprova ninguém injustamente
            conn.execute("UPDATE treino_casos SET estado='encerrado', encerrado_em=?, revisao=? WHERE id=?",
                         (_agora(), json.dumps({"encerrado_por": SALA["revisor"], "motivo": motivo}, ensure_ascii=False),
                          row["id"]))
        return obter_caso(cfg, comp, nivel, pid)  # o próximo da fila, ou um caso novo
    if not certificado(cfg, c.designer, comp):
        r = certificar(cfg, c.designer, comp)
        if not r["ok"]:
            return None
    for _ in range(3):
        caso = criar_caso(cfg, comp, nivel)
        if caso["estado"] == "validado":
            return caso
    return None


REVALIDAR_APOS_MIN = 30


def _ainda_vale(c, caso: dict, row, cfg) -> list[str]:
    """Reconferência do revisor antes de REUSAR um caso guardado: a verdade de alguns casos depende de agora (janela
    de 7 dias do desempenho, quadro de funcionários, rotinas existentes). Achado no treino endurecido: casos de dias
    atrás reprovavam quem acertava. Caso recém-criado (menos de 30 min) não precisa."""
    try:
        if datetime.now() - datetime.fromisoformat(row["criado_em"]) < timedelta(minutes=REVALIDAR_APOS_MIN):
            return []
        return list(c.conferir({**caso, "nivel": caso["nivel"], "semente": caso["semente"]}, cfg) or [])
    except Exception as e:
        return [f"reconferência quebrou ({type(e).__name__}: {e})"]


# =============================================================================== a tentativa
def tentar(cfg, pid: str, comp: str, caso: dict, rodada: str = "") -> dict:
    from robo import licoes, memoria
    c = CATALOGO[comp]
    gente = organizacao.por_id(cfg)
    p = gente.get(pid) or {}
    destino = pasta(cfg) / "sandbox" / f"{rodada or 'avulsa'}_{pid}"
    shutil.rmtree(destino, ignore_errors=True)
    t0 = time.perf_counter()
    try:
        sb = _sandbox(cfg, destino, banco=c.requer_banco)
        resposta = c.executar(cfg, sb, pid, caso)
        acertou, nota, tipo, detalhe = c.corrigir(caso, resposta)
    except Exception as e:
        log.exception("Treino: %s quebrou no caso %s", comp, caso["id"])  # vira erro de sistema (registro permanente)
        resposta = {"texto": f"{type(e).__name__}: {e}"}
        acertou, nota, tipo, detalhe = False, 0.0, "excecao_no_treino", f"{type(e).__name__}: {e}"
    finally:
        shutil.rmtree(destino, ignore_errors=True)
    seg = round(time.perf_counter() - t0, 3)
    resumo_resp = {"ok": resposta.get("ok"), "natureza": resposta.get("natureza"), "texto": str(resposta.get("texto", ""))[:1500],
                   "evidencia": resposta.get("evidencia")}
    with _tb(cfg).tx() as conn:
        cur = conn.execute("INSERT INTO treino_tentativas (data_hora, rodada, caso_id, funcionario, andar, cargo_nivel, competencia, "
                           "nivel, ferramenta, acertou, nota, tipo_erro, detalhe, resposta, segundos, versao_codigo) "
                           "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (_agora(), rodada, caso["id"], pid, p.get("andar"), organizacao.nivel_de(pid, p), comp,
                            caso["nivel"], c.ferramenta, int(bool(acertou)), float(nota), tipo or None, detalhe[:1000],
                            json.dumps(resumo_resp, ensure_ascii=False, default=str), seg, versao_codigo()))
        tid = cur.lastrowid
    memoria.experiencia(cfg, pid, "acerto" if acertou else "erro",
                        f"Treino {c.nome} nível {caso['nivel']}: {'acertou' if acertou else 'errou'} — {detalhe[:160]}", "treino",
                        f"{caso['id']}#T{tid}")
    if not acertou:
        _aprender_com_o_erro(cfg, pid, p, c, caso, tipo, detalhe)
    try:
        from robo import aprendizados
        aprendizados.registrar(cfg, pid, f"treino:{comp}", "acerto" if acertou else "erro", acao=f"caso {caso['id']}",
                               causa="" if acertou else (tipo or "erro sem tipo") + (f": {detalhe[:300]}" if detalhe else ""),
                               nivel=caso["nivel"], evidencia_id=f"T{tid}", origem="treino",
                               contexto={"competencia": comp, "tipo_erro": tipo or ""})
    except Exception:
        log.debug("Aprendizado do treino não registrado", exc_info=True)
    mudanca = ajustar_nivel(cfg, pid, comp)
    r = {"tentativa": tid, "funcionario": pid, "competencia": comp, "nivel": caso["nivel"], "acertou": bool(acertou),
         "nota": nota, "tipo_erro": tipo, "detalhe": detalhe, "segundos": seg, "mudanca_nivel": mudanca}
    from robo import interacoes
    interacoes.apos_tentativa(cfg, r)  # mentoria do erro, fechamento da mentoria anterior, troca ao subir de nível
    return r


def colegas_que_aprendem(cfg, pid: str, comp: str, limite: int = 12) -> list[str]:
    """Quem é da MESMA área de quem errou e também treina esta competência (estagiários incluídos: estudar é
    observar). Limite para a lição não virar ruído para a empresa inteira."""
    area = organizacao.area_de(pid)
    gente = [p for p in organizacao.lista(cfg) if p["id"] != pid and organizacao.area_de(p["id"]) == area]
    return [p["id"] for p in gente if comp in competencias_de(p["id"], cfg)][:limite]


def _aprender_com_o_erro(cfg, pid, p, c, caso, tipo, detalhe) -> None:
    from robo import licoes, memoria
    ref = f"{c.id}:{caso['nivel']}:{tipo}"
    lid = licoes.criar(cfg, "treino", ref, f"Treino — {c.nome}, nível {caso['nivel']} ({NIVEIS[caso['nivel']]}): {tipo.replace('_', ' ')}",
                       f"O que o nível exige: {c.niveis.get(caso['nivel'], '')}.\nO que deu errado: {detalhe}\n"
                       f"Caso: {caso['id']} ({caso.get('resumo', '')}).\nComo provar que aprendeu: acertar {c.nome} no nível "
                       f"{caso['nivel']} ou acima.", f"{c.nome} {tipo.replace('_', ' ')} nível {caso['nivel']}",
                       f"acertar {c.nome} no nível {caso['nivel']} ou acima", p.get("andar"), pid, "pessoa", "casos_planejamento")
    licoes.atribuir(cfg, "treino", ref, pid, "casos_planejamento")
    if lid:  # 1º erro deste tipo: a equipe da mesma área que treina esta competência estuda junto (aprende com o colega)
        for colega in colegas_que_aprendem(cfg, pid, c.id):
            licoes.atribuir(cfg, "treino", ref, colega, "casos_planejamento")
    with _tb(cfg).tx() as conn:
        n = conn.execute("SELECT COUNT(*) FROM treino_tentativas WHERE competencia=? AND nivel=? AND tipo_erro=? AND data_hora>=?",
                         (c.id, caso["nivel"], tipo, (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds"))).fetchone()[0]
    if n >= int(_c(cfg)["erros_para_handover"]):  # erro que se repete é do código, não da pessoa: vai para quem cuida
        dono = organizacao.ENCAMINHAR.get(c.ferramenta, "coord_engenharia")
        memoria.handover(cfg, f"Treino: {c.nome} nível {caso['nivel']} — {tipo.replace('_', ' ')}",
                         f"treino_{c.id}", SALA["planejador"], f"{n}x em 7 dias; exemplo: {detalhe[:200]} (caso {caso['id']})",
                         responsavel=dono)


def ajustar_nivel(cfg, pid: str, comp: str) -> dict | None:
    """Janela das últimas N tentativas no nível atual (desde a última mudança): sobe ou desce com evidência."""
    k = _c(cfg)
    with _tb(cfg).tx() as conn:
        nivel = nivel_atual(cfg, pid, comp, conn)
        desde = conn.execute("SELECT desde FROM treino_niveis WHERE funcionario=? AND competencia=?", (pid, comp)).fetchone()["desde"]
        janela = conn.execute("SELECT id, acertou FROM treino_tentativas WHERE funcionario=? AND competencia=? AND nivel=? "
                              "AND data_hora>=? ORDER BY id DESC LIMIT ?", (pid, comp, nivel, desde, int(k["janela_nivel"]))).fetchall()
        if len(janela) < int(k["janela_nivel"]):
            return None
        certas = sum(r["acertou"] for r in janela)
        para = decidir_nivel(nivel, certas, len(janela), int(k["sobe_com"]), int(k["desce_com"]))
        if para == nivel:
            return None
        motivo = (f"{certas} de {len(janela)} certas no nível {nivel}: " +
                  ("sobe para o próximo" if para > nivel else "volta um nível para consolidar"))
        evid = ",".join(f"T{r['id']}" for r in janela)
        conn.execute("UPDATE treino_niveis SET nivel=?, desde=? WHERE funcionario=? AND competencia=?", (para, _agora(), pid, comp))
        conn.execute("INSERT INTO treino_niveis_eventos (data_hora, funcionario, competencia, de, para, motivo, evidencia) "
                     "VALUES (?,?,?,?,?,?,?)", (_agora(), pid, comp, nivel, para, motivo, evid))
    return {"de": nivel, "para": para, "motivo": motivo}


# =============================================================================== distribuição (Yasmin) e rotina
def _ultima(cfg) -> dict:
    with _tb(cfg).tx() as c:
        return {(r["funcionario"], r["competencia"]): r["ult"] for r in c.execute(
            "SELECT funcionario, competencia, MAX(data_hora) ult FROM treino_tentativas GROUP BY funcionario, competencia")}


def rodada(cfg, quantos: int | None = None, funcionarios: list[str] | None = None) -> dict:
    """Uma rodada de distribuição. Nunca roda duas ao mesmo tempo."""
    if not _rodando.acquire(blocking=False):
        return {"ok": False, "motivo": "outra rodada de treino está em andamento"}
    try:
        return _rodada(cfg, quantos, funcionarios)
    finally:
        _rodando.release()


def _pdis_abertos(cfg, pid: str) -> list[str]:
    """Competências com plano de melhoria aberto pelo RH (robo/rh_desempenho.py) — vazio se o RH ainda não rodou."""
    with _tb(cfg).tx() as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='rh_pdi'").fetchone():
            return []
        return [r[0] for r in c.execute("SELECT competencia FROM rh_pdi WHERE funcionario=? AND fechado_em IS NULL ORDER BY id",
                                        (pid,))]


def _rodada(cfg, quantos, funcionarios) -> dict:
    _tb(cfg)
    rid = f"TR-{datetime.now():%Y%m%d-%H%M%S}"
    ultima = _ultima(cfg)
    pessoas = [p["id"] for p in elegiveis(cfg)] if funcionarios is None else list(funcionarios)
    quando = lambda pid: max([v for (f, _), v in ultima.items() if f == pid] or [""])  # noqa: E731
    pessoas.sort(key=quando)  # quem está há mais tempo sem treinar vem primeiro
    if quantos:
        pessoas = pessoas[:int(quantos)]
    feitas, sem_caso = [], []
    from robo import jobs
    jid = jobs.abrir(cfg, "treino", "sintetico", rid, ROTINA_RESPONSAVEL)
    try:
        _rodar_pessoas(cfg, pessoas, ultima, rid, jid, feitas, sem_caso)
    except BaseException as e:
        jobs.fechar(cfg, jid, "falhou", {"erro": f"{type(e).__name__}: {e}", "tentativas": len(feitas)})
        raise
    jobs.fechar(cfg, jid, "concluido", {"tentativas": len(feitas), "acertos": sum(f["acertou"] for f in feitas),
                                        "sem_caso": len(sem_caso)})
    encerrar_casos(cfg)
    try:
        from robo import interacoes
        interacoes.conversas_por_fatos(cfg)  # SLA das rotinas e acerto baixo num andar viram conversa registrada
    except Exception:
        log.exception("Treino: conversas por fatos falharam")
    return {"ok": True, "rodada": rid, "tentativas": len(feitas), "acertos": sum(f["acertou"] for f in feitas),
            "mudancas_de_nivel": [f for f in feitas if f["mudanca_nivel"]], "sem_caso": sem_caso, "detalhe": feitas}


ROTINA_RESPONSAVEL = "casos_planejamento"


def _rodar_pessoas(cfg, pessoas, ultima, rid, jid, feitas, sem_caso) -> None:
    from robo import jobs
    for pid in pessoas:
        comps = competencias_de(pid, cfg)
        if not comps:
            continue
        comp = min(comps, key=lambda c: ultima.get((pid, c), ""))  # a competência há mais tempo sem prática
        pdi = [x for x in _pdis_abertos(cfg, pid) if x in comps]
        if pdi and ultima.get((pid, pdi[0]), "") <= max(ultima.get((pid, c), "") for c in comps):
            comp = pdi[0]  # plano de melhoria aberto (RH): essa competência vem antes, em rodadas alternadas
        nivel = nivel_atual(cfg, pid, comp)
        try:
            caso = obter_caso(cfg, comp, nivel, pid)
        except Exception as e:
            log.exception("Treino: não consegui preparar caso de %s nível %s", comp, nivel)
            caso = None
            sem_caso.append(f"{comp} n{nivel}: {type(e).__name__}")
        if not caso:
            sem_caso.append(f"{comp} n{nivel}")
            continue
        eid = jobs.etapa(cfg, jid, f"treino:{comp}:n{nivel}", pid)
        f = tentar(cfg, pid, comp, caso, rid)
        jobs.fechar_etapa(cfg, eid, f["acertou"], f"caso {caso.get('id')}",
                          {"tentativa": f.get("tentativa"), "caso": caso.get("id"), "nivel": caso.get("nivel")})
        feitas.append(f)


def encerrar_casos(cfg) -> int:
    """Casos usados o bastante (ou antigos) saem da fila: com erro → guardados; sem erro → refeitos pela semente."""
    k = _c(cfg)
    limite = (datetime.now() - timedelta(days=int(k["dias_caso_ativo"]))).isoformat(timespec="seconds")
    with _tb(cfg).tx() as c:
        alvos = [dict(r) for r in c.execute(
            "SELECT t.id, (SELECT COUNT(*) FROM treino_tentativas x WHERE x.caso_id=t.id) n, "
            "(SELECT COUNT(*) FROM treino_tentativas x WHERE x.caso_id=t.id AND x.acertou=0) erros "
            "FROM treino_casos t WHERE t.estado='validado' AND t.encerrado_em IS NULL AND "
            "((SELECT COUNT(*) FROM treino_tentativas x WHERE x.caso_id=t.id) >= ? OR t.criado_em < ?)",
            (int(k["max_tentativas_por_caso"]), limite))]
    for a in alvos:
        destino = pasta(cfg) / "casos" / a["id"]
        if a["erros"]:
            _guardar(cfg, a["id"], destino, "teve erro")
        else:
            shutil.rmtree(destino, ignore_errors=True)
        with _tb(cfg).tx() as c:
            c.execute("UPDATE treino_casos SET estado='encerrado', encerrado_em=? WHERE id=?", (_agora(), a["id"]))
    return len(alvos)


def rotina(cfg) -> dict | None:
    k = _c(cfg)
    if not k.get("habilitado", True):
        return None
    with _tb(cfg).tx() as c:
        ult = c.execute("SELECT MAX(data_hora) FROM treino_tentativas").fetchone()[0]
    if ult and datetime.now() - datetime.fromisoformat(ult) < timedelta(minutes=float(k["intervalo_minutos"])):
        return None
    recalibrados = recalibrar(cfg)
    r = rodada(cfg, int(k["por_rodada"]))
    saida = {x: r.get(x) for x in ("rodada", "tentativas", "acertos", "sem_caso")}
    if recalibrados:
        saida["recalibrados"] = recalibrados
    return saida


def decidir_nivel(nivel: int, certas: int, janela: int, sobe_com: int = 4, desce_com: int = 2) -> int:
    if janela < 5:
        return nivel
    if certas >= sobe_com and nivel < max(NIVEIS):
        return nivel + 1
    if certas <= desce_com and nivel > min(NIVEIS):
        return nivel - 1
    return nivel


def provas() -> dict:
    """Provas técnicas REAIS da Sala de Casos (o RH roda uma vez e guarda)."""
    import tempfile
    r = {}
    sem_cfg = {"conhecimento", "sql", "desempenho"}  # dependem do banco da empresa ou do PostgreSQL: provados no exame
    for designer in SALA["designers"]:
        casos = []
        for comp in [c for c in CATALOGO.values() if c.designer == designer and c.id not in sem_cfg]:
            with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
                try:
                    x, y = comp.gerar(5, 4242, Path(a), None), comp.gerar(5, 4242, Path(b), None)
                    igual = conteudo_hash(x.get("arquivo"), x["gabarito"]) == conteudo_hash(y.get("arquivo"), y["gabarito"])
                    confere = not comp.conferir({**x, "semente": 4242, "nivel": 5, "competencia": comp.id}, None)
                except Exception:
                    igual = confere = False
            casos += [(f"{comp.nome}: caso desafio reprodutível pela semente", igual),
                      (f"{comp.nome}: gabarito do desafio confere por outro caminho", confere)]
        r[designer] = casos or [("Tem competência no catálogo", False)]
    with tempfile.TemporaryDirectory() as a:
        comp = CATALOGO["calculo"]
        x = comp.gerar(2, 77, Path(a), None)
        x.update({"semente": 77, "nivel": 2, "competencia": "calculo"})
        sabotado = json.loads(json.dumps(x))
        chave = next(iter(sabotado["gabarito"]["valores"]))
        sabotado["gabarito"]["valores"][chave] = (sabotado["gabarito"]["valores"][chave] or 0) + 1
        r["casos_revisor"] = [("Aprova caso correto", comp.conferir(x, None) == []),
                              ("Pega gabarito sabotado", bool(comp.conferir(sabotado, None)))]
    r["casos_planejamento"] = [("4 de 5 sobe", decidir_nivel(2, 4, 5) == 3), ("2 de 5 desce", decidir_nivel(3, 2, 5) == 2),
                               ("3 de 5 fica", decidir_nivel(3, 3, 5) == 3), ("Não passa do desafio", decidir_nivel(5, 5, 5) == 5),
                               ("Não desce do básico", decidir_nivel(1, 0, 5) == 1), ("Janela incompleta não muda", decidir_nivel(2, 4, 4) == 2)]
    r["head_casos"] = [("Exige revisão de quem não gerou", SALA["revisor"] not in SALA["designers"]),
                       ("Todo item do catálogo tem designer da sala", all(c.designer in SALA["designers"] for c in CATALOGO.values())),
                       ("Todo item tem os 5 níveis descritos", all(set(c.niveis) == set(NIVEIS) for c in CATALOGO.values()))]
    return r


# =============================================================================== leitura (painel, reunião, gestão)
def painel(cfg, horas: int = 24) -> dict:
    _tb(cfg)
    desde = (datetime.now() - timedelta(hours=horas)).isoformat(timespec="seconds")
    gente = organizacao.por_id(cfg)
    nome = lambda x: (gente.get(x) or {}).get("nome", x)  # noqa: E731
    with _tb(cfg).tx() as c:
        tot = dict(c.execute("SELECT COUNT(*) n, SUM(acertou) ok FROM treino_tentativas").fetchone())
        rec = dict(c.execute("SELECT COUNT(*) n, SUM(acertou) ok, COUNT(DISTINCT funcionario) pessoas FROM treino_tentativas "
                             "WHERE data_hora>=?", (desde,)).fetchone())
        por_comp = [dict(r) for r in c.execute(
            "SELECT competencia, nivel, COUNT(*) n, SUM(acertou) ok FROM treino_tentativas GROUP BY competencia, nivel")]
        niveis = [dict(r) for r in c.execute("SELECT funcionario, competencia, nivel FROM treino_niveis")]
        eventos = [dict(r) for r in c.execute("SELECT * FROM treino_niveis_eventos WHERE de IS NOT NULL ORDER BY id DESC LIMIT 40")]
        ultimas = [dict(r) for r in c.execute("SELECT id, data_hora, funcionario, competencia, nivel, acertou, tipo_erro, detalhe, "
                                              "segundos, caso_id FROM treino_tentativas ORDER BY id DESC LIMIT 40")]
        casos = {r["estado"]: r["n"] for r in c.execute("SELECT estado, COUNT(*) n FROM treino_casos GROUP BY estado")}
        certs = [dict(r) for r in c.execute(
            "SELECT designer, competencia, versao_gerador, ok, data_hora, detalhe FROM treino_certificacoes "
            "WHERE id IN (SELECT MAX(id) FROM treino_certificacoes GROUP BY designer, competencia)")]
        erros_tipo = [dict(r) for r in c.execute(
            "SELECT competencia, nivel, tipo_erro, COUNT(*) n FROM treino_tentativas WHERE acertou=0 GROUP BY 1, 2, 3 "
            "ORDER BY n DESC LIMIT 15")]
    pessoas = {}
    for n in niveis:
        pessoas.setdefault(n["funcionario"], {})[n["competencia"]] = n["nivel"]
    competencias = []
    for comp in CATALOGO.values():
        linhas = [x for x in por_comp if x["competencia"] == comp.id]
        competencias.append({"id": comp.id, "nome": comp.nome, "ferramenta": comp.ferramenta, "designer": comp.designer,
                             "designer_nome": nome(comp.designer), "niveis": comp.niveis, "requer_banco": comp.requer_banco,
                             "por_nivel": {x["nivel"]: {"n": x["n"], "taxa": round(100 * (x["ok"] or 0) / x["n"], 1)} for x in linhas},
                             "pessoas_por_nivel": {lv: sum(1 for p in niveis if p["competencia"] == comp.id and p["nivel"] == lv)
                                                   for lv in NIVEIS}})
    for x in eventos + ultimas:
        x["nome"] = nome(x["funcionario"])
    for x in certs:
        x["designer_nome"] = nome(x["designer"])
    return {"total": {"tentativas": tot["n"], "acertos": tot["ok"] or 0},
            "recente": {"horas": horas, "tentativas": rec["n"], "acertos": rec["ok"] or 0, "pessoas": rec["pessoas"]},
            "elegiveis": len(elegiveis(cfg)), "competencias": competencias, "niveis_por_pessoa": pessoas,
            "mudancas_de_nivel": eventos, "ultimas": ultimas, "casos": casos, "certificacoes": certs,
            "erros_mais_comuns": erros_tipo, "niveis": NIVEIS, "versao_codigo": versao_codigo(),
            "sala": {k: (nome(v) if isinstance(v, str) else [nome(x) for x in v]) for k, v in SALA.items()}}


def pessoa(cfg, pid: str) -> dict:
    """A ficha de treino de uma pessoa: nível em cada competência e a linha do tempo de mudanças."""
    _tb(cfg)
    with _tb(cfg).tx() as c:
        niveis = {r["competencia"]: dict(r) for r in c.execute("SELECT * FROM treino_niveis WHERE funcionario=?", (pid,))}
        eventos = [dict(r) for r in c.execute("SELECT * FROM treino_niveis_eventos WHERE funcionario=? ORDER BY id", (pid,))]
        por = {r["competencia"]: dict(r) for r in c.execute(
            "SELECT competencia, COUNT(*) n, SUM(acertou) ok FROM treino_tentativas WHERE funcionario=? GROUP BY competencia", (pid,))}
    return {"funcionario": pid, "competencias": competencias_de(pid, cfg), "niveis": niveis, "eventos": eventos, "tentativas": por}
