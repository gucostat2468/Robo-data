"""Orquestra o processamento de UM arquivo.

  1. Extrair      ler a planilha (leitura.py)
  2. Transformar  limpar, validar e modelar (limpeza.py, validacao.py, modelagem.py)
  3. Carregar     PostgreSQL em camadas (banco.py, se habilitado) + arquivo em Bases-Tratadas
  4. Arquivar     original vai para Bases-Originais (aprovado) ou Bases-Erros (reprovado)

Regra de ouro: "tudo ou nada". Se qualquer etapa encontrar erro, nada é publicado.
Se o problema for temporário (banco fora do ar, arquivo de saída aberto no Excel), o arquivo
fica em Bases-Limpeza e o robô tenta de novo sozinho (status ADIADO).
"""

from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from robo import historico
from robo.config import Config
from robo.escrita import gravar_tabelas
from robo.leitura import EXTENSOES_SUPORTADAS, ErroLeitura, ler_arquivo
from robo.limpeza import limpar_tabela, normalizar_nome_coluna
from robo.modelagem import dicionario_dados, modelar, tipo_amigavel
from robo.relatorio import Relatorio
from robo.validacao import validar_tabela

log = logging.getLogger("robo")

SUCESSO = "sucesso"
REPROVADO = "reprovado"
ADIADO = "adiado"
DIAGNOSTICO = "diagnostico"


@dataclass
class Resultado:
    arquivo: Path
    status: str
    relatorio: Relatorio
    tabelas: dict = field(default_factory=dict)
    saidas: list = field(default_factory=list)
    tabelas_banco: list = field(default_factory=list)
    linhas_entrada: int = 0
    linhas_saida: int = 0
    duracao: float = 0.0
    destino_original: Path | None = None
    id: str = ""
    motivo_adiamento: str = ""


@dataclass
class _Tratamento:
    brutas: dict = field(default_factory=dict)
    tabelas: dict = field(default_factory=dict)
    regra: dict = field(default_factory=dict)
    modelo: dict | None = None
    linhas_entrada: int = 0


def _carimbo() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _destino_livre(pasta: Path, nome: str) -> Path:
    destino, contador = pasta / nome, 2
    while destino.exists():
        destino = pasta / f"{Path(nome).stem}_{contador}{Path(nome).suffix}"
        contador += 1
    return destino


def _mover(origem: Path, pasta: Path, nome: str) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    destino = _destino_livre(pasta, nome)
    shutil.move(str(origem), str(destino))
    return destino


def nome_base_tabela(caminho: Path, regra: dict) -> str:
    destino = regra.get("destino") or {}
    return normalizar_nome_coluna(destino.get("tabela") or caminho.stem)


def _tratar(caminho: Path, cfg: Config, rel: Relatorio) -> _Tratamento:
    t = _Tratamento(regra=cfg.regra_para(caminho.name))
    if t.regra:
        rel.info(f"Regra aplicada: padrão '{t.regra.get('padrao')}'")

    if caminho.suffix.lower() not in EXTENSOES_SUPORTADAS:
        rel.erro(f"Formato '{caminho.suffix}' não suportado. Envie .xlsx, .xlsm, .xls, .csv ou .txt")
        return t
    try:
        t.brutas = ler_arquivo(caminho, abas=t.regra.get("abas", cfg.leitura["abas"]),
                               linhas_busca_cabecalho=int(cfg.leitura["linhas_busca_cabecalho"]))
    except ErroLeitura as e:
        rel.erro(str(e))
        return t
    if not t.brutas:
        rel.erro("O arquivo não tem nenhuma aba com dados")
        return t

    t.linhas_entrada = sum(len(df) for df in t.brutas.values())
    unica = len(t.brutas) == 1
    t.modelo = t.regra.get("modelo") if unica else None
    for aba, bruto in t.brutas.items():
        nome = normalizar_nome_coluna(cfg.saida["nome_aba"]) if unica else normalizar_nome_coluna(aba)
        rel.info(f"Aba '{aba}' lida: cabeçalho na linha {bruto.attrs.get('linha_cabecalho', '?')}, "
                 f"{len(bruto)} linhas, {len(bruto.columns)} colunas", tabela=nome)
        limpo = limpar_tabela(bruto, nome, cfg.limpeza, t.regra, rel)
        validar_tabela(limpo, nome, t.regra, rel)
        for nome_final, df in modelar(limpo, nome, t.modelo, rel).items():
            t.tabelas[nome_final] = df.reset_index(drop=True)

    if cfg.saida.get("colunas_auditoria", True):
        processado_em = pd.Timestamp(datetime.now().replace(microsecond=0))
        for nome, df in t.tabelas.items():
            if not nome.startswith("dim_"):
                df["_arquivo_origem"] = caminho.name
                df["_processado_em"] = processado_em
    return t


def _resumo_tabelas(tabelas: dict) -> list[dict]:
    return [{"nome": n, "linhas": len(df), "colunas": [{"nome": c, "tipo": tipo_amigavel(df[c])} for c in df.columns]}
            for n, df in tabelas.items()]


def _carregar_banco(cfg: Config, caminho: Path, t: _Tratamento, rel: Relatorio, lote_id: str, aprovado: bool) -> list[str]:
    """Uma transação por arquivo. Levanta ErroBancoIndisponivel (adiar) ou registra erro no relatório (reprovar)."""
    from robo.banco import Banco, ErroCargaDados

    banco = Banco(cfg.banco, cfg.base)
    banco.criar_banco_se_preciso()
    gravadas: list[str] = []
    base = nome_base_tabela(caminho, t.regra)
    with banco.conectar() as conn:
        try:
            with conn.transaction():
                banco.inicializar(conn)
                if cfg.banco.get("carregar_bruto", True) and t.brutas:
                    gravadas += banco.carregar_bruto(conn, base, t.brutas, caminho.name, lote_id)
                if aprovado:
                    gravadas += banco.carregar_tratado(conn, base, t.tabelas, caminho.name, lote_id,
                                                       t.regra.get("destino") or {}, t.modelo)
                    modelos = banco.executar_modelos(conn)
                    if modelos:
                        rel.info(f"Modelos SQL executados na camada analítica: {', '.join(modelos)}")
                banco.registrar_lote(conn, _dados_lote(caminho, lote_id, rel, t, gravadas, aprovado))
        except ErroCargaDados as e:
            rel.erro(f"Carga no PostgreSQL recusada: {e}")
            # registra o lote reprovado (nova transação, já que a anterior foi desfeita)
            with conn.transaction():
                banco.inicializar(conn)
                banco.registrar_lote(conn, _dados_lote(caminho, lote_id, rel, t, [], False))
            return []
    if gravadas:
        rel.info(f"PostgreSQL: {', '.join(gravadas)}")
    return gravadas


def _dados_lote(caminho, lote_id, rel: Relatorio, t: _Tratamento, gravadas, aprovado) -> dict:
    return {
        "lote_id": lote_id, "arquivo": caminho.name, "status": SUCESSO if aprovado else REPROVADO,
        "linhas_entrada": t.linhas_entrada,
        "linhas_saida": sum(len(df) for n, df in t.tabelas.items() if not n.startswith("dim_")) if aprovado else 0,
        "erros": len(rel.erros), "avisos": len(rel.avisos), "tabelas": gravadas,
        "mensagem": "; ".join(o.mensagem for o in rel.erros)[:2000] or None,
        "ocorrencias": [o.__dict__ for o in rel.ocorrencias if o.nivel != "INFO"],
    }


def processar_arquivo(caminho: str | Path, cfg: Config, gravar: bool = True) -> Resultado:
    """gravar=False = modo diagnóstico: só analisa; não grava, não carrega no banco e não move nada."""
    inicio = time.perf_counter()
    caminho = Path(caminho)
    rel = Relatorio(arquivo=caminho.name)
    log.info("Processando %s", caminho.name)

    try:
        t = _tratar(caminho, cfg, rel)
    except Exception as e:  # erro inesperado: nunca deixa o robô cair
        log.exception("Falha inesperada ao tratar %s", caminho.name)
        rel.erro(f"Falha inesperada: {type(e).__name__}: {e}")
        t = _Tratamento()

    r = Resultado(arquivo=caminho, status=DIAGNOSTICO, relatorio=rel, tabelas=t.tabelas, linhas_entrada=t.linhas_entrada,
                  linhas_saida=sum(len(df) for n, df in t.tabelas.items() if not n.startswith("dim_")))
    if not gravar:
        r.duracao = time.perf_counter() - inicio
        return r

    cfg.criar_pastas()
    carimbo = _carimbo()
    # o id é o nome que o original terá no arquivo morto (Bases-Originais ou Bases-Erros)
    pasta_arquivo_morto = cfg.erros if rel.tem_erros else cfg.originais / datetime.now().strftime("%Y-%m")
    r.id = _destino_livre(pasta_arquivo_morto, f"{carimbo}_{caminho.name}").stem

    # ---- carga no banco (antes dos arquivos: se o banco recusar, o arquivo não é publicado)
    if cfg.banco.get("habilitado"):
        from robo.banco import ErroBancoIndisponivel
        try:
            r.tabelas_banco = _carregar_banco(cfg, caminho, t, rel, r.id, aprovado=not rel.tem_erros)
        except ErroBancoIndisponivel as e:
            return _adiar(r, inicio, f"PostgreSQL indisponível: {e}")
        except Exception as e:
            log.exception("Falha inesperada no banco ao carregar %s", caminho.name)
            rel.erro(f"Falha inesperada no PostgreSQL: {type(e).__name__}: {e}")

    if rel.tem_erros:
        r.status = REPROVADO
        r.linhas_saida = 0
        r.destino_original = _mover(caminho, cfg.erros, f"{r.id}{caminho.suffix}")
        relatorio_txt = r.destino_original.with_name(f"{r.destino_original.stem}_ERROS.txt")
        relatorio_txt.write_text(rel.texto(), encoding="utf-8-sig")
        r.saidas = [relatorio_txt]
        log.warning("REPROVADO %s: %d erro(s). Veja %s", caminho.name, len(rel.erros), relatorio_txt)
    else:
        nome_base = caminho.stem + (cfg.saida.get("sufixo") or "")
        if cfg.saida.get("versionar"):
            nome_base += f"_{carimbo}"
        if str(cfg.saida.get("formato", "xlsx")).lower() != "nenhum":
            try:
                r.saidas, avisos = gravar_tabelas(t.tabelas, cfg.tratadas, nome_base, cfg.saida)
            except PermissionError:
                return _adiar(r, inicio, "o arquivo de saída está aberto (feche o Excel/Power BI)")
            for a in avisos:
                rel.aviso(a)
        r.status = SUCESSO
        r.destino_original = _mover(caminho, cfg.originais / datetime.now().strftime("%Y-%m"), f"{r.id}{caminho.suffix}")
        _gravar_relatorio_qualidade(cfg, nome_base, rel, t.tabelas)
        destinos = [p.name for p in r.saidas] + r.tabelas_banco
        log.info("OK %s -> %s (%d linhas, %d aviso(s))", caminho.name, ", ".join(destinos), r.linhas_saida, len(rel.avisos))

    r.duracao = time.perf_counter() - inicio
    _registrar(cfg, r)
    return r


def _adiar(r: Resultado, inicio: float, motivo: str) -> Resultado:
    r.status = ADIADO
    r.motivo_adiamento = motivo
    r.duracao = time.perf_counter() - inicio
    log.warning("ADIADO %s: %s. Tentarei de novo em instantes.", r.arquivo.name, motivo)
    return r


def _registrar(cfg: Config, r: Resultado):
    historico.registrar(cfg.logs, {
        "data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "arquivo": r.arquivo.name, "status": r.status,
        "linhas_entrada": r.linhas_entrada, "linhas_saida": r.linhas_saida, "erros": len(r.relatorio.erros),
        "avisos": len(r.relatorio.avisos), "duracao_seg": f"{r.duracao:.1f}".replace(".", ","),
        "saidas": " | ".join([p.name for p in r.saidas] + r.tabelas_banco), "id": r.id,
    })
    historico.salvar_execucao(cfg.logs, r.id, {
        "id": r.id, "arquivo": r.arquivo.name, "status": r.status,
        "data_hora": r.relatorio.inicio.strftime("%Y-%m-%d %H:%M:%S"), "duracao_seg": round(r.duracao, 2),
        "linhas_entrada": r.linhas_entrada, "linhas_saida": r.linhas_saida,
        "original": str(r.destino_original) if r.destino_original else None,
        "saidas": [str(p) for p in r.saidas], "tabelas_banco": r.tabelas_banco,
        "tabelas": _resumo_tabelas(r.tabelas) if r.status == SUCESSO else [],
        "ocorrencias": [o.__dict__ for o in r.relatorio.ocorrencias],
    })


def _gravar_relatorio_qualidade(cfg: Config, nome_base: str, rel: Relatorio, tabelas: dict):
    """Relatório de qualidade + dicionário de dados ficam em Bases-Relatorios (fora da pasta que o Power BI lê)."""
    try:
        cfg.relatorios.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(cfg.relatorios / f"{nome_base}_qualidade.xlsx", engine="openpyxl") as w:
            rel.para_dataframe().to_excel(w, sheet_name="log_qualidade", index=False)
            dicionario_dados(tabelas).to_excel(w, sheet_name="dicionario_dados", index=False)
    except PermissionError:
        log.warning("Relatório de qualidade de %s não foi atualizado (arquivo aberto).", nome_base)
