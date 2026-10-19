"""Telas de referência do painel Power BI (1920x1080) com os NÚMEROS REAIS do modelo estrela.

    python powerbi/gerar_telas.py

Lê powerbi/dados/*.csv (gerados por exportar_estrela.py — a mesma fonte do Power BI) e grava em powerbi/telas/:
  NN_pagina.png         a tela pronta (como o painel deve ficar)
  NN_pagina_fundo.png   só a moldura (cards, rótulos, slots de filtro) → Formatar página → Tela de fundo no Power BI

Design (skill powerbi-ui-ux-pro): arquétipo 3 — Dark Premium (monitoramento contínuo); canvas #18181B, cards #27272A,
acento violeta; paleta das 5 cores dos andares validada (luminosidade, croma, daltonismo, contraste) no modo escuro.
"""

from __future__ import annotations

import csv
import html
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

PASTA = Path(__file__).resolve().parent
DADOS = PASTA / "dados"
TELAS = PASTA / "telas"

# ------------------------------------------------------------------ tokens de design
CANVAS, LATERAL, CARD, BORDA, GRADE = "#18181B", "#1F1F23", "#27272A", "#34343A", "#3A3A40"
TEXTO, ROTULO, APAGADO = "#FAFAFA", "#A1A1AA", "#8B8B94"
ACENTO, ACENTO_SUAVE = "#9D5CF5", "#2E2440"
POS, ATEN, NEG = "#4CC272", "#E6C558", "#E06666"
ANDARES = ["#8B5CF6", "#0D9488", "#D97706", "#E11D48", "#3B82F6"]  # 1º..5º andar (ordem fixa, validada)
FONTE = "'Segoe UI', Inter, 'DejaVu Sans', sans-serif"
W, H, M, G = 1920, 1080, 24, 16
X0, LARG = 256, 1920 - 256 - 24  # conteúdo à direita da barra lateral

PAGINAS = [("01_visao_executiva", "Visão Executiva", "◉"), ("02_treino_evolucao", "Treino & Evolução", "▲"),
           ("03_pessoas_andares", "Pessoas & Andares", "●"), ("04_conversas_mentorias", "Conversas & Mentorias", "✉"),
           ("05_operacao_rotinas", "Operação & Rotinas", "⚙")]


def ler(t):
    with open(DADOS / f"{t}.csv", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def num(x):
    return float(x.replace(",", ".")) if x not in ("", None) else None


def br(v, casas=0):
    s = f"{v:,.{casas}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def esc(s):
    return html.escape(str(s))


# ------------------------------------------------------------------ números (as mesmas regras das medidas DAX)
def calcular() -> dict:
    treino, inter, ment, rot = ler("fato_treino"), ler("fato_interacoes"), ler("fato_mentorias"), ler("fato_rotinas")
    evol, nivat, func, comp, andar = (ler("fato_evolucao_nivel"), ler("fato_nivel_atual"), ler("dim_funcionario"),
                                      ler("dim_competencia"), ler("dim_andar"))
    fn = {f["funcionario_id"]: f for f in func}
    cn = {c["competencia_id"]: c["competencia"] for c in comp}
    an = {a["andar"]: a["andar_nome"] for a in andar}
    dt = lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M:%S")  # noqa: E731
    pct = lambda xs: 100 * sum(int(x["acertou"]) for x in xs) / len(xs) if xs else None  # noqa: E731
    fim = max(dt(t["data_hora"]) for t in treino)
    jan = timedelta(hours=8)
    rec = [t for t in treino if dt(t["data_hora"]) > fim - jan]
    ant = [t for t in treino if fim - 2 * jan < dt(t["data_hora"]) <= fim - jan]
    r = {"inicio": min(dt(t["data_hora"]) for t in treino), "fim": fim, "treino": treino, "fn": fn, "an": an}
    r.update(tent=len(treino), acerto=pct(treino), pessoas=len({t["funcionario_id"] for t in treino}),
             quadro=sum(1 for f in func if f["no_quadro"] == "1"), nivel_medio=sum(int(n["nivel"]) for n in nivat) / len(nivat),
             tent_rec=len(rec), tent_ant=len(ant), acerto_rec=pct(rec), acerto_ant=pct(ant),
             subidas=sum(1 for e in evol if e["tipo_evento"] == "subiu"),
             descidas=sum(1 for e in evol if e["tipo_evento"] == "desceu"),
             subidas_rec=sum(1 for e in evol if e["tipo_evento"] == "subiu" and dt(e["data_hora"]) > fim - jan),
             conversas=len(inter), mentorias=len(ment), rotinas_exec=len(rot), rotinas_erro=sum(int(x["com_erro"]) for x in rot),
             segundos=sum(num(t["segundos"]) or 0 for t in treino) / len(treino))
    by = lambda xs, k: _agrupar(xs, k)  # noqa: E731
    r["por_comp"] = sorted([(cn.get(k, k), len(v), pct(v)) for k, v in by(treino, "competencia_id").items()], key=lambda x: (-x[2], -x[1]))
    r["por_nivel"] = [(int(k), len(v), pct(v)) for k, v in sorted(by(treino, "nivel").items(), key=lambda x: int(x[0]))]
    niv_andar = defaultdict(list)
    for n in nivat:
        a = fn.get(n["funcionario_id"], {}).get("andar")
        if a:
            niv_andar[a].append(int(n["nivel"]))
    # andar = o andar ATUAL da pessoa (dim_andar → dim_funcionario → fatos, como no modelo); o andar 0 ("fora do quadro")
    # fica fora dos gráficos por andar e é citado no rodapé
    t_andar = defaultdict(list)
    for t in treino:
        t_andar[fn[t["funcionario_id"]]["andar"]].append(t)
    r["fora_quadro_tent"] = len(t_andar.get("0", []))
    r["por_andar"] = [(int(a), an.get(a, a), len(v), pct(v), len({t["funcionario_id"] for t in v}),
                       sum(1 for f in func if f["andar"] == a and f["no_quadro"] == "1"),
                       sum(niv_andar[a]) / len(niv_andar[a]) if niv_andar[a] else 0)
                      for a, v in sorted(t_andar.items(), key=lambda x: int(x[0])) if a != "0"]
    horas = defaultdict(list)
    for t in treino:
        horas[dt(t["data_hora"]).replace(minute=0, second=0)].append(t)
    r["por_hora"] = [(h, len(v), pct(v)) for h, v in sorted(horas.items())]
    r["erros_tipo"] = Counter(t["tipo_erro"] for t in treino if t["acertou"] == "0").most_common()
    nivp, tp = defaultdict(list), defaultdict(list)
    for n in nivat:
        nivp[n["funcionario_id"]].append(int(n["nivel"]))
    for t in treino:
        tp[t["funcionario_id"]].append(t)
    r["ranking"] = sorted(((fn[p]["nome"], fn[p]["cargo"], int(fn[p]["andar"] or 0), sum(v) / len(v), len(tp[p]), pct(tp[p]))
                           for p, v in nivp.items() if p in fn and tp[p]), key=lambda x: (-x[3], -x[4], x[0]))[:10]
    ordem = ["Estagiário", "Júnior", "Pleno", "Sênior", "Especialista", "Coordenador(a)", "Gerente", "Head", "Diretor(a)"]
    cargos = Counter(f["nivel_cargo"] for f in func if f["no_quadro"] == "1")
    r["cargos"] = [(c, cargos[c]) for c in ordem if cargos.get(c)]
    r["conv_tipo"] = Counter(i["tipo"] for i in inter).most_common()
    r["ment_sit"] = Counter(m["situacao"] for m in ment).most_common()
    r["mentores"] = [(fn.get(k, {}).get("nome", k), v) for k, v in Counter(m["mentor_id"] for m in ment).most_common(5)]
    r["conv_recentes"] = [(dt(i["data_hora"]), fn.get(i["de_id"], {}).get("nome", i["de_id"]),
                           fn.get(i["para_id"], {}).get("nome", i["para_id"] or "—"), i["tipo"], i["texto"]) for i in inter][::-1][:7]
    r["rotinas"] = sorted([(k, len(v), sum(int(x["com_erro"]) for x in v), sum(num(x["segundos"]) or 0 for x in v) / len(v))
                           for k, v in by(rot, "rotina").items()], key=lambda x: -x[1])
    r["fechadas"] = sum(1 for m in ment if m["situacao"] != "aberta")
    r["ajudou"] = sum(1 for m in ment if m["situacao"] == "ajudou")
    return r


def _agrupar(xs, k):
    d = defaultdict(list)
    for x in xs:
        d[x[k]].append(x)
    return d


# ------------------------------------------------------------------ peças visuais (SVG/HTML)
def card(x, y, w, h, titulo="", sub="", corpo="", fundo=False):
    t = f'<div class="ct">{esc(titulo)}</div>' if titulo else ""
    s = f'<div class="cs">{esc(sub)}</div>' if sub else ""
    return (f'<div class="card" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px">{t}{s}'
            f'{"" if fundo else corpo}</div>')


ICONES = {
    "alvo": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/>',
    "check": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.6 2.6L16 9.5"/>',
    "pessoas": '<circle cx="9" cy="9" r="3.2"/><path d="M3.5 19c.8-3.2 3-5 5.5-5s4.7 1.8 5.5 5"/><circle cx="17" cy="8" r="2.4"/><path d="M15.5 13.4c2.3.2 4 1.8 4.7 4.6"/>',
    "camadas": '<path d="M12 4l8 4-8 4-8-4z"/><path d="M4 12l8 4 8-4"/><path d="M4 16l8 4 8-4"/>',
    "seta": '<path d="M12 19V6"/><path d="M6.5 11.5L12 6l5.5 5.5"/>',
    "chat": '<path d="M5 6h14v9H10l-4 3.5V15H5z"/>',
    "mao": '<path d="M7 12l3 3 7-7"/><path d="M4 12a8 8 0 1016 0"/>',
    "engrenagem": '<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/>',
    "alerta": '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17v.5"/>',
    "relogio": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
}


def kpi(x, y, w, icone, rotulo, valor, delta="", cor_delta=ROTULO, fundo=False):
    ic = (f'<div class="ki"><svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="{ACENTO}" '
          f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{ICONES[icone]}</svg></div>')
    corpo = "" if fundo else (f'<div class="kv">{esc(valor)}</div><div class="kd" style="color:{cor_delta}">{esc(delta)}</div>')
    return (f'<div class="card kpi" style="left:{x}px;top:{y}px;width:{w}px;height:104px">{ic}'
            f'<div class="kl">{esc(rotulo)}</div>{corpo}</div>')


def delta_pp(atual, anterior, rotulo="vs 8 h anteriores"):
    d = atual - anterior
    return (f"{'▲ +' if d >= 0 else '▼ '}{br(d, 1)} p.p. {rotulo}", POS if d >= 0 else NEG)


def delta_pct(atual, anterior, rotulo="vs 8 h anteriores"):
    if not anterior:
        return ("sem base anterior", ROTULO)
    d = 100 * (atual - anterior) / anterior
    return (f"{'▲ +' if d >= 0 else '▼ '}{br(d, 1)}% {rotulo}", POS if d >= 0 else NEG)


def hbar(itens, w, h, cores=None, fmt=lambda v: br(v, 1), maximo=None, rot_w=240, val_w=90, limite=None):
    """Barras horizontais: rótulo à esquerda, valor à direita, ponta arredondada 4px, 2px de respiro entre barras."""
    n = len(itens)
    maximo = maximo or max(v for _, v, *_ in itens) or 1
    passo = min(44, (h - 8) / max(n, 1))
    alt = max(10, passo - 12)
    area = w - rot_w - val_w - 16
    s = [f'<svg width="{w}" height="{h}">']
    if limite is not None:
        xl = rot_w + area * limite / maximo
        s.append(f'<line x1="{xl}" y1="0" x2="{xl}" y2="{n * passo}" stroke="{ATEN}" stroke-width="1.5" stroke-dasharray="4 4"/>')
    for i, (rot, v, *extra) in enumerate(itens):
        y = i * passo + (passo - alt) / 2
        cor = (cores[i] if isinstance(cores, list) else cores) or ACENTO
        largura = max(4, area * v / maximo)
        s.append(f'<text x="{rot_w - 12}" y="{y + alt / 2 + 5}" text-anchor="end" class="ax">{esc(rot)}</text>')
        s.append(f'<rect x="{rot_w}" y="{y}" width="{area}" height="{alt}" rx="4" fill="{GRADE}" opacity=".35"/>')
        s.append(f'<rect x="{rot_w}" y="{y}" width="{largura}" height="{alt}" rx="4" fill="{cor}"/>')
        txt = extra[0] if extra else fmt(v)
        s.append(f'<text x="{w - val_w + 8}" y="{y + alt / 2 + 5}" class="vl">{esc(txt)}</text>')
    return "".join(s) + "</svg>"


def vbar(itens, w, h, cor=ACENTO, fmt=lambda v: br(v, 0), cores=None, maximo=None, base_rot=34):
    n = len(itens)
    maximo = maximo or max(v for _, v in itens) or 1
    area_h = h - base_rot - 30
    passo = (w - 20) / n
    larg = min(72, passo * 0.56)
    s = [f'<svg width="{w}" height="{h}">']
    for k in range(1, 4):
        y = 30 + area_h - area_h * k / 3
        s.append(f'<line x1="10" x2="{w - 10}" y1="{y}" y2="{y}" stroke="{GRADE}" stroke-width="1" stroke-dasharray="2 4"/>')
    s.append(f'<line x1="10" x2="{w - 10}" y1="{30 + area_h}" y2="{30 + area_h}" stroke="{BORDA}"/>')
    for i, (rot, v) in enumerate(itens):
        x = 10 + i * passo + (passo - larg) / 2
        hh = max(3, area_h * v / maximo)
        y = 30 + area_h - hh
        c = cores[i] if cores else cor
        s.append(f'<path d="M{x},{30 + area_h} V{y + 4} q0,-4 4,-4 H{x + larg - 4} q4,0 4,4 V{30 + area_h} Z" fill="{c}"/>')
        s.append(f'<text x="{x + larg / 2}" y="{y - 8}" text-anchor="middle" class="vl">{esc(fmt(v))}</text>')
        s.append(f'<text x="{x + larg / 2}" y="{h - 10}" text-anchor="middle" class="ax">{esc(rot)}</text>')
    return "".join(s) + "</svg>"


def linha(pontos, w, h, cor=ACENTO, fmt=lambda v: br(v, 0), y_min=None, y_max=None, rotulos_x=None, area=True, ref=None):
    """Linha 2px, área suave, marcador 8px no último ponto, grade recessiva, eixo Y à esquerda."""
    vals = [v for _, v in pontos]
    y_min = min(vals) if y_min is None else y_min
    y_max = max(vals) if y_max is None else y_max
    y_max = y_max if y_max > y_min else y_min + 1
    esq, dir_, top, base = 56, 16, 18, 36
    pw, ph = w - esq - dir_, h - top - base
    px = lambda i: esq + pw * i / max(len(pontos) - 1, 1)  # noqa: E731
    py = lambda v: top + ph - ph * (v - y_min) / (y_max - y_min)  # noqa: E731
    s = [f'<svg width="{w}" height="{h}">']
    for k in range(5):
        v = y_min + (y_max - y_min) * k / 4
        y = py(v)
        s.append(f'<line x1="{esq}" x2="{w - dir_}" y1="{y}" y2="{y}" stroke="{GRADE}" stroke-dasharray="2 4"/>')
        s.append(f'<text x="{esq - 10}" y="{y + 5}" text-anchor="end" class="ax">{esc(fmt(v))}</text>')
    if ref is not None:
        s.append(f'<line x1="{esq}" x2="{w - dir_}" y1="{py(ref[0])}" y2="{py(ref[0])}" stroke="{ATEN}" stroke-width="1.5" stroke-dasharray="5 5"/>'
                 f'<text x="{w - dir_}" y="{py(ref[0]) - 8}" text-anchor="end" class="ax" fill="{ATEN}">{esc(ref[1])}</text>')
    d = " ".join(f"{'M' if i == 0 else 'L'}{px(i):.1f},{py(v):.1f}" for i, (_, v) in enumerate(pontos))
    if area:
        s.append(f'<path d="{d} L{px(len(pontos) - 1):.1f},{top + ph} L{px(0):.1f},{top + ph} Z" fill="{cor}" opacity=".14"/>')
    s.append(f'<path d="{d}" fill="none" stroke="{cor}" stroke-width="2.4" stroke-linejoin="round"/>')
    ul = len(pontos) - 1
    s.append(f'<circle cx="{px(ul)}" cy="{py(vals[-1])}" r="5" fill="{cor}" stroke="{CARD}" stroke-width="2"/>')
    s.append(f'<text x="{px(ul) - 10}" y="{max(14, py(vals[-1]) - 12)}" text-anchor="end" class="vl">{esc(fmt(vals[-1]))}</text>')
    passo = max(1, len(pontos) // 8)
    for i, (rot, _) in enumerate(pontos):
        if i % passo == 0 or i == ul:
            ancora = "end" if i == ul else ("start" if i == 0 else "middle")
            s.append(f'<text x="{px(i)}" y="{h - 10}" text-anchor="{ancora}" class="ax">{esc(rotulos_x(rot) if rotulos_x else rot)}</text>')
    return "".join(s) + "</svg>"


def tabela(cabec, linhas, larguras, alinhar=None, destaque_col=None):
    alinhar = alinhar or ["left"] * len(cabec)
    th = "".join(f'<th style="width:{l}px;text-align:{a}">{esc(c)}</th>' for c, l, a in zip(cabec, larguras, alinhar))
    corpo = []
    for ln in linhas:
        tds = []
        for j, (v, a) in enumerate(zip(ln, alinhar)):
            estilo = f"text-align:{a}"
            if isinstance(v, tuple):
                v, cor = v
                estilo += f";color:{cor};font-weight:600"
            tds.append(f'<td style="{estilo}">{esc(v)}</td>')
        corpo.append("<tr>" + "".join(tds) + "</tr>")
    return f'<table><thead><tr>{th}</tr></thead><tbody>{"".join(corpo)}</tbody></table>'


def chips(itens):
    return '<div class="chips">' + "".join(f'<div class="chip"><span>✓</span>{esc(t)}</div>' for t in itens) + "</div>"


# ------------------------------------------------------------------ moldura comum
def moldura(pagina_idx, titulo, pergunta, r, conteudo):
    nav = "".join(f'<div class="nav{" ativo" if i == pagina_idx else ""}"><span>{ic}</span>{esc(nome)}</div>'
                  for i, (_, nome, ic) in enumerate(PAGINAS))
    filtros = "".join(f'<div class="fl"><div class="flr">{esc(f)}</div><div class="flc"></div></div>'
                      for f in ("PERÍODO", "ANDAR", "COMPETÊNCIA", "NÍVEL"))
    atual = r["fim"].strftime("%d/%m/%Y %H:%M")
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:{W}px;height:{H}px;background:{CANVAS};font-family:{FONTE};color:{TEXTO};position:relative;overflow:hidden}}
.lat{{position:absolute;left:0;top:0;width:232px;height:{H}px;background:{LATERAL};border-right:1px solid {BORDA};padding:24px 16px}}
.marca{{display:flex;gap:10px;align-items:center;margin-bottom:28px}}
.logo{{width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg,#8324F3,#461F84);display:grid;place-items:center;font-weight:700}}
.marca b{{display:block;font-size:15px}} .marca i{{display:block;font-style:normal;font-size:11px;color:{ROTULO}}}
.nav{{display:flex;gap:10px;align-items:center;height:44px;padding:0 12px;border-radius:10px;font-size:14px;color:{ROTULO};margin-bottom:4px}}
.nav span{{width:18px;text-align:center}} .nav.ativo{{background:{ACENTO_SUAVE};color:{TEXTO};font-weight:600;box-shadow:inset 3px 0 0 {ACENTO}}}
.sec{{font-size:10px;letter-spacing:.12em;color:{APAGADO};margin:26px 4px 10px}}
.fl{{margin-bottom:12px}} .flr{{font-size:9px;letter-spacing:.12em;color:{ROTULO};margin:0 2px 5px}}
.flc{{height:44px;border:1px solid {BORDA};border-radius:10px;background:{CARD}}}
.cab{{position:absolute;left:{X0}px;top:{M}px;width:{LARG}px;height:56px;display:flex;align-items:center;justify-content:space-between}}
.cab h1{{font-size:26px;font-weight:600;letter-spacing:-.01em}} .cab p{{font-size:13px;color:{ROTULO};margin-top:2px}}
.atu{{font-size:12px;color:{ROTULO};border:1px solid {BORDA};border-radius:999px;padding:7px 14px;background:{CARD}}}
.atu b{{color:{POS}}}
.card{{position:absolute;background:{CARD};border:1px solid {BORDA};border-radius:14px;padding:16px 18px;overflow:hidden}}
.ct{{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:{ROTULO};font-weight:600}}
.cs{{font-size:12px;color:{APAGADO};margin-top:3px}}
.kpi{{padding:18px 18px 14px 82px}} .ki{{position:absolute;left:18px;top:24px;width:48px;height:48px;border-radius:12px;background:{ACENTO_SUAVE};display:grid;place-items:center}}
.kl{{font-size:12px;color:{ROTULO};letter-spacing:.02em}} .kv{{font-size:32px;font-weight:600;line-height:1.15;margin-top:2px;letter-spacing:-.01em}}
.kd{{font-size:12px;margin-top:2px;font-weight:500}}
svg text{{font-family:{FONTE}}} .ax{{fill:{ROTULO};font-size:12px}} .vl{{fill:{TEXTO};font-size:13px;font-weight:600}}
.corpo{{position:absolute;left:18px;right:18px;bottom:14px}}
.corpo:has(table){{top:64px;bottom:auto}}
table{{width:100%;border-collapse:collapse;font-size:13px}} th{{color:{ROTULO};font-weight:600;font-size:11px;letter-spacing:.06em;text-transform:uppercase;padding:8px 6px;border-bottom:1px solid {BORDA}}}
td{{padding:9px 6px;border-bottom:1px solid #303036;color:{TEXTO};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:0}}
.chips{{display:flex;gap:12px}} .chip{{flex:1;font-size:13px;color:{TEXTO};background:{CARD};border:1px solid {BORDA};border-radius:12px;padding:12px 14px;line-height:1.35}}
.chip span{{color:{POS};font-weight:700;margin-right:8px}}
.leg{{display:flex;gap:16px;font-size:12px;color:{ROTULO};margin-top:8px}} .leg i{{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}}
.rod{{position:absolute;left:{X0}px;bottom:8px;font-size:10px;color:{APAGADO}}}
</style></head><body>
<div class="lat"><div class="marca"><div class="logo">R</div><div><b>Robô de Planilhas</b><i>Painel da empresa</i></div></div>
{nav}<div class="sec">FILTROS</div>{filtros}</div>
<div class="cab"><div><h1>{esc(titulo)}</h1><p>{esc(pergunta)}</p></div><div class="atu"><b>●</b> Atualizado em {atual}</div></div>
{conteudo}
<div class="rod">Fonte: PostgreSQL (Neon) · schema bi · {br(r['tent'])} tentativas de treino de {br(r['pessoas'])} funcionários entre {r['inicio']:%d/%m %H:%M} e {r['fim']:%d/%m %H:%M} · dados de treino sintéticos, correção e registros reais</div>
</body></html>"""


def _kpis(itens, fundo):
    n = len(itens)
    w = (LARG - G * (n - 1)) / n
    return "".join(kpi(X0 + i * (w + G), 104, w, *it, fundo=fundo) for i, it in enumerate(itens))


Y1 = 104 + 104 + 24  # início da área de gráficos


# ------------------------------------------------------------------ páginas
def pagina_executiva(r, fundo):
    d1, c1 = delta_pct(r["tent_rec"], r["tent_ant"])
    d2, c2 = delta_pp(r["acerto_rec"], r["acerto_ant"])
    k = _kpis([("alvo", "Tentativas de treino", br(r["tent"]), d1, c1),
               ("check", "Taxa de acerto", f"{br(r['acerto'], 1)}%", d2, c2),
               ("pessoas", "Funcionários ativos", f"{r['pessoas']} de {r['quadro'] + (r['pessoas'] - r['quadro'])}", "todos treinaram no período", POS),
               ("camadas", "Nível médio (1–5)", br(r["nivel_medio"], 2), f"▲ {r['subidas']} subidas · {r['descidas']} quedas", POS),
               ("chat", "Conversas registradas", br(r["conversas"]), f"{r['mentorias']} delas são mentorias", ROTULO)], fundo)
    w1 = LARG * 0.62
    w2 = LARG - w1 - G
    h1 = 430
    pontos = [(h, n) for h, n, _ in r["por_hora"]]
    c = card(X0, Y1, w1, h1, "Tentativas por hora", "Ritmo de trabalho da empresa (turnos na nuvem a cada 2 h)",
             f'<div class="corpo">{linha(pontos, w1 - 36, h1 - 80, rotulos_x=lambda h: h.strftime("%d/%m %Hh"))}</div>', fundo)
    andares = [(f"{a}º {nome.split(',')[0][:30]}", pc, f"{br(pc, 1)}%") for a, nome, n, pc, *_ in r["por_andar"]]
    c += card(X0 + w1 + G, Y1, w2, h1, "Taxa de acerto por andar",
              f"Andar atual da pessoa · tracejado = meta de 95% · {r['fora_quadro_tent']} tentativas de quem saiu do quadro ficam fora",
              f'<div class="corpo">{hbar(andares, w2 - 36, h1 - 90, cores=ANDARES, maximo=100, limite=95, rot_w=260)}</div>', fundo)
    y2 = Y1 + h1 + G
    h2 = 1080 - y2 - 36 - 92
    niveis = [(f"Nível {n}", pc) for n, _, pc in r["por_nivel"]]
    cores_niv = [POS if pc >= 95 else (ATEN if pc >= 85 else NEG) for _, pc in niveis]
    c += card(X0, y2, w1 / 2 - G / 2, h2, "Acerto por nível de dificuldade", "O nível 4 é onde a empresa ainda erra: é aí que o treino ensina",
              f'<div class="corpo">{vbar(niveis, w1 / 2 - G / 2 - 36, h2 - 84, cores=cores_niv, maximo=100, fmt=lambda v: br(v, 1) + "%")}</div>', fundo)
    erros = [(t.replace("_", " "), n) for t, n in r["erros_tipo"]] or [("sem erros", 0)]
    c += card(X0 + w1 / 2 + G / 2, y2, w1 / 2 - G / 2, h2, "Erros por tipo", f"{sum(n for _, n in r['erros_tipo'])} erros no período — cada um virou lição",
              f'<div class="corpo">{hbar(erros, w1 / 2 - G / 2 - 36, h2 - 84, cores=NEG, fmt=lambda v: br(v, 0), rot_w=170, val_w=50)}</div>', fundo)
    top = r["ranking"][:5]
    c += card(X0 + w1 + G, y2, w2, h2, "Destaques: maior nível médio", "Nível médio nas competências do contrato",
              f'<div class="corpo">{tabela(["Pessoa", "Cargo", "Nível", "Acerto"], [(p, cg[:26], br(nv, 1), f"{br(pc, 0)}%") for p, cg, _a, nv, _n, pc in top], [130, 260, 70, 80], ["left", "left", "right", "right"])}</div>', fundo)
    pior = min(r["por_nivel"], key=lambda x: x[2])
    ins = chips([f"{br(r['acerto'], 1)}% de acerto em {br(r['tent'])} tentativas — todos os {r['pessoas']} funcionários treinaram",
                 f"No nível {pior[0]} o acerto cai para {br(pior[2], 1)}%: a dificuldade discrimina",
                 f"{r['subidas']} subidas de nível e nenhuma queda; nível médio {br(r['nivel_medio'], 2)} de 5"])
    c += "" if fundo else f'<div style="position:absolute;left:{X0}px;top:{1080 - 36 - 76}px;width:{LARG}px">{ins}</div>'
    return k + c


def pagina_treino(r, fundo):
    d2, c2 = delta_pp(r["acerto_rec"], r["acerto_ant"])
    k = _kpis([("check", "Taxa de acerto", f"{br(r['acerto'], 1)}%", d2, c2),
               ("seta", "Subidas de nível", br(r["subidas"]), f"{r['subidas_rec']} nas últimas 8 h", POS),
               ("camadas", "Nível médio (1–5)", br(r["nivel_medio"], 2), "média das competências de cada pessoa", ROTULO),
               ("relogio", "Tempo médio por tentativa", f"{br(r['segundos'], 2)} s", "ferramenta real executada", ROTULO)], fundo)
    w1 = LARG * 0.5 - G / 2
    h = (1080 - Y1 - 36 - G) / 2
    comps = [(n[:30], pc, f"{br(pc, 1)}% · {t}") for n, t, pc in r["por_comp"]]
    c = card(X0, Y1, w1, h * 2 + G, "Acerto por competência", "Rótulo: taxa de acerto · tentativas",
             f'<div class="corpo">{hbar(comps, w1 - 36, h * 2 + G - 90, cores=ACENTO, maximo=100, limite=95, rot_w=250, val_w=110)}</div>', fundo)
    niv = [(f"Nível {n}", t) for n, t, _ in r["por_nivel"]]
    c += card(X0 + w1 + G, Y1, w1, h, "Tentativas por nível", "Onde está a empresa hoje na escada de dificuldade",
              f'<div class="corpo">{vbar(niv, w1 - 36, h - 84)}</div>', fundo)
    pts = [(hh, pc) for hh, _, pc in r["por_hora"]]
    c += card(X0 + w1 + G, Y1 + h + G, w1, h, "Taxa de acerto por hora", "Linha tracejada = meta de 95%",
              f'<div class="corpo">{linha(pts, w1 - 36, h - 80, cor=POS, fmt=lambda v: br(v, 0) + "%", y_min=80, y_max=100, ref=(95, "meta 95%"), rotulos_x=lambda x: x.strftime("%Hh"))}</div>', fundo)
    return k + c


def pagina_pessoas(r, fundo):
    fora = r["pessoas"] - sum(p for *_, p, _q, _n in [(x[0], x[1], x[2], x[3], x[4], x[5], x[6]) for x in r["por_andar"]])
    k = _kpis([("pessoas", "Funcionários no quadro", br(r["quadro"]), "5 andares, do estagiário ao diretor", ROTULO),
               ("check", "Treinaram no período", br(r["pessoas"]), "100% do quadro", POS),
               ("camadas", "Nível médio da empresa", br(r["nivel_medio"], 2), "escala de dificuldade 1 a 5", ROTULO),
               ("seta", "Subidas de nível", br(r["subidas"]), "promoções do RH exigem 30 tentativas/30 dias", ROTULO)], fundo)
    w1 = LARG * 0.58
    w2 = LARG - w1 - G
    h1 = 360
    linhas = [((f"{a}º", ANDARES[a - 1]), nome, br(q), br(p), br(n), (f"{br(pc, 1)}%", POS if pc >= 95 else ATEN), br(nv, 2))
              for a, nome, n, pc, p, q, nv in r["por_andar"]]
    c = card(X0, Y1, w1, h1, "Andares", "Quadro, quem treinou, volume, acerto e nível médio",
             f'<div class="corpo">{tabela(["Andar", "Área", "Quadro", "Ativos", "Tentativas", "Acerto", "Nível"], linhas, [60, 380, 80, 80, 100, 90, 70], ["left", "left", "right", "right", "right", "right", "right"])}</div>', fundo)
    niv = [(f"{a}º", nv) for a, _n, _t, _p, _pe, _q, nv in r["por_andar"]]
    c += card(X0 + w1 + G, Y1, w2, h1, "Nível médio por andar", "Cor fixa por andar em todo o painel",
              f'<div class="corpo">{vbar(niv, w2 - 36, h1 - 84, cores=ANDARES, maximo=5, fmt=lambda v: br(v, 2))}</div>', fundo)
    y2 = Y1 + h1 + G
    h2 = 1080 - y2 - 36
    rk = [(i + 1, p, cg[:30], f"{a}º", br(nv, 2), br(n), f"{br(pc, 0)}%") for i, (p, cg, a, nv, n, pc) in enumerate(r["ranking"][:9])]
    c += card(X0, y2, w1, h2, "Ranking — maior nível médio", "Desempate: mais tentativas",
              f'<div class="corpo">{tabela(["#", "Pessoa", "Cargo", "Andar", "Nível", "Tentativas", "Acerto"], rk, [40, 140, 320, 70, 70, 100, 80], ["left", "left", "left", "left", "right", "right", "right"])}</div>', fundo)
    cargos = [(c_, n) for c_, n in r["cargos"]]
    c += card(X0 + w1 + G, y2, w2, h2, "Quadro por nível de cargo", "Estrutura da empresa (do código do robô)",
              f'<div class="corpo">{hbar(cargos, w2 - 36, h2 - 84, cores=ACENTO, fmt=lambda v: br(v, 0), rot_w=150, val_w=50)}</div>', fundo)
    return k + c


ROT_TIPO = {"pedido": "Pedido de ajuda", "mentoria": "Mentoria", "troca": "Troca de experiência", "retorno": "Retorno",
            "resposta": "Resposta", "sem_mentor": "Sem mentor", "agradecimento": "Agradecimento"}
ROT_SIT = {"aberta": "Aberta (aguarda próxima tentativa)", "ajudou": "Ajudou", "nao_ajudou": "Não ajudou"}


def pagina_conversas(r, fundo):
    taxa = f"{br(100 * r['ajudou'] / r['fechadas'], 0)}%" if r["fechadas"] else "—"
    k = _kpis([("chat", "Conversas registradas", br(r["conversas"]), "todas nascem de um fato registrado", ROTULO),
               ("mao", "Mentorias", br(r["mentorias"]), f"{r['fechadas']} fechadas · {r['mentorias'] - r['fechadas']} abertas", ROTULO),
               ("check", "Mentorias que ajudaram", taxa, f"amostra pequena ({r['fechadas']} fechadas): leia com cautela", ATEN),
               ("pessoas", "Mentores diferentes", br(len(r["mentores"])), "quem acertou ensina quem errou", ROTULO)], fundo)
    w1 = LARG * 0.34
    h1 = 330
    tipos = [(ROT_TIPO.get(t, t), n) for t, n in r["conv_tipo"]]
    c = card(X0, Y1, w1, h1, "Conversas por tipo", "", f'<div class="corpo">{hbar(tipos, w1 - 36, h1 - 60, cores=ACENTO, fmt=lambda v: br(v, 0), rot_w=190, val_w=40)}</div>', fundo)
    sit = [(ROT_SIT.get(s, s), n) for s, n in r["ment_sit"]]
    cores_sit = [ATEN if "Aberta" in s else (POS if s == "Ajudou" else NEG) for s, _ in sit]
    c += card(X0 + w1 + G, Y1, w1, h1, "Mentorias por situação", "Fecha na próxima tentativa do aprendiz",
              f'<div class="corpo">{hbar(sit, w1 - 36, h1 - 80, cores=cores_sit, fmt=lambda v: br(v, 0), rot_w=230, val_w=40)}</div>', fundo)
    w3 = LARG - 2 * w1 - 2 * G
    c += card(X0 + 2 * (w1 + G), Y1, w3, h1, "Quem mais ensinou", "Mentorias por mentor",
              f'<div class="corpo">{hbar(r["mentores"], w3 - 36, h1 - 80, cores=ACENTO, fmt=lambda v: br(v, 0), rot_w=120, val_w=40)}</div>', fundo)
    y2 = Y1 + h1 + G
    h2 = 1080 - y2 - 36
    linhas = [(t.strftime("%d/%m %H:%M"), de, para, ROT_TIPO.get(tp, tp), tx) for t, de, para, tp, tx in r["conv_recentes"]]
    c += card(X0, y2, LARG, h2, "Conversas mais recentes", "Texto integral fica em bi.fato_interacoes (tabela com quebra de linha no Power BI)",
              f'<div class="corpo">{tabela(["Quando", "De", "Para", "Tipo", "Mensagem"], linhas, [120, 130, 130, 170, 1050], ["left"] * 5)}</div>', fundo)
    return k + c


def pagina_operacao(r, fundo):
    suc = 100 * (r["rotinas_exec"] - r["rotinas_erro"]) / r["rotinas_exec"]
    k = _kpis([("engrenagem", "Execuções de rotinas", br(r["rotinas_exec"]), "treino, registro, backup, memória, TI…", ROTULO),
               ("check", "Taxa de sucesso", f"{br(suc, 1)}%", "meta 99%", POS if suc >= 99 else ATEN),
               ("alerta", "Execuções com erro", br(r["rotinas_erro"]), "cada erro vira handover com dono", NEG if r["rotinas_erro"] else POS),
               ("relogio", "Rotinas diferentes", br(len(r["rotinas"])), "todas com registro de início, fim e status", ROTULO)], fundo)
    w1 = LARG * 0.5 - G / 2
    h1 = 1080 - Y1 - 36
    ex = [(n, t, f"{t}") for n, t, _e, _s in r["rotinas"]]
    c = card(X0, Y1, w1, h1, "Execuções por rotina", "Volume de trabalho automático",
             f'<div class="corpo">{hbar(ex, w1 - 36, h1 - 84, cores=ACENTO, fmt=lambda v: br(v, 0), rot_w=150, val_w=50)}</div>', fundo)
    linhas = [(n, br(t), (br(e), NEG if e else POS), f"{br(s, 2)} s", (f"{br(100 * (t - e) / t, 1)}%", POS if e == 0 else ATEN))
              for n, t, e, s in r["rotinas"]]
    c += card(X0 + w1 + G, Y1, w1, h1, "Saúde de cada rotina", "Erros em vermelho; tempo médio por execução",
              f'<div class="corpo">{tabela(["Rotina", "Execuções", "Erros", "Tempo médio", "Sucesso"], linhas, [200, 110, 80, 130, 110], ["left", "right", "right", "right", "right"])}</div>', fundo)
    return k + c


FUNCOES = [pagina_executiva, pagina_treino, pagina_pessoas, pagina_conversas, pagina_operacao]
PERGUNTAS = ["Como a empresa está agora, em um olhar?", "Os funcionários estão aprendendo — e onde ainda erram?",
             "Quem são, onde estão e como cada andar evolui?", "Quem ajuda quem, e isso funciona?",
             "As rotinas automáticas estão saudáveis?"]


def gerar() -> list[Path]:
    from playwright.sync_api import sync_playwright
    r = calcular()
    TELAS.mkdir(parents=True, exist_ok=True)
    saidas = []
    with sync_playwright() as p:
        nav = p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        pg = nav.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        for i, ((arq, nome, _ic), f, perg) in enumerate(zip(PAGINAS, FUNCOES, PERGUNTAS)):
            for fundo in (False, True):
                html_ = moldura(i, nome, perg, r, f(r, fundo))
                if fundo:  # o fundo leva só a moldura: a pílula "atualizado" fica vazia (o texto vem da medida DAX), sem rodapé
                    html_ = html_.replace(f'Atualizado em {r["fim"].strftime("%d/%m/%Y %H:%M")}', '<span style="visibility:hidden">Atualizado em 00/00/0000 00:00</span>').replace(
                        html_[html_.find('<div class="rod">'):html_.find("</body>")], "")
                pg.set_content(html_, wait_until="load")
                destino = TELAS / f"{arq}{'_fundo' if fundo else ''}.png"
                pg.screenshot(path=str(destino), full_page=False)
                saidas.append(destino)
        nav.close()
    return saidas


if __name__ == "__main__":
    for s in gerar():
        print(s)
    sys.exit(0)
