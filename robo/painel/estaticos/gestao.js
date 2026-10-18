// Gestão do projeto: saúde de cada página, andar, função e módulo, e a evolução real de cada funcionário.
// Tudo vem de /api/gestao (código + registros). Nada aqui é estimado.

Object.assign(E, { gestao: null, gestaoAba: "paginas", gestaoAndar: "" });
const TENDENCIA = { evoluindo: ["Evoluindo", "sucesso"], estavel: ["Estável", ""], piorando: ["Piorando", "perigo"],
  dados_insuficientes: ["Dados insuficientes", "alerta"] };
const etiquetaTendencia = (t) => { const [x, c] = TENDENCIA[t] || [t, ""]; return `<span class="etiqueta ${c}">${esc(x)}</span>`; };
const FAROL_ANDAR = { verde: "🟢", amarelo: "🟡", vermelho: "🔴", cinza: "⚪" };

async function carregarGestao() {
  try { E.gestao = await api("/api/gestao"); } catch (e) { avisar(e.message, "erro"); }
}

function miniSerie(taxas) {  // barrinhas por semana (cinza = sem dado)
  return `<span style="display:inline-flex;gap:2px;align-items:flex-end;height:22px" title="${esc(taxas.map((t) => t == null ? "—" : `${t}%`).join(" · "))}">${taxas.map((t) =>
    `<span style="width:6px;height:${t == null ? 3 : Math.max(3, Math.round(t / 100 * 22))}px;background:${t == null ? "var(--borda)" : t >= 90 ? "var(--sucesso)" : t >= 70 ? "var(--alerta)" : "var(--perigo)"};border-radius:2px"></span>`).join("")}</span>`;
}

function abaPaginas(g) {
  return `<div class="tabela-envoltorio"><table class="tabela"><thead><tr><th>Página</th><th>Para que serve</th><th>Andar</th><th>Rotas conferidas agora</th><th>Situação</th></tr></thead><tbody>
    ${g.paginas.map((p) => `<tr><td><a href="#${esc(p.id)}"><b>${esc(p.titulo)}</b></a></td><td>${esc(p.para_que)}</td><td>${p.andar}º</td>
      <td>${p.checagens.length ? p.checagens.map((c) => `<div class="mono" style="font-size:12px">${c.ok ? "✅" : "❌"} ${esc(c.rota)}${c.ms != null ? ` · ${c.ms} ms` : ""}${c.erro ? ` <span class="muted">(${esc(c.erro.slice(0, 120))})</span>` : ""}</div>`).join("") : `<span class="muted">sem carga inicial</span>`}</td>
      <td>${p.ok ? `<span class="etiqueta sucesso">ok</span>` : `<span class="etiqueta perigo">com falha</span>`}</td></tr>`).join("")}</tbody></table></div>`;
}

function abaAndares(g) {
  return `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px">${g.andares.map((a) => `<div class="cartao"><div class="cartao-corpo">
      <div style="display:flex;justify-content:space-between"><strong>${a.andar}º · ${esc(a.nome)}</strong><span title="scorecard do diretor">${FAROL_ANDAR[a.farol]}</span></div>
      <p class="muted" style="margin:4px 0 8px">${a.pessoas} pessoa(s) · diretor ${esc(E.nomes?.[a.diretor] || a.diretor || "—")} · head ${esc(E.nomes?.[a.head] || a.head || "—")}</p>
      <ul class="lista-ficha">
        <li>Acerto em 30 dias: <b>${a.taxa_30d == null ? "sem dado" : `${a.taxa_30d}%`}</b> <span class="muted">(${a.acertos_30d} acertos, ${a.erros_30d} erros)</span></li>
        <li>Handovers abertos: <b>${a.handovers_abertos}</b>${a.handovers_recorrentes ? ` · <span class="etiqueta perigo">${a.handovers_recorrentes} recorrente(s)</span>` : ""}</li>
        <li>Lições comprovadas: <b>${a.pct_licoes_aplicadas == null ? "—" : `${a.pct_licoes_aplicadas}%`}</b> <span class="muted">de ${a.licoes_atribuidas}</span></li>
        <li>Evolução: ${Object.entries(a.tendencias).map(([t, n]) => `${etiquetaTendencia(t)} ${n}`).join(" ")}</li>
        ${a.insuficientes.length ? `<li>Abaixo da exigência: <b>${esc(a.insuficientes.join(", "))}</b></li>` : ""}</ul>
      <button class="btn pequeno" data-acao="gestao-andar" data-andar="${a.andar}">Ver pessoas do andar</button></div></div>`).join("")}</div>`;
}

function abaEvolucao(g) {
  const lista = g.evolucao.filter((e) => !E.gestaoAndar || String(e.andar) === E.gestaoAndar)
    .sort((a, b) => (a.tendencia === "piorando" ? -1 : 0) - (b.tendencia === "piorando" ? -1 : 0) || b.eventos - a.eventos);
  return `<div class="caixa-texto" style="margin-bottom:8px"><select id="gestao-andar"><option value="">Todos os andares</option>${[1, 2, 3, 4, 5].map((a) => `<option value="${a}" ${E.gestaoAndar === String(a) ? "selected" : ""}>${a}º andar</option>`).join("")}</select></div>
    <p class="muted" style="font-size:12px">Taxa de acerto por semana (8 semanas, da mais antiga à atual). Tendência só aparece com pelo menos 5 eventos nas 2 últimas semanas e 5 nas anteriores; a diferença precisa ser de 5 pontos ou mais.</p>
    <div class="tabela-envoltorio"><table class="tabela"><thead><tr><th>Funcionário</th><th>Andar</th><th>8 semanas</th><th>Eventos</th><th>Variação</th><th>Tendência</th><th></th></tr></thead><tbody>
    ${lista.map((e) => `<tr><td><b>${esc(e.nome)}</b><br><small class="muted">${esc(e.papel)}</small></td><td>${e.andar}º</td><td>${miniSerie(e.taxas_semana)}</td>
      <td class="direita">${e.eventos}</td><td class="direita">${e.delta_pp == null ? "—" : `${e.delta_pp > 0 ? "+" : ""}${e.delta_pp} pp`}</td><td>${etiquetaTendencia(e.tendencia)}</td>
      <td><button class="btn pequeno" data-acao="caderno" data-id="${esc(e.id)}">Caderno</button></td></tr>`).join("")}</tbody></table></div>`;
}

function abaFuncoes(g) {
  return `<div class="tabela-envoltorio"><table class="tabela"><thead><tr><th>Função</th><th>Risco</th><th>Responsável</th><th>Usos 30d</th><th>% ok</th><th>Exceções</th><th>Tempo médio</th><th>Testes</th></tr></thead><tbody>
    ${g.funcoes.map((f) => `<tr><td><b>${esc(f.nome)}</b> <span class="mono muted">${esc(f.id)}</span><br><small class="muted">${esc(f.descricao)}</small></td>
      <td><span class="etiqueta ${f.risco === "alto" ? "perigo" : f.risco === "medio" ? "alerta" : ""}">${esc(f.risco)}</span>${f.altera_dados ? ` <span class="etiqueta alerta">altera dados</span>` : ""}</td>
      <td>${esc(E.nomes?.[f.responsavel] || f.responsavel || "—")}<br><small class="muted">${f.autorizados} autorizado(s)</small></td>
      <td class="direita">${f.usos}</td><td class="direita">${f.pct_ok == null ? "—" : `${f.pct_ok}%`}</td>
      <td class="direita">${f.excecoes ? `<span class="etiqueta perigo">${f.excecoes}</span>` : "0"}</td>
      <td class="direita">${f.segundos_medio == null ? "—" : `${f.segundos_medio}s`}</td>
      <td>${f.citada_em_testes ? `<span class="etiqueta sucesso">${f.citada_em_testes}</span>` : `<span class="etiqueta perigo">sem teste</span>`}</td></tr>`).join("")}</tbody></table></div>`;
}

function abaModulos(g) {
  return `<div class="tabela-envoltorio"><table class="tabela"><thead><tr><th>Módulo</th><th>Para que serve</th><th>Linhas</th><th>Funções</th><th>Testes que o cobrem</th><th>Erros abertos</th></tr></thead><tbody>
    ${g.modulos.map((m) => `<tr><td class="mono">${esc(m.modulo)}</td><td>${esc(m.para_que)}</td><td class="direita">${m.linhas}</td><td class="direita">${m.funcoes}</td>
      <td>${m.testes.length ? `<small>${esc(m.testes.join(", "))}</small>` : `<span class="etiqueta perigo">nenhum</span>`}</td>
      <td class="direita">${m.erros_abertos ? `<span class="etiqueta perigo">${m.erros_abertos}</span>` : "0"}</td></tr>`).join("")}</tbody></table></div>`;
}

function renderGestao() {
  const g = E.gestao;
  const acoes = `<button class="btn" data-acao="recarregar-gestao">${icone("recarregar")}Conferir de novo</button>`;
  if (!g) return cabecalho("Gestão do projeto", "", acoes) + `<div class="carregando">Conferindo páginas, andares, funções e módulos…</div>`;
  const r = g.resumo;
  const falhas = g.paginas.filter((p) => !p.ok).length;
  const cartoes = [
    ["Páginas", `${g.paginas.length - falhas}/${g.paginas.length} ok`, falhas ? `${falhas} com falha agora` : "todas as rotas responderam"],
    ["Funcionários", r.funcionarios, Object.entries(r.tendencias).map(([t, n]) => `${(TENDENCIA[t] || [t])[0]}: ${n}`).join(" · ")],
    ["Funções", g.funcoes.length, `${r.funcoes_sem_teste.length} sem teste · ${r.funcoes_sem_uso_30d.length} sem uso em 30 dias`],
    ["Módulos", g.modulos.length, `${r.modulos_sem_teste.length} sem teste · ${r.modulos_com_erro_aberto.length} com erro aberto`],
    ["Aprendizado real", `${g.aprendizado.regras_ativas} regra(s)`, `${(g.aprendizado.por_estado || {}).comprovada || 0} comprovada(s) · ${(g.aprendizado.por_estado || {}).pendente || 0} esperando você · lições comprovadas ${g.aprendizado.licoes_comprovadas_pct}% · cadeia ${g.aprendizado.integridade ? "íntegra" : "QUEBRADA"}`],
  ].map(([t, v, d]) => `<div class="cartao"><div class="cartao-corpo"><div class="muted">${esc(t)}</div><div style="font-size:26px;font-weight:700">${esc(String(v))}</div><small class="muted">${esc(d)}</small></div></div>`).join("");
  const abas = [["paginas", "Páginas"], ["andares", "Andares"], ["evolucao", "Evolução por funcionário"], ["funcoes", "Funções"], ["modulos", "Módulos (código)"]]
    .map(([k, t]) => `<button class="btn ${E.gestaoAba === k ? "primario" : ""}" data-acao="gestao-aba" data-aba="${k}">${t}</button>`).join("");
  const corpo = { paginas: abaPaginas, andares: abaAndares, evolucao: abaEvolucao, funcoes: abaFuncoes, modulos: abaModulos }[E.gestaoAba](g);
  return cabecalho("Gestão do projeto", `Conferido em ${esc(dataT(g.gerado_em))}. Código + registros, nada estimado.`, acoes) +
    `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px">${cartoes}</div>
    <div style="display:flex;flex-wrap:wrap;gap:6px;margin:14px 0">${abas}</div>${corpo}`;
}

Object.assign(PAGINAS, { gestao: { titulo: "Gestão do projeto", render: renderGestao, carregar: async () => { await nomesDaEquipe(); await carregarGestao(); } } });
Object.assign(ACOES, {
  "recarregar-gestao": (el) => comCarregando(el, async () => { await carregarGestao(); desenhar(); }),
  "gestao-aba": (el) => { E.gestaoAba = el.dataset.aba; desenhar(); },
  "gestao-andar": (el) => { E.gestaoAba = "evolucao"; E.gestaoAndar = el.dataset.andar; desenhar(); },
});
document.addEventListener("change", (e) => { if (e.target.id === "gestao-andar") { E.gestaoAndar = e.target.value; desenhar(); } });
