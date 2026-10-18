// Banco da empresa: cada tabela da memória (SQLite) ao vivo — linhas, proteção, última gravação, backups e a cópia no
// PostgreSQL. Tudo vem de /api/banco/registros (lido agora do banco). Nada aqui é estimado.

Object.assign(E, { registros: null });

async function carregarRegistros() {
  try { E.registros = await api("/api/banco/registros"); } catch (e) { avisar(e.message, "erro"); }
}

function renderRegistros() {
  const r = E.registros;
  const acoes = `<button class="btn" data-acao="registros-recarregar">${icone("recarregar")}Conferir de novo</button>`;
  const desc = "A memória da empresa inteira. Nada se apaga (o banco recusa), tudo tem backup diário conferido e cópia no PostgreSQL para SQL, Power BI e Machine Learning.";
  if (!r) return cabecalho("Banco da empresa", desc, acoes) + `<div class="carregando">Lendo o banco…</div>`;
  const bs = r.backup_sqlite, bp = r.backup_postgres, pg = r.postgres;
  const cartoes = [
    ["Registros guardados", num(r.total_linhas), `${r.tabelas.length} tabelas · ${num(r.tamanho_mb)} MB · ${r.arquivo}`],
    ["Integridade do arquivo", r.integridade === "ok" ? "ok" : "PROBLEMA", `verificação do SQLite agora · diário ${r.modo_diario}`],
    ["Cadeia do conhecimento", r.cadeia_conhecimento.integra ? "íntegra" : "QUEBRADA", "SHA-256 com âncora em arquivo"],
    ["Último backup (SQLite)", bs?.ok ? dataT(bs.data_hora.replace(" ", "T")) : "ainda não", bs?.ok ? `${bs.tabelas} tabelas · ${num(bs.linhas)} linhas · ${num(bs.tamanho_mb)} MB · SHA ${bs.sha256.slice(0, 12)}…` : "roda sozinho 1x por dia"],
    ["Cópia no PostgreSQL", pg.ok ? `${pg.tabelas_copiadas} tabelas` : "desligada", pg.ok ? `schema ${pg.schema} · última cópia ${pg.ultima_copia ? dataT(pg.ultima_copia) : "—"}` : pg.motivo],
    ["Último backup (PostgreSQL)", bp?.ok ? dataT(bp.data_hora.replace(" ", "T")) : "—", bp?.ok ? `${bp.metodo} · ${num(bp.tamanho_mb)} MB` : "só com PostgreSQL ligado"],
  ].map(([t, v, d]) => `<div class="cartao"><div class="cartao-corpo"><div class="muted">${esc(t)}</div><div style="font-size:22px;font-weight:700">${esc(String(v))}</div><small class="muted">${esc(d)}</small></div></div>`).join("");
  const alertas = [
    ...(r.sem_documentacao.length ? [`Tabela(s) sem documentação: ${r.sem_documentacao.join(", ")}`] : []),
    ...(r.desprotegidas.length ? [`Tabela(s) que ainda podem ser apagadas: ${r.desprotegidas.join(", ")}`] : []),
    ...(r.integridade !== "ok" ? [`Integridade: ${r.integridade}`] : []),
  ];
  const selo = (t) => t.imutavel ? `<span class="etiqueta sucesso" title="não altera nem apaga">imutável</span>` :
    t.protegida_contra_apagar ? `<span class="etiqueta info" title="a situação muda; a linha nunca some">não apaga</span>` : `<span class="etiqueta alerta">estado atual</span>`;
  const grupos = Object.entries(r.grupos).map(([g, nome]) => {
    const ts = r.tabelas.filter((t) => t.grupo === g);
    return `<div class="secao-titulo" style="margin-top:14px">${esc(nome)}</div>
      <div class="tabela-envoltorio"><table class="tabela"><thead><tr><th>Tabela</th><th>Para que serve · 1 linha =</th><th class="direita">Linhas</th>
        <th class="direita">No PostgreSQL</th><th>Última gravação</th><th>Proteção</th></tr></thead><tbody>
      ${ts.map((t) => `<tr><td class="mono"><b>${esc(t.tabela)}</b></td><td>${esc(t.para_que)}<br><small class="muted">1 linha = ${esc(t.grao)} · ML: ${esc(t.ml)}</small></td>
        <td class="direita">${num(t.linhas)}</td>
        <td class="direita">${t.no_postgres == null ? `<span class="muted">—</span>` : t.no_postgres === t.linhas ? `${num(t.no_postgres)} ✅` : `${num(t.no_postgres)} <span class="muted">(copia a cada hora)</span>`}</td>
        <td>${t.ultima_gravacao ? esc(dataT(t.ultima_gravacao)) : `<span class="muted">—</span>`}</td><td>${selo(t)}</td></tr>`).join("")}
      </tbody></table></div>`;
  }).join("");
  const arquivos = `<div class="secao-titulo" style="margin-top:14px">Registros em arquivo (também no backup e guardados para sempre)</div>
    <ul class="lista-ficha">${r.arquivos.map((a) => `<li><span class="mono">${esc(a.onde)}</span> — ${esc(a.o_que)}: <b>${num(a.quantidade)}</b></li>`).join("")}</ul>`;
  return cabecalho("Banco da empresa", desc, acoes) +
    (alertas.length ? `<div class="ocorrencia erro" style="margin-bottom:12px"><div class="principal">${alertas.map(esc).join("<br>")}</div></div>` : "") +
    `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px">${cartoes}</div>` + grupos + arquivos;
}

Object.assign(PAGINAS, { registros: { titulo: "Banco da empresa", render: renderRegistros, carregar: carregarRegistros } });
Object.assign(ACOES, { "registros-recarregar": (el) => comCarregando(el, async () => { await carregarRegistros(); desenhar(); }) });
