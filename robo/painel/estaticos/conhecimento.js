// Conhecimento: caderno de lições de cada funcionário (permanente, versionado, cadeia de registros) e erros de sistema.
// Usa as funções do painel.js e do atendimento.js. Nada aqui inventa dado: tudo vem da API.

const ESTADO_LICAO = { atribuida: ["Atribuída", ""], estudada: ["Estudada", "info"], avaliada: ["Avaliada", "alerta"], aplicada: ["Aplicada", "sucesso"] };
const ORIGEM_LICAO = { handover: "Erro (handover)", boa_pratica: "Boa prática (PDCA)", laboratorio: "Laboratório", correcao: "Correção do dono",
  manual: "Manual", dono: "Lição do dono" };
const etiquetaLicao = (e) => { const [t, c] = ESTADO_LICAO[e] || [e, ""]; return `<span class="etiqueta ${c}">${esc(t)}</span>`; };
Object.assign(E, { conhecimento: null, errosSistema: null, buscaLicao: "", achadasLicao: null });

async function carregarConhecimento() {
  await nomesDaEquipe();
  try { E.conhecimento = await api("/api/conhecimento"); } catch (e) { avisar(e.message, "erro"); }
  try { E.errosSistema = (await api("/api/erros")).erros; } catch { E.errosSistema = []; }
}

function renderConhecimento() {
  const k = E.conhecimento;
  const acoes = `<button class="btn primario" data-acao="licao-nova">${icone("mais")}Nova lição</button>
    <button class="btn" data-acao="licoes-rodar">${icone("play")}Rodar ciclo agora</button>
    <button class="btn" data-acao="recarregar-conhecimento">${icone("recarregar")}Atualizar</button>`;
  if (!k) return cabecalho("Conhecimento", "", acoes) + `<div class="carregando">Lendo o caderno de lições…</div>`;
  const at = k.atribuicoes || {}, total = Object.values(at).reduce((a, b) => a + b, 0) || 1;
  const pct = (e) => Math.round(100 * (at[e] || 0) / total);
  const integ = k.integridade;
  const cartoes = [
    ["Lições ativas", k.licoes, Object.entries(k.por_origem).map(([o, n]) => `${ORIGEM_LICAO[o] || o}: ${n}`).join(" · ")],
    ["Atribuições", total, "uma por pessoa que precisa saber"],
    ["Comprovadas na prática", `${pct("aplicada")}%`, `${at.aplicada || 0} aplicadas · ${at.avaliada || 0} avaliadas · ${at.estudada || 0} estudadas · ${at.atribuida || 0} novas`],
    ["Cadeia de registros", integ.integra ? "Íntegra" : "QUEBRADA", integ.integra ? `${integ.registros} registros conferidos (SHA-256)` : `adulteração no registro ${integ.quebra_em}`],
  ].map(([t, v, d], i) => `<div class="cartao"><div class="cartao-corpo"><div class="muted">${esc(t)}</div>
      <div style="font-size:28px;font-weight:700;${i === 3 && !integ.integra ? "color:var(--perigo)" : ""}">${esc(String(v))}</div>
      <small class="muted">${esc(d)}</small></div></div>`).join("");
  const nomes = E.nomes || {};
  const pessoas = k.pessoas.map((p) => `<tr><td><b>${esc(p.nome)}</b><br><small class="muted">${esc(nomes[p.funcionario] || p.funcionario)}</small></td>
      <td>${p.total}</td><td>${p.aplicadas || 0}</td><td>${p.novas || 0}</td>
      <td><div style="background:var(--borda);border-radius:6px;height:8px;width:120px"><div style="background:var(--${p.pct >= 80 ? "sucesso" : p.pct >= 50 ? "alerta" : "perigo"});height:8px;border-radius:6px;width:${p.pct * 1.2}px"></div></div><small>${p.pct}%</small></td>
      <td><button class="btn pequeno" data-acao="caderno" data-id="${esc(p.funcionario)}">Caderno</button></td></tr>`).join("");
  const recentes = k.recentes.map((l) => `<li>${l.arquivada ? `<span class="etiqueta">arquivada</span>` : ""}
      <button class="btn pequeno" data-acao="licao-ver" data-id="${esc(l.id)}">${esc(l.id)}</button> ${esc(l.titulo)}
      <span class="muted">· ${esc(ORIGEM_LICAO[l.origem_tipo] || l.origem_tipo)} · v${l.versao} · ${esc(dataT(l.criada_em))}</span></li>`).join("");
  const achadas = E.achadasLicao ? (E.achadasLicao.length ? E.achadasLicao.map((l) => `<li><button class="btn pequeno" data-acao="licao-ver" data-id="${esc(l.id)}">${esc(l.id)}</button> ${esc(l.titulo)}</li>`).join("")
    : "<li>Nenhuma lição responde a essa pergunta. Se for algo que a empresa precisa saber, crie uma lição.</li>") : "";
  const errs = E.errosSistema || [];
  const linhasErro = errs.map((e) => `<tr><td><span class="etiqueta ${e.estado === "resolvido" ? "sucesso" : "perigo"}">${esc(e.estado)}</span></td>
      <td><b>${esc(e.tipo)}</b> em <span class="mono">${esc(e.modulo)}.${esc(e.funcao)}</span><br><small>${esc(e.mensagem.slice(0, 200))}</small></td>
      <td>${e.ocorrencias}</td><td>${esc(dataT(e.primeira))}<br><small class="muted">última ${esc(dataT(e.ultima))}</small></td>
      <td><button class="btn pequeno" data-acao="erro-ver" data-id="${e.id}">Detalhes</button>
      ${e.estado !== "resolvido" ? `<button class="btn pequeno" data-acao="erro-resolver" data-id="${e.id}">Marcar resolvido</button>` : ""}</td></tr>`).join("");
  return cabecalho("Conhecimento", "Tudo o que a empresa aprendeu vira lição. Cada pessoa estuda, é testada e só conta como aplicada com prova. Nada se apaga.", acoes) +
    `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px">${cartoes}</div>
    <section class="cartao" style="margin-top:14px"><div class="cartao-corpo"><div class="secao-titulo">Perguntar ao conhecimento da empresa</div>
      <div class="caixa-texto"><input id="licao-busca" value="${esc(E.buscaLicao)}" placeholder="Ex.: como calcular o NPS? o que fazer com data em texto?" style="flex:1">
      <button class="btn" data-acao="licao-buscar">${icone("busca")}Buscar</button></div>
      ${achadas ? `<ul class="lista-ficha">${achadas}</ul>` : ""}</div></section>
    <div class="secao-titulo" style="margin-top:14px">Quem tem mais lição sem comprovar (de quem cobrar primeiro)</div>
    <div class="tabela-envoltorio"><table class="tabela"><thead><tr><th>Funcionário</th><th>Lições</th><th>Aplicadas</th><th>Novas</th><th>% comprovado</th><th></th></tr></thead><tbody>${pessoas}</tbody></table></div>
    <div class="secao-titulo" style="margin-top:14px">Lições mais recentes</div><ul class="lista-ficha">${recentes || "<li>Nenhuma lição ainda.</li>"}</ul>
    <div class="secao-titulo" style="margin-top:14px">Erros de sistema (registro permanente: cada tipo vira handover para a TI)</div>
    ${errs.length ? `<div class="tabela-envoltorio"><table class="tabela"><thead><tr><th>Estado</th><th>Erro</th><th>Vezes</th><th>Quando</th><th></th></tr></thead><tbody>${linhasErro}</tbody></table></div>`
      : `<p class="muted">Nenhum erro de sistema registrado. Se algum acontecer, ele aparece aqui com o traceback completo e não pode ser apagado.</p>`}
    <p class="muted" style="font-size:12px">Como funciona: atribuída → <b>estudada</b> (entrou no caderno) → <b>avaliada</b> (a pessoa acha a lição quando perguntada)
      → <b>aplicada</b> (prova prática: o caso do laboratório refeito passou, o PDCA verificou o handover, ou é referência de manual). Sem prova, não vira “aplicada”.</p>`;
}

async function verCaderno(pid) {
  let c; try { c = await api(`/api/conhecimento/caderno?id=${encodeURIComponent(pid)}`); } catch (e) { return avisar(e.message, "erro"); }
  const nome = E.nomes?.[pid] || pid;
  abrirGaveta(`<div class="gaveta-cab"><div style="flex:1"><div class="muted">Caderno de lições</div><h2>${esc(nome)}</h2></div>
      <button class="btn fantasma" data-acao="fechar-gaveta" aria-label="Fechar">${icone("x")}</button></div>
    <div class="gaveta-corpo"><div class="chips-colunas">${Object.entries(c.por_estado).map(([e, n]) => `${etiquetaLicao(e)} ${n}`).join(" ")}
      <span class="etiqueta">${c.pct_aplicada}% comprovado</span></div>
      <ul class="lista-ficha">${c.licoes.map((l) => `<li>${etiquetaLicao(l.estado)} <button class="btn pequeno" data-acao="licao-ver" data-id="${esc(l.licao_id)}">${esc(l.licao_id)}</button>
        ${esc(l.titulo)} <span class="muted">· v${l.versao} · ${esc(ORIGEM_LICAO[l.origem_tipo] || l.origem_tipo)}</span>
        ${l.evidencia ? `<br><small class="muted">Evidência: ${esc(l.evidencia)}</small>` : ""}</li>`).join("")}</ul></div>`);
}

async function verLicao(id) {
  let l; try { l = await api(`/api/conhecimento/licao?id=${encodeURIComponent(id)}`); } catch (e) { return avisar(e.message, "erro"); }
  E.licaoAberta = l;
  abrirGaveta(`<div class="gaveta-cab"><div style="flex:1"><div class="muted">${esc(l.id)} · v${l.versao} · ${esc(ORIGEM_LICAO[l.origem_tipo] || l.origem_tipo)}</div><h2>${esc(l.titulo)}</h2></div>
      <button class="btn fantasma" data-acao="fechar-gaveta" aria-label="Fechar">${icone("x")}</button></div>
    <div class="gaveta-corpo">${l.arquivada ? `<p class="etiqueta alerta">Arquivada: ${esc(l.motivo_arquivo || "")}</p>` : ""}
      <pre class="mono" style="white-space:pre-wrap">${esc(l.conteudo)}</pre>
      <p><b>Pergunta-chave:</b> ${esc(l.pergunta || "—")}<br><b>Como comprovar que foi aplicada:</b> ${esc(l.como_aplicar || "—")}</p>
      <div class="secao-titulo">Versões</div><ul class="lista-ficha">${l.versoes.map((v) => `<li>v${v.versao} · ${esc(v.autor)} · ${esc(dataT(v.criada_em))}${v.arquivada ? ` · arquivada (${esc(v.motivo_arquivo || "")})` : ""}</li>`).join("")}</ul>
      <div class="secao-titulo">Quem tem esta lição (${l.pessoas.length})</div>
      <ul class="lista-ficha">${l.pessoas.map((p) => `<li>${etiquetaLicao(p.estado)} ${esc(p.nome)}${p.evidencia ? ` <small class="muted">— ${esc(p.evidencia)}</small>` : ""}</li>`).join("")}</ul>
      <div class="secao-titulo">Trilha na cadeia de registros</div>
      <ul class="lista-ficha">${l.trilha.slice(-40).map((t) => `<li class="mono" style="font-size:12px">#${t.id} ${esc(dataT(t.data_hora))} ${esc(t.tipo)} · ${esc(t.quem)} · ${esc(t.hash.slice(0, 12))}…</li>`).join("")}</ul>
      ${l.arquivada ? "" : `<div class="secao-titulo">Governança (só você, o dono)</div>
        <label>Conteúdo corrigido (cria a versão ${l.versao + 1}; a atual continua guardada)<textarea id="licao-conteudo" rows="6">${esc(l.conteudo)}</textarea></label>
        <label>Motivo da mudança<input id="licao-motivo" placeholder="Ex.: a regra estava incompleta"></label>
        <div class="acoes" style="margin-top:8px"><button class="btn primario" data-acao="licao-versao" data-id="${esc(l.id)}">Publicar versão nova</button>
        <button class="btn perigo" data-acao="licao-arquivar" data-id="${esc(l.id)}">Arquivar</button></div>`}</div>`);
}

function novaLicao() {
  abrirGaveta(`<div class="gaveta-cab"><div style="flex:1"><div class="muted">Só o dono cria lição manual</div><h2>Nova lição</h2></div>
      <button class="btn fantasma" data-acao="fechar-gaveta" aria-label="Fechar">${icone("x")}</button></div>
    <div class="gaveta-corpo">
      <label>Título<input id="nl-titulo" placeholder="Ex.: NPS sempre com 0 casas decimais"></label>
      <label>Conteúdo (o que todos precisam saber)<textarea id="nl-conteudo" rows="7"></textarea></label>
      <label>Pergunta-chave (como alguém perguntaria)<input id="nl-pergunta" placeholder="Ex.: quantas casas decimais no NPS?"></label>
      <label>Como comprovar que foi aplicada<input id="nl-aplicar" placeholder="Ex.: toda resposta de NPS sai inteira"></label>
      <label>Para quem<select id="nl-publico"><option value="todos">Todos os funcionários</option><option value="lideranca">Só a liderança</option>
        ${[1, 2, 3, 4, 5].map((a) => `<option value="andar:${a}">Só o ${a}º andar</option>`).join("")}</select></label>
      <div class="acoes" style="margin-top:8px"><button class="btn primario" data-acao="licao-criar">Criar e atribuir</button></div></div>`);
}

Object.assign(PAGINAS, {
  conhecimento: { titulo: "Conhecimento", render: renderConhecimento, carregar: carregarConhecimento },
});
Object.assign(ACOES, {
  "recarregar-conhecimento": async () => { await carregarConhecimento(); desenhar(); },
  caderno: (el) => verCaderno(el.dataset.id),
  "licao-ver": (el) => verLicao(el.dataset.id),
  "licao-nova": novaLicao,
  "licao-buscar": async () => {
    E.buscaLicao = ($("#licao-busca")?.value || "").trim(); if (!E.buscaLicao) return;
    try { E.achadasLicao = (await api(`/api/conhecimento/buscar?q=${encodeURIComponent(E.buscaLicao)}`)).licoes; } catch (e) { avisar(e.message, "erro"); }
    desenhar();
  },
  "licoes-rodar": (el) => comCarregando(el, async () => {
    const r = await api("/api/conhecimento/rodar", { corpo: {} });
    avisar(r.integridade ? `Ciclo concluído: ${r.estudada} estudadas, ${r.avaliada} avaliadas, ${r.aplicada} aplicadas. Cadeia ${r.integridade.integra ? "íntegra" : "QUEBRADA"}.` : "Ciclo concluído.", "sucesso");
    await carregarConhecimento(); desenhar(); }),
  "licao-criar": (el) => comCarregando(el, async () => {
    const pub = $("#nl-publico").value; const [publico, andar] = pub.startsWith("andar:") ? ["andar", pub.split(":")[1]] : [pub, null];
    const r = await api("/api/conhecimento/criar", { corpo: { titulo: $("#nl-titulo").value, conteudo: $("#nl-conteudo").value,
      pergunta: $("#nl-pergunta").value, como_aplicar: $("#nl-aplicar").value, publico, andar } });
    fecharGaveta(); avisar(`Lição ${r.id} criada e atribuída.`, "sucesso"); await carregarConhecimento(); desenhar(); }),
  "licao-versao": (el) => comCarregando(el, async () => {
    const r = await api("/api/conhecimento/versao", { corpo: { id: el.dataset.id, conteudo: $("#licao-conteudo").value, motivo: $("#licao-motivo").value } });
    avisar(`Versão nova publicada: ${r.id}. A anterior continua guardada.`, "sucesso"); await carregarConhecimento(); desenhar(); verLicao(r.id); }),
  "licao-arquivar": async (el) => {
    const motivo = ($("#licao-motivo")?.value || "").trim();
    if (!motivo) return avisar("Escreva o motivo no campo “Motivo da mudança” antes de arquivar.", "erro");
    if (!(await confirmar({ titulo: "Arquivar esta lição?", texto: "Ela sai das atribuições, mas continua guardada para sempre.", botao: "Arquivar", perigo: true }))) return;
    try { await api("/api/conhecimento/arquivar", { corpo: { id: el.dataset.id, motivo } }); fecharGaveta(); await carregarConhecimento(); desenhar(); }
    catch (e) { avisar(e.message, "erro"); }
  },
  "erro-ver": (el) => {
    const e = (E.errosSistema || []).find((x) => String(x.id) === el.dataset.id); if (!e) return;
    abrirGaveta(`<div class="gaveta-cab"><div style="flex:1"><div class="muted">Erro ${e.id} · impressão ${esc(e.impressao)} · ${e.ocorrencias} vez(es)</div><h2>${esc(e.tipo)} em ${esc(e.modulo)}.${esc(e.funcao)}</h2></div>
        <button class="btn fantasma" data-acao="fechar-gaveta" aria-label="Fechar">${icone("x")}</button></div>
      <div class="gaveta-corpo"><p>${esc(e.mensagem)}</p><p class="muted">Handover: ${esc(e.handover_id || "—")} · estado ${esc(e.estado)}</p>
        <div class="secao-titulo">Traceback da última ocorrência</div><pre class="mono" style="white-space:pre-wrap;font-size:12px">${esc(e.traceback_ultimo || "(sem traceback)")}</pre>
        <div class="secao-titulo">Traceback da primeira ocorrência</div><pre class="mono" style="white-space:pre-wrap;font-size:12px">${esc(e.traceback_primeiro || "(sem traceback)")}</pre></div>`);
  },
  "erro-resolver": async (el) => {
    if (!(await confirmar({ titulo: "Marcar como resolvido?", texto: "O registro continua guardado. Se o erro voltar, ele reabre sozinho.", botao: "Marcar resolvido" }))) return;
    try { await api("/api/erros/resolver", { corpo: { id: Number(el.dataset.id) } }); await carregarConhecimento(); desenhar(); } catch (e) { avisar(e.message, "erro"); }
  },
});
document.addEventListener("keydown", (e) => {
  if (e.target.id === "licao-busca" && e.key === "Enter") { e.preventDefault(); ACOES["licao-buscar"](); }
});
