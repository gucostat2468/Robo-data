"""Registro único de funcionários e contrato de execução de cada um.

Antes, a lista de pessoas era montada em quatro lugares (canal, quadro, estratégia e painel). Agora todos consultam
este módulo. Nada muda de nome, cargo ou andar: o registro é montado a partir das mesmas fontes de sempre
(agentes nativos, supervisores, analistas, Sala Excel, quadro, canal, TI e contratados).

Contrato de execução = o que a pessoa pode fazer de verdade:
  identidade, cargo, nível, andar, gestor, especialidade, objetivo, responsabilidades, ferramentas autorizadas,
  entradas e saídas aceitas, permissões, risco máximo, critérios de sucesso e de falha, para quem encaminha
  cada assunto, quando pede ajuda, quem revisa o trabalho dela e quais são as suas fontes de conhecimento.

Regras de hierarquia (valem para todo mundo, inclusive contratados):
  - ninguém revisa nem aprova o próprio trabalho (o revisor é sempre outra pessoa);
  - ninguém muda as próprias permissões nem se promove (só o dono promove; ver `pode_alterar_permissoes`);
  - estagiário trabalha em observação: lê, calcula e relata, mas não altera dado nem aprova nada.
"""

from __future__ import annotations

import sqlite3
import time
from functools import lru_cache
from pathlib import Path

DONO = "dono"

# andar → canal do andar e líder (o líder de cada andar é definido só em contratacao.LIDER_DO_ANDAR)
CANAL_DO_ANDAR = {1: "engenharia", 2: "analise", 3: "excel", 4: "geral", 5: "ti"}
NOME_ANDAR = {1: "Engenharia de Dados", 2: "Analytics e Ciência de Dados", 3: "Sala Excel e BI",
              4: "Operações, governança, canal e Pessoas (RH)", 5: "TI, DevOps e segurança"}

# Permissões por nível. "altera_dados" = pode executar ferramenta que muda arquivo publicado (sempre com aprovação do
# dono); "aprova" = pode ser revisor independente de trabalho alheio.
PERMISSOES_NIVEL = {
    "diretor": {"le_dados": True, "calcula": True, "altera_dados": False, "aprova": True, "risco_maximo": "medio"},
    "head": {"le_dados": True, "calcula": True, "altera_dados": True, "aprova": True, "risco_maximo": "alto"},
    "gerente": {"le_dados": True, "calcula": True, "altera_dados": False, "aprova": True, "risco_maximo": "medio"},
    "coordenador": {"le_dados": True, "calcula": True, "altera_dados": True, "aprova": True, "risco_maximo": "alto"},
    "especialista": {"le_dados": True, "calcula": True, "altera_dados": True, "aprova": True, "risco_maximo": "alto"},
    "senior": {"le_dados": True, "calcula": True, "altera_dados": True, "aprova": True, "risco_maximo": "alto"},
    "pleno": {"le_dados": True, "calcula": True, "altera_dados": False, "aprova": True, "risco_maximo": "medio"},
    "junior": {"le_dados": True, "calcula": True, "altera_dados": False, "aprova": False, "risco_maximo": "baixo"},
    "estagiario": {"le_dados": True, "calcula": True, "altera_dados": False, "aprova": False, "risco_maximo": "baixo"},
}
ORDEM_RISCO = {"baixo": 0, "medio": 1, "alto": 2}

# Ferramentas que todo mundo pode usar (só leem)
FERRAMENTAS_COMUNS = ["conhecimento", "historico", "laboratorio"]
# Ferramentas por andar
FERRAMENTAS_ANDAR = {
    1: ["diagnosticar_planilha", "consulta_sql"],
    2: ["calcular", "perfil_indicadores", "resumo_executivo", "consulta_sql"],
    3: ["calcular", "perfil_indicadores"],
    4: ["resumo_executivo"],
    5: ["ronda_ti", "orquestracao", "postgres_saude", "segredos_repo", "restauracao_backup"],
}
# O TRABALHO DO PAPEL: o que cada área faz de verdade (pedido do dono: "cada funcionário faz o seu papel").
# Antes a ferramenta vinha do ANDAR e o andar inteiro fazia a mesma coisa (o 4º andar todo conferia LGPD, até o RH e
# a equipe de demandas). Agora a área define o trabalho, e a pessoa faz rodízio entre os trabalhos da área.
TRABALHO_DA_AREA = {
    "Engenharia de Dados": ["diagnosticar_planilha", "consulta_sql", "anomalias"],
    "Qualidade de Dados": ["diagnosticar_planilha", "anomalias", "perfil_indicadores"],
    "Governança e Privacidade": ["dados_pessoais", "diagnosticar_planilha"],
    "Análise de Dados": ["perfil_indicadores", "segmentacao", "calcular"],
    "Estatística": ["calcular", "drivers", "anomalias"],
    "Customer Insights e Pesquisa": ["perfil_indicadores", "drivers", "segmentacao"],
    "Storytelling e Negócio": ["perfil_indicadores", "calcular"],
    "Pessoas e Cultura": ["desempenho", "people_analytics", "desenvolvimento", "recrutamento"],
    "Treinamento e Avaliação": ["revisar_caso"],
}
# Andares cujo trabalho é do ANDAR (a área da ficha diz a formação, não o que a pessoa faz aqui)
TRABALHO_DO_ANDAR = {
    3: ["calcular", "perfil_indicadores", "segmentacao"],                       # Sala Excel e BI: contas, indicadores
    5: ["ronda_ti", "orquestracao", "postgres_saude", "segredos_repo", "restauracao_backup"],  # TI: operação da casa
}
# Quem já tem trabalho próprio numa rotina da empresa (registrado em jobs) e não recebe demanda de outra coisa
ROTINA_PROPRIA = {**{p: "demandas" for p in ("dem_coordenador", "dem_gerador", "dem_distribuidor", "dem_cobertura",
                                            "dem_avaliador")},
                  **{p: "fabrica" for p in ("fab_coordenador", "fab_gerador", "fab_conferente", "fab_revisor")}}


def trabalho_do_papel(pid: str, andar: int) -> list[str]:
    """Os trabalhos da função da pessoa, na ordem de prioridade (o rodízio das demandas anda por esta lista)."""
    andar = int(andar or 1)
    return list(TRABALHO_DO_ANDAR.get(andar) or TRABALHO_DA_AREA.get(area_de(pid), []))


# Ferramentas extras por pessoa (especialidade)
LIDERES = ["ger_engenharia", "coord_engenharia", "ger_analise", "coord_analise", "excel_supervisor", "coord_excel",
           "ger_operacoes", "canal_helena", "ger_ti", "coord_devops",
           "dir_dados", "dir_analytics", "dir_operacoes", "dir_pessoas", "dir_tecnologia",
           "head_engenharia", "head_ciencia", "head_bi", "head_governanca", "head_rh", "head_ti", "head_python"]
FERRAMENTAS_PESSOA = {
    "recepcao": ["publicar_planilha"], "coord_engenharia": ["publicar_planilha", "calcular"],
    "supervisor": ["calcular"], "dba": ["consulta_sql"], "banco": ["consulta_sql"],
    "canal_nina": ["calcular"], "canal_iara": ["historico", "ideias"], "canal_helena": ["organizacao"],
    "ger_operacoes": ["organizacao"], "ger_ti": ["organizacao"], "excel_supervisor": ["diagnosticar_planilha"],
    "sec_senior": ["dados_pessoais"], "coord_devops": ["diagnosticar_planilha"],
    "bi_powerbi": ["paineis", "consulta_sql"], "bi_reconciliacao": ["paineis", "consulta_sql"],
    "fab_coordenador": ["fabrica"], "fab_gerador": ["fabrica"], "fab_conferente": ["fabrica"], "fab_revisor": ["fabrica"],
    "dem_coordenador": ["demandas"], "dem_gerador": ["demandas"], "dem_distribuidor": ["demandas"],
    "dem_cobertura": ["demandas"], "dem_avaliador": ["demandas"],
    "head_aws": ["prontidao_nuvem"], "cloud_aws": ["prontidao_nuvem"], "aws_senior": ["restauracao_backup", "postgres_saude"],
}
# Sala de Casos (4º andar): a revisão independente de casos de treino é a ferramenta de trabalho de todos eles
for _pid in ("head_casos", "casos_engenharia", "casos_analytics", "casos_governanca", "casos_ti", "casos_revisor",
             "casos_planejamento"):
    FERRAMENTAS_PESSOA.setdefault(_pid, []).append("revisar_caso")

# Para quem cada tipo de ferramenta é encaminhado quando a pessoa não pode usá-la
ENCAMINHAR = {
    "calcular": "analise_estatistica", "perfil_indicadores": "analise_indicadores",
    "resumo_executivo": "analise_relator", "diagnosticar_planilha": "coord_engenharia",
    "publicar_planilha": "recepcao", "consulta_sql": "dba", "dados_pessoais": "gov_pleno_lgpd",
    "ronda_ti": "coord_devops", "orquestracao": "airflow_pleno", "organizacao": "canal_helena", "reuniao_andar": "ger_operacoes", "ideias": "canal_iara", "paineis": "bi_powerbi", "fabrica": "fab_coordenador", "demandas": "dem_coordenador",
    "scorecard": "dir_operacoes", "auditoria": "head_engenharia", "drivers": "cd_senior_drivers",
    "segmentacao": "cd_pleno_segmentos", "anomalias": "cd_junior_anomalias", "recrutamento": "rh_rs",
    "desenvolvimento": "rh_td", "desempenho": "rh_desempenho", "people_analytics": "rh_people", "raio_x": "dir_operacoes",
    "revisao_biblioteca": "head_python", "estrategia_python": "head_python", "laboratorio": "head_engenharia",
    "conhecimento": "canal_nina", "historico": "canal_nina", "revisar_caso": "casos_revisor", "sql_treino": "dba",
    "restauracao_backup": "aws_senior", "prontidao_nuvem": "head_aws", "postgres_saude": "aws_senior",
    "segredos_repo": "sec_senior",
}

ENTRADAS = {
    "diagnosticar_planilha": "planilha .xlsx/.xlsm/.xls/.csv/.txt", "calcular": "pergunta de cálculo + base publicada ou arquivo",
    "perfil_indicadores": "planilha ou base publicada", "consulta_sql": "id de uma consulta da biblioteca",
    "dados_pessoais": "planilha ou base publicada", "publicar_planilha": "planilha (com sua aprovação)",
    "resumo_executivo": "resultados das etapas anteriores", "ronda_ti": "nada (lê o próprio computador)",
    "orquestracao": "nada (lê os registros das rotinas)", "revisar_caso": "caso de treino (arquivo, gabarito e semente)",
    "conhecimento": "pergunta em texto", "historico": "pergunta sobre o que aconteceu", "organizacao": "pergunta sobre a equipe",
    "paineis": "nada (lê a memória da empresa)",
}
SAIDAS = {
    "diagnosticar_planilha": "lista de erros e avisos com linha do Excel", "calcular": "tabela com o resultado e a base usada",
    "perfil_indicadores": "perfil das colunas e indicadores com margem de erro", "consulta_sql": "linhas do PostgreSQL",
    "dados_pessoais": "colunas que parecem dado pessoal", "publicar_planilha": "arquivo na fila de Bases-Limpeza",
    "resumo_executivo": "arquivo .md com o resumo executivo", "ronda_ti": "verificações de saúde do sistema",
    "orquestracao": "rotinas atrasadas, com erro ou lentas e o responsável",
    "revisar_caso": "aprovado ou reprovado, com cada problema encontrado",
    "conhecimento": "resposta do conhecimento registrado", "historico": "execuções recentes",
    "organizacao": "quem faz o quê na empresa",
    "paineis": "5 painéis com cada número conferido por outra pessoa (logs/paineis/painel.json)",
}


def _papel_curto(texto: str) -> str:
    return str(texto or "").split(" — ")[0]


@lru_cache(maxsize=1)
def _fixos() -> tuple:
    """Pessoas do quadro fixo, na ordem histórica (mesma ordem que o canal e o painel sempre usaram)."""
    from robo.agentes import NATIVOS
    from robo.analise import ANALISTAS
    from robo.canal import EQUIPE_CANAL
    from robo.excel import EQUIPE_EXCEL
    from robo.producao import SUPERVISORES
    from robo.quadro import QUADRO
    from robo.ti import EQUIPE_TI
    p: list[dict] = []
    p += [{"id": a["id"], "nome": a["nome"], "papel": a["papel"], "andar": 1, "grupo": "nativo",
           "canal": "banco" if a["id"] == "banco" else "engenharia", "cor": a.get("cor"), "descricao": a.get("descricao", "")}
          for a in NATIVOS]
    p += [{"id": f"analise_{a['id']}", "nome": a["nome"], "papel": a["papel"], "andar": 2, "grupo": "analista",
           "canal": "analise", "cor": a.get("cor"), "descricao": a.get("descricao", "")} for a in ANALISTAS]
    p += [{"id": a["id"], "nome": a["nome"], "papel": a["papel"], "andar": 3, "grupo": "excel", "canal": "excel",
           "cor": a.get("cor"), "descricao": a.get("descricao", "")} for a in EQUIPE_EXCEL]
    p += [{"id": a["id"], "nome": a["nome"], "papel": a["papel"], "andar": a["andar"], "grupo": "supervisor",
           "canal": "banco" if a["id"] == "dba" else "lideranca", "cor": a.get("cor"), "descricao": a.get("descricao", "")}
          for a in SUPERVISORES]
    canais_canal = {"canal_iara": "ideias", "canal_helena": "rh"}
    p += [{"id": a["id"], "nome": a["nome"], "papel": a["papel"], "andar": a["andar"], "grupo": "canal",
           "canal": canais_canal.get(a["id"], "geral"), "cor": a.get("cor"), "descricao": a.get("descricao", "")}
          for a in EQUIPE_CANAL]
    p += [{"id": x["id"], "nome": x["nome"], "papel": _papel_curto(x["cargo"]), "andar": x["andar"], "grupo": "quadro",
           "canal": "geral", "cor": x.get("cor"), "descricao": x.get("descricao") or "; ".join(x.get("escopo") or [])}
          for x in QUADRO]
    p += [{"id": x["id"], "nome": x["nome"], "papel": _papel_curto(x["cargo"]), "andar": 5, "grupo": "ti", "canal": "ti",
           "cor": x.get("cor"), "descricao": "; ".join(x.get("escopo") or [])} for x in EQUIPE_TI]
    from robo.paineis import EQUIPE_BI
    p += [{"id": x["id"], "nome": x["nome"], "papel": _papel_curto(x["cargo"]), "andar": x["andar"], "grupo": "bi", "canal": "excel",
           "cor": x.get("cor"), "descricao": "; ".join(x.get("escopo") or [])} for x in EQUIPE_BI]
    from robo.fabrica import EQUIPE_FABRICA
    p += [{"id": x["id"], "nome": x["nome"], "papel": _papel_curto(x["cargo"]), "andar": x["andar"], "grupo": "fabrica",
           "canal": "geral", "cor": x.get("cor"), "descricao": "; ".join(x.get("escopo") or [])} for x in EQUIPE_FABRICA]
    from robo.demandas import EQUIPE_DEMANDAS
    p += [{"id": x["id"], "nome": x["nome"], "papel": _papel_curto(x["cargo"]), "andar": x["andar"], "grupo": "demandas",
           "canal": "geral", "cor": x.get("cor"), "descricao": "; ".join(x.get("escopo") or [])} for x in EQUIPE_DEMANDAS]
    from robo.lideranca import EQUIPE as LIDERANCA
    p += [{"id": x["id"], "nome": x["nome"], "papel": _papel_curto(x["cargo"]), "andar": x["andar"], "grupo": "lideranca",
           "canal": "lideranca" if x["nivel"] in ("diretor", "head") else ("rh" if x["id"].startswith("rh_") else CANAL_DO_ANDAR[x["andar"]]),
           "cor": x.get("cor"), "descricao": x["descricao"]} for x in LIDERANCA]
    return tuple(p)


def lista(cfg=None, com_contratados: bool = True) -> list[dict]:
    """Todos os funcionários (sem o dono). Com `cfg`, inclui os contratados (agentes personalizados ativos)."""
    pessoas = [dict(x) for x in _fixos()]
    if cfg is not None and com_contratados:
        try:
            from robo.pipeline import obter_equipe
            fixos = {x["id"] for x in pessoas}
            for a in obter_equipe(cfg).personalizados:
                if a["id"] in fixos or not a.get("ativo", True):
                    continue
                andar = int(a.get("andar") or 1)
                pessoas.append({"id": a["id"], "nome": a["nome"], "papel": a.get("papel") or a.get("cargo") or "Agente",
                                "andar": andar, "grupo": "contratado", "canal": CANAL_DO_ANDAR.get(andar, "geral"),
                                "cor": a.get("cor"), "descricao": a.get("descricao", ""), "nivel": a.get("nivel") or "pleno",
                                "_agente": a})
        except Exception:  # configuração com problema não pode esconder o quadro fixo
            pass
    if cfg is not None:  # nível efetivo decidido pelo ciclo de RH (promoção registrada em rh_movimentos)
        niveis = _rh_estado(cfg)[0]
        for x in pessoas:
            if x["id"] in niveis:
                x["nivel_rh"] = niveis[x["id"]]
    return pessoas


# ------------------------------------------------------------------- RH: nível efetivo e afastamentos (rh_desempenho)
_CACHE_RH: dict[str, tuple[float, dict, dict]] = {}


def _rh_estado(cfg) -> tuple[dict, dict]:
    """(nível efetivo por pessoa, ferramentas de produção afastadas por pessoa), lidos de rh_cargos e rh_pdi.
    Leitura direta e somente leitura; guarda 5 s (o ciclo de RH limpa na hora em que grava)."""
    logs = getattr(cfg, "logs", None)
    if not logs:
        return {}, {}
    arq = Path(logs) / "trabalho.db"
    chave, agora = str(arq), time.monotonic()
    guardado = _CACHE_RH.get(chave)
    if guardado and agora - guardado[0] < 5:
        return guardado[1], guardado[2]
    niveis: dict = {}
    afastadas: dict = {}
    if arq.exists():
        try:
            con = sqlite3.connect(f"file:{arq}?mode=ro", uri=True, timeout=5)
            try:
                tabelas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if "rh_cargos" in tabelas:
                    niveis = {f: n for f, n in con.execute("SELECT funcionario, nivel FROM rh_cargos")}
                if "rh_pdi" in tabelas:
                    for f, ferr in con.execute("SELECT funcionario, ferramenta FROM rh_pdi "
                                               "WHERE afastado_em IS NOT NULL AND fechado_em IS NULL"):
                        afastadas.setdefault(f, set()).add(ferr)
            finally:
                con.close()
        except sqlite3.Error:
            pass
    _CACHE_RH[chave] = (agora, niveis, afastadas)
    return niveis, afastadas


def limpar_cache_rh() -> None:
    _CACHE_RH.clear()


def afastado_de(pid: str, cfg=None) -> list[str]:
    """Ferramentas que a pessoa NÃO usa em produção enquanto o plano de melhoria não fecha (continua treinando)."""
    return sorted(_rh_estado(cfg)[1].get(pid, ())) if cfg is not None else []


def por_id(cfg=None) -> dict[str, dict]:
    return {p["id"]: p for p in lista(cfg)}


def nivel_de(pid: str, pessoa: dict | None = None) -> str:
    """Nível do cargo. Promoção registrada pelo ciclo de RH vale primeiro (chega em `pessoa` por lista(cfg))."""
    if pessoa and pessoa.get("nivel_rh"):
        return pessoa["nivel_rh"]
    from robo import demandas, fabrica, lideranca, quadro, rh, ti
    f = (rh.FICHAS.get(pid) or quadro.POR_ID.get(pid) or ti.POR_ID.get(pid) or lideranca.POR_ID.get(pid)
         or fabrica.POR_ID.get(pid) or demandas.POR_ID.get(pid) or {})
    return f.get("nivel") or (pessoa or {}).get("nivel") or "pleno"


def area_de(pid: str) -> str:
    from robo import demandas, fabrica, lideranca, quadro, rh, ti
    f = (rh.FICHAS.get(pid) or quadro.POR_ID.get(pid) or ti.POR_ID.get(pid) or lideranca.POR_ID.get(pid)
         or fabrica.POR_ID.get(pid) or demandas.POR_ID.get(pid) or {})
    return f.get("area") or ""


def gestor_de(pid: str) -> str | None:
    from robo import fabrica, lideranca, paineis, quadro, ti
    if pid in paineis.GESTORES:
        return paineis.GESTORES[pid]
    if pid in fabrica.GESTORES:
        return fabrica.GESTORES[pid]
    from robo import demandas
    if pid in demandas.GESTORES:
        return demandas.GESTORES[pid]
    if pid in lideranca.NOVOS_GESTORES:  # gerentes que passaram a ter head ou diretor acima
        return lideranca.NOVOS_GESTORES[pid]
    if pid in lideranca.POR_ID:
        return lideranca.POR_ID[pid]["gestor"]
    if pid in ti.GESTORES:
        return ti.GESTORES[pid]
    if pid in quadro.GESTORES_EXISTENTES:
        return quadro.GESTORES_EXISTENTES[pid]
    if pid in quadro.POR_ID:
        return quadro.POR_ID[pid].get("gestor")
    return None


def lider_do_andar(andar: int) -> str:
    from robo.contratacao import LIDER_DO_ANDAR
    return LIDER_DO_ANDAR.get(int(andar or 1), "canal_helena")


def revisor_de(pid: str, cfg=None) -> str:
    """Quem revisa o trabalho de `pid`: o gestor, se ele puder aprovar; senão o líder do andar; senão o dono.
    Nunca devolve a própria pessoa."""
    gente = por_id(cfg)
    candidatos = [gestor_de(pid)]
    p = gente.get(pid)
    if p:
        candidatos.append(lider_do_andar(p["andar"]))
    for c in candidatos:
        if c and c != pid and (c == DONO or (c in gente and PERMISSOES_NIVEL[nivel_de(c, gente[c])]["aprova"])):
            return c
    return DONO


def ferramentas_de(pid: str, andar: int) -> list[str]:
    from robo import lideranca
    from robo.sql_treino import AREAS_DE_DADOS
    fs = (list(FERRAMENTAS_COMUNS) + FERRAMENTAS_ANDAR.get(int(andar or 1), []) + FERRAMENTAS_PESSOA.get(pid, [])
          + trabalho_do_papel(pid, andar))
    if area_de(pid) in AREAS_DE_DADOS:  # engenharia, análise, estatística, qualidade e insights treinam SQL de verdade
        fs.append("sql_treino")
    fs += (lideranca.POR_ID.get(pid) or {}).get("ferramentas", [])
    if pid in LIDERES:
        fs.append("reuniao_andar")
    if int(andar or 0) == 5 and pid in ("ger_ti", "coord_devops", "dev_pleno", "dir_tecnologia"):
        fs.append("estrategia_python")  # a TI Python olha a operação de forma estratégica  # gerentes e coordenadores respondem pela situação do andar a qualquer momento
    return list(dict.fromkeys(fs))


def autorizadas(pid: str, cfg=None) -> list[str]:
    """Ferramentas do contrato, já filtradas pelo risco máximo do nível (estagiário só usa as de risco baixo)."""
    p = por_id(cfg).get(pid)
    if not p:
        return []
    from robo.ferramentas import REGISTRO as FERR
    teto = ORDEM_RISCO[PERMISSOES_NIVEL.get(nivel_de(pid, p), PERMISSOES_NIVEL["pleno"])["risco_maximo"]]
    return [x for x in ferramentas_de(pid, p["andar"]) if x in FERR and ORDEM_RISCO[FERR[x].risco] <= teto]


def contrato(pid: str, cfg=None) -> dict | None:
    """Contrato de execução completo de um funcionário (ou None se não existe)."""
    from robo import rh
    gente = por_id(cfg)
    p = gente.get(pid)
    if not p:
        return None
    nivel = nivel_de(pid, p)
    perm = dict(PERMISSOES_NIVEL.get(nivel, PERMISSOES_NIVEL["pleno"]))
    if nivel == "estagiario":
        perm["modo"] = "observação (não altera nem aprova nada até o dono promover)"
    agente = p.get("_agente") or {"id": pid, "habilidades": []}
    try:
        f = rh.ficha(agente)
    except Exception:
        f = {}
    ferramentas = autorizadas(pid, cfg)
    gestor = gestor_de(pid)
    revisor = revisor_de(pid, cfg)
    nome_de = lambda x: "Você (dono)" if x == DONO else (gente.get(x) or {}).get("nome", x)
    return {
        "id": pid, "nome": p["nome"], "cargo": f.get("cargo") or p["papel"], "papel": p["papel"], "nivel": nivel,
        "nivel_nome": rh.NOME_NIVEL.get(nivel, nivel), "andar": p["andar"], "nome_andar": NOME_ANDAR.get(p["andar"], ""),
        "grupo": p["grupo"], "canal": p["canal"], "cor": p.get("cor"),
        "gestor": gestor, "gestor_nome": nome_de(gestor) if gestor else None,
        "especialidade": f.get("area") or "", "objetivo": p.get("descricao") or "; ".join(f.get("responsabilidades") or [])[:300],
        "responsabilidades": list(f.get("responsabilidades") or []),
        "ferramentas": ferramentas, "afastado_de": afastado_de(pid, cfg),
        "entradas": {x: ENTRADAS.get(x, "") for x in ferramentas}, "saidas": {x: SAIDAS.get(x, "") for x in ferramentas},
        "permissoes": perm, "risco_maximo": perm["risco_maximo"],
        "criterios_sucesso": list(f.get("criterios") or []),
        "criterios_falha": ["Resultado sem evidência (arquivo, número ou linha de origem)",
                            "Ferramenta devolveu erro ou nada", "Revisor independente reprovou"],
        "limites": list(f.get("limites") or []),
        "encaminha": {x: ENCAMINHAR[x] for x in ENCAMINHAR if x not in ferramentas},
        "pede_ajuda_quando": ["O pedido precisa de uma ferramenta que não está no contrato",
                              "O risco da ação passa do risco máximo do nível",
                              "Faltou dado para responder com certeza (pergunta ao dono em vez de chutar)"],
        "revisor": revisor, "revisor_nome": nome_de(revisor),
        "fontes_conhecimento": ["conhecimento/*.md", f"agentes/{pid}.md (manual, se existir)",
                                "base de conhecimento do canal", "histórico de execuções",
                                "handovers e boas práticas da área (memória da empresa)"]
                               + (["conhecimento/lideranca_e_gestao.md (Project Oxygen, SBI, 70-20-10, PDI, promoção)"]
                                  if pid in LIDERES or nivel in ("gerente", "coordenador", "head", "diretor") else []),
    }


def pode_usar(pid: str, ferramenta: str, cfg=None, producao: bool = False) -> bool:
    """producao=True: além do contrato, respeita o afastamento do RH (plano de melhoria sem evolução). O treino chama
    sem producao — quem está afastado continua treinando a ferramenta até voltar."""
    if ferramenta not in autorizadas(pid, cfg):
        return False
    return not (producao and ferramenta in afastado_de(pid, cfg))


def quem_usa(ferramenta: str, cfg=None, preferido: str | None = None) -> str | None:
    """Quem deve executar uma ferramenta: o preferido (se pode), o responsável padrão, ou o primeiro autorizado."""
    for c in (preferido, ENCAMINHAR.get(ferramenta)):
        if c and pode_usar(c, ferramenta, cfg, producao=True):
            return c
    for p in lista(cfg, com_contratados=False):
        if pode_usar(p["id"], ferramenta, cfg, producao=True):
            return p["id"]
    return None


def pode_alterar_permissoes(quem: str, alvo: str) -> bool:
    """Mudança MANUAL de permissões: só o dono. Ninguém mexe nas próprias permissões. (Promoção por política, medida
    nos registros, segue robo/rh_desempenho.py: RH propõe, o gestor — outra pessoa — valida, e o que dá direito de
    alterar dados ou tira alguém do estágio continua sendo decisão do dono.)"""
    return quem == DONO and alvo != DONO


def lotacao(cfg=None) -> dict:
    """Andar → nível → ids (prova de que todo andar está completo)."""
    andares: dict[int, dict[str, list[str]]] = {}
    for p in lista(cfg, com_contratados=cfg is not None):
        andares.setdefault(p["andar"], {}).setdefault(nivel_de(p["id"], p), []).append(p["id"])
    return andares
