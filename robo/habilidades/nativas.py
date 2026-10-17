"""Catálogo nativo de habilidades. Cada uma documenta QUANDO usar e os CUIDADOS (campo conhecimento)."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime

import numpy as np
import pandas as pd

from robo.limpeza import _converter, _detectar_decimal, normalizar_nome_coluna, sem_acento
from robo.habilidades import ACAO_INVALIDOS, ErroHabilidade, Param, habilidade

PADRONIZACAO = "Padronização"
DOCUMENTOS = "Documentos e contato"
QUALIDADE = "Qualidade e validação"
ENRIQUECIMENTO = "Enriquecimento"
PESQUISA = "Pesquisa e Customer Insights"
ESTRUTURA = "Estrutura"
PRIVACIDADE = "Privacidade (LGPD)"

PALAVRAS_MINUSCULAS = {"de", "da", "do", "das", "dos", "e", "em", "na", "no", "nas", "nos", "a", "o", "para", "por", "com"}


def _chave(v) -> str:
    return sem_acento(str(v)).strip().lower()


def _digitos(v) -> str:
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"\D", "", str(v))


def _numerica(df, coluna):
    if not pd.api.types.is_numeric_dtype(df[coluna]):
        raise ErroHabilidade(f"a coluna '{coluna}' precisa ser numérica (hoje é texto). Use a habilidade Converter tipo antes.")
    return df[coluna].astype("float64")


# =============================================================================== padronização
@habilidade("padronizar_texto", "Padronizar textos", PADRONIZACAO,
       "Deixa textos no mesmo formato: maiúsculas, minúsculas, título ou frase, com ou sem acentos.",
       [Param("colunas", "colunas", "Colunas de texto"),
        Param("modo", "escolha", "Formato", padrao="titulo", opcoes=["maiusculo", "minusculo", "titulo", "frase", "nenhum"],
              ajuda="título: 'Maria da Silva' (preposições ficam minúsculas)"),
        Param("remover_acentos", "booleano", "Remover acentos", padrao=False)],
       conhecimento="""
QUANDO USAR: nomes de cidades, cursos, produtos e categorias digitados de formas diferentes
("SÃO PAULO", "são paulo", "Sao Paulo"). Sem padronização, o Power BI mostra três barras para o mesmo valor.
CUIDADOS: remover acentos ajuda a agrupar, mas piora a leitura em relatórios — prefira remover só em colunas-chave.
Siglas (UF, EAD) ficam melhores em maiúsculo; nomes de pessoas em título.""")
def padronizar_texto(df, p, ctx):
    def titulo(s):
        palavras = s.lower().split(" ")
        return " ".join(w if (i and w in PALAVRAS_MINUSCULAS) else w[:1].upper() + w[1:] for i, w in enumerate(palavras))

    funcoes = {"maiusculo": str.upper, "minusculo": str.lower, "titulo": titulo,
               "frase": lambda s: s[:1].upper() + s[1:].lower(), "nenhum": lambda s: s}
    f = funcoes[p["modo"]]
    for col in p["colunas"]:
        antes = df[col].copy()
        df[col] = df[col].map(lambda v: (sem_acento(f(v)) if p["remover_acentos"] else f(v)) if isinstance(v, str) else v)
        mudou = int((antes.astype(str) != df[col].astype(str)).sum())
        if mudou:
            ctx.info(f"{mudou} valor(es) padronizados ({p['modo']})", coluna=col, quantidade=mudou)
    return df


@habilidade("mapear_valores", "De-para de valores", PADRONIZACAO,
       "Troca valores por uma versão oficial (ex.: 'a distância', 'EaD', 'online' → 'EAD').",
       [Param("coluna", "coluna", "Coluna"),
        Param("mapa", "mapa", "De-para (uma linha por valor: original=oficial)",
              ajuda="ex.:\na distancia=EAD\nonline=EAD\npresencial=Presencial"),
        Param("nao_mapeados", "escolha", "Valores fora do de-para", padrao="manter",
              opcoes=["manter", "aviso", "erro", "vazio"])],
       conhecimento="""
QUANDO USAR: categorias com grafias diferentes vindas de sistemas ou pessoas diferentes. É a habilidade mais usada em
pesquisa de mercado para consolidar respostas abertas curtas (ex.: canal, região, curso).
COMO FUNCIONA: a comparação ignora maiúsculas, acentos e espaços nas pontas.
CUIDADOS: use "erro" em 'valores fora do de-para' quando a lista oficial é fechada (ex.: UF) — assim um valor novo
nunca passa despercebido para o Power BI.""")
def mapear_valores(df, p, ctx):
    col = p["coluna"]
    mapa = {_chave(k): v for k, v in p["mapa"].items()}
    oficiais = {_chave(v) for v in mapa.values()}
    trocados = 0
    novos = []
    for i, v in df[col].items():
        if v is None or (not isinstance(v, str) and pd.isna(v)):
            novos.append(v)
            continue
        k = _chave(v)
        if k in mapa:
            trocados += mapa[k] != v
            novos.append(mapa[k])
        else:
            novos.append(v)
    df[col] = pd.Series(novos, index=df.index, dtype=object)
    if trocados:
        ctx.info(f"{trocados} valor(es) trocados pelo de-para", coluna=col, quantidade=trocados)
    fora = df[col].notna() & ~df[col].map(lambda v: _chave(v) in mapa or _chave(v) in oficiais)
    acao = p["nao_mapeados"]
    if acao != "manter":
        df = ctx.tratar_invalidos(df, col, fora, acao, "Valores fora do de-para")
    return df


@habilidade("converter_tipo", "Converter tipo", PADRONIZACAO,
       "Força colunas para texto, inteiro, decimal, data ou data e hora.",
       [Param("colunas", "colunas", "Colunas"),
        Param("tipo", "escolha", "Tipo", opcoes=["texto", "inteiro", "decimal", "data", "datahora"]),
        ACAO_INVALIDOS],
       conhecimento="""
QUANDO USAR: quando a detecção automática errar — por exemplo, uma coluna de notas com muitos "N/A" que ficou texto,
ou um código numérico que deve continuar texto.
ENTENDE: números brasileiros (1.234,56), moeda (R$), percentual (45% → 0,45) e datas dd/mm/aaaa.
CUIDADOS: inteiro com casas decimais é inválido; prefira "decimal" para valores monetários.""")
def converter_tipo(df, p, ctx):
    for col in p["colunas"]:
        original = df[col]
        convertida = _converter(original, p["tipo"], _detectar_decimal(original.dropna()))
        invalidos = original.notna() & convertida.isna()
        df[col] = convertida
        df = ctx.tratar_invalidos(df, col, invalidos, p["invalidos"], f"Valores que não são '{p['tipo']}'",
                                  exemplos_de=original)
    return df


@habilidade("arredondar", "Arredondar números", PADRONIZACAO,
       "Arredonda colunas numéricas para N casas decimais.",
       [Param("colunas", "colunas", "Colunas numéricas"), Param("casas", "inteiro", "Casas decimais", padrao=2)],
       conhecimento="""
QUANDO USAR: valores calculados com dízimas (ex.: médias) que poluem tabelas e somas no Power BI.
CUIDADOS: arredonde no FINAL; somar valores já arredondados acumula diferença de centavos.""")
def arredondar(df, p, ctx):
    for col in p["colunas"]:
        df[col] = _numerica(df, col).round(p["casas"])
    return df


# =============================================================================== documentos e contato
def _cpf_valido(d: str) -> bool:
    if len(d) != 11 or d == d[0] * 11:
        return False
    for n in (9, 10):
        soma = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        if int(d[n]) != (soma * 10 % 11) % 10:
            return False
    return True


def _cnpj_valido(d: str) -> bool:
    if len(d) != 14 or d == d[0] * 14:
        return False
    for n, pesos in ((12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]), (13, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])):
        resto = sum(int(d[i]) * pesos[i] for i in range(n)) % 11
        if int(d[n]) != (0 if resto < 2 else 11 - resto):
            return False
    return True


@habilidade("normalizar_documento", "CPF / CNPJ", DOCUMENTOS,
       "Padroniza e valida CPF e CNPJ pelos dígitos verificadores.",
       [Param("colunas", "colunas", "Colunas com CPF/CNPJ"),
        Param("tipo", "escolha", "Documento", padrao="auto", opcoes=["auto", "cpf", "cnpj"]),
        Param("formato", "escolha", "Formato de saída", padrao="digitos", opcoes=["digitos", "formatado"],
              ajuda="dígitos: 12345678909 · formatado: 123.456.789-09"),
        ACAO_INVALIDOS],
       conhecimento="""
QUANDO USAR: antes de cruzar bases por CPF/CNPJ (ex.: pesquisa × CRM). Pontuação diferente faz o cruzamento falhar.
COMO FUNCIONA: recupera zeros à esquerda perdidos pelo Excel e confere os dígitos verificadores (o mesmo cálculo da
Receita Federal). Documento com dígito errado quase sempre é erro de digitação.
CUIDADOS: CPF é dado pessoal (LGPD). Se a base vai circular, combine com a habilidade Anonimizar.""")
def normalizar_documento(df, p, ctx):
    for col in p["colunas"]:
        original = df[col]
        saida, invalidos = [], []
        for v in original:
            d = _digitos(v)
            if not d:
                saida.append(pd.NA), invalidos.append(False)
                continue
            tipo = p["tipo"] if p["tipo"] != "auto" else ("cnpj" if len(d) > 11 else "cpf")
            tamanho = 14 if tipo == "cnpj" else 11
            if tamanho - 3 <= len(d) < tamanho:
                d = d.zfill(tamanho)  # zeros à esquerda que o Excel removeu
            ok = _cnpj_valido(d) if tipo == "cnpj" else _cpf_valido(d)
            invalidos.append(not ok)
            if ok and p["formato"] == "formatado":
                d = (f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}" if tipo == "cpf"
                     else f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}")
            saida.append(d)
        df[col] = pd.Series(saida, index=df.index, dtype=object)
        df = ctx.tratar_invalidos(df, col, pd.Series(invalidos, index=df.index), p["invalidos"],
                                  "Documento inválido (dígito verificador não confere)", exemplos_de=original)
    return df


@habilidade("validar_email", "E-mail", DOCUMENTOS,
       "Coloca e-mails em minúsculas, tira espaços e valida o formato.",
       [Param("colunas", "colunas", "Colunas de e-mail"), ACAO_INVALIDOS],
       conhecimento="""
QUANDO USAR: listas para disparo de pesquisa, CRM e cruzamentos. E-mail inválido derruba a taxa de entrega e
pode prejudicar a reputação do domínio que dispara.
CUIDADOS: valida o FORMATO (nome@dominio.com), não se a caixa existe. Para disparos, prefira "vazio" ou "remover".""")
def validar_email(df, p, ctx):
    padrao = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$")
    for col in p["colunas"]:
        original = df[col]
        df[col] = original.map(lambda v: str(v).strip().lower().replace(" ", "") if isinstance(v, str) else v)
        invalidos = df[col].notna() & ~df[col].map(lambda v: bool(padrao.match(str(v))))
        df = ctx.tratar_invalidos(df, col, invalidos, p["invalidos"], "E-mail com formato inválido", exemplos_de=original)
    return df


@habilidade("normalizar_telefone", "Telefone (Brasil)", DOCUMENTOS,
       "Padroniza telefones brasileiros com DDD e valida a quantidade de dígitos.",
       [Param("colunas", "colunas", "Colunas de telefone"),
        Param("formato", "escolha", "Formato de saída", padrao="formatado", opcoes=["digitos", "formatado"],
              ajuda="formatado: (11) 98765-4321"),
        Param("ddd_padrao", "texto", "DDD para números sem DDD (opcional)", obrigatorio=False),
        ACAO_INVALIDOS],
       conhecimento="""
QUANDO USAR: listas de contato (closed loop com detratores, call center, WhatsApp).
COMO FUNCIONA: remove +55, zeros e símbolos; aceita fixo (10 dígitos) e celular (11 dígitos, começando com 9).
CUIDADOS: o DDD padrão só deve ser usado quando você tem certeza da região da base.""")
def normalizar_telefone(df, p, ctx):
    ddd = _digitos(p.get("ddd_padrao") or "")
    for col in p["colunas"]:
        original = df[col]
        saida, invalidos = [], []
        for v in original:
            d = _digitos(v).lstrip("0")
            if not d:
                saida.append(pd.NA), invalidos.append(False)
                continue
            if d.startswith("55") and len(d) in (12, 13):
                d = d[2:]
            if len(d) in (8, 9) and len(ddd) == 2:
                d = ddd + d
            ok = len(d) == 10 or (len(d) == 11 and d[2] == "9")
            invalidos.append(not ok)
            if ok and p["formato"] == "formatado":
                d = f"({d[:2]}) {d[2:-4]}-{d[-4:]}"
            saida.append(d)
        df[col] = pd.Series(saida, index=df.index, dtype=object)
        df = ctx.tratar_invalidos(df, col, pd.Series(invalidos, index=df.index), p["invalidos"],
                                  "Telefone inválido", exemplos_de=original)
    return df


@habilidade("normalizar_cep", "CEP", DOCUMENTOS,
       "Padroniza CEP no formato 00000-000 e recupera o zero à esquerda perdido pelo Excel.",
       [Param("colunas", "colunas", "Colunas de CEP"), ACAO_INVALIDOS],
       conhecimento="""
QUANDO USAR: análises por região e cruzamento com bases de endereço. O Excel transforma 01310-100 em 1310100.
CUIDADOS: valida apenas o formato (8 dígitos); não confere se o CEP existe nos Correios.""")
def normalizar_cep(df, p, ctx):
    for col in p["colunas"]:
        original = df[col]
        saida, invalidos = [], []
        for v in original:
            d = _digitos(v)
            if not d:
                saida.append(pd.NA), invalidos.append(False)
                continue
            if len(d) == 7:
                d = d.zfill(8)
            ok = len(d) == 8
            invalidos.append(not ok)
            saida.append(f"{d[:5]}-{d[5:]}" if ok else d)
        df[col] = pd.Series(saida, index=df.index, dtype=object)
        df = ctx.tratar_invalidos(df, col, pd.Series(invalidos, index=df.index), p["invalidos"], "CEP inválido",
                                  exemplos_de=original)
    return df


# =============================================================================== qualidade e validação
@habilidade("validar_regex", "Validar formato (expressão regular)", QUALIDADE,
       "Confere se os valores seguem um padrão (ex.: matrícula com 2 letras e 6 números).",
       [Param("coluna", "coluna", "Coluna"),
        Param("padrao", "texto", "Expressão regular", ajuda="ex.: ^[A-Z]{2}\\d{6}$"),
        Param("mensagem", "texto", "Mensagem do erro", padrao="Valor fora do padrão esperado"),
        ACAO_INVALIDOS],
       conhecimento="""
QUANDO USAR: códigos internos com formato fixo (matrícula, pedido, protocolo).
CUIDADOS: teste a expressão antes em uma planilha pequena (tela Testar planilha). ^ e $ obrigam o valor inteiro a casar.""")
def validar_regex(df, p, ctx):
    try:
        padrao = re.compile(p["padrao"])
    except re.error as e:
        raise ErroHabilidade(f"expressão regular inválida: {e}") from e
    col = p["coluna"]
    invalidos = df[col].notna() & ~df[col].map(lambda v: bool(padrao.search(str(v))))
    return ctx.tratar_invalidos(df, col, invalidos, p["invalidos"], p["mensagem"])


@habilidade("validar_datas", "Validar datas", QUALIDADE,
       "Barra datas futuras ou fora de um período.",
       [Param("coluna", "coluna", "Coluna de data"),
        Param("nao_futuras", "booleano", "Recusar datas no futuro", padrao=True),
        Param("minima", "texto", "Data mínima (dd/mm/aaaa)", obrigatorio=False),
        Param("maxima", "texto", "Data máxima (dd/mm/aaaa)", obrigatorio=False),
        ACAO_INVALIDOS],
       conhecimento="""
QUANDO USAR: data de resposta, compra ou atendimento. Datas futuras ou de 1900 costumam ser erro de digitação
ou de conversão (dia e mês trocados) e distorcem séries mensais no Power BI.""")
def validar_datas(df, p, ctx):
    col = p["coluna"]
    if not pd.api.types.is_datetime64_any_dtype(df[col]):
        raise ErroHabilidade(f"a coluna '{col}' não é data. Use a habilidade Converter tipo antes.")
    serie = df[col]
    fora = pd.Series(False, index=df.index)
    if p["nao_futuras"]:
        fora |= serie > pd.Timestamp(datetime.now())
    for chave, op in (("minima", "lt"), ("maxima", "gt")):
        if p.get(chave):
            try:
                limite = pd.Timestamp(datetime.strptime(p[chave].strip(), "%d/%m/%Y"))
            except ValueError as e:
                raise ErroHabilidade(f"data {chave} inválida: use dd/mm/aaaa") from e
            fora |= (serie < limite) if op == "lt" else (serie > limite)
    return ctx.tratar_invalidos(df, col, fora & serie.notna(), p["invalidos"], "Data fora do período permitido")


@habilidade("checar_duplicados", "Duplicidade por chave", QUALIDADE,
       "Encontra linhas com a mesma chave (ex.: mesmo cliente respondendo duas vezes).",
       [Param("colunas", "colunas", "Colunas que formam a chave"),
        Param("acao", "escolha", "O que fazer", padrao="erro", opcoes=["erro", "aviso", "manter_primeiro", "manter_ultimo"])],
       conhecimento="""
QUANDO USAR: pesquisas com uma resposta por pessoa, cadastros e pedidos. Duplicidade infla contagens e médias.
ESCOLHA: "manter_ultimo" é o padrão de mercado para pesquisas (vale a resposta mais recente);
"erro" é melhor quando duplicidade indica problema na extração.""")
def checar_duplicados(df, p, ctx):
    dup = df.duplicated(subset=p["colunas"], keep=False)
    if not dup.any():
        return df
    exemplos = [f"linha {i}: " + ", ".join(f"{c}={df.at[i, c]}" for c in p["colunas"]) for i in df.index[dup][:5]]
    acao = p["acao"]
    if acao in ("erro", "aviso"):
        getattr(ctx, acao)(f"Chave repetida ({' + '.join(p['colunas'])})", quantidade=int(dup.sum()), exemplos=exemplos)
        return df
    manter = "first" if acao == "manter_primeiro" else "last"
    remover = df.duplicated(subset=p["colunas"], keep=manter)
    ctx.aviso(f"Duplicidades removidas, mantendo o {'primeiro' if manter == 'first' else 'último'} registro",
              quantidade=int(remover.sum()), exemplos=exemplos)
    return df[~remover]


@habilidade("completude_minima", "Completude mínima", QUALIDADE,
       "Exige um percentual mínimo de preenchimento nas colunas indicadas.",
       [Param("colunas", "colunas", "Colunas"),
        Param("minimo_pct", "numero", "Preenchimento mínimo (%)", padrao=95),
        Param("acao", "escolha", "Se não atingir", padrao="erro", opcoes=["erro", "aviso"])],
       conhecimento="""
QUANDO USAR: colunas que sustentam indicadores (nota, data, segmento). Uma base com 40% de notas vazias gera
indicador enviesado — melhor barrar e corrigir na origem do que publicar.
REFERÊNCIA: abaixo de 80% de preenchimento a coluna não deve sustentar conclusões sozinha.""")
def completude_minima(df, p, ctx):
    total = len(df) or 1
    for col in p["colunas"]:
        pct = 100 * df[col].notna().sum() / total
        if pct < p["minimo_pct"]:
            getattr(ctx, p["acao"])(f"Preenchimento de {pct:.1f}% (mínimo {p['minimo_pct']:.0f}%)", coluna=col,
                                    quantidade=int(df[col].isna().sum()))
    return df


@habilidade("outliers", "Valores atípicos (outliers)", QUALIDADE,
       "Detecta valores muito fora do padrão pelo método IQR ou desvio-padrão.",
       [Param("coluna", "coluna", "Coluna numérica"),
        Param("metodo", "escolha", "Método", padrao="iqr", opcoes=["iqr", "zscore"],
              ajuda="IQR: robusto, bom para valores monetários · z-score: para distribuições simétricas"),
        Param("limite", "numero", "Sensibilidade", padrao=1.5, ajuda="IQR: 1,5 (padrão) ou 3 (só extremos) · z-score: 3"),
        Param("acao", "escolha", "O que fazer", padrao="sinalizar", opcoes=["sinalizar", "aviso", "erro", "remover"],
              ajuda="sinalizar: cria a coluna <coluna>_outlier (Sim/Não) para filtrar no Power BI")],
       conhecimento="""
QUANDO USAR: valores monetários, tempos de atendimento, quantidades. Um valor digitado com zeros a mais
distorce médias e gráficos.
CUIDADOS: outlier NÃO é sinônimo de erro (pode ser um cliente grande de verdade). Prefira "sinalizar" e decidir
na análise; "remover" só com certeza.""")
def outliers(df, p, ctx):
    col = p["coluna"]
    x = _numerica(df, col)
    if p["metodo"] == "iqr":
        q1, q3 = x.quantile(0.25), x.quantile(0.75)
        iqr = q3 - q1
        fora = (x < q1 - p["limite"] * iqr) | (x > q3 + p["limite"] * iqr)
    else:
        desvio = x.std()
        fora = ((x - x.mean()).abs() / desvio > p["limite"]) if desvio else pd.Series(False, index=df.index)
    fora = fora.fillna(False)
    if p["acao"] == "sinalizar":
        df[f"{col}_outlier"] = fora.map({True: "Sim", False: "Não"})
        if fora.any():
            ctx.info(f"{int(fora.sum())} outlier(s) sinalizado(s) em {col}_outlier", coluna=col, quantidade=int(fora.sum()))
        return df
    return ctx.tratar_invalidos(df, col, fora, p["acao"], f"Valor atípico ({p['metodo'].upper()})")


@habilidade("filtrar_linhas", "Filtrar linhas", QUALIDADE,
       "Mantém só as linhas que atendem a uma condição (ex.: status == 'Concluída').",
       [Param("condicao", "expressao", "Manter linhas onde…", ajuda="ex.: nota_nps >= 0 and status == 'Concluída'"),
        Param("acao", "escolha", "Linhas fora da condição", padrao="remover", opcoes=["remover", "aviso", "erro"])],
       conhecimento="""
QUANDO USAR: tirar testes, respostas incompletas, cancelados ou registros de outra unidade antes de publicar.
SINTAXE: nomes de colunas padronizados, comparações (==, !=, >, <), and/or, textos entre aspas simples.
CUIDADOS: sempre confira na tela Testar planilha quantas linhas saíram — um filtro errado some com dados.""")
def filtrar_linhas(df, p, ctx):
    try:
        manter = df.astype({c: "float64" for c in df.columns if str(df[c].dtype) == "Int64"}).eval(p["condicao"], engine="python")
    except Exception as e:
        raise ErroHabilidade(f"condição inválida: {e}") from e
    if not isinstance(manter, pd.Series) or manter.dtype != bool:
        manter = pd.Series(manter, index=df.index).fillna(False).astype(bool)
    fora = ~manter
    if p["acao"] == "remover":
        if fora.any():
            ctx.info(f"{int(fora.sum())} linha(s) removida(s) pelo filtro", quantidade=int(fora.sum()),
                     exemplos=[f"linha {i}" for i in df.index[fora][:5]])
        return df[manter]
    if fora.any():
        getattr(ctx, p["acao"])(f"Linhas fora da condição: {p['condicao']}", quantidade=int(fora.sum()),
                                exemplos=[f"linha {i}" for i in df.index[fora][:5]])
    return df


# =============================================================================== enriquecimento
@habilidade("preencher_vazios", "Preencher vazios", ENRIQUECIMENTO,
       "Completa células vazias com um valor fixo, o valor anterior, a média, a mediana ou a moda.",
       [Param("colunas", "colunas", "Colunas"),
        Param("metodo", "escolha", "Preencher com", opcoes=["valor", "anterior", "media", "mediana", "moda"]),
        Param("valor", "texto", "Valor fixo (se método = valor)", obrigatorio=False)],
       conhecimento="""
QUANDO USAR: "anterior" para planilhas com células mescladas (o Excel só guarda o valor na 1ª linha);
"valor" para categorias como "Não informado".
CUIDADO IMPORTANTE: preencher NOTAS de pesquisa com média/mediana INVENTA respostas e altera o resultado.
Em pesquisa, prefira deixar vazio e reportar a base de respondentes.""")
def preencher_vazios(df, p, ctx):
    for col in p["colunas"]:
        vazios = int(df[col].isna().sum())
        if not vazios:
            continue
        m = p["metodo"]
        if m == "valor":
            if p.get("valor") in (None, ""):
                raise ErroHabilidade("informe o valor fixo")
            valor = p["valor"]
            if pd.api.types.is_numeric_dtype(df[col]):
                try:
                    valor = float(str(valor).replace(",", "."))
                except ValueError as e:
                    raise ErroHabilidade(f"a coluna '{col}' é numérica; o valor precisa ser número") from e
            df[col] = df[col].fillna(valor)
        elif m == "anterior":
            df[col] = df[col].ffill()
        elif m in ("media", "mediana"):
            x = _numerica(df, col)
            df[col] = df[col].fillna(x.mean() if m == "media" else x.median())
        else:
            moda = df[col].mode(dropna=True)
            if len(moda):
                df[col] = df[col].fillna(moda.iloc[0])
        ctx.aviso(f"{vazios} vazio(s) preenchido(s) ({m})", coluna=col, quantidade=vazios)
    return df


@habilidade("coluna_calculada", "Coluna calculada", ENRIQUECIMENTO,
       "Cria uma coluna a partir de uma conta (ex.: valor_total = quantidade * preco).",
       [Param("nova_coluna", "coluna", "Nome da nova coluna", existente=False),
        Param("expressao", "expressao", "Fórmula", ajuda="ex.: quantidade * preco_unitario  ·  (receita - custo) / receita")],
       conhecimento="""
QUANDO USAR: medidas de LINHA que você vai somar/filtrar no Power BI (margem por pedido, tempo de atendimento).
QUANDO NÃO USAR: razões de TOTAL (ex.: % de promotores, ticket médio) — essas devem ser medidas DAX, senão a média
das razões fica errada no total.
SINTAXE: + − * / ( ), nomes de colunas padronizados.""")
def coluna_calculada(df, p, ctx):
    try:
        base = df.astype({c: "float64" for c in df.columns if str(df[c].dtype) == "Int64"})
        df[p["nova_coluna"]] = base.eval(p["expressao"], engine="python")
    except Exception as e:
        raise ErroHabilidade(f"fórmula inválida: {e}") from e
    ctx.info(f"Coluna {p['nova_coluna']} = {p['expressao']}")
    return df


@habilidade("classificar_faixas", "Faixas (idade, valor, tempo…)", ENRIQUECIMENTO,
       "Agrupa números em faixas nomeadas (ex.: idade → 18-24, 25-34…).",
       [Param("coluna", "coluna", "Coluna numérica"),
        Param("nova_coluna", "coluna", "Nome da nova coluna", existente=False),
        Param("limites", "lista", "Limites (em ordem crescente)", ajuda="ex.: 18, 25, 35, 45"),
        Param("rotulos", "lista", "Nomes das faixas (um a mais que os limites)",
              ajuda="ex.: Menos de 18, 18-24, 25-34, 35-44, 45+")],
       conhecimento="""
QUANDO USAR: perfis de público (faixa etária, renda, tempo de casa). Gráficos com faixas são muito mais legíveis
que com valores contínuos.
REGRA: cada limite inicia a faixa seguinte (18 entra em "18-24"). Use as mesmas faixas em todas as ondas da pesquisa
para comparar ao longo do tempo.""")
def classificar_faixas(df, p, ctx):
    try:
        limites = [float(str(v).replace(",", ".")) for v in p["limites"]]
    except ValueError as e:
        raise ErroHabilidade("os limites precisam ser números") from e
    if limites != sorted(limites):
        raise ErroHabilidade("os limites precisam estar em ordem crescente")
    if len(p["rotulos"]) != len(limites) + 1:
        raise ErroHabilidade(f"informe {len(limites) + 1} nomes de faixa para {len(limites)} limites")
    x = _numerica(df, p["coluna"])
    faixas = pd.cut(x, [-np.inf, *limites, np.inf], labels=p["rotulos"], right=False)
    df[p["nova_coluna"]] = faixas.astype(object).where(faixas.notna(), pd.NA)
    return df


@habilidade("extrair_data", "Partes da data", ENRIQUECIMENTO,
       "Cria colunas de ano, mês, trimestre, dia da semana… a partir de uma data.",
       [Param("coluna", "coluna", "Coluna de data"),
        Param("partes", "lista", "Partes", padrao=["ano", "mes", "ano_mes"],
              ajuda="ano, mes, mes_nome, trimestre, ano_mes, dia_semana, semana_ano")],
       conhecimento="""
QUANDO USAR: quando a base vai para Excel/tabela dinâmica ou para um Power BI SEM tabela calendário.
QUANDO NÃO USAR: no Power BI com modelo estrela, prefira a dim_calendario (regra "modelo: calendario") — é a
boa prática e permite inteligência de tempo no DAX.""")
def extrair_data(df, p, ctx):
    col = p["coluna"]
    if not pd.api.types.is_datetime64_any_dtype(df[col]):
        raise ErroHabilidade(f"a coluna '{col}' não é data")
    meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro",
             "Novembro", "Dezembro"]
    dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    d = df[col].dt
    geradores = {
        "ano": lambda: d.year.astype("Int64"), "mes": lambda: d.month.astype("Int64"),
        "mes_nome": lambda: d.month.map(lambda m: meses[int(m) - 1] if pd.notna(m) else pd.NA),
        "trimestre": lambda: d.quarter.map(lambda q: f"T{int(q)}" if pd.notna(q) else pd.NA),
        "ano_mes": lambda: d.strftime("%Y-%m"),
        "dia_semana": lambda: d.dayofweek.map(lambda x: dias[int(x)] if pd.notna(x) else pd.NA),
        "semana_ano": lambda: d.isocalendar().week.astype("Int64"),
    }
    for parte in p["partes"]:
        if parte not in geradores:
            raise ErroHabilidade(f"parte '{parte}' desconhecida (use: {', '.join(geradores)})")
        df[f"{col}_{parte}"] = geradores[parte]()
    return df


@habilidade("dividir_coluna", "Dividir coluna", ENRIQUECIMENTO,
       "Separa uma coluna em várias (ex.: 'São Paulo - SP' → cidade e uf).",
       [Param("coluna", "coluna", "Coluna"), Param("separador", "texto", "Separador", ajuda="ex.:  -  ou  /  ou  ;"),
        Param("novas_colunas", "colunas", "Nomes das novas colunas", existente=False)],
       conhecimento="""
QUANDO USAR: campos combinados vindos de sistemas (cidade/UF, nome completo, código-descrição).
CUIDADOS: a última nova coluna recebe o restante do texto se houver mais separadores do que colunas.""")
def dividir_coluna(df, p, ctx):
    n = len(p["novas_colunas"])
    partes = df[p["coluna"]].astype("string").str.split(p["separador"], n=n - 1, expand=True, regex=False)
    for i, nome in enumerate(p["novas_colunas"]):
        df[nome] = partes[i].str.strip().astype(object).where(partes[i].notna(), pd.NA) if i in partes.columns else pd.NA
    return df


@habilidade("juntar_colunas", "Juntar colunas", ENRIQUECIMENTO,
       "Concatena colunas em uma (ex.: cidade + ' / ' + uf).",
       [Param("colunas", "colunas", "Colunas, na ordem"), Param("separador", "texto", "Separador", padrao=" "),
        Param("nova_coluna", "coluna", "Nome da nova coluna", existente=False)],
       conhecimento="QUANDO USAR: rótulos para gráficos e chaves compostas para cruzamentos. Vazios são ignorados.")
def juntar_colunas(df, p, ctx):
    def juntar(linha):
        valores = [str(v) for v in linha if v is not None and not (not isinstance(v, str) and pd.isna(v)) and str(v) != ""]
        return p["separador"].join(valores) if valores else pd.NA
    df[p["nova_coluna"]] = df[p["colunas"]].astype(object).apply(juntar, axis=1)
    return df


# =============================================================================== pesquisa e customer insights
@habilidade("classificar_nps", "Classificar NPS", PESQUISA,
       "Cria a coluna Promotor / Neutro / Detrator a partir da nota de 0 a 10.",
       [Param("coluna", "coluna", "Coluna da nota (0 a 10)"),
        Param("nova_coluna", "coluna", "Nome da nova coluna", padrao="grupo_nps", existente=False),
        ACAO_INVALIDOS],
       conhecimento="""
METODOLOGIA (Bain/Reichheld): 9-10 Promotores · 7-8 Neutros · 0-6 Detratores. NPS = %Promotores − %Detratores
(vai de −100 a +100).
NO POWER BI: com esta coluna, o NPS vira uma medida simples:
  NPS = DIVIDE(COUNTROWS(FILTER(f, f[grupo_nps]="Promotor")) − COUNTROWS(FILTER(f, f[grupo_nps]="Detrator")), COUNTROWS(f)) * 100
CUIDADOS: notas fora de 0-10 são erro de coleta — por padrão o arquivo é reprovado.""")
def classificar_nps(df, p, ctx):
    col = p["coluna"]
    x = _numerica(df, col)
    invalidos = x.notna() & ((x < 0) | (x > 10) | (x != x.round()))
    df = ctx.tratar_invalidos(df, col, invalidos, p["invalidos"], "Nota NPS fora de 0 a 10")
    x = _numerica(df, col)
    x = x.where(~(x.notna() & ((x < 0) | (x > 10) | (x != x.round()))))  # nota inválida mantida não é classificada
    grupo = np.select([x >= 9, x >= 7, x >= 0], ["Promotor", "Neutro", "Detrator"], default="")
    df[p["nova_coluna"]] = pd.Series(grupo, index=df.index).replace("", pd.NA)
    contagem = df[p["nova_coluna"]].value_counts()
    n = int(contagem.sum())
    if n:
        nps = 100 * (contagem.get("Promotor", 0) - contagem.get("Detrator", 0)) / n
        ctx.info(f"NPS desta base: {nps:.1f} ({n} respostas)")
    return df


@habilidade("classificar_csat", "Classificar CSAT (top-2-box)", PESQUISA,
       "Marca quem está satisfeito pelas duas notas mais altas da escala.",
       [Param("coluna", "coluna", "Coluna da nota"),
        Param("escala", "escolha", "Escala", padrao="5", opcoes=["5", "7", "10"]),
        Param("nova_coluna", "coluna", "Nome da nova coluna", padrao="satisfeito", existente=False),
        ACAO_INVALIDOS],
       conhecimento="""
METODOLOGIA: CSAT = % de respondentes nas duas notas mais altas (top-2-box): 4-5 na escala de 5, 6-7 na de 7,
9-10 na de 10. É mais estável e comunicável que a média.
CUIDADOS: nunca compare CSAT de escalas diferentes sem reconverter.""")
def classificar_csat(df, p, ctx):
    col, escala = p["coluna"], int(p["escala"])
    x = _numerica(df, col)
    invalidos = x.notna() & ((x < 1) | (x > escala))
    df = ctx.tratar_invalidos(df, col, invalidos, p["invalidos"], f"Nota fora da escala 1 a {escala}")
    x = _numerica(df, col)
    x = x.where(~(x.notna() & ((x < 1) | (x > escala))))  # nota fora da escala mantida não é classificada
    df[p["nova_coluna"]] = x.map(lambda v: pd.NA if pd.isna(v) else ("Sim" if v >= escala - 1 else "Não"))
    return df


@habilidade("categorizar_texto", "Codificar verbatins por tema", PESQUISA,
       "Classifica respostas abertas em temas por palavras-chave (codificação temática).",
       [Param("coluna", "coluna", "Coluna de texto (comentário)"),
        Param("temas", "mapa", "Temas e palavras-chave (tema=palavra1, palavra2)",
              ajuda="ex.:\nPreço=caro, preço, valor, mensalidade\nAtendimento=atendimento, atendente, demora"),
        Param("nova_coluna", "coluna", "Nome da nova coluna", padrao="tema", existente=False),
        Param("multiplos", "booleano", "Permitir mais de um tema por resposta", padrao=True),
        Param("sem_tema", "texto", "Rótulo quando nenhum tema casar", padrao="Outros")],
       conhecimento="""
QUANDO USAR: primeira leitura quantitativa de comentários (NPS, CSAT, SAC): "quantos falam de preço?".
COMO FUNCIONA: procura as palavras-chave sem diferenciar acentos/maiúsculas e como palavra inteira ou início de
palavra ("atend" pega atendimento, atendente).
CUIDADOS: não entende ironia nem negação ("não é caro" conta como Preço). Valide uma amostra manualmente e
refine o livro de códigos — e acompanhe a % de "Outros" (acima de 30% indica temas faltando).""")
def categorizar_texto(df, p, ctx):
    regras = []
    for tema, palavras in p["temas"].items():
        termos = [_chave(t) for t in str(palavras).split(",") if t.strip()]
        if termos:
            regras.append((tema, re.compile(r"\b(" + "|".join(re.escape(t) for t in termos) + r")")))
    if not regras:
        raise ErroHabilidade("informe pelo menos um tema com palavras-chave")
    saida = []
    for v in df[p["coluna"]]:
        if v is None or (not isinstance(v, str) and pd.isna(v)) or not str(v).strip():
            saida.append(pd.NA)
            continue
        texto = _chave(v)
        achados = [tema for tema, rx in regras if rx.search(texto)]
        if not achados:
            saida.append(p["sem_tema"])
        else:
            saida.append("; ".join(achados) if p["multiplos"] else achados[0])
    df[p["nova_coluna"]] = pd.Series(saida, index=df.index, dtype=object)
    preenchidos = df[p["nova_coluna"]].dropna()
    if len(preenchidos):
        outros = 100 * (preenchidos == p["sem_tema"]).mean()
        ctx.info(f"{len(preenchidos)} comentário(s) codificados; {outros:.0f}% sem tema")
        if outros > 30:
            ctx.aviso(f"{outros:.0f}% dos comentários ficaram em '{p['sem_tema']}': revise as palavras-chave")
    return df


# =============================================================================== estrutura
@habilidade("selecionar_colunas", "Selecionar colunas", ESTRUTURA,
       "Mantém só as colunas necessárias ou exclui as que não devem ser publicadas.",
       [Param("modo", "escolha", "Modo", padrao="excluir", opcoes=["manter", "excluir"]),
        Param("colunas", "colunas", "Colunas")],
       conhecimento="""
QUANDO USAR: tirar colunas internas, de controle ou sensíveis antes de publicar. Modelos menores deixam o
Power BI mais rápido (boa prática: só importe o que vai usar).""")
def selecionar_colunas(df, p, ctx):
    if p["modo"] == "manter":
        auditoria = [c for c in df.columns if c.startswith("_")]
        return df[[*p["colunas"], *auditoria]]
    return df.drop(columns=p["colunas"])


@habilidade("renomear_colunas", "Renomear colunas", ESTRUTURA,
       "Troca nomes de colunas (ex.: vlr_tot → valor_total).",
       [Param("mapa", "mapa", "Nomes (atual=novo)", ajuda="ex.:\nvlr_tot=valor_total\ndt_resp=data_resposta")],
       conhecimento="""
QUANDO USAR: padronizar nomes entre ondas/fornecedores para que o Power BI e as consultas SQL continuem funcionando
mesmo quando o layout da planilha muda.""")
def renomear_colunas(df, p, ctx):
    mapa = {normalizar_nome_coluna(k): normalizar_nome_coluna(v) for k, v in p["mapa"].items()}
    faltando = [k for k in mapa if k not in df.columns]
    if faltando:
        raise ErroHabilidade(f"coluna(s) inexistente(s): {', '.join(faltando)}")
    return df.rename(columns=mapa)


# =============================================================================== privacidade
@habilidade("anonimizar", "Anonimizar dados pessoais", PRIVACIDADE,
       "Protege CPF, e-mail, telefone e nomes: troca por código (hash), mascara ou remove.",
       [Param("colunas", "colunas", "Colunas com dados pessoais"),
        Param("metodo", "escolha", "Método", padrao="hash", opcoes=["hash", "mascarar", "remover"],
              ajuda="hash: código irreversível que ainda permite cruzar bases · mascarar: ***.456.789-** · remover: apaga a coluna"),
        Param("sal", "texto", "Chave secreta do hash (guarde-a!)", obrigatorio=False,
              ajuda="Use sempre a mesma chave para conseguir cruzar bases anonimizadas")],
       conhecimento="""
LGPD: princípio da necessidade — só circule dados pessoais quando indispensável. Para análise, o hash basta:
o mesmo CPF vira sempre o mesmo código (com a mesma chave), então dá para contar clientes e cruzar bases
sem expor ninguém.
CUIDADOS: sem chave secreta, um hash de CPF pode ser revertido por força bruta. Defina uma chave forte e não a
coloque em planilhas.""")
def anonimizar(df, p, ctx):
    sal = p.get("sal") or ""
    if p["metodo"] == "hash" and not sal:
        ctx.aviso("Hash sem chave secreta: recomendável definir uma para proteger CPFs e telefones")
    for col in p["colunas"]:
        if p["metodo"] == "remover":
            df = df.drop(columns=[col])
            continue
        if p["metodo"] == "hash":
            df[col] = df[col].map(lambda v: pd.NA if v is None or (not isinstance(v, str) and pd.isna(v))
                                  else hashlib.sha256(f"{sal}|{_chave(v)}".encode()).hexdigest()[:16])
        else:
            def mascarar(v):
                if v is None or (not isinstance(v, str) and pd.isna(v)):
                    return pd.NA
                s = str(v)
                if "@" in s:
                    nome, dominio = s.split("@", 1)
                    return f"{nome[:1]}***@{dominio}"
                visiveis = max(2, len(s) // 4)
                return "*" * (len(s) - visiveis) + s[-visiveis:]
            df[col] = df[col].map(mascarar)
        ctx.info(f"Coluna protegida ({p['metodo']})", coluna=col)
    return df
