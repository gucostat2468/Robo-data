"""Modo demonstração: a empresa inteira funcionando na sua frente, sem tocar na sua produção.

  python -m robo demo            (ou o arquivo "Demonstracao.bat")

O que faz (tudo real, nada simulado):
  1. cria a pasta demonstracao/ no projeto, com OneDrive/Bases-Limpeza, logs e config.yaml PRÓPRIOS (a sua pasta do
     OneDrive e o seu histórico não são usados);
  2. coloca na entrada planilhas sujas de 6 áreas (educação/NPS, varejo, RH, financeiro, marketing, logística),
     geradas pelo mesmo gerador do laboratório — título, linha vazia, R$ em texto, datas em texto, duplicata e Total —
     e uma planilha com DEFEITO de verdade (células #REF! e #DIV/0!), que o robô precisa barrar: ela vai para
     Reprovados, vira handover da área e a coordenação levanta a mão na reunião;
  3. pede uma senha para o painel na primeira vez (a TI não aceita painel aberto sem senha);
  4. se o seu config.yaml já usa PostgreSQL, a demonstração usa o MESMO servidor, num banco separado
     (robo_demonstracao) — os seus dados não são tocados;
  5. laboratório a cada 3 minutos (na produção são 10), para você ver o treino acontecendo;
  6. abre o painel: o robô processa as planilhas, os funcionários trabalham, você conversa, abre reunião, cria
     lições, aprova tarefas. Para recomeçar do zero: python -m robo demo --recomecar.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from robo.config import RAIZ_PROJETO

PASTA = RAIZ_PROJETO / "demonstracao"
SEMENTES = {"educacao_nps": 101, "varejo": 202, "rh": 303, "financeiro": 404, "marketing": 505, "logistica": 606}
NOMES = {"educacao_nps": "nps_pesquisa_alunos", "varejo": "vendas_lojas", "rh": "clima_colaboradores",
         "financeiro": "contas_a_receber", "marketing": "campanhas_digitais", "logistica": "entregas_transportadora"}


def preparar(pasta: Path = PASTA, recomecar: bool = False, porta: int = 8799) -> Path:
    """Monta (ou reaproveita) a empresa de demonstração. Devolve o caminho do config.yaml dela."""
    from robo import laboratorio
    if recomecar and pasta.exists():
        shutil.rmtree(pasta)
    entrada = pasta / "OneDrive" / "Bases-Limpeza"
    entrada.mkdir(parents=True, exist_ok=True)
    (pasta / "OneDrive" / "Bases-Tratadas").mkdir(exist_ok=True)
    caminho = pasta / "config.yaml"
    if not caminho.exists():
        shutil.copy(RAIZ_PROJETO / "config.exemplo.yaml", caminho)
        dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
        dados["pastas"] = {"entrada": str(entrada), "logs": str(pasta / "logs"), "agentes": str(RAIZ_PROJETO / "agentes"),
                           "habilidades": str(pasta / "habilidades")}
        dados.setdefault("painel", {}).update({"porta": porta, "ligar_robo_ao_abrir": True, "notificacoes": False})
        dados["laboratorio"] = {"intervalo_minutos": 3}
        dados["banco"] = _banco_da_producao() or {**(dados.get("banco") or {}), "habilitado": False}
        caminho.write_text("# Config da DEMONSTRAÇÃO (gerado por python -m robo demo). Não é o da produção.\n"
                           + yaml.safe_dump(dados, allow_unicode=True, sort_keys=False), encoding="utf-8")
        for area, semente in SEMENTES.items():
            laboratorio.escrever_sujo(laboratorio.gerar(area, semente), entrada / f"{NOMES[area]}.xlsx")
        _com_defeito(entrada / "pedidos_com_formula_quebrada.xlsx")
    return caminho


def _com_defeito(caminho: Path) -> None:
    """Planilha que chega quebrada (fórmula com referência apagada e divisão por zero): tem que ser reprovada."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["Pedido", "Cliente", "Valor", "Desconto", "Margem"])
    for i in range(1, 41):
        ws.append([i, f"Cliente {i:02d}", 100 + i * 7.5, 0.05, "#REF!" if i % 9 == 0 else ("#DIV/0!" if i % 13 == 0 else 0.3)])
    wb.save(caminho)


def _banco_da_producao() -> dict | None:
    prod = RAIZ_PROJETO / "config.yaml"
    if not prod.exists():
        return None
    try:
        b = (yaml.safe_load(prod.read_text(encoding="utf-8")) or {}).get("banco") or {}
    except yaml.YAMLError:
        return None
    if not b.get("habilitado"):
        return None
    return {**b, "banco": "robo_demonstracao"}


def tem_senha(caminho: Path) -> bool:
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    return bool((dados.get("painel") or {}).get("senha_hash"))
