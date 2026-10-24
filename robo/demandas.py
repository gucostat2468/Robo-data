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
# Ritmo (pedido do dono: "todos trabalhando muito"): cada pessoa recebe trabalho do papel a cada 6 h (antes 24 h),
# o 5º andar a cada 3 h e a equipe de AWS a cada hora. 20 por ciclo de 30 min = até 960 por dia de turno contínuo.
PADRAO = {"habilitada": True, "intervalo_minutos": 30, "por_ciclo": 20, "por_dia": 600, "por_pessoa_horas": 6,
          # o 5º andar (TI, nuvem, segurança) recebe trabalho com mais frequência; a equipe de AWS mais que todos
          "horas_por_andar": {"5": 3}, "horas_por_pessoa": {"head_aws": 1, "aws_senior": 1, "cloud_aws": 1},
          "horas_sem_atividade": 48, "horas_abandono": 6, "avaliacoes_por_ciclo": 3}

# =============================================================================== a equipe de demandas (4º andar)
# Cinco funções complementares. A Sala de Casos (head_casos) planeja os CASOS DE TREINO com gabarito; esta equipe
# planeja as DEMANDAS de trabalho com as ferramentas do contrato. O avaliador responde ao head_casos, e não à
# coordenadora, para que quem avalia não seja subordinado a quem distribui.
EQUIPE_DEMANDAS = [
    {"id": "dem_coordenador", "nome": "Aurora", "cargo": "Coordenadora de Demandas", "nivel": "coordenador", "andar": 4,
     "cor": "#7C3AED", "area": "Treinamento e Avaliação",
     "escopo": ["Responde pela rotina de demandas: quando distribuir, quantas por ciclo e por dia, e quando parar",
                "Garante que ninguém fique para trás nem sobrecarregado e que nenhuma demanda use dado real",
                "Assina cada ciclo, com quem recebeu, quem foi pulado e por quê"],
     "criterios": ["Nenhum elegível sem demanda sem motivo registrado", "Teto por ciclo e por dia respeitado",
                   "Estagiário em observação"],
     "metodologias": ["Planejamento de capacidade", "Fila justa (quem espera há mais tempo primeiro)"]},
    {"id": "dem_gerador", "nome": "Vicente", "cargo": "Analista Sênior de Geração de Demandas", "nivel": "senior",
     "andar": 4, "cor": "#8B5CF6", "area": "Treinamento e Avaliação",
     "escopo": ["Monta cada demanda no nível certo (básico, médio, difícil, profissional) para o cargo e o histórico",
                "Define objetivo, evidência esperada e critérios de aceitação verificáveis de cada etapa",
                "Bloqueia, com o motivo, a demanda que não tem condição de rodar"],
     "criterios": ["Nível nunca acima do teto do cargo", "Todo critério conferível sem IA",
                   "Demanda sem condição não vira tarefa"],
     "metodologias": ["Dificuldade progressiva (sobe com acertos, desce com falha)", "Critérios de aceitação mensuráveis"]},
    {"id": "dem_distribuidor", "nome": "Isadora", "cargo": "Analista Pleno de Distribuição de Demandas", "nivel": "pleno",
     "andar": 4, "cor": "#A78BFA", "area": "Treinamento e Avaliação",
     "escopo": ["Escolhe quem recebe em cada ciclo: sem atividade há mais tempo primeiro, depois menor carga",
                "Alterna os andares para que nenhum fique para trás",
                "Registra o motivo de cada atribuição"],
     "criterios": ["Ninguém com duas demandas abertas", "Andares alternados no ciclo", "Motivo registrado"],
     "metodologias": ["Round-robin por andar", "Balanceamento de carga"]},
    {"id": "dem_cobertura", "nome": "Renan", "cargo": "Analista Pleno de Cobertura de Demandas", "nivel": "pleno",
     "andar": 4, "cor": "#6D28D9", "area": "Treinamento e Avaliação",
     "escopo": ["Mede a cobertura por andar e por área: elegíveis, com demanda, concluídas, bloqueadas e sem trabalho",
                "Encerra com o motivo a demanda abandonada e devolve a pessoa para a fila",
                "Quem ficou sem demanda adequada recebe uma demanda de treinamento ou o motivo fica registrado"],
     "criterios": ["Cobertura completa só com todos os elegíveis atendidos ou justificados",
                   "Abandono encerrado com motivo, nunca apagado"],
     "metodologias": ["Indicadores de cobertura por andar", "Gestão de exceções"]},
    {"id": "dem_avaliador", "nome": "Bento", "cargo": "Avaliador Independente de Demandas", "nivel": "especialista",
     "andar": 4, "cor": "#5B21B6", "area": "Treinamento e Avaliação",
     "escopo": ["Reavalia uma amostra das demandas aprovadas por outro caminho: critérios, revisor independente, "
                "artefatos e a conta refeita a partir do arquivo",
                "Registra confirmação ou divergência; divergência vira aprendizado do executor"],
     "criterios": ["Nunca avalia demanda que executou ou revisou", "Divergência sempre registrada"],
     "metodologias": ["Auditoria por amostragem", "Segunda linha de defesa"]},
]
POR_ID = {p["id"]: p for p in EQUIPE_DEMANDAS}
GESTORES = {"dem_coordenador": "head_casos", "dem_gerador": "dem_coordenador", "dem_distribuidor": "dem_coordenador",
            "dem_cobertura": "dem_coordenador", "dem_avaliador": "head_casos"}
RESPONSAVEL = "dem_coordenador"

# níveis de dificuldade: o que muda é o TRABALHO (mais etapas, colega de outra área, arquivo entregue), não o rótulo
NIVEIS = ("basico", "medio", "dificil", "profissional")
TETO_DO_CARGO = {"junior": "basico", "pleno": "medio", "senior": "dificil", "especialista": "dificil",
                 "coordenador": "dificil", "gerente": "profissional", "head": "profissional", "diretor": "profissional"}
SOBE_COM = 2  # demandas concluídas seguidas no nível atual para subir um nível
# 1ª demanda de cada cargo: júnior e pleno começam no básico; sênior/especialista/coordenador no médio; gerente, head
# e diretor no difícil. Daí para cima só com prova (SOBE_COM concluídas seguidas). Antes todos começavam no básico e,
# com 1 demanda a cada 6 h, o boletim real mostrou só básico (163) e médio (9): nenhum head chegou ao difícil.
INICIO_DO_CARGO = {"junior": "basico", "pleno": "basico", "senior": "medio", "especialista": "medio",
                   "coordenador": "medio", "gerente": "dificil", "head": "dificil", "diretor": "dificil"}
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
CREATE TABLE IF NOT EXISTS demandas_registro (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT NOT NULL, ciclo TEXT, funcionario TEXT NOT NULL, andar INTEGER,
  area TEXT, evento TEXT NOT NULL, nivel TEXT, ferramenta TEXT, solicitacao TEXT, motivo TEXT, responsavel TEXT);
CREATE INDEX IF NOT EXISTS ix_demreg_func ON demandas_registro(funcionario, data_hora);
CREATE TRIGGER IF NOT EXISTS demandas_registro_imutavel BEFORE UPDATE ON demandas_registro
BEGIN SELECT RAISE(ABORT, 'registro de demanda é permanente: não se altera'); END;
CREATE TABLE IF NOT EXISTS demandas_avaliacoes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT NOT NULL, solicitacao TEXT NOT NULL UNIQUE, avaliador TEXT,
  executores TEXT, revisor TEXT, nivel TEXT, veredito TEXT NOT NULL, achados TEXT);
CREATE TRIGGER IF NOT EXISTS demandas_avaliacoes_imutavel BEFORE UPDATE ON demandas_avaliacoes
BEGIN SELECT RAISE(ABORT, 'avaliação independente é permanente: não se altera'); END;
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
    """Drivers precisam de um alvo NPS ou CSAT (mesma regra da ferramenta, calculos._coluna_indicador) E de atributos
    numéricos para comparar: sem eles a tarefa é impossível e falhava sem culpa de quem a recebeu (achado no turno da
    nuvem: a NPS da fábrica só tinha a nota). Quando a fábrica guardou a verdade dos drivers, ela vira critério."""
    from robo.calculos import _coluna_indicador
    from robo.ciencia import _numericas
    bases = _recentes(Path(cfg.tratadas) / "_treino")
    sem_atributo = 0
    for arq in bases:
        df = _ler(arq)
        alvo = _coluna_indicador("nps", df) or _coluna_indicador("csat", df)
        if not alvo:
            continue
        if not _numericas(df, [alvo]):
            sem_atributo += 1
            continue
        verdade = _verdade_dos_drivers(cfg, arq)
        extras = [{"tipo": "primeiro_driver", "esperado": verdade["ordem"][0]}] if verdade else []
        return {"arquivo": str(arq)}, extras
    if sem_atributo:
        return (f"{sem_atributo} base(s) com NPS/CSAT, mas sem atributo numérico (nota de atendimento, conteúdo…) para "
                "comparar com o indicador: drivers não têm o que medir")
    return (f"nenhuma das {len(bases)} base(s) sintética(s) recentes tem coluna de NPS ou CSAT para ser o alvo "
            "(a fábrica gera as regras nps e csat_ces; a demanda volta quando houver um lote delas)")


def _verdade_dos_drivers(cfg, arquivo: Path) -> dict | None:
    """A ordem verdadeira dos drivers, do gabarito que a fábrica guardou ao gerar o lote (fabrica_lotes)."""
    try:
        with _tb(cfg).tx() as c:
            r = c.execute("SELECT gabarito FROM fabrica_lotes WHERE arquivo LIKE ? ORDER BY id DESC LIMIT 1",
                          (f"%{Path(arquivo).name}",)).fetchone()
    except Exception:
        return None
    try:
        return (json.loads(r[0] or "{}").get("drivers") or None) if r else None
    except ValueError:
        return None


def _ml_para_treinar(cfg, pessoa):
    """Só há o que treinar com dados suficientes e novos (treinar o mesmo dataset de novo não ensina nada)."""
    from robo import modelos_ml as ml
    n = len(ml._linhas_rotuladas(cfg))
    if n < ml.CRITERIOS["min_linhas"]:
        return f"só {n} demanda(s) fechada(s) rotulada(s); o primeiro treino precisa de {ml.CRITERIOS['min_linhas']}"
    with ml._tb(cfg).tx() as c:
        ultimo = c.execute("SELECT COALESCE(MAX(d.linhas),0) FROM ml_datasets d JOIN ml_experimentos e "
                           "ON e.dataset_id=d.id").fetchone()[0] or 0
    if ultimo and n - ultimo < ml.CRITERIOS["crescimento_para_retreino"]:
        return (f"o dataset cresceu {n - ultimo} demanda(s) desde o último treino; retreino a partir de "
                f"{ml.CRITERIOS['crescimento_para_retreino']}")
    return {}, []


def _ml_para_avaliar(cfg, pessoa):
    """Só avalia candidato que OUTRA pessoa treinou."""
    from robo import modelos_ml as ml
    pend = [m for m in ml._modelos(cfg) if m["estado"] == "candidato" and m["criado_por"] != pessoa["id"]]
    if not pend:
        return "nenhum modelo candidato esperando avaliação independente"
    return {}, []


def _sql_lotes(cfg, pessoa):
    """Leitura real no PostgreSQL: os lotes sintéticos que a esteira gravou no schema treino (demanda consulta_sql).
    Antes tinha o mesmo nome do preparo do exercício de SQL e era substituída por ele: toda consulta_sql falhava."""
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


def _sql(cfg, pessoa):
    """Exercício de SQL: um lote da fábrica que já está no PostgreSQL e tem gabarito conferido. Cada pessoa pega um lote
    diferente (rodízio pelo id), para a turma não responder sempre a mesma pergunta."""
    if not (cfg.banco or {}).get("habilitado"):
        return "PostgreSQL desligado nas Configurações: exercício de SQL não roda"
    from robo import sql_treino
    try:
        lotes = sql_treino.lotes_no_banco(cfg, sql_treino.lotes_com_gabarito(cfg))
    except Exception as e:
        return f"PostgreSQL indisponível ({type(e).__name__})"
    if not lotes:
        return "nenhum lote da fábrica conferido está no PostgreSQL ainda (schema treino)"
    import zlib
    lote = lotes[zlib.crc32(pessoa["id"].encode()) % len(lotes)]
    return ({"regra": lote["regra"], "arquivo": lote["arquivo"], "gabarito": lote["gabarito"]},
            [{"tipo": "verdadeiro", "chave": "confere"}])


COMPETENCIAS_REVISAVEIS = ("limpeza", "calculo", "indicadores", "lgpd", "anomalias", "segmentacao", "drivers")


def _caso_para_revisar(cfg, pessoa):
    """Sala de Casos: um caso de treino validado e recente, feito por OUTRO designer (ninguém revisa o que criou)."""
    from robo import treino
    with treino._tb(cfg).tx() as c:
        linhas = c.execute(
            "SELECT * FROM treino_casos WHERE estado='validado' AND designer<>? AND competencia IN (%s) "
            "ORDER BY criado_em DESC LIMIT 30" % ",".join("?" * len(COMPETENCIAS_REVISAVEIS)),
            (pessoa["id"], *COMPETENCIAS_REVISAVEIS)).fetchall()
    for r in linhas:
        if r["arquivo"] and not Path(r["arquivo"]).exists():
            continue  # arquivo de outra máquina (cada turno da nuvem começa numa nova) ou guardado no arquivo morto
        caso = {**treino._carregar(r), "sha": r["conteudo_sha256"]}
        return {"caso": caso}, []
    # nenhum caso com arquivo nesta máquina: a Sala produz um caso novo (o designer da competência cria, o revisor da
    # Sala valida) e esta pessoa faz a revisão independente dele. Nunca revisa o que ela mesma criou.
    from robo.treino_casos import CATALOGO as COMPETENCIAS
    import zlib
    ordem = sorted(COMPETENCIAS_REVISAVEIS, key=lambda x: zlib.crc32(f"{pessoa['id']}{_agora()[:13]}{x}".encode()))
    for comp in ordem:
        if COMPETENCIAS[comp].designer == pessoa["id"]:
            continue
        try:
            novo = treino.criar_caso(cfg, comp, 3)
        except Exception:
            continue
        if novo.get("estado") == "validado":
            with treino._tb(cfg).tx() as c:
                r = c.execute("SELECT * FROM treino_casos WHERE id=?", (novo["id"],)).fetchone()
            return {"caso": {**treino._carregar(r), "sha": r["conteudo_sha256"]}}, []
    return "nenhum caso de treino validado de outro designer disponível para revisão agora"


def _pergunta_da_area(cfg, pessoa):
    from robo import organizacao
    area = organizacao.area_de(pessoa["id"]) or "dados"
    return ({"pergunta": f"boas práticas de {area}"}, [])


def _pergunta_da_ferramenta(cfg, ferramenta: str) -> dict:
    """A pergunta do nível difícil é sobre o TRABALHO da pessoa (a ferramenta), não genérica: assim a resposta ou é
    específica ou é um 'não sei' honesto, que mostra uma lacuna real no conhecimento da empresa."""
    from robo import ferramentas
    f = ferramentas.REGISTRO.get(ferramenta)
    return {"pergunta": f"{f.nome}: {f.descricao}" if f else ferramenta, "especifico": True}


def secoes_genericas() -> set[str]:
    """Títulos de abertura dos manuais (o '# Título' de cada .md): falam da empresa toda, não do trabalho de ninguém."""
    from robo.config import RAIZ_PROJETO
    titulos = set()
    for arq in (RAIZ_PROJETO / "conhecimento").glob("*.md"):
        for linha in arq.read_text(encoding="utf-8").splitlines():
            if linha.startswith("# "):
                titulos.add(linha[2:].strip())
                break
    return titulos


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
           "linhas devolvidas pelo PostgreSQL", BASICOS, _sql_lotes),
    Modelo("sql_treino", "Exercício de SQL no PostgreSQL com os dados da fábrica",
           "Responder com SQL (somente leitura) uma pergunta sobre um lote real do banco, e bater com o gabarito.",
           "o SQL, o resultado do banco e a conferência com o gabarito do lote", BASICOS, _sql),
    Modelo("restauracao_backup", "Testar se o último backup volta",
           "Restaurar o backup mais recente numa pasta temporária e provar que ele está íntegro e completo.",
           "integridade, tabelas e linhas do backup restaurado", BASICOS + [{"tipo": "dados", "chave": "integridade"}]),
    Modelo("prontidao_nuvem", "Conferir se o projeto está pronto para servidor",
           "Checar Dockerfile, usuário sem root, porta por variável e segredos fora do repositório.",
           "cada item conferido com ok ou não", BASICOS + [{"tipo": "dados", "chave": "itens"}]),
    Modelo("postgres_saude", "Medir a saúde do PostgreSQL",
           "Medir espaço contra o limite do plano, linhas mortas, conexões e consultas presas.",
           "tamanho do banco, schemas, conexões", BASICOS + [{"tipo": "dados", "chave": "mb"}]),
    Modelo("segredos_repo", "Procurar segredos no repositório público",
           "Varrer os arquivos versionados atrás de senha, token e chave escritos.",
           "arquivos lidos e achados (sem mostrar o segredo)", BASICOS + [{"tipo": "dados", "chave": "arquivos_lidos"}]),
    Modelo("ml_treinar", "Treinar o modelo de risco de demanda",
           "Montar o dataset versionado (corte temporal, sem vazamento), treinar baseline e candidato e medir no teste.",
           "experimento registrado com dataset, parâmetros, métricas e checksum",
           BASICOS + [{"tipo": "dados", "chave": "experimento"}], _ml_para_treinar),
    Modelo("ml_avaliar", "Avaliar de forma independente o modelo candidato",
           "Refazer as métricas do arquivo do modelo e do dataset, por outro caminho, e aprovar ou reprovar com motivo.",
           "decisão com motivos e métricas refeitas", BASICOS + [{"tipo": "dados", "chave": "decisao"}], _ml_para_avaliar),
    Modelo("ml_registro", "Integridade, promoção e monitoramento dos modelos",
           "Conferir o checksum de cada artefato, promover só o aprovado por outra pessoa e monitorar a sombra.",
           "artefatos conferidos e eventos do registro de modelos", BASICOS),
    Modelo("ml_portfolio", "Programa de modelos: backlog e critérios",
           "Atualizar o backlog de ML com o estado real de cada caso e o que falta para o próximo passo.",
           "backlog com estado real e critérios de promoção", BASICOS),
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
    Modelo("revisar_caso", "Revisar um caso de treino feito por outro designer",
           "Conferir de forma independente um caso de treino: íntegro, reprodutível pela semente e com gabarito certo.",
           "integridade, reprodução e conferência do caso por outro caminho", BASICOS, _caso_para_revisar),
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
        elif t == "verdadeiro" and _dado(r.get("dados") or {}, c["chave"]) is not True:
            falhas.append(f"'{c['chave']}' não é verdadeiro no resultado"
                          + (": " + "; ".join((r.get("dados") or {}).get("diferencas") or [])
                             if (r.get("dados") or {}).get("diferencas") else ""))
        elif t == "fonte_especifica" and any(f"“{g}”" in str(r.get("evidencia") or "") for g in c.get("genericas") or []):
            falhas.append("a fonte é a abertura genérica de um manual, não um conhecimento sobre este trabalho")
        elif t == "artefato":
            arqs = [Path(x) for x in r.get("artefatos") or []]
            if not arqs:
                falhas.append("nenhum arquivo entregue")
            elif not all(x.exists() and x.stat().st_size > 0 for x in arqs):
                falhas.append("arquivo entregue não existe ou está vazio")
        elif t == "primeiro_driver":
            lista = _dado(r.get("dados") or {}, "drivers.drivers") or []
            achado = lista[0].get("atributo") if lista and isinstance(lista[0], dict) else None
            if achado != c.get("esperado"):
                falhas.append(f"o driver principal achado foi '{achado}', mas o gabarito da fábrica diz '{c.get('esperado')}'")
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




def _texto_criterio(c: dict) -> str:
    return {"ok": "a ferramenta termina com sucesso", "evidencia": "evidência registrada",
            "natureza": "não pode ser só limitação", "texto_min": f"resposta com pelo menos {c.get('n')} caracteres",
            "dados": f"o resultado traz '{c.get('chave')}'", "linhas_min": f"pelo menos {c.get('n')} linha(s) do banco",
            "valor_unico": f"o valor bate com a conta independente de {c.get('coluna')}",
            "artefato": "arquivo entregue e não vazio",
            "fonte_especifica": "conhecimento específico do trabalho (não a abertura genérica de um manual)",
            "verdadeiro": "o resultado do banco bate com o gabarito",
            "primeiro_driver": f"o driver principal é o do gabarito da fábrica ({c.get('esperado')})"}.get(c.get("tipo"), c.get("tipo", ""))


# =============================================================================== Vicente: nível e montagem
def _historico(tb: Trabalho, pid: str, limite: int = 10) -> list[dict]:
    """Últimas demandas da pessoa (mais recente primeiro), com o nível de cada uma."""
    with tb.tx() as c:
        linhas = [dict(r) for r in c.execute(
            "SELECT id, estado, plano, modelo, criada_em FROM solicitacoes WHERE origem=? AND funcionario=? "
            "ORDER BY criada_em DESC, id DESC LIMIT ?", (ORIGEM, pid, limite))]
    for l in linhas:
        try:
            plano = json.loads(l.pop("plano") or "{}") or {}
        except ValueError:
            plano = {}
        l["nivel"] = plano.get("nivel") or "basico"
        l["tipo_demanda"] = plano.get("tipo_demanda") or "trabalho"
    return linhas


def nivel_para(cargo: str, historico: list[dict]) -> tuple[str, str]:
    """(nível, motivo). Começa no básico; sobe um nível depois de SOBE_COM concluídas seguidas no nível atual; desce um
    depois de uma FALHA; nunca passa do teto do cargo. Só conta demanda de trabalho (a de treinamento não mexe no nível).
    'Concluída parcialmente' mantém o nível: costuma ser lacuna da EMPRESA (ex.: conhecimento que não existe), não erro
    de quem executou; não sobe nem desce."""
    teto = TETO_DO_CARGO.get(cargo, "basico")
    # cancelada = abandonada (o robô caiu, por exemplo): não é mérito nem culpa da pessoa, não entra na conta
    hist = [h for h in historico if h.get("tipo_demanda", "trabalho") == "trabalho" and h["estado"] in FINAIS
            and h["estado"] != "cancelada"]
    if not hist:
        inicio = INICIO_DO_CARGO.get(cargo, "basico")
        if NIVEIS.index(inicio) > NIVEIS.index(teto):
            inicio = teto
        return inicio, f"primeira demanda: começa no {inicio} (início do cargo {cargo}; sobe só com entregas concluídas)"
    atual = hist[0]["nivel"] if hist[0]["nivel"] in NIVEIS else "basico"
    inicio = INICIO_DO_CARGO.get(cargo, "basico")
    if NIVEIS.index(inicio) > NIVEIS.index(teto):
        inicio = teto
    # recalibração: quem NUNCA trabalhou no nível de início do cargo (histórico de antes desta regra) e não falhou na
    # última vai para ele; quem já esteve lá e caiu por falha segue a regra normal (desce, prova, sobe)
    if hist[0]["estado"] != "falhou" and all(NIVEIS.index(h["nivel"]) < NIVEIS.index(inicio)
                                             for h in hist if h["nivel"] in NIVEIS):
        return inicio, f"recalibrado para o início do cargo ({cargo}: {inicio}); o histórico era todo abaixo dele"
    i = NIVEIS.index(atual)
    if hist[0]["estado"] == "falhou":
        novo, motivo = NIVEIS[max(0, i - 1)], f"a última ({hist[0]['estado']}) não foi concluída: desce para revisar a base"
    elif len(hist) >= SOBE_COM and all(h["nivel"] == atual and h["estado"] == "concluida" for h in hist[:SOBE_COM]):
        novo, motivo = NIVEIS[min(len(NIVEIS) - 1, i + 1)], f"{SOBE_COM} concluídas seguidas no {atual}: sobe um nível"
    else:
        novo, motivo = atual, f"mantém o {atual} até {SOBE_COM} concluídas seguidas"
    if NIVEIS.index(novo) > NIVEIS.index(teto):
        return teto, f"{motivo}; limitado ao teto do cargo ({cargo}: {teto})"
    return novo, motivo


def _colega(cfg, ferramenta: str, exceto: str) -> str | None:
    """Um colega (nunca a própria pessoa) que pode usar a ferramenta: o responsável padrão primeiro."""
    from robo import organizacao
    for c in (organizacao.ENCAMINHAR.get(ferramenta),):
        if c and c != exceto and organizacao.pode_usar(c, ferramenta, cfg, producao=True):
            return c
    for p in organizacao.lista(cfg, com_contratados=False):
        if p["id"] != exceto and organizacao.pode_usar(p["id"], ferramenta, cfg, producao=True):
            return p["id"]
    return None


def montar(cfg, pessoa: dict, ferramenta: str, nivel: str = "basico", estudo_de: str | None = None) -> dict | str:
    """O plano da demanda no nível pedido: {titulo, etapas, criterios_por_etapa, ...} ou o motivo de não dar para montar.
      básico        1 etapa: a ferramenta da pessoa;
      médio         + resumo executivo (.md) das etapas: entrega um arquivo;
      difícil       + consulta ao conhecimento da empresa sobre a própria área antes do resumo;
      profissional  + conferência cruzada por um colega de outra área (LGPD na mesma base, ou a situação do andar)."""
    m = CATALOGO[ferramenta]
    if estudo_de:  # treinamento: estudar o assunto da demanda que ficou bloqueada (compatível com o trabalho da pessoa)
        preparado = (_pergunta_da_ferramenta(cfg, estudo_de), [])
    else:
        preparado = m.preparar(cfg, pessoa) if m.preparar else ({}, [])
    if isinstance(preparado, str):
        return preparado
    params, extras = preparado
    if ferramenta == "sql_treino":  # o exercício de SQL tem o nível da demanda (contagem → reconciliação com CTE)
        params = {**params, "nivel": nivel}
    if ferramenta == "conhecimento":  # estudo só vale com conhecimento específico, nunca a abertura de um manual
        params = {**params, "especifico": True}
        extras = list(extras) + [{"tipo": "fonte_especifica", "genericas": sorted(secoes_genericas())}]
    pid = pessoa["id"]
    etapas = [{"titulo": m.titulo, "ferramenta": ferramenta, "funcionario": pid, "parametros": params}]
    crits = {1: list(m.criterios) + list(extras)}
    if nivel in ("dificil", "profissional") and ferramenta != "conhecimento":
        etapas.append({"titulo": "Consultar o que a empresa já sabe sobre este trabalho", "ferramenta": "conhecimento",
                       "funcionario": pid, "parametros": _pergunta_da_ferramenta(cfg, ferramenta)})
        crits[len(etapas)] = [{"tipo": "ok"}, {"tipo": "evidencia"},
                              {"tipo": "fonte_especifica", "genericas": sorted(secoes_genericas())}]
    if nivel == "profissional":
        conferir = []
        if ferramenta == "sql_treino":
            # o "arquivo" do SQL é o nome do lote no banco, não uma planilha: o colega (o DBA primeiro) refaz o lote por
            # OUTRA consulta (soma e média da métrica) e confere com o mesmo gabarito
            cruz, titulo = "sql_treino", "Conferência cruzada: o mesmo lote por outra consulta (soma e média)"
            p3 = {**params, "nivel": "medio"}
            conferir = [{"tipo": "verdadeiro", "chave": "confere"}]
        elif params.get("arquivo"):
            cruz, p3, titulo = "dados_pessoais", {"arquivo": params["arquivo"]}, "Conferência cruzada: dados pessoais (LGPD)"
        else:
            cruz, p3, titulo = "reuniao_andar", {"andar": pessoa["andar"]}, "Conferência cruzada: situação do andar"
        colega = _colega(cfg, cruz, pid)
        if not colega:
            return f"ninguém além de {pid} pode fazer a conferência cruzada ({cruz})"
        etapas.append({"titulo": titulo, "ferramenta": cruz, "funcionario": colega, "parametros": p3})
        crits[len(etapas)] = list(BASICOS) + conferir
    if nivel != "basico":
        etapas.append({"titulo": "Resumo executivo das etapas (.md)", "ferramenta": "resumo_executivo", "funcionario": pid,
                       "parametros": {}, "depende": list(range(1, len(etapas) + 1))})
        crits[len(etapas)] = [{"tipo": "ok"}, {"tipo": "artefato"}]
    titulo = m.titulo if nivel == "basico" else f"{m.titulo} — nível {nivel}"
    return {"titulo": titulo, "etapas": etapas, "criterios_por_etapa": {str(k): v for k, v in crits.items()},
            "objetivo": m.objetivo, "evidencia_esperada": m.evidencia}


def criar_demanda(cfg, pessoa: dict, ferramenta: str, nivel: str = "basico", tipo: str = "trabalho",
                  motivo_nivel: str = "", estudo_de: str | None = None) -> tuple[str | None, str]:
    """Cria a tarefa (não executa). Devolve (id, '') ou (None, motivo do bloqueio)."""
    from robo import orquestrador, organizacao
    plano = montar(cfg, pessoa, ferramenta, nivel, estudo_de)
    if isinstance(plano, str):
        return None, plano
    revisor = organizacao.revisor_de(pessoa["id"], cfg)
    todos = [c for v in plano["criterios_por_etapa"].values() for c in v]
    pedido = (f"Objetivo: {plano['objetivo']}\nResponsável: {pessoa['nome']} ({pessoa['papel']}), {pessoa['andar']}º andar.\n"
              f"Nível: {nivel}" + (f" ({motivo_nivel})" if motivo_nivel else "") + f". Etapas: {len(plano['etapas'])}.\n"
              f"Evidência esperada: {plano['evidencia_esperada']}.\nCritérios de aceitação: "
              + "; ".join(dict.fromkeys(_texto_criterio(c) for c in todos)) + ".\nDados: sintéticos (fábrica), nunca produção.")
    sid = orquestrador.criar_demanda(
        cfg, plano["titulo"], pedido, pessoa["id"], plano["etapas"], revisor,
        plano_extra={"objetivo": plano["objetivo"], "evidencia_esperada": plano["evidencia_esperada"],
                     "criterios_por_etapa": plano["criterios_por_etapa"], "dados": "sintetico", "nivel": nivel,
                     "tipo_demanda": tipo, "gerada_por": "dem_gerador", "motivo_nivel": motivo_nivel})
    return sid, ""


# =============================================================================== Isadora: quem recebe
def _estado_das_demandas(tb: Trabalho, agora: datetime) -> dict:
    """Por pessoa: última demanda, última concluída, abertas e carga dos últimos 7 dias."""
    sete = (agora - timedelta(days=7)).isoformat(timespec="seconds")
    por: dict = {}
    with tb.tx() as c:
        for r in c.execute("SELECT id, funcionario, estado, criada_em, atualizada_em, plano FROM solicitacoes WHERE origem=?",
                           (ORIGEM,)):
            p = por.setdefault(r["funcionario"], {"ultima": "", "ultima_concluida": "", "abertas": [], "carga_7d": 0})
            # estudo dado porque o trabalho do papel estava BLOQUEADO não ocupa a vez da pessoa: no próximo ciclo ela
            # volta a ser candidata a trabalho de verdade (antes ficava 6 h presa no estudo)
            try:
                estudo = (json.loads(r["plano"] or "{}") or {}).get("tipo_demanda") == "treinamento"
            except ValueError:
                estudo = False
            if not estudo:
                p["ultima"] = max(p["ultima"], r["criada_em"])
            if r["estado"] == "concluida":
                p["ultima_concluida"] = max(p["ultima_concluida"], r["atualizada_em"] or r["criada_em"])
            if r["estado"] not in FINAIS:
                p["abertas"].append({"id": r["id"], "criada_em": r["criada_em"]})
            if r["criada_em"] >= sete:
                p["carga_7d"] += 1
    return por


def ordenar(candidatas: list[dict], estado: dict, agora: datetime, horas_sem_atividade: float) -> list[tuple[dict, str]]:
    """Fila justa: (1) quem nunca recebeu, (2) quem está sem demanda concluída há mais de `horas_sem_atividade`,
    (3) os demais; dentro de cada grupo, quem espera há mais tempo e com menor carga. Depois alterna os andares
    (round-robin) para nenhum andar ficar para trás no ciclo. Devolve (pessoa, motivo)."""
    corte = (agora - timedelta(hours=horas_sem_atividade)).isoformat(timespec="seconds")

    def chave(p):
        e = estado.get(p["id"]) or {}
        if not e.get("ultima"):
            return (0, "", 0, p["id"]), "nunca recebeu demanda"
        if (e.get("ultima_concluida") or "") < corte:
            return (1, e["ultima"], e["carga_7d"], p["id"]), f"sem demanda concluída há mais de {horas_sem_atividade:g} h"
        return (2, e["ultima"], e["carga_7d"], p["id"]), f"última demanda em {e['ultima'][:16]}; carga de {e['carga_7d']} em 7 dias"
    marcadas = sorted(((chave(p), p) for p in candidatas), key=lambda x: x[0][0])
    por_andar: dict[int, list] = {}
    for (k, motivo), p in marcadas:
        por_andar.setdefault(int(p["andar"]), []).append((k, p, motivo))
    # round-robin respeitando a prioridade: a cada volta, cada andar entrega o seu próximo da fila
    saida = []
    while any(por_andar.values()):
        volta = sorted((fila.pop(0) for fila in por_andar.values() if fila), key=lambda x: x[0])
        saida += [(p, motivo) for _, p, motivo in volta]
    return saida


# =============================================================================== Renan: abandono e cobertura
def encerrar_abandonadas(cfg, tb: Trabalho, estado: dict, agora: datetime, horas: float) -> list[dict]:
    """Demanda aberta há mais de `horas` (o robô caiu no meio, por exemplo) é encerrada como cancelada, com o motivo,
    em nome de quem fez isso (dem_cobertura, nunca o dono). Nada é apagado; a pessoa volta para a fila."""
    corte = (agora - timedelta(hours=horas)).isoformat(timespec="seconds")
    feitas = []
    for pid, e in estado.items():
        for a in list(e["abertas"]):
            if a["criada_em"] >= corte:
                continue
            motivo = f"aberta desde {a['criada_em'][:16]} sem terminar (mais de {horas:g} h): encerrada para reatribuir"
            s = tb.solicitacao(a["id"])
            tb.mudar_estado(a["id"], "cancelada", "dem_cobertura", motivo)
            for et in (s or {}).get("etapas", []):
                if et["estado"] in ("pendente", "aguardando_dependencia", "aguardando_aprovacao", "em_execucao"):
                    tb.atualizar_etapa(et["id"], "dem_cobertura", estado="cancelada")
            e["abertas"].remove(a)
            feitas.append({"funcionario": pid, "solicitacao": a["id"], "motivo": motivo})
    return feitas


def cobertura(cfg, dias: int = 7, agora: datetime | None = None) -> dict:
    """Indicadores verificáveis de cobertura por andar e por área, na janela de `dias`. 'completa' só é verdade se
    todo elegível recebeu demanda na janela ou tem justificativa registrada (pulado/bloqueado com motivo)."""
    from robo import organizacao
    agora = agora or datetime.now()
    desde = (agora - timedelta(days=dias)).isoformat(timespec="seconds")
    tb = _tb(cfg)
    with tb.tx() as c:
        por_pessoa = {r["funcionario"]: dict(r) for r in c.execute(
            "SELECT funcionario, COUNT(*) total, SUM(estado='concluida') concluidas, SUM(estado IN "
            "('falhou','concluida_parcialmente','cancelada')) com_problema, MAX(criada_em) ultima FROM solicitacoes "
            "WHERE origem=? AND criada_em>=? GROUP BY funcionario", (ORIGEM, desde))}
        justificadas = {r["funcionario"]: r["motivo"] for r in c.execute(
            "SELECT funcionario, motivo FROM demandas_registro WHERE evento IN ('pulada','bloqueada','sem_trabalho') "
            "AND data_hora>=? ORDER BY id", (desde,))}
    andares: dict = {}
    areas: dict = {}
    for p in organizacao.lista(cfg):
        area = organizacao.area_de(p["id"]) or "sem área"
        for grupo, chave in ((andares, p["andar"]), (areas, area)):
            g = grupo.setdefault(chave, {"quadro": 0, "elegiveis": 0, "com_demanda": 0, "concluidas": 0, "com_problema": 0,
                                         "sem_demanda": [], "justificados": {}})
            g["quadro"] += 1
            if organizacao.nivel_de(p["id"], p) in NIVEIS_SEM_DEMANDA:
                g["justificados"][p["id"]] = NIVEIS_SEM_DEMANDA["estagiario"]
                continue
            g["elegiveis"] += 1
            pp = por_pessoa.get(p["id"])
            if pp:
                g["com_demanda"] += 1
                g["concluidas"] += int(pp["concluidas"] or 0)
                g["com_problema"] += int(pp["com_problema"] or 0)
            elif p["id"] in justificadas:
                g["justificados"][p["id"]] = justificadas[p["id"]]
            else:
                g["sem_demanda"].append(p["id"])
    for grupo in (andares, areas):
        for g in grupo.values():
            g["completa"] = not g["sem_demanda"]
    return {"janela_dias": dias, "andares": andares, "areas": areas, "por_pessoa": por_pessoa,
            "completa": all(g["completa"] for g in andares.values())}


# =============================================================================== Bento: avaliação independente
def avaliar(cfg, limite: int = 3, agora: datetime | None = None) -> list[dict]:
    """Segunda linha: reavalia demandas concluídas ainda não avaliadas (as mais recentes, uma por executor) sem
    olhar o veredito do revisor. Confere: revisor diferente de todos os executores; critérios de cada etapa de novo;
    arquivos entregues; e a conta do cálculo refeita a partir do ARQUIVO (não do valor guardado na demanda)."""
    from robo import aprendizados
    tb = _tb(cfg)
    with tb.tx() as c:
        feitas = {r[0] for r in c.execute("SELECT solicitacao FROM demandas_avaliacoes")}
        candidatas = [r["id"] for r in c.execute(
            "SELECT id FROM solicitacoes WHERE origem=? AND estado='concluida' ORDER BY atualizada_em DESC LIMIT 200",
            (ORIGEM,))]
    saida, vistos = [], set()
    for sid in candidatas:
        if len(saida) >= limite or sid in feitas:
            continue
        s = tb.solicitacao(sid)
        executores = {e["funcionario"] for e in s["etapas"]}
        if "dem_avaliador" in executores or s["revisor"] == "dem_avaliador" or s["funcionario"] in vistos:
            continue  # nunca avalia o que fez ou revisou; uma por executor por ciclo
        vistos.add(s["funcionario"])
        achados = []
        if s["revisor"] in executores or s["revisor"] == "dono":
            achados.append(f"revisor {s['revisor']} não é independente")
        crits = (s.get("plano") or {}).get("criterios_por_etapa") or {}
        for e in s["etapas"]:
            achados += [f"etapa {e['ordem']}: {x}" for x in conferir_criterios(e["resultado"], crits.get(str(e["ordem"])))]
            for c in crits.get(str(e["ordem"])) or []:
                if c.get("tipo") == "valor_unico" and e["parametros"].get("arquivo"):
                    achados += _refazer_conta(e, c)
        veredito = "divergente" if achados else "confirmada"
        with tb.tx() as c:
            c.execute("INSERT INTO demandas_avaliacoes (data_hora, solicitacao, avaliador, executores, revisor, nivel, veredito, "
                      "achados) VALUES (?,?,?,?,?,?,?,?)",
                      ((agora or datetime.now()).isoformat(timespec="seconds"), sid, "dem_avaliador",
                       ",".join(sorted(executores)), s["revisor"], (s.get("plano") or {}).get("nivel"), veredito,
                       json.dumps(achados, ensure_ascii=False)))
        if achados:  # divergência vira aprendizado de quem executou (a causa fica registrada, sem apagar a aprovação)
            try:
                aprendizados.registrar(cfg, s["funcionario"], f"demanda:{s['etapas'][0]['ferramenta']}", "erro",
                                       acao=s["titulo"], causa="; ".join(achados)[:500],
                                       correcao="refazer a demanda conferindo cada critério antes de entregar",
                                       evidencia_id=sid, origem="validacao")
            except Exception:
                pass
        saida.append({"solicitacao": sid, "veredito": veredito, "achados": achados})
    return saida


def _refazer_conta(etapa: dict, criterio: dict) -> list[str]:
    import pandas as pd
    try:
        df = _ler(Path(etapa["parametros"]["arquivo"]))
        refeito = float(pd.to_numeric(df[criterio["coluna"]], errors="coerce").mean())
    except Exception as e:
        return [f"não consegui refazer a conta a partir do arquivo ({type(e).__name__})"]
    valores = list(((_dado((etapa["resultado"] or {}).get("dados") or {}, "calculo.valores")) or {}).values())
    if len(valores) != 1 or not math.isclose(float(valores[0]), refeito, rel_tol=1e-6, abs_tol=1e-6):
        return [f"conta refeita do arquivo deu {refeito}, a demanda entregou {valores}"]
    return []


# =============================================================================== o ciclo (Aurora assina)
def candidatas(cfg, pessoa: dict) -> list[str]:
    """Os trabalhos da FUNÇÃO da pessoa que o catálogo cobre e que ela pode fazer, em ordem: os da especialidade
    (contrato pessoal e liderança), depois os da área/andar (organizacao.trabalho_do_papel), depois o treino de SQL
    (áreas de dados). As
    ferramentas que todo mundo tem (conhecimento, histórico, laboratório) só entram se não houver nada da função."""
    from robo import ferramentas, lideranca, organizacao
    from robo.sql_treino import AREAS_DE_DADOS
    pid, andar = pessoa["id"], pessoa["andar"]
    contrato = organizacao.ferramentas_de(pid, andar)
    especialidade = (list(organizacao.FERRAMENTAS_PESSOA.get(pid, []))
                     + list((lideranca.POR_ID.get(pid) or {}).get("ferramentas", []))
                     + (["reuniao_andar"] if pid in organizacao.LIDERES else []))
    sql = ["sql_treino"] if organizacao.area_de(pid) in AREAS_DE_DADOS else []
    ordem = (especialidade + organizacao.trabalho_do_papel(pid, andar) + sql
             + [f for f in contrato if f not in GERAIS] + list(GERAIS))
    ok = [f for f in dict.fromkeys(ordem) if f in contrato and f in CATALOGO and f in ferramentas.REGISTRO
          and organizacao.pode_usar(pid, f, cfg, producao=True)]
    proprias = [f for f in ok if f not in GERAIS]
    return proprias or ok


def escolher_ferramenta(cfg, pessoa: dict, ultima: str | None = None, usadas: list[str] | None = None) -> str | None:
    """Rodízio dentro do papel: o trabalho da função que a pessoa fez há MAIS tempo (nunca feito vem primeiro; empate,
    a ordem do papel). `usadas` = ferramentas das últimas demandas, da mais recente para a mais antiga."""
    suas = candidatas(cfg, pessoa)
    if not suas:
        return None
    usadas = list(usadas or ([ultima] if ultima else []))
    recencia = {f: (usadas.index(f) if f in usadas else len(usadas) + 1) for f in suas}
    return max(suas, key=lambda f: (recencia[f], -suas.index(f)))


def _escolher(cfg, pessoa, ultima, usadas=None):
    """Chama escolher_ferramenta com o histórico só se ela aceitar (testes antigos trocam a função)."""
    try:
        return escolher_ferramenta(cfg, pessoa, ultima, usadas)
    except TypeError:
        return escolher_ferramenta(cfg, pessoa)


def _raridade(cfg) -> dict:
    from robo import organizacao
    conta: dict[str, int] = {}
    for p in organizacao.lista(cfg):
        for f in organizacao.ferramentas_de(p["id"], p["andar"]):
            conta[f] = conta.get(f, 0) + 1
    return conta


def intervalo_da_pessoa(c: dict, pessoa: dict) -> float:
    """Horas entre demandas: pessoa > andar > geral. Nunca mais folgado que o geral (só aperta)."""
    geral = float(c["por_pessoa_horas"])
    por_pessoa = (c.get("horas_por_pessoa") or {}).get(pessoa["id"])
    por_andar = (c.get("horas_por_andar") or {}).get(str(pessoa.get("andar")))
    escolhido = por_pessoa if por_pessoa is not None else por_andar
    return min(geral, float(escolhido)) if escolhido is not None else geral


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


def observar(cfg, atribuidas: list[dict], finais: dict) -> list[dict]:
    """Regra do dono: estagiário não executa, OBSERVA. Cada estagiário acompanha um trabalho concluído neste ciclo,
    da própria área (ou do andar), e a observação fica registrada no ciclo e na memória dele (o que viu, de quem)."""
    from robo import memoria, organizacao
    gente = organizacao.por_id(cfg)
    feitos = [a for a in atribuidas if finais.get(a["solicitacao"]) in ("concluida", "concluida_parcialmente")]
    eventos = []
    for p in organizacao.lista(cfg):
        if organizacao.nivel_de(p["id"], p) != "estagiario" or not feitos:
            continue
        area = organizacao.area_de(p["id"])
        alvo = (next((a for a in feitos if organizacao.area_de(a["funcionario"]) == area), None)
                or next((a for a in feitos if (gente.get(a["funcionario"]) or {}).get("andar") == p["andar"]), None))
        if not alvo:
            continue
        quem = gente.get(alvo["funcionario"]) or {}
        titulo = CATALOGO[alvo["ferramenta"]].titulo if alvo["ferramenta"] in CATALOGO else alvo["ferramenta"]
        texto = (f"Observei {quem.get('nome', alvo['funcionario'])} ({quem.get('papel', '')}) fazendo \"{titulo}\" no nível "
                 f"{alvo['nivel']}: terminou {finais.get(alvo['solicitacao'])}.")
        memoria.experiencia(cfg, p["id"], "aprendizado", texto, "observacao", alvo["solicitacao"])
        eventos.append({"funcionario": p["id"], "andar": p["andar"], "evento": "observou", "solicitacao": alvo["solicitacao"],
                        "ferramenta": alvo["ferramenta"], "motivo": texto, "responsavel": "dem_distribuidor"})
    return eventos


def _registrar(tb: Trabalho, ciclo: str, eventos: list[dict]) -> None:
    from robo import organizacao
    with tb.tx() as c:
        for e in eventos:
            c.execute("INSERT INTO demandas_registro (data_hora, ciclo, funcionario, andar, area, evento, nivel, ferramenta, "
                      "solicitacao, motivo, responsavel) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (_agora(), ciclo, e["funcionario"], e.get("andar"), organizacao.area_de(e["funcionario"]),
                       e["evento"], e.get("nivel"), e.get("ferramenta"), e.get("solicitacao"), e.get("motivo", ""),
                       e["responsavel"]))


def rotina(cfg, agora: datetime | None = None) -> dict | None:
    """Um ciclo. Devolve o resumo (None = fora do horário: não é trabalho). Cada fase abre a sua etapa no job do
    ciclo, com quem a faz, na hora em que começa (prova de trabalho dos cinco)."""
    from robo import jobs, organizacao
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
    ciclo = agora.isoformat(timespec="seconds")
    jid = jobs.abrir(cfg, "ciclo_demandas", "sintetico", None, RESPONSAVEL)
    eventos: list[dict] = []
    try:
        # ---- Renan: demandas abandonadas e quem pode receber
        jobs.etapa(cfg, jid, "cobertura", "dem_cobertura")
        estado = _estado_das_demandas(tb, agora)
        reatribuidas = encerrar_abandonadas(cfg, tb, estado, agora, float(c["horas_abandono"]))
        eventos += [{"funcionario": r["funcionario"], "evento": "reatribuida", "solicitacao": r["solicitacao"],
                     "motivo": r["motivo"], "responsavel": "dem_cobertura"} for r in reatribuidas]
        candidatas = []
        for p in organizacao.lista(cfg):
            nivel_cargo, e = organizacao.nivel_de(p["id"], p), estado.get(p["id"]) or {}
            horas = intervalo_da_pessoa(c, p)
            limite_pessoa = (agora - timedelta(hours=horas)).isoformat(timespec="seconds")
            motivo = (NIVEIS_SEM_DEMANDA.get(nivel_cargo)
                      or (f"o trabalho do papel é a rotina {organizacao.ROTINA_PROPRIA[p['id']]} (registrada em jobs)"
                          if p["id"] in organizacao.ROTINA_PROPRIA else "")
                      or ("já tem uma demanda aberta" if e.get("abertas") else "")
                      or (f"recebeu demanda há menos de {horas:g} h" if e.get("ultima", "") > limite_pessoa else ""))
            if motivo:
                eventos.append({"funcionario": p["id"], "andar": p["andar"], "evento": "pulada", "motivo": motivo,
                                "responsavel": "dem_cobertura"})
            else:
                candidatas.append(p)
        # ---- Isadora: fila justa, alternando andares
        jobs.etapa(cfg, jid, "distribuicao", "dem_distribuidor")
        fila = ordenar(candidatas, estado, agora, float(c["horas_sem_atividade"]))
        vagas = max(0, min(int(c["por_ciclo"]), int(c["por_dia"]) - hoje))
        # ---- Vicente monta cada demanda no nível certo; quem não tem demanda adequada recebe treinamento (Renan)
        jobs.etapa(cfg, jid, "geracao", "dem_gerador")
        finais, atribuidas, bloqueadas = {}, [], []
        for p, motivo_fila in fila:
            if len(atribuidas) >= vagas:
                break
            hist = _historico(tb, p["id"])
            usadas = [h["modelo"].split(":", 1)[1] for h in hist if (h.get("modelo") or "").startswith("demanda:")
                      and h.get("tipo_demanda") == "trabalho"]
            ferr = _escolher(cfg, p, usadas[0] if usadas else None, usadas)
            nivel, motivo_nivel = nivel_para(organizacao.nivel_de(p["id"], p), hist)
            tipo, primeira, sid, motivos_bloq = "trabalho", ferr, None, []
            # o trabalho da vez; se estiver bloqueado, os OUTROS trabalhos do papel na ordem do rodízio, antes de mandar
            # a pessoa estudar (antes desistia no 1º bloqueio: 20 pessoas viravam estudo só por causa do SQL)
            tentadas: list[str] = []
            while ferr and ferr not in tentadas and len(tentadas) < 8:
                tentadas.append(ferr)
                sid, motivo = criar_demanda(cfg, p, ferr, nivel, motivo_nivel=motivo_nivel)
                if sid:
                    if ferr != primeira:
                        motivo_nivel = f"{motivo_nivel}; {primeira} estava bloqueado, fez {ferr} (do mesmo papel)"
                    break
                motivos_bloq.append(f"{ferr}: {motivo}")
                bloqueadas.append({"funcionario": p["id"], "ferramenta": ferr, "motivo": motivo})
                eventos.append({"funcionario": p["id"], "andar": p["andar"], "evento": "bloqueada", "ferramenta": ferr,
                                "nivel": nivel, "motivo": motivo, "responsavel": "dem_gerador"})
                ferr = _escolher(cfg, p, None, tentadas + usadas)
            if not primeira:
                motivos_bloq.append("nenhuma ferramenta do contrato está no catálogo de demandas")
            motivo = "; ".join(motivos_bloq)
            if not sid:
                ferr = primeira
                estudo = primeira
                ferr, nivel, tipo = "conhecimento", "basico", "treinamento"
                sid, motivo2 = criar_demanda(cfg, p, ferr, nivel, tipo="treinamento", estudo_de=estudo,
                                             motivo_nivel="sem demanda de trabalho adequada neste ciclo: " + motivo)
                if not sid:
                    eventos.append({"funcionario": p["id"], "andar": p["andar"], "evento": "sem_trabalho",
                                    "motivo": f"{motivo}; treinamento também indisponível: {motivo2}",
                                    "responsavel": "dem_cobertura"})
                    continue
            atribuidas.append({"funcionario": p["id"], "ferramenta": ferr, "nivel": nivel, "tipo": tipo, "solicitacao": sid})
            eventos.append({"funcionario": p["id"], "andar": p["andar"],
                            "evento": "atribuida" if tipo == "trabalho" else "treinamento", "ferramenta": ferr,
                            "nivel": nivel, "solicitacao": sid, "responsavel": "dem_distribuidor",
                            "motivo": f"{motivo_fila}; nível {nivel}: {motivo_nivel}" if tipo == "trabalho"
                            else f"{motivo_fila}; treinamento no lugar da demanda bloqueada"})
            finais[sid] = _executar_com_job(cfg, sid, p["id"], ferr)  # executa já: nuvem e notebook veem no ciclo
        # ---- estagiários: observam um colega da área num trabalho concluído deste ciclo e registram o que viram
        eventos += observar(cfg, atribuidas, finais)
        # ---- Bento: avaliação independente por amostragem
        jobs.etapa(cfg, jid, "avaliacao", "dem_avaliador")
        avaliacoes = avaliar(cfg, int(c["avaliacoes_por_ciclo"]), agora)
        _registrar(tb, ciclo, eventos)
        cob = cobertura(cfg, agora=agora)
        concluidas = sum(1 for e in finais.values() if e == "concluida")
        detalhe = {"atribuidas": atribuidas, "estados": finais, "bloqueadas": bloqueadas, "reatribuidas": reatribuidas,
                   "avaliacoes": avaliacoes, "vagas": vagas, "hoje_antes": hoje,
                   "puladas": [{"funcionario": e["funcionario"], "motivo": e["motivo"]} for e in eventos if e["evento"] == "pulada"],
                   "cobertura": {"completa": cob["completa"],
                                 "andares": {a: {k: v for k, v in g.items() if k in ("elegiveis", "com_demanda", "sem_demanda")}
                                             for a, g in cob["andares"].items()}}}
        with tb.tx() as conn:
            conn.execute("INSERT INTO demandas_ciclos (data_hora, responsavel, elegiveis, atribuidas, concluidas, bloqueadas, "
                         "detalhe) VALUES (?,?,?,?,?,?,?)",
                         (ciclo, RESPONSAVEL, len(candidatas), len(atribuidas), concluidas, len(bloqueadas),
                          json.dumps(detalhe, ensure_ascii=False, default=str)))
        jobs.fechar(cfg, jid, "concluido", {"atribuidas": len(atribuidas), "concluidas": concluidas,
                                            "avaliacoes": len(avaliacoes), "cobertura_completa": cob["completa"]})
    except BaseException as e:
        jobs.fechar(cfg, jid, "falhou", {"erro": f"{type(e).__name__}: {e}"})
        raise
    return {"elegiveis": len(candidatas), "atribuidas": len(atribuidas), "concluidas": concluidas,
            "bloqueadas": len(bloqueadas), "reatribuidas": len(reatribuidas), "avaliacoes": avaliacoes,
            "estados": finais, "cobertura_completa": cob["completa"]}


# =============================================================================== provas técnicas (RH)
def provas() -> dict:
    """Provas da equipe de demandas: regras determinísticas conferidas sem banco."""
    agora = datetime(2026, 10, 23, 12, 0, 0)
    c = lambda e, n: {"estado": e, "nivel": n}
    fila = ordenar([{"id": "a", "andar": 1}, {"id": "b", "andar": 1}, {"id": "c", "andar": 2}],
                   {"a": {"ultima": "2026-10-23T08:00:00", "ultima_concluida": "2026-10-23T08:00:00", "carga_7d": 3}},
                   agora, 48)
    return {
        "dem_gerador": [("Primeira demanda no início do cargo (sênior no médio, júnior no básico)",
                         nivel_para("senior", [])[0] == "medio" and nivel_para("junior", [])[0] == "basico"),
                        ("Sobe depois de 2 concluídas", nivel_para("senior", [c("concluida", "basico")] * 2)[0] == "medio"),
                        ("Nunca passa do teto do cargo", nivel_para("junior", [c("concluida", "basico")] * 2)[0] == "basico"),
                        ("Desce depois de falha", nivel_para("gerente", [c("falhou", "dificil")])[0] == "medio")],
        "dem_distribuidor": [("Quem nunca recebeu vem antes", [p["id"] for p, _ in fila][:2] == ["b", "c"]),
                             ("Alterna os andares", {p["andar"] for p, _ in fila[:2]} == {1, 2})],
        "dem_avaliador": [("Divergência no cálculo é achada", bool(conferir_criterios(
            {"ok": True, "evidencia": "x", "dados": {"calculo": {"valores": {"t": 2.0}}}},
            [{"tipo": "valor_unico", "esperado": 1.0}])))],
        "dem_cobertura": [("Arquivo vazio não conta como entrega", bool(conferir_criterios(
            {"ok": True, "artefatos": ["/nao/existe.md"]}, [{"tipo": "artefato"}])))],
        "dem_coordenador": [("Estagiário fica em observação", "estagiario" in NIVEIS_SEM_DEMANDA),
                            ("Publicar planilha fora da distribuição", "publicar_planilha" in FORA_DA_DISTRIBUICAO)],
    }
