"""Orquestração das rotinas (equipe de Airflow do 5º andar).

O robô já tem o próprio agendador (o laço do painel). Esta equipe cuida de três coisas reais:

  1. FLUXOS — a mesma ordem e frequência das rotinas, escrita uma vez só e usada pelo robô E pelo Airflow
     (a DAG é gerada daqui; ninguém mantém duas listas);
  2. DAG do Apache Airflow — `python -m robo airflow-dag` gera airflow/dags/robo_empresa.py. Cada tarefa chama
     `python -m robo rotina <nome>`: código de saída 0 = fez/em dia, 1 = erro (o Airflow tenta de novo), 99 = já está
     rodando em outro programa (o Airflow marca como pulada). O robô e o Airflow nunca rodam a mesma rotina juntos
     (trava de arquivo do sistema operacional em robo/rotinas.py);
  3. SLA — confere, com os registros de rotinas_execucoes/rotinas_estado, o que está atrasado, o que terminou em erro e
     o que ficou lento. Isso roda na ronda de TI e é a ferramenta "orquestracao" do treino.

No Windows o Airflow não roda direto: precisa do WSL2 (Linux dentro do Windows) ou Docker. É opcional — com
`rotinas: {agendador: airflow}` no config.yaml o robô deixa as rotinas para o Airflow (o canal continua no robô).
"""

from __future__ import annotations

import hashlib
import json
import shlex
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

from robo.rotinas import ROTINAS

# Rotina que fica sempre no robô: posta no canal a cada minuto (o Airflow não é feito para agendar de minuto em minuto)
APENAS_NO_ROBO = {"canal", "registro"}  # de minuto em minuto: ficam no robô

FLUXOS = {
    "robo_horario": {"descricao": "Rotinas de gestão em sequência: cada uma decide se está na hora (backup diário, "
                                  "reunião semanal…)", "cron": "0 * * * *", "a_cada_min": 60, "limite_min": 120,
                     "rotinas": ["estrategia", "backup", "pdca", "licoes", "estudo", "auditoria", "reuniao",
                                 "rh_desempenho", "alcadas", "ideias", "paineis", "caixa_dono",
                                 "jornada", "modelos"]},
    "robo_memoria": {"descricao": "Cópia incremental de toda a memória para o PostgreSQL", "cron": "*/10 * * * *",
                     "a_cada_min": 10, "limite_min": 15, "rotinas": ["memoria_pg"]},
    "robo_treino": {"descricao": "Treino contínuo de todos os funcionários", "cron": "*/5 * * * *", "a_cada_min": 5,
                    "limite_min": 20, "rotinas": ["treino"]},
    "robo_laboratorio": {"descricao": "Laboratório de planilhas sintéticas", "cron": "*/10 * * * *", "a_cada_min": 10,
                         "limite_min": 30, "rotinas": ["laboratorio"]},
    "robo_ronda_ti": {"descricao": "Ronda de TI (saúde do computador, segurança e SLA das rotinas)", "cron": "*/30 * * * *",
                      "a_cada_min": 30, "limite_min": 15, "rotinas": ["ronda_ti"]},
    "robo_demandas": {"descricao": "Demandas para os funcionários: trabalho real com ferramenta, critérios e revisão",
                      "cron": "*/30 * * * *", "a_cada_min": 30, "limite_min": 25, "rotinas": ["demandas"]},
    "robo_dialogo": {"descricao": "Conversas entre funcionários quando há fato e necessidade (e conferência dos compromissos)",
                     "cron": "*/20 * * * *", "a_cada_min": 20, "limite_min": 15, "rotinas": ["dialogo"]},
    "robo_fabrica": {"descricao": "Fábrica de Planilhas: lote sintético na esteira (só com a fila real vazia) e conferência "
                                  "do resultado contra o gabarito", "cron": "*/30 * * * *", "a_cada_min": 30,
                     "limite_min": 25, "rotinas": ["fabrica"]},
    "robo_telegram": {"descricao": "Grupo do Telegram: responde o dono e manda o resumo do período (desligado sem token)",
                      "cron": "*/1 * * * *", "a_cada_min": 1, "limite_min": 2, "rotinas": ["telegram"]},
}

# Regras de SLA (as mesmas no robô, no treino e na documentação)
FOLGA_ATRASO = 1.5            # atrasada = sem verificação há mais de 1,5 × o intervalo da rotina
CARENCIA_ABERTURA_MIN = 20    # nos primeiros 20 min depois de abrir o notebook o robô está colocando tudo em dia
LENTA_MIN_HISTORICO = 5       # só dá para dizer "lenta" com pelo menos 5 execuções anteriores
LENTA_FATOR, LENTA_FOLGA_SEG = 3.0, 60.0  # lenta = mais que 3 × a mediana E mais que a mediana + 60 s


# =============================================================================== fluxos
def validar_fluxos(fluxos: dict | None = None, rotinas: dict | None = None) -> list[str]:
    """Problemas de desenho dos fluxos (lista vazia = ok): rotina sem fluxo, rotina repetida, rotina que não existe,
    frequência do fluxo mais lenta que o intervalo da rotina (deixaria a rotina atrasada), cron incoerente."""
    fluxos = FLUXOS if fluxos is None else fluxos
    rotinas = ROTINAS if rotinas is None else rotinas
    problemas, vistos = [], {}
    for dag, f in fluxos.items():
        if not f.get("rotinas"):
            problemas.append(f"fluxo {dag} sem nenhuma rotina")
        minutos = int(f.get("a_cada_min") or 0)
        cron_esperado = "0 * * * *" if minutos == 60 else f"*/{minutos} * * * *"
        if minutos <= 0 or (minutos != 60 and 60 % minutos):
            problemas.append(f"fluxo {dag}: 'a cada {minutos} min' não cabe num cron de minutos (use 60 ou um divisor de 60)")
        elif f.get("cron") != cron_esperado:
            problemas.append(f"fluxo {dag}: cron '{f.get('cron')}' não bate com 'a cada {minutos} min' ({cron_esperado})")
        for nome in f.get("rotinas") or []:
            if nome not in rotinas:
                problemas.append(f"fluxo {dag}: rotina {nome} não existe em robo/rotinas.py")
                continue
            if nome in vistos:
                problemas.append(f"rotina {nome} está em dois fluxos ({vistos[nome]} e {dag})")
            vistos[nome] = dag
            intervalo_min = float(rotinas[nome][2]) * 60
            if minutos > intervalo_min + 1e-9:
                problemas.append(f"rotina {nome} precisa de verificação a cada {intervalo_min:g} min, mas o fluxo {dag} "
                                 f"roda a cada {minutos} min — ela ficaria atrasada")
    for nome in rotinas:
        if nome not in vistos and nome not in APENAS_NO_ROBO:
            problemas.append(f"rotina {nome} não está em nenhum fluxo (nem o robô nem o Airflow a rodariam em ordem)")
    return problemas


def assinatura(comando: str = "") -> str:
    """Impressão digital do desenho: muda se mudar fluxo, rotina, intervalo ou comando. Vai no cabeçalho da DAG."""
    base = {"fluxos": FLUXOS, "rotinas": {k: v[2] for k, v in ROTINAS.items()}, "comando": comando}
    return hashlib.sha256(json.dumps(base, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def caminho_wsl(caminho: str) -> str:
    """C:\\Users\\voce\\Robo-data → /mnt/c/Users/voce/Robo-data (como o Airflow, dentro do WSL, enxerga o Windows)."""
    c = str(caminho).replace("\\", "/")
    if len(c) >= 2 and c[1] == ":":
        return f"/mnt/{c[0].lower()}{c[2:]}"
    return c


def destino_padrao(cfg) -> Path:
    """rotinas.dag_airflow no config.yaml, ou airflow/dags/robo_empresa.py na pasta do projeto (fora do git: tem
    os caminhos deste computador)."""
    escolhido = (cfg.dados.get("rotinas") or {}).get("dag_airflow")
    if escolhido:
        p = Path(escolhido)
        return p if p.is_absolute() else Path(cfg.base) / p
    return Path(cfg.base) / "airflow" / "dags" / "robo_empresa.py"


_MODELO_DAG = '''"""DAG GERADA AUTOMATICAMENTE pelo Robô de Planilhas — NÃO EDITE À MÃO (rode: python -m robo airflow-dag).

Responsável: equipe de Orquestração (5º andar). Fonte única: robo/orquestracao.py (FLUXOS) e robo/rotinas.py.
Cada tarefa chama `python -m robo rotina <nome>`: saída 0 = fez/em dia; 1 = erro (o Airflow tenta de novo);
99 = a rotina já está rodando no robô (o Airflow marca como pulada — nunca roda em dobro).
Gerada em {gerada_em}.
"""
from datetime import datetime, timedelta

try:  # Airflow 3
    from airflow.sdk import DAG
except ImportError:  # Airflow 2.4+
    from airflow import DAG
try:
    from airflow.providers.standard.operators.bash import BashOperator
except ImportError:
    from airflow.operators.bash import BashOperator

ASSINATURA = "{assinatura}"
COMANDO = {comando!r}
FLUXOS = {fluxos}
PADRAO = {{"owner": "robo_planilhas", "retries": 2, "retry_delay": timedelta(minutes=5)}}

for _dag_id, _f in FLUXOS.items():
    with DAG(dag_id=_dag_id, description=_f["descricao"], schedule=_f["cron"], start_date=datetime(2026, 1, 1),
             catchup=False, max_active_runs=1, default_args=PADRAO, tags=["robo_planilhas"]) as _dag:
        _anterior = None
        for _nome in _f["rotinas"]:
            _t = BashOperator(task_id=_nome, bash_command=f"{{COMANDO}} {{_nome}}",
                              execution_timeout=timedelta(minutes=_f["limite_min"]))
            if _anterior is not None:
                _anterior >> _t
            _anterior = _t
    globals()[_dag_id] = _dag
'''


def comando_rotina(projeto: Path | str, python: str, wsl: bool, caminho_config: Path | str | None = None) -> str:
    """O python do Windows (python.exe) é chamado de dentro do WSL; o caminho do config vai no formato do Windows,
    porque é o python do Windows que vai abri-lo."""
    proj, py = (caminho_wsl(projeto), caminho_wsl(python)) if wsl else (str(projeto), str(python))
    cfg_txt = f" --config {shlex.quote(str(caminho_config))}" if caminho_config else ""
    return f"cd {shlex.quote(proj)} && {shlex.quote(py)} -m robo{cfg_txt} rotina"


def gerar_dag(cfg, destino: Path | None = None, python: str | None = None, projeto: Path | None = None,
              wsl: bool | None = None, caminho_config: Path | str | None = None) -> dict:
    """Escreve a DAG do Airflow a partir dos FLUXOS. Recusa gerar se o desenho tiver problema."""
    import os
    from robo.config import RAIZ_PROJETO
    problemas = validar_fluxos()
    if problemas:
        raise ValueError("Fluxos com problema; a DAG não foi gerada: " + "; ".join(problemas))
    wsl = (os.name == "nt") if wsl is None else wsl
    comando = comando_rotina(projeto or RAIZ_PROJETO, python or sys.executable, wsl, caminho_config)
    destino = Path(destino) if destino else destino_padrao(cfg)
    destino.parent.mkdir(parents=True, exist_ok=True)
    ass = assinatura(comando)
    texto = _MODELO_DAG.format(gerada_em=datetime.now().strftime("%d/%m/%Y %H:%M"), assinatura=ass, comando=comando,
                               fluxos=json.dumps(FLUXOS, ensure_ascii=False, indent=4))
    compile(texto, str(destino), "exec")  # nunca grava DAG com erro de sintaxe
    tmp = destino.with_suffix(".tmp")
    tmp.write_text(texto, encoding="utf-8")
    tmp.replace(destino)
    return {"arquivo": str(destino), "assinatura": ass, "comando": comando, "wsl": wsl,
            "dags": {k: {"cron": v["cron"], "tarefas": v["rotinas"]} for k, v in FLUXOS.items()}}


def assinatura_no_arquivo(arquivo: Path) -> tuple[str, str] | None:
    try:
        texto = Path(arquivo).read_text(encoding="utf-8")
    except OSError:
        return None
    ass = com = None
    for linha in texto.splitlines():
        if linha.startswith("ASSINATURA = "):
            ass = linha.split("=", 1)[1].strip().strip('"')
        elif linha.startswith("COMANDO = "):
            import ast
            com = ast.literal_eval(linha.split("=", 1)[1].strip())
    return (ass, com) if ass and com is not None else None


# =============================================================================== SLA das rotinas
def _dt(texto):
    try:
        return datetime.fromisoformat(str(texto)) if texto else None
    except ValueError:
        return None


def analisar_sla(cfg, agora: datetime | None = None, rotinas: dict | None = None) -> dict:
    """Lê rotinas_estado, rotinas_execucoes e sessoes (registros reais) e aponta, por rotina:
      atrasada  — sem verificação há mais de 1,5 × o intervalo (fora dos 20 min de carência depois de abrir o notebook);
      com_erro  — a ÚLTIMA execução terminou em erro (erro antigo seguido de sucesso não conta, mas aparece no histórico);
      lenta     — a última execução levou mais que 3 × a mediana das 20 anteriores E mais que a mediana + 60 s
                  (só com 5 ou mais execuções anteriores)."""
    from robo import rotinas as mod
    rotinas = ROTINAS if rotinas is None else rotinas
    agora = agora or datetime.now()
    tb = mod._tb(cfg)
    with tb.tx() as c:
        estado = {r["nome"]: dict(r) for r in c.execute("SELECT * FROM rotinas_estado")}
        sessao = c.execute("SELECT aberto_em FROM sessoes ORDER BY id DESC LIMIT 1").fetchone()
        execs = {}
        for nome in rotinas:
            execs[nome] = [dict(r) for r in c.execute(
                "SELECT inicio, fim, segundos, status FROM rotinas_execucoes WHERE nome=? AND status IN ('fez','erro') "
                "ORDER BY id DESC LIMIT 21", (nome,))]
        desde = (agora - timedelta(hours=24)).isoformat(timespec="seconds")
        falhas_24h = {r["nome"]: r["n"] for r in c.execute(
            "SELECT nome, count(*) AS n FROM rotinas_execucoes WHERE status='erro' AND inicio>=? GROUP BY nome", (desde,))}
    aberto = _dt(sessao["aberto_em"]) if sessao else None
    # sem nenhuma sessão registrada o robô nunca foi aberto: não há contra o que medir atraso
    carencia = aberto is None or agora - aberto < timedelta(minutes=CARENCIA_ABERTURA_MIN)
    atrasadas, com_erro, lentas, detalhes = [], [], [], {}
    for nome, (resp, _desc, horas) in rotinas.items():
        e = estado.get(nome) or {}
        ref = _dt(e.get("ultima_verificacao")) or _dt(e.get("ultima_execucao"))
        limite = timedelta(hours=float(horas) * FOLGA_ATRASO)
        if not carencia and (ref is None or agora - ref > limite):
            atrasadas.append(nome)
            detalhes.setdefault(nome, []).append(
                "nunca verificada" if ref is None else f"última verificação há {_duracao(agora - ref)} (limite {_duracao(limite)})")
        ult = execs[nome][0] if execs[nome] else None
        if ult and ult["status"] == "erro":
            com_erro.append(nome)
            detalhes.setdefault(nome, []).append(f"a última execução ({str(ult['inicio'])[:16]}) terminou em erro")
        feitas = [x for x in execs[nome] if x["status"] == "fez" and x["segundos"] is not None]
        if ult and ult["status"] == "fez" and len(feitas) > LENTA_MIN_HISTORICO:
            atual, anteriores = float(feitas[0]["segundos"]), [float(x["segundos"]) for x in feitas[1:21]]
            med = statistics.median(anteriores)
            if atual > LENTA_FATOR * med and atual > med + LENTA_FOLGA_SEG:
                lentas.append(nome)
                detalhes.setdefault(nome, []).append(f"levou {atual:.0f} s; o normal é {med:.0f} s")
    return {"data_hora": agora.isoformat(timespec="seconds"), "carencia_abertura": carencia,
            "atrasadas": atrasadas, "com_erro": com_erro, "lentas": lentas, "falhas_24h": falhas_24h,
            "detalhes": detalhes, "responsaveis": {n: rotinas[n][0] for n in set(atrasadas + com_erro + lentas)},
            "ok": not (atrasadas or com_erro or lentas)}


def gravar_cenario(cfg, cenario: dict, agora: datetime | None = None) -> None:
    """Escreve um cenário de execuções num computador de TESTE (provas do RH e treino). Recusa um banco que já tenha
    execuções registradas — assim nunca mistura dado sintético com a produção.
    cenario = {"sessao_min_atras": 600,
               "estado": [{"nome", "verif_min_atras", "ultimo_status"}],
               "execucoes": [{"nome", "fim_min_atras", "segundos", "status"}]}"""
    from robo import rotinas as mod
    agora = agora or datetime.now()
    iso = lambda minutos: (agora - timedelta(minutes=float(minutos))).isoformat(timespec="seconds")  # noqa: E731
    tb = mod._tb(cfg)
    with tb.tx() as c:
        if c.execute("SELECT count(*) FROM rotinas_execucoes").fetchone()[0] or c.execute("SELECT count(*) FROM sessoes").fetchone()[0]:
            raise RuntimeError("este banco já tem execuções registradas: cenário sintético só em computador de teste")
        c.execute("INSERT INTO sessoes (aberto_em, ultimo_batimento, desligado_antes_horas, briefing) VALUES (?,?,?,?)",
                  (iso(cenario["sessao_min_atras"]), iso(0), None, "computador de teste"))
        for e in sorted(cenario["execucoes"], key=lambda x: -float(x["fim_min_atras"])):  # mais antiga primeiro (id cresce)
            fim = float(e["fim_min_atras"])
            c.execute("INSERT INTO rotinas_execucoes (nome, inicio, fim, segundos, status, detalhe) VALUES (?,?,?,?,?,?)",
                      (e["nome"], iso(fim + float(e["segundos"]) / 60), iso(fim), float(e["segundos"]), e["status"],
                       "falha simulada" if e["status"] == "erro" else ""))
        for e in cenario["estado"]:
            c.execute("INSERT INTO rotinas_estado (nome, ultima_verificacao, ultima_execucao, ultimo_status, detalhe) "
                      "VALUES (?,?,?,?,?)", (e["nome"], iso(e["verif_min_atras"]), iso(e["verif_min_atras"]),
                                             e["ultimo_status"], ""))


def _duracao(d: timedelta) -> str:
    m = d.total_seconds() / 60
    if m < 90:
        return f"{m:.0f} min"
    if m < 48 * 60:
        return f"{m / 60:.1f} h".replace(".", ",")
    return f"{m / 1440:.1f} dias".replace(".", ",")


def texto_sla(r: dict) -> str:
    if r["ok"]:
        extra = " (carência de abertura: colocando em dia)" if r["carencia_abertura"] else ""
        return f"SLA das rotinas: tudo em dia{extra}."
    partes = []
    for rotulo, chave in (("Atrasadas", "atrasadas"), ("Com erro", "com_erro"), ("Lentas", "lentas")):
        if r[chave]:
            partes.append(f"{rotulo}: " + ", ".join(r[chave]))
    linhas = [f"SLA das rotinas — {'; '.join(partes)}."]
    for nome, motivos in r["detalhes"].items():
        linhas.append(f"• {nome} ({r['responsaveis'].get(nome, '?')}): " + "; ".join(motivos))
    return "\n".join(linhas)
