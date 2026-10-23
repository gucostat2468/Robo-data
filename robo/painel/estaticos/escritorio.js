/* =====================================================================
   Escritório 3D — cada agente é uma etapa REAL do robô.
   A cena é montada a partir da equipe configurada (agentes nativos + os seus)
   e anima os eventos que o pipeline publica em /api/escritorio.
   Three.js está embutido em ./vendor (funciona sem internet).
   ===================================================================== */
import * as THREE from "three";
import { OrbitControls } from "./terceiros/OrbitControls.js";

const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (v) => Number(v || 0).toLocaleString("pt-BR");
const ESCURO = matchMedia("(prefers-color-scheme: dark)").matches;

async function api(caminho, corpo, arquivo) {
  const op = { method: corpo || arquivo ? "POST" : "GET", headers: {} };
  if (op.method === "POST") op.headers["X-Robo-Painel"] = "1";
  if (arquivo) { op.body = arquivo; op.headers["X-Nome-Arquivo"] = encodeURIComponent(arquivo.name); }
  else if (corpo) { op.body = JSON.stringify(corpo); op.headers["Content-Type"] = "application/json"; }
  const r = await fetch(caminho, op);
  const d = await r.json().catch(() => ({}));
  if (r.status === 401 && d.login) { location.href = "inicio.html"; throw new Error(d.erro); } // painel com senha: entra lá
  if (!r.ok) throw new Error(d.erro || `Erro ${r.status}`);
  return d;
}
function avisar(msg, tipo = "") {
  const el = document.createElement("div");
  el.className = `aviso ${tipo}`; el.textContent = msg;
  $("#avisos").appendChild(el); setTimeout(() => el.remove(), 4500);
}

// ------------------------------------------------------------------ renderizador
let renderer;
try {
  renderer = new THREE.WebGLRenderer({ antialias: true });
} catch {
  $("#sem-3d").hidden = false;
  throw new Error("WebGL indisponível");
}
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = ESCURO ? 0.9 : 1.05;
$("#cena").appendChild(renderer.domElement);

const cena = new THREE.Scene();
cena.background = new THREE.Color(ESCURO ? "#121722" : "#dfe6ef");
cena.fog = new THREE.Fog(cena.background, 45, 90);
const camera = new THREE.PerspectiveCamera(38, innerWidth / innerHeight, 0.1, 200);
const controles = new OrbitControls(camera, renderer.domElement);
controles.enableDamping = true;
controles.maxPolarAngle = 1.32;
controles.minDistance = 6;
controles.maxDistance = 55;

cena.add(new THREE.HemisphereLight(ESCURO ? "#7d8bb0" : "#ffffff", ESCURO ? "#202534" : "#b9a88f", ESCURO ? 1.1 : 1.6));
const sol = new THREE.DirectionalLight(ESCURO ? "#c9d4ff" : "#fff4e5", ESCURO ? 1.2 : 2.4);
sol.position.set(-10, 18, 12);
sol.castShadow = true;
sol.shadow.mapSize.set(2048, 2048);
Object.assign(sol.shadow.camera, { left: -26, right: 26, top: 18, bottom: -18, near: 1, far: 60 });
sol.shadow.bias = -0.0004;
cena.add(sol);

// ------------------------------------------------------------------ materiais e utilitários
const mats = {};
function mat(cor, extra = {}) {
  const chave = `${cor}|${JSON.stringify(extra)}`;
  if (!mats[chave]) mats[chave] = new THREE.MeshStandardMaterial({ color: cor, roughness: 0.75, metalness: 0.05, ...extra });
  return mats[chave];
}
function caixa(l, a, p, material, x = 0, y = 0, z = 0, sombra = true) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(l, a, p), material);
  m.position.set(x, y, z); m.castShadow = sombra; m.receiveShadow = true;
  return m;
}
function cilindro(r1, r2, a, material, x = 0, y = 0, z = 0, seg = 20) {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(r1, r2, a, seg), material);
  m.position.set(x, y, z); m.castShadow = true; m.receiveShadow = true;
  return m;
}
function texturaTexto(desenhar, largura = 512, altura = 160) {
  const c = document.createElement("canvas");
  c.width = largura; c.height = altura;
  desenhar(c.getContext("2d"), largura, altura);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
  return t;
}
function retanguloArredondado(ctx, x, y, l, a, r) {
  ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + l, y, x + l, y + a, r); ctx.arcTo(x + l, y + a, x, y + a, r);
  ctx.arcTo(x, y + a, x, y, r); ctx.arcTo(x, y, x + l, y, r); ctx.closePath();
}
function rotulo(titulo, subtitulo, cor) {
  const tex = texturaTexto((ctx, l, a) => {
    ctx.shadowColor = "rgba(0,0,0,.18)"; ctx.shadowBlur = 14; ctx.shadowOffsetY = 4;
    retanguloArredondado(ctx, 10, 10, l - 20, a - 24, 26);
    ctx.fillStyle = ESCURO ? "#1b2130" : "#ffffff"; ctx.fill();
    ctx.shadowColor = "transparent";
    ctx.fillStyle = cor; retanguloArredondado(ctx, 10, 10, 16, a - 24, 8); ctx.fill();
    ctx.fillStyle = ESCURO ? "#eef1f6" : "#101828"; ctx.font = "700 46px Segoe UI, system-ui, sans-serif";
    ctx.fillText(titulo, 46, 66, l - 70);
    ctx.fillStyle = ESCURO ? "#9aa5b8" : "#667085"; ctx.font = "500 32px Segoe UI, system-ui, sans-serif";
    ctx.fillText(subtitulo, 46, 112, l - 70);
  });
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false }));
  s.scale.set(2.3, 0.72, 1);
  return s;
}
function selo(simbolo, cor) {
  const tex = texturaTexto((ctx, l, a) => {
    ctx.beginPath(); ctx.arc(l / 2, a / 2, l / 2 - 6, 0, Math.PI * 2);
    ctx.fillStyle = cor; ctx.fill();
    ctx.lineWidth = 8; ctx.strokeStyle = "#fff"; ctx.stroke();
    ctx.fillStyle = "#fff"; ctx.font = "800 84px Segoe UI, system-ui, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(simbolo, l / 2, a / 2 + 4);
  }, 128, 128);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false }));
  s.scale.set(0.55, 0.55, 1); s.visible = false; s.userData.selo = true;
  return s;
}
function placa(texto, cor) {
  const tex = texturaTexto((ctx, l, a) => {
    retanguloArredondado(ctx, 6, 6, l - 12, a - 12, 22); ctx.fillStyle = cor; ctx.fill();
    ctx.fillStyle = "#fff"; ctx.font = "700 54px Segoe UI, system-ui, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(texto, l / 2, a / 2 + 2, l - 40);
  }, 512, 120);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false }));
  s.scale.set(2.4, 0.56, 1);
  return s;
}

// ------------------------------------------------------------------ personagem
const PELES = ["#f2c7a5", "#d9a37e", "#a86f4c", "#7c4f34", "#f5d3b8", "#c68a63"];
const CABELOS = ["#2b1d14", "#5a3a22", "#141414", "#8a5a2b", "#c9a15c", "#3d3d3d"];
function hashTexto(t) { let h = 0; for (const c of t) h = (h * 31 + c.charCodeAt(0)) >>> 0; return h; }

function criarPersonagem(cor, semente, emPe = false) {
  const g = new THREE.Group();
  const pele = mat(PELES[semente % PELES.length]);
  const cabelo = mat(CABELOS[(semente >>> 3) % CABELOS.length]);
  const calca = mat(ESCURO ? "#3a4256" : "#33405a");
  const pernas = [];
  for (const lado of [-1, 1]) {
    if (emPe) {
      const quadril = new THREE.Group(); quadril.position.set(lado * 0.12, 0.86, 0); g.add(quadril);
      quadril.add(caixa(0.17, 0.82, 0.18, calca, 0, -0.41, 0));
      quadril.add(caixa(0.17, 0.08, 0.28, mat("#222"), 0, -0.82, 0.05));
      pernas.push(quadril);
    } else {
      g.add(caixa(0.17, 0.16, 0.5, calca, lado * 0.12, 0.62, 0.22));
      g.add(caixa(0.15, 0.5, 0.15, calca, lado * 0.12, 0.34, 0.45));
      g.add(caixa(0.17, 0.08, 0.26, mat("#222"), lado * 0.12, 0.05, 0.52));
    }
  }
  const tronco = new THREE.Group(); tronco.position.y = emPe ? 0.82 : 0.66; g.add(tronco);
  const camisa = new THREE.Mesh(new THREE.CapsuleGeometry(0.25, 0.42, 6, 14), mat(cor));
  camisa.position.y = 0.42; camisa.castShadow = true; tronco.add(camisa);
  const cabeca = new THREE.Group(); cabeca.position.y = 0.98; tronco.add(cabeca);
  const rosto = new THREE.Mesh(new THREE.SphereGeometry(0.21, 24, 18), pele); rosto.castShadow = true; cabeca.add(rosto);
  const topo = new THREE.Mesh(new THREE.SphereGeometry(0.222, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2.1), cabelo);
  topo.rotation.x = -0.25; topo.position.z = -0.02; cabeca.add(topo);
  for (const lado of [-1, 1]) {
    const olho = new THREE.Mesh(new THREE.SphereGeometry(0.028, 10, 8), mat("#1d1d1d"));
    olho.position.set(lado * 0.075, 0.02, 0.19); cabeca.add(olho);
  }
  const sorriso = new THREE.Mesh(new THREE.TorusGeometry(0.06, 0.012, 6, 14, Math.PI), mat("#7a3b2e"));
  sorriso.position.set(0, -0.06, 0.195); sorriso.rotation.z = Math.PI; cabeca.add(sorriso);
  const bracos = [];
  for (const lado of [-1, 1]) {
    const ombro = new THREE.Group(); ombro.position.set(lado * 0.31, 0.62, 0.02); tronco.add(ombro);
    const braco = new THREE.Mesh(new THREE.CapsuleGeometry(0.075, 0.36, 4, 10), mat(cor));
    braco.position.y = -0.22; braco.castShadow = true; ombro.add(braco);
    const mao = new THREE.Mesh(new THREE.SphereGeometry(0.07, 10, 8), pele); mao.position.y = -0.46; ombro.add(mao);
    ombro.rotation.x = emPe ? -0.15 : -1.15; ombro.rotation.z = lado * -0.12;
    bracos.push(ombro);
  }
  if (emPe) { // prancheta de quem confere
    const prancheta = caixa(0.26, 0.34, 0.03, mat("#a16207"), 0, -0.4, 0.06); prancheta.add(caixa(0.2, 0.24, 0.01, mat("#ffffff"), 0, -0.02, 0.02));
    bracos[0].add(prancheta);
  }
  return { grupo: g, tronco, cabeca, bracos, pernas, alturaTronco: emPe ? 0.82 : 0.66 };
}

// ------------------------------------------------------------------ mobiliário
function criarMesa(corAgente) {
  const g = new THREE.Group();
  const tampo = mat(ESCURO ? "#d9d4cc" : "#f7f4ef"), perna = mat("#8b6b4a");
  g.add(caixa(1.5, 0.06, 0.8, tampo, 0, 0.76, 0));
  for (const [x, z] of [[-0.68, -0.33], [0.68, -0.33], [-0.68, 0.33], [0.68, 0.33]]) g.add(caixa(0.06, 0.74, 0.06, perna, x, 0.37, z));
  // notebook: a tampa fica virada para o agente; o logo (cor do agente) acende quando ele trabalha
  const base = caixa(0.46, 0.025, 0.32, mat("#3a3f4a"), 0, 0.8, -0.02); g.add(base);
  const tampa = new THREE.Group(); tampa.position.set(0, 0.81, 0.14); g.add(tampa);
  tampa.add(caixa(0.46, 0.32, 0.02, mat("#41464f"), 0, 0.16, 0));
  const logo = new THREE.Mesh(new THREE.CircleGeometry(0.05, 20), new THREE.MeshStandardMaterial({ color: corAgente, emissive: corAgente, emissiveIntensity: 0.15 }));
  logo.position.set(0, 0.17, 0.012); tampa.add(logo);
  tampa.rotation.x = 0.28;
  // caneca e pilha de papéis
  g.add(cilindro(0.05, 0.045, 0.11, mat(corAgente), -0.55, 0.85, 0.15));
  g.add(caixa(0.26, 0.04, 0.34, mat("#ffffff"), 0.52, 0.81, 0.05));
  return { grupo: g, tampa, logo };
}
function criarCadeira() {
  const g = new THREE.Group(), escuro = mat("#2f3542");
  g.add(caixa(0.55, 0.09, 0.52, escuro, 0, 0.5, 0));
  g.add(caixa(0.52, 0.42, 0.07, escuro, 0, 0.78, -0.27));
  g.add(cilindro(0.04, 0.04, 0.4, mat("#888"), 0, 0.26, 0));
  g.add(cilindro(0.26, 0.26, 0.04, mat("#555"), 0, 0.04, 0, 5));
  return g;
}
function criarPlanta(x, z, escala = 1) {
  const g = new THREE.Group();
  g.add(cilindro(0.28, 0.22, 0.5, mat("#e3d5c3"), 0, 0.25, 0));
  for (let i = 0; i < 7; i++) {
    const folha = new THREE.Mesh(new THREE.SphereGeometry(0.28, 12, 10), mat(i % 2 ? "#4f9d62" : "#3f8752"));
    folha.position.set(Math.sin(i * 1.7) * 0.2, 0.75 + (i % 3) * 0.22, Math.cos(i * 1.7) * 0.2);
    folha.scale.set(1, 1.3, 1); folha.castShadow = true; g.add(folha);
  }
  g.position.set(x, 0, z); g.scale.setScalar(escala);
  return g;
}

// ------------------------------------------------------------------ estado da cena
// ------------------------------------------------------------------ estado da cena (prédio de 2 andares)
const ALTURA = 4.4; // pé-direito: cada andar fica 4,4 m acima do anterior
const NOME_ANDAR = { 1: "1º andar · Engenharia de dados", 2: "2º andar · Analytics e Ciência de Dados", 3: "3º andar · Sala Excel e BI",
  4: "4º andar · Operações, Governança e Pessoas (RH)", 5: "5º andar · TI, DevOps e Segurança" };
const CURTO_ANDAR = { 1: "1º · Dados", 2: "2º · Analytics", 3: "3º · Excel/BI", 4: "4º · Operações e RH", 5: "5º · TI" };
const PLACA_ANDAR = { 1: ["1º ANDAR · ENGENHARIA DE DADOS", "#1d3fb0"], 2: ["2º ANDAR · ANÁLISE E QUALIDADE", "#7c3aed"], 3: ["3º ANDAR · SALA EXCEL", "#107c41"],
  4: ["4º ANDAR · DIRETORIA E CANAL", "#9a3412"], 5: ["5º ANDAR · TI E SEGURANÇA", "#111827"] };
const COR_TV = { 1: ["#0f1b3d", "#1d3fb0"], 2: ["#1e1038", "#6d28d9"], 3: ["#062b18", "#107c41"], 4: ["#2a0f05", "#9a3412"], 5: ["#05070d", "#1f2937"] };
const yAndar = (andar) => (andar - 1) * ALTURA;
const andarDe = (a) => Number(a.andar) || 1;
// "prédio" conta como acima de todos os andares (mostra todos)
const nivelVista = (v) => (v === "predio" ? 99 : v);
const estado = {
  equipe: [], estacoes: new Map(), ultimoSeq: 0, iniciado: false, chaveEquipe: "",
  fila: [], filaEventos: [], tocando: null, documentos: new Map(), selecionado: null,
  ligado: false, bancoHabilitado: false, agentesNumeros: {}, kpis: null, analiseHoje: null,
  andarVisivel: 1, seguir: true, ultimoManual: 0,
};
let raiz = new THREE.Group(); cena.add(raiz);
const andares = {};
let listaAndares = [1, 2, 3];
let geo = null, elevador = null;
let caixaEntrada, caixaTratadas, caixaErros, pilhaEntrada = [], pilhaTratadas = [], pilhaErros = [], leds = [];
const prateleiras = {}, pilhasRelatorios = {};
const tvs = {};
const clicaveis = [];
const ETAPA_NATIVA = new Set(["recepcao", "leitura", "limpeza", "validacao", "modelagem", "banco", "publicacao",
  "supervisor", "dba", "coord_engenharia", "coord_analise",
  "excel_supervisor", "excel_pesquisa", "excel_formulas", "excel_trade", "excel_dinamicas"]);

function montarPredio(equipe) {
  cena.remove(raiz); raiz = new THREE.Group(); cena.add(raiz);
  estado.estacoes.clear(); clicaveis.length = 0; leds = [];
  pilhaEntrada = []; pilhaTratadas = []; pilhaErros = [];
  for (const k of Object.keys(andares)) delete andares[k];
  for (const k of Object.keys(prateleiras)) { delete prateleiras[k]; delete pilhasRelatorios[k]; }
  listaAndares = [...new Set([1, 2, 3, ...equipe.map(andarDe)])].sort((a, b) => a - b);
  const porAndar = Object.fromEntries(listaAndares.map((n) => [n, equipe.filter((a) => andarDe(a) === n)]));
  const sentados = (lista) => lista.filter((a) => !a.ronda).length;
  const porFileira = Math.max(3, ...listaAndares.map((n) => Math.ceil(sentados(porAndar[n]) / 2))), espaco = 3.9;
  const colX = (c) => (c - (porFileira - 1) / 2) * espaco;
  const minX = colX(0) - 6.2, maxX = colX(porFileira - 1) + 4.2;
  geo = { colX, porFileira, minX, maxX, largura: maxX - minX, zFundo: -1.5, zFrente: 3.3, zParede: -4.6, profundidade: 11.5,
          xElevador: minX + 1.3, zElevador: -4.6 + 1.25 };
  for (const andar of listaAndares) {
    const g = new THREE.Group(); g.position.y = yAndar(andar); raiz.add(g);
    andares[andar] = g;
    construirAndar(g, andar, porAndar[andar]);
  }
  if (!listaAndares.includes(estado.andarVisivel) && estado.andarVisivel !== "predio") estado.andarVisivel = 1;
  desenharBotoesAndares();
  construirElevador();
  enquadrarCameras();
  definirAndarVisivel(estado.andarVisivel);
}

// corredores livres (entre as fileiras e na frente da fileira da frente) — por onde os supervisores andam
const corredores = () => ({ fundo: geo.zFundo + 1.8, frente: geo.zFrente + 1.75, x1: geo.colX(0) - 1.6, x2: geo.colX(geo.porFileira - 1) + 1.6 });

function criarAndarilho(g, andar, ag, i) {
  const c = corredores();
  const semente = hashTexto(ag.id);
  const p = criarPersonagem(ag.cor, semente, true);
  const grupo = new THREE.Group(); g.add(grupo); grupo.add(p.grupo);
  const ronda = [[c.x1, c.fundo], [c.x2, c.fundo], [c.x2, c.frente], [c.x1, c.frente]];
  if (i % 2) ronda.reverse();
  const inicio = ronda[i % ronda.length]; grupo.position.set(inicio[0], 0, inicio[1]);
  const etiqueta = rotulo(ag.nome, ag.papel + (ag.ficha?.nivel ? ` · ${ag.ficha.nivel}` : ""), ag.cor);
  etiqueta.position.set(0, 2.55, 0); etiqueta.scale.set(2.6, 0.81, 1); grupo.add(etiqueta);
  const anel = new THREE.Mesh(new THREE.TorusGeometry(0.3, 0.035, 8, 40), new THREE.MeshStandardMaterial({ color: ag.cor, emissive: ag.cor, emissiveIntensity: 0.8 }));
  anel.rotation.x = Math.PI / 2; anel.position.y = 2.15; anel.visible = false; grupo.add(anel);
  const ok = selo("✓", "#16a34a"), erro = selo("!", "#dc2626"), estudo = selo("✎", "#2563eb");
  for (const s of [ok, erro, estudo]) { s.position.set(0.42, 2.15, 0.1); grupo.add(s); }
  estudo.visible = Boolean(ag.prontidao);
  p.grupo.traverse((o) => { if (o.isMesh) { o.userData.agente = ag.id; clicaveis.push(o); } });
  const yBase = yAndar(andar);
  estado.estacoes.set(ag.id, {
    agente: ag, andar, grupo, p, anel, etiqueta, selos: { ok, erro, estudo }, prontidao: Boolean(ag.prontidao), semente, movel: true, yBase,
    ronda, alvoRonda: (i + 1) % ronda.length, caminho: [], mesa: { logo: { material: { emissiveIntensity: 0 } }, tampa: {} },
    get mesaPos() { const v = new THREE.Vector3(); grupo.getWorldPosition(v); return v.add(new THREE.Vector3(0, 0.9, 0)); },
    situacao: "parado", ate: 0,
  });
}

// caminho pelos corredores até ficar de frente para um ponto (local do andar)
function caminhoAte(e, destino) {
  const c = corredores(), atual = e.grupo.position;
  const corredorDestino = destino.z < (geo.zFundo + geo.zFrente) / 2 + 0.6 ? c.fundo : c.frente;
  const corredorAtual = Math.abs(atual.z - c.fundo) < Math.abs(atual.z - c.frente) ? c.fundo : c.frente;
  const pts = [[atual.x, corredorAtual]];
  if (corredorAtual !== corredorDestino) {
    const lateral = Math.abs(atual.x - c.x1) < Math.abs(atual.x - c.x2) ? c.x1 : c.x2;
    pts.push([lateral, corredorAtual], [lateral, corredorDestino]);
  }
  pts.push([destino.x, corredorDestino]);
  return pts.map(([x, z]) => new THREE.Vector3(x, 0, z));
}

function construirAndar(g, andar, equipe) {
  const { colX, minX, maxX, largura, zFundo, zFrente, zParede, profundidade, xElevador, zElevador } = geo;
  const yBase = yAndar(andar);
  const cx = (minX + maxX) / 2, cz = zParede + profundidade / 2;

  // piso (no 2º andar é uma laje com o vão do elevador)
  if (andar === 1) {
    g.add(caixa(largura, 0.2, profundidade, mat(ESCURO ? "#3b3631" : "#e7dccb"), cx, -0.1, cz, false));
    for (let i = 0; i < Math.floor(largura / 1.2); i++) g.add(caixa(0.02, 0.005, profundidade, mat(ESCURO ? "#35302b" : "#dccfbb"), minX + i * 1.2, 0.003, cz, false));
  } else {
    const carpete = mat(ESCURO ? "#2c3342" : "#dde3ec");
    const xVao = xElevador + 0.95, zVao = zElevador + 0.95;
    g.add(caixa(maxX - xVao, 0.3, profundidade, carpete, (xVao + maxX) / 2, -0.15, cz, false));
    g.add(caixa(xVao - minX, 0.3, zParede + profundidade - zVao, carpete, (minX + xVao) / 2, -0.15, (zVao + zParede + profundidade) / 2, false));
    for (let i = 1; i < Math.floor(profundidade / 1.5); i++) g.add(caixa(largura - 2, 0.004, 0.02, mat(ESCURO ? "#363e50" : "#cfd6e2"), cx + 1, 0.003, zParede + i * 1.5, false));
    g.add(caixa(largura, 0.1, 0.08, mat(ESCURO ? "#3d4558" : "#c7ced9"), cx, 0.55, zParede + profundidade, false)); // guarda-corpo baixo
    // borda da laje (fachada): esconde o andar de baixo quando você está num andar de cima
    g.add(caixa(largura, 1.3, 0.3, mat(ESCURO ? "#30384a" : "#e4e8ef"), cx, -0.8, zParede + profundidade - 0.05, false));
  }
  g.add(caixa(largura - 3, 0.01, 0.9, mat(ESCURO ? "#2b3550" : "#cdd8ea"), cx + 0.6, 0.01, zFundo + 1.55, false));
  g.add(caixa(largura - 3, 0.01, 0.9, mat(ESCURO ? "#2b3550" : "#cdd8ea"), cx + 0.6, 0.01, zFrente + 1.55, false));

  // paredes, rodapé e janelas
  const corParede = mat(andar === 1 ? (ESCURO ? "#262c39" : "#f3efe8") : andar === 3 ? (ESCURO ? "#1f2d27" : "#edf5ef") : (ESCURO ? "#232a38" : "#eef2f7"));
  const altParede = andar === 1 ? ALTURA : 3.6;
  g.add(caixa(largura, altParede, 0.2, corParede, cx, altParede / 2, zParede, false));
  g.add(caixa(0.2, altParede, profundidade, corParede, minX, altParede / 2, cz, false));
  g.add(caixa(largura, 0.14, 0.24, mat(ESCURO ? "#1d222d" : "#d9d2c6"), cx, 0.07, zParede + 0.02, false));
  const vidro = new THREE.MeshStandardMaterial({ color: ESCURO ? "#24345e" : "#bfe0ff", emissive: ESCURO ? "#1b2a55" : "#a8d4ff", emissiveIntensity: ESCURO ? 0.7 : 0.35 });
  for (const x of [minX + 4.4, maxX - 3.2]) {
    g.add(caixa(3.2, 1.8, 0.05, vidro, x, 2.0, zParede + 0.12, false));
    g.add(caixa(3.4, 0.08, 0.1, mat("#ffffff"), x, 1.06, zParede + 0.14, false));
    g.add(caixa(0.06, 1.8, 0.08, mat("#ffffff"), x, 2.0, zParede + 0.14, false));
  }
  const [textoPlaca, corPlaca] = PLACA_ANDAR[andar] || [`${andar}º ANDAR`, "#475569"];
  const placaAndar = placa(textoPlaca, corPlaca);
  placaAndar.scale.set(4.2, 0.98, 1); placaAndar.position.set(cx, 3.35, zParede + 0.3); g.add(placaAndar);

  // TV do andar
  const canvas = document.createElement("canvas"); canvas.width = 1024; canvas.height = 512;
  const textura = new THREE.CanvasTexture(canvas); textura.colorSpace = THREE.SRGBColorSpace;
  tvs[andar] = { canvas, textura };
  g.add(caixa(4.3, 2.35, 0.1, mat("#15181f"), cx + 4.6, 2.05, zParede + 0.14, false));
  const tela = new THREE.Mesh(new THREE.PlaneGeometry(4.1, 2.15), new THREE.MeshBasicMaterial({ map: textura, toneMapped: false }));
  tela.position.set(cx + 4.6, 2.05, zParede + 0.2); g.add(tela);
  desenharTV(andar);

  const xLateral = colX(0) - 3.4;
  if (andar === 1) {
    const mesaEntrada = new THREE.Group();
    mesaEntrada.add(caixa(1.4, 0.06, 0.9, mat("#f7f4ef"), 0, 0.76, 0));
    for (const [x, z] of [[-0.62, -0.38], [0.62, -0.38], [-0.62, 0.38], [0.62, 0.38]]) mesaEntrada.add(caixa(0.06, 0.74, 0.06, mat("#8b6b4a"), x, 0.37, z));
    mesaEntrada.add(caixa(0.7, 0.12, 0.5, mat("#f0b429"), 0, 0.85, 0));
    mesaEntrada.position.set(xLateral, 0, zFundo + 0.3); g.add(mesaEntrada);
    const p = placa("Bases-Limpeza", "#b7791f"); p.position.set(xLateral, 1.75, zFundo + 0.3); g.add(p);
    caixaEntrada = new THREE.Vector3(xLateral, 0.93, zFundo + 0.3);
    const caixote = (cor, z, texto) => {
      const c = new THREE.Group();
      c.add(caixa(1.2, 0.7, 0.9, mat(cor), 0, 0.35, 0)); c.add(caixa(1.05, 0.05, 0.75, mat("#ffffff"), 0, 0.71, 0, false));
      c.position.set(xLateral, 0, z); g.add(c);
      const pl = placa(texto, cor); pl.position.set(xLateral, 1.45, z); g.add(pl);
      return new THREE.Vector3(xLateral, 0.74, z);
    };
    caixaTratadas = caixote("#16a34a", zFrente + 0.1, "Bases-Tratadas");
    caixaErros = caixote("#dc2626", zFrente + 1.6, "Bases-Erros");
    const sofa = new THREE.Group(); sofa.position.set(maxX - 1.6, 0, zFrente + 0.4); sofa.rotation.y = -Math.PI / 2;
    sofa.add(caixa(2.2, 0.42, 0.85, mat("#5b6b8c"), 0, 0.3, 0)); sofa.add(caixa(2.2, 0.6, 0.22, mat("#56658a"), 0, 0.62, -0.32));
    g.add(sofa);
  } else {
    // estante de entregas (Bases-Relatorios) e sala de reunião
    const estante = new THREE.Group(); estante.position.set(xLateral, 0, zFrente + 0.8);
    estante.add(caixa(1.6, 1.7, 0.5, mat(ESCURO ? "#4a3b2f" : "#a47c55"), 0, 0.85, 0));
    const cores = ["#ef4444", "#3b82f6", "#22c55e", "#f59e0b", "#8b5cf6", "#0ea5e9"];
    for (let prat = 0; prat < 3; prat++) for (let i = 0; i < 6; i++) {
      estante.add(caixa(0.16, 0.42, 0.34, mat(cores[(i + prat) % 6]), -0.6 + i * 0.22, 0.3 + prat * 0.52, 0.06));
    }
    g.add(estante);
    const p = placa({ 3: "Entregas Excel", 4: "Atas das sprints", 5: "Servidor local" }[andar] || "Bases-Relatorios", corPlaca); p.position.set(xLateral, 2.15, zFrente + 0.8); g.add(p);
    prateleiras[andar] = { local: new THREE.Vector3(xLateral, 1.72, zFrente + 0.8), mundo: new THREE.Vector3(xLateral, yBase + 1.72, zFrente + 0.8) };
    pilhasRelatorios[andar] = [];
    const mesa = new THREE.Group(); mesa.position.set(maxX - 2.2, 0, zFrente + 0.6);
    mesa.add(cilindro(1.0, 1.0, 0.06, mat("#f7f4ef"), 0, 0.76, 0, 32)); mesa.add(cilindro(0.08, 0.12, 0.74, mat("#8b6b4a"), 0, 0.37, 0));
    for (let i = 0; i < 5; i++) { const c = criarCadeira(); const a = (i / 5) * Math.PI * 2; c.position.set(Math.cos(a) * 1.35, 0, Math.sin(a) * 1.35); c.rotation.y = -a - Math.PI / 2; mesa.add(c); }
    g.add(mesa);
    // quadro na parede lateral: gráfico de NPS (análise) ou planilha com fórmulas (Sala Excel)
    const quadro = andar === 3 ? texturaTexto((ctx, l, a) => {
      ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, l, a);
      ctx.fillStyle = "#107c41"; ctx.fillRect(0, 0, l, 44);
      ctx.fillStyle = "#ffffff"; ctx.font = "700 26px Segoe UI, system-ui"; ctx.fillText("fx  =CONT.SES(Dados!C:C;A5)", 16, 31);
      ctx.strokeStyle = "#d1d5db"; ctx.lineWidth = 1;
      for (let r = 0; r < 9; r++) { ctx.beginPath(); ctx.moveTo(0, 60 + r * 30); ctx.lineTo(l, 60 + r * 30); ctx.stroke(); }
      for (let c = 0; c < 5; c++) { ctx.beginPath(); ctx.moveTo(c * 110, 44); ctx.lineTo(c * 110, a); ctx.stroke(); }
      ctx.fillStyle = "#334155"; ctx.font = "500 20px Segoe UI, system-ui";
      [["Segmento", "Base", "%", "Conf."], ["Sul", "312", "31%", "OK"], ["Sudeste", "455", "45%", "OK"], ["Nordeste", "233", "23%", "OK"]]
        .forEach((linha, r) => linha.forEach((v, c) => { ctx.fillStyle = v === "OK" ? "#16a34a" : "#334155"; ctx.fillText(v, 8 + c * 110, 82 + r * 30); }));
    }, 512, 320) : texturaTexto((ctx, l, a) => {
      ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, l, a);
      ctx.fillStyle = "#334155"; ctx.font = "700 40px Segoe UI, system-ui"; ctx.fillText("Evolução do NPS", 30, 60);
      [42, 47, 39, 51, 55, 58].forEach((v, i) => { ctx.fillStyle = i === 5 ? "#7c3aed" : "#a5b4fc"; ctx.fillRect(40 + i * 75, 300 - v * 4, 50, v * 4); });
    }, 512, 320);
    const lousa = new THREE.Mesh(new THREE.PlaneGeometry(2.4, 1.5), new THREE.MeshStandardMaterial({ map: quadro }));
    lousa.position.set(minX + 0.13, 1.9, zFrente - 0.6); lousa.rotation.y = Math.PI / 2; g.add(lousa);
  }
  g.add(criarPlanta(minX + 0.8, zParede + 3.0, 1.1));
  g.add(criarPlanta(maxX - 0.8, zParede + 0.8, 1.1));
  g.add(criarPlanta(maxX - 0.8, zFrente + 2.6, 0.9));

  // quem faz ronda (supervisor e coordenadores) anda pelos corredores
  const rondantes = equipe.filter((a) => a.ronda);
  equipe = equipe.filter((a) => !a.ronda);
  rondantes.forEach((ag, i) => criarAndarilho(g, andar, ag, i));

  // estações dos agentes: fileira do fundo da esquerda para a direita; da frente, da direita para a esquerda
  const porFileira = Math.max(1, Math.ceil(equipe.length / 2));
  equipe.forEach((ag, i) => {
    const fundo = i < porFileira;
    const coluna = fundo ? i : porFileira - 1 - (i - porFileira);
    const x = colX(coluna), z = fundo ? zFundo : zFrente;
    const semente = hashTexto(ag.id);
    const grupo = new THREE.Group(); grupo.position.set(x, 0, z); g.add(grupo);
    const mesa = criarMesa(ag.cor); mesa.grupo.position.z = 0.72; grupo.add(mesa.grupo);
    const cadeira = criarCadeira(); cadeira.position.z = -0.12; grupo.add(cadeira);
    const p = criarPersonagem(ag.cor, semente); grupo.add(p.grupo);
    const nivel = ag.ficha?.nivel ? ` · ${ag.ficha.nivel}` : "";
    const sub = `${ag.papel}${nivel}`;
    const etiqueta = rotulo(ag.nome, sub, ag.cor); etiqueta.position.set(0, 2.45, 0); etiqueta.scale.set(2.6, 0.81, 1); grupo.add(etiqueta);
    const anel = new THREE.Mesh(new THREE.TorusGeometry(0.3, 0.035, 8, 40), new THREE.MeshStandardMaterial({ color: ag.cor, emissive: ag.cor, emissiveIntensity: 0.8 }));
    anel.rotation.x = Math.PI / 2; anel.position.y = 1.98; anel.visible = false; grupo.add(anel);
    const ok = selo("✓", "#16a34a"), erro = selo("!", "#dc2626"), estudo = selo("✎", "#2563eb");
    for (const s of [ok, erro, estudo]) { s.position.set(0.42, 2.0, 0.1); grupo.add(s); }
    if (ag.id === "banco") {
      const rack = new THREE.Group(); rack.position.set(1.25, 0, -0.9);
      rack.add(caixa(0.7, 1.9, 0.6, mat("#1f2430"), 0, 0.95, 0));
      for (let r = 0; r < 6; r++) for (let c = 0; c < 3; c++) {
        const led = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.04, 0.02), new THREE.MeshStandardMaterial({ color: "#22c55e", emissive: "#22c55e", emissiveIntensity: 0.4 }));
        led.position.set(-0.18 + c * 0.18, 0.4 + r * 0.24, 0.31); rack.add(led); leds.push(led);
      }
      grupo.add(rack);
    }
    if (i % 3 === 1) grupo.add(criarPlanta(-1.1, -0.7, 0.55));
    for (const parte of [p.grupo, mesa.grupo]) parte.traverse((o) => { if (o.isMesh) { o.userData.agente = ag.id; clicaveis.push(o); } });
    // ninguém dorme: quem está sem trabalho fica de prontidão (estudando e revisando), com o notebook aberto
    const prontidao = Boolean(ag.prontidao);
    estudo.visible = prontidao;
    estado.estacoes.set(ag.id, {
      agente: ag, andar, grupo, p, mesa, anel, etiqueta, selos: { ok, erro, estudo }, prontidao, semente,
      mesaPos: new THREE.Vector3(x + 0.52, yBase + 0.86, z + 0.77), situacao: "parado", ate: 0,
    });
  });
}

function construirElevador() {
  const { xElevador: x, zElevador: z } = geo;
  const vidro = new THREE.MeshStandardMaterial({ color: "#9ec5ff", transparent: true, opacity: 0.18, depthWrite: false, roughness: 0.1 });
  const altura = yAndar(listaAndares.at(-1)) + 3.6, poco = new THREE.Group();
  poco.add(caixa(1.7, altura, 0.04, vidro, x, altura / 2, z + 0.85, false));
  poco.add(caixa(0.04, altura, 1.7, vidro, x + 0.85, altura / 2, z, false));
  for (const [dx, dz] of [[-0.85, -0.85], [0.85, -0.85], [-0.85, 0.85], [0.85, 0.85]]) poco.add(caixa(0.07, altura, 0.07, mat("#64748b"), x + dx, altura / 2, z + dz));
  raiz.add(poco);
  const cabine = new THREE.Group();
  cabine.add(caixa(1.5, 0.08, 1.5, mat("#475569"), 0, 0.04, 0));
  cabine.add(caixa(1.5, 0.08, 1.5, mat("#475569"), 0, 2.3, 0));
  cabine.add(caixa(1.5, 2.3, 0.05, mat(ESCURO ? "#334155" : "#cbd5e1"), 0, 1.15, -0.72));
  const luz = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.03, 0.3), new THREE.MeshStandardMaterial({ color: "#fff7d6", emissive: "#fff7d6", emissiveIntensity: 1.2 }));
  luz.position.y = 2.24; cabine.add(luz);
  cabine.position.set(x, 0, z); raiz.add(cabine);
  for (const andar of listaAndares) {
    const p = placa(`Elevador · ${andar}º`, "#475569"); p.scale.set(1.9, 0.44, 1);
    p.position.set(x + 0.2, 2.75, z + 1.0); andares[andar].add(p);
  }
  elevador = { cabine, x, z };
}
const pontoElevador = (andar) => new THREE.Vector3(geo.xElevador, yAndar(andar) + 1.0, geo.zElevador);

// ------------------------------------------------------------------ câmera, andares e caminhada
let enquadramentos = {};
function enquadrarCameras() {
  const { minX, maxX, largura, zParede } = geo;
  const temPainel = innerWidth >= 900;
  const cx = (minX + maxX) / 2 + (temPainel ? largura * 300 / innerWidth * 0.32 : 0);
  const aspecto = innerWidth / innerHeight;
  const dist = Math.max(17, largura * (aspecto < 1.6 ? 1.18 : 1.04)) * (temPainel ? 1.08 : 1.3);
  for (const andar of listaAndares) {
    const y = yAndar(andar);
    enquadramentos[andar] = { pos: new THREE.Vector3(cx + 1.2, y + dist * 0.6, zParede + 4.8 + dist * 0.8), alvo: new THREE.Vector3(cx + 0.8, y + 0.4, zParede + 5.6) };
  }
  const topo = yAndar(listaAndares.at(-1));
  enquadramentos.predio = { pos: new THREE.Vector3(cx + 2, topo * 0.65 + ALTURA * 0.6 + dist * 0.18, zParede + 6 + dist * 1.15 + topo * 0.7),
                            alvo: new THREE.Vector3(cx + 0.8, topo * 0.5 + ALTURA * 0.3, zParede + 5) };
  if (!estado.iniciado) { const e = enquadramentos[estado.andarVisivel]; camera.position.copy(e.pos); controles.target.copy(e.alvo); controles.update(); }
}

function desenharBotoesAndares() {
  const caixa = $("#andares");
  caixa.innerHTML = listaAndares.map((n) => `<button data-andar="${n}" title="Tecla ${n}">${CURTO_ANDAR[n] || `${n}º andar`}</button>`).join("")
    + `<button data-andar="predio" title="Tecla P">Prédio</button>`;
  caixa.querySelectorAll("[data-andar]").forEach((b) => b.classList.toggle("ativo", b.dataset.andar === String(estado.andarVisivel)));
}

function definirAndarVisivel(andar) {
  estado.andarVisivel = andar;
  const vista = nivelVista(andar);
  for (const n of listaAndares) {
    if (!andares[n]) continue;
    andares[n].visible = n <= vista;
    // num andar de cima, as placas e etiquetas dos de baixo não aparecem "flutuando" por baixo da laje
    const escondeEtiquetas = andar !== "predio" && n < vista;
    andares[n].traverse((o) => { if (o.isSprite && !o.userData.selo) o.visible = !escondeEtiquetas; });
  }
  document.querySelectorAll("#andares [data-andar]").forEach((b) => b.classList.toggle("ativo", b.dataset.andar === String(andar)));
}

function irParaAndar(andar, manual = false) {
  if (manual) estado.ultimoManual = performance.now();
  const destino = enquadramentos[andar]; if (!destino) return;
  const subindo = nivelVista(andar) >= nivelVista(estado.andarVisivel);
  if (subindo) definirAndarVisivel(andar); // mostra o andar de cima antes de a câmera subir
  voo = { t0: performance.now(), dur: 1100, dePos: camera.position.clone(), deAlvo: controles.target.clone(),
          paraPos: destino.pos.clone(), paraAlvo: destino.alvo.clone(), aoTerminar: subindo ? null : () => definirAndarVisivel(andar) };
  if (!subindo) estado.andarVisivel = andar;
  document.querySelectorAll("#andares [data-andar]").forEach((b) => b.classList.toggle("ativo", b.dataset.andar === String(andar)));
  $("#hud-ficha").hidden = true; estado.selecionado = null; desenharEquipe();
}

const teclas = new Set();
addEventListener("keydown", (e) => {
  if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) return;
  const digito = /^Digit(\d)$/.exec(e.code);
  if (digito && listaAndares.includes(Number(digito[1]))) return irParaAndar(Number(digito[1]), true);
  if (e.code === "KeyP" || e.code === "Digit0") return irParaAndar("predio", true);
  if (e.code === "KeyF") return alternarSeguir();
  if (e.key === "Escape") return irParaAndar(estado.andarVisivel, true);
  if (["KeyW", "KeyA", "KeyS", "KeyD", "KeyQ", "KeyE", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "ShiftLeft", "ShiftRight"].includes(e.code)) {
    teclas.add(e.code); if (e.code.startsWith("Arrow")) e.preventDefault();
  }
});
addEventListener("keyup", (e) => teclas.delete(e.code));
addEventListener("blur", () => teclas.clear());

function caminhar(dt) {
  if (!teclas.size || !geo) return;
  const rapido = teclas.has("ShiftLeft") || teclas.has("ShiftRight") ? 2.4 : 1;
  const frente = controles.target.clone().sub(camera.position); frente.y = 0;
  if (frente.lengthSq() < 1e-6) return;
  frente.normalize();
  const direita = new THREE.Vector3().crossVectors(frente, new THREE.Vector3(0, 1, 0));
  const mov = new THREE.Vector3();
  if (teclas.has("KeyW") || teclas.has("ArrowUp")) mov.add(frente);
  if (teclas.has("KeyS") || teclas.has("ArrowDown")) mov.sub(frente);
  if (teclas.has("KeyD") || teclas.has("ArrowRight")) mov.add(direita);
  if (teclas.has("KeyA") || teclas.has("ArrowLeft")) mov.sub(direita);
  if (mov.lengthSq()) {
    mov.normalize().multiplyScalar(7 * rapido * dt);
    const alvo = controles.target.clone().add(mov);
    alvo.x = Math.min(geo.maxX, Math.max(geo.minX, alvo.x));
    alvo.z = Math.min(geo.zParede + geo.profundidade, Math.max(geo.zParede, alvo.z));
    camera.position.add(alvo.clone().sub(controles.target)); controles.target.copy(alvo);
  }
  const giro = (teclas.has("KeyQ") ? 1 : 0) - (teclas.has("KeyE") ? 1 : 0);
  if (giro) {
    const desloc = camera.position.clone().sub(controles.target);
    desloc.applyAxisAngle(new THREE.Vector3(0, 1, 0), giro * 1.4 * dt);
    camera.position.copy(controles.target).add(desloc);
  }
  voo = null; estado.ultimoManual = performance.now();
}
controles.addEventListener("start", () => { estado.ultimoManual = performance.now(); voo = null; });

function alternarSeguir() {
  estado.seguir = !estado.seguir;
  const b = $("#btn-seguir"); if (b) { b.classList.toggle("ativo", estado.seguir); b.setAttribute("aria-pressed", String(estado.seguir)); }
  avisar(estado.seguir ? "A câmera vai acompanhar o documento entre os andares." : "Câmera livre: ela não troca de andar sozinha.");
}

// ------------------------------------------------------------------ TVs
function desenharTV(andar) {
  const tv = tvs[andar]; if (!tv) return;
  const ctx = tv.canvas.getContext("2d"), l = 1024, a = 512;
  const grad = ctx.createLinearGradient(0, 0, l, a);
  const [c0, c1] = COR_TV[andar] || COR_TV[2];
  grad.addColorStop(0, c0); grad.addColorStop(1, c1);
  ctx.fillStyle = grad; ctx.fillRect(0, 0, l, a);
  ctx.fillStyle = "rgba(255,255,255,.85)"; ctx.font = "600 34px Segoe UI, system-ui, sans-serif"; ctx.textAlign = "left";
  ctx.fillText({ 1: "HOJE NA ENGENHARIA", 2: "HOJE NA ANÁLISE", 3: "HOJE NA SALA EXCEL", 4: "HOJE NA DIRETORIA", 5: "SAÚDE DO SISTEMA" }[andar] || "HOJE", 48, 70);
  ctx.textAlign = "right"; ctx.fillStyle = estado.ligado ? "#7fe0b4" : "#f5b445";
  ctx.fillText(estado.ligado ? "● Monitorando" : "● Pausado", l - 48, 70); ctx.textAlign = "left";
  let blocos;
  if (andar === 1) {
    const k = estado.kpis || {};
    blocos = [["Aprovados", k.hoje_sucesso ?? 0, "#7fe0b4"], ["Reprovados", k.hoje_reprovado ?? 0, "#ff9a85"],
      ["Na fila", estado.fila.length, "#ffd27a"], ["Linhas", k.hoje_linhas ?? 0, "#a9c1ff"]];
  } else if (andar === 5) {
    const t = estado.ti || {};
    blocos = [["Status", t.saudavel === false ? "ALERTA" : t.saudavel ? "OK" : "—", t.saudavel === false ? "#ff9a85" : "#7fe0b4"],
      ["Alertas", (t.alertas || []).length, "#ffd27a"], ["Pessoas de TI", estado.equipe.filter((a) => andarDe(a) === 5).length, "#a9c1ff"]];
  } else if (andar === 4) {
    const c = estado.canalHoje || {};
    blocos = [["Mensagens hoje", c.mensagens ?? 0, "#fdba74"], [`Sprint ${c.sprint ?? 1}`, c.dias_restantes ?? 0, "#7fe0b4"], ["Pessoas", estado.equipe.length, "#a9c1ff"]];
  } else if (andar === 3) {
    const x = estado.excelHoje || {};
    blocos = [["Entregas", x.entregas ?? 0, "#86efac"], ["Conferências", x.conferencias ?? 0, "#7fe0b4"], ["Divergências", x.divergencias ?? 0, "#ffd27a"]];
  } else {
    const h = estado.analiseHoje || {};
    blocos = [["Bases", h.bases ?? 0, "#f0abfc"], ["Diferenças reais", h.destaques ?? 0, "#7fe0b4"], ["Alertas", h.alertas ?? 0, "#ffd27a"]];
  }
  blocos.forEach(([t, v, c], i) => {
    const x = 48 + i * 238, alto = andar === 1 ? 300 : 170;
    ctx.fillStyle = "rgba(255,255,255,.08)"; retanguloArredondado(ctx, x, 110, 216, alto, 20); ctx.fill();
    ctx.fillStyle = c; ctx.font = `700 ${andar === 1 ? 92 : typeof v === "string" ? 60 : 72}px Segoe UI, system-ui, sans-serif`; ctx.fillText(typeof v === "string" ? v : num(v), x + 22, andar === 1 ? 280 : 200, 180);
    ctx.fillStyle = "rgba(255,255,255,.8)"; ctx.font = "500 30px Segoe UI, system-ui, sans-serif"; ctx.fillText(t, x + 22, andar === 1 ? 350 : 255, 190);
  });
  if (andar === 2) {
    const linhas = (estado.analiseHoje?.ultimo_resumo || []).slice(1, 5);
    ctx.fillStyle = "rgba(255,255,255,.92)"; ctx.font = "600 26px Segoe UI, system-ui, sans-serif";
    ctx.fillText(linhas.length ? `Último resumo · ${estado.analiseHoje.ultimo_arquivo}` : "Nenhuma análise hoje ainda", 48, 330, l - 96);
    ctx.font = "400 23px Segoe UI, system-ui, sans-serif"; ctx.fillStyle = "rgba(255,255,255,.8)";
    linhas.forEach((t, i) => ctx.fillText(String(t).trim(), 48, 370 + i * 34, l - 96));
  } else if (andar === 5) {
    const t = estado.ti || {};
    ctx.fillStyle = "rgba(255,255,255,.92)"; ctx.font = "600 26px Segoe UI, system-ui, sans-serif";
    ctx.fillText(t.data_hora ? `Última ronda de TI · ${t.data_hora.slice(11, 16)}` : "Primeira ronda de TI em andamento", 48, 330, l - 96);
    ctx.font = "400 23px Segoe UI, system-ui, sans-serif"; ctx.fillStyle = "rgba(255,255,255,.8)";
    (t.alertas?.length ? t.alertas.slice(0, 3) : ["Disco, dependências, logs e segurança verificados."]).forEach((x, i) => ctx.fillText(x, 48, 370 + i * 34, l - 96));
  } else if (andar === 4) {
    const c = estado.canalHoje || {};
    ctx.fillStyle = "rgba(255,255,255,.92)"; ctx.font = "600 26px Segoe UI, system-ui, sans-serif";
    ctx.fillText(`Faltam ${c.dias_restantes ?? 0} dia(s) para fechar a sprint ${c.sprint ?? 1}`, 48, 330, l - 96);
    ctx.font = "400 23px Segoe UI, system-ui, sans-serif"; ctx.fillStyle = "rgba(255,255,255,.8)";
    ctx.fillText(c.ultima || "Canal em silêncio por enquanto — fale com a equipe pelo painel.", 48, 370, l - 96);
  } else if (andar === 3) {
    const x = estado.excelHoje || {};
    ctx.fillStyle = "rgba(255,255,255,.92)"; ctx.font = "600 26px Segoe UI, system-ui, sans-serif";
    ctx.fillText(x.ultimo ? `Última entrega · ${x.ultimo}` : "Nenhuma entrega Excel hoje ainda", 48, 330, l - 96);
    ctx.font = "400 23px Segoe UI, system-ui, sans-serif"; ctx.fillStyle = "rgba(255,255,255,.8)";
    ["Toda fórmula é recalculada e comparada com o Python na aba Conferência.",
     "Ricardo só assina quando 100% das conferências fecham."].forEach((t, i) => ctx.fillText(t, 48, 370 + i * 34, l - 96));
  } else {
    ctx.fillStyle = "rgba(255,255,255,.55)"; ctx.font = "400 26px Segoe UI, system-ui, sans-serif";
    ctx.fillText(`Atualizado ${new Date().toLocaleTimeString("pt-BR")}`, 48, 475);
  }
  tv.textura.needsUpdate = true;
}

// ------------------------------------------------------------------ documentos (com elevador)
function novoDocumento(arquivo) {
  const g = new THREE.Group();
  g.add(caixa(0.34, 0.02, 0.44, mat("#ffffff"), 0, 0, 0));
  const faixa = caixa(0.34, 0.025, 0.08, new THREE.MeshStandardMaterial({ color: "#2654d9" }), 0, 0.002, -0.17);
  g.add(faixa); g.position.copy(caixaEntrada); raiz.add(g);
  const doc = { arquivo, g, faixa, andar: 1, rota: [] };
  estado.documentos.set(arquivo, doc);
  return doc;
}
// devolve a duração total (ms); troca de andar passa pelo elevador
function moverDocumento(doc, destino, dur, andarDestino = doc.andar) {
  doc.rota = [];
  if (andarDestino !== doc.andar) {
    doc.rota.push({ para: pontoElevador(doc.andar), dur: Math.max(500, dur * 0.5), salto: true });
    doc.rota.push({ para: pontoElevador(andarDestino), dur: 1500, vertical: true });
    doc.rota.push({ para: destino.clone(), dur: Math.max(500, dur * 0.6), salto: true });
    doc.andar = andarDestino;
  } else {
    doc.rota.push({ para: destino.clone(), dur, salto: true });
  }
  return doc.rota.reduce((t, s) => t + s.dur, 0);
}
function empilhar(pilha, base, cor, pai = raiz) {
  const folha = caixa(0.34, 0.02, 0.44, mat(cor), base.x + (Math.random() - 0.5) * 0.12, base.y + 0.01 + pilha.length * 0.025, base.z + (Math.random() - 0.5) * 0.1);
  folha.rotation.y = (Math.random() - 0.5) * 0.4; pai.add(folha); pilha.push(folha);
  if (pilha.length > 14) pai.remove(pilha.shift());
}
function atualizarPilhaEntrada() {
  if (!caixaEntrada) return;
  const alvo = Math.min(8, Math.max(0, estado.fila.length - (estado.tocando ? 1 : 0)));
  while (pilhaEntrada.length > alvo) raiz.remove(pilhaEntrada.pop());
  while (pilhaEntrada.length < alvo) empilhar(pilhaEntrada, caixaEntrada, "#ffffff");
}

// ------------------------------------------------------------------ reprodução dos eventos reais
const DURACAO = { recepcao: 1.2, leitura: 1.6, limpeza: 1.8, validacao: 1.6, modelagem: 1.6, banco: 1.7, publicacao: 1.4, concluido: 1.6, adiado: 1.3 };
const FRASE = {
  recepcao: "recebeu", leitura: "está lendo", limpeza: "está limpando", validacao: "está auditando",
  modelagem: "está modelando para o Power BI", banco: "está carregando no PostgreSQL", publicacao: "está publicando",
  analise_perfil: "está traçando o perfil de", analise_indicadores: "está calculando os indicadores de",
  analise_estatistica: "está testando o que é diferença real em", analise_monitoramento: "está comparando com as cargas anteriores",
  analise_relator: "está escrevendo o resumo executivo de",
  supervisor: "está conferindo (conciliação de linhas e integridade) antes de publicar", dba: "está conferindo no PostgreSQL, antes do commit,",
  coord_engenharia: "está passando o checklist de produção de", coord_analise: "está revisando as análises de",
  excel_pesquisa: "está montando o plano tabular (CONT.SES) de", excel_formulas: "está escrevendo as fórmulas de NPS, CSAT e margem de",
  excel_trade: "está montando o SOMASES de trade (loja, canal, SKU) de", excel_dinamicas: "está organizando o resumo e o guia de uso de",
  excel_supervisor: "está conferindo célula a célula, contra o Python, a entrega de",
  eng_pleno_tipos: "está conferindo os tipos de cada coluna de", eng_junior_espacos: "está conferindo espaços e linhas vazias de",
  eng_junior_auditoria: "está conferindo a origem de cada linha de", eng_estagiario: "está rastreando uma amostra (observação) de",
  eng_pleno_releitura: "está relendo o arquivo gravado de", ana_pleno_recalculo: "está recalculando o NPS, por conta própria, de",
  ana_pleno_base: "está conferindo as bases pequenas de", ana_junior_faixas: "está conferindo as faixas dos indicadores de",
  ana_estagiario: "está recontando as bases (observação) de", ger_analise: "está escrevendo a manchete para o dono de",
  coord_excel: "está conferindo a integridade da entrega Excel de", xl_pleno_formulas: "está conferindo se tudo é fórmula viva em",
  xl_junior_formatos: "está conferindo formatos e cabeçalhos de", xl_estagiario: "está sorteando conferências (observação) de",
  gov_pleno_lgpd: "está procurando dados pessoais (LGPD) em", gov_estagiaria: "está atualizando o catálogo de dados com",
};
const DURACAO_EXTRA = { supervisor: 2.4, dba: 1.6, coord_engenharia: 2.0, coord_analise: 2.0, excel_supervisor: 2.2, coord_excel: 2.0 };

function idAgente(etapa) {
  if (etapa.startsWith("agente:")) return etapa.slice(7);
  if (etapa.startsWith("analise:")) return `analise_${etapa.slice(8)}`;
  return ETAPA_NATIVA.has(etapa) || estado.estacoes.has(etapa) ? etapa : null;
}

function definirSituacao(id, situacao, segundos = 0) {
  const e = estado.estacoes.get(id); if (!e) return;
  e.situacao = situacao; e.ate = segundos ? performance.now() + segundos * 1000 : 0;
  e.anel.visible = situacao === "trabalhando";
  e.selos.ok.visible = situacao === "ok"; e.selos.erro.visible = situacao === "erro";
  e.selos.estudo.visible = situacao === "parado" && e.prontidao;
  e.mesa.logo.material.emissiveIntensity = situacao === "trabalhando" ? 1.6 : 0.15;
  desenharEquipe();
}

function seguirPara(andar) {
  const livre = performance.now() - estado.ultimoManual > 8000;
  if (estado.seguir && livre && estado.andarVisivel !== "predio" && estado.andarVisivel !== andar) irParaAndar(andar);
}

function iniciarEvento(ev) {
  const velocidade = estado.filaEventos.length > 12 ? 0.35 : estado.filaEventos.length > 5 ? 0.6 : 1;
  // conferências do quadro (plenos, juniores, estagiários) são rápidas: a animação acompanha
  const rapida = /^(eng|ana|xl|gov)_/.test(ev.etapa) || ev.etapa.startsWith("ger_");
  const dur = (DURACAO[ev.etapa] || (rapida ? 0.9 : 1.5)) * velocidade;
  const curto = ev.arquivo.length > 38 ? `${ev.arquivo.slice(0, 35)}…` : ev.arquivo;
  let doc = estado.documentos.get(ev.arquivo);

  if (ev.etapa === "tarefa_fim") { // tarefa da central terminou: o documento dela sai da mesa
    for (const [chave, d] of estado.documentos) if (chave.startsWith(ev.arquivo)) { raiz.remove(d.g); estado.documentos.delete(chave); }
    const NOME_FIM = { concluida: "✅ concluída", concluida_parcialmente: "🟡 concluída em parte", falhou: "⛔ falhou" };
    narrar(`📋 Tarefa ${ev.arquivo} ${NOME_FIM[ev.status] || ev.status} — detalhes em Solicitações no painel`);
    estado.tocando = { ev, fim: performance.now() + 1500 };
    return;
  }

  if (ev.etapa === "concluido" || ev.etapa === "adiado") {
    doc = doc || novoDocumento(ev.arquivo);
    let total, final;
    if (ev.etapa === "adiado") {
      doc.faixa.material.color.set("#f59e0b"); total = moverDocumento(doc, caixaEntrada, dur * 1000, 1); final = "entrada";
      definirSituacao("publicacao", "parado"); narrar(`⏳ ${curto} adiado — o robô tenta de novo em instantes`);
    } else if (ev.status === "sucesso") {
      doc.faixa.material.color.set("#16a34a");
      if (doc.andar >= 2 && prateleiras[doc.andar]) {
        total = moverDocumento(doc, prateleiras[doc.andar].mundo, dur * 1000, doc.andar); final = "relatorios";
        empilhar(pilhaTratadas, caixaTratadas, "#dcfce7");
        definirSituacao(doc.andar === 3 ? "excel_supervisor" : "analise_relator", "ok", 2.2);
        narrar(`✅ ${curto} aprovado — ${num(ev.linhas)} linhas em Bases-Tratadas${ev.banco ? " e no PostgreSQL" : ""}; análise e entrega Excel em Bases-Relatorios`);
      } else {
        total = moverDocumento(doc, caixaTratadas.clone().add(new THREE.Vector3(0, 0.3, 0)), dur * 1000, 1); final = "tratadas";
        definirSituacao("publicacao", "ok", 2.2);
        narrar(`✅ ${curto} aprovado — ${num(ev.linhas)} linhas prontas em Bases-Tratadas${ev.banco ? " e no PostgreSQL" : ""}`);
      }
    } else {
      doc.faixa.material.color.set("#dc2626"); total = moverDocumento(doc, caixaErros.clone().add(new THREE.Vector3(0, 0.3, 0)), dur * 1000, 1); final = "erros";
      definirSituacao(String(ev.motivo || "").includes("Supervisor") ? "supervisor" : "validacao", "erro", 3); definirSituacao("publicacao", "parado");
      narrar(`⛔ ${curto} reprovado — ${num(ev.erros)} erro(s). Veja em Reprovados no painel`);
    }
    seguirPara(doc.andar);
    estado.tocando = { ev, fim: performance.now() + Math.max(dur * 1000, total + 200), doc, final, andarFinal: doc.andar };
    return;
  }

  const id = idAgente(ev.etapa);
  const est = id && estado.estacoes.get(id);
  if (!est) { estado.tocando = { ev, fim: performance.now() + 50 }; return; }
  doc = doc || novoDocumento(ev.arquivo);
  if (est.movel) { // supervisor/coordenador vai até onde o documento está
    if (doc.andar !== est.andar) { const ultimo = doc.rota.at(-1)?.para; if (ultimo) doc.g.position.copy(ultimo); }
    const local = doc.g.position.clone(); local.y -= est.yBase;
    est.caminho = caminhoAte(est, local);
    const distancia = est.caminho.reduce((d, p, i) => d + (i ? p.distanceTo(est.caminho[i - 1]) : p.distanceTo(est.grupo.position)), 0);
    seguirPara(est.andar);
    estado.equipe.forEach((a) => { const e = estado.estacoes.get(a.id); if (e && e.situacao === "trabalhando") definirSituacao(a.id, "parado"); });
    definirSituacao(id, "trabalhando");
    narrar(`${est.agente.nome} (${est.agente.papel}) ${FRASE[id] || "está conferindo"} ${curto}`);
    estado.tocando = { ev, fim: performance.now() + (Math.min(3.5, distancia / 2.6) + (DURACAO_EXTRA[id] || 1.8) * velocidade) * 1000, id };
    return;
  }
  doc.faixa.material.color.set(est.agente.cor);
  const trocaAndar = est.andar !== doc.andar;
  const deslocamento = moverDocumento(doc, est.mesaPos, Math.min(900, dur * 450), est.andar);
  seguirPara(est.andar);
  estado.equipe.forEach((a) => { const e = estado.estacoes.get(a.id); if (e && e.situacao === "trabalhando") definirSituacao(a.id, "parado"); });
  definirSituacao(id, "trabalhando");
  const frase = FRASE[id] || FRASE[ev.etapa] || "está trabalhando em";
  narrar(`${trocaAndar ? `⬆ Subiu para o ${est.andar}º andar · ` : ""}${est.agente.nome} (${est.agente.papel || "agente"}) ${frase} ${curto}`);
  estado.tocando = { ev, fim: performance.now() + dur * 1000 + (trocaAndar ? deslocamento : 0), id };
}

function finalizarEvento() {
  const t = estado.tocando; estado.tocando = null;
  if (!t) return;
  if (t.id) { const e = estado.estacoes.get(t.id); if (e && e.situacao === "trabalhando") definirSituacao(t.id, "parado"); }
  if (t.final && t.doc) {
    raiz.remove(t.doc.g); estado.documentos.delete(t.doc.arquivo);
    if (t.final === "tratadas") empilhar(pilhaTratadas, caixaTratadas, "#dcfce7");
    else if (t.final === "erros") empilhar(pilhaErros, caixaErros, "#fee2e2");
    else if (t.final === "relatorios") empilhar(pilhasRelatorios[t.andarFinal], prateleiras[t.andarFinal].local, t.andarFinal === 3 ? "#dcfce7" : "#ede9fe", andares[t.andarFinal]);
  }
}

function narrar(texto) { $("#hud-agora").textContent = texto; }

// ------------------------------------------------------------------ interface lateral (equipe e ficha profissional)
const NOME_SITUACAO = { parado: "de plantão", trabalhando: "trabalhando", ok: "concluiu", erro: "barrou", prontidao: "de prontidão" };
const CLASSE_SITUACAO = { trabalhando: "trabalhando", ok: "ok", erro: "erro", prontidao: "prontidao" };

function linhaMembro(a) {
  const e = estado.estacoes.get(a.id); const sit = e?.situacao === "parado" && e.prontidao ? "prontidao" : e?.situacao || "parado";
  const n = estado.agentesNumeros[a.id];
  const detalhe = a.prontidao ? a.prontidao : n ? `${typeof n.valor === "string" ? n.valor : num(n.valor)} ${n.rotulo}` : a.habilidades.length ? `${a.habilidades.length} habilidade(s)` : a.papel;
  return { sit, detalhe };
}

let estruturaEquipe = "";
function desenharEquipe() {
  const caixa = $("#hud-equipe");
  const estrutura = JSON.stringify([listaAndares, estado.equipe.map((a) => [a.id, a.nome, a.papel, a.ficha?.nivel])]);
  if (estrutura !== estruturaEquipe) { // só remonta a lista quando a equipe muda (contratação, troca de andar...)
    estruturaEquipe = estrutura;
    const html = [];
    for (const andar of [...listaAndares].reverse()) {
      const membros = estado.equipe.filter((a) => andarDe(a) === andar);
      if (!membros.length) continue;
      html.push(`<h3><button class="link-andar" data-ir-andar="${andar}">${NOME_ANDAR[andar] || `${andar}º andar`} (${membros.length})</button></h3>`);
      for (const a of membros) {
        const nivel = a.ficha?.nivel ? `<em class="nivel">${esc(a.ficha.nivel)}</em>` : "";
        html.push(`<button class="membro" data-agente="${esc(a.id)}">
          <span class="avatar" style="background:${esc(a.cor)}">${esc(a.nome.slice(0, 1))}</span>
          <span class="info"><strong>${esc(a.nome)} · ${esc(a.papel)}</strong><small>${nivel}<span data-detalhe></span></small></span>
          <span class="estado" data-estado></span></button>`);
      }
    }
    html.push(`<div style="padding:10px 14px"><a class="btn pequeno" style="width:100%" href="inicio.html#agentes">Equipe, contratações e habilidades</a></div>`);
    caixa.innerHTML = html.join("");
  }
  // atualização leve: só textos e classes (o botão não sai do lugar enquanto você clica)
  for (const b of caixa.querySelectorAll("[data-agente]")) {
    const a = estado.equipe.find((x) => x.id === b.dataset.agente); if (!a) continue;
    const { sit, detalhe } = linhaMembro(a);
    b.classList.toggle("selecionado", estado.selecionado === a.id);
    const d = b.querySelector("[data-detalhe]"); if (d.textContent !== detalhe) d.textContent = detalhe;
    const st = b.querySelector("[data-estado]");
    if (st.textContent !== NOME_SITUACAO[sit]) { st.textContent = NOME_SITUACAO[sit]; st.className = `estado ${CLASSE_SITUACAO[sit] || ""}`; }
  }
}

function mostrarFicha(id) {
  const a = estado.equipe.find((x) => x.id === id);
  const ficha = $("#hud-ficha");
  if (!a) { ficha.hidden = true; estado.selecionado = null; desenharEquipe(); return; }
  estado.selecionado = id;
  const n = estado.agentesNumeros[id], f = a.ficha || {};
  const lista = (titulo, itens) => itens?.length ? `<div><div class="secao-titulo">${titulo}</div><ul class="ficha-lista">${itens.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : "";
  ficha.innerHTML = `<header><span class="avatar" style="background:${esc(a.cor)}">${esc(a.nome.slice(0, 1))}</span>
      <div><h2>${esc(a.nome)}</h2><span class="muted">${esc(f.cargo || a.papel)}</span></div>
      <button class="btn fantasma pequeno fechar" data-fechar aria-label="Fechar">✕</button></header>
    <div class="chips-colunas">${f.nivel ? `<span class="etiqueta info">${esc(f.nivel)}</span>` : ""}${f.area ? `<span class="etiqueta">${esc(f.area)}</span>` : ""}
      ${f.provas ? `<span class="etiqueta ${f.provas.aprovado ? "sucesso" : "perigo"}">Provas técnicas ${f.provas.acertos}/${f.provas.total}</span>` : ""}
      <span class="etiqueta">${(NOME_ANDAR[andarDe(a)] || `${andarDe(a)}º andar`).split(" · ")[0]}</span>
      ${f.gestor ? `<span class="etiqueta">Responde a ${esc(f.gestor)}</span>` : ""}</div>
    <p>${esc(a.descricao)}</p>
    ${a.prontidao ? `<p class="muted">Agora: ${esc(a.prontidao)}. Ninguém aqui dorme — sem arquivo, a pessoa estuda e revisa o próprio método.</p>` : ""}
    ${n ? `<div><div class="numero">${typeof n.valor === "string" ? esc(n.valor) : num(n.valor)}</div><span class="muted">${esc(n.rotulo)}</span></div>` : ""}
    ${lista("Metodologias e referências", f.metodologias)}
    ${lista("Responsabilidades", f.responsabilidades)}
    ${lista("Critérios de qualidade", f.criterios)}
    ${lista("O que não faz (limites)", f.limites)}
    ${a.aceita_habilidades ? `<div><div class="secao-titulo">Habilidades</div>${a.habilidades.length ? `<div class="chips-colunas">${a.habilidades.map((s) => `<span class="chip-coluna">${esc(s)}</span>`).join("")}</div>` : `<p class="muted">Nenhuma habilidade extra.</p>`}</div>` : ""}
    <div class="acoes"><a class="btn primario" href="inicio.html#conversa=${encodeURIComponent(a.id)}">Conversar com ${esc(a.nome)}</a>
    <a class="btn" href="inicio.html#agentes">Ver ficha completa no painel</a></div>`;
  ficha.hidden = false;
  const est = estado.estacoes.get(id);
  if (est && est.andar !== estado.andarVisivel && estado.andarVisivel !== "predio") definirAndarVisivel(est.andar);
  focarAgente(id);
  desenharEquipe();
}

let voo = null;
function focarAgente(id) {
  const e = estado.estacoes.get(id); if (!e) return;
  const alvo = new THREE.Vector3(); e.grupo.getWorldPosition(alvo); alvo.add(new THREE.Vector3(0, 1.2, 0.4));
  estado.ultimoManual = performance.now();
  voo = { t0: performance.now(), dur: 900, dePos: camera.position.clone(), deAlvo: controles.target.clone(),
          paraPos: alvo.clone().add(new THREE.Vector3(1.6, 3.4, 6.4)), paraAlvo: alvo };
}

$("#hud-equipe").addEventListener("click", (e) => {
  const andar = e.target.closest("[data-ir-andar]"); if (andar) return irParaAndar(Number(andar.dataset.irAndar), true);
  const b = e.target.closest("[data-agente]"); if (b) mostrarFicha(b.dataset.agente);
});
$("#hud-ficha").addEventListener("click", (e) => { if (e.target.closest("[data-fechar]")) irParaAndar(estado.andarVisivel, true); });
$("#andares").addEventListener("click", (e) => { const b = e.target.closest("[data-andar]"); if (b) irParaAndar(b.dataset.andar === "predio" ? "predio" : Number(b.dataset.andar), true); });
$("#btn-seguir").addEventListener("click", alternarSeguir);
$("#btn-agora").addEventListener("click", async () => {
  try { await api("/api/robo/processar-agora", {}); avisar("Processando a fila agora…"); } catch (e) { avisar(e.message, "erro"); }
});
$("#btn-enviar").addEventListener("click", () => {
  const input = document.createElement("input"); input.type = "file"; input.multiple = true; input.accept = ".xlsx,.xlsm,.xls,.csv,.txt";
  input.onchange = async () => {
    for (const f of input.files) {
      try { await api("/api/enviar", null, f); avisar(`${f.name} entregue na recepção`, "sucesso"); } catch (e) { avisar(`${f.name}: ${e.message}`, "erro"); }
    }
  };
  input.click();
});

// clique em um agente na cena (só o que está visível)
const raio = new THREE.Raycaster(), ponteiro = new THREE.Vector2();
const visivel = (o) => { for (let x = o; x; x = x.parent) if (!x.visible) return false; return true; };
const alvoNoPonteiro = () => raio.intersectObjects(clicaveis, false).find((i) => visivel(i.object));
let arrastou = false, inicioClique = null;
renderer.domElement.addEventListener("pointerdown", (e) => { inicioClique = [e.clientX, e.clientY]; arrastou = false; });
renderer.domElement.addEventListener("pointermove", (e) => {
  if (inicioClique && Math.hypot(e.clientX - inicioClique[0], e.clientY - inicioClique[1]) > 5) arrastou = true;
  ponteiro.set((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
  raio.setFromCamera(ponteiro, camera);
  renderer.domElement.style.cursor = alvoNoPonteiro() ? "pointer" : "grab";
});
renderer.domElement.addEventListener("pointerup", (e) => {
  inicioClique = null;
  if (arrastou) return;
  ponteiro.set((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
  raio.setFromCamera(ponteiro, camera);
  const alvo = alvoNoPonteiro();
  if (alvo) mostrarFicha(alvo.object.userData.agente);
});
addEventListener("resize", () => { camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); renderer.setSize(innerWidth, innerHeight); if (geo) enquadrarCameras(); });

// ------------------------------------------------------------------ dados do robô
// Prova de trabalho: anima "trabalhando" quem tem etapa de job aberta no servidor; quem saiu da lista volta ao plantão.
function mostrarTrabalhoReal(t) {
  const ids = new Set(t.ids || []);
  estado.porServidor = estado.porServidor || new Set();
  for (const id of ids) {
    const e = estado.estacoes.get(id);
    if (e && e.situacao !== "trabalhando") definirSituacao(id, "trabalhando");
  }
  for (const id of estado.porServidor) {
    const e = estado.estacoes.get(id);
    if (!ids.has(id) && e && e.situacao === "trabalhando" && !estado.tocando) definirSituacao(id, "parado");
  }
  estado.porServidor = ids;
  const el = $("#hud-real");
  if (!el) return;
  const min = t.ultima_planilha_min;
  const total = estado.equipe.length || "?";
  el.innerHTML = `<span><b>${ids.size} de ${total}</b> com trabalho real agora</span>` +
    `<span class="${min == null || min > 60 ? "vermelho" : ""}">${min == null ? "nenhuma planilha processada ainda" : `última planilha há <b>${min} min</b>`}</span>`;
}

async function atualizar() {
  try {
    const d = await api(`/api/escritorio?desde=${estado.ultimoSeq}`);
    estado.ligado = d.ligado; estado.fila = d.fila || []; estado.agentesNumeros = d.agentes || {};
    estado.bancoHabilitado = Boolean(d.banco_habilitado); estado.analiseHoje = d.analise_hoje || null; estado.excelHoje = d.excel_hoje || null; estado.canalHoje = d.canal_hoje || null; estado.ti = d.ti || null;
    const chave = JSON.stringify((d.equipe || []).map((a) => [a.id, a.nome, a.papel, a.cor, a.prontidao, a.andar, a.ronda, a.habilidades.length, a.ficha?.nivel])) + estado.bancoHabilitado;
    if (chave !== estado.chaveEquipe) {
      estado.chaveEquipe = chave; estado.equipe = d.equipe || [];
      estado.documentos.forEach((doc) => raiz.remove(doc.g)); estado.documentos.clear();
      montarPredio(estado.equipe);
    }
    const agora = Date.now() / 1000;
    for (const ev of d.eventos || []) {
      if (!estado.iniciado && agora - ev.ts > 20) continue; // ao abrir, não repete o que já passou
      if (ev.fala) { mostrarBalao(ev.etapa, ev.fala, ev.para); if (!ev.tarefa) continue; } // conversa: balão na hora
      estado.filaEventos.push(ev);
    }
    mostrarVivo(d.vivo || {});
    mostrarTrabalhoReal(d.trabalho_real || {});
    estado.ultimoSeq = Math.max(estado.ultimoSeq, d.ultimo_seq || 0);
    estado.iniciado = true;
    $("#hud-status").innerHTML = d.erro_config ? `<i class="ponto erro"></i>Configuração pendente`
      : d.ligado ? `<i class="ponto ligado"></i>Monitorando · ${estado.fila.length} na fila` : `<i class="ponto pausado"></i>Pausado`;
    if (!estado.tocando && !estado.filaEventos.length && !estado.documentos.size) {
      narrar(estado.fila.length ? `${estado.fila.length} arquivo(s) aguardando sincronização na recepção` : "Aguardando planilhas em Bases-Limpeza…");
    }
    atualizarPilhaEntrada(); desenharEquipe(); desenharTV(2); desenharTV(3); desenharTV(4); desenharTV(5);
  } catch {
    $("#hud-status").innerHTML = `<i class="ponto erro"></i>Sem conexão com o robô`;
  }
}
async function atualizarTV() {
  try { estado.kpis = (await api("/api/estado")).kpis; desenharTV(1); } catch { /* tenta de novo */ }
}

// ------------------------------------------------------------------ andarilhos (ronda e ida até o documento)
function andarAgente(e, dt, t) {
  const g = e.grupo, p = e.p;
  let alvo = null, velocidade = 0.9;
  if (e.situacao === "trabalhando" && e.caminho.length) { alvo = e.caminho[0]; velocidade = 2.6; }
  else if (e.situacao !== "trabalhando") {
    if (e.caminho.length && e.situacao === "parado") e.caminho = [];
    const r = e.ronda[e.alvoRonda]; alvo = new THREE.Vector3(r[0], 0, r[1]);
  }
  let andando = false;
  if (alvo) {
    const delta = alvo.clone().sub(g.position); delta.y = 0;
    const dist = delta.length();
    if (dist < 0.05) {
      if (e.situacao === "trabalhando") e.caminho.shift(); else e.alvoRonda = (e.alvoRonda + 1) % e.ronda.length;
    } else {
      g.position.add(delta.multiplyScalar(Math.min(1, (velocidade * dt) / dist)));
      const angulo = Math.atan2(alvo.x - g.position.x, alvo.z - g.position.z);
      g.rotation.y += Math.atan2(Math.sin(angulo - g.rotation.y), Math.cos(angulo - g.rotation.y)) * Math.min(1, dt * 8);
      andando = true;
    }
  }
  if (e.situacao === "trabalhando" && !e.caminho.length) { // chegou: vira para a mesa e confere a prancheta
    const deFrente = g.position.z < (geo.zFundo + geo.zFrente) / 2 + 0.6 ? Math.PI : 0;
    g.rotation.y += Math.atan2(Math.sin(deFrente - g.rotation.y), Math.cos(deFrente - g.rotation.y)) * Math.min(1, dt * 6);
    p.cabeca.rotation.x = 0.35; p.bracos[0].rotation.x = -1.3 + Math.sin(t * 3) * 0.05; p.bracos[1].rotation.x = -0.9;
  } else {
    p.cabeca.rotation.x = 0.05;
    p.bracos[0].rotation.x = andando ? -0.9 : -0.9; p.bracos[1].rotation.x = andando ? Math.sin(t * 7) * 0.45 : -0.15;
  }
  const passo = andando ? Math.sin(t * (velocidade > 1 ? 11 : 7)) * 0.5 : 0;
  if (p.pernas?.length) { p.pernas[0].rotation.x = passo; p.pernas[1].rotation.x = -passo; }
  p.tronco.position.y = p.alturaTronco + (andando ? Math.abs(Math.sin(t * 7)) * 0.03 : 0);
  if (e.selos.ok.visible || e.selos.erro.visible) for (const s of [e.selos.ok, e.selos.erro]) s.position.y = 2.15 + Math.sin(t * 4) * 0.05;
  const pos = new THREE.Vector3(); g.getWorldPosition(pos);
  e.etiqueta.material.opacity = e.agente.id === estado.selecionado ? 1 : Math.min(1, Math.max(0, (camera.position.distanceTo(pos) - 5) / 4));
}

// ------------------------------------------------------------------ animação
const relogio = new THREE.Clock();
let ultimoQuadro = performance.now();
// ------------------------------------------------------------------ balões de conversa em cima de cada pessoa
const baloes = new Map(); // id → {el, ate}
// O que foi REGISTRADO no banco vira balão: conversas (com o horário real) e cada tentativa de treino (✔/✘).
const vivo = { conversa: 0, treino: 0, iniciado: false };
function haQuanto(iso) {
  const seg = Math.max(0, (Date.now() - new Date(String(iso).replace(" ", "T")).getTime()) / 1000);
  if (!isFinite(seg)) return "";
  return seg < 60 ? "agora" : seg < 3600 ? `há ${Math.round(seg / 60)} min` : seg < 86400 ? `há ${Math.round(seg / 3600)} h` : `há ${Math.round(seg / 86400)} d`;
}
function mostrarVivo(v) {
  const conversas = (v.conversas || []).slice().reverse(), treino = (v.treino || []).slice().reverse();
  if (!vivo.iniciado) {  // ao abrir: as últimas conversas reais, uma por vez, com o horário em que aconteceram
    vivo.iniciado = true;
    conversas.slice(-6).forEach((c, i) => setTimeout(() => mostrarBalao(c.de, c.texto, c.para, haQuanto(c.data_hora)), 900 + i * 2600));
    vivo.conversa = Math.max(0, ...conversas.map((c) => c.id));
    vivo.treino = Math.max(0, ...treino.map((t) => t.id));
    return;
  }
  for (const c of conversas) if (c.id > vivo.conversa) { mostrarBalao(c.de, c.texto, c.para, haQuanto(c.data_hora)); vivo.conversa = c.id; }
  for (const t of treino) if (t.id > vivo.treino) {
    mostrarBalao(t.funcionario, `${t.acertou ? "✔ acertei" : "✘ errei"} ${t.competencia} · nível ${t.nivel}`, null, "treino", t.acertou ? "ok" : "erro");
    vivo.treino = t.id;
  }
}
function mostrarBalao(id, texto, para, quando, tom) {
  const est = estado.estacoes.get(id); if (!est) return;
  let b = baloes.get(id);
  if (!b) {
    const el = document.createElement("div"); el.className = "balao-fala";
    el.style.cssText = "position:fixed;z-index:20;max-width:240px;padding:8px 10px;border-radius:12px;background:#fff;color:#111827;" +
      "font:12px/1.35 system-ui,sans-serif;box-shadow:0 6px 18px rgba(0,0,0,.18);pointer-events:none;transform:translate(-50%,-100%)";
    document.body.appendChild(el); b = { el }; baloes.set(id, b);
  }
  const nomePara = para && estado.estacoes.get(para) ? `<b>→ ${esc(estado.estacoes.get(para).agente.nome)}</b> ` : "";
  b.el.innerHTML = `<b>${esc(est.agente.nome)}</b>: ${nomePara}${esc(texto)}` +
    (quando ? `<div style="margin-top:3px;font-size:10.5px;color:#64748b">${esc(quando)}</div>` : "");
  b.el.style.borderLeft = tom === "ok" ? "4px solid #059669" : tom === "erro" ? "4px solid #dc2626" : "4px solid #2563eb";
  b.ate = performance.now() + 8000;
  if (baloes.size > 8) { const [velho] = [...baloes.entries()].sort((a, c) => a[1].ate - c[1].ate); velho[1].el.remove(); baloes.delete(velho[0]); }
}
const _vetorBalao = new THREE.Vector3();
function posicionarBaloes(agora) {
  if (!baloes.size) return;
  // o balão nunca fica por baixo da barra do topo nem da lista da equipe (à direita): encosta na borda livre
  const topo = document.querySelector(".hud-topo")?.getBoundingClientRect().bottom || 0;
  const lista = document.getElementById("hud-equipe");
  const direita = lista && lista.offsetParent ? lista.getBoundingClientRect().left : innerWidth;
  for (const [id, b] of baloes) {
    const est = estado.estacoes.get(id);
    if (!est || agora > b.ate) { b.el.remove(); baloes.delete(id); continue; }
    if (!andares[est.andar]?.visible) { b.el.style.display = "none"; continue; }
    est.grupo.getWorldPosition(_vetorBalao); _vetorBalao.y += 2.3;
    _vetorBalao.project(camera);
    const fora = _vetorBalao.z > 1 || Math.abs(_vetorBalao.x) > 1.1 || Math.abs(_vetorBalao.y) > 1.1;
    b.el.style.display = fora ? "none" : "block";
    const w = b.el.offsetWidth, h = b.el.offsetHeight;
    const x = Math.min(Math.max((_vetorBalao.x + 1) / 2 * innerWidth, w / 2 + 8), Math.max(w / 2 + 8, direita - w / 2 - 8));
    const y = Math.max((1 - _vetorBalao.y) / 2 * innerHeight, topo + h + 8);
    b.el.style.left = `${x}px`;
    b.el.style.top = `${y}px`;
    b.el.style.opacity = Math.min(1, (b.ate - agora) / 800).toFixed(2);
  }
}

function animar() {
  requestAnimationFrame(animar);
  posicionarBaloes(performance.now());
  const t = relogio.getElapsedTime(), agora = performance.now();
  const dt = Math.min(0.05, (agora - ultimoQuadro) / 1000); ultimoQuadro = agora;

  if (!estado.tocando && estado.filaEventos.length) iniciarEvento(estado.filaEventos.shift());
  if (estado.tocando && agora >= estado.tocando.fim) finalizarEvento();

  for (const [id, e] of estado.estacoes) {
    if (e.ate && agora > e.ate) definirSituacao(id, "parado");
    if (e.movel) andarAgente(e, dt, t);
    if (!andares[e.andar]?.visible) continue;
    if (e.movel) { e.anel.rotation.z += 0.06; continue; }
    const fase = e.semente % 100;
    const { tronco, cabeca, bracos } = e.p;
    if (e.situacao === "trabalhando") {
      bracos[0].rotation.x = -1.2 + Math.sin(t * 18 + fase) * 0.12;
      bracos[1].rotation.x = -1.2 + Math.sin(t * 18 + fase + 1.6) * 0.12;
      cabeca.rotation.x = 0.18 + Math.sin(t * 3) * 0.04;
      cabeca.rotation.y = Math.sin(t * 1.5 + fase) * 0.12;
      e.anel.rotation.z += 0.08;
      tronco.position.y = e.p.alturaTronco + Math.abs(Math.sin(t * 9)) * 0.012;
    } else if (e.situacao === "erro") {
      bracos[1].rotation.x = -2.9 + Math.sin(t * 8) * 0.15; bracos[0].rotation.x = -1.15; cabeca.rotation.x = -0.1;
    } else if (e.situacao === "ok") {
      bracos[0].rotation.x = -2.6; bracos[1].rotation.x = -2.6;
      tronco.position.y = e.p.alturaTronco + Math.abs(Math.sin(t * 6)) * 0.05;
    } else if (e.prontidao) { // estudando: lê no notebook e digita devagar, olhando a tela
      bracos[0].rotation.x = -1.15 + Math.sin(t * 5 + fase) * 0.06;
      bracos[1].rotation.x = -1.15 + Math.sin(t * 5 + fase + 2) * 0.06;
      cabeca.rotation.x = 0.22 + Math.sin(t * 0.7 + fase) * 0.04; cabeca.rotation.y = Math.sin(t * 0.5 + fase) * 0.1;
      e.selos.estudo.position.y = 2.0 + Math.sin(t * 1.5) * 0.06;
    } else {
      bracos[0].rotation.x += (-1.0 - bracos[0].rotation.x) * 0.1;
      bracos[1].rotation.x += (-1.0 - bracos[1].rotation.x) * 0.1;
      cabeca.rotation.x = Math.sin(t * 0.8 + fase) * 0.05;
      cabeca.rotation.y = Math.sin(t * 0.35 + fase) * 0.35;
      tronco.position.y = e.p.alturaTronco + Math.sin(t * 1.6 + fase) * 0.006;
    }
    for (const s of [e.selos.ok, e.selos.erro]) if (s.visible) s.position.y = 2.0 + Math.sin(t * 4) * 0.05;
    const pos = new THREE.Vector3(); e.grupo.getWorldPosition(pos);
    const distancia = camera.position.distanceTo(pos);
    e.etiqueta.material.opacity = id === estado.selecionado ? 1 : Math.min(1, Math.max(0, (distancia - 5) / 4));
  }
  const bancoTrabalhando = estado.estacoes.get("banco")?.situacao === "trabalhando";
  leds.forEach((led, i) => {
    const aceso = bancoTrabalhando ? Math.random() > 0.45 : Math.sin(t * 2 + i) > 0.6;
    led.material.emissiveIntensity = estado.bancoHabilitado ? (aceso ? 1.8 : 0.15) : 0.05;
  });

  for (const doc of estado.documentos.values()) {
    doc.g.visible = Boolean(andares[doc.andar]?.visible);
    const seg = doc.rota[0];
    if (!seg) continue;
    if (!seg.t0) { seg.t0 = agora; seg.de = doc.g.position.clone(); }
    const k = Math.min(1, (agora - seg.t0) / seg.dur), s = k * k * (3 - 2 * k);
    doc.g.position.lerpVectors(seg.de, seg.para, s);
    if (seg.salto) { doc.g.position.y += Math.sin(Math.PI * s) * 1.1; doc.g.rotation.y = Math.sin(Math.PI * s) * 0.6; }
    if (seg.vertical && elevador) { elevador.cabine.position.y = doc.g.position.y - 1.0; doc.g.visible = true; }
    if (k >= 1) doc.rota.shift();
  }

  caminhar(dt);
  if (voo) {
    const k = Math.min(1, (agora - voo.t0) / voo.dur), s = k * k * (3 - 2 * k);
    camera.position.lerpVectors(voo.dePos, voo.paraPos, s);
    controles.target.lerpVectors(voo.deAlvo, voo.paraAlvo, s);
    if (k >= 1) { const fim = voo.aoTerminar; voo = null; if (fim) fim(); }
  }
  controles.update();
  renderer.render(cena, camera);
}

await atualizar();
await atualizarTV();
animar();
setInterval(atualizar, 1000);
setInterval(atualizarTV, 4000);
