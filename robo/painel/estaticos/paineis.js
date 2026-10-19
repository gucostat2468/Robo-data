// Dashboards: os painéis que a Bárbara (especialista em Power BI) monta do zero a partir do banco real e mantém de hora
// em hora; o Heitor (analista de BI) refaz as contas por outro caminho antes de publicar. Tudo vem de /api/paineis.
// Gráficos em SVG puro (sem biblioteca externa): linha para tendência, barras para comparar, colunas para níveis.

Object.assign(E, { paineis: null, paineisAba: "planilhas", paineisPlanilha: 0 });

async function carregarPaineis() {
  try { E.paineis = await api("/api/paineis"); } catch (e) { avisar(e.message, "erro"); }
}

const pbPct = (x, casas = 1) => x == null ? "—" : `${(x * 100).toFixed(casas).replace(".", ",")}%`;
const pbNum = (v, formato) => v == null ? "—" : formato === "percentual" ? pbPct(v) :
  formato === "decimal" ? Number(v).toFixed(2).replace(".", ",") : num(v);

function pbKpis(pagina) {
  const itens = Object.values(pagina.indicadores || {});
  if (!itens.length) return "";
  return `<div class="pb-kpis">${itens.map((i) => `<div class="pb-kpi" title="${esc(i.sql)}">
      <span class="pb-kpi-rotulo">${esc(i.rotulo)}</span>
      <strong class="pb-kpi-valor">${esc(pbNum(i.valor, i.formato))}</strong>
      ${i.detalhe ? `<small class="muted">${esc(i.detalhe)}</small>` : ""}</div>`).join("")}</div>`;
}

function pbLinha(g, campo, rotuloX) {  // tendência no tempo (cartão largo: proporção 4:1 para não ficar gigante)
  const L = g.linhas || [];
  if (L.length < 2) return pbVazio(L.length ? "Só um ponto até agora: a linha aparece a partir do segundo." : "");
  const W = 1000, H = 250, m = { e: 44, d: 14, t: 14, b: 30 };
  const max = Math.max(1, ...L.map((r) => r[campo] || 0));
  const x = (i) => m.e + i * (W - m.e - m.d) / (L.length - 1);
  const y = (v) => H - m.b - (v || 0) / max * (H - m.t - m.b);
  const pts = L.map((r, i) => `${x(i).toFixed(1)},${y(r[campo]).toFixed(1)}`).join(" ");
  const passo = Math.ceil(L.length / 6);
  const eixoX = L.map((r, i) => i % passo && i !== L.length - 1 ? "" :
    `<text x="${x(i)}" y="${H - 8}" text-anchor="${i === L.length - 1 ? "end" : i === 0 ? "start" : "middle"}" class="pb-eixo">${esc(rotuloX(r))}</text>`).join("");
  const grade = [0, 0.5, 1].map((f) => `<line x1="${m.e}" x2="${W - m.d}" y1="${y(max * f)}" y2="${y(max * f)}" class="pb-grade"/>
    <text x="${m.e - 6}" y="${y(max * f) + 4}" text-anchor="end" class="pb-eixo">${num(Math.round(max * f))}</text>`).join("");
  const ult = L[L.length - 1];
  return `<svg viewBox="0 0 ${W} ${H}" class="pb-svg" role="img" aria-label="${esc(g.titulo)}">${grade}
    <polygon points="${m.e},${H - m.b} ${pts} ${x(L.length - 1)},${H - m.b}" class="pb-area"/>
    <polyline points="${pts}" class="pb-linha"/>
    <circle cx="${x(L.length - 1)}" cy="${y(ult[campo])}" r="4" class="pb-ponto"/>
    <text x="${x(L.length - 1) - 6}" y="${y(ult[campo]) - 8}" text-anchor="end" class="pb-valor">${num(ult[campo])}</text>${eixoX}</svg>`;
}

function pbBarras(g, campo, rotulo, formato, meta) {  // comparação entre categorias (horizontal: rótulo longo cabe)
  const L = (g.linhas || []).slice(0, 20);
  if (!L.length) return pbVazio();
  const max = formato === "percentual" ? 1 : Math.max(1, ...L.map((r) => r[campo] || 0));
  return `<div class="pb-barras">${L.map((r) => {
    const v = r[campo];
    const ruim = formato === "percentual" && meta != null && v != null && v < meta;
    return `<div class="pb-barra-linha"><span class="pb-barra-rotulo" title="${esc(rotulo(r))}">${esc(rotulo(r))}</span>
      <span class="pb-barra-trilho"><span class="pb-barra" style="width:${Math.max(1.5, (v || 0) / max * 100)}%;background:${ruim ? "var(--perigo)" : "var(--primaria)"}"></span>
      ${meta != null ? `<span class="pb-meta" style="left:${meta * 100}%" title="meta ${pbPct(meta, 0)}"></span>` : ""}</span>
      <b class="pb-barra-valor">${esc(formato === "percentual" ? pbPct(v) : num(v))}</b></div>`;
  }).join("")}</div>`;
}

function pbColunas(g, series) {  // poucas categorias ordenadas (níveis 1–5, dias): colunas lado a lado
  const L = g.linhas || [];
  if (!L.length) return pbVazio();
  const W = 480, H = 210, m = { e: 10, d: 10, t: 24, b: 28 };
  const max = Math.max(1e-9, ...L.flatMap((r) => series.map((s) => s.valor(r) || 0)));
  const fatia = (W - m.e - m.d) / L.length, larg = Math.min(46, fatia * 0.7 / series.length);
  const barras = L.map((r, i) => series.map((s, k) => {
    const v = s.valor(r) || 0, h = v / max * (H - m.t - m.b);
    const x0 = m.e + i * fatia + (fatia - larg * series.length) / 2 + k * larg;
    return `<rect x="${x0}" y="${H - m.b - h}" width="${larg - 3}" height="${Math.max(1, h)}" rx="3" fill="${s.cor(r)}"><title>${esc(s.nome)}: ${esc(s.texto(r))}</title></rect>
      <text x="${x0 + (larg - 3) / 2}" y="${H - m.b - h - 6}" text-anchor="middle" class="pb-valor">${esc(s.texto(r))}</text>`;
  }).join("") + `<text x="${m.e + i * fatia + fatia / 2}" y="${H - 9}" text-anchor="middle" class="pb-eixo">${esc(series[0].rotulo(r))}</text>`).join("");
  const legenda = series.length > 1 ? `<div class="pb-legenda">${series.map((s) => `<span><i style="background:${s.cor({})}"></i>${esc(s.nome)}</span>`).join("")}</div>` : "";
  return `<svg viewBox="0 0 ${W} ${H}" class="pb-svg" role="img" aria-label="${esc(g.titulo)}">${barras}</svg>${legenda}`;
}

function pbTabela(g, colunas) {
  const L = g.linhas || [];
  if (!L.length) return pbVazio();
  return `<div class="tabela-envoltorio pb-tabela"><table class="tabela"><thead><tr>${colunas.map((c) => `<th>${esc(c[0])}</th>`).join("")}</tr></thead>
    <tbody>${L.slice(0, 15).map((r) => `<tr>${colunas.map((c) => `<td>${c[1](r)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

const pbVazio = (texto) => `<div class="pb-vazio">${esc(texto || "Sem registros ainda: este gráfico enche quando a empresa gerar esses dados.")}</div>`;

function pbCartao(g, corpo, largo) {
  if (!g) return "";
  return `<section class="pb-cartao${largo ? " largo" : ""}"><header><h3>${esc(g.titulo)}</h3>
    <details class="pb-sql"><summary>consulta</summary><code>${esc(g.sql || "")}</code></details></header>${corpo}</section>`;
}

const pbHora = (r) => (r.hora || "").slice(8, 10) + "/" + (r.hora || "").slice(5, 7) + " " + (r.hora || "").slice(11, 13) + "h";
const pbDia = (r) => (r.dia || "").slice(8, 10) + "/" + (r.dia || "").slice(5, 7);
const corTaxaPb = (t) => t == null ? "var(--borda-forte)" : t >= 0.95 ? "var(--sucesso)" : t >= 0.8 ? "var(--alerta)" : "var(--perigo)";

function pbPagina(p) {
  const G = p.graficos || {};
  const blocos = {
    executiva: () => [
      pbCartao(G.por_hora, pbLinha(G.por_hora || {}, "tentativas", pbHora), true),
      pbCartao(G.por_andar, pbBarras(G.por_andar || {}, "taxa", (r) => r.rotulo, "percentual", 0.95)),
      pbCartao(G.por_nivel, pbColunas(G.por_nivel || {}, [{ nome: "Acerto", valor: (r) => r.taxa, texto: (r) => pbPct(r.taxa),
        cor: (r) => corTaxaPb(r.taxa), rotulo: (r) => `Nível ${r.nivel}` }])),
      pbCartao(G.por_dia, pbColunas(G.por_dia || {}, [{ nome: "Tentativas", valor: (r) => r.tentativas, texto: (r) => num(r.tentativas),
        cor: () => "var(--primaria)", rotulo: pbDia }]), true),
    ],
    treino: () => [
      pbCartao(G.por_competencia, pbBarras(G.por_competencia || {}, "taxa", (r) => r.rotulo, "percentual", 0.95), true),
      pbCartao(G.gargalos, pbTabela(G.gargalos || {}, [["Onde", (r) => esc(r.rotulo)], ["Tentativas", (r) => num(r.n)],
        ["Acerto", (r) => `<span class="etiqueta perigo">${pbPct(r.taxa, 0)}</span>`]])),
      pbCartao(G.erros, pbBarras(G.erros || {}, "n", (r) => (r.tipo_erro || "").replaceAll("_", " "))),
      pbCartao(G.evolucao, pbColunas(G.evolucao || {}, [
        { nome: "Subidas", valor: (r) => r.subidas, texto: (r) => num(r.subidas || 0), cor: () => "var(--sucesso)", rotulo: pbDia },
        { nome: "Quedas", valor: (r) => r.quedas, texto: (r) => num(r.quedas || 0), cor: () => "var(--perigo)", rotulo: pbDia }])),
    ],
    pessoas: () => [
      pbCartao(G.headcount, pbBarras(G.headcount || {}, "pessoas", (r) => r.rotulo)),
      pbCartao(G.ranking, pbTabela(G.ranking || {}, [["Pessoa", (r) => `<b>${esc(r.nome)}</b>`], ["Andar", (r) => r.andar ? `${r.andar}º` : "—"],
        ["Tentativas", (r) => num(r.tentativas)], ["Acerto", (r) => `<span style="color:${corTaxaPb(r.taxa)};font-weight:600">${pbPct(r.taxa)}</span>`]])),
      pbCartao(G.rh, pbTabela(G.rh || {}, [["Movimento", (r) => esc(r.tipo)], ["Situação", (r) => esc(r.situacao || "")], ["Qtde", (r) => num(r.n)]])),
    ],
    conversas: () => [
      pbCartao(G.ultimas, `<ul class="pb-conversas">${(G.ultimas?.linhas || []).map((r) => `<li><b>${esc(r.de_nome)}</b> → ${esc(r.para_nome)}
        <span class="etiqueta">${esc(r.tipo)}</span> <small class="muted">${esc(dataT(r.data_hora))}</small><br>${esc(r.texto)}</li>`).join("") || "<li class='muted'>Nenhuma conversa ainda.</li>"}</ul>`, true),
      pbCartao(G.por_tipo, pbBarras(G.por_tipo || {}, "n", (r) => r.tipo)),
      pbCartao(G.quem_fala, pbBarras(G.quem_fala || {}, "n", (r) => r.rotulo)),
      pbCartao(G.mentorias, pbBarras(G.mentorias || {}, "n", (r) => (r.situacao || "").replaceAll("_", " "))),
    ],
    operacao: () => [
      pbCartao(G.rotinas, pbTabela(G.rotinas || {}, [["Rotina", (r) => `<b>${esc(r.nome)}</b>`], ["Responsável", (r) => esc(r.responsavel || "")],
        ["Execuções", (r) => num(r.execucoes)], ["Erros", (r) => r.erros ? `<span class="etiqueta perigo">${num(r.erros)}</span>` : "0"],
        ["Tempo médio", (r) => `${num(Math.round((r.segundos_medio || 0) * 10) / 10)} s`], ["Última", (r) => esc(dataT(r.ultima))]]), true),
      pbCartao(G.tabelas, pbBarras(G.tabelas || {}, "linhas", (r) => r.tabela)),
    ],
  };
  const achados = (p.achados || []).length ? `<div class="pb-achados">${p.achados.map((a) => `<div>✔ ${esc(a)}</div>`).join("")}</div>` : "";
  return pbKpis(p) + `<div class="pb-grade-cartoes">${(blocos[p.id] ? blocos[p.id]() : []).join("")}</div>` + achados;
}

// ------------------------------------------------------------------ Planilhas: a leitura da Bárbara de cada planilha
const pbNumBr = (v) => v == null ? "—" : Math.abs(v) >= 1000 ? num(Math.round(v * 100) / 100) : String(Math.round(v * 10000) / 10000).replace(".", ",");
const PB_PAPEL = { id: "identificador", data: "data", categoria: "categoria (dimensão)", numero: "métrica (medida)",
  texto_livre: "texto livre", texto: "texto", vazia: "vazia" };

function pbPlanilhas(lista) {
  if (!lista || !lista.length) return pbVazio("Nenhuma planilha lida ainda. Quando uma planilha for publicada em Bases-Tratadas (ou o laboratório gerar as sintéticas), a Bárbara lê aqui.");
  const i = Math.min(E.paineisPlanilha || 0, lista.length - 1), L = lista[i];
  const seletor = `<div class="pl-lista" role="tablist" aria-label="Planilhas lidas">${lista.map((x, k) => `<button role="tab" aria-selected="${k === i}"
    class="pl-item${k === i ? " ativo" : ""}" data-acao="paineis-planilha" data-i="${k}"><b>${esc(x.nome.replace(/\.(xlsx|csv)$/i, "").replace(/^laboratorio_/, ""))}</b>
    <small>${esc(x.tema.nome)}</small><span class="etiqueta ${x.origem === "real" ? "sucesso" : ""}">${x.origem === "real" ? "real" : "sintética"}</span></button>`).join("")}</div>`;
  const kpis = `<div class="pb-kpis">${Object.entries(L.ancoras).map(([n, v]) => `<div class="pb-kpi"><span class="pb-kpi-rotulo">${esc(n)}</span>
    <strong class="pb-kpi-valor">${esc(/taxa/i.test(n) ? pbPct(v, 2) : pbNumBr(v))}</strong><small class="muted">número-âncora: o Power BI tem que mostrar este valor sem filtro</small></div>`).join("")}</div>`;
  const seg = L.por_segmento;
  const grafico = seg ? pbCartao({ titulo: `${seg.principal} por ${seg.rotulo}`, sql: `agrupado por ${seg.coluna} (pandas), conferido pelo Heitor com numpy` },
    pbBarras({ linhas: seg.linhas }, seg.principal, (r) => r.segmento), true) : "";
  const regrasOk = L.regras.filter((r) => r.nivel === "ok").length;
  const dicionario = pbCartao({ titulo: "Dicionário dos cabeçalhos (o que é cada coluna)", sql: "papel pelo conteúdo (robo/analise.py) + glossário de negócio (robo/leitura_bi.py)" },
    pbTabela({ linhas: L.colunas }, [["Cabeçalho", (r) => `<b>${esc(r.rotulo)}</b><br><small class="mono muted">${esc(r.coluna)}</small>`],
      ["Papel", (r) => esc(PB_PAPEL[r.papel] || r.papel)], ["Significado", (r) => esc(r.significado)], ["Regra de negócio", (r) => esc(r.regra || "—")],
      ["Preenchido", (r) => pbPct(r.preenchimento, 0)]]), true);
  const regras = pbCartao({ titulo: `Regras de negócio conferidas nos dados (${regrasOk} de ${L.regras.length} sem problema)`, sql: "cada regra contada linha a linha" },
    pbTabela({ linhas: L.regras }, [["Coluna", (r) => esc(r.coluna)], ["Regra", (r) => esc(r.regra)],
      ["Resultado", (r) => `<span class="etiqueta ${r.nivel === "erro" ? "perigo" : r.nivel === "aviso" ? "alerta" : r.nivel === "ok" ? "sucesso" : ""}">${esc(r.texto)}</span>`]]]]), true);
  const m = L.modelo;
  const estrela = pbCartao({ titulo: "Modelo estrela proposto", sql: "fato = métricas + chaves; dimensões = categorias; calendário = coluna de data" },
    `<div class="pl-estrela"><div class="pl-dims">${m.dimensoes.map((d) => `<div class="pl-caixa">${esc(d.tabela)}<small>${d.valores} valores</small></div>`).join("")}
      ${m.calendario ? `<div class="pl-caixa">dim_calendario<small>a partir de ${esc(m.calendario)}</small></div>` : ""}</div>
      <div class="pl-seta">1 → *</div><div class="pl-caixa fato">${esc(m.fato)}<small>${m.metricas.map(esc).join(", ") || "sem métricas"}</small></div></div>
      <ul class="lista-ficha">${m.relacoes.map((r) => `<li class="mono" style="font-size:12px">${esc(r)}</li>`).join("")}</ul>`);
  const medidas = pbCartao({ titulo: `Medidas DAX (${L.medidas.length}) — prontas para colar em Página Inicial → Nova medida`, sql: "geradas para as colunas desta planilha" },
    L.medidas.map((d) => `<details class="pl-medida"><summary><b>${esc(d.nome)}</b>${L.ancoras[d.nome] !== undefined ? ` <span class="muted">→ deve mostrar ${esc(/taxa/i.test(d.nome) ? pbPct(L.ancoras[d.nome], 2) : pbNumBr(L.ancoras[d.nome]))}</span>` : ""}</summary>
      <pre class="pl-dax">${esc(d.dax)}</pre><p>${esc(d.explicacao)}</p><p class="muted">${esc(d.contexto)}</p></details>`).join(""), true);
  const visuais = pbCartao({ titulo: "Visuais recomendados", sql: "pela pergunta de negócio" },
    pbTabela({ linhas: L.visuais }, [["Visual", (r) => `<b>${esc(r.visual)}</b>`], ["Responde", (r) => esc(r.pergunta)], ["Por quê", (r) => esc(r.porque)], ["Quando não usar", (r) => esc(r.nao_usar)]]), true);
  const tema = `<div class="pl-tema"><div><span class="etiqueta ${L.origem === "real" ? "sucesso" : ""}">${L.origem === "real" ? "planilha real" : "dados sintéticos (laboratório)"}</span>
    <h2>${esc(L.tema.nome)}</h2><p>${esc(L.tema.descricao)}</p><small class="muted">${esc(L.nome)} · ${num(L.linhas)} linhas × ${L.colunas_qtd} colunas${L.tema.evidencia ? ` · reconhecido por: ${L.tema.evidencia.map(esc).join(", ")}` : ""}</small></div>
    ${L.tema.perguntas.length ? `<div><b>Perguntas que este painel responde</b><ul class="lista-ficha">${L.tema.perguntas.map((q) => `<li>${esc(q)}</li>`).join("")}</ul></div>` : ""}</div>`;
  const achados = `<div class="pb-achados">${L.achados.map((a) => /^Regra quebrada/.test(a) ? `<div class="alerta">⚠ ${esc(a)}</div>` : `<div>✔ ${esc(a)}</div>`).join("")}</div>`;
  return seletor + tema + kpis + achados + `<div class="pb-grade-cartoes" style="margin-top:12px">${grafico}${dicionario}${regras}${estrela}${medidas}${visuais}</div>`;
}

function renderPaineis() {
  const d = E.paineis;
  const acoes = `<button class="btn primario" data-acao="paineis-atualizar">${icone("recarregar")}Montar e conferir agora</button>`;
  const desc = "Planilhas: a Bárbara lê cada planilha (reais e sintéticas), entende o tema pelos cabeçalhos, confere as regras de negócio e entrega o modelo e as medidas DAX. " +
    "Equipe: os painéis de desempenho, montados do banco da empresa de hora em hora. " +
    "Antes de publicar, o Heitor refaz cada total por outro caminho: se um número não bate, o painel não é publicado. " +
    "Passe o mouse num número ou abra “consulta” para ver de onde ele veio.";
  if (!d) return cabecalho("Dashboards", desc, acoes) + `<div class="carregando">Lendo os painéis…</div>`;
  if (!d.painel) return cabecalho("Dashboards", desc, acoes) +
    `<div class="cartao"><div class="cartao-corpo">Ainda não há painel publicado. A rotina “paineis” monta o primeiro na próxima hora — ou clique em “Montar e conferir agora”.</div></div>`;
  const P = d.painel;
  const temPlanilhas = Array.isArray(P.planilhas);
  const abasLista = (temPlanilhas ? [{ id: "planilhas", titulo: `Planilhas (${P.planilhas.length})` }] : []).concat(P.paginas);
  const aba = abasLista.find((p) => p.id === E.paineisAba) || abasLista[0];
  const conf = P.conferencia || {};
  const selo = `<div class="pb-selo"><span class="ponto ligado"></span><span>Versão ${esc(String(P.versao))} · montada por <b>${esc(P.autor_nome)}</b> em ${esc(dataT(P.montado_em))}
    · conferida por <b>${esc(conf.conferente_nome || "")}</b>: ${conf.divergencias === 0 ? "nenhuma divergência" : esc(String(conf.divergencias))}</span></div>`;
  const abas = `<div class="pb-abas" role="tablist">${abasLista.map((p) => `<button role="tab" aria-selected="${p.id === aba.id}" class="pb-aba${p.id === aba.id ? " ativa" : ""}"
    data-acao="paineis-aba" data-aba="${esc(p.id)}">${esc(p.titulo)}</button>`).join("")}</div>`;
  const versoes = `<details class="pb-versoes"><summary>Registro de manutenção (${d.versoes.length} últimas montagens — nada é apagado)</summary>
    ${pbTabela({ linhas: d.versoes }, [["Quando", (r) => esc(dataT(r.data_hora))], ["Situação", (r) => `<span class="etiqueta ${r.situacao === "reprovado" ? "perigo" : r.situacao === "publicado" ? "sucesso" : ""}">${esc(r.situacao.replace("_", " "))}</span>`],
      ["Assinatura", (r) => `<span class="mono">${esc(r.assinatura)}</span>`], ["Divergências", (r) => esc((JSON.parse(r.divergencias || "[]")).join("; ") || "—")]])}</details>`;
  return cabecalho("Dashboards", desc, acoes) + selo + abas + `<div class="pb-pagina">${aba.id === "planilhas" ? pbPlanilhas(P.planilhas) : pbPagina(aba)}</div>` + versoes;
}

Object.assign(PAGINAS, { paineis: { titulo: "Dashboards", render: renderPaineis, carregar: carregarPaineis } });
Object.assign(ACOES, {
  "paineis-aba": (el) => { E.paineisAba = el.dataset.aba; desenhar(); },
  "paineis-planilha": (el) => { E.paineisPlanilha = Number(el.dataset.i) || 0; desenhar(); },
  "paineis-atualizar": (el) => comCarregando(el, async () => {
    try {
      const r = await api("/api/paineis/atualizar", { corpo: {} });
      avisar(r.situacao === "reprovado" ? `O Heitor segurou a publicação: ${r.divergencias.join("; ")}` :
        r.situacao === "publicado" ? `Versão ${r.versao} publicada e conferida.` : "Nada mudou desde a última versão (registrado).",
      r.ok ? "sucesso" : "alerta");
    } catch (e) { avisar(e.message, "erro"); }
    await carregarPaineis(); desenhar();
  }),
});
