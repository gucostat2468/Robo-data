"""Linha de comando do robô.

  python -m robo monitorar               fica vigiando Bases-Limpeza (modo normal do dia a dia)
  python -m robo varrer                  processa uma vez tudo o que está em Bases-Limpeza e sai
  python -m robo processar ARQUIVO       processa um arquivo específico (grava e move)
  python -m robo diagnosticar ARQUIVO    só analisa e mostra o relatório; não grava nem move nada
  python -m robo status                  mostra pastas encontradas, fila e últimos processamentos
  python -m robo manutencao              apaga backups/logs antigos conforme a retenção
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from robo import __version__
from robo.config import ErroConfig, carregar_config
from robo.manutencao import executar_manutencao
from robo.monitor import Monitor, TravaInstancia, eh_candidato
from robo.pipeline import processar_arquivo

log = logging.getLogger("robo")


def configurar_log(pasta_logs: Path, verboso: bool = False, em_arquivo: bool = True):
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%d/%m/%Y %H:%M:%S")
    log.setLevel(logging.DEBUG if verboso else logging.INFO)
    log.handlers.clear()
    if em_arquivo:
        pasta_logs.mkdir(parents=True, exist_ok=True)
        arquivo = TimedRotatingFileHandler(pasta_logs / "robo.log", when="midnight", backupCount=60, encoding="utf-8")
        arquivo.setFormatter(fmt)
        log.addHandler(arquivo)
    if sys.stdout is not None:  # pythonw (modo oculto) não tem console
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(fmt)
        log.addHandler(console)


def _imprimir_resultado(r):
    print()
    print(r.relatorio.texto())
    if r.tabelas:
        print("\nPRÉVIA DAS TABELAS")
        print("-" * 60)
        for nome, df in r.tabelas.items():
            print(f"\n[{nome}] {len(df)} linhas x {len(df.columns)} colunas")
            print(df.dtypes.astype(str).to_string())
            print(df.head(5).to_string())
    for s in r.saidas:
        print(f"\nArquivo gerado: {s}")


def _status(cfg):
    print(f"Robô de Planilhas v{__version__}\n")
    for nome, pasta in cfg.pastas().items():
        print(f"  {'OK ' if pasta.exists() else '-- '} {nome:<26} {pasta}")
    fila = [p.name for p in cfg.entrada.iterdir() if eh_candidato(p)] if cfg.entrada.exists() else []
    print(f"\nArquivos aguardando em Bases-Limpeza: {len(fila)}")
    for n in fila[:20]:
        print(f"  - {n}")
    erros = list(cfg.erros.glob("*_ERROS.txt")) if cfg.erros.exists() else []
    print(f"Arquivos reprovados aguardando correção (Bases-Erros): {len(erros)}")
    hist = cfg.logs / "historico_processamentos.csv"
    if hist.exists():
        with open(hist, encoding="utf-8-sig") as f:
            linhas = list(csv.reader(f, delimiter=";"))[1:]
        print("\nÚltimos processamentos:")
        for l in linhas[-10:]:
            print(f"  {l[0]}  {l[2]:<10} {l[1]}  ({l[4]} linhas, {l[5]} erros, {l[6]} avisos)")


def _comando_banco(cfg, acao: str) -> int:
    from robo.banco import Banco, ErroBancoIndisponivel, ErroCargaDados
    banco = Banco(cfg.banco, cfg.base)
    if acao == "testar":
        r = banco.testar()
        print(("OK  " if r["ok"] else "ERRO  ") + r["mensagem"])
        return 0 if r["ok"] else 1
    try:
        if acao == "modelos":
            with banco.conectar() as conn, conn.transaction():
                banco.inicializar(conn)
                feitos = banco.executar_modelos(conn)
            print("Modelos executados: " + (", ".join(feitos) or "nenhum"))
        else:
            r = banco.resumo()
            for t in r["tabelas"]:
                print(f"  {t['schema']}.{t['nome']:<35} {t['tipo']:<7} {t['linhas'] if t['linhas'] is not None else '':>10}")
        return 0
    except (ErroBancoIndisponivel, ErroCargaDados) as e:
        print(f"ERRO  {e}")
        return 1


def _comando_rotina(args) -> int:
    from robo import rotinas
    if not args.nome:
        for nome, (resp, desc, horas) in rotinas.ROTINAS.items():
            print(f"{nome:12s} a cada {horas * 60:g} min  ({resp})  {desc}")
        return 0
    if args.nome not in rotinas.ROTINAS:
        print(f"Rotina desconhecida: {args.nome}. Existem: {', '.join(rotinas.ROTINAS)}", file=sys.stderr)
        return 2
    try:
        cfg = carregar_config(Path(args.config) if args.config else None)
    except ErroConfig as e:
        print(f"Configuração com problema: {e}", file=sys.stderr)
        return 1
    configurar_log(cfg.logs, args.verboso)
    r = rotinas.executar(cfg, args.nome, rotinas.funcao(cfg, args.nome))
    if isinstance(r, dict) and r.get("em_andamento"):
        print(f"{args.nome}: já está rodando em outro programa (o robô ou outra tarefa) — nada feito para não rodar em dobro.")
        return 99
    est = next((e for e in rotinas.estado(cfg) if e["nome"] == args.nome), {})
    status = est.get("ultimo_status")
    print(f"{args.nome}: em dia (nada a fazer agora)" if status == "em_dia" else f"{args.nome}: {status} — {est.get('detalhe') or ''}")
    return 1 if est.get("ultimo_status") == "erro" else 0


def _telegram(args) -> int:
    from robo import telegram
    from robo.config import RAIZ_PROJETO
    from robo.painel import configuracao
    arq = Path(args.config) if args.config else RAIZ_PROJETO / "config.yaml"
    cfg = carregar_config(arq if arq.exists() else None)
    if not telegram.token(cfg):
        print("Falta o token. No Prompt de Comando: setx ROBO_TELEGRAM_TOKEN \"o-token-do-BotFather\" "
              "e abra um Prompt NOVO.", file=sys.stderr)
        return 1
    try:
        if args.testar:
            eu = telegram._api(cfg, "getMe")
            print(f"Token OK: o robô do Telegram é @{eu.get('username')} ({eu.get('first_name')}).")
            c = telegram._c(cfg)
            if c["chat_id"]:
                g = telegram._api(cfg, "getChat", {"chat_id": c["chat_id"]})
                print(f"Grupo OK: {g.get('title')} (id {c['chat_id']}). Ligado: {'sim' if c['habilitado'] else 'não'}.")
            else:
                print("Grupo ainda não configurado: escreva qualquer coisa no grupo e rode --descobrir.")
            return 0
        if args.descobrir:
            vistos = {}
            for u in telegram._api(cfg, "getUpdates", {"timeout": 0}) or []:
                m = u.get("message") or {}
                ch, de = m.get("chat") or {}, m.get("from") or {}
                vistos[(ch.get("id"), de.get("id"))] = (ch.get("title") or ch.get("type"), de.get("first_name"), m.get("text"))
            if not vistos:
                print("Nenhuma mensagem nova. Adicione o robô ao grupo, escreva 'oi' no grupo e rode de novo.")
                return 1
            for (chat, autor), (titulo, nome, texto) in vistos.items():
                print(f"Grupo: {titulo}  →  id do grupo: {chat}   |   {nome}  →  seu id: {autor}   (\"{texto}\")")
            print("\nAgora: python -m robo telegram --configurar <id do grupo> <seu id>")
            return 0
        if args.configurar:
            if not arq.exists():
                print("Ainda não existe config.yaml: abra o robô uma vez (python -m robo app) antes.", file=sys.stderr)
                return 1
            grupo, dono = args.configurar
            configuracao._gravar(arq, "telegram", "chat_id", str(grupo))
            configuracao._gravar(arq, "telegram", "dono_id", str(dono))
            configuracao._gravar(arq, "telegram", "habilitado", True)
            cfg = carregar_config(arq)
            ok = telegram.enviar(cfg, "Grupo ligado. A partir de agora a equipe responde aqui. Pergunte, por exemplo: "
                                      "\"como está o treino?\" ou \"quem está trabalhando agora?\"", "canal_nina")
            print("Configurado e testado: a Nina mandou a primeira mensagem no grupo." if ok else
                  "Configurado, mas a mensagem de teste falhou: rode --testar.")
            return 0 if ok else 1
        r = telegram.apresentar(cfg)
        print(f"{r['enviados']} cartão(ões) enviado(s)." + (f" Parou: {r['erro']}" if r.get("erro") else ""))
        return 0 if not r.get("erro") else 1
    except telegram.ErroTelegram as e:
        print(f"O Telegram respondeu: {e}", file=sys.stderr)
        return 1


def _cobertura_demandas(args) -> int:
    from robo import demandas, organizacao
    try:
        cfg = carregar_config(Path(args.config) if args.config else None)
    except ErroConfig as e:
        print(f"Configuração com problema: {e}", file=sys.stderr)
        return 1
    cob = demandas.cobertura(cfg, dias=args.dias)
    nomes = {p["id"]: p["nome"] for p in organizacao.lista(cfg)}
    print(f"Cobertura de demandas nos últimos {args.dias} dia(s):\n")
    for titulo, grupo in (("Por andar", cob["andares"]), ("Por área", cob["areas"])):
        print(titulo)
        for chave, g in sorted(grupo.items(), key=lambda x: str(x[0])):
            rotulo = f"{chave}º andar" if titulo == "Por andar" else chave
            print(f" {'✔' if g['completa'] else '✘'} {rotulo}: {g['com_demanda']} de {g['elegiveis']} elegíveis com demanda, "
                  f"{g['concluidas']} concluída(s), {g['com_problema']} com problema"
                  + (f", {len(g['justificados'])} com motivo registrado" if g["justificados"] else ""))
            if g["sem_demanda"]:
                print("     sem demanda e sem motivo: " + ", ".join(nomes.get(x, x) for x in g["sem_demanda"]))
        print()
    print("Cobertura completa." if cob["completa"] else "Cobertura INCOMPLETA: há elegível sem demanda e sem motivo registrado.")
    return 0 if cob["completa"] else 1


def _cobertura_banco(args) -> int:
    from robo import cobertura_banco
    try:
        cfg = carregar_config(Path(args.config) if args.config else None)
    except ErroConfig as e:
        print(f"Configuração com problema: {e}", file=sys.stderr)
        return 1
    r = cobertura_banco.levantar(cfg)
    destino = cobertura_banco.salvar_relatorio(cfg, r)
    for onde, s in r["resumo"].items():
        vazias = ", ".join(f"{v} {k.replace('vazia: ', '')}" for k, v in s["vazias"].items())
        print(f" {onde}: {s['com_dados']} de {s['tabelas']} com dados" + (f" | vazias: {vazias}" if vazias else ""))
    if r["erro_postgres"]:
        print(f" PostgreSQL não conferido: {r['erro_postgres']}")
    elif not (cfg.banco or {}).get("habilitado"):
        print(" PostgreSQL desligado no config.yaml: só o SQLite foi conferido.")
    sem_causa = [i for i in r["itens"] if i["situacao"] == cobertura_banco.SEM_CAUSA]
    for i in sem_causa:
        print(f" ! sem causa conhecida: {i['onde']} {i['schema'] or ''} {i['tabela']}")
    print(f"\nRelatório completo (tabela por tabela, com a causa de cada vazia): {destino}")
    return 0


def _diagnostico_celular(args) -> int:
    from robo import diagnostico_celular as dc
    try:
        cfg = carregar_config(Path(args.config) if args.config else None)
    except ErroConfig as e:
        print(f"Configuração com problema: {e}", file=sys.stderr)
        return 1
    print("Diagnóstico do celular (só lê, não altera nada)\n")
    itens = dc.rodar(cfg)
    marca = {"ok": "✔", "atencao": "!", "falha": "✘", "nao_se_aplica": "–"}
    for i in itens:
        print(f" {marca[i['situacao']]} {i['titulo']}: {i['detalhe']}")
        if i["corrigir"] and i["situacao"] != "ok":
            print(f"     → {i['corrigir']}")
    falhas = sum(i["situacao"] == "falha" for i in itens)
    url = dc.endereco(cfg)
    if url:
        print(f"\nEndereço para o celular: {url}")
        qr = dc.qr_terminal(url)
        if qr:
            print("Aponte a câmera do celular para o quadrado abaixo:\n")
            print(qr)
        else:
            print("(Para ver o QR code aqui: pip install segno)")
        if args.salvar_qr:
            svg = dc.qr_svg(url)
            if svg:
                destino = cfg.logs / "celular_qr.svg"
                destino.write_text(svg, encoding="utf-8")
                print(f"QR code salvo em {destino}")
    print(f"\nResultado: {falhas} falha(s)." + (" Pode abrir no celular." if not falhas else
                                                 " Corrija o primeiro ✘ da lista: os seguintes costumam depender dele."))
    return 1 if falhas else 0


def _celular(args) -> int:
    from robo.config import RAIZ_PROJETO
    from robo.painel import celular, configuracao
    arq = Path(args.config) if args.config else RAIZ_PROJETO / "config.yaml"
    if not arq.exists():
        print("Ainda não existe config.yaml: abra o robô uma vez (python -m robo app) antes.", file=sys.stderr)
        return 1
    if args.ligar or args.desligar:
        configuracao._gravar(arq, "celular", "habilitado", bool(args.ligar))
    cfg = carregar_config(arq)
    conf = celular.configuracao(cfg)
    if not conf["habilitado"]:
        print("Acompanhamento pelo celular: DESLIGADO. Para ligar: python -m robo celular --ligar")
        return 0
    if not (cfg.painel or {}).get("senha_hash"):
        print("Ligado no config.yaml, mas NÃO vai abrir: o painel está sem senha. Defina com: python -m robo senha",
              file=sys.stderr)
        return 1
    ip = celular.ip_da_rede() or "<ip-deste-computador>"
    print("Acompanhamento pelo celular: LIGADO (somente leitura). Feche e abra o robô para valer.")
    print(f"  No celular, na MESMA rede Wi-Fi: http://{ip}:{conf['porta']}/  (Safari → Compartilhar → 'Adicionar à Tela de Início')")
    print("  Senha: a mesma do painel.")
    print("  Na 1ª vez o Windows pergunta sobre o firewall: marque SÓ 'Redes privadas'.")
    print("  Fora de casa: use a VPN Tailscale (nos dois aparelhos). Nunca abra esta porta no roteador.")
    return 0


def principal(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="robo", description="Robô de Planilhas — ETL automático Bases-Limpeza -> Bases-Tratadas")
    p.add_argument("--config", help="caminho do config.yaml (padrão: config.yaml na pasta do projeto)")
    p.add_argument("-v", "--verboso", action="store_true")
    sub = p.add_subparsers(dest="comando", required=True)
    sa = sub.add_parser("app", help="abre o painel (interface gráfica) e liga o robô")
    sa.add_argument("--sem-janela", action="store_true", help="só liga em segundo plano (inicialização do Windows)")
    sa.add_argument("--porta", type=int)
    sub.add_parser("monitorar", help="vigia a pasta de entrada continuamente (sem interface)")
    sub.add_parser("varrer", help="processa uma vez todos os arquivos da entrada")
    sp = sub.add_parser("processar", help="processa um arquivo específico")
    sp.add_argument("arquivo")
    sd = sub.add_parser("diagnosticar", help="analisa um arquivo sem gravar nem mover")
    sd.add_argument("arquivo")
    sest = sub.add_parser("estudio", help="PRODUTO: interface simples no navegador — envie a planilha (limpeza, "
                                         "padronização, análise e relatório) e consulte os dados tratados em SQL. "
                                         "Só neste computador")
    sest.add_argument("--porta", type=int, default=8765)
    sest.add_argument("--sem-navegador", action="store_true", help="não abre o navegador sozinho")
    sest.add_argument("--atalho", action="store_true", help="cria o atalho do Estúdio na Área de Trabalho (Windows)")
    sen = sub.add_parser("entregar", help="PRODUTO: transforma QUALQUER planilha num pacote "
                                          "para o gestor: base tratada, qualidade, modelo Power BI + DAX, ML opcional e "
                                          "relatorio.html com recomendações. Roda só no seu computador; a base não sai dele")
    sen.add_argument("arquivo")
    sen.add_argument("--destino", help="pasta onde criar a entrega (padrão: a pasta do arquivo)")
    sen.add_argument("--segmentos", help="colunas de segmento separadas por vírgula (padrão: o robô escolhe)")
    sen.add_argument("--alvo", help="Machine Learning: coluna a prever (com linha de base, teste e checagem de vazamento)")
    scen = sub.add_parser("cenario", help="gera uma planilha SINTÉTICA de clientes (até 100 mil linhas) com erros "
                                          "plantados e o gabarito (números, erros e ML) ao lado")
    scen.add_argument("--linhas", type=int, default=10_000)
    scen.add_argument("--semente", type=int, default=1)
    scen.add_argument("--nivel", type=float, default=1.0, help="multiplica a quantidade de erros (1 = padrão)")
    scen.add_argument("--destino", default=".", help="pasta onde gravar (padrão: a pasta atual)")
    spl = sub.add_parser("placar", help="prova da esteira: gera cenários com gabarito, roda a entrega completa em cada "
                                        "um e mostra o que bateu e o que falhou")
    spl.add_argument("--cenarios", type=int, default=3)
    spl.add_argument("--linhas", type=int, default=5000)
    spl.add_argument("--semente", type=int, default=1)
    spl.add_argument("--nivel", type=float, default=1.0)
    sub.add_parser("status", help="mostra pastas, fila e histórico")
    sub.add_parser("manutencao", help="remove arquivos antigos conforme a retenção")
    sdm = sub.add_parser("demo", help="abre a empresa de demonstração (pasta separada, planilhas de 6 áreas)")
    sdm.add_argument("--recomecar", action="store_true", help="apaga a demonstração anterior e começa do zero")
    sdm.add_argument("--porta", type=int, default=8799)
    sdm.add_argument("--sem-janela", action="store_true")
    sdm.add_argument("--senha", help="senha do painel da demonstração (se não informar, ela é pedida)")
    sub.add_parser("senha", help="define ou troca a senha do painel (pede a senha duas vezes, sem mostrar)")
    sub.add_parser("atalhos", help="cria o atalho 'Robô de Planilhas' na Área de Trabalho e no Menu Iniciar (Windows)")
    si = sub.add_parser("inicializacao", help="liga/desliga o robô junto com o Windows")
    si.add_argument("acao", choices=["ligar", "desligar", "status"])
    sb = sub.add_parser("banco", help="PostgreSQL: testar conexão, executar modelos SQL, ver tabelas")
    sb.add_argument("acao", choices=["testar", "modelos", "resumo"])
    sib = sub.add_parser("instalar-banco", help="cria o banco REAL no seu PostgreSQL: usuários robo_app e robo_leitura, "
                                              "schemas, permissões e senhas em variáveis de ambiente")
    sib.add_argument("--host", default="localhost")
    sib.add_argument("--porta", type=int, default=5432)
    sib.add_argument("--banco", default="robo_dados")
    sib.add_argument("--superusuario", default="postgres", help="o usuário administrador criado na instalação do PostgreSQL")
    sib.add_argument("--sem-setx", action="store_true", help="não gravar as senhas nas variáveis do Windows")
    sub.add_parser("banco-doc", help="regera documentacao/banco_de_dados.md a partir do dicionário de dados do código")
    sub.add_parser("semear-aprendizado", help="importa a semente de ~200 lições (origem 'semente', nunca conta como acerto real)")
    sro = sub.add_parser("rotina", help="roda UMA rotina da empresa agora e registra (é o que o Airflow chama). "
                                        "Saída: 0 fez/em dia, 1 erro, 99 já rodando em outro programa")
    sro.add_argument("nome", nargs="?", help="nome da rotina (sem nome: lista todas)")
    sdag = sub.add_parser("airflow-dag", help="gera airflow/dags/robo_empresa.py (DAG do Apache Airflow) a partir das rotinas")
    sdag.add_argument("--destino", help="arquivo da DAG (padrão: airflow/dags/robo_empresa.py na pasta do projeto)")
    sdag.add_argument("--sem-wsl", action="store_true", help="não converter caminhos C:\\ para /mnt/c (Airflow fora do WSL)")
    sdag.add_argument("--python", help="python que o Airflow deve chamar (padrão: o python que está rodando este comando)")
    stu = sub.add_parser("turno", help="um turno de trabalho na NUVEM grátis (GitHub Actions + PostgreSQL gratuito): restaura a "
                                       "memória, trabalha, salva tudo a cada 10 min. Lê ROBO_PG_URL e ROBO_PG_SENHA_LEITURA")
    stu.add_argument("--minutos", type=float, default=20)
    stu.add_argument("--pasta", default="nuvem_trabalho", help="pasta de trabalho temporária")
    sse = sub.add_parser("servico", help="modo servidor (contêiner/Cloud Run): turnos um atrás do outro e uma página de "
                                         "saúde SOMENTE LEITURA na porta da variável PORT (padrão 8080). Sem painel")
    sse.add_argument("--minutos", type=float, default=20, help="duração de cada turno")
    sse.add_argument("--pasta", default="/tmp/empresa", help="pasta de trabalho temporária")
    spc = sub.add_parser("preparar-pc", help="prepara o computador de uma vez (Prompt como Administrador): banco real, "
                                             "memória, celular, banco no celular, início com o Windows, vigia e diagnóstico")
    spc.add_argument("--memoria", help="arquivo trabalho_AAAAMMDD_HHMMSS.db.gz com a memória da empresa a importar")
    svi = sub.add_parser("vigia", help="religa o robô sozinho se ele cair: ligar/desligar a tarefa agendada (Windows), "
                                       "status, ou checar agora")
    svi.add_argument("acao", choices=["ligar", "desligar", "status", "checar"])
    sub.add_parser("diagnostico", help="confere este computador (Python, pastas, PostgreSQL, senhas, trava, rede, firewall, "
                                       "serviço, backups) — só lê, não altera nada")
    sim = sub.add_parser("importar-memoria", help="traz a memória da empresa de um backup trabalho_*.db.gz (ex.: de outro "
                                                  "computador). Com o robô FECHADO. Nada se perde")
    sim.add_argument("arquivo")
    sim.add_argument("--substituir", action="store_true", help="trocar mesmo se este computador já tiver história "
                                                                "(a memória atual é guardada antes)")
    stg = sub.add_parser("telegram", help="grupo do Telegram: testar, descobrir o id do grupo, configurar e apresentar "
                                          "a equipe (token na variável ROBO_TELEGRAM_TOKEN)")
    gtg = stg.add_mutually_exclusive_group(required=True)
    gtg.add_argument("--testar", action="store_true")
    gtg.add_argument("--descobrir", action="store_true")
    gtg.add_argument("--configurar", nargs=2, metavar=("ID_DO_GRUPO", "SEU_ID"))
    gtg.add_argument("--apresentar", action="store_true")
    sub.add_parser("modelos", help="inteligência própria: datasets, modelos, avaliações e a referência em sombra — só lê")
    sub.add_parser("boletim", help="mostra o boletim que o app do celular recebe (o turno da nuvem publica a cada 5 min) — "
                                   "só lê")
    scd = sub.add_parser("cobertura-demandas", help="quem recebeu demanda, por andar e por área, e quem ficou sem e por "
                                                    "quê — só lê")
    scd.add_argument("--dias", type=int, default=7)
    sub.add_parser("cobertura-banco", help="conta as linhas de cada tabela (SQLite e PostgreSQL) e diz por que cada "
                                           "vazia está vazia — só conta, não inventa dado")
    sdc = sub.add_parser("diagnostico-celular", help="confere passo a passo por que o celular abre ou não abre o robô e "
                                                    "mostra o QR code do endereço — só lê, não altera nada")
    sdc.add_argument("--salvar-qr", action="store_true", help="salva o QR code em logs/celular_qr.svg")
    scel = sub.add_parser("celular", help="acompanhamento pelo celular (somente leitura, rede de casa): ligar, desligar ou ver")
    grupo = scel.add_mutually_exclusive_group()
    grupo.add_argument("--ligar", action="store_true")
    grupo.add_argument("--desligar", action="store_true")
    slb = sub.add_parser("liberar-banco-celular", help="deixa o app de banco do celular ler o PostgreSQL (só robo_leitura, "
                                                       "só rede de casa) — rode no Prompt como Administrador")
    slb.add_argument("--host", default="localhost")
    slb.add_argument("--porta", type=int, default=5432)
    slb.add_argument("--banco", default="robo_dados")
    slb.add_argument("--superusuario", default="postgres")
    slb.add_argument("--rede", help="rede da casa (padrão: descoberta sozinha, ex.: 192.168.0.0/24)")
    args = p.parse_args(argv)

    if args.comando == "rotina":
        return _comando_rotina(args)
    if args.comando == "turno":
        import json
        import os
        from robo import nuvem
        url = nuvem.url_do_ambiente()  # ROBO_PG_URL, ou DB_USER/DB_PASS/DB_NAME (+ INSTANCE_CONNECTION_NAME)
        if not url:
            print("::warning::Falta o segredo ROBO_PG_URL (endereço do PostgreSQL gratuito). Veja documentacao/nuvem_gratis.md"
                  if os.environ.get("GITHUB_ACTIONS") else "Defina ROBO_PG_URL (veja documentacao/nuvem_gratis.md).")
            return 0 if os.environ.get("GITHUB_ACTIONS") else 1
        nuvem.mascarar_para_o_github(url)
        cfg = nuvem.config_da_nuvem(Path(args.pasta), url, os.environ.get("ROBO_PG_SENHA_LEITURA", ""))
        configurar_log(cfg.logs, args.verboso)
        r = nuvem.turno(cfg, args.minutos)
        r["empresa"] = nuvem.resumo_do_turno(cfg)
        print(json.dumps(r, ensure_ascii=False, indent=1, default=str))
        if r["alerta_espaco"]:
            print(f"::warning::Banco gratuito com {r['banco_mb']} MB de {r['limite_mb']} MB: decidir arquivamento.")
        return 0
    if args.comando == "modelos":
        import json
        from robo import modelos_ml
        cfg = carregar_config(Path(args.config) if args.config else None)
        print(json.dumps(modelos_ml.resumo(cfg), ensure_ascii=False, indent=1, default=str))
        return 0
    if args.comando == "boletim":
        import json
        from robo import boletim
        cfg = carregar_config(Path(args.config) if args.config else None)
        print(json.dumps(boletim.montar(cfg), ensure_ascii=False, indent=1, default=str))
        return 0
    if args.comando == "servico":
        from robo import servico
        return servico.principal(args.pasta, args.minutos, args.verboso)
    if args.comando == "preparar-pc":
        from robo import preparar_pc
        return preparar_pc.preparar(principal, args.config, args.memoria)
    if args.comando == "vigia":
        from robo import vigia
        if args.acao in ("ligar", "desligar", "status"):
            try:
                if args.acao == "ligar":
                    print(f"Vigia ligado: a cada 5 minutos o Windows roda {vigia.ligar_tarefa()}")
                    print("Se o robô cair, ele volta sozinho em até 5 minutos. Cada queda fica registrada (vigia_eventos).")
                elif args.acao == "desligar":
                    vigia.desligar_tarefa()
                    print("Vigia desligado.")
                else:
                    estado = vigia.tarefa_ligada()
                    print("Vigia: " + ("ligado" if estado else "desligado" if estado is False else "só existe no Windows"))
                return 0
            except Exception as e:
                print(f"Não foi possível: {e}", file=sys.stderr)
                return 1
        try:
            cfg = carregar_config(Path(args.config) if args.config else None)
        except ErroConfig as e:
            print(f"Configuração com problema: {e}", file=sys.stderr)
            return 1
        r = vigia.checar(cfg, args.config)
        print(f"Vigia: {r['situacao']}")
        return 0 if r["situacao"] != "sem_resposta" else 1
    if args.comando == "diagnostico":
        from robo import diagnostico_pc
        try:
            cfg = carregar_config(Path(args.config) if args.config else None)
        except ErroConfig as e:
            print(f"Configuração com problema: {e}", file=sys.stderr)
            return 1
        itens = diagnostico_pc.rodar(cfg)
        marca = {"ok": "✔", "atencao": "!", "falha": "✘", "nao_se_aplica": "–"}
        for i in itens:
            print(f" {marca[i['situacao']]} {i['titulo']}: {i['detalhe']}")
            if i["corrigir"] and i["situacao"] != "ok":
                print(f"     → {i['corrigir']}")
        falhas = sum(i["situacao"] == "falha" for i in itens)
        atencoes = sum(i["situacao"] == "atencao" for i in itens)
        print(f"\nResultado: {falhas} falha(s), {atencoes} ponto(s) de atenção." + (" Tudo certo." if not falhas and not atencoes else ""))
        return 1 if falhas else 0
    if args.comando == "telegram":
        return _telegram(args)
    if args.comando == "cobertura-demandas":
        return _cobertura_demandas(args)
    if args.comando == "cobertura-banco":
        return _cobertura_banco(args)
    if args.comando == "diagnostico-celular":
        return _diagnostico_celular(args)
    if args.comando == "importar-memoria":
        from robo import backup
        try:
            cfg = carregar_config(Path(args.config) if args.config else None)
            r = backup.restaurar_sqlite(cfg, Path(args.arquivo), substituir=args.substituir)
        except Exception as e:
            print(f"Não importei: {e}", file=sys.stderr)
            return 1
        for passo in r["passos"]:
            print(f"  ✔ {passo}")
        print("Abra o robô (python -m robo app). Com o PostgreSQL instalado, em até 1 hora a memória inteira é copiada para o "
              "schema robo do banco robo_dados (ou rode agora: python -m robo rotina memoria_pg).")
        return 0
    if args.comando == "airflow-dag":
        from robo import orquestracao
        try:
            cfg = carregar_config(Path(args.config) if args.config else None)
            r = orquestracao.gerar_dag(cfg, Path(args.destino) if args.destino else None, python=args.python,
                                       wsl=False if args.sem_wsl else None, caminho_config=args.config)
        except (ErroConfig, ValueError) as e:
            print(f"Não gerei a DAG: {e}", file=sys.stderr)
            return 1
        print(f"DAG gerada: {r['arquivo']}  (assinatura {r['assinatura']})")
        for dag, d in r["dags"].items():
            print(f"  {dag:18s} {d['cron']:14s} " + " → ".join(d["tarefas"]))
        print(f"Cada tarefa roda: {r['comando']} <rotina>")
        print("Copie o arquivo para a pasta dags do Airflow (no WSL: ~/airflow/dags/). Guia: documentacao/airflow.md")
        return 0

    if args.comando == "celular":
        return _celular(args)

    if args.comando == "liberar-banco-celular":
        import getpass
        import os
        from robo import acesso_rede_banco
        senha = os.environ.get("ROBO_PG_SUPER_SENHA")
        if senha is None:
            print(f"Senha do usuário '{args.superusuario}' do PostgreSQL (a que você criou ao instalar o PostgreSQL):")
            senha = getpass.getpass("Senha: ")
        try:
            r = acesso_rede_banco.liberar(args.superusuario, senha, args.host, args.porta, args.banco, rede=args.rede)
        except Exception as e:
            print(f"Não consegui liberar: {e}", file=sys.stderr)
            return 1
        for passo in r["passos"]:
            print(f"  ✔ {passo}")
        print("\nPREENCHA NO APP DO CELULAR (celular na MESMA rede Wi-Fi da casa):")
        for campo, valor in r["app"].items():
            print(f"  {campo:9s} {valor}")
        print("\nO usuário robo_leitura só lê: pelo celular ninguém altera nem apaga nada. Nunca abra a porta no roteador.")
        return 0

    if args.comando == "semear-aprendizado":
        from robo import aprendizados
        cfg = carregar_config(Path(args.config) if args.config else None)
        n = aprendizados.semear(cfg)
        print(f"Semente importada: {n} lição(ões) nova(s) com origem 'semente' (não contam como acerto real).")
        return 0

    if args.comando == "banco-doc":
        from robo import dicionario_dados
        print(f"Gerado: {dicionario_dados.gravar_documentacao()}")
        return 0

    if args.comando == "instalar-banco":
        import getpass
        import os
        from robo import instalacao_banco
        from robo.config import RAIZ_PROJETO
        senha = os.environ.get("ROBO_PG_SUPER_SENHA")
        if senha is None:
            print(f"Senha do usuário '{args.superusuario}' do PostgreSQL (a que você criou ao instalar o PostgreSQL):")
            senha = getpass.getpass("Senha: ")
        try:
            r = instalacao_banco.instalar(Path(args.config) if args.config else RAIZ_PROJETO / "config.yaml", args.superusuario,
                                          senha, args.host, args.porta, args.banco, gravar_variaveis=not args.sem_setx)
        except Exception as e:
            print(f"Não consegui instalar o banco: {type(e).__name__}: {e}", file=sys.stderr)
            return 1
        print(f"\nPostgreSQL {r['versao_postgres']} — banco instalado:")
        for passo in r["passos"]:
            print(f"  ✔ {passo}")
        c = r["conexao"]
        print("\nVARIÁVEIS DE CONEXÃO (guarde num gerenciador de senhas; elas NÃO ficam em nenhum arquivo):")
        print(f"  servidor: {c['host']}   porta: {c['porta']}   banco: {c['banco']}")
        for u, s in r["senhas"].items():
            print(f"  usuário {u:13s} senha: {s}")
        print(f"  (também em %{c['variavel_senha_app']}% e %{c['variavel_senha_leitura']}% — feche e abra o robô para ele ler)")
        print("\nPower BI: Obter dados → Banco de dados PostgreSQL → Servidor localhost:5432, Banco robo_dados,"
              " usuário robo_leitura (só leitura: o Power BI nunca altera nada).")
        return 0

    if args.comando in ("atalhos", "inicializacao"):
        from robo.painel import sistema
        try:
            if args.comando == "atalhos":
                print("Atalhos criados: " + " e ".join(sistema.criar_atalhos()))
            elif args.acao == "status":
                print("Inicia com o Windows: " + ("sim" if sistema.inicializacao_ligada() else "não"))
            else:
                ligado = sistema.definir_inicializacao(args.acao == "ligar")
                print("O robô vai ligar sozinho quando você entrar no Windows." if ligado
                      else "Inicialização automática desligada.")
            return 0
        except Exception as e:
            print(f"Não foi possível: {e}")
            return 1

    if args.comando == "demo":
        import getpass

        from robo import demonstracao
        from robo.painel import configuracao
        from robo.painel.acesso import gerar_hash
        from robo.painel.servidor import iniciar_app
        caminho = demonstracao.preparar(recomecar=args.recomecar, porta=args.porta)
        if not demonstracao.tem_senha(caminho):
            senha = args.senha
            if not senha:
                print("Primeira vez na demonstração: crie a senha do painel (mínimo 8 caracteres).")
                senha = getpass.getpass("Senha: ")
                if senha != getpass.getpass("Repita a senha: "):
                    print("As duas senhas não são iguais.", file=sys.stderr)
                    return 1
            try:
                configuracao.definir_senha(caminho, gerar_hash(senha))
            except ValueError as e:
                print(e, file=sys.stderr)
                return 1
        configurar_log(carregar_config(caminho).logs, args.verboso)
        print(f"Demonstração em {caminho.parent} — painel em http://127.0.0.1:{args.porta}/")
        return iniciar_app(caminho, abrir_janela=not args.sem_janela, porta=args.porta)

    if args.comando == "app":
        from robo.config import RAIZ_PROJETO
        from robo.painel.servidor import iniciar_app
        configurar_log(RAIZ_PROJETO / "logs", args.verboso)
        try:
            pasta_logs = carregar_config(args.config).logs
            if pasta_logs != RAIZ_PROJETO / "logs":
                configurar_log(pasta_logs, args.verboso)
        except ErroConfig:
            pass  # o painel mostra a tela de configuração inicial
        return iniciar_app(Path(args.config) if args.config else None, abrir_janela=not args.sem_janela, porta=args.porta)

    try:
        cfg = carregar_config(args.config)
    except ErroConfig as e:
        print(f"ERRO DE CONFIGURAÇÃO: {e}", file=sys.stderr)
        return 2

    # status/diagnóstico não escrevem no robo.log (evita disputar o arquivo com o robô em execução)
    configurar_log(cfg.logs, args.verboso, em_arquivo=args.comando not in ("status", "diagnosticar"))

    if args.comando == "status":
        _status(cfg)
        return 0
    if args.comando == "diagnosticar":
        r = processar_arquivo(args.arquivo, cfg, gravar=False)
        _imprimir_resultado(r)
        return 1 if r.relatorio.tem_erros else 0
    if args.comando == "estudio" and args.atalho:
        from robo.painel import sistema
        try:
            print("Atalho 'Robô de Planilhas - Estúdio' criado: " + " e ".join(sistema.criar_atalho_estudio()))
            return 0
        except Exception as e:
            print(f"Não foi possível: {e}")
            return 1
    if args.comando == "estudio":
        from robo import estudio
        estudio.abrir(cfg, args.porta, navegador=not args.sem_navegador)
        return 0
    if args.comando == "cenario":
        from robo import cenarios
        cen = cenarios.gerar(args.linhas, args.semente, args.nivel)
        arq = cenarios.gravar(cen, Path(args.destino))
        g = cen["gabarito"]
        print(f"Planilha: {arq}\nGabarito: {arq.with_suffix('').with_suffix('.gabarito.json')}")
        print(f"  {g['numeros']['linhas_planilha']} linhas na planilha · {len(cen['manifesto'])} erros plantados · "
              f"{100 * g['numeros']['taxa_cancelamento']:.1f}% cancelaram")
        return 0
    if args.comando == "placar":
        from robo import cenarios
        cfg.criar_pastas()
        r = cenarios.placar(cfg, args.cenarios, args.linhas, semente_inicial=args.semente, nivel=args.nivel)
        for c in r["cenarios"]:
            print(f"\nCenário semente {c['semente']} ({c['linhas']} linhas, {c['segundos']}s): {c['ok']} de {c['total']}")
            for i in c["itens"]:
                print(f"  {'OK   ' if i['ok'] else 'FALHA'} [{i['grupo']}] {i['verificacao']}: {i['detalhe']}")
        print(f"\nPlacar: {r['acertos']} de {r['verificacoes']} ({r['pct']}%) · detalhes em {r['pasta']}")
        return 0 if r["acertos"] == r["verificacoes"] else 1
    if args.comando == "entregar":
        from robo import entrega
        r = entrega.entregar(cfg, args.arquivo, args.destino,
                             [x.strip() for x in args.segmentos.split(",")] if args.segmentos else None, args.alvo)
        print(f"Entrega {'pronta' if r['ok'] else 'com problemas'}: {r['pasta']}")
        for a in r["arquivos"]:
            print(f"  • {a}")
        print("Recomendações:")
        for x in r["recomendacoes"]:
            print(f"  - {x.replace('**', '')}")
        for e in r["erros"]:
            print(f"  ! {e}")
        return 0 if r["ok"] else 1
    if args.comando == "processar":
        cfg.criar_pastas()
        r = processar_arquivo(args.arquivo, cfg)
        _imprimir_resultado(r)
        return 0 if r.status == "sucesso" else 1
    if args.comando == "banco":
        return _comando_banco(cfg, args.acao)
    if args.comando == "manutencao":
        print(executar_manutencao(cfg))
        return 0
    if args.comando == "senha":
        import getpass

        from robo.painel import configuracao
        from robo.painel.acesso import gerar_hash
        nova = getpass.getpass("Nova senha do painel (mínimo 8 caracteres): ")
        if nova != getpass.getpass("Repita a senha: "):
            print("As duas senhas não são iguais. Nada foi alterado.", file=sys.stderr)
            return 1
        try:
            h = gerar_hash(nova)
        except ValueError as e:
            print(e, file=sys.stderr)
            return 1
        configuracao.definir_senha(configuracao.garantir_arquivo(args.config), h)
        print("Senha definida. Reabra o painel: ele vai pedir a senha.")
        return 0

    cfg.criar_pastas()
    try:
        with TravaInstancia(cfg.logs):
            monitor = Monitor(cfg)
            if args.comando == "varrer":
                resultados = monitor.ciclo(forcar=True)
                ok = sum(r.status == "sucesso" for r in resultados)
                print(f"\n{len(resultados)} arquivo(s) processado(s): {ok} com sucesso, {len(resultados) - ok} com problema.")
                return 0 if ok == len(resultados) else 1
            try:
                monitor.rodar()
            except KeyboardInterrupt:
                log.info("Robô encerrado pelo usuário.")
    except RuntimeError as e:
        log.error(str(e))
        return 3
    return 0
