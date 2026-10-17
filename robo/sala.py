"""Sala de reunião (estilo Teams): o dono conversa com a liderança de um andar, todos na tela ao mesmo tempo.

Ao abrir, cada participante fala a sua parte, com dados do momento:
  diretor(a) — o scorecard da área (farol e o que está vermelho);
  head       — a última auditoria por amostragem;
  gerente/coordenação — o que deu certo, o que deu errado e o plano de ação;
  laboratório — o que a equipe treinou e errou na semana.
Depois, cada mensagem do dono vai para quem ele escolher (clicando na tela da pessoa ou citando o nome) — ou para a
coordenação. A reunião é uma conversa com vários participantes: fica registrada e continua depois de reiniciar.
"""

from __future__ import annotations

import re

from robo import lideranca, organizacao
from robo.trabalho import Trabalho


def participantes(andar: int) -> list[str]:
    from robo.contratacao import LIDER_DO_ANDAR
    from robo import quadro
    gerentes = [p["id"] for p in quadro.QUADRO if p["andar"] == andar and p["nivel"] == "gerente"]
    if andar == 3:
        gerentes = ["excel_supervisor"]
    ids = [lideranca.DIRETOR_DO_ANDAR.get(andar), lideranca.HEAD_DO_ANDAR.get(andar)] + gerentes + [LIDER_DO_ANDAR.get(andar)]
    if andar == 4:
        ids += ["dir_pessoas", "head_rh"]
    if andar == 5:
        ids += ["head_python"]
    vistos = []
    for i in ids:
        if i and i not in vistos:
            vistos.append(i)
    return vistos


def abrir(cfg, andar: int) -> dict:
    from robo import auditoria, ferramentas, interacoes, reuniao
    andar = int(andar)
    gente = organizacao.por_id(cfg)
    ps = [p for p in participantes(andar) if p in gente]
    lider = next((p for p in reversed(ps) if organizacao.nivel_de(p, gente[p]) == "coordenador"), ps[-1])
    tb = Trabalho(cfg)
    cid = tb.criar_conversa(lider, f"Reunião do {andar}º andar — {organizacao.NOME_ANDAR.get(andar, '')}", "reuniao",
                            {"participantes": ps, "andar": andar, "sala": True})
    tb.mensagem(cid, "dono", f"Abri a reunião do {andar}º andar. Quero saber de tudo o que está acontecendo.")

    def fala(autor, r):
        tb.mensagem(cid, autor, r["texto"], r["natureza"], r)
        interacoes.balao(autor, r["texto"].split("\n")[0].replace("**", "")[:120], rotulo="reunião")

    diretor = lideranca.DIRETOR_DO_ANDAR.get(andar)
    if diretor in ps:
        fala(diretor, ferramentas.executar("scorecard", cfg, quem=diretor, andar=andar))
    if andar == 4 and "dir_pessoas" in ps:
        fala("dir_pessoas", ferramentas.executar("scorecard", cfg, quem="dir_pessoas"))
    head = lideranca.HEAD_DO_ANDAR.get(andar)
    if head in ps:
        ult = next((a for a in auditoria.listar(cfg, 50) if a["head"] == head), None)
        texto = (auditoria.texto({**ult, "sem_amostra": not ult["amostra"]}) if ult else
                 "Ainda não fiz a auditoria por amostragem desta área. Ela roda uma vez por semana; se quiser, "
                 "peça agora: “faça a auditoria”.")
        fala(head, ferramentas.resultado(True, "ferramenta", texto, evidencia="última auditoria registrada"))
    v = reuniao.ao_vivo(cfg, andar)["andares"]
    if v:
        a = v[0]
        plano = "; ".join(f"{x['acao'][:90]} ({x.get('quem_precisa_agir') or x['responsavel']})" for x in a["plano_de_acao"][:3])
        texto = (f"Deu certo: {'; '.join(a['deu_certo'][:3])}.\n\n## Deu errado\n" + "\n".join(f"• {x}" for x in a["deu_errado"][:5])
                 + f"\n\n## Plano de ação\n{plano or 'Nada novo a corrigir.'}\n\n## Em andamento agora\n"
                 + ("\n".join(a["agora"]) or "Nada em andamento."))
        fala(lider, ferramentas.resultado(True, "ferramenta", texto, evidencia="histórico, memória, handovers e central (agora)"))
    lab = ferramentas.executar("laboratorio", cfg)
    if lab["ok"]:
        fala(head if head in ps else lider, lab)
    return {"conversa_id": cid, "participantes": ps, "lider": lider}


def falar(cfg, conversa_id: str, texto: str, para: str | None = None) -> dict:
    from robo import atendimento
    tb = Trabalho(cfg)
    conv = tb.conversa(conversa_id)
    if not conv or not conv["contexto"].get("sala"):
        raise ValueError("Reunião não encontrada.")
    ps = conv["contexto"]["participantes"]
    gente = organizacao.por_id(cfg)
    alvo = para if para in ps else None
    if not alvo:  # citou alguém pelo nome? ("Beatriz, …", "@Eduardo …")
        t = texto.lower()
        alvo = next((p for p in ps if re.search(rf"(^|[@\s]){re.escape(gente[p]['nome'].lower())}([\s,:?!.]|$)", t)), None)
    return atendimento.conversar(cfg, alvo or conv["funcionario"], texto, conversa_id, origem="reuniao")


def detalhes(cfg, conversa_id: str) -> dict | None:
    from robo import rh
    conv = Trabalho(cfg).conversa(conversa_id)
    if not conv or not conv["contexto"].get("sala"):
        return None
    gente = organizacao.por_id(cfg)
    conv["pessoas"] = [{"id": p, "nome": gente[p]["nome"], "cargo": gente[p]["papel"], "cor": gente[p].get("cor"),
                        "nivel": rh.NOME_NIVEL.get(organizacao.nivel_de(p, gente[p]), "")}
                       for p in conv["contexto"]["participantes"] if p in gente]
    return conv
