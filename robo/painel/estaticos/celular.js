// Acompanhamento pelo celular: lê /api/resumo a cada 10 s. Ações (pausar, retomar, reprocessar, ver log) só aparecem
// se o dono ligou celular.acoes no notebook; cada uma é registrada lá.
"use strict";
(function () {
  const $ = (id) => document.getElementById(id);
  let relogio = null;

  function el(tag, classe, texto) {
    const e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texto !== undefined && texto !== null) e.textContent = String(texto);
    return e;
  }

  function mostrar(login) {
    $("tela-login").hidden = !login;
    $("tela-resumo").hidden = login;
    $("sair").hidden = login;
    if (login) { clearInterval(relogio); relogio = null; $("senha").focus(); }
  }

  function dataBr(iso) {
    if (!iso) return "—";
    const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
    return m ? `${m[3]}/${m[2]} ${m[4]}:${m[5]}` : String(iso);
  }

  function kpi(rotulo, valor, det, tom, largo) {
    const c = el("div", "kpi" + (tom ? " " + tom : "") + (largo ? " largo" : ""));
    c.append(el("div", "rotulo", rotulo), el("div", "valor", valor), el("div", "det", det || ""));
    return c;
  }

  // no celular, lista longa vira "a, b, c, d e mais N" (a lista inteira está no painel do notebook)
  function resumir(nomes, max = 4) {
    return nomes.length > max ? `${nomes.slice(0, max).join(", ")} e mais ${nomes.length - max}` : nomes.join(", ");
  }

  function indisponivel(p) { return !p || p.indisponivel; }

  function lista(alvo, itens, vazio, montar) {
    const ul = $(alvo);
    ul.replaceChildren();
    if (!itens || !itens.length) { const li = el("li"); li.append(el("span", "vazio", vazio)); ul.append(li); return; }
    itens.forEach((x) => ul.append(montar(x)));
  }

  function desenharAcoes(a) {
    const ligadas = !!(a && a.ligadas);
    $("aba-acoes").hidden = !ligadas;
    if (!ligadas) return;
    lista("reprovados", a.reprovados, "Nenhuma planilha reprovada.", (nome) => {
      const li = el("li"), b = el("button", "acao linha", nome);
      b.addEventListener("click", () => agir("reprocessar", nome));
      li.append(b);
      return li;
    });
  }

  async function agir(acao, nome) {
    const textos = { pausar: "Pausar o robô? Os arquivos novos ficam esperando na pasta.", retomar: "Retomar o robô?",
      reprocessar: `Mandar "${nome}" de volta para a fila?` };
    if (textos[acao] && !confirm(textos[acao])) return;
    $("resultado-acao").textContent = "Enviando…";
    try {
      const resp = await fetch("/api/acao", { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-Robo-Celular": "1" }, body: JSON.stringify({ acao, nome }) });
      const r = await resp.json();
      if (resp.status === 401) return mostrar(true);
      if (!resp.ok) throw new Error(r.erro || resp.status);
      if (acao === "ver_log") {
        $("log").hidden = false;
        $("log").textContent = r.linhas.length ? r.linhas.join("\n") : "Log vazio.";
        $("resultado-acao").textContent = "";
        return;
      }
      $("resultado-acao").textContent = acao === "reprocessar" ? `${r.nome} voltou para a fila.`
        : (r.ligado ? "Robô ligado." : "Robô pausado.");
      atualizar();
    } catch (e) {
      $("resultado-acao").textContent = "Não deu certo: " + e.message;
    }
  }

  document.querySelectorAll(".botoes .acao").forEach((b) => b.addEventListener("click", () => agir(b.dataset.acao)));

  function desenhar(r) {
    desenharAcoes(r.acoes);
    $("atualizado").textContent = "Atualizado em " + r.gerado_em + " · renova a cada 10 s";
    const g = $("cartoes");
    g.replaceChildren();
    const robo = r.robo || {};
    g.append(indisponivel(robo) ? kpi("Robô", "—", robo.indisponivel, "atencao")
      : robo.ligado === null ? kpi("Robô", "—", "sem informação do monitor", "atencao")
      : kpi("Robô", robo.ligado ? "Ligado" : "Pausado", robo.fila == null ? "" : `${robo.fila} arquivo(s) na fila`, robo.ligado ? "bom" : "atencao"));
    const ro = r.rotinas || {};
    if (indisponivel(ro)) g.append(kpi("Rotinas", "—", ro.indisponivel, "atencao"));
    else {
      const probl = ro.atrasadas.length + ro.com_erro.length;
      const det = probl ? [ro.com_erro.length ? "erro: " + ro.com_erro.map((x) => x.nome).join(", ") : "",
        ro.atrasadas.length ? "atrasadas: " + resumir(ro.atrasadas) : ""].filter(Boolean).join(" · ") : `${ro.total} rotinas em dia`;
      g.append(kpi("Rotinas", probl ? `${probl} com problema` : "Em dia", det, ro.com_erro.length ? "ruim" : (probl ? "atencao" : "bom")));
    }
    const t = r.treino || {};
    g.append(indisponivel(t) ? kpi("Treino 24 h", "—", t.indisponivel, "atencao")
      : kpi("Treino 24 h", t.tentativas_24h ? `${t.pct_24h}%` : "—",
        `${t.acertos_24h} de ${t.tentativas_24h} certas · ${t.pessoas_24h} de ${t.elegiveis} pessoas`,
        t.tentativas_24h ? (t.pct_24h >= 80 ? "bom" : "atencao") : "atencao"));
    const d = r.decisoes || {};
    g.append(indisponivel(d) ? kpi("Decisões", "—", d.indisponivel, "atencao")
      : kpi("Decisões", d.atrasadas.length ? `${d.atrasadas.length} atrasada(s)` : "Em dia", `${d.abertas} aberta(s)`,
        d.atrasadas.length ? "ruim" : "bom"));
    const cx = r.caixa || {};
    g.append(indisponivel(cx) ? kpi("Caixa do dono", "—", cx.indisponivel, "atencao")
      : kpi("Caixa do dono", cx.novas ? `${cx.novas} esperando você` : "Nada pendente",
        cx.novas ? `${cx.ideias_novas} ideia(s) · ${cx.pendencias_novas} decisão(ões) — decida no painel` : "ideias e decisões em dia",
        cx.novas ? "atencao" : "bom"));
    const ti = r.ti || {};
    g.append(indisponivel(ti) ? kpi("TI", "—", ti.indisponivel, "atencao")
      : kpi("Ronda de TI", ti.saudavel === false ? "Com alerta" : (ti.saudavel ? "Saudável" : "—"), dataBr(ti.data_hora),
        ti.saudavel === false ? "ruim" : (ti.saudavel ? "bom" : "atencao")));
    const b = r.backup || {};
    g.append(indisponivel(b) ? kpi("Backup", "—", b.indisponivel, "atencao")
      : kpi("Último backup", dataBr(b.sqlite), "PostgreSQL: " + dataBr(b.postgres), b.sqlite ? "bom" : "atencao"));

    lista("planilhas", indisponivel(r.planilhas) ? [] : r.planilhas, "Nenhuma planilha processada ainda.", (p) => {
      const li = el("li"), txt = el("div");
      txt.append(el("div", "princ", p.arquivo), el("div", "sec", `${dataBr(p.data_hora)} · ${p.linhas || 0} linhas`));
      const ok = /sucesso|aprov/i.test(p.status);
      li.append(txt, el("span", "selo " + (ok ? "ok" : "falha"), ok ? "Aprovada" : "Reprovada"));
      return li;
    });
    lista("decisoes", indisponivel(d) ? [] : d.atrasadas, "Nenhuma decisão atrasada.", (x) => {
      const li = el("li"), txt = el("div");
      txt.append(el("div", "princ", x.texto), el("div", "sec", `${x.dono} · prazo ${dataBr(x.prazo + " 00:00").slice(0, 5)}`));
      li.append(txt);
      return li;
    });
    const gt = r.gente || {};
    const gg = $("gente");
    gg.replaceChildren();
    const conta = (x, rotulo, vazio) => (x ? kpi(rotulo, String(x["24h"]), `${x["7d"]} em 7 dias`, x["24h"] ? "bom" : "")
      : kpi(rotulo, "—", vazio, "atencao"));
    if (!indisponivel(gt)) {
      gg.append(conta(gt.conversas, "Conversas 24 h", "ainda não registradas"),
        conta(gt.mentorias, "Mentorias 24 h", "módulo ainda não ativo"),
        conta(gt.rh, "RH 24 h", "módulo ainda não ativo"),
        conta(gt.lideranca, "Liderança decidiu 24 h", "módulo ainda não ativo"));
    }
    lista("feed", indisponivel(r.ao_vivo) ? [] : r.ao_vivo, "Nada registrado ainda.", (x) => {
      const li = el("li"), l1 = el("div", "linha1");
      const rot = { canal: "canal", conversa: "conversa", acerto: "acertou", erro: "errou", nivel: "nível", rh: "RH", lideranca: "liderança" };
      l1.append(el("span", "", `${dataBr(x.data_hora)} · ${x.quem}`), el("span", "tag " + x.tipo, rot[x.tipo] || x.tipo));
      li.append(l1, el("div", "texto", x.texto));
      return li;
    });
    lista("andares", indisponivel(r.andares) ? [] : r.andares, "Sem treino registrado.", (a) => {
      const li = el("li"), txt = el("div");
      txt.style.flex = "1";
      txt.append(el("div", "princ", `${a.andar}º · ${a.nome}`),
        el("div", "sec", `${a.pessoas_24h} de ${a.quadro} pessoas treinaram · ${a.tentativas_24h} tentativas · nível médio ${a.nivel_medio ?? "—"}`));
      const barra = el("div", "barra"), s = el("span");
      s.style.width = (a.pct_24h ?? 0) + "%";
      barra.append(s);
      txt.append(barra);
      li.append(txt, el("span", "selo " + (a.pct_24h == null ? "" : a.pct_24h >= 80 ? "ok" : "falha"), a.pct_24h == null ? "—" : a.pct_24h + "%"));
      return li;
    });
    lista("alertas", indisponivel(ti) ? [] : ti.alertas, "Nenhum alerta ativo.", (a) => {
      const li = el("li");
      li.append(el("div", "sec", a));
      return li;
    });
  }

  async function atualizar() {
    try {
      const resp = await fetch("/api/resumo", { credentials: "same-origin", cache: "no-store" });
      const r = await resp.json();
      if (resp.status === 401 || r.login) return mostrar(true);
      if (!resp.ok) throw new Error(r.erro || resp.status);
      mostrar(false);
      desenhar(r);
      if (!relogio) relogio = setInterval(atualizar, 10000);
    } catch (e) {
      $("atualizado").textContent = "Sem conexão com o notebook (" + e.message + "). Tentando de novo…";
    }
  }

  $("form-login").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    $("erro-login").textContent = "";
    try {
      const resp = await fetch("/entrar", { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ senha: $("senha").value }) });
      const r = await resp.json();
      if (!resp.ok) { $("erro-login").textContent = r.erro || "Não foi possível entrar."; return; }
      $("senha").value = "";
      atualizar();
    } catch (e) {
      $("erro-login").textContent = "Sem conexão com o notebook.";
    }
  });

  $("sair").addEventListener("click", async () => {
    await fetch("/sair", { method: "POST", credentials: "same-origin" }).catch(() => {});
    mostrar(true);
  });

  document.querySelectorAll(".aba").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".aba").forEach((x) => x.classList.toggle("ativa", x === b));
    document.querySelectorAll("[data-painel]").forEach((p) => { p.hidden = p.dataset.painel !== b.dataset.aba; });
  }));

  // ---------------------------------------------------------------- instalar como app
  // O service worker (tela offline) só existe em HTTPS; no Wi-Fi de casa (http) o navegador não deixa, e tudo bem.
  if ("serviceWorker" in navigator && window.isSecureContext) {
    navigator.serviceWorker.register("/service-worker.js").catch(() => {});
  }
  let pedidoInstalar = null;
  window.addEventListener("beforeinstallprompt", (ev) => { ev.preventDefault(); pedidoInstalar = ev; $("instalar").hidden = false; });
  $("instalar").addEventListener("click", async () => {
    if (!pedidoInstalar) return;
    pedidoInstalar.prompt();
    await pedidoInstalar.userChoice.catch(() => null);
    pedidoInstalar = null;
    $("instalar").hidden = true;
  });
  const instalado = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  if (!instalado && /iPhone|iPad|iPod/.test(navigator.userAgent)) {
    $("dica-instalar").textContent = "Para virar app: toque em Compartilhar e depois em \"Adicionar à Tela de Início\".";
    $("dica-instalar").hidden = false;
  }

  atualizar();
})();
