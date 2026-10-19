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
    sro = sub.add_parser("rotina", help="roda UMA rotina da empresa agora e registra (é o que o Airflow chama). "
                                        "Saída: 0 fez/em dia, 1 erro, 99 já rodando em outro programa")
    sro.add_argument("nome", nargs="?", help="nome da rotina (sem nome: lista todas)")
    sdag = sub.add_parser("airflow-dag", help="gera airflow/dags/robo_empresa.py (DAG do Apache Airflow) a partir das rotinas")
    sdag.add_argument("--destino", help="arquivo da DAG (padrão: airflow/dags/robo_empresa.py na pasta do projeto)")
    sdag.add_argument("--sem-wsl", action="store_true", help="não converter caminhos C:\\ para /mnt/c (Airflow fora do WSL)")
    sdag.add_argument("--python", help="python que o Airflow deve chamar (padrão: o python que está rodando este comando)")
    sub.add_parser("diagnostico", help="confere este computador (Python, pastas, PostgreSQL, senhas, trava, rede, firewall, "
                                       "serviço, backups) — só lê, não altera nada")
    sim = sub.add_parser("importar-memoria", help="traz a memória da empresa de um backup trabalho_*.db.gz (ex.: de outro "
                                                  "computador). Com o robô FECHADO. Nada se perde")
    sim.add_argument("arquivo")
    sim.add_argument("--substituir", action="store_true", help="trocar mesmo se este computador já tiver história "
                                                                "(a memória atual é guardada antes)")
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
