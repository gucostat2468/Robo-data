"""Estratégia: backlog priorizado da sprint, alinhado com todos os andares, avaliações técnicas e treinamentos.

Backlog (logs/estrategia/backlog.json)
  Cada item tem responsável, andar, impacto, urgência e esforço (1 a 5).
  Prioridade = impacto × urgência ÷ esforço (quanto maior, primeiro).
  Itens AUTOMÁTICOS nascem dos dados — erro que se repete, alerta de TI, caso de treinamento que falhou,
  pessoa reprovada na avaliação, experiência de estagiário terminando, alerta de análise, ideias da Iara —
  e são dados como feitos sozinhos quando a condição some (com essa observação, para ninguém ser enganado).
  Itens do DONO entram pelo painel e só mudam quando alguém muda.

Avaliações técnicas (logs/rh/avaliacoes.jsonl)
  Reaplica, do zero, as provas de TODO o quadro (nada vem do cache) e guarda o histórico.

Treinamentos (logs/rh/treinamentos.jsonl)
  Roda o centro de treinamento (robo/treinamento.py) e mostra, por pessoa, os casos difíceis que ela domina.

Rotina: avaliação + treinamento rodam sozinhos uma vez por sprint (15 dias) e quando você pede no painel.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

from robo import historico

STATUS = ["a_fazer", "fazendo", "travado", "feito"]
NOME_STATUS = {"a_fazer": "A fazer", "fazendo": "Fazendo", "travado": "Travado", "feito": "Feito"}
LIDER_ANDAR = {1: "coord_engenharia", 2: "coord_analise", 3: "coord_excel", 4: "canal_helena", 5: "coord_devops"}
GERENTE_ANDAR = {1: "ger_engenharia", 2: "ger_analise", 3: "excel_supervisor", 4: "ger_operacoes", 5: "ger_ti"}
_trava = threading.Lock()


def _pasta(cfg) -> Path:
    p = Path(cfg.logs) / "estrategia"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def prioridade(item: dict) -> float:
    return round(int(item.get("impacto", 3)) * int(item.get("urgencia", 3)) / max(1, int(item.get("esforco", 3))), 2)


# =============================================================================== backlog
def ler_backlog(cfg) -> list[dict]:
    arq = _pasta(cfg) / "backlog.json"
    try:
        return json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _salvar(cfg, itens: list[dict]) -> None:
    arq = _pasta(cfg) / "backlog.json"
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(itens, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(arq)


def salvar_item(cfg, dados: dict) -> dict:
    """Cria ou atualiza um item (pelo painel). Valida tudo o que chega."""
    titulo = str(dados.get("titulo", "")).strip()[:200]
    if not titulo and not dados.get("id"):
        raise ValueError("Escreva o que precisa ser feito.")
    with _trava:
        itens = ler_backlog(cfg)
        item = next((i for i in itens if i["id"] == dados.get("id")), None)
        if item is None:
            item = {"id": f"d{int(datetime.now().timestamp() * 1000)}", "origem": "dono", "criado_em": _agora(),
                    "chave": "", "status": "a_fazer"}
            itens.append(item)
        if titulo:
            item["titulo"] = titulo
        for campo in ("motivo", "responsavel"):
            if campo in dados:
                item[campo] = str(dados[campo] or "")[:500]
        for campo in ("impacto", "urgencia", "esforco"):
            if campo in dados:
                item[campo] = min(5, max(1, int(dados[campo])))
        if "andar" in dados:
            item["andar"] = min(9, max(1, int(dados["andar"])))
        if dados.get("status") in STATUS:
            if dados["status"] != item.get("status"):
                item.setdefault("historico", []).append(f"{_agora()}: {NOME_STATUS.get(item.get('status'), '')} → "
                                                       f"{NOME_STATUS[dados['status']]}")
            item["status"] = dados["status"]
        for campo, padrao in (("impacto", 3), ("urgencia", 3), ("esforco", 3), ("andar", 1), ("motivo", "")):
            item.setdefault(campo, padrao)
        item["prioridade"] = prioridade(item)
        item["atualizado_em"] = _agora()
        _salvar(cfg, itens)
    return item


def excluir_item(cfg, item_id: str) -> None:
    with _trava:
        itens = [i for i in ler_backlog(cfg) if i["id"] != item_id]
        _salvar(cfg, itens)


def _automaticos(cfg) -> list[dict]:
    """O que os dados de hoje dizem que precisa ser feito. Cada item tem uma 'chave' estável (para não duplicar)."""
    itens = []
    hoje = date.today()
    corte = (hoje - timedelta(days=15)).isoformat()
    hist = [h for h in historico.ler(cfg.logs, 3000) if (h.get("data_hora") or "")[:10] >= corte]
    # 1. erro que se repete nas reprovações
    motivos: dict[str, int] = {}
    for h in hist:
        if h.get("status") != "reprovado":
            continue
        exe = historico.ler_execucao(cfg.logs, h.get("id") or "") or {}
        for o in exe.get("ocorrencias") or []:
            if o.get("nivel") == "ERRO":
                m = re.sub(r"\d+", "N", str(o.get("mensagem", "")))[:110]
                motivos[m] = motivos.get(m, 0) + 1
                break
    for m, n in sorted(motivos.items(), key=lambda x: -x[1])[:5]:
        if n >= 2:
            itens.append({"chave": "erro:" + m, "titulo": f"Eliminar na origem: {m}", "andar": 1, "responsavel": "coord_engenharia",
                          "motivo": f"Barrou {n} arquivo(s) nos últimos 15 dias.", "impacto": 4, "urgencia": min(5, 2 + n),
                          "esforco": 2})
    # 2. alertas de TI
    try:
        from robo import ti
        ronda = ti.ultima_ronda(cfg) or {}
        for i in ronda.get("itens") or []:
            if i["nivel"] == "estagiario":
                continue
            for a in i["achados"]:
                itens.append({"chave": "ti:" + a[:120], "titulo": f"TI: {a[:150]}", "andar": 5, "responsavel": i["id"],
                              "motivo": "Alerta da ronda de TI.", "impacto": 4, "urgencia": 5 if "CRÍTICO" in a else 3, "esforco": 2})
    except Exception:
        pass
    # 3. casos de treinamento que falharam
    from robo import treinamento
    ultimo = (treinamento.historico(cfg, 1) or [None])[-1]
    for c in (ultimo or {}).get("casos") or []:
        if not c["ok"]:
            itens.append({"chave": "treino:" + c["id"], "titulo": f"Corrigir o robô para: {c['titulo']}", "andar": 1,
                          "responsavel": c["responsaveis"][0], "motivo": "; ".join(c["falhas"])[:300], "impacto": 5,
                          "urgencia": 4, "esforco": 3})
    # 4. reprovados na avaliação técnica
    av = (ler_avaliacoes(cfg, 1) or [None])[-1]
    for p in (av or {}).get("pessoas") or []:
        if not p["aprovado"]:
            itens.append({"chave": "avaliacao:" + p["id"], "titulo": f"Treinar {p['nome']} até passar na avaliação técnica",
                          "andar": p.get("andar", 1), "responsavel": LIDER_ANDAR.get(p.get("andar", 1), "canal_helena"),
                          "motivo": "; ".join(p.get("bloqueios") or [])[:300], "impacto": 5, "urgencia": 5, "esforco": 2})
    # 5. experiência de estagiário terminando
    try:
        from robo.pipeline import obter_equipe
        for a in obter_equipe(cfg).personalizados:
            fim = a.get("fim_experiencia")
            if a.get("nivel") == "estagiario" and fim and date.fromisoformat(str(fim)) - hoje <= timedelta(days=15):
                itens.append({"chave": "experiencia:" + a["id"], "titulo": f"Avaliar a experiência de {a['nome']} (termina {fim})",
                              "andar": int(a.get("andar") or 1), "responsavel": a.get("contratante") or "canal_helena",
                              "motivo": "Período de 3 meses terminando.", "impacto": 3, "urgencia": 4, "esforco": 1})
    except Exception:
        pass
    # 6. alertas de monitoramento das análises
    pasta = Path(cfg.logs) / "analises"
    vistos = set()
    for arq in sorted(pasta.glob("2*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:30] if pasta.exists() else []:
        try:
            d = json.loads(arq.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if d.get("base") in vistos:
            continue
        vistos.add(d.get("base"))
        for a in d.get("alertas") or []:
            if a.get("nivel") == "atenção":
                texto = str(a.get("mensagem") or a.get("alerta") or a.get("metrica") or "variação fora do normal")[:140]
                itens.append({"chave": f"analise:{d.get('base')}:{texto}", "titulo": f"Investigar em {d.get('base')}: {texto}",
                              "andar": 2, "responsavel": "analise_monitoramento", "motivo": "Alerta do monitoramento.",
                              "impacto": 4, "urgencia": 3, "esforco": 2})
    # 7. ideias da Iara (no máximo 2 por vez, para manter o foco)
    try:
        from robo.canal import ideias
        for ideia in ideias(cfg)[:2]:
            titulo = ideia.split(". Motivo:")[0]
            itens.append({"chave": "ideia:" + titulo[:100], "titulo": titulo[:180], "andar": 4, "responsavel": "canal_iara",
                          "motivo": ideia[len(titulo):].strip(" .")[:300], "impacto": 3, "urgencia": 2, "esforco": 3})
    except Exception:
        pass
    return itens


def sincronizar(cfg) -> dict:
    """Atualiza o backlog com o que os dados mostram. Não mexe em itens do dono."""
    novos = self_resolvidos = 0
    with _trava:
        itens = ler_backlog(cfg)
        auto = {i["chave"]: i for i in _automaticos(cfg)}
        existentes = {i.get("chave"): i for i in itens if i.get("origem") == "automatico"}
        for chave, a in auto.items():
            if chave in existentes:
                e = existentes[chave]
                if e["status"] == "feito" and e.get("resolvido_sozinho"):
                    e["status"], e["resolvido_sozinho"] = "a_fazer", False  # o problema voltou
                    e.setdefault("historico", []).append(f"{_agora()}: o problema voltou → A fazer")
                e["motivo"] = a["motivo"]
                continue
            item = {**a, "id": "a" + hashlib.sha1(chave.encode()).hexdigest()[:10], "origem": "automatico",
                    "status": "a_fazer", "criado_em": _agora(), "atualizado_em": _agora()}
            item["prioridade"] = prioridade(item)
            itens.append(item)
            novos += 1
        for chave, e in existentes.items():
            if chave not in auto and e["status"] != "feito":
                e["status"], e["resolvido_sozinho"] = "feito", True
                e.setdefault("historico", []).append(f"{_agora()}: resolvido (a condição não aparece mais nos dados)")
                e["atualizado_em"] = _agora()
                self_resolvidos += 1
        for i in itens:
            i["prioridade"] = prioridade(i)
        _salvar(cfg, itens)
    return {"novos": novos, "resolvidos": self_resolvidos}


def alinhamento(cfg, itens: list[dict] | None = None) -> list[dict]:
    """Por andar: o gerente assume as 3 prioridades abertas mais importantes da sprint."""
    from robo.canal import pessoas
    gente = pessoas()
    itens = itens if itens is not None else ler_backlog(cfg)
    abertos = sorted([i for i in itens if i["status"] != "feito"], key=lambda i: -i.get("prioridade", 0))
    saida = []
    for andar in sorted({1, 2, 3, 4, 5} | {int(i.get("andar") or 1) for i in itens}):
        top = [i for i in abertos if int(i.get("andar") or 1) == andar][:3]
        g = GERENTE_ANDAR.get(andar)
        saida.append({"andar": andar, "gerente": gente.get(g, {}).get("nome", g) if g else "—",
                      "prioridades": [{"titulo": i["titulo"], "responsavel": gente.get(i.get("responsavel"), {}).get("nome",
                                       i.get("responsavel")), "status": NOME_STATUS[i["status"]], "prioridade": i["prioridade"]}
                                      for i in top],
                      "travados": sum(1 for i in itens if int(i.get("andar") or 1) == andar and i["status"] == "travado")})
    return saida


# =============================================================================== avaliações técnicas
def avaliar_todos(cfg) -> dict:
    """Reaplica as provas de todo o quadro, do zero. Devolve e grava o resultado."""
    from robo import rh
    from robo.agentes import NATIVOS
    from robo.analise import ANALISTAS
    from robo.canal import EQUIPE_CANAL
    from robo.excel import EQUIPE_EXCEL
    from robo.pipeline import obter_equipe
    from robo.producao import SUPERVISORES
    from robo.quadro import QUADRO
    from robo.ti import EQUIPE_TI
    rh._provas_nativas_cache.cache_clear()
    pessoas = [(a["id"], a["nome"], 1) for a in NATIVOS] + [(a["id"], a["nome"], a["andar"]) for a in SUPERVISORES]
    pessoas += [(f"analise_{a['id']}", a["nome"], 2) for a in ANALISTAS] + [(a["id"], a["nome"], 3) for a in EQUIPE_EXCEL]
    pessoas += [(p["id"], p["nome"], p["andar"]) for p in QUADRO] + [(a["id"], a["nome"], a["andar"]) for a in EQUIPE_CANAL]
    pessoas += [(p["id"], p["nome"], 5) for p in EQUIPE_TI]
    resultado = []
    for pid, nome, andar in pessoas:
        f = rh.ficha({"id": pid, "habilidades": []})
        p = f["provas"]
        resultado.append({"id": pid, "nome": nome, "andar": andar, "nivel": f.get("nivel"), "acertos": p["acertos"],
                          "total": p["total"], "aprovado": p["aprovado"], "bloqueios": p["bloqueios"]})
    for a in obter_equipe(cfg).personalizados:
        if not a.get("ativo", True):
            continue
        p = rh.processo_seletivo(a)
        resultado.append({"id": a["id"], "nome": a["nome"], "andar": int(a.get("andar") or 1),
                          "nivel": rh.NOME_NIVEL.get(a.get("nivel"), a.get("nivel")), "acertos": p["acertos"],
                          "total": p["total"], "aprovado": p["aprovado"], "bloqueios": p["bloqueios"]})
    registro = {"data_hora": _agora(), "pessoas": resultado, "aprovados": sum(r["aprovado"] for r in resultado),
                "total": len(resultado)}
    pasta = Path(cfg.logs) / "rh"
    pasta.mkdir(parents=True, exist_ok=True)
    with open(pasta / "avaliacoes.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")
    return registro


def ler_avaliacoes(cfg, limite: int = 20) -> list[dict]:
    arq = Path(cfg.logs) / "rh" / "avaliacoes.jsonl"
    if not arq.exists():
        return []
    saida = []
    for l in arq.read_text(encoding="utf-8").splitlines()[-limite:]:
        try:
            saida.append(json.loads(l))
        except json.JSONDecodeError:
            continue
    return saida


def treinar_todos(cfg) -> dict:
    from robo import treinamento
    r = treinamento.rodar()
    treinamento.registrar(cfg, r)
    return r


def trilhas(cfg) -> list[dict]:
    """Por pessoa: casos difíceis sob sua responsabilidade e quantos ela domina (último treinamento)."""
    from robo import treinamento
    from robo.canal import pessoas
    gente = pessoas()
    ultimo = (treinamento.historico(cfg, 1) or [None])[-1]
    status = {c["id"]: c["ok"] for c in (ultimo or {}).get("casos") or []}
    por_pessoa: dict[str, list] = {}
    for caso in treinamento.CASOS:
        for p in caso.responsaveis:
            por_pessoa.setdefault(p, []).append({"id": caso.id, "titulo": caso.titulo, "ok": status.get(caso.id)})
    return [{"id": p, "nome": gente.get(p, {}).get("nome", p), "papel": gente.get(p, {}).get("papel", ""), "casos": casos,
             "dominados": sum(1 for c in casos if c["ok"]), "total": len(casos)}
            for p, casos in sorted(por_pessoa.items(), key=lambda x: gente.get(x[0], {}).get("nome", x[0]))]


def rotina(cfg) -> bool:
    """Uma vez por sprint: avaliação técnica + treinamento + sincronização do backlog e aviso no canal #rh."""
    av = ler_avaliacoes(cfg, 1)
    ultima = datetime.strptime(av[-1]["data_hora"], "%Y-%m-%d %H:%M:%S") if av else None
    if ultima and datetime.now() - ultima < timedelta(days=15):
        sincronizar(cfg)
        return False
    a = avaliar_todos(cfg)
    t = treinar_todos(cfg)
    sincronizar(cfg)
    try:
        from robo.canal import Canal
        Canal(cfg).postar("canal_helena", f"Avaliação técnica da sprint: {a['aprovados']}/{a['total']} pessoas aprovadas. "
                                          f"Treinamento com planilhas difíceis: {t['aprovados']}/{t['total']} casos dominados."
                                          + ("" if t["aprovados"] == t["total"] else " Os casos que falharam viraram prioridade "
                                                                                     "na sprint."), "rh", "acontecimento")
    except Exception:
        pass
    return True
