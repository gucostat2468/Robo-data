"""Leitura do config.yaml, valores padrão e descoberta automática das pastas do OneDrive."""

from __future__ import annotations

import copy
import fnmatch
import os
from pathlib import Path

import yaml

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
ARQUIVO_CONFIG_PADRAO = RAIZ_PROJETO / "config.yaml"

NOME_PASTA_ENTRADA = "Bases-Limpeza"
NOME_PASTA_SAIDA = "Bases-Tratadas"

PADROES: dict = {
    "pastas": {
        # "auto" = procura a pasta Bases-Limpeza dentro do seu OneDrive
        "entrada": "auto",
        "saida": "auto",
        # Pastas auxiliares. "auto" = criadas ao lado de Bases-Limpeza
        "erros": "auto",
        "originais": "auto",
        "relatorios": "auto",
        "logs": "logs",
        # definições dos agentes (YAML) e habilidades em Python escritas por você
        "agentes": "agentes",
        "habilidades": "habilidades_personalizadas",
    },
    "monitoramento": {
        "intervalo_segundos": 5,
        # tempo que o arquivo precisa ficar sem mudar (OneDrive terminou de sincronizar)
        "espera_estabilidade_segundos": 10,
    },
    "leitura": {
        # "primeira" = primeira aba com dados | "todas" = cada aba vira uma tabela
        "abas": "primeira",
        "linhas_busca_cabecalho": 20,
    },
    "limpeza": {
        "remover_duplicadas": True,
        "remover_linhas_total": True,
        "inferir_tipos": True,
        # % mínimo de valores convertíveis para a coluna virar número/data
        "limiar_conversao": 0.95,
        "valores_nulos": ["", "-", "--", "---", ".", "n/a", "na", "null", "none", "nan", "nulo", "vazio", "sem informação", "sem informacao", "s/i"],
        # "erro" = #REF!, #DIV/0!, #N/D etc. bloqueiam o arquivo | "anular" = viram vazio (com aviso)
        "erros_excel": "erro",
        # colunas cujo nome indica identificador ficam sempre como texto (preserva zeros à esquerda)
        "padroes_identificador": ["id", "id_*", "*_id", "cpf*", "cnpj*", "cep*", "telefone*", "celular*", "matricula*", "codigo*", "cod_*", "ra", "rg"],
    },
    "saida": {
        # xlsx | csv | ambos | nenhum (nenhum = só grava no banco)
        "formato": "xlsx",
        "sufixo": "",
        # True = cada processamento gera um arquivo novo com data/hora no nome
        "versionar": False,
        "nome_aba": "dados",
        "colunas_auditoria": True,
        "csv_separador": ";",
        "csv_decimal": ",",
    },
    "banco": {
        # Carga no PostgreSQL (ELT). Desligado até você configurar.
        "habilitado": False,
        "host": "localhost",
        "porta": 5432,
        "banco": "robo_dados",
        "usuario": "postgres",
        "senha": "",
        # se esta variável de ambiente existir, a senha vem dela (mais seguro que deixar no arquivo)
        "senha_variavel_ambiente": "ROBO_PG_SENHA",
        "carregar_bruto": True,
        "pasta_modelos": "modelos_sql",
        # por_arquivo | substituir | mesclar | anexar
        "modo_carga_padrao": "por_arquivo",
        "tempo_limite_conexao": 5,
    },
    # 2º andar: análise automática após cada publicação (ver robo/analise.py)
    "analise": {
        "habilitado": True,
        "base_minima": 30,
        "confianca": 0.95,
        "max_categorias": 30,
        "max_segmentos": 10,
        "variacao_alerta_pct": 30,
        "analistas_desligados": [],
    },
    # 3º andar: Sala Excel (entrega com fórmulas e conferência para cada base aprovada)
    "excel": {"habilitado": True, "max_linhas": 300000, "max_categorias": 30, "max_segmentos": 6, "top_trade": 50},
    "painel": {
        "porta": 8765,
        "ligar_robo_ao_abrir": True,
        "notificacoes": True,
    },
    "manutencao": {
        "dias_retencao_originais": 180,
        "dias_retencao_relatorios": 180,
        "dias_retencao_logs": 60,
    },
    "regras": [],
}


# chave em config.yaml -> atributo do objeto Config (a pasta de saída se chama "tratadas" no código)
ATRIBUTO_PASTA = {"saida": "tratadas", "erros": "erros", "originais": "originais", "relatorios": "relatorios"}


class ErroConfig(Exception):
    pass


def _mesclar(base: dict, extra: dict) -> dict:
    resultado = copy.deepcopy(base)
    for chave, valor in (extra or {}).items():
        if isinstance(valor, dict) and isinstance(resultado.get(chave), dict):
            resultado[chave] = _mesclar(resultado[chave], valor)
        else:
            resultado[chave] = valor
    return resultado


def _expandir(caminho: str, base: Path) -> Path:
    p = Path(os.path.expandvars(os.path.expanduser(str(caminho))))
    return p if p.is_absolute() else (base / p).resolve()


def raizes_onedrive() -> list[Path]:
    """Lugares onde o OneDrive costuma ficar no Windows (pessoal e corporativo)."""
    candidatos = []
    for var in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        if os.environ.get(var):
            candidatos.append(Path(os.environ[var]))
    casa = Path.home()
    if casa.exists():
        candidatos += sorted(casa.glob("OneDrive*"))
    vistos, unicos = set(), []
    for c in candidatos:
        chave = str(c).lower()
        if chave not in vistos and c.is_dir():
            vistos.add(chave)
            unicos.append(c)
    return unicos


def localizar_pasta(nome: str, raizes: list[Path] | None = None, profundidade: int = 4) -> Path | None:
    """Procura uma pasta pelo nome (sem diferenciar maiúsculas) até N níveis abaixo das raízes."""
    alvo = nome.lower()
    for raiz in raizes if raizes is not None else raizes_onedrive():
        fila = [(raiz, 0)]
        while fila:
            atual, nivel = fila.pop(0)
            if atual.name.lower() == alvo:
                return atual
            if nivel >= profundidade:
                continue
            try:
                filhos = [f for f in atual.iterdir() if f.is_dir() and not f.name.startswith(".")]
            except (PermissionError, OSError):
                continue
            fila += [(f, nivel + 1) for f in filhos]
    return None


class Config:
    def __init__(self, dados: dict, base: Path, arquivo: Path | None = None):
        self.dados = dados
        self.base = base
        self.arquivo = arquivo
        self._resolver_pastas()

    # ---- atalhos -------------------------------------------------------
    def __getitem__(self, chave):
        return self.dados[chave]

    @property
    def limpeza(self) -> dict:
        return self.dados["limpeza"]

    @property
    def leitura(self) -> dict:
        return self.dados["leitura"]

    @property
    def saida(self) -> dict:
        return self.dados["saida"]

    @property
    def monitoramento(self) -> dict:
        return self.dados["monitoramento"]

    @property
    def banco(self) -> dict:
        return self.dados["banco"]

    @property
    def painel(self) -> dict:
        return self.dados["painel"]

    @property
    def manutencao(self) -> dict:
        return self.dados["manutencao"]

    # ---- pastas --------------------------------------------------------
    def _resolver_pastas(self):
        p = self.dados["pastas"]
        entrada = p.get("entrada") or "auto"
        if str(entrada).lower() == "auto":
            achada = localizar_pasta(NOME_PASTA_ENTRADA)
            if achada is None:
                raise ErroConfig(
                    f"Não encontrei a pasta '{NOME_PASTA_ENTRADA}' dentro do OneDrive. "
                    "Abra o config.yaml e informe o caminho completo em pastas > entrada."
                )
            self.entrada = achada
        else:
            self.entrada = _expandir(entrada, self.base)

        irma = self.entrada.parent
        auto = {
            "saida": irma / NOME_PASTA_SAIDA,
            "erros": irma / "Bases-Erros",
            "originais": irma / "Bases-Originais",
            "relatorios": irma / "Bases-Relatorios",
        }
        for nome, padrao in auto.items():
            valor = p.get(nome) or "auto"
            setattr(self, ATRIBUTO_PASTA[nome], padrao if str(valor).lower() == "auto" else _expandir(valor, self.base))
        self.logs = _expandir(p.get("logs") or "logs", self.base)
        self.agentes = _expandir(p.get("agentes") or "agentes", RAIZ_PROJETO)
        self.habilidades = _expandir(p.get("habilidades") or p.get("skills") or "habilidades_personalizadas", RAIZ_PROJETO)

    def criar_pastas(self):
        for pasta in self.pastas().values():
            pasta.mkdir(parents=True, exist_ok=True)

    def pastas(self) -> dict[str, Path]:
        return {
            "Bases-Limpeza (entrada)": self.entrada,
            "Bases-Tratadas (saída)": self.tratadas,
            "Erros": self.erros,
            "Originais (backup)": self.originais,
            "Relatórios de qualidade": self.relatorios,
            "Logs": self.logs,
        }

    # ---- regras por arquivo ---------------------------------------------
    def regra_para(self, nome_arquivo: str) -> dict:
        """Primeira regra cujo 'padrao' casa com o nome do arquivo (ex.: 'nps_*.xlsx')."""
        for regra in self.dados.get("regras") or []:
            padrao = str(regra.get("padrao", "")).lower()
            if padrao and fnmatch.fnmatch(nome_arquivo.lower(), padrao):
                return regra
        return {}


def carregar_config(caminho: str | Path | None = None, sobrescrever: dict | None = None) -> Config:
    caminho = Path(caminho) if caminho else ARQUIVO_CONFIG_PADRAO
    dados_usuario = {}
    if caminho.exists():
        with open(caminho, encoding="utf-8") as f:
            dados_usuario = yaml.safe_load(f) or {}
        base = caminho.resolve().parent
    else:
        base = RAIZ_PROJETO
        if caminho != ARQUIVO_CONFIG_PADRAO and not sobrescrever:
            import logging
            logging.getLogger("robo").warning("Arquivo de configuração %s não existe: usando os valores padrão", caminho)
    dados = _mesclar(PADROES, dados_usuario)
    if sobrescrever:
        dados = _mesclar(dados, sobrescrever)
    if not isinstance(dados.get("regras"), list):
        raise ErroConfig("A seção 'regras' do config.yaml precisa ser uma lista (cada item começa com '- padrao:').")
    return Config(dados, base, caminho)
