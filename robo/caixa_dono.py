"""Caixa do dono: toda ideia e toda pendência que só o dono decide, num lugar só.

Entra na caixa:
  (a) ideias e sugestões de QUALQUER funcionário, sempre tiradas de dado registrado:
      - as ideias da Iara (ideias_registro);
      - sugestões que os próprios funcionários fazem pelos fatos (caixa_dono_sugestoes):
          * gestor sugere treinamento quando alguém da equipe errou 3 vezes ou mais a mesma competência (7 dias);
          * o responsável por uma rotina sugere correção quando ela terminou em erro 3 vezes ou mais (7 dias);
      - propostas de regra nova aprendida (propostas_regra pendentes);
  (b) o que espera decisão do dono em outros módulos (sem duplicar a lógica deles: a decisão é repassada):
      - promoção que só o dono decide e desligamento de contratado (rh_desempenho);
      - aprovações de solicitações (orquestrador).

Regras:
  - só o dono decide aqui (quem != "dono" → PermissionError); ninguém aprova a própria sugestão;
  - toda decisão vira evento PERMANENTE em caixa_dono_eventos (só inclusão);
  - ideia aprovada vira item do backlog da Estratégia para quem sugeriu e é anunciada no canal;
  - ideia recusada não volta por 30 dias, a não ser que o número que a motivou mude 25% ou mais.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta

from robo.trabalho import Trabalho, _agora

DIAS_SEM_REPETIR = 30
MUDANCA_RELEVANTE = 0.25

ESQUEMA = """CREATE TABLE IF NOT EXISTS caixa_dono_eventos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, item_id TEXT, tipo TEXT, decisao TEXT, quem TEXT, nota TEXT,
  origem TEXT, titulo TEXT, numero REAL, ref TEXT);
CREATE INDEX IF NOT EXISTS ix_caixa_item ON caixa_dono_eventos(item_id, id);
CREATE TRIGGER IF NOT EXISTS caixa_dono_eventos_sem_alterar BEFORE UPDATE ON caixa_dono_eventos
BEGIN SELECT RAISE(ABORT, 'registro permanente: caixa_dono_eventos não pode ser alterado'); END;
CREATE TABLE IF NOT EXISTS caixa_dono_sugestoes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, chave TEXT, autor TEXT, titulo TEXT, motivo TEXT,
  primeiro_passo TEXT, impacto INTEGER, numero REAL);
CREATE INDEX IF NOT EXISTS ix_caixa_sug ON caixa_dono_sugestoes(chave, data_hora);
CREATE TRIGGER IF NOT EXISTS caixa_dono_sugestoes_sem_alterar BEFORE UPDATE ON caixa_dono_sugestoes
BEGIN SELECT RAISE(ABORT, 'registro permanente: caixa_dono_sugestoes não pode ser alterado'); END;"""


def _tb(cfg) -> Trabalho:
    from robo.trabalho import proteger
    tb = Trabalho(cfg)
    with tb.tx() as c:
        c.executescript(ESQUEMA)
        proteger(c)
    return tb


def _tabelas(c) -> set[str]:
    return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _numero(texto: str) -> float | None:
    # o primeiro número "solto" (ignora códigos como HO-20261019-ab12 ou T832)
    m = re.search(r"(?<![\w-])\d+(?:[.,]\d+)?(?![\w-])", texto or "")
    return float(m.group(0).replace(",", ".")) if m else None


def _mudou_muito(antes: float | None, agora: float | None) -> bool:
    if antes is None or agora is None:
        return False
    if antes == 0:
        return agora != 0
    return abs(agora - antes) / abs(antes) >= MUDANCA_RELEVANTE


def _chave(*partes) -> str:
    return hashlib.sha256("|".join(str(p) for p in partes).encode()).hexdigest()[:16]


# =============================================================================== sugestões dos funcionários (fatos)
def gerar_sugestoes(cfg, agora: datetime | None = None) -> list[dict]:
    """Sugestões que os funcionários fazem pelos fatos registrados. Só registra a mesma sugestão de novo depois de
    7 dias (se o problema continuar). Devolve as novas."""
    from robo import organizacao
    from robo.rotinas import ROTINAS
    agora = agora or datetime.now()
    desde = (agora - timedelta(days=7)).isoformat(timespec="seconds")
    gente = organizacao.por_id(cfg)
    nome = lambda x: (gente.get(x) or {}).get("nome", x)  # noqa: E731
    candidatas = []
    tb = _tb(cfg)
    with tb.tx() as c:
        tem = _tabelas(c)
        if "treino_tentativas" in tem:
            from robo.treino_casos import CATALOGO
            for r in c.execute("SELECT funcionario, competencia, COUNT(*) n FROM treino_tentativas WHERE acertou=0 AND "
                               "data_hora>=? GROUP BY 1, 2 HAVING n >= 3 ORDER BY n DESC LIMIT 10", (desde,)):
                gestor = organizacao.gestor_de(r["funcionario"])
                if not gestor or gestor == organizacao.DONO:
                    gestor = "rh_td"
                comp = CATALOGO[r["competencia"]].nome if r["competencia"] in CATALOGO else r["competencia"]
                candidatas.append({
                    "chave": _chave("treino", r["funcionario"], r["competencia"]), "autor": gestor,
                    "titulo": f"Treinamento dirigido para {nome(r['funcionario'])} em {comp}",
                    "motivo": f"{r['n']} erros em {comp} nos últimos 7 dias (registrados em treino_tentativas)",
                    "primeiro_passo": "Sessão com quem mais acerta essa competência + revisão da lição do erro",
                    "impacto": 3, "numero": float(r["n"])})
        if "rotinas_execucoes" in tem:
            for r in c.execute("SELECT nome, COUNT(*) n FROM rotinas_execucoes WHERE status='erro' AND fim>=? GROUP BY 1 "
                               "HAVING n >= 3 ORDER BY n DESC", (desde,)):
                resp = (ROTINAS.get(r["nome"]) or ("airflow_pleno",))[0]
                candidatas.append({
                    "chave": _chave("rotina", r["nome"]), "autor": resp,
                    "titulo": f"Corrigir a rotina {r['nome']}, que vem terminando em erro",
                    "motivo": f"{r['n']} execuções com erro nos últimos 7 dias (rotinas_execucoes)",
                    "primeiro_passo": "Ler o detalhe do último erro no registro da rotina e reproduzir no computador de teste",
                    "impacto": 4, "numero": float(r["n"])})
        novas = []
        for s in candidatas:
            if c.execute("SELECT 1 FROM caixa_dono_sugestoes WHERE chave=? AND data_hora>=?", (s["chave"], desde)).fetchone():
                continue
            c.execute("INSERT INTO caixa_dono_sugestoes (data_hora, chave, autor, titulo, motivo, primeiro_passo, impacto, "
                      "numero) VALUES (?,?,?,?,?,?,?,?)", (agora.isoformat(timespec="seconds"), s["chave"], s["autor"],
                                                           s["titulo"], s["motivo"], s["primeiro_passo"], s["impacto"],
                                                           s["numero"]))
            novas.append(s)
    return novas


# =============================================================================== a caixa
def _ultimas_decisoes(c) -> dict[str, dict]:
    ult = {}
    for r in c.execute("SELECT * FROM caixa_dono_eventos ORDER BY id"):
        ult[r["item_id"]] = dict(r)
    return ult


def itens(cfg, agora: datetime | None = None, com_decididos: bool = True) -> list[dict]:
    """Tudo o que está (ou esteve) na caixa, mais novo primeiro. Situação: nova, aprovada, recusada."""
    from robo import organizacao
    agora = agora or datetime.now()
    gente = organizacao.por_id(cfg)

    def quem(pid):
        p = gente.get(pid) or {}
        return {"id": pid, "nome": p.get("nome", pid), "cargo": p.get("papel", "")}

    janela = (agora - timedelta(days=DIAS_SEM_REPETIR)).isoformat(timespec="seconds")
    lista = []
    tb = _tb(cfg)
    with tb.tx() as c:
        tem = _tabelas(c)
        decididos = _ultimas_decisoes(c)
        if "ideias_registro" in tem:
            vistos = set()
            for r in c.execute("SELECT * FROM ideias_registro WHERE data_hora>=? ORDER BY id DESC", (janela,)):
                if r["chave"] in vistos:
                    continue
                vistos.add(r["chave"])
                lista.append({"id": f"ideia:{r['chave']}", "tipo": "ideia", "data_hora": r["data_hora"], "origem": quem(r["dono"]),
                              "sugerido_por": quem("canal_iara"), "titulo": r["titulo"], "motivo": r["motivo"],
                              "primeiro_passo": r["primeiro_passo"], "impacto": r["impacto"], "numero": _numero(r["motivo"]),
                              "decide": "aprovar_recusar"})
        vistos = set()
        for r in c.execute("SELECT * FROM caixa_dono_sugestoes WHERE data_hora>=? ORDER BY id DESC", (janela,)):
            if r["chave"] in vistos:
                continue
            vistos.add(r["chave"])
            lista.append({"id": f"sug:{r['chave']}", "tipo": "sugestao", "data_hora": r["data_hora"], "origem": quem(r["autor"]),
                          "sugerido_por": quem(r["autor"]), "titulo": r["titulo"], "motivo": r["motivo"],
                          "primeiro_passo": r["primeiro_passo"], "impacto": r["impacto"], "numero": r["numero"],
                          "decide": "aprovar_recusar"})
        if "propostas_regra" in tem:
            for r in c.execute("SELECT * FROM propostas_regra WHERE estado='pendente' ORDER BY criada_em DESC"):
                lista.append({"id": f"regra:{r['id']}", "tipo": "regra", "data_hora": r["criada_em"], "origem": quem(r["autor"]),
                              "sugerido_por": quem(r["autor"]),
                              "titulo": f"Regra nova: {r['tipo']} em {r['coluna']} ← '{r['valor']}'",
                              "motivo": r["motivo"] or "", "primeiro_passo": "Aprovar faz a regra valer na próxima planilha",
                              "impacto": 3, "numero": None, "decide": "aprovar_recusar"})
        if "rh_movimentos" in tem:
            for r in c.execute("SELECT * FROM rh_movimentos m WHERE situacao='aguardando_dono' AND NOT EXISTS (SELECT 1 FROM "
                               "rh_movimentos d WHERE d.ref=m.id AND d.tipo IN ('decisao_dono','decisao_alcada')) ORDER BY id DESC"):
                alvo = quem(r["funcionario"])["nome"]
                titulo = (f"Promoção de {alvo}: {r['de_nivel']} → {r['para_nivel']}" if r["tipo"] == "promocao"
                          else f"Desligamento proposto: {alvo}")
                lista.append({"id": f"rh:{r['id']}", "tipo": "rh", "data_hora": r["data_hora"], "origem": quem(r["proposto_por"]),
                              "sugerido_por": quem(r["proposto_por"]), "titulo": titulo, "motivo": r["motivo"] or "",
                              "primeiro_passo": "A decisão vale na hora e fica registrada no RH", "impacto": 4, "numero": None,
                              "decide": "aprovar_recusar"})
        if "aprovacoes" in tem:
            for r in c.execute("SELECT a.*, s.titulo, s.funcionario FROM aprovacoes a JOIN solicitacoes s ON "
                               "s.id=a.solicitacao_id WHERE a.estado='pendente' ORDER BY a.criada_em DESC"):
                r = dict(r)
                pediu = r.get("solicitante") or r.get("funcionario") or ""
                lista.append({"id": f"aprov:{r['id']}", "tipo": "aprovacao", "data_hora": r.get("criada_em"),
                              "origem": quem(pediu), "sugerido_por": quem(pediu),
                              "titulo": f"Aprovar: {r.get('titulo') or ''}",
                              "motivo": (r.get("pedido") or "") + (f" (risco {r['risco']})" if r.get("risco") else ""),
                              "primeiro_passo": "Aprovar libera o próximo passo da solicitação", "impacto": 3, "numero": None,
                              "decide": "aprovar_recusar"})
    saida = []
    for it in lista:
        d = decididos.get(it["id"])
        if d and d["decisao"] == "recusada" and d["data_hora"] >= janela and _mudou_muito(d["numero"], it["numero"]):
            d = None  # o número que motivou mudou muito: volta para a caixa como nova
        it["situacao"] = d["decisao"] if d else "nova"
        it["decidido_em"] = d["data_hora"] if d else None
        it["nota_dono"] = d["nota"] if d else ""
        if it["situacao"] == "nova" or com_decididos:
            saida.append(it)
    saida.sort(key=lambda x: str(x["data_hora"] or ""), reverse=True)            # mais novo primeiro…
    saida.sort(key=lambda x: (x["situacao"] != "nova", -(x["impacto"] or 0)))   # …dentro de: novas antes, maior impacto antes
    return saida


def resumo(cfg) -> dict:
    todos = itens(cfg)
    novas = [i for i in todos if i["situacao"] == "nova"]
    return {"novas": len(novas), "ideias_novas": sum(i["tipo"] in ("ideia", "sugestao") for i in novas),
            "pendencias_novas": sum(i["tipo"] in ("regra", "rh", "aprovacao") for i in novas)}


def decidir(cfg, item_id: str, aprovar: bool, nota: str = "", quem: str = "dono") -> dict:
    """Só o dono decide. A decisão é repassada ao módulo dono do assunto e registrada para sempre."""
    from robo import organizacao
    if quem != organizacao.DONO:
        raise PermissionError("Só o dono decide os itens da Caixa do dono.")
    it = next((i for i in itens(cfg) if i["id"] == item_id), None)
    if not it:
        raise ValueError("Item não encontrado na caixa.")
    if it["situacao"] != "nova":
        raise ValueError("Este item já foi decidido.")
    if it["sugerido_por"]["id"] == quem:
        raise PermissionError("Ninguém aprova a própria sugestão.")
    nota = (nota or "").strip()[:500]
    tipo, ref = it["tipo"], item_id.split(":", 1)[1]
    detalhe = {}
    if tipo == "regra":
        from robo import aprendizado
        detalhe = aprendizado.decidir(cfg, ref, aprovar, "dono", nota or ("aprovada na Caixa do dono" if aprovar else "recusada"))
    elif tipo == "rh":
        from robo import rh_desempenho
        detalhe = rh_desempenho.decidir_dono(cfg, int(ref), aprovar, nota or ("Aprovado pelo dono na Caixa do dono" if aprovar
                                                                              else "Recusado pelo dono na Caixa do dono"))
    elif tipo == "aprovacao":
        from robo import orquestrador
        detalhe = orquestrador.decidir(cfg, ref, aprovar, nota)
    elif aprovar:  # ideia/sugestão aprovada vira trabalho de quem sugeriu
        from robo import estrategia
        resp = it["origem"]["id"]
        item = estrategia.salvar_item(cfg, {"titulo": it["titulo"], "responsavel": resp, "impacto": it["impacto"] or 3,
                                            "motivo": f"Aprovada pelo dono na Caixa do dono. Motivo: {it['motivo']}. "
                                                      f"Primeiro passo: {it['primeiro_passo']}"
                                                      + (f". Nota do dono: {nota}" if nota else "")})
        detalhe = {"backlog": item["id"]}
    with _tb(cfg).tx() as c:
        c.execute("INSERT INTO caixa_dono_eventos (data_hora, item_id, tipo, decisao, quem, nota, origem, titulo, numero, ref) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?)", (_agora(), item_id, tipo, "aprovada" if aprovar else "recusada", quem, nota,
                                                   it["origem"]["id"], it["titulo"], it["numero"],
                                                   json.dumps(detalhe, ensure_ascii=False, default=str)[:1000]))
    try:
        from robo.canal import Canal
        texto = (f"O dono {'aprovou' if aprovar else 'recusou'}: {it['titulo']}"
                 + (f" → vira trabalho de {it['origem']['nome']} no backlog" if aprovar and tipo in ("ideia", "sugestao") else "")
                 + (f". Nota: {nota}" if nota else ""))
        Canal(cfg).postar("ger_operacoes", texto, "geral", "decisao")
    except Exception:
        pass
    return {"ok": True, "item": item_id, "decisao": "aprovada" if aprovar else "recusada", "detalhe": detalhe}


def rotina(cfg) -> dict:
    """De hora em hora: os funcionários registram as sugestões que os fatos pedem; a caixa avisa o que chegou."""
    novas = gerar_sugestoes(cfg)
    if novas:
        try:
            from robo.canal import Canal
            Canal(cfg).postar("ger_operacoes", f"{len(novas)} sugestão(ões) nova(s) da equipe foram para a Caixa do dono: "
                              + " | ".join(s["titulo"] for s in novas[:3]), "geral", "ideia")
        except Exception:
            pass
    return {"sugestoes_novas": len(novas), **resumo(cfg)}
