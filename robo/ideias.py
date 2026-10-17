"""Iara: ideias para o futuro da operação, tiradas da memória de todos os funcionários (nunca inventadas).

Cada ideia traz o DADO que a originou, o primeiro passo e o impacto esperado. Fontes:
  - handovers que mais se repetem (prevenir na origem vale mais que barrar toda semana);
  - handovers parados (abertos há mais de 14 dias sem ninguém aplicar);
  - divergências entre calculadora e banco (confiabilidade em primeiro lugar);
  - pedidos seus que a empresa não conseguiu atender (o que falta construir, pela demanda real);
  - etapas bloqueadas por falta de ferramenta;
  - funcionários abaixo de 90% de acerto;
  - bases que mais reprovam.
"""

from __future__ import annotations

import collections
from datetime import datetime, timedelta

from robo import memoria, organizacao
from robo.trabalho import Trabalho


def gerar(cfg, limite: int = 10) -> list[dict]:
    tb = Trabalho(cfg)
    gente = organizacao.por_id(cfg)
    nome = lambda x: (gente.get(x) or {}).get("nome", x)  # noqa: E731
    ideias = []
    hos = memoria.handovers(cfg, limite=2000)

    for h in [h for h in hos if "divergencia" in memoria._norm(h["erro"]) and h["estado"] != "verificado"][:2]:
        ideias.append({"impacto": 5, "titulo": "Resolver a divergência entre calculadora e banco",
                       "motivo": f"{h['id']}: {h['erro'][:160]} ({h['recorrencias']}x)",
                       "primeiro_passo": "Dora roda a consulta SQL mostrada no cálculo e compara linha a linha com a planilha publicada",
                       "dono": "dba"})
    repetidos = sorted([h for h in hos if h["recorrencias"] >= 3 and h["estado"] != "verificado"], key=lambda h: -h["recorrencias"])
    for h in repetidos[:3]:
        ideias.append({"impacto": 4, "titulo": f"Prevenir na origem: {h['causa'][:80]}",
                       "motivo": f"{h['id']} repetiu {h['recorrencias']} vezes ({h['erro'][:120]})",
                       "primeiro_passo": ("Mandar para quem gera a planilha um modelo de envio com a regra: " + h["regra"][:160])
                       if h.get("na_origem") else h["regra"][:200], "dono": h["responsavel"]})
    sem_causa = [h for h in hos if h["causa"] == memoria.CAUSA_DESCONHECIDA and h["estado"] != "verificado"]
    if sem_causa:
        ideias.append({"impacto": 4, "titulo": f"Ensinar a causa de {len(sem_causa)} tipo(s) de erro que o robô ainda não conhece",
                       "motivo": "; ".join(h["erro"][:90] for h in sem_causa[:3]),
                       "primeiro_passo": "A coordenação escreve causa + regra + como verificar (vira uma categoria nova em "
                                         "robo/memoria.py com teste), e os registros antigos se reclassificam sozinhos",
                       "dono": "coord_engenharia"})
    parado = (datetime.now() - timedelta(days=14)).isoformat(timespec="seconds")
    parados = [h for h in hos if h["estado"] in ("aberto", "reaberto") and str(h["criado_em"]) < parado]
    if parados:
        ideias.append({"impacto": 4, "titulo": f"Destravar {len(parados)} handover(s) parados há mais de 14 dias",
                       "motivo": "; ".join(h["id"] for h in parados[:5]),
                       "primeiro_passo": "Levar para a próxima reunião semanal com prazo e responsável", "dono": "ger_operacoes"})
    with tb.tx() as c:
        sem_resposta = [r["pedido"] for r in c.execute(
            "SELECT pedido FROM solicitacoes WHERE tipo='conversa' AND estado='falhou' ORDER BY criada_em DESC LIMIT 200")]
        bloqueadas = [r["titulo"] for r in c.execute(
            "SELECT titulo FROM etapas WHERE estado='bloqueada' AND ferramenta IS NULL")]
    if sem_resposta:
        top = collections.Counter(p.strip().lower()[:60] for p in sem_resposta).most_common(3)
        ideias.append({"impacto": 4, "titulo": f"Construir o que você pediu e a empresa não soube fazer ({len(sem_resposta)} pedido(s))",
                       "motivo": "Mais pedidos sem resposta: " + "; ".join(f"“{p}” ({n}x)" for p, n in top),
                       "primeiro_passo": "Escolher o mais pedido e transformar em ferramenta ou em conhecimento .md",
                       "dono": "canal_iara"})
    for titulo, n in collections.Counter(bloqueadas).most_common(2):
        ideias.append({"impacto": 3, "titulo": f"Criar a ferramenta que falta: {titulo}",
                       "motivo": f"{n} tarefa(s) terminaram em parte porque esta etapa não tem ferramenta",
                       "primeiro_passo": "Diego (dev) estima e implementa com teste automatizado", "dono": "dev_pleno"})
    fracos = [d for d in memoria.desempenho(cfg, 30) if d["taxa"] is not None and d["taxa"] < 90 and d["eventos"] >= 5]
    if fracos:
        ideias.append({"impacto": 3, "titulo": f"Treinamento focado para {len(fracos)} pessoa(s) abaixo de 90% de acerto",
                       "motivo": ", ".join(f"{d['nome']} {d['taxa']}%" for d in fracos[:6]),
                       "primeiro_passo": "Cada líder revê os erros listados no dossiê da pessoa e define uma regra nova",
                       "dono": "canal_helena"})
    from robo import historico
    ruins = collections.Counter(memoria._base(h.get("arquivo", "")) for h in historico.ler(cfg.logs, 3000)
                                if h.get("status") == "reprovado")
    for base, n in ruins.most_common(1):
        if n >= 3:
            ideias.append({"impacto": 3, "titulo": f"A base “{base}” reprova muito ({n} vezes)",
                           "motivo": f"{n} carga(s) reprovada(s) no histórico",
                           "primeiro_passo": "Abrir a lista de erros dessa base e combinar um padrão de envio com a origem",
                           "dono": "coord_engenharia"})
    if not ideias:
        ideias.append({"impacto": 1, "titulo": "Nada urgente na memória agora",
                       "motivo": "Sem erro repetido, sem handover parado, sem pedido sem resposta",
                       "primeiro_passo": "Seguir o PDCA e as rodadas de estudo", "dono": "canal_iara"})
    for i in ideias:
        i["dono_nome"] = nome(i["dono"])
    return sorted(ideias, key=lambda i: -i["impacto"])[:limite]
