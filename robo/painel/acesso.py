"""Senha do painel.

- A senha nunca é guardada: só a impressão PBKDF2-SHA256 (200 mil rodadas, sal aleatório) em `painel.senha_hash`.
- Sem senha definida, o painel funciona como antes (e a ronda de segurança do Wagner avisa o risco).
- Com senha, toda rota /api exige a sessão (cookie HttpOnly, SameSite=Strict, válido por 12 horas, só na memória:
  fechar o robô encerra todas as sessões).
- Força bruta: depois de 5 senhas erradas seguidas, o login fica travado por 60 segundos (e dobra a cada nova rodada).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time

RODADAS = 200_000
VALIDADE_SESSAO = 12 * 3600
TENTATIVAS = 5
NOME_COOKIE = "robo_sessao"
ROTAS_LIVRES = {"/api/ping", "/api/login", "/api/acesso"}


def gerar_hash(senha: str) -> str:
    if len(senha or "") < 8:
        raise ValueError("A senha precisa ter pelo menos 8 caracteres.")
    sal = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), bytes.fromhex(sal), RODADAS).hex()
    return f"pbkdf2_sha256${RODADAS}${sal}${h}"


def conferir_hash(senha: str, guardado: str) -> bool:
    try:
        algoritmo, rodadas, sal, h = guardado.split("$")
        if algoritmo != "pbkdf2_sha256":
            return False
        calc = hashlib.pbkdf2_hmac("sha256", (senha or "").encode("utf-8"), bytes.fromhex(sal), int(rodadas)).hex()
        return hmac.compare_digest(calc, h)
    except (ValueError, AttributeError):
        return False


class Acesso:
    def __init__(self):
        self._sessoes: dict[str, float] = {}
        self._erros = 0
        self._travado_ate = 0.0
        self._rodada_trava = 0
        self._trava = threading.Lock()

    def entrar(self, senha: str, guardado: str) -> str:
        """Devolve o token da sessão ou levanta ValueError com o motivo."""
        with self._trava:
            agora = time.time()
            if agora < self._travado_ate:
                raise ValueError(f"Muitas tentativas erradas. Tente de novo em {int(self._travado_ate - agora) + 1} s.")
            if not conferir_hash(senha, guardado):
                self._erros += 1
                if self._erros >= TENTATIVAS:
                    self._rodada_trava += 1
                    self._travado_ate = agora + 60 * (2 ** (self._rodada_trava - 1))
                    self._erros = 0
                raise ValueError("Senha incorreta.")
            self._erros, self._rodada_trava = 0, 0
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

    def sair_de_todas(self) -> None:
        with self._trava:
            self._sessoes.clear()


def token_do_cookie(cabecalho: str | None) -> str | None:
    for parte in (cabecalho or "").split(";"):
        nome, _, valor = parte.strip().partition("=")
        if nome == NOME_COOKIE:
            return valor
    return None
