"""Demandas: cada funcionário recebe trabalho real, executado pela própria ferramenta e conferido por outra pessoa.

    python -m robo rotina demandas

O que já existia e é reaproveitado (nada duplicado):
  - robo/trabalho.py      solicitações, etapas, eventos, aprovações e artefatos (registro permanente);
  - robo/orquestrador.py  execução etapa por etapa com ferramenta real, contrato de ferramentas, aprovação e
                          REVISOR INDEPENDENTE (nunca quem executou);
  - robo/ferramentas.py   as ferramentas de verdade (cálculo, diagnóstico, SQL somente leitura, ronda de TI…).

O que este módulo acrescenta:
  1. um CATÁLOGO de demandas por ferramenta: objetivo, contexto, critérios de aceitação verificáveis e evidência
     esperada. A demanda é a "ordem de serviço"; a ferramenta é quem faz;
  2. CRITÉRIOS DE ACEITAÇÃO conferidos pelo revisor, sem IA (conferir_criterios). O cálculo, por exemplo, só é
     aceito se bater com uma conta independente feita em pandas por outro caminho;
  3. DISTRIBUIÇÃO JUSTA (rotina): quem está há mais tempo sem demanda recebe primeiro; ninguém tem duas demandas
     abertas; no máximo uma por pessoa a cada `por_pessoa_horas`; teto por ciclo e por dia.

Regras de honestidade:
  - estagiário fica em modo de observação (regra do dono): não recebe demanda, e o motivo fica registrado;
  - demanda que não tem como rodar (sem planilha sintética, PostgreSQL desligado, ferramenta que precisa de algo que
    o robô não tem) NÃO vira tarefa de mentira: fica registrada no ciclo como bloqueada, com o motivo;
  - os dados de trabalho são SINTÉTICOS (as planilhas da fábrica em Bases-Tratadas/_treino e Bases-Originais/_treino);
    a solicitação sai marcada com origem 'demanda_sintetica'. Nenhuma demanda lê planilha real nem publica nada;
  - publicar planilha (altera dados) nunca é distribuída automaticamente.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from robo.trabalho import FINAIS, Trabalho, _agora

ORIGEM = "demanda_sintetica"
PADRAO = {"habilitada": True, "intervalo_minutos": 30, "por_ciclo": 6, "por_dia": 150, "por_pessoa_horas": 24}
NIVEIS_SEM_DEMANDA = {"estagiario": "estagiário fica em modo de observação (regra do dono)"}
# ferramentas que não entram na distribuição automática, e por quê (registrado no ciclo)
FORA_DA_DISTRIBUICAO = {
    "publicar_planilha": "altera dados de produção: só com pedido e aprovação do dono",
    "revisar_caso": "precisa de um caso da Sala de Casos; a revisão já acontece no treino",
    "resumo_executivo": "depende das etapas anteriores de uma tarefa; não existe sozinho",
}

ESQUEMA = """
CREATE TABLE IF NOT EXISTS demandas_ciclos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT NOT NULL, responsavel TEXT, elegiveis INTEGER,
  atribuidas INTEGER, concluidas INTEGER, bloqueadas INTEGER, detalhe TEXT);
CREATE TRIGGER IF NOT EXISTS demandas_ciclos_imutavel BEFORE UPDATE ON demandas_ciclos
BEGIN SELECT RAISE(ABORT, 'ciclo de demandas é permanente: não se altera'); END;
"""


def _c(cfg) -> dict:
    return {**PADRAO, **((getattr(cfg, "dados", {}) or {}).get("demandas") or {})}


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    with tb.tx() as c:
        c.executescript(ESQUEMA)
        from robo.trabalho import proteger
        proteger(c)
    return tb


# =============================================================================== material de trabalho (sintético)
def _recentes(pasta: Path, limite: int = 10) -> list[Path]:
    """A esteira arquiva com carimbo e por mês (_treino/2026-10/20261023_..._TREINO_x.xlsx): procura nas subpastas."""
    if not pasta.is_dir():
        return []
    arqs = [p for p in pasta.rglob("*TREINO_*") if p.is_file() and p.suffix.lower() in (".xlsx", ".csv")]
    return sorted(arqs, key=lambda p: p.stat().st_mtime, reverse=True)[:limite]


def _mais_recente(pasta: Path) -> Path | None:
    r = _recentes(pasta, 1)
    return r[0] if r else None


def base_tratada(cfg) -> Path | None:
    """A planilha sintética mais recente já tratada pela esteira (Bases-Tratadas/_treino)."""
    return _mais_recente(Path(cfg.tratadas) / "_treino")


def base_original(cfg) -> Path | None:
    """A cópia original (suja) da planilha sintética mais recente (Bases-Originais/_treino)."""
    return _mais_recente(Path(cfg.originais) / "_treino")


def _ler(arquivo: Path):
    import pandas as pd
    return pd.read_csv(arquivo) if arquivo.suffix.lower() == ".csv" else pd.read_excel(arquivo)


def _coluna_numerica(df, padroes_id: list[str]) -> str | None:
    """Uma métrica de verdade: numérica, com variação e que NÃO seja identificador pela mesma regra da limpeza
    (limpeza.padroes_identificador do config.yaml: nota_fiscal, pedido, cpf…). A calculadora usa a mesma regra."""
    import pandas as pd

    from robo.limpeza import _eh_identificador
    for c in df.columns:
        n = str(c).lower()
        if n.startswith("_") or _eh_identificador(n, padroes_id):
            continue
        s = pd.to_numeric(df[c], errors="coerce")
        if s.notna().mean() >= 0.9 and s.nunique() > 2:
            return str(c)
    return None


# =============================================================================== catálogo
@dataclass
class Modelo:
    ferramenta: str
    titulo: str
    objetivo: str
    evidencia: str
    criterios: list[dict] = field(default_factory=list)
    # preparar(cfg, pessoa) → (parâmetros, critérios extras) ou str (motivo de bloqueio: a demanda não é criada)
    preparar: Callable | None = None


BASICOS = [{"tipo": "ok"}, {"tipo": "evidencia"}, {"tipo": "natureza", "nao": ["limitacao"]}, {"tipo": "texto_min", "n": 30}]


def _com_tratada(cfg, pessoa):
    arq = base_tratada(cfg)
    return ({"arquivo": str(arq)}, []) if arq else "ainda não há planilha sintética tratada (Bases-Tratadas/_treino)"


def _com_original(cfg, pessoa):
    arq = base_original(cfg)
    return ({"arquivo": str(arq)}, []) if arq else "ainda não há planilha sintética original (Bases-Originais/_treino)"


def _calculo(cfg, pessoa):
    """Média de uma métrica da base sintética. O critério compara com a média feita aqui, em pandas, por outro caminho."""
    import pandas as pd
    bases = _recentes(Path(cfg.tratadas) / "_treino")
    if not bases:
        return "ainda não há planilha sintética tratada (Bases-Tratadas/_treino)"
    padroes = (cfg.dados.get("limpeza") or {}).get("padroes_identificador") or []
    for arq in bases:
        df = _ler(arq)
        col = _coluna_numerica(df, padroes)
        if col:
            break
    else:
        return f"nenhuma das {len(bases)} base(s) sintética(s) recentes tem métrica numérica que não seja identificador"
    esperado = float(pd.to_numeric(df[col], errors="coerce").mean())
    return ({"arquivo": str(arq), "pergunta": f"média de {col}"},
            [{"tipo": "valor_unico", "esperado": esperado, "tolerancia": 1e-6, "coluna": col}])


def _com_indicador(cfg, pessoa):
    """Drivers precisam de um alvo NPS ou CSAT, pela mesma regra da ferramenta (calculos._coluna_indicador)."""
    from robo.calculos import _coluna_indicador
    bases = _recentes(Path(cfg.tratadas) / "_treino")
    for arq in bases:
        df = _ler(arq)
        if _coluna_indicador("nps", df) or _coluna_indicador("csat", df):
            return {"arquivo": str(arq)}, []
    return (f"nenhuma das {len(bases)} base(s) sintética(s) recentes tem coluna de NPS ou CSAT para ser o alvo "
            "(a fábrica gera as regras nps e csat_ces; a demanda volta quando houver um lote delas)")


def _sql(cfg, pessoa):
    """Leitura real no PostgreSQL: os lotes sintéticos que a esteira gravou no schema treino."""
    if not (cfg.banco or {}).get("habilitado"):
        return "PostgreSQL desligado nas Configurações: consulta SQL não roda"
    from robo.banco import Banco
    try:
        with Banco(cfg.banco, cfg.base).conectar() as conn:
            existe = conn.execute("SELECT to_regclass('treino.lotes')").fetchone()[0]
            n = conn.execute("SELECT COUNT(*) FROM treino.lotes").fetchone()[0] if existe else 0
    except Exception as e:
        return f"PostgreSQL indisponível ({type(e).__name__})"
    if not n:
        return "o schema treino ainda não tem lotes (nenhuma planilha da fábrica foi carregada)"
    return ({"sql": "SELECT arquivo, status, linhas_entrada, linhas_saida, erros FROM treino.lotes "
                    "ORDER BY processado_em DESC LIMIT 20"},
            [{"tipo": "linhas_min", "n": min(int(n), 20)}])


def _pergunta_da_area(cfg, pessoa):
    from robo import organizacao
    area = organizacao.area_de(pessoa["id"]) or "dados"
    return ({"pergunta": f"boas práticas de {area}"}, [])


def _quem(cfg, pessoa):
    return ({"quem": pessoa["id"]}, [])


def _andar(cfg, pessoa):
    return ({"andar": pessoa["andar"]}, [])


CATALOGO: dict[str, Modelo] = {m.ferramenta: m for m in [
    Modelo("calcular", "Calcular a média de uma métrica da base sintética",
           "Responder com um número conferível qual é a média da métrica principal da última base da fábrica.",
           "valor calculado + conferência por SQL quando houver banco", BASICOS, _calculo),
    Modelo("diagnosticar_planilha", "Diagnosticar a planilha original da fábrica",
           "Rodar o pipeline em modo diagnóstico (sem gravar) na planilha suja e relatar o que barraria a produção.",
           "relatório do diagnóstico com erros e avisos", BASICOS, _com_original),
    Modelo("perfil_indicadores", "Perfil e indicadores da base sintética",
           "Descrever as colunas e calcular os indicadores (NPS/CSAT/CES quando houver) com margem de erro.",
           "perfil das colunas e indicadores calculados", BASICOS, _com_tratada),
    Modelo("dados_pessoais", "Verificar dados pessoais (LGPD) na base sintética",
           "Procurar e-mail, CPF e telefone e dizer onde estão, antes de qualquer uso da base.",
           "colunas com dado pessoal encontradas (ou nenhuma)", BASICOS, _com_tratada),
    Modelo("drivers", "Drivers do indicador na base sintética",
           "Medir o que mais influencia o indicador principal (correlação e regressão).",
           "tabela de drivers com força e significância", BASICOS, _com_indicador),
    Modelo("segmentacao", "Segmentação da base sintética",
           "Encontrar grupos parecidos (k-means) e dizer se a separação é boa (silhueta).",
           "grupos encontrados com silhueta", BASICOS, _com_tratada),
    Modelo("anomalias", "Anomalias na base sintética",
           "Apontar valores fora do padrão com a linha de origem.", "lista de anomalias com linha", BASICOS, _com_tratada),
    Modelo("consulta_sql", "Conferir no PostgreSQL os lotes da fábrica",
           "Ler, em transação somente leitura, os lotes sintéticos gravados no schema treino.",
           "linhas devolvidas pelo PostgreSQL", BASICOS, _sql),
    Modelo("ronda_ti", "Ronda de saúde do sistema", "Conferir disco, pastas, dependências, segurança e logs agora.",
           "verificações executadas neste computador", BASICOS),
    Modelo("orquestracao", "SLA das rotinas", "Apontar rotinas atrasadas, com erro ou lentas pelos registros.",
           "rotinas_execucoes e rotinas_estado", BASICOS),
    Modelo("reuniao_andar", "Situação do andar agora", "Levantar o que deu certo, errado e o plano de ação do andar.",
           "histórico, solicitações, memória e handovers do andar", BASICOS, _andar),
    Modelo("scorecard", "Scorecard da área", "Indicadores da área com meta e farol, calculados dos registros.",
           "indicadores com meta e farol", BASICOS, _quem),
    Modelo("auditoria", "Auditoria por amostragem", "Refazer por outro caminho uma amostra das entregas da semana.",
           "amostra refeita e registrada em auditorias", BASICOS, _quem),
    Modelo("desempenho", "Desempenho da semana", "Acertos, erros e situação de cada pessoa pela regra do RH.",
           "memória da semana", BASICOS),
    Modelo("people_analytics", "Indicadores de pessoas", "Quadro, aprovação nas provas e trabalho registrado.",
           "registro de funcionários e provas", BASICOS),
    Modelo("recrutamento", "Situação das contratações", "Resumo de vagas, experiências e efetivações.",
           "robo/contratacao.py", BASICOS),
    Modelo("desenvolvimento", "Planos de desenvolvimento 70-20-10", "Montar planos para quem errou na semana.",
           "memória, handovers e boas práticas", BASICOS, _quem),
    Modelo("revisao_biblioteca", "Revisão da biblioteca sob sua responsabilidade",
           "Rodar os guardas de comportamento da biblioteca e abrir handover se algo mudou.",
           "guardas executados na versão instalada", BASICOS, _quem),
    Modelo("estrategia_python", "Estratégia Python", "Desempenho por volume e projeção a partir do laboratório.",
           "tempos medidos no laboratório", BASICOS),
    Modelo("raio_x", "Raio-X da empresa", "Como a empresa está agora, com números de todos os registros.",
           "registros lidos agora", BASICOS),
    Modelo("organizacao", "Quadro por andar e nível", "Conferir quem faz o quê, por andar e nível.",
           "registro único de funcionários", BASICOS),
    Modelo("ideias", "Ideias para o futuro", "Propostas tiradas da memória de todos, com o dado de origem.",
           "memória, handovers e solicitações", BASICOS),
    Modelo("laboratorio", "Balanço do laboratório", "O que a equipe treinou e errou no laboratório.",
           "laboratorio_exercicios", BASICOS),
    Modelo("historico", "Últimas execuções do robô", "Ler o histórico e resumir as últimas execuções.",
           "histórico de execuções", BASICOS),
    Modelo("conhecimento", "Consultar o conhecimento da área",
           "Achar no conhecimento da empresa (manuais, lições, handovers) o que vale para a própria área.",
           "fonte do conhecimento (manual, lição ou handover)", BASICOS + [{"tipo": "dados", "chave": "fonte"}],
           _pergunta_da_area),
]}
# as ferramentas que todos têm ficam por último: a demanda vai para a ferramenta mais específica da pessoa
GERAIS = ("conhecimento", "historico", "laboratorio")


# =============================================================================== critérios de aceitação
def _dado(dados: dict, chave: str):
    atual = dados
    for parte in chave.split("."):
        if not isinstance(atual, dict) or parte not in atual:
            return None
        atual = atual[parte]
    return atual


def conferir_criterios(resultado: dict, criterios: list[dict]) -> list[str]:
    """Confere o resultado de uma etapa contra os critérios. Devolve os que falharam (lista vazia = aceito).
    Determinístico: nada aqui pergunta a uma IA."""
    r = resultado or {}
    falhas = []
    for c in criterios or []:
        t = c.get("tipo")
        if t == "ok" and not r.get("ok"):
            falhas.append("a ferramenta não terminou com sucesso")
        elif t == "evidencia" and not str(r.get("evidencia") or "").strip():
            falhas.append("sem evidência registrada")
        elif t == "natureza" and r.get("natureza") in (c.get("nao") or []):
            falhas.append(f"resultado de natureza '{r.get('natureza')}' não aceita")
        elif t == "texto_min" and len(str(r.get("texto") or "").strip()) < int(c.get("n", 1)):
            falhas.append(f"texto com menos de {c.get('n')} caracteres")
        elif t == "dados" and _dado(r.get("dados") or {}, c["chave"]) in (None, "", [], {}):
            falhas.append(f"faltou '{c['chave']}' nos dados do resultado")
        elif t == "linhas_min" and len((r.get("dados") or {}).get("linhas") or []) < int(c.get("n", 1)):
            falhas.append(f"menos de {c.get('n')} linha(s) devolvidas")
        elif t == "valor_unico":
            valores = list(((_dado(r.get("dados") or {}, "calculo.valores")) or {}).values())
            esperado, tol = float(c["esperado"]), float(c.get("tolerancia", 1e-6))
            if len(valores) != 1:
                falhas.append(f"esperava um único valor calculado, veio {len(valores)}")
            else:
                try:
                    v = float(valores[0])
                except (TypeError, ValueError):
                    v = math.nan
                if not math.isclose(v, esperado, rel_tol=tol, abs_tol=tol):
                    falhas.append(f"valor {v} diferente da conta independente {esperado} ({c.get('coluna')})")
    return falhas


# =============================================================================== distribuição
def _ultimas_por_pessoa(tb: Trabalho) -> tuple[dict, set]:
    """Última demanda de cada pessoa e quem tem demanda aberta."""
    ultima, abertas = {}, set()
    with tb.tx() as c:
        for r in c.execute("SELECT funcionario, estado, criada_em FROM solicitacoes WHERE origem=?", (ORIGEM,)):
            p = r["funcionario"]
            if r["criada_em"] > ultima.get(p, ""):
                ultima[p] = r["criada_em"]
            if r["estado"] not in FINAIS:
                abertas.add(p)
    return ultima, abertas


def escolher_ferramenta(cfg, pessoa: dict) -> str | None:
    """A ferramenta mais específica da pessoa (a que menos gente tem), entre as do contrato que o catálogo cobre."""
    from robo import ferramentas, organizacao
    suas = [f for f in organizacao.ferramentas_de(pessoa["id"], pessoa["andar"])
            if f in CATALOGO and f in ferramentas.REGISTRO and organizacao.pode_usar(pessoa["id"], f, cfg, producao=True)]
    if not suas:
        return None
    raridade = _raridade(cfg)
    return sorted(suas, key=lambda f: (f in GERAIS, raridade.get(f, 0), f))[0]


def _raridade(cfg) -> dict:
    from robo import organizacao
    conta: dict[str, int] = {}
    for p in organizacao.lista(cfg):
        for f in organizacao.ferramentas_de(p["id"], p["andar"]):
            conta[f] = conta.get(f, 0) + 1
    return conta


def criar_demanda(cfg, pessoa: dict, ferramenta: str) -> tuple[str | None, str]:
    """Cria a tarefa (ainda não executa). Devolve (id, '') ou (None, motivo do bloqueio)."""
    from robo import orquestrador, organizacao
    m = CATALOGO[ferramenta]
    preparado = m.preparar(cfg, pessoa) if m.preparar else ({}, [])
    if isinstance(preparado, str):
        return None, preparado
    params, extras = preparado
    criterios = list(m.criterios) + list(extras)
    revisor = organizacao.revisor_de(pessoa["id"], cfg)
    pedido = (f"Objetivo: {m.objetivo}\nResponsável: {pessoa['nome']} ({pessoa['papel']}), {pessoa['andar']}º andar.\n"
              f"Evidência esperada: {m.evidencia}.\nCritérios de aceitação: "
              + "; ".join(_texto_criterio(c) for c in criterios) + ".\nDados: sintéticos (fábrica), nunca produção.")
    return orquestrador.criar_demanda(cfg, m.titulo, pedido, pessoa["id"], ferramenta, params, revisor,
                                      plano_extra={"objetivo": m.objetivo, "evidencia_esperada": m.evidencia,
                                                   "criterios": criterios, "dados": "sintetico", "nivel": "basico"}), ""


def _texto_criterio(c: dict) -> str:
    return {"ok": "a ferramenta termina com sucesso", "evidencia": "evidência registrada",
            "natureza": "não pode ser só limitação", "texto_min": f"resposta com pelo menos {c.get('n')} caracteres",
            "dados": f"o resultado traz '{c.get('chave')}'", "linhas_min": f"pelo menos {c.get('n')} linha(s) do banco",
            "valor_unico": f"o valor bate com a conta independente de {c.get('coluna')}"}.get(c.get("tipo"), c.get("tipo", ""))


def _executar_com_job(cfg, sid: str, pid: str, ferramenta: str) -> str:
    """Executa a demanda dentro de um job aberto: enquanto roda, a pessoa aparece como TRABALHANDO (status honesto,
    robo/jobs.py); ao terminar, o job fecha com a solicitação como evidência."""
    from robo import jobs, orquestrador
    jid = jobs.abrir(cfg, "demanda", "sintetico", None, pid)
    jobs.etapa(cfg, jid, ferramenta, pid)
    estado = "falhou"
    try:
        estado = orquestrador.executar(cfg, sid)
    finally:
        jobs.fechar(cfg, jid, "concluido" if estado == "concluida" else "falhou", {"solicitacao": sid, "estado": estado})
    return estado


def rotina(cfg, agora: datetime | None = None) -> dict | None:
    """Um ciclo de distribuição. Devolve o resumo (None = fora do horário: não é trabalho)."""
    from robo import organizacao, orquestrador
    c = _c(cfg)
    if not c["habilitada"]:
        return None
    agora = agora or datetime.now()
    tb = _tb(cfg)
    with tb.tx() as conn:
        ult = conn.execute("SELECT MAX(data_hora) FROM demandas_ciclos").fetchone()[0]
        hoje = conn.execute("SELECT COUNT(*) FROM solicitacoes WHERE origem=? AND criada_em>=?",
                            (ORIGEM, agora.strftime("%Y-%m-%d"))).fetchone()[0]
    if ult and agora - datetime.fromisoformat(ult) < timedelta(minutes=float(c["intervalo_minutos"])):
        return None
    ultima, abertas = _ultimas_por_pessoa(tb)
    limite_pessoa = (agora - timedelta(hours=float(c["por_pessoa_horas"]))).isoformat(timespec="seconds")
    gente = organizacao.lista(cfg)
    puladas, candidatas = [], []
    for p in gente:
        nivel = organizacao.nivel_de(p["id"], p)
        if nivel in NIVEIS_SEM_DEMANDA:
            puladas.append({"funcionario": p["id"], "motivo": NIVEIS_SEM_DEMANDA[nivel]})
        elif p["id"] in abertas:
            puladas.append({"funcionario": p["id"], "motivo": "já tem uma demanda aberta"})
        elif ultima.get(p["id"], "") > limite_pessoa:
            puladas.append({"funcionario": p["id"], "motivo": f"recebeu demanda há menos de {c['por_pessoa_horas']} h"})
        else:
            candidatas.append(p)
    # quem está há mais tempo sem demanda primeiro (nunca recebeu = primeiro de todos); empate: andar e id
    candidatas.sort(key=lambda p: (ultima.get(p["id"], ""), p["andar"], p["id"]))
    vagas = max(0, min(int(c["por_ciclo"]), int(c["por_dia"]) - hoje))
    atribuidas, bloqueadas, finais = [], [], {}
    for p in candidatas:
        if len(atribuidas) >= vagas:
            break
        ferr = escolher_ferramenta(cfg, p)
        if not ferr:
            bloqueadas.append({"funcionario": p["id"], "motivo": "nenhuma ferramenta do contrato está no catálogo de demandas"})
            continue
        sid, motivo = criar_demanda(cfg, p, ferr)
        if not sid:
            bloqueadas.append({"funcionario": p["id"], "ferramenta": ferr, "motivo": motivo})
            continue
        atribuidas.append({"funcionario": p["id"], "ferramenta": ferr, "solicitacao": sid})
        finais[sid] = _executar_com_job(cfg, sid, p["id"], ferr)  # executa já: nuvem e notebook veem o resultado no ciclo
    concluidas = sum(1 for e in finais.values() if e == "concluida")
    detalhe = {"atribuidas": atribuidas, "estados": finais, "bloqueadas": bloqueadas, "puladas": puladas,
               "vagas": vagas, "hoje_antes": hoje}
    with tb.tx() as conn:
        conn.execute("INSERT INTO demandas_ciclos (data_hora, responsavel, elegiveis, atribuidas, concluidas, bloqueadas, "
                     "detalhe) VALUES (?,?,?,?,?,?,?)",
                     (agora.isoformat(timespec="seconds"), "casos_planejamento", len(candidatas), len(atribuidas),
                      concluidas, len(bloqueadas), json.dumps(detalhe, ensure_ascii=False, default=str)))
    return {"elegiveis": len(candidatas), "atribuidas": len(atribuidas), "concluidas": concluidas,
            "bloqueadas": len(bloqueadas), "estados": finais}


def cobertura(cfg) -> dict:
    """Quem já recebeu demanda, por andar (base da Etapa 4: ninguém pode ficar para trás)."""
    from robo import organizacao
    tb = _tb(cfg)
    with tb.tx() as c:
        por_pessoa = {r["funcionario"]: dict(r) for r in c.execute(
            "SELECT funcionario, COUNT(*) total, SUM(estado='concluida') concluidas, SUM(estado IN "
            "('falhou','concluida_parcialmente')) com_problema, MAX(criada_em) ultima FROM solicitacoes WHERE origem=? "
            "GROUP BY funcionario", (ORIGEM,))}
    andares: dict = {}
    for p in organizacao.lista(cfg):
        a = andares.setdefault(p["andar"], {"quadro": 0, "elegiveis": 0, "com_demanda": 0, "sem_demanda": []})
        a["quadro"] += 1
        if organizacao.nivel_de(p["id"], p) in NIVEIS_SEM_DEMANDA:
            continue
        a["elegiveis"] += 1
        if p["id"] in por_pessoa:
            a["com_demanda"] += 1
        else:
            a["sem_demanda"].append(p["id"])
    return {"andares": andares, "por_pessoa": por_pessoa}
