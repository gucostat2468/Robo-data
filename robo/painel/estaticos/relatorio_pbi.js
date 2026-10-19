// Relatório interativo no padrão do Power BI (engenharia reversa documentada em documentacao/powerbi_engenharia_reversa.md):
//  - cores do tema padrão (dataColors oficiais), cartões no topo, visuais em caixas com título;
//  - FILTRO CRUZADO: clicar numa barra filtra os outros visuais e realça a barra (Ctrl/⌘ soma seleções);
//  - painel de FILTROS à direita (segmentação por categoria e período), "Redefinir para o padrão";
//  - cabeçalho do visual: modo foco, mostrar como tabela, exportar CSV, ordenar;
//  - dica de ferramenta (tooltip) com valor e % do total;
//  - sem filtro, os cartões têm que bater com os números-âncora conferidos pelo Heitor (selo verde).
// Tudo é calculado no navegador a partir das linhas da planilha (amostra.colunas), com as MESMAS regras das medidas DAX.

const PBI_CORES = ["#118DFF", "#12239E", "#E66C37", "#6B007B", "#E044A7", "#744EC2", "#D9B300", "#D64550", "#197278", "#1AAB40"];
Object.assign(E, { pbi: { chave: "", filtros: {}, cruzado: null, foco: null, tabela: null, ordem: {}, abertoFiltros: true } });

function pbiEstado(L) {
  const chave = `${L.nome}|${L.assinatura}`;
  if (E.pbi.chave !== chave) E.pbi = { chave, filtros: {}, cruzado: null, foco: null, tabela: null, ordem: {}, abertoFiltros: E.pbi.abertoFiltros };
  return E.pbi;
}

// --------------------------------------------------------------------------------------------- cálculo (= DAX)
function pbiMedir(med, col, idx) {
  const v = idx.map((i) => col[i]).filter((x) => x !== null && x !== undefined && !Number.isNaN(x));
  if (med.agregacao === "nps") {
    if (!v.length) return null;
    return (v.filter((x) => x >= 9).length - v.filter((x) => x <= 6).length) / v.length * 100;
  }
  if (med.agregacao === "media") return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
  return v.reduce((a, b) => a + b, 0);
}

function pbiLinhas(A, st, ignorar) {  // índices que passam pelos filtros (ignorar = visual que originou o filtro cruzado)
  const idx = [];
  const dt = A.data ? A.colunas[A.data] : null;
  for (let i = 0; i < A.linhas; i++) {
    let ok = true;
    for (const [c, vals] of Object.entries(st.filtros)) {
      if (c === "__de" || c === "__ate") continue;
      if (vals && vals.length && !vals.includes(A.colunas[c][i])) { ok = false; break; }
    }
    if (ok && dt) {
      if (st.filtros.__de && (!dt[i] || dt[i] < st.filtros.__de)) ok = false;
      if (st.filtros.__ate && (!dt[i] || dt[i] > st.filtros.__ate)) ok = false;
    }
    if (ok && st.cruzado && st.cruzado.visual !== ignorar && !st.cruzado.valores.includes(A.colunas[st.cruzado.coluna][i])) ok = false;
    if (ok) idx.push(i);
  }
  return idx;
}

function pbiAgrupar(A, coluna, med, idx) {
  const grupos = new Map();
  for (const i of idx) {
    const k = A.colunas[coluna][i] ?? "(em branco)";
    if (!grupos.has(k)) grupos.set(k, []);
    grupos.get(k).push(i);
  }
  return [...grupos.entries()].map(([k, ids]) => ({ k, v: pbiMedir(med, A.colunas[med.coluna], ids), n: ids.length }));
}

const pbiFmt = (v, med) => v == null ? "—" : med && med.agregacao === "nps" ? String(Math.round(v * 10) / 10).replace(".", ",")
  : Math.abs(v) >= 1000 ? num(Math.round(v)) : String(Math.round(v * 100) / 100).replace(".", ",");

// --------------------------------------------------------------------------------------------- visuais
function pbiCabecalho(id, titulo, st) {
  return `<header class="pbi-cab"><h4>${esc(titulo)}</h4><span class="pbi-icones" role="toolbar" aria-label="Opções do visual">
    <button title="Ordenar" aria-label="Ordenar" data-acao="pbi-ordem" data-v="${id}">↕</button>
    <button title="Mostrar como tabela" aria-label="Mostrar como tabela" data-acao="pbi-tabela" data-v="${id}" aria-pressed="${st.tabela === id}">▦</button>
    <button title="Exportar dados (CSV)" aria-label="Exportar dados" data-acao="pbi-csv" data-v="${id}">⤓</button>
    <button title="${st.foco === id ? "Voltar ao relatório" : "Modo foco"}" aria-label="Modo foco" data-acao="pbi-foco" data-v="${id}">${st.foco === id ? "✕" : "⤢"}</button>
  </span></header>`;
}

function pbiTabelaHtml(linhas, rotulo, med) {
  return `<div class="tabela-envoltorio pbi-tab"><table class="tabela"><thead><tr><th>${esc(rotulo)}</th><th>${esc(med.nome)}</th><th>Linhas</th></tr></thead>
    <tbody>${linhas.map((r) => `<tr><td>${esc(r.k)}</td><td>${esc(pbiFmt(r.v, med))}</td><td>${num(r.n)}</td></tr>`).join("")}</tbody></table></div>`;
}

function pbiBarras(id, A, st, coluna, rotulo, med, cor) {
  let linhas = pbiAgrupar(A, coluna, med, pbiLinhas(A, st, id));
  const ord = st.ordem[id] || "valor";
  linhas.sort((a, b) => ord === "valor" ? (b.v ?? -Infinity) - (a.v ?? -Infinity) : String(a.k).localeCompare(String(b.k), "pt-BR"));
  const total = linhas.reduce((a, r) => a + (r.v || 0), 0);
  const max = Math.max(1e-9, ...linhas.map((r) => Math.abs(r.v || 0)));
  const selecao = st.cruzado && st.cruzado.visual === id ? st.cruzado.valores : null;
  const corpo = st.tabela === id ? pbiTabelaHtml(linhas, rotulo, med) : `<div class="pbi-barras">${linhas.map((r) => {
    const apagada = selecao && !selecao.includes(r.k);
    const dica = `${rotulo}: ${r.k}\n${med.nome}: ${pbiFmt(r.v, med)}${med.agregacao === "soma" && total ? `\n% do total: ${pbPct((r.v || 0) / total)}` : ""}\nLinhas: ${num(r.n)}`;
    return `<button class="pbi-barra-linha${apagada ? " apagada" : ""}" data-acao="pbi-cruzar" data-v="${id}" data-c="${esc(coluna)}" data-k="${esc(r.k)}"
      data-dica="${esc(dica)}" aria-pressed="${!!(selecao && selecao.includes(r.k))}">
      <span class="pbi-rot">${esc(r.k)}</span><span class="pbi-trilho"><span style="width:${Math.max(1, Math.abs(r.v || 0) / max * 100)}%;background:${(r.v || 0) < 0 ? "#D64554" : cor}"></span></span>
      <b>${esc(pbiFmt(r.v, med))}</b></button>`;
  }).join("") || pbVazio("Nenhuma linha com estes filtros.")}</div>`;
  return { linhas, html: `<section class="pbi-visual" data-visual="${id}">${pbiCabecalho(id, `${med.nome} por ${rotulo}`, st)}${corpo}</section>` };
}

function pbiLinha(id, A, st, med) {
  const idx = pbiLinhas(A, st, id);
  const meses = new Map();
  for (const i of idx) {
    const d = A.colunas[A.data][i];
    if (!d) continue;
    const m = d.slice(0, 7);
    if (!meses.has(m)) meses.set(m, []);
    meses.get(m).push(i);
  }
  const linhas = [...meses.keys()].sort().map((m) => ({ k: m, v: pbiMedir(med, A.colunas[med.coluna], meses.get(m)), n: meses.get(m).length }));
  if (st.tabela === id) return { linhas, html: `<section class="pbi-visual">${pbiCabecalho(id, `${med.nome} por mês`, st)}${pbiTabelaHtml(linhas, "Mês", med)}</section>` };
  if (linhas.length < 2) return { linhas, html: `<section class="pbi-visual">${pbiCabecalho(id, `${med.nome} por mês`, st)}${pbVazio("Menos de 2 meses com dados: a linha precisa de pelo menos 2 pontos.")}</section>` };
  const W = 460, H = 220, m = { e: 44, d: 14, t: 16, b: 28 };
  const vs = linhas.map((r) => r.v || 0), mx = Math.max(...vs), mn = Math.min(0, ...vs);
  const x = (i) => m.e + i * (W - m.e - m.d) / (linhas.length - 1), y = (v) => H - m.b - (v - mn) / Math.max(1e-9, mx - mn) * (H - m.t - m.b);
  const pts = linhas.map((r, i) => `${x(i).toFixed(1)},${y(r.v || 0).toFixed(1)}`).join(" ");
  const nomeMes = (k) => ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"][Number(k.slice(5, 7)) - 1] + "/" + k.slice(2, 4);
  const svg = `<svg viewBox="0 0 ${W} ${H}" class="pb-svg" role="img" aria-label="${esc(med.nome)} por mês">
    ${[0, 0.5, 1].map((f) => { const v = mn + (mx - mn) * f; return `<line x1="${m.e}" x2="${W - m.d}" y1="${y(v)}" y2="${y(v)}" class="pb-grade"/><text x="${m.e - 6}" y="${y(v) + 4}" text-anchor="end" class="pb-eixo">${esc(pbiFmt(v, med))}</text>`; }).join("")}
    <polyline points="${pts}" fill="none" stroke="${PBI_CORES[0]}" stroke-width="2.5" stroke-linejoin="round"/>
    ${linhas.map((r, i) => `<circle cx="${x(i)}" cy="${y(r.v || 0)}" r="4" fill="${PBI_CORES[0]}" data-dica="${esc(`Mês: ${nomeMes(r.k)}\n${med.nome}: ${pbiFmt(r.v, med)}\nLinhas: ${num(r.n)}`)}"/>
      <text x="${x(i)}" y="${H - 9}" text-anchor="middle" class="pb-eixo">${nomeMes(r.k)}</text>`).join("")}</svg>`;
  return { linhas, html: `<section class="pbi-visual">${pbiCabecalho(id, `${med.nome} por mês`, st)}${svg}</section>` };
}

function pbiMatriz(id, A, st, coluna, rotulo) {  // matriz com formatação condicional (barras de dados, gradiente do tema)
  const idx = pbiLinhas(A, st, id);
  const meds = A.medidas;
  const grupos = new Map();
  for (const i of idx) { const k = A.colunas[coluna][i] ?? "(em branco)"; if (!grupos.has(k)) grupos.set(k, []); grupos.get(k).push(i); }
  const linhas = [...grupos.entries()].map(([k, ids]) => ({ k, n: ids.length, vs: meds.map((md) => pbiMedir(md, A.colunas[md.coluna], ids)) }));
  linhas.sort((a, b) => (b.vs[0] ?? -Infinity) - (a.vs[0] ?? -Infinity));
  const maxs = meds.map((_, j) => Math.max(1e-9, ...linhas.map((r) => Math.abs(r.vs[j] || 0))));
  const total = meds.map((md) => pbiMedir(md, A.colunas[md.coluna], idx));
  const html = `<section class="pbi-visual largo">${pbiCabecalho(id, `Matriz: ${rotulo} × medidas`, st)}
    <div class="tabela-envoltorio pbi-tab"><table class="tabela"><thead><tr><th>${esc(rotulo)}</th>${meds.map((md) => `<th>${esc(md.nome)}</th>`).join("")}<th>Linhas</th></tr></thead>
    <tbody>${linhas.map((r) => `<tr><td>${esc(r.k)}</td>${r.vs.map((v, j) => `<td class="pbi-celula"><span class="pbi-databar" style="width:${Math.abs(v || 0) / maxs[j] * 100}%"></span><span>${esc(pbiFmt(v, meds[j]))}</span></td>`).join("")}<td>${num(r.n)}</td></tr>`).join("")}
    <tr class="pbi-total"><td>Total</td>${total.map((v, j) => `<td>${esc(pbiFmt(v, meds[j]))}</td>`).join("")}<td>${num(idx.length)}</td></tr></tbody></table></div></section>`;
  return { linhas: linhas.map((r) => ({ k: r.k, v: r.vs[0], n: r.n })), html };
}

function pbiFiltros(A, st) {
  const dims = A.dimensoes;
  const blocos = dims.map((d) => {
    const vals = [...new Set(A.colunas[d.coluna].filter((v) => v != null))].sort((a, b) => String(a).localeCompare(String(b), "pt-BR"));
    const sel = st.filtros[d.coluna] || [];
    return `<details class="pbi-filtro" open><summary>${esc(d.rotulo)} <small>${sel.length ? `${sel.length} selecionado(s)` : "é (Tudo)"}</small></summary>
      ${vals.slice(0, 40).map((v) => `<label><input type="checkbox" data-pbi-filtro="${esc(d.coluna)}" value="${esc(v)}" ${sel.includes(v) ? "checked" : ""}> ${esc(v)}</label>`).join("")}</details>`;
  }).join("");
  const data = A.data ? `<details class="pbi-filtro" open><summary>Período <small>${st.filtros.__de || st.filtros.__ate ? "filtrado" : "é (Tudo)"}</small></summary>
    <label>De <input type="date" data-pbi-data="__de" value="${esc(st.filtros.__de || "")}"></label>
    <label>Até <input type="date" data-pbi-data="__ate" value="${esc(st.filtros.__ate || "")}"></label></details>` : "";
  return `<aside class="pbi-painel-filtros${st.abertoFiltros ? "" : " fechado"}" aria-label="Filtros">
    <button class="pbi-filtros-titulo" data-acao="pbi-filtros-abrir" aria-expanded="${st.abertoFiltros}">⏷ Filtros</button>
    <div class="pbi-filtros-corpo"><p class="muted">Filtros nesta página</p>${blocos}${data}</div></aside>`;
}

// --------------------------------------------------------------------------------------------- página do relatório
function pbiRelatorio(L) {
  const A = L.amostra;
  if (!A || !A.linhas || !A.medidas.length) return pbVazio("Esta planilha não tem métrica numérica para montar o relatório.");
  const st = pbiEstado(L);
  const med = A.medidas[0];
  const idx = pbiLinhas(A, st, null);
  const semFiltro = !st.cruzado && !Object.entries(st.filtros).some(([, v]) => v && v.length);
  const cartoes = A.medidas.map((md, j) => {
    const v = pbiMedir(md, A.colunas[md.coluna], idx);
    return `<div class="pbi-cartao"><span>${esc(md.nome)}</span><strong style="color:${PBI_CORES[j % 10] === "#D9B300" ? "#252423" : "#252423"}">${esc(pbiFmt(v, md))}</strong></div>`;
  }).join("") + `<div class="pbi-cartao"><span>Linhas</span><strong>${num(idx.length)}</strong></div>`;
  // conferência: sem filtro, o navegador tem que chegar nos MESMOS números que o Heitor conferiu
  let selo = "";
  if (semFiltro && A.linhas === A.total) {
    const difs = A.medidas.filter((md) => {
      const anc = L.ancoras[md.nome], v = pbiMedir(md, A.colunas[md.coluna], idx);
      return anc != null && v != null && Math.abs(anc - v) > Math.max(1e-3, 1e-9 * Math.abs(anc));
    });
    selo = difs.length ? `<span class="etiqueta perigo">⚠ ${difs.length} número(s) diferente(s) das âncoras</span>`
      : `<span class="etiqueta sucesso">✓ sem filtro, os cartões batem com as âncoras conferidas pelo Heitor</span>`;
  } else if (A.linhas < A.total) {
    selo = `<span class="etiqueta alerta">relatório com as primeiras ${num(A.linhas)} de ${num(A.total)} linhas</span>`;
  }
  const visuais = [];
  const dims = A.dimensoes;
  const rotuloDe = (c) => (dims.find((d) => d.coluna === c) || {}).rotulo || c;
  if (dims[0]) visuais.push({ id: "v1", ...pbiBarras("v1", A, st, dims[0].coluna, dims[0].rotulo, med, PBI_CORES[0]) });
  if (dims[1]) visuais.push({ id: "v2", ...pbiBarras("v2", A, st, dims[1].coluna, dims[1].rotulo, med, PBI_CORES[1]) });
  if (A.data) visuais.push({ id: "v3", ...pbiLinha("v3", A, st, med) });
  if (dims[0]) visuais.push({ id: "v4", ...pbiMatriz("v4", A, st, dims[0].coluna, dims[0].rotulo) });
  E._pbiVisuais = Object.fromEntries(visuais.map((v) => [v.id, v.linhas]));
  const focado = st.foco && visuais.find((v) => v.id === st.foco);
  const filtrosAtivos = [
    ...Object.entries(st.filtros).filter(([c, v]) => v && v.length && !c.startsWith("__")).map(([c, v]) => `${rotuloDe(c)}: ${v.join(", ")}`),
    ...(st.filtros.__de || st.filtros.__ate ? [`período: ${st.filtros.__de || "…"} a ${st.filtros.__ate || "…"}`] : []),
    ...(st.cruzado ? [`clique em ${rotuloDe(st.cruzado.coluna)}: ${st.cruzado.valores.join(", ")}`] : [])];
  const barra = `<div class="pbi-barra">${selo}<span class="muted">${filtrosAtivos.length ? "Filtros ativos: " + esc(filtrosAtivos.join(" · ")) : "Clique numa barra para filtrar a página (Ctrl/⌘ soma seleções)"}</span>
    <button class="btn" data-acao="pbi-redefinir" ${filtrosAtivos.length || st.foco ? "" : "disabled"}>↺ Redefinir para o padrão</button></div>`;
  const tela = focado ? `<div class="pbi-foco">${focado.html}</div>`
    : `<div class="pbi-cartoes">${cartoes}</div><div class="pbi-grade">${visuais.map((v) => v.html).join("")}</div>`;
  return `<div class="pbi-relatorio">${barra}<div class="pbi-corpo"><div class="pbi-tela">${tela}</div>${pbiFiltros(A, st)}</div></div>`;
}

// --------------------------------------------------------------------------------------------- ações
function pbiCsv(id) {
  const linhas = (E._pbiVisuais || {})[id] || [];
  const csv = "﻿categoria;valor;linhas\n" + linhas.map((r) => `"${String(r.k).replaceAll('"', '""')}";${r.v == null ? "" : String(r.v).replace(".", ",")};${r.n}`).join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  a.download = `visual_${id}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

Object.assign(ACOES, {
  "pbi-cruzar": (el, ev) => {
    const st = E.pbi, k = el.dataset.k, multi = ev && (ev.ctrlKey || ev.metaKey);
    if (st.cruzado && st.cruzado.visual === el.dataset.v) {
      const vals = st.cruzado.valores.includes(k) ? (multi ? st.cruzado.valores.filter((x) => x !== k) : (st.cruzado.valores.length > 1 ? [k] : []))
        : (multi ? [...st.cruzado.valores, k] : [k]);
      st.cruzado = vals.length ? { ...st.cruzado, valores: vals } : null;
    } else st.cruzado = { visual: el.dataset.v, coluna: el.dataset.c, valores: [k] };
    desenhar();
  },
  "pbi-foco": (el) => { E.pbi.foco = E.pbi.foco === el.dataset.v ? null : el.dataset.v; desenhar(); },
  "pbi-tabela": (el) => { E.pbi.tabela = E.pbi.tabela === el.dataset.v ? null : el.dataset.v; desenhar(); },
  "pbi-ordem": (el) => { E.pbi.ordem[el.dataset.v] = E.pbi.ordem[el.dataset.v] === "nome" ? "valor" : "nome"; desenhar(); },
  "pbi-csv": (el) => pbiCsv(el.dataset.v),
  "pbi-redefinir": () => { Object.assign(E.pbi, { filtros: {}, cruzado: null, foco: null, tabela: null, ordem: {} }); desenhar(); },
  "pbi-filtros-abrir": () => { E.pbi.abertoFiltros = !E.pbi.abertoFiltros; desenhar(); },
});

document.addEventListener("change", (e) => {
  const t = e.target;
  if (t.dataset && t.dataset.pbiFiltro) {
    const c = t.dataset.pbiFiltro, atual = new Set(E.pbi.filtros[c] || []);
    if (t.checked) atual.add(t.value); else atual.delete(t.value);
    E.pbi.filtros[c] = [...atual];
    desenhar();
  } else if (t.dataset && t.dataset.pbiData) {
    E.pbi.filtros[t.dataset.pbiData] = t.value || "";
    desenhar();
  }
});

// dica de ferramenta (tooltip) como a do Power BI: segue o mouse sobre barras e pontos
(() => {
  let dica = null;
  document.addEventListener("mousemove", (e) => {
    const alvo = e.target.closest && e.target.closest("[data-dica]");
    if (!alvo) { if (dica) dica.hidden = true; return; }
    if (!dica) { dica = document.createElement("div"); dica.className = "pbi-dica"; document.body.appendChild(dica); }
    dica.textContent = alvo.dataset.dica;
    dica.hidden = false;
    dica.style.left = `${Math.min(e.clientX + 14, innerWidth - dica.offsetWidth - 8)}px`;
    dica.style.top = `${Math.min(e.clientY + 14, innerHeight - dica.offsetHeight - 8)}px`;
  });
})();
