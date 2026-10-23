// Página "No celular": os passos do diagnóstico (robo/diagnostico_celular.py) e o QR code do endereço, para abrir o
// acompanhamento no celular apontando a câmera para a tela do notebook. Só lê.

Object.assign(E, { celular: null });

async function carregarCelular() {
  try { E.celular = await api("/api/celular/diagnostico"); } catch (e) { avisar(e.message, "erro"); }
}

const CEL_SITUACAO = { ok: ["sucesso", "ok"], atencao: ["alerta", "atenção"], falha: ["perigo", "falha"], nao_se_aplica: ["", "informação"] };

function renderCelular() {
  const c = E.celular;
  const acoes = `<button class="btn" data-acao="celular-recarregar">${icone("recarregar")}Conferir de novo</button>`;
  const desc = "Abra o robô no celular em 3 toques: abra a câmera, aponte para o quadrado e toque no link. " +
    "Funciona no Wi-Fi de casa (ou pela VPN Tailscale) e usa a mesma senha deste painel.";
  if (!c) return cabecalho("No celular", desc, acoes) + `<div class="carregando">Conferindo…</div>`;
  const falhas = c.itens.filter((i) => i.situacao === "falha").length;
  const qr = c.url && c.qr_svg
    ? `<img class="cel-qr" alt="QR code do endereço ${esc(c.url)}" src="data:image/svg+xml;charset=utf-8,${encodeURIComponent(c.qr_svg)}">`
    : `<p class="muted">${c.url ? "Para ver o QR code aqui, instale o pacote segno (rode instalar.bat de novo)." : "Sem rede: não há endereço para o celular."}</p>`;
  const passos = c.itens.map((i) => {
    const [cor, rot] = CEL_SITUACAO[i.situacao] || ["", i.situacao];
    return `<li><div><b>${esc(i.titulo)}</b> <span class="etiqueta ${cor}">${esc(rot)}</span></div>
      <div class="muted">${esc(i.detalhe)}</div>${i.corrigir && i.situacao !== "ok" ? `<div><small>→ ${esc(i.corrigir)}</small></div>` : ""}</li>`;
  }).join("");
  return cabecalho("No celular", desc, acoes) + `<div class="grade duas">
    <div class="cartao"><div class="cartao-corpo cel-cartao-qr">${qr}
      ${c.url ? `<p><b>${esc(c.url)}</b></p>` : ""}
      <p class="muted">${falhas ? `${falhas} passo(s) com falha: corrija o primeiro da lista antes de tentar no celular.` : "Tudo pronto do lado do notebook."}</p>
    </div></div>
    <div class="cartao"><div class="cartao-corpo"><ol class="cel-passos">${passos}</ol></div></div>
  </div>`;
}

Object.assign(PAGINAS, { celular: { titulo: "No celular", render: renderCelular, carregar: carregarCelular } });
Object.assign(ACOES, {
  "celular-recarregar": (el) => comCarregando(el, async () => { await carregarCelular(); desenhar(); }),
});
