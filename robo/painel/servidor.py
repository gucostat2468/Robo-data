"""Servidor local do painel (somente 127.0.0.1) + API JSON usada pela interface.

Segurança: só aceita conexões da própria máquina, confere o cabeçalho Host (contra "DNS rebinding")
e exige um cabeçalho próprio nas ações (POST), que páginas de outros sites não conseguem enviar.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import shutil
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import uuid
from datetime import date, datetime
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pandas as pd
import yaml

from robo import __version__, historico
from robo.config import RAIZ_PROJETO
from robo.leitura import EXTENSOES_SUPORTADAS
from robo.painel.acesso import NOME_COOKIE, ROTAS_LIVRES, VALIDADE_SESSAO, token_do_cookie
from robo.painel.acesso import conferir_hash as conferir
from robo.manutencao import executar_manutencao
from robo.monitor import TravaInstancia, eh_candidato
from robo.painel import configuracao, sistema
from robo.painel.controle import ControleRobo
from robo.pipeline import processar_arquivo

log = logging.getLogger("robo")

ESTATICOS = Path(__file__).parent / "estaticos"
LIMITE_UPLOAD = 300 * 1024 * 1024
LIMITE_JSON = 2 * 1024 * 1024  # corpo de ações do painel (texto, configurações); planilhas usam o upload
CABECALHOS_SEGURANCA = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",  # nenhum site pode exibir o painel dentro de uma moldura (clickjacking)
    "Content-Security-Policy": "frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
}
CABECALHO_ACAO = "X-Robo-Painel"
RE_CARIMBO = re.compile(r"^\d{8}_\d{6}_")
TIPOS_ESTATICOS = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml", ".ico": "image/x-icon", ".png": "image/png", ".txt": "text/plain; charset=utf-8",
}


class ErroApi(Exception):
    def __init__(self, mensagem: str, status: int = 400):
        super().__init__(mensagem)
        self.status = status


# ---------------------------------------------------------------------------- formatação
def _fmt(v) -> str:
    if v is None or v is pd.NA or v is pd.NaT:
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.strftime("%d/%m/%Y %H:%M") if (v.hour or v.minute) else v.strftime("%d/%m/%Y")
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, Decimal):
        casas = min(4, max(0, -v.as_tuple().exponent)) if v.as_tuple().exponent < 0 else 0
        return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if isinstance(v, bool):
        return "Sim" if v else "Não"
    if isinstance(v, float):
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if isinstance(v, int) or hasattr(v, "__index__"):
        return f"{int(v):,}".replace(",", ".")
    return str(v)


def _ficha_curta(f: dict | None) -> dict | None:
    if not f:
        return None
    p = f.get("provas") or {}
    return {k: f.get(k) for k in ("cargo", "nivel", "area", "metodologias", "responsabilidades", "criterios", "limites", "mentor", "gestor")} | \
        {"provas": {"acertos": p.get("acertos", 0), "total": p.get("total", 0), "aprovado": p.get("aprovado", True)}}


def _ocorrencias(rel_ou_lista) -> list[dict]:
    itens = rel_ou_lista.ocorrencias if hasattr(rel_ou_lista, "ocorrencias") else rel_ou_lista
    return [o.__dict__ if hasattr(o, "__dict__") else o for o in itens]


def _nome_original(nome: str) -> str:
    return RE_CARIMBO.sub("", nome)


def _dentro(caminho: Path, pastas) -> bool:
    try:
        alvo = caminho.resolve()
    except OSError:
        return False
    return any(alvo == p.resolve() or p.resolve() in alvo.parents for p in pastas if p)


# ---------------------------------------------------------------------------- API
SENHA_ILEGIVEL = "!config-ilegivel"  # nenhuma senha confere com isto: painel trancado até o arquivo ser corrigido


class Api:
    def __init__(self, controle: ControleRobo, porta: int):
        self.c = controle
        self.porta = porta
        self.encerrar = threading.Event()
        from robo.painel.acesso import Acesso
        self.acesso = Acesso()

    @property
    def senha_hash(self) -> str | None:
        """Lida do ARQUIVO de configuração, não da config carregada: se a config falhar (pasta não achada, YAML
        quebrado), o painel continua com senha. Arquivo ilegível = trancado (falha fechada), nunca aberto."""
        arq = Path(self.c.caminho_config) if self.c.caminho_config else RAIZ_PROJETO / "config.yaml"
        try:
            chave = (str(arq), arq.stat().st_mtime_ns)
        except OSError:
            return (self.c.cfg.painel.get("senha_hash") if self.c.cfg else None) or None
        if getattr(self, "_senha_cache", (None, None))[0] != chave:
            try:
                dados = yaml.safe_load(arq.read_text(encoding="utf-8")) or {}
                h = ((dados.get("painel") or {}) if isinstance(dados, dict) else {}).get("senha_hash") or None
            except Exception:
                h = SENHA_ILEGIVEL
            self._senha_cache = (chave, h)
        return self._senha_cache[1]

    def acesso_estado(self, q, token=None) -> dict:
        return {"senha": bool(self.senha_hash), "logado": not self.senha_hash or self.acesso.valida(token)}

    def definir_senha(self, b, token=None) -> dict:
        from robo.painel.acesso import gerar_hash
        if self.senha_hash and not conferir(str(b.get("atual") or ""), self.senha_hash):
            raise ErroApi("A senha atual não confere.", 403)
        nova = str(b.get("nova") or "")
        if nova != str(b.get("confirmacao") or ""):
            raise ErroApi("A confirmação não é igual à nova senha.")
        try:
            h = gerar_hash(nova)
        except ValueError as e:
            raise ErroApi(str(e))
        if self.senha_hash == SENHA_ILEGIVEL:
            raise ErroApi("O config.yaml não pôde ser lido; por segurança a senha não pode ser trocada pelo painel. "
                          "Corrija o arquivo ou use: python -m robo senha", 409)
        configuracao.definir_senha(configuracao.garantir_arquivo(self.c.caminho_config), h)
        if self.c.cfg:
            self.c.cfg.painel["senha_hash"] = h
        self.acesso.sair_de_todas()  # senha nova derruba as sessões antigas
        log.info("Senha do painel definida/alterada.")
        return {"ok": True}

    @property
    def cfg(self):
        if not self.c.cfg:
            raise ErroApi(self.c.erro_config or "Configuração indisponível", 409)
        return self.c.cfg

    def presenca(self) -> None:
        """O dono está usando o painel: registra (no máximo 1x por minuto). Base das alçadas (robo/alcadas.py)."""
        agora = time.time()
        if agora - getattr(self, "_ultima_presenca", 0) < 60 or not self.c.cfg:
            return
        self._ultima_presenca = agora
        try:
            from robo import alcadas
            alcadas.marcar_presenca(self.c.cfg, "painel")
        except Exception:
            log.debug("Não consegui registrar a presença do dono", exc_info=True)

    # ---------------- leitura
    def estado(self, _q) -> dict:
        c = self.c
        base = {"versao": __version__, "erro_config": c.erro_config, "ligado": c.ligado,
                "ligado_desde": c.ligado_desde, "agora": time.time()}
        if not c.cfg:
            return base
        cfg, m = c.cfg, c.monitor
        hist = historico.ler(cfg.logs, 2000)
        hoje = datetime.now().strftime("%Y-%m-%d")
        de_hoje = [h for h in hist if h.get("data_hora", "").startswith(hoje)]
        ult30 = [h for h in hist if h.get("data_hora", "") >= (pd.Timestamp.now() - pd.Timedelta(days=30)).strftime("%Y-%m-%d")]

        def contar(lista, status):
            return sum(1 for h in lista if h.get("status") == status)

        def soma(lista, campo):
            return sum(int(h.get(campo) or 0) for h in lista if h.get("status") == "sucesso")

        reprovados = self._listar_reprovados(detalhes=False)
        pastas = {}
        for chave, nome, caminho in (("entrada", "Bases-Limpeza", cfg.entrada), ("tratadas", "Bases-Tratadas", cfg.tratadas),
                                     ("erros", "Bases-Erros", cfg.erros), ("originais", "Bases-Originais", cfg.originais),
                                     ("relatorios", "Bases-Relatorios", cfg.relatorios), ("logs", "Logs", cfg.logs)):
            qtd = None
            if chave in ("entrada", "tratadas") and caminho.exists():
                qtd = sum(1 for p in caminho.iterdir() if eh_candidato(p))
            pastas[chave] = {"nome": nome, "caminho": str(caminho), "existe": caminho.exists(), "qtd": qtd}
        pastas["erros"]["qtd"] = len(reprovados)
        total30 = contar(ult30, "sucesso") + contar(ult30, "reprovado")
        base.update({
            "processando": m.processando,
            "ultimo_ciclo": m.ultimo_ciclo,
            "fila": m.estado_fila(),
            "pastas": pastas,
            "kpis": {
                "hoje_sucesso": contar(de_hoje, "sucesso"),
                "hoje_reprovado": contar(de_hoje, "reprovado"),
                "hoje_linhas": soma(de_hoje, "linhas_saida"),
                "reprovados_pendentes": len(reprovados),
                "taxa_aprovacao_30d": round(100 * contar(ult30, "sucesso") / total30) if total30 else None,
                "total_30d": total30,
            },
            "recentes": hist[:8],
            "banco_habilitado": bool(cfg.banco.get("habilitado")),
            "notificacoes": bool(cfg.painel.get("notificacoes", True)),
        })
        return base

    def escritorio(self, q) -> dict:
        """Eventos das etapas + números do dia por agente (alimenta o escritório 3D)."""
        c = self.c
        desde = int(q.get("desde", ["0"])[0])
        dados = {"ligado": c.ligado, "erro_config": c.erro_config, "eventos": c.eventos_desde(desde),
                 "ultimo_seq": c._seq_eventos, "fila": [], "agentes": {}}
        if not c.cfg:
            return dados
        cfg = c.cfg
        hoje = datetime.now().strftime("%Y-%m-%d")
        h = [x for x in historico.ler(cfg.logs, 3000) if x.get("data_hora", "").startswith(hoje)]
        ok = [x for x in h if x.get("status") == "sucesso"]
        ruim = [x for x in h if x.get("status") == "reprovado"]
        soma = lambda lista, campo: sum(int(x.get(campo) or 0) for x in lista)
        com_banco = [x for x in ok if "tratado." in (x.get("saidas") or "")]
        from robo.pipeline import obter_equipe
        from robo.analise import ANALISTAS, PADRAO_ANALISE
        equipe = [{"id": a["id"], "nome": a["nome"], "papel": a.get("papel", ""), "cor": a.get("cor", "#64748B"),
                   "descricao": a.get("descricao", ""), "nativo": a.get("nativo", False), "ativo": a.get("ativo", True),
                   "habilidades": [s.get("habilidade") for s in a.get("habilidades", []) if s.get("ativo", True)],
                   "aceita_habilidades": a.get("aceita_habilidades", True), "andar": 1, "ficha": _ficha_curta(a.get("ficha"))}
                  for a in obter_equipe(cfg).lista()]
        cfg_analise = {**PADRAO_ANALISE, **(cfg.dados.get("analise") or {})}
        desligados = set(cfg_analise.get("analistas_desligados") or [])
        from robo import rh
        from robo.producao import SUPERVISORES
        from robo.excel import EQUIPE_EXCEL
        # ninguém dorme: quem não tem trabalho no momento fica "de prontidão" (estudando, revisando), nunca desligado
        equipe += [{**a, "nativo": True, "aceita_habilidades": False, "habilidades": [], "ativo": True,
                    "prontidao": "revisando os modelos SQL (banco ainda não configurado)" if a["id"] == "dba" and not cfg.banco.get("habilitado") else "",
                    "ficha": _ficha_curta(rh.ficha({"id": a["id"], "habilidades": []}))} for a in SUPERVISORES]
        equipe += [{**a, "id": f"analise_{a['id']}", "nativo": True, "aceita_habilidades": False, "habilidades": [], "andar": 2, "ativo": True,
                    "prontidao": "" if cfg_analise.get("habilitado", True) and a["id"] not in desligados
                    else "estudando (análise pausada nas Configurações)",
                    "ficha": _ficha_curta(rh.ficha({"id": f"analise_{a['id']}", "habilidades": []}))} for a in ANALISTAS]
        cfg_excel = cfg.dados.get("excel") or {}
        equipe += [{**a, "nativo": True, "aceita_habilidades": False, "habilidades": [], "andar": 3, "ativo": True,
                    "ronda": a["id"] == "excel_supervisor",
                    "prontidao": "" if cfg_excel.get("habilitado", True) else "estudando (Sala Excel pausada nas Configurações)",
                    "ficha": _ficha_curta(rh.ficha({"id": a["id"], "habilidades": []}))} for a in EQUIPE_EXCEL]
        from robo import quadro
        from robo.canal import EQUIPE_CANAL
        equipe += [{"id": p["id"], "nome": p["nome"], "papel": p["papel"], "cor": p["cor"], "descricao": p["descricao"] or
                    "; ".join(p["escopo"]), "nativo": True, "aceita_habilidades": False, "habilidades": [], "andar": p["andar"],
                    "ativo": True, "ronda": p["nivel"] == "coordenador", "prontidao": "",
                    "ficha": _ficha_curta(rh.ficha({"id": p["id"], "habilidades": []}))} for p in quadro.QUADRO]
        equipe += [{**a, "nativo": True, "aceita_habilidades": False, "habilidades": [], "ativo": True,
                    "ronda": a["id"] == "canal_helena", "prontidao": "",
                    "ficha": _ficha_curta(rh.ficha({"id": a["id"], "habilidades": []}))} for a in EQUIPE_CANAL]
        from robo import ti
        ronda_ti = ti.ultima_ronda(cfg) or {}
        status_ti = {i["id"]: i for i in ronda_ti.get("itens") or []}
        equipe += [{"id": p["id"], "nome": p["nome"], "papel": p["cargo"].split(" — ")[0], "cor": p["cor"], "andar": 5,
                    "descricao": "; ".join(p["escopo"]), "nativo": True, "aceita_habilidades": False, "habilidades": [],
                    "ativo": True, "ronda": p["nivel"] == "coordenador", "prontidao": "",
                    "ficha": _ficha_curta(rh.ficha({"id": p["id"], "habilidades": []}))} for p in ti.EQUIPE_TI]
        from robo.paineis import EQUIPE_BI
        equipe += [{"id": p["id"], "nome": p["nome"], "papel": p["cargo"].split(" — ")[0], "cor": p["cor"], "andar": p["andar"],
                    "descricao": "; ".join(p["escopo"]), "nativo": True, "aceita_habilidades": False, "habilidades": [],
                    "ativo": True, "ronda": False, "prontidao": "",
                    "ficha": _ficha_curta(rh.ficha({"id": p["id"], "habilidades": []}))} for p in EQUIPE_BI]
        from robo.fabrica import EQUIPE_FABRICA
        equipe += [{"id": p["id"], "nome": p["nome"], "papel": p["cargo"].split(" — ")[0], "cor": p["cor"], "andar": p["andar"],
                    "descricao": "; ".join(p["escopo"]), "nativo": True, "aceita_habilidades": False, "habilidades": [],
                    "ativo": True, "ronda": False, "prontidao": "",
                    "ficha": _ficha_curta(rh.ficha({"id": p["id"], "habilidades": []}))} for p in EQUIPE_FABRICA]
        from robo import lideranca
        equipe += [{"id": p["id"], "nome": p["nome"], "papel": p["papel"], "cor": p["cor"], "andar": p["andar"],
                    "descricao": p["descricao"], "nativo": True, "aceita_habilidades": False, "habilidades": [], "ativo": True,
                    "ronda": p["nivel"] in ("head",), "prontidao": "",
                    "ficha": _ficha_curta(rh.ficha({"id": p["id"], "habilidades": []}))} for p in lideranca.EQUIPE]
        for a in equipe:
            if not a.get("ativo", True):  # agente personalizado pausado pelo dono: segue estudando, não dorme
                a["ativo"], a["prontidao"] = True, "em treinamento (pausado por você na tela Agentes)"
            elif a["id"] == "banco" and not cfg.banco.get("habilitado"):
                a["prontidao"] = "preparando as tabelas (PostgreSQL ainda não configurado)"
            a.setdefault("prontidao", "")
        excel_hoje = self._excel_hoje(cfg, ok)
        conferencias_hoje = self._quadro_hoje(cfg, ok + ruim)
        dados.update({
            "equipe": equipe,
            "fila": c.monitor.estado_fila() if c.monitor else [],
            "banco_habilitado": bool(cfg.banco.get("habilitado")),
            "agentes": {
                "recepcao": {"valor": len(h), "rotulo": "arquivos recebidos hoje"},
                "leitura": {"valor": soma(h, "linhas_entrada"), "rotulo": "linhas lidas hoje"},
                "limpeza": {"valor": soma(ok, "linhas_entrada") - soma(ok, "linhas_saida"), "rotulo": "linhas descartadas hoje"},
                "validacao": {"valor": len(ruim), "rotulo": "arquivos barrados hoje"},
                "modelagem": {"valor": len(ok), "rotulo": "bases modeladas hoje"},
                "banco": {"valor": soma(com_banco, "linhas_saida"), "rotulo": "linhas carregadas hoje",
                          "inativo": not cfg.banco.get("habilitado")},
                "publicacao": {"valor": len(ok), "rotulo": "planilhas publicadas hoje"},
                **self._numeros_analise(hoje),
                "excel_supervisor": {"valor": excel_hoje["conferencias"], "rotulo": "conferências de fórmula assinadas hoje"},
                **{k: {"valor": excel_hoje["entregas"], "rotulo": "entregas Excel hoje"}
                   for k in ("excel_pesquisa", "excel_formulas", "excel_trade", "excel_dinamicas")},
                **conferencias_hoje,
                **{i: {"valor": len(x["achados"]) if x["achados"] else "OK",
                       "rotulo": "alerta(s) na última ronda" if x["achados"] else "na última ronda de TI"}
                   for i, x in status_ti.items()},
            },
            "analise_hoje": self._analise_hoje(hoje),
            "excel_hoje": excel_hoje,
            "canal_hoje": self._canal_hoje(cfg),
            "ti": {"saudavel": ronda_ti.get("saudavel"), "data_hora": ronda_ti.get("data_hora"),
                   "alertas": [a for i in ronda_ti.get("itens") or [] for a in i["achados"]][:5]},
            "vivo": self._vivo(cfg), "trabalho_real": self._trabalho_real(cfg),
        })
        return dados

    def _trabalho_real(self, cfg) -> dict:
        """Quem tem etapa de job ABERTA agora e há quanto tempo a última planilha foi processada (robo/jobs.py)."""
        from robo import jobs
        try:
            agora = jobs.trabalhando_agora(cfg)
            return {**jobs.resumo(cfg), "ids": list(agora), "etapas": agora}
        except Exception:
            log.debug("Escritório: prova de trabalho indisponível", exc_info=True)
            return {}

    def fabrica(self, _q) -> dict:
        from robo import fabrica
        return fabrica.resumo(self.cfg)

    def fabrica_produzir(self, _b) -> dict:
        from robo import fabrica
        return {"ok": True, "lote": fabrica.produzir_lote(self.cfg)}

    def prova_de_trabalho(self, _q) -> dict:
        """Para cada funcionário, a última evidência AUDITÁVEL: etapa de job com arquivo, linhas, hash e caminho; se não
        houver job, o último trabalho real registrado; se nem isso, "sem registro". É a resposta oficial para a pergunta
        "a operação diz que está tudo funcionando — é verdade?"."""
        from robo import atividade_equipe, jobs
        cfg = self.cfg
        q = atividade_equipe.quadro(cfg)
        ev = jobs.ultima_evidencia(cfg)
        pessoas = []
        for p in q["pessoas"]:
            e = ev.get(p["id"])
            pessoas.append({"id": p["id"], "nome": p["nome"], "cargo": p["cargo"], "andar": p["andar"], "situacao": p["situacao"],
                            "agora": p.get("agora"), "evidencia_job": e, "ultimo_trabalho_real": p.get("ultimo"),
                            "prova": "job" if e else ("registro" if p.get("ultimo") else "sem registro")})
        return {"gerado_em": q["gerado_em"], "regra": q["regra"], "jobs": q.get("jobs"),
                "trabalho_real_agora": q.get("trabalho_real_agora"), "total_pessoas": q.get("total_pessoas"),
                "com_prova_de_job": sum(1 for x in pessoas if x["prova"] == "job"),
                "sem_registro": [x["nome"] for x in pessoas if x["prova"] == "sem registro"], "pessoas": pessoas}

    def _vivo(self, cfg) -> dict:
        """O que acabou de ser REGISTRADO no banco (conversas e tentativas de treino) — vira balão em cima de quem fez."""
        from robo.trabalho import Trabalho
        from robo.treino_casos import CATALOGO
        saida = {"conversas": [], "treino": []}
        try:
            with Trabalho(cfg).tx() as c:
                tabelas = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if "interacoes" in tabelas:
                    saida["conversas"] = [dict(r) for r in c.execute(
                        "SELECT id, data_hora, de, para, tipo, substr(texto, 1, 220) AS texto FROM interacoes ORDER BY id DESC LIMIT 12")]
                if "treino_tentativas" in tabelas:
                    saida["treino"] = [{**dict(r), "competencia": CATALOGO[r["competencia"]].nome if r["competencia"] in CATALOGO
                                        else r["competencia"]} for r in c.execute(
                        "SELECT id, data_hora, funcionario, competencia, nivel, acertou FROM treino_tentativas ORDER BY id DESC LIMIT 30")]
        except Exception:
            log.debug("Escritório: registros ao vivo indisponíveis", exc_info=True)
        return saida

    def _execucao_resumida(self, cfg, i: str) -> dict:
        """Partes do JSON da execução usadas no escritório (lidas uma vez só e guardadas em memória)."""
        cache = self.__dict__.setdefault("_cache_execucoes", {})
        if i in cache:
            return cache[i]
        exe = historico.ler_execucao(cfg.logs, i) or {}
        resumo = {"excel": exe.get("excel"),
                  "quadro": [{"id": q["id"], "ok": q["ok"], "achados": len(q.get("achados") or [])}
                             for q in exe.get("quadro") or []]}
        if exe:  # só guarda quando o detalhe já existe (senão tenta de novo na próxima atualização)
            if len(cache) > 5000:
                cache.clear()
            cache[i] = resumo
        return resumo

    def _quadro_hoje(self, cfg, execucoes: list[dict]) -> dict:
        from robo.quadro import QUADRO
        feitas = {p["id"]: 0 for p in QUADRO}
        achados = dict(feitas)
        for x in execucoes[:300]:
            for q in self._execucao_resumida(cfg, x.get("id") or "")["quadro"]:
                if q["id"] in feitas:
                    feitas[q["id"]] += 1
                    achados[q["id"]] += q["achados"]
        return {i: {"valor": feitas[i], "rotulo": f"conferências hoje · {achados[i]} achado(s)"} for i in feitas}

    def _canal_hoje(self, cfg) -> dict:
        try:
            from robo.canal import Canal
            c = Canal(cfg)
            hoje = datetime.now().strftime("%Y-%m-%d")
            msgs = [m for m in c.listar(limite=500) if m["data_hora"].startswith(hoje)]
            numero, ini, fim = c.sprint_de(date.today())
            return {"mensagens": len(msgs), "sprint": numero, "dias_restantes": (fim - date.today()).days,
                    "ultima": (msgs[-1]["nome"] + ": " + msgs[-1]["texto"][:140]) if msgs else ""}
        except Exception:
            log.debug("canal indisponível", exc_info=True)
            return {}

    def _excel_hoje(self, cfg, aprovados: list[dict]) -> dict:
        """Entregas da Sala Excel de hoje."""
        entregas = []
        for x in aprovados[:300]:
            ex = self._execucao_resumida(cfg, x.get("id") or "")["excel"]
            if ex:
                entregas.append(ex)
        ultimo = Path(entregas[0]["arquivo"]).name if entregas else None
        return {"entregas": len(entregas), "conferencias": sum(int(e.get("conferencias") or 0) for e in entregas),
                "divergencias": sum(1 for e in entregas if e.get("revisao_ok") is False), "ultimo": ultimo}

    def _analises_do_dia(self, hoje: str) -> list[dict]:
        pasta = self.cfg.logs / "analises"
        if not pasta.exists():
            return []
        itens = []
        for arq in sorted(pasta.glob("2*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:200]:
            if datetime.fromtimestamp(arq.stat().st_mtime).strftime("%Y-%m-%d") != hoje:
                break
            try:
                itens.append(json.loads(arq.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return itens

    def _numeros_analise(self, hoje: str) -> dict:
        a = self._analises_do_dia(hoje)
        conta = lambda chave, filtro=lambda x: True: sum(1 for d in a for x in (d.get(chave) or []) if filtro(x))
        return {
            "analise_perfil": {"valor": conta("perfil"), "rotulo": "colunas descritas hoje"},
            "analise_indicadores": {"valor": conta("indicadores", lambda x: x.get("segmento") == "Total"),
                                    "rotulo": "indicadores calculados hoje"},
            "analise_estatistica": {"valor": conta("destaques", lambda x: x.get("significativo")),
                                    "rotulo": "diferenças reais encontradas hoje"},
            "analise_monitoramento": {"valor": conta("alertas", lambda x: x.get("nivel") == "atenção"),
                                      "rotulo": "alertas de atenção hoje"},
            "analise_relator": {"valor": len(a), "rotulo": "resumos escritos hoje"},
        }

    def _analise_hoje(self, hoje: str) -> dict:
        a = self._analises_do_dia(hoje)
        ultimo = a[0] if a else None
        return {"bases": len(a),
                "destaques": sum(1 for d in a for x in (d.get("destaques") or []) if x.get("significativo")),
                "alertas": sum(1 for d in a for x in (d.get("alertas") or []) if x.get("nivel") == "atenção"),
                "ultimo_arquivo": ultimo.get("arquivo") if ultimo else None,
                "ultimo_resumo": [r.get("resumo_executivo") for r in (ultimo.get("resumo") or [])][:7] if ultimo else []}

    def historico(self, q) -> dict:
        limite = int(q.get("limite", ["500"])[0])
        return {"itens": historico.ler(self.cfg.logs, limite)}

    def execucao(self, q) -> dict:
        dados = historico.ler_execucao(self.cfg.logs, q.get("id", [""])[0])
        if not dados:
            raise ErroApi("Detalhes deste processamento não foram encontrados (podem ter sido apagados pela manutenção).", 404)
        return dados

    def _listar_reprovados(self, detalhes=True) -> list[dict]:
        cfg = self.cfg
        if not cfg.erros.exists():
            return []
        itens = []
        for arq in sorted(cfg.erros.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not arq.is_file() or arq.name.endswith("_ERROS.txt") or not eh_candidato(arq):
                continue
            item = {"nome": arq.name, "original": _nome_original(arq.name), "id": arq.stem,
                    "data": datetime.fromtimestamp(arq.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")}
            if detalhes:
                exe = historico.ler_execucao(cfg.logs, arq.stem) or {}
                ocorr = exe.get("ocorrencias") or []
                item["erros"] = [o for o in ocorr if o.get("nivel") == "ERRO"]
                item["avisos"] = [o for o in ocorr if o.get("nivel") == "AVISO"]
                if exe.get("data_hora"):
                    item["data"] = exe["data_hora"]
                if not exe:
                    txt = arq.with_name(f"{arq.stem}_ERROS.txt")
                    item["texto"] = txt.read_text(encoding="utf-8-sig") if txt.exists() else ""
            itens.append(item)
        return itens

    def reprovados(self, _q) -> dict:
        return {"itens": self._listar_reprovados()}

    def log(self, q) -> dict:
        return {"itens": self.c.memoria_log.desde(int(q.get("desde", ["0"])[0]))}

    def config(self, _q) -> dict:
        c = self.c
        base = {"erro_config": c.erro_config, "suporta_windows": sistema.EH_WINDOWS,
                "inicializacao_windows": sistema.inicializacao_ligada(), "versao": __version__,
                "arquivo_config": str(configuracao.garantir_arquivo(c.caminho_config))}
        if not c.cfg:
            return base
        cfg = c.cfg
        b = dict(cfg.banco)
        b["senha_definida"] = bool(b.pop("senha", ""))
        regras = [{"padrao": r.get("padrao"), "itens": [k for k in r if k != "padrao"]} for r in cfg.dados.get("regras") or []]
        base.update({
            "pastas": {k: str(v) for k, v in cfg.pastas().items()},
            "saida": {"formato": cfg.saida.get("formato"), "versionar": bool(cfg.saida.get("versionar"))},
            "monitoramento": cfg.monitoramento,
            "banco": b,
            "painel": {k: v for k, v in cfg.painel.items() if k != "senha_hash"},  # a impressão da senha não sai do servidor
            "senha_definida": bool(cfg.painel.get("senha_hash")),
            "regras": regras,
            "modelos_sql": self._modelos_sql(),
            "manutencao": cfg.manutencao,
        })
        return base

    def _pasta_modelos(self) -> Path:
        from robo.banco import Banco
        return Banco(self.cfg.banco, self.cfg.base).pasta_modelos

    def _modelos_sql(self) -> list[dict]:
        pasta = self._pasta_modelos()
        if not pasta.exists():
            return []
        return [{"nome": p.name, "ativo": not p.name.startswith("_")} for p in sorted(pasta.glob("*.sql"))]

    def agentes(self, _q) -> dict:
        from robo import habilidades
        from robo.agentes import POSICOES
        from robo.pipeline import obter_equipe
        equipe = obter_equipe(self.cfg)
        from robo import rh
        from robo.analise import ANALISTAS
        catalogo = [{**s, "risco": rh.RISCO_BASE.get(s["id"], "medio"), "provas": len(rh.provas_da_habilidade(s["id"]))}
                    for s in habilidades.catalogo()]
        from robo.producao import SUPERVISORES
        analistas = [{**a, "id": f"analise_{a['id']}", "nativo": True, "aceita_habilidades": False, "habilidades": [], "andar": 2,
                      "ativo": True, "ficha": rh.ficha({"id": f"analise_{a['id']}", "habilidades": []})} for a in ANALISTAS]
        lideranca = [{**a, "nativo": True, "aceita_habilidades": False, "habilidades": [], "ativo": True,
                      "ficha": rh.ficha({"id": a["id"], "habilidades": []})} for a in SUPERVISORES]
        from robo.excel import EQUIPE_EXCEL
        sala_excel = [{**a, "nativo": True, "aceita_habilidades": False, "habilidades": [], "ativo": True, "andar": 3,
                       "ficha": rh.ficha({"id": a["id"], "habilidades": []})} for a in EQUIPE_EXCEL]
        from robo import quadro
        from robo.canal import EQUIPE_CANAL
        quadro_pessoal = [{"id": p["id"], "nome": p["nome"], "papel": p["papel"], "cor": p["cor"], "andar": p["andar"],
                           "descricao": p["descricao"] or "; ".join(p["escopo"]), "nativo": True, "aceita_habilidades": False,
                           "habilidades": [], "ativo": True, "ficha": rh.ficha({"id": p["id"], "habilidades": []})}
                          for p in quadro.QUADRO]
        quadro_pessoal += [{**a, "nativo": True, "aceita_habilidades": False, "habilidades": [], "ativo": True,
                            "ficha": rh.ficha({"id": a["id"], "habilidades": []})} for a in EQUIPE_CANAL]
        return {"agentes": equipe.lista(), "analistas": analistas, "lideranca": lideranca, "sala_excel": sala_excel,
                "quadro": quadro_pessoal, "escopos": quadro.ESCOPO_NIVEL, "catalogo": catalogo,
                "erros_habilidades": list(habilidades.ERROS_CARGA), "posicoes": POSICOES,
                "rh": {"niveis": [{"id": n, "nome": rh.NOME_NIVEL[n], "risco_maximo": rh.RISCO_MAXIMO[n]} for n in rh.NIVEIS],
                       "areas": rh.AREAS}}

    def agente_salvar(self, b) -> dict:
        from robo.agentes import IDS_NATIVOS, ErroAgente
        from robo.pipeline import obter_equipe
        dados = b.get("agente") or {}
        if not isinstance(dados, dict):
            raise ErroApi("'agente' precisa ser um objeto.")
        novo = not (self.cfg.agentes / f"{dados.get('id', '')}.yaml").exists()
        try:
            if novo and dados.get("id") not in IDS_NATIVOS:
                from robo.contratacao import contratar_manual
                a = contratar_manual(self.cfg, dados)  # contratação: anuncia no canal e aplica experiência de estagiário
            else:
                a = obter_equipe(self.cfg).salvar(dados)
        except ErroAgente as e:
            raise ErroApi(str(e))
        log.info("Agente %s salvo pelo painel", a.get("nome") or a.get("id"))
        return {"ok": True, "id": a["id"]}

    def agente_manual(self, b) -> dict:
        from robo.agentes import ErroAgente
        from robo.pipeline import obter_equipe
        try:
            obter_equipe(self.cfg).salvar_manual(str(b.get("id", "")), str(b.get("texto", "")))
        except ErroAgente as e:
            raise ErroApi(str(e))
        return {"ok": True}

    def agente_manual_ler(self, q) -> dict:
        from robo.pipeline import obter_equipe
        return {"texto": obter_equipe(self.cfg).manual(q.get("id", [""])[0])}

    # ------------------------------------------------------------ canal da equipe (offline)
    def canal(self, q) -> dict:
        from robo.canal import CANAIS, Canal, pessoas
        c = Canal(self.cfg)
        p = lambda k: q.get(k, [""])[0]
        msgs = c.listar(canal=p("canal"), autor=p("autor"), tipo=p("tipo"), busca=p("busca"),
                        dias=int(p("dias") or 0), desde_id=int(p("desde") or 0), limite=int(p("limite") or 300))
        numero, ini, fim = c.sprint_de(date.today())
        gente = pessoas()
        autores = sorted({m["autor"] for m in c.listar(limite=5000)})
        from robo import ia
        return {"mensagens": msgs, "canais": CANAIS, "ia": ia.status(self.cfg),
                "autores": [{"id": a, "nome": gente.get(a, {}).get("nome", a), "papel": gente.get(a, {}).get("papel", "")}
                            for a in autores],
                "sprint": {"numero": numero, "inicio": ini.isoformat(), "fim": fim.isoformat(),
                           "dias_restantes": (fim - date.today()).days}}

    def canal_enviar(self, b) -> dict:
        from robo.canal import Canal
        texto = str(b.get("texto", "")).strip()
        if not texto:
            raise ErroApi("Escreva uma mensagem.")
        return {"mensagens": Canal(self.cfg).perguntar(texto, str(b.get("canal") or "geral"))}

    def ia_testar(self, b) -> dict:
        """Testa uma conversa SEM postar no canal: mostra a resposta, de onde veio (regra ou IA) e os fatos usados."""
        from robo import ia
        from robo.canal import responder
        texto = str(b.get("texto", "")).strip()
        if not texto:
            raise ErroApi("Escreva uma pergunta para testar.")
        return {"ia": ia.status(self.cfg), "respostas": responder(texto, self.cfg)}

    def canal_sprint(self, _b) -> dict:
        from robo.canal import Canal
        c = Canal(self.cfg)
        c.sincronizar()
        return {"mensagens": c.publicar_sprint()}

    # ------------------------------------------------------------ central de dados e estratégia
    def central(self, q) -> dict:
        from robo import central
        return central.montar(self.cfg, int(q.get("dias", ["1"])[0] or 1))

    def quem_faz_o_que(self, _q) -> dict:
        """Escopo de cada funcionário + o último trabalho que ele deixou registrado (robo/atividade_equipe.py)."""
        from robo import atividade_equipe
        return atividade_equipe.quadro(self.cfg)

    def paineis(self, _q) -> dict:
        """Dashboards montados pela Bárbara e conferidos pelo Heitor (logs/paineis/painel.json) + o registro de versões."""
        from robo import paineis
        cfg = self.cfg
        return {"painel": paineis.publicado(cfg), "versoes": paineis.versoes(cfg, 12),
                "equipe": [{"id": p["id"], "nome": p["nome"], "cargo": p["cargo"], "cor": p["cor"]} for p in paineis.EQUIPE_BI]}

    def paineis_atualizar(self, _corpo) -> dict:
        from robo import paineis
        r = paineis.rotina(self.cfg)
        return {"ok": r["situacao"] != "reprovado", **{k: v for k, v in r.items() if k != "estrela"}}

    def estrategia(self, _q) -> dict:
        from robo import estrategia, treinamento
        from robo.canal import Canal, pessoas
        cfg = self.cfg
        itens = sorted(estrategia.ler_backlog(cfg), key=lambda i: (i["status"] == "feito", -i.get("prioridade", 0)))
        gente = pessoas()
        for i in itens:
            i["responsavel_nome"] = gente.get(i.get("responsavel"), {}).get("nome", i.get("responsavel") or "—")
        avs = estrategia.ler_avaliacoes(cfg, 12)
        treinos = treinamento.historico(cfg, 12)
        numero, ini, fim = Canal(cfg).sprint_de(date.today())
        return {"backlog": itens, "alinhamento": estrategia.alinhamento(cfg, itens), "status": estrategia.NOME_STATUS,
                "sprint": {"numero": numero, "inicio": ini.isoformat(), "fim": fim.isoformat(),
                           "dias_restantes": (fim - date.today()).days},
                "avaliacao": avs[-1] if avs else None,
                "avaliacoes": [{"data_hora": a["data_hora"], "aprovados": a["aprovados"], "total": a["total"]} for a in avs],
                "treinamento": treinos[-1] if treinos else None,
                "treinamentos": [{"data_hora": t["data_hora"], "aprovados": t["aprovados"], "total": t["total"]} for t in treinos],
                "trilhas": estrategia.trilhas(cfg),
                "pessoas": sorted([{"id": k, "nome": v["nome"], "papel": v["papel"]} for k, v in gente.items() if k != "dono"],
                                  key=lambda p: p["nome"])}

    def estrategia_item(self, b) -> dict:
        from robo import estrategia
        try:
            return {"item": estrategia.salvar_item(self.cfg, b.get("item") or {})}
        except (ValueError, TypeError) as e:
            raise ErroApi(str(e))

    def estrategia_excluir(self, b) -> dict:
        from robo import estrategia
        estrategia.excluir_item(self.cfg, str(b.get("id", "")))
        return {"ok": True}

    def estrategia_avaliar(self, _b) -> dict:
        from robo import estrategia
        r = estrategia.avaliar_todos(self.cfg)
        estrategia.sincronizar(self.cfg)
        return {"aprovados": r["aprovados"], "total": r["total"]}

    def estrategia_treinar(self, _b) -> dict:
        from robo import estrategia
        r = estrategia.treinar_todos(self.cfg)
        estrategia.sincronizar(self.cfg)
        return {"aprovados": r["aprovados"], "total": r["total"]}

    def estrategia_sincronizar(self, _b) -> dict:
        from robo import estrategia
        return estrategia.sincronizar(self.cfg)

    def boas_praticas(self, _q) -> dict:
        arq = RAIZ_PROJETO / "conhecimento" / "boas_praticas.md"
        return {"texto": arq.read_text(encoding="utf-8") if arq.exists() else ""}

    # ------------------------------------------------------------ TI (5º andar)
    def ti(self, _q) -> dict:
        from robo import jornada, ti
        return {"ronda": ti.ultima_ronda(self.cfg), "intervalo_minutos": ti._c(self.cfg)["intervalo_minutos"],
                "jornada": jornada.ultimas(self.cfg, 8)}

    def jornada_rodar(self, _b) -> dict:
        from robo import jornada
        return jornada.rotina(self.cfg)

    def caixa_dono(self, _q) -> dict:
        """Tudo que chega ao dono: ideias e sugestões da equipe + o que só ele decide."""
        from robo import alcadas, caixa_dono
        try:
            alcadas.marcar_presenca(self.cfg, "painel")
        except Exception:
            pass
        itens = caixa_dono.itens(self.cfg)
        return {"itens": itens, "resumo": caixa_dono.resumo(self.cfg)}

    def caixa_dono_decidir(self, b) -> dict:
        """Quem está no painel é o dono (o painel exige a senha dele)."""
        from robo import caixa_dono
        try:
            return caixa_dono.decidir(self.cfg, str(b.get("id") or ""), bool(b.get("aprovar")), str(b.get("nota") or "")[:500])
        except (ValueError, PermissionError) as e:
            raise ErroApi(str(e))

    def ti_ronda(self, _b) -> dict:
        from robo import ti
        return {"ronda": ti.ronda(self.cfg)}

    def agente_excluir(self, b) -> dict:
        from robo.agentes import ErroAgente
        from robo.pipeline import obter_equipe
        try:
            obter_equipe(self.cfg).excluir(str(b.get("id", "")))
        except ErroAgente as e:
            raise ErroApi(str(e))
        log.info("Agente %s excluído (guardado em agentes/_excluidos)", b.get("id"))
        return {"ok": True}

    def consultas(self, _q) -> dict:
        from robo import consultas
        return {"itens": consultas.listar(), "banco_habilitado": bool(self.cfg.banco.get("habilitado"))}

    def consulta(self, q) -> dict:
        from robo import consultas
        try:
            return consultas.ler(q.get("id", [""])[0])
        except ValueError as e:
            raise ErroApi(str(e), 404)

    def consulta_executar(self, b) -> dict:
        from robo import consultas
        from robo.banco import Banco, ErroBancoIndisponivel
        cfg = self.cfg
        if not cfg.banco.get("habilitado"):
            raise ErroApi("Ligue o banco de dados em Configurações para executar consultas.", 409)
        id_consulta = str(b.get("id", ""))
        try:
            info = consultas.ler(id_consulta)
            r = consultas.executar(Banco(cfg.banco, cfg.base), id_consulta)
        except ValueError as e:
            raise ErroApi(str(e), 404)
        except ErroBancoIndisponivel as e:
            raise ErroApi(str(e), 503)
        except Exception as e:
            return {"ok": False, "mensagem": consultas.explicar_erro(str(e).strip(), info.get("requer", ""))}
        return {"ok": True, "colunas": r["colunas"], "linhas": [[_fmt(v) for v in l] for l in r["linhas"]],
                "truncado": r["truncado"], "duracao": r["duracao"]}

    def banco_resumo(self, _q) -> dict:
        from robo.banco import Banco, ErroBancoIndisponivel
        cfg = self.cfg
        if not cfg.banco.get("habilitado"):
            return {"ok": False, "habilitado": False, "mensagem": "Banco de dados desligado"}
        try:
            r = Banco(cfg.banco, cfg.base).resumo()
            for l in r["lotes"]:
                l["processado_em"] = l["processado_em"].strftime("%Y-%m-%d %H:%M:%S") if l["processado_em"] else ""
            return {"ok": True, "habilitado": True, **r}
        except ErroBancoIndisponivel as e:
            return {"ok": False, "habilitado": True, "mensagem": str(e)}

    # ---------------- ações
    def ligar(self, _b):
        self.c.ligar()
        return {"ligado": self.c.ligado}

    def pausar(self, _b):
        self.c.pausar()
        return {"ligado": self.c.ligado}

    def processar_agora(self, _b):
        if not self.c.processar_agora():
            raise ErroApi("Robô não configurado", 409)
        return {"ok": True}

    def abrir(self, b):
        cfg = self.cfg
        alvo = b.get("alvo")
        pastas = {"entrada": cfg.entrada, "tratadas": cfg.tratadas, "erros": cfg.erros, "originais": cfg.originais,
                  "relatorios": cfg.relatorios, "logs": cfg.logs,
                  "modelos": self._pasta_modelos(), "projeto": RAIZ_PROJETO,
                  "consultas": RAIZ_PROJETO / "consultas_sql", "agentes": cfg.agentes, "habilidades": cfg.habilidades}
        if alvo in pastas:
            caminho = pastas[alvo]
            caminho.mkdir(parents=True, exist_ok=True)
        elif alvo == "config":
            caminho = configuracao.garantir_arquivo(self.c.caminho_config)
        elif alvo == "arquivo":
            # só arquivos de DADOS e relatórios, das pastas de dados (nunca .bat/.vbs/.py da pasta do projeto)
            caminho = Path(str(b.get("caminho", "")))
            pastas_dados = [cfg.entrada, cfg.tratadas, cfg.erros, cfg.originais, cfg.relatorios, cfg.logs]
            seguros = {".xlsx", ".xlsm", ".xls", ".csv", ".txt", ".json", ".md", ".log"}
            if (not _dentro(caminho, pastas_dados) or not caminho.exists()
                    or caminho.suffix.lower() not in seguros):
                raise ErroApi("Arquivo não encontrado, fora das pastas de dados ou de um tipo que o painel não abre", 404)
        elif alvo == "reprovado":
            caminho = cfg.erros / Path(str(b.get("nome", ""))).name
            if not caminho.exists():
                raise ErroApi("Arquivo não encontrado em Bases-Erros", 404)
        else:
            raise ErroApi("Destino desconhecido")
        sistema.abrir_no_sistema(caminho)
        return {"ok": True, "caminho": str(caminho)}

    def reprocessar(self, b):
        cfg = self.cfg
        arq = cfg.erros / Path(str(b.get("nome", ""))).name
        if not arq.is_file():
            raise ErroApi("Arquivo não encontrado em Bases-Erros", 404)
        destino = cfg.entrada / _nome_original(arq.name)
        if destino.exists():
            raise ErroApi(f"Já existe um '{destino.name}' em Bases-Limpeza aguardando processamento.", 409)
        try:
            shutil.move(str(arq), str(destino))
        except PermissionError:
            raise ErroApi("O arquivo está aberto no Excel. Salve, feche e tente de novo.", 409)
        txt = arq.with_name(f"{arq.stem}_ERROS.txt")
        txt.unlink(missing_ok=True)
        log.info("Reprocessamento solicitado: %s voltou para Bases-Limpeza", destino.name)
        return {"ok": True, "nome": destino.name}

    def descartar(self, b):
        cfg = self.cfg
        arq = cfg.erros / Path(str(b.get("nome", ""))).name
        if not arq.is_file():
            raise ErroApi("Arquivo não encontrado em Bases-Erros", 404)
        lixeira = cfg.erros / "_descartados"
        lixeira.mkdir(exist_ok=True)
        for p in (arq, arq.with_name(f"{arq.stem}_ERROS.txt")):
            if p.exists():
                try:
                    shutil.move(str(p), str(lixeira / p.name))
                except PermissionError:
                    raise ErroApi("O arquivo está aberto no Excel. Feche e tente de novo.", 409)
        log.info("Arquivo reprovado descartado: %s (guardado em Bases-Erros/_descartados)", arq.name)
        return {"ok": True}

    def _salvar_upload(self, corpo: Path, nome: str, destino: Path) -> Path:
        nome = Path(nome).name
        if Path(nome).suffix.lower() not in EXTENSOES_SUPORTADAS:
            raise ErroApi(f"Formato não suportado. Envie {', '.join(sorted(EXTENSOES_SUPORTADAS))}.", 415)
        alvo = destino / nome
        shutil.move(str(corpo), str(alvo))
        return alvo

    def _publicar_sem_sobrescrever(self, corpo: Path, nome: str, destino: Path) -> Path:
        """Coloca o arquivo na fila sem nunca sobrescrever outro com o mesmo nome, nem com dois envios ao mesmo tempo.
        Copia para um nome que o monitor ignora (~robo_tmp_…) e publica com os.link, que é atômico e FALHA se o nome
        já existir (no Windows, os.rename também falha nesse caso)."""
        nome = Path(nome).name
        if Path(nome).suffix.lower() not in EXTENSOES_SUPORTADAS:
            raise ErroApi(f"Formato não suportado. Envie {', '.join(sorted(EXTENSOES_SUPORTADAS))}.", 415)
        alvo = destino / nome
        temp = destino / f"~robo_tmp_{uuid.uuid4().hex}_{nome}"
        shutil.move(str(corpo), str(temp))
        try:
            try:
                os.link(temp, alvo)
                temp.unlink()
            except FileExistsError:
                raise
            except OSError:  # sistema de arquivos sem link: no Windows, rename não sobrescreve
                if os.name != "nt" and alvo.exists():
                    raise FileExistsError(alvo)
                os.rename(temp, alvo)
        except FileExistsError:
            temp.unlink(missing_ok=True)
            raise ErroApi(f"Já existe '{nome}' aguardando em Bases-Limpeza.", 409)
        return alvo

    def testar(self, corpo: Path, nome: str):
        pasta = Path(tempfile.mkdtemp(prefix="robo_teste_"))
        try:
            arq = self._salvar_upload(corpo, nome, pasta)
            r = processar_arquivo(arq, self.cfg, gravar=False)
            tabelas = []
            for n, df in r.tabelas.items():
                amostra = df.head(25)
                from robo.modelagem import tipo_amigavel
                tabelas.append({
                    "nome": n, "linhas": len(df),
                    "colunas": [{"nome": c, "tipo": tipo_amigavel(df[c]),
                                 "vazios": int(df[c].isna().sum())} for c in df.columns],
                    "amostra": [[_fmt(v) for v in linha] for linha in amostra.astype(object).itertuples(index=False, name=None)],
                })
            return {"arquivo": arq.name, "aprovado": not r.relatorio.tem_erros, "linhas_entrada": r.linhas_entrada,
                    "linhas_saida": r.linhas_saida, "duracao": round(r.duracao, 2),
                    "regra": self.cfg.regra_para(arq.name).get("padrao"),
                    "ocorrencias": _ocorrencias(r.relatorio), "tabelas": tabelas}
        finally:
            shutil.rmtree(pasta, ignore_errors=True)

    def enviar(self, corpo: Path, nome: str):
        cfg = self.cfg
        if (cfg.entrada / Path(nome).name).exists():  # resposta rápida; a garantia de verdade é a publicação atômica
            raise ErroApi(f"Já existe '{Path(nome).name}' aguardando em Bases-Limpeza.", 409)
        alvo = self._publicar_sem_sobrescrever(corpo, nome, cfg.entrada)
        log.info("Arquivo enviado pelo painel: %s", alvo.name)
        return {"ok": True, "nome": alvo.name}

    def definir_entrada(self, b):
        caminho = Path(str(b.get("caminho", "")).strip().strip('"'))
        if not caminho.is_dir():
            raise ErroApi("Essa pasta não existe. Copie o caminho no Explorador (botão direito > Copiar como caminho).")
        arquivo = configuracao.garantir_arquivo(self.c.caminho_config)
        configuracao.definir(arquivo, "pastas", "entrada", caminho.as_posix())
        self.c.recarregar()
        if self.c.cfg and self.c.cfg.painel.get("ligar_robo_ao_abrir", True):
            self.c.ligar()
        return {"ok": self.c.cfg is not None, "erro": self.c.erro_config}

    def salvar_config(self, b):
        arquivo = configuracao.garantir_arquivo(self.c.caminho_config)
        alteracoes = b.get("alteracoes") or {}
        if not isinstance(alteracoes, dict) or not all(isinstance(v, dict) or v is None for v in alteracoes.values()):
            raise ErroApi("'alteracoes' precisa ser {seção: {chave: valor}}.")
        try:
            for secao, valores in alteracoes.items():
                for chave, valor in (valores or {}).items():
                    if secao == "banco" and chave == "senha" and valor in (None, ""):
                        continue  # campo vazio = manter a senha atual
                    configuracao.definir(arquivo, secao, chave, valor)
        except ValueError as e:
            raise ErroApi(str(e))
        self.c.recarregar()
        log.info("Configurações salvas pelo painel")
        return {"ok": True, "erro": self.c.erro_config}

    def banco_testar(self, b):
        from robo.banco import Banco
        cfg = self.cfg
        params = dict(cfg.banco)
        for k, v in (b.get("banco") or {}).items():
            if k == "senha" and not v:
                continue
            params[k] = v
        return Banco(params, cfg.base).testar()

    def banco_modelos(self, _b):
        from robo.banco import Banco, ErroBancoIndisponivel, ErroCargaDados
        cfg = self.cfg
        banco = Banco(cfg.banco, cfg.base)
        try:
            with banco.conectar() as conn, conn.transaction():
                banco.inicializar(conn)
                feitos = banco.executar_modelos(conn)
            log.info("Modelos SQL executados pelo painel: %s", ", ".join(feitos) or "nenhum")
            return {"ok": True, "executados": feitos}
        except (ErroBancoIndisponivel, ErroCargaDados) as e:
            return {"ok": False, "mensagem": str(e)}

    def manutencao(self, _b):
        return {"ok": True, "removidos": executar_manutencao(self.cfg)}

    def inicializacao(self, b):
        try:
            return {"ligado": sistema.definir_inicializacao(bool(b.get("ligar")))}
        except RuntimeError as e:
            raise ErroApi(str(e))

    def atalhos(self, _b):
        try:
            return {"ok": True, "locais": sistema.criar_atalhos()}
        except Exception as e:
            raise ErroApi(f"Não consegui criar os atalhos: {e}")

    def recarregar(self, _b):
        self.c.recarregar()
        return {"ok": self.c.cfg is not None, "erro": self.c.erro_config}

    def sair(self, _b):
        log.info("Aplicativo encerrado pelo painel.")
        threading.Thread(target=lambda: (time.sleep(0.3), self.encerrar.set()), daemon=True).start()
        return {"ok": True}

    # ------------------------------------------------------------ atendimento, solicitações e memória
    def _pasta_anexos(self) -> Path:
        p = Path(self.cfg.logs) / "trabalho" / "anexos"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def anexar(self, corpo: Path, nome: str):
        pasta = self._pasta_anexos() / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        pasta.mkdir(parents=True)
        alvo = self._salvar_upload(corpo, nome, pasta)
        return {"arquivo": str(alvo), "nome": alvo.name}

    def funcionarios(self, q) -> dict:
        from robo import ia, organizacao
        return {"funcionarios": [{k: v for k, v in p.items() if k != "_agente"} |
                                 {"nivel": organizacao.nivel_de(p["id"], p), "area": organizacao.area_de(p["id"]),
                                  "lider": p["id"] in organizacao.LIDERES}
                                 for p in organizacao.lista(self.cfg)], "andares": organizacao.NOME_ANDAR,
                "ia": ia.status(self.cfg)}

    def funcionario(self, q) -> dict:
        from robo import memoria
        pid = q.get("id", [""])[0]
        d = memoria.dossie(self.cfg, pid)
        if not d:
            raise ErroApi("Funcionário não encontrado.", 404)
        from robo.trabalho import Trabalho
        return {**d, "conversas_recentes": Trabalho(self.cfg).conversas(pid, 10)}

    def conversa(self, q) -> dict:
        from robo.trabalho import Trabalho
        c = Trabalho(self.cfg).conversa(q.get("id", [""])[0])
        if not c:
            raise ErroApi("Conversa não encontrada.", 404)
        return c

    def conversa_enviar(self, b) -> dict:
        from robo import atendimento
        arquivo = b.get("arquivo") or None
        if arquivo:  # só aceita arquivo que veio pelo anexo do painel
            alvo = Path(str(arquivo)).resolve()
            if self._pasta_anexos().resolve() not in alvo.parents or not alvo.is_file():
                raise ErroApi("Anexo inválido: envie o arquivo pelo botão de anexar.", 400)
            arquivo = str(alvo)
        return atendimento.conversar(self.cfg, str(b.get("funcionario") or ""), str(b.get("texto") or ""),
                                     b.get("conversa_id") or None, arquivo, str(b.get("origem") or "ficha")[:20])

    def solicitacoes(self, q) -> dict:
        from robo.trabalho import ESTADOS, Trabalho
        g = lambda k: (q.get(k, [""])[0] or None)  # noqa: E731
        tb = Trabalho(self.cfg)
        andar = g("andar")
        dias = g("dias")
        return {"itens": tb.listar(estado=g("estado"), funcionario=g("funcionario"), andar=int(andar) if andar else None,
                                   tipo=g("tipo"), prioridade=g("prioridade"), origem=g("origem"),
                                   dias=int(dias) if dias else None, texto=g("texto")),
                "contagem": tb.contagem(), "aprovacoes": tb.aprovacoes_pendentes(), "estados": ESTADOS}

    def solicitacao(self, q) -> dict:
        from robo.trabalho import Trabalho
        s = Trabalho(self.cfg).solicitacao(q.get("id", [""])[0])
        if not s:
            raise ErroApi("Solicitação não encontrada.", 404)
        return s

    def solicitacao_criar(self, b) -> dict:
        from robo import orquestrador
        texto = str(b.get("texto") or "").strip()
        if not texto:
            raise ErroApi("Descreva o que você precisa.")
        arquivo = b.get("arquivo") or None
        if arquivo:
            alvo = Path(str(arquivo)).resolve()
            if self._pasta_anexos().resolve() not in alvo.parents or not alvo.is_file():
                raise ErroApi("Anexo inválido.", 400)
            arquivo = str(alvo)
        sid = orquestrador.criar(self.cfg, texto, b.get("funcionario") or "canal_nina", origem="manual", arquivo=arquivo,
                                 prioridade=str(b.get("prioridade") or "media"))
        return {"id": sid}

    def aprovacao_decidir(self, b) -> dict:
        from robo import orquestrador
        from robo.trabalho import ErroTransicao
        try:
            return orquestrador.decidir(self.cfg, str(b.get("id") or ""), bool(b.get("aprovado")), str(b.get("motivo") or "")[:500])
        except ErroTransicao as e:
            raise ErroApi(str(e), 409)

    def solicitacao_cancelar(self, b) -> dict:
        from robo import orquestrador
        from robo.trabalho import ErroTransicao
        try:
            orquestrador.cancelar(self.cfg, str(b.get("id") or ""), str(b.get("motivo") or "")[:500])
        except ErroTransicao as e:
            raise ErroApi(str(e), 409)
        return {"ok": True}

    def memoria_resumo(self, q) -> dict:
        from robo import memoria, reuniao
        dias = int(q.get("dias", ["7"])[0])
        from robo import desenvolvimento, ideias
        return {"desempenho": memoria.desempenho(self.cfg, dias), "handovers": memoria.handovers(self.cfg, limite=100),
                "pdca": memoria.resumo_pdca(self.cfg), "boas_praticas": memoria.boas_praticas(self.cfg, limite=100),
                "ideias": ideias.gerar(self.cfg), "ultimo_estudo": desenvolvimento.ultima_rodada(self.cfg),
                "reunioes": [{k: r[k] for k in ("id", "inicio", "fim", "data_hora", "arquivo")} | {"ata": r["ata"]}
                             for r in reuniao.listar(self.cfg, 5)]}

    def handover_estado(self, b) -> dict:
        from robo import memoria
        try:
            memoria.mudar_handover(self.cfg, str(b.get("id") or ""), str(b.get("estado") or ""))
        except ValueError as e:
            raise ErroApi(str(e))
        return {"ok": True}

    def raio_x(self, q) -> dict:
        from robo import lideranca, raio_x
        r = raio_x.montar(self.cfg)
        r["scorecards"] = [lideranca.scorecard(self.cfg, d) for d in
                           ("dir_dados", "dir_analytics", "dir_operacoes", "dir_pessoas", "dir_tecnologia")]
        r["resumo"] = raio_x.texto(r)
        return r

    def auditorias_rodar(self, _b) -> dict:
        from robo import auditoria, rotinas
        res = rotinas.executar(self.cfg, "auditoria", lambda: auditoria.auditar_todos(self.cfg))
        return {"auditorias": res}

    def sala_abrir(self, b) -> dict:
        from robo import sala
        andar = int(b.get("andar") or 1)
        if andar not in (1, 2, 3, 4, 5):
            raise ErroApi("Andar inválido.")
        return sala.abrir(self.cfg, andar)

    def sala_falar(self, b) -> dict:
        from robo import sala
        texto = str(b.get("texto") or "").strip()
        if not texto:
            raise ErroApi("Escreva o que quer dizer na reunião.")
        try:
            return sala.falar(self.cfg, str(b.get("conversa_id") or ""), texto, b.get("para") or None)
        except ValueError as e:
            raise ErroApi(str(e))

    def sala_acao(self, b) -> dict:
        """Botões da sala (estilo Teams). Cada ação fica registrada em sala_eventos."""
        from robo import sala
        cid, acao = str(b.get("conversa_id") or ""), str(b.get("acao") or "")
        try:
            if acao == "palavra":
                return sala.dar_palavra(self.cfg, cid, str(b.get("id") or ""))
            if acao == "maos":
                return {"maos": sala.levantar_maos(self.cfg, cid)}
            if acao == "reagir":
                return sala.reagir(self.cfg, cid, int(b.get("mensagem") or 0), str(b.get("reacao") or ""))
            if acao == "convidar":
                return sala.convidar(self.cfg, cid, str(b.get("id") or ""))
            if acao == "remover":
                return sala.remover(self.cfg, cid, str(b.get("id") or ""))
            if acao == "compartilhar":
                return sala.compartilhar(self.cfg, cid, str(b.get("tipo") or ""), b.get("ref") or None)
            if acao == "notas":
                return sala.anotar(self.cfg, cid, str(b.get("texto") or ""))
            if acao == "pauta":
                itens = b.get("itens")
                return sala.pauta(self.cfg, cid, [str(x) for x in itens] if isinstance(itens, list) else None,
                                  int(b["marcar"]) if b.get("marcar") is not None else None)
            if acao in ("tarefa", "decisao"):
                return sala.criar_tarefa(self.cfg, cid, str(b.get("texto") or "").strip(), str(b.get("responsavel") or ""),
                                         str(b.get("prazo") or ""), str(b.get("criterio") or ""))
            if acao == "repactuar":
                return sala.repactuar(self.cfg, cid, str(b.get("id") or ""), str(b.get("prazo") or ""), str(b.get("motivo") or ""))
            if acao == "concluir_decisao":
                return sala.concluir_decisao(self.cfg, cid, str(b.get("id") or ""), str(b.get("evidencia") or ""))
            if acao == "cancelar_decisao":
                return sala.cancelar_decisao(self.cfg, cid, str(b.get("id") or ""), str(b.get("motivo") or ""))
            if acao == "encerrar":
                return sala.encerrar(self.cfg, cid, str(b.get("justificativa") or ""))
        except ValueError as e:
            raise ErroApi(str(e))
        raise ErroApi("Ação desconhecida.")

    def sala_ver(self, q) -> dict:
        from robo import sala
        d = sala.detalhes(self.cfg, q.get("id", [""])[0])
        if not d:
            raise ErroApi("Reunião não encontrada.", 404)
        return d

    def salas(self, q) -> dict:
        from robo.trabalho import Trabalho
        return {"salas": [c for c in Trabalho(self.cfg).conversas(limite=100) if (c["contexto"] or {}).get("sala")][:10]}

    def reuniao_ao_vivo(self, q) -> dict:
        from robo import reuniao
        andar = q.get("andar", [""])[0]
        return reuniao.ao_vivo(self.cfg, int(andar) if andar else None)

    def estudo_rodar(self, _b) -> dict:
        from robo import desenvolvimento
        r = desenvolvimento.estudar(self.cfg)
        return {k: r[k] for k in ("funcionarios", "aprovados")}

    def reuniao_gerar(self, _b) -> dict:
        from robo import reuniao
        return reuniao.gerar(self.cfg)

    def memoria_exportar(self, b) -> dict:
        from robo import memoria
        arq = memoria.exportar_dossie(self.cfg, str(b.get("id") or ""))
        if not arq:
            raise ErroApi("Funcionário não encontrado.", 404)
        return {"arquivo": str(arq)}

    def memoria_sincronizar(self, _b) -> dict:
        from robo import memoria
        return memoria.sincronizar_postgres(self.cfg)

    # ------------------------------------------------------------------ gestão do projeto
    def gestao(self, _q) -> dict:
        """Visão de gestão + checagem ao vivo de cada página: chama as mesmas rotas que a página usa."""
        import time
        from robo import gestao
        v = gestao.visao(self.cfg)
        for pg in v["paginas"]:
            pg["checagens"] = []
            for rota in pg["apis"]:
                if rota == "/api/gestao":
                    pg["checagens"].append({"rota": rota, "ok": True, "ms": None, "erro": None})
                    continue
                inicio = time.perf_counter()
                try:
                    ROTAS_GET[rota](self, {})
                    ok, erro = True, None
                except ErroApi as e:  # resposta controlada (ex.: banco desligado) não é defeito da página
                    ok, erro = e.status < 500, str(e)
                except Exception as e:
                    log.exception("Gestão: rota %s falhou", rota)
                    ok, erro = False, f"{type(e).__name__}: {e}"
                pg["checagens"].append({"rota": rota, "ok": ok, "ms": round(1000 * (time.perf_counter() - inicio)), "erro": erro})
            pg["ok"] = all(c["ok"] for c in pg["checagens"])
        return v

    # ------------------------------------------------------------------ caderno de lições e erros de sistema
    # Quem usa o painel é o dono (entrou com a senha): só daqui saem lição manual, versão nova e arquivamento.
    def conhecimento(self, _q) -> dict:
        from robo import licoes
        return licoes.painel(self.cfg)

    def conhecimento_caderno(self, q) -> dict:
        from robo import licoes, organizacao
        pid = q.get("id", [""])[0]
        if pid not in organizacao.por_id(self.cfg):
            raise ErroApi("Funcionário não encontrado.", 404)
        return licoes.caderno(self.cfg, pid)

    def conhecimento_licao(self, q) -> dict:
        from robo import licoes
        d = licoes.detalhe(self.cfg, q.get("id", [""])[0])
        if not d:
            raise ErroApi("Lição não encontrada.", 404)
        return d

    def conhecimento_buscar(self, q) -> dict:
        from robo import licoes
        return {"licoes": licoes.buscar(self.cfg, q.get("q", [""])[0], q.get("funcionario", [None])[0] or None, 20)}

    def conhecimento_rodar(self, _b) -> dict:
        from robo import licoes, rotinas
        r = rotinas.executar(self.cfg, "licoes", lambda: licoes.rodada(self.cfg))
        licoes.exportar(self.cfg)
        return r or {}

    def conhecimento_criar(self, b) -> dict:
        from robo import licoes
        campos = {k: str(b.get(k) or "").strip() for k in ("titulo", "conteudo", "pergunta", "como_aplicar", "publico")}
        if not (campos["titulo"] and campos["conteudo"]):
            raise ErroApi("A lição precisa de título e conteúdo.")
        andar = int(b["andar"]) if str(b.get("andar") or "").isdigit() else None
        lid = licoes.criar(self.cfg, "dono", f"{campos['titulo']}|{datetime.now().isoformat()}", campos["titulo"],
                           campos["conteudo"], campos["pergunta"] or campos["titulo"],
                           campos["como_aplicar"] or "usar nas respostas e no trabalho", andar, None,
                           campos["publico"] if campos["publico"] in ("andar", "todos", "lideranca") else "todos", "dono")
        return {"id": lid}

    def conhecimento_versao(self, b) -> dict:
        from robo import licoes
        conteudo, motivo = str(b.get("conteudo") or "").strip(), str(b.get("motivo") or "").strip()
        if not (conteudo and motivo):
            raise ErroApi("Versão nova exige o conteúdo e o motivo da mudança.")
        return {"id": licoes.nova_versao(self.cfg, str(b.get("id") or ""), conteudo, motivo, "dono")}

    def conhecimento_arquivar(self, b) -> dict:
        from robo import licoes
        licoes.arquivar(self.cfg, str(b.get("id") or ""), str(b.get("motivo") or ""), "dono")
        return {"ok": True}

    def aprendizado(self, _q) -> dict:
        from robo import aprendizado
        return {"propostas": aprendizado.listar(self.cfg), **aprendizado.resumo(self.cfg)}

    def aprendizado_decidir(self, b) -> dict:
        """Só o dono (quem está no painel) aprova ou recusa uma regra nova."""
        from robo import aprendizado
        try:
            return aprendizado.decidir(self.cfg, str(b.get("id") or ""), bool(b.get("aprovar")), "dono", str(b.get("motivo") or ""))
        except ValueError as e:
            raise ErroApi(str(e))

    def aprendizado_desativar(self, b) -> dict:
        """Só o dono desativa uma regra aprendida (com motivo). Não apaga: o registro fica."""
        from robo import aprendizado
        try:
            return aprendizado.desativar(self.cfg, str(b.get("id") or ""), "dono", str(b.get("motivo") or ""))
        except ValueError as e:
            raise ErroApi(str(e))

    def banco_registros(self, _q) -> dict:
        """O banco de registros ao vivo: tabelas, linhas, proteção, integridade, backups e cópia no PostgreSQL."""
        from robo import dicionario_dados
        return dicionario_dados.estado(self.cfg)

    def treino(self, _q) -> dict:
        from robo import treino
        return treino.painel(self.cfg)

    def governanca(self, _q) -> dict:
        """RH de desempenho e alçadas (somente leitura)."""
        from robo import alcadas, rh_desempenho
        return {"rh": rh_desempenho.resumo(self.cfg), "alcadas": alcadas.listar(self.cfg, 50),
                "dono": alcadas.dono_offline(self.cfg), "matriz": {k: list(v) for k, v in alcadas.MATRIZ.items()}}

    def treino_pessoa(self, q) -> dict:
        from robo import treino
        return treino.pessoa(self.cfg, q.get("id", [""])[0])

    def treino_rodar(self, b) -> dict:
        """Uma rodada agora (o robô já roda sozinho a cada poucos minutos)."""
        from robo import treino
        quantos = max(1, min(30, int(b.get("quantos") or 6)))
        r = treino.rodada(self.cfg, quantos)
        return {k: r.get(k) for k in ("ok", "motivo", "rodada", "tentativas", "acertos", "sem_caso")}

    def erros_sistema(self, _q) -> dict:
        from robo import erros
        return {"erros": erros.listar(self.cfg)}

    def erros_resolver(self, b) -> dict:
        from robo import erros
        erros.marcar_resolvido(self.cfg, int(b.get("id") or 0), "dono")
        return {"ok": True}


ROTAS_GET = {
    "/api/ping": lambda api, q: {"app": "robo-planilhas", "versao": __version__},
    "/api/governanca": Api.governanca,
    "/api/estado": Api.estado, "/api/escritorio": Api.escritorio, "/api/agentes": Api.agentes, "/api/historico": Api.historico, "/api/execucao": Api.execucao,
    "/api/reprovados": Api.reprovados, "/api/log": Api.log, "/api/config": Api.config,
    "/api/banco/resumo": Api.banco_resumo, "/api/canal": Api.canal, "/api/ti": Api.ti,
    "/api/central": Api.central, "/api/estrategia": Api.estrategia, "/api/boas-praticas": Api.boas_praticas,
    "/api/agentes/manual": Api.agente_manual_ler, "/api/consultas": Api.consultas, "/api/consulta": Api.consulta,
    "/api/funcionarios": Api.funcionarios, "/api/funcionario": Api.funcionario, "/api/conversa": Api.conversa,
    "/api/solicitacoes": Api.solicitacoes, "/api/solicitacao": Api.solicitacao, "/api/memoria": Api.memoria_resumo,
    "/api/reuniao/ao-vivo": Api.reuniao_ao_vivo, "/api/raio-x": Api.raio_x,
    "/api/reuniao/sala": Api.sala_ver, "/api/reuniao/salas": Api.salas,
    "/api/conhecimento": Api.conhecimento, "/api/conhecimento/caderno": Api.conhecimento_caderno,
    "/api/conhecimento/licao": Api.conhecimento_licao, "/api/conhecimento/buscar": Api.conhecimento_buscar,
    "/api/erros": Api.erros_sistema, "/api/gestao": Api.gestao, "/api/treino": Api.treino, "/api/banco/registros": Api.banco_registros, "/api/treino/pessoa": Api.treino_pessoa, "/api/aprendizado": Api.aprendizado,
    "/api/paineis": Api.paineis, "/api/quem-faz-o-que": Api.quem_faz_o_que, "/api/prova-de-trabalho": Api.prova_de_trabalho, "/api/fabrica": Api.fabrica,
    "/api/caixa-dono": Api.caixa_dono,
}
ROTAS_POST = {
    "/api/robo/ligar": Api.ligar, "/api/robo/pausar": Api.pausar, "/api/robo/processar-agora": Api.processar_agora,
    "/api/abrir": Api.abrir, "/api/reprovados/reprocessar": Api.reprocessar, "/api/reprovados/descartar": Api.descartar,
    "/api/config/entrada": Api.definir_entrada, "/api/config/salvar": Api.salvar_config,
    "/api/config/recarregar": Api.recarregar, "/api/banco/testar": Api.banco_testar,
    "/api/banco/modelos": Api.banco_modelos, "/api/manutencao": Api.manutencao,
    "/api/consultas/executar": Api.consulta_executar, "/api/agentes/salvar": Api.agente_salvar,
    "/api/agentes/excluir": Api.agente_excluir, "/api/agentes/manual/salvar": Api.agente_manual,
    "/api/canal/enviar": Api.canal_enviar, "/api/canal/sprint": Api.canal_sprint, "/api/ti/ronda": Api.ti_ronda,
    "/api/estrategia/item": Api.estrategia_item, "/api/estrategia/excluir": Api.estrategia_excluir,
    "/api/estrategia/avaliar": Api.estrategia_avaliar, "/api/estrategia/treinar": Api.estrategia_treinar,
    "/api/estrategia/sincronizar": Api.estrategia_sincronizar, "/api/inicializacao": Api.inicializacao, "/api/atalhos": Api.atalhos, "/api/sair": Api.sair,
    "/api/conversa/enviar": Api.conversa_enviar, "/api/solicitacoes/criar": Api.solicitacao_criar,
    "/api/aprovacoes/decidir": Api.aprovacao_decidir, "/api/solicitacoes/cancelar": Api.solicitacao_cancelar,
    "/api/handovers/estado": Api.handover_estado, "/api/reuniao/gerar": Api.reuniao_gerar, "/api/estudo/rodar": Api.estudo_rodar,
    "/api/auditorias/rodar": Api.auditorias_rodar,
    "/api/reuniao/sala/abrir": Api.sala_abrir, "/api/reuniao/sala/falar": Api.sala_falar,
    "/api/reuniao/sala/acao": Api.sala_acao,
    "/api/memoria/exportar": Api.memoria_exportar, "/api/memoria/sincronizar": Api.memoria_sincronizar,
    "/api/conhecimento/rodar": Api.conhecimento_rodar, "/api/conhecimento/criar": Api.conhecimento_criar,
    "/api/conhecimento/versao": Api.conhecimento_versao, "/api/conhecimento/arquivar": Api.conhecimento_arquivar,
    "/api/erros/resolver": Api.erros_resolver, "/api/aprendizado/decidir": Api.aprendizado_decidir, "/api/treino/rodar": Api.treino_rodar, "/api/aprendizado/desativar": Api.aprendizado_desativar,
    "/api/paineis/atualizar": Api.paineis_atualizar, "/api/fabrica/produzir": Api.fabrica_produzir, "/api/ia/testar": Api.ia_testar,
    "/api/caixa-dono/decidir": Api.caixa_dono_decidir, "/api/jornada/rodar": Api.jornada_rodar,
}
ROTAS_UPLOAD = {"/api/testar": Api.testar, "/api/enviar": Api.enviar, "/api/conversa/anexar": Api.anexar}


def criar_manipulador(api: Api):
    hosts_validos = {f"127.0.0.1:{api.porta}", f"localhost:{api.porta}"}
    origens_validas = {f"http://{h}" for h in hosts_validos}

    class Manipulador(BaseHTTPRequestHandler):
        server_version = "RoboPlanilhas"
        timeout = 30  # conexão lenta ou corpo menor que o anunciado não segura uma linha de execução para sempre

        def log_message(self, *args):  # silencia o log padrão de cada requisição
            pass

        def _json(self, dados, status=200, cabecalhos=None):
            corpo = json.dumps(dados, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            for k, v in (cabecalhos or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            for k, v in CABECALHOS_SEGURANCA.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def _host_ok(self) -> bool:
            return self.headers.get("Host", "") in hosts_validos

        def _token(self):
            return token_do_cookie(self.headers.get("Cookie"))

        def _bloqueado(self, caminho: str) -> bool:
            """Com senha definida, toda rota /api (menos login e ping) exige sessão válida."""
            if not caminho.startswith("/api/") or caminho in ROTAS_LIVRES:
                return False
            if api.senha_hash and not api.acesso.valida(self._token()):
                return True
            api.presenca()  # quem passou daqui é o dono usando o painel
            return False

        def do_GET(self):
            if not self._host_ok():
                return self._json({"erro": "host inválido"}, 403)
            url = urllib.parse.urlparse(self.path)
            if self._bloqueado(url.path):
                return self._json({"erro": "Entre com a senha do painel.", "login": True}, 401)
            if url.path == "/api/acesso":
                return self._json(api.acesso_estado({}, self._token()))
            if url.path in ROTAS_GET:
                return self._executar(lambda: ROTAS_GET[url.path](api, urllib.parse.parse_qs(url.query)))
            return self._estatico(url.path)

        def do_POST(self):
            if not self._host_ok() or self.headers.get(CABECALHO_ACAO) != "1":
                return self._json({"erro": "requisição recusada"}, 403)
            origem = self.headers.get("Origin")
            if origem and origem not in origens_validas:
                return self._json({"erro": "origem recusada"}, 403)
            caminho = urllib.parse.urlparse(self.path).path
            try:
                tamanho = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                tamanho = -1
            if tamanho < 0:
                self.close_connection = True
                return self._json({"erro": "tamanho da requisição inválido"}, 400)
            if self._bloqueado(caminho):
                self.close_connection = True
                return self._json({"erro": "Entre com a senha do painel.", "login": True}, 401)
            if caminho in ("/api/login", "/api/logout", "/api/senha"):
                return self._acesso(caminho, tamanho)
            if caminho in ROTAS_UPLOAD:
                return self._upload(caminho, tamanho)
            if caminho not in ROTAS_POST:
                return self._json({"erro": "rota inexistente"}, 404)
            if tamanho > LIMITE_JSON:
                self.close_connection = True  # não lê o corpo gigante: responde e encerra a conexão
                return self._json({"erro": "requisição grande demais"}, 413)
            try:
                corpo = json.loads(self.rfile.read(tamanho) or b"{}") if tamanho else {}
            except ValueError:  # JSON inválido e também bytes que não são UTF-8
                return self._json({"erro": "JSON inválido"}, 400)
            if not isinstance(corpo, dict):
                return self._json({"erro": "O corpo precisa ser um objeto JSON ({...})."}, 400)
            return self._executar(lambda: ROTAS_POST[caminho](api, corpo))

        def _upload(self, caminho, tamanho):
            if tamanho <= 0 or tamanho > LIMITE_UPLOAD:
                return self._json({"erro": "Arquivo vazio ou maior que 300 MB"}, 413)
            nome = urllib.parse.unquote(self.headers.get("X-Nome-Arquivo", "")) or "arquivo"
            fd, nome_temp = tempfile.mkstemp(prefix="robo_upload_")
            temp = Path(nome_temp)
            try:
                with os.fdopen(fd, "wb") as f:  # usa o descritor do mkstemp (antes ele vazava a cada upload)
                    restante = tamanho
                    while restante > 0:
                        bloco = self.rfile.read(min(1 << 20, restante))
                        if not bloco:
                            break
                        f.write(bloco)
                        restante -= len(bloco)
                if restante > 0:  # a conexão caiu no meio: arquivo incompleto não é processado
                    return self._json({"erro": "O envio foi interrompido antes do fim. Tente de novo."}, 400)
                return self._executar(lambda: ROTAS_UPLOAD[caminho](api, temp, nome))
            finally:
                temp.unlink(missing_ok=True)

        def _acesso(self, caminho, tamanho):
            if tamanho > 10_000:
                self.close_connection = True
                return self._json({"erro": "requisição grande demais"}, 413)
            try:
                b = json.loads(self.rfile.read(tamanho) or b"{}")
            except ValueError:
                return self._json({"erro": "JSON inválido"}, 400)
            if not isinstance(b, dict):
                return self._json({"erro": "O corpo precisa ser um objeto JSON ({...})."}, 400)
            if caminho == "/api/logout":
                api.acesso.sair(self._token())
                return self._json({"ok": True}, cabecalhos={"Set-Cookie": f"{NOME_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"})
            if caminho == "/api/senha":
                if api.senha_hash and not api.acesso.valida(self._token()):
                    return self._json({"erro": "Entre com a senha do painel.", "login": True}, 401)
                return self._executar(lambda: api.definir_senha(b))
            if not api.senha_hash:
                return self._json({"ok": True, "sem_senha": True})
            try:
                token = api.acesso.entrar(str(b.get("senha") or ""), api.senha_hash)
            except ValueError as e:
                log.warning("Login recusado no painel: %s", e)
                return self._json({"erro": str(e)}, 403)
            return self._json({"ok": True}, cabecalhos={
                "Set-Cookie": f"{NOME_COOKIE}={token}; Path=/; Max-Age={VALIDADE_SESSAO}; HttpOnly; SameSite=Strict"})

        def _executar(self, funcao):
            try:
                return self._json(funcao())
            except ErroApi as e:
                return self._json({"erro": str(e)}, e.status)
            except (ValueError, TypeError) as e:  # parâmetro inválido (ex.: dias=abc) é erro de quem pediu
                return self._json({"erro": f"Parâmetro inválido: {e}"}, 400)
            except Exception as e:
                log.exception("Erro na API do painel")
                return self._json({"erro": f"{type(e).__name__}: {e}"}, 500)

        def _estatico(self, caminho):
            nome = "inicio.html" if caminho in ("", "/") else caminho.lstrip("/")
            arquivo = (ESTATICOS / nome).resolve()
            if ESTATICOS.resolve() not in arquivo.parents or not arquivo.is_file():
                return self._json({"erro": "não encontrado"}, 404)
            corpo = arquivo.read_bytes()
            # tipos fixos: no Windows o mimetypes lê o registro e pode devolver text/plain para .js,
            # o que impede o navegador de executar os módulos do escritório 3D
            tipo = TIPOS_ESTATICOS.get(arquivo.suffix.lower()) or mimetypes.guess_type(arquivo.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Cache-Control", "no-cache")
            for k, v in CABECALHOS_SEGURANCA.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

    return Manipulador


def ja_rodando(porta: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/ping", timeout=1.5) as r:
            return json.loads(r.read()).get("app") == "robo-planilhas"
    except Exception:
        return False


def iniciar_app(caminho_config: Path | None = None, abrir_janela: bool = True, porta: int | None = None) -> int:
    controle = ControleRobo(caminho_config)
    porta = porta or int((controle.cfg.painel if controle.cfg else {}).get("porta", 8765))
    url = f"http://127.0.0.1:{porta}/"
    if ja_rodando(porta):
        log.info("O robô já está aberto; mostrando a janela.")
        if abrir_janela:
            sistema.abrir_janela(url)
        return 0

    pasta_trava = controle.cfg.logs if controle.cfg else RAIZ_PROJETO / "logs"
    try:
        trava = TravaInstancia(pasta_trava).__enter__()
    except RuntimeError as e:
        log.error("%s (feche o robô aberto pelo iniciar_robo.bat ou ferramentas)", e)
        return 3

    api = Api(controle, porta)
    try:
        servidor = ThreadingHTTPServer(("127.0.0.1", porta), criar_manipulador(api))
    except OSError as e:
        log.error("Porta %s ocupada por outro programa (%s). Mude 'painel: porta' no config.yaml.", porta, e)
        trava.__exit__()
        return 4
    servidor.daemon_threads = True
    threading.Thread(target=servidor.serve_forever, name="robo-painel", daemon=True).start()
    log.info("Painel disponível em %s", url)
    try:  # acompanhamento pelo celular: servidor separado, SOMENTE LEITURA, desligado por padrão (robo/painel/celular.py)
        from robo.painel import celular
        celular.iniciar(lambda: controle.cfg, lambda: api.senha_hash, controle)
    except Exception:
        log.exception("Não consegui ligar o acompanhamento pelo celular")

    controle.iniciar_rotinas()
    if controle.cfg and controle.cfg.painel.get("ligar_robo_ao_abrir", True):
        controle.ligar()
    if abrir_janela:
        sistema.abrir_janela(url)
    try:
        while not api.encerrar.wait(1):
            pass
    except KeyboardInterrupt:
        pass
    finally:
        controle.pausar()
        servidor.shutdown()
        trava.__exit__()
    return 0
