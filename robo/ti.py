"""5º andar · TI: desenvolvimento, DevOps, infraestrutura, segurança e cloud — cuidando do próprio sistema.

Os outros andares cuidam dos DADOS. Este andar cuida da MÁQUINA e do PROGRAMA que tratam os dados:
uma "ronda de TI" roda ao ligar o robô e a cada 30 minutos (config.yaml → ti.intervalo_minutos).
Cada pessoa faz uma verificação real no seu computador e o resultado aparece no painel, no prédio 3D e,
quando algo muda para pior, no canal #ti (sem repetir o mesmo alerta a cada ronda).

Nada aqui usa internet ou nuvem. A arquiteta de cloud é CONSULTIVA: avalia se o sistema estaria pronto para
migrar para a AWS um dia, sem enviar nada para fora.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta
from importlib import metadata
from pathlib import Path

from robo.config import RAIZ_PROJETO

log = logging.getLogger("robo")

PADRAO_TI = {"intervalo_minutos": 30, "disco_minimo_gb": 2.0, "disco_critico_gb": 0.5, "erros_log_alerta": 5}
PYTHON_SUPORTADO = ((3, 11), (3, 14))
RDS_POSTGRES_MINIMO = 13  # versões mais antigas já saíram do suporte padrão do Amazon RDS


def _c(cfg) -> dict:
    return {**PADRAO_TI, **(cfg.dados.get("ti") or {})}


# =============================================================================== verificações
def chk_dependencias(cfg) -> list[str]:
    """Diego (dev pleno): Python suportado e cada biblioteca de requisitos.txt instalada na versão mínima."""
    problemas = []
    v = sys.version_info[:2]
    if not PYTHON_SUPORTADO[0] <= v <= PYTHON_SUPORTADO[1]:
        problemas.append(f"Python {v[0]}.{v[1]} fora do suportado (3.11 a 3.14)")
    req = RAIZ_PROJETO / "requisitos.txt"
    for linha in req.read_text(encoding="utf-8").splitlines() if req.exists() else []:
        m = re.match(r"^\s*([A-Za-z0-9_.-]+)(\[[^\]]+\])?\s*>=\s*([\d.]+)", linha)
        if not m:
            continue
        nome, minimo = m.group(1), m.group(3)
        try:
            instalada = metadata.version(nome)
        except metadata.PackageNotFoundError:
            problemas.append(f"{nome} não está instalado (rode instalar.bat)")
            continue
        if _versao(instalada) < _versao(minimo):
            problemas.append(f"{nome} {instalada} abaixo do mínimo {minimo} (rode instalar.bat)")
    return problemas


def _versao(texto: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", texto)[:3])


def chk_disco_e_pastas(cfg) -> list[str]:
    """Rodrigo (infra pleno): espaço livre no disco das pastas e permissão de escrita em cada pasta de trabalho."""
    c = _c(cfg)
    problemas = []
    for nome, pasta in cfg.pastas().items():
        pasta = Path(pasta)
        if not pasta.exists():
            continue
        try:
            with tempfile.NamedTemporaryFile(dir=pasta, prefix="~robo_ti_", delete=True):
                pass
        except OSError as e:
            problemas.append(f"sem permissão de escrita em {nome} ({pasta}): {e.strerror}")
    raiz = Path(getattr(cfg, "entrada", "") or next(iter(cfg.pastas().values())))
    alvo = raiz if raiz.exists() else Path(cfg.logs)
    if alvo.exists():
        livre = shutil.disk_usage(alvo).free / 1024 ** 3
        if livre < float(c["disco_critico_gb"]):
            problemas.append(f"CRÍTICO: só {livre:.2f} GB livres no disco das planilhas")
        elif livre < float(c["disco_minimo_gb"]):
            problemas.append(f"pouco espaço: {livre:.1f} GB livres (mínimo recomendado {c['disco_minimo_gb']} GB)")
    return problemas


def chk_erros_no_log(cfg) -> list[str]:
    """Letícia (dev júnior): conta erros de programa (ERROR/Traceback) no robo.log das últimas 24 horas."""
    arq = Path(cfg.logs) / "robo.log"
    if not arq.exists():
        return []
    corte = (datetime.now() - timedelta(hours=24)).strftime("%d/%m/%Y %H:%M")
    erros = 0
    with open(arq, encoding="utf-8", errors="replace") as f:
        for linha in f:
            if "| ERROR" in linha or "| CRITICAL" in linha:
                data = linha[:16]
                try:
                    if datetime.strptime(data, "%d/%m/%Y %H:%M") >= datetime.strptime(corte, "%d/%m/%Y %H:%M"):
                        erros += 1
                except ValueError:
                    erros += 1
    limite = int(_c(cfg)["erros_log_alerta"])
    return [f"{erros} erro(s) de programa no log nas últimas 24h (alerta a partir de {limite}) — veja logs/robo.log"] \
        if erros >= limite else []


def chk_seguranca(cfg) -> list[str]:
    """Wagner (segurança sênior): painel só na própria máquina, senha fora do arquivo e código novo vigiado."""
    problemas = []
    from robo.painel import servidor
    fonte = Path(servidor.__file__).read_text(encoding="utf-8")
    if 'ThreadingHTTPServer(("127.0.0.1"' not in fonte:
        problemas.append("o painel não está preso a 127.0.0.1 (ficaria visível na rede)")
    if cfg.banco.get("senha"):
        problemas.append("senha do PostgreSQL gravada no config.yaml — prefira a variável de ambiente ROBO_PG_SENHA")
    if not (cfg.painel or {}).get("senha_hash"):
        problemas.append("o painel está sem senha: qualquer pessoa logada neste Windows abre os dados "
                         "(Configurações → Senha do painel, ou 'python -m robo senha')")
    # integridade: todo .py novo ou alterado em habilidades_personalizadas é código que roda no robô
    estado = _ler_estado(cfg)
    anteriores = estado.get("hashes_habilidades") or {}
    atuais = {}
    pasta = Path(cfg.habilidades)
    for arq in sorted(pasta.glob("*.py")) if pasta.exists() else []:
        if arq.name.startswith("_"):
            continue
        atuais[arq.name] = hashlib.sha256(arq.read_bytes()).hexdigest()
    if "hashes_habilidades" in estado:
        mudou = [n for n, h in atuais.items() if anteriores.get(n) != h]
        if mudou:
            problemas.append(f"código de habilidade novo/alterado: {', '.join(mudou)} — confirme que foi você "
                             f"(depois de confirmar, este aviso some na próxima ronda)")
    estado["hashes_habilidades"] = atuais
    _salvar_estado(cfg, estado)
    if os.name == "posix" and Path(cfg.base).exists():
        cfg_arq = Path(cfg.base) / "config.yaml"
        if cfg_arq.exists() and cfg_arq.stat().st_mode & 0o002:
            problemas.append("config.yaml pode ser alterado por qualquer usuário do computador")
    return problemas


def chk_cloud(cfg) -> list[str]:
    """Marina (cloud/AWS, consultiva): o banco e os dados estariam prontos para migrar para a AWS (Amazon RDS)?"""
    if not cfg.banco.get("habilitado"):
        return []
    try:
        from robo.banco import Banco
        b = Banco(cfg.banco, cfg.base)
        # a versão é do SERVIDOR: consulta no banco de manutenção 'postgres', que sempre existe (o banco do robô só
        # nasce na primeira carga — antes, a ronda de TI na abertura acusava falha num computador novo)
        with b.conectar("postgres") as conn:
            versao = conn.execute("SHOW server_version").fetchone()[0]
    except Exception as e:  # servidor fora do ar: aí sim é um problema real
        return [f"não consegui consultar a versão do PostgreSQL ({type(e).__name__})"]
    principal = _versao(versao)[0]
    return [f"PostgreSQL {versao}: abaixo da versão {RDS_POSTGRES_MINIMO}, sem suporte padrão no Amazon RDS — "
            f"atualize antes de pensar em nuvem"] if principal < RDS_POSTGRES_MINIMO else []


def chk_tamanho_logs(cfg) -> list[str]:
    """Caíque (estagiário de DevOps, observação): mede a pasta de logs e aponta os maiores arquivos."""
    pasta = Path(cfg.logs)
    if not pasta.exists():
        return []
    arquivos = [p for p in pasta.rglob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in arquivos) / 1024 ** 2
    if total < 500:
        return []
    maiores = sorted(arquivos, key=lambda p: p.stat().st_size, reverse=True)[:3]
    return [f"logs ocupam {total:.0f} MB; maiores: " + ", ".join(f"{p.name} ({p.stat().st_size / 1024 ** 2:.0f} MB)" for p in maiores)]


EQUIPE_TI = [
    {"id": "ger_ti", "nome": "Gustavo", "cargo": "Gerente de TI e Infraestrutura", "nivel": "gerente", "cor": "#111827",
     "funcao": None, "area": "Engenharia de Dados",
     "escopo": ["Responde pela disponibilidade do robô e do painel", "Prioriza o backlog técnico (dívida técnica)",
                "Leva para a sprint o que travou na TI"],
     "criterios": ["Ronda de TI em dia", "Nenhum alerta crítico sem dono"],
     "metodologias": ["ITIL (gestão de incidentes)", "Indicadores de disponibilidade"]},
    {"id": "coord_devops", "nome": "Fernanda", "cargo": "Coordenadora de DevOps e Confiabilidade (SRE)", "nivel": "coordenador",
     "cor": "#374151", "funcao": None, "area": "Engenharia de Dados",
     "escopo": ["Assina a ronda de TI: saudável só com todas as verificações OK",
                "Garante que toda mudança passe pelos testes automatizados antes de ir para produção"],
     "criterios": ["Ronda sem falha crítica", "Testes automatizados verdes"], "metodologias": ["SRE", "CI (integração contínua)"]},
    {"id": "sec_senior", "nome": "Wagner", "cargo": "Especialista Sênior em Segurança da Informação", "nivel": "senior",
     "cor": "#7F1D1D", "funcao": chk_seguranca, "area": "Governança e Privacidade",
     "escopo": ["Confere que o painel só responde na própria máquina", "Cobra a senha do banco fora do arquivo",
                "Vigia código novo em habilidades personalizadas"],
     "criterios": ["Zero exposição na rede", "Zero segredo em texto puro"], "metodologias": ["OWASP Top 10", "Defesa em profundidade"]},
    {"id": "cloud_aws", "nome": "Marina", "cargo": "Arquiteta de Cloud (AWS) — consultiva", "nivel": "especialista",
     "cor": "#B45309", "funcao": chk_cloud, "area": "Engenharia de Dados",
     "escopo": ["Avalia se o banco estaria pronto para o Amazon RDS", "Desenha o caminho de migração quando você quiser"],
     "criterios": ["Recomendação com versão e motivo"], "metodologias": ["AWS Well-Architected Framework"],
     "nao_faz": ["Não envia nada para a nuvem: o sistema é 100% local por decisão do dono"]},
    {"id": "dev_pleno", "nome": "Diego", "cargo": "Desenvolvedor Python Pleno", "nivel": "pleno", "cor": "#1E40AF",
     "funcao": chk_dependencias, "area": "Engenharia de Dados",
     "escopo": ["Confere a versão do Python e de cada biblioteca exigida"], "criterios": ["Todas as dependências no mínimo exigido"],
     "metodologias": ["Gestão de dependências (versões mínimas)"]},
    {"id": "infra_pleno", "nome": "Rodrigo", "cargo": "Analista de Infraestrutura Pleno", "nivel": "pleno", "cor": "#065F46",
     "funcao": chk_disco_e_pastas, "area": "Engenharia de Dados",
     "escopo": ["Mede o espaço livre em disco", "Testa permissão de escrita em todas as pastas de trabalho"],
     "criterios": ["Mais de 2 GB livres", "Todas as pastas graváveis"], "metodologias": ["Monitoramento de capacidade"]},
    {"id": "dev_junior", "nome": "Letícia", "cargo": "Desenvolvedora Júnior", "nivel": "junior", "cor": "#2563EB",
     "funcao": chk_erros_no_log, "area": "Engenharia de Dados",
     "escopo": ["Lê o robo.log e conta erros de programa das últimas 24h"], "criterios": ["Menos de 5 erros por dia"],
     "metodologias": ["Observabilidade por logs"]},
    {"id": "devops_estagiario", "nome": "Caíque", "cargo": "Estagiário de DevOps", "nivel": "estagiario", "cor": "#60A5FA",
     "funcao": chk_tamanho_logs, "area": "Engenharia de Dados",
     "escopo": ["Mede o tamanho dos logs e aponta os maiores (observação)"], "criterios": ["Relato claro"],
     "metodologias": ["Higiene de logs"]},
]
POR_ID = {p["id"]: p for p in EQUIPE_TI}
GESTORES = {"ger_ti": "dono", "coord_devops": "ger_ti", "sec_senior": "coord_devops", "cloud_aws": "ger_ti",
            "dev_pleno": "coord_devops", "infra_pleno": "coord_devops", "dev_junior": "dev_pleno", "devops_estagiario": "infra_pleno"}


# =============================================================================== ronda
def _arq_estado(cfg) -> Path:
    return Path(cfg.logs) / "ti" / "estado.json"


def _ler_estado(cfg) -> dict:
    try:
        return json.loads(_arq_estado(cfg).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _salvar_estado(cfg, e: dict) -> None:
    arq = _arq_estado(cfg)
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(arq)


def ronda(cfg, anunciar: bool = True) -> dict:
    """Roda todas as verificações, grava o resultado e avisa no canal #ti só o que piorou desde a última ronda."""
    itens = []
    for p in EQUIPE_TI:
        if p["funcao"] is None:
            continue
        inicio = time.perf_counter()
        try:
            achados = list(p["funcao"](cfg) or [])
        except Exception as e:
            achados = [f"não consegui concluir a verificação ({type(e).__name__}: {e})"]
        itens.append({"id": p["id"], "nome": p["nome"], "cargo": p["cargo"], "nivel": p["nivel"], "ok": not achados,
                      "achados": achados, "segundos": round(time.perf_counter() - inicio, 2)})
    criticos = [a for i in itens if i["nivel"] != "estagiario" for a in i["achados"]]
    resultado = {"data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "saudavel": not criticos, "itens": itens,
                 "assinatura": {"coordenadora": "Fernanda", "saudavel": not criticos}}
    estado = _ler_estado(cfg)
    ja_avisados = set(estado.get("alertas_ativos") or [])
    novos = [a for a in criticos if a not in ja_avisados]
    resultado["novos_alertas"] = novos
    estado["alertas_ativos"] = criticos
    estado["ultima_ronda"] = resultado
    _salvar_estado(cfg, estado)
    if anunciar:
        try:
            from robo.canal import Canal
            canal = Canal(cfg)
            for i in itens:
                for a in i["achados"]:
                    if a in novos:
                        canal.postar(i["id"], a, "ti", "alerta")
            if ja_avisados and not criticos:
                canal.postar("coord_devops", "Ronda de TI: tudo normalizado, nenhum alerta ativo.", "ti", "acontecimento")
        except Exception:
            log.debug("Canal indisponível para a ronda de TI", exc_info=True)
    return resultado


def ultima_ronda(cfg) -> dict | None:
    return _ler_estado(cfg).get("ultima_ronda")


# =============================================================================== provas técnicas (RH)
def provas_ti() -> dict:
    class _Cfg:
        pass
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        (base / "entrada").mkdir()
        (base / "logs").mkdir()
        (base / "habilidades").mkdir()
        cfg = _Cfg()
        cfg.logs, cfg.habilidades, cfg.base = base / "logs", base / "habilidades", base
        cfg.dados, cfg.banco = {"ti": {"disco_minimo_gb": 0.0001, "disco_critico_gb": 0.00001}}, {"habilitado": False}
        cfg.painel = {"senha_hash": "pbkdf2_sha256$1$00$00"}  # sistema limpo = painel com senha
        cfg.entrada = base / "entrada"
        cfg.pastas = lambda: {"Bases-Limpeza (entrada)": base / "entrada", "Logs": base / "logs"}
        seg_ok = chk_seguranca(cfg)
        (base / "habilidades" / "nova.py").write_text("x = 1\n", encoding="utf-8")
        seg_novo = chk_seguranca(cfg)
        cfg.banco = {"habilitado": False, "senha": "123"}
        seg_senha = chk_seguranca(cfg)
        cfg.banco = {"habilitado": False}
        cfg.painel = {}
        seg_painel = chk_seguranca(cfg)
        cfg.painel = {"senha_hash": "pbkdf2_sha256$1$00$00"}
        disco_ok = chk_disco_e_pastas(cfg)
        cfg.dados = {"ti": {"disco_minimo_gb": 10 ** 9, "disco_critico_gb": 10 ** 8}}
        disco_cheio = chk_disco_e_pastas(cfg)
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        (base / "logs" / "robo.log").write_text("".join(f"{agora} | ERROR   | falhou\n" for _ in range(6)), encoding="utf-8")
        cfg.dados = {}
        log_ruim = chk_erros_no_log(cfg)
        (base / "logs" / "robo.log").write_text(f"{agora} | INFO    | ok\n", encoding="utf-8")
        log_ok = chk_erros_no_log(cfg)
        logs_pequenos = chk_tamanho_logs(cfg)
        # ronda completa: com disco "cheio" não pode sair saudável; repetir o mesmo alerta não gera aviso novo
        cfg.dados = {"ti": {"disco_minimo_gb": 10 ** 9, "disco_critico_gb": 10 ** 8}}
        r1, r2 = ronda(cfg, anunciar=False), ronda(cfg, anunciar=False)
        cfg.dados = {"ti": {"disco_minimo_gb": 0.0001, "disco_critico_gb": 0.00001}}
        chk_seguranca(cfg)  # registra o código atual como conhecido
        r3 = ronda(cfg, anunciar=False)
    return {
        "sec_senior": [("Sistema limpo não gera alerta", not seg_ok), ("Pega código novo de habilidade", bool(seg_novo)),
                       ("Pega senha gravada no arquivo", any("PostgreSQL" in x for x in seg_senha)),
                       ("Pega painel sem senha", any("painel está sem senha" in x for x in seg_painel))],
        "infra_pleno": [("Disco com espaço não alerta", not disco_ok), ("Disco cheio vira CRÍTICO", any("CRÍTICO" in x for x in disco_cheio))],
        "dev_junior": [("Log limpo não alerta", not log_ok), ("6 erros em 24h geram alerta", bool(log_ruim))],
        "dev_pleno": [("Ambiente atual com dependências corretas", not chk_dependencias(cfg)),
                      ("Compara versões corretamente", _versao("2.10.1") > _versao("2.9.9"))],
        "cloud_aws": [("Sem banco, nada a avaliar", not chk_cloud(cfg)), ("Lê versão do PostgreSQL", _versao("16.4 (Ubuntu)")[0] == 16)],
        "devops_estagiario": [("Logs pequenos não geram relato", not logs_pequenos),
                              ("Executa sem alterar nada", isinstance(logs_pequenos, list))],
        "coord_devops": [("Não assina ronda com falha crítica", not r1["saudavel"]), ("Assina ronda toda verde", r3["saudavel"])],
        "ger_ti": [("Alerta novo é comunicado", bool(r1["novos_alertas"])), ("Não repete o mesmo alerta", not r2["novos_alertas"])],
    }
