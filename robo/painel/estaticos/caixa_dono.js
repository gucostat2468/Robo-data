// Caixa do dono: toda ideia e sugestão da equipe (sempre com o dado que a motivou) e tudo o que só você decide.
// Tudo vem de /api/caixa-dono. A decisão é sua e fica registrada para sempre (caixa_dono_eventos).

Object.assign(E, { caixa: null, caixaFiltro: "nova" });

async function carregarCaixa(silencioso = false) {
  try { E.caixa = await api("/api/caixa-dono"); atualizarSeloCaixa(); } catch (e) { if (!silencioso) avisar(e.message, "erro"); }
}

function atualizarSeloCaixa() {
  const b = $("#badge-caixa");
  const n = E.caixa?.resumo?.novas || 0;
  if (b) { b.hidden = !n; b.textContent = n > 99 ? "99+" : String(n); }
}

const CAIXA_TIPOS = { ideia: "Ideia", sugestao: "Sugestão da equipe", regra: "Regra nova", rh: "RH", aprovacao: "Aprovação" };

function cartaoCaixa(i) {
  const nova = i.situacao === "nova";
  const selo = nova ? `<span class="etiqueta info">nova</span>` : i.situacao === "aprovada" ? `<span class="etiqueta sucesso">aprovada</span>`
    : `<span class="etiqueta perigo">recusada</span>`;
  const quem = i.sugerido_por || {};
  const acoes = nova ? `<div class="caixa-acoes">
      <input type="text" id="nota-${esc(i.id)}" placeholder="Nota para a equipe (opcional)" maxlength="500">
      <button class="btn primario" data-acao="caixa-decidir" data-id="${esc(i.id)}" data-aprovar="1">${icone("ok")}Aprovar</button>
      <button class="btn" data-acao="caixa-decidir" data-id="${esc(i.id)}" data-aprovar="0">Recusar</button></div>`
    : `<small class="muted">Decidido em ${esc(dataT(i.decidido_em))}${i.nota_dono ? ` · sua nota: ${esc(i.nota_dono)}` : ""}</small>`;
  return `<article class="caixa-item${nova ? " nova" : ""}">
    <header><span class="etiqueta">${esc(CAIXA_TIPOS[i.tipo] || i.tipo)}</span>${selo}
      <span class="muted">impacto ${"●".repeat(i.impacto || 0)}${"○".repeat(Math.max(0, 5 - (i.impacto || 0)))}</span>
      <small class="muted" style="margin-left:auto">${esc(dataT(i.data_hora))}</small></header>
    <h3>${esc(i.titulo)}</h3>
    <p class="caixa-quem">De <b>${esc(quem.nome || "")}</b>${quem.cargo ? ` · ${esc(quem.cargo)}` : ""}${i.origem && i.origem.id !== quem.id ? ` · para <b>${esc(i.origem.nome)}</b>` : ""}</p>
    <dl><dt>Por quê (o dado)</dt><dd>${esc(i.motivo || "—")}</dd><dt>Primeiro passo</dt><dd>${esc(i.primeiro_passo || "—")}</dd></dl>
    ${acoes}</article>`;
}

function renderCaixa() {
  const c = E.caixa;
  const desc = "Toda ideia e sugestão da equipe chega aqui, sempre com o número que a motivou, junto com o que só você decide " +
    "(promoções, regras novas, aprovações). Ideia aprovada vira trabalho de quem sugeriu; recusada não volta por 30 dias, " +
    "a menos que o número mude muito.";
  const acoes = `<button class="btn" data-acao="caixa-recarregar">${icone("recarregar")}Atualizar</button>`;
  if (!c) return cabecalho("Caixa do dono", desc, acoes) + `<div class="carregando">Abrindo a caixa…</div>`;
  const filtros = [["nova", "Novas"], ["todas", "Todas"], ["aprovada", "Aprovadas"], ["recusada", "Recusadas"]];
  const lista = c.itens.filter((i) => E.caixaFiltro === "todas" || i.situacao === E.caixaFiltro);
  const r = c.resumo;
  return cabecalho("Caixa do dono", desc, acoes) +
    `<div class="pb-kpis"><div class="pb-kpi"><span class="pb-kpi-rotulo">Esperando você</span><strong class="pb-kpi-valor">${num(r.novas)}</strong></div>
      <div class="pb-kpi"><span class="pb-kpi-rotulo">Ideias e sugestões novas</span><strong class="pb-kpi-valor">${num(r.ideias_novas)}</strong></div>
      <div class="pb-kpi"><span class="pb-kpi-rotulo">Pendências que só você decide</span><strong class="pb-kpi-valor">${num(r.pendencias_novas)}</strong></div></div>
    <div class="pb-abas" role="tablist">${filtros.map(([k, t]) => `<button role="tab" class="pb-aba${E.caixaFiltro === k ? " ativa" : ""}"
      aria-selected="${E.caixaFiltro === k}" data-acao="caixa-filtro" data-filtro="${k}">${t}</button>`).join("")}</div>
    <div class="caixa-lista">${lista.map(cartaoCaixa).join("") || `<div class="cartao vazio"><p>Nada aqui agora.</p></div>`}</div>`;
}

Object.assign(PAGINAS, { caixa: { titulo: "Caixa do dono", render: renderCaixa, carregar: carregarCaixa } });
Object.assign(ACOES, {
  "caixa-recarregar": (el) => comCarregando(el, async () => { await carregarCaixa(); desenhar(); }),
  "caixa-filtro": (el) => { E.caixaFiltro = el.dataset.filtro; desenhar(); },
  "caixa-decidir": (el) => comCarregando(el, async () => {
    const id = el.dataset.id, aprovar = el.dataset.aprovar === "1";
    const nota = document.getElementById(`nota-${id}`)?.value || "";
    try {
      await api("/api/caixa-dono/decidir", { corpo: { id, aprovar, nota } });
      avisar(aprovar ? "Aprovado — a equipe foi avisada no canal." : "Recusado e registrado.", "sucesso");
    } catch (e) { avisar(e.message, "erro"); }
    await carregarCaixa(); desenhar();
  }),
});
// o selo do menu acompanha a caixa mesmo com outra página aberta
// (só depois do login: antes disso a tela de senha está aberta e a API responderia 401)
setTimeout(function primeira() {
  if (document.querySelector("input[type=password]")) { setTimeout(primeira, 1500); return; }
  carregarCaixa(true);
}, 1200);
setInterval(() => { if (!document.hidden) carregarCaixa(true).then(() => { if (E.pagina === "caixa") desenhar(); }); }, 60000);
