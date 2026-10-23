"""Orquestra o processamento de UM arquivo.

  1. Extrair      ler a planilha (leitura.py)
  2. Transformar  limpar, validar e modelar (limpeza.py, validacao.py, modelagem.py)
  3. Carregar     PostgreSQL em camadas (banco.py, se habilitado) + arquivo em Bases-Tratadas.
                  A camada "bruto" guarda tudo o que chegou (inclusive reprovados, para auditoria);
                  "tratado" e "analitico" só recebem arquivos 100% aprovados.
  4. Arquivar     original vai para Bases-Originais (aprovado) ou Bases-Erros (reprovado)

Regra de ouro: "tudo ou nada". Se qualquer etapa encontrar erro, nada é publicado.
Se o problema for temporário (banco fora do ar, arquivo de saída aberto no Excel), o arquivo
fica em Bases-Limpeza e o robô tenta de novo sozinho (status ADIADO).
"""

from __future__ import annotations

import json
import logging
import os
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


def _queda_de_conexao(e: Exception) -> bool:
    try:
        import psycopg
    except ImportError:
        return False
    return isinstance(e, (psycopg.OperationalError, psycopg.InterfaceError))


def _saida_aberta(cfg, caminho: Path) -> Path | None:
    """Algum arquivo publicado desta base está travado por outro programa (Excel/Power BI no Windows)?"""
    nome_base = caminho.stem + (cfg.saida.get("sufixo") or "")
    pasta = Path(cfg.tratadas)
    if not pasta.exists():
        return None
    for arq in list(pasta.glob(f"{nome_base}.*")) + list(pasta.glob(f"{nome_base}__*.csv")):
        try:
            with open(arq, "r+b"):
                pass
        except PermissionError:
            return arq
        except OSError:
            continue
    return None


def _regra_com_aprendizado(cfg, nome: str) -> dict:
    """Regra do config.yaml + o que foi aprendido e aprovado pelo dono (sinônimos e valores novos — robo/aprendizado.py)."""
    regra = cfg.regra_para(nome)
    if not regra.get("padrao"):
        return regra
    from robo import aprendizado
    return aprendizado.aplicar_overlay(regra, aprendizado.regras_ativas(cfg, str(regra["padrao"])))


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
    analise: dict | None = None
    checklist: dict | None = None
    checklist_analise: dict | None = None
    excel: dict | None = None
    quadro: list = field(default_factory=list)   # conferências de gerentes, plenos, juniores e estagiários
    tratamento: object = None   # só no modo diagnóstico: o tratamento completo (para as ferramentas do atendimento)


@dataclass
class _Tratamento:
    brutas: dict = field(default_factory=dict)
    tabelas: dict = field(default_factory=dict)
    regra: dict = field(default_factory=dict)
    modelo: dict | None = None
    linhas_entrada: int = 0
    analisaveis: dict = field(default_factory=dict)   # tabelas limpas ANTES de virar fato/dimensões (2º andar)


def _guardar_anteriores(pasta: Path, nome_base: str, seguranca: Path) -> list[tuple[Path, Path]]:
    """Copia os arquivos já publicados com este nome para uma pasta de segurança (em logs/, fora do alcance
    do Power BI) antes de sobrescrever."""
    if not pasta.exists():
        return []
    pares = []
    for p in pasta.iterdir():
        if p.is_file() and (p.name.startswith(f"{nome_base}.") or p.name.startswith(f"{nome_base}__")):
            seguranca.mkdir(parents=True, exist_ok=True)
            copia = seguranca / p.name
            shutil.copy2(p, copia)
            pares.append((p, copia))
    return pares


def _restaurar_anteriores(pares: list[tuple[Path, Path]]) -> None:
    for original, copia in pares:
        if copia.exists():
            shutil.copy2(copia, original)
            copia.unlink(missing_ok=True)


def _descartar_anteriores(pares: list[tuple[Path, Path]]) -> None:
    """A versão nova passou na releitura: as cópias de segurança não são mais necessárias."""
    for _, copia in pares:
        copia.unlink(missing_ok=True)


def _conferencias_equipe(fase: str, ctx, rel, ao_etapa, bloquear: bool) -> list[dict]:
    """Roda as conferências do quadro de pessoal da fase e registra cada achado no relatório de qualidade.

    bloquear=True (1º andar): achado de pleno/júnior vira ERRO (o arquivo não é publicado).
    Estagiário sempre fica em observação (AVISO). Gerente nunca bloqueia (AVISO).
    """
    from robo import quadro
    for p in quadro.QUADRO + quadro.CONFERENCIAS_EXTRAS:
        if p["fase"] == fase and p["funcao"] is not None:
            _sinal(ao_etapa, p["id"], ctx.arquivo)
    resultado = quadro.conferir(fase, ctx)
    for x in resultado:
        for achado in x["achados"]:
            texto = f"{x['cargo'].split(' — ')[0]} {x['nome']}: {achado}"
            if x["nivel"] == "estagiario":
                rel.aviso(f"Em observação (não bloqueia) — {texto}")
            elif bloquear and x["bloqueia"]:
                rel.erro(f"Barrado na conferência da equipe — {texto}")
            else:
                rel.aviso(texto)
    return resultado


def _carimbo() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _destino_livre(pasta: Path, nome: str) -> Path:
    destino, contador = pasta / nome, 2
    while destino.exists():
        destino = pasta / f"{Path(nome).stem}_{contador}{Path(nome).suffix}"
        contador += 1
    return destino


def _mover(origem: Path, pasta: Path, nome: str, tentativas: int = 5) -> Path:
    """Move o original para o arquivo morto. O OneDrive/antivírus às vezes trava o arquivo por segundos: tenta de novo.
    A data do arquivo passa a ser a de hoje (a retenção conta a partir do arquivamento, não da criação na origem)."""
    pasta.mkdir(parents=True, exist_ok=True)
    destino = _destino_livre(pasta, nome)
    for i in range(tentativas):
        try:
            shutil.move(str(origem), str(destino))
            break
        except PermissionError:
            if i == tentativas - 1:
                raise
            time.sleep(0.5 * (i + 1))
    try:
        os.utime(destino)
    except OSError:
        pass
    return destino


MARCAS = "ja_publicados.json"


def _arquivar_ou_marcar(cfg, origem: Path, pasta: Path, nome: str, rel) -> Path:
    """Se não der para mover (travado), guarda uma CÓPIA e marca o original como já processado: o monitor não o
    processa de novo e o retira da entrada assim que for liberado."""
    try:
        return _mover(origem, pasta, nome)
    except OSError as e:
        pasta.mkdir(parents=True, exist_ok=True)
        copia = _destino_livre(pasta, nome)
        shutil.copy2(str(origem), str(copia))
        os.utime(copia)
        st = origem.stat()
        marcas = _ler_marcas(cfg)
        marcas[origem.name] = [st.st_size, st.st_mtime_ns, str(copia)]
        _gravar_marcas(cfg, marcas)
        rel.aviso(f"O original estava travado ({type(e).__name__}); uma cópia foi arquivada em {copia.name} e ele sai da "
                  "entrada assim que for liberado (não será processado de novo)")
        return copia


def _ler_marcas(cfg) -> dict:
    arq = Path(cfg.logs) / MARCAS
    try:
        return json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
    except (OSError, ValueError):
        return {}


def _gravar_marcas(cfg, marcas: dict) -> None:
    arq = Path(cfg.logs) / MARCAS
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(marcas, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, arq)


def ja_publicado(cfg, arq: Path) -> bool:
    """Arquivo já processado que ficou na entrada por estar travado? Tenta retirá-lo; nunca reprocessa."""
    marcas = _ler_marcas(cfg)
    m = marcas.get(arq.name)
    if not m:
        return False
    try:
        st = arq.stat()
    except OSError:
        return False
    if [st.st_size, st.st_mtime_ns] != m[:2]:  # mudou: é uma versão nova do arquivo, processa normalmente
        marcas.pop(arq.name, None)
        _gravar_marcas(cfg, marcas)
        return False
    try:
        arq.unlink()
        marcas.pop(arq.name, None)
        _gravar_marcas(cfg, marcas)
        log.info("%s (já processado e arquivado em %s) foi retirado da entrada", arq.name, Path(m[2]).name)
    except OSError:
        pass
    return True


def nome_base_tabela(caminho: Path, regra: dict) -> str:
    destino = regra.get("destino") or {}
    return normalizar_nome_coluna(destino.get("tabela") or caminho.stem)


def _sinal(ao_etapa, etapa: str, arquivo: str, **extra):
    """Avisa quem estiver ouvindo (o escritório 3D) que uma etapa começou. Nunca interrompe o processamento."""
    if ao_etapa:
        try:
            ao_etapa(etapa, arquivo, **extra)
        except Exception:
            log.debug("Falha no aviso de etapa", exc_info=True)


_CACHE_EQUIPE: dict = {}


def obter_equipe(cfg: Config):
    """Equipe de agentes, recarregada sozinha quando algum arquivo de agentes/ ou habilidades_personalizadas/ muda."""
    from robo.agentes import Equipe

    def assinatura(pasta: Path):
        if not pasta.exists():
            return ()
        return tuple(sorted((p.name, p.stat().st_mtime_ns) for p in pasta.iterdir() if p.is_file()))

    chave = (str(cfg.agentes), str(cfg.habilidades))
    marca = (assinatura(cfg.agentes), assinatura(cfg.habilidades))
    guardado = _CACHE_EQUIPE.get(chave)
    if guardado and guardado[0] == marca:
        return guardado[1]
    equipe = Equipe(cfg.agentes, cfg.habilidades)
    _CACHE_EQUIPE[chave] = (marca, equipe)
    return equipe


def _tratar(caminho: Path, cfg: Config, rel: Relatorio, ao_etapa=None) -> _Tratamento:
    t = _Tratamento(regra=_regra_com_aprendizado(cfg, caminho.name))
    if t.regra:
        rel.info(f"Regra aplicada: padrão '{t.regra.get('padrao')}'")

    if caminho.suffix.lower() not in EXTENSOES_SUPORTADAS:
        rel.erro(f"Formato '{caminho.suffix}' não suportado. Envie .xlsx, .xlsm, .xls, .csv ou .txt")
        return t
    try:  # antes de agir: o que já se errou com esse mesmo arquivo (memória de acertos e erros)
        from robo import aprendizados
        for x in aprendizados.consultar(cfg, "esteira:validacao", {"arquivo": caminho.name}, n=3, onde="esteira",
                                        quem="validacao"):
            if json.loads(x["contexto"] or "{}").get("arquivo") == caminho.name:
                rel.info(f"Memória: este arquivo já foi barrado por: {x['causa'][:200]}"
                         + (f" Como evitar: {x['correcao']}" if x["correcao"] else ""))
    except Exception:
        log.debug("Consulta à memória falhou", exc_info=True)
    _sinal(ao_etapa, "leitura", caminho.name)
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
    equipe = obter_equipe(cfg)
    unica = len(t.brutas) == 1
    t.modelo = t.regra.get("modelo") if unica else None
    usados: set[str] = set()
    for aba, bruto in t.brutas.items():
        nome = normalizar_nome_coluna(cfg.saida["nome_aba"]) if unica else normalizar_nome_coluna(aba)
        while nome in usados:  # "Vendas" e "vendas " viram o mesmo nome: a segunda ganha _2, _3…
            nome = f"{nome}_{len([u for u in usados if u.startswith(nome)]) + 1}"
        usados.add(nome)
        rel.info(f"Aba '{aba}' lida: cabeçalho na linha {bruto.attrs.get('linha_cabecalho', '?')}, "
                 f"{len(bruto)} linhas, {len(bruto.columns)} colunas", tabela=nome)
        if len(bruto.attrs.get("abas_empilhadas") or []) > 1:
            rel.info(f"Abas com o mesmo cabeçalho empilhadas: {', '.join(bruto.attrs['abas_empilhadas'])} "
                     f"(coluna _aba_origem diz de onde veio cada linha)", tabela=nome)
        if bruto.attrs.get("abas_ignoradas"):
            rel.aviso(f"Abas com estrutura diferente NÃO foram lidas: {', '.join(bruto.attrs['abas_ignoradas'])}. "
                      f"Se elas também são dados, use 'abas: todas' na regra deste arquivo", tabela=nome)
        _sinal(ao_etapa, "limpeza", caminho.name)
        limpo = limpar_tabela(bruto, nome, cfg.limpeza, t.regra, rel)
        limpo = equipe.executar("limpeza", limpo, rel, nome, caminho.name, ao_etapa)
        _sinal(ao_etapa, "validacao", caminho.name)
        validar_tabela(limpo, nome, t.regra, rel)
        limpo = equipe.executar("validacao", limpo, rel, nome, caminho.name, ao_etapa)
        limpo = equipe.executar("modelagem", limpo, rel, nome, caminho.name, ao_etapa)
        t.analisaveis[nome] = limpo
        _sinal(ao_etapa, "modelagem", caminho.name)
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


def _carregar_banco(cfg: Config, caminho: Path, t: _Tratamento, rel: Relatorio, lote_id: str, aprovado: bool,
                    ao_etapa=None) -> list[str]:
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
                    _sinal(ao_etapa, "dba", caminho.name)
                    conferidos = banco.reconciliar(conn, lote_id, getattr(banco, "esperado_bruto", {}))
                    rel.info(f"DBA conferiu no PostgreSQL antes do commit: {', '.join(conferidos)}")
                    modelos = banco.executar_modelos(conn)
                    if modelos:
                        rel.info(f"Modelos SQL executados na camada analítica: {', '.join(modelos)}")
                banco.registrar_lote(conn, _dados_lote(caminho, lote_id, rel, t, gravadas, aprovado))
        except ErroCargaDados as e:
            rel.erro(f"Carga no PostgreSQL recusada: {e}")
            # a transação foi desfeita; numa nova, guarda só o bruto (auditoria) e o lote reprovado
            gravadas = []
            with conn.transaction():
                banco.inicializar(conn)
                if cfg.banco.get("carregar_bruto", True) and t.brutas:
                    gravadas = banco.carregar_bruto(conn, base, t.brutas, caminho.name, lote_id)
                banco.registrar_lote(conn, _dados_lote(caminho, lote_id, rel, t, gravadas, False))
            return gravadas
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


def processar_arquivo(caminho: str | Path, cfg: Config, gravar: bool = True, ao_etapa=None) -> Resultado:
    """gravar=False = modo diagnóstico: só analisa; não grava, não carrega no banco e não move nada.
    ao_etapa(etapa, arquivo, **extra): chamado no início de cada etapa (usado pelo escritório 3D).

    Com gravar=True, todo processamento abre um JOB (robo/jobs.py): cada etapa fica registrada com quem fez, e o job
    fecha com a evidência (linhas, saídas, hash). É a prova de trabalho — sem job, ninguém aparece "trabalhando"."""
    if not gravar:
        return _processar_arquivo(caminho, cfg, gravar, ao_etapa)
    from robo import jobs, organizacao
    nome = Path(caminho).name
    origem = "sintetico" if nome.upper().startswith("TREINO_") else "real"
    try:
        jid = jobs.abrir(cfg, "planilha", origem, nome, "recepcao")
        gente = organizacao.por_id(cfg)
    except Exception:  # o registro de trabalho nunca pode impedir a planilha de ser tratada
        log.debug("Job não aberto", exc_info=True)
        return _processar_arquivo(caminho, cfg, gravar, ao_etapa)

    def anotar(etapa, arquivo, **extra):
        if etapa not in ("adiado", "concluido"):
            quem = etapa if etapa in gente else (f"analise_{etapa}" if f"analise_{etapa}" in gente else None)
            try:
                jobs.etapa(cfg, jid, etapa, quem)
            except Exception:
                log.debug("Etapa do job não registrada", exc_info=True)
        if ao_etapa:
            ao_etapa(etapa, arquivo, **extra)
    cfg_job = cfg_de_treino(cfg) if origem == "sintetico" else cfg
    try:
        r = _processar_arquivo(caminho, cfg_job, gravar, anotar)
    except BaseException as e:
        jobs.fechar(cfg, jid, "falhou", {"erro": f"{type(e).__name__}: {e}"})
        raise
    saidas = [str(x) for x in (r.saidas or [])]
    evidencia = {"status": r.status, "linhas_entrada": r.linhas_entrada, "linhas_saida": r.linhas_saida, "saidas": saidas,
                 "execucao": r.id, "erros": len(r.relatorio.erros), "motivo_adiamento": r.motivo_adiamento or None}
    estado = "concluido" if r.status == SUCESSO else ("adiado" if r.status == ADIADO else "falhou")
    jobs.fechar(cfg, jid, estado, evidencia, jobs.hash_arquivo(saidas[0]) if saidas else None)
    try:  # memória de acertos e erros: quem barrou, por quê e como corrigir (robo/aprendizados.py)
        from robo import aprendizados
        aprendizados.da_esteira(cfg, r, jid)
    except Exception:
        log.debug("Aprendizado da esteira não registrado", exc_info=True)
    return r


def cfg_de_treino(cfg: Config) -> Config:
    """Planilha sintética (TREINO_*) passa pela MESMA esteira, mas tudo que ela produz fica separado: saída em
    Bases-Tratadas/_treino, originais/erros/relatórios em _treino, e NADA vai para o PostgreSQL de produção."""
    import copy
    t = copy.copy(cfg)
    t.dados = {**cfg.dados, "banco": {**(cfg.dados.get("banco") or {}), "habilitado": False}}
    for attr in ("tratadas", "erros", "originais", "relatorios"):
        setattr(t, attr, Path(getattr(cfg, attr)) / "_treino")
    return t


def _processar_arquivo(caminho: str | Path, cfg: Config, gravar: bool = True, ao_etapa=None) -> Resultado:
    inicio = time.perf_counter()
    caminho = Path(caminho)
    rel = Relatorio(arquivo=caminho.name)
    log.info("Processando %s" if gravar else "Testando %s (sem gravar nada)", caminho.name)

    try:
        t = _tratar(caminho, cfg, rel, ao_etapa if gravar else None)
    except Exception as e:  # erro inesperado: nunca deixa o robô cair
        log.exception("Falha inesperada ao tratar %s", caminho.name)
        rel.erro(f"Falha inesperada: {type(e).__name__}: {e}")
        t = _Tratamento()

    r = Resultado(arquivo=caminho, status=DIAGNOSTICO, relatorio=rel, tabelas=t.tabelas, linhas_entrada=t.linhas_entrada,
                  linhas_saida=sum(len(df) for n, df in t.tabelas.items() if not n.startswith("dim_")))
    if not gravar:
        r.duracao = time.perf_counter() - inicio
        r.tratamento = t
        return r

    cfg.criar_pastas()
    carimbo = _carimbo()
    # o id é o nome que o original terá no arquivo morto (Bases-Originais ou Bases-Erros)
    pasta_arquivo_morto = cfg.erros if rel.tem_erros else cfg.originais / datetime.now().strftime("%Y-%m")
    r.id = _destino_livre(pasta_arquivo_morto, f"{carimbo}_{caminho.name}").stem

    # ---- portão de produção: conferência independente do supervisor (quem faz não é quem aprova)
    from robo import producao
    conferencias = []
    if not rel.tem_erros and t.analisaveis:
        _sinal(ao_etapa, "supervisor", caminho.name)
        try:
            conferencias = producao.conferencia_supervisor(t, rel, cfg, caminho.name)
        except Exception as e:
            log.exception("Conferência do supervisor falhou")
            rel.erro(f"Supervisor de planilhas não conseguiu conferir: {type(e).__name__}: {e}")

    # ---- plenos, juniores e estagiário do 1º andar: segunda conferência independente (antes do banco)
    from robo import quadro
    ctx = quadro.Contexto(arquivo=caminho.name, cfg=cfg, regra=t.regra or {}, brutas=t.brutas, analisaveis=t.analisaveis,
                          tabelas=t.tabelas)
    if not rel.tem_erros and t.analisaveis:
        r.quadro += _conferencias_equipe("engenharia", ctx, rel, ao_etapa, bloquear=True)

    # ---- a saída está aberta no Excel/Power BI? adia ANTES do banco (senão o banco gravaria e o arquivo não)
    aberta = _saida_aberta(cfg, caminho) if not rel.tem_erros else None
    if aberta:
        _sinal(ao_etapa, "adiado", caminho.name)
        return _adiar(r, inicio, f"o arquivo de saída {aberta.name} está aberto (feche o Excel/Power BI)")

    # ---- carga no banco (antes dos arquivos: se o banco recusar, o arquivo não é publicado)
    if cfg.banco.get("habilitado"):
        from robo.banco import ErroBancoIndisponivel
        _sinal(ao_etapa, "banco", caminho.name)
        try:
            r.tabelas_banco = _carregar_banco(cfg, caminho, t, rel, r.id, aprovado=not rel.tem_erros, ao_etapa=ao_etapa)
        except ErroBancoIndisponivel as e:
            _sinal(ao_etapa, "adiado", caminho.name)
            return _adiar(r, inicio, f"PostgreSQL indisponível: {e}")
        except Exception as e:
            if _queda_de_conexao(e):  # conexão caiu no meio da carga: não é defeito da planilha — tenta de novo depois
                _sinal(ao_etapa, "adiado", caminho.name)
                return _adiar(r, inicio, f"a conexão com o PostgreSQL caiu durante a carga ({type(e).__name__})")
            log.exception("Falha inesperada no banco ao carregar %s", caminho.name)
            rel.erro(f"Falha inesperada no PostgreSQL: {type(e).__name__}: {e}")

    r.checklist = None
    if not rel.tem_erros:
        _sinal(ao_etapa, "coord_engenharia", caminho.name)
        r.checklist = producao.checklist_engenharia(rel, conferencias, obter_equipe(cfg), bool(cfg.banco.get("habilitado")),
                                                    bool(r.tabelas_banco) if cfg.banco.get("habilitado") else None,
                                                    equipe_quadro=r.quadro)
        if not r.checklist["liberado"]:
            for i in r.checklist["itens"]:
                if not i["ok"]:
                    rel.erro(f"Coordenadora de Engenharia não liberou para produção: {i['item']}"
                             + (f" — {i['detalhe']}" if i["detalhe"] else ""))
        else:
            rel.info(f"Liberado para produção pela Coordenadora de Engenharia ({len(r.checklist['itens'])} itens do checklist OK)")
    _sinal(ao_etapa, "publicacao", caminho.name)

    def reprovar():
        r.status = REPROVADO
        r.linhas_saida = 0
        r.id = _destino_livre(cfg.erros, f"{r.id}{caminho.suffix}").stem  # mantém o id (lote do banco) se estiver livre
        r.destino_original = _arquivar_ou_marcar(cfg, caminho, cfg.erros, f"{r.id}{caminho.suffix}", rel)
        relatorio_txt = r.destino_original.with_name(f"{r.destino_original.stem}_ERROS.txt")
        relatorio_txt.write_text(rel.texto(), encoding="utf-8-sig")
        r.saidas = [relatorio_txt]
        log.warning("REPROVADO %s: %d erro(s). Veja %s", caminho.name, len(rel.erros), relatorio_txt)

    if not rel.tem_erros and str(cfg.saida.get("formato", "xlsx")).lower() != "nenhum":
        nome_base = caminho.stem + (cfg.saida.get("sufixo") or "")
        if cfg.saida.get("versionar"):
            nome_base += f"_{carimbo}"
        # guarda a versão publicada anterior: se a nova for reprovada na releitura, a anterior volta
        anteriores = _guardar_anteriores(cfg.tratadas, nome_base, Path(cfg.logs) / "versao_anterior")
        try:
            r.saidas, avisos = gravar_tabelas(t.tabelas, cfg.tratadas, nome_base, cfg.saida)
        except PermissionError:
            _restaurar_anteriores(anteriores)
            _sinal(ao_etapa, "adiado", caminho.name)
            motivo = "o arquivo de saída está aberto (feche o Excel/Power BI)"
            if r.tabelas_banco:  # o banco já tinha confirmado: desfaz o lote para a próxima tentativa não duplicar
                try:
                    from robo.banco import Banco
                    Banco(cfg.banco, cfg.base).desfazer_lote(r.id, r.tabelas_banco, f"adiado: {motivo}")
                except Exception:
                    log.exception("Não consegui desfazer o lote %s no PostgreSQL", r.id)
            return _adiar(r, inicio, motivo)
        except Exception as e:  # ex.: formato de saída inválido no config.yaml — reprova em vez de tentar para sempre
            _restaurar_anteriores(anteriores)
            rel.erro(f"Não consegui gravar a saída: {e}")
            r.saidas, avisos = [], []
        for a in avisos:
            rel.aviso(a)
        # releitura do que foi gravado: se o disco gravou diferente, nada fica publicado
        ctx.saidas = list(r.saidas)
        r.quadro += _conferencias_equipe("publicacao", ctx, rel, ao_etapa, bloquear=True)
        if rel.tem_erros:
            for saida in r.saidas:
                Path(saida).unlink(missing_ok=True)
            _restaurar_anteriores(anteriores)
            if r.tabelas_banco:
                rel.erro("Atenção: a carga no PostgreSQL já tinha sido confirmada; o lote "
                         f"{r.id} deve ser conferido/removido pela DBA")
            r.saidas = []
        else:
            _descartar_anteriores(anteriores)

    if rel.tem_erros:
        reprovar()
    else:
        nome_base = caminho.stem + (cfg.saida.get("sufixo") or "")
        if cfg.saida.get("versionar"):
            nome_base += f"_{carimbo}"
        r.status = SUCESSO
        r.destino_original = _arquivar_ou_marcar(cfg, caminho, cfg.originais / datetime.now().strftime("%Y-%m"),
                                                 f"{r.id}{caminho.suffix}", rel)
        _gravar_relatorio_qualidade(cfg, nome_base, rel, t.tabelas, r.checklist)
        destinos = [p.name for p in r.saidas] + r.tabelas_banco
        log.info("OK %s -> %s (%d linhas, %d aviso(s))", caminho.name, ", ".join(destinos), r.linhas_saida, len(rel.avisos))
        # 2º andar: análise automática. Já está publicado; aqui nada pode reprovar ou travar.
        try:
            from robo.analise import analisar
            r.analise = analisar(t.analisaveis, caminho.name, r.id, cfg, t.regra, ao_etapa)
            if r.analise:
                log.info("Análise de %s pronta (%s)", caminho.name, Path(r.analise.get("relatorio") or "painel").name)
                base_min = int((cfg.dados.get("analise") or {}).get("base_minima", 30))
                ctx.analise = r.analise
                revisao = _conferencias_equipe("analise", ctx, rel, ao_etapa, bloquear=False)
                r.quadro += revisao
                _sinal(ao_etapa, "coord_analise", caminho.name)
                r.checklist_analise = producao.checklist_analise(r.analise, base_min, revisao)
                _sinal(ao_etapa, "ger_analise", caminho.name)
                from robo.quadro import manchete
                r.analise["manchete"] = manchete(r.analise)
        except Exception:
            log.exception("Análise automática de %s falhou (a planilha já está publicada)", caminho.name)
        # 3º andar: Sala Excel monta a entrega com fórmulas e conferência
        try:
            from robo.analise import chave_base
            from robo.excel import gerar_entrega
            r.excel = gerar_entrega(t.analisaveis, caminho.name, chave_base(caminho.name, t.regra), cfg, None, None, ao_etapa)
            if r.excel:
                log.info("Sala Excel entregou %s (%d conferências)", Path(r.excel["arquivo"]).name, r.excel["conferencias"])
                ctx.excel = r.excel
                revisao = _conferencias_equipe("excel", ctx, rel, ao_etapa, bloquear=False)
                r.quadro += revisao
                falhas = [f"{x['nome']}: {a}" for x in revisao if x["bloqueia"] and not x["ok"] for a in x["achados"]]
                r.excel["revisao_ok"] = not falhas
                r.excel["divergencias"] = falhas
                if falhas:
                    log.error("Entrega Excel de %s com divergência: %s", caminho.name, "; ".join(falhas[:3]))
        except Exception:
            log.exception("Sala Excel falhou em %s (a planilha já está publicada)", caminho.name)
        # 4º andar: governança (dados pessoais) e catálogo de dados
        try:
            r.quadro += _conferencias_equipe("governanca", ctx, rel, ao_etapa, bloquear=False)
        except Exception:
            log.exception("Governança falhou em %s", caminho.name)
        # RH: conta observações dos estagiários e contrata quando os dados mostram demanda comprovada
        try:
            from robo import contratacao
            contratacao.registrar_observacoes(cfg, rel)
            contratacao.avaliar_experiencias(cfg)  # fim dos 3 meses de experiência
            for a in contratacao.avaliar(cfg, caminho.name, t.regra, t.analisaveis):
                rel.info(f"RH contratou {a['nome']} ({a['cargo']}) em observação: {a['descricao']}")
        except Exception:
            log.exception("Contratação automática falhou em %s", caminho.name)

    r.duracao = time.perf_counter() - inicio
    if r.status == SUCESSO:
        ctx.duracao = r.duracao
        r.quadro += _conferencias_equipe("fim", ctx, rel, None, bloquear=False)
    _registrar(cfg, r)
    _sinal(ao_etapa, "concluido", caminho.name, status=r.status, linhas=r.linhas_saida,
           erros=len(rel.erros), banco=bool(r.tabelas_banco))
    return r


def _adiar(r: Resultado, inicio: float, motivo: str) -> Resultado:
    r.status = ADIADO
    r.motivo_adiamento = motivo
    r.duracao = time.perf_counter() - inicio
    log.warning("ADIADO %s: %s. Tentarei de novo em instantes.", r.arquivo.name, motivo)
    return r


def _registrar(cfg: Config, r: Resultado):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    historico.registrar_ocorrencias(cfg.relatorios, agora, r.arquivo.name, r.status, r.id, r.relatorio.ocorrencias)
    historico.registrar(cfg.logs, {
        "data_hora": agora, "arquivo": r.arquivo.name, "status": r.status,
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
        "analise": {k: v for k, v in (r.analise or {}).items() if not k.startswith("_")} or None,
        "checklist_producao": r.checklist,
        "checklist_analise": r.checklist_analise,
        "excel": r.excel,
        "quadro": r.quadro,
        "ocorrencias": [o.__dict__ for o in r.relatorio.ocorrencias],
    })


def _gravar_relatorio_qualidade(cfg: Config, nome_base: str, rel: Relatorio, tabelas: dict, checklist: dict | None = None):
    """Relatório de qualidade + dicionário de dados ficam em Bases-Relatorios (fora da pasta que o Power BI lê)."""
    try:
        cfg.relatorios.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(cfg.relatorios / f"{nome_base}_qualidade.xlsx", engine="openpyxl") as w:
            rel.para_dataframe().to_excel(w, sheet_name="log_qualidade", index=False)
            dicionario_dados(tabelas).to_excel(w, sheet_name="dicionario_dados", index=False)
            if checklist:
                from robo.producao import tabela_checklist
                tabela_checklist(checklist).to_excel(w, sheet_name="checklist_producao", index=False)
            from robo.escrita import _neutralizar_formulas
            for ws in w.sheets.values():  # textos da origem que começam com "=" ficam como texto
                _neutralizar_formulas(ws)
    except PermissionError:
        log.warning("Relatório de qualidade de %s não foi atualizado (arquivo aberto).", nome_base)
