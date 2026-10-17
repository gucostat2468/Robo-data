"""Habilidades: habilidades de tratamento de dados que os agentes executam.

Uma habilidade é uma função  f(df, parametros, contexto) -> df  registrada com metadados:
nome, categoria, descrição, CONHECIMENTO (quando usar / cuidados) e PARÂMETROS tipados.
O painel usa os metadados para montar o formulário de configuração automaticamente.

Criar a sua (arquivo .py dentro da pasta habilidades_personalizadas/ do projeto):

    from robo.habilidades import Param, habilidade

    @habilidade(id="marcar_vip", nome="Marcar clientes VIP", categoria="Minhas habilidades",
           descricao="Cria a coluna vip = Sim quando o valor passa do limite.",
           parametros=[Param("coluna", "coluna", "Coluna de valor"),
                       Param("limite", "numero", "Valor mínimo para ser VIP", padrao=1000)])
    def marcar_vip(df, p, ctx):
        df["vip"] = (df[p["coluna"]] >= p["limite"]).map({True: "Sim", False: "Não"})
        ctx.info(f"{(df['vip'] == 'Sim').sum()} clientes VIP")
        return df
"""

from __future__ import annotations

import importlib.util
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import pandas as pd

log = logging.getLogger("robo")

TIPOS_PARAMETRO = {"coluna", "colunas", "texto", "numero", "inteiro", "booleano", "escolha", "lista", "mapa", "expressao"}


class ErroHabilidade(Exception):
    """Configuração inválida de uma habilidade (parâmetro faltando, coluna inexistente...)."""


class ErroColunaAusente(ErroHabilidade):
    """A planilha não tem a coluna que a habilidade usa (pode ser pulada se a habilidade estiver marcada como opcional)."""


@dataclass
class Param:
    nome: str
    tipo: str
    rotulo: str
    obrigatorio: bool = True
    padrao: Any = None
    opcoes: list = field(default_factory=list)
    ajuda: str = ""
    existente: bool = True   # para coluna/colunas: precisa existir na planilha? (False = coluna que será criada)

    def __post_init__(self):
        if self.tipo not in TIPOS_PARAMETRO:
            raise ValueError(f"Tipo de parâmetro inválido: {self.tipo}")
        if self.padrao is not None:
            self.obrigatorio = False


@dataclass
class Habilidade:
    id: str
    nome: str
    categoria: str
    descricao: str
    funcao: Callable
    parametros: list[Param] = field(default_factory=list)
    conhecimento: str = ""
    origem: str = "nativa"

    def metadados(self) -> dict:
        return {"id": self.id, "nome": self.nome, "categoria": self.categoria, "descricao": self.descricao,
                "conhecimento": self.conhecimento, "origem": self.origem,
                "parametros": [asdict(p) for p in self.parametros]}


REGISTRO: dict[str, Habilidade] = {}
ERROS_CARGA: list[str] = []


def habilidade(id: str, nome: str, categoria: str, descricao: str, parametros: list[Param] | None = None,
          conhecimento: str = ""):
    def decorar(funcao):
        origem = "personalizada" if not funcao.__module__.startswith("robo.") else "nativa"
        REGISTRO[id] = Habilidade(id, nome, categoria, descricao, funcao, parametros or [], conhecimento.strip(), origem)
        return funcao
    return decorar


# ---------------------------------------------------------------------------- contexto
class Contexto:
    """O que a habilidade enxerga além dos dados: onde registrar ocorrências e de quem é a tarefa."""

    def __init__(self, rel, tabela: str, arquivo: str, agente: str, habilidade_nome: str):
        self.rel, self.tabela, self.arquivo, self.agente, self.habilidade_nome = rel, tabela, arquivo, agente, habilidade_nome

    def _msg(self, mensagem: str) -> str:
        return f"{mensagem} — {self.agente} · {self.habilidade_nome}"

    def erro(self, mensagem, coluna="", quantidade=None, exemplos=()):
        self.rel.erro(self._msg(mensagem), tabela=self.tabela, coluna=coluna, quantidade=quantidade, exemplos=exemplos)

    def aviso(self, mensagem, coluna="", quantidade=None, exemplos=()):
        self.rel.aviso(self._msg(mensagem), tabela=self.tabela, coluna=coluna, quantidade=quantidade, exemplos=exemplos)

    def info(self, mensagem, coluna="", quantidade=None, exemplos=()):
        self.rel.info(self._msg(mensagem), tabela=self.tabela, coluna=coluna, quantidade=quantidade, exemplos=exemplos)

    def tratar_invalidos(self, df: pd.DataFrame, coluna: str, mascara: pd.Series, acao: str, mensagem: str,
                         exemplos_de=None) -> pd.DataFrame:
        """Padrão único para valores inválidos: erro (reprova), aviso (mantém), vazio (apaga) ou remover (linha)."""
        mascara = mascara.fillna(False).astype(bool)
        qtd = int(mascara.sum())
        if not qtd:
            return df
        fonte = exemplos_de if exemplos_de is not None else df[coluna]
        exemplos = [f"linha {i}: '{fonte[i]}'" for i in df.index[mascara][:5]]
        if acao == "erro":
            self.erro(mensagem, coluna=coluna, quantidade=qtd, exemplos=exemplos)
        elif acao == "aviso":
            self.aviso(mensagem, coluna=coluna, quantidade=qtd, exemplos=exemplos)
        elif acao == "vazio":
            df = df.copy()
            df.loc[mascara, coluna] = pd.NA
            self.aviso(f"{mensagem} (esvaziados)", coluna=coluna, quantidade=qtd, exemplos=exemplos)
        elif acao == "remover":
            df = df[~mascara]
            self.aviso(f"{mensagem} (linhas removidas)", coluna=coluna, quantidade=qtd, exemplos=exemplos)
        return df


ACAO_INVALIDOS = Param("invalidos", "escolha", "O que fazer com valores inválidos", padrao="erro",
                       opcoes=["erro", "aviso", "vazio", "remover"],
                       ajuda="erro = reprova o arquivo · aviso = mantém e registra · vazio = apaga o valor · remover = apaga a linha")


# ---------------------------------------------------------------------------- parâmetros
def _como_lista(valor) -> list:
    if valor is None or valor == "":
        return []
    if isinstance(valor, (list, tuple)):
        return [v for v in valor if str(v).strip() != ""]
    return [v.strip() for v in str(valor).replace("\n", ",").split(",") if v.strip()]


def _como_mapa(valor) -> dict:
    if not valor:
        return {}
    if isinstance(valor, dict):
        return {str(k): v for k, v in valor.items()}
    mapa = {}
    for linha in str(valor).splitlines():
        if "=" in linha:
            k, v = linha.split("=", 1)
            mapa[k.strip()] = v.strip()
    return mapa


def preparar_parametros(sk: Habilidade, brutos: dict, colunas_df=None) -> dict:
    """Converte e valida os parâmetros. Levanta ErroHabilidade com mensagem clara."""
    from robo.limpeza import normalizar_nome_coluna
    p = {}
    brutos = brutos or {}
    for par in sk.parametros:
        valor = brutos.get(par.nome, par.padrao)
        vazio = valor is None or valor == "" or valor == [] or valor == {}
        if vazio:
            if par.obrigatorio:
                raise ErroHabilidade(f"parâmetro obrigatório '{par.rotulo}' não preenchido")
            p[par.nome] = par.padrao
            continue
        try:
            if par.tipo == "coluna":
                valor = normalizar_nome_coluna(valor)
            elif par.tipo == "colunas":
                valor = [normalizar_nome_coluna(c) for c in _como_lista(valor)]
            elif par.tipo == "numero":
                valor = float(str(valor).replace(",", "."))
            elif par.tipo == "inteiro":
                valor = int(float(str(valor).replace(",", ".")))
            elif par.tipo == "booleano":
                valor = valor if isinstance(valor, bool) else str(valor).strip().lower() in ("1", "true", "sim", "s", "yes")
            elif par.tipo == "lista":
                valor = _como_lista(valor)
            elif par.tipo == "mapa":
                valor = _como_mapa(valor)
            elif par.tipo == "escolha":
                valor = str(valor)
                if par.opcoes and valor not in par.opcoes:
                    raise ErroHabilidade(f"'{par.rotulo}' aceita: {', '.join(par.opcoes)}")
            else:
                valor = str(valor)
        except (TypeError, ValueError) as e:
            raise ErroHabilidade(f"valor inválido em '{par.rotulo}': {valor!r}") from e
        p[par.nome] = valor
    if colunas_df is not None:
        faltando = []
        for par in sk.parametros:
            if not par.existente or not p.get(par.nome):
                continue
            if par.tipo == "coluna" and p[par.nome] not in colunas_df:
                faltando.append(p[par.nome])
            elif par.tipo == "colunas":
                faltando += [c for c in p[par.nome] if c not in colunas_df]
        if faltando:
            raise ErroColunaAusente(f"coluna(s) inexistente(s) na planilha: {', '.join(faltando)}")
    return p


# ---------------------------------------------------------------------------- execução / carga
def executar_habilidade(df: pd.DataFrame, config: dict, rel, tabela: str, arquivo: str, agente: str) -> pd.DataFrame:
    sk = REGISTRO.get(config.get("habilidade", ""))
    nome_agente = agente
    if sk is None:
        rel.erro(f"Habilidade '{config.get('habilidade')}' não existe no catálogo — {nome_agente}", tabela=tabela)
        return df
    ctx = Contexto(rel, tabela, arquivo, nome_agente, sk.nome)
    try:
        p = preparar_parametros(sk, config.get("parametros") or {}, set(df.columns))
        resultado = sk.funcao(df.copy(), p, ctx)
        if not isinstance(resultado, pd.DataFrame):
            raise ErroHabilidade("a habilidade não devolveu uma tabela")
        return resultado
    except ErroColunaAusente as e:
        if config.get("opcional"):
            ctx.info(f"Habilidade pulada nesta planilha ({e}) — marcada como opcional")
        else:
            ctx.erro(f"Configuração inválida: {e}. Se esta planilha não precisa desta tarefa, limite o agente em "
                     f"'Arquivos que ele trata' (ex.: nps_*) ou marque a habilidade como opcional")
    except ErroHabilidade as e:
        ctx.erro(f"Configuração inválida: {e}")
    except Exception as e:
        log.exception("Falha na habilidade %s", sk.id)
        ctx.erro(f"Falha ao executar: {type(e).__name__}: {e}")
    return df


def carregar_personalizadas(pasta: Path) -> list[str]:
    """Importa os .py de habilidades_personalizadas/. Erros não derrubam o robô: ficam listados no painel."""
    ERROS_CARGA.clear()
    for sk_id in [k for k, v in REGISTRO.items() if v.origem == "personalizada"]:
        REGISTRO.pop(sk_id, None)
    if not pasta.exists():
        return []
    carregadas = []
    for arq in sorted(pasta.glob("*.py")):
        if arq.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"habilidades_personalizadas.{arq.stem}", arq)
            modulo = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(modulo)
            carregadas.append(arq.name)
        except Exception as e:
            ERROS_CARGA.append(f"{arq.name}: {type(e).__name__}: {e}")
            log.error("Habilidade personalizada %s não carregou: %s", arq.name, e)
    return carregadas


def catalogo() -> list[dict]:
    return sorted((s.metadados() for s in REGISTRO.values()), key=lambda m: (m["origem"] != "nativa", m["categoria"], m["nome"]))


from robo.habilidades import nativas  # noqa: E402,F401  (registra o catálogo nativo)
