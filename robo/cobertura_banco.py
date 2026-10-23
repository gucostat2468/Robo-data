"""Cobertura de persistência: quais tabelas têm dados, de que natureza, e POR QUE as vazias estão vazias.

    python -m robo cobertura-banco

Existe porque "tabela vazia" pode querer dizer coisas muito diferentes, e cada uma pede uma ação diferente:
  - a funcionalidade existe, mas ainda não foi acionada (ex.: só nasce quando o dono conversa no painel);
  - a funcionalidade existe, mas nada a chama (defeito de ligação: precisa ser conectada);
  - a tabela é temporária por desenho (criada, conferida e removida);
  - o schema foi planejado e nenhum código grava nele;
  - ninguém sabe (sem causa registrada = investigar).

Nada aqui inventa dado para "encher" tabela. O levantamento só CONTA linhas e registra a causa conhecida de cada vazia.
Cada levantamento fica guardado em cobertura_persistencia (só de inclusão), e a cópia da memória o leva ao PostgreSQL.

Natureza dos dados (para nunca misturar real com sintético):
  real       produção: planilhas suas, schemas bruto, tratado, analitico e analise;
  sintetico  fábrica e laboratório: schemas laboratorio e treino, arquivos TREINO_*;
  operacao   registros do funcionamento da empresa (jobs, treino, rotinas, conversas) no SQLite e em robo.memoria_*;
  controle   lotes e ocorrências da esteira (robo.lotes, robo.ocorrencias).
"""

from __future__ import annotations

import json
from pathlib import Path

from robo.trabalho import Trabalho, _agora

ESQUEMA = """
CREATE TABLE IF NOT EXISTS cobertura_persistencia (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT NOT NULL, levantamento TEXT NOT NULL, onde TEXT NOT NULL,
  schema TEXT, tabela TEXT NOT NULL, linhas INTEGER NOT NULL, natureza TEXT, situacao TEXT NOT NULL, causa TEXT,
  gatilho TEXT, modulo TEXT);
CREATE INDEX IF NOT EXISTS ix_cobertura_levantamento ON cobertura_persistencia(levantamento);
CREATE TRIGGER IF NOT EXISTS cobertura_persistencia_imutavel BEFORE UPDATE ON cobertura_persistencia
BEGIN SELECT RAISE(ABORT, 'levantamento de cobertura é permanente: não se altera'); END;
"""

COM_DADOS = "com dados"
NAO_ACIONADA = "vazia: funcionalidade não acionada"
DESCONECTADA = "vazia: implementada, mas nada a chama"
TEMPORARIA = "vazia: tabela temporária por desenho"
PLANEJADA = "vazia: planejada, sem código que grave"
SEM_CAUSA = "vazia: sem causa registrada (investigar)"

# Causa de cada tabela que pode ficar vazia, levantada no código (quem grava e o que dispara). (situacao, causa, gatilho, módulo)
CAUSAS: dict[str, tuple[str, str, str, str]] = {
    # motor de solicitações (pedido → etapas → funcionário → ferramenta → aprovação → artefato)
    "solicitacoes": (NAO_ACIONADA, "nasce de pedido do dono, da rotina demandas (trabalho para cada funcionário) ou de "
                     "planilha processada; nenhum dos três aconteceu ainda neste banco",
                     "rotina demandas, planilha na esteira ou pedido no chat", "robo/demandas.py, robo/trabalho.py"),
    "etapas": (NAO_ACIONADA, "etapas pertencem a uma solicitação; sem solicitação, sem etapa",
               "rotina demandas ou pedido do dono", "robo/trabalho.py"),
    "eventos": (NAO_ACIONADA, "linha do tempo de uma solicitação; sem solicitação, sem evento",
                "rotina demandas ou pedido do dono", "robo/trabalho.py"),
    "artefatos": (NAO_ACIONADA, "arquivo entregue por uma etapa (resumo executivo, base publicada); as ferramentas das "
                  "demandas respondem em texto e dados, sem arquivo", "tarefa com resumo executivo ou publicação",
                  "robo/trabalho.py"),
    "telegram_mensagens": (NAO_ACIONADA, "o grupo do Telegram ainda não foi ligado (precisa do token do @BotFather, que só o "
                           "dono cria)", "python -m robo telegram --configurar", "robo/telegram.py"),
    "demandas_registro": (NAO_ACIONADA, "a rotina demandas ainda não rodou neste banco", "robô aberto ou turno da nuvem",
                          "robo/demandas.py"),
    "demandas_avaliacoes": (NAO_ACIONADA, "Bento só avalia demanda CONCLUÍDA que não executou nem revisou; ainda não "
                            "houve nenhuma neste banco", "demanda concluída + rotina demandas", "robo/demandas.py"),
    "demandas_ciclos": (NAO_ACIONADA, "a rotina demandas (a cada 30 min) ainda não rodou neste banco",
                        "robô aberto ou turno da nuvem", "robo/demandas.py"),
    "aprovacoes": (NAO_ACIONADA, "só etapa que ALTERA dados pede aprovação do dono; as demandas automáticas nunca "
                   "alteram dados (publicar planilha fica fora da distribuição)", "pedido do dono para publicar",
                   "robo/trabalho.py"),
    # conversa direta do dono com um funcionário
    "conversas": (NAO_ACIONADA, "conversa do dono com um funcionário pela ficha ou chat; a nuvem não tem painel",
                  "abrir a ficha de alguém no painel e escrever", "robo/trabalho.py"),
    "mensagens": (NAO_ACIONADA, "mensagens de uma conversa do dono", "escrever numa conversa do painel", "robo/trabalho.py"),
    "arquivos": (NAO_ACIONADA, "anexo enviado numa conversa", "anexar arquivo no chat do painel", "robo/trabalho.py"),
    # aprendizado de regras com o dono
    "propostas_regra": (NAO_ACIONADA, "nasce de planilha REAL reprovada com correção possível ou de correção do dono no chat",
                        "planilha real reprovada / correção do dono", "robo/aprendizado.py"),
    "regras_aprendidas": (NAO_ACIONADA, "só existe depois que o dono aprova uma proposta de regra",
                          "aprovar uma proposta na tela de regras", "robo/aprendizado.py"),
    "boas_praticas": (NAO_ACIONADA, "PDCA: um erro corrigido que não volta por um período vira boa prática",
                      "handover fechado e sem regressão no prazo", "robo/memoria.py"),
    # liderança e decisões
    "decisoes": (NAO_ACIONADA, "decisão com dono e prazo sai de reunião ou de pedido do dono",
                 "reunião com decisão registrada", "robo/decisoes.py"),
    "decisoes_eventos": (NAO_ACIONADA, "histórico de uma decisão; sem decisão, sem evento", "decisão criada",
                         "robo/decisoes.py"),
    "alcadas_decisoes": (NAO_ACIONADA, "a liderança só decide com o dono FORA há horas e item pendente na matriz",
                         "dono ausente + pendência dentro da alçada", "robo/alcadas.py"),
    "caixa_dono_sugestoes": (NAO_ACIONADA, "sugestão sai de fato repetido (erro de treino recorrente, rotina com erro)",
                             "erro repetido no treino ou rotina falhando", "robo/caixa_dono.py"),
    "caixa_dono_eventos": (NAO_ACIONADA, "decisão do dono sobre um item da caixa", "decidir um item na Caixa do dono",
                           "robo/caixa_dono.py"),
    # RH
    "rh_movimentos": (NAO_ACIONADA, "promoção, plano de melhoria e afastamento exigem dias de evidência acumulada",
                      "critério da política de RH atingido", "robo/rh_desempenho.py"),
    "rh_cargos": (NAO_ACIONADA, "cargo só muda com movimento de RH validado", "promoção validada", "robo/rh_desempenho.py"),
    "rh_pdi": (NAO_ACIONADA, "plano de desenvolvimento abre quando o acerto fica abaixo do mínimo por dias seguidos",
               "desempenho baixo sustentado", "robo/rh_desempenho.py"),
    # sala de reunião ao vivo
    "sala_eventos": (NAO_ACIONADA, "reunião ao vivo aberta pelo dono no painel", "abrir a Sala de reunião",
                     "robo/sala.py"),
    "salas_encerradas": (NAO_ACIONADA, "reunião ao vivo encerrada", "encerrar uma reunião na Sala", "robo/sala.py"),
    # tabelas de rotinas: vazias num computador onde o robô ainda não ficou aberto (python -m robo app) ou na nuvem
    "dialogo_ciclos": (NAO_ACIONADA, "a rotina dialogo (a cada 20 min) ainda não rodou neste banco",
                       "robô aberto ou turno da nuvem", "robo/dialogo.py"),
    "dialogo_conversas": (NAO_ACIONADA, "conversa entre funcionários só nasce de um fato que pede conversa (erro repetido, "
                          "rotina com erro, planilha barrada, alerta da TI)", "fato do dia + rotina dialogo",
                          "robo/dialogo.py"),
    "jornada_execucoes": (NAO_ACIONADA, "a rotina jornada (de hora em hora) ainda não rodou neste banco",
                          "robô aberto ou python -m robo rotina jornada", "robo/jornada.py"),
    "paineis_versoes": (NAO_ACIONADA, "o Estúdio de Painéis só publica versão com dado REAL publicado e reconciliado",
                        "planilha real publicada + rotina paineis", "robo/paineis.py"),
    "paineis_planilhas": (NAO_ACIONADA, "leitura de BI de cada planilha publicada; sem rotina paineis, sem leitura",
                          "rotina paineis com planilha publicada", "robo/paineis.py"),
    "voz_falas": (NAO_ACIONADA, "cada fala composta pela voz de um funcionário (canal, conversas)",
                  "funcionário falando no canal ou numa conversa", "robo/voz.py"),
    "fabrica_lotes": (NAO_ACIONADA, "a fábrica gera com a fila real vazia, no intervalo configurado",
                      "rotina fabrica", "robo/fabrica.py"),
    "acessos_celular": (NAO_ACIONADA, "só registra quando alguém tenta entrar pelo celular", "entrar pelo app do celular",
                        "robo/painel/celular.py"),
    "vigia_eventos": (NAO_ACIONADA, "a vigia só registra no Windows com a tarefa agendada ligada",
                      "python -m robo vigia ligar", "robo/vigia.py"),
    # controle da esteira real no PostgreSQL (robo.lotes e robo.ocorrencias)
    "lotes": (NAO_ACIONADA, "um lote por planilha REAL carregada no PostgreSQL (as da fábrica vão para treino.lotes)",
              "planilha sua processada com o banco ligado", "robo/banco.py"),
    "ocorrencias": (NAO_ACIONADA, "erros e avisos de cada planilha REAL carregada no PostgreSQL",
                    "planilha sua processada com o banco ligado", "robo/banco.py"),
    "cobertura_persistencia": (NAO_ACIONADA, "o primeiro levantamento conta as tabelas antes de se gravar",
                               "python -m robo cobertura-banco (ou o turno da nuvem)", "robo/cobertura_banco.py"),
    # memória da empresa
    "aprendizados_uso": (NAO_ACIONADA, "a esteira consulta a memória antes de ler cada planilha, mas o uso só é registrado "
                         "quando a consulta devolve um erro parecido já aprendido (a 1ª planilha de cada tipo não acha nada)",
                         "planilha entrando na esteira depois de um erro parecido registrado", "robo/aprendizados.py"),
    "instantaneos_sqlite": (NAO_ACIONADA, "cópia do SQLite inteiro gravada pelo turno da nuvem logo DEPOIS deste "
                            "levantamento (no 1º salvamento ainda não há nenhuma)", "salvamento do turno da nuvem",
                            "robo/nuvem.py"),
    "aprendizados_replay": (DESCONECTADA, "replay() existe, mas nenhuma rotina o chama; e ele só refaz erros REAIS "
                            "guardados em Bases-Erros", "chamar aprendizados.replay (ainda não ligado)", "robo/aprendizados.py"),
}

# Schemas do PostgreSQL e o que os enche
SCHEMAS = {
    "bruto": ("real", "cópia em texto de cada planilha REAL, como chegou", "planilha sua processada com o banco ligado"),
    "tratado": ("real", "tabelas tratadas das planilhas REAIS aprovadas", "planilha sua aprovada com o banco ligado"),
    "analitico": ("real", "modelos SQL (modelos_sql/) sobre o tratado real", "planilha real aprovada + modelos_sql"),
    "analise": ("real", "resultados da análise do 2º andar das planilhas reais", "análise de planilha real com o banco ligado"),
    "laboratorio": ("sintetico", "cópia bruta das planilhas da fábrica (TREINO_*); o laboratório usa tabelas "
                    "temporárias que remove após conferir", "lote da fábrica processado pela esteira"),
    "treino": ("sintetico", "tratado, controle (lotes, ocorrências) e análise das planilhas da fábrica",
               "lote da fábrica aprovado pela esteira"),
    "robo": ("operacao", "memória da empresa (robo.memoria_*), lotes e ocorrências reais, instantâneos",
             "rotina memoria_pg e esteira real"),
}


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    with tb.tx() as c:
        c.executescript(ESQUEMA)
        from robo.trabalho import proteger
        proteger(c)
    return tb


def _natureza_sqlite(tabela: str) -> str:
    return "controle" if tabela == "cobertura_persistencia" else "operacao"


def _classificar(tabela: str, linhas: int) -> tuple[str, str, str, str]:
    if linhas > 0:
        _, causa, gatilho, modulo = CAUSAS.get(tabela, ("", "", "", ""))
        return COM_DADOS, "", gatilho, modulo
    return CAUSAS.get(tabela, (SEM_CAUSA, "nenhuma causa conhecida: investigar quem grava nesta tabela", "", ""))


def levantar_sqlite(cfg) -> list[dict]:
    # cada módulo cria a própria tabela (vazia) se ainda não existir: assim um módulo que nunca rodou aparece como
    # tabela vazia com causa, em vez de simplesmente sumir do levantamento
    from robo.dicionario_dados import _todas_as_tabelas
    _todas_as_tabelas(cfg)
    itens = []
    with _tb(cfg).tx() as c:
        tabelas = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                           "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for t in tabelas:
            n = c.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            situacao, causa, gatilho, modulo = _classificar(t, n)
            itens.append({"onde": "sqlite", "schema": None, "tabela": t, "linhas": n, "natureza": _natureza_sqlite(t),
                          "situacao": situacao, "causa": causa, "gatilho": gatilho, "modulo": modulo})
    return itens


def levantar_postgres(cfg) -> list[dict]:
    """Conta as linhas de cada tabela dos schemas do robô. Sem banco ligado: lista vazia (não finge que conferiu)."""
    if not (cfg.banco or {}).get("habilitado"):
        return []
    from psycopg import sql

    from robo.banco import Banco
    itens = []
    with Banco(cfg.banco, cfg.base).conectar() as conn:
        existentes = {r[0] for r in conn.execute("SELECT nspname FROM pg_namespace")}
        tabelas = conn.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_type='BASE TABLE' "
                               "AND table_schema = ANY(%s) ORDER BY 1, 2", (list(SCHEMAS),)).fetchall()
        por_schema: dict[str, int] = {}
        for schema, t in tabelas:
            n = conn.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(schema, t))).fetchone()[0]
            por_schema[schema] = por_schema.get(schema, 0) + 1
            natureza = "controle" if schema == "robo" and t in ("lotes", "ocorrencias") else SCHEMAS[schema][0]
            espelho = t[len("memoria_"):] if schema == "robo" and t.startswith("memoria_") else None
            if n > 0:
                situacao, causa, gatilho, modulo = COM_DADOS, "", "", ""
            elif espelho:  # robo.memoria_X vazia = a tabela X do SQLite está vazia: mesma causa
                situacao, causa, gatilho, modulo = _classificar(espelho, 0)
                causa = f"espelho de {espelho} (vazia no SQLite também): {causa}"
            elif schema == "robo":
                situacao, causa, gatilho, modulo = _classificar(t, 0)
            else:  # tabela criada e vazia num schema de dados: a causa é a do schema (ex.: lote sem linhas)
                _, para_que, gatilho = SCHEMAS[schema]
                situacao, causa, modulo = NAO_ACIONADA, f"tabela criada, ainda sem linhas ({para_que})", ""
            itens.append({"onde": "postgres", "schema": schema, "tabela": t, "linhas": n, "natureza": natureza,
                          "situacao": situacao, "causa": causa, "gatilho": gatilho, "modulo": modulo})
        for schema, (natureza, para_que, gatilho) in SCHEMAS.items():
            if schema in existentes and not por_schema.get(schema):
                situacao = NAO_ACIONADA
                causa = f"schema sem nenhuma tabela ({para_que}); nasce quando acontecer: {gatilho}"
                itens.append({"onde": "postgres", "schema": schema, "tabela": "(schema vazio)", "linhas": 0,
                              "natureza": natureza, "situacao": situacao, "causa": causa, "gatilho": gatilho, "modulo": ""})
    return itens


def levantar(cfg, gravar: bool = True) -> dict:
    """Levanta SQLite e PostgreSQL. gravar=True guarda o levantamento em cobertura_persistencia (para comparar no tempo)."""
    itens = levantar_sqlite(cfg)
    erro_pg = None
    try:
        itens += levantar_postgres(cfg)
    except Exception as e:  # banco fora do ar não impede o levantamento do SQLite, e fica dito
        erro_pg = f"{type(e).__name__}: {e}"[:300]
    rotulo = _agora()
    if gravar:
        with _tb(cfg).tx() as c:
            c.executemany("INSERT INTO cobertura_persistencia (data_hora, levantamento, onde, schema, tabela, linhas, natureza, "
                          "situacao, causa, gatilho, modulo) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                          [(rotulo, rotulo, i["onde"], i["schema"], i["tabela"], i["linhas"], i["natureza"], i["situacao"],
                            i["causa"], i["gatilho"], i["modulo"]) for i in itens])
    return {"levantamento": rotulo, "itens": itens, "erro_postgres": erro_pg, "resumo": resumir(itens)}


def resumir(itens: list[dict]) -> dict:
    saida: dict = {}
    for i in itens:
        chave = i["onde"] if i["onde"] == "sqlite" else f"postgres.{i['schema']}"
        s = saida.setdefault(chave, {"tabelas": 0, "com_dados": 0, "vazias": {}})
        s["tabelas"] += 1
        if i["situacao"] == COM_DADOS:
            s["com_dados"] += 1
        else:
            s["vazias"][i["situacao"]] = s["vazias"].get(i["situacao"], 0) + 1
    return saida


def relatorio_md(r: dict) -> str:
    linhas = [f"# Cobertura de persistência ({r['levantamento']})", "",
              "Cada tabela com o número real de linhas. As vazias trazem a causa levantada no código. Nada aqui foi "
              "preenchido para parecer cheio.", ""]
    if r.get("erro_postgres"):
        linhas += [f"> PostgreSQL não conferido: {r['erro_postgres']}", ""]
    linhas += ["## Resumo", "", "| Onde | Tabelas | Com dados | Vazias por causa |", "|---|---|---|---|"]
    for onde, s in r["resumo"].items():
        vazias = "; ".join(f"{k.replace('vazia: ', '')}: {v}" for k, v in s["vazias"].items()) or "—"
        linhas.append(f"| {onde} | {s['tabelas']} | {s['com_dados']} | {vazias} |")
    vazias = [i for i in r["itens"] if i["situacao"] != COM_DADOS]
    if vazias:
        linhas += ["", "## Vazias e por quê", "", "| Onde | Tabela | Situação | Causa | O que enche | Quem grava |",
                   "|---|---|---|---|---|---|"]
        for i in vazias:
            onde = i["onde"] if i["onde"] == "sqlite" else f"postgres.{i['schema']}"
            linhas.append(f"| {onde} | {i['tabela']} | {i['situacao'].replace('vazia: ', '')} | {i['causa']} | "
                          f"{i['gatilho'] or '—'} | {i['modulo'] or '—'} |")
    linhas += ["", "## Com dados", "", "| Onde | Tabela | Linhas | Natureza |", "|---|---|---|---|"]
    for i in r["itens"]:
        if i["situacao"] == COM_DADOS:
            onde = i["onde"] if i["onde"] == "sqlite" else f"postgres.{i['schema']}"
            linhas.append(f"| {onde} | {i['tabela']} | {i['linhas']:,} | {i['natureza']} |".replace(",", "."))
    return "\n".join(linhas) + "\n"


def salvar_relatorio(cfg, r: dict) -> Path:
    destino = Path(cfg.logs) / "cobertura_banco.md"
    destino.write_text(relatorio_md(r), encoding="utf-8")
    (Path(cfg.logs) / "cobertura_banco.json").write_text(json.dumps(r, ensure_ascii=False, default=str, indent=1),
                                                         encoding="utf-8")
    return destino
