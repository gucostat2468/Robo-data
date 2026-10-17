"""Servidor local do painel (somente 127.0.0.1) + API JSON usada pela interface.

Segurança: só aceita conexões da própria máquina, confere o cabeçalho Host (contra "DNS rebinding")
e exige um cabeçalho próprio nas ações (POST), que páginas de outros sites não conseguem enviar.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import re
import shutil
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from datetime import date, datetime
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pandas as pd

from robo import __version__, historico
from robo.config import RAIZ_PROJETO
from robo.leitura import EXTENSOES_SUPORTADAS
from robo.manutencao import executar_manutencao
from robo.monitor import TravaInstancia, eh_candidato
from robo.painel import configuracao, sistema
from robo.painel.controle import ControleRobo
from robo.pipeline import processar_arquivo

log = logging.getLogger("robo")

ESTATICOS = Path(__file__).parent / "static"
LIMITE_UPLOAD = 300 * 1024 * 1024
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
    return {k: f.get(k) for k in ("cargo", "nivel", "area", "metodologias", "responsabilidades", "criterios", "limites", "mentor")} | \
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
class Api:
    def __init__(self, controle: ControleRobo, porta: int):
        self.c = controle
        self.porta = porta
        self.encerrar = threading.Event()

    @property
    def cfg(self):
        if not self.c.cfg:
            raise ErroApi(self.c.erro_config or "Configuração indisponível", 409)
        return self.c.cfg

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
                   "skills": [s.get("skill") for s in a.get("skills", []) if s.get("ativo", True)],
                   "aceita_skills": a.get("aceita_skills", True), "andar": 1, "ficha": _ficha_curta(a.get("ficha"))}
                  for a in obter_equipe(cfg).lista()]
        cfg_analise = {**PADRAO_ANALISE, **(cfg.dados.get("analise") or {})}
        desligados = set(cfg_analise.get("analistas_desligados") or [])
        from robo import rh
        from robo.producao import SUPERVISORES
        equipe += [{**a, "nativo": True, "aceita_skills": False, "skills": [], "ativo": a["id"] != "dba" or bool(cfg.banco.get("habilitado")),
                    "ficha": _ficha_curta(rh.ficha({"id": a["id"], "skills": []}))} for a in SUPERVISORES]
        equipe += [{**a, "id": f"analise_{a['id']}", "nativo": True, "aceita_skills": False, "skills": [], "andar": 2,
                    "ativo": bool(cfg_analise.get("habilitado", True)) and a["id"] not in desligados,
                    "ficha": _ficha_curta(rh.ficha({"id": f"analise_{a['id']}", "skills": []}))} for a in ANALISTAS]
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
            },
            "analise_hoje": self._analise_hoje(hoje),
        })
        return dados

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
            "painel": cfg.painel,
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
        from robo import skills
        from robo.agentes import POSICOES
        from robo.pipeline import obter_equipe
        equipe = obter_equipe(self.cfg)
        from robo import rh
        from robo.analise import ANALISTAS
        catalogo = [{**s, "risco": rh.RISCO_BASE.get(s["id"], "medio"), "provas": len(rh.provas_da_skill(s["id"]))}
                    for s in skills.catalogo()]
        from robo.producao import SUPERVISORES
        analistas = [{**a, "id": f"analise_{a['id']}", "nativo": True, "aceita_skills": False, "skills": [], "andar": 2,
                      "ativo": True, "ficha": rh.ficha({"id": f"analise_{a['id']}", "skills": []})} for a in ANALISTAS]
        lideranca = [{**a, "nativo": True, "aceita_skills": False, "skills": [], "ativo": True,
                      "ficha": rh.ficha({"id": a["id"], "skills": []})} for a in SUPERVISORES]
        return {"agentes": equipe.lista(), "analistas": analistas, "lideranca": lideranca, "catalogo": catalogo,
                "erros_skills": list(skills.ERROS_CARGA), "posicoes": POSICOES,
                "rh": {"niveis": [{"id": n, "nome": rh.NOME_NIVEL[n], "risco_maximo": rh.RISCO_MAXIMO[n]} for n in rh.NIVEIS],
                       "areas": rh.AREAS}}

    def agente_salvar(self, b) -> dict:
        from robo.agentes import ErroAgente
        from robo.pipeline import obter_equipe
        try:
            a = obter_equipe(self.cfg).salvar(b.get("agente") or {})
        except ErroAgente as e:
            raise ErroApi(str(e))
        log.info("Agente %s salvo pelo painel", a.get("nome") or a.get("id"))
        return {"ok": True, "id": a["id"]}

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
                  "consultas": RAIZ_PROJETO / "consultas_sql", "agentes": cfg.agentes, "skills": cfg.skills}
        if alvo in pastas:
            caminho = pastas[alvo]
            caminho.mkdir(parents=True, exist_ok=True)
        elif alvo == "config":
            caminho = configuracao.garantir_arquivo(self.c.caminho_config)
        elif alvo == "arquivo":
            caminho = Path(str(b.get("caminho", "")))
            if not _dentro(caminho, list(pastas.values())) or not caminho.exists():
                raise ErroApi("Arquivo não encontrado ou fora das pastas do robô", 404)
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
        if (cfg.entrada / Path(nome).name).exists():
            raise ErroApi(f"Já existe '{Path(nome).name}' aguardando em Bases-Limpeza.", 409)
        alvo = self._salvar_upload(corpo, nome, cfg.entrada)
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


ROTAS_GET = {
    "/api/ping": lambda api, q: {"app": "robo-planilhas", "versao": __version__},
    "/api/estado": Api.estado, "/api/escritorio": Api.escritorio, "/api/agentes": Api.agentes, "/api/historico": Api.historico, "/api/execucao": Api.execucao,
    "/api/reprovados": Api.reprovados, "/api/log": Api.log, "/api/config": Api.config,
    "/api/banco/resumo": Api.banco_resumo, "/api/consultas": Api.consultas, "/api/consulta": Api.consulta,
}
ROTAS_POST = {
    "/api/robo/ligar": Api.ligar, "/api/robo/pausar": Api.pausar, "/api/robo/processar-agora": Api.processar_agora,
    "/api/abrir": Api.abrir, "/api/reprovados/reprocessar": Api.reprocessar, "/api/reprovados/descartar": Api.descartar,
    "/api/config/entrada": Api.definir_entrada, "/api/config/salvar": Api.salvar_config,
    "/api/config/recarregar": Api.recarregar, "/api/banco/testar": Api.banco_testar,
    "/api/banco/modelos": Api.banco_modelos, "/api/manutencao": Api.manutencao,
    "/api/consultas/executar": Api.consulta_executar, "/api/agentes/salvar": Api.agente_salvar,
    "/api/agentes/excluir": Api.agente_excluir, "/api/inicializacao": Api.inicializacao, "/api/atalhos": Api.atalhos, "/api/sair": Api.sair,
}
ROTAS_UPLOAD = {"/api/testar": Api.testar, "/api/enviar": Api.enviar}


def criar_manipulador(api: Api):
    hosts_validos = {f"127.0.0.1:{api.porta}", f"localhost:{api.porta}"}
    origens_validas = {f"http://{h}" for h in hosts_validos}

    class Manipulador(BaseHTTPRequestHandler):
        server_version = "RoboPlanilhas"

        def log_message(self, *args):  # silencia o log padrão de cada requisição
            pass

        def _json(self, dados, status=200):
            corpo = json.dumps(dados, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def _host_ok(self) -> bool:
            return self.headers.get("Host", "") in hosts_validos

        def do_GET(self):
            if not self._host_ok():
                return self._json({"erro": "host inválido"}, 403)
            url = urllib.parse.urlparse(self.path)
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
            tamanho = int(self.headers.get("Content-Length") or 0)
            if caminho in ROTAS_UPLOAD:
                return self._upload(caminho, tamanho)
            if caminho not in ROTAS_POST:
                return self._json({"erro": "rota inexistente"}, 404)
            try:
                corpo = json.loads(self.rfile.read(tamanho) or b"{}") if tamanho else {}
            except json.JSONDecodeError:
                return self._json({"erro": "JSON inválido"}, 400)
            return self._executar(lambda: ROTAS_POST[caminho](api, corpo))

        def _upload(self, caminho, tamanho):
            if tamanho <= 0 or tamanho > LIMITE_UPLOAD:
                return self._json({"erro": "Arquivo vazio ou maior que 300 MB"}, 413)
            nome = urllib.parse.unquote(self.headers.get("X-Nome-Arquivo", "")) or "arquivo"
            temp = Path(tempfile.mkstemp(prefix="robo_upload_")[1])
            try:
                with open(temp, "wb") as f:
                    restante = tamanho
                    while restante > 0:
                        bloco = self.rfile.read(min(1 << 20, restante))
                        if not bloco:
                            break
                        f.write(bloco)
                        restante -= len(bloco)
                return self._executar(lambda: ROTAS_UPLOAD[caminho](api, temp, nome))
            finally:
                temp.unlink(missing_ok=True)

        def _executar(self, funcao):
            try:
                return self._json(funcao())
            except ErroApi as e:
                return self._json({"erro": str(e)}, e.status)
            except Exception as e:
                log.exception("Erro na API do painel")
                return self._json({"erro": f"{type(e).__name__}: {e}"}, 500)

        def _estatico(self, caminho):
            nome = "index.html" if caminho in ("", "/") else caminho.lstrip("/")
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
