// Treino contínuo: todos os funcionários trabalhando em casos sintéticos com gabarito, no nível de cada um.
// Tudo vem de /api/treino (registros reais: tentativas, níveis, casos, certificações). Nada aqui é estimado.

Object.assign(E, { treino: null, treinoFiltro: "" });

async function carregarTreino() {
  try { E.treino = await api("/api/treino"); } catch (e) { avisar(e.message, "erro"); }
}

const pct = (ok, n) => n ? `${num(Math.round(1000 * ok / n) / 10)}%` : "—";
const corTaxa = (t) => t == null ? "" : t >= 90 ? "sucesso" : t >= 70 ? "alerta" : "perigo";

function barrasNivel(porNivel) {  // quantas pessoas em cada nível (1 → 5)
  const max = Math.max(1, ...Object.values(porNivel));
  return `<span style="display:inline-flex;gap:3px;align-items:flex-end;height:26px">${[1, 2, 3, 4, 5].map((n) => {
    const q = porNivel[n] || 0;
    return `<span title="nível ${n}: ${q} pessoa(s)" style="display:inline-flex;flex-direction:column;align-items:center;font-size:10px">
      <span style="width:12px;height:${q ? Math.max(3, Math.round(q / max * 18)) : 2}px;background:${q ? "var(--primaria)" : "var(--borda)"};border-radius:2px"></span>${n}</span>`;
  }).join("")}</span>`;
}

function renderTreino() {
  const t = E.treino;
  const acoes = `<button class="btn primario" data-acao="treino-rodar">${icone("play")}Rodar uma rodada agora</button>
    <button class="btn" data-acao="treino-recarregar">${icone("recarregar")}Atualizar</button>`;
  const desc = "Cada funcionário recebe um caso com resposta conhecida, no nível dele, usando a ferramenta real do contrato. " +
    "4 de 5 certas sobe de nível; 2 ou menos desce. Os dados dos casos são sintéticos; a correção, os níveis, as lições e os registros são reais.";
  if (!t) return cabecalho("Treino contínuo", desc, acoes) + `<div class="carregando">Lendo os registros de treino…</div>`;
  const certs = t.certificacoes || [];
  const cartoes = [
    ["Últimas 24 h", `${t.recente.tentativas || 0} tentativas`, `${t.recente.pessoas || 0} de ${t.elegiveis} pessoas treinaram · acerto ${pct(t.recente.acertos, t.recente.tentativas)}`],
    ["Desde o início", t.total.tentativas || 0, `acerto ${pct(t.total.acertos, t.total.tentativas)} · nada é apagado`],
    ["Casos (Sala de Casos)", (t.casos.validado || 0) + (t.casos.encerrado || 0), `${t.casos.reprovado || 0} reprovado(s) na revisão antes de chegar a alguém`],
    ["Designers certificados", `${certs.filter((c) => c.ok).length}/${certs.length}`, "exame com um caso de cada nível, revisado por outra pessoa"],
    ["Versão do código", t.versao_codigo, "gravada em cada tentativa (rastreável para ML)"],
  ].map(([a, v, d]) => `<div class="cartao"><div class="cartao-corpo"><div class="muted">${esc(a)}</div><div style="font-size:24px;font-weight:700">${esc(String(v))}</div><small class="muted">${esc(d)}</small></div></div>`).join("");

  const comps = `<div class="secao-titulo">Competências (uma por ferramenta de contrato que dá para corrigir com gabarito)</div>
    <div class="tabela-envoltorio"><table class="tabela"><thead><tr><th>Competência</th><th>Quem prepara</th><th>Pessoas por nível</th><th>Acerto por nível</th></tr></thead><tbody>
    ${t.competencias.map((c) => `<tr><td><b>${esc(c.nome)}</b><br><small class="muted">ferramenta ${esc(c.ferramenta)}${c.requer_banco ? " · precisa do PostgreSQL" : ""}</small></td>
      <td>${esc(c.designer_nome)}</td><td>${barrasNivel(c.pessoas_por_nivel)}</td>
      <td>${[1, 2, 3, 4, 5].map((n) => { const x = c.por_nivel[n]; return `<span class="etiqueta ${x ? corTaxa(x.taxa) : ""}" title="${esc(c.niveis[n] || "")}">n${n}: ${x ? `${num(x.taxa)}% (${x.n})` : "—"}</span>`; }).join(" ")}</td></tr>`).join("")}
    </tbody></table></div>`;

  const sala = `<div class="secao-titulo" style="margin-top:14px">Sala de Casos — ${esc(t.sala.head)} (head), ${esc(t.sala.revisor)} (revisora), ${esc(t.sala.planejador)} (planejamento)</div>
    <div class="tabela-envoltorio"><table class="tabela"><thead><tr><th>Designer</th><th>Competência</th><th>Versão do gerador</th><th>Certificação</th></tr></thead><tbody>
    ${certs.map((c) => `<tr><td>${esc(c.designer_nome)}</td><td>${esc(c.competencia)}</td><td class="mono">${esc(c.versao_gerador)}</td>
      <td>${c.ok ? `<span class="etiqueta sucesso">certificado</span>` : `<span class="etiqueta perigo">reprovado</span>`} <small class="muted">${esc(dataT(c.data_hora))}</small></td></tr>`).join("") || `<tr><td colspan="4" class="muted">Nenhum exame ainda (acontece na primeira vez que a competência é usada).</td></tr>`}
    </tbody></table></div>`;

  const mudancas = `<div class="secao-titulo" style="margin-top:14px">Mudanças de nível (com as tentativas que provaram)</div>
    <ul class="lista-ficha">${t.mudancas_de_nivel.map((m) => `<li>${m.para > m.de ? "⬆️" : "⬇️"} <b>${esc(m.nome)}</b> · ${esc(m.competencia)}: nível ${m.de} → ${m.para}
      <span class="muted">— ${esc(m.motivo)} · ${esc(dataT(m.data_hora))} · prova ${esc(m.evidencia)}</span></li>`).join("") || `<li class="muted">Ainda ninguém mudou de nível (são 5 tentativas no nível para decidir).</li>`}</ul>`;

  const erros = `<div class="secao-titulo" style="margin-top:14px">Erros que mais se repetem (viram lição para a pessoa e, a partir de 3, handover para a área)</div>
    <ul class="lista-ficha">${t.erros_mais_comuns.map((e) => `<li><b>${esc(e.competencia)}</b> nível ${e.nivel}: ${esc((e.tipo_erro || "").replaceAll("_", " "))} <span class="etiqueta">${e.n}x</span></li>`).join("") || `<li class="muted">Nenhum erro registrado.</li>`}</ul>`;

  const f = (E.treinoFiltro || "").toLowerCase();
  const ultimas = t.ultimas.filter((u) => !f || `${u.nome} ${u.competencia}`.toLowerCase().includes(f));
  const feed = `<div class="secao-titulo" style="margin-top:14px;display:flex;justify-content:space-between;gap:8px;align-items:center">Últimas tentativas
      <label class="campo-busca">${icone("busca")}<input type="text" id="treino-filtro" placeholder="Pessoa ou competência…" value="${esc(E.treinoFiltro || "")}"></label></div>
    <div class="tabela-envoltorio"><table class="tabela"><thead><tr><th>Quando</th><th>Quem</th><th>Competência</th><th>Nível</th><th>Resultado</th><th>Detalhe</th></tr></thead><tbody>
    ${ultimas.map((u) => `<tr><td>${esc(dataT(u.data_hora))}</td><td>${esc(u.nome)}</td><td>${esc(u.competencia)}</td><td>${u.nivel}</td>
      <td>${u.acertou ? `<span class="etiqueta sucesso">acertou</span>` : `<span class="etiqueta perigo">errou</span>`}</td>
      <td><small>${esc((u.detalhe || "").slice(0, 160))}</small> <span class="muted mono" style="font-size:11px">T${u.id} · ${num(u.segundos)} s</span></td></tr>`).join("") || `<tr><td colspan="6" class="muted">Sem tentativas ainda.</td></tr>`}
    </tbody></table></div>`;

  return cabecalho("Treino contínuo", desc, acoes) +
    `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px;margin-bottom:14px">${cartoes}</div>` +
    comps + sala + mudancas + erros + feed;
}

Object.assign(PAGINAS, { treino: { titulo: "Treino contínuo", render: renderTreino, carregar: async () => { await carregarTreino(); } } });
Object.assign(ACOES, {
  "treino-recarregar": (el) => comCarregando(el, async () => { await carregarTreino(); desenhar(); }),
  "treino-rodar": (el) => comCarregando(el, async () => {
    try {
      const r = await api("/api/treino/rodar", { corpo: { quantos: 6 } });
      avisar(r.ok ? `Rodada ${r.rodada}: ${r.tentativas} tentativa(s), ${r.acertos} certa(s).` : r.motivo, r.ok ? "sucesso" : "alerta");
    } catch (e) { avisar(e.message, "erro"); }
    await carregarTreino(); desenhar();
  }),
});
document.addEventListener("input", (e) => {
  if (e.target.id !== "treino-filtro") return;
  E.treinoFiltro = e.target.value;
  clearTimeout(E._buscaTreino);
  E._buscaTreino = setTimeout(() => { desenhar(); const c = $("#treino-filtro"); if (c) { c.focus(); c.setSelectionRange(c.value.length, c.value.length); } }, 250);
});
