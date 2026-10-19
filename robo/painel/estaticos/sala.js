// Sala de reunião no estilo Microsoft Teams (engenharia reversa; ver documentacao/sala_teams.md).
// Barra de controles, galeria/palestrante/fixar, mão levantada, reações, painel de pessoas, compartilhar na tela,
// chat da reunião, anotações, pauta, tarefas, cronômetro, sua câmera (local), leitura em voz (local) e resumo ao encerrar.
// Tudo o que os funcionários dizem vem da API (dados gravados); nada é inventado aqui.

Object.assign(E, { sala: null, salaId: null, salaPara: "", salaPainel: "chat", salaVisao: "galeria", salaFixado: null,
  camStream: null, salaVoz: false, salaLidos: new Set(), salaReagindo: null });

async function carregarSala() {
  await nomesDaEquipe();
  if (E.salaId) { try { E.sala = await api(`/api/reuniao/sala?id=${encodeURIComponent(E.salaId)}`); } catch { E.sala = null; E.salaId = null; } }
  try { E.salas = (await api("/api/reuniao/salas")).salas; } catch { E.salas = []; }
  lerEmVoz();
}

const salaAcao = (acao, extra = {}) => api("/api/reuniao/sala/acao", { corpo: { conversa_id: E.salaId, acao, ...extra } });
const nomeNaSala = (id) => id === "dono" ? "Você" : (E.nomes?.[id] || id).split(" · ")[0];
const tempoDeSala = (desde) => { const s = Math.max(0, Math.floor((Date.now() - new Date(desde).getTime()) / 1000));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
  return (h ? `${h}:` : "") + `${String(m).padStart(2, "0")}:${String(x).padStart(2, "0")}`; };

// ------------------------------------------------------------------ peças
function tileSala(p, s, grande = false) {
  const ultimaDe = {}; for (const m of s.mensagens) ultimaDe[m.autor] = m;
  const falando = [...s.mensagens].reverse().find((m) => m.autor !== "dono")?.autor;
  const maos = s.contexto.maos || [];
  const posMao = maos.findIndex((m) => m.id === p.id);
  const ult = ultimaDe[p.id], fala = ult ? ult.texto.split("\n")[0].replace(/\*\*/g, "") : "";
  const ativo = p.id === falando, escolhido = p.id === E.salaPara, fixado = p.id === E.salaFixado;
  const dono = p.id === "dono";
  const rosto = dono && E.camStream
    ? `<video id="cam-dono" autoplay muted playsinline style="width:100%;height:100%;object-fit:cover;border-radius:10px;position:absolute;inset:0"></video>`
    : `<span style="width:${grande ? 120 : 64}px;height:${grande ? 120 : 64}px;border-radius:50%;background:${esc(p.cor || "#64748B")};display:grid;place-items:center;color:#fff;font-size:${grande ? 48 : 26}px;font-weight:600">${esc(p.nome.slice(0, 1))}</span>`;
  return `<div class="tile-reuniao" data-acao="${dono ? "" : "sala-para"}" data-id="${esc(p.id)}" title="${dono ? "" : "Clique para falar com " + esc(p.nome)}"
      style="position:relative;background:#292929;border-radius:10px;padding:14px;min-height:${grande ? 360 : 170}px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;
      cursor:${dono ? "default" : "pointer"};overflow:hidden;outline:${ativo ? "3px solid #7B83EB" : escolhido ? "2px dashed #A6A7DC" : "1px solid #3b3b3b"}">
    ${rosto}
    <div style="position:relative;text-align:center"><strong style="color:#fff">${esc(p.nome)}</strong><br><small style="color:#c8c8c8">${esc(p.cargo)}${p.nivel ? ` · ${esc(p.nivel)}` : ""}</small></div>
    ${fala && !dono ? `<div style="position:relative;margin-top:4px;background:#fff;color:#111;border-radius:10px;padding:6px 8px;font-size:12px;line-height:1.3;max-height:${grande ? 120 : 52}px;overflow:hidden">${esc(fala.slice(0, grande ? 400 : 140))}</div>` : ""}
    ${ativo ? `<span style="position:absolute;top:8px;left:10px;font-size:11px;color:#c5c8ff">● falando</span>` : ""}
    ${posMao >= 0 ? `<span title="${esc(maos[posMao].motivo)}" style="position:absolute;top:8px;right:10px;background:#FFC83D;color:#111;border-radius:12px;padding:2px 8px;font-size:12px;font-weight:600">✋ ${posMao + 1}</span>` : ""}
    ${!dono ? `<button class="btn pequeno" data-acao="sala-fixar" data-id="${esc(p.id)}" title="${fixado ? "Desafixar" : "Fixar"}" style="position:absolute;bottom:8px;right:8px;background:${fixado ? "#6264A7" : "#3b3b3b"};color:#fff;border:0">📌</button>` : ""}
    ${escolhido ? `<span style="position:absolute;bottom:10px;left:10px;font-size:11px;color:#c5c8ff">você fala com ${esc(p.nome)}</span>` : ""}</div>`;
}

function palcoSala(s) {
  const pessoas = [{ id: "dono", nome: "Você", cargo: "Dono da empresa", cor: "#6264A7", nivel: "" }, ...s.pessoas];
  const palco = s.contexto.palco;
  if (palco) {
    return `<div style="display:grid;grid-template-rows:auto auto;gap:10px">
      <div style="background:#fff;color:#111;border-radius:10px;padding:16px;min-height:300px;border:3px solid #C4314B">
        <div style="display:flex;justify-content:space-between;align-items:center"><strong>📺 Você está compartilhando: ${esc(palco.titulo)}</strong>
          <button class="btn pequeno" data-acao="sala-compartilhar" data-tipo="parar">Parar de compartilhar</button></div>
        <pre class="mono" style="white-space:pre-wrap;margin:10px 0 0;font-size:13px">${esc(palco.texto)}</pre></div>
      <div style="display:flex;gap:8px;overflow:auto">${pessoas.map((p) => `<div style="min-width:170px;flex:0 0 170px">${tileSala(p, s)}</div>`).join("")}</div></div>`;
  }
  if (E.salaVisao === "palestrante" || E.salaFixado) {
    const falando = [...s.mensagens].reverse().find((m) => m.autor !== "dono")?.autor;
    const destaque = pessoas.find((p) => p.id === E.salaFixado) || pessoas.find((p) => p.id === falando) || pessoas[1] || pessoas[0];
    return `<div style="display:grid;gap:10px">${tileSala(destaque, s, true)}
      <div style="display:flex;gap:8px;overflow:auto">${pessoas.filter((p) => p.id !== destaque.id).map((p) => `<div style="min-width:170px;flex:0 0 170px">${tileSala(p, s)}</div>`).join("")}</div></div>`;
  }
  return `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px">${pessoas.map((p) => tileSala(p, s)).join("")}</div>`;
}

function painelChat(s) {
  const reac = s.reacoes_disponiveis || {};
  const msgs = s.mensagens.map((m) => `<div class="msg ${m.autor === "dono" ? "minha" : ""}" style="margin:6px 0">
      <div class="msg-cab"><strong>${esc(nomeNaSala(m.autor))}</strong>${m.autor !== "dono" ? etiquetaNatureza(m.natureza) : ""}<time>${esc(dataT(m.criada_em))}</time>
        ${m.autor !== "dono" && !s.contexto.encerrada ? `<button class="btn pequeno fantasma" data-acao="sala-reagir-abrir" data-id="${m.id}" title="Reagir">😊</button>` : ""}</div>
      <div class="msg-texto">${m.autor === "dono" ? esc(m.texto) : formatarMensagem(m.texto)}</div>
      ${Object.keys(m.reacoes || {}).length ? `<div style="margin-top:4px">${Object.entries(m.reacoes).map(([e, n]) => `<span class="etiqueta">${e} ${n}</span>`).join(" ")}</div>` : ""}
      ${E.salaReagindo === m.id ? `<div style="margin-top:4px">${Object.entries(reac).map(([k, e]) => `<button class="btn pequeno" data-acao="sala-reagir" data-id="${m.id}" data-reacao="${k}" title="${k}">${e}</button>`).join(" ")}</div>` : ""}</div>`).join("");
  if (s.contexto.encerrada) return `<div class="cartao-corpo" id="transcricao-sala" style="overflow:auto;flex:1">${msgs}</div>`;
  return `<div class="cartao-corpo" id="transcricao-sala" style="overflow:auto;flex:1">${msgs}</div>
    <div class="caixa-texto" style="flex-wrap:wrap"><select id="sala-para" style="flex:1 1 100%">
        <option value="">Falar com: quem conduz (ou quem eu citar com @nome)</option>${s.pessoas.map((p) => `<option value="${esc(p.id)}" ${E.salaPara === p.id ? "selected" : ""}>Falar com: ${esc(p.nome)} · ${esc(p.cargo)}</option>`).join("")}</select>
      <textarea id="sala-texto" rows="2" placeholder="Escreva para a reunião. Enter envia." style="flex:1 1 260px;min-width:0"></textarea>
      <button class="btn primario" data-acao="sala-falar">${icone("enviar")}Falar</button></div>`;
}

function painelPessoas(s) {
  const maos = s.contexto.maos || [];
  const dentro = new Set(s.contexto.participantes);
  const fora = Object.entries(E.nomes || {}).filter(([id]) => !dentro.has(id));
  return `<div class="cartao-corpo" style="overflow:auto;flex:1">
    <div class="secao-titulo">Mãos levantadas (${maos.length}) — por ordem</div>
    ${maos.length ? `<ol style="padding-left:18px">${maos.map((m) => `<li style="margin-bottom:8px"><b>${esc(nomeNaSala(m.id))}</b> — ${esc(m.motivo)}
        ${s.contexto.encerrada ? "" : `<br><button class="btn pequeno primario" data-acao="sala-palavra" data-id="${esc(m.id)}">Dar a palavra</button>`}</li>`).join("")}</ol>`
      : `<p class="muted">Ninguém com a mão levantada. A mão sobe sozinha quando há farol vermelho, auditoria com achado, handover aberto ou desempenho abaixo da exigência.</p>`}
    ${s.contexto.encerrada ? "" : `<button class="btn pequeno" data-acao="sala-maos">${icone("recarregar")}Conferir de novo quem tem assunto</button>`}
    <div class="secao-titulo" style="margin-top:12px">Na reunião (${s.pessoas.length + 1})</div>
    <ul class="lista-ficha"><li><b>Você</b> · organizador</li>${s.pessoas.map((p) => `<li><b>${esc(p.nome)}</b> · ${esc(p.cargo)}
      ${p.id === s.funcionario ? `<span class="etiqueta">conduz</span>` : s.contexto.encerrada ? "" : `<button class="btn pequeno" data-acao="sala-remover" data-id="${esc(p.id)}">Remover</button>`}</li>`).join("")}</ul>
    ${s.contexto.encerrada ? "" : `<div class="secao-titulo" style="margin-top:12px">Convidar alguém</div>
      <div class="caixa-texto"><select id="sala-convidar" style="flex:1"><option value="">Escolha um funcionário…</option>${fora.map(([id, n]) => `<option value="${esc(id)}">${esc(n)}</option>`).join("")}</select>
      <button class="btn" data-acao="sala-convidar">Convidar</button></div>`}</div>`;
}

function painelNotas(s) {
  const pauta = s.contexto.pauta || [];
  const tarefas = s.contexto.tarefas || [];
  const fechada = s.contexto.encerrada;
  return `<div class="cartao-corpo" style="overflow:auto;flex:1">
    <div class="secao-titulo">Pauta</div>
    <ul class="lista-ficha">${pauta.map((p, i) => `<li><label style="display:flex;gap:6px;align-items:center"><input type="checkbox" data-sala-pauta="${i}" ${p.feito ? "checked" : ""} ${fechada ? "disabled" : ""}>
      <span style="${p.feito ? "text-decoration:line-through" : ""}">${esc(p.texto)}</span></label></li>`).join("") || "<li class='muted'>Sem pauta.</li>"}</ul>
    ${fechada ? "" : `<label>Itens da pauta (um por linha)<textarea id="sala-pauta" rows="3">${esc(pauta.map((p) => p.texto).join("\n"))}</textarea></label>
      <button class="btn pequeno" data-acao="sala-pauta">Salvar pauta</button>`}
    <div class="secao-titulo" style="margin-top:12px">Anotações da reunião</div>
    <textarea id="sala-notas" rows="6" ${fechada ? "disabled" : ""} placeholder="Decisões, combinados, dúvidas…">${esc(s.contexto.notas || "")}</textarea>
    ${fechada ? "" : `<button class="btn pequeno" data-acao="sala-notas">Salvar anotações</button>`}
    <div class="secao-titulo" style="margin-top:12px">Pendências do andar (decisões abertas — cobradas em toda reunião)</div>
    <ul class="lista-ficha">${(s.decisoes_pendentes || []).map((d) => `<li><span class="etiqueta ${d.estado === "atrasada" ? "perigo" : "alerta"}">${esc(d.estado_nome)}</span>
      <b>${esc(d.id)}</b> ${esc(d.texto)} <span class="muted">· ${esc(d.dono_nome)} · prazo ${esc(d.prazo.split("-").reverse().join("/"))}
      ${d.dias_para_o_prazo < 0 ? `(${-d.dias_para_o_prazo} dia(s) de atraso)` : `(faltam ${d.dias_para_o_prazo})`} · pronto quando: ${esc(d.criterio)}${d.repactuacoes ? ` · repactuada ${d.repactuacoes}x` : ""}</span>
      ${fechada ? "" : `<div class="acoes" style="margin-top:4px"><button class="btn pequeno" data-acao="sala-repactuar" data-id="${esc(d.id)}">Novo prazo</button>
        <button class="btn pequeno" data-acao="sala-concluir-decisao" data-id="${esc(d.id)}">Cumprida (com evidência)</button>
        <button class="btn pequeno" data-acao="sala-cancelar-decisao" data-id="${esc(d.id)}">Cancelar</button></div>`}</li>`).join("") || "<li class='muted'>Nenhuma decisão aberta neste andar.</li>"}</ul>
    <div class="secao-titulo" style="margin-top:12px">Decisões desta reunião (viram tarefa na central)</div>
    <ul class="lista-ficha">${tarefas.map((t) => `<li><button class="btn pequeno" data-acao="ver-solicitacao" data-id="${esc(t.id)}">${esc(t.id)}</button> ${t.decisao ? `<b>${esc(t.decisao)}</b> ` : ""}${esc(nomeNaSala(t.responsavel))}: ${esc(t.texto)}
      ${t.prazo ? `<span class="muted">· prazo ${esc(t.prazo.split("-").reverse().join("/"))} · pronto quando: ${esc(t.criterio || "")}</span>` : ""} ${t.estado ? etiquetaEstado(t.estado, t.estado_nome) : ""}</li>`).join("") || "<li class='muted'>Nenhuma decisão ainda.</li>"}</ul>
    ${fechada ? "" : `<label>O que foi decidido<input id="sala-tarefa" placeholder="Ex.: padronizar a coluna de data da base nps_outubro"></label>
      <label>Dono (quem faz)<select id="sala-tarefa-resp">${s.pessoas.map((p) => `<option value="${esc(p.id)}">${esc(p.nome)} · ${esc(p.cargo)}</option>`).join("")}
        ${Object.entries(E.nomes || {}).filter(([id]) => !s.contexto.participantes.includes(id)).map(([id, n]) => `<option value="${esc(id)}">${esc(n)}</option>`).join("")}</select></label>
      <label>Prazo<input type="date" id="sala-tarefa-prazo"></label>
      <label>Pronto quando (como vamos verificar)<input id="sala-tarefa-criterio" placeholder="Ex.: a base passa sem aviso de data em texto por 2 cargas seguidas"></label>
      <button class="btn" data-acao="sala-tarefa">Registrar decisão</button>`}</div>`;
}

function recapSala(s) {
  const r = s.contexto.recap; if (!r) return "";
  const lista = (t, xs) => `<div class="secao-titulo" style="margin-top:10px">${esc(t)}</div><ul class="lista-ficha">${(xs.length ? xs : ["—"]).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
  return `<section class="cartao" style="margin-bottom:14px"><div class="cartao-corpo">
    <div class="secao-titulo">Resumo da reunião (recap) · ${r.minutos} min · salvo em <span class="mono">${esc(s.contexto.arquivo || "")}</span></div>
    ${lista("Participantes", r.participantes)}${lista("Quem falou", Object.entries(r.falas).map(([k, v]) => `${k}: ${v} fala(s)`))}
    ${lista("Pauta", r.pauta)}${lista("Decisões (dono, prazo e critério)", r.decisoes || [])}${lista("Pendências anteriores tratadas", r.pendencias_tratadas || [])}
    ${(r.pendencias_sem_tratamento || []).length ? lista(`Pendências NÃO tratadas — justificativa: ${r.justificativa}`, r.pendencias_sem_tratamento) : ""}
    ${r.ata_sha256 ? `<p class="muted mono" style="font-size:11px">Ata SHA-256: ${esc(r.ata_sha256)}</p>` : ""}${lista("Mãos atendidas", r.maos_atendidas)}${lista("Mãos sem palavra", r.maos_sem_palavra)}
    ${lista("Compartilhado na tela", r.compartilhado)}${lista("Reações", Object.entries(r.reacoes).map(([e, n]) => `${e} ${n}`))}
    <div class="secao-titulo" style="margin-top:10px">Anotações</div><p style="white-space:pre-wrap">${esc(r.notas || "—")}</p></div></section>`;
}

function barraSala(s) {
  const b = (acao, rot, ativo = false, extra = "") => `<button class="btn pequeno" data-acao="${acao}" ${extra}
      style="background:${ativo ? "#6264A7" : "#3b3b3b"};color:#fff;border:0">${rot}</button>`;
  const fechada = s.contexto.encerrada;
  const comp = Object.entries(s.compartilhaveis || {}).map(([k, t]) => `<option value="${k}">${esc(t)}</option>`).join("");
  return `<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;background:#1F1F1F;border-radius:12px;padding:8px 10px;margin-bottom:10px">
    <span id="sala-timer" data-desde="${esc(s.criada_em)}" style="color:#fff;font-family:monospace;margin-right:6px">${fechada ? `${s.contexto.recap?.minutos ?? ""} min` : tempoDeSala(s.criada_em)}</span>
    ${b("sala-painel", "💬 Chat", E.salaPainel === "chat", 'data-painel="chat"')}
    ${b("sala-painel", `👥 Pessoas${(s.contexto.maos || []).length ? ` · ✋${s.contexto.maos.length}` : ""}`, E.salaPainel === "pessoas", 'data-painel="pessoas"')}
    ${b("sala-painel", `📝 Pauta, notas e decisões${(s.decisoes_pendentes || []).some((d) => d.estado === "atrasada") ? " · 🔴" : ""}`, E.salaPainel === "notas", 'data-painel="notas"')}
    ${b("sala-visao", E.salaVisao === "galeria" ? "▦ Galeria" : "◱ Palestrante", false)}
    ${fechada ? "" : `<select id="sala-compartilhar" style="background:#3b3b3b;color:#fff;border:0;border-radius:6px;padding:4px 8px;width:auto;flex:0 0 auto;max-width:240px;min-height:0;height:30px"><option value="">📺 Compartilhar…</option>${comp}</select>`}
    ${b("sala-camera", E.camStream ? "📷 Câmera ligada" : "📷 Câmera", !!E.camStream)}
    ${b("sala-voz", E.salaVoz ? "🔊 Lendo em voz" : "🔈 Ler em voz", E.salaVoz)}
    <span style="flex:1"></span>
    ${b("sala-sair", "Sair")}
    ${fechada ? "" : `<button class="btn pequeno" data-acao="sala-encerrar" style="background:#C4314B;color:#fff;border:0">Encerrar reunião</button>`}</div>`;
}

function renderSala() {
  const s = E.sala;
  const botoes = [1, 2, 3, 4, 5].map((a) => `<button class="btn ${s && s.contexto.andar === a ? "primario" : ""}" data-acao="sala-abrir" data-andar="${a}">${a}º andar</button>`).join("");
  if (!s) {
    return cabecalho("Sala de reunião", "Escolha o andar: a liderança entra na sala, cada um apresenta a sua parte com os dados de agora e quem tem assunto levanta a mão.", botoes) +
      (E.salas?.length ? `<div class="secao-titulo">Reuniões recentes</div><ul class="lista-ficha">${E.salas.map((x) => `<li><button class="btn pequeno" data-acao="sala-retomar" data-id="${esc(x.id)}">${esc(x.titulo)}</button>
        ${x.contexto?.encerrada ? `<span class="etiqueta">encerrada</span>` : `<span class="etiqueta sucesso">aberta</span>`} <span class="muted">${esc(dataT(x.atualizada_em))}</span></li>`).join("")}</ul>` : "");
  }
  const lateral = E.salaPainel === "pessoas" ? painelPessoas(s) : E.salaPainel === "notas" ? painelNotas(s) : painelChat(s);
  return cabecalho(s.titulo, `${s.contexto.encerrada ? "Reunião encerrada" : "Reunião ao vivo"} · ${s.pessoas.length + 1} pessoa(s). Clique na tela de alguém para falar com essa pessoa.`, botoes) +
    barraSala(s) + recapSala(s) +
    `<div class="sala-grade">
      <section style="background:#1F1F1F;border-radius:14px;padding:14px">${palcoSala(s)}</section>
      <section class="cartao" style="display:flex;flex-direction:column;max-height:76vh">${lateral}</section></div>`;
}

// ------------------------------------------------------------------ voz e câmera (só no seu computador)
function lerEmVoz() {
  const s = E.sala; if (!s) return;
  const novas = s.mensagens.filter((m) => m.autor !== "dono" && !E.salaLidos.has(m.id));
  novas.forEach((m) => E.salaLidos.add(m.id));
  if (!E.salaVoz || !("speechSynthesis" in window) || !E._salaVozPronta) { E._salaVozPronta = true; return; }
  for (const m of novas.slice(-3)) {
    const u = new SpeechSynthesisUtterance(`${nomeNaSala(m.autor)}: ${m.texto.split("\n")[0].replace(/\*\*/g, "").slice(0, 300)}`);
    u.lang = "pt-BR";
    const voz = speechSynthesis.getVoices().find((v) => v.lang?.toLowerCase().startsWith("pt"));
    if (voz) u.voice = voz;
    speechSynthesis.speak(u);
  }
}

async function alternarCamera() {
  if (E.camStream) { E.camStream.getTracks().forEach((t) => t.stop()); E.camStream = null; desenhar(); return; }
  if (!navigator.mediaDevices?.getUserMedia) return avisar("Este navegador não permite usar a câmera aqui.", "erro");
  try { E.camStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false }); desenhar(); }
  catch (e) { avisar(`Câmera não liberada: ${e.message}. A imagem não sai do seu computador.`, "erro"); }
}

setInterval(() => {
  const t = $("#sala-timer"); if (t && !E.sala?.contexto?.encerrada) t.textContent = tempoDeSala(t.dataset.desde);
  const v = $("#cam-dono"); if (v && E.camStream && v.srcObject !== E.camStream) v.srcObject = E.camStream;
}, 1000);

async function falarNaSala(el) {
  const texto = ($("#sala-texto")?.value || "").trim(); if (!texto) return;
  await comCarregando(el, async () => {
    await api("/api/reuniao/sala/falar", { corpo: { conversa_id: E.salaId, texto, para: E.salaPara || null } });
    limparCampo("sala-texto");
    await atualizarSala();
    $("#sala-texto")?.focus();
  });
}
async function atualizarSala() {
  await carregarSala(); desenhar();
  const t = $("#transcricao-sala"); if (t) t.scrollTop = t.scrollHeight;
}
const comSala = (el, fn) => comCarregando(el, async () => { await fn(); await atualizarSala(); });

// ------------------------------------------------------------------ registro
Object.assign(PAGINAS, { reuniao: { titulo: "Sala de reunião", render: renderSala, carregar: carregarSala } });
Object.assign(ACOES, {
  "sala-abrir": (el) => comCarregando(el, async () => {
    const r = await api("/api/reuniao/sala/abrir", { corpo: { andar: Number(el.dataset.andar) } });
    E.salaId = r.conversa_id; E.salaPara = ""; E.salaFixado = null; E.salaPainel = r.maos?.length ? "pessoas" : "chat";
    E._salaVozPronta = false; E.salaLidos = new Set(); await atualizarSala(); }),
  "sala-retomar": async (el) => { E.salaId = el.dataset.id; E.salaPara = ""; E._salaVozPronta = false; E.salaLidos = new Set(); await atualizarSala(); },
  "sala-sair": () => { E.salaId = null; E.sala = null; E.salaPara = ""; if (E.camStream) { E.camStream.getTracks().forEach((t) => t.stop()); E.camStream = null; }
    if ("speechSynthesis" in window) speechSynthesis.cancel(); carregarSala().then(desenhar); },
  "sala-para": (el) => { E.salaPara = E.salaPara === el.dataset.id ? "" : el.dataset.id; E.salaPainel = "chat"; desenhar(); $("#sala-texto")?.focus(); },
  "sala-falar": (el) => falarNaSala(el),
  "sala-painel": (el) => { E.salaPainel = el.dataset.painel; desenhar(); },
  "sala-visao": () => { E.salaVisao = E.salaVisao === "galeria" ? "palestrante" : "galeria"; E.salaFixado = null; desenhar(); },
  "sala-fixar": (el) => { E.salaFixado = E.salaFixado === el.dataset.id ? null : el.dataset.id; desenhar(); },
  "sala-camera": alternarCamera,
  "sala-voz": () => { E.salaVoz = !E.salaVoz; if (!E.salaVoz && "speechSynthesis" in window) speechSynthesis.cancel();
    if (E.salaVoz && !("speechSynthesis" in window)) avisar("Este navegador não tem leitura em voz.", "erro"); desenhar(); },
  "sala-palavra": (el) => comSala(el, () => salaAcao("palavra", { id: el.dataset.id })).then(() => { E.salaPainel = "chat"; desenhar(); }),
  "sala-maos": (el) => comSala(el, () => salaAcao("maos")),
  "sala-reagir-abrir": (el) => { E.salaReagindo = E.salaReagindo === Number(el.dataset.id) ? null : Number(el.dataset.id); desenhar(); },
  "sala-reagir": (el) => comSala(el, async () => { await salaAcao("reagir", { mensagem: Number(el.dataset.id), reacao: el.dataset.reacao }); E.salaReagindo = null; }),
  "sala-convidar": (el) => comSala(el, async () => { const id = $("#sala-convidar").value; if (!id) throw new Error("Escolha quem convidar."); await salaAcao("convidar", { id }); }),
  "sala-remover": (el) => comSala(el, () => salaAcao("remover", { id: el.dataset.id })),
  "sala-compartilhar": (el) => comSala(el, () => salaAcao("compartilhar", { tipo: el.dataset.tipo })),
  "sala-notas": (el) => comSala(el, async () => { await salaAcao("notas", { texto: $("#sala-notas").value }); avisar("Anotações salvas.", "sucesso"); }),
  "sala-pauta": (el) => comSala(el, () => salaAcao("pauta", { itens: $("#sala-pauta").value.split("\n").map((x) => x.trim()).filter(Boolean) })),
  "sala-tarefa": (el) => comSala(el, async () => {
    const r = await salaAcao("decisao", { texto: $("#sala-tarefa").value, responsavel: $("#sala-tarefa-resp").value,
      prazo: $("#sala-tarefa-prazo").value, criterio: $("#sala-tarefa-criterio").value });
    limparCampo("sala-tarefa"); limparCampo("sala-tarefa-criterio");
    avisar(`Decisão ${r.decisao} registrada (tarefa ${r.id} na central).`, "sucesso"); }),
  "sala-repactuar": (el) => comSala(el, async () => {
    const prazo = prompt("Novo prazo (dd/mm/aaaa):"); if (!prazo) return;
    const motivo = prompt("Motivo do novo prazo (o que mudou)?"); if (!motivo) return;
    await salaAcao("repactuar", { id: el.dataset.id, prazo, motivo }); avisar("Novo prazo registrado.", "sucesso"); }),
  "sala-concluir-decisao": (el) => comSala(el, async () => {
    const evidencia = prompt("Qual é a evidência de que foi feito (onde ver, o que mudou)?"); if (!evidencia) return;
    await salaAcao("concluir_decisao", { id: el.dataset.id, evidencia }); avisar("Decisão cumprida (declarada por você, com evidência).", "sucesso"); }),
  "sala-cancelar-decisao": (el) => comSala(el, async () => {
    const motivo = prompt("Por que cancelar esta decisão?"); if (!motivo) return;
    await salaAcao("cancelar_decisao", { id: el.dataset.id, motivo }); avisar("Decisão cancelada (o registro fica).", "sucesso"); }),
  "sala-encerrar": async (el) => {
    if (!(await confirmar({ titulo: "Encerrar a reunião?", texto: "A ata (com hash), as decisões e a transcrição são salvas. Depois de encerrada, ninguém fala mais nesta sala.", botao: "Encerrar", perigo: true }))) return;
    await comSala(el, async () => {
      try { await salaAcao("encerrar"); }
      catch (e) {
        if (!/decisão\(ões\) atrasada/.test(e.message)) throw e;
        const justificativa = prompt(`${e.message}\n\nPara encerrar mesmo assim, escreva a justificativa (fica na ata):`);
        if (!justificativa) throw new Error("Reunião continua aberta: trate as pendências atrasadas.");
        await salaAcao("encerrar", { justificativa });
      }
    });
  },
});
document.addEventListener("keydown", (e) => {
  if (e.target.id === "sala-texto" && e.key === "Enter" && !e.shiftKey) { e.preventDefault(); falarNaSala($("[data-acao='sala-falar']")); }
});
document.addEventListener("change", async (e) => {
  if (e.target.id === "sala-para") { E.salaPara = e.target.value; desenhar(); return; }
  if (e.target.id === "sala-compartilhar" && e.target.value) { const tipo = e.target.value;
    try { await salaAcao("compartilhar", { tipo }); } catch (err) { avisar(err.message, "erro"); } await atualizarSala(); }
  if (e.target.dataset.salaPauta !== undefined) {
    try { await salaAcao("pauta", { marcar: Number(e.target.dataset.salaPauta) }); } catch (err) { avisar(err.message, "erro"); } await atualizarSala(); }
});
