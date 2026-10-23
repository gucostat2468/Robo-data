"""Diagnóstico do acompanhamento pelo celular: `python -m robo diagnostico-celular`.

Confere, na ordem em que o problema costuma acontecer, cada passo entre o notebook e o celular:
ligado no config → senha do painel → rede de casa → servidor ouvindo → resposta pelo IP da rede (o caminho do
celular) → firewall do Windows → instalação como app → ações. No fim mostra o endereço e um QR code para apontar a
câmera do celular.

Só LÊ e testa: não altera nada. Cada item volta como (situação, título, detalhe, como corrigir), com as mesmas
situações do `python -m robo diagnostico`: ok | atencao | falha | nao_se_aplica.

O QR code usa o pacote `segno` (grátis, só Python). Sem ele, o endereço aparece por escrito e o diagnóstico avisa.
"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request

from robo.diagnostico_pc import ATENCAO, FALHA, NA, OK

TEMPO_REDE_S = 3


def _conf(cfg) -> dict:
    from robo.painel import celular
    return {**celular.configuracao(cfg), "acoes": bool((cfg.dados.get("celular") or {}).get("acoes", False))}


def _sem_proxy():
    """O teste é na rede de casa: nunca passa por proxy, mesmo que o computador tenha um configurado."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def endereco(cfg, ip: str | None = None) -> str | None:
    from robo.painel import celular
    ip = ip or celular.ip_da_rede()
    return f"http://{ip}:{_conf(cfg)['porta']}/" if ip else None


# ----------------------------------------------------------------------------------------------- passos
def _ligado(cfg, ctx) -> tuple:
    if _conf(cfg)["habilitado"]:
        return OK, "1. Ligado no config.yaml", "celular.habilitado = true", ""
    return FALHA, "1. Ligado no config.yaml", "o acompanhamento pelo celular está desligado", \
        "rode: python -m robo celular --ligar  (depois feche e abra o robô)"


def _senha(cfg, ctx) -> tuple:
    if (cfg.painel or {}).get("senha_hash"):
        return OK, "2. Senha do painel", "definida (o celular usa a mesma)", ""
    return FALHA, "2. Senha do painel", "o painel está sem senha: por segurança o servidor do celular não liga", \
        "rode: python -m robo senha"


def _rede(cfg, ctx) -> tuple:
    from robo.painel import celular
    ip = ctx.get("ip")
    if not ip:
        return FALHA, "3. Rede de casa", "este computador não está em nenhuma rede (sem IP)", "conecte o notebook no Wi-Fi de casa"
    if not celular.ip_privado(ip):
        return ATENCAO, "3. Rede de casa", f"IP {ip} não é de rede de casa: o servidor do celular recusa endereços públicos", \
            "use o Wi-Fi de casa ou a VPN Tailscale"
    if os.name == "nt":
        from robo import diagnostico_pc
        situacao, _, detalhe, corrigir = diagnostico_pc._rede(cfg)
        return situacao, "3. Rede de casa", detalhe, corrigir
    return OK, "3. Rede de casa", f"IP {ip}", ""


def _ouvindo(cfg, ctx) -> tuple:
    porta = _conf(cfg)["porta"]
    try:
        with socket.create_connection(("127.0.0.1", porta), timeout=TEMPO_REDE_S):
            pass
    except OSError:
        ctx["ouvindo"] = False
        return FALHA, "4. Servidor do celular", f"nada respondendo na porta {porta} deste computador", \
            "abra o robô (python -m robo app). Se já está aberto, veja no log se a porta está ocupada"
    ctx["ouvindo"] = True
    return OK, "4. Servidor do celular", f"ouvindo na porta {porta}", ""


def _pela_rede(cfg, ctx) -> tuple:
    """O caminho do celular: o IP da rede, não o 127.0.0.1. Se aqui falha e o passo 4 passou, é firewall ou rede."""
    url = endereco(cfg, ctx.get("ip"))
    if not url:
        return NA, "5. Resposta pelo IP da rede", "sem IP de rede para testar", ""
    if not ctx.get("ouvindo"):
        return NA, "5. Resposta pelo IP da rede", "pulado: o servidor não está ouvindo (passo 4)", ""
    try:
        with _sem_proxy().open(url + "manifest.webmanifest", timeout=TEMPO_REDE_S) as r:
            nome = json.loads(r.read()).get("short_name")
    except (urllib.error.URLError, OSError, ValueError) as e:
        return FALHA, "5. Resposta pelo IP da rede", f"{url} não respondeu ({e})", \
            "provável firewall: no Windows, Segurança do Windows → Firewall → Permitir um app → Python → marque 'Privada'"
    if nome != "Robô":
        return ATENCAO, "5. Resposta pelo IP da rede", f"{url} respondeu, mas não parece o robô", \
            "outro programa usa esta porta: mude celular.porta no config.yaml"
    return OK, "5. Resposta pelo IP da rede", f"{url} respondeu como o celular vai ver", ""


def _firewall(cfg, ctx) -> tuple:
    if os.name != "nt":
        return NA, "6. Firewall do Windows", "este computador não é Windows", ""
    from robo import diagnostico_pc
    situacao, _, detalhe, corrigir = diagnostico_pc._celular(cfg)
    return situacao, "6. Firewall do Windows", detalhe, corrigir


def _instalavel(cfg, ctx) -> tuple:
    """Honesto: o modo offline (service worker) só existe em HTTPS. Na rede de casa é http, então o atalho funciona,
    mas a tela offline e a instalação completa no Android dependem de HTTPS (Tailscale grátis resolve)."""
    return NA, "7. Instalar como app", "pelo Wi-Fi de casa (http) o atalho na tela de início funciona; tela offline e "\
        "instalação completa no Android exigem HTTPS", "para HTTPS grátis: Tailscale nos dois aparelhos e "\
        "'tailscale serve --bg 8766' no notebook (ver README §13)"


def _acoes(cfg, ctx) -> tuple:
    if _conf(cfg)["acoes"]:
        return OK, "8. Ações pelo celular", "ligadas: reprocessar, pausar, retomar e ver log (cada uma registrada)", ""
    return NA, "8. Ações pelo celular", "desligadas (padrão): o celular só acompanha", \
        "para ligar, no config.yaml: celular: {acoes: true}"


PASSOS = [_ligado, _senha, _rede, _ouvindo, _pela_rede, _firewall, _instalavel, _acoes]


def rodar(cfg, ip: str | None = "auto") -> list[dict]:
    """ip='auto' descobre o IP da rede; None simula 'sem rede'; um texto força o IP (usado nos testes)."""
    from robo.painel import celular
    ctx = {"ip": celular.ip_da_rede() if ip == "auto" else ip}
    itens = []
    for f in PASSOS:
        try:
            situacao, titulo, detalhe, corrigir = f(cfg, ctx)
        except Exception as e:
            situacao, titulo, detalhe, corrigir = FALHA, f.__name__.strip("_"), \
                f"a verificação quebrou: {type(e).__name__}: {e}", "me mande esta linha"
        itens.append({"situacao": situacao, "titulo": titulo, "detalhe": detalhe, "corrigir": corrigir})
    return itens


# ----------------------------------------------------------------------------------------------- QR code
def qr_terminal(url: str) -> str | None:
    """QR code em texto para o terminal (None sem o pacote segno)."""
    try:
        import segno
    except ImportError:
        return None
    import io
    saida = io.StringIO()
    segno.make(url, error="m").terminal(out=saida, compact=True, border=2)
    return saida.getvalue()


def qr_svg(url: str) -> str | None:
    """QR code em SVG (para o painel e para salvar). None sem o pacote segno."""
    try:
        import segno
    except ImportError:
        return None
    import io
    saida = io.BytesIO()
    segno.make(url, error="m").save(saida, kind="svg", scale=6, border=2, dark="#0F172A", light="#FFFFFF")
    return saida.getvalue().decode("utf-8")
