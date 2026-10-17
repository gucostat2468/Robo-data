"""Contratação automática: o prédio contrata sozinho quando os dados mostram uma necessidade real.

Como funciona (tudo offline, sem IA externa):
  1. Depois de cada publicação, a Helena (RH) olha cada coluna publicada e reconhece o que ela parece ser
     (e-mail, telefone, CPF/CNPJ, CEP) — pelo nome da coluna OU pelo formato dos valores.
  2. Antes de contratar, ela TESTA numa cópia: a habilidade certa mudaria alguma coisa ou acharia valor inválido?
     Se nada mudaria, não há trabalho — ninguém é contratado à toa.
  3. O contratado entra como ESTAGIÁRIO, em modo observação: roda numa cópia e só relata o que faria.
     Nada nos dados publicados muda até você promover a pessoa (tela Agentes).
  4. Quem contrata é a LIDERANÇA do andar (coordenador ou gerente), que conhece o trabalho do dia a dia.
     Autonomia dos líderes: só contratam ESTAGIÁRIOS. Júnior para cima é decisão sua.
  5. Toda contratação passa no processo seletivo técnico e é anunciada no canal #rh.
  6. Período de experiência: 3 meses (90 dias). No fim, o líder avalia com dados:
       - observou arquivos suficientes e nenhuma execução falhou → recomenda efetivar como Júnior (você decide);
       - não teve trabalho ou falhou → é desligado (sai sem deixar rastro nos dados, porque nunca alterou nada).

Limites (config.yaml → contratacao_automatica): habilitada, maximo (padrão 12), observacoes_minimas (padrão 5),
dias_experiencia (padrão 90).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from robo.limpeza import normalizar_nome_coluna

log = logging.getLogger("robo")

PADRAO = {"habilitada": True, "maximo": 12, "observacoes_minimas": 5, "dias_experiencia": 90}
# líder que contrata em cada andar (coordenador; no 5º andar, o gerente de TI)
LIDER_DO_ANDAR = {1: "coord_engenharia", 2: "coord_analise", 3: "coord_excel", 4: "canal_helena", 5: "coord_devops"}

# o que reconhecer → que habilidade resolve → que cargo contratar
DEMANDAS = [
    {"tipo": "email", "habilidade": "validar_email", "nome_col": re.compile(r"(^|_)(e_?mail|email)(_|$)"),
     "valor": re.compile(r"^\s*[^@\s]+@[^@\s]+\s*$"), "cargo": "Estagiário de Qualidade de Dados — E-mails", "cor": "#0891B2"},
    {"tipo": "telefone", "habilidade": "normalizar_telefone", "nome_col": re.compile(r"(^|_)(telefone|fone|celular|whatsapp|tel)(_|$)"),
     "valor": re.compile(r"^\s*(\+55\s?)?\(\d{2}\)\s?9?\d{4}[-\s]?\d{4}\s*$"),  # só com DDD entre parênteses: (11) 98765-4321
     "cargo": "Estagiário de Qualidade de Dados — Telefones", "cor": "#0D9488"},
    {"tipo": "documento", "habilidade": "normalizar_documento", "nome_col": re.compile(r"(^|_)(cpf|cnpj|documento|doc)(_|$)"),
     "valor": re.compile(r"^\s*\d{3}\.\d{3}\.\d{3}-\d{2}\s*$|^\s*\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\s*$"),  # só formatado
     "cargo": "Estagiário de Qualidade de Dados — CPF/CNPJ", "cor": "#4F46E5"},
    {"tipo": "cep", "habilidade": "normalizar_cep", "nome_col": re.compile(r"(^|_)(cep|codigo_postal)(_|$)"),
     "valor": re.compile(r"^\s*\d{5}-\d{3}\s*$"), "cargo": "Estagiário de Qualidade de Dados — CEP", "cor": "#9333EA"},
]

NOMES = ["Alice", "Benício", "Cecília", "Davi Lucca", "Elisa", "Felipe", "Giovana", "Heitor", "Isis", "Joaquim", "Lívia",
         "Miguel", "Nicole", "Otávio", "Pietra", "Raul", "Sofia", "Tomás", "Valentina", "Yuri"]
AUDITORIA = {"_arquivo_origem", "_processado_em", "_aba_origem", "_linha_origem"}


def _config(cfg) -> dict:
    return {**PADRAO, **(cfg.dados.get("contratacao_automatica") or {})}


def _arquivo_estado(cfg) -> Path:
    return Path(cfg.logs) / "contratacao.json"


def _estado(cfg) -> dict:
    try:
        return json.loads(_arquivo_estado(cfg).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _salvar_estado(cfg, e: dict) -> None:
    arq = _arquivo_estado(cfg)
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(arq)


def reconhecer(serie: pd.Series, nome: str) -> dict | None:
    """Que demanda esta coluna representa (pelo nome ou por ≥60% dos valores num formato inequívoco).

    Datas e números nunca são reconhecidos pelo valor: "2025-12-01" ou 11987654321 são ambíguos demais.
    """
    if pd.api.types.is_datetime64_any_dtype(serie) or pd.api.types.is_bool_dtype(serie):
        return None
    if pd.api.types.is_numeric_dtype(serie):
        return next((d for d in DEMANDAS if d["nome_col"].search(nome)), None)
    valores = serie.dropna().astype(str).str.strip()
    valores = valores[valores != ""].head(300)
    for d in DEMANDAS:
        if d["nome_col"].search(nome):
            return d
    if len(valores) >= 5:
        for d in DEMANDAS:
            if valores.str.match(d["valor"]).mean() >= 0.6:
                return d
    return None


def parametros(habilidade: str, coluna: str) -> dict:
    """Parâmetros seguros: valor inválido é MANTIDO e registrado (nunca reprova o arquivo nem apaga dado)."""
    from robo.habilidades import REGISTRO
    p = {"colunas": [coluna]}
    if any(x.nome == "invalidos" for x in REGISTRO[habilidade].parametros):
        p["invalidos"] = "aviso"
    return p


def precisa(df: pd.DataFrame, coluna: str, habilidade: str) -> str:
    """Testa a habilidade numa cópia. Devolve a evidência ("alteraria 3 célula(s)…") ou "" se não há trabalho."""
    from robo.agentes import _diferencas
    from robo.habilidades import executar_habilidade
    from robo.relatorio import Relatorio
    rel = Relatorio("teste_rh")
    depois = executar_habilidade(df[[coluna]].copy(), {"habilidade": habilidade, "parametros": parametros(habilidade, coluna)},
                                 rel, "teste", "teste", "RH")
    if any(o.nivel == "ERRO" and ("Configuração inválida" in o.mensagem or "Falha ao executar" in o.mensagem)
           for o in rel.ocorrencias):
        return ""  # a habilidade não se aplica a esta coluna: não há contratação
    mudanca = _diferencas(df[[coluna]], depois)
    preenchidos = int(df[coluna].notna().sum()) or 1
    qtd_invalidos = sum(int(o.quantidade or 0) for o in rel.ocorrencias if o.nivel in ("AVISO", "ERRO"))
    if coluna in depois.columns and len(depois) == len(df):  # valores que a habilidade apagaria também contam
        qtd_invalidos += int((df[coluna].notna().values & depois[coluna].isna().values).sum())
    if qtd_invalidos / preenchidos > 0.5:
        return ""  # mais da metade "inválida" = a coluna não é deste tipo; contratar seria um erro
    invalidos = [o.mensagem for o in rel.ocorrencias if o.nivel in ("AVISO", "ERRO")]
    partes = ([mudanca] if mudanca != "nenhuma alteração" else []) + invalidos[:1]
    return "; ".join(partes)


def _ja_coberto(equipe, habilidade: str, coluna: str, padrao: str) -> bool:
    for a in equipe.personalizados:
        for s in a.get("habilidades") or []:
            cols = (s.get("parametros") or {}).get("colunas") or []
            cols = [normalizar_nome_coluna(c) for c in (cols if isinstance(cols, list) else [cols])]
            if s.get("habilidade") == habilidade and coluna in cols and (padrao in a.get("aplicar_em", []) or "*" in a.get("aplicar_em", [])):
                return True
    return False


def avaliar(cfg, arquivo: str, regra: dict | None, tabelas: dict) -> list[dict]:
    """Chamado depois de cada publicação. Contrata estagiários quando há demanda comprovada. Nunca levanta exceção."""
    c = _config(cfg)
    if not c.get("habilitada", True) or not tabelas:
        return []
    from robo.agentes import ErroAgente
    from robo.analise import chave_base
    from robo.pipeline import obter_equipe
    equipe = obter_equipe(cfg)
    automaticos = [a for a in equipe.personalizados if a.get("contratado_por") == "automatico"]
    base = chave_base(arquivo, regra or {})
    padrao = f"{base}*"
    contratados = []
    for tabela, df in tabelas.items():
        for col in df.columns:
            if col in AUDITORIA or len(automaticos) + len(contratados) >= int(c["maximo"]):
                continue
            d = reconhecer(df[col], col)
            if not d or _ja_coberto(equipe, d["habilidade"], col, padrao):
                continue
            evidencia = precisa(df, col, d["habilidade"])
            if not evidencia:
                continue
            lider = LIDER_DO_ANDAR[1]
            ocupados = {a["nome"] for a in equipe.personalizados}
            nome = next((n for n in NOMES if n not in ocupados), f"Estagiário {len(ocupados) + 1}")
            completo = re.sub(r"[^a-z0-9_]", "_", f"auto_{d['tipo']}_{base}_{col}".lower())
            # nomes longos são cortados; o final com 6 caracteres do resumo evita que dois cortes fiquem iguais
            agente_id = completo if len(completo) <= 40 else f"{completo[:33].rstrip('_')}_{hashlib.sha1(completo.encode()).hexdigest()[:6]}"
            dados = {"id": agente_id, "nome": nome, "papel": d["cargo"].split(" — ")[-1], "cargo": d["cargo"],
                     "nivel": "estagiario", "area": "Qualidade de Dados", "mentor": "limpeza", "andar": 1,
                     "contratado_por": "automatico", "contratante": lider, "contratado_em": date.today().isoformat(),
                     "fim_experiencia": (date.today() + timedelta(days=int(c["dias_experiencia"]))).isoformat(), "cor": d["cor"], "posicao": "limpeza", "ordem": 60, "ativo": True,
                     "descricao": f"Contratado(a) pela liderança do 1º andar porque a coluna '{col}' da base '{base}' "
                                  f"precisa de tratamento: {evidencia}.",
                     "aplicar_em": [padrao],
                     "habilidades": [{"habilidade": d["habilidade"], "parametros": parametros(d["habilidade"], col), "opcional": True}],
                     "manual": f"# Manual — {d['cargo']}\n\n## Por que fui contratado\nNa base **{base}**, a coluna "
                               f"`{col}` mostrou: {evidencia}.\n\n## O que faço\nRodo a habilidade `{d['habilidade']}` "
                               f"numa cópia e relato o que mudaria. Como estagiário, **não altero** os dados publicados.\n\n"
                               f"## Período de experiência\n3 meses (até {(date.today() + timedelta(days=int(c['dias_experiencia']))).strftime('%d/%m/%Y')}). "
                               f"No fim, a liderança avalia: com trabalho e sem falhas, recomenda efetivar como Júnior "
                               f"(o dono decide na tela Agentes); sem trabalho ou com falhas, a pessoa é desligada."}
            try:
                equipe.salvar(dados)
            except ErroAgente as e:
                log.info("Contratação automática não aprovada (%s): %s", agente_id, e)
                continue
            contratados.append(dados)
            _anunciar(cfg, f"Contratei {nome} como {d['cargo']} (1º andar, em observação, experiência de 3 meses). Motivo: "
                           f"na base {base}, a coluna '{col}' {evidencia}. Aprovado(a) no processo seletivo técnico. "
                           f"Nada muda nos dados até você promover na tela Agentes.", autor=lider, canal="engenharia")
    return contratados


def registrar_observacoes(cfg, rel) -> list[str]:
    """Conta os arquivos observados por cada estagiário (e falhas de execução) para a avaliação de experiência."""
    e = _estado(cfg)
    contagem = e.setdefault("observacoes", {})
    falhas = e.setdefault("falhas", {})
    from robo.pipeline import obter_equipe
    vistos = []
    for a in obter_equipe(cfg).personalizados:
        if a.get("nivel") != "estagiario":
            continue
        obs = [o for o in rel.ocorrencias if f"Estagiário {a['nome']} em observação" in o.mensagem]
        if obs:
            contagem[a["id"]] = contagem.get(a["id"], 0) + 1
            if any("Falha ao executar" in x for o in obs for x in (o.exemplos or [])):
                falhas[a["id"]] = falhas.get(a["id"], 0) + 1
            vistos.append(a["id"])
    _salvar_estado(cfg, e)
    return vistos


def avaliar_experiencias(cfg, hoje: date | None = None) -> list[dict]:
    """No fim dos 3 meses, o líder que contratou avalia cada estagiário com base em dados (observações e falhas)."""
    hoje = hoje or date.today()
    c = _config(cfg)
    e = _estado(cfg)
    avaliados = set(e.setdefault("avaliados", []))
    from robo.pipeline import obter_equipe
    equipe = obter_equipe(cfg)
    decisoes = []
    for a in list(equipe.personalizados):
        fim = a.get("fim_experiencia")
        if a.get("nivel") != "estagiario" or not fim or a["id"] in avaliados or date.fromisoformat(str(fim)) > hoje:
            continue
        obs = int(e.get("observacoes", {}).get(a["id"], 0))
        falhou = int(e.get("falhas", {}).get(a["id"], 0))
        lider = a.get("contratante") or LIDER_DO_ANDAR.get(int(a.get("andar") or 1), "canal_helena")
        if obs >= int(c["observacoes_minimas"]) and not falhou:
            decisao = "efetivar"
            _anunciar(cfg, f"Fim da experiência de {a['nome']} ({a.get('cargo') or a.get('papel')}): {obs} arquivo(s) observados "
                           f"e nenhuma falha. Recomendo efetivar como Júnior — aí as correções passam a valer. Para aprovar: "
                           f"Agentes → {a['nome']} → nível Júnior → Salvar.", autor=lider)
        else:
            decisao = "desligar"
            motivo = f"{falhou} falha(s) de execução" if falhou else f"só {obs} arquivo(s) observados (mínimo {c['observacoes_minimas']})"
            try:
                equipe.excluir(a["id"])
            except Exception:
                log.exception("Não consegui desligar %s", a["id"])
                continue
            _anunciar(cfg, f"Fim da experiência de {a['nome']}: {motivo}. Desligado(a) — como estagiário(a), nunca alterou "
                           f"nenhum dado, então nada precisa ser desfeito.", autor=lider)
        avaliados.add(a["id"])
        decisoes.append({"id": a["id"], "nome": a["nome"], "decisao": decisao, "observacoes": obs, "falhas": falhou})
    e["avaliados"] = sorted(avaliados)
    _salvar_estado(cfg, e)
    return decisoes


def _anunciar(cfg, texto: str, autor: str = "canal_helena", canal: str = "rh") -> None:
    try:
        from robo.canal import Canal
        c = Canal(cfg)
        c.postar(autor, texto, "rh", "contratacao")
        if canal != "rh":
            c.postar(autor, texto, canal, "contratacao")
    except Exception:
        log.debug("Não consegui anunciar no canal", exc_info=True)


def contratar_manual(cfg, dados: dict) -> dict:
    """Contratação feita pelo dono no painel: qualquer andar (o prédio cresce se o andar não existir).
    Estagiário contratado pelo dono também cumpre 3 meses de experiência."""
    from robo.pipeline import obter_equipe
    extra = {}
    if dados.get("nivel") == "estagiario" and not dados.get("fim_experiencia"):
        dias = int(_config(cfg)["dias_experiencia"])
        extra = {"contratado_em": date.today().isoformat(), "fim_experiencia": (date.today() + timedelta(days=dias)).isoformat()}
    a = obter_equipe(cfg).salvar({**dados, **extra, "contratado_por": "dono"})
    _anunciar(cfg, f"Boas-vindas a {a['nome']} ({a.get('cargo') or a.get('papel')}, "
                   f"{a.get('nivel')}) no {a.get('andar', 1)}º andar — aprovado(a) no processo seletivo técnico.")
    return a


def resumo(cfg) -> dict:
    return {"config": _config(cfg), **_estado(cfg)}

