"""Tempo do turno por natureza: quanto do turno foi trabalho, estudo, revisão, manutenção, erro ou parada. MEDIDO.

Antes só havia estimativa ("~45% ocupado"). Agora o turno da nuvem cronometra cada chamada do laço (cada rotina, a
esteira, o salvamento, o boletim e a pausa entre voltas) com o relógio de alta precisão. O tempo da rotina "demandas"
é repartido pelas demandas que ela executou (jobs com início e fim no banco). O que o cronômetro não cobriu aparece
como "sem_medicao" e nunca é distribuído entre as outras naturezas.

Naturezas:
  operacional   trabalho do papel que entrega algo: demanda de trabalho/projeto, esteira, fábrica, painéis, modelos
  estudo        treino, laboratório, lições, demanda de estudo (dada porque o trabalho estava bloqueado)
  revisao       auditoria por amostragem e o que a coordenação das demandas gasta fora das demandas
  coordenacao   diálogo, PDCA, caixa do dono, alçadas, RH de desempenho, reunião, estratégia, ideias
  manutencao    backup, cópia para o PostgreSQL, registro, ronda de TI, jornada de teste, canal, boletim
  erro          rotina ou demanda que terminou em erro/falha
  parado        pausa entre as voltas do laço (nada a fazer naquele instante)
  sem_medicao   tempo do turno fora de qualquer chamada cronometrada

Bloqueio e espera de dependência não ocupam tempo (a demanda nem nasce): vão como CONTAGEM (eventos 'bloqueada' do
ciclo de demandas e etapas 'bloqueada' por dependência), nunca como minutos inventados.

Indicador principal: entregas aprovadas na revisão independente (estado 'concluida') por hora de turno.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from datetime import datetime

from robo.trabalho import Trabalho, _agora

NATUREZAS = ("operacional", "estudo", "revisao", "coordenacao", "manutencao", "erro", "parado", "sem_medicao")
NATUREZA_DA_ROTINA = {
    "fabrica": "operacional", "paineis": "operacional", "modelos": "operacional", "esteira": "operacional",
    "treino": "estudo", "laboratorio": "estudo", "licoes": "estudo", "estudo": "estudo",
    "auditoria": "revisao",
    "dialogo": "coordenacao", "pdca": "coordenacao", "caixa_dono": "coordenacao", "alcadas": "coordenacao",
    "rh_desempenho": "coordenacao", "reuniao": "coordenacao", "estrategia": "coordenacao", "ideias": "coordenacao",
    "backup": "manutencao", "memoria_pg": "manutencao", "registro": "manutencao", "ronda_ti": "manutencao",
    "jornada": "manutencao", "canal": "manutencao", "telegram": "manutencao", "salvar": "manutencao",
    "boletim": "manutencao", "inicio": "manutencao",
    "pausa": "parado",
}
ESQUEMA = """
CREATE TABLE IF NOT EXISTS tempo_turnos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, inicio TEXT NOT NULL, fim TEXT NOT NULL, segundos REAL NOT NULL,
  voltas INTEGER, por_natureza TEXT NOT NULL, por_chamada TEXT NOT NULL, contagens TEXT NOT NULL,
  entregas_aprovadas INTEGER NOT NULL, entregas_por_hora REAL NOT NULL, cobertura REAL NOT NULL);
CREATE TRIGGER IF NOT EXISTS tempo_turnos_nao_muda BEFORE UPDATE ON tempo_turnos
BEGIN SELECT RAISE(ABORT, 'registro permanente: tempo do turno não pode ser alterado'); END;
"""


class Cronometro:
    """Soma o tempo de parede de cada chamada do turno, por chave (nome da rotina, 'esteira', 'pausa'...)."""

    def __init__(self):
        self.inicio_txt = _agora()
        self._t0 = time.perf_counter()
        self.por_chamada: dict[str, float] = {}
        self.erros: dict[str, float] = {}

    @contextmanager
    def medir(self, chave: str):
        t = time.perf_counter()
        try:
            yield
        finally:
            self.por_chamada[chave] = self.por_chamada.get(chave, 0.0) + time.perf_counter() - t

    def rotina(self, cfg, nome: str, executar, funcao):
        """Executa a rotina pelo caminho normal (rotinas.executar) e marca o tempo como erro se ela falhou."""
        t = time.perf_counter()
        r = None
        try:
            r = executar(cfg, nome, funcao)
            return r
        finally:
            dt = time.perf_counter() - t
            self.por_chamada[nome] = self.por_chamada.get(nome, 0.0) + dt
            if _falhou(cfg, nome):
                self.erros[nome] = self.erros.get(nome, 0.0) + dt

    def total(self) -> float:
        return time.perf_counter() - self._t0


def _falhou(cfg, nome: str) -> bool:
    try:
        with Trabalho(cfg).tx() as c:
            r = c.execute("SELECT ultimo_status FROM rotinas_estado WHERE nome=?", (nome,)).fetchone()
        return bool(r and r[0] == "erro")
    except Exception:
        return False


def _demandas_do_periodo(c, inicio: str, fim: str) -> list[dict]:
    """Jobs de demanda fechados no período, com a natureza tirada da solicitação (trabalho, projeto ou estudo)."""
    saida = []
    for j in c.execute("SELECT inicio, fim, estado, evidencia FROM jobs WHERE tipo='demanda' AND fim IS NOT NULL "
                       "AND inicio>=? AND inicio<=?", (inicio, fim)):
        try:
            sid = (json.loads(j["evidencia"] or "{}") or {}).get("solicitacao")
        except ValueError:
            sid = None
        tipo = "trabalho"
        if sid:
            s = c.execute("SELECT plano FROM solicitacoes WHERE id=?", (sid,)).fetchone()
            try:
                tipo = (json.loads((s or {"plano": "{}"})["plano"] or "{}") or {}).get("tipo_demanda") or "trabalho"
            except ValueError:
                pass
        seg = max(0.0, (datetime.fromisoformat(j["fim"]) - datetime.fromisoformat(j["inicio"])).total_seconds())
        nat = "erro" if j["estado"] == "falhou" else ("estudo" if tipo == "treinamento" else "operacional")
        saida.append({"natureza": nat, "segundos": seg})
    return saida


def calcular(cfg, crono: Cronometro, fim_txt: str | None = None, total_s: float | None = None) -> dict:
    """Reparte o tempo cronometrado em naturezas. Não grava (fechar() grava)."""
    fim_txt = fim_txt or _agora()
    total = float(total_s if total_s is not None else crono.total())
    por = dict.fromkeys(NATUREZAS, 0.0)
    for chave, seg in crono.por_chamada.items():
        erro = min(seg, crono.erros.get(chave, 0.0))
        por["erro"] += erro
        if chave != "demandas":
            por[NATUREZA_DA_ROTINA.get(chave, "manutencao")] += seg - erro
    from robo import jobs
    with jobs._tb(cfg).tx() as c:  # garante a tabela de jobs (máquina nova pode não ter nenhum ainda)
        dem = _demandas_do_periodo(c, crono.inicio_txt, fim_txt)
        aprovadas = c.execute(
            "SELECT COUNT(*) FROM solicitacoes WHERE origem='demanda_sintetica' AND estado='concluida' AND "
            "atualizada_em>=? AND atualizada_em<=? AND COALESCE(json_extract(plano,'$.tipo_demanda'),'trabalho') "
            "<> 'treinamento'", (crono.inicio_txt, fim_txt)).fetchone()[0]
        try:
            bloqueios = c.execute("SELECT COUNT(*) FROM demandas_registro WHERE evento='bloqueada' AND data_hora>=? "
                                  "AND data_hora<=?", (crono.inicio_txt, fim_txt)).fetchone()[0]
        except Exception:
            bloqueios = 0
        try:
            espera = c.execute("SELECT COUNT(*) FROM etapas e JOIN solicitacoes s ON s.id=e.solicitacao_id WHERE "
                               "e.estado='bloqueada' AND e.resultado LIKE '%depende de%' AND s.atualizada_em>=? AND "
                               "s.atualizada_em<=?", (crono.inicio_txt, fim_txt)).fetchone()[0]
        except Exception:
            espera = 0
    # a rotina "demandas": o que as demandas mediram vai para a natureza delas (limitado ao tempo da rotina); o resto
    # é a coordenação do ciclo (cobertura, distribuição, geração, revisão e avaliação por amostragem)
    t_dem = crono.por_chamada.get("demandas", 0.0) - min(crono.por_chamada.get("demandas", 0.0),
                                                           crono.erros.get("demandas", 0.0))
    medido = sum(d["segundos"] for d in dem)
    fator = min(1.0, t_dem / medido) if medido else 0.0
    for d in dem:
        por[d["natureza"]] += d["segundos"] * fator
    por["revisao"] += max(0.0, t_dem - medido * fator)
    coberto = sum(crono.por_chamada.values())
    por["sem_medicao"] = max(0.0, total - coberto)
    horas = total / 3600 if total else 0.0
    return {"inicio": crono.inicio_txt, "fim": fim_txt, "segundos": round(total, 1),
            "por_natureza": {k: round(v, 1) for k, v in por.items()},
            "percentual": {k: round(100 * v / total, 1) if total else 0.0 for k, v in por.items()},
            "por_chamada": {k: round(v, 2) for k, v in sorted(crono.por_chamada.items(), key=lambda x: -x[1])},
            "contagens": {"demandas_executadas": len(dem), "bloqueios": bloqueios, "etapas_esperando_dependencia": espera},
            "entregas_aprovadas": aprovadas, "entregas_por_hora": round(aprovadas / horas, 2) if horas else 0.0,
            "cobertura": round(min(1.0, coberto / total), 3) if total else 0.0,
            "precisao": "rotinas, esteira e pausa: relógio de alta precisão; divisão das demandas: 1 s (início e fim "
                        "gravados em segundos)"}


def fechar(cfg, crono: Cronometro, voltas: int = 0) -> dict:
    """Calcula e grava o tempo do turno (registro permanente). Nunca derruba o turno."""
    r = calcular(cfg, crono)
    tb = Trabalho(cfg)
    with tb.tx() as c:
        c.executescript(ESQUEMA)
        from robo.trabalho import proteger
        proteger(c)
        c.execute("INSERT INTO tempo_turnos (inicio, fim, segundos, voltas, por_natureza, por_chamada, contagens, "
                  "entregas_aprovadas, entregas_por_hora, cobertura) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (r["inicio"], r["fim"], r["segundos"], voltas, json.dumps(r["por_natureza"]),
                   json.dumps(r["por_chamada"]), json.dumps(r["contagens"]), r["entregas_aprovadas"],
                   r["entregas_por_hora"], r["cobertura"]))
    return r


def ultimos(cfg, n: int = 10) -> list[dict]:
    try:
        with Trabalho(cfg).tx() as c:
            linhas = c.execute("SELECT * FROM tempo_turnos ORDER BY id DESC LIMIT ?", (n,)).fetchall()
    except Exception:
        return []
    saida = []
    for x in linhas:
        d = dict(x)
        for k in ("por_natureza", "por_chamada", "contagens"):
            d[k] = json.loads(d[k] or "{}")
        d["percentual"] = {k: round(100 * v / d["segundos"], 1) if d["segundos"] else 0.0
                           for k, v in d["por_natureza"].items()}
        saida.append(d)
    return saida
