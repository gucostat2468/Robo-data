// Fábrica de Planilhas: lotes sintéticos (TREINO_) de 15 regras de negócio, para a empresa treinar na esteira real.
// Tudo vem de /api/fabrica (robo/fabrica.py). Nenhum número daqui entra em painel real.

Object.assign(E, { fabrica: null });

async function carregarFabrica() {
  try { E.fabrica = await api("/api/fabrica"); } catch (e) { avisar(e.message, "erro"); }
}

const FAB_ESTADO = {
  na_esteira: ["info", "na esteira"], conferido_ok: ["sucesso", "esteira acertou"], conferido_divergente: ["perigo", "esteira errou"],
  esteira_reprovou: ["perigo", "esteira reprovou"], reprovado_na_conferencia: ["alerta", "barrado na conferência"],
  gerado: ["", "gerado (sem injetar)"],
};

function renderFabrica() {
  const f = E.fabrica;
  const acoes = `<button class="btn primario" data-acao="fabrica-produzir">${icone("play")}Produzir um lote agora</button>
    <button class="btn" data-acao="fabrica-recarregar">${icone("recarregar")}Atualizar</button>`;
  const desc = "Planilhas inventadas para treino, com milhares de linhas e a sujeira do mundo real. Cada uma passa pela mesma esteira " +
    "de uma planilha real, sai separada em Bases-Tratadas/_treino e é conferida contra o gabarito. Com planilha real na fila, a fábrica espera.";
  if (!f) return cabecalho("Fábrica de Planilhas", desc, acoes) + `<div class="carregando">Lendo a fábrica…</div>`;
  const c = f.config, e = f.por_estado || {};
  const total = Object.values(e).reduce((a, b) => a + b, 0);
  const acertou = e.conferido_ok || 0, errou = (e.conferido_divergente || 0) + (e.esteira_reprovou || 0);
  const cartoes = [
    ["Lotes produzidos", num(total), `${num(f.linhas_geradas)} linhas no total`],
    ["Esteira acertou", num(acertou), errou ? `${num(errou)} lote(s) em que a esteira errou` : "nenhum erro da esteira até agora"],
    ["Na esteira agora", num(e.na_esteira || 0), "um lote por vez"],
    ["Situação", c.habilitada ? "ligada" : "desligada", `a cada ${c.intervalo_minutos} min, até ${c.teto_por_dia} por dia, ${num(c.linhas_min)} a ${num(c.linhas_max)} linhas`],
  ].map(([a, v, d]) => `<div class="cartao"><div class="cartao-corpo"><div class="muted">${esc(a)}</div><div style="font-size:24px;font-weight:700">${esc(String(v))}</div><small class="muted">${esc(d)}</small></div></div>`).join("");
  const equipe = `<div class="secao-titulo">Quem faz</div><ul class="lista-ficha">${f.equipe.map((p) =>
    `<li><b>${esc(p.nome)}</b>, ${esc(p.cargo)}: ${esc(p.escopo.join(". "))}.</li>`).join("")}</ul>`;
  const lotes = `<div class="secao-titulo" style="margin-top:14px">Últimos lotes</div>
    <div class="tabela-envoltorio"><table class="tabela"><thead><tr><th>Quando</th><th>Regra de negócio</th><th>Linhas</th><th>Nível</th><th>Resultado</th><th>Detalhe</th></tr></thead><tbody>
    ${f.ultimos.map((l) => { const [cor, rot] = FAB_ESTADO[l.estado] || ["", l.estado]; let det = "";
      try { det = (JSON.parse(l.resultado || "{}").problemas || []).join(". "); } catch (x) { det = ""; }
      return `<tr><td>${esc(dataT(l.data_hora))}</td><td>${esc(l.regra)}</td><td>${num(l.linhas)}</td><td>${l.nivel}</td>
        <td><span class="etiqueta ${cor}">${esc(rot)}</span></td><td><small>${esc(det || "—")}</small></td></tr>`; }).join("")
      || `<tr><td colspan="6" class="muted">Nenhum lote ainda. A fábrica começa quando a fila real estiver vazia.</td></tr>`}</tbody></table></div>`;
  return cabecalho("Fábrica de Planilhas", desc, acoes) +
    `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px;margin-bottom:14px">${cartoes}</div>` + equipe + lotes;
}

Object.assign(PAGINAS, { fabrica: { titulo: "Fábrica de Planilhas", render: renderFabrica, carregar: carregarFabrica } });
Object.assign(ACOES, {
  "fabrica-recarregar": (el) => comCarregando(el, async () => { await carregarFabrica(); desenhar(); }),
  "fabrica-produzir": (el) => comCarregando(el, async () => {
    try {
      const r = await api("/api/fabrica/produzir", { corpo: {} });
      avisar(r.lote.estado === "na_esteira" ? `Lote ${r.lote.arquivo} (${num(r.lote.linhas)} linhas) entrou na esteira.`
        : `Lote barrado: ${r.lote.problemas.join(". ")}`, r.lote.estado === "na_esteira" ? "sucesso" : "alerta");
    } catch (e) { avisar(e.message, "erro"); }
    await carregarFabrica(); desenhar();
  }),
});
