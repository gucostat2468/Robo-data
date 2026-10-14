/* =====================================================================
   Escritório 3D — cada agente é uma etapa REAL do robô.
   A cena é montada a partir da equipe configurada (agentes nativos + os seus)
   e anima os eventos que o pipeline publica em /api/escritorio.
   Three.js está embutido em ./vendor (funciona sem internet).
   ===================================================================== */
import * as THREE from "three";
import { OrbitControls } from "./vendor/OrbitControls.js";

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
  s.scale.set(0.55, 0.55, 1); s.visible = false;
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

function criarPersonagem(cor, semente) {
  const g = new THREE.Group();
  const pele = mat(PELES[semente % PELES.length]);
  const cabelo = mat(CABELOS[(semente >>> 3) % CABELOS.length]);
  const calca = mat(ESCURO ? "#3a4256" : "#33405a");
  for (const lado of [-1, 1]) {
    g.add(caixa(0.17, 0.16, 0.5, calca, lado * 0.12, 0.62, 0.22));
    g.add(caixa(0.15, 0.5, 0.15, calca, lado * 0.12, 0.34, 0.45));
    g.add(caixa(0.17, 0.08, 0.26, mat("#222"), lado * 0.12, 0.05, 0.52));
  }
  const tronco = new THREE.Group(); tronco.position.y = 0.66; g.add(tronco);
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
    ombro.rotation.x = -1.15; ombro.rotation.z = lado * -0.12;
    bracos.push(ombro);
  }
  return { grupo: g, tronco, cabeca, bracos };
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
const estado = {
  equipe: [], estacoes: new Map(), ultimoSeq: 0, iniciado: false, chaveEquipe: "",
  fila: [], filaEventos: [], tocando: null, documentos: new Map(), selecionado: null,
  ligado: false, bancoHabilitado: false, agentesNumeros: {}, kpis: null,
};
let raiz = new THREE.Group(); cena.add(raiz);
let caixaEntrada, caixaTratadas, caixaErros, pilhaEntrada = [], pilhaTratadas = [], pilhaErros = [], tvTextura, tvCanvas, leds = [];
const clicaveis = [];

const ETAPA_NATIVA = new Set(["recepcao", "leitura", "limpeza", "validacao", "modelagem", "banco", "publicacao"]);

function montarEscritorio(equipe) {
  cena.remove(raiz); raiz = new THREE.Group(); cena.add(raiz);
  estado.estacoes.clear(); clicaveis.length = 0; leds = [];
  pilhaEntrada = []; pilhaTratadas = []; pilhaErros = [];

  const n = equipe.length, porFileira = Math.ceil(n / 2), espaco = 3.9;
  const colX = (c) => (c - (porFileira - 1) / 2) * espaco;
  const zFundo = -1.5, zFrente = 3.3;
  const minX = colX(0) - 6.2, maxX = colX(porFileira - 1) + 4.2;
  const largura = maxX - minX, profundidade = 11.5, zParede = -4.6;

  // piso, tapete do fluxo, paredes e janelas
  const piso = caixa(largura, 0.2, profundidade, mat(ESCURO ? "#3b3631" : "#e7dccb"), (minX + maxX) / 2, -0.1, zParede + profundidade / 2, false);
  piso.receiveShadow = true; raiz.add(piso);
  for (let i = 0; i < Math.floor(largura / 1.2); i++) {
    raiz.add(caixa(0.02, 0.005, profundidade, mat(ESCURO ? "#35302b" : "#dccfbb"), minX + i * 1.2, 0.003, zParede + profundidade / 2, false));
  }
  raiz.add(caixa(largura - 3, 0.01, 0.9, mat(ESCURO ? "#2b3550" : "#cdd8ea"), (minX + maxX) / 2 + 0.6, 0.01, zFundo + 1.55, false));
  raiz.add(caixa(largura - 3, 0.01, 0.9, mat(ESCURO ? "#2b3550" : "#cdd8ea"), (minX + maxX) / 2 + 0.6, 0.01, zFrente + 1.55, false));
  const corParede = mat(ESCURO ? "#262c39" : "#f3efe8");
  raiz.add(caixa(largura, 3.6, 0.2, corParede, (minX + maxX) / 2, 1.8, zParede, false));
  raiz.add(caixa(0.2, 3.6, profundidade, corParede, minX, 1.8, zParede + profundidade / 2, false));
  raiz.add(caixa(largura, 0.14, 0.24, mat(ESCURO ? "#1d222d" : "#d9d2c6"), (minX + maxX) / 2, 0.07, zParede + 0.02, false));
  const vidro = new THREE.MeshStandardMaterial({ color: ESCURO ? "#24345e" : "#bfe0ff", emissive: ESCURO ? "#1b2a55" : "#a8d4ff", emissiveIntensity: ESCURO ? 0.7 : 0.35 });
  for (const x of [minX + 3.2, maxX - 3.2]) {
    raiz.add(caixa(3.2, 1.8, 0.05, vidro, x, 2.0, zParede + 0.12, false));
    raiz.add(caixa(3.4, 0.08, 0.1, mat("#ffffff"), x, 1.06, zParede + 0.14, false));
    raiz.add(caixa(0.06, 1.8, 0.08, mat("#ffffff"), x, 2.0, zParede + 0.14, false));
  }

  // TV com os números do dia
  tvCanvas = document.createElement("canvas"); tvCanvas.width = 1024; tvCanvas.height = 512;
  tvTextura = new THREE.CanvasTexture(tvCanvas); tvTextura.colorSpace = THREE.SRGBColorSpace;
  raiz.add(caixa(4.3, 2.35, 0.1, mat("#15181f"), (minX + maxX) / 2, 2.25, zParede + 0.14, false));
  const tela = new THREE.Mesh(new THREE.PlaneGeometry(4.1, 2.15), new THREE.MeshBasicMaterial({ map: tvTextura, toneMapped: false }));
  tela.position.set((minX + maxX) / 2, 2.25, zParede + 0.2); raiz.add(tela);
  desenharTV();

  // caixa de entrada (Bases-Limpeza)
  const xEntrada = colX(0) - 3.4;
  const mesaEntrada = new THREE.Group();
  mesaEntrada.add(caixa(1.4, 0.06, 0.9, mat("#f7f4ef"), 0, 0.76, 0));
  for (const [x, z] of [[-0.62, -0.38], [0.62, -0.38], [-0.62, 0.38], [0.62, 0.38]]) mesaEntrada.add(caixa(0.06, 0.74, 0.06, mat("#8b6b4a"), x, 0.37, z));
  mesaEntrada.add(caixa(0.7, 0.12, 0.5, mat("#f0b429"), 0, 0.85, 0));
  mesaEntrada.position.set(xEntrada, 0, zFundo + 0.3); raiz.add(mesaEntrada);
  const pEntrada = placa("Bases-Limpeza", "#b7791f"); pEntrada.position.set(xEntrada, 1.75, zFundo + 0.3); raiz.add(pEntrada);
  caixaEntrada = new THREE.Vector3(xEntrada, 0.93, zFundo + 0.3);

  // caixas de saída (Bases-Tratadas e Bases-Erros)
  const xSaida = colX(0) - 3.4;
  const caixote = (cor, z, texto) => {
    const g = new THREE.Group();
    g.add(caixa(1.2, 0.7, 0.9, mat(cor), 0, 0.35, 0));
    g.add(caixa(1.05, 0.05, 0.75, mat("#ffffff"), 0, 0.71, 0, false));
    g.position.set(xSaida, 0, z); raiz.add(g);
    const p = placa(texto, cor); p.position.set(xSaida, 1.45, z); raiz.add(p);
    return new THREE.Vector3(xSaida, 0.74, z);
  };
  caixaTratadas = caixote("#16a34a", zFrente + 0.1, "Bases-Tratadas");
  caixaErros = caixote("#dc2626", zFrente + 1.6, "Bases-Erros");

  // estações: fileira do fundo da esquerda para a direita; da frente, da direita para a esquerda
  equipe.forEach((ag, i) => {
    const fundo = i < porFileira;
    const coluna = fundo ? i : porFileira - 1 - (i - porFileira);
    const x = colX(coluna), z = fundo ? zFundo : zFrente;
    const semente = hashTexto(ag.id);
    const grupo = new THREE.Group(); grupo.position.set(x, 0, z); raiz.add(grupo);
    const mesa = criarMesa(ag.cor); mesa.grupo.position.z = 0.72; grupo.add(mesa.grupo);
    const cadeira = criarCadeira(); cadeira.position.z = -0.12; grupo.add(cadeira);
    const p = criarPersonagem(ag.cor, semente); grupo.add(p.grupo);
    const sub = !ag.ativo ? "desligado" : ag.id === "banco" && !estado.bancoHabilitado ? "banco desligado" : ag.papel;
    const etiqueta = rotulo(ag.nome, sub, ag.cor); etiqueta.position.set(0, 2.45, 0); grupo.add(etiqueta);
    etiqueta.scale.set(2.6, 0.81, 1);
    const anel = new THREE.Mesh(new THREE.TorusGeometry(0.3, 0.035, 8, 40), new THREE.MeshStandardMaterial({ color: ag.cor, emissive: ag.cor, emissiveIntensity: 0.8 }));
    anel.rotation.x = Math.PI / 2; anel.position.y = 1.98; anel.visible = false; grupo.add(anel);
    const ok = selo("✓", "#16a34a"), erro = selo("!", "#dc2626"), zz = selo("z", "#94a3b8");
    for (const s of [ok, erro, zz]) { s.position.set(0.42, 2.0, 0.1); grupo.add(s); }
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
    p.grupo.traverse((o) => { if (o.isMesh) { o.userData.agente = ag.id; clicaveis.push(o); } });
    mesa.grupo.traverse((o) => { if (o.isMesh) { o.userData.agente = ag.id; clicaveis.push(o); } });
    const inativo = !ag.ativo || (ag.id === "banco" && !estado.bancoHabilitado);
    if (inativo) { mesa.tampa.rotation.x = 1.45; zz.visible = true; }
    estado.estacoes.set(ag.id, {
      agente: ag, grupo, p, mesa, anel, etiqueta, selos: { ok, erro, zz }, inativo, semente,
      mesaPos: new THREE.Vector3(x + 0.52, 0.86, z + 0.77), situacao: inativo ? "desligado" : "parado", ate: 0, trabalho: 0,
    });
  });

  // decoração
  raiz.add(criarPlanta(minX + 0.8, zParede + 0.8, 1.2));
  raiz.add(criarPlanta(maxX - 0.8, zParede + 0.8, 1.1));
  raiz.add(criarPlanta(maxX - 0.8, zFrente + 2.6, 0.9));
  const sofa = new THREE.Group(); sofa.position.set(maxX - 1.6, 0, zFrente + 0.4); sofa.rotation.y = -Math.PI / 2;
  sofa.add(caixa(2.2, 0.42, 0.85, mat("#5b6b8c"), 0, 0.3, 0)); sofa.add(caixa(2.2, 0.6, 0.22, mat("#56658a"), 0, 0.62, -0.32));
  raiz.add(sofa);

  enquadrarCamera(minX, maxX, zParede);
}

let enquadramento = null;
function enquadrarCamera(minX, maxX, zParede) {
  const largura = maxX - minX;
  const temPainel = innerWidth >= 900;
  // o painel da equipe ocupa ~300 px à direita: desloca o centro para o escritório caber na área livre
  const cx = (minX + maxX) / 2 + (temPainel ? largura * 300 / innerWidth * 0.32 : 0);
  const aspecto = innerWidth / innerHeight;
  const dist = Math.max(17, largura * (aspecto < 1.6 ? 1.18 : 1.04)) * (temPainel ? 1.08 : 1.3);
  enquadramento = { pos: new THREE.Vector3(cx + 1.2, dist * 0.6, zParede + 4.8 + dist * 0.8), alvo: new THREE.Vector3(cx + 0.8, 0.4, zParede + 5.6) };
  if (!estado.iniciado) { camera.position.copy(enquadramento.pos); controles.target.copy(enquadramento.alvo); controles.update(); }
}

// ------------------------------------------------------------------ TV
function desenharTV() {
  if (!tvCanvas) return;
  const ctx = tvCanvas.getContext("2d"), l = 1024, a = 512, k = estado.kpis || {};
  const grad = ctx.createLinearGradient(0, 0, l, a); grad.addColorStop(0, "#0f1b3d"); grad.addColorStop(1, "#1d3fb0");
  ctx.fillStyle = grad; ctx.fillRect(0, 0, l, a);
  ctx.fillStyle = "rgba(255,255,255,.85)"; ctx.font = "600 34px Segoe UI, system-ui, sans-serif";
  ctx.fillText("HOJE NO ESCRITÓRIO", 48, 70);
  ctx.textAlign = "right"; ctx.fillStyle = estado.ligado ? "#7fe0b4" : "#f5b445";
  ctx.fillText(estado.ligado ? "● Monitorando" : "● Pausado", l - 48, 70); ctx.textAlign = "left";
  const blocos = [["Aprovados", k.hoje_sucesso ?? 0, "#7fe0b4"], ["Reprovados", k.hoje_reprovado ?? 0, "#ff9a85"],
    ["Na fila", estado.fila.length, "#ffd27a"], ["Linhas", k.hoje_linhas ?? 0, "#a9c1ff"]];
  blocos.forEach(([t, v, c], i) => {
    const x = 48 + i * 238;
    ctx.fillStyle = "rgba(255,255,255,.08)"; retanguloArredondado(ctx, x, 120, 216, 300, 20); ctx.fill();
    ctx.fillStyle = c; ctx.font = "700 92px Segoe UI, system-ui, sans-serif"; ctx.fillText(num(v), x + 22, 290, 180);
    ctx.fillStyle = "rgba(255,255,255,.8)"; ctx.font = "500 34px Segoe UI, system-ui, sans-serif"; ctx.fillText(t, x + 22, 360);
  });
  ctx.fillStyle = "rgba(255,255,255,.55)"; ctx.font = "400 26px Segoe UI, system-ui, sans-serif";
  ctx.fillText(`Atualizado ${new Date().toLocaleTimeString("pt-BR")}`, 48, 475);
  if (tvTextura) tvTextura.needsUpdate = true;
}

// ------------------------------------------------------------------ documentos (papel que anda entre as mesas)
function novoDocumento(arquivo) {
  const g = new THREE.Group();
  g.add(caixa(0.34, 0.02, 0.44, mat("#ffffff"), 0, 0, 0));
  const faixa = caixa(0.34, 0.025, 0.08, new THREE.MeshStandardMaterial({ color: "#2654d9" }), 0, 0.002, -0.17);
  g.add(faixa);
  g.position.copy(caixaEntrada); raiz.add(g);
  const doc = { arquivo, g, faixa, de: g.position.clone(), para: g.position.clone(), t0: 0, dur: 0 };
  estado.documentos.set(arquivo, doc);
  return doc;
}
function moverDocumento(doc, destino, dur) {
  doc.de = doc.g.position.clone(); doc.para = destino.clone(); doc.t0 = performance.now(); doc.dur = dur;
}
function empilhar(pilha, base, cor) {
  const folha = caixa(0.34, 0.02, 0.44, mat(cor), base.x + (Math.random() - 0.5) * 0.12, base.y + 0.01 + pilha.length * 0.025, base.z + (Math.random() - 0.5) * 0.1);
  folha.rotation.y = (Math.random() - 0.5) * 0.4; raiz.add(folha); pilha.push(folha);
  if (pilha.length > 14) raiz.remove(pilha.shift());
}
function atualizarPilhaEntrada() {
  const alvo = Math.min(8, Math.max(0, estado.fila.length - (estado.tocando ? 1 : 0)));
  while (pilhaEntrada.length > alvo) raiz.remove(pilhaEntrada.pop());
  while (pilhaEntrada.length < alvo) empilhar(pilhaEntrada, caixaEntrada, "#ffffff");
}

// ------------------------------------------------------------------ reprodução dos eventos reais
const DURACAO = { recepcao: 1.2, leitura: 1.6, limpeza: 1.8, validacao: 1.6, modelagem: 1.6, banco: 1.7, publicacao: 1.4, concluido: 1.6, adiado: 1.3 };
const FRASE = {
  recepcao: "recebeu", leitura: "está lendo", limpeza: "está limpando", validacao: "está auditando",
  modelagem: "está modelando para o Power BI", banco: "está carregando no PostgreSQL", publicacao: "está publicando",
};

function idAgente(etapa) {
  if (etapa.startsWith("agente:")) return etapa.slice(7);
  return ETAPA_NATIVA.has(etapa) ? etapa : null;
}

function definirSituacao(id, situacao, segundos = 0) {
  const e = estado.estacoes.get(id); if (!e) return;
  e.situacao = situacao; e.ate = segundos ? performance.now() + segundos * 1000 : 0;
  e.anel.visible = situacao === "trabalhando";
  e.selos.ok.visible = situacao === "ok"; e.selos.erro.visible = situacao === "erro";
  e.selos.zz.visible = situacao === "desligado";
  e.mesa.logo.material.emissiveIntensity = situacao === "trabalhando" ? 1.6 : 0.15;
  desenharEquipe();
}

function iniciarEvento(ev) {
  const velocidade = estado.filaEventos.length > 10 ? 0.35 : estado.filaEventos.length > 4 ? 0.6 : 1;
  const dur = (DURACAO[ev.etapa] || 1.4) * velocidade;
  const curto = ev.arquivo.length > 38 ? `${ev.arquivo.slice(0, 35)}…` : ev.arquivo;
  let doc = estado.documentos.get(ev.arquivo);

  if (ev.etapa === "concluido" || ev.etapa === "adiado") {
    doc = doc || novoDocumento(ev.arquivo);
    const pub = "publicacao";
    if (ev.etapa === "adiado") {
      doc.faixa.material.color.set("#f59e0b"); moverDocumento(doc, caixaEntrada, dur * 1000);
      definirSituacao(pub, "parado"); narrar(`⏳ ${curto} adiado — o robô tenta de novo em instantes`);
    } else if (ev.status === "sucesso") {
      doc.faixa.material.color.set("#16a34a"); moverDocumento(doc, caixaTratadas.clone().add(new THREE.Vector3(0, 0.3, 0)), dur * 1000);
      definirSituacao(pub, "ok", 2.2);
      narrar(`✅ ${curto} aprovado — ${num(ev.linhas)} linhas prontas em Bases-Tratadas${ev.banco ? " e no PostgreSQL" : ""}`);
    } else {
      doc.faixa.material.color.set("#dc2626"); moverDocumento(doc, caixaErros.clone().add(new THREE.Vector3(0, 0.3, 0)), dur * 1000);
      definirSituacao("validacao", "erro", 3); definirSituacao(pub, "parado");
      narrar(`⛔ ${curto} reprovado — ${num(ev.erros)} erro(s). Veja em Reprovados no painel`);
    }
    estado.tocando = { ev, fim: performance.now() + dur * 1000, doc, final: ev.etapa === "adiado" ? "entrada" : ev.status === "sucesso" ? "tratadas" : "erros" };
    return;
  }

  const id = idAgente(ev.etapa);
  const est = id && estado.estacoes.get(id);
  if (!est) { estado.tocando = { ev, fim: performance.now() + 50 }; return; }
  doc = doc || novoDocumento(ev.arquivo);
  doc.faixa.material.color.set(est.agente.cor);
  moverDocumento(doc, est.mesaPos, Math.min(900, dur * 450));
  estado.equipe.forEach((a) => { const e = estado.estacoes.get(a.id); if (e && e.situacao === "trabalhando") definirSituacao(a.id, e.inativo ? "desligado" : "parado"); });
  definirSituacao(id, "trabalhando");
  const frase = FRASE[ev.etapa] || "está trabalhando em";
  narrar(`${est.agente.nome} (${est.agente.papel || "agente"}) ${frase} ${curto}`);
  estado.tocando = { ev, fim: performance.now() + dur * 1000, id };
}

function finalizarEvento() {
  const t = estado.tocando; estado.tocando = null;
  if (!t) return;
  if (t.id) { const e = estado.estacoes.get(t.id); if (e && e.situacao === "trabalhando") definirSituacao(t.id, "parado"); }
  if (t.final && t.doc) {
    raiz.remove(t.doc.g); estado.documentos.delete(t.doc.arquivo);
    if (t.final === "tratadas") empilhar(pilhaTratadas, caixaTratadas, "#dcfce7");
    else if (t.final === "erros") empilhar(pilhaErros, caixaErros, "#fee2e2");
  }
}

function narrar(texto) { $("#hud-agora").textContent = texto; }

// ------------------------------------------------------------------ interface lateral (equipe e ficha)
const NOME_SITUACAO = { parado: "livre", trabalhando: "trabalhando", ok: "concluiu", erro: "barrou", desligado: "desligado" };
const CLASSE_SITUACAO = { trabalhando: "trabalhando", ok: "ok", erro: "erro", desligado: "desligado" };

function desenharEquipe() {
  const html = [`<h3>Equipe (${estado.equipe.length})</h3>`];
  for (const a of estado.equipe) {
    const e = estado.estacoes.get(a.id); const sit = e?.situacao || "parado";
    const n = estado.agentesNumeros[a.id];
    const detalhe = n ? `${num(n.valor)} ${n.rotulo}` : a.skills.length ? `${a.skills.length} skill(s)` : a.papel;
    html.push(`<button class="membro ${estado.selecionado === a.id ? "selecionado" : ""}" data-agente="${esc(a.id)}">
      <span class="avatar" style="background:${esc(a.cor)}">${esc(a.nome.slice(0, 1))}</span>
      <span class="info"><strong>${esc(a.nome)} · ${esc(a.papel)}</strong><small>${esc(detalhe)}</small></span>
      <span class="estado ${CLASSE_SITUACAO[sit] || ""}">${NOME_SITUACAO[sit]}</span></button>`);
  }
  html.push(`<div style="padding:10px 14px"><a class="btn pequeno" style="width:100%" href="index.html#agentes">Gerenciar agentes e skills</a></div>`);
  $("#hud-equipe").innerHTML = html.join("");
}

function mostrarFicha(id) {
  const a = estado.equipe.find((x) => x.id === id);
  const ficha = $("#hud-ficha");
  if (!a) { ficha.hidden = true; estado.selecionado = null; desenharEquipe(); return; }
  estado.selecionado = id;
  const n = estado.agentesNumeros[id];
  ficha.innerHTML = `<header><span class="avatar" style="background:${esc(a.cor)}">${esc(a.nome.slice(0, 1))}</span>
      <div><h2>${esc(a.nome)}</h2><span class="muted">${esc(a.papel)}${a.nativo ? " · nativo" : ""}</span></div>
      <button class="btn fantasma pequeno fechar" data-fechar aria-label="Fechar">✕</button></header>
    <p>${esc(a.descricao)}</p>
    ${n ? `<div><div class="numero">${num(n.valor)}</div><span class="muted">${esc(n.rotulo)}</span></div>` : ""}
    ${a.aceita_skills ? `<div><div class="secao-titulo">Skills</div>${a.skills.length ? `<div class="chips-colunas">${a.skills.map((s) => `<span class="chip-coluna">${esc(s)}</span>`).join("")}</div>` : `<p class="muted">Nenhuma skill extra.</p>`}</div>
      <a class="btn" href="index.html#agentes">Configurar skills</a>` : `<p class="muted">Agente de infraestrutura: não usa skills de dados.</p>`}`;
  ficha.hidden = false;
  focarAgente(id);
  desenharEquipe();
}

let voo = null;
function focarAgente(id) {
  const e = estado.estacoes.get(id); if (!e) return;
  const alvo = e.grupo.position.clone().add(new THREE.Vector3(0, 1.2, 0.4));
  voo = { t0: performance.now(), dur: 900, dePos: camera.position.clone(), deAlvo: controles.target.clone(),
          paraPos: alvo.clone().add(new THREE.Vector3(1.6, 3.4, 6.4)), paraAlvo: alvo };
}
function visaoGeral() {
  if (!enquadramento) return;
  voo = { t0: performance.now(), dur: 900, dePos: camera.position.clone(), deAlvo: controles.target.clone(),
          paraPos: enquadramento.pos.clone(), paraAlvo: enquadramento.alvo.clone() };
  $("#hud-ficha").hidden = true; estado.selecionado = null; desenharEquipe();
}

$("#hud-equipe").addEventListener("click", (e) => { const b = e.target.closest("[data-agente]"); if (b) mostrarFicha(b.dataset.agente); });
$("#hud-ficha").addEventListener("click", (e) => { if (e.target.closest("[data-fechar]")) visaoGeral(); });
$("#btn-camera").addEventListener("click", visaoGeral);
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

// clique em um agente na cena
const raio = new THREE.Raycaster(), ponteiro = new THREE.Vector2();
let arrastou = false, inicioClique = null;
renderer.domElement.addEventListener("pointerdown", (e) => { inicioClique = [e.clientX, e.clientY]; arrastou = false; });
renderer.domElement.addEventListener("pointermove", (e) => {
  if (inicioClique && Math.hypot(e.clientX - inicioClique[0], e.clientY - inicioClique[1]) > 5) arrastou = true;
  ponteiro.set((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
  raio.setFromCamera(ponteiro, camera);
  renderer.domElement.style.cursor = raio.intersectObjects(clicaveis, false).length ? "pointer" : "grab";
});
renderer.domElement.addEventListener("pointerup", (e) => {
  if (arrastou) return;
  ponteiro.set((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
  raio.setFromCamera(ponteiro, camera);
  const alvo = raio.intersectObjects(clicaveis, false)[0];
  if (alvo) mostrarFicha(alvo.object.userData.agente);
});
addEventListener("resize", () => { camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); renderer.setSize(innerWidth, innerHeight); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") visaoGeral(); });

// ------------------------------------------------------------------ dados do robô
async function atualizar() {
  try {
    const d = await api(`/api/escritorio?desde=${estado.ultimoSeq}`);
    estado.ligado = d.ligado; estado.fila = d.fila || []; estado.agentesNumeros = d.agentes || {};
    estado.bancoHabilitado = Boolean(d.banco_habilitado);
    const chave = JSON.stringify((d.equipe || []).map((a) => [a.id, a.nome, a.papel, a.cor, a.ativo, a.skills.length])) + estado.bancoHabilitado;
    if (chave !== estado.chaveEquipe) {
      estado.chaveEquipe = chave; estado.equipe = d.equipe || [];
      estado.documentos.forEach((doc) => raiz.remove(doc.g)); estado.documentos.clear();
      montarEscritorio(estado.equipe);
    }
    const agora = Date.now() / 1000;
    for (const ev of d.eventos || []) {
      // ao abrir, não repete o que já aconteceu há mais de 20 s
      if (!estado.iniciado && agora - ev.ts > 20) continue;
      estado.filaEventos.push(ev);
    }
    estado.ultimoSeq = Math.max(estado.ultimoSeq, d.ultimo_seq || 0);
    estado.iniciado = true;
    $("#hud-status").innerHTML = d.erro_config ? `<i class="ponto erro"></i>Configuração pendente`
      : d.ligado ? `<i class="ponto ligado"></i>Monitorando · ${estado.fila.length} na fila` : `<i class="ponto pausado"></i>Pausado`;
    if (!estado.tocando && !estado.filaEventos.length && !estado.documentos.size) {
      narrar(estado.fila.length ? `${estado.fila.length} arquivo(s) aguardando sincronização na recepção` : "Aguardando planilhas em Bases-Limpeza…");
    }
    atualizarPilhaEntrada(); desenharEquipe();
  } catch {
    $("#hud-status").innerHTML = `<i class="ponto erro"></i>Sem conexão com o robô`;
  }
}
async function atualizarTV() {
  try { estado.kpis = (await api("/api/estado")).kpis; desenharTV(); } catch { /* tenta de novo */ }
}

// ------------------------------------------------------------------ animação
const relogio = new THREE.Clock();
function animar() {
  requestAnimationFrame(animar);
  const t = relogio.getElapsedTime(), agora = performance.now();

  if (!estado.tocando && estado.filaEventos.length) iniciarEvento(estado.filaEventos.shift());
  if (estado.tocando && agora >= estado.tocando.fim) finalizarEvento();

  for (const [id, e] of estado.estacoes) {
    if (e.ate && agora > e.ate) definirSituacao(id, e.inativo ? "desligado" : "parado");
    const fase = e.semente % 100;
    const { tronco, cabeca, bracos } = e.p;
    if (e.situacao === "trabalhando") {
      bracos[0].rotation.x = -1.2 + Math.sin(t * 18 + fase) * 0.12;
      bracos[1].rotation.x = -1.2 + Math.sin(t * 18 + fase + 1.6) * 0.12;
      cabeca.rotation.x = 0.18 + Math.sin(t * 3) * 0.04;
      cabeca.rotation.y = Math.sin(t * 1.5 + fase) * 0.12;
      e.anel.rotation.z += 0.08;
      tronco.position.y = 0.66 + Math.abs(Math.sin(t * 9)) * 0.012;
    } else if (e.situacao === "erro") {
      bracos[1].rotation.x = -2.9 + Math.sin(t * 8) * 0.15;
      bracos[0].rotation.x = -1.15;
      cabeca.rotation.x = -0.1;
    } else if (e.situacao === "ok") {
      bracos[0].rotation.x = -2.6; bracos[1].rotation.x = -2.6;
      tronco.position.y = 0.66 + Math.abs(Math.sin(t * 6)) * 0.05;
    } else if (e.situacao === "desligado") {
      cabeca.rotation.x = 0.45; bracos[0].rotation.x = -0.9; bracos[1].rotation.x = -0.9;
      e.selos.zz.position.y = 2.0 + Math.sin(t * 1.5) * 0.08;
    } else {
      bracos[0].rotation.x += (-1.0 - bracos[0].rotation.x) * 0.1;
      bracos[1].rotation.x += (-1.0 - bracos[1].rotation.x) * 0.1;
      cabeca.rotation.x = Math.sin(t * 0.8 + fase) * 0.05;
      cabeca.rotation.y = Math.sin(t * 0.35 + fase) * 0.35;
      tronco.position.y = 0.66 + Math.sin(t * 1.6 + fase) * 0.006;
    }
    for (const s of [e.selos.ok, e.selos.erro]) if (s.visible) s.position.y = 2.0 + Math.sin(t * 4) * 0.05;
    const distancia = camera.position.distanceTo(e.grupo.position);
    e.etiqueta.material.opacity = id === estado.selecionado ? 1 : Math.min(1, Math.max(0, (distancia - 5) / 4));
  }
  const bancoTrabalhando = estado.estacoes.get("banco")?.situacao === "trabalhando";
  leds.forEach((led, i) => {
    const aceso = bancoTrabalhando ? Math.random() > 0.45 : Math.sin(t * 2 + i) > 0.6;
    led.material.emissiveIntensity = estado.bancoHabilitado ? (aceso ? 1.8 : 0.15) : 0.05;
  });

  for (const doc of estado.documentos.values()) {
    if (!doc.dur) continue;
    const k = Math.min(1, (agora - doc.t0) / doc.dur), s = k * k * (3 - 2 * k);
    doc.g.position.lerpVectors(doc.de, doc.para, s);
    doc.g.position.y += Math.sin(Math.PI * s) * 1.1;
    doc.g.rotation.y = Math.sin(Math.PI * s) * 0.6;
    if (k >= 1) doc.dur = 0;
  }

  if (voo) {
    const k = Math.min(1, (agora - voo.t0) / voo.dur), s = k * k * (3 - 2 * k);
    camera.position.lerpVectors(voo.dePos, voo.paraPos, s);
    controles.target.lerpVectors(voo.deAlvo, voo.paraAlvo, s);
    if (k >= 1) voo = null;
  }
  controles.update();
  renderer.render(cena, camera);
}

await atualizar();
await atualizarTV();
animar();
setInterval(atualizar, 1000);
setInterval(atualizarTV, 4000);
