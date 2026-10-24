"""Inteligência própria: modelos de Machine Learning treinados com os registros da empresa, com ciclo de vida completo.

    python -m robo modelos            mostra o catálogo (datasets, experimentos, modelos, eventos)

O que isto É e o que NÃO é (para nunca confundir):
  - É treinamento de modelo de verdade: os parâmetros saem dos dados de treino, a escolha do ajuste usa a validação e a
    nota final vem de um teste que o modelo nunca viu. O artefato (pesos) é um arquivo versionado com checksum.
  - NÃO é a memória (lições, handovers) nem a IA de conversa (robo/ia.py): aquilo recupera e redige; isto aprende
    parâmetros. NÃO é um modelo de linguagem.
  - Sem biblioteca nova: regressão logística escrita em numpy (que já vem com o pandas). scikit-learn/PyTorch só
    entram quando um caso de uso provar que precisa (decisão registrada no catálogo).

1º caso de uso — risco de falha da demanda (finalidade "risco_demanda"):
  alvo        a demanda sintética NÃO termina concluída (parcial ou falhou), decidido pelos critérios de aceitação
              determinísticos + revisão independente (rótulo confiável; estudo por bloqueio fica de fora);
  atributos   só o que se sabe NA CRIAÇÃO da demanda: ferramenta, nível, andar, senioridade, nº de etapas e o histórico
              de falhas da pessoa e da ferramenta ATÉ aquele momento (nada do futuro: sem vazamento);
  corte       temporal: 70% mais antigos treinam, 15% seguintes validam, 15% mais novos testam;
  baseline    taxa de falha por ferramenta × nível no treino (suavizada);
  uso         SOMBRA: o modelo de referência só dá a probabilidade de cada demanda nova (ml_inferencias) e o
              monitoramento compara com o que aconteceu. Nenhuma decisão da empresa usa o modelo: uso operacional é
              decisão do dono (DECISAO_USO_OPERACIONAL).

Quem faz o quê (ninguém aprova o próprio trabalho):
  a equipe é a de EQUIPE_ML (robo/lideranca.py): líder define critérios e backlog; engenheiro de ML treina;
  avaliador (4º andar, independente) refaz as métricas a partir do arquivo e do dataset e aprova ou reprova;
  MLOps (5º andar) só promove o que foi aprovado por OUTRA pessoa, confere os checksums e faz rollback.
Tudo fica em tabelas só de inclusão (nada se apaga nem se altera); o estado de cada modelo é derivado dos eventos.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np

from robo.trabalho import Trabalho, _agora

FINALIDADE = "risco_demanda"
VERSAO_PIPELINE = "1"
EQUIPE_ML = {"lider": "ml_lider", "engenheiro": "ml_engenheiro", "mlops": "ml_mlops", "avaliador": "ml_avaliador"}
DECISAO_USO_OPERACIONAL = "desligado: o modelo só roda em sombra até o dono decidir usá-lo em alguma escolha da empresa"

# critérios do líder (iguais para todo candidato; mudar aqui é mudança de código, com teste)
CRITERIOS = {"min_linhas": 60, "min_teste": 20, "precisa_bater_baseline": True, "precisa_bater_referencia": True,
             "auc_minima": 0.55, "reprodutivel": True, "crescimento_para_retreino": 20,
             "monitor_min_fechadas": 30, "degradacao_tolerancia": 0.05}
LAMBDAS = (0.01, 0.1, 1.0)
ITERACOES = 1500
PASSO = 0.2
NIVEIS = {"basico": 0, "medio": 1, "dificil": 2, "profissional": 3}
SENIORIDADE = {"estagiario": 0, "junior": 1, "pleno": 2, "senior": 3, "especialista": 3, "coordenador": 4,
               "gerente": 5, "head": 6, "diretor": 6}

# backlog do líder: o que merece ML, com o estado REAL de cada item (só o 1º está implementado)
BACKLOG = [
    {"caso": "risco_demanda", "pergunta": "Esta demanda tem risco de não ser concluída?", "estado": "implementado (sombra)",
     "por_que_ml": "depende da combinação de ferramenta, nível, pessoa e histórico; regra fixa não acompanha"},
    {"caso": "proximo_treino", "pergunta": "Qual exercício mais reduz o erro desta pessoa?", "estado": "planejado",
     "por_que_ml": "precisa de antes/depois por intervenção; os registros de lições já guardam isso"},
    {"caso": "classe_de_erro", "pergunta": "De que tipo é este erro de esteira (texto)?", "estado": "planejado",
     "por_que_ml": "texto livre; começar por palavras-chave + regressão antes de qualquer rede neural"},
    {"caso": "atraso_rotina", "pergunta": "Esta rotina vai atrasar hoje?", "estado": "em espera",
     "por_que_ml": "poucos atrasos registrados até agora: uma regra (SLA) resolve melhor por enquanto"},
]

ESQUEMA = """
CREATE TABLE IF NOT EXISTS ml_datasets (
  id TEXT PRIMARY KEY, criado_em TEXT, finalidade TEXT, versao_pipeline TEXT, versao_codigo TEXT, linhas INTEGER,
  positivos INTEGER, inicio TEXT, fim TEXT, colunas TEXT, checksum TEXT, arquivo TEXT, origem TEXT, responsavel TEXT);
CREATE TABLE IF NOT EXISTS ml_experimentos (
  id TEXT PRIMARY KEY, criado_em TEXT, finalidade TEXT, dataset_id TEXT REFERENCES ml_datasets(id), versao_codigo TEXT,
  algoritmo TEXT, parametros TEXT, semente INTEGER, ambiente TEXT, metricas TEXT, segundos REAL, artefato TEXT,
  checksum TEXT, responsavel TEXT, estado TEXT);
CREATE TABLE IF NOT EXISTS ml_modelos (
  id TEXT PRIMARY KEY, criado_em TEXT, finalidade TEXT, versao INTEGER, experimento_id TEXT REFERENCES ml_experimentos(id),
  dataset_id TEXT, artefato TEXT, checksum TEXT, criado_por TEXT);
CREATE TABLE IF NOT EXISTS ml_modelos_eventos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, modelo_id TEXT REFERENCES ml_modelos(id), evento TEXT, quem TEXT,
  detalhe TEXT);
CREATE INDEX IF NOT EXISTS ix_ml_eventos_modelo ON ml_modelos_eventos(modelo_id, id);
CREATE TABLE IF NOT EXISTS ml_inferencias (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, modelo_id TEXT, solicitacao_id TEXT, probabilidade REAL,
  modo TEXT, UNIQUE(modelo_id, solicitacao_id));
"""
TABELAS = ("ml_datasets", "ml_experimentos", "ml_modelos", "ml_modelos_eventos", "ml_inferencias")


class ErroGovernanca(ValueError):
    """Tentativa de quebrar uma regra do ciclo (ex.: avaliar o próprio modelo, promover sem aprovação)."""


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    with tb.tx() as c:
        c.executescript(ESQUEMA)
        for t in TABELAS:  # registro permanente: nem apagar (proteger) nem alterar
            c.execute(f"CREATE TRIGGER IF NOT EXISTS {t}_sem_alterar BEFORE UPDATE ON {t} "
                      f"BEGIN SELECT RAISE(ABORT, 'registro permanente: {t} não se altera'); END")
        from robo.trabalho import proteger
        proteger(c)
    return tb


def _pasta(cfg) -> Path:
    p = Path(cfg.logs) / "ml"
    (p / "datasets").mkdir(parents=True, exist_ok=True)
    (p / "modelos").mkdir(parents=True, exist_ok=True)
    return p


def _sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _versao_codigo() -> str:
    try:
        from robo.treino import versao_codigo
        return versao_codigo()
    except Exception:
        return "desconhecida"


# =============================================================================== 1. dataset (engenharia de dados para ML)
def _linhas_rotuladas(cfg) -> list[dict]:
    """Uma linha por demanda sintética FECHADA, com atributos calculados só com o que existia na criação dela."""
    from robo import organizacao
    tb = _tb(cfg)
    with tb.tx() as c:
        brutas = c.execute("SELECT id, funcionario, andar, modelo, estado, plano, criada_em, atualizada_em FROM solicitacoes "
                           "WHERE origem='demanda_sintetica' AND estado IN ('concluida','concluida_parcialmente','falhou') "
                           "ORDER BY criada_em, id").fetchall()
    gente = organizacao.por_id(cfg)
    linhas = []
    for sid, pid, andar, modelo, estado, plano, criada, fechada in brutas:
        try:
            p = json.loads(plano or "{}")
        except ValueError:
            p = {}
        if p.get("tipo_demanda") == "treinamento":  # estudo por bloqueio não é a tarefa do papel: fica fora
            continue
        pessoa = gente.get(pid) or {}
        linhas.append({"id": sid, "funcionario": pid, "criada_em": criada, "fechada_em": fechada or criada,
                       "ferramenta": (modelo or "").split(":")[-1], "nivel": NIVEIS.get(p.get("nivel") or "basico", 0),
                       "andar": int(andar or pessoa.get("andar") or 0),
                       "senioridade": SENIORIDADE.get(organizacao.nivel_de(pid, pessoa) if pid else "pleno", 2),
                       "etapas": _n_etapas(p), "falhou": int(estado != "concluida")})
    # histórico até a criação: só demandas FECHADAS antes de esta nascer (o futuro nunca entra)
    fechadas = sorted(linhas, key=lambda x: x["fechada_em"])
    for l in linhas:
        antes = [x for x in fechadas if x["fechada_em"] < l["criada_em"] and x["id"] != l["id"]]
        da_pessoa = [x["falhou"] for x in antes if x["funcionario"] == l["funcionario"]]
        da_ferr = [x["falhou"] for x in antes if x["ferramenta"] == l["ferramenta"]]
        l["hist_pessoa_n"] = len(da_pessoa)
        l["hist_pessoa_taxa"] = (sum(da_pessoa) + 1) / (len(da_pessoa) + 2)   # suavizado (Laplace): sem histórico = 0,5
        l["hist_ferramenta_taxa"] = (sum(da_ferr) + 1) / (len(da_ferr) + 2)
    return linhas


def _n_etapas(plano: dict) -> int:
    """O plano gravado guarda o nº de etapas (inteiro); planos antigos podem guardar a lista."""
    e = plano.get("etapas")
    return max(1, int(e)) if isinstance(e, (int, float)) else max(1, len(e or []))


COLUNAS = ["id", "funcionario", "criada_em", "ferramenta", "nivel", "andar", "senioridade", "etapas", "hist_pessoa_n",
           "hist_pessoa_taxa", "hist_ferramenta_taxa", "falhou"]


def montar_dataset(cfg, quem: str = EQUIPE_ML["engenheiro"]) -> dict:
    """Dataset versionado: o id É o checksum do conteúdo (mesmos dados = mesmo dataset, nunca duplicado)."""
    linhas = _linhas_rotuladas(cfg)
    corpo = json.dumps([[l[k] for k in COLUNAS] for l in linhas], ensure_ascii=False, separators=(",", ":"))
    checksum = _sha(corpo)
    did = f"DS-{FINALIDADE}-{checksum[:12]}"
    tb = _tb(cfg)
    with tb.tx() as c:
        ja = c.execute("SELECT id FROM ml_datasets WHERE id=?", (did,)).fetchone()
        if not ja:
            arq = _pasta(cfg) / "datasets" / f"{did}.json"
            arq.write_text(json.dumps({"colunas": COLUNAS, "linhas": json.loads(corpo)}, ensure_ascii=False), encoding="utf-8")
            c.execute("INSERT INTO ml_datasets (id, criado_em, finalidade, versao_pipeline, versao_codigo, linhas, positivos, "
                      "inicio, fim, colunas, checksum, arquivo, origem, responsavel) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (did, _agora(), FINALIDADE, VERSAO_PIPELINE, _versao_codigo(), len(linhas),
                       sum(l["falhou"] for l in linhas), linhas[0]["criada_em"] if linhas else None,
                       linhas[-1]["criada_em"] if linhas else None, json.dumps(COLUNAS), checksum, str(arq),
                       "solicitacoes (demanda_sintetica fechada, sem estudo por bloqueio)", quem))
    return {"id": did, "linhas": len(linhas), "positivos": sum(l["falhou"] for l in linhas), "checksum": checksum,
            "novo": not ja}


def ler_dataset(cfg, did: str) -> list[dict]:
    """Relê do arquivo e confere o checksum (dataset adulterado não é usado)."""
    with _tb(cfg).tx() as c:
        r = c.execute("SELECT arquivo, checksum FROM ml_datasets WHERE id=?", (did,)).fetchone()
    if not r:
        raise ErroGovernanca(f"dataset {did} não registrado")
    d = json.loads(Path(r[0]).read_text(encoding="utf-8"))
    corpo = json.dumps(d["linhas"], ensure_ascii=False, separators=(",", ":"))
    if _sha(corpo) != r[1]:
        raise ErroGovernanca(f"dataset {did} não confere com o checksum registrado")
    return [dict(zip(d["colunas"], x)) for x in d["linhas"]]


def dividir(linhas: list[dict]) -> dict:
    """Corte temporal (as linhas já vêm em ordem de criação): treino antigo, validação no meio, teste mais novo."""
    n = len(linhas)
    a, b = int(n * 0.70), int(n * 0.85)
    return {"treino": linhas[:a], "validacao": linhas[a:b], "teste": linhas[b:]}


# =============================================================================== 2. modelos (baseline e candidato)
def baseline_treinar(treino: list[dict]) -> dict:
    """Taxa de falha por ferramenta × nível no treino, suavizada para a taxa da ferramenta e depois para a geral."""
    geral = (sum(l["falhou"] for l in treino) + 1) / (len(treino) + 2)
    por_f, por_fn = {}, {}
    for l in treino:
        por_f.setdefault(l["ferramenta"], []).append(l["falhou"])
        por_fn.setdefault(f"{l['ferramenta']}|{l['nivel']}", []).append(l["falhou"])
    tf = {k: (sum(v) + 2 * geral) / (len(v) + 2) for k, v in por_f.items()}
    tfn = {k: (sum(v) + 2 * tf[k.split("|")[0]]) / (len(v) + 2) for k, v in por_fn.items()}
    return {"tipo": "baseline_taxa", "geral": geral, "ferramenta": tf, "ferramenta_nivel": tfn}


def baseline_prever(m: dict, linhas: list[dict]) -> np.ndarray:
    return np.array([m["ferramenta_nivel"].get(f"{l['ferramenta']}|{l['nivel']}",
                                                m["ferramenta"].get(l["ferramenta"], m["geral"])) for l in linhas], dtype=float)


NUMERICAS = ["nivel", "senioridade", "etapas", "hist_pessoa_n", "hist_pessoa_taxa", "hist_ferramenta_taxa"]


def _matriz(m: dict, linhas: list[dict]) -> np.ndarray:
    num = np.array([[float(l[k]) for k in NUMERICAS] for l in linhas], dtype=float).reshape(len(linhas), len(NUMERICAS))
    num = (num - np.array(m["medias"])) / np.array(m["desvios"])
    cat = np.array([[1.0 if l["ferramenta"] == f else 0.0 for f in m["ferramentas"]]
                    + [1.0 if l["andar"] == a else 0.0 for a in m["andares"]] for l in linhas], dtype=float)
    return np.hstack([num, cat.reshape(len(linhas), len(m["ferramentas"]) + len(m["andares"]))])


def _sigmoide(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def logistica_treinar(treino: list[dict], lam: float) -> dict:
    """Regressão logística com penalidade L2, descida de gradiente determinística (mesmos dados = mesmos pesos)."""
    num = np.array([[float(l[k]) for k in NUMERICAS] for l in treino], dtype=float)
    m = {"tipo": "logistica_l2", "lambda": lam, "numericas": NUMERICAS, "medias": num.mean(0).round(12).tolist(),
         "desvios": np.where(num.std(0) > 0, num.std(0), 1.0).round(12).tolist(),
         "ferramentas": sorted({l["ferramenta"] for l in treino}), "andares": sorted({l["andar"] for l in treino})}
    X, y = _matriz(m, treino), np.array([l["falhou"] for l in treino], dtype=float)
    w, b = np.zeros(X.shape[1]), float(np.log((y.mean() + 1e-6) / (1 - y.mean() + 1e-6)))
    for _ in range(ITERACOES):
        p = _sigmoide(X @ w + b)
        w -= PASSO * (X.T @ (p - y) / len(y) + lam * w)
        b -= PASSO * float((p - y).mean())
    m.update(pesos=np.round(w, 10).tolist(), vies=round(b, 10))
    return m


def logistica_prever(m: dict, linhas: list[dict]) -> np.ndarray:
    return _sigmoide(_matriz(m, linhas) @ np.array(m["pesos"]) + m["vies"])


def prever(m: dict, linhas: list[dict]) -> np.ndarray:
    return baseline_prever(m, linhas) if m["tipo"] == "baseline_taxa" else logistica_prever(m, linhas)


# =============================================================================== 3. métricas
def metricas(y, p) -> dict:
    y, p = np.asarray(y, dtype=float), np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    if not len(y):
        return {"n": 0}
    out = {"n": int(len(y)), "taxa_real": round(float(y.mean()), 6),
           "log_loss": round(float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean()), 6),
           "brier": round(float(((p - y) ** 2).mean()), 6)}
    pos, neg = p[y == 1], p[y == 0]
    if len(pos) and len(neg):  # AUC pelo método dos postos (Mann-Whitney)
        ordem = np.argsort(np.concatenate([pos, neg]), kind="mergesort")
        postos = np.empty(len(ordem))
        valores = np.concatenate([pos, neg])[ordem]
        i = 0
        while i < len(valores):  # empates recebem o posto médio
            j = i
            while j + 1 < len(valores) and valores[j + 1] == valores[i]:
                j += 1
            postos[ordem[i:j + 1]] = (i + j) / 2 + 1
            i = j + 1
        out["auc"] = round(float((postos[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))), 6)
    else:
        out["auc"] = None
    return out


def auc_por_pares(y, p) -> float | None:
    """2º caminho do avaliador: AUC contando todos os pares (lento, mas independente do método dos postos)."""
    y, p = list(map(int, y)), list(map(float, p))
    pos = [pi for yi, pi in zip(y, p) if yi == 1]
    neg = [pi for yi, pi in zip(y, p) if yi == 0]
    if not pos or not neg:
        return None
    s = sum(1.0 if a > b else 0.5 if a == b else 0.0 for a in pos for b in neg)
    return s / (len(pos) * len(neg))


# =============================================================================== 4. experimento (engenheiro de ML)
def _artefato(cfg, mid: str, modelo: dict) -> tuple[str, str]:
    texto = json.dumps(modelo, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    arq = _pasta(cfg) / "modelos" / f"{mid}.json"
    arq.write_text(texto, encoding="utf-8")
    return str(arq), _sha(texto)


def carregar(cfg, mid: str) -> dict:
    """Lê o artefato e confere o checksum registrado (modelo adulterado não é usado)."""
    with _tb(cfg).tx() as c:
        r = c.execute("SELECT artefato, checksum FROM ml_modelos WHERE id=?", (mid,)).fetchone()
    if not r:
        raise ErroGovernanca(f"modelo {mid} não registrado")
    texto = Path(r[0]).read_text(encoding="utf-8")
    if _sha(texto) != r[1]:
        raise ErroGovernanca(f"artefato de {mid} não confere com o checksum registrado")
    return json.loads(texto)


def _ajustar(treino, validacao) -> tuple[dict, dict]:
    escolha = None
    for lam in LAMBDAS:  # o ajuste é escolhido na VALIDAÇÃO; o teste fica intocado até o fim
        m = logistica_treinar(treino, lam)
        ll = metricas([l["falhou"] for l in validacao], logistica_prever(m, validacao))["log_loss"]
        if escolha is None or ll < escolha[1]:
            escolha = (m, ll)
    return escolha[0], {"lambda_escolhido": escolha[0]["lambda"], "log_loss_validacao": escolha[1]}


def treinar(cfg, quem: str = EQUIPE_ML["engenheiro"]) -> dict:
    """Monta o dataset, treina baseline e candidato, mede no teste e registra experimento + modelo candidato.
    Idempotente: dataset já treinado devolve o experimento existente (não cria candidato repetido)."""
    import time
    t0 = time.perf_counter()
    ds = montar_dataset(cfg, quem)
    if ds["linhas"] < CRITERIOS["min_linhas"]:
        return {"ok": False, "motivo": f"só {ds['linhas']} demanda(s) fechada(s) rotulada(s); o líder exige "
                                       f"{CRITERIOS['min_linhas']} para treinar", "dataset": ds}
    tb = _tb(cfg)
    with tb.tx() as c:
        ja = c.execute("SELECT e.id, m.id FROM ml_experimentos e JOIN ml_modelos m ON m.experimento_id=e.id "
                       "WHERE e.dataset_id=? ORDER BY e.criado_em DESC LIMIT 1", (ds["id"],)).fetchone()
    if ja:
        return {"ok": True, "repetido": True, "experimento": ja[0], "modelo": ja[1], "dataset": ds,
                "motivo": "este dataset já foi treinado; nada novo para aprender"}
    linhas = ler_dataset(cfg, ds["id"])
    partes = dividir(linhas)
    if len(partes["teste"]) < CRITERIOS["min_teste"] or len({l["falhou"] for l in partes["treino"]}) < 2:
        return {"ok": False, "motivo": "teste pequeno demais ou treino com uma classe só (todas concluídas ou todas "
                                       "falhas): não há o que aprender", "dataset": ds}
    base = baseline_treinar(partes["treino"])
    cand, ajuste = _ajustar(partes["treino"], partes["validacao"])
    yt = [l["falhou"] for l in partes["teste"]]
    met = {"baseline": metricas(yt, baseline_prever(base, partes["teste"])),
           "candidato": metricas(yt, logistica_prever(cand, partes["teste"])),
           "tamanhos": {k: len(v) for k, v in partes.items()}, **ajuste}
    with tb.tx() as c:
        versao = (c.execute("SELECT COALESCE(MAX(versao),0) FROM ml_modelos WHERE finalidade=?",
                            (FINALIDADE,)).fetchone()[0] or 0) + 1
    mid, eid = f"{FINALIDADE}-v{versao}", f"EXP-{FINALIDADE}-v{versao}-{ds['checksum'][:8]}"
    modelo = {**cand, "finalidade": FINALIDADE, "baseline": base, "dataset_id": ds["id"]}
    arq, chk = _artefato(cfg, mid, modelo)
    ambiente = {"numpy": np.__version__, "versao_pipeline": VERSAO_PIPELINE}
    with tb.tx() as c:
        c.execute("INSERT INTO ml_experimentos (id, criado_em, finalidade, dataset_id, versao_codigo, algoritmo, parametros, "
                  "semente, ambiente, metricas, segundos, artefato, checksum, responsavel, estado) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (eid, _agora(), FINALIDADE, ds["id"], _versao_codigo(), "regressao_logistica_l2_numpy",
                   json.dumps({"lambdas": LAMBDAS, "iteracoes": ITERACOES, "passo": PASSO, "corte": "temporal 70/15/15"}),
                   0, json.dumps(ambiente), json.dumps(met), round(time.perf_counter() - t0, 3), arq, chk, quem, "treinado"))
        c.execute("INSERT INTO ml_modelos (id, criado_em, finalidade, versao, experimento_id, dataset_id, artefato, checksum, "
                  "criado_por) VALUES (?,?,?,?,?,?,?,?,?)", (mid, _agora(), FINALIDADE, versao, eid, ds["id"], arq, chk, quem))
        _evento(c, mid, "candidato", quem, {"metricas_teste": met["candidato"], "baseline_teste": met["baseline"]})
    return {"ok": True, "experimento": eid, "modelo": mid, "dataset": ds, "metricas": met, "checksum": chk}


# =============================================================================== 5. estado (derivado dos eventos)
def _evento(c, mid: str, evento: str, quem: str, detalhe: dict) -> None:
    c.execute("INSERT INTO ml_modelos_eventos (data_hora, modelo_id, evento, quem, detalhe) VALUES (?,?,?,?,?)",
              (_agora(), mid, evento, quem, json.dumps(detalhe, ensure_ascii=False, default=str)))


def eventos(cfg, mid: str | None = None) -> list[dict]:
    with _tb(cfg).tx() as c:
        sql = "SELECT id, data_hora, modelo_id, evento, quem, detalhe FROM ml_modelos_eventos"
        rs = c.execute(sql + (" WHERE modelo_id=?" if mid else "") + " ORDER BY id", (mid,) if mid else ()).fetchall()
    return [{"id": r[0], "data_hora": r[1], "modelo": r[2], "evento": r[3], "quem": r[4], "detalhe": json.loads(r[5] or "{}")}
            for r in rs]


def estado_de(cfg, mid: str) -> str:
    """candidato → aprovado | reprovado → referencia → substituido (ou de volta a referencia por rollback)."""
    est = "inexistente"
    for e in eventos(cfg, mid):
        est = {"candidato": "candidato", "avaliado_aprovado": "aprovado", "avaliado_reprovado": "reprovado",
               "promovido": "referencia", "substituido": "substituido", "rollback_saiu": "substituido",
               "rollback_voltou": "referencia"}.get(e["evento"], est)
    return est


def referencia(cfg) -> str | None:
    """O modelo de referência (sombra) atual: o último que entrou como referência e não saiu."""
    atual = None
    for e in eventos(cfg):
        if e["evento"] in ("promovido", "rollback_voltou"):
            atual = e["modelo"]
        elif e["evento"] in ("substituido", "rollback_saiu") and e["modelo"] == atual:
            atual = None
    return atual


def _modelos(cfg) -> list[dict]:
    with _tb(cfg).tx() as c:
        rs = c.execute("SELECT id, versao, experimento_id, dataset_id, criado_por, criado_em FROM ml_modelos "
                       "WHERE finalidade=? ORDER BY versao", (FINALIDADE,)).fetchall()
    return [{"id": r[0], "versao": r[1], "experimento": r[2], "dataset": r[3], "criado_por": r[4], "criado_em": r[5],
             "estado": estado_de(cfg, r[0])} for r in rs]


# =============================================================================== 6. avaliação independente
def avaliar(cfg, mid: str | None = None, quem: str = EQUIPE_ML["avaliador"]) -> dict:
    """O avaliador refaz TUDO a partir do arquivo do modelo e do dataset (checksums conferidos), por outro caminho de
    AUC, retreina para provar reprodutibilidade e compara com o baseline e com a referência atual. Nunca avalia o que
    ele mesmo treinou."""
    if mid is None:
        pend = [m for m in _modelos(cfg) if m["estado"] == "candidato"]
        if not pend:
            return {"ok": False, "motivo": "nenhum candidato esperando avaliação"}
        mid = pend[0]["id"]
    with _tb(cfg).tx() as c:
        r = c.execute("SELECT m.criado_por, m.dataset_id, e.metricas, e.parametros FROM ml_modelos m "
                      "JOIN ml_experimentos e ON e.id=m.experimento_id WHERE m.id=?", (mid,)).fetchone()
    if not r:
        raise ErroGovernanca(f"modelo {mid} não registrado")
    criador, did = r[0], r[1]
    if quem == criador:
        raise ErroGovernanca(f"{quem} treinou {mid}: quem treina não avalia o próprio modelo")
    if estado_de(cfg, mid) != "candidato":
        return {"ok": False, "motivo": f"{mid} não é candidato (está {estado_de(cfg, mid)})"}
    modelo = carregar(cfg, mid)
    linhas = ler_dataset(cfg, did)
    partes = dividir(linhas)
    teste = partes["teste"]
    yt = [l["falhou"] for l in teste]
    p_cand = logistica_prever(modelo, teste)
    m_cand, m_base = metricas(yt, p_cand), metricas(yt, baseline_prever(modelo["baseline"], teste))
    auc2 = auc_por_pares(yt, p_cand)
    refeito, _ = _ajustar(partes["treino"], partes["validacao"])
    reprodutivel = refeito["pesos"] == modelo["pesos"] and refeito["vies"] == modelo["vies"]
    ref = referencia(cfg)
    m_ref = metricas(yt, prever(carregar(cfg, ref), teste)) if ref else None
    motivos = []
    if len(teste) < CRITERIOS["min_teste"]:
        motivos.append(f"teste com {len(teste)} linhas (mínimo {CRITERIOS['min_teste']})")
    if m_cand["auc"] is None:
        motivos.append("o teste tem uma classe só: não dá para medir separação")
    elif m_cand["auc"] < CRITERIOS["auc_minima"]:
        motivos.append(f"AUC {m_cand['auc']:.3f} abaixo do mínimo {CRITERIOS['auc_minima']}")
    if auc2 is not None and m_cand["auc"] is not None and abs(auc2 - m_cand["auc"]) > 1e-6:
        motivos.append(f"AUC não confere por outro caminho ({auc2:.6f} × {m_cand['auc']:.6f})")
    if CRITERIOS["precisa_bater_baseline"] and m_cand["log_loss"] >= m_base["log_loss"]:
        motivos.append(f"não bate o baseline (log loss {m_cand['log_loss']:.4f} ≥ {m_base['log_loss']:.4f})")
    if CRITERIOS["precisa_bater_referencia"] and m_ref and m_cand["log_loss"] >= m_ref["log_loss"]:
        motivos.append(f"não bate a referência atual {ref} (log loss {m_cand['log_loss']:.4f} ≥ {m_ref['log_loss']:.4f})")
    if CRITERIOS["reprodutivel"] and not reprodutivel:
        motivos.append("retreino com os mesmos dados deu pesos diferentes: não é reprodutível")
    aprovado = not motivos
    detalhe = {"candidato": m_cand, "baseline": m_base, "referencia": ref, "referencia_metricas": m_ref,
               "auc_por_pares": auc2, "reprodutivel": reprodutivel, "motivos": motivos, "criterios": CRITERIOS}
    with _tb(cfg).tx() as c:
        _evento(c, mid, "avaliado_aprovado" if aprovado else "avaliado_reprovado", quem, detalhe)
    return {"ok": True, "modelo": mid, "aprovado": aprovado, **detalhe}


# =============================================================================== 7. MLOps: promoção, rollback, integridade
def promover(cfg, mid: str | None = None, quem: str = EQUIPE_ML["mlops"]) -> dict:
    """Só o que OUTRA pessoa aprovou vira referência (sombra). A referência anterior fica registrada como substituída."""
    if mid is None:
        aprov = [m for m in _modelos(cfg) if m["estado"] == "aprovado"]
        if not aprov:
            return {"ok": False, "motivo": "nenhum modelo aprovado esperando promoção"}
        mid = aprov[-1]["id"]
    if estado_de(cfg, mid) != "aprovado":
        raise ErroGovernanca(f"{mid} está '{estado_de(cfg, mid)}': só modelo aprovado pelo avaliador é promovido")
    aprov_por = [e["quem"] for e in eventos(cfg, mid) if e["evento"] == "avaliado_aprovado"][-1]
    criador = next(m["criado_por"] for m in _modelos(cfg) if m["id"] == mid)
    if quem in (aprov_por, criador):
        raise ErroGovernanca(f"{quem} treinou ou aprovou {mid}: a promoção é de outra pessoa")
    carregar(cfg, mid)  # artefato íntegro antes de promover
    anterior = referencia(cfg)
    with _tb(cfg).tx() as c:
        if anterior:
            _evento(c, anterior, "substituido", quem, {"por": mid})
        _evento(c, mid, "promovido", quem, {"anterior": anterior, "uso": "sombra", "uso_operacional": DECISAO_USO_OPERACIONAL})
    return {"ok": True, "modelo": mid, "anterior": anterior}


def rollback(cfg, motivo: str, quem: str = EQUIPE_ML["mlops"]) -> dict:
    """Volta para a referência anterior (a última substituída que tinha sido aprovada)."""
    atual = referencia(cfg)
    if not atual:
        return {"ok": False, "motivo": "não há referência para desfazer"}
    anteriores = [e for e in eventos(cfg) if e["evento"] == "substituido" and e["detalhe"].get("por") == atual]
    if not anteriores:
        return {"ok": False, "motivo": f"{atual} é a primeira referência: não há versão anterior para voltar"}
    volta = anteriores[-1]["modelo"]
    carregar(cfg, volta)
    with _tb(cfg).tx() as c:
        _evento(c, atual, "rollback_saiu", quem, {"motivo": motivo, "volta": volta})
        _evento(c, volta, "rollback_voltou", quem, {"motivo": motivo, "saiu": atual})
    return {"ok": True, "saiu": atual, "voltou": volta}


def conferir_artefatos(cfg) -> dict:
    ok, ruins = 0, []
    for m in _modelos(cfg):
        try:
            carregar(cfg, m["id"])
            ok += 1
        except (ErroGovernanca, OSError, ValueError) as e:
            ruins.append(f"{m['id']}: {e}")
    return {"conferidos": ok, "problemas": ruins}


# =============================================================================== 8. sombra e monitoramento
def pontuar_em_sombra(cfg, limite: int = 200) -> dict:
    """A referência dá a probabilidade de cada demanda ainda não pontuada, com os atributos de quando ela nasceu.
    Nada da empresa usa este número (sombra): serve para medir se o modelo acerta no mundo, não só no teste."""
    ref = referencia(cfg)
    if not ref:
        return {"ok": False, "motivo": "nenhum modelo de referência ainda (precisa de candidato aprovado e promovido)"}
    modelo = carregar(cfg, ref)
    tb = _tb(cfg)
    with tb.tx() as c:
        feitas = {r[0] for r in c.execute("SELECT solicitacao_id FROM ml_inferencias WHERE modelo_id=?", (ref,))}
        fim = c.execute("SELECT d.fim FROM ml_modelos m JOIN ml_datasets d ON d.id=m.dataset_id WHERE m.id=?",
                        (ref,)).fetchone()[0] or ""
    # só o que nasceu DEPOIS do dataset do modelo: pontuar o próprio treino daria um monitoramento otimista (vazamento)
    todas = [l for l in _linhas_abertas_e_fechadas(cfg) if l["criada_em"] > fim]
    novas = [l for l in todas if l["id"] not in feitas][-limite:]
    if not novas:
        return {"ok": True, "modelo": ref, "pontuadas": 0}
    p = prever(modelo, novas)
    with tb.tx() as c:
        c.executemany("INSERT OR IGNORE INTO ml_inferencias (data_hora, modelo_id, solicitacao_id, probabilidade, modo) "
                      "VALUES (?,?,?,?,?)", [(_agora(), ref, l["id"], round(float(pi), 6), "sombra") for l, pi in zip(novas, p)])
    return {"ok": True, "modelo": ref, "pontuadas": len(novas)}


def _linhas_abertas_e_fechadas(cfg) -> list[dict]:
    """Mesmos atributos do dataset (incluindo demandas ainda abertas, que não têm rótulo)."""
    fechadas = {l["id"]: l for l in _linhas_rotuladas(cfg)}
    from robo import organizacao
    with _tb(cfg).tx() as c:
        abertas = c.execute("SELECT id, funcionario, andar, modelo, plano, criada_em FROM solicitacoes "
                            "WHERE origem='demanda_sintetica' AND estado NOT IN ('concluida','concluida_parcialmente','falhou',"
                            "'cancelada') ORDER BY criada_em").fetchall()
    gente = organizacao.por_id(cfg)
    hist = sorted(fechadas.values(), key=lambda x: x["fechada_em"])
    for sid, pid, andar, modelo, plano, criada in abertas:
        try:
            p = json.loads(plano or "{}")
        except ValueError:
            p = {}
        if p.get("tipo_demanda") == "treinamento":
            continue
        pessoa = gente.get(pid) or {}
        ferr = (modelo or "").split(":")[-1]
        antes = [x for x in hist if x["fechada_em"] < criada]
        dp = [x["falhou"] for x in antes if x["funcionario"] == pid]
        df = [x["falhou"] for x in antes if x["ferramenta"] == ferr]
        fechadas[sid] = {"id": sid, "funcionario": pid, "criada_em": criada, "ferramenta": ferr,
                         "nivel": NIVEIS.get(p.get("nivel") or "basico", 0), "andar": int(andar or pessoa.get("andar") or 0),
                         "senioridade": SENIORIDADE.get(organizacao.nivel_de(pid, pessoa) if pid else "pleno", 2),
                         "etapas": _n_etapas(p), "hist_pessoa_n": len(dp),
                         "hist_pessoa_taxa": (sum(dp) + 1) / (len(dp) + 2), "hist_ferramenta_taxa": (sum(df) + 1) / (len(df) + 2)}
    return sorted(fechadas.values(), key=lambda x: (x["criada_em"], x["id"]))


def monitorar(cfg, quem: str = EQUIPE_ML["mlops"]) -> dict:
    """Compara o que a referência previu em sombra com o que aconteceu. Pior que o próprio teste além da tolerância
    (ou pior que o baseline) = degradação: evento registrado e handover para a equipe de ML (nada muda sozinho)."""
    ref = referencia(cfg)
    if not ref:
        return {"ok": False, "motivo": "nenhum modelo de referência para monitorar"}
    rot = {l["id"]: l["falhou"] for l in _linhas_rotuladas(cfg)}
    with _tb(cfg).tx() as c:
        inf = c.execute("SELECT solicitacao_id, probabilidade FROM ml_inferencias WHERE modelo_id=?", (ref,)).fetchall()
    pares = [(rot[s], p) for s, p in inf if s in rot]
    teste = next((e["detalhe"].get("candidato") for e in eventos(cfg, ref) if e["evento"] == "avaliado_aprovado"), {}) or {}
    saida = {"ok": True, "modelo": ref, "pontuadas": len(inf), "fechadas": len(pares), "teste": teste}
    if len(pares) < CRITERIOS["monitor_min_fechadas"]:
        saida["situacao"] = f"aguardando: {len(pares)} de {CRITERIOS['monitor_min_fechadas']} demandas pontuadas já fechadas"
        return saida
    real = metricas([y for y, _ in pares], [p for _, p in pares])
    saida["real"] = real
    limite = (teste.get("log_loss") or real["log_loss"]) * (1 + CRITERIOS["degradacao_tolerancia"])
    degradou = real["log_loss"] > limite
    saida["situacao"] = "degradou" if degradou else "estavel"
    ultimo = [e for e in eventos(cfg, ref) if e["evento"] in ("monitorado", "degradacao")]
    with _tb(cfg).tx() as c:
        if not ultimo or ultimo[-1]["detalhe"].get("fechadas") != len(pares):  # só registra quando há dado novo
            _evento(c, ref, "degradacao" if degradou else "monitorado", quem,
                    {"fechadas": len(pares), "real": real, "teste": teste, "limite_log_loss": round(limite, 6)})
    if degradou:
        from robo import memoria
        memoria.handover(cfg, f"Modelo {ref} degradou em sombra: log loss real {real['log_loss']:.4f} > limite {limite:.4f}",
                         "ml_risco_demanda", quem, f"{len(pares)} demandas fechadas")
    return saida


# =============================================================================== 9. rotina e resumo
def rotina(cfg) -> dict | None:
    """Uma volta do ciclo, cada passo por quem responde por ele: sombra e monitoramento (MLOps); treino quando o
    dataset cresceu (engenheiro); avaliação (avaliador); promoção (MLOps). Nada a fazer = None (rotina em dia)."""
    saida = {}
    try:
        s = pontuar_em_sombra(cfg)
        if s.get("pontuadas"):
            saida["sombra"] = s["pontuadas"]
        mo = monitorar(cfg)
        if mo.get("ok") and mo.get("fechadas"):
            saida["monitoramento"] = mo.get("situacao")
        n_atual = len(_linhas_rotuladas(cfg))
        with _tb(cfg).tx() as c:
            ultimo = c.execute("SELECT COALESCE(MAX(linhas),0) FROM ml_datasets d JOIN ml_experimentos e "
                               "ON e.dataset_id=d.id").fetchone()[0] or 0
        if n_atual >= CRITERIOS["min_linhas"] and n_atual - ultimo >= CRITERIOS["crescimento_para_retreino"]:
            t = treinar(cfg)
            if t.get("ok") and not t.get("repetido"):
                saida["treinou"] = t["modelo"]
        a = avaliar(cfg)
        if a.get("ok"):
            saida["avaliou"] = f"{a['modelo']}: {'aprovado' if a['aprovado'] else 'reprovado'}"
        p = promover(cfg)
        if p.get("ok"):
            saida["promoveu"] = p["modelo"]
    except ErroGovernanca as e:
        saida["governanca"] = str(e)
    return saida or None


def resumo(cfg) -> dict:
    """Para o boletim e o painel: só o que está nos registros."""
    mods = _modelos(cfg)
    with _tb(cfg).tx() as c:
        nds = c.execute("SELECT COUNT(*), MAX(linhas) FROM ml_datasets").fetchone()
        ninf = c.execute("SELECT COUNT(*) FROM ml_inferencias").fetchone()[0]
    ultimo_av = next((e for e in reversed(eventos(cfg)) if e["evento"].startswith("avaliado_")), None)
    return {"finalidade": FINALIDADE, "rotuladas_agora": len(_linhas_rotuladas(cfg)), "minimo_para_treinar": CRITERIOS["min_linhas"],
            "datasets": nds[0] or 0, "maior_dataset": nds[1] or 0, "modelos": [{k: m[k] for k in ("id", "estado", "criado_por")}
                                                                                for m in mods],
            "referencia": referencia(cfg), "inferencias_sombra": ninf, "uso_operacional": DECISAO_USO_OPERACIONAL,
            "ultima_avaliacao": ({"modelo": ultimo_av["modelo"], "resultado": ultimo_av["evento"], "quem": ultimo_av["quem"],
                                  "candidato": ultimo_av["detalhe"].get("candidato"),
                                  "baseline": ultimo_av["detalhe"].get("baseline"),
                                  "motivos": ultimo_av["detalhe"].get("motivos")} if ultimo_av else None)}


# =============================================================================== 10. ferramentas da equipe (contratos)
def _r(ok, natureza, texto, dados=None, evidencia=""):
    from robo.ferramentas import resultado
    return resultado(ok, natureza, texto, dados or {}, evidencia=evidencia)


def f_ml_portfolio(cfg, quem: str = EQUIPE_ML["lider"], **_) -> dict:
    """Líder: o backlog de modelos com o estado REAL de cada caso, os critérios e o que falta para o próximo passo."""
    r = resumo(cfg)
    falta = max(0, r["minimo_para_treinar"] - r["rotuladas_agora"])
    linhas = [f"- **{b['caso']}** ({b['estado']}): {b['pergunta']} — {b['por_que_ml']}" for b in BACKLOG]
    estado = (f"Referência em sombra: {r['referencia']}." if r["referencia"] else
              f"Sem modelo de referência ainda; faltam {falta} demanda(s) rotulada(s) para o 1º treino." if falta else
              "Dados suficientes; o próximo treino/avaliação decide se há referência.")
    texto = (f"Programa de inteligência própria — {len(BACKLOG)} casos no backlog, 1 implementado.\n{estado}\n"
             f"Critérios de promoção: bater o baseline e a referência no teste temporal, AUC ≥ {CRITERIOS['auc_minima']}, "
             f"reprodutível, avaliado por outra pessoa. Uso operacional: {DECISAO_USO_OPERACIONAL}.\n" + "\n".join(linhas))
    return _r(True, "conhecimento", texto, {"backlog": BACKLOG, "resumo": r, "criterios": CRITERIOS},
              evidencia="ml_modelos, ml_modelos_eventos e ml_datasets lidos agora")


def f_ml_treinar(cfg, quem: str = EQUIPE_ML["engenheiro"], **_) -> dict:
    """Engenheiro de ML: dataset versionado + baseline + candidato, medidos no teste temporal."""
    t = treinar(cfg, quem)
    if not t.get("ok"):
        return _r(False, "limitacao", f"Não treinei: {t['motivo']}.", {"dataset": t.get("dataset")})
    if t.get("repetido"):
        return _r(False, "limitacao", f"Não treinei de novo: {t['motivo']} ({t['experimento']}).", {"experimento": t["experimento"]})
    c, b = t["metricas"]["candidato"], t["metricas"]["baseline"]
    texto = (f"Treinei {t['modelo']} com o dataset {t['dataset']['id']} ({t['dataset']['linhas']} demandas, "
             f"{t['dataset']['positivos']} não concluídas). No teste temporal ({c['n']} demandas): log loss {c['log_loss']:.4f} "
             f"(baseline {b['log_loss']:.4f}), AUC {c['auc'] if c['auc'] is None else round(c['auc'], 3)} "
             f"(baseline {b['auc'] if b['auc'] is None else round(b['auc'], 3)}). Fica como candidato até a avaliação independente.")
    return _r(True, "calculo", texto, {"experimento": t["experimento"], "modelo": t["modelo"], "metricas": t["metricas"],
                                       "checksum": t["checksum"]}, evidencia=f"experimento {t['experimento']} registrado")


def f_ml_avaliar(cfg, quem: str = EQUIPE_ML["avaliador"], **_) -> dict:
    """Avaliador independente: refaz as métricas do arquivo e do dataset, retreina e decide."""
    try:
        a = avaliar(cfg, quem=quem)
    except ErroGovernanca as e:
        return _r(False, "limitacao", f"Avaliação recusada: {e}.")
    if not a.get("ok"):
        return _r(False, "limitacao", f"Nada para avaliar: {a['motivo']}.")
    decisao = "APROVADO" if a["aprovado"] else "REPROVADO"
    texto = (f"{a['modelo']}: {decisao}. Log loss {a['candidato']['log_loss']:.4f} contra baseline "
             f"{a['baseline']['log_loss']:.4f}; AUC conferida por dois caminhos; reprodutível: "
             f"{'sim' if a['reprodutivel'] else 'não'}." + (" Motivos: " + "; ".join(a["motivos"]) if a["motivos"] else ""))
    return _r(True, "calculo", texto, {"modelo": a["modelo"], "decisao": decisao, "motivos": a["motivos"],
                                       "candidato": a["candidato"], "baseline": a["baseline"]},
              evidencia=f"artefato e dataset de {a['modelo']} conferidos pelo checksum e reavaliados agora")


def f_ml_registro(cfg, quem: str = EQUIPE_ML["mlops"], **_) -> dict:
    """MLOps: integridade de todos os artefatos, promoção do que foi aprovado por outra pessoa e monitoramento."""
    integ = conferir_artefatos(cfg)
    try:
        prom = promover(cfg, quem=quem)
    except ErroGovernanca as e:
        prom = {"ok": False, "motivo": str(e)}
    som, mon = pontuar_em_sombra(cfg), monitorar(cfg, quem)
    ok = not integ["problemas"]
    texto = (f"{integ['conferidos']} artefato(s) conferido(s) pelo checksum" + (f"; PROBLEMAS: {integ['problemas']}" if not ok else "")
             + f". Promoção: {prom.get('modelo') or prom.get('motivo')}. Referência: {referencia(cfg) or 'nenhuma'}; "
             f"sombra: {som.get('pontuadas', 0)} nova(s) pontuada(s); monitoramento: {mon.get('situacao') or mon.get('motivo')}.")
    return _r(ok, "execucao" if ok else "limitacao", texto, {"integridade": integ, "promocao": prom, "sombra": som,
                                                              "monitoramento": mon},
              evidencia="checksums dos artefatos e eventos do registro de modelos conferidos agora")


# =============================================================================== 11. provas técnicas (RH)
def provas() -> dict:
    y = [0, 0, 1, 1]
    perfeito, invertido = [0.1, 0.2, 0.8, 0.9], [0.9, 0.8, 0.2, 0.1]
    linhas = [{"id": f"s{i}", "criada_em": f"2026-01-{i + 1:02d}", "falhou": i % 2} for i in range(20)]
    p = dividir(linhas)
    temporal = max(l["criada_em"] for l in p["treino"]) < min(l["criada_em"] for l in p["teste"])
    trein = [{"ferramenta": "x", "nivel": 0, "andar": 1, "senioridade": 2, "etapas": 1, "hist_pessoa_n": 0,
              "hist_pessoa_taxa": 0.5, "hist_ferramenta_taxa": 0.5, "falhou": i % 2} for i in range(30)]
    m1, m2 = logistica_treinar(trein, 0.1), logistica_treinar(trein, 0.1)
    return {
        "ml_lider": [("Critério exige bater o baseline", CRITERIOS["precisa_bater_baseline"]),
                     ("Uso operacional fica com o dono", "dono" in DECISAO_USO_OPERACIONAL)],
        "ml_engenheiro": [("AUC 1 para separação perfeita", metricas(y, perfeito)["auc"] == 1.0),
                          ("AUC 0 para separação invertida", metricas(y, invertido)["auc"] == 0.0),
                          ("Corte temporal: o teste é mais novo que o treino", temporal),
                          ("Mesmos dados = mesmos pesos (reprodutível)", m1["pesos"] == m2["pesos"])],
        "ml_avaliador": [("AUC por outro caminho confere", auc_por_pares(y, [0.1, 0.4, 0.35, 0.8]) == metricas(y, [0.1, 0.4, 0.35, 0.8])["auc"]),
                         ("Log loss pune a confiança errada", metricas(y, invertido)["log_loss"] > metricas(y, perfeito)["log_loss"])],
        "ml_mlops": [("Ferramenta sem histórico cai na taxa geral (não inventa)",
                      baseline_prever(baseline_treinar(trein), [{"ferramenta": "nova", "nivel": 3}])[0]
                      == baseline_treinar(trein)["geral"]),
                     ("Checksum muda se o artefato muda", _sha("a") != _sha("b"))],
    }
