"""Ciclo de desempenho do RH: promoção, plano de melhoria (PDI), afastamento da ferramenta e reintegração.

Tudo sai dos REGISTROS (treino_tentativas, treino_niveis, experiencias, licoes_funcionario e, se existir,
mentorias) — nenhuma decisão é opinião. Cada movimento fica em rh_movimentos (imutável: não altera, não apaga).

POLÍTICA (a mesma no código, na documentação e nos testes — veja POLITICA abaixo):

  Promoção (escada: estagiário → júnior → pleno → sênior → especialista). Cargos de liderança (coordenador, gerente,
  head, diretor) são estrutura da empresa e não entram no ciclo. Para subir, nos últimos 30 dias:
    - pelo menos 30 tentativas de treino e 90% ou mais de acerto;
    - média do nível de treino (todas as competências da pessoa) ≥ alvo do cargo novo:
        júnior 2,0 · pleno 3,0 · sênior 4,0 · especialista 4,5 e nível 5 em pelo menos metade das competências;
    - no máximo 2 erros de produção registrados (experiencias tipo erro fora do treino);
    - nenhum plano de melhoria aberto e nenhuma promoção nos últimos 30 dias.
  Quem decide:
    - o RH (Mauro, analista de desempenho) PROPÕE com a evidência; se o promovido for o próprio Mauro, quem propõe é a
      head de RH (ninguém propõe a si mesmo);
    - o GESTOR da pessoa VALIDA, recontando os números por outro caminho (SQL agregado em vez do laço do RH). Precisa
      ser outra pessoa, que possa aprovar. Gestor inválido ou o próprio dono → a proposta espera o dono;
    - continua SEMPRE com o dono: sair do estágio (estagiário → júnior) e qualquer promoção que dê o direito de alterar
      dados (pleno → sênior). Nesses casos o RH só propõe, com a evidência.

  Plano de melhoria (PDI): acerto abaixo de 60% nas últimas 10 tentativas de uma competência → PDI aberto (lição com
  os erros reais da pessoa). Fecha quando acerta 4 das 5 últimas no nível atual dela.
  Afastamento: PDI aberto há 14 dias ou mais sem melhorar (acerto das últimas 10 não subiu) → a pessoa deixa de usar a
  ferramenta daquela competência EM PRODUÇÃO (organizacao.pode_usar(..., producao=True)), mas continua treinando.
  Reintegração: automática quando volta a acertar 4 de 5 — o PDI fecha e a ferramenta volta.
  PDI e afastamento também são propostos pelo RH e validados por outra pessoa (gestor, revisor ou liderança de RH).

  Desligamento e admissão: só existem para CONTRATADOS (agentes criados pela contratação — robo/contratacao.py, que
  já cuida do fim da experiência). Os funcionários nativos são funções do código do robô: não dá para "demitir"
  código; para eles a medida mais forte é o afastamento da ferramenta. Para um contratado afastado há 30 dias ou mais
  o RH PROPÕE o desligamento, e só o dono decide (apagar alguém é decisão do dono).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from robo import organizacao
from robo.trabalho import Trabalho

log = logging.getLogger("robo")

ESCADA = {"estagiario": "junior", "junior": "pleno", "pleno": "senior", "senior": "especialista"}
POLITICA = {
    "janela_dias": 30, "min_tentativas": 30, "acerto_min": 0.90, "erros_producao_max": 2, "intervalo_promocao_dias": 30,
    "alvo": {"junior": {"media_nivel": 2.0}, "pleno": {"media_nivel": 3.0}, "senior": {"media_nivel": 4.0},
             "especialista": {"media_nivel": 4.5, "fracao_nivel5": 0.5}},
    "pdi_janela": 10, "pdi_acerto_max": 0.60, "pdi_fecha_certas": 4, "pdi_fecha_de": 5, "pdi_dias_afastar": 14,
    "dias_afastado_para_propor_desligamento": 30, "intervalo_ciclo_horas": 24,
}
PROPONENTE, PROPONENTE_RESERVA = "rh_desempenho", "head_rh"
VALIDADORES_RH = ["head_rh", "dir_pessoas", "canal_helena"]

ESQUEMA = """
CREATE TABLE IF NOT EXISTS rh_movimentos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, funcionario TEXT, tipo TEXT, de_nivel TEXT, para_nivel TEXT,
  competencia TEXT, motivo TEXT, evidencia TEXT, proposto_por TEXT, validado_por TEXT, situacao TEXT, ref INTEGER);
CREATE INDEX IF NOT EXISTS ix_rhm_func ON rh_movimentos(funcionario, id);
CREATE TRIGGER IF NOT EXISTS rh_movimentos_imutavel BEFORE UPDATE ON rh_movimentos
BEGIN SELECT RAISE(ABORT, 'movimento de RH não muda depois de gravado'); END;
CREATE TABLE IF NOT EXISTS rh_cargos (funcionario TEXT PRIMARY KEY, nivel TEXT, desde TEXT, movimento_id INTEGER);
CREATE TABLE IF NOT EXISTS rh_pdi (
  id INTEGER PRIMARY KEY AUTOINCREMENT, funcionario TEXT, competencia TEXT, ferramenta TEXT, aberto_em TEXT,
  acerto_abertura REAL, movimento_id INTEGER, afastado_em TEXT, fechado_em TEXT);
CREATE INDEX IF NOT EXISTS ix_rhp_func ON rh_pdi(funcionario, competencia);
CREATE TABLE IF NOT EXISTS rh_ciclos (id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, resumo TEXT);
CREATE TRIGGER IF NOT EXISTS rh_ciclos_imutavel BEFORE UPDATE ON rh_ciclos
BEGIN SELECT RAISE(ABORT, 'ciclo de RH não muda depois de gravado'); END;
"""


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    with tb.tx() as c:
        c.executescript(ESQUEMA)
        from robo.trabalho import proteger
        proteger(c)
    return tb


def _iso(d: datetime) -> str:
    return d.isoformat(timespec="seconds")


def _tem_tabela(c, nome: str) -> bool:
    return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nome,)).fetchone())


def _gente(cfg) -> dict:
    return organizacao.por_id(cfg)


def _pode_aprovar(pid: str | None, gente: dict) -> bool:
    if not pid or pid == organizacao.DONO or pid not in gente:
        return False
    return organizacao.PERMISSOES_NIVEL.get(organizacao.nivel_de(pid, gente[pid]), {}).get("aprova", False)


def so_dono(de: str, para: str) -> bool:
    """Promoções que só o dono decide: sair do estágio e ganhar o direito de alterar dados."""
    perm = organizacao.PERMISSOES_NIVEL
    return de == "estagiario" or (not perm[de]["altera_dados"] and perm[para]["altera_dados"])


def proponente_para(pid: str) -> str:
    return PROPONENTE_RESERVA if pid == PROPONENTE else PROPONENTE


def validador_gestor(pid: str, proponente: str, gente: dict) -> str | None:
    """Validador de promoção: o gestor da pessoa — outra pessoa, diferente de quem propôs, que pode aprovar."""
    g = organizacao.gestor_de(pid)
    return g if g not in (pid, proponente) and _pode_aprovar(g, gente) else None


def validador_geral(pid: str, proponente: str, gente: dict, cfg=None) -> str | None:
    """Validador de PDI e afastamento: gestor, revisor, ou a liderança de RH — nunca a própria pessoa nem quem propôs."""
    for c in [organizacao.gestor_de(pid), organizacao.revisor_de(pid, cfg)] + VALIDADORES_RH:
        if c not in (pid, proponente) and _pode_aprovar(c, gente):
            return c
    return None


# =============================================================================== números (dois caminhos independentes)
def numeros(c, pid: str, desde: str) -> dict:
    """Caminho do RH: lê as linhas e conta em Python."""
    linhas = c.execute("SELECT acertou FROM treino_tentativas WHERE funcionario=? AND data_hora>=?", (pid, desde)).fetchall()
    niveis = [int(r["nivel"]) for r in c.execute("SELECT nivel FROM treino_niveis WHERE funcionario=?", (pid,))]
    certas = sum(1 for r in linhas if r["acertou"])
    erros_prod = c.execute("SELECT count(*) FROM experiencias WHERE funcionario=? AND tipo='erro' AND data_hora>=? "
                           "AND COALESCE(origem,'') NOT IN ('treino','laboratorio')", (pid, desde)).fetchone()[0]
    aplicadas = 0
    if _tem_tabela(c, "licoes_funcionario"):
        aplicadas = c.execute("SELECT count(*) FROM licoes_funcionario WHERE funcionario=? AND estado='aplicada'",
                              (pid,)).fetchone()[0]
    mentorias = None
    if _tem_tabela(c, "mentorias"):
        try:
            mentorias = c.execute("SELECT count(*) FROM mentorias WHERE mentor=? OR aprendiz=?", (pid, pid)).fetchone()[0]
        except Exception:
            mentorias = None
    return {"tentativas": len(linhas), "certas": certas, "acerto": round(certas / len(linhas), 4) if linhas else 0.0,
            "competencias": len(niveis), "media_nivel": round(sum(niveis) / len(niveis), 3) if niveis else 0.0,
            "nivel5": sum(1 for n in niveis if n == 5), "erros_producao": erros_prod, "licoes_aplicadas": aplicadas,
            "mentorias": mentorias}


def recontagem(c, pid: str, desde: str) -> dict:
    """Caminho do validador: agregados em SQL (outra conta, mesmo registro)."""
    t = c.execute("SELECT count(*) n, COALESCE(sum(acertou),0) s FROM treino_tentativas WHERE funcionario=? AND data_hora>=?",
                  (pid, desde)).fetchone()
    n = c.execute("SELECT count(*) n, COALESCE(avg(nivel),0) m, COALESCE(sum(nivel=5),0) c5 FROM treino_niveis "
                  "WHERE funcionario=?", (pid,)).fetchone()
    return {"tentativas": t["n"], "certas": t["s"], "competencias": n["n"], "media_nivel": round(float(n["m"]), 3),
            "nivel5": n["c5"]}


def elegivel(num: dict, para: str) -> tuple[bool, list[str]]:
    p, alvo = POLITICA, POLITICA["alvo"][para]
    faltas = []
    if num["tentativas"] < p["min_tentativas"]:
        faltas.append(f"{num['tentativas']} tentativas em 30 dias (mínimo {p['min_tentativas']})")
    if num["acerto"] < p["acerto_min"]:
        faltas.append(f"acerto {num['acerto']:.0%} (mínimo {p['acerto_min']:.0%})")
    if num["media_nivel"] < alvo["media_nivel"]:
        faltas.append(f"média de nível {num['media_nivel']:.2f} (alvo {alvo['media_nivel']})")
    if "fracao_nivel5" in alvo and num["competencias"] and num["nivel5"] / num["competencias"] < alvo["fracao_nivel5"]:
        faltas.append(f"nível 5 em {num['nivel5']} de {num['competencias']} competências (mínimo metade)")
    if num["erros_producao"] > p["erros_producao_max"]:
        faltas.append(f"{num['erros_producao']} erros de produção (máximo {p['erros_producao_max']})")
    return not faltas, faltas


# =============================================================================== registro
def _mov(c, agora: datetime, pid: str, tipo: str, situacao: str, motivo: str, evidencia: dict, proposto_por: str,
         validado_por: str | None = None, de: str | None = None, para: str | None = None, comp: str | None = None,
         ref: int | None = None) -> int:
    cur = c.execute("INSERT INTO rh_movimentos (data_hora, funcionario, tipo, de_nivel, para_nivel, competencia, motivo, "
                    "evidencia, proposto_por, validado_por, situacao, ref) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (_iso(agora), pid, tipo, de, para, comp, motivo[:1000], json.dumps(evidencia, ensure_ascii=False,
                                                                                         default=str),
                     proposto_por, validado_por, situacao, ref))
    return cur.lastrowid


def _anunciar(cfg, autor: str, texto: str) -> None:
    try:
        from robo.canal import Canal
        Canal(cfg).postar(autor, texto, "rh", "rh")
    except Exception:
        log.debug("Canal indisponível para o RH", exc_info=True)


def _experiencia(cfg, pid: str, tipo: str, resumo: str, ref: str) -> None:
    try:
        from robo import memoria
        memoria.experiencia(cfg, pid, tipo, resumo, "rh", ref)
    except Exception:
        log.debug("Não consegui registrar a experiência de RH", exc_info=True)


def movimentos(cfg, funcionario: str | None = None, limite: int = 200) -> list[dict]:
    sql, args = "SELECT * FROM rh_movimentos", []
    if funcionario:
        sql += " WHERE funcionario=?"
        args.append(funcionario)
    with _tb(cfg).tx() as c:
        return [dict(r) for r in c.execute(sql + " ORDER BY id DESC LIMIT ?", args + [limite])]


def pendentes_dono(cfg) -> list[dict]:
    """Propostas que esperam o dono e ainda não tiveram decisão (nem do dono, nem por alçada)."""
    with _tb(cfg).tx() as c:
        decididas = {r["ref"] for r in c.execute("SELECT ref FROM rh_movimentos WHERE tipo IN "
                                                 "('decisao_dono','decisao_alcada') AND ref IS NOT NULL")}
        return [dict(r) for r in c.execute("SELECT * FROM rh_movimentos WHERE situacao='aguardando_dono' ORDER BY id")
                if r["id"] not in decididas]


def _efetivar_promocao(c, agora, pid: str, para: str, mov_id: int) -> None:
    c.execute("INSERT INTO rh_cargos (funcionario, nivel, desde, movimento_id) VALUES (?,?,?,?) ON CONFLICT(funcionario) "
              "DO UPDATE SET nivel=excluded.nivel, desde=excluded.desde, movimento_id=excluded.movimento_id",
              (pid, para, _iso(agora), mov_id))


# =============================================================================== ciclo
def ciclo(cfg, agora: datetime | None = None) -> dict:
    """Roda a política para todos (idempotente: o que já está proposto, aberto ou decidido não se repete)."""
    from robo.treino import EQUIPE_SALA, _tb as tb_treino
    from robo.treino_casos import CATALOGO
    agora = agora or datetime.now()
    tb_treino(cfg)
    tb = _tb(cfg)
    gente = _gente(cfg)
    p = POLITICA
    desde = _iso(agora - timedelta(days=p["janela_dias"]))
    feito = {"promocoes": [], "aguardando_dono": [], "pdi_abertos": [], "pdi_fechados": [], "afastamentos": [],
             "reintegracoes": [], "desligamentos_propostos": [], "sem_validador": []}
    with tb.tx() as c:
        for pid, pessoa in gente.items():
            if pid in EQUIPE_SALA:
                continue
            _ciclo_pdi(c, cfg, agora, pid, gente, CATALOGO, feito)
            _ciclo_promocao(c, cfg, agora, pid, pessoa, gente, desde, feito)
            if pessoa.get("grupo") == "contratado":
                _ciclo_desligamento(c, agora, pid, feito)
        c.execute("INSERT INTO rh_ciclos (data_hora, resumo) VALUES (?,?)",
                  (_iso(agora), json.dumps({k: len(v) for k, v in feito.items()}, ensure_ascii=False)))
    organizacao.limpar_cache_rh()
    _comunicar(cfg, feito, gente)
    return feito


def _ciclo_promocao(c, cfg, agora, pid, pessoa, gente, desde, feito) -> None:
    de = organizacao.nivel_de(pid, pessoa)
    para = ESCADA.get(de)
    if not para:
        return  # liderança ou topo da escada técnica
    if c.execute("SELECT 1 FROM rh_movimentos m WHERE m.funcionario=? AND m.situacao='aguardando_dono' AND NOT EXISTS "
                 "(SELECT 1 FROM rh_movimentos d WHERE d.ref=m.id AND d.tipo IN ('decisao_dono','decisao_alcada'))",
                 (pid,)).fetchone():
        return  # já há proposta esperando decisão
    recente = _iso(agora - timedelta(days=POLITICA["intervalo_promocao_dias"]))
    if c.execute("SELECT 1 FROM rh_movimentos WHERE funcionario=? AND data_hora>? AND ((tipo='promocao' AND "
                 "situacao='efetivada') OR (tipo IN ('decisao_dono','decisao_alcada') AND situacao='aprovada') OR "
                 "tipo='reversao')", (pid, recente)).fetchone():
        return  # no máximo uma promoção por mês (e reversão do dono segura a próxima por um mês)
    if c.execute("SELECT 1 FROM rh_pdi WHERE funcionario=? AND fechado_em IS NULL", (pid,)).fetchone():
        return
    num = numeros(c, pid, desde)
    ok, faltas = elegivel(num, para)
    if not ok:
        return
    proponente = proponente_para(pid)
    evid = {"numeros": num, "politica": POLITICA["alvo"][para], "janela_desde": desde}
    motivo = (f"{num['tentativas']} tentativas em 30 dias, {num['acerto']:.0%} de acerto, média de nível "
              f"{num['media_nivel']:.2f} em {num['competencias']} competência(s), {num['erros_producao']} erro(s) de produção")
    if so_dono(de, para):
        mid = _mov(c, agora, pid, "promocao", "aguardando_dono", motivo + " — decisão do dono (muda permissões de dados "
                   "ou tira do estágio)", evid, proponente, None, de, para)
        feito["aguardando_dono"].append({"funcionario": pid, "de": de, "para": para, "movimento": mid})
        return
    validador = validador_gestor(pid, proponente, gente)
    if not validador:
        mid = _mov(c, agora, pid, "promocao", "aguardando_dono", motivo + " — sem gestor que possa validar: decide o dono",
                   evid, proponente, None, de, para)
        feito["aguardando_dono"].append({"funcionario": pid, "de": de, "para": para, "movimento": mid})
        return
    recont = recontagem(c, pid, desde)
    confere = all(recont[k] == num[k] for k in ("tentativas", "certas", "competencias", "nivel5")) and \
        abs(recont["media_nivel"] - num["media_nivel"]) < 1e-6
    evid["recontagem_do_validador"] = recont
    if not confere:
        _mov(c, agora, pid, "promocao", "recusada_pelo_validador", "a recontagem do gestor não bateu com a do RH", evid,
             proponente, validador, de, para)
        return
    mid = _mov(c, agora, pid, "promocao", "efetivada", motivo, evid, proponente, validador, de, para)
    _efetivar_promocao(c, agora, pid, para, mid)
    feito["promocoes"].append({"funcionario": pid, "de": de, "para": para, "validado_por": validador, "movimento": mid})


def _acerto(linhas) -> float:
    return sum(1 for r in linhas if r["acertou"]) / len(linhas) if linhas else 0.0


def _ciclo_pdi(c, cfg, agora, pid, gente, catalogo, feito) -> None:
    p = POLITICA
    comps = [r["competencia"] for r in c.execute("SELECT DISTINCT competencia FROM treino_tentativas WHERE funcionario=?",
                                                 (pid,))]
    for comp in comps:
        ultimas = c.execute("SELECT acertou, nivel FROM treino_tentativas WHERE funcionario=? AND competencia=? "
                            "ORDER BY id DESC LIMIT ?", (pid, comp, p["pdi_janela"])).fetchall()
        aberto = c.execute("SELECT * FROM rh_pdi WHERE funcionario=? AND competencia=? AND fechado_em IS NULL "
                           "ORDER BY id DESC LIMIT 1", (pid, comp)).fetchone()
        ferramenta = catalogo[comp].ferramenta if comp in catalogo else comp
        if not aberto:
            if len(ultimas) >= p["pdi_janela"] and _acerto(ultimas) < p["pdi_acerto_max"]:
                proponente = proponente_para(pid)
                validador = validador_geral(pid, proponente, gente, cfg)
                if not validador:
                    feito["sem_validador"].append({"funcionario": pid, "competencia": comp})
                    continue
                acerto = round(_acerto(ultimas), 4)
                evid = {"ultimas": [dict(r) for r in ultimas], "acerto": acerto}
                mid = _mov(c, agora, pid, "pdi_aberto", "efetivada", f"acerto {acerto:.0%} nas últimas {len(ultimas)} "
                           f"tentativas de {comp} (limite {p['pdi_acerto_max']:.0%})", evid, proponente, validador, comp=comp)
                c.execute("INSERT INTO rh_pdi (funcionario, competencia, ferramenta, aberto_em, acerto_abertura, movimento_id) "
                          "VALUES (?,?,?,?,?,?)", (pid, comp, ferramenta, _iso(agora), acerto, mid))
                feito["pdi_abertos"].append({"funcionario": pid, "competencia": comp, "acerto": acerto, "movimento": mid})
            continue
        nivel_atual = c.execute("SELECT nivel FROM treino_niveis WHERE funcionario=? AND competencia=?", (pid, comp)).fetchone()
        nivel_atual = int(nivel_atual["nivel"]) if nivel_atual else 1
        no_nivel = c.execute("SELECT acertou FROM treino_tentativas WHERE funcionario=? AND competencia=? AND nivel>=? "
                             "AND data_hora>=? ORDER BY id DESC LIMIT ?",
                             (pid, comp, nivel_atual, aberto["aberto_em"], p["pdi_fecha_de"])).fetchall()
        if len(no_nivel) >= p["pdi_fecha_de"] and sum(1 for r in no_nivel if r["acertou"]) >= p["pdi_fecha_certas"]:
            evid = {"ultimas_no_nivel": [dict(r) for r in no_nivel], "nivel": nivel_atual}
            if aberto["afastado_em"]:
                mid = _mov(c, agora, pid, "reintegracao", "efetivada", f"voltou a acertar {p['pdi_fecha_certas']} de "
                           f"{p['pdi_fecha_de']} em {comp} no nível {nivel_atual}: {ferramenta} liberada de novo",
                           evid, proponente_para(pid), "sistema", comp=comp, ref=aberto["movimento_id"])
                feito["reintegracoes"].append({"funcionario": pid, "competencia": comp, "movimento": mid})
            mid = _mov(c, agora, pid, "pdi_fechado", "efetivada", f"acertou {p['pdi_fecha_certas']} de {p['pdi_fecha_de']} "
                       f"em {comp} no nível {nivel_atual}", evid, proponente_para(pid), "sistema", comp=comp,
                       ref=aberto["movimento_id"])
            c.execute("UPDATE rh_pdi SET fechado_em=? WHERE id=?", (_iso(agora), aberto["id"]))
            feito["pdi_fechados"].append({"funcionario": pid, "competencia": comp, "movimento": mid})
            continue
        if not aberto["afastado_em"] and aberto["aberto_em"] <= _iso(agora - timedelta(days=p["pdi_dias_afastar"])):
            acerto = round(_acerto(ultimas), 4)
            if acerto <= float(aberto["acerto_abertura"]):
                proponente = proponente_para(pid)
                validador = validador_geral(pid, proponente, gente, cfg)
                if not validador:
                    feito["sem_validador"].append({"funcionario": pid, "competencia": comp})
                    continue
                mid = _mov(c, agora, pid, "afastamento", "efetivada", f"PDI de {comp} aberto há {p['pdi_dias_afastar']}+ "
                           f"dias sem melhorar ({aberto['acerto_abertura']:.0%} → {acerto:.0%}): sem {ferramenta} em produção "
                           "até voltar a acertar; continua treinando", {"acerto_abertura": aberto["acerto_abertura"],
                                                                        "acerto_agora": acerto}, proponente, validador,
                           comp=comp, ref=aberto["movimento_id"])
                c.execute("UPDATE rh_pdi SET afastado_em=? WHERE id=?", (_iso(agora), aberto["id"]))
                feito["afastamentos"].append({"funcionario": pid, "competencia": comp, "ferramenta": ferramenta,
                                              "validado_por": validador, "movimento": mid})


def _ciclo_desligamento(c, agora, pid, feito) -> None:
    limite = _iso(agora - timedelta(days=POLITICA["dias_afastado_para_propor_desligamento"]))
    pdi = c.execute("SELECT * FROM rh_pdi WHERE funcionario=? AND fechado_em IS NULL AND afastado_em IS NOT NULL "
                    "AND afastado_em<=? ORDER BY id LIMIT 1", (pid, limite)).fetchone()
    if not pdi or c.execute("SELECT 1 FROM rh_movimentos WHERE funcionario=? AND tipo='desligamento_proposto' AND ref=?",
                            (pid, pdi["movimento_id"])).fetchone():
        return
    mid = _mov(c, agora, pid, "desligamento_proposto", "aguardando_dono", f"contratado afastado de {pdi['ferramenta']} desde "
               f"{pdi['afastado_em'][:10]} sem voltar a acertar — só o dono decide desligar", {"pdi": dict(pdi)},
               PROPONENTE, None, comp=pdi["competencia"], ref=pdi["movimento_id"])
    feito["desligamentos_propostos"].append({"funcionario": pid, "movimento": mid})


def _comunicar(cfg, feito: dict, gente: dict) -> None:
    nome = lambda x: (gente.get(x) or {}).get("nome", x)  # noqa: E731
    for x in feito["promocoes"]:
        _anunciar(cfg, PROPONENTE, f"Promoção: {nome(x['funcionario'])} passa de {x['de']} para {x['para']} — pela política, "
                                   f"validada por {nome(x['validado_por'])} (movimento {x['movimento']}).")
        _experiencia(cfg, x["funcionario"], "acerto", f"Promovido(a) a {x['para']} pela política de desempenho",
                     f"RH-{x['movimento']}")
    for x in feito["aguardando_dono"]:
        _anunciar(cfg, PROPONENTE, f"Proposta para o dono: {nome(x['funcionario'])} de {x['de']} para {x['para']} "
                                   f"(movimento {x['movimento']}) — evidência registrada.")
    for x in feito["pdi_abertos"]:
        _anunciar(cfg, PROPONENTE, f"Plano de melhoria aberto para {nome(x['funcionario'])} em {x['competencia']} "
                                   f"(acerto {x['acerto']:.0%} nas últimas 10).")
        _experiencia(cfg, x["funcionario"], "aprendizado", f"Plano de melhoria em {x['competencia']}", f"RH-{x['movimento']}")
        _licao_pdi(cfg, x)
    for x in feito["afastamentos"]:
        _anunciar(cfg, PROPONENTE, f"Afastamento: {nome(x['funcionario'])} fica sem {x['ferramenta']} em produção até voltar "
                                   f"a acertar (continua treinando). Validado por {nome(x['validado_por'])}.")
    for x in feito["reintegracoes"]:
        _anunciar(cfg, PROPONENTE, f"Reintegração: {nome(x['funcionario'])} voltou a acertar {x['competencia']} — "
                                   "ferramenta liberada.")
        _experiencia(cfg, x["funcionario"], "acerto", f"Reintegrado(a) em {x['competencia']}", f"RH-{x['movimento']}")
    for x in feito["desligamentos_propostos"]:
        _anunciar(cfg, PROPONENTE, f"Proposta para o dono: desligar o contratado {nome(x['funcionario'])} "
                                   f"(movimento {x['movimento']}).")


def _licao_pdi(cfg, x: dict) -> None:
    """Lição do PDI com os erros REAIS da pessoa naquela competência (tipos e detalhes das tentativas)."""
    try:
        from robo import licoes
        with Trabalho(cfg).tx() as c:
            erros = c.execute("SELECT tipo_erro, detalhe FROM treino_tentativas WHERE funcionario=? AND competencia=? "
                              "AND acertou=0 ORDER BY id DESC LIMIT 10", (x["funcionario"], x["competencia"])).fetchall()
        tipos: dict[str, int] = {}
        for e in erros:
            tipos[e["tipo_erro"] or "erro"] = tipos.get(e["tipo_erro"] or "erro", 0) + 1
        conteudo = ("Erros que mais se repetiram: " + ", ".join(f"{k} ({v}x)" for k, v in sorted(tipos.items(), key=lambda i: -i[1]))
                    + "\nÚltimos detalhes:\n" + "\n".join(f"- {(e['detalhe'] or '')[:200]}" for e in erros[:5]))
        licoes.criar(cfg, "rh_pdi", f"RH-{x['movimento']}", f"Plano de melhoria em {x['competencia']}", conteudo,
                     f"{x['competencia']} plano de melhoria", "acertar 4 de 5 no nível atual", None, x["funcionario"],
                     "pessoa", PROPONENTE)
    except Exception:
        log.debug("Não consegui criar a lição do PDI", exc_info=True)


# =============================================================================== decisões (dono e alçada) e reversão
def _proposta_aberta(c, mov_id: int) -> dict:
    m = c.execute("SELECT * FROM rh_movimentos WHERE id=?", (mov_id,)).fetchone()
    if not m or m["situacao"] != "aguardando_dono":
        raise ValueError("Não há proposta esperando decisão com esse número.")
    if c.execute("SELECT 1 FROM rh_movimentos WHERE ref=? AND tipo IN ('decisao_dono','decisao_alcada')", (mov_id,)).fetchone():
        raise ValueError("Esta proposta já foi decidida.")
    return dict(m)


def decidir_dono(cfg, mov_id: int, aprovar: bool, motivo: str, quem: str = "dono", agora: datetime | None = None) -> dict:
    """O dono decide uma proposta (promoção que só ele decide, ou desligamento de contratado)."""
    if quem != organizacao.DONO:
        raise PermissionError("Só o dono decide esta proposta.")
    if len((motivo or "").strip()) < 5:
        raise ValueError("Diga o motivo da decisão.")
    agora = agora or datetime.now()
    with _tb(cfg).tx() as c:
        m = _proposta_aberta(c, mov_id)
        did = _mov(c, agora, m["funcionario"], "decisao_dono", "aprovada" if aprovar else "recusada", motivo, {},
                   "dono", "dono", m["de_nivel"], m["para_nivel"], m["competencia"], mov_id)
        if aprovar and m["tipo"] == "promocao":
            _efetivar_promocao(c, agora, m["funcionario"], m["para_nivel"], did)
    if aprovar and m["tipo"] == "desligamento_proposto":
        from robo.pipeline import obter_equipe
        obter_equipe(cfg).excluir(m["funcionario"])
    organizacao.limpar_cache_rh()
    return {"ok": True, "movimento": did}


def aplicar_por_alcada(cfg, mov_id: int, decisor: str, validador: str, motivo: str, agora: datetime | None = None) -> int:
    """Promoção que NÃO é exclusiva do dono e só esperava por falta de gestor válido: decidida pela alçada
    (robo/alcadas.py confere quem pode; aqui confere de novo a regra de duas pessoas)."""
    agora = agora or datetime.now()
    with _tb(cfg).tx() as c:
        m = _proposta_aberta(c, mov_id)
        if m["tipo"] != "promocao" or so_dono(m["de_nivel"], m["para_nivel"]):
            raise PermissionError("Esta promoção é decisão do dono.")
        if len({decisor, validador, m["funcionario"], m["proposto_por"]}) < 4:
            raise PermissionError("Quem decide, quem valida, o promovido e quem propôs precisam ser pessoas diferentes.")
        did = _mov(c, agora, m["funcionario"], "decisao_alcada", "aprovada", motivo, {"decisor": decisor},
                   decisor, validador, m["de_nivel"], m["para_nivel"], None, mov_id)
        _efetivar_promocao(c, agora, m["funcionario"], m["para_nivel"], did)
    organizacao.limpar_cache_rh()
    _anunciar(cfg, decisor, f"Promoção decidida por alçada (dono fora): {m['funcionario']} de {m['de_nivel']} para "
                            f"{m['para_nivel']}, validada por {validador}. O dono pode reverter em 7 dias.")
    return did


def reverter_movimento(cfg, mov_id: int, motivo: str, quem: str = "dono", agora: datetime | None = None) -> dict:
    """Só o dono: desfaz uma promoção (o cargo volta ao anterior; o histórico fica)."""
    if quem != organizacao.DONO:
        raise PermissionError("Só o dono reverte um movimento de RH.")
    agora = agora or datetime.now()
    with _tb(cfg).tx() as c:
        m = c.execute("SELECT * FROM rh_movimentos WHERE id=?", (mov_id,)).fetchone()
        if not m or not ((m["tipo"] == "promocao" and m["situacao"] == "efetivada") or
                         (m["tipo"] in ("decisao_alcada", "decisao_dono") and m["situacao"] == "aprovada" and m["para_nivel"])):
            raise ValueError("Só uma promoção efetivada pode ser revertida.")
        if c.execute("SELECT 1 FROM rh_movimentos WHERE tipo='reversao' AND ref=?", (mov_id,)).fetchone():
            raise ValueError("Este movimento já foi revertido.")
        rid = _mov(c, agora, m["funcionario"], "reversao", "efetivada", motivo, {}, "dono", "dono", m["para_nivel"],
                   m["de_nivel"], None, mov_id)
        _efetivar_promocao(c, agora, m["funcionario"], m["de_nivel"], rid)
    organizacao.limpar_cache_rh()
    return {"ok": True, "movimento": rid}


# =============================================================================== rotina e painel
def rotina(cfg) -> dict | None:
    """Uma vez por dia (a própria rotina confere a hora do último ciclo)."""
    tb = _tb(cfg)
    with tb.tx() as c:
        ult = c.execute("SELECT max(data_hora) FROM rh_ciclos").fetchone()[0]
    if ult and datetime.fromisoformat(ult) > datetime.now() - timedelta(hours=POLITICA["intervalo_ciclo_horas"]):
        return None
    r = ciclo(cfg)
    return {k: len(v) for k, v in r.items()}


def resumo(cfg) -> dict:
    with _tb(cfg).tx() as c:
        por_tipo = {r["tipo"]: r["n"] for r in c.execute("SELECT tipo, count(*) n FROM rh_movimentos GROUP BY tipo")}
        pdi = [dict(r) for r in c.execute("SELECT * FROM rh_pdi WHERE fechado_em IS NULL ORDER BY id")]
        cargos = [dict(r) for r in c.execute("SELECT * FROM rh_cargos ORDER BY desde DESC")]
        ult = c.execute("SELECT data_hora, resumo FROM rh_ciclos ORDER BY id DESC LIMIT 1").fetchone()
    return {"politica": POLITICA, "movimentos_por_tipo": por_tipo, "pdi_abertos": pdi, "cargos": cargos,
            "pendentes_dono": pendentes_dono(cfg), "ultimo_ciclo": dict(ult) if ult else None}
