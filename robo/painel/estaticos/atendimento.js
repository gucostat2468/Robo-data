// Atendimento: conversa direta com cada funcionário, central de solicitações e memória (desempenho, handovers, reuniões).
// Usa as funções do painel.js (api, esc, icone, abrirGaveta, avisar…). Nada aqui inventa dado: tudo vem da API.

const NATUREZA = {
  conhecimento: ["Conhecimento registrado", "info"], calculo: ["Cálculo determinístico", "sucesso"],
  execucao: ["Execução de código", "sucesso"], ferramenta: ["Ferramenta do sistema", ""],
  hipotese: ["Hipótese", "alerta"], precisa_confirmacao: ["Precisa da sua confirmação", "alerta"],
  limitacao: ["Limitação (não foi feito)", "perigo"],
};
const COR_ESTADO = {
  concluida: "sucesso", concluida_parcialmente: "alerta", falhou: "perigo", cancelada: "", bloqueada: "perigo",
  aguardando_aprovacao: "alerta", aguardando_esclarecimento: "alerta", reprovada_revisao: "perigo", em_execucao: "info",
  em_revisao: "info", na_fila: "info",
};
const dataT = (t) => dataCurta(String(t || "").replace("T", " "));
const etiquetaNatureza = (n) => { const [t, c] = NATUREZA[n] || [n || "—", ""]; return `<span class="etiqueta ${c}">${esc(t)}</span>`; };
const etiquetaEstado = (s, nome) => `<span class="etiqueta ${COR_ESTADO[s] || ""}">${esc(nome || s)}</span>`;
Object.assign(E, { conversa: null, conversaPessoa: null, conversaAnexo: null, solic: null, filtroSolic: { dias: "30" }, memoria: null });

// ------------------------------------------------------------------ conversa com um funcionário
async function abrirConversa(pid, conversaId = null) {
  let ficha;
  try { ficha = await api(`/api/funcionario?id=${encodeURIComponent(pid)}`); } catch (e) { return avisar(e.message, "erro"); }
  E.conversaPessoa = ficha; E.conversaAnexo = null;
  E.conversa = conversaId ? await api(`/api/conversa?id=${encodeURIComponent(conversaId)}`).catch(() => null) : null;
  desenharConversa();
}

function desenharConversa() {
  const f = E.conversaPessoa; if (!f) return;
  const c = f.contrato, conv = E.conversa;
  const nomeDe = (id) => id === "dono" ? "Você" : id === c.id ? c.nome : id;
  const msgs = (conv?.mensagens || []).map((m) => `<div class="msg ${m.autor === "dono" ? "minha" : ""}">
      <div class="msg-cab"><strong>${esc(nomeDe(m.autor))}</strong>${m.autor !== "dono" ? etiquetaNatureza(m.natureza) : ""}
        ${m.solicitacao_id && m.solicitacao_id.startsWith("TAR") ? `<button class="btn pequeno" data-acao="ver-solicitacao" data-id="${esc(m.solicitacao_id)}">Ver tarefa</button>` : ""}
        <time>${esc(dataT(m.criada_em))}</time></div>
      <div class="msg-texto">${esc(m.texto)}</div>
      ${m.dados?.evidencia ? `<div class="muted" style="font-size:12px;margin-top:4px">Evidência: ${esc(m.dados.evidencia)}</div>` : ""}
      ${m.dados?.encaminhado_para ? `<div style="margin-top:6px"><button class="btn pequeno" data-acao="conversar" data-id="${esc(m.dados.encaminhado_para)}">Conversar direto com quem faz</button></div>` : ""}
    </div>`).join("");
  const anteriores = (f.conversas_recentes || []).filter((x) => x.id !== conv?.id).slice(0, 5);
  abrirGaveta(`<div class="gaveta-cab"><span class="avatar" style="background:${esc(c.cor || "#64748B")}">${esc(c.nome.slice(0, 1))}</span>
      <div style="flex:1"><div class="muted">${esc(c.andar)}º andar · ${esc(c.nome_andar)}</div><h2>Conversa com ${esc(c.nome)} · ${esc(c.cargo)}</h2></div>
      <button class="btn fantasma" data-acao="fechar-gaveta" aria-label="Fechar">${icone("x")}</button></div>
    <div class="gaveta-corpo">
      <div class="chips-colunas"><span class="etiqueta info">${esc(c.nivel_nome)}</span><span class="etiqueta">Revisor: ${esc(c.revisor_nome)}</span>
        <span class="etiqueta">Risco máximo: ${esc(c.risco_maximo)}</span>${c.permissoes.modo ? `<span class="etiqueta alerta">${esc(c.permissoes.modo)}</span>` : ""}</div>
      <p class="muted" style="margin:0">Ferramentas no contrato: ${c.ferramentas.map(esc).join(", ")}. O que não estiver aqui, ${esc(c.nome)} encaminha para quem faz.
        Cada resposta mostra de onde veio (conhecimento, cálculo, execução…). A conversa fica guardada e continua depois de reiniciar.</p>
      ${anteriores.length ? `<div class="muted" style="font-size:13px">Conversas anteriores: ${anteriores.map((x) => `<button class="btn pequeno" data-acao="retomar-conversa" data-id="${esc(c.id)}" data-conversa="${esc(x.id)}">${esc((x.titulo || "").slice(0, 40))}</button>`).join(" ")}</div>` : ""}
      <div class="mensagens" id="mensagens-conversa" style="max-height:52vh;overflow:auto">${msgs || `<p class="muted" style="padding:12px">Escreva abaixo. Exemplos: “o que você faz?”, “nps por curso”, “e por modalidade?”, anexe uma planilha e peça “verifique esta planilha”.</p>`}</div>
      ${E.conversaAnexo ? `<div class="dica">${icone("pasta")}<p>Anexo pronto: <b>${esc(E.conversaAnexo.nome)}</b> (vai junto com a próxima mensagem)</p></div>` :
        conv?.contexto?.arquivo ? `<div class="muted" style="font-size:12px">Arquivo desta conversa: ${esc(conv.contexto.arquivo.split(/[\\/]/).pop())}</div>` : ""}
      <div class="caixa-texto"><textarea id="conversa-texto" rows="2" placeholder="Mensagem para ${esc(c.nome)}. Enter envia, Shift+Enter quebra linha."></textarea>
        <button class="btn" data-acao="conversa-anexar">${icone("pasta")}Anexar</button>
        <button class="btn primario" data-acao="conversa-enviar">${icone("enviar")}Enviar</button></div>
    </div>`);
  $("#gaveta").classList.add("larga");
  const m = $("#mensagens-conversa"); if (m) m.scrollTop = m.scrollHeight;
  $("#conversa-texto")?.focus();
}

async function enviarConversa(el) {
  const texto = ($("#conversa-texto")?.value || "").trim();
  if (!texto && !E.conversaAnexo) return;
  const corpo = { funcionario: E.conversaPessoa.contrato.id, texto, conversa_id: E.conversa?.id || null,
                  arquivo: E.conversaAnexo?.arquivo || null, origem: "ficha" };
  await comCarregando(el, async () => {
    const r = await api("/api/conversa/enviar", { corpo });
    E.conversaAnexo = null;
    E.conversa = await api(`/api/conversa?id=${encodeURIComponent(r.conversa_id)}`);
    desenharConversa();
  });
}

function anexarConversa() {
  const input = document.createElement("input");
  input.type = "file"; input.accept = ".xlsx,.xlsm,.xls,.csv,.txt";
  input.onchange = async () => {
    const arq = input.files[0]; if (!arq) return;
    try { E.conversaAnexo = await api("/api/conversa/anexar", { arquivo: arq }); desenharConversa(); }
    catch (e) { avisar(e.message, "erro"); }
  };
  input.click();
}

// ------------------------------------------------------------------ central de solicitações
async function carregarSolicitacoes() {
  const q = new URLSearchParams(Object.entries(E.filtroSolic).filter(([, v]) => v));
  try { E.solic = await api(`/api/solicitacoes?${q}`); } catch (e) { avisar(e.message, "erro"); }
}

function renderSolicitacoes() {
  const s = E.solic;
  const acoes = `<button class="btn" data-acao="recarregar-solic">${icone("recarregar")}Atualizar</button>`;
  if (!s) return cabecalho("Solicitações", "", acoes) + `<div class="carregando">Carregando…</div>`;
  const f = E.filtroSolic;
  const sel = (id, opcoes, rotulo) => `<select data-filtro-solic="${id}"><option value="">${rotulo}</option>${opcoes.map(([v, t]) => `<option value="${esc(v)}" ${String(f[id] || "") === String(v) ? "selected" : ""}>${esc(t)}</option>`).join("")}</select>`;
  const cont = s.contagem.por_estado || {};
  const aprov = s.aprovacoes.map((a) => `<div class="ocorrencia aviso"><div class="principal"><strong>${esc(a.pedido)}</strong>
      <div class="muted">${esc(a.solicitacao_id)} · ${esc(a.titulo || "")} · pedido por ${esc(a.solicitante)} · risco ${esc(a.risco)}</div></div>
      <div class="acoes"><button class="btn primario pequeno" data-acao="aprovar" data-id="${esc(a.id)}" data-valor="1">${icone("ok")}Aprovar</button>
      <button class="btn pequeno" data-acao="aprovar" data-id="${esc(a.id)}" data-valor="0">${icone("x")}Recusar</button></div></div>`).join("");
  const linhas = s.itens.map((i) => `<tr data-acao="ver-solicitacao" data-id="${esc(i.id)}" style="cursor:pointer">
      <td class="mono">${esc(i.id)}</td><td>${esc(i.tipo)}</td><td>${esc(i.titulo)}</td><td>${esc(i.funcionario || "—")}</td>
      <td>${esc(i.origem)}</td><td>${esc(i.prioridade)}</td><td>${etiquetaEstado(i.estado, i.estado_nome)}${i.aprovacoes_pendentes ? ` <span class="etiqueta alerta">${i.aprovacoes_pendentes} aprovação</span>` : ""}</td>
      <td>${esc(dataT(i.criada_em))}</td></tr>`).join("");
  return cabecalho("Solicitações", "Todo pedido seu (manual) e todo arquivo processado (automático), com plano, etapas, responsáveis, aprovações, revisão e histórico. Fica guardado em logs/trabalho.db.", acoes) +
    `<section class="cartao"><div class="cartao-corpo">
      <div class="secao-titulo">Novo pedido</div>
      <div class="caixa-texto" style="flex-wrap:wrap"><textarea id="solic-texto" rows="2" style="flex:1 1 360px;min-width:0" placeholder="Ex.: faça uma análise completa desta planilha · verifique esta planilha · publique esta planilha · monte uma apresentação"></textarea>
        <select id="solic-prioridade" style="flex:0 0 auto;width:auto"><option value="media">Prioridade média</option><option value="alta">Alta</option><option value="baixa">Baixa</option></select>
        <button class="btn" data-acao="solic-anexar">${icone("pasta")}${E.solicAnexo ? esc(E.solicAnexo.nome) : "Anexar"}</button>
        <button class="btn primario" data-acao="solic-criar">${icone("enviar")}Registrar</button></div></div></section>
    <div class="chips-colunas" style="margin:12px 0">${Object.entries(cont).map(([k, n]) => `<span class="etiqueta ${COR_ESTADO[k] || ""}">${esc(s.estados[k] || k)}: ${n}</span>`).join("") || `<span class="muted">Nenhuma solicitação ainda.</span>`}</div>
    ${aprov ? `<div class="secao-titulo">Aguardando a sua aprovação</div>${aprov}` : ""}
    <div class="filtros-canal" style="margin:12px 0">
      ${sel("estado", Object.entries(s.estados), "Todos os estados")}
      ${sel("tipo", [["conversa", "Conversa"], ["tarefa", "Tarefa"], ["projeto", "Projeto"]], "Todos os tipos")}
      ${sel("origem", [["manual", "Manual"], ["automatica", "Automática"]], "Toda origem")}
      ${sel("prioridade", [["alta", "Alta"], ["media", "Média"], ["baixa", "Baixa"]], "Toda prioridade")}
      ${sel("andar", [1, 2, 3, 4, 5].map((a) => [a, `${a}º andar`]), "Todos os andares")}
      ${sel("dias", [["1", "Últimas 24h"], ["7", "7 dias"], ["30", "30 dias"], ["90", "90 dias"]], "Todo o período")}
      <label class="campo-busca">${icone("busca")}<input type="text" id="solic-busca" placeholder="Buscar…" value="${esc(f.texto || "")}"></label></div>
    <div class="tabela-envoltorio"><table class="tabela"><thead><tr><th>Id</th><th>Tipo</th><th>Pedido</th><th>Responsável</th><th>Origem</th><th>Prioridade</th><th>Estado</th><th>Criada</th></tr></thead>
      <tbody>${linhas || `<tr><td colspan="8" class="muted">Nada com estes filtros.</td></tr>`}</tbody></table></div>`;
}

async function verSolicitacao(id) {
  let s;
  try { s = await api(`/api/solicitacao?id=${encodeURIComponent(id)}`); } catch (e) { return avisar(e.message, "erro"); }
  const etapas = s.etapas.map((e) => `<div class="ocorrencia ${e.estado === "concluida" ? "" : e.estado === "falhou" || e.estado === "bloqueada" ? "erro" : "aviso"}">
      <div class="principal"><strong>${e.ordem}. ${esc(e.titulo)}</strong> ${etiquetaEstado(e.estado)} ${e.natureza ? etiquetaNatureza(e.natureza) : ""}
      <div class="muted">Responsável: ${esc(e.funcionario)} · ferramenta: ${esc(e.ferramenta || "nenhuma no robô")} · risco ${esc(e.risco)}${e.depende.length ? ` · depende de ${e.depende.join(", ")}` : ""}${e.precisa_aprovacao ? " · precisa de aprovação" : ""}</div>
      ${e.resultado?.texto ? `<pre class="mono" style="white-space:pre-wrap;margin:6px 0 0">${esc(e.resultado.texto.slice(0, 3000))}</pre>` : ""}
      ${e.resultado?.evidencia ? `<div class="muted" style="font-size:12px">Evidência: ${esc(e.resultado.evidencia)}</div>` : ""}</div></div>`).join("");
  const eventos = s.eventos.map((e) => `<li><time class="mono">${esc(dataT(e.data_hora))}</time> · <b>${esc(e.quem || "")}</b> ${esc(e.texto)}</li>`).join("");
  const artefatos = s.artefatos.map((a) => `<li class="mono">${esc(a.caminho)} <span class="muted">(${esc(a.descricao || a.tipo)})</span></li>`).join("");
  const rev = s.revisao || {};
  abrirGaveta(`<div class="gaveta-cab"><div style="flex:1"><div class="muted">${esc(s.id)} · ${esc(s.tipo)} · ${esc(s.origem)}</div><h2>${esc(s.titulo)}</h2></div>
      <button class="btn fantasma" data-acao="fechar-gaveta" aria-label="Fechar">${icone("x")}</button></div>
    <div class="gaveta-corpo">
      <div class="chips-colunas">${etiquetaEstado(s.estado, s.estado_nome)}<span class="etiqueta">Prioridade ${esc(s.prioridade)}</span>
        ${s.revisor ? `<span class="etiqueta">Revisor independente: ${esc(s.revisor)}</span>` : ""}</div>
      <p>${esc(s.pedido)}</p>
      ${s.tarefas.length ? `<div class="secao-titulo">Tarefas do projeto</div><ul class="lista-ficha">${s.tarefas.map((t) => `<li><button class="btn pequeno" data-acao="ver-solicitacao" data-id="${esc(t.id)}">${esc(t.id)}</button> ${esc(t.titulo)} — ${esc(t.estado)}</li>`).join("")}</ul>` : ""}
      ${etapas ? `<div class="secao-titulo">Plano e etapas</div>${etapas}` : ""}
      ${rev.revisor ? `<div class="secao-titulo">Revisão</div><p>${esc(rev.revisor)} conferiu ${(rev.conferido || []).length} etapa(s): ${rev.achados?.length ? esc(rev.achados.join("; ")) : "sem achados"}.</p>` : ""}
      ${s.resultado?.nao_feitas?.length ? `<div class="secao-titulo">O que NÃO foi feito</div><ul class="lista-ficha">${s.resultado.nao_feitas.map((x) => `<li><b>${esc(x.titulo)}</b>: ${esc(x.motivo)}</li>`).join("")}</ul>` : ""}
      ${artefatos ? `<div class="secao-titulo">Arquivos gerados</div><ul class="lista-ficha">${artefatos}</ul>` : ""}
      <div class="secao-titulo">Histórico</div><ul class="lista-ficha">${eventos}</ul>
      ${["concluida", "concluida_parcialmente", "falhou", "cancelada"].includes(s.estado) ? "" :
        `<div class="acoes" style="justify-content:flex-end"><button class="btn" data-acao="cancelar-solicitacao" data-id="${esc(s.id)}">${icone("x")}Cancelar</button></div>`}
    </div>`);
  $("#gaveta").classList.add("larga");
}

// ------------------------------------------------------------------ memória, desempenho, handovers e reunião semanal
async function carregarMemoria() {
  try { E.memoria = await api(`/api/memoria?dias=${E.memoriaDias || 7}`); } catch (e) { avisar(e.message, "erro"); }
}

const NOME_SITUACAO_DESEMP = { ok: ["Bom", "sucesso"], atencao: ["Atenção", "alerta"], insuficiente: ["Insuficiente", "perigo"], sem_dados: ["Sem dados", ""] };

function renderMemoria() {
  const m = E.memoria;
  const acoes = `<button class="btn" data-acao="memoria-pg">${icone("banco")}Copiar memória para o PostgreSQL</button>
    <button class="btn" data-acao="estudo-rodar">${icone("frasco")}Rodada de estudo agora</button>
    <button class="btn primario" data-acao="reuniao-gerar">${icone("historico")}Fazer a reunião semanal agora</button>`;
  if (!m) return cabecalho("Memória e reuniões", "", acoes) + `<div class="carregando">Carregando…</div>`;
  const andar = E.memoriaAndar || "";
  const desemp = m.desempenho.filter((d) => !andar || String(d.andar) === andar)
    .sort((a, b) => (b.eventos - a.eventos)).map((d) => {
      const [t, c] = NOME_SITUACAO_DESEMP[d.situacao] || [d.situacao, ""];
      return `<tr><td>${esc(d.nome)} <small class="muted">${esc(d.id)}</small></td><td>${d.andar}º</td><td class="direita">${d.acertos}</td><td class="direita">${d.erros}</td>
        <td class="direita">${d.aprendizados}</td><td class="direita">${d.taxa === null ? "—" : `${d.taxa}%`}</td><td><span class="etiqueta ${c}">${t}</span></td>
        <td><button class="btn pequeno" data-acao="conversar" data-id="${esc(d.id)}">${icone("chat")}Conversar</button>
        <button class="btn pequeno" data-acao="dossie" data-id="${esc(d.id)}">Dossiê .md</button></td></tr>`;
    }).join("");
  const hos = m.handovers.map((h) => `<div class="ocorrencia ${h.estado === "reaberto" ? "erro" : h.estado === "verificado" ? "" : "aviso"}"><div class="principal">
      <strong>${esc(h.erro)}</strong> <span class="etiqueta">${h.recorrencias}x</span>
      <div class="muted">${esc(h.id)} · ${esc(h.area)} · responsável ${esc(h.responsavel)} · causa: ${esc(h.causa)}</div>
      <div><b>Por que aconteceu:</b> ${esc(h.por_que_aconteceu)}</div>
      <div><b>Por que ainda não foi resolvido:</b> ${esc(h.por_que_nao_resolvido)}</div>
      <div><b>Quem precisa agir:</b> ${esc(h.quem_precisa_agir)}${h.simples ? ` <span class="etiqueta sucesso">erro simples</span>` : ""}${h.escalado ? ` <span class="etiqueta perigo">escalado para ${esc(h.escalado_para)}</span>` : ""}</div>
      <div><b>Para não repetir:</b> ${esc(h.regra)}</div><div class="muted"><b>Como verificar:</b> ${esc(h.como_verificar)}</div></div>
      <select data-handover="${esc(h.id)}">${["aberto", "em_aplicacao", "aplicado", "verificado", "reaberto"].map((e) => `<option ${e === h.estado ? "selected" : ""} value="${e}">${e.replace("_", " ")}</option>`).join("")}</select></div>`).join("");
  const r = m.reunioes[0];
  const ata = r ? r.ata.andares.map((a) => `<div class="cartao" style="margin-bottom:8px"><div class="cartao-corpo">
      <strong>${a.andar}º andar — ${esc(a.nome)}</strong> <span class="muted">líder: ${esc(a.lider_nome)}</span>
      <div class="grade-2" style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:6px">
        <div><div class="secao-titulo">Deu certo</div><ul class="lista-ficha">${a.deu_certo.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
        <div><div class="secao-titulo">Deu errado</div><ul class="lista-ficha">${a.deu_errado.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div></div>
      <div class="secao-titulo">Plano de ação</div><ul class="lista-ficha">${a.plano_de_acao.map((x) => `<li>${x.simples ? `<span class="etiqueta sucesso">simples</span> ` : ""}${esc(x.acao)} — <b>${esc(x.quem_precisa_agir || x.responsavel_nome || x.responsavel)}</b>, até ${esc(x.prazo)} <span class="muted">(${esc(x.motivo)})</span></li>`).join("") || "<li>Nada novo a corrigir.</li>"}</ul>
    </div></div>`).join("") : `<p class="muted">Nenhuma reunião ainda. Ela acontece sozinha uma vez por semana, ou clique em “Fazer a reunião semanal agora”.</p>`;
  return cabecalho("Memória e reuniões", "O que cada funcionário acertou, errou e aprendeu (com a origem de cada fato), os handovers de cada área — todo erro vira regra para não repetir — e a reunião semanal da liderança.", acoes) +
    `<div class="dica">${icone("info")}<p>Desempenho insuficiente (pelo menos 5 eventos e menos de 70% de acerto): 1ª reunião = plano de melhoria; 2ª = proposta de desligamento, que <b>só você</b> aprova em Solicitações.
      Cargos fixos são código do robô: desempenho ruim vira defeito para a TI corrigir com teste automatizado.</p></div>
    <div class="secao-titulo">Reunião ao vivo com cada coordenador (calculada agora, sem gravar)</div>
    <div class="chips-colunas">${[1, 2, 3, 4, 5].map((a) => `<button class="btn pequeno ${String(E.aoVivoAndar) === String(a) ? "primario" : ""}" data-acao="ao-vivo" data-andar="${a}">${a}º andar</button>`).join("")}</div>
    ${renderAoVivo()}
    <div class="secao-titulo" style="margin-top:12px">PDCA contínuo (todos os andares)</div>
    <div class="chips-colunas"><span class="etiqueta alerta">P · planejar ${m.pdca.planejar}</span><span class="etiqueta info">D · fazendo ${m.pdca.fazer}</span>
      <span class="etiqueta">C · checando ${m.pdca.checar}</span><span class="etiqueta sucesso">A · padronizado ${m.pdca.agir}</span>
      <span class="muted">Última rodada de estudo: ${m.ultimo_estudo ? esc(dataT(m.ultimo_estudo.criada_em)) + " — " + esc(m.ultimo_estudo.texto) : "ainda não houve"}</span></div>
    <div class="secao-titulo" style="margin-top:12px">Ideias da Iara para o futuro (tiradas da memória)</div>
    <ul class="lista-ficha">${m.ideias.map((i) => `<li><b>${esc(i.titulo)}</b> — por quê: ${esc(i.motivo)}. <i>Primeiro passo:</i> ${esc(i.primeiro_passo)} <span class="muted">(dono: ${esc(i.dono_nome)})</span></li>`).join("")}</ul>
    <div class="secao-titulo" style="margin-top:12px">Boas práticas padronizadas (${m.boas_praticas.length})</div>
    ${m.boas_praticas.length ? `<ul class="lista-ficha">${m.boas_praticas.map((b) => `<li><b>${esc(b.pratica)}</b> <span class="muted">— ${esc(b.area)} · ${esc(b.id)} · prova: ${esc(b.evidencia)}</span></li>`).join("")}</ul>`
      : `<p class="muted">Ainda nenhuma: um handover vira boa prática quando é aplicado e o erro não volta.</p>`}
    <div class="secao-titulo" style="margin-top:12px">Última reunião semanal ${r ? `· ${esc(dataT(r.data_hora))}` : ""}</div>${ata}
    ${r && (r.ata.pdi.length || r.ata.propostas_desligamento.length || r.ata.defeitos_de_codigo.length) ? `<p>Plano de melhoria: ${esc(r.ata.pdi.join(", ") || "ninguém")} · Desligamento proposto: ${esc(r.ata.propostas_desligamento.join(", ") || "ninguém")} · Defeito de código: ${esc(r.ata.defeitos_de_codigo.join(", ") || "nenhum")}</p>` : ""}
    <div class="secao-titulo" style="margin-top:12px">Desempenho por funcionário
      <select id="mem-dias">${[[7, "7 dias"], [30, "30 dias"], [90, "90 dias"]].map(([d, t]) => `<option value="${d}" ${Number(E.memoriaDias || 7) === d ? "selected" : ""}>${t}</option>`).join("")}</select>
      <select id="mem-andar"><option value="">Todos os andares</option>${[1, 2, 3, 4, 5].map((a) => `<option value="${a}" ${andar === String(a) ? "selected" : ""}>${a}º andar</option>`).join("")}</select></div>
    <div class="tabela-envoltorio"><table class="tabela"><thead><tr><th>Funcionário</th><th>Andar</th><th class="direita">Acertos</th><th class="direita">Erros</th><th class="direita">Aprendizados</th><th class="direita">Taxa</th><th>Situação</th><th></th></tr></thead>
      <tbody>${desemp}</tbody></table></div>
    <div class="secao-titulo" style="margin-top:12px">Handovers por área (${m.handovers.length})</div>${hos || `<p class="muted">Nenhum erro registrado ainda.</p>`}`;
}

function renderAoVivo() {
  const v = E.aoVivo;
  if (!E.aoVivoAndar) return `<p class="muted">Escolha um andar para ouvir o coordenador agora.</p>`;
  if (!v) return `<div class="carregando">Calculando…</div>`;
  return v.andares.map((a) => `<div class="cartao" style="margin:8px 0"><div class="cartao-corpo">
      <strong>${a.andar}º andar — ${esc(a.nome)}</strong> <span class="muted">coordenação: ${esc(a.lider_nome)}</span>
      <button class="btn pequeno" data-acao="conversar" data-id="${esc(a.lider)}">${icone("chat")}Conversar com ${esc(a.lider_nome)}</button>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:6px">
        <div><div class="secao-titulo">Deu certo</div><ul class="lista-ficha">${a.deu_certo.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
        <div><div class="secao-titulo">Deu errado</div><ul class="lista-ficha">${a.deu_errado.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div></div>
      <div class="secao-titulo">Em andamento agora</div><ul class="lista-ficha">${a.agora.map((x) => `<li>${esc(x)}</li>`).join("") || "<li>Nada em andamento.</li>"}</ul>
      <div class="secao-titulo">Plano de ação</div><ul class="lista-ficha">${a.plano_de_acao.map((x) => `<li>${esc(x.acao)} — <b>${esc(x.quem_precisa_agir || x.responsavel_nome)}</b>, até ${esc(x.prazo)}</li>`).join("") || "<li>Nada novo.</li>"}</ul>
      <div class="muted">PDCA do andar: ${a.pdca.planejar} planejar · ${a.pdca.fazer} fazendo · ${a.pdca.checar} checando · ${a.pdca.agir} padronizados</div>
    </div></div>`).join("") + (v.em_risco.length ? `<p class="muted">Abaixo do mínimo: ${v.em_risco.map((d) => `${esc(d.nome)} (${d.taxa}%)`).join(", ")}</p>` : "");
}

// ------------------------------------------------------------------ chat da empresa (todos os funcionários, com filtros)
async function carregarChat() {
  try { E.chat = await api("/api/funcionarios"); } catch (e) { avisar(e.message, "erro"); }
}

function renderChat() {
  const c = E.chat;
  if (!c) return cabecalho("Chat da empresa", "") + `<div class="carregando">Carregando…</div>`;
  const f = E.filtroChat || (E.filtroChat = {});
  const areas = [...new Set(c.funcionarios.map((p) => p.area).filter(Boolean))].sort();
  const niveis = [...new Set(c.funcionarios.map((p) => p.nivel))];
  const busca = (f.texto || "").toLowerCase();
  const lista = c.funcionarios.filter((p) => (!f.andar || String(p.andar) === f.andar) && (!f.area || p.area === f.area)
    && (!f.nivel || p.nivel === f.nivel) && (!f.lideres || p.lider)
    && (!busca || `${p.nome} ${p.papel} ${p.area}`.toLowerCase().includes(busca)));
  const sel = (id, opcoes, rotulo) => `<select data-filtro-chat="${id}"><option value="">${rotulo}</option>${opcoes.map(([v, t]) => `<option value="${esc(v)}" ${String(f[id] || "") === String(v) ? "selected" : ""}>${esc(t)}</option>`).join("")}</select>`;
  return cabecalho("Chat da empresa", `Fale com qualquer um dos ${c.funcionarios.length} funcionários. Cada um responde com a ferramenta do próprio contrato, mostra de onde veio a resposta e, se não for com ele, passa para quem faz. Quando não sabe, diz que não sabe. ${c.ia.configurado ? "" : "Sem IA: respostas por regras, cálculos e código."}`) +
    `<div class="filtros-canal" style="margin-bottom:12px">${sel("andar", Object.entries(c.andares).map(([a, n]) => [a, `${a}º · ${n}`]), "Todos os andares")}
      ${sel("area", areas.map((a) => [a, a]), "Todas as áreas")}${sel("nivel", niveis.map((n) => [n, n]), "Todos os níveis")}
      <label style="display:flex;gap:6px;align-items:center"><input type="checkbox" data-filtro-chat="lideres" ${f.lideres ? "checked" : ""}> só coordenação</label>
      <label class="campo-busca">${icone("busca")}<input type="text" id="chat-busca" placeholder="Nome, cargo ou área…" value="${esc(f.texto || "")}"></label></div>
    <section class="equipe">${lista.map((p) => `<article class="cartao agente" data-acao="conversar" data-id="${esc(p.id)}" style="cursor:pointer">
      <div class="agente-topo"><span class="avatar" style="background:${esc(p.cor || "#64748B")}">${esc(p.nome.slice(0, 1))}</span>
        <div><strong>${esc(p.nome)}</strong><small>${esc(p.papel)} · ${esc(p.nivel)}</small></div></div>
      <p class="muted" style="margin:6px 0 0">${p.andar}º andar${p.area ? ` · ${esc(p.area)}` : ""}${p.lider ? " · coordenação" : ""}</p></article>`).join("") || `<p class="muted">Ninguém com esses filtros.</p>`}</section>`;
}

// ------------------------------------------------------------------ registro de páginas e ações
Object.assign(PAGINAS, {
  solicitacoes: { titulo: "Solicitações", render: renderSolicitacoes, carregar: carregarSolicitacoes },
  memoria: { titulo: "Memória e reuniões", render: renderMemoria, carregar: carregarMemoria },
  chat: { titulo: "Chat da empresa", render: renderChat, carregar: carregarChat },
});
Object.assign(ACOES, {
  "ao-vivo": async (el) => { E.aoVivoAndar = el.dataset.andar; E.aoVivo = null; desenhar();
    try { E.aoVivo = await api(`/api/reuniao/ao-vivo?andar=${el.dataset.andar}`); } catch (e) { avisar(e.message, "erro"); } desenhar(); },
  "estudo-rodar": (el) => comCarregando(el, async () => { const r = await api("/api/estudo/rodar", { corpo: {} });
    avisar(`Rodada de estudo: ${r.funcionarios} funcionários, ${r.aprovados} aprovados na prova.`, "sucesso"); await carregarMemoria(); desenhar(); }),
  conversar: (el) => abrirConversa(el.dataset.id),
  "retomar-conversa": (el) => abrirConversa(el.dataset.id, el.dataset.conversa),
  "conversa-enviar": (el) => enviarConversa(el),
  "conversa-anexar": anexarConversa,
  "ver-solicitacao": (el) => verSolicitacao(el.dataset.id),
  "recarregar-solic": async () => { await carregarSolicitacoes(); desenhar(); },
  "solic-anexar": () => {
    const input = document.createElement("input"); input.type = "file"; input.accept = ".xlsx,.xlsm,.xls,.csv,.txt";
    input.onchange = async () => { const a = input.files[0]; if (!a) return;
      try { E.solicAnexo = await api("/api/conversa/anexar", { arquivo: a }); desenhar(); } catch (e) { avisar(e.message, "erro"); } };
    input.click();
  },
  "solic-criar": (el) => comCarregando(el, async () => {
    const texto = ($("#solic-texto")?.value || "").trim();
    if (!texto) throw new Error("Descreva o que você precisa.");
    const r = await api("/api/solicitacoes/criar", { corpo: { texto, prioridade: $("#solic-prioridade").value, arquivo: E.solicAnexo?.arquivo || null } });
    E.solicAnexo = null; avisar(`Registrado: ${r.id}`, "sucesso");
    await carregarSolicitacoes(); desenhar(); verSolicitacao(r.id);
  }),
  aprovar: (el) => comCarregando(el, async () => {
    await api("/api/aprovacoes/decidir", { corpo: { id: el.dataset.id, aprovado: el.dataset.valor === "1" } });
    avisar(el.dataset.valor === "1" ? "Aprovado: a tarefa continua." : "Recusado: a etapa não será executada.", "sucesso");
    await carregarSolicitacoes(); desenhar();
  }),
  "cancelar-solicitacao": async (el) => {
    const ok = await confirmar({ titulo: "Cancelar esta solicitação?", texto: "As etapas que ainda não rodaram não serão executadas.", botao: "Cancelar solicitação", perigo: true });
    if (!ok) return;
    try { await api("/api/solicitacoes/cancelar", { corpo: { id: el.dataset.id } }); fecharGaveta(); await carregarSolicitacoes(); desenhar(); }
    catch (e) { avisar(e.message, "erro"); }
  },
  "reuniao-gerar": (el) => comCarregando(el, async () => { await api("/api/reuniao/gerar", { corpo: {} }); avisar("Reunião registrada e publicada no #lideranca.", "sucesso"); await carregarMemoria(); desenhar(); }),
  "memoria-pg": (el) => comCarregando(el, async () => {
    const r = await api("/api/memoria/sincronizar", { corpo: {} });
    avisar(r.ok ? `Copiado para ${r.schema}.memoria_experiencias (${r.experiencias}) e ${r.schema}.memoria_handovers (${r.handovers}).` : r.motivo, r.ok ? "sucesso" : "");
  }),
  dossie: (el) => comCarregando(el, async () => { const r = await api("/api/memoria/exportar", { corpo: { id: el.dataset.id } }); avisar(`Dossiê gravado em ${r.arquivo}`, "sucesso"); }),
});

document.addEventListener("keydown", (e) => {
  if (e.target.id === "conversa-texto" && e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviarConversa($("[data-acao='conversa-enviar']")); }
});
document.addEventListener("change", async (e) => {
  if (e.target.dataset.filtroSolic) { E.filtroSolic[e.target.dataset.filtroSolic] = e.target.value; await carregarSolicitacoes(); desenhar(); }
  if (e.target.dataset.handover) {
    try { await api("/api/handovers/estado", { corpo: { id: e.target.dataset.handover, estado: e.target.value } }); } catch (err) { avisar(err.message, "erro"); }
    await carregarMemoria(); desenhar();
  }
  if (e.target.dataset.filtroChat) { E.filtroChat[e.target.dataset.filtroChat] = e.target.type === "checkbox" ? e.target.checked : e.target.value; desenhar(); }
  if (e.target.id === "mem-dias") { E.memoriaDias = e.target.value; await carregarMemoria(); desenhar(); }
  if (e.target.id === "mem-andar") { E.memoriaAndar = e.target.value; desenhar(); }
});
document.addEventListener("input", (e) => {
  if (e.target.id === "chat-busca") {
    E.filtroChat.texto = e.target.value;
    clearTimeout(E._buscaChat);
    E._buscaChat = setTimeout(() => { desenhar(); const c = $("#chat-busca"); if (c) { c.focus(); c.setSelectionRange(c.value.length, c.value.length); } }, 250);
  }
  if (e.target.id === "solic-busca") {
    E.filtroSolic.texto = e.target.value;
    clearTimeout(E._buscaSolic);
    E._buscaSolic = setTimeout(async () => { await carregarSolicitacoes(); desenhar(); const c = $("#solic-busca"); if (c) { c.focus(); c.setSelectionRange(c.value.length, c.value.length); } }, 350);
  }
});
// tarefas rodam em segundo plano: a página de solicitações se atualiza sozinha enquanto estiver aberta
setInterval(async () => {
  if (E.pagina !== "solicitacoes" || document.activeElement?.id === "solic-texto") return;
  await carregarSolicitacoes(); desenharSemPerderFoco();
}, 4000);
// abrir conversa direto pelo endereço: inicio.html#conversa=<id> (usado pela ficha do escritório 3D)
function abrirConversaPeloEndereco() {
  const m = location.hash.match(/^#conversa=([\w-]+)/);
  if (m) { history.replaceState(null, "", "#solicitacoes"); irPara("solicitacoes").then(() => abrirConversa(m[1])); }
}
window.addEventListener("hashchange", abrirConversaPeloEndereco);
abrirConversaPeloEndereco();
