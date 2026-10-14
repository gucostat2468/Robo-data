"""Orquestra o processamento de UM arquivo: ler -> limpar -> validar -> modelar -> gravar -> arquivar."""

from __future__ import annotations

import csv
import logging
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from robo.config import Config
from robo.escrita import gravar_tabelas
from robo.leitura import EXTENSOES_SUPORTADAS, ErroLeitura, ler_arquivo
from robo.limpeza import limpar_tabela, normalizar_nome_coluna
from robo.modelagem import dicionario_dados, modelar
from robo.relatorio import Relatorio
from robo.validacao import validar_tabela

log = logging.getLogger("robo")

SUCESSO = "sucesso"
REPROVADO = "reprovado"
ADIADO = "adiado"          # não deu para gravar agora (ex.: arquivo de saída aberto no Excel); tenta de novo
DIAGNOSTICO = "diagnostico"


@dataclass
class Resultado:
    arquivo: Path
    status: str
    relatorio: Relatorio
    tabelas: dict = field(default_factory=dict)
    saidas: list = field(default_factory=list)
    linhas_entrada: int = 0
    linhas_saida: int = 0
    duracao: float = 0.0
    destino_original: Path | None = None


def _carimbo() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _mover(origem: Path, pasta: Path, nome: str) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / nome
    contador = 2
    while destino.exists():
        destino = pasta / f"{Path(nome).stem}_{contador}{Path(nome).suffix}"
        contador += 1
    shutil.move(str(origem), str(destino))
    return destino


def _registrar_historico(cfg: Config, r: Resultado):
    cfg.logs.mkdir(parents=True, exist_ok=True)
    arquivo = cfg.logs / "historico_processamentos.csv"
    novo = not arquivo.exists()
    with open(arquivo, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        if novo:
            w.writerow(["data_hora", "arquivo", "status", "linhas_entrada", "linhas_saida", "erros", "avisos",
                        "duracao_seg", "saidas"])
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), r.arquivo.name, r.status, r.linhas_entrada,
                    r.linhas_saida, len(r.relatorio.erros), len(r.relatorio.avisos), f"{r.duracao:.1f}".replace(".", ","),
                    " | ".join(p.name for p in r.saidas)])


def _tratar(caminho: Path, cfg: Config, rel: Relatorio) -> tuple[dict[str, pd.DataFrame], int]:
    """Leitura + limpeza + validação + modelagem. Não grava nada."""
    regra = cfg.regra_para(caminho.name)
    if regra:
        rel.info(f"Regra aplicada: padrão '{regra.get('padrao')}'")

    if caminho.suffix.lower() not in EXTENSOES_SUPORTADAS:
        rel.erro(f"Formato '{caminho.suffix}' não suportado. Envie .xlsx, .xlsm, .xls, .csv ou .txt")
        return {}, 0
    try:
        brutas = ler_arquivo(caminho, abas=regra.get("abas", cfg.leitura["abas"]),
                             linhas_busca_cabecalho=int(cfg.leitura["linhas_busca_cabecalho"]))
    except ErroLeitura as e:
        rel.erro(str(e))
        return {}, 0
    if not brutas:
        rel.erro("O arquivo não tem nenhuma aba com dados")
        return {}, 0

    linhas_entrada = sum(len(df) for df in brutas.values())
    unica = len(brutas) == 1
    finais: dict[str, pd.DataFrame] = {}
    for aba, bruto in brutas.items():
        nome = normalizar_nome_coluna(cfg.saida["nome_aba"]) if unica else normalizar_nome_coluna(aba)
        rel.info(f"Aba '{aba}' lida: cabeçalho na linha {bruto.attrs.get('linha_cabecalho', '?')}, "
                 f"{len(bruto)} linhas, {len(bruto.columns)} colunas", tabela=nome)
        limpo = limpar_tabela(bruto, nome, cfg.limpeza, regra, rel)
        validar_tabela(limpo, nome, regra, rel)
        modelo = regra.get("modelo") if unica else None
        for nome_final, df in modelar(limpo, nome, modelo, rel).items():
            finais[nome_final] = df.reset_index(drop=True)

    if cfg.saida.get("colunas_auditoria", True):
        processado_em = pd.Timestamp(datetime.now().replace(microsecond=0))
        for nome, df in finais.items():
            if nome.startswith("dim_"):
                continue
            df["_arquivo_origem"] = caminho.name
            df["_processado_em"] = processado_em
    return finais, linhas_entrada


def processar_arquivo(caminho: str | Path, cfg: Config, gravar: bool = True) -> Resultado:
    """gravar=False = modo diagnóstico: só analisa, não grava nem move nada."""
    inicio = time.perf_counter()
    caminho = Path(caminho)
    rel = Relatorio(arquivo=caminho.name)
    log.info("Processando %s", caminho.name)

    try:
        tabelas, linhas_entrada = _tratar(caminho, cfg, rel)
    except Exception as e:  # erro inesperado: nunca deixa o robô cair
        log.exception("Falha inesperada ao tratar %s", caminho.name)
        rel.erro(f"Falha inesperada: {type(e).__name__}: {e}")
        tabelas, linhas_entrada = {}, 0

    r = Resultado(arquivo=caminho, status=DIAGNOSTICO, relatorio=rel, tabelas=tabelas, linhas_entrada=linhas_entrada,
                  linhas_saida=sum(len(df) for n, df in tabelas.items() if not n.startswith("dim_")))
    if not gravar:
        r.duracao = time.perf_counter() - inicio
        return r

    cfg.criar_pastas()
    carimbo = _carimbo()

    if rel.tem_erros:
        r.status = REPROVADO
        r.linhas_saida = 0
        r.destino_original = _mover(caminho, cfg.erros, f"{carimbo}_{caminho.name}")
        relatorio_txt = r.destino_original.with_name(f"{r.destino_original.stem}_ERROS.txt")
        relatorio_txt.write_text(rel.texto(), encoding="utf-8-sig")
        r.saidas = [relatorio_txt]
        log.warning("REPROVADO %s: %d erro(s). Veja %s", caminho.name, len(rel.erros), relatorio_txt)
    else:
        nome_base = caminho.stem + (cfg.saida.get("sufixo") or "")
        if cfg.saida.get("versionar"):
            nome_base += f"_{carimbo}"
        try:
            r.saidas, avisos = gravar_tabelas(tabelas, cfg.tratadas, nome_base, cfg.saida)
        except PermissionError:
            r.status = ADIADO
            r.duracao = time.perf_counter() - inicio
            log.warning("ADIADO %s: o arquivo de saída está aberto (feche o Excel/Power BI). Tentarei de novo.",
                        caminho.name)
            return r
        for a in avisos:
            rel.aviso(a)
        r.status = SUCESSO
        r.destino_original = _mover(caminho, cfg.originais / datetime.now().strftime("%Y-%m"), f"{carimbo}_{caminho.name}")
        _gravar_relatorio_qualidade(cfg, nome_base, rel, tabelas)
        log.info("OK %s -> %s (%d linhas, %d aviso(s))", caminho.name, ", ".join(p.name for p in r.saidas),
                 r.linhas_saida, len(rel.avisos))

    r.duracao = time.perf_counter() - inicio
    _registrar_historico(cfg, r)
    return r


def _gravar_relatorio_qualidade(cfg: Config, nome_base: str, rel: Relatorio, tabelas: dict):
    """Relatório de qualidade + dicionário de dados ficam em Bases-Relatorios (fora da pasta que o Power BI lê)."""
    try:
        cfg.relatorios.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(cfg.relatorios / f"{nome_base}_qualidade.xlsx", engine="openpyxl") as w:
            rel.para_dataframe().to_excel(w, sheet_name="log_qualidade", index=False)
            dicionario_dados(tabelas).to_excel(w, sheet_name="dicionario_dados", index=False)
    except PermissionError:
        log.warning("Relatório de qualidade de %s não foi atualizado (arquivo aberto).", nome_base)
