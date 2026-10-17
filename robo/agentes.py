"""Equipe de agentes: quem faz o quê, em que ordem e com quais skills.

Cada agente é um arquivo YAML em agentes/ (fácil de ler, versionar e copiar):

    id: tina
    nome: Tina
    papel: Contatos
    descricao: Padroniza telefones e e-mails das bases de pesquisa.
    cor: "#F97316"
    posicao: limpeza        # trabalha logo depois de: limpeza | validacao | modelagem
    ordem: 10               # desempate entre agentes da mesma posição (menor primeiro)
    ativo: true
    aplicar_em: ["nps_*"]   # só nestes arquivos ("*" = todos)
    skills:
      - skill: normalizar_telefone
        parametros: {colunas: [telefone], formato: formatado}

Os 7 agentes nativos sempre existem. Três deles (limpeza, validacao, modelagem) aceitam skills extras,
gravadas em agentes/<id>.yaml com a mesma estrutura.

Ordem no processamento de cada tabela:
  limpeza nativa → skills da Limpeza → agentes "limpeza"
  validação nativa → skills da Auditoria → agentes "validacao"
  skills da Modelagem → agentes "modelagem" → modelagem nativa (fato/dimensões)
"""

from __future__ import annotations

import fnmatch
import logging
import re
from copy import deepcopy
from pathlib import Path

import pandas as pd
import yaml

from robo import skills as catalogo_skills

log = logging.getLogger("robo")

POSICOES = ["limpeza", "validacao", "modelagem"]
RE_ID = re.compile(r"^[a-z][a-z0-9_]{1,39}$")

NATIVOS = [
    {"id": "recepcao", "nome": "Rita", "papel": "Recepção", "cor": "#F59E0B", "aceita_skills": False,
     "descricao": "Vigia a pasta Bases-Limpeza. Espera o OneDrive terminar de sincronizar e o arquivo ser fechado no "
                  "Excel antes de passar adiante."},
    {"id": "leitura", "nome": "Leo", "papel": "Leitura (Extração)", "cor": "#3B82F6", "aceita_skills": False,
     "descricao": "Abre a planilha, descobre codificação, separador e onde está o cabeçalho de verdade, e detecta erros "
                  "de fórmula (#REF!, #N/D)."},
    {"id": "limpeza", "nome": "Lia", "papel": "Limpeza", "cor": "#14B8A6", "aceita_skills": True,
     "descricao": "Padroniza nomes de colunas, tira espaços, converte R$ 1.234,56 e datas, remove linhas vazias, de Total "
                  "e duplicadas. Recebe skills de padronização."},
    {"id": "validacao", "nome": "Otto", "papel": "Auditoria (Validação)", "cor": "#EF4444", "aceita_skills": True,
     "descricao": "Confere as regras: colunas obrigatórias, chaves únicas, faixas de valores. Qualquer erro barra o "
                  "arquivo inteiro. Recebe skills de qualidade."},
    {"id": "modelagem", "nome": "Ana", "papel": "Modelagem", "cor": "#8B5CF6", "aceita_skills": True,
     "descricao": "Prepara para o Power BI: colunas calculadas, classificações, modelo estrela (fato e dimensões) e "
                  "tabela calendário."},
    {"id": "banco", "nome": "Beto", "papel": "Banco de dados (ELT)", "cor": "#0EA5E9", "aceita_skills": False,
     "descricao": "Carrega no PostgreSQL em camadas — bruto, tratado e analítico — numa única transação."},
    {"id": "publicacao", "nome": "Duda", "papel": "Publicação e arquivo", "cor": "#22C55E", "aceita_skills": False,
     "descricao": "Grava a planilha final em Bases-Tratadas e guarda o original — ou manda para Bases-Erros com o "
                  "relatório do que corrigir."},
]
IDS_NATIVOS = {a["id"] for a in NATIVOS}


class ErroAgente(Exception):
    pass


def _padrao_agente(dados: dict) -> dict:
    a = {"id": "", "nome": "", "papel": "", "descricao": "", "cor": "#64748B", "posicao": "limpeza", "ordem": 50,
         "ativo": True, "aplicar_em": ["*"], "skills": [], "nivel": "pleno", "area": "", "cargo": "", "mentor": ""}
    a.update({k: v for k, v in (dados or {}).items() if v is not None})
    if isinstance(a["aplicar_em"], str):
        a["aplicar_em"] = [p.strip() for p in a["aplicar_em"].split(",") if p.strip()] or ["*"]
    a["skills"] = [s for s in (a.get("skills") or []) if isinstance(s, dict)]
    for s in a["skills"]:
        s.setdefault("ativo", True)
        s.setdefault("parametros", {})
    return a


def validar_agente(a: dict, nativo: bool = False) -> list[str]:
    problemas = []
    if not nativo:
        if not RE_ID.match(str(a.get("id", ""))):
            problemas.append("id inválido (use letras minúsculas, números e _; comece com letra)")
        if a.get("id") in IDS_NATIVOS:
            problemas.append("id reservado para um agente nativo")
        if not str(a.get("nome", "")).strip():
            problemas.append("informe o nome do agente")
        if a.get("posicao") not in POSICOES:
            problemas.append(f"posição inválida (use: {', '.join(POSICOES)})")
        if not re.match(r"^#[0-9a-fA-F]{6}$", str(a.get("cor", ""))):
            problemas.append("cor inválida (use o formato #RRGGBB)")
    from robo import rh
    nivel = a.get("nivel") or "pleno"
    if not nativo and nivel not in rh.NIVEIS:
        problemas.append(f"nível inválido (use: {', '.join(rh.NIVEIS)})")
    for i, s in enumerate(a.get("skills") or [], 1):
        sk = catalogo_skills.REGISTRO.get(s.get("skill", ""))
        if sk is None:
            problemas.append(f"skill {i}: '{s.get('skill')}' não existe no catálogo")
            continue
        try:
            catalogo_skills.preparar_parametros(sk, s.get("parametros") or {})
        except catalogo_skills.ErroSkill as e:
            problemas.append(f"skill {i} ({sk.nome}): {e}")
            continue
        if s.get("ativo", True) and not nativo and nivel in rh.NIVEIS:
            risco = rh.risco_de(sk.id, s.get("parametros"))
            if not rh.nivel_permite(nivel, risco):
                problemas.append(f"skill {i} ({sk.nome}) tem risco {rh.NOME_RISCO[risco]} e o nível "
                                 f"{rh.NOME_NIVEL[nivel]} não permite: promova o agente ou passe a tarefa a um sênior")
    return problemas


def _diferencas(antes: pd.DataFrame, depois: pd.DataFrame) -> str:
    partes = []
    if len(depois) != len(antes):
        partes.append(f"{len(antes)} → {len(depois)} linhas")
    novas = [c for c in depois.columns if c not in antes.columns]
    saidas = [c for c in antes.columns if c not in depois.columns]
    if novas:
        partes.append(f"criaria {', '.join(novas)}")
    if saidas:
        partes.append(f"removeria {', '.join(saidas)}")
    comuns = [c for c in antes.columns if c in depois.columns]
    idx = antes.index.intersection(depois.index)
    alteradas = 0
    for c in comuns:
        a, b = antes.loc[idx, c].astype(object), depois.loc[idx, c].astype(object)
        alteradas += int((~((a == b) | (a.isna() & b.isna()))).sum())
    if alteradas:
        partes.append(f"alteraria {alteradas} célula(s)")
    return "; ".join(partes) or "nenhuma alteração"


class Equipe:
    def __init__(self, pasta_agentes: Path, pasta_skills: Path | None = None):
        self.pasta = Path(pasta_agentes)
        self.pasta_skills = Path(pasta_skills) if pasta_skills else None
        self.personalizados: list[dict] = []
        self.skills_nativos: dict[str, list] = {p: [] for p in POSICOES}
        self.problemas: dict[str, list[str]] = {}
        self.carregar()

    # ------------------------------------------------------------ leitura
    def carregar(self):
        if self.pasta_skills:
            catalogo_skills.carregar_personalizadas(self.pasta_skills)
        self.personalizados, self.problemas = [], {}
        self.skills_nativos = {p: [] for p in POSICOES}
        if not self.pasta.exists():
            return
        for arq in sorted(self.pasta.glob("*.yaml")):
            try:
                dados = yaml.safe_load(arq.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError as e:
                self.problemas[arq.stem] = [f"arquivo YAML inválido: {e}"]
                continue
            if arq.stem in IDS_NATIVOS:
                if arq.stem in POSICOES:
                    a = _padrao_agente({"id": arq.stem, "skills": dados.get("skills")})
                    self.skills_nativos[arq.stem] = a["skills"]
                    if p := validar_agente(a, nativo=True):
                        self.problemas[arq.stem] = p
                continue
            a = _padrao_agente({**dados, "id": dados.get("id") or arq.stem})
            p = validar_agente(a)
            if not p and a.get("ativo", True):
                from robo import rh
                selecao = rh.processo_seletivo(a)
                if not selecao["aprovado"]:
                    p = ["não aprovado no processo seletivo técnico"] + selecao["bloqueios"]
            if p:
                self.problemas[a["id"]] = p
            self.personalizados.append(a)
        self.personalizados.sort(key=lambda a: (POSICOES.index(a["posicao"]) if a["posicao"] in POSICOES else 9,
                                                a.get("ordem", 50), a["nome"]))

    def lista(self) -> list[dict]:
        """Todos os agentes, na ordem em que trabalham (usada pelo painel e pelo escritório 3D)."""
        from robo import rh
        resultado = []
        for n in NATIVOS:
            item = {**deepcopy(n), "nativo": True, "ativo": True, "aplicar_em": ["*"],
                    "posicao": n["id"], "skills": deepcopy(self.skills_nativos.get(n["id"], [])),
                    "problemas": self.problemas.get(n["id"], [])}
            extras = [{**deepcopy(a), "nativo": False, "aceita_skills": True, "problemas": self.problemas.get(a["id"], [])}
                      for a in self.personalizados if a["posicao"] == n["id"]]
            item["ficha"] = rh.ficha(item)
            for x in extras:
                x["ficha"] = rh.ficha(x)
            if n["id"] == "modelagem":
                resultado += extras + [item]  # agentes "modelagem" trabalham ANTES da modelagem nativa
            else:
                resultado += [item] + extras
        return resultado

    # ------------------------------------------------------------ execução
    def executar(self, posicao: str, df: pd.DataFrame, rel, tabela: str, arquivo: str, ao_etapa=None) -> pd.DataFrame:
        nativo = next(n for n in NATIVOS if n["id"] == posicao)
        df = self._executar_skills(df, self.skills_nativos.get(posicao, []), rel, tabela, arquivo,
                                   f"{nativo['nome']} ({nativo['papel']})")
        for a in self.personalizados:
            if a["posicao"] != posicao or not a.get("ativo", True):
                continue
            if not any(fnmatch.fnmatch(arquivo.lower(), str(p).lower()) for p in a["aplicar_em"]):
                continue
            if self.problemas.get(a["id"]):
                rel.erro(f"Agente {a['nome']} está com configuração inválida: {'; '.join(self.problemas[a['id']])}",
                         tabela=tabela)
                continue
            if ao_etapa:
                try:
                    ao_etapa(f"agente:{a['id']}", arquivo)
                except Exception:
                    pass
            if a.get("nivel") == "estagiario":
                # MODO OBSERVAÇÃO: o estagiário trabalha numa cópia; o dado publicado não muda
                from robo.relatorio import Relatorio
                rel_obs = Relatorio(arquivo)
                copia = self._executar_skills(df.copy(), a["skills"], rel_obs, tabela, arquivo, f"{a['nome']} (estagiário)")
                achados = [f"{o.nivel}: {o.mensagem}" for o in rel_obs.ocorrencias if o.nivel != "INFO"]
                rel.info(f"Estagiário {a['nome']} em observação (nada foi alterado): {_diferencas(df, copia)}"
                         + (f"; encontraria {len(achados)} ocorrência(s)" if achados else ""), tabela=tabela, exemplos=achados)
                continue
            antes = len(df)
            df = self._executar_skills(df, a["skills"], rel, tabela, arquivo, f"{a['nome']} ({a['papel'] or 'agente'})")
            rel.info(f"Agente {a['nome']} concluiu {len([s for s in a['skills'] if s.get('ativo', True)])} skill(s): "
                     f"{antes} → {len(df)} linhas", tabela=tabela)
        return df

    def _executar_skills(self, df, lista, rel, tabela, arquivo, agente):
        for config in lista:
            if not config.get("ativo", True):
                continue
            filtro = config.get("aplicar_em")
            if filtro and not any(fnmatch.fnmatch(arquivo.lower(), str(p).lower()) for p in
                                  ([filtro] if isinstance(filtro, str) else filtro)):
                continue
            df = catalogo_skills.executar_skill(df, config, rel, tabela, arquivo, agente)
        return df

    # ------------------------------------------------------------ gravação (painel)
    def salvar(self, dados: dict) -> dict:
        agente_id = str(dados.get("id", "")).strip()
        nativo = agente_id in IDS_NATIVOS
        if nativo and agente_id not in POSICOES:
            raise ErroAgente("Este agente nativo não usa skills de dados.")
        a = _padrao_agente({**dados, "id": agente_id})
        problemas = validar_agente(a, nativo=nativo)
        if problemas:
            raise ErroAgente("; ".join(problemas))
        from robo import rh
        selecao = rh.processo_seletivo({**a, "nivel": a.get("nivel") if not nativo else "especialista"})
        if not selecao["aprovado"]:
            raise ErroAgente("Não aprovado no processo seletivo técnico: " + "; ".join(selecao["bloqueios"]))
        self.pasta.mkdir(parents=True, exist_ok=True)
        if nativo:
            conteudo = {"skills": a["skills"]}
        else:
            conteudo = {k: a[k] for k in ("id", "nome", "papel", "cargo", "nivel", "area", "mentor", "descricao", "cor",
                                          "posicao", "ordem", "ativo", "aplicar_em", "skills")}
        texto = ("# Agente do Robô de Planilhas — editado pelo painel (pode editar à mão também)\n"
                 + yaml.safe_dump(conteudo, allow_unicode=True, sort_keys=False, default_flow_style=False))
        (self.pasta / f"{agente_id}.yaml").write_text(texto, encoding="utf-8")
        self.carregar()
        return a

    def excluir(self, agente_id: str):
        if agente_id in IDS_NATIVOS:
            raise ErroAgente("Agentes nativos não podem ser excluídos (você pode remover as skills deles).")
        arq = self.pasta / f"{agente_id}.yaml"
        if not arq.exists():
            raise ErroAgente("Agente não encontrado.")
        lixeira = self.pasta / "_excluidos"
        lixeira.mkdir(exist_ok=True)
        arq.replace(lixeira / arq.name)
        self.carregar()
