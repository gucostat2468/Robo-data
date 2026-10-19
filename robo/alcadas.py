"""Alçadas: o que a liderança decide sozinha quando o dono está fora — e o que continua esperando o dono.

Regras que não se negociam:
  - só vale com o dono FORA há `autonomia.horas_offline` horas (última presença = painel aberto ou entrada pelo
    celular) e para pendências paradas há `autonomia.horas_pendente` horas;
  - DUAS PESSOAS: quem decide e quem valida são pessoas diferentes, ambas com permissão de aprovar, e nenhuma delas é
    o autor do item nem a pessoa afetada (ninguém aprova o que propôs nem decide sobre si mesmo);
  - só dentro da MATRIZ abaixo; o resto (risco médio/alto, permissões, estagiário, exclusão, segurança, configuração,
    publicar ou alterar dados) fica para o dono — e fica registrado que ficou, com o motivo;
  - toda decisão vai para alcadas_decisoes (imutável), é anunciada no canal e o dono pode REVERTER em 7 dias.
"""

from __future__ import annotations

import copy
import json
import logging
import shutil
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from robo import organizacao
from robo.trabalho import Trabalho

log = logging.getLogger("robo")

PADRAO = {"habilitada": True, "horas_offline": 12, "horas_pendente": 6, "dias_reversao": 7, "dias_repactuacao": 7}

# item → (risco, decide sozinho?, quem decide / como, por quê)
MATRIZ = {
    "proposta_regra:sinonimo": ("baixo", True, "gestor ou head da área do autor decide; outro líder valida",
                                "só aprova se o arquivo reprovado, reprocessado num computador de teste com a regra, "
                                "passar sem nenhum erro"),
    "proposta_regra:mapeamento": ("medio", False, "dono", "troca um valor por outro: se forem coisas diferentes, "
                                  "estraga dado — o próprio aviso da proposta pede conferência humana"),
    "proposta_regra:valor_permitido": ("medio", False, "dono", "amplia a lista do que é aceito: pode deixar passar lixo"),
    "proposta_regra:apelido": ("medio", False, "dono", "vale para todos os cálculos da empresa"),
    "decisao_atrasada": ("baixo", True, "gestor do responsável repactua UMA vez (+7 dias), outro líder valida",
                         "não deixa decisão vencida sem dono enquanto você está fora; você pode desfazer"),
    "rh_promocao": ("medio", True, "head de RH decide, outro líder valida (só a que esperava por falta de gestor)",
                    "a política e a recontagem já foram feitas; nunca a que dá direito de alterar dados ou tira do estágio"),
    "rh_promocao_do_dono": ("alto", False, "dono", "estagiário → júnior ou ganho do direito de alterar dados"),
    "rh_desligamento": ("alto", False, "dono", "desligar é decisão do dono"),
    "aprovacoes": ("alto", False, "dono", "publicar ou alterar dados de produção"),
    "permissoes_seguranca_configuracao": ("alto", False, "dono", "nunca por alçada"),
}

ESQUEMA = """
CREATE TABLE IF NOT EXISTS dono_presenca (origem TEXT PRIMARY KEY, ultima TEXT);
CREATE TABLE IF NOT EXISTS alcadas_decisoes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, item_tipo TEXT, item_id TEXT, decisor TEXT, validador TEXT,
  decisao TEXT, motivo TEXT, evidencia TEXT, reversivel_ate TEXT, ref INTEGER);
CREATE INDEX IF NOT EXISTS ix_alc_item ON alcadas_decisoes(item_tipo, item_id);
CREATE TRIGGER IF NOT EXISTS alcadas_decisoes_imutavel BEFORE UPDATE ON alcadas_decisoes
BEGIN SELECT RAISE(ABORT, 'decisão de alçada não muda depois de gravada'); END;
"""


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    with tb.tx() as c:
        c.executescript(ESQUEMA)
        from robo.trabalho import proteger
        proteger(c)
    return tb


def config(cfg) -> dict:
    return {**PADRAO, **((getattr(cfg, "dados", {}) or {}).get("autonomia") or {})}


def _iso(d: datetime) -> str:
    return d.isoformat(timespec="seconds")


# =============================================================================== presença do dono
def marcar_presenca(cfg, origem: str = "painel", agora: datetime | None = None) -> None:
    with _tb(cfg).tx() as c:
        c.execute("INSERT INTO dono_presenca (origem, ultima) VALUES (?,?) ON CONFLICT(origem) DO UPDATE SET "
                  "ultima=excluded.ultima", (origem, _iso(agora or datetime.now())))


def dono_offline(cfg, agora: datetime | None = None) -> dict:
    """Última presença = maior entre o painel usado e a entrada pelo celular. Nunca visto: conta desde a 1ª abertura do
    robô (sessoes). Sem nenhum registro, não presume ausência."""
    agora = agora or datetime.now()
    marcas = []
    with _tb(cfg).tx() as c:
        marcas += [r["ultima"] for r in c.execute("SELECT ultima FROM dono_presenca")]
        tabelas = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "acessos_celular" in tabelas:
            r = c.execute("SELECT max(data_hora) FROM acessos_celular WHERE evento='entrou'").fetchone()[0]
            marcas.append(r)
        primeira = c.execute("SELECT min(aberto_em) FROM sessoes").fetchone()[0] if "sessoes" in tabelas else None
    marcas = [datetime.fromisoformat(m) for m in marcas if m]
    ultima = max(marcas) if marcas else None
    referencia = ultima or (datetime.fromisoformat(primeira) if primeira else None)
    if referencia is None:
        return {"offline": False, "horas": None, "ultima": None, "motivo": "sem nenhum registro de presença nem de abertura"}
    horas = round((agora - referencia).total_seconds() / 3600, 2)
    return {"offline": horas >= float(config(cfg)["horas_offline"]), "horas": horas,
            "ultima": _iso(ultima) if ultima else None, "motivo": "" if ultima else "dono nunca registrado: conta desde a "
                                                                                  "1ª abertura do robô"}


# =============================================================================== quem decide e quem valida
def _pode_aprovar(pid, gente) -> bool:
    if not pid or pid == organizacao.DONO or pid not in gente:
        return False
    nivel = organizacao.nivel_de(pid, gente[pid])
    return nivel != "estagiario" and organizacao.PERMISSOES_NIVEL.get(nivel, {}).get("aprova", False)


def _escolher(candidatos, excluir, gente) -> str | None:
    for c in candidatos:
        if c not in excluir and _pode_aprovar(c, gente):
            return c
    return None


def _head_do_andar(pid, gente):
    from robo import lideranca
    return lideranca.HEAD_DO_ANDAR.get((gente.get(pid) or {}).get("andar"))


def par_para(cfg, item_tipo: str, item: dict) -> tuple[str | None, str | None]:
    """(decisor, validador) previstos pela matriz para um item."""
    gente = organizacao.por_id(cfg)
    if item_tipo == "proposta_regra":
        autor = item["autor"]
        decisor = _escolher([organizacao.gestor_de(autor), _head_do_andar(autor, gente), organizacao.revisor_de(autor, cfg)],
                            {autor}, gente)
        validador = _escolher([_head_do_andar(autor, gente), organizacao.gestor_de(decisor or ""), "dir_dados",
                               "dir_operacoes"], {autor, decisor}, gente)
        return decisor, validador
    if item_tipo == "decisao_atrasada":
        resp = item["dono"]
        g = organizacao.gestor_de(resp)
        decisor = g if g != resp and _pode_aprovar(g, gente) else None
        validador = _escolher([organizacao.gestor_de(decisor or ""), _head_do_andar(resp, gente), "dir_operacoes",
                               "ger_operacoes"], {resp, decisor}, gente)
        return decisor, validador
    if item_tipo == "rh_promocao":
        envolvidos = {item["funcionario"], item["proposto_por"]}
        decisor = _escolher(["head_rh", "dir_pessoas"], envolvidos, gente)
        validador = _escolher(["dir_pessoas", organizacao.gestor_de(decisor or ""), "dir_operacoes", "ger_operacoes"],
                              envolvidos | {decisor}, gente)
        return decisor, validador
    return None, None


# =============================================================================== prova de regra (computador de teste)
def provar_regra(cfg, p: dict) -> tuple[bool, str]:
    """Reprocessa o arquivo reprovado, em modo diagnóstico, numa pasta de teste, com as regras atuais + a proposta.
    Passa só se não sobrar NENHUM erro."""
    from robo import aprendizado
    from robo.config import Config
    from robo.pipeline import processar_arquivo
    arq = Path(p.get("arquivo_erros") or "")
    if not arq.is_file():
        return False, "o arquivo reprovado não está mais em Bases-Erros: não dá para provar"
    regra = cfg.regra_para(p["arquivo"])
    if not regra.get("padrao"):
        return False, "nenhuma regra do config.yaml casa com o arquivo"
    extra = {"sinonimos": {p["coluna"]: [p["valor"]]}} if p["tipo"] == "sinonimo" else {}
    nova = aprendizado.aplicar_overlay(aprendizado.aplicar_overlay(regra, aprendizado.regras_ativas(cfg, regra["padrao"])),
                                       extra)
    with tempfile.TemporaryDirectory(prefix="robo_alcada_") as d:
        base = Path(d)
        dados = copy.deepcopy(cfg.dados)
        dados["regras"] = [nova]
        dados["pastas"] = {k: str(base / k) for k in ("entrada", "logs", "agentes", "habilidades")}
        dados["banco"] = {**(dados.get("banco") or {}), "habilitado": False}
        teste = Config(dados, cfg.base)
        teste.criar_pastas()
        copia = Path(teste.entrada) / p["arquivo"]
        shutil.copy2(arq, copia)
        r = processar_arquivo(copia, teste, gravar=False)
    erros = [f"{o.mensagem}" + (f" ({o.coluna})" if o.coluna else "") for o in r.relatorio.erros]
    return (not erros), ("reprocessado sem nenhum erro" if not erros else "ainda reprova: " + "; ".join(erros[:3]))


# =============================================================================== autorização (chamada também pelos módulos)
def _ja_tratado(c, item_tipo, item_id) -> bool:
    return bool(c.execute("SELECT 1 FROM alcadas_decisoes WHERE item_tipo=? AND item_id=? AND decisao<>'revertida_pelo_dono'",
                          (item_tipo, str(item_id))).fetchone())


def autoriza(cfg, item_tipo: str, item_id, decisor: str, validador: str | None, agora: datetime | None = None
             ) -> tuple[bool, str]:
    """Confere TUDO de novo (os módulos chamam isto antes de aceitar alguém que não é o dono)."""
    agora = agora or datetime.now()
    k = config(cfg)
    if not k["habilitada"]:
        return False, "autonomia desligada no config.yaml"
    off = dono_offline(cfg, agora)
    if not off["offline"]:
        return False, "o dono está presente: a decisão é dele"
    gente = organizacao.por_id(cfg)
    if not decisor or not validador or decisor == validador:
        return False, "precisa de duas pessoas diferentes (quem decide e quem valida)"
    if not (_pode_aprovar(decisor, gente) and _pode_aprovar(validador, gente)):
        return False, "quem decide e quem valida precisam poder aprovar (estagiário e júnior não aprovam)"
    limite = _iso(agora - timedelta(hours=float(k["horas_pendente"])))
    with _tb(cfg).tx() as c:
        if _ja_tratado(c, item_tipo, item_id):
            return False, "este item já foi tratado por alçada"
        if item_tipo == "proposta_regra":
            from robo import aprendizado
            aprendizado._tb(cfg)
            p = c.execute("SELECT * FROM propostas_regra WHERE id=?", (item_id,)).fetchone()
            if not p or p["estado"] != "pendente":
                return False, "proposta inexistente ou já decidida"
            if not MATRIZ.get(f"proposta_regra:{p['tipo']}", ("", False))[1]:
                return False, f"regra do tipo '{p['tipo']}' é decisão do dono"
            if p["autor"] in (decisor, validador):
                return False, "o autor da proposta não decide nem valida"
            if p["criada_em"] > limite:
                return False, "pendência recente: espera o dono"
            p = dict(p)
        elif item_tipo == "decisao_atrasada":
            from robo import decisoes
            decisoes._tb(cfg)
            d = c.execute("SELECT * FROM decisoes WHERE id=?", (item_id,)).fetchone()
            if not d or d["estado"] != "atrasada":
                return False, "decisão inexistente ou não está atrasada"
            if decisor != organizacao.gestor_de(d["dono"]) or d["dono"] in (decisor, validador):
                return False, "quem repactua é o gestor do responsável (e o responsável não valida)"
            if c.execute("SELECT 1 FROM alcadas_decisoes WHERE item_tipo='decisao_atrasada' AND item_id=?", (item_id,)).fetchone():
                return False, "a alçada só repactua uma vez"
        elif item_tipo == "rh_promocao":
            from robo import rh_desempenho
            rh_desempenho._tb(cfg)
            m = c.execute("SELECT * FROM rh_movimentos WHERE id=?", (int(item_id),)).fetchone()
            if not m or m["tipo"] != "promocao" or m["situacao"] != "aguardando_dono":
                return False, "não há promoção esperando com esse número"
            if rh_desempenho.so_dono(m["de_nivel"], m["para_nivel"]):
                return False, "promoção que tira do estágio ou dá direito de alterar dados é do dono"
            if {m["funcionario"], m["proposto_por"]} & {decisor, validador}:
                return False, "o promovido e quem propôs não decidem nem validam"
            if m["data_hora"] > limite:
                return False, "pendência recente: espera o dono"
        else:
            return False, f"'{item_tipo}' está fora da matriz de alçadas: é do dono"
    if item_tipo == "proposta_regra":
        ok, prova = provar_regra(cfg, p)
        if not ok:
            return False, f"a prova não passou ({prova})"
    return True, "dentro da alçada"


def _registrar(cfg, agora, item_tipo, item_id, decisor, validador, decisao, motivo, evidencia, ref=None) -> int:
    reversivel = _iso(agora + timedelta(days=int(config(cfg)["dias_reversao"]))) if decisao == "aprovada_por_alcada" else None
    with _tb(cfg).tx() as c:
        cur = c.execute("INSERT INTO alcadas_decisoes (data_hora, item_tipo, item_id, decisor, validador, decisao, motivo, "
                        "evidencia, reversivel_ate, ref) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (_iso(agora), item_tipo, str(item_id), decisor, validador, decisao, motivo[:1000],
                         json.dumps(evidencia, ensure_ascii=False, default=str), reversivel, ref))
        return cur.lastrowid


def _anunciar(cfg, autor, texto) -> None:
    try:
        from robo.canal import Canal
        Canal(cfg).postar(autor or "ger_operacoes", texto, "geral", "decisao")
    except Exception:
        log.debug("Canal indisponível para a alçada", exc_info=True)


# =============================================================================== rodada
def pendencias(cfg, agora: datetime | None = None) -> list[dict]:
    """Tudo que espera o dono há mais de horas_pendente e ainda não foi tratado por alçada."""
    from robo import aprendizado, decisoes, rh_desempenho
    agora = agora or datetime.now()
    limite = _iso(agora - timedelta(hours=float(config(cfg)["horas_pendente"])))
    aprendizado._tb(cfg)
    decisoes.atualizar(cfg, agora.date())
    rh_desempenho._tb(cfg)
    itens = []
    with _tb(cfg).tx() as c:
        for p in c.execute("SELECT * FROM propostas_regra WHERE estado='pendente' AND criada_em<=? ORDER BY criada_em", (limite,)):
            itens.append({"item_tipo": "proposta_regra", "item_id": p["id"], "chave": f"proposta_regra:{p['tipo']}",
                          "item": dict(p), "texto": f"regra {p['tipo']} {p['coluna']} ← '{p['valor']}' ({p['padrao']})"})
        for d in c.execute("SELECT * FROM decisoes WHERE estado='atrasada' AND prazo<=? ORDER BY prazo", (limite[:10],)):
            itens.append({"item_tipo": "decisao_atrasada", "item_id": d["id"], "chave": "decisao_atrasada", "item": dict(d),
                          "texto": f"decisão atrasada: {d['texto'][:80]}"})
        for m in rh_desempenho.pendentes_dono(cfg):
            if m["data_hora"] > limite:
                continue
            if m["tipo"] == "promocao":
                chave = "rh_promocao_do_dono" if rh_desempenho.so_dono(m["de_nivel"], m["para_nivel"]) else "rh_promocao"
            else:
                chave = "rh_desligamento"
            itens.append({"item_tipo": "rh_promocao" if chave == "rh_promocao" else chave, "item_id": str(m["id"]),
                          "chave": chave, "item": m, "texto": f"{m['tipo']} de {m['funcionario']}"})
        tratados = {(r["item_tipo"], r["item_id"]) for r in c.execute("SELECT item_tipo, item_id FROM alcadas_decisoes")}
    return [i for i in itens if (i["item_tipo"], str(i["item_id"])) not in tratados]


def rodada(cfg, agora: datetime | None = None) -> dict:
    agora = agora or datetime.now()
    k = config(cfg)
    off = dono_offline(cfg, agora)
    if not k["habilitada"] or not off["offline"]:
        return {"offline": off, "decididas": [], "para_o_dono": []}
    decididas, para_o_dono = [], []
    for it in pendencias(cfg, agora):
        risco, autonomo, quem, porque = MATRIZ.get(it["chave"], ("alto", False, "dono", "fora da matriz"))
        if not autonomo:
            aid = _registrar(cfg, agora, it["item_tipo"], it["item_id"], None, None, "deixada_para_o_dono",
                             f"risco {risco}: {porque}", {"item": it["texto"]})
            para_o_dono.append({"alcada": aid, **{x: it[x] for x in ("item_tipo", "item_id", "texto")}, "motivo": porque})
            continue
        decisor, validador = par_para(cfg, it["item_tipo"], it["item"])
        ok, motivo = autoriza(cfg, it["item_tipo"], it["item_id"], decisor, validador, agora)
        if not ok:
            aid = _registrar(cfg, agora, it["item_tipo"], it["item_id"], decisor, validador, "deixada_para_o_dono", motivo,
                             {"item": it["texto"]})
            para_o_dono.append({"alcada": aid, **{x: it[x] for x in ("item_tipo", "item_id", "texto")}, "motivo": motivo})
            continue
        try:
            evid = _aplicar(cfg, it, decisor, validador, off, agora)
        except Exception as e:  # nada é dado como decidido se a aplicação falhou
            log.exception("Alçada: não consegui aplicar %s %s", it["item_tipo"], it["item_id"])
            aid = _registrar(cfg, agora, it["item_tipo"], it["item_id"], decisor, validador, "deixada_para_o_dono",
                             f"falhou ao aplicar: {type(e).__name__}: {e}", {"item": it["texto"]})
            para_o_dono.append({"alcada": aid, **{x: it[x] for x in ("item_tipo", "item_id", "texto")}, "motivo": str(e)})
            continue
        texto = (f"Dono fora há {off['horas']:.0f} h. {it['texto']}: aprovado por alçada — decide "
                 f"{decisor}, valida {validador}. Você pode reverter em {k['dias_reversao']} dias.")
        aid = _registrar(cfg, agora, it["item_tipo"], it["item_id"], decisor, validador, "aprovada_por_alcada",
                         f"{quem}; {porque}", evid)
        _anunciar(cfg, decisor, texto)
        decididas.append({"alcada": aid, "item_tipo": it["item_tipo"], "item_id": it["item_id"], "decisor": decisor,
                          "validador": validador, "texto": it["texto"]})
    return {"offline": off, "decididas": decididas, "para_o_dono": para_o_dono}


def _aplicar(cfg, it, decisor, validador, off, agora) -> dict:
    from robo import aprendizado, decisoes, rh_desempenho
    if it["item_tipo"] == "proposta_regra":
        r = aprendizado.decidir(cfg, it["item_id"], True, quem=decisor, validador=validador,
                                motivo=f"alçada (dono fora há {off['horas']:.0f} h); validado por {validador}")
        return {"reenviado": r.get("reenviado"), "prova": "reprocessado sem nenhum erro"}
    if it["item_tipo"] == "decisao_atrasada":
        novo = date.today() + timedelta(days=int(config(cfg)["dias_repactuacao"]))
        decisoes.repactuar(cfg, it["item_id"], novo, f"Alçada: dono fora há {off['horas']:.0f} h; repactuada pelo gestor "
                                                    f"{decisor}, validada por {validador}", "ALCADA",
                           quem=decisor, validador=validador)
        return {"prazo_anterior": it["item"]["prazo"], "prazo_novo": novo.isoformat()}
    if it["item_tipo"] == "rh_promocao":
        mid = rh_desempenho.aplicar_por_alcada(cfg, int(it["item_id"]), decisor, validador,
                                               f"alçada (dono fora há {off['horas']:.0f} h)", agora)
        return {"movimento": mid}
    raise ValueError("tipo fora da matriz")


def reverter(cfg, alcada_id: int, motivo: str, quem: str = "dono", agora: datetime | None = None) -> dict:
    """Só o dono, e só dentro do prazo de reversão. A decisão original continua registrada; a reversão é outra linha."""
    from robo import aprendizado, decisoes, rh_desempenho
    if quem != organizacao.DONO:
        raise PermissionError("Só o dono reverte uma decisão de alçada.")
    if len((motivo or "").strip()) < 5:
        raise ValueError("Diga o motivo da reversão.")
    agora = agora or datetime.now()
    with _tb(cfg).tx() as c:
        a = c.execute("SELECT * FROM alcadas_decisoes WHERE id=?", (alcada_id,)).fetchone()
        if not a or a["decisao"] != "aprovada_por_alcada":
            raise ValueError("Só uma decisão aprovada por alçada pode ser revertida.")
        if c.execute("SELECT 1 FROM alcadas_decisoes WHERE ref=? AND decisao='revertida_pelo_dono'", (alcada_id,)).fetchone():
            raise ValueError("Esta decisão já foi revertida.")
        if a["reversivel_ate"] and _iso(agora) > a["reversivel_ate"]:
            raise ValueError("Passou o prazo de reversão: trate como uma decisão nova.")
        a = dict(a)
    evid = json.loads(a["evidencia"] or "{}")
    if a["item_tipo"] == "proposta_regra":
        aprendizado.desativar(cfg, a["item_id"], "dono", f"reversão da alçada: {motivo}")
    elif a["item_tipo"] == "decisao_atrasada":
        decisoes.reverter_repactuacao(cfg, a["item_id"], evid.get("prazo_anterior"), motivo, quem="dono")
    elif a["item_tipo"] == "rh_promocao":
        rh_desempenho.reverter_movimento(cfg, int(evid["movimento"]), f"reversão da alçada: {motivo}", "dono", agora)
    rid = _registrar(cfg, agora, a["item_tipo"], a["item_id"], "dono", None, "revertida_pelo_dono", motivo, {}, alcada_id)
    _anunciar(cfg, "ger_operacoes", f"O dono reverteu a decisão de alçada {alcada_id} ({a['item_tipo']}): {motivo}")
    return {"ok": True, "reversao": rid}


def listar(cfg, limite: int = 100) -> list[dict]:
    with _tb(cfg).tx() as c:
        return [dict(r) for r in c.execute("SELECT * FROM alcadas_decisoes ORDER BY id DESC LIMIT ?", (limite,))]


def rotina(cfg) -> dict | None:
    r = rodada(cfg)
    if not r["decididas"] and not r["para_o_dono"]:
        return None
    return {"offline_horas": r["offline"]["horas"], "decididas": len(r["decididas"]), "para_o_dono": len(r["para_o_dono"])}
