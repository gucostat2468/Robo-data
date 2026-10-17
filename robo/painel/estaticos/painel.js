/* =====================================================================
   Robô de Planilhas — interface
   Sem bibliotecas externas: funciona offline. Conversa com a API local (/api/...).
   ===================================================================== */
"use strict";

// ------------------------------------------------------------------ ícones (traço 24x24)
const ICONES = {
  grafico: '<path d="M4 20V10"/><path d="M10 20V4"/><path d="M16 20v-7"/><path d="M22 20H2"/>',
  lista: '<path d="M9 6h11M9 12h11M9 18h11"/><path d="M4 6h.01M4 12h.01M4 18h.01"/>',
  alvo: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 21l1.9-5.4A8 8 0 1 1 21 12z"/><path d="M8.5 11h7"/><path d="M8.5 14.5h4.5"/>',
  escudo: '<path d="M12 3 4.5 6v6c0 4.4 3.2 8.2 7.5 9 4.3-.8 7.5-4.6 7.5-9V6z"/><path d="m9 12 2 2 4-4"/>',
  home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M10 21v-6h4v6"/>',
  alerta: '<path d="M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  historico: '<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/><path d="M12 7v5l3 2"/>',
  frasco: '<path d="M9 3h6"/><path d="M10 3v6L4.6 18.6A1.6 1.6 0 0 0 6 21h12a1.6 1.6 0 0 0 1.4-2.4L14 9V3"/><path d="M7.5 15h9"/>',
  banco: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
  atividade: '<path d="M3 12h4l3 8 4-16 3 8h4"/>',
  ajustes: '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
  pasta: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  play: '<path d="M7 4.5v15l12-7.5z"/>',
  pausa: '<path d="M8 5v14M16 5v14"/>',
  raio: '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
  enviar: '<path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/>',
  ok: '<path d="m5 12.5 4.5 4.5L19 7"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  planilha: '<path d="M14 3H6.5A1.5 1.5 0 0 0 5 4.5v15A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V8z"/><path d="M14 3v5h5"/><path d="M8.5 12.5h7M8.5 16.5h7M12 11v7"/>',
  abrir: '<path d="M14 4h6v6"/><path d="M20 4 11 13"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  lixeira: '<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/>',
  busca: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  energia: '<path d="M12 3v9"/><path d="M6.3 6.3a8 8 0 1 0 11.4 0"/>',
  recarregar: '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
  relogio: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  seta: '<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>',
  robo: '<rect x="4" y="8" width="16" height="12" rx="3"/><path d="M12 4v4"/><circle cx="9" cy="14" r="1.2"/><circle cx="15" cy="14" r="1.2"/><path d="M2 13v3M22 13v3"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 8h.01"/>',
  girar: '<path d="M21 12a9 9 0 1 1-6.2-8.6"/>',
  editar: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
  codigo: '<path d="m8 8-4 4 4 4"/><path d="m16 8 4 4-4 4"/><path d="m13.5 5-3 14"/>',
  copiar: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/>',
  cubo: '<path d="M12 2 3 7v10l9 5 9-5V7z"/><path d="m3 7 9 5 9-5"/><path d="M12 12v10"/>',
  equipe: '<circle cx="9" cy="8" r="3.2"/><path d="M3 20a6 6 0 0 1 12 0"/><circle cx="17.5" cy="9" r="2.5"/><path d="M16 14.2a5 5 0 0 1 6 4.8"/>',
  mais: '<path d="M12 5v14M5 12h14"/>',
  cima: '<path d="m6 15 6-6 6 6"/>',
  baixo: '<path d="m6 9 6 6 6-6"/>',
  atalho: '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>',
};
const icone = (nome, classe = "") => `<svg class="icone ${classe}" viewBox="0 0 24 24" aria-hidden="true">${ICONES[nome] || ""}</svg>`;

// ------------------------------------------------------------------ utilitários
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (v) => (v === null || v === undefined || v === "") ? "—" : Number(v).toLocaleString("pt-BR");
const $ = (sel, raiz = document) => raiz.querySelector(sel);

function dataCurta(texto) {
  if (!texto) return "";
  const [d, h = ""] = String(texto).split(" ");
  const [a, m, dia] = d.split("-");
  const hoje = new Date();
  const ehHoje = Number(a) === hoje.getFullYear() && Number(m) === hoje.getMonth() + 1 && Number(dia) === hoje.getDate();
  return ehHoje ? `hoje, ${h.slice(0, 5)}` : `${dia}/${m}/${a} ${h.slice(0, 5)}`;
}
function relativo(segundos) {
  if (segundos == null) return "";
  const s = Math.max(0, Math.round(Date.now() / 1000 - segundos));
  if (s < 5) return "agora";
  if (s < 60) return `há ${s} s`;
  if (s < 3600) return `há ${Math.floor(s / 60)} min`;
  return `há ${Math.floor(s / 3600)} h`;
}
function tamanho(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1048576).toFixed(1).replace(".", ",")} MB`;
}
function duracao(seg) {
  const v = Number(String(seg ?? "").replace(",", "."));
  if (!isFinite(v)) return "—";
  return v < 60 ? `${v.toFixed(1).replace(".", ",")} s` : `${Math.floor(v / 60)} min ${Math.round(v % 60)} s`;
}

async function api(caminho, { corpo, arquivo, metodo } = {}) {
  const opcoes = { method: metodo || (corpo !== undefined || arquivo ? "POST" : "GET"), headers: {} };
  if (opcoes.method === "POST") opcoes.headers["X-Robo-Painel"] = "1";
  if (arquivo) {
    opcoes.body = arquivo;
    opcoes.headers["X-Nome-Arquivo"] = encodeURIComponent(arquivo.name);
    opcoes.headers["Content-Type"] = "application/octet-stream";
  } else if (corpo !== undefined) {
    opcoes.body = JSON.stringify(corpo);
    opcoes.headers["Content-Type"] = "application/json";
  }
  let resposta;
  try {
    resposta = await fetch(caminho, opcoes);
  } catch {
    throw new Error("Sem conexão com o robô. Ele foi encerrado? Abra pelo atalho “Robô de Planilhas”.");
  }
  const dados = await resposta.json().catch(() => ({}));
  if (resposta.status === 401 && dados.login) { mostrarLogin(); throw new Error(dados.erro); }
  if (!resposta.ok) throw new Error(dados.erro || `Erro ${resposta.status}`);
  return dados;
}

function mostrarLogin() {
  if ($("#tela-login")) return;
  const el = document.createElement("div");
  el.id = "tela-login";
  el.style.cssText = "position:fixed;inset:0;z-index:999;display:grid;place-items:center;background:var(--fundo)";
  el.innerHTML = `<form class="cartao" style="width:min(380px,92vw)"><div class="cartao-corpo">
      <h1 style="margin:0 0 6px">Robô de Planilhas</h1><p class="muted" style="margin:0 0 14px">Este painel tem senha. Digite para entrar.</p>
      <input type="password" id="login-senha" autocomplete="current-password" placeholder="Senha" style="width:100%;margin-bottom:10px">
      <p id="login-erro" class="muted" style="color:var(--perigo);min-height:1.2em;margin:0 0 8px"></p>
      <button class="btn primario" type="submit" style="width:100%">Entrar</button></div></form>`;
  el.querySelector("form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const r = await fetch("/api/login", { method: "POST", headers: { "X-Robo-Painel": "1", "Content-Type": "application/json" },
      body: JSON.stringify({ senha: $("#login-senha").value }) });
    const d = await r.json().catch(() => ({}));
    if (r.ok) location.reload(); else $("#login-erro").textContent = d.erro || "Não foi possível entrar.";
  });
  document.body.appendChild(el);
  $("#login-senha").focus();
}

function avisar(mensagem, tipo = "") {
  const el = document.createElement("div");
  el.className = `aviso ${tipo}`;
  el.innerHTML = `${icone(tipo === "erro" ? "alerta" : tipo === "sucesso" ? "ok" : "info")}<div>${esc(mensagem)}</div>`;
  $("#avisos").appendChild(el);
  setTimeout(() => el.remove(), tipo === "erro" ? 7000 : 4000);
}

function confirmar({ titulo, texto, botao = "Confirmar", perigo = false }) {
  return new Promise((resolver) => {
    const fundo = $("#modal");
    fundo.innerHTML = `<div class="modal" role="dialog" aria-modal="true">
      <h2>${esc(titulo)}</h2><p>${esc(texto)}</p>
      <div class="acoes"><button class="btn" data-r="0">Cancelar</button>
      <button class="btn ${perigo ? "perigo" : "primario"}" data-r="1">${esc(botao)}</button></div></div>`;
    fundo.hidden = false;
    const fechar = (r) => { fundo.hidden = true; fundo.innerHTML = ""; resolver(r); };
    fundo.onclick = (e) => { if (e.target === fundo) fechar(false); const b = e.target.closest("[data-r]"); if (b) fechar(b.dataset.r === "1"); };
    $("[data-r='1']", fundo).focus();
  });
}

async function comCarregando(botao, tarefa) {
  if (botao) { botao.disabled = true; botao.dataset.html = botao.innerHTML; botao.innerHTML = `${icone("girar", "girando")} Aguarde…`; }
  try { return await tarefa(); }
  catch (e) { avisar(e.message, "erro"); }
  finally { if (botao && botao.isConnected) { botao.disabled = false; botao.innerHTML = botao.dataset.html; } }
}

// ------------------------------------------------------------------ estado
const E = {
  geral: null, pagina: "inicio",
  historico: [], filtro: "todos", busca: "", assinaturaHist: "",
  reprovados: null, assinaturaRep: "",
  teste: null, arquivoTeste: null, abaTeste: 0,
  config: null, banco: null,
  equipe: null, editando: null, catalogoAberto: false, buscaHabilidade: "",
  consultas: null, consultaAtual: null, resultadoConsulta: null, buscaConsulta: "",
  log: [], logSeq: 0, logFiltro: "todos", autoRolar: true,
  organograma: null,
  canal: null, canalAtual: "geral", canalAutor: "", canalTipo: "", canalDias: 0, canalBusca: "", canalRascunho: "",
  ti: null,
  central: null, centralDias: 1,
  estrategia: null, abaEstrategia: "prioridades", filtroAndarEst: "", boasPraticas: null, editandoItem: null,
};

const STATUS = {
  sucesso: ["Aprovado", "sucesso", "ok"],
  reprovado: ["Reprovado", "perigo", "x"],
  adiado: ["Adiado", "alerta", "relogio"],
};
const etiquetaStatus = (s) => { const [t, c, i] = STATUS[s] || [s, "", "info"]; return `<span class="etiqueta ${c}">${icone(i)}${esc(t)}</span>`; };

// ------------------------------------------------------------------ navegação
const PAGINAS = {
  inicio: { titulo: "Visão geral", render: renderInicio },
  reprovados: { titulo: "Reprovados", render: renderReprovados, carregar: carregarReprovados },
  historico: { titulo: "Histórico", render: renderHistorico, carregar: carregarHistorico },
  testar: { titulo: "Testar planilha", render: renderTestar },
  banco: { titulo: "Banco de dados", render: renderBanco, carregar: carregarBanco },
  consultas: { titulo: "Consultas SQL", render: renderConsultas, carregar: carregarConsultas },
  agentes: { titulo: "Equipe e contratações", render: renderAgentes, carregar: carregarAgentes },
  atividade: { titulo: "Atividade", render: renderAtividade },
  canal: { titulo: "Canal da equipe", render: renderCanal, carregar: carregarCanal },
  ti: { titulo: "TI e segurança", render: renderTI, carregar: carregarTI },
  central: { titulo: "Central de dados", render: renderCentral, carregar: carregarCentral },
  estrategia: { titulo: "Estratégia", render: renderEstrategia, carregar: carregarEstrategia },
  configuracoes: { titulo: "Configurações", render: renderConfig, carregar: carregarConfig },
};

async function irPara(pagina) {
  if (!PAGINAS[pagina]) pagina = "inicio";
  E.pagina = pagina;
  fecharGaveta();
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("ativo", a.dataset.pagina === pagina));
  document.title = `${PAGINAS[pagina].titulo} · Robô de Planilhas`;
  desenhar();
  if (PAGINAS[pagina].carregar) { await PAGINAS[pagina].carregar(); desenhar(); }
  $("#conteudo").scrollTop = 0;
}

function desenhar() {
  const alvo = $("#conteudo");
  if (!E.geral) { alvo.innerHTML = `<div class="carregando">Conectando ao robô…</div>`; return; }
  if (E.geral.erro_config && E.pagina !== "atividade") { alvo.innerHTML = renderBoasVindas(); return; }
  alvo.innerHTML = `<div class="pagina">${PAGINAS[E.pagina].render()}</div>`;
  if (E.pagina === "atividade") rolarLog();
  if (E.pagina === "canal") { const m = $("#mensagens"); if (m) m.scrollTop = m.scrollHeight; }
}

const cabecalho = (titulo, subtitulo, acoes = "") =>
  `<div class="cabecalho"><div><h1>${esc(titulo)}</h1><p>${subtitulo}</p></div><div class="acoes">${acoes}</div></div>`;

// ------------------------------------------------------------------ atualização periódica
async function atualizarEstado() {
  try {
    const anterior = E.geral;
    E.geral = await api("/api/estado");
    atualizarLateral();
    if (!anterior || Boolean(anterior.erro_config) !== Boolean(E.geral.erro_config)) return desenhar();
    if (E.pagina === "inicio") desenharSemPerderFoco();
    const k = E.geral.kpis || {};
    const assRep = `${k.reprovados_pendentes}`;
    if (E.pagina === "reprovados" && assRep !== E.assinaturaRep) { await carregarReprovados(); desenhar(); }
    const assHist = (E.geral.recentes || [])[0]?.id || "";
    if (E.pagina === "historico" && assHist !== E.assinaturaHist) { await carregarHistorico(); desenharSemPerderFoco(); }
  } catch (e) {
    E.geral = E.geral && { ...E.geral, desconectado: true };
    atualizarLateral(e.message);
  }
}

function desenharSemPerderFoco() {
  const ativo = document.activeElement;
  if (ativo && ["INPUT", "SELECT", "TEXTAREA"].includes(ativo.tagName) && $("#conteudo").contains(ativo)) {
    if (E.pagina === "historico") { const corpo = $("#corpo-historico"); if (corpo) corpo.innerHTML = linhasHistorico(); }
    return;
  }
  desenhar();
}

function atualizarLateral(erro) {
  const g = E.geral || {};
  const ponto = $("#ponto-status"), texto = $("#texto-status"), sub = $("#subtexto-status");
  ponto.className = "ponto";
  if (erro || g.desconectado) { ponto.classList.add("erro"); texto.textContent = "Sem conexão"; sub.textContent = "O aplicativo foi encerrado"; }
  else if (g.erro_config) { ponto.classList.add("erro"); texto.textContent = "Configuração pendente"; sub.textContent = "Escolha a pasta de entrada"; }
  else if (g.ligado) {
    ponto.classList.add("ligado");
    texto.textContent = g.processando ? "Processando…" : "Monitorando";
    sub.textContent = g.processando ? g.processando : `Verificado ${relativo(g.ultimo_ciclo)}`;
  } else { ponto.classList.add("pausado"); texto.textContent = "Pausado"; sub.textContent = "Arquivos novos vão aguardar"; }
  const n = g.kpis?.reprovados_pendentes || 0;
  const badge = $("#badge-reprovados");
  badge.hidden = !n; badge.textContent = n;
}

// ------------------------------------------------------------------ primeira configuração
function renderBoasVindas() {
  return `<div class="boas-vindas cartao"><div class="cartao-corpo">
    <img src="robo.svg" width="48" height="48" alt="">
    <h1>Vamos conectar suas pastas</h1>
    <p class="muted">Não encontrei a pasta <b>Bases-Limpeza</b> automaticamente. Informe onde ela está e o robô cria as demais pastas ao lado dela.</p>
    <div class="erro-caixa">${esc(E.geral.erro_config)}</div>
    <ol>
      <li>Abra o <b>Explorador de Arquivos</b> e encontre a pasta <b>Bases-Limpeza</b> no seu OneDrive.</li>
      <li>Clique nela com o <b>botão direito</b> → <b>Copiar como caminho</b>.</li>
      <li>Cole abaixo (Ctrl+V) e clique em <b>Salvar e começar</b>.</li>
    </ol>
    <div class="form"><label class="inteiro">Caminho da pasta Bases-Limpeza
      <input type="text" id="campo-entrada" placeholder="C:\\Users\\voce\\OneDrive\\Bases-Limpeza"></label></div>
    <div class="acoes"><button class="btn primario" data-acao="salvar-entrada">${icone("ok")}Salvar e começar</button></div>
  </div></div>`;
}

// ------------------------------------------------------------------ visão geral
const ESTADO_FILA = {
  detectado: ["Detectado", "info", "info"],
  aguardando: ["Aguardando sincronização", "info", "relogio"],
  em_uso: ["Aberto em outro programa", "alerta", "alerta"],
  processando: ["Processando", "info", "girar"],
  adiado: ["Adiado", "alerta", "relogio"],
};

function renderInicio() {
  const g = E.geral, k = g.kpis || {}, p = g.pastas || {};
  const ligado = g.ligado;
  const heroi = `<section class="cartao heroi ${ligado ? "" : "pausado"}">
    <div class="heroi-status">
      <div class="heroi-icone">${icone(ligado ? "robo" : "pausa")}</div>
      <div><h2>${ligado ? (g.processando ? `Processando ${esc(g.processando)}` : "Monitorando Bases-Limpeza") : "Robô pausado"}</h2>
      <p>${ligado ? `Verificado ${relativo(g.ultimo_ciclo)} · solte planilhas na pasta ou arraste para esta janela`
        : "Arquivos colocados em Bases-Limpeza vão aguardar até você ligar o robô."}</p></div>
    </div>
    <div class="acoes">
      <button class="btn" data-acao="processar-agora" title="Processa já o que está na fila, sem esperar">${icone("raio")}Processar agora</button>
      ${ligado ? `<button class="btn" data-acao="pausar">${icone("pausa")}Pausar</button>`
        : `<button class="btn primario" data-acao="ligar">${icone("play")}Ligar robô</button>`}
    </div></section>`;

  const kpis = `<section class="grade kpis">
    <div class="cartao kpi"><span class="kpi-rotulo">${icone("ok")}Aprovados hoje</span><span class="kpi-valor">${num(k.hoje_sucesso)}</span>
      <span class="kpi-rodape">${k.hoje_reprovado ? `${num(k.hoje_reprovado)} reprovado(s) hoje` : "nenhum reprovado hoje"}</span></div>
    <div class="cartao kpi"><span class="kpi-rotulo">${icone("planilha")}Linhas tratadas hoje</span><span class="kpi-valor">${num(k.hoje_linhas)}</span>
      <span class="kpi-rodape">nos arquivos aprovados</span></div>
    <div class="cartao kpi"><span class="kpi-rotulo">${icone("atividade")}Taxa de aprovação</span>
      <span class="kpi-valor">${k.taxa_aprovacao_30d == null ? "—" : `${k.taxa_aprovacao_30d}%`}</span>
      <span class="kpi-rodape">${k.total_30d ? `${num(k.total_30d)} arquivo(s) nos últimos 30 dias` : "ainda sem processamentos"}</span></div>
    <div class="cartao kpi ${k.reprovados_pendentes ? "perigo" : ""}" ${k.reprovados_pendentes ? 'data-acao="ir" data-pagina="reprovados"' : ""}>
      <span class="kpi-rotulo">${icone("alerta")}Aguardando correção</span><span class="kpi-valor">${num(k.reprovados_pendentes)}</span>
      <span class="kpi-rodape">${k.reprovados_pendentes ? "clique para ver o que corrigir →" : "nenhuma pendência"}</span></div>
  </section>`;

  const fila = g.fila || [];
  const cartaoFila = `<section class="cartao">
    <div class="cartao-cab"><h2>Na fila agora</h2><span class="muted">${fila.length ? `${fila.length} arquivo(s) em Bases-Limpeza` : ""}</span></div>
    ${fila.length ? `<ul class="lista" style="margin-top:8px">${fila.map((f) => {
      const [t, c, i] = ESTADO_FILA[f.estado] || [f.estado, "", "info"];
      const extra = f.estado === "aguardando" && f.segundos != null ? ` · ${f.segundos}s` : "";
      return `<li><div class="icone-arquivo ${c}">${icone("planilha")}</div>
        <div class="principal"><strong>${esc(f.nome)}</strong><small>${tamanho(f.tamanho)}${f.motivo ? ` · ${esc(f.motivo)}` : ""}</small></div>
        <span class="etiqueta ${c}">${icone(i, f.estado === "processando" ? "girando" : "")}${t}${extra}</span></li>`;
    }).join("")}</ul>` : `<div class="cartao-corpo">
      <div class="dropzone compacta" data-acao="escolher-arquivo" data-modo="enviar">
        <strong>Nenhum arquivo aguardando</strong>
        <span class="muted">Arraste planilhas para esta janela ou clique para escolher</span></div></div>`}
  </section>`;

  const recentes = g.recentes || [];
  const cartaoRecentes = `<section class="cartao">
    <div class="cartao-cab"><h2>Últimos processamentos</h2><a href="#historico" class="muted">Ver histórico →</a></div>
    ${recentes.length ? `<ul class="lista" style="margin-top:8px">${recentes.map((h) => {
      const c = STATUS[h.status]?.[1] || "";
      return `<li class="clicavel" data-acao="ver-execucao" data-id="${esc(h.id)}">
        <div class="icone-arquivo ${c}">${icone(STATUS[h.status]?.[2] || "planilha")}</div>
        <div class="principal"><strong>${esc(h.arquivo)}</strong>
        <small>${dataCurta(h.data_hora)} · ${h.status === "sucesso" ? `${num(h.linhas_saida)} linhas` : `${num(h.erros)} erro(s)`}${Number(h.avisos) ? ` · ${num(h.avisos)} aviso(s)` : ""}</small></div>
        ${etiquetaStatus(h.status)}</li>`;
    }).join("")}</ul>` : `<div class="vazio"><strong>Nada processado ainda</strong>Assim que uma planilha chegar, ela aparece aqui.</div>`}
  </section>`;

  const no = (alvo, rotulo, info, classe = "") => `<button class="fluxo-no ${classe}" data-acao="abrir" data-alvo="${alvo}" title="Abrir pasta">
    <strong>${icone("pasta")}${rotulo}</strong><small>${info}</small></button>`;
  const fluxo = `<section class="cartao">
    <div class="cartao-cab"><h2>Fluxo das pastas</h2><span class="muted">Clique numa pasta para abrir no Explorador</span></div>
    <div class="fluxo">
      ${no("entrada", "Bases-Limpeza", `${num(p.entrada?.qtd)} aguardando`)}
      <span class="fluxo-seta">${icone("seta")}</span>
      <div class="fluxo-no robo"><strong>${icone("robo")}Robô</strong><small>limpa · valida · modela${g.banco_habilitado ? " · PostgreSQL" : ""}</small></div>
      <span class="fluxo-seta">${icone("seta")}</span>
      <div class="fluxo-saidas">
        ${no("tratadas", "Bases-Tratadas", `${num(p.tratadas?.qtd)} arquivo(s) prontos`, "ok")}
        ${no("erros", "Bases-Erros", `${num(p.erros?.qtd)} para corrigir`, (p.erros?.qtd ? "erro" : ""))}
      </div>
    </div></section>`;

  return cabecalho("Visão geral", "Acompanhe o robô e o que está acontecendo com suas planilhas.") + heroi + kpis +
    `<div class="grade duas">${cartaoFila}${cartaoRecentes}</div>` + fluxo;
}

// ------------------------------------------------------------------ reprovados
async function carregarReprovados() {
  try {
    E.reprovados = (await api("/api/reprovados")).itens;
    E.assinaturaRep = `${E.reprovados.length}`;
  } catch (e) { avisar(e.message, "erro"); }
}

function blocoOcorrencias(lista, { mostrarInfo = true } = {}) {
  const erros = lista.filter((o) => o.nivel === "ERRO"), avisos = lista.filter((o) => o.nivel === "AVISO"), info = lista.filter((o) => o.nivel === "INFO");
  const item = (o, classe) => `<div class="ocorrencia ${classe}"><div class="principal">
      <strong>${esc(o.mensagem)}</strong>
      ${((o.tabela && o.tabela !== "dados") || o.coluna || o.quantidade != null) ? `<div class="local">${[o.coluna && `Coluna: ${esc(o.coluna)}`, o.tabela && o.tabela !== "dados" && `Tabela: ${esc(o.tabela)}`, o.quantidade != null && `Ocorrências: ${num(o.quantidade)}`].filter(Boolean).join(" · ")}</div>` : ""}
      ${(o.exemplos || []).length ? `<div class="exemplos">${o.exemplos.map((x) => `<span>${esc(x)}</span>`).join("")}</div>` : ""}
    </div></div>`;
  let html = "";
  if (erros.length) html += `<div><div class="secao-titulo">Erros — impedem a publicação (${erros.length})</div><div class="ocorrencias">${erros.map((o) => item(o, "erro")).join("")}</div></div>`;
  if (avisos.length) html += `<div><div class="secao-titulo">Avisos (${avisos.length})</div><div class="ocorrencias">${avisos.map((o) => item(o, "aviso")).join("")}</div></div>`;
  if (mostrarInfo && info.length) html += `<details class="etapas"><summary>Etapas executadas (${info.length})</summary><div class="ocorrencias">${info.map((o) => item(o, "info")).join("")}</div></details>`;
  return html || `<p class="muted">Nenhuma ocorrência.</p>`;
}

function renderReprovados() {
  const itens = E.reprovados;
  const passos = `<section class="passos">
    <div class="passo"><b>1</b><div><strong>Abra no Excel</strong><small>Botão “Abrir planilha”</small></div></div>
    <div class="passo"><b>2</b><div><strong>Corrija</strong><small>As linhas indicadas abaixo</small></div></div>
    <div class="passo"><b>3</b><div><strong>Salve e feche</strong><small>Ctrl+S e feche o Excel</small></div></div>
    <div class="passo"><b>4</b><div><strong>Reprocesse</strong><small>Botão “Já corrigi”</small></div></div></section>`;
  let corpo;
  if (itens === null) corpo = `<div class="carregando">Carregando…</div>`;
  else if (!itens.length) corpo = `<section class="cartao"><div class="vazio"><div class="icone-grande sucesso">${icone("ok")}</div>
      <strong>Nenhum arquivo aguardando correção</strong>Tudo o que chegou foi aprovado ou já foi resolvido.</div></section>`;
  else corpo = itens.map((r) => `<section class="cartao reprovado">
      <div class="reprovado-topo">
        <div class="icone-arquivo perigo">${icone("planilha")}</div>
        <div class="principal"><strong>${esc(r.original)}</strong><div class="muted">Reprovado ${dataCurta(r.data)} · ${num((r.erros || []).length)} tipo(s) de erro</div></div>
        <div class="acoes">
          <button class="btn" data-acao="abrir" data-alvo="reprovado" data-nome="${esc(r.nome)}">${icone("abrir")}Abrir planilha</button>
          <button class="btn primario" data-acao="reprocessar" data-nome="${esc(r.nome)}">${icone("recarregar")}Já corrigi — reprocessar</button>
          <button class="btn fantasma" data-acao="descartar" data-nome="${esc(r.nome)}" title="Tirar da lista sem processar">${icone("lixeira")}</button>
        </div>
      </div>
      ${r.texto !== undefined && !(r.erros || []).length ? `<pre class="mono" style="white-space:pre-wrap;margin:0">${esc(r.texto)}</pre>` : blocoOcorrencias([...(r.erros || []), ...(r.avisos || [])], { mostrarInfo: false })}
    </section>`).join("");
  return cabecalho("Reprovados", "Arquivos que não foram publicados porque têm erros. Nada deles chegou em Bases-Tratadas ou no banco.",
    `<button class="btn" data-acao="abrir" data-alvo="erros">${icone("pasta")}Abrir Bases-Erros</button>`) +
    (itens && itens.length ? passos : "") + corpo;
}

// ------------------------------------------------------------------ histórico
async function carregarHistorico() {
  try {
    E.historico = (await api("/api/historico?limite=1000")).itens;
    E.assinaturaHist = E.historico[0]?.id || "";
  } catch (e) { avisar(e.message, "erro"); }
}

function linhasHistorico() {
  const busca = E.busca.trim().toLowerCase();
  const itens = E.historico.filter((h) => (E.filtro === "todos" || h.status === E.filtro) && (!busca || (h.arquivo || "").toLowerCase().includes(busca)));
  if (!itens.length) return `<tr><td colspan="7"><div class="vazio"><strong>Nenhum processamento encontrado</strong>${E.historico.length ? "Ajuste o filtro ou a busca." : "Os arquivos processados aparecem aqui."}</div></td></tr>`;
  return itens.map((h) => `<tr class="clicavel" data-acao="ver-execucao" data-id="${esc(h.id)}">
    <td class="num">${dataCurta(h.data_hora)}</td>
    <td class="arquivo" title="${esc(h.arquivo)}">${esc(h.arquivo)}</td>
    <td>${etiquetaStatus(h.status)}</td>
    <td class="direita num">${num(h.linhas_entrada)} → ${num(h.linhas_saida)}</td>
    <td class="direita num">${Number(h.erros) ? `<span class="etiqueta perigo">${num(h.erros)}</span>` : "0"}</td>
    <td class="direita num">${Number(h.avisos) ? `<span class="etiqueta alerta">${num(h.avisos)}</span>` : "0"}</td>
    <td class="direita num">${duracao(h.duracao_seg)}</td></tr>`).join("");
}

function renderHistorico() {
  const filtros = [["todos", "Todos"], ["sucesso", "Aprovados"], ["reprovado", "Reprovados"]];
  return cabecalho("Histórico", "Todos os processamentos. Clique numa linha para ver o detalhe completo.",
    `<button class="btn" data-acao="abrir" data-alvo="logs" title="O arquivo historico_processamentos.csv pode ser aberto no Excel ou Power BI">${icone("pasta")}Abrir pasta de logs</button>`) +
    `<section class="cartao">
      <div class="barra">
        <div class="segmentado">${filtros.map(([v, t]) => `<button class="${E.filtro === v ? "ativo" : ""}" data-acao="filtro" data-valor="${v}">${t}</button>`).join("")}</div>
        <label class="campo-busca">${icone("busca")}<input type="text" id="busca-historico" placeholder="Buscar arquivo…" value="${esc(E.busca)}"></label>
        <span class="muted" style="margin-left:auto">${num(E.historico.length)} registro(s)</span>
      </div>
      <div class="tabela-envoltorio"><table class="tabela">
        <thead><tr><th>Data</th><th>Arquivo</th><th>Status</th><th class="direita">Linhas (entrada → saída)</th><th class="direita">Erros</th><th class="direita">Avisos</th><th class="direita">Duração</th></tr></thead>
        <tbody id="corpo-historico">${linhasHistorico()}</tbody></table></div>
    </section>`;
}

// ------------------------------------------------------------------ gaveta de detalhes
function abrirGaveta(html) {
  const g = $("#gaveta");
  g.innerHTML = html; g.classList.add("aberta"); g.setAttribute("aria-hidden", "false");
  $("#gaveta-fundo").hidden = false;
}
function fecharGaveta() {
  const g = $("#gaveta");
  g.classList.remove("aberta", "larga");
  E.editando = null; g.setAttribute("aria-hidden", "true");
  $("#gaveta-fundo").hidden = true;
}

async function verExecucao(id) {
  if (!id) return avisar("Este registro é de uma versão antiga e não tem detalhes.", "erro");
  abrirGaveta(`<div class="carregando">Carregando…</div>`);
  try {
    const d = await api(`/api/execucao?id=${encodeURIComponent(id)}`);
    const erros = (d.ocorrencias || []).filter((o) => o.nivel === "ERRO").length;
    const avisos = (d.ocorrencias || []).filter((o) => o.nivel === "AVISO").length;
    const nomeArq = (c) => c.split(/[\\/]/).pop();
    const destinos = [
      ...(d.saidas || []).map((c) => `<li><div class="icone-arquivo ${d.status === "sucesso" ? "sucesso" : "perigo"}">${icone("planilha")}</div>
        <div class="principal"><strong>${esc(nomeArq(c))}</strong><small>${d.status === "sucesso" ? "Bases-Tratadas" : "Relatório de erros"}</small></div>
        <button class="btn pequeno" data-acao="abrir" data-alvo="arquivo" data-caminho="${esc(c)}">${icone("abrir")}Abrir</button></li>`),
      ...(d.tabelas_banco || []).map((t) => `<li><div class="icone-arquivo info">${icone("banco")}</div>
        <div class="principal"><strong class="mono">${esc(t)}</strong><small>PostgreSQL</small></div></li>`),
      d.original ? `<li><div class="icone-arquivo">${icone("planilha")}</div><div class="principal"><strong>${esc(nomeArq(d.original))}</strong>
        <small>Original guardado em ${d.status === "sucesso" ? "Bases-Originais" : "Bases-Erros"}</small></div>
        <button class="btn pequeno" data-acao="abrir" data-alvo="arquivo" data-caminho="${esc(d.original)}">${icone("abrir")}Abrir</button></li>` : "",
    ].join("");
    abrirGaveta(`<div class="gaveta-cab">
        <div style="flex:1"><div class="muted">${dataCurta(d.data_hora)}</div><h2>${esc(d.arquivo)}</h2><div style="margin-top:6px">${etiquetaStatus(d.status)}</div></div>
        <button class="btn fantasma" data-acao="fechar-gaveta" aria-label="Fechar">${icone("x")}</button></div>
      <div class="gaveta-corpo">
        <div class="metricas">
          <div class="metrica"><small>Linhas lidas</small><strong>${num(d.linhas_entrada)}</strong></div>
          <div class="metrica"><small>Linhas publicadas</small><strong>${num(d.linhas_saida)}</strong></div>
          <div class="metrica"><small>Erros / avisos</small><strong>${erros} / ${avisos}</strong></div>
          <div class="metrica"><small>Duração</small><strong>${duracao(d.duracao_seg)}</strong></div>
        </div>
        ${destinos ? `<div><div class="secao-titulo">Arquivos e destinos</div><ul class="lista cartao">${destinos}</ul></div>` : ""}
        ${(d.tabelas || []).map((t) => `<div><div class="secao-titulo">Tabela ${esc(t.nome)} · ${num(t.linhas)} linhas</div>
          <div class="chips-colunas">${t.colunas.map((c) => `<span class="chip-coluna">${esc(c.nome)} <em>${esc(c.tipo)}</em></span>`).join("")}</div></div>`).join("")}
        ${blocoOcorrencias(d.ocorrencias || [])}
      </div>`);
  } catch (e) { fecharGaveta(); avisar(e.message, "erro"); }
}

// ------------------------------------------------------------------ testar planilha
function renderTestar() {
  const t = E.teste;
  let resultado = "";
  if (t === "carregando") resultado = `<div class="carregando">${icone("girar", "girando")} Analisando ${esc(E.arquivoTeste?.name || "")}…</div>`;
  else if (t) {
    const erros = t.ocorrencias.filter((o) => o.nivel === "ERRO").length, avisos = t.ocorrencias.filter((o) => o.nivel === "AVISO").length;
    const tab = t.tabelas[E.abaTeste] || t.tabelas[0];
    resultado = `<div class="veredito ${t.aprovado ? "sucesso" : "perigo"}">
        <div class="heroi-icone">${icone(t.aprovado ? "ok" : "alerta")}</div>
        <div><h2>${t.aprovado ? "Seria aprovada" : "Seria reprovada"} — ${esc(t.arquivo)}</h2>
        <p>${num(t.linhas_entrada)} linhas lidas → ${num(t.linhas_saida)} linhas tratadas · ${erros} erro(s), ${avisos} aviso(s) · ${t.regra ? `regra “${esc(t.regra)}”` : "sem regra específica"}</p></div>
        <div class="acoes">
          <button class="btn" data-acao="escolher-arquivo" data-modo="testar">${icone("frasco")}Testar outra</button>
          <button class="btn ${t.aprovado ? "primario" : ""}" data-acao="enviar-testado">${icone("enviar")}${t.aprovado ? "Enviar para processamento" : "Enviar mesmo assim"}</button>
        </div></div>
      <section class="cartao"><div class="cartao-cab"><h2>Ocorrências</h2></div><div class="cartao-corpo">${blocoOcorrencias(t.ocorrencias)}</div></section>
      ${tab ? `<section class="cartao">
        <div class="cartao-cab"><h2>Prévia do resultado</h2><span class="muted">primeiras ${Math.min(25, tab.linhas)} de ${num(tab.linhas)} linhas</span></div>
        ${t.tabelas.length > 1 ? `<div class="abas" style="margin-top:12px">${t.tabelas.map((x, i) => `<button class="${i === E.abaTeste ? "ativo" : ""}" data-acao="aba-teste" data-i="${i}">${esc(x.nome)}</button>`).join("")}</div>` : ""}
        <div class="cartao-corpo"><div class="chips-colunas">${tab.colunas.map((c) => `<span class="chip-coluna">${esc(c.nome)} <em>${esc(c.tipo)}${c.vazios ? ` · ${num(c.vazios)} vazios` : ""}</em></span>`).join("")}</div></div>
        <div class="tabela-envoltorio" style="border-top:1px solid var(--borda)"><table class="tabela compacta">
          <thead><tr>${tab.colunas.map((c) => `<th>${esc(c.nome)}</th>`).join("")}</tr></thead>
          <tbody>${tab.amostra.map((l) => `<tr>${l.map((v) => `<td>${esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
      </section>` : ""}`;
  }
  return cabecalho("Testar planilha", "Veja exatamente o que o robô faria com um arquivo — sem gravar, mover ou carregar nada.") +
    (t && t !== "carregando" ? "" : `<div class="dropzone" data-acao="escolher-arquivo" data-modo="testar">
      <div class="icone-grande">${icone("frasco")}</div>
      <strong>Arraste uma planilha aqui ou clique para escolher</strong>
      <span class="muted">.xlsx, .xlsm, .xls, .csv ou .txt — o arquivo original não é alterado</span></div>`) + resultado;
}

async function testarArquivo(arquivo) {
  E.arquivoTeste = arquivo; E.teste = "carregando"; E.abaTeste = 0;
  if (E.pagina !== "testar") location.hash = "#testar"; else desenhar();
  try { E.teste = await api("/api/testar", { arquivo }); }
  catch (e) { E.teste = null; avisar(e.message, "erro"); }
  if (E.pagina === "testar") desenhar();
}

async function enviarArquivos(arquivos) {
  for (const arquivo of arquivos) {
    try { await api("/api/enviar", { arquivo }); avisar(`${arquivo.name} enviado para Bases-Limpeza`, "sucesso"); }
    catch (e) { avisar(`${arquivo.name}: ${e.message}`, "erro"); }
  }
  atualizarEstado();
}

// ------------------------------------------------------------------ banco de dados
async function carregarBanco() {
  E.banco = null;
  if (!E.geral?.banco_habilitado) return;
  try { E.banco = await api("/api/banco/resumo"); } catch (e) { E.banco = { ok: false, mensagem: e.message }; }
}

const CAMADAS = [
  ["bruto", "Bruto", "Tudo o que chegou, como veio — inclusive reprovados", "#98a2b3"],
  ["tratado", "Tratado", "Limpo, validado e com tipos corretos", "#2654d9"],
  ["analitico", "Analítico", "Suas regras de negócio em SQL", "#0f7b55"],
];

function renderBanco() {
  const g = E.geral;
  const explicacao = `<section class="cartao"><div class="cartao-cab"><h2>Como o ELT funciona aqui</h2></div><div class="cartao-corpo">
    <div class="camadas">${CAMADAS.map(([, nome, desc, cor]) => `<div class="camada"><header><strong><span class="marca-camada" style="background:${cor}"></span>${nome}</strong><small>${desc}</small></header></div>`).join("")}</div>
    <p class="muted" style="margin:14px 0 0">Todo arquivo que chega fica guardado em <b>bruto</b> (auditoria). Só os <b>aprovados</b> entram em <b>tratado</b>, numa única transação: entram inteiros ou não entra nada.
    Depois, os arquivos <code>.sql</code> da pasta <b>modelos_sql</b> criam a camada <b>analítica</b> dentro do banco — o “T” do ELT.</p></div></section>`;
  if (!g.banco_habilitado) {
    return cabecalho("Banco de dados", "Carga automática em PostgreSQL (opcional).") + `<section class="cartao heroi pausado">
      <div class="heroi-status"><div class="heroi-icone">${icone("banco")}</div>
      <div><h2>PostgreSQL desligado</h2><p>Hoje o robô publica apenas arquivos em Bases-Tratadas. Ligue o banco para ter histórico acumulado e consultas SQL.</p></div></div>
      <div class="acoes"><a class="btn primario" href="#configuracoes">${icone("ajustes")}Configurar banco</a></div></section>` + explicacao;
  }
  const b = E.banco;
  const acoes = `<button class="btn" data-acao="abrir" data-alvo="modelos">${icone("pasta")}Pasta de modelos SQL</button>
    <button class="btn" data-acao="executar-modelos">${icone("raio")}Executar modelos agora</button>
    <button class="btn" data-acao="atualizar-banco">${icone("recarregar")}Atualizar</button>`;
  if (!b) return cabecalho("Banco de dados", "Camadas do PostgreSQL e últimas cargas.", acoes) + `<div class="carregando">Consultando o banco…</div>`;
  if (!b.ok) return cabecalho("Banco de dados", "Camadas do PostgreSQL e últimas cargas.", acoes) +
    `<section class="cartao heroi pausado"><div class="heroi-status"><div class="heroi-icone">${icone("alerta")}</div>
      <div><h2>Sem conexão com o PostgreSQL</h2><p>${esc(b.mensagem)}</p><p>Enquanto isso, arquivos novos ficam aguardando (status “Adiado”) — nada se perde.</p></div></div>
      <div class="acoes"><a class="btn" href="#configuracoes">${icone("ajustes")}Revisar configuração</a></div></section>` + explicacao;

  const porSchema = (s) => b.tabelas.filter((t) => t.schema === s);
  const cfgB = E.config?.banco || {};
  return cabecalho("Banco de dados", "Camadas do PostgreSQL e últimas cargas.", acoes) +
    `<section class="camadas">${CAMADAS.map(([s, nome, desc, cor]) => {
      const lista = porSchema(s);
      return `<div class="camada cartao"><header><strong><span class="marca-camada" style="background:${cor}"></span>${nome} <span class="etiqueta">${lista.length}</span></strong><small>${desc}</small></header>
        <ul>${lista.length ? lista.map((t) => `<li><code title="${esc(s)}.${esc(t.nome)}">${esc(t.nome)}</code><span class="muted num">${t.tipo === "visão" ? "visão" : `${num(t.linhas)} linhas`}</span></li>`).join("")
          : `<li class="muted">vazio</li>`}</ul></div>`;
    }).join("")}</section>
    <section class="cartao"><div class="cartao-cab"><h2>Últimas cargas</h2><span class="muted">tabela robo.lotes</span></div>
      ${b.lotes.length ? `<div class="tabela-envoltorio" style="margin-top:10px"><table class="tabela">
        <thead><tr><th>Data</th><th>Arquivo</th><th>Status</th><th class="direita">Linhas</th><th>Tabelas</th></tr></thead>
        <tbody>${b.lotes.map((l) => `<tr class="clicavel" data-acao="ver-execucao" data-id="${esc(l.lote_id)}"><td class="num">${dataCurta(l.processado_em)}</td><td class="arquivo">${esc(l.arquivo)}</td>
          <td>${etiquetaStatus(l.status)}</td><td class="direita num">${num(l.linhas_saida)}</td><td class="mono muted truncar" title="${esc((l.tabelas || []).join("\n"))}">${esc((l.tabelas || []).join(", "))}</td></tr>`).join("")}</tbody></table></div>`
        : `<div class="vazio"><strong>Nenhuma carga ainda</strong>A primeira planilha aprovada aparece aqui.</div>`}
    </section>
    <div class="dica">${icone("info")}<p><b>Conectar o Power BI:</b> Página Inicial → Obter dados → <b>Banco de dados PostgreSQL</b> →
      Servidor <code>${esc(cfgB.host || "localhost")}:${esc(cfgB.porta || 5432)}</code>, Banco <code>${esc(cfgB.banco || "robo_dados")}</code>.
      Use as tabelas de <b>tratado</b> e as visões de <b>analitico</b>.</p></div>`;
}

// ------------------------------------------------------------------ agentes e habilidades
const POSICAO_TEXTO = { limpeza: "Depois da Limpeza", validacao: "Depois da Auditoria", modelagem: "Antes da Modelagem" };

async function carregarAgentes() {
  try {
    const [equipe, escritorio] = await Promise.all([api("/api/agentes"), api("/api/escritorio")]);
    E.equipe = equipe; E.organograma = escritorio.equipe || [];
  } catch (e) { avisar(e.message, "erro"); }
}

const NOME_ANDAR_PAINEL = { 1: "1º andar · Engenharia de dados", 2: "2º andar · Analytics e ciência de dados", 3: "3º andar · Sala Excel e BI",
  4: "4º andar · Operações, governança e Pessoas (RH)", 5: "5º andar · TI, DevOps e segurança" };
const ORDEM_NIVEL = ["Diretor(a)", "Head", "Gerente", "Coordenador(a)", "Especialista", "Sênior", "Pleno", "Júnior", "Estagiário"];

function renderOrganograma() {
  const gente = E.organograma || [];
  if (!gente.length) return "";
  const andares = [...new Set(gente.map((a) => Number(a.andar) || 1))].sort((a, b) => a - b);
  return `<section class="organograma"><div class="secao-titulo">Quadro de pessoal · ${gente.length} pessoas em ${andares.length} andares</div>
    ${andares.map((n) => {
      const membros = gente.filter((a) => (Number(a.andar) || 1) === n);
      const porNivel = ORDEM_NIVEL.map((nv) => [nv, membros.filter((a) => (a.ficha?.nivel || "Pleno") === nv)]).filter(([, l]) => l.length);
      return `<details class="cartao andar-org" ${n === 1 ? "open" : ""}><summary><strong>${esc(NOME_ANDAR_PAINEL[n] || `${n}º andar`)}</strong>
        <span class="muted">${membros.length} pessoas · ${porNivel.map(([nv, l]) => `${l.length} ${nv.toLowerCase()}`).join(" · ")}</span></summary>
        <div class="niveis-org">${porNivel.map(([nv, l]) => `<div class="nivel-org"><div class="nivel-nome">${esc(nv)}</div>
          ${l.map((a) => `<button class="pessoa-org" data-acao="ver-pessoa" data-id="${esc(a.id)}">${avatar(a)}<span><strong>${esc(a.nome)}</strong>
            <small>${esc(a.ficha?.cargo || a.papel)}</small>${a.ficha?.gestor ? `<small class="muted">responde a ${esc(a.ficha.gestor.split(" (")[0])}</small>` : ""}</span>
            ${a.ficha?.provas ? `<span class="etiqueta ${a.ficha.provas.aprovado ? "sucesso" : "perigo"}">${a.ficha.provas.acertos}/${a.ficha.provas.total}</span>` : ""}</button>`).join("")}
        </div>`).join("")}</div></details>`;
    }).join("")}</section>`;
}

async function abrirPessoa(id) {
  const a = (E.organograma || []).find((x) => x.id === id); if (!a) return;
  let manual = "";
  try { manual = (await api(`/api/agentes/manual?id=${encodeURIComponent(id)}`)).texto; } catch { /* sem manual */ }
  const f = a.ficha || {};
  const lista = (t, itens) => itens?.length ? `<div><div class="secao-titulo">${t}</div><ul class="lista-ficha">${itens.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : "";
  abrirGaveta(`<div class="gaveta-cab">${avatar(a)}<div style="flex:1"><div class="muted">${esc(NOME_ANDAR_PAINEL[a.andar] || "")}</div>
      <h2>${esc(a.nome)} · ${esc(f.cargo || a.papel)}</h2></div>
      <button class="btn primario" data-acao="conversar" data-id="${esc(id)}">${icone("chat")}Conversar</button>
      <button class="btn fantasma" data-acao="fechar-gaveta" aria-label="Fechar">${icone("x")}</button></div>
    <div class="gaveta-corpo">
      <div class="chips-colunas">${f.nivel ? `<span class="etiqueta info">${esc(f.nivel)}</span>` : ""}${f.area ? `<span class="etiqueta">${esc(f.area)}</span>` : ""}
        ${f.gestor ? `<span class="etiqueta">Responde a ${esc(f.gestor)}</span>` : ""}
        ${f.provas ? `<span class="etiqueta ${f.provas.aprovado ? "sucesso" : "perigo"}">Provas técnicas ${f.provas.acertos}/${f.provas.total}</span>` : ""}</div>
      <p>${esc(a.descricao || "")}</p>
      ${lista("Responsabilidades (escopo)", f.responsabilidades)}${lista("Critérios de qualidade", f.criterios)}
      ${lista("Metodologias", f.metodologias)}${lista("Limites do cargo", f.limites)}
      <div><div class="secao-titulo">Manual de procedimentos (.md)</div>
        <p class="muted" style="margin:0 0 8px">Escreva em Markdown como esta pessoa deve trabalhar. Fica em agentes/${esc(id)}.md e o canal usa para responder.</p>
        <textarea id="manual-md" class="mono" rows="14" placeholder="# Manual de ${esc(a.nome)}\n\n## Como confiro\n...">${esc(manual)}</textarea></div>
      <div class="acoes" style="justify-content:flex-end"><button class="btn primario" data-acao="salvar-manual" data-id="${esc(id)}">${icone("ok")}Salvar manual</button></div>
    </div>`);
  $("#gaveta").classList.add("larga");
}

const avatar = (a, classe = "avatar") => `<span class="${classe}" style="background:${esc(a.cor)}">${esc((a.nome || "?").slice(0, 1).toUpperCase())}</span>`;

function renderAgentes() {
  const acoes = `<button class="btn" data-acao="abrir" data-alvo="habilidades">${icone("pasta")}Habilidades em Python</button>
    <a class="btn" href="escritorio.html">${icone("cubo")}Ver no escritório 3D</a>
    <button class="btn primario" data-acao="novo-agente">${icone("mais")}Contratar</button>`;
  if (!E.equipe) return cabecalho("Equipe e contratações", "", acoes) + `<div class="carregando">Carregando…</div>`;
  const erros = E.equipe.erros_habilidades || [];
  return cabecalho("Equipe e contratações", "Todo o prédio, andar por andar, do gerente ao estagiário. Clique numa pessoa para ver a ficha e escrever o manual (.md). Para contratar, use “Novo agente”.", acoes) +
    (erros.length ? `<div class="ocorrencia erro"><div class="principal"><strong>Habilidades personalizadas com problema</strong><div class="exemplos">${erros.map((x) => `<span>${esc(x)}</span>`).join("")}</div></div></div>` : "") +
    `<div class="dica">${icone("info")}<p>A ordem abaixo é a ordem real de trabalho. Agentes nativos fazem o essencial; os seus agentes e as habilidades extras
      entram depois da <b>Limpeza</b>, depois da <b>Auditoria</b> ou antes da <b>Modelagem</b>. Qualquer habilidade que encontrar erro <b>reprova o arquivo</b> — nada sai pela metade.</p></div>
    ${renderOrganograma()}
    <div class="secao-titulo" style="margin-top:8px">Linha de produção · ordem real de trabalho</div>
    <section class="equipe">${E.equipe.agentes.map((a, i) => `<article class="cartao agente ${a.ativo ? "" : "inativo"}" data-acao="editar-agente" data-id="${esc(a.id)}">
      <span class="ordem-agente">${i + 1}º</span>
      <div class="agente-topo">${avatar(a)}<div><strong>${esc(a.nome)}</strong><small>${esc(a.papel || "")}</small></div></div>
      <p>${esc(a.descricao || "Sem descrição.")}</p>
      <div class="chips-colunas">
        ${a.nativo ? `<span class="etiqueta">nativo</span>` : `<span class="etiqueta info">${esc(POSICAO_TEXTO[a.posicao] || a.posicao)}</span>`}
        ${a.aceita_habilidades ? `<span class="etiqueta ${a.habilidades.length ? "sucesso" : ""}">${a.habilidades.length} habilidade(s)</span>` : ""}
        ${!a.nativo && (a.aplicar_em || []).join(",") !== "*" ? `<span class="etiqueta">${esc(a.aplicar_em.join(", "))}</span>` : ""}
        ${a.ficha?.nivel ? `<span class="etiqueta info">${esc(a.ficha.nivel)}</span>` : ""}
        ${!a.nativo && a.andar ? `<span class="etiqueta">${esc(a.andar)}º andar</span>` : ""}
        ${a.fim_experiencia && a.nivel === "estagiario" ? `<span class="etiqueta alerta">experiência até ${esc(dataBr(a.fim_experiencia))}</span>` : ""}
        ${a.contratado_por === "automatico" ? `<span class="etiqueta">contratado pela liderança</span>` : ""}
        ${a.ativo ? "" : `<span class="etiqueta alerta">em treinamento</span>`}
        ${(a.problemas || []).length ? `<span class="etiqueta perigo">${icone("alerta")}configuração inválida</span>` : ""}
      </div></article>`).join("")}</section>`;
}

function editorAgente() {
  const a = E.editando, cat = E.equipe.catalogo;
  const porId = Object.fromEntries(cat.map((s) => [s.id, s]));
  const campoParam = (sk, i, par, valor) => {
    const id = `p-${i}-${par.nome}`, nome = `${esc(par.rotulo)}${par.obrigatorio ? " *" : ""}`;
    const ajuda = par.ajuda ? `<small>${esc(par.ajuda).replace(/\n/g, "<br>")}</small>` : "";
    const v = valor ?? par.padrao ?? "";
    const attrs = `id="${id}" data-habilidade="${i}" data-param="${esc(par.nome)}" data-tipo="${par.tipo}"`;
    if (par.tipo === "booleano") return `<label>${nome}${ajuda}<span>${chave(Boolean(v), "alternar-local", attrs)}</span></label>`;
    if (par.tipo === "escolha") return `<label>${nome}${ajuda}<select ${attrs}>${par.opcoes.map((o) => `<option ${String(v) === String(o) ? "selected" : ""}>${esc(o)}</option>`).join("")}</select></label>`;
    if (par.tipo === "mapa") {
      const texto = typeof v === "object" ? Object.entries(v).map(([k, x]) => `${k}=${x}`).join("\n") : v;
      return `<label class="inteiro">${nome}${ajuda}<textarea ${attrs}>${esc(texto)}</textarea></label>`;
    }
    const texto = Array.isArray(v) ? v.join(", ") : v;
    const tipo = par.tipo === "numero" || par.tipo === "inteiro" ? "number" : "text";
    return `<label class="${par.tipo === "expressao" ? "inteiro" : ""}">${nome}${ajuda}<input type="${tipo}" step="any" ${attrs} value="${esc(texto)}" ${par.tipo === "expressao" ? 'class="mono"' : ""}></label>`;
  };
  const habilidadesHtml = (a.habilidades || []).map((cfgSk, i) => {
    const sk = porId[cfgSk.habilidade];
    if (!sk) return `<div class="ocorrencia erro"><div class="principal"><strong>Habilidade “${esc(cfgSk.habilidade)}” não existe no catálogo</strong></div>
      <button class="btn pequeno perigo" data-acao="remover-habilidade" data-i="${i}">${icone("lixeira")}</button></div>`;
    return `<div class="habilidade-cartao ${cfgSk.ativo === false ? "desligada" : ""}">
      <div class="habilidade-cab"><b class="contador">${i + 1}</b><div class="principal"><strong>${esc(sk.nome)}</strong><small>${esc(sk.categoria)} · ${esc(sk.descricao)}</small></div>
        ${chave(cfgSk.ativo !== false, "alternar-local", `data-habilidade-ativa="${i}" title="Ligar/desligar"`)}
        <button class="btn fantasma pequeno" data-acao="mover-habilidade" data-i="${i}" data-d="-1" title="Subir" ${i === 0 ? "disabled" : ""}>${icone("cima")}</button>
        <button class="btn fantasma pequeno" data-acao="mover-habilidade" data-i="${i}" data-d="1" title="Descer" ${i === a.habilidades.length - 1 ? "disabled" : ""}>${icone("baixo")}</button>
        <button class="btn fantasma pequeno" data-acao="remover-habilidade" data-i="${i}" title="Remover">${icone("lixeira")}</button></div>
      <div class="habilidade-corpo">
        ${sk.parametros.length ? `<div class="form">${sk.parametros.map((par) => campoParam(sk, i, par, (cfgSk.parametros || {})[par.nome])).join("")}</div>` : `<p class="muted">Sem parâmetros.</p>`}
        ${sk.conhecimento ? `<details class="conhecimento"><summary>Conhecimento: quando usar e cuidados</summary><pre>${esc(sk.conhecimento)}</pre></details>` : ""}
      </div></div>`;
  }).join("");

  const busca = E.buscaHabilidade.trim().toLowerCase();
  let grupo = "";
  const catalogoHtml = cat.filter((s) => !busca || `${s.nome} ${s.descricao} ${s.categoria}`.toLowerCase().includes(busca)).map((s) => {
    let h = "";
    if (s.categoria !== grupo) { grupo = s.categoria; h += `<div class="grupo">${esc(grupo)}</div>`; }
    return h + `<button data-acao="adicionar-habilidade" data-habilidade="${esc(s.id)}"><strong>${esc(s.nome)}</strong><small>${esc(s.descricao)}</small></button>`;
  }).join("");

  const nativoInfo = a.nativo ? `<p class="muted" style="margin:0">${esc(a.descricao)}</p>` : `
    <div class="form">
      <label>Nome<input type="text" id="ag-nome" value="${esc(a.nome)}" placeholder="Ex.: Tina"></label>
      <label>Função<input type="text" id="ag-papel" value="${esc(a.papel)}" placeholder="Ex.: Contatos e LGPD"></label>
      <label class="inteiro">O que faz<input type="text" id="ag-descricao" value="${esc(a.descricao)}" placeholder="Uma frase para a equipe entender o papel dele"></label>
      <label>Quando trabalha<select id="ag-posicao">${E.equipe.posicoes.map((p) => `<option value="${p}" ${a.posicao === p ? "selected" : ""}>${POSICAO_TEXTO[p]}</option>`).join("")}</select></label>
      <label>Ordem (menor trabalha antes)<input type="number" id="ag-ordem" value="${esc(a.ordem ?? 50)}"></label>
      <label>Arquivos que ele trata<input type="text" id="ag-aplicar" value="${esc((a.aplicar_em || ["*"]).join(", "))}"><small>* = todos · nps_* = só os que começam com nps_</small></label>
      <label>Cor no escritório<input type="color" id="ag-cor" value="${esc(a.cor || "#64748b")}"></label>
      <label>Nível<select id="ag-nivel">${(E.equipe.rh?.niveis || []).map((n) => `<option value="${n.id}" ${(a.nivel || "pleno") === n.id ? "selected" : ""}>${esc(n.nome)} (risco até ${esc(n.risco_maximo)})</option>`).join("")}</select>
        <small>Estagiário só observa (não altera dados) e tem 3 meses de experiência.</small></label>
      <label>Andar<input type="number" id="ag-andar" min="1" max="9" value="${esc(a.andar || 1)}"><small>Um andar novo aparece no prédio sozinho.</small></label>
      <label>Cargo<input type="text" id="ag-cargo" value="${esc(a.cargo || "")}" placeholder="Ex.: Analista de Dados Júnior — Contatos"></label>
      <label>Área<select id="ag-area">${(E.equipe.rh?.areas || []).map((x) => `<option ${a.area === x ? "selected" : ""}>${esc(x)}</option>`).join("")}</select></label>
      <label>Mentor (quem revisa o trabalho)<select id="ag-mentor"><option value="">—</option>${(E.organograma || []).filter((x) => ["Sênior", "Especialista", "Coordenador(a)"].includes(x.ficha?.nivel)).map((x) => `<option value="${esc(x.id)}" ${a.mentor === x.id ? "selected" : ""}>${esc(x.nome)} · ${esc(x.ficha?.cargo || x.papel)}</option>`).join("")}</select></label>
      <label class="inteiro">Manual de procedimentos (.md)<textarea id="ag-manual" class="mono" rows="6" placeholder="# Como trabalho\n...">${esc(a.manual || "")}</textarea></label>
    </div>
    <div class="opcao"><div><strong>Agente ligado</strong><small>Desligado, ele não trabalha (mas a configuração fica guardada).</small></div>${chave(a.ativo !== false, "alternar-local", 'id="ag-ativo"')}</div>`;

  return `<div class="gaveta-cab">${avatar(a, "avatar")}
      <div style="flex:1"><div class="muted">${a.nativo ? "Agente nativo" : a.id ? "Agente personalizado" : "Novo agente"}</div><h2>${esc(a.nome || "Novo agente")}${a.papel ? ` · ${esc(a.papel)}` : ""}</h2></div>
      <button class="btn fantasma" data-acao="fechar-gaveta" aria-label="Fechar">${icone("x")}</button></div>
    <div class="gaveta-corpo">
      ${(a.problemas || []).length ? `<div class="ocorrencia erro"><div class="principal"><strong>Configuração inválida</strong><div class="exemplos">${a.problemas.map((x) => `<span>${esc(x)}</span>`).join("")}</div></div></div>` : ""}
      ${nativoInfo}
      ${a.aceita_habilidades === false ? `<div class="dica">${icone("info")}<p>Este agente faz uma tarefa de infraestrutura (ler, carregar ou arquivar) e não usa habilidades de dados.</p></div>` : `
      <div><div class="secao-titulo">Habilidades — executadas de cima para baixo</div>
        <div style="display:flex;flex-direction:column;gap:10px">${habilidadesHtml || `<p class="muted">Nenhuma habilidade ainda. Adicione do catálogo abaixo.</p>`}</div></div>
      <div><div class="secao-titulo">Catálogo de habilidades (${cat.length})</div>
        ${E.catalogoAberto ? `<label class="campo-busca" style="max-width:none;margin-bottom:10px">${icone("busca")}<input type="text" id="busca-habilidade" placeholder="Buscar habilidade…" value="${esc(E.buscaHabilidade)}"></label>
          <div class="catalogo" id="catalogo-habilidades">${catalogoHtml}</div>`
        : `<button class="btn" data-acao="abrir-catalogo">${icone("mais")}Adicionar habilidade</button>`}</div>`}
      <div class="acoes" style="justify-content:space-between;border-top:1px solid var(--borda);padding-top:16px">
        <div>${!a.nativo && a.id && E.equipe.agentes.some((x) => x.id === a.id) ? `<button class="btn perigo" data-acao="excluir-agente">${icone("lixeira")}Excluir agente</button>` : ""}</div>
        <div class="acoes"><button class="btn" data-acao="fechar-gaveta">Cancelar</button>
        ${a.aceita_habilidades === false ? "" : `<button class="btn primario" data-acao="salvar-agente">${icone("ok")}Salvar agente</button>`}</div>
      </div>
    </div>`;
}

function coletarEditor() {
  const a = E.editando; if (!a) return;
  const ler = (id) => $(`#${id}`);
  if (!a.nativo && ler("ag-nome")) {
    a.nome = ler("ag-nome").value.trim(); a.papel = ler("ag-papel").value.trim(); a.descricao = ler("ag-descricao").value.trim();
    a.posicao = ler("ag-posicao").value; a.ordem = Number(ler("ag-ordem").value) || 50; a.cor = ler("ag-cor").value;
    a.aplicar_em = ler("ag-aplicar").value.split(",").map((x) => x.trim()).filter(Boolean);
    a.ativo = ler("ag-ativo").getAttribute("aria-checked") === "true";
    a.nivel = ler("ag-nivel")?.value || "pleno"; a.andar = Number(ler("ag-andar")?.value) || 1;
    a.cargo = ler("ag-cargo")?.value.trim() || ""; a.area = ler("ag-area")?.value || ""; a.mentor = ler("ag-mentor")?.value || "";
    a.manual = ler("ag-manual")?.value ?? a.manual;
  }
  (a.habilidades || []).forEach((s, i) => {
    const liga = $(`[data-habilidade-ativa="${i}"]`);
    if (liga) s.ativo = liga.getAttribute("aria-checked") === "true";
    s.parametros = s.parametros || {};
    document.querySelectorAll(`[data-habilidade="${i}"][data-param]`).forEach((el) => {
      const tipo = el.dataset.tipo;
      let v = tipo === "booleano" ? el.getAttribute("aria-checked") === "true" : el.value;
      if (tipo === "colunas" || tipo === "lista") v = String(v).split(",").map((x) => x.trim()).filter(Boolean);
      if (tipo === "mapa") {
        const mapa = {};
        String(v).split("\n").forEach((linha) => { const k = linha.indexOf("="); if (k > 0) mapa[linha.slice(0, k).trim()] = linha.slice(k + 1).trim(); });
        v = Object.keys(mapa).length ? mapa : "";
      }
      if ((tipo === "numero" || tipo === "inteiro") && v !== "") v = Number(v);
      if (v === "" || (Array.isArray(v) && !v.length)) delete s.parametros[el.dataset.param]; else s.parametros[el.dataset.param] = v;
    });
  });
}

function abrirEditor(agente) {
  E.editando = JSON.parse(JSON.stringify(agente)); E.catalogoAberto = false; E.buscaHabilidade = "";
  abrirGaveta(editorAgente());
  $("#gaveta").classList.add("larga");
}
const redesenharEditor = () => { const rolagem = $(".gaveta-corpo")?.scrollTop || 0; abrirGaveta(editorAgente()); $("#gaveta").classList.add("larga"); const c = $(".gaveta-corpo"); if (c) c.scrollTop = rolagem; };

// ------------------------------------------------------------------ consultas SQL
async function carregarConsultas() {
  try {
    E.consultas = await api("/api/consultas");
    if (!E.consultaAtual && E.consultas.itens.length) await abrirConsulta(E.consultas.itens[0].id, false);
  } catch (e) { avisar(e.message, "erro"); }
}

async function abrirConsulta(id, redesenhar = true) {
  try { E.consultaAtual = await api(`/api/consulta?id=${encodeURIComponent(id)}`); E.resultadoConsulta = null; }
  catch (e) { avisar(e.message, "erro"); }
  if (redesenhar) desenhar();
}

function listaConsultas() {
  const busca = E.buscaConsulta.trim().toLowerCase();
  const itens = (E.consultas?.itens || []).filter((c) => !busca || `${c.titulo} ${c.pergunta} ${c.categoria}`.toLowerCase().includes(busca));
  if (!itens.length) return `<div class="vazio">Nenhuma consulta encontrada.</div>`;
  let html = "", grupo = "";
  for (const c of itens) {
    if (c.categoria !== grupo) { grupo = c.categoria; html += `<div class="grupo">${esc(grupo)}</div>`; }
    html += `<button class="${E.consultaAtual?.id === c.id ? "ativo" : ""}" data-acao="abrir-consulta" data-id="${esc(c.id)}">
      <strong>${esc(c.titulo)}</strong><small title="${esc(c.pergunta)}">${esc(c.pergunta)}</small></button>`;
  }
  return html;
}

function renderConsultas() {
  const acoes = `<button class="btn" data-acao="abrir" data-alvo="consultas">${icone("pasta")}Abrir pasta das consultas</button>`;
  if (!E.consultas) return cabecalho("Consultas SQL", "", acoes) + `<div class="carregando">Carregando…</div>`;
  const c = E.consultaAtual, r = E.resultadoConsulta;
  const semBanco = !E.consultas.banco_habilitado;
  let resultado = "";
  if (r === "carregando") resultado = `<div class="carregando">${icone("girar", "girando")} Executando…</div>`;
  else if (r && !r.ok) resultado = `<div class="ocorrencia erro"><div class="principal"><strong>Não foi possível executar</strong><div class="local">${esc(r.mensagem)}</div></div></div>`;
  else if (r) resultado = `<div class="secao-titulo">Resultado · ${num(r.linhas.length)} linha(s)${r.truncado ? " (mostrando as primeiras 1.000)" : ""} · ${duracao(r.duracao)}</div>
    ${r.linhas.length ? `<div class="tabela-envoltorio cartao"><table class="tabela compacta"><thead><tr>${r.colunas.map((x) => `<th>${esc(x)}</th>`).join("")}</tr></thead>
    <tbody>${r.linhas.map((l) => `<tr>${l.map((v) => `<td>${esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`
      : `<div class="vazio"><strong>A consulta não retornou linhas</strong>Os dados podem não ter o período ou o filtro usado.</div>`}`;
  return cabecalho("Consultas SQL", "Perguntas de negócio prontas para responder com os dados do banco. Copie para o Power BI ou execute aqui.", acoes) +
    `<div class="consultas">
      <section class="cartao consultas-lista">
        <div class="barra"><label class="campo-busca" style="max-width:none">${icone("busca")}<input type="text" id="busca-consulta" placeholder="Buscar por tema…" value="${esc(E.buscaConsulta)}"></label></div>
        <div id="lista-consultas">${listaConsultas()}</div>
      </section>
      <section class="cartao">${c ? `<div class="cartao-corpo" style="display:flex;flex-direction:column;gap:16px">
        <div><div class="muted">${esc(c.categoria)}</div><h2 style="font-size:19px;margin-top:2px">${esc(c.titulo)}</h2></div>
        <dl class="campos-consulta">
          <dt>Pergunta</dt><dd>${esc(c.pergunta)}</dd>
          <dt>Como ler</dt><dd>${esc(c.como_ler)}</dd>
          <dt>Precisa de</dt><dd class="mono">${esc(c.requer)}</dd>
        </dl>
        <pre class="sql">${esc(c.sql)}</pre>
        <div class="acoes">
          <button class="btn primario" data-acao="executar-consulta" ${semBanco ? "disabled" : ""}>${icone("play")}Executar</button>
          <button class="btn" data-acao="copiar-consulta">${icone("copiar")}Copiar SQL</button>
          <button class="btn fantasma" data-acao="abrir" data-alvo="arquivo" data-caminho="${esc(c.caminho)}">${icone("editar")}Editar arquivo</button>
          ${semBanco ? `<span class="muted">Ligue o banco em Configurações para executar.</span>` : ""}
        </div>
        ${resultado}
        <div class="dica">${icone("info")}<p><b>No Power BI:</b> Obter dados → Banco de dados PostgreSQL → <b>Opções avançadas</b> → cole este SQL em “Instrução SQL”. O resultado vira uma tabela pronta para gráficos.</p></div>
      </div>` : `<div class="vazio">Escolha uma consulta.</div>`}</section>
    </div>`;
}

// ------------------------------------------------------------------ atividade (log)
function renderAtividade() {
  const filtros = [["todos", "Tudo"], ["problemas", "Avisos e erros"]];
  return cabecalho("Atividade", "Registro ao vivo do que o robô está fazendo.",
    `<button class="btn" data-acao="abrir" data-alvo="logs">${icone("pasta")}Abrir pasta de logs</button>`) +
    `<section class="cartao"><div class="barra">
      <div class="segmentado">${filtros.map(([v, t]) => `<button class="${E.logFiltro === v ? "ativo" : ""}" data-acao="log-filtro" data-valor="${v}">${t}</button>`).join("")}</div>
      <span class="muted" style="margin-left:auto">Atualiza sozinho</span></div>
      <div class="log" id="log">${linhasLog()}</div></section>`;
}
function linhasLog() {
  const itens = E.log.filter((r) => E.logFiltro === "todos" || r.nivel !== "INFO");
  if (!itens.length) return `<div class="vazio">Nenhuma mensagem ainda.</div>`;
  const nomes = { INFO: "info", WARNING: "aviso", ERROR: "erro", DEBUG: "debug" };
  return itens.map((r) => `<div class="log-linha ${r.nivel}"><span class="hora">${esc(r.hora)}</span><span class="nivel">${nomes[r.nivel] || r.nivel}</span><span class="msg">${esc(r.mensagem)}</span></div>`).join("");
}
function rolarLog() { const el = $("#log"); if (el && E.autoRolar) el.scrollTop = el.scrollHeight; }
async function atualizarLog() {
  try {
    const novos = (await api(`/api/log?desde=${E.logSeq}`)).itens;
    if (!novos.length) return;
    E.log.push(...novos); E.log = E.log.slice(-1000); E.logSeq = novos[novos.length - 1].seq;
    if (E.pagina === "atividade") {
      const el = $("#log"); if (!el) return;
      E.autoRolar = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
      el.innerHTML = linhasLog(); rolarLog();
    }
  } catch { /* o indicador lateral já mostra a falta de conexão */ }
}

// ------------------------------------------------------------------ configurações
async function carregarConfig() {
  try { E.config = await api("/api/config"); } catch (e) { avisar(e.message, "erro"); }
}

const chave = (ligado, acao, extras = "", desabilitado = false) =>
  `<button class="chave" role="switch" aria-checked="${ligado ? "true" : "false"}" data-acao="${acao}" ${extras} ${desabilitado ? "disabled" : ""}></button>`;

function renderConfig() {
  const c = E.config;
  if (!c) return cabecalho("Configurações", "") + `<div class="carregando">Carregando…</div>`;
  const b = c.banco || {}, s = c.saida || {}, p = c.painel || {};
  const nomesPastas = Object.keys(c.pastas || {});
  const alvos = ["entrada", "tratadas", "erros", "originais", "relatorios", "logs"];
  return cabecalho("Configurações", `Ajustes salvos em <code class="mono">${esc(c.arquivo_config)}</code>`,
    `<button class="btn" data-acao="abrir" data-alvo="config">${icone("editar")}Editar config.yaml</button>
     <button class="btn" data-acao="recarregar-config">${icone("recarregar")}Recarregar</button>`) +

  `<section class="cartao"><div class="cartao-cab"><h2>Senha do painel</h2></div><div class="cartao-corpo">
    <p class="muted" style="margin-top:0">${c.senha_definida ? "O painel pede senha para abrir. Para trocar, digite a atual e a nova." : "<b>O painel está sem senha</b>: qualquer pessoa logada neste Windows vê os dados. Defina uma com pelo menos 8 caracteres."}</p>
    <div class="caixa-texto" style="flex-wrap:wrap">${c.senha_definida ? `<input type="password" id="senha-atual" placeholder="Senha atual" autocomplete="current-password">` : ""}
      <input type="password" id="senha-nova" placeholder="Nova senha" autocomplete="new-password"><input type="password" id="senha-conf" placeholder="Repita a nova senha" autocomplete="new-password">
      <button class="btn primario" data-acao="definir-senha">${icone("escudo")}${c.senha_definida ? "Trocar senha" : "Definir senha"}</button>
      ${c.senha_definida ? `<button class="btn" data-acao="sair-sessao">Sair (encerrar sessão)</button>` : ""}</div></div></section>
  <section class="cartao"><div class="cartao-cab"><h2>Geral</h2></div><div class="cartao-corpo">
    <div class="opcao"><div><strong>Ligar o robô ao abrir o aplicativo</strong><small>Se desligado, o robô começa pausado.</small></div>
      ${chave(p.ligar_robo_ao_abrir, "cfg-chave", 'data-secao="painel" data-chave="ligar_robo_ao_abrir"')}</div>
    <div class="opcao"><div><strong>Notificações do Windows</strong><small>Avisa quando uma planilha é tratada ou reprovada, mesmo com o painel fechado.</small></div>
      ${chave(p.notificacoes, "cfg-chave", 'data-secao="painel" data-chave="notificacoes"')}</div>
    <div class="opcao"><div><strong>Iniciar junto com o Windows</strong><small>${c.suporta_windows ? "O robô liga sozinho, em segundo plano, quando você entra no computador." : "Disponível apenas no Windows."}</small></div>
      ${chave(c.inicializacao_windows, "inicializacao", "", !c.suporta_windows)}</div>
    <div class="opcao"><div><strong>Atalho na Área de Trabalho e no Menu Iniciar</strong><small>Cria “Robô de Planilhas” para abrir este painel com dois cliques.</small></div>
      <button class="btn" data-acao="criar-atalhos" ${c.suporta_windows ? "" : "disabled"}>${icone("atalho")}Criar atalhos</button></div>
  </div></section>

  <section class="cartao"><div class="cartao-cab"><h2>Pastas</h2></div><div class="cartao-corpo">
    ${nomesPastas.map((n, i) => `<div class="caminho"><strong>${esc(n)}</strong><code title="${esc(c.pastas[n])}">${esc(c.pastas[n])}</code>
      <button class="btn pequeno" data-acao="abrir" data-alvo="${alvos[i]}">${icone("pasta")}Abrir</button></div>`).join("")}
    <div class="form" style="margin-top:14px"><label class="inteiro">Trocar a pasta de entrada (Bases-Limpeza)
      <small>As pastas auxiliares (Tratadas, Erros, Originais, Relatórios) ficam ao lado dela.</small>
      <input type="text" id="campo-entrada" placeholder="Cole o caminho da pasta"></label></div>
    <div class="acoes" style="margin-top:10px"><button class="btn" data-acao="salvar-entrada">${icone("ok")}Salvar pasta</button></div>
  </div></section>

  <section class="cartao"><div class="cartao-cab"><h2>Saída em arquivo</h2></div><div class="cartao-corpo">
    <div class="form">
      <label>Formato do arquivo tratado<select id="cfg-formato">
        ${[["xlsx", "Excel (.xlsx)"], ["csv", "CSV (;)"], ["ambos", "Excel e CSV"], ["nenhum", "Nenhum — só banco de dados"]].map(([v, t]) => `<option value="${v}" ${s.formato === v ? "selected" : ""}>${t}</option>`).join("")}
      </select></label>
      <label>Espera da sincronização (segundos)<input type="number" min="2" max="300" id="cfg-espera" value="${esc(c.monitoramento?.espera_estabilidade_segundos ?? 10)}">
        <small>Tempo sem mudanças antes de processar.</small></label>
    </div>
    <div class="opcao" style="margin-top:14px"><div><strong>Guardar versões</strong><small>Cada processamento gera um arquivo novo com data e hora. Desligado: substitui o anterior (melhor para o Power BI).</small></div>
      ${chave(s.versionar, "alternar-local", 'id="cfg-versionar"')}</div>
    <div class="acoes" style="margin-top:6px"><button class="btn primario" data-acao="salvar-saida">${icone("ok")}Salvar</button></div>
  </div></section>

  <section class="cartao" id="secao-banco"><div class="cartao-cab"><h2>Banco de dados PostgreSQL (ELT)</h2>
    ${chave(b.habilitado, "alternar-local", 'id="cfg-banco-habilitado"')}</div><div class="cartao-corpo">
    <div class="form">
      <label>Servidor<input type="text" id="cfg-host" value="${esc(b.host)}"></label>
      <label>Porta<input type="number" id="cfg-porta" value="${esc(b.porta)}"></label>
      <label>Banco<input type="text" id="cfg-banco" value="${esc(b.banco)}"><small>Criado automaticamente se não existir.</small></label>
      <label>Usuário<input type="text" id="cfg-usuario" value="${esc(b.usuario)}"></label>
      <label>Senha<input type="password" id="cfg-senha" placeholder="${b.senha_definida ? "•••••••• (mantida — digite para trocar)" : "senha do PostgreSQL"}" autocomplete="new-password">
        <small>Fica gravada só no seu computador (config.yaml).</small></label>
      <label>Modo de carga padrão<select id="cfg-modo">
        ${[["por_arquivo", "Por arquivo — reprocessar substitui só aquele arquivo"], ["substituir", "Substituir — a tabela fica só com o último arquivo"], ["mesclar", "Mesclar — atualiza por chave (definida na regra)"], ["anexar", "Anexar — sempre acrescenta"]].map(([v, t]) => `<option value="${v}" ${b.modo_carga_padrao === v ? "selected" : ""}>${t}</option>`).join("")}
      </select></label>
    </div>
    <div class="opcao" style="margin-top:14px"><div><strong>Guardar camada bruta</strong><small>Mantém uma cópia exata (texto) de cada planilha em bruto.* para auditoria.</small></div>
      ${chave(b.carregar_bruto, "alternar-local", 'id="cfg-bruto"')}</div>
    <div class="acoes" style="margin-top:6px">
      <button class="btn" data-acao="testar-banco">${icone("banco")}Testar conexão</button>
      <button class="btn primario" data-acao="salvar-banco">${icone("ok")}Salvar</button>
      <span class="muted" id="resultado-banco"></span></div>
  </div></section>

  <section class="cartao"><div class="cartao-cab"><h2>Regras e modelos</h2></div><div class="cartao-corpo">
    <div class="secao-titulo">Regras por arquivo (config.yaml)</div>
    ${(c.regras || []).length ? `<ul class="lista cartao">${c.regras.map((r) => `<li><div class="icone-arquivo">${icone("planilha")}</div>
      <div class="principal"><strong class="mono">${esc(r.padrao)}</strong><small>${esc(r.itens.join(" · ") || "sem validações")}</small></div></li>`).join("")}</ul>`
      : `<p class="muted">Nenhuma regra ainda — todas as planilhas recebem a limpeza padrão. Crie regras para validar colunas obrigatórias, faixas, chaves e modelagem.</p>`}
    <div class="secao-titulo" style="margin-top:16px">Modelos SQL (camada analítica)</div>
    ${(c.modelos_sql || []).length ? `<div class="chips-colunas">${c.modelos_sql.map((m) => `<span class="chip-coluna">${esc(m.nome)} <em>${m.ativo ? "ativo" : "desativado"}</em></span>`).join("")}</div>` : `<p class="muted">Nenhum arquivo .sql.</p>`}
    <div class="acoes" style="margin-top:14px">
      <button class="btn" data-acao="abrir" data-alvo="config">${icone("editar")}Editar regras</button>
      <button class="btn" data-acao="abrir" data-alvo="modelos">${icone("pasta")}Pasta de modelos SQL</button></div>
  </div></section>

  <section class="cartao"><div class="cartao-cab"><h2>Manutenção</h2></div><div class="cartao-corpo">
    <p class="muted" style="margin-top:0">Todo dia o robô apaga automaticamente: originais com mais de <b>${num(c.manutencao?.dias_retencao_originais)}</b> dias,
      relatórios com mais de <b>${num(c.manutencao?.dias_retencao_relatorios)}</b> dias e logs com mais de <b>${num(c.manutencao?.dias_retencao_logs)}</b> dias.
      A pasta Bases-Erros nunca é limpa automaticamente.</p>
    <div class="acoes"><button class="btn" data-acao="manutencao">${icone("lixeira")}Executar manutenção agora</button></div>
  </div></section>

  <section class="cartao"><div class="cartao-cab"><h2>Aplicativo</h2><span class="muted">versão ${esc(c.versao)}</span></div><div class="cartao-corpo">
    <div class="opcao"><div><strong>Fechar esta janela não desliga o robô</strong><small>Ele continua trabalhando em segundo plano. Para desligar de vez, encerre o aplicativo.</small></div>
      <button class="btn perigo" data-acao="sair">${icone("energia")}Encerrar aplicativo</button></div>
  </div></section>`;
}

const valor = (id) => $(`#${id}`)?.value ?? "";
const marcado = (id) => $(`#${id}`)?.getAttribute("aria-checked") === "true";

async function salvarConfig(alteracoes, botao, mensagem = "Configurações salvas") {
  return comCarregando(botao, async () => {
    const r = await api("/api/config/salvar", { corpo: { alteracoes } });
    if (r.erro) avisar(r.erro, "erro"); else avisar(mensagem, "sucesso");
    await Promise.all([carregarConfig(), atualizarEstado()]);
    if (E.pagina === "configuracoes") desenhar();
  });
}

function dadosBanco() {
  const d = { habilitado: marcado("cfg-banco-habilitado"), host: valor("cfg-host").trim(), porta: Number(valor("cfg-porta")) || 5432,
    banco: valor("cfg-banco").trim(), usuario: valor("cfg-usuario").trim(), carregar_bruto: marcado("cfg-bruto"), modo_carga_padrao: valor("cfg-modo") };
  const senha = valor("cfg-senha");
  if (senha) d.senha = senha;
  return d;
}

// ------------------------------------------------------------------ ações (cliques)
// ------------------------------------------------------------------ canal da equipe (offline)
async function carregarCanal() {
  const q = new URLSearchParams({ canal: E.canalAtual === "geral" ? "" : E.canalAtual, autor: E.canalAutor, tipo: E.canalTipo,
                                  dias: E.canalDias || "", busca: E.canalBusca, limite: 300 });
  try { E.canal = await api(`/api/canal?${q}`); } catch (e) { avisar(e.message, "erro"); }
}

const TIPO_MSG = { pergunta: "você perguntou", resposta: "resposta", acontecimento: "aconteceu", sprint: "sprint", alerta: "alerta",
  boletim: "boletim", contratacao: "RH", mensagem: "mensagem" };
const SUGESTOES = ["Como está hoje?", "Quais erros tivemos?", "Sprint", "Ideias para melhorar", "Como faço um PROCX?",
  "Amostra para margem de 5% numa base de 2000", "Quem é a equipe?", "Como ligo o PostgreSQL?"];

function renderCanal() {
  const c = E.canal;
  const acoes = `<button class="btn" data-acao="canal-sprint">${icone("historico")}Rodar sprint agora</button>`;
  if (!c) return cabecalho("Canal da equipe", "", acoes) + `<div class="carregando">Carregando…</div>`;
  const sp = c.sprint;
  const lista = c.mensagens.map((m) => `<div class="msg ${m.autor === "dono" ? "minha" : ""} tipo-${esc(m.tipo)}">
      <div class="msg-cab"><strong>${esc(m.nome)}</strong><small>${esc(m.papel)}</small><span class="etiqueta">${esc(TIPO_MSG[m.tipo] || m.tipo)}</span>
        ${E.canalAtual === "geral" && m.canal !== "geral" ? `<span class="etiqueta info">#${esc(m.canal)}</span>` : ""}<time>${esc(dataCurta(m.data_hora))}</time></div>
      <div class="msg-texto">${esc(m.texto)}</div></div>`).join("");
  return cabecalho("Canal da equipe", `Converse com todo o prédio — 100% no seu computador, sem internet e sem API. Sprint ${sp.numero}: ${esc(dataBr(sp.inicio))} a ${esc(dataBr(sp.fim))} (faltam ${sp.dias_restantes} dia(s)).`, acoes) +
    `<div class="canal-layout">
      <nav class="canais">${Object.entries(c.canais).map(([id, nome]) => `<button data-acao="canal-ir" data-canal="${id}" class="${E.canalAtual === id ? "ativo" : ""}"><b>#${esc(id)}</b><small>${esc(nome)}</small></button>`).join("")}</nav>
      <section class="conversa cartao">
        <div class="filtros-canal">
          <select id="canal-autor"><option value="">Todas as pessoas</option>${c.autores.map((a) => `<option value="${esc(a.id)}" ${E.canalAutor === a.id ? "selected" : ""}>${esc(a.nome)} · ${esc(a.papel)}</option>`).join("")}</select>
          <select id="canal-tipo"><option value="">Todos os tipos</option>${Object.entries(TIPO_MSG).map(([k, v]) => `<option value="${k}" ${E.canalTipo === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
          <select id="canal-dias">${[[0, "Todo o período"], [1, "Últimas 24h"], [7, "Últimos 7 dias"], [15, "Últimos 15 dias"], [30, "Últimos 30 dias"]].map(([d, t]) => `<option value="${d}" ${Number(E.canalDias) === d ? "selected" : ""}>${t}</option>`).join("")}</select>
          <label class="campo-busca">${icone("busca")}<input type="text" id="canal-busca" placeholder="Buscar nas mensagens…" value="${esc(E.canalBusca)}"></label>
        </div>
        <div class="mensagens" id="mensagens">${lista || `<p class="muted" style="padding:20px">Nada por aqui ainda. Pergunte algo abaixo — a equipe responde na hora.</p>`}</div>
        <div class="sugestoes">${SUGESTOES.map((t) => `<button class="btn pequeno" data-acao="canal-sugestao" data-texto="${esc(t)}">${esc(t)}</button>`).join("")}</div>
        <div class="caixa-texto"><textarea id="canal-texto" rows="2" placeholder="Escreva para a equipe (#${esc(E.canalAtual)}). Chame alguém pelo nome: “Ricardo, como faço…”. Enter envia, Shift+Enter quebra linha.">${esc(E.canalRascunho)}</textarea>
          <button class="btn primario" data-acao="canal-enviar">${icone("enviar")}Enviar</button></div>
      </section></div>`;
}

async function enviarCanal() {
  const caixa = $("#canal-texto");
  const texto = (E.canalRascunho && !caixa?.value ? E.canalRascunho : caixa?.value || "").trim();
  if (!texto) return;
  E.canalRascunho = "";
  try { await api("/api/canal/enviar", { corpo: { texto, canal: E.canalAtual } }); } catch (e) { avisar(e.message, "erro"); return; }
  await carregarCanal(); desenhar();
  const lista = $("#mensagens"); if (lista) lista.scrollTop = lista.scrollHeight;
  $("#canal-texto")?.focus();
}

// ------------------------------------------------------------------ central de dados (tempo real)
async function carregarCentral() {
  try { E.central = await api(`/api/central?dias=${E.centralDias}`); } catch (e) { avisar(e.message, "erro"); }
}

function barrasDias(serie) {
  const max = Math.max(1, ...serie.map((d) => d.aprovados + d.reprovados));
  const l = 560, a = 150, w = l / serie.length;
  const barras = serie.map((d, i) => {
    const ha = (d.aprovados / max) * (a - 24), hr = (d.reprovados / max) * (a - 24), x = i * w + 4;
    const dia = d.dia.slice(8, 10) + "/" + d.dia.slice(5, 7);
    return `<g><title>${dia}: ${d.aprovados} aprovado(s), ${d.reprovados} reprovado(s)</title>
      <rect x="${x}" y="${a - 18 - ha}" width="${w - 8}" height="${ha}" rx="3" fill="var(--sucesso)"/>
      <rect x="${x}" y="${a - 18 - ha - hr}" width="${w - 8}" height="${hr}" rx="3" fill="var(--perigo)"/>
      <text x="${x + (w - 8) / 2}" y="${a - 4}" text-anchor="middle" font-size="10" fill="var(--texto-3)">${dia}</text></g>`;
  }).join("");
  return `<svg viewBox="0 0 ${l} ${a}" class="grafico-dias" role="img" aria-label="Aprovados e reprovados por dia">${barras}</svg>`;
}

function renderCentral() {
  const periodos = [[1, "Hoje"], [7, "7 dias"], [30, "30 dias"]];
  const acoes = `<div class="segmentado">${periodos.map(([d, t]) => `<button data-acao="central-dias" data-dias="${d}" class="${E.centralDias === d ? "ativo" : ""}">${t}</button>`).join("")}</div>`;
  const c = E.central;
  if (!c) return cabecalho("Central de dados", "", acoes) + `<div class="carregando">Carregando…</div>`;
  const t = c.totais, a = c.areas;
  const kpi = (rotulo, valor, classe = "", sub = "") => `<div class="cartao kpi ${classe}"><span>${rotulo}</span><strong>${valor}</strong>${sub ? `<small>${sub}</small>` : ""}</div>`;
  const maxMotivo = Math.max(1, ...c.motivos.map((m) => m.vezes));
  return cabecalho("Central de dados", `Ao vivo · atualizado às ${esc(c.atualizado_em)} · tudo vem do histórico real do robô`, acoes) +
    `<section class="kpis">
      ${kpi("Planilhas recebidas", num(t.recebidos))}
      ${kpi("Aprovadas (acertos)", num(t.aprovados), "ok")}
      ${kpi("Reprovadas (erradas)", num(t.reprovados), t.reprovados ? "ruim" : "")}
      ${kpi("Taxa de aprovação", t.taxa_aprovacao === null ? "—" : `${String(t.taxa_aprovacao).replace(".", ",")}%`)}
      ${kpi("Linhas publicadas", num(t.linhas_publicadas), "", `${num(t.linhas_removidas)} removidas com motivo`)}
      ${kpi("Tempo médio", t.tempo_medio === null ? "—" : `${String(t.tempo_medio).replace(".", ",")} s`, "", `${num(t.avisos)} aviso(s)`)}
    </section>
    <div class="grade-2">
      <div class="cartao"><div class="cartao-titulo">Últimos 14 dias <small class="muted">· verde aprovadas, vermelho reprovadas</small></div>${barrasDias(c.serie)}</div>
      <div class="cartao"><div class="cartao-titulo">Por que barramos</div>
        ${c.motivos.length ? c.motivos.map((m) => `<div class="barra-motivo"><span title="${esc(m.motivo)}">${esc(m.motivo)}</span><b style="width:${(m.vezes / maxMotivo) * 100}%"></b><em>${m.vezes}</em></div>`).join("")
          : `<p class="muted">Nenhuma reprovação no período.</p>`}
        ${c.quem_barrou.length ? `<div class="chips-colunas" style="margin-top:10px">${c.quem_barrou.map((q) => `<span class="etiqueta">${esc(q.quem)}: ${q.vezes}</span>`).join("")}</div>` : ""}</div>
    </div>
    <section class="areas-central">
      ${[["1", "Engenharia", `${num(a["1"].aprovados)} aprovadas · ${num(a["1"].reprovados)} barradas · ${num(a["1"].linhas)} linhas`],
        ["2", "Análise", `${num(a["2"].bases_analisadas)} bases analisadas · ${num(a["2"].alertas)} alerta(s) · ${num(a["2"].com_ressalva)} com ressalva`],
        ["3", "Sala Excel", `${num(a["3"].entregas)} entregas · ${num(a["3"].conferencias)} conferências · ${num(a["3"].divergencias)} divergência(s)`],
        ["4", "Governança", `${num(a["4"].dados_pessoais)} coluna(s) com possível dado pessoal`],
        ["5", "TI", a["5"].saudavel === false ? `ALERTA: ${esc((a["5"].alertas || [])[0] || "")}` : a["5"].saudavel ? "sistema saudável" : "aguardando a primeira ronda"]]
        .map(([n, tit, txt]) => `<div class="cartao area-central ${n === "5" && a["5"].saudavel === false ? "ruim" : ""}"><small>${n}º andar</small><strong>${tit}</strong><span>${txt}</span></div>`).join("")}
    </section>
    <div class="cartao"><div class="cartao-titulo">Planilhas erradas ${c.erradas.length ? `<small class="muted">· clique para ver cada erro com a linha do Excel</small>` : ""}</div>
      ${c.erradas.length ? `<table class="tabela"><thead><tr><th>Arquivo</th><th>Quando</th><th>Quem barrou</th><th>Motivo principal</th></tr></thead><tbody>
        ${c.erradas.map((x) => `<tr class="clicavel" data-acao="ver-execucao" data-id="${esc(x.id)}"><td><strong>${esc(x.arquivo)}</strong><br><small class="muted">${x.erros} erro(s)</small></td>
          <td>${esc(dataCurta(x.data_hora))}</td><td>${esc(x.quem_barrou || "—")}</td>
          <td>${esc(x.motivo || "")}${(x.exemplos || []).length ? `<br><small class="muted">${esc(x.exemplos.join(" · "))}</small>` : ""}</td></tr>`).join("")}</tbody></table>`
        : `<p class="muted">Nenhuma planilha errada no período. 👏</p>`}</div>
    <div class="grade-2">
      <div class="cartao"><div class="cartao-titulo">Análises (manchetes da gerente Patrícia)</div>
        ${c.analises.length ? `<ul class="lista-ficha">${c.analises.map((x) => `<li><strong>${esc(x.base || x.arquivo)}</strong> · ${esc(x.manchete)}${x.ressalvas ? ` <span class="etiqueta alerta">${x.ressalvas} ressalva(s)</span>` : ""}</li>`).join("")}</ul>`
          : `<p class="muted">Nenhuma análise no período.</p>`}
        ${c.alertas_analise.length ? `<div class="secao-titulo" style="margin-top:10px">Alertas do monitoramento</div><ul class="lista-ficha">${c.alertas_analise.map((x) => `<li><strong>${esc(x.base)}</strong>: ${esc(x.mensagem)}</li>`).join("")}</ul>` : ""}</div>
      <div class="cartao"><div class="cartao-titulo">Acertos recentes</div>
        ${c.acertos.length ? `<table class="tabela"><tbody>${c.acertos.map((x) => `<tr class="clicavel" data-acao="ver-execucao" data-id="${esc(x.id)}"><td>${esc(x.arquivo)}</td><td>${num(x.linhas)} linhas</td><td>${esc(dataCurta(x.data_hora))}</td></tr>`).join("")}</tbody></table>`
          : `<p class="muted">Nenhuma aprovação no período.</p>`}</div>
    </div>
    <div class="cartao"><div class="cartao-titulo">Conferências da equipe no período <small class="muted">· achados = problemas que a pessoa encontrou</small></div>
      ${c.pessoas.length ? `<table class="tabela"><thead><tr><th>Pessoa</th><th>Andar</th><th>Conferências</th><th>Achados</th></tr></thead><tbody>
        ${c.pessoas.map((p) => `<tr><td>${esc(p.nome)}</td><td>${p.andar}º</td><td>${num(p.conferencias)}</td><td>${p.achados ? `<span class="etiqueta alerta">${num(p.achados)}</span>` : "0"}</td></tr>`).join("")}</tbody></table>`
        : `<p class="muted">Sem conferências no período.</p>`}</div>`;
}

// ------------------------------------------------------------------ estratégia
async function carregarEstrategia() {
  try {
    E.estrategia = await api("/api/estrategia");
    if (E.abaEstrategia === "boas" && !E.boasPraticas) E.boasPraticas = (await api("/api/boas-praticas")).texto;
  } catch (e) { avisar(e.message, "erro"); }
}

function markdown(md) {
  const inline = (t) => esc(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`(.+?)`/g, "<code>$1</code>");
  const out = []; let lista = false;
  for (const linha of String(md || "").split("\n")) {
    if (/^\s*-\s+/.test(linha)) { if (!lista) { out.push("<ul class='lista-ficha'>"); lista = true; } out.push(`<li>${inline(linha.replace(/^\s*-\s+/, ""))}</li>`); continue; }
    if (lista) { out.push("</ul>"); lista = false; }
    if (/^#\s/.test(linha)) out.push(`<h2>${inline(linha.slice(2))}</h2>`);
    else if (/^##\s/.test(linha)) out.push(`<h3>${inline(linha.slice(3))}</h3>`);
    else if (linha.trim()) out.push(`<p>${inline(linha)}</p>`);
  }
  if (lista) out.push("</ul>");
  return out.join("");
}

const ABAS_EST = [["prioridades", "Prioridades da sprint"], ["alinhamento", "Alinhamento dos andares"], ["avaliacoes", "Avaliações técnicas"],
  ["treinamentos", "Treinamentos"], ["boas", "Boas práticas"]];

function renderEstrategia() {
  const es = E.estrategia;
  const acoes = `<button class="btn" data-acao="est-sincronizar">${icone("historico")}Atualizar com os dados</button>
    <button class="btn primario" data-acao="est-novo">${icone("mais")}Nova prioridade</button>`;
  if (!es) return cabecalho("Estratégia", "", acoes) + `<div class="carregando">Carregando…</div>`;
  const sp = es.sprint;
  const abas = `<div class="segmentado abas-est">${ABAS_EST.map(([id, t]) => `<button data-acao="est-aba" data-aba="${id}" class="${E.abaEstrategia === id ? "ativo" : ""}">${t}</button>`).join("")}</div>`;
  const corpo = { prioridades: estPrioridades, alinhamento: estAlinhamento, avaliacoes: estAvaliacoes, treinamentos: estTreinamentos,
    boas: () => `<div class="cartao manual-md">${E.boasPraticas ? markdown(E.boasPraticas) : "Carregando…"}</div>` }[E.abaEstrategia]();
  return cabecalho("Estratégia", `Sprint ${sp.numero}: ${esc(dataBr(sp.inicio))} a ${esc(dataBr(sp.fim))} · faltam ${sp.dias_restantes} dia(s). Prioridade = impacto × urgência ÷ esforço.`, acoes) + abas + corpo;
}

function estPrioridades() {
  const es = E.estrategia;
  const filtro = E.filtroAndarEst ? Number(E.filtroAndarEst) : 0;
  const itens = es.backlog.filter((i) => !filtro || Number(i.andar) === filtro);
  const colunas = Object.entries(es.status);
  return `<div class="filtros-canal" style="padding:0 0 12px"><select id="est-andar"><option value="">Todos os andares</option>
      ${[1, 2, 3, 4, 5].map((n) => `<option value="${n}" ${filtro === n ? "selected" : ""}>${esc(NOME_ANDAR_PAINEL[n])}</option>`).join("")}</select>
      <span class="muted">${itens.filter((i) => i.status !== "feito").length} aberta(s) · itens automáticos nascem dos dados e se fecham sozinhos quando o problema some</span></div>
    <div class="kanban">${colunas.map(([st, nome]) => {
      const lista = itens.filter((i) => i.status === st);
      return `<div class="kanban-col"><div class="kanban-cab">${esc(nome)} <b class="contador">${lista.length}</b></div>
        ${lista.map((i) => `<article class="cartao item-est ${i.origem}">
          <div class="item-topo"><span class="etiqueta ${i.prioridade >= 8 ? "perigo" : i.prioridade >= 4 ? "alerta" : ""}">prioridade ${String(i.prioridade).replace(".", ",")}</span>
            <span class="etiqueta">${i.andar}º andar</span>${i.origem === "automatico" ? `<span class="etiqueta info">dos dados</span>` : `<span class="etiqueta">seu</span>`}</div>
          <strong>${esc(i.titulo)}</strong>
          ${i.motivo ? `<small class="muted">${esc(i.motivo)}</small>` : ""}
          <small>Responsável: <b>${esc(i.responsavel_nome)}</b> · I${i.impacto} U${i.urgencia} E${i.esforco}</small>
          ${i.resolvido_sozinho ? `<small class="muted">Resolvido: a condição não aparece mais nos dados.</small>` : ""}
          <div class="item-acoes"><select data-status-item="${esc(i.id)}">${colunas.map(([k, v]) => `<option value="${k}" ${k === i.status ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
            <button class="btn pequeno fantasma" data-acao="est-editar" data-id="${esc(i.id)}">${icone("ajustes")}</button>
            ${i.origem === "dono" ? `<button class="btn pequeno fantasma" data-acao="est-excluir" data-id="${esc(i.id)}">${icone("lixeira")}</button>` : ""}</div>
        </article>`).join("") || `<p class="muted" style="padding:6px">—</p>`}</div>`;
    }).join("")}</div>`;
}

function estAlinhamento() {
  return `<section class="alinhamento">${E.estrategia.alinhamento.map((a) => `<div class="cartao"><small class="muted">${esc(NOME_ANDAR_PAINEL[a.andar] || `${a.andar}º andar`)}</small>
      <strong>Gerente: ${esc(a.gerente)}</strong>${a.travados ? `<span class="etiqueta perigo">${a.travados} travado(s)</span>` : ""}
      ${a.prioridades.length ? `<ol class="lista-ficha">${a.prioridades.map((p) => `<li><b>${esc(p.titulo)}</b><br><small class="muted">${esc(p.responsavel)} · ${esc(p.status)} · prioridade ${String(p.prioridade).replace(".", ",")}</small></li>`).join("")}</ol>`
        : `<p class="muted">Nenhuma prioridade aberta neste andar.</p>`}</div>`).join("")}</section>`;
}

function estAvaliacoes() {
  const es = E.estrategia, av = es.avaliacao;
  const topo = `<div class="acoes" style="margin-bottom:12px"><button class="btn primario" data-acao="est-avaliar">${icone("ok")}Aplicar avaliação técnica agora</button>
    <span class="muted">Reaplica do zero as provas de todo o quadro (caso correto + erro plantado). Roda sozinha a cada sprint.</span></div>`;
  if (!av) return topo + `<div class="cartao vazio"><p>Nenhuma avaliação ainda.</p></div>`;
  const filtro = E.filtroAndarEst ? Number(E.filtroAndarEst) : 0;
  const pessoas = av.pessoas.filter((p) => !filtro || Number(p.andar) === filtro);
  return topo + `<div class="grade-2"><div class="cartao kpi ${av.aprovados === av.total ? "ok" : "ruim"}"><span>Última avaliação (${esc(dataCurta(av.data_hora))})</span>
      <strong>${av.aprovados}/${av.total}</strong><small>pessoas aprovadas</small></div>
    <div class="cartao"><div class="cartao-titulo">Histórico</div>${es.avaliacoes.slice().reverse().map((x) => `<div>${esc(dataCurta(x.data_hora))}: <b>${x.aprovados}/${x.total}</b></div>`).join("")}</div></div>
    <div class="cartao"><table class="tabela"><thead><tr><th>Pessoa</th><th>Andar</th><th>Nível</th><th>Provas</th><th>Resultado</th></tr></thead><tbody>
      ${pessoas.map((p) => `<tr><td>${esc(p.nome)}</td><td>${p.andar}º</td><td>${esc(p.nivel || "")}</td><td>${p.acertos}/${p.total}</td>
        <td>${p.aprovado ? `<span class="etiqueta sucesso">aprovado</span>` : `<span class="etiqueta perigo">reprovado</span><br><small>${esc((p.bloqueios || []).join("; "))}</small>`}</td></tr>`).join("")}</tbody></table></div>`;
}

function estTreinamentos() {
  const es = E.estrategia, t = es.treinamento;
  const topo = `<div class="acoes" style="margin-bottom:12px"><button class="btn primario" data-acao="est-treinar">${icone("frasco")}Rodar treinamento agora</button>
    <span class="muted">Planilhas difíceis geradas na hora e processadas pelo robô de verdade, numa pasta separada (não toca a produção).</span></div>`;
  if (!t) return topo + `<div class="cartao vazio"><p>Nenhum treinamento ainda.</p></div>`;
  return topo + `<div class="grade-2"><div class="cartao kpi ${t.aprovados === t.total ? "ok" : "ruim"}"><span>Último treinamento (${esc(dataCurta(t.data_hora))})</span>
      <strong>${t.aprovados}/${t.total}</strong><small>casos difíceis dominados · ${String(t.segundos).replace(".", ",")} s</small></div>
    <div class="cartao"><div class="cartao-titulo">Histórico</div>${es.treinamentos.slice().reverse().map((x) => `<div>${esc(dataCurta(x.data_hora))}: <b>${x.aprovados}/${x.total}</b></div>`).join("")}</div></div>
    <div class="cartao"><div class="cartao-titulo">Casos difíceis</div><table class="tabela"><thead><tr><th>Caso</th><th>Problema real</th><th>Quem domina</th><th>Resultado</th></tr></thead><tbody>
      ${t.casos.map((c) => `<tr><td><strong>${esc(c.titulo)}</strong></td><td><small>${esc(c.problema)}</small></td>
        <td><small>${esc(c.responsaveis.map((r) => (es.trilhas.find((x) => x.id === r) || {}).nome || r).join(", "))}</small></td>
        <td>${c.ok ? `<span class="etiqueta sucesso">dominado</span>` : `<span class="etiqueta perigo">falhou</span><br><small>${esc(c.falhas.join("; "))}</small>`}</td></tr>`).join("")}</tbody></table></div>
    <div class="cartao"><div class="cartao-titulo">Trilha de cada pessoa</div><div class="trilhas">${es.trilhas.map((p) => `<div class="trilha"><strong>${esc(p.nome)}</strong><small class="muted">${esc(p.papel)}</small>
      <span class="etiqueta ${p.dominados === p.total ? "sucesso" : "alerta"}">${p.dominados}/${p.total} casos</span></div>`).join("")}</div></div>`;
}

function editorItem(i) {
  const es = E.estrategia;
  const sel = (id, v) => `<select id="${id}">${[1, 2, 3, 4, 5].map((n) => `<option ${Number(v) === n ? "selected" : ""}>${n}</option>`).join("")}</select>`;
  return `<div class="gaveta-cab"><div style="flex:1"><div class="muted">${i.id ? (i.origem === "automatico" ? "Prioridade vinda dos dados" : "Sua prioridade") : "Nova prioridade"}</div>
      <h2>${esc(i.titulo || "Nova prioridade")}</h2></div><button class="btn fantasma" data-acao="fechar-gaveta" aria-label="Fechar">${icone("x")}</button></div>
    <div class="gaveta-corpo"><div class="form">
      <label class="inteiro">O que precisa ser feito<input type="text" id="it-titulo" value="${esc(i.titulo || "")}" ${i.origem === "automatico" ? "readonly" : ""}></label>
      <label class="inteiro">Por quê (motivo)<input type="text" id="it-motivo" value="${esc(i.motivo || "")}"></label>
      <label>Andar<select id="it-andar">${[1, 2, 3, 4, 5].map((n) => `<option value="${n}" ${Number(i.andar || 1) === n ? "selected" : ""}>${esc(NOME_ANDAR_PAINEL[n])}</option>`).join("")}</select></label>
      <label>Responsável<select id="it-resp">${es.pessoas.map((p) => `<option value="${esc(p.id)}" ${i.responsavel === p.id ? "selected" : ""}>${esc(p.nome)} · ${esc(p.papel)}</option>`).join("")}</select></label>
      <label>Impacto (1 a 5)${sel("it-impacto", i.impacto || 3)}<small>Quanto melhora o resultado se for feito.</small></label>
      <label>Urgência (1 a 5)${sel("it-urgencia", i.urgencia || 3)}<small>Quanto custa esperar.</small></label>
      <label>Esforço (1 a 5)${sel("it-esforco", i.esforco || 3)}<small>Quanto trabalho dá (maior = mais difícil).</small></label>
      <label>Situação<select id="it-status">${Object.entries(es.status).map(([k, v]) => `<option value="${k}" ${(i.status || "a_fazer") === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
    </div>
    ${(i.historico || []).length ? `<div><div class="secao-titulo">Histórico</div><ul class="lista-ficha">${i.historico.map((h) => `<li>${esc(h)}</li>`).join("")}</ul></div>` : ""}
    <div class="acoes" style="justify-content:flex-end"><button class="btn" data-acao="fechar-gaveta">Cancelar</button>
      <button class="btn primario" data-acao="est-salvar" data-id="${esc(i.id || "")}">${icone("ok")}Salvar</button></div></div>`;
}

// ------------------------------------------------------------------ TI e segurança (5º andar)
async function carregarTI() {
  try { E.ti = await api("/api/ti"); } catch (e) { avisar(e.message, "erro"); }
}

function renderTI() {
  const acoes = `<button class="btn primario" data-acao="ti-ronda">${icone("atividade")}Rodar ronda agora</button>`;
  const r = E.ti?.ronda;
  if (!r) return cabecalho("TI e segurança", "O 5º andar cuida da máquina e do programa.", acoes) + `<div class="vazio cartao"><p>Nenhuma ronda ainda. Clique em “Rodar ronda agora”.</p></div>`;
  return cabecalho("TI e segurança", `Última ronda: ${esc(dataCurta(r.data_hora))} · automática a cada ${E.ti.intervalo_minutos ?? 30} minutos. Assinada por Fernanda (DevOps/SRE).`, acoes) +
    `<div class="cartao ${r.saudavel ? "ok-cartao" : "alerta-cartao"}" style="padding:16px 20px;display:flex;gap:12px;align-items:center">
      ${icone(r.saudavel ? "ok" : "alerta")}<strong>${r.saudavel ? "Sistema saudável: todas as verificações passaram." : "Há alertas — veja abaixo o que fazer."}</strong></div>
    <div class="cartao"><table class="tabela"><thead><tr><th>Quem</th><th>O que verifica</th><th>Resultado</th></tr></thead><tbody>
      ${r.itens.map((i) => `<tr><td><strong>${esc(i.nome)}</strong><br><small class="muted">${esc(i.cargo)}</small></td>
        <td><small>${esc(({ sec_senior: "Painel só na sua máquina, senha fora do arquivo, código novo vigiado", cloud_aws: "Prontidão do PostgreSQL para o Amazon RDS (consultivo, nada vai para a nuvem)",
          dev_pleno: "Python e bibliotecas nas versões exigidas", infra_pleno: "Espaço em disco e permissão de escrita nas pastas",
          dev_junior: "Erros de programa no log das últimas 24h", devops_estagiario: "Tamanho dos logs (observação)" })[i.id] || "")}</small></td>
        <td>${i.ok ? `<span class="etiqueta sucesso">${icone("ok")}OK</span>` : i.achados.map((a) => `<div class="etiqueta ${i.nivel === "estagiario" ? "" : "alerta"}" style="white-space:normal;margin:2px 0">${esc(a)}</div>`).join("")}</td></tr>`).join("")}
    </tbody></table></div>`;
}

function dataBr(iso) { const [a, m, d] = String(iso || "").slice(0, 10).split("-"); return d ? `${d}/${m}/${a}` : ""; }

const ACOES = {
  "definir-senha": (el) => comCarregando(el, async () => {
    const r = await fetch("/api/senha", { method: "POST", headers: { "X-Robo-Painel": "1", "Content-Type": "application/json" },
      body: JSON.stringify({ atual: $("#senha-atual")?.value || "", nova: $("#senha-nova").value, confirmacao: $("#senha-conf").value }) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.erro || `Erro ${r.status}`);
    avisar("Senha definida. Entre de novo com a senha nova.", "sucesso"); setTimeout(() => location.reload(), 900);
  }),
  "sair-sessao": async () => { await fetch("/api/logout", { method: "POST", headers: { "X-Robo-Painel": "1" }, body: "{}" }); location.reload(); },
  ir: (el) => { location.hash = `#${el.dataset.pagina}`; },
  ligar: (el) => comCarregando(el, async () => { await api("/api/robo/ligar", { corpo: {} }); await atualizarEstado(); desenhar(); }),
  pausar: (el) => comCarregando(el, async () => { await api("/api/robo/pausar", { corpo: {} }); await atualizarEstado(); desenhar(); }),
  "processar-agora": async (el) => comCarregando(el, async () => {
    await api("/api/robo/processar-agora", { corpo: {} });
    avisar(E.geral?.fila?.length ? "Processando a fila agora…" : "Nenhum arquivo na fila no momento.");
    setTimeout(atualizarEstado, 600);
  }),
  abrir: (el) => api("/api/abrir", { corpo: { alvo: el.dataset.alvo, caminho: el.dataset.caminho, nome: el.dataset.nome } }).catch((e) => avisar(e.message, "erro")),
  "ver-execucao": (el) => verExecucao(el.dataset.id),
  "fechar-gaveta": fecharGaveta,
  reprocessar: (el) => comCarregando(el, async () => {
    const r = await api("/api/reprovados/reprocessar", { corpo: { nome: el.dataset.nome } });
    avisar(`${r.nome} voltou para a fila e será processado.`, "sucesso");
    await carregarReprovados(); await atualizarEstado(); desenhar();
  }),
  descartar: async (el) => {
    const ok = await confirmar({ titulo: "Descartar este arquivo?", texto: "Ele sai da lista de reprovados e vai para Bases-Erros/_descartados. Nada é publicado.", botao: "Descartar", perigo: true });
    if (!ok) return;
    try { await api("/api/reprovados/descartar", { corpo: { nome: el.dataset.nome } }); avisar("Arquivo descartado."); await carregarReprovados(); await atualizarEstado(); desenhar(); }
    catch (e) { avisar(e.message, "erro"); }
  },
  filtro: (el) => { E.filtro = el.dataset.valor; desenhar(); },
  "log-filtro": (el) => { E.logFiltro = el.dataset.valor; E.autoRolar = true; desenhar(); },
  "escolher-arquivo": (el) => escolherArquivo(el.dataset.modo),
  "enviar-testado": (el) => comCarregando(el, async () => { if (E.arquivoTeste) { await enviarArquivos([E.arquivoTeste]); E.teste = null; location.hash = "#inicio"; } }),
  "aba-teste": (el) => { E.abaTeste = Number(el.dataset.i); desenhar(); },
  "salvar-entrada": (el) => comCarregando(el, async () => {
    const caminho = valor("campo-entrada").trim();
    if (!caminho) throw new Error("Cole o caminho da pasta Bases-Limpeza.");
    const r = await api("/api/config/entrada", { corpo: { caminho } });
    if (!r.ok) throw new Error(r.erro || "Não foi possível usar essa pasta.");
    avisar("Pasta configurada! O robô já está monitorando.", "sucesso");
    E.config = null; await atualizarEstado(); location.hash = "#inicio"; desenhar();
  }),
  "cfg-chave": (el) => {
    const novo = el.getAttribute("aria-checked") !== "true";
    el.setAttribute("aria-checked", String(novo));
    salvarConfig({ [el.dataset.secao]: { [el.dataset.chave]: novo } }, null, "Preferência salva");
  },
  "alternar-local": (el) => el.setAttribute("aria-checked", String(el.getAttribute("aria-checked") !== "true")),
  inicializacao: (el) => comCarregando(null, async () => {
    const r = await api("/api/inicializacao", { corpo: { ligar: el.getAttribute("aria-checked") !== "true" } });
    el.setAttribute("aria-checked", String(r.ligado));
    avisar(r.ligado ? "O robô vai ligar sozinho quando você entrar no Windows." : "Inicialização automática desligada.", "sucesso");
  }),
  "criar-atalhos": (el) => comCarregando(el, async () => { const r = await api("/api/atalhos", { corpo: {} }); avisar(`Atalhos criados: ${r.locais.join(" e ")}.`, "sucesso"); }),
  "salvar-saida": (el) => salvarConfig({
    saida: { formato: valor("cfg-formato"), versionar: marcado("cfg-versionar") },
    monitoramento: { espera_estabilidade_segundos: Math.max(2, Number(valor("cfg-espera")) || 10) },
  }, el),
  "salvar-banco": (el) => salvarConfig({ banco: dadosBanco() }, el, "Configuração do banco salva"),
  "testar-banco": (el) => comCarregando(el, async () => {
    const r = await api("/api/banco/testar", { corpo: { banco: dadosBanco() } });
    const alvo = $("#resultado-banco");
    if (alvo) alvo.innerHTML = r.ok ? `<span class="etiqueta sucesso">${icone("ok")}${esc(r.mensagem)}</span>` : `<span class="etiqueta perigo">${icone("x")}Falhou</span>`;
    avisar(r.mensagem, r.ok ? "sucesso" : "erro");
  }),
  "executar-modelos": (el) => comCarregando(el, async () => {
    const r = await api("/api/banco/modelos", { corpo: {} });
    avisar(r.ok ? `Modelos executados: ${r.executados.join(", ") || "nenhum"}` : r.mensagem, r.ok ? "sucesso" : "erro");
    await carregarBanco(); desenhar();
  }),
  "novo-agente": () => abrirEditor({ id: "", nome: "", papel: "", descricao: "", cor: "#f97316", posicao: "limpeza", ordem: 50,
    ativo: true, aplicar_em: ["*"], habilidades: [], nativo: false, aceita_habilidades: true, nivel: "estagiario", andar: 1,
    area: "Qualidade de Dados", manual: "" }),
  "ver-pessoa": (el) => abrirPessoa(el.dataset.id),
  "salvar-manual": (el) => comCarregando(el, async () => {
    await api("/api/agentes/manual/salvar", { corpo: { id: el.dataset.id, texto: $("#manual-md").value } });
    avisar("Manual salvo. O canal já usa este conteúdo para responder.", "sucesso");
  }),
  "canal-ir": async (el) => { E.canalAtual = el.dataset.canal; await carregarCanal(); desenhar(); },
  "canal-enviar": () => enviarCanal(),
  "canal-sprint": (el) => comCarregando(el, async () => {
    await api("/api/canal/sprint", { corpo: {} });
    avisar("Sprint publicada: cada pessoa contou o que fez, o que foi bom, o que travou e o backlog.", "sucesso");
    await carregarCanal(); desenhar();
  }),
  "canal-sugestao": (el) => { E.canalRascunho = el.dataset.texto; enviarCanal(); },
  "central-dias": async (el) => { E.centralDias = Number(el.dataset.dias); await carregarCentral(); desenhar(); },
  "est-aba": async (el) => { E.abaEstrategia = el.dataset.aba; await carregarEstrategia(); desenhar(); },
  "est-novo": () => { abrirGaveta(editorItem({ andar: 1, impacto: 3, urgencia: 3, esforco: 3, status: "a_fazer", responsavel: "ger_engenharia" })); },
  "est-editar": (el) => { const i = E.estrategia.backlog.find((x) => x.id === el.dataset.id); if (i) abrirGaveta(editorItem(i)); },
  "est-salvar": (el) => comCarregando(el, async () => {
    const item = { id: el.dataset.id || undefined, titulo: $("#it-titulo").value, motivo: $("#it-motivo").value, andar: Number($("#it-andar").value),
      responsavel: $("#it-resp").value, impacto: Number($("#it-impacto").value), urgencia: Number($("#it-urgencia").value),
      esforco: Number($("#it-esforco").value), status: $("#it-status").value };
    await api("/api/estrategia/item", { corpo: { item } });
    avisar("Prioridade salva.", "sucesso"); fecharGaveta(); await carregarEstrategia(); desenhar();
  }),
  "est-excluir": async (el) => {
    const ok = await confirmar({ titulo: "Excluir esta prioridade?", texto: "Ela sai do backlog.", botao: "Excluir", perigo: true });
    if (!ok) return;
    await api("/api/estrategia/excluir", { corpo: { id: el.dataset.id } }); await carregarEstrategia(); desenhar();
  },
  "est-sincronizar": (el) => comCarregando(el, async () => {
    const r = await api("/api/estrategia/sincronizar", { corpo: {} });
    avisar(`${r.novos} prioridade(s) nova(s) vinda(s) dos dados · ${r.resolvidos} resolvida(s) sozinha(s).`, "sucesso");
    await carregarEstrategia(); desenhar();
  }),
  "est-avaliar": (el) => comCarregando(el, async () => {
    const r = await api("/api/estrategia/avaliar", { corpo: {} });
    avisar(`Avaliação técnica: ${r.aprovados}/${r.total} pessoas aprovadas.`, r.aprovados === r.total ? "sucesso" : "erro");
    await carregarEstrategia(); desenhar();
  }),
  "est-treinar": (el) => comCarregando(el, async () => {
    const r = await api("/api/estrategia/treinar", { corpo: {} });
    avisar(`Treinamento: ${r.aprovados}/${r.total} casos difíceis dominados.`, r.aprovados === r.total ? "sucesso" : "erro");
    await carregarEstrategia(); desenhar();
  }),
  "ti-ronda": (el) => comCarregando(el, async () => { E.ti = await api("/api/ti/ronda", { corpo: {} }); desenhar(); avisar("Ronda de TI concluída."); }),
  "editar-agente": (el) => { const a = E.equipe.agentes.find((x) => x.id === el.dataset.id); if (a) abrirEditor(a); },
  "abrir-catalogo": () => { coletarEditor(); E.catalogoAberto = true; redesenharEditor(); $("#busca-habilidade")?.focus(); },
  "adicionar-habilidade": (el) => {
    coletarEditor();
    E.editando.habilidades.push({ habilidade: el.dataset.habilidade, ativo: true, parametros: {} });
    E.catalogoAberto = false; E.buscaHabilidade = ""; redesenharEditor();
    avisar("Habilidade adicionada. Preencha os campos com * e salve.");
  },
  "remover-habilidade": (el) => { coletarEditor(); E.editando.habilidades.splice(Number(el.dataset.i), 1); redesenharEditor(); },
  "mover-habilidade": (el) => {
    coletarEditor();
    const i = Number(el.dataset.i), j = i + Number(el.dataset.d), l = E.editando.habilidades;
    [l[i], l[j]] = [l[j], l[i]]; redesenharEditor();
  },
  "salvar-agente": (el) => comCarregando(el, async () => {
    coletarEditor();
    const a = E.editando;
    if (!a.nativo && !a.id) a.id = (a.nome || "agente").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").replace(/^(\d)/, "a_$1").slice(0, 40) || "agente";
    const corpo = { id: a.id, habilidades: a.habilidades };
    if (!a.nativo) Object.assign(corpo, { nome: a.nome, papel: a.papel, descricao: a.descricao, cor: a.cor, posicao: a.posicao, ordem: a.ordem,
      ativo: a.ativo, aplicar_em: a.aplicar_em, nivel: a.nivel, andar: a.andar, cargo: a.cargo, area: a.area, mentor: a.mentor,
      manual: a.manual ?? "", contratado_por: a.contratado_por, contratante: a.contratante, contratado_em: a.contratado_em,
      fim_experiencia: a.fim_experiencia });
    await api("/api/agentes/salvar", { corpo: { agente: corpo } });
    avisar(`${a.nome} salvo! Já vale para as próximas planilhas.`, "sucesso");
    fecharGaveta(); await carregarAgentes(); desenhar();
  }),
  "excluir-agente": async () => {
    const a = E.editando;
    const ok = await confirmar({ titulo: `Excluir ${a.nome}?`, texto: "A configuração vai para agentes/_excluidos (dá para recuperar).", botao: "Excluir", perigo: true });
    if (!ok) return;
    try { await api("/api/agentes/excluir", { corpo: { id: a.id } }); avisar("Agente excluído."); fecharGaveta(); await carregarAgentes(); desenhar(); }
    catch (e) { avisar(e.message, "erro"); }
  },
  "abrir-consulta": (el) => abrirConsulta(el.dataset.id),
  "executar-consulta": async () => {
    if (!E.consultaAtual) return;
    E.resultadoConsulta = "carregando"; desenhar();
    try { E.resultadoConsulta = await api("/api/consultas/executar", { corpo: { id: E.consultaAtual.id } }); }
    catch (e) { E.resultadoConsulta = { ok: false, mensagem: e.message }; }
    desenhar();
  },
  "copiar-consulta": async () => {
    try { await navigator.clipboard.writeText(E.consultaAtual.sql); avisar("SQL copiado.", "sucesso"); }
    catch { avisar("Não consegui copiar automaticamente. Selecione o texto e use Ctrl+C.", "erro"); }
  },
  "atualizar-banco": (el) => comCarregando(el, async () => { await carregarBanco(); desenhar(); }),
  "recarregar-config": (el) => comCarregando(el, async () => {
    const r = await api("/api/config/recarregar", { corpo: {} });
    avisar(r.ok ? "Configuração recarregada." : r.erro, r.ok ? "sucesso" : "erro");
    await carregarConfig(); await atualizarEstado(); desenhar();
  }),
  manutencao: (el) => comCarregando(el, async () => {
    const r = await api("/api/manutencao", { corpo: {} });
    const total = Object.values(r.removidos).reduce((a, b) => a + b, 0);
    avisar(total ? `${total} arquivo(s) antigo(s) removido(s).` : "Nada para limpar.", "sucesso");
  }),
  sair: async () => {
    const ok = await confirmar({ titulo: "Encerrar o aplicativo?", texto: "O robô para de monitorar Bases-Limpeza até ser aberto de novo pelo atalho.", botao: "Encerrar", perigo: true });
    if (!ok) return;
    await api("/api/sair", { corpo: {} }).catch(() => {});
    document.body.innerHTML = `<div class="boas-vindas cartao"><div class="cartao-corpo"><h1>Robô encerrado</h1><p class="muted">Pode fechar esta janela. Para abrir de novo, use o atalho “Robô de Planilhas”.</p></div></div>`;
  },
};

document.addEventListener("click", (ev) => {
  const el = ev.target.closest("[data-acao]");
  if (!el || el.disabled) return;
  const acao = ACOES[el.dataset.acao];
  if (acao) { ev.preventDefault(); acao(el); }
});
$("#gaveta-fundo").addEventListener("click", fecharGaveta);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") fecharGaveta(); });
document.addEventListener("input", (e) => {
  if (e.target.id === "busca-habilidade") {
    E.buscaHabilidade = e.target.value;
    const tmp = document.createElement("div"); tmp.innerHTML = editorAgente();
    $("#catalogo-habilidades").innerHTML = $("#catalogo-habilidades", tmp).innerHTML;
  }
  if (e.target.id === "busca-consulta") { E.buscaConsulta = e.target.value; $("#lista-consultas").innerHTML = listaConsultas(); }
  if (e.target.id === "busca-historico") { E.busca = e.target.value; $("#corpo-historico").innerHTML = linhasHistorico(); }
  if (e.target.id === "canal-texto") E.canalRascunho = e.target.value;
  if (e.target.id === "canal-busca") {
    E.canalBusca = e.target.value;
    clearTimeout(E._buscaCanal);
    E._buscaCanal = setTimeout(async () => { await carregarCanal(); atualizarMensagens(); }, 300);
  }
});
document.addEventListener("change", async (e) => {
  if (e.target.dataset.statusItem) {
    try { await api("/api/estrategia/item", { corpo: { item: { id: e.target.dataset.statusItem, status: e.target.value } } }); }
    catch (err) { avisar(err.message, "erro"); }
    await carregarEstrategia(); desenhar(); return;
  }
  if (e.target.id === "est-andar") { E.filtroAndarEst = e.target.value; desenhar(); return; }
  const mapa = { "canal-autor": "canalAutor", "canal-tipo": "canalTipo", "canal-dias": "canalDias" };
  if (mapa[e.target.id]) { E[mapa[e.target.id]] = e.target.value; await carregarCanal(); desenhar(); }
});
document.addEventListener("keydown", (e) => {
  if (e.target.id === "canal-texto" && e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviarCanal(); }
});

// atualiza só a lista de mensagens (não atrapalha quem está digitando)
function atualizarMensagens() {
  const alvo = $("#mensagens"); if (!alvo || !E.canal) return;
  const tmp = document.createElement("div"); tmp.innerHTML = renderCanal();
  const novo = $("#mensagens", tmp);
  if (novo && novo.innerHTML !== alvo.innerHTML) {
    const noFim = alvo.scrollTop + alvo.clientHeight >= alvo.scrollHeight - 30;
    alvo.innerHTML = novo.innerHTML;
    if (noFim) alvo.scrollTop = alvo.scrollHeight;
  }
}

// ------------------------------------------------------------------ arquivos: escolher e arrastar
function escolherArquivo(modo) {
  const input = document.createElement("input");
  input.type = "file"; input.accept = ".xlsx,.xlsm,.xls,.csv,.txt"; input.multiple = modo === "enviar";
  input.onchange = () => { const arqs = [...input.files]; if (!arqs.length) return; modo === "testar" ? testarArquivo(arqs[0]) : enviarArquivos(arqs); };
  input.click();
}

let contadorArraste = 0;
const temArquivos = (e) => [...(e.dataTransfer?.types || [])].includes("Files");
window.addEventListener("dragenter", (e) => { if (!temArquivos(e)) return; e.preventDefault(); contadorArraste++; $("#soltar").hidden = false; });
window.addEventListener("dragleave", (e) => { if (!temArquivos(e)) return; contadorArraste = Math.max(0, contadorArraste - 1); if (!contadorArraste) $("#soltar").hidden = true; });
window.addEventListener("dragover", (e) => {
  if (!temArquivos(e)) return;
  e.preventDefault();
  document.querySelectorAll(".soltar-zona").forEach((z) => z.classList.toggle("sobre", z.contains(e.target)));
});
window.addEventListener("drop", (e) => {
  if (!temArquivos(e)) return;
  e.preventDefault();
  contadorArraste = 0; $("#soltar").hidden = true;
  const zona = e.target.closest?.(".soltar-zona");
  const arquivos = [...e.dataTransfer.files];
  if (!zona || !arquivos.length) return;
  if (zona.dataset.acao === "testar") testarArquivo(arquivos[0]); else enviarArquivos(arquivos);
});

// ------------------------------------------------------------------ início
document.querySelectorAll("[data-icone]").forEach((el) => { el.outerHTML = icone(el.dataset.icone); });
window.addEventListener("hashchange", () => irPara(location.hash.slice(1)));
(async () => {
  await atualizarEstado();
  if (E.geral && !E.geral.erro_config) carregarConfig();
  irPara(location.hash.slice(1) || "inicio");
  setInterval(atualizarEstado, 2000);
  setInterval(async () => { if (E.pagina === "canal") { await carregarCanal(); atualizarMensagens(); } }, 4000);
  setInterval(async () => {  // central de dados ao vivo (não redesenha enquanto você interage com um campo)
    if (E.pagina !== "central") return;
    await carregarCentral();
    if (!["SELECT", "INPUT"].includes(document.activeElement?.tagName)) desenharSemPerderFoco();
  }, 3000);
  setInterval(atualizarLog, 2000);
  atualizarLog();
})();
