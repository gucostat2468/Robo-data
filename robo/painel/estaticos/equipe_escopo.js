// Quem faz o quê: o escopo de cada funcionário e o ÚLTIMO trabalho que ele deixou registrado no banco.
// Tudo vem de /api/quem-faz-o-que (robo/atividade_equipe.py). Quem não tem registro aparece assim — nada é inventado.

Object.assign(E, { quem: null, quemAndar: "todos", quemBusca: "", quemSituacao: "" });

async function carregarQuem() {
  try { E.quem = await api("/api/quem-faz-o-que"); } catch (e) { avisar(e.message, "erro"); }
}

const QUEM_SITUACAO = {
  trabalhando: ["sucesso", "Trabalhando agora"], ativo_hoje: ["info", "Ativo hoje"],
  plantao: ["", "Só plantão (rotina)"], ocioso: ["alerta", "Ocioso (24 h+)"], sem_registro: ["perigo", "Sem registro"],
};

function quemHa(iso) {
  if (!iso) return "";
  const min = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (min < 1) return "agora";
  if (min < 60) return `há ${min} min`;
  const h = Math.round(min / 60);
  return h < 48 ? `há ${h} h` : `há ${Math.round(h / 24)} dias`;
}

function quemCartao(p) {
  const [cor, rotulo] = QUEM_SITUACAO[p.situacao] || ["", p.situacao];
  const u = p.ultimo;
  const escopo = (p.escopo || []).map((x) => `<li>${esc(x)}</li>`).join("") || `<li class="muted">Escopo não descrito na ficha.</li>`;
  const rotinas = (p.rotinas || []).length ? `<div class="qf-sub">Rotinas sob responsabilidade</div><ul>${p.rotinas.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "";
  const fontes = Object.entries(p.fontes_24h || {}).map(([f, n]) => `${esc(f.replaceAll("_", " "))}: ${n}`).join(" · ");
  return `<article class="qf-cartao" style="--qf-cor:${esc(p.cor || "var(--borda-forte)")}">
    <header class="qf-topo"><div class="qf-quem"><b>${esc(p.nome)}</b><small class="muted">${esc(p.cargo || "")}</small></div>
      <span class="etiqueta ${cor}">${esc(rotulo)}</span></header>
    <div class="qf-meta"><span>${p.andar}º andar</span><span>${esc(p.nivel || "")}</span>${p.gestor ? `<span>gestor: ${esc(p.gestor)}</span>` : ""}</div>
    ${p.agora ? `<div class="qf-agora">Agora: ${esc(p.agora.etapa)} no job ${p.agora.job} (${esc(p.agora.tipo)}${p.agora.arquivo ? `, ${esc(p.agora.arquivo)}` : ""}), desde ${esc(quemHa(p.agora.inicio))}</div>` : ""}
    <div class="qf-ultimo">${u ? `<div class="qf-sub">Último trabalho real · ${esc(quemHa(u.quando))}</div><p>${esc(u.o_que)}</p>
      <small class="muted">${esc(dataT(u.quando))} · ${esc(u.natureza || "")} · fonte: ${esc(u.fonte)}${p.real_24h ? ` · ${p.real_24h} trabalho(s) real(is) em 24 h` : ""}</small>`
      : `<div class="qf-sub">Último trabalho real</div><p class="muted">Nenhum trabalho real registrado ainda.</p>`}
      ${p.ultimo_plantao ? `<small class="muted qf-plantao">Plantão (não conta como trabalho): ${esc(p.ultimo_plantao.o_que)} · ${esc(quemHa(p.ultimo_plantao.quando))}</small>` : ""}</div>
    <details class="qf-escopo"><summary>Escopo${(p.ferramentas || []).length ? ` · ${p.ferramentas.length} ferramenta(s)` : ""}</summary>
      <ul>${escopo}</ul>${rotinas}
      ${(p.ferramentas || []).length ? `<div class="qf-sub">Ferramentas do contrato</div><p class="mono qf-ferr">${esc(p.ferramentas.join(", "))}</p>` : ""}
      ${fontes ? `<div class="qf-sub">Registros nas últimas 24 h</div><p class="qf-ferr">${fontes}</p>` : ""}</details>
  </article>`;
}

function renderQuem() {
  const q = E.quem;
  const acoes = `<button class="btn" data-acao="quem-recarregar">${icone("recarregar")}Atualizar</button>`;
  const desc = "O escopo de cada funcionário e o último trabalho REAL que ele deixou registrado. Rotina automática, ronda de TI e " +
    "aviso no canal contam só como plantão, nunca como trabalho. Quem está parado aparece em destaque para a liderança agir.";
  if (!q) return cabecalho("Quem faz o quê", desc, acoes) + `<div class="carregando">Lendo os registros de cada pessoa…</div>`;
  const andares = q.andares.map((a) => `<button class="btn pequeno ${String(E.quemAndar) === String(a.andar) ? "primario" : ""}"
    data-acao="quem-andar" data-andar="${a.andar}">${a.andar}º · ${a.pessoas}</button>`).join("");
  const resumo = `<div class="qf-resumo">${q.andares.map((a) => `<div class="qf-andar">
      <b>${a.andar}º · ${esc(a.nome)}</b>
      <span><span class="etiqueta sucesso">${a.trabalhando} agora</span> <span class="etiqueta info">${a.ativo_hoje} hoje</span>
      ${a.plantao ? `<span class="etiqueta">${a.plantao} só plantão</span>` : ""}
      ${a.ocioso ? `<span class="etiqueta alerta">${a.ocioso} ocioso(s)</span>` : ""}${a.sem_registro ? ` <span class="etiqueta perigo">${a.sem_registro} sem registro</span>` : ""}</span></div>`).join("")}</div>`;
  const j = q.jobs || {};
  const minPl = j.ultima_planilha_min;
  const topo = `<div class="qf-topo-real"><div><b>${q.trabalho_real_agora} de ${q.total_pessoas}</b><span>com trabalho real agora</span></div>
    <div class="${minPl == null || minPl > 60 ? "qf-vermelho" : ""}"><b>${minPl == null ? "nunca" : `há ${num(minPl)} min`}</b><span>última planilha processada${j.ultima_planilha ? ` (${esc(j.ultima_planilha.origem)})` : ""}</span></div>
    <div class="${j.ultima_planilha_real_min == null || j.ultima_planilha_real_min > 60 ? "qf-vermelho" : ""}"><b>${j.ultima_planilha_real_min == null ? "nunca" : `há ${num(j.ultima_planilha_real_min)} min`}</b><span>última planilha REAL</span></div></div>`;
  const parados = q.parados.length ? `<div class="qf-parados"><b>Sem trabalho real nas últimas 24 horas (${q.parados.length}):</b> ${q.parados.map((p) =>
    `${esc(p.nome)} (${p.andar}º, ${esc(QUEM_SITUACAO[p.situacao]?.[1] || p.situacao)}${p.gestor ? `, gestor ${esc(p.gestor)}` : ""})`).join("; ")}</div>`
    : `<div class="qf-ok">Todo mundo deixou trabalho real registrado nas últimas 24 horas.</div>`;
  const busca = (E.quemBusca || "").toLowerCase();
  const lista = q.pessoas.filter((p) => (E.quemAndar === "todos" || String(p.andar) === String(E.quemAndar)) &&
    (!E.quemSituacao || p.situacao === E.quemSituacao) &&
    (!busca || `${p.nome} ${p.cargo} ${(p.escopo || []).join(" ")} ${p.ultimo?.o_que || ""}`.toLowerCase().includes(busca)));
  const filtros = `<div class="qf-filtros"><div class="chips-colunas"><button class="btn pequeno ${E.quemAndar === "todos" ? "primario" : ""}"
      data-acao="quem-andar" data-andar="todos">Todos · ${q.pessoas.length}</button>${andares}</div>
    <div class="qf-filtros-linha"><label class="campo-busca">${icone("busca")}<input type="text" id="quem-busca" placeholder="Nome, cargo ou tarefa…" value="${esc(E.quemBusca || "")}"></label>
    <select id="quem-situacao" aria-label="Situação"><option value="">Todas as situações</option>${Object.entries(QUEM_SITUACAO).map(([k, [, r]]) =>
      `<option value="${k}" ${E.quemSituacao === k ? "selected" : ""}>${esc(r)}</option>`).join("")}</select></div></div>`;
  return cabecalho("Quem faz o quê", desc, acoes) + topo + resumo + parados + filtros +
    `<p class="muted qf-regra">${esc(q.regra)} · ${lista.length} pessoa(s) na lista · lido ${esc(quemHa(q.gerado_em))}</p>` +
    `<div class="qf-grade">${lista.map(quemCartao).join("") || `<p class="muted">Ninguém com esse filtro.</p>`}</div>`;
}

Object.assign(PAGINAS, { quem: { titulo: "Quem faz o quê", render: renderQuem, carregar: carregarQuem } });
Object.assign(ACOES, {
  "quem-recarregar": (el) => comCarregando(el, async () => { await carregarQuem(); desenhar(); }),
  "quem-andar": (el) => { E.quemAndar = el.dataset.andar; desenhar(); },
});
document.addEventListener("input", (e) => {
  if (e.target.id !== "quem-busca") return;
  E.quemBusca = e.target.value;
  clearTimeout(E._buscaQuem);
  E._buscaQuem = setTimeout(() => { desenhar(); const c = $("#quem-busca"); if (c) { c.focus(); c.setSelectionRange(c.value.length, c.value.length); } }, 250);
});
document.addEventListener("change", (e) => {
  if (e.target.id !== "quem-situacao") return;
  E.quemSituacao = e.target.value;
  desenhar();
});
