"""Liderança executiva, ciência de dados e sala de RH: diretores, heads, cientistas de dados e time de Pessoas.

Hierarquia (de cima para baixo): Dono → Diretor(a) → Head → Gerente → Coordenador(a) → Especialista/Sênior → Pleno →
Júnior → Estagiário. Nenhum cargo existe só para enfeitar: cada um tem uma ferramenta real e uma prova técnica.

  Diretor(a) — responde pelo RESULTADO da área: scorecard com metas e farol (verde/amarelo/vermelho) calculado dos
               registros, prioridades da área e decisões que sobem para o dono. Escopo inspirado no papel de CDAO da
               Gartner (valor gerado pelos dados, governança e confiabilidade da informação), no modelo de competências
               da SHRM (Pessoas) e nos objetivos de nível de serviço do livro de SRE do Google (Tecnologia).
  Head       — autoridade TÉCNICA acima de todos da área: auditoria semanal por amostragem, refazendo por outro
               caminho o que a equipe entregou (é assim que se confia no resultado sem refazer tudo).
  Cientistas — drivers do indicador, segmentação de clientes e anomalias (robo/ciencia.py).
  RH         — recrutamento e seleção, treinamento e desenvolvimento, desempenho e people analytics.
"""

from __future__ import annotations

from datetime import datetime, timedelta

FONTES = {
    "gartner_cdao": "Gartner — papel do Chief Data & Analytics Officer (valor, governança, confiabilidade da informação)",
    "dama": "DAMA-DMBOK — papéis de governança: data owner decide, data steward executa, custodian protege",
    "shrm": "SHRM HR Competency Model — 9 competências (HR Expertise + 8 comportamentais)",
    "oxygen": "Google Project Oxygen — 10 comportamentos de bons gestores (coach, desenvolvimento de carreira, decisão…)",
    "ccl_702010": "Center for Creative Leadership — modelo 70-20-10 (experiência, relações/feedback, cursos)",
    "ccl_sbi": "Center for Creative Leadership — feedback SBI (Situação, Comportamento, Impacto)",
    "sre": "Google SRE — objetivos de nível de serviço (SLO) e orçamento de erro",
    "kda": "Key driver analysis — correlação + regressão padronizada + VIF para colinearidade (Bain, prática de CX)",
}


def _p(id, nome, cargo, nivel, andar, area, gestor, cor, escopo, criterios, metodologias, nao_faz, ferramentas):
    return {"id": id, "nome": nome, "cargo": cargo, "papel": cargo.split(" — ")[0], "nivel": nivel, "andar": andar,
            "area": area, "gestor": gestor, "cor": cor, "escopo": escopo, "criterios": criterios,
            "metodologias": metodologias, "nao_faz": nao_faz, "ferramentas": ferramentas, "descricao": "; ".join(escopo)}


EQUIPE = [
    # ------------------------------------------------------------------ diretoria
    _p("dir_dados", "Beatriz", "Diretora de Dados e Engenharia (CDO)", "diretor", 1, "Engenharia de Dados", "dono", "#0B1F4D",
       ["Responde pelo valor e pela confiabilidade dos dados que a empresa publica",
        "Acompanha o scorecard do 1º andar (aprovação, erros repetidos, divergências, rotinas) e leva ao dono o que está vermelho",
        "Dona dos dados (data owner): decide regras e prioridades; a execução é da equipe"],
       ["Scorecard do 1º andar sem vermelho por 4 semanas", "Toda divergência calculadora × banco explicada"],
       [FONTES["gartner_cdao"], FONTES["dama"], FONTES["sre"]],
       ["Não executa etapa operacional", "Não aprova o próprio pedido; decisões que alteram dados sobem para o dono"],
       ["scorecard", "reuniao_andar"]),
    _p("dir_analytics", "Rogério", "Diretor de Analytics, Ciência de Dados e BI", "diretor", 2, "Customer Insights e Pesquisa", "dono",
       "#3B0764",
       ["Responde pela qualidade das análises, dos modelos e das entregas em Excel (2º e 3º andares)",
        "Cobra que todo número tenha conta aberta, conferência no banco e base suficiente",
        "Decide o que vira recomendação para o negócio e o que ainda é hipótese"],
       ["100% dos cálculos aplicáveis conferidos no banco", "Auditorias dos heads aprovadas"],
       [FONTES["gartner_cdao"], FONTES["kda"], FONTES["oxygen"]],
       ["Não publica número sem conferência", "Não confunde correlação com causa"], ["scorecard", "reuniao_andar"]),
    _p("dir_operacoes", "Cláudia", "Diretora de Operações e Governança", "diretor", 4, "Governança e Privacidade", "dono", "#7C2D12",
       ["Garante que pedidos, aprovações, handovers e reuniões andem no prazo",
        "Responde pela LGPD e pelo catálogo de dados", "Destrava o que está parado há mais de 14 dias"],
       ["Nenhuma aprovação esperando mais de 48 h", "Nenhum handover parado há mais de 14 dias"],
       [FONTES["dama"], FONTES["oxygen"]], ["Não decide por você o que precisa da sua aprovação"],
       ["scorecard", "reuniao_andar", "raio_x"]),
    _p("dir_pessoas", "Marta", "Diretora de Pessoas e Cultura (CHRO)", "diretor", 4, "Pessoas e Cultura", "dono", "#831843",
       ["Responde por contratação, desenvolvimento, desempenho e desligamentos",
        "Garante que a liderança desenvolva pessoas: feedback SBI, plano de desenvolvimento 70-20-10, estudo 2x por semana",
        "Leva ao dono as propostas de promoção e de desligamento, sempre com dados"],
       ["100% aprovados nas provas", "Rodada de estudo em dia", "Todo desempenho insuficiente com plano de melhoria"],
       [FONTES["shrm"], FONTES["oxygen"], FONTES["ccl_702010"], FONTES["ccl_sbi"]],
       ["Não desliga nem promove: propõe; quem decide é o dono"], ["scorecard", "people_analytics", "reuniao_andar"]),
    _p("dir_tecnologia", "Alexandre", "Diretor de Tecnologia (CTO)", "diretor", 5, "Engenharia de Dados", "dono", "#111827",
       ["Responde pela disponibilidade, segurança e recuperação do sistema",
        "Define os objetivos de nível de serviço: ronda saudável, backup diário, zero rotina com erro, painel com senha",
        "Prioriza a dívida técnica que gera erro repetido"],
       ["Ronda de TI saudável", "Backup em dia", "Painel com senha"], [FONTES["sre"]],
       ["Não envia nada para a nuvem (decisão do dono)"], ["scorecard", "ronda_ti", "reuniao_andar"]),
    # ------------------------------------------------------------------ heads (autoridade técnica)
    _p("head_engenharia", "Eduardo", "Head de Engenharia de Dados", "head", 1, "Engenharia de Dados", "dir_dados", "#1E3A8A",
       ["Maior autoridade técnica do 1º andar: define padrões de ingestão, limpeza, modelagem e carga",
        "Auditoria semanal por amostragem: relê bases publicadas e confere linhas com o histórico e com o PostgreSQL",
        "Revisa as boas práticas novas do andar"],
       ["Auditoria semanal feita", "Nenhuma diferença de linhas entre arquivo, histórico e banco"],
       [FONTES["dama"], FONTES["sre"]], ["Não aprova o próprio trabalho"], ["auditoria", "diagnosticar_planilha", "consulta_sql"]),
    _p("head_ciencia", "Natália", "Head de Ciência de Dados", "head", 2, "Estatística", "dir_analytics", "#4C1D95",
       ["Maior autoridade técnica em estatística e modelos", "Auditoria semanal: recalcula o NPS das análises publicadas "
        "por outro caminho e compara", "Valida método de drivers, segmentação e testes"],
       ["Auditoria semanal feita", "Nenhum indicador publicado diferente do recálculo"],
       [FONTES["kda"], FONTES["gartner_cdao"]], ["Não aprova o próprio modelo"],
       ["auditoria", "calcular", "drivers", "segmentacao", "anomalias"]),
    _p("head_bi", "Felipe", "Head de BI e Excel", "head", 3, "Storytelling e Negócio", "dir_analytics", "#14532D",
       ["Maior autoridade técnica em Excel, Power Query e entregas", "Auditoria semanal: reabre entregas Excel e confere "
        "fórmulas vivas e integridade"], ["Auditoria semanal feita", "Nenhuma entrega com fórmula quebrada"],
       [FONTES["gartner_cdao"]], ["Não assina a própria entrega"], ["auditoria", "calcular"]),
    _p("head_governanca", "Simone", "Head de Governança de Dados", "head", 4, "Governança e Privacidade", "dir_operacoes", "#92400E",
       ["Maior autoridade em governança e LGPD", "Auditoria semanal: procura dado pessoal nas bases publicadas"],
       ["Auditoria semanal feita", "Nenhum dado pessoal publicado sem decisão registrada"], [FONTES["dama"]],
       ["Não decide sozinha publicar dado pessoal"], ["auditoria", "dados_pessoais"]),
    _p("head_rh", "Juliana", "Head de Gente e Gestão", "head", 4, "Pessoas e Cultura", "dir_pessoas", "#9D174D",
       ["Maior autoridade em desenvolvimento de pessoas e gestão", "Auditoria semanal: confere se todos passaram nas provas e "
        "se a rodada de estudo está em dia", "Forma a liderança: 1:1, feedback SBI, plano 70-20-10"],
       ["Auditoria semanal feita", "Liderança com plano de desenvolvimento para cada pessoa abaixo da meta"],
       [FONTES["shrm"], FONTES["oxygen"], FONTES["ccl_702010"], FONTES["ccl_sbi"]], ["Não desliga nem promove"],
       ["auditoria", "people_analytics", "desempenho"]),
    _p("head_ti", "André", "Head de Infraestrutura e Segurança", "head", 5, "Governança e Privacidade", "dir_tecnologia", "#7F1D1D",
       ["Maior autoridade técnica em infraestrutura e segurança", "Auditoria semanal: backup, ronda e rotinas com erro"],
       ["Auditoria semanal feita", "Nenhuma rotina com erro sem handover"], [FONTES["sre"]],
       ["Não desliga controles de segurança"], ["auditoria", "ronda_ti"]),
    # ------------------------------------------------------------------ cientistas de dados (2º andar)
    _p("cd_senior_drivers", "Vinícius", "Cientista de Dados Sênior — Drivers", "senior", 2, "Estatística", "head_ciencia", "#6D28D9",
       ["Descobre o que mais influencia o NPS/CSAT (key driver analysis)", "Avisa quando atributos são parecidos demais (VIF)"],
       ["Ranking com correlação, peso e aviso de colinearidade", "Nunca chama associação de causa"], [FONTES["kda"]],
       ["Não afirma causa"], ["drivers", "calcular"]),
    _p("cd_pleno_segmentos", "Carolina", "Cientista de Dados Pleno — Segmentação", "pleno", 2, "Análise de Dados", "head_ciencia",
       "#7E22CE", ["Agrupa clientes parecidos (k-means) e descreve cada grupo", "Diz quando a separação é fraca"],
       ["Grupos com tamanho, médias e qualidade (silhueta)"], ["k-means++ com silhueta"],
       ["Não cria persona com separação fraca"], ["segmentacao", "calcular"]),
    _p("cd_junior_anomalias", "Lucas", "Cientista de Dados Júnior — Anomalias", "junior", 2, "Qualidade de Dados", "cd_senior_drivers",
       "#A855F7", ["Aponta valores fora do padrão com a linha de origem"], ["Achado com linha e faixa normal"],
       ["Regra de Tukey (3×IQR)"], ["Não exclui dado: só aponta"], ["anomalias"]),
    # ------------------------------------------------------------------ sala de RH (4º andar)
    _p("rh_rs", "Priscila", "Analista de Recrutamento e Seleção Pleno", "pleno", 4, "Pessoas e Cultura", "canal_helena", "#DB2777",
       ["Acompanha contratações automáticas e manuais, experiência de 3 meses e efetivações"],
       ["Toda contratação com prova técnica e líder responsável"], [FONTES["shrm"]],
       ["Não contrata sem prova técnica"], ["recrutamento"]),
    _p("rh_td", "Roberta", "Analista de Treinamento e Desenvolvimento Pleno", "pleno", 4, "Pessoas e Cultura", "canal_helena", "#EC4899",
       ["Monta a trilha de desenvolvimento de cada pessoa com os erros dela e os handovers do andar (70-20-10)",
        "Acompanha a rodada de estudo 2x por semana"], ["Trilha individual para quem tem erro na semana"],
       [FONTES["ccl_702010"]], ["Não marca estudo que não aconteceu"], ["desenvolvimento"]),
    _p("rh_desempenho", "Mauro", "Analista de Desempenho Sênior", "senior", 4, "Pessoas e Cultura", "canal_helena", "#BE185D",
       ["Calcula desempenho (acertos ÷ eventos), aponta quem precisa de plano de melhoria", "Prepara a parte de pessoas da reunião"],
       ["Classificação igual à política de RH"], [FONTES["oxygen"], FONTES["ccl_sbi"]], ["Não propõe desligamento sem 2 reuniões"],
       ["desempenho", "people_analytics"]),
    _p("rh_people", "Tiago", "Analista de People Analytics Pleno", "pleno", 4, "Pessoas e Cultura", "rh_desempenho", "#F472B6",
       ["Indicadores de pessoas: quadro por andar e nível, aprovação nas provas, desempenho médio, contratações e desligamentos"],
       ["Números batem com o registro de funcionários"], [FONTES["shrm"]], ["Não expõe dado fora da empresa"],
       ["people_analytics"]),
    # ------------------------------------------------------------------ guilda Python (5º andar): a mais cobrada da empresa
    _p("head_python", "Henrique", "Head de Engenharia Python", "head", 5, "Engenharia de Dados", "dir_tecnologia", "#1D4ED8",
       ["Maior autoridade técnica em Python da empresa", "Lidera a guilda de bibliotecas e olha a operação de forma "
        "estratégica: desempenho por volume, projeção de crescimento, dívida técnica e avisos de depreciação",
        "Decide quando atualizar uma biblioteca (só com todas as revisões passando)"],
       ["Revisões das bibliotecas todas verdes", "Projeção de volume atualizada", "Exigência: 90% de acerto"],
       [FONTES["sre"]], ["Não atualiza biblioteca sem revisão verde"], ["revisao_biblioteca", "estrategia_python"]),
    _p("esp_pandas", "Sofia", "Especialista em pandas", "especialista", 5, "Engenharia de Dados", "head_python", "#150458",
       ["Garante que agrupamentos, tipos, leitura de planilhas e conversões do pandas se comportam como o robô espera",
        "Pega avisos de depreciação antes de virarem erro na próxima versão"],
       ["Revisão do pandas verde", "Exigência: 90% de acerto"], ["pandas: groupby, dtypes nulláveis, IO"],
       ["Não aceita 'funciona na minha máquina'"], ["revisao_biblioteca", "calcular"]),
    _p("esp_numpy", "Nicolas", "Especialista em numpy", "especialista", 5, "Estatística", "head_python", "#4DABCF",
       ["Garante a matemática por trás de drivers, segmentação e correlação (mínimos quadrados, sementes, precisão)"],
       ["Revisão do numpy verde", "Exigência: 90% de acerto"], ["numpy: álgebra linear, aleatoriedade reproduzível"],
       ["Não troca método sem prova"], ["revisao_biblioteca"]),
    _p("esp_openpyxl", "Olívia", "Especialista em openpyxl (Excel)", "especialista", 5, "Engenharia de Dados", "head_python",
       "#107C41", ["Garante que fórmulas, formatos e células mescladas do Excel são lidos e gravados corretamente"],
       ["Revisão do openpyxl verde", "Exigência: 90% de acerto"], ["openpyxl: fórmulas, data_only, estilos"],
       ["Não grava número por cima de fórmula"], ["revisao_biblioteca"]),
    _p("esp_xlrd", "Xavier", "Especialista em xlrd (.xls antigo)", "especialista", 5, "Engenharia de Dados", "head_python", "#217346",
       ["Garante a leitura de planilhas .xls antigas e conhece os limites delas (sem macro, sem .xlsx)"],
       ["Revisão do xlrd verde", "Exigência: 90% de acerto"], ["xlrd 2.x"], ["Não promete o que o .xls não guarda"],
       ["revisao_biblioteca"]),
    _p("esp_yaml", "Elisa", "Especialista em PyYAML (configuração)", "especialista", 5, "Governança e Privacidade", "head_python",
       "#CB171E", ["Garante que o config.yaml é lido com segurança (safe_load) e sem perder acento"],
       ["Revisão do PyYAML verde", "Exigência: 90% de acerto"], ["PyYAML safe_load/safe_dump"],
       ["Não usa load inseguro"], ["revisao_biblioteca"]),
    _p("esp_psycopg", "Pietro", "Especialista em psycopg (PostgreSQL)", "especialista", 5, "Engenharia de Dados", "head_python",
       "#336791", ["Garante SQL composto com segurança, parâmetros separados do texto e transações corretas"],
       ["Revisão do psycopg verde", "Exigência: 90% de acerto"], ["psycopg 3: sql.Composed, COPY, transações"],
       ["Não cola valor dentro do SQL"], ["revisao_biblioteca", "consulta_sql"]),
    _p("esp_sqlite", "Silas", "Especialista em sqlite3 (memória da empresa)", "especialista", 5, "Engenharia de Dados",
       "head_python", "#003B57", ["Garante que a memória da empresa (trabalho.db) grava tudo ou nada e aguenta reinício"],
       ["Revisão do sqlite3 verde", "Exigência: 90% de acerto"], ["sqlite3: transações, WAL"],
       ["Não grava fora de transação"], ["revisao_biblioteca"]),
    _p("rh_estagiaria", "Lorena", "Estagiária de RH", "estagiario", 4, "Pessoas e Cultura", "rh_desempenho", "#F9A8D4",
       ["Acompanha os indicadores de desempenho em modo observação"], ["Relato correto"], [FONTES["oxygen"]],
       ["Não altera nem decide nada"], ["desempenho"]),
    # ------------------------------------------------------------------ Sala de Casos (4º andar, responde ao dono)
    # Quem prepara o trabalho de treino de TODA a empresa precisa saber mais do que quem vai fazê-lo: cada designer só
    # gera casos da competência em que passou no exame dos 5 níveis (inclusive o desafio), e nada vai para ninguém sem
    # a revisão independente. Ficam fora dos andares que avaliam para não avaliar o próprio chefe.
    _p("head_casos", "Otávio", "Head da Sala de Casos — treino contínuo da empresa", "head", 4, "Treinamento e Avaliação", "dono",
       "#0E7490", ["Responde pelo catálogo de competências e níveis (o que cada cargo precisa saber fazer)",
                   "Certifica os designers: exame com um caso de cada nível, revisado pela revisora",
                   "Suspende a certificação de quem teve 2 casos reprovados nos últimos 10"],
       ["100% dos designers certificados na versão atual de cada gerador", "Nenhum caso sem revisão chegou a alguém"],
       [FONTES["ccl_702010"], "Avaliação por evidência: gabarito conhecido e conferido por outro caminho"],
       ["Não corrige tentativa de ninguém à mão: a correção é objetiva, pelo gabarito",
        "Não aprova o caso de um designer (quem revisa é a revisora)"], []),
    _p("casos_engenharia", "Lívia", "Designer de Casos — Engenharia de Dados", "especialista", 4, "Treinamento e Avaliação",
       "head_casos", "#0891B2", ["Gera os casos de limpeza de planilha, leitura de histórico e SQL, com a sujeira de cada nível",
                                 "Calcula o gabarito a partir dos dados limpos ANTES de sujá-los"],
       ["Casos aprovados na revisão", "Casos reprodutíveis pela semente"], ["Geração de dados com resposta conhecida"],
       ["Não revisa os próprios casos"], []),
    _p("casos_analytics", "Murilo", "Designer de Casos — Analytics e Ciência de Dados", "especialista", 4,
       "Treinamento e Avaliação", "head_casos", "#06B6D4",
       ["Gera os casos de cálculo, NPS, anomalias, segmentação e drivers", "Planta o que precisa ser achado (grupos, outliers, driver)"],
       ["Casos aprovados na revisão", "Gabarito sem ambiguidade (folga mínima entre a resposta certa e a 2ª)"],
       ["Estatística aplicada", "Dados sintéticos com estrutura plantada"], ["Não revisa os próprios casos"], []),
    _p("casos_governanca", "Raquel", "Designer de Casos — Governança, Pessoas e Conhecimento", "especialista", 4,
       "Treinamento e Avaliação", "head_casos", "#0D9488",
       ["Gera os casos de LGPD (com iscas), desempenho de RH, resumo executivo e busca no conhecimento"],
       ["Casos aprovados na revisão", "Toda isca comprovadamente não é dado pessoal"], ["LGPD", "Política de desempenho"],
       ["Não revisa os próprios casos"], []),
    _p("casos_ti", "Augusto", "Designer de Casos — TI e Segurança", "especialista", 4, "Treinamento e Avaliação", "head_casos",
       "#155E75", ["Monta computadores de teste com problemas plantados para a ronda de TI"],
       ["Casos aprovados na revisão", "Nível desafio testa também o que NÃO existe (alarme falso)"], ["SRE", "Segurança"],
       ["Não mexe no computador de produção"], []),
    _p("casos_revisor", "Valéria", "Revisora Independente de Casos", "especialista", 4, "Treinamento e Avaliação", "head_casos",
       "#164E63", ["Revisa CADA caso antes de ir para alguém: refaz pela semente, refaz o gabarito por outro caminho e confirma a sujeira",
                   "Reprova e devolve com o motivo; reprovação conta contra o designer"],
       ["Zero caso com gabarito errado entregue"], ["Dupla checagem independente (four-eyes)"], ["Não gera casos"], []),
    _p("casos_planejamento", "Yasmin", "Planejadora de Treino", "senior", 4, "Treinamento e Avaliação", "head_casos", "#0F766E",
       ["Distribui o trabalho: quem está há mais tempo sem treinar primeiro, na competência mais antiga, no nível da pessoa",
        "Aplica a regra de nível: 4 de 5 certas sobe; 2 ou menos desce — sempre com as tentativas como prova"],
       ["Todos os elegíveis treinando toda semana", "Toda mudança de nível com evidência"], ["Aprendizagem adaptativa"],
       ["Não muda nível na mão"], []),
]
POR_ID = {p["id"]: p for p in EQUIPE}

GUILDA_PYTHON = ["head_python", "esp_pandas", "esp_numpy", "esp_openpyxl", "esp_xlrd", "esp_yaml", "esp_psycopg", "esp_sqlite"]
# os mais cobrados da empresa: acerto mínimo de 90% (o resto da empresa: 70%)
EXIGENCIA = {pid: 90.0 for pid in GUILDA_PYTHON}

# quem passa a responder a quem (os gerentes existentes ganham head ou diretor acima)
NOVOS_GESTORES = {"ger_engenharia": "head_engenharia", "ger_analise": "dir_analytics", "excel_supervisor": "head_bi",
                  "ger_operacoes": "dir_operacoes", "canal_helena": "head_rh", "ger_ti": "head_ti"}
DIRETOR_DO_ANDAR = {1: "dir_dados", 2: "dir_analytics", 3: "dir_analytics", 4: "dir_operacoes", 5: "dir_tecnologia"}
HEAD_DO_ANDAR = {1: "head_engenharia", 2: "head_ciencia", 3: "head_bi", 4: "head_governanca", 5: "head_ti"}


# =============================================================================== scorecards da diretoria
def _ind(nome, valor, meta, farol, fonte, texto_valor=None):
    return {"indicador": nome, "valor": valor, "valor_texto": texto_valor if texto_valor is not None else str(valor),
            "meta": meta, "farol": farol, "fonte": fonte}


def farol(valor, verde, amarelo, maior_melhor=True) -> str:
    """verde/amarelo/vermelho; None = cinza (sem dado)."""
    if valor is None:
        return "cinza"
    if maior_melhor:
        return "verde" if valor >= verde else "amarelo" if valor >= amarelo else "vermelho"
    return "verde" if valor <= verde else "amarelo" if valor <= amarelo else "vermelho"


def scorecard(cfg, diretor: str) -> dict:
    from robo import historico, memoria, organizacao, rotinas
    from robo.trabalho import Trabalho
    tb = Trabalho(cfg)
    semana = (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds")
    inds = []
    if diretor == "dir_dados":
        h7 = [h for h in historico.ler(cfg.logs, 5000) if str(h.get("data_hora", "")).replace(" ", "T") >= semana]
        aprov = [h for h in h7 if h.get("status") in ("sucesso", "reprovado")]
        taxa = round(100 * sum(h["status"] == "sucesso" for h in aprov) / len(aprov)) if aprov else None
        inds.append(_ind("Planilhas aprovadas na semana", taxa, "≥ 90%", farol(taxa, 90, 75),
                         "histórico de execuções", f"{taxa}%" if taxa is not None else "sem planilha"))
        hos = memoria.handovers(cfg, 1, abertos=True, limite=1000)
        inds.append(_ind("Handovers abertos no 1º andar", len(hos), "≤ 3", farol(len(hos), 3, 8, False), "handovers"))
        rep = sum(1 for h in hos if h["recorrencias"] >= 3)
        inds.append(_ind("Erros repetidos 3+ vezes sem correção", rep, "0", farol(rep, 0, 1, False), "handovers"))
        div = len(tb.memorias("conferencia_calculo", "divergente", 100_000))
        inds.append(_ind("Divergências calculadora × banco", div, "0", farol(div, 0, 0, False), "conferências"))
    elif diretor == "dir_analytics":
        conf = tb.memorias("conferencia_calculo", limite=100_000)
        aplic = [m for m in conf if m["chave"] in ("conferido", "divergente")]
        pct = round(100 * sum(m["chave"] == "conferido" for m in aplic) / len(aplic)) if aplic else None
        inds.append(_ind("Cálculos conferidos no banco (entre os aplicáveis)", pct, "100%", farol(pct, 100, 95),
                         "conferências", f"{pct}%" if pct is not None else "sem cálculo conferível"))
        tarefas = [t for t in tb.listar(dias=30, limite=5000) if t["tipo"] == "tarefa" and t["andar"] in (2, 3)
                   and t["estado"] in ("concluida", "concluida_parcialmente")]
        inteiras = round(100 * sum(t["estado"] == "concluida" for t in tarefas) / len(tarefas)) if tarefas else None
        inds.append(_ind("Tarefas de análise entregues por inteiro (30 dias)", inteiras, "≥ 80%", farol(inteiras, 80, 60),
                         "central de solicitações", f"{inteiras}%" if inteiras is not None else "sem tarefa"))
        d = [x for x in memoria.desempenho(cfg, 7) if x["andar"] in (2, 3) and x["taxa"] is not None]
        media = round(sum(x["taxa"] for x in d) / len(d)) if d else None
        inds.append(_ind("Acerto médio da equipe (2º e 3º andares)", media, "≥ 90%", farol(media, 90, 70), "memória",
                         f"{media}%" if media is not None else "sem eventos"))
    elif diretor == "dir_operacoes":
        limite48 = (datetime.now() - timedelta(hours=48)).isoformat(timespec="seconds")
        velhas = [a for a in tb.aprovacoes_pendentes() if a["criada_em"] < limite48]
        inds.append(_ind("Aprovações esperando mais de 48 h", len(velhas), "0", farol(len(velhas), 0, 2, False), "aprovações"))
        limite14 = (datetime.now() - timedelta(days=14)).isoformat(timespec="seconds")
        parados = [h for h in memoria.handovers(cfg, abertos=True, limite=5000) if str(h["criado_em"]) < limite14]
        inds.append(_ind("Handovers parados há mais de 14 dias", len(parados), "0", farol(len(parados), 0, 3, False), "handovers"))
        bp30 = [b for b in memoria.boas_praticas(cfg, limite=1000)
                if b["criada_em"] >= (datetime.now() - timedelta(days=30)).isoformat(timespec="seconds")]
        inds.append(_ind("Boas práticas criadas em 30 dias", len(bp30), "≥ 1", farol(len(bp30), 1, 0), "boas práticas"))
        reu = next((r for r in rotinas.estado(cfg) if r["nome"] == "reuniao"), {})
        inds.append(_ind("Reunião semanal em dia", 0 if reu.get("atrasada") else 1, "sim",
                         "vermelho" if reu.get("atrasada") else "verde", "rotinas", "não" if reu.get("atrasada") else "sim"))
    elif diretor == "dir_pessoas":
        d = memoria.desempenho(cfg, 7)
        insuf = [x for x in d if x["situacao"] == "insuficiente"]
        inds.append(_ind("Pessoas com desempenho insuficiente", len(insuf), "0", farol(len(insuf), 0, 2, False), "memória"))
        from robo import desenvolvimento
        u = desenvolvimento.ultima_rodada(cfg)
        dias = round((datetime.now() - datetime.fromisoformat(u["criada_em"])).total_seconds() / 86400, 1) if u else None
        inds.append(_ind("Dias desde a última rodada de estudo", dias, "≤ 3,5", farol(dias, 3.5, 7, False), "rotinas",
                         f"{dias}" if dias is not None else "nunca"))
        pa = people_analytics(cfg)
        inds.append(_ind("Aprovados nas provas técnicas", pa["pct_aprovados"], "100%", farol(pa["pct_aprovados"], 100, 95),
                         "RH", f"{pa['pct_aprovados']}%"))
        com_mem = pa["pct_com_memoria_30d"]
        inds.append(_ind("Pessoas com memória registrada (30 dias)", com_mem, "≥ 80%", farol(com_mem, 80, 50), "memória",
                         f"{com_mem}%"))
    elif diretor == "dir_tecnologia":
        from robo import backup, ti
        r = ti.ultima_ronda(cfg) or {}
        inds.append(_ind("Última ronda de TI saudável", 1 if r.get("saudavel") else 0, "sim",
                         "verde" if r.get("saudavel") else ("cinza" if not r else "vermelho"), "ronda de TI",
                         "sim" if r.get("saudavel") else ("sem ronda" if not r else "não")))
        if cfg.banco.get("habilitado"):
            b = backup.ultimo(cfg) or {}
            horas = None
            if b.get("ok") and b.get("data_hora"):
                horas = round((datetime.now() - datetime.strptime(b["data_hora"], "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600, 1)
            inds.append(_ind("Horas desde o último backup", horas, "≤ 24", farol(horas, 24, 48, False), "backup",
                             f"{horas}" if horas is not None else "sem backup"))
        erros = [e for e in rotinas.execucoes(cfg, limite=500) if e["status"] == "erro"
                 and e["inicio"] >= (datetime.now() - timedelta(hours=24)).isoformat(timespec="seconds")]
        inds.append(_ind("Rotinas com erro nas últimas 24 h", len(erros), "0", farol(len(erros), 0, 1, False), "rotinas"))
        senha = bool((cfg.painel or {}).get("senha_hash"))
        inds.append(_ind("Painel com senha", 1 if senha else 0, "sim", "verde" if senha else "vermelho", "configuração",
                         "sim" if senha else "não"))
    vermelhos = [i for i in inds if i["farol"] == "vermelho"]
    nome = POR_ID.get(diretor, {}).get("nome", diretor)
    parecer = (f"{nome}: área em ordem, todos os indicadores dentro da meta." if not vermelhos and not
               any(i["farol"] == "amarelo" for i in inds) else
               f"{nome}: {len(vermelhos)} indicador(es) no vermelho — " + "; ".join(
                   f"{i['indicador']} ({i['valor_texto']}, meta {i['meta']})" for i in vermelhos) if vermelhos else
               f"{nome}: sem vermelho, mas com ponto de atenção — " + "; ".join(
                   f"{i['indicador']} ({i['valor_texto']}, meta {i['meta']})" for i in inds if i["farol"] == "amarelo"))
    return {"diretor": diretor, "nome": nome, "indicadores": inds, "parecer": parecer,
            "data_hora": datetime.now().isoformat(timespec="seconds")}


# =============================================================================== RH
def pct(parte: int, total: int) -> int:
    return round(100 * parte / total) if total else 0


def people_analytics(cfg) -> dict:
    from robo import contratacao, memoria, organizacao, rh
    gente = organizacao.lista(cfg)
    por_andar, por_nivel = {}, {}
    for p in gente:
        por_andar[p["andar"]] = por_andar.get(p["andar"], 0) + 1
        n = organizacao.nivel_de(p["id"], p)
        por_nivel[n] = por_nivel.get(n, 0) + 1
    aprov = 0
    for p in gente:
        try:
            aprov += bool(rh.ficha(p.get("_agente") or {"id": p["id"], "habilidades": []})["provas"]["aprovado"])
        except Exception:
            pass
    d30 = memoria.desempenho(cfg, 30)
    com_mem = sum(1 for x in d30 if x["eventos"] or x["aprendizados"])
    taxas = [x["taxa"] for x in d30 if x["taxa"] is not None]
    try:
        cont = contratacao.resumo(cfg)
    except Exception:
        cont = {}
    return {"total": len(gente), "por_andar": por_andar, "por_nivel": por_nivel,
            "pct_aprovados": pct(aprov, len(gente)), "pct_com_memoria_30d": pct(com_mem, len(gente)),
            "acerto_medio_30d": round(sum(taxas) / len(taxas)) if taxas else None,
            "insuficientes": [x["nome"] for x in d30 if x["situacao"] == "insuficiente"], "contratacao": cont}


def trilha_individual(erros: list[dict], handovers: list[dict], boas: list[dict]) -> list[str]:
    """Plano 70-20-10 de uma pessoa, montado só com o que aconteceu com ela e com o andar."""
    itens = []
    for e in erros[:3]:  # 70%: aprender no trabalho, com o próprio erro
        itens.append(f"70% (no trabalho): refazer com acompanhamento o caso “{e['resumo'][:80]}” e registrar o que mudou")
    for h in handovers[:2]:  # 20%: com outras pessoas
        itens.append(f"20% (com o líder): 1:1 com feedback SBI sobre {h['id']} — {h['regra'][:100]}")
    for b in boas[:2]:  # 10%: estudo formal
        itens.append(f"10% (estudo): ler e aplicar a boa prática {b['id']} — {b['pratica'][:100]}")
    if not itens:
        itens.append("Sem erro nem pendência na semana: manter a rodada de estudo e ensinar um colega (mentoria)")
    return itens


# =============================================================================== provas técnicas
def provas() -> dict:
    from robo import ciencia, contratacao
    import pandas as pd
    r = {}
    for d in ("dir_dados", "dir_analytics", "dir_operacoes", "dir_pessoas", "dir_tecnologia"):
        r[d] = [("Meta atingida fica verde", farol(95, 90, 75) == "verde"),
                ("Abaixo do mínimo fica vermelho", farol(50, 90, 75) == "vermelho"),
                ("Sem dado fica cinza (não inventa)", farol(None, 90, 75) == "cinza"),
                ("Indicador 'menor é melhor' correto", farol(0, 0, 2, False) == "verde" and farol(5, 0, 2, False) == "vermelho")]
    from robo import auditoria
    r.update(auditoria.provas())
    r.update(ciencia.provas())
    from robo import bibliotecas
    r.update(bibliotecas.provas())
    from robo import treino
    r.update(treino.provas())
    emails = pd.Series(["a@b.com", "c@d.com.br", "x@y.org"] * 5)
    r["rh_rs"] = [("Reconhece demanda de e-mail para contratar", (contratacao.reconhecer(emails, "contato") or {}).get("habilidade") is not None),
                  ("Não contrata para coluna de nota", contratacao.reconhecer(pd.Series([1, 2, 3] * 5), "nota") is None)]
    t = trilha_individual([{"resumo": "nota fora da faixa"}], [{"id": "HO-1", "regra": "corrigir na origem"}],
                          [{"id": "BP-1", "pratica": "conferir faixa"}])
    r["rh_td"] = [("Trilha 70-20-10 com o erro real", len(t) == 3 and t[0].startswith("70%") and "nota fora" in t[0]),
                  ("Sem erro, propõe mentoria (não inventa lacuna)", "mentoria" in trilha_individual([], [], [])[0])]
    from robo.memoria import situacao
    r["rh_desempenho"] = [("Classifica insuficiente (1 de 6)", situacao(1, 5) == "insuficiente"),
                          ("Classifica bom (19 de 20)", situacao(19, 1) == "ok"), ("Poucos eventos = sem dados", situacao(0, 0) == "sem_dados")]
    r["rh_estagiaria"] = list(r["rh_desempenho"])
    r["rh_people"] = [("Percentual do indicador correto (3 de 4 = 75%)", pct(3, 4) == 75),
                      ("Sem ninguém no quadro não divide por zero", pct(0, 0) == 0),
                      ("Classificação usada é a da política", situacao(2, 3) == "insuficiente")]
    r["head_rh"] = r.get("head_rh", []) + [("Conhece a regra de desempenho", situacao(1, 5) == "insuficiente")]
    return r
