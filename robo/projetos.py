"""Projetos entre andares: um trabalho de várias etapas, cada etapa com uma pessoa diferente, dependências e revisão.

Uma demanda comum é uma pessoa e uma ferramenta (mediana de 2 s no turno real). Um projeto de Customer Insights de
verdade passa por várias mãos e uma etapa só começa quando a anterior foi concluída:

  1. Engenharia (1º andar)      diagnostica a planilha original suja                  diagnosticar_planilha
  2. Análise (2º andar)         perfil e indicadores (NPS com margem de erro)          perfil_indicadores   ← 1
  3. Ciência de Dados           drivers do NPS (conferidos com o gabarito da fábrica)  drivers              ← 2
  4. Governança                 dados pessoais (LGPD) na mesma base                    dados_pessoais
  5. Relator (2º andar)         resumo executivo das etapas (.md)                      resumo_executivo     ← 2, 3, 4

Todas as etapas usam a MESMA base (a da fábrica com NPS e atributos). A revisão independente é do gestor do dono do
projeto, que não executa nenhuma etapa. Critérios de aceitação de cada etapa: os mesmos das demandas
(demandas.CATALOGO), mais o primeiro driver verdadeiro guardado pela fábrica. Dados: sintéticos, nunca produção.

Roda dentro do ciclo de demandas (sem agendador novo), no máximo um projeto a cada `projetos_intervalo_horas`.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

DONO_DO_PROJETO = "coord_analise"
INTERVALO_HORAS = 0.0  # sem espera entre projetos: o limite é a equipe livre e o tempo do turno (pedido do dono)
POR_CICLO = 2          # projetos por ciclo de demandas (um de cada tipo, em rodízio)
# etapa: (título, ferramenta, de onde vem a equipe, dependências)
ETAPAS = [
    ("Diagnóstico da planilha original (o que barraria a produção)", "diagnosticar_planilha", {"andar": 1}, []),
    ("Perfil e indicadores (NPS com margem de erro)", "perfil_indicadores", {"prefixos": ("analise_",)}, [1]),
    ("Drivers do NPS (o que mais pesa na nota)", "drivers", {"prefixos": ("cd_", "head_ciencia")}, [2]),
    ("Dados pessoais na base (LGPD)", "dados_pessoais", {"prefixos": ("gov_", "sec_")}, []),
    ("Resumo executivo do projeto (.md)", "resumo_executivo", {"area": "Storytelling e Negócio"}, [2, 3, 4]),
]
# 2º tipo: segmentação de clientes (quem são os grupos, o que foge do padrão), na base tratada mais recente
ETAPAS_SEGMENTACAO = [
    ("Diagnóstico da planilha original (o que barraria a produção)", "diagnosticar_planilha", {"andar": 1}, []),
    ("Perfil da base (colunas, indicadores e margem de erro)", "perfil_indicadores", {"prefixos": ("analise_",)}, [1]),
    ("Segmentação de clientes (k-means com silhueta)", "segmentacao", {"prefixos": ("cd_pleno_segmentos", "head_ciencia",
                                                                                   "ana_")}, [2]),
    ("Anomalias (valores fora do padrão, com a linha)", "anomalias", {"prefixos": ("cd_junior_anomalias", "analise_")},
     [2]),
    ("Dados pessoais na base (LGPD)", "dados_pessoais", {"prefixos": ("gov_", "sec_")}, []),
    ("Resumo executivo do projeto (.md)", "resumo_executivo", {"area": "Storytelling e Negócio"}, [2, 3, 4, 5]),
]
TIPOS = {"nps": ("Projeto NPS", ETAPAS, "análise NPS completa entre andares"),
         "segmentacao": ("Projeto Segmentação", ETAPAS_SEGMENTACAO, "segmentação de clientes e anomalias entre andares")}


def _participacoes(cfg) -> dict[str, int]:
    from robo.trabalho import Trabalho
    with Trabalho(cfg).tx() as c:
        linhas = c.execute("SELECT e.funcionario, COUNT(*) FROM etapas e JOIN solicitacoes s ON s.id=e.solicitacao_id "
                           "WHERE json_extract(s.plano,'$.tipo_demanda')='projeto' GROUP BY e.funcionario").fetchall()
    return {r[0]: r[1] for r in linhas}


def _escolher(cfg, ferramenta: str, origem: dict, ja: set[str], vezes: dict[str, int]) -> str | None:
    """Quem faz a etapa: da área/andar pedido, com a ferramenta no contrato, fora do projeto até aqui; rodízio (quem
    participou menos de projetos vem antes). Sem ninguém na área, qualquer autorizado de fora do projeto."""
    from robo import organizacao
    gente = [p for p in organizacao.lista(cfg) if p["id"] not in ja and organizacao.nivel_de(p["id"], p) != "estagiario"
             and organizacao.pode_usar(p["id"], ferramenta, cfg, producao=True)]
    da_area = [p for p in gente if ("andar" in origem and p["andar"] == origem["andar"])
               or ("area" in origem and organizacao.area_de(p["id"]) == origem["area"])
               or p["id"].startswith(origem.get("prefixos") or ("\0",))]
    pool = da_area or gente
    pool.sort(key=lambda p: (vezes.get(p["id"], 0), p["id"]))
    return pool[0]["id"] if pool else None


def _original_da_mesma_base(cfg, tratada: Path) -> Path | None:
    pasta = Path(cfg.originais) / "_treino"  # a esteira guarda a original numa subpasta do mês
    parecidas = sorted(pasta.rglob(f"*{tratada.stem}*"))  # nome com a data na frente
    return parecidas[-1] if parecidas else None


def montar(cfg, tipo: str = "nps", ocupados: set[str] | None = None) -> dict | str:
    """O plano do projeto ou o motivo de não dar para montar agora (sem base adequada, sem equipe livre).
    ocupados: quem já está em outro projeto deste ciclo (ninguém faz dois ao mesmo tempo)."""
    from robo import demandas, organizacao
    nome, modelo_etapas, _ = TIPOS[tipo]
    dono = organizacao.por_id(cfg).get(DONO_DO_PROJETO) or {}
    if tipo == "nps":
        base = demandas._com_indicador(cfg, dono)
        if isinstance(base, str):
            return "projeto NPS sem base: " + base
    else:
        arq = demandas.base_tratada(cfg)
        if not arq:
            return f"{nome} sem base: ainda não há planilha sintética tratada"
        base = ({"arquivo": str(arq)}, [])
    params_base, extras_drivers = base
    tratada = Path(params_base["arquivo"])
    original = _original_da_mesma_base(cfg, tratada)
    revisor = organizacao.revisor_de(DONO_DO_PROJETO, cfg)
    ja, vezes = {DONO_DO_PROJETO, revisor, *(ocupados or set())}, _participacoes(cfg)
    etapas, crits, mapa = [], {}, {}
    for i, (titulo, ferr, origem, deps) in enumerate(modelo_etapas, 1):
        if ferr == "diagnosticar_planilha" and not original:
            continue  # a cópia suja desta base não está na máquina: a etapa não é inventada
        quem = _escolher(cfg, ferr, origem, ja, vezes)
        if not quem:
            return f"ninguém fora do projeto tem '{ferr}' no contrato"
        ja.add(quem)
        mapa[i] = len(etapas) + 1
        params = {"arquivo": str(original)} if ferr == "diagnosticar_planilha" else (
            {} if ferr == "resumo_executivo" else {"arquivo": str(tratada)})
        etapas.append({"titulo": titulo, "ferramenta": ferr, "funcionario": quem, "parametros": params,
                       "depende": [mapa[d] for d in deps if d in mapa]})
        if ferr == "resumo_executivo":
            crits[len(etapas)] = [{"tipo": "ok"}, {"tipo": "artefato"}]
        else:
            crits[len(etapas)] = list(demandas.CATALOGO[ferr].criterios) + (extras_drivers if ferr == "drivers" else [])
    return {"titulo": f"{nome} — {tratada.stem}", "etapas": etapas, "revisor": revisor, "base": str(tratada),
            "criterios_por_etapa": {str(k): v for k, v in crits.items()}, "tipo": tipo}


def criar(cfg, tipo: str = "nps", ocupados: set[str] | None = None) -> tuple[str | None, str]:
    """Cria o projeto (não executa). Devolve (id, '') ou (None, motivo). Em `ocupados` entram os executores dele."""
    from robo import orquestrador, organizacao
    plano = montar(cfg, tipo, ocupados)
    if isinstance(plano, str):
        return None, plano
    if ocupados is not None:
        ocupados.update(e["funcionario"] for e in plano["etapas"])
    gente = organizacao.por_id(cfg)
    linhas = [f"{n}. {e['titulo']} — {(gente.get(e['funcionario']) or {}).get('nome', e['funcionario'])}"
              + (f" (depois de {', '.join(map(str, e['depende']))})" if e["depende"] else "")
              for n, e in enumerate(plano["etapas"], 1)]
    pedido = (f"Objetivo: {TIPOS[tipo][2]}, do diagnóstico ao resumo executivo.\n"
              f"Base: {Path(plano['base']).name} (sintética, da fábrica; nunca produção).\nEtapas:\n" + "\n".join(linhas)
              + f"\nRevisão independente: {plano['revisor']}.")
    sid = orquestrador.criar_demanda(
        cfg, plano["titulo"], pedido, DONO_DO_PROJETO, plano["etapas"], plano["revisor"],
        plano_extra={"tipo_demanda": "projeto", "nivel": "profissional", "dados": "sintetico", "base": plano["base"],
                     "criterios_por_etapa": plano["criterios_por_etapa"], "gerada_por": "dem_gerador",
                     "objetivo": TIPOS[tipo][2], "tipo_projeto": tipo})
    return sid, ""


def ciclo(cfg, agora: datetime | None = None, intervalo_horas: float = INTERVALO_HORAS,
          por_ciclo: int = POR_CICLO) -> dict | None:
    """Projetos do ciclo de demandas, criados e executados na hora, em rodízio de tipo (NPS, segmentação). Cada
    pessoa entra em no máximo um projeto do ciclo. None = ainda não é hora (só com intervalo_horas > 0)."""
    from robo import demandas
    from robo.trabalho import Trabalho
    agora = agora or datetime.now()
    with Trabalho(cfg).tx() as c:
        ult = c.execute("SELECT MAX(criada_em) FROM solicitacoes WHERE json_extract(plano,'$.tipo_demanda')='projeto'"
                        ).fetchone()[0]
        feitos = dict(c.execute("SELECT COALESCE(json_extract(plano,'$.tipo_projeto'),'nps'), COUNT(*) FROM solicitacoes "
                                "WHERE json_extract(plano,'$.tipo_demanda')='projeto' GROUP BY 1").fetchall())
    if intervalo_horas > 0 and ult and agora - datetime.fromisoformat(ult) < timedelta(hours=intervalo_horas):
        return None
    ordem = sorted(TIPOS, key=lambda t: (feitos.get(t, 0), t))  # o tipo menos feito vem primeiro
    ocupados: set[str] = set()
    feitos_agora, motivos = [], []
    for k in range(max(0, int(por_ciclo))):
        tipo = ordem[k % len(ordem)]
        sid, motivo = criar(cfg, tipo, ocupados)
        if not sid:
            motivos.append(motivo)
            continue
        estado = demandas._executar_com_job(cfg, sid, DONO_DO_PROJETO, f"projeto_{tipo}")
        feito = {"projeto": sid, "tipo": tipo, "estado": estado}
        if estado == "concluida":  # aprovado na revisão: vira o pacote de entrega do produto (robo/entrega.py)
            feito["entrega"] = registrar_entrega(cfg, sid)
        feitos_agora.append(feito)
    # compatível com quem lê um projeto só (o primeiro) e com o detalhe do ciclo
    primeiro = feitos_agora[0] if feitos_agora else {"projeto": None}
    return {**primeiro, "projetos": feitos_agora, "motivo": "; ".join(motivos)}


ESQUEMA_ENTREGAS = """CREATE TABLE IF NOT EXISTS entregas (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT NOT NULL, projeto TEXT, base TEXT, pasta TEXT,
  ok INTEGER, recomendacoes TEXT, arquivos TEXT);
CREATE TRIGGER IF NOT EXISTS entregas_nao_muda BEFORE UPDATE ON entregas
BEGIN SELECT RAISE(ABORT, 'registro permanente: entrega não pode ser alterada'); END;"""


def registrar_entrega(cfg, sid: str) -> dict | None:
    """O projeto aprovado gera o mesmo pacote que o dono gera com `python -m robo entregar` (base tratada,
    indicadores.xlsx e relatorio.html) a partir da base do projeto, e o registro fica no banco (permanente).
    Nunca derruba o ciclo: falha vira motivo no retorno."""
    from robo import entrega
    from robo.trabalho import Trabalho, _agora, proteger
    tb = Trabalho(cfg)
    s = tb.solicitacao(sid) or {}
    base = (s.get("plano") or {}).get("base")
    if not base or not Path(base).exists():
        return None
    try:
        r = entrega.entregar(cfg, base, Path(cfg.logs) / "entregas")
    except Exception as e:
        import logging
        logging.getLogger("robo").exception("Entrega do projeto %s falhou", sid)
        return {"ok": False, "motivo": f"{type(e).__name__}: {e}"}
    with tb.tx() as c:
        c.executescript(ESQUEMA_ENTREGAS)
        proteger(c)
        c.execute("INSERT INTO entregas (data_hora, projeto, base, pasta, ok, recomendacoes, arquivos) VALUES "
                  "(?,?,?,?,?,?,?)", (_agora(), sid, Path(base).name, r["pasta"], int(r["ok"]),
                                      json.dumps(r["recomendacoes"], ensure_ascii=False), json.dumps(r["arquivos"])))
    return {"ok": r["ok"], "pasta": r["pasta"], "recomendacoes": r["recomendacoes"]}


def entregas(cfg, limite: int = 5) -> list[dict]:
    from robo.trabalho import Trabalho
    try:
        with Trabalho(cfg).tx() as c:
            linhas = c.execute("SELECT * FROM entregas ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
    except Exception:
        return []
    return [{**dict(x), "recomendacoes": json.loads(x["recomendacoes"] or "[]")} for x in linhas]


def resumo(cfg, limite: int = 10) -> list[dict]:
    """Os últimos projetos: estado e, por etapa, quem fez e como terminou."""
    from robo.trabalho import Trabalho
    with Trabalho(cfg).tx() as c:
        projs = c.execute("SELECT id, titulo, estado, criada_em FROM solicitacoes WHERE "
                          "json_extract(plano,'$.tipo_demanda')='projeto' ORDER BY criada_em DESC LIMIT ?",
                          (limite,)).fetchall()
        saida = []
        for p in projs:
            et = c.execute("SELECT ordem, titulo, funcionario, estado FROM etapas WHERE solicitacao_id=? ORDER BY ordem",
                           (p["id"],)).fetchall()
            saida.append({**dict(p), "etapas": [dict(e) for e in et]})
    return json.loads(json.dumps(saida, default=str))
