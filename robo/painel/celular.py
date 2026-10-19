"""Acompanhar a empresa pelo celular — SOMENTE LEITURA, só na rede da sua casa.

Por que um segundo servidor (e não abrir o painel principal na rede):
  - o painel principal tem botões que mudam coisas (aprovar regra, apagar reprovado, rodar SQL…) e continua preso a
    127.0.0.1: só abre no próprio notebook;
  - este servidor do celular NÃO tem nenhuma ação: só uma página de acompanhamento e um resumo em JSON. Mesmo que
    alguém descubra a senha, não consegue alterar nada;
  - vem DESLIGADO. Liga com `python -m robo celular --ligar` (grava celular.habilitado no config.yaml).

Regras de segurança (todas verificadas em testes/teste_celular.py):
  - só responde a endereços de rede privada (casa, VPN Tailscale); qualquer outro recebe 403;
  - exige a MESMA senha do painel; sem senha definida no painel, o servidor do celular se recusa a ligar;
  - sessão por cookie HttpOnly + SameSite=Strict, 12 horas;
  - 5 senhas erradas do mesmo endereço → 15 minutos bloqueado;
  - toda tentativa de entrar (certa ou errada) fica registrada para sempre em acessos_celular (não altera, não apaga).
"""

from __future__ import annotations

import ipaddress
import json
import logging
import secrets
import socket
import threading
import time
import urllib.parse
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from robo.painel.acesso import conferir_hash
from robo.trabalho import Trabalho, _agora

log = logging.getLogger("robo")

PORTA_PADRAO = 8766
VALIDADE_SESSAO = 12 * 3600
TENTATIVAS = 5
BLOQUEIO_SEGUNDOS = 15 * 60
NOME_COOKIE = "robo_celular"
LIMITE_CORPO = 4_000
ESTATICOS = Path(__file__).resolve().parent / "estaticos"

REDES_PRIVADAS = [ipaddress.ip_network(r) for r in (
    "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10",  # 100.64/10 = Tailscale
    "::1/128", "fe80::/10")]

CABECALHOS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}

ESQUEMA = """
CREATE TABLE IF NOT EXISTS acessos_celular (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, ip TEXT, evento TEXT, detalhe TEXT, navegador TEXT);
CREATE TRIGGER IF NOT EXISTS acessos_celular_imutavel BEFORE UPDATE ON acessos_celular
BEGIN SELECT RAISE(ABORT, 'registro de acesso pelo celular é permanente: não se altera'); END;
"""


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    with tb.tx() as c:
        c.executescript(ESQUEMA)
        from robo.trabalho import proteger
        proteger(c)
    return tb


def registrar_acesso(cfg, ip: str, evento: str, detalhe: str = "", navegador: str = "") -> None:
    with _tb(cfg).tx() as c:
        c.execute("INSERT INTO acessos_celular (data_hora, ip, evento, detalhe, navegador) VALUES (?,?,?,?,?)",
                  (_agora(), ip, evento, detalhe[:300], navegador[:200]))


def acessos(cfg, limite: int = 50) -> list[dict]:
    with _tb(cfg).tx() as c:
        return [dict(r) for r in c.execute("SELECT * FROM acessos_celular ORDER BY id DESC LIMIT ?", (limite,))]


# ----------------------------------------------------------------------------------------------- rede
def ip_privado(ip: str) -> bool:
    """Só rede de casa/VPN. Endereço IPv4 dentro de IPv6 (::ffff:192.168.0.5) é tratado como IPv4."""
    try:
        end = ipaddress.ip_address((ip or "").split("%")[0])
    except ValueError:
        return False
    if isinstance(end, ipaddress.IPv6Address) and end.ipv4_mapped:
        end = end.ipv4_mapped
    return any(end.version == r.version and end in r for r in REDES_PRIVADAS)


def ip_da_rede() -> str | None:
    """IP deste computador na rede de casa. O UDP 'connect' não envia nada: só pergunta ao sistema qual placa usaria."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()
    return ip if ip and not ip.startswith("127.") else None


def configuracao(cfg) -> dict:
    c = dict((cfg.dados.get("celular") or {}) if cfg else {})
    return {"habilitado": bool(c.get("habilitado", False)), "porta": int(c.get("porta") or PORTA_PADRAO)}


# ----------------------------------------------------------------------------------------------- sessão e senha
class PortaoCelular:
    """Senha, sessões e bloqueio por endereço (cada IP tem a própria contagem de erros)."""

    def __init__(self):
        self._sessoes: dict[str, float] = {}
        self._erros: dict[str, int] = {}
        self._bloqueado_ate: dict[str, float] = {}
        self._trava = threading.Lock()

    def entrar(self, ip: str, senha: str, guardado: str) -> str:
        with self._trava:
            agora = time.time()
            ate = self._bloqueado_ate.get(ip, 0)
            if agora < ate:
                raise PermissionError(f"Bloqueado por excesso de senhas erradas. Tente de novo em {int((ate - agora) / 60) + 1} min.")
            if not conferir_hash(senha, guardado):
                self._erros[ip] = self._erros.get(ip, 0) + 1
                if self._erros[ip] >= TENTATIVAS:
                    self._bloqueado_ate[ip] = agora + BLOQUEIO_SEGUNDOS
                    self._erros[ip] = 0
                    raise PermissionError("5 senhas erradas: este aparelho ficou bloqueado por 15 minutos.")
                raise ValueError("Senha incorreta.")
            self._erros.pop(ip, None)
            token = secrets.token_urlsafe(32)
            self._sessoes = {t: v for t, v in self._sessoes.items() if v > agora}
            self._sessoes[token] = agora + VALIDADE_SESSAO
            return token

    def valida(self, token: str | None) -> bool:
        if not token:
            return False
        with self._trava:
            v = self._sessoes.get(token)
            return bool(v and v > time.time())

    def sair(self, token: str | None) -> None:
        with self._trava:
            self._sessoes.pop(token or "", None)


# ----------------------------------------------------------------------------------------------- resumo (só leitura)
def _parte(saida: dict, chave: str, funcao) -> None:
    """Uma parte que falha não derruba as outras: aparece como indisponível, com o motivo."""
    try:
        saida[chave] = funcao()
    except Exception as e:
        log.debug("Celular: parte %s indisponível", chave, exc_info=True)
        saida[chave] = {"indisponivel": f"{type(e).__name__}: {e}"[:200]}


def resumo(cfg, controle=None) -> dict:
    from robo import backup, decisoes, historico, rotinas, ti, treino
    saida: dict = {"gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M:%S")}

    def _robo():
        ligado = bool(controle.ligado) if controle else None  # None = este servidor não enxerga o robô (não inventa)
        fila = len(controle.monitor.estado_fila()) if controle and getattr(controle, "monitor", None) else None
        return {"ligado": ligado, "fila": fila}

    def _rotinas():
        est = rotinas.estado(cfg)
        return {"total": len(est),
                "atrasadas": [r["nome"] for r in est if r["atrasada"]],
                "com_erro": [{"nome": r["nome"], "detalhe": r["detalhe"][:160]} for r in est if r["ultimo_status"] == "erro"]}

    def _treino():
        p = treino.painel(cfg, 24)
        r, t = p["recente"], p["total"]
        return {"tentativas_24h": r["tentativas"], "acertos_24h": r["acertos"], "pessoas_24h": r["pessoas"],
                "elegiveis": p["elegiveis"], "tentativas_total": t["tentativas"], "acertos_total": t["acertos"],
                "pct_24h": round(100 * r["acertos"] / r["tentativas"], 1) if r["tentativas"] else None,
                "mudancas_de_nivel": [{"nome": e["nome"], "competencia": e.get("competencia"), "de": e.get("de"),
                                       "para": e.get("para")} for e in p["mudancas_de_nivel"][:5]]}

    def _planilhas():
        linhas = historico.ler(cfg.logs, 8)
        return [{"data_hora": l.get("data_hora", ""), "arquivo": l.get("arquivo", ""), "status": l.get("status", ""),
                 "linhas": l.get("linhas_saida", ""), "erros": l.get("erros", "")} for l in linhas]

    def _ti():
        r = ti.ultima_ronda(cfg) or {}
        return {"data_hora": r.get("data_hora"), "saudavel": r.get("saudavel"),
                "alertas": [a for i in (r.get("itens") or []) for a in i.get("achados", [])][:8]}

    def _decisoes():
        abertas = decisoes.listar(cfg, abertas=True, limite=50)
        return {"abertas": len(abertas),
                "atrasadas": [{"texto": d["texto"][:140], "dono": d["dono_nome"], "prazo": d["prazo"]}
                              for d in abertas if d["estado"] == "atrasada"][:8]}

    def _caixa():
        from robo import caixa_dono
        r = caixa_dono.resumo(cfg)
        novas = [i for i in caixa_dono.itens(cfg, com_decididos=False)][:5]
        return {**r, "ultimas": [{"titulo": i["titulo"][:140], "de": i["sugerido_por"]["nome"]} for i in novas]}

    def _backup():
        s, p = backup.ultimo_sqlite(cfg) or {}, backup.ultimo(cfg) or {}
        return {"sqlite": s.get("data_hora") or s.get("criado_em"), "postgres": p.get("data_hora") or p.get("criado_em")}

    for chave, f in (("robo", _robo), ("rotinas", _rotinas), ("treino", _treino), ("planilhas", _planilhas),
                     ("ti", _ti), ("decisoes", _decisoes), ("backup", _backup), ("caixa", _caixa),
                     ("ao_vivo", lambda: ao_vivo(cfg)), ("andares", lambda: andares(cfg)),
                     ("gente", lambda: movimentos_de_gente(cfg))):
        _parte(saida, chave, f)
    return saida


def _tabelas(c) -> set[str]:
    return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def ao_vivo(cfg, limite: int = 30) -> list[dict]:
    """O que acabou de acontecer, de todas as fontes registradas, na ordem do tempo (mais recente primeiro).
    Só lê: canal, conversas entre funcionários, tentativas de treino, mudanças de nível, RH e decisões da liderança."""
    from robo import organizacao
    from robo.canal import Canal
    from robo.treino_casos import CATALOGO
    gente = organizacao.por_id(cfg)
    nome = lambda x: (gente.get(x) or {}).get("nome", x or "")  # noqa: E731
    comp = lambda x: CATALOGO[x].nome if x in CATALOGO else x  # noqa: E731
    itens = []
    for m in Canal(cfg).listar(limite=limite)[-limite:]:
        itens.append({"data_hora": m["data_hora"], "tipo": "canal", "quem": m.get("nome") or m["autor"],
                      "texto": f"#{m['canal']}: {m['texto']}"})
    with Trabalho(cfg).tx() as c:
        t = _tabelas(c)
        if "interacoes" in t:
            for r in c.execute("SELECT data_hora, de, para, tipo, texto FROM interacoes ORDER BY id DESC LIMIT ?", (limite,)):
                itens.append({"data_hora": r["data_hora"], "tipo": "conversa", "quem": nome(r["de"]),
                              "texto": (f"→ {nome(r['para'])}: " if r["para"] else "") + r["texto"]})
        if "treino_tentativas" in t:
            for r in c.execute("SELECT data_hora, funcionario, competencia, nivel, acertou, detalhe FROM treino_tentativas "
                               "ORDER BY id DESC LIMIT ?", (limite,)):
                itens.append({"data_hora": r["data_hora"], "tipo": "acerto" if r["acertou"] else "erro", "quem": nome(r["funcionario"]),
                              "texto": f"{comp(r['competencia'])} nível {r['nivel']}: "
                                       + ("acertou" if r["acertou"] else "errou — " + str(r["detalhe"] or "")[:120])})
        if "treino_niveis_eventos" in t:
            for r in c.execute("SELECT data_hora, funcionario, competencia, de, para FROM treino_niveis_eventos WHERE de IS NOT NULL "
                               "ORDER BY id DESC LIMIT ?", (limite,)):
                itens.append({"data_hora": r["data_hora"], "tipo": "nivel", "quem": nome(r["funcionario"]),
                              "texto": f"{comp(r['competencia'])}: {'subiu' if r['para'] > r['de'] else 'desceu'} do nível "
                                       f"{r['de']} para o {r['para']}"})
        if "rh_movimentos" in t:
            for r in c.execute("SELECT * FROM rh_movimentos ORDER BY id DESC LIMIT ?", (limite,)):
                r = dict(r)
                itens.append({"data_hora": r.get("data_hora"), "tipo": "rh", "quem": nome(r.get("funcionario")),
                              "texto": f"RH — {r.get('tipo')}: {r.get('motivo') or ''}"[:220]})
        if "alcadas_decisoes" in t:
            for r in c.execute("SELECT * FROM alcadas_decisoes ORDER BY id DESC LIMIT ?", (limite,)):
                r = dict(r)
                itens.append({"data_hora": r.get("data_hora"), "tipo": "lideranca", "quem": nome(r.get("decisor")),
                              "texto": f"decidiu ({r.get('item_tipo')}): {r.get('decisao')} — validado por "
                                       f"{nome(r.get('validador'))}. {r.get('motivo') or ''}"[:220]})
    itens.sort(key=lambda x: str(x["data_hora"]).replace("T", " "), reverse=True)
    return itens[:limite]


def andares(cfg) -> list[dict]:
    """Treino por andar nas últimas 24 h e nível médio atual — para ver quem está evoluindo."""
    from robo import organizacao
    desde = (datetime.now() - timedelta(hours=24)).isoformat(timespec="seconds")
    gente = organizacao.por_id(cfg)
    with Trabalho(cfg).tx() as c:
        if "treino_tentativas" not in _tabelas(c):
            return []
        rec = {r["andar"]: dict(r) for r in c.execute(
            "SELECT andar, COUNT(*) n, SUM(acertou) ok, COUNT(DISTINCT funcionario) pessoas FROM treino_tentativas "
            "WHERE data_hora>=? GROUP BY andar", (desde,))}
        niveis = [dict(r) for r in c.execute("SELECT funcionario, nivel FROM treino_niveis")]
    medio: dict = {}
    for n in niveis:
        andar = (gente.get(n["funcionario"]) or {}).get("andar")
        if andar:
            medio.setdefault(int(andar), []).append(n["nivel"])
    saida = []
    for andar in sorted({int(a) for a in organizacao.NOME_ANDAR} | set(medio)):
        r = rec.get(andar) or {"n": 0, "ok": 0, "pessoas": 0}
        quadro = sum(1 for p in gente.values() if int(p.get("andar") or 0) == andar)
        saida.append({"andar": andar, "nome": organizacao.NOME_ANDAR.get(andar, ""), "quadro": quadro,
                      "tentativas_24h": r["n"], "pct_24h": round(100 * (r["ok"] or 0) / r["n"], 1) if r["n"] else None,
                      "pessoas_24h": r["pessoas"],
                      "nivel_medio": round(sum(medio[andar]) / len(medio[andar]), 2) if medio.get(andar) else None})
    return saida


def movimentos_de_gente(cfg) -> dict:
    """RH, liderança e conversas: contagens das últimas 24 h e 7 dias (só o que está registrado)."""
    agora = datetime.now()
    d1, d7 = ((agora - timedelta(hours=h)).isoformat(timespec="seconds") for h in (24, 24 * 7))
    saida = {}
    with Trabalho(cfg).tx() as c:
        t = _tabelas(c)
        for tabela, chave in (("interacoes", "conversas"), ("rh_movimentos", "rh"), ("alcadas_decisoes", "lideranca"),
                              ("mentorias", "mentorias")):
            if tabela in t:
                saida[chave] = {"24h": c.execute(f"SELECT COUNT(*) FROM {tabela} WHERE data_hora>=?", (d1,)).fetchone()[0],
                                "7d": c.execute(f"SELECT COUNT(*) FROM {tabela} WHERE data_hora>=?", (d7,)).fetchone()[0]}
            else:
                saida[chave] = None
        if "mentorias" in t:
            saida["mentorias_ajudou"] = c.execute("SELECT COUNT(*) FROM mentorias WHERE situacao='ajudou'").fetchone()[0]
            saida["mentorias_abertas"] = c.execute("SELECT COUNT(*) FROM mentorias WHERE situacao='aberta'").fetchone()[0]
    return saida


# ----------------------------------------------------------------------------------------------- servidor
MANIFESTO = {
    "name": "Robô de Planilhas — acompanhamento", "short_name": "Robô", "start_url": "/", "display": "standalone",
    "background_color": "#F5F7FB", "theme_color": "#1D4ED8", "lang": "pt-BR",
    "icons": [{"src": "/robo.svg", "sizes": "any", "type": "image/svg+xml"}],
}


# os únicos arquivos servidos (CSP default-src 'self' proíbe script e estilo embutidos na página)
ARQUIVOS = {"/robo.svg": ("robo.svg", "image/svg+xml"), "/celular.css": ("celular.css", "text/css; charset=utf-8"),
            "/celular.js": ("celular.js", "text/javascript; charset=utf-8")}


def criar_manipulador(obter_cfg, senha_hash, controle=None, portao: PortaoCelular | None = None):
    """obter_cfg() e senha_hash() são lidos a cada pedido: trocar a senha no painel vale na hora para o celular."""
    portao = portao or PortaoCelular()

    class Manipulador(BaseHTTPRequestHandler):
        server_version = "RoboCelular"
        timeout = 20

        def log_message(self, *args):
            pass

        def _ip(self) -> str:
            return self.client_address[0] if self.client_address else ""

        def _enviar(self, status: int, corpo: bytes, tipo: str, extra: dict | None = None):
            self.send_response(status)
            self.send_header("Content-Type", tipo)
            for k, v in {**CABECALHOS, **(extra or {})}.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def _json(self, dados, status=200, extra=None):
            self._enviar(status, json.dumps(dados, ensure_ascii=False, default=str).encode("utf-8"),
                         "application/json; charset=utf-8", extra)

        def _token(self):
            for parte in (self.headers.get("Cookie") or "").split(";"):
                nome, _, valor = parte.strip().partition("=")
                if nome == NOME_COOKIE:
                    return valor
            return None

        def _rede_ok(self) -> bool:
            if ip_privado(self._ip()):
                return True
            self._json({"erro": "Acesso só pela rede de casa (ou VPN)."}, 403)
            return False

        def do_GET(self):
            if not self._rede_ok():
                return
            caminho = urllib.parse.urlparse(self.path).path
            if caminho in ("/", "/index.html"):
                return self._enviar(200, (ESTATICOS / "celular.html").read_bytes(), "text/html; charset=utf-8")
            if caminho == "/manifest.webmanifest":
                return self._enviar(200, json.dumps(MANIFESTO, ensure_ascii=False).encode("utf-8"), "application/manifest+json")
            if caminho in ARQUIVOS:
                nome, tipo = ARQUIVOS[caminho]
                return self._enviar(200, (ESTATICOS / nome).read_bytes(), tipo, {"Cache-Control": "no-cache"})
            if caminho == "/api/resumo":
                if not portao.valida(self._token()):
                    # 200 com login=True (e não 401): a página pergunta "estou logado?" ao abrir e isso não é erro
                    return self._json({"erro": "Entre com a senha do painel.", "login": True})
                try:
                    cfg = obter_cfg()
                    try:  # acompanhar pelo celular = dono presente (as alçadas da liderança só agem com o dono fora)
                        from robo import alcadas
                        alcadas.marcar_presenca(cfg, "celular")
                    except Exception:
                        log.debug("Celular: não marquei presença", exc_info=True)
                    return self._json(resumo(cfg, controle))
                except Exception as e:
                    log.exception("Celular: falha ao montar o resumo")
                    return self._json({"erro": f"{type(e).__name__}: {e}"}, 500)
            return self._json({"erro": "não encontrado"}, 404)

        def do_POST(self):
            if not self._rede_ok():
                return
            caminho = urllib.parse.urlparse(self.path).path
            if caminho not in ("/entrar", "/sair"):
                return self._json({"erro": "não encontrado"}, 404)
            try:
                tamanho = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                tamanho = -1
            if tamanho < 0 or tamanho > LIMITE_CORPO:
                self.close_connection = True
                return self._json({"erro": "requisição inválida"}, 413)
            corpo = self.rfile.read(tamanho) if tamanho else b""
            if caminho == "/sair":
                portao.sair(self._token())
                return self._json({"ok": True}, extra={"Set-Cookie": f"{NOME_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"})
            try:
                dados = json.loads(corpo or b"{}")
                senha = str(dados.get("senha") or "") if isinstance(dados, dict) else ""
            except ValueError:
                return self._json({"erro": "JSON inválido"}, 400)
            cfg, guardado = obter_cfg(), senha_hash()
            navegador = self.headers.get("User-Agent", "")
            if not guardado:
                return self._json({"erro": "O painel está sem senha: defina a senha no notebook antes de usar o celular."}, 403)
            try:
                token = portao.entrar(self._ip(), senha, guardado)
            except (ValueError, PermissionError) as e:
                evento = "bloqueado" if isinstance(e, PermissionError) else "senha_errada"
                _registrar_seguro(cfg, self._ip(), evento, str(e), navegador)
                log.warning("Celular: entrada recusada de %s (%s)", self._ip(), e)
                return self._json({"erro": str(e)}, 429 if isinstance(e, PermissionError) else 403)
            _registrar_seguro(cfg, self._ip(), "entrou", "", navegador)
            return self._json({"ok": True}, extra={
                "Set-Cookie": f"{NOME_COOKIE}={token}; Path=/; Max-Age={VALIDADE_SESSAO}; HttpOnly; SameSite=Strict"})

    return Manipulador


def _registrar_seguro(cfg, ip, evento, detalhe, navegador) -> None:
    try:
        registrar_acesso(cfg, ip, evento, detalhe, navegador)
    except Exception:
        log.exception("Celular: não consegui registrar o acesso de %s", ip)


def iniciar(obter_cfg, senha_hash, controle=None, porta: int | None = None, endereco: str = "0.0.0.0"):
    """Liga o servidor do celular numa linha própria. Devolve (servidor, motivo): servidor None = não ligou, com o motivo."""
    cfg = obter_cfg()
    if not cfg:
        return None, "sem configuração carregada"
    conf = configuracao(cfg)
    if not conf["habilitado"]:
        return None, "desligado (ligue com: python -m robo celular --ligar)"
    if not senha_hash():
        log.error("Acompanhamento pelo celular NÃO foi ligado: o painel está sem senha (python -m robo senha).")
        return None, "o painel está sem senha: defina a senha antes de liberar o celular"
    porta = porta or conf["porta"]
    try:
        servidor = ThreadingHTTPServer((endereco, porta), criar_manipulador(obter_cfg, senha_hash, controle))
    except OSError as e:
        log.error("Celular: porta %s ocupada (%s). Mude 'celular: porta' no config.yaml.", porta, e)
        return None, f"porta {porta} ocupada"
    servidor.daemon_threads = True
    threading.Thread(target=servidor.serve_forever, name="robo-celular", daemon=True).start()
    ip = ip_da_rede()
    log.info("Acompanhamento pelo celular (somente leitura): http://%s:%s/ — mesma rede Wi-Fi da casa",
             ip or "<ip-deste-computador>", servidor.server_address[1])
    return servidor, ""
