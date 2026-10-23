"""Dicionário de dados da empresa: cada tabela do banco de registros, para que serve, o que é UMA linha, a regra de
proteção e como serve a Machine Learning. A documentação (documentacao/banco_de_dados.md) é GERADA daqui — o texto
nunca fica diferente do código — e um teste falha se aparecer tabela sem descrição.

estado(cfg) mostra o banco ao vivo: linhas por tabela, proteção, integridade, último backup e a cópia no PostgreSQL.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

IMUTAVEL = "só acrescenta (imutável: não altera nem apaga)"
SITUACAO = "registro com situação (a situação muda; a linha nunca some)"
ESTADO_ATUAL = "estado atual (sobrescrito de propósito; a história fica em outra tabela)"

GRUPOS = {
    "pessoas": "Pessoas e memória (o que cada funcionário fez, errou e aprendeu)",
    "trabalho": "Trabalho (central de solicitações, conversas e entregas)",
    "conhecimento": "Conhecimento e aprendizado (lições, regras aprendidas, cadeia de integridade)",
    "treino": "Treino contínuo e laboratório (casos com gabarito, tentativas e níveis)",
    "reunioes": "Reuniões e decisões (atas, eventos e cobrança)",
    "operacao": "Operação, TI e qualidade (rotinas, ferramentas, erros, auditorias e backups)",
}

# tabela → (grupo, para que serve, o que é 1 linha, regra, uso em Machine Learning)
TABELAS = {
    "experiencias": ("pessoas", "Memória de cada funcionário: acertos, erros, aprendizados, colaboração e treinamento",
                     "um acontecimento de uma pessoa (com origem: produção, treino, laboratório, estudo…)", IMUTAVEL,
                     "série temporal de desempenho por pessoa; rótulo acerto/erro por origem"),
    "handovers": ("pessoas", "Cada tipo de erro vira um handover para a área: causa, regra, como verificar e PDCA",
                  "um tipo de erro numa base (repetição soma recorrência)", SITUACAO,
                  "taxonomia de erros e tempo até a correção (aberto → verificado)"),
    "handover_eventos": ("pessoas", "Histórico de cada handover: cada ocorrência e cada mudança de estado",
                         "um evento de um handover", IMUTAVEL, "sequência de estados para modelar recorrência e regressão"),
    "boas_praticas": ("pessoas", "O que o PDCA comprovou que funciona (e se depois foi invalidado)",
                      "uma prática nascida de um handover verificado", SITUACAO, "efeito das correções ao longo do tempo"),
    "memoria": ("pessoas", "Lembretes da empresa (correções do dono, estados de provas, conferências de cálculo)",
                "um lembrete com tipo e chave", IMUTAVEL, "contexto e decisões do dono"),
    "interacoes": ("pessoas", "Conversas entre funcionários (pedido de ajuda, mentoria, cobrança)",
                   "uma interação entre duas pessoas", IMUTAVEL, "rede de colaboração (quem ajuda quem)"),
    "mentorias": ("pessoas", "Mentoria nascida de um erro de treino: quem ajudou quem, com qual lição, e se ajudou",
                  "um pedido de ajuda a um mentor escolhido pelos acertos registrados", SITUACAO,
                  "qualidade de cada mentor (taxa de 'ajudou') e efeito da mentoria no acerto seguinte"),
    "solicitacoes": ("trabalho", "Central de solicitações: pedidos, planos, resultado e revisão independente",
                     "um pedido (tarefa, projeto ou conversa)", SITUACAO, "tempo de ciclo e taxa de aprovação na revisão"),
    "etapas": ("trabalho", "As etapas do plano de cada solicitação, com quem executou e o resultado",
               "uma etapa de uma solicitação", SITUACAO, "sucesso por ferramenta e por pessoa"),
    "aprovacoes": ("trabalho", "Pedidos de aprovação ao dono (risco, quem pediu, decisão e motivo)",
                   "um pedido de aprovação", SITUACAO, "padrões de risco e decisão"),
    "eventos": ("trabalho", "Linha do tempo de cada solicitação (cada mudança de estado)", "um evento de uma solicitação",
                IMUTAVEL, "sequência de estados (process mining)"),
    "artefatos": ("trabalho", "Arquivos entregues pelas solicitações (relatórios, resumos)", "um arquivo entregue", SITUACAO,
                  "o que foi entregue para cada pedido"),
    "arquivos": ("trabalho", "Arquivos anexados às conversas e solicitações", "um anexo", SITUACAO, "entradas do trabalho"),
    "conversas": ("trabalho", "Conversas com cada funcionário (e salas de reunião)", "uma conversa", SITUACAO,
                  "contexto das perguntas do dono"),
    "mensagens": ("trabalho", "Cada mensagem das conversas, com a natureza da resposta e a evidência",
                  "uma mensagem", IMUTAVEL, "perguntas × respostas × natureza (base para avaliar respostas)"),
    "licoes": ("conhecimento", "Caderno de lições: tudo o que a empresa aprendeu (erros, PDCA, treino, manuais, dono)",
               "uma versão de uma lição", SITUACAO, "base de conhecimento versionada"),
    "licoes_funcionario": ("conhecimento", "Cada lição de cada pessoa: atribuída → estudada → avaliada → aplicada (com prova)",
                           "uma lição para uma pessoa", SITUACAO, "curva de aprendizado por pessoa e por tema"),
    "licoes_uso": ("conhecimento", "Quando uma lição foi usada numa resposta de verdade", "um uso de uma lição", IMUTAVEL,
                   "aplicação real do conhecimento"),
    "registro_conhecimento": ("conhecimento", "Cadeia com hash (SHA-256) de tudo o que acontece com o conhecimento",
                              "um elo da cadeia (com o hash do anterior)", IMUTAVEL, "auditoria: prova de que nada foi adulterado"),
    "propostas_regra": ("conhecimento", "Regras propostas a partir de reprovações (só o dono aprova) e a prova",
                        "uma proposta de regra", SITUACAO, "o que reprova e o que resolve"),
    "regras_aprendidas": ("conhecimento", "Regras aprovadas em vigor (sinônimo, valor, correção, apelido) e desativações",
                          "uma regra aprovada", SITUACAO, "efeito das regras na taxa de aprovação"),
    "treino_casos": ("treino", "Casos de treino da Sala de Casos: gerador, semente, gabarito e revisão independente",
                     "um caso (reproduzível pela semente + versão do gerador)", SITUACAO,
                     "dificuldade de cada caso (taxa de acerto por caso)"),
    "treino_tentativas": ("treino", "Cada tentativa de cada funcionário: competência, nível, acertou, tipo de erro, tempo "
                                    "e a versão do código", "uma tentativa", IMUTAVEL,
                          "principal base para ML: desempenho × nível × competência × versão do código"),
    "treino_niveis": ("treino", "Nível atual de cada pessoa em cada competência", "pessoa × competência", ESTADO_ATUAL,
                      "a história fica em treino_niveis_eventos"),
    "treino_niveis_eventos": ("treino", "Cada subida e descida de nível, com as tentativas que provaram",
                              "uma mudança de nível", IMUTAVEL, "progressão (curva de evolução)"),
    "treino_certificacoes": ("treino", "Exames dos designers da Sala de Casos (um caso de cada nível, revisado)",
                             "um exame", IMUTAVEL, "qualidade de quem gera os casos"),
    "laboratorio_exercicios": ("treino", "Laboratório: planilhas sintéticas de 6 áreas em 4 níveis, etapa por etapa",
                               "uma etapa de um exercício", IMUTAVEL, "termômetro do código por nível de sujeira"),
    "laboratorio_medidas": ("treino", "Tempo do pipeline por volume (projeção de capacidade)", "uma medida", IMUTAVEL,
                            "regressão de tempo × linhas"),
    "reunioes": ("reunioes", "Reunião semanal da liderança: ata completa por andar", "uma reunião semanal", SITUACAO,
                 "o que se discutiu e o plano de ação"),
    "sala_eventos": ("reunioes", "Tudo o que acontece numa sala de reunião (abrir, mão, palavra, decisão, encerrar)",
                     "um evento de uma sala", IMUTAVEL, "dinâmica das reuniões"),
    "salas_encerradas": ("reunioes", "Ata (recap) de cada reunião de andar, com o hash do arquivo", "uma reunião encerrada",
                         IMUTAVEL, "decisões e pendências por reunião"),
    "decisoes": ("reunioes", "Decisões de reunião: dono, prazo, critério de pronto e situação apurada pelos registros",
                 "uma decisão", SITUACAO, "cumprimento de prazo por área e por pessoa"),
    "decisoes_eventos": ("reunioes", "Histórico de cada decisão (criada, cobrada, repactuada, cancelada, situação)",
                         "um evento de uma decisão", IMUTAVEL, "quantas repactuações até cumprir"),
    "rotinas_estado": ("operacao", "Última execução de cada rotina (para saber se está atrasada)", "uma rotina", ESTADO_ATUAL,
                       "a história fica em rotinas_execucoes"),
    "rotinas_execucoes": ("operacao", "Cada execução de cada rotina (início, fim, status e detalhe)", "uma execução",
                          IMUTAVEL, "confiabilidade das rotinas"),
    "sessoes": ("operacao", "Cada vez que o robô foi aberto (e quanto tempo ficou desligado antes)", "uma sessão", SITUACAO,
                "disponibilidade"),
    "uso_ferramentas": ("operacao", "Cada uso de cada ferramenta: quem, se deu certo, tempo e exceção", "um uso", IMUTAVEL,
                        "confiabilidade por ferramenta"),
    "erros_sistema": ("operacao", "Todo erro de programa (com traceback), agrupado por tipo, ligado a um handover da TI",
                      "um tipo de erro (repetição soma ocorrência)", SITUACAO, "estabilidade do código por versão"),
    "auditorias": ("operacao", "Auditorias por amostragem dos heads (conferido por outro caminho)", "uma auditoria",
                   IMUTAVEL, "confiança nos resultados publicados"),
    "backups_registro": ("operacao", "Cada backup (SQLite e PostgreSQL): arquivo, SHA-256, linhas e integridade",
                         "um backup", IMUTAVEL, "prova de que dá para restaurar"),
    "ideias_registro": ("conhecimento", "Cada ideia da Iara (ideias e expansão), com o dado que a originou e o dono",
                        "uma ideia registrada num dia", IMUTAVEL, "quais problemas mais geram ideias e quanto tempo levam para sumir"),
    "caixa_dono_eventos": ("conhecimento", "Cada decisão do dono na Caixa do dono (ideia, sugestão, regra, RH ou aprovação): "
                           "aprovada ou recusada, com a nota e o número que motivou", "uma decisão do dono", IMUTAVEL,
                           "que tipo de ideia o dono aprova; tempo até decidir"),
    "caixa_dono_sugestoes": ("conhecimento", "Sugestões que os funcionários fazem a partir de fatos registrados (erros repetidos "
                             "no treino, rotinas com erro)", "uma sugestão registrada", IMUTAVEL,
                             "de onde vêm as melhores ideias; problemas recorrentes"),
    "jornada_execucoes": ("operacao", "Cada volta completa da esteira com planilha sintética (equipe de Airflow): etapa a "
                          "etapa, com o tempo de cada uma", "uma volta da jornada", IMUTAVEL,
                          "confiabilidade da esteira por versão do código; etapa que mais falha; tempo por etapa"),
    "paineis_versoes": ("operacao", "Cada montagem dos painéis (Bárbara) e a conferência do Heitor: situação, indicadores e "
                        "divergências", "uma versão dos painéis", IMUTAVEL, "evolução de cada indicador no tempo; qualidade dos painéis"),
    "jobs": ("operacao", "Prova de trabalho: cada processamento real (planilha real ou sintética, rodada de treino, exercício do "
             "laboratório, rotina que fez algo), com início, fim, estado, responsável, evidência e hash da saída",
             "um processamento", "só de inclusão; um job fechado nunca muda (gatilho)",
             "carga real de trabalho por pessoa e por tipo; tempo de ciclo; taxa de falha da esteira"),
    "jobs_etapas": ("operacao", "Cada etapa de um job, com QUEM fez, início, fim, ok e evidência — é o que define quem está "
                    "trabalhando agora (etapa aberta nos últimos 15 minutos)", "uma etapa de um job",
                    "só de inclusão; uma etapa fechada nunca muda (gatilho)",
                    "tempo por etapa e por pessoa; gargalos da esteira; prova auditável de trabalho"),
    "aprendizados": ("conhecimento", "Memória de acertos e erros: cada decisão (esteira, fábrica, treino, laboratório, conversa) "
                     "com quem, competência, resultado, causa, correção, evidência e origem; a semente fica com origem "
                     "'semente' e nunca conta como acerto real", "uma decisão de um funcionário", IMUTAVEL,
                     "rótulo supervisionado (acertou/errou) por competência, nível e versão; reincidência de erro"),
    "aprendizados_uso": ("conhecimento", "Cada vez que a memória foi consultada antes de agir (onde e por quem)",
                         "uma consulta à memória", IMUTAVEL, "quanto a memória é usada e se o uso reduz o erro"),
    "aprendizados_replay": ("conhecimento", "Cada erro antigo refeito como teste de regressão: o mesmo motivo ainda barra?",
                            "um erro refeito", IMUTAVEL, "taxa de reincidência por competência e por versão do código"),
    "dialogo_conversas": ("conhecimento", "Cada conversa entre funcionários nascida de um fato (pedido de ajuda, cobrança, aviso), "
                          "com o compromisso verificável e se ele foi cumprido (com a prova)", "uma conversa", SITUACAO,
                          "quais conversas resolvem; tempo até cumprir; quem ajuda quem"),
    "demandas_ciclos": ("operacao", "Cada ciclo de distribuição de demandas: elegíveis, atribuídas, concluídas, bloqueadas "
                        "e, no detalhe, quem foi pulado e por quê (estagiário, demanda aberta, recebeu há pouco)",
                        "um ciclo da rotina demandas", IMUTAVEL,
                        "cobertura de trabalho por pessoa e andar; quem ficou sem demanda e por quê"),
    "telegram_mensagens": ("operacao", "Cada mensagem do grupo do Telegram: entrada (quem escreveu, se era o dono) e "
                           "saída (qual funcionário respondeu), com erro quando o envio falhou",
                           "uma mensagem do grupo", IMUTAVEL,
                           "o que o dono pergunta pelo celular; tempo e qualidade das respostas"),
    "telegram_vinculos": ("operacao", "Cada vínculo do grupo do Telegram feito pelo celular com /vincular e o código "
                          "certo: qual grupo e quem é o dono (o código nunca é gravado)", "um vínculo", IMUTAVEL,
                          "quando e por quem o grupo foi ligado; troca de grupo vira linha nova"),
    "demandas_registro": ("operacao", "Cada decisão da distribuição sobre uma pessoa: atribuída, treinamento, pulada, "
                          "bloqueada, reatribuída ou sem trabalho, com nível, ferramenta, motivo e quem decidiu",
                          "um evento de distribuição", IMUTAVEL,
                          "cobertura por andar e área; quem nunca recebe trabalho e por quê; justiça da distribuição"),
    "demandas_avaliacoes": ("conhecimento", "Avaliação independente (Bento) de uma demanda concluída: critérios conferidos "
                            "de novo, revisor independente, arquivos e a conta refeita do arquivo; veredito e achados",
                            "uma demanda avaliada", IMUTAVEL,
                            "qualidade real das entregas por nível e ferramenta; quanto a revisão de 1ª linha deixa passar"),
    "dialogo_ciclos": ("operacao", "Cada ciclo das conversas: quantos fatos avaliados, quantas conversas e se não houve assunto",
                       "um ciclo", IMUTAVEL, "quanto silêncio é falta de assunto e não de gente"),
    "cobertura_persistencia": ("operacao", "Cada levantamento de cobertura do banco: tabela por tabela (SQLite e PostgreSQL), "
                               "linhas, natureza (real, sintético, operação, controle) e a causa de cada tabela vazia",
                               "uma tabela num levantamento", IMUTAVEL,
                               "evolução da cobertura no tempo; quais partes da operação ainda não gravam nada"),
    "voz_falas": ("conhecimento", "Cada fala composta pela voz de um funcionário: quem, ato de fala, molde usado, hash do texto e "
                  "se veio de regra ou de IA (garante variação sem repetir parágrafo em 24 h e permite auditar)",
                  "uma fala", IMUTAVEL, "estilo e variação de cada voz; quanto a IA redige versus a regra"),
    "fabrica_lotes": ("conhecimento", "Cada planilha sintética da Fábrica: regra de negócio, semente, linhas, nível de sujeira, "
                      "quem gerou, conferiu e revisou, o gabarito e a conferência final contra a saída da esteira",
                      "um lote (uma planilha TREINO_)", SITUACAO,
                      "acerto da esteira por regra de negócio e por nível de sujeira; regressões entre versões do código"),
    "paineis_planilhas": ("conhecimento", "Cada planilha lida pela Bárbara: tema, papel e regra de cada cabeçalho, regras "
                          "quebradas, medidas DAX e números-âncora (leitura completa em JSON)", "uma planilha com um conteúdo",
                          IMUTAVEL, "aprender a reconhecer tema e regra de negócio pelo cabeçalho (rótulo supervisionado)"),
    "vigia_eventos": ("operacao", "Cada vez que o vigia achou o robô parado (e religou) ou sem responder", "um evento do vigia",
                      IMUTAVEL, "disponibilidade real: quedas por dia e tempo até voltar"),
    "logs_sistema": ("operacao", "Cada registro do log do sistema (robo.log e os girados), com nível e mensagem completa",
                     "um registro do log (com o traceback, se houver)", IMUTAVEL,
                     "série de eventos e erros por módulo e hora; prever falha antes de acontecer"),
    "canal_mensagens": ("trabalho", "Cada mensagem do canal da equipe (todos os campos)", "uma mensagem", IMUTAVEL,
                        "o que cada pessoa comunica e quando; conversas por área"),
    "arquivos_linhas": ("operacao", "Cada linha nova dos arquivos que só crescem (.jsonl, .csv): RH, conhecimento, histórico",
                        "uma linha de um arquivo, na ordem", IMUTAVEL, "reconstruir qualquer arquivo da pasta de logs"),
    "arquivos_versoes": ("operacao", "Cada versão de arquivo reescrito (.json, .md, .yaml, .txt): atas, estado da TI, "
                         "relatórios de erro, config.yaml sem senhas, equipe", "uma versão de um arquivo", IMUTAVEL,
                         "como a configuração e os documentos mudaram ao longo do tempo"),
    "registro_cursores": ("operacao", "Até onde cada arquivo já foi lido pelo registro total", "um arquivo (por geração)",
                          ESTADO_ATUAL, "controle interno: a história fica nas tabelas acima"),
    "acessos_celular": ("operacao", "Cada tentativa de entrar pelo celular (certa, errada ou bloqueada) e cada ação feita por ele, com IP e aparelho",
                        "uma entrada ou uma ação (evento 'acao': pausar, retomar, ver log, reprocessar) pelo celular", IMUTAVEL,
                        "padrão de uso e detecção de acesso estranho (horário, IP, erros seguidos)"),
    "rh_movimentos": ("pessoas", "Cada movimento de RH: promoção, plano de melhoria, afastamento, reintegração, propostas ao "
                      "dono, decisões e reversões — com a evidência (números) e quem propôs e quem validou",
                      "um movimento de RH de uma pessoa", IMUTAVEL,
                      "carreira por pessoa; rótulo de promoção/PDI a partir do desempenho dos 30 dias anteriores"),
    "rh_cargos": ("pessoas", "Nível efetivo de quem foi promovido pela política (vale sobre o nível do cadastro)",
                  "uma pessoa promovida e o nível atual dela", ESTADO_ATUAL, "nível atual (a história está em rh_movimentos)"),
    "rh_pdi": ("pessoas", "Planos de melhoria abertos e fechados, e o afastamento da ferramenta em produção",
               "um plano de melhoria de uma pessoa numa competência", SITUACAO,
               "tempo até recuperar; efeito do PDI no acerto"),
    "rh_ciclos": ("pessoas", "Cada rodada do ciclo de desempenho do RH, com o resumo do que decidiu",
                  "uma execução do ciclo de RH", IMUTAVEL, "frequência de promoções e PDIs ao longo do tempo"),
    "alcadas_decisoes": ("reunioes", "O que a liderança decidiu (ou deixou para o dono) com o dono fora: quem decidiu, "
                         "quem validou, a prova e até quando o dono pode reverter", "uma decisão de alçada ou uma reversão",
                         IMUTAVEL, "padrão de decisões delegadas e reversões do dono (qualidade da autonomia)"),
    "dono_presenca": ("operacao", "Última vez que o dono usou o painel (base para saber se ele está fora)",
                      "uma origem de presença e o último horário", ESTADO_ATUAL, "horários de presença do dono"),
}
COLUNAS_DE_DATA = ("data_hora", "criada_em", "criado_em", "inicio", "primeira", "aberto_em", "atualizada_em",
                   "ultima_verificacao", "atribuida_em", "aprovada_em")


def _todas_as_tabelas(cfg) -> None:
    """Garante que todo módulo criou o próprio esquema (para listar e documentar tudo)."""
    from robo import (alcadas, aprendizado, auditoria, backup, decisoes, erros, interacoes, laboratorio, licoes,
                      registro_total, rh_desempenho, sala, treino, vigia)
    from robo import aprendizados, caixa_dono, dialogo, fabrica, ideias, jobs, jornada, paineis, voz
    from robo.painel import celular
    from robo.ferramentas import USO_ESQUEMA
    from robo.rotinas import ESQUEMA as ROTINAS
    from robo.trabalho import Trabalho
    Trabalho(cfg)
    for m in (aprendizado, auditoria, erros, interacoes, laboratorio, licoes, sala, treino, decisoes, celular,
              rh_desempenho, alcadas, registro_total, vigia):
        m._tb(cfg)
    ideias._tb_registro(cfg)
    paineis._tb(cfg)
    jobs._tb(cfg)
    fabrica._tb(cfg)
    voz._tb(cfg)
    aprendizados._tb(cfg)
    dialogo._tb(cfg)
    from robo import demandas, telegram
    demandas._tb(cfg)
    telegram._tb(cfg)
    caixa_dono._tb(cfg)
    jornada._tb(cfg)
    from robo import cobertura_banco
    cobertura_banco._tb(cfg)
    from robo.trabalho import proteger
    with Trabalho(cfg).tx() as c:
        c.executescript(USO_ESQUEMA + ROTINAS + backup.ESQUEMA_REGISTRO)
        proteger(c)


def estado(cfg) -> dict:
    """O banco ao vivo: cada tabela com linhas, proteção, última gravação e a cópia no PostgreSQL."""
    from robo import backup, licoes
    _todas_as_tabelas(cfg)
    arq = Path(cfg.logs) / "trabalho.db"
    c = sqlite3.connect(arq)
    try:
        nomes = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        gatilhos = list(c.execute("SELECT tbl_name, upper(sql) FROM sqlite_master WHERE type='trigger'"))
        tabelas = []
        for t in nomes:
            cols = [r[1] for r in c.execute(f'PRAGMA table_info("{t}")')]
            data = next((x for x in COLUNAS_DE_DATA if x in cols), None)
            ultima = c.execute(f'SELECT MAX("{data}") FROM "{t}"').fetchone()[0] if data else None
            g, para_que, grao, regra, ml = TABELAS.get(t, ("sem_grupo", "", "", "", ""))
            tabelas.append({"tabela": t, "grupo": g, "para_que": para_que, "grao": grao, "regra": regra, "ml": ml,
                            "documentada": t in TABELAS, "colunas": cols,
                            "linhas": c.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0], "ultima_gravacao": ultima,
                            "protegida_contra_apagar": any(n == t and "BEFORE DELETE" in s for n, s in gatilhos),
                            "imutavel": any(n == t and "BEFORE UPDATE" in s for n, s in gatilhos)})
        integridade = c.execute("PRAGMA quick_check").fetchone()[0]
        modo = c.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        c.close()
    pg = _copia_postgres(cfg, nomes)
    for t in tabelas:
        t["no_postgres"] = pg["linhas"].get(t["tabela"]) if pg["ok"] else None
    integ = licoes.verificar_integridade(cfg)
    return {"arquivo": str(arq), "tamanho_mb": round(arq.stat().st_size / 1024 ** 2, 2), "integridade": integridade,
            "modo_diario": modo, "tabelas": tabelas, "total_linhas": sum(t["linhas"] for t in tabelas),
            "sem_documentacao": [t["tabela"] for t in tabelas if not t["documentada"]],
            "desprotegidas": [t["tabela"] for t in tabelas if not t["protegida_contra_apagar"] and TABELAS.get(t["tabela"], ("",) * 4)[3] != ESTADO_ATUAL],
            "cadeia_conhecimento": {"integra": integ["integra"], "registros": integ.get("registros")},
            "backup_sqlite": backup.ultimo_sqlite(cfg), "backup_postgres": backup.ultimo(cfg), "postgres": pg,
            "grupos": GRUPOS, "arquivos": _arquivos(cfg)}


def _copia_postgres(cfg, nomes: list[str]) -> dict:
    if not (cfg.banco or {}).get("habilitado"):
        return {"ok": False, "motivo": "PostgreSQL desligado nas Configurações (a memória segue segura no SQLite e nos backups)",
                "linhas": {}}
    try:
        from robo.banco import Banco
        b = Banco(cfg.banco, cfg.base)
        schema = b.schemas["controle"]
        with b.conectar(leitura=True) as conn:
            existentes = {r[0] for r in conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=%s",
                                                     (schema,))}
            linhas = {t: conn.execute(f'SELECT COUNT(*) FROM "{schema}"."memoria_{t}"').fetchone()[0]
                      for t in nomes if f"memoria_{t}" in existentes}
        from robo import rotinas
        ult = next((r for r in rotinas.estado(cfg) if r["nome"] == "memoria_pg"), {})
        return {"ok": True, "schema": schema, "linhas": linhas, "ultima_copia": ult.get("ultima_execucao"),
                "tabelas_copiadas": len(linhas)}
    except Exception as e:
        return {"ok": False, "motivo": f"{type(e).__name__}: {e}", "linhas": {}}


def _arquivos(cfg) -> list[dict]:
    """Registros que vivem em arquivo (também protegidos pelo backup e pela retenção 'guardar para sempre')."""
    logs = Path(cfg.logs)

    def conta(padrao):
        return sum(1 for _ in logs.glob(padrao))

    def linhas(p):
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                return sum(1 for _ in f)
        except OSError:
            return 0
    return [{"onde": "logs/historico_processamentos.csv", "o_que": "uma linha por planilha processada",
             "quantidade": max(0, linhas(logs / "historico_processamentos.csv") - 1)},
            {"onde": "logs/execucoes/*.json", "o_que": "ficha completa de cada processamento", "quantidade": conta("execucoes/*.json")},
            {"onde": "logs/reunioes/*.md", "o_que": "atas das reuniões (o hash está no banco)", "quantidade": conta("reunioes/*.md")},
            {"onde": "logs/canal/mensagens.jsonl", "o_que": "mensagens do canal da equipe", "quantidade": linhas(logs / "canal/mensagens.jsonl")},
            {"onde": "logs/conhecimento/*.jsonl", "o_que": "exportação diária do caderno + âncoras da cadeia", "quantidade": conta("conhecimento/*.jsonl")},
            {"onde": "logs/backups_sqlite/*.db.gz", "o_que": "backups diários do banco de registros", "quantidade": conta("backups_sqlite/*.db.gz")},
            {"onde": "logs/treino/arquivo/*.zip", "o_que": "casos de treino com erro, guardados para sempre", "quantidade": conta("treino/arquivo/*.zip")}]


# =============================================================================== documentação gerada
def gerar_markdown() -> str:
    import tempfile
    import yaml
    from robo.config import RAIZ_PROJETO, Config
    with tempfile.TemporaryDirectory() as d:
        dados = yaml.safe_load((RAIZ_PROJETO / "config.exemplo.yaml").read_text(encoding="utf-8"))
        dados["pastas"] = {k: str(Path(d) / k) for k in ("entrada", "logs", "agentes", "habilidades")}
        dados["banco"] = {**(dados.get("banco") or {}), "habilitado": False}
        cfg = Config(dados, Path(d))
        cfg.criar_pastas()
        e = estado(cfg)
    por = {t["tabela"]: t for t in e["tabelas"]}
    md = ["# Banco de dados da empresa", "",
          "> Gerado pelo código (`python -m robo banco-doc`, a partir de `robo/dicionario_dados.py`). Não edite à mão: "
          "um teste confere que este arquivo bate com o código.", "",
          "## Onde fica cada coisa", "",
          "| Onde | O que guarda | Para quê |", "|---|---|---|",
          f"| `logs/trabalho.db` (SQLite) | **Fonte de tudo**: a memória da empresa ({len(TABELAS)} tabelas abaixo) | Funciona sem internet e sem servidor; nada se apaga |",
          "| `logs/backups_sqlite/` | Cópia diária do `trabalho.db`, conferida (`integrity_check`) e com SHA-256 | Restaurar se o disco falhar; o 1º de cada mês fica para sempre |",
          "| PostgreSQL `robo_dados`, schema `robo` | Espelho de TODAS as tabelas (`memoria_<tabela>`) | Consultas em SQL, Power BI e Machine Learning |",
          "| PostgreSQL schemas `bruto` → `tratado` → `analitico` | As planilhas de negócio (ELT) | Análise e Power BI |",
          "| PostgreSQL schemas `laboratorio` e `treino` | Tabelas sintéticas temporárias do treino | Treino de SQL (refeitas pela semente) |", "",
          "## Regras que valem para todas as tabelas", "",
          "1. **Nada se apaga.** Toda tabela de registro tem um gatilho que recusa `DELETE` — inclusive as que forem criadas no futuro (`trabalho.proteger`).",
          f"2. **Três tipos de tabela.** *{IMUTAVEL}*; *{SITUACAO}*; *{ESTADO_ATUAL}*.",
          "3. **Backup diário** do SQLite (online, sem parar a operação) e do PostgreSQL; o primeiro de cada mês nunca é apagado; cada backup fica registrado em `backups_registro`.",
          "4. **Espelho completo** no PostgreSQL a cada hora: tabela imutável nunca é sobrescrita lá (adulterar o SQLite não muda a cópia).",
          "5. **Cadeia de integridade** (SHA-256) no conhecimento, com âncora em arquivo: adulteração é detectada.",
          "6. **Versão do código** em cada tentativa de treino: todo resultado é rastreável até o código que o produziu.", "",
          "## Tabelas", ""]
    for g, nome in GRUPOS.items():
        md += [f"### {nome}", "", "| Tabela | Para que serve | 1 linha = | Regra | Uso em Machine Learning |", "|---|---|---|---|---|"]
        for t, (grupo, para_que, grao, regra, ml) in TABELAS.items():
            if grupo == g:
                md.append(f"| `{t}` | {para_que} | {grao} | {regra} | {ml} |")
        md.append("")
    md += ["## Colunas de cada tabela", ""]
    for t in sorted(TABELAS):
        cols = por.get(t, {}).get("colunas") or []
        md.append(f"- **`{t}`**: " + ", ".join(f"`{c}`" for c in cols))
    md += ["", "## Como usar para Machine Learning (exemplo em SQL no PostgreSQL)", "",
           "```sql",
           "-- desempenho por competência e nível, por versão do código (cada linha = uma tentativa real, imutável)",
           "SELECT competencia, nivel, versao_codigo, COUNT(*) AS tentativas, AVG(acertou) AS taxa_acerto,",
           "       AVG(segundos) AS tempo_medio",
           "FROM robo.memoria_treino_tentativas",
           "GROUP BY competencia, nivel, versao_codigo",
           "ORDER BY competencia, nivel;", "```", "",
           "Tabelas-chave para modelos: `treino_tentativas` (rótulo `acertou`, atributos nível/competência/cargo/andar/tempo), "
           "`experiencias` (série por pessoa), `handover_eventos` e `decisoes_eventos` (sequências de estado), "
           "`uso_ferramentas` e `erros_sistema` (confiabilidade por versão).", "",
           "## Conectar o Power BI (só leitura)", "",
           "1. Power BI Desktop → **Página Inicial** → **Obter dados** → **Mais…** → **Banco de dados PostgreSQL** → **Conectar**.",
           "2. Servidor: `localhost:5432` · Banco de dados: `robo_dados` · Modo: **Importar** → **OK**.",
           "3. Na janela de credenciais, aba **Banco de dados**: usuário `robo_leitura` e a senha mostrada pelo `python -m robo instalar-banco`.",
           "4. Escolha as tabelas `robo.memoria_*` (memória da empresa) ou `analitico.*` (negócio) → **Transformar Dados**.",
           "O usuário `robo_leitura` não consegue alterar nada: o banco recusa (o instalador prova isso).", ""]
    return "\n".join(md)


def gravar_documentacao() -> Path:
    from robo.config import RAIZ_PROJETO
    destino = RAIZ_PROJETO / "documentacao" / "banco_de_dados.md"
    destino.write_text(gerar_markdown(), encoding="utf-8")
    return destino
