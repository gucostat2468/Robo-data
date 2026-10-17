"""Central de dados: o que está acontecendo agora, por área, a partir do histórico real do robô.

Tudo vem de logs/historico.csv e dos detalhes de cada execução (logs/execucoes/<id>.json).
Os detalhes de cada execução são lidos uma única vez e guardados em memória (o painel atualiza a cada 3 s).
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from robo import historico


def _num_br(v) -> float:
    """Número do histórico (gravado com vírgula decimal: '0,3')."""
    try:
        return float(str(v or 0).replace(".", "").replace(",", ".")) if "," in str(v or "") else float(v or 0)
    except ValueError:
        return 0.0

_CACHE: dict[str, dict] = {}


def _resumo_execucao(cfg, i: str) -> dict:
    if i in _CACHE:
        return _CACHE[i]
    exe = historico.ler_execucao(cfg.logs, i) or {}
    ocorr = exe.get("ocorrencias") or []
    erros = [o for o in ocorr if o.get("nivel") == "ERRO"]
    avisos = [o for o in ocorr if o.get("nivel") == "AVISO"]
    principal = erros[0]["mensagem"] if erros else ""
    quem = ("Supervisor de planilhas" if "Supervisor" in principal else "DBA" if "DBA" in principal
            else "Equipe (plenos/juniores)" if "conferência da equipe" in principal
            else "Coordenadora de Engenharia" if "Coordenadora" in principal
            else "Leitura" if "aberto" in principal or "codificação" in principal or "aba com dados" in principal
            else "Auditoria (regras)" if erros else "")
    analise = exe.get("analise") or {}
    excel = exe.get("excel") or {}
    r = {"erros": len(erros), "avisos": len(avisos), "motivo": principal, "quem_barrou": quem,
         "exemplos": (erros[0].get("exemplos") or [])[:3] if erros else [],
         "manchete": analise.get("manchete"), "base": analise.get("base"),
         "ressalvas": len((exe.get("checklist_analise") or {}).get("ressalvas") or []),
         "excel_conferencias": int(excel.get("conferencias") or 0), "excel_ok": excel.get("revisao_ok", bool(excel)),
         "quadro": [{"id": q["id"], "nome": q["nome"], "andar": q["andar"], "achados": len(q.get("achados") or [])}
                    for q in exe.get("quadro") or []],
         "avisos_top": [o["mensagem"] for o in avisos][:3]}
    if exe:
        _CACHE[i] = r
    return r


def _janela(dias: int) -> str:
    return (date.today() - timedelta(days=max(0, dias - 1))).isoformat()


def montar(cfg, dias: int = 1) -> dict:
    dias = min(max(int(dias or 1), 1), 90)
    inicio = _janela(dias)
    hist = [h for h in historico.ler(cfg.logs, 20000) if (h.get("data_hora") or "")[:10] >= inicio]
    ok = [h for h in hist if h.get("status") == "sucesso"]
    ruim = [h for h in hist if h.get("status") == "reprovado"]
    soma = lambda lista, campo: sum(int(h.get(campo) or 0) for h in lista)

    # série por dia (sempre os últimos 14 dias, para enxergar tendência)
    serie = []
    todos = historico.ler(cfg.logs, 20000)
    for k in range(13, -1, -1):
        d = (date.today() - timedelta(days=k)).isoformat()
        do_dia = [h for h in todos if (h.get("data_hora") or "").startswith(d)]
        serie.append({"dia": d, "aprovados": sum(h.get("status") == "sucesso" for h in do_dia),
                      "reprovados": sum(h.get("status") == "reprovado" for h in do_dia)})

    detalhes = {h.get("id"): _resumo_execucao(cfg, h.get("id") or "") for h in hist[:500]}
    motivos: dict[str, int] = {}
    quem: dict[str, int] = {}
    for h in ruim:
        d = detalhes.get(h.get("id")) or {}
        if d.get("motivo"):
            chave = re.sub(r"\d+", "N", d["motivo"])[:120]
            motivos[chave] = motivos.get(chave, 0) + 1
        if d.get("quem_barrou"):
            quem[d["quem_barrou"]] = quem.get(d["quem_barrou"], 0) + 1

    # conferências do quadro por pessoa (achados no período)
    por_pessoa: dict[str, dict] = {}
    for d in detalhes.values():
        for q in d.get("quadro") or []:
            p = por_pessoa.setdefault(q["id"], {"nome": q["nome"], "andar": q["andar"], "conferencias": 0, "achados": 0})
            p["conferencias"] += 1
            p["achados"] += q["achados"]

    analises = [{"arquivo": h.get("arquivo"), "data_hora": h.get("data_hora"), "manchete": detalhes[h.get("id")]["manchete"],
                 "base": detalhes[h.get("id")]["base"], "ressalvas": detalhes[h.get("id")]["ressalvas"], "id": h.get("id")}
                for h in ok if detalhes.get(h.get("id"), {}).get("manchete")][:15]
    alertas_monit = _alertas_monitoramento(cfg, inicio)
    entregas = [d for h in ok for d in [detalhes.get(h.get("id")) or {}] if d.get("excel_conferencias")]
    try:
        from robo import ti
        ronda = ti.ultima_ronda(cfg) or {}
    except Exception:
        ronda = {}
    lgpd = sum(p["achados"] for i, p in por_pessoa.items() if i == "gov_pleno_lgpd")

    return {
        "atualizado_em": datetime.now().strftime("%H:%M:%S"), "dias": dias,
        "totais": {"recebidos": len(hist), "aprovados": len(ok), "reprovados": len(ruim),
                   "adiados": sum(h.get("status") == "adiado" for h in hist),
                   "taxa_aprovacao": round(100 * len(ok) / len(hist), 1) if hist else None,
                   "linhas_publicadas": soma(ok, "linhas_saida"),
                   "linhas_removidas": soma(ok, "linhas_entrada") - soma(ok, "linhas_saida"),
                   "avisos": soma(hist, "avisos"), "erros": soma(ruim, "erros"),
                   "tempo_medio": round(sum(_num_br(h.get("duracao_seg")) for h in ok) / len(ok), 1) if ok else None},
        "serie": serie,
        "erradas": [{"id": h.get("id"), "arquivo": h.get("arquivo"), "data_hora": h.get("data_hora"),
                     "erros": int(h.get("erros") or 0), **{k: (detalhes.get(h.get("id")) or {}).get(k)
                                                           for k in ("motivo", "quem_barrou", "exemplos")}} for h in ruim[:25]],
        "acertos": [{"id": h.get("id"), "arquivo": h.get("arquivo"), "data_hora": h.get("data_hora"),
                     "linhas": int(h.get("linhas_saida") or 0), "avisos": int(h.get("avisos") or 0)} for h in ok[:15]],
        "motivos": [{"motivo": m, "vezes": n} for m, n in sorted(motivos.items(), key=lambda x: -x[1])[:8]],
        "quem_barrou": [{"quem": q, "vezes": n} for q, n in sorted(quem.items(), key=lambda x: -x[1])],
        "areas": {
            "1": {"titulo": "Engenharia de dados", "recebidos": len(hist), "aprovados": len(ok), "reprovados": len(ruim),
                  "linhas": soma(ok, "linhas_saida")},
            "2": {"titulo": "Análise e qualidade", "bases_analisadas": len(analises),
                  "com_ressalva": sum(1 for a in analises if a["ressalvas"]), "alertas": len(alertas_monit)},
            "3": {"titulo": "Sala Excel", "entregas": len(entregas),
                  "conferencias": sum(d["excel_conferencias"] for d in entregas),
                  "divergencias": sum(1 for d in entregas if not d.get("excel_ok", True))},
            "4": {"titulo": "Governança", "dados_pessoais": lgpd},
            "5": {"titulo": "TI", "saudavel": ronda.get("saudavel"), "ultima_ronda": ronda.get("data_hora"),
                  "alertas": [a for i in ronda.get("itens") or [] for a in i["achados"]][:5]},
        },
        "pessoas": sorted([{"id": i, **p} for i, p in por_pessoa.items()], key=lambda p: (p["andar"], -p["achados"])),
        "analises": analises,
        "alertas_analise": alertas_monit[:10],
    }


def _alertas_monitoramento(cfg, inicio: str) -> list[dict]:
    pasta = Path(cfg.logs) / "analises"
    saida = []
    for arq in sorted(pasta.glob("2*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:100] if pasta.exists() else []:
        if datetime.fromtimestamp(arq.stat().st_mtime).date().isoformat() < inicio:
            break
        try:
            d = json.loads(arq.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for a in d.get("alertas") or []:
            if a.get("nivel") == "atenção":
                saida.append({"base": d.get("base"), "arquivo": d.get("arquivo"), "mensagem": a.get("mensagem")})
    return saida
