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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="robo", description="Robô de Planilhas — ETL automático Bases-Limpeza -> Bases-Tratadas")
    p.add_argument("--config", help="caminho do config.yaml (padrão: config.yaml na pasta do projeto)")
    p.add_argument("-v", "--verboso", action="store_true")
    sub = p.add_subparsers(dest="comando", required=True)
    sub.add_parser("monitorar", help="vigia a pasta de entrada continuamente")
    sub.add_parser("varrer", help="processa uma vez todos os arquivos da entrada")
    sp = sub.add_parser("processar", help="processa um arquivo específico")
    sp.add_argument("arquivo")
    sd = sub.add_parser("diagnosticar", help="analisa um arquivo sem gravar nem mover")
    sd.add_argument("arquivo")
    sub.add_parser("status", help="mostra pastas, fila e histórico")
    sub.add_parser("manutencao", help="remove arquivos antigos conforme a retenção")
    args = p.parse_args(argv)

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
    if args.comando == "manutencao":
        print(executar_manutencao(cfg))
        return 0

    cfg.criar_pastas()
    try:
        with TravaInstancia(cfg.logs):
            monitor = Monitor(cfg)
            if args.comando == "varrer":
                monitor.espera = 0
                monitor.ciclo()          # 1ª passada registra os arquivos
                resultados = monitor.ciclo()  # 2ª passada processa os que estão estáveis
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
