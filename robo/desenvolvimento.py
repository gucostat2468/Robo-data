"""Desenvolvimento da equipe: rodada de estudo de TODOS os funcionários, duas vezes por semana.

O que cada funcionário faz na rodada (tudo real, tudo registrado na memória dele):
  1. refaz a prova técnica do cargo (o mesmo código que o RH usa: caso bom + erro plantado);
  2. revisa os próprios erros da semana;
  3. estuda os handovers abertos do andar (erros da área que ainda não foram resolvidos);
  4. estuda as boas práticas novas do andar (o que o PDCA padronizou).
Antes da rodada, roda a etapa "checar" do PDCA, para estudar já com as boas práticas do dia.

Sendo honesto sobre o limite: os funcionários são código determinístico. "Estudar" não muda o código sozinho; o que a
rodada garante é que (a) ninguém continua trabalhando com prova reprovada sem isso aparecer, (b) todo erro e toda boa
prática da área ficam na memória de cada pessoa e aparecem quando você conversa com ela, e (c) a liderança vê quem está
caindo de desempenho. Quem transforma uma lição em mudança de comportamento é a regra aplicada (no config ou no código).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from robo import memoria, organizacao
from robo.trabalho import Trabalho

DIAS_ENTRE_ESTUDOS = 3.5  # duas vezes por semana


def ultima_rodada(cfg) -> dict | None:
    m = Trabalho(cfg).memorias("estudo_rodada", limite=1)
    return m[0] if m else None


def estudar(cfg, anunciar: bool = True) -> dict:
    from robo import rh
    memoria.checar_pdca(cfg)
    tb = Trabalho(cfg)
    semana = (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds")
    resultado = []
    for p in organizacao.lista(cfg):
        pid, andar = p["id"], p["andar"]
        try:
            agente = p.get("_agente") or {"id": pid, "habilidades": []}
            prova = rh.ficha(agente)["provas"]
        except Exception as e:
            prova = {"aprovado": False, "acertos": 0, "total": 0, "bloqueios": [f"prova não rodou: {type(e).__name__}: {e}"]}
        meus_erros = [e for e in memoria.experiencias(cfg, pid, desde=semana, limite=200) if e["tipo"] == "erro"]
        abertos = memoria.handovers(cfg, andar, abertos=True, limite=10)
        praticas = [b for b in memoria.boas_praticas(cfg, andar, 20) if b["criada_em"] >= semana]
        conteudo = [f"prova técnica {prova['acertos']}/{prova['total']} ({'aprovado' if prova['aprovado'] else 'REPROVADO'})",
                    f"{len(meus_erros)} erro(s) próprio(s) revisado(s)",
                    f"{len(abertos)} handover(s) abertos do andar estudados",
                    f"{len(praticas)} boa(s) prática(s) nova(s) do andar"]
        detalhe = "\n".join([f"Erro: {e['resumo']}" for e in meus_erros[:5]]
                            + [f"Handover {h['id']}: {h['regra']}" for h in abertos[:5]]
                            + [f"Boa prática {b['id']}: {b['pratica']}" for b in praticas[:5]])
        memoria.experiencia(cfg, pid, "treinamento", "Rodada de estudo: " + "; ".join(conteudo), "estudo", "", detalhe, tb)
        if not prova["aprovado"]:
            memoria.experiencia(cfg, pid, "erro", "Reprovado na prova da rodada de estudo", "estudo", "",
                                "; ".join(prova.get("bloqueios") or []), tb)
            for b in (prova.get("bloqueios") or [])[:3]:
                memoria.handover(cfg, b, pid, "canal_helena", p["nome"], tb)
        resultado.append({"id": pid, "nome": p["nome"], "andar": andar, "prova_ok": prova["aprovado"],
                          "erros_revisados": len(meus_erros), "handovers_estudados": len(abertos),
                          "boas_praticas_novas": len(praticas)})
    try:  # quem acertou ensina quem errou na mesma área (conversa registrada e no canal)
        from robo import interacoes
        trocas = interacoes.trocar_experiencias(cfg)
    except Exception:
        trocas = []
    aprovados = sum(r["prova_ok"] for r in resultado)
    tb.lembrar("estudo_rodada", datetime.now().strftime("%Y-%m-%d"),
               f"{len(resultado)} funcionário(s) estudaram; {aprovados} aprovados na prova", "desenvolvimento")
    if anunciar:
        try:
            from robo.canal import Canal
            Canal(cfg).postar("canal_helena", f"Rodada de estudo concluída: {len(resultado)} funcionários refizeram a prova "
                              f"({aprovados} aprovados), revisaram os próprios erros e estudaram os handovers e as boas práticas "
                              "do andar. Tudo ficou na memória de cada um.", "rh", tipo="treinamento")
        except Exception:
            pass
    return {"funcionarios": len(resultado), "aprovados": aprovados, "trocas": len(trocas), "pessoas": resultado}


def rotina(cfg) -> dict | None:
    u = ultima_rodada(cfg)
    if u and datetime.fromisoformat(u["criada_em"]) > datetime.now() - timedelta(days=DIAS_ENTRE_ESTUDOS):
        return None
    return estudar(cfg)
