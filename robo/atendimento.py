"""Atendimento: o dono conversa direto com qualquer funcionário, com memória da conversa.

Entradas que usam esta mesma infraestrutura: a ficha do funcionário (painel e escritório 3D), a central de
solicitações, o contexto de um arquivo anexado e o acompanhamento de uma tarefa.

O que a conversa lembra (fica em logs/trabalho.db e sobrevive a reinício):
  - o arquivo anexado e a base em uso;
  - o último cálculo (para perguntas de continuação: "e por região?", "e onde canal = App?");
  - as suas correções ("na verdade a coluna de nota é nota_final", "use a base vendas");
  - as tarefas abertas a partir da conversa.

Como responde:
  1. Pergunta sobre a própria pessoa → contrato de execução (registro único).
  2. Pedido com objetivo ("verifique esta planilha", "faça uma análise completa") → vira TAREFA com plano,
     etapas, responsáveis, aprovações e revisão (robo/orquestrador.py).
  3. Pergunta → a ferramenta certa (cálculo, histórico, conhecimento…). Se a ferramenta não está no contrato da
     pessoa, ela diz isso e o colega certo responde na mesma conversa (encaminhamento de verdade).
  4. Sem certeza → diz que não sabe e sugere o que perguntar. Nunca inventa.
"""

from __future__ import annotations

import re

from robo import ferramentas, orquestrador, organizacao
from robo.trabalho import Trabalho


def _norm(t: str) -> str:
    from robo.canal import normalizar
    return normalizar(t)


def _msg(autor: str, r: dict, **extra) -> dict:
    return {"autor": autor, "texto": r["texto"], "natureza": r["natureza"], "natureza_nome": r["natureza_nome"],
            "evidencia": r.get("evidencia", ""), "dados": {k: v for k, v in (r.get("dados") or {}).items()
                                                           if k in ("autor", "pergunta", "fonte", "aprovaria", "achados")},
            **extra}


# --------------------------------------------------------------------------- memória da conversa
def _aplicar_correcoes(pergunta: str, ctx: dict) -> str:
    for errado, certo in (ctx.get("correcoes") or {}).items():
        pergunta = re.sub(rf"\b{re.escape(errado)}\b", certo, pergunta, flags=re.IGNORECASE)
    return pergunta


def _correcao(texto: str) -> dict | None:
    """'na verdade a coluna X é Y' / 'use a base Y' / 'considere o arquivo …' → mudança de contexto."""
    t = _norm(texto)
    m = re.search(r"(?:use|usar|considere|troque para|mude para) (?:a )?base ([\w-]+)", t)
    if m:
        return {"base": m.group(1)}
    m = re.search(r"(?:na verdade|corrigindo|correcao|errei)[, :]+(?:a )?coluna (?:de |do |da )?([\w-]+) (?:e|eh|se chama|chama) ([\w-]+)", t)
    if m:
        return {"correcao": (m.group(1), m.group(2))}
    if re.match(r"^(esqueca|esquece|limpe|limpa) (o )?(arquivo|contexto)", t):
        return {"limpar": True}
    return None


def _continuacao(texto: str, ctx: dict) -> str | None:
    """'e por região?' → refaz o último cálculo com o novo corte. Sem cálculo anterior, não é continuação."""
    anterior = ctx.get("ultimo_calculo")
    if not anterior:
        return None
    t = _norm(texto).rstrip("?").strip()
    m = re.match(r"^(?:e|agora|e se for|e se) (por|onde|na base|so|somente|apenas) (.+)$", t)
    if not m:
        return None
    tipo, resto = m.group(1), m.group(2)
    base_q = anterior
    if tipo == "por":
        base_q = re.sub(r"\s+por\s+.*?(?=\s+onde\s+|\s+na base\s+|$)", "", base_q, flags=re.IGNORECASE)
        return f"{base_q} por {resto}"
    if tipo in ("onde", "so", "somente", "apenas"):
        resto = re.sub(r"^onde\s+", "", resto)
        base_q = re.sub(r"\s+onde\s+.*?(?=\s+na base\s+|$)", "", base_q, flags=re.IGNORECASE)
        return f"{base_q} onde {resto}"
    base_q = re.sub(r"\s+na base\s+[\w-]+", "", base_q, flags=re.IGNORECASE)
    return f"{base_q} na base {resto}"


# --------------------------------------------------------------------------- respostas
def _sobre_mim(t: str) -> bool:
    return bool(re.search(r"quem (e|eh) voce|o que voce faz|qual (e )?(o )?seu (cargo|papel|contrato|trabalho)|"
                          r"suas (responsabilidades|ferramentas|permissoes)|voce pode|apresente", t))


def _texto_contrato(c: dict) -> str:
    nomes = {f: ferramentas.REGISTRO[f].nome for f in c["ferramentas"] if f in ferramentas.REGISTRO}
    linhas = [f"Sou {c['nome']}, {c['cargo']} ({c['nivel_nome']}, {c['andar']}º andar — {c['nome_andar']}).",
              f"Gestor: {c['gestor_nome'] or '—'} · Quem revisa o meu trabalho: {c['revisor_nome']}.",
              "Responsabilidades: " + ("; ".join(c["responsabilidades"][:4]) or "—") + ".",
              "Ferramentas que posso usar: " + ", ".join(nomes.values()) + ".",
              f"Risco máximo que posso assumir: {c['risco_maximo']}."
              + (" Altero dados só com a sua aprovação." if c["permissoes"]["altera_dados"] else " Não altero dados.")]
    if c["permissoes"].get("modo"):
        linhas.append(f"Modo: {c['permissoes']['modo']}.")
    if c["limites"]:
        linhas.append("Limites: " + "; ".join(c["limites"][:3]) + ".")
    return "\n".join(linhas)


def _escolher_ferramenta(t: str, ctx: dict) -> str | None:
    """Ferramenta para uma pergunta (não tarefa). Ordem: mais específica primeiro."""
    if re.search(r"historico|ultim(as|os) (execuc|arquivos|planilhas|processament)|o que (aconteceu|foi processado)", t):
        return "historico"
    if re.search(r"saude|ronda|disco|seguranca do (sistema|computador|robo)", t):
        return "ronda_ti"
    if re.search(r"dado(s)? pessoa|lgpd|cpf|e-?mail|telefone", t) and (ctx.get("arquivo") or "base" in t):
        return "dados_pessoais"
    if re.search(r"consultas? sql|quais consultas", t):
        return "consulta_sql"
    if re.search(r"quantas pessoas|lotacao|organograma|quem faz o que", t):
        return "organizacao"
    return None


def conversar(cfg, funcionario: str, texto: str, conversa_id: str | None = None, arquivo: str | None = None,
              origem: str = "ficha") -> dict:
    """Uma mensagem do dono para `funcionario`. Devolve {conversa_id, respostas, solicitacao_id}."""
    texto = str(texto or "").strip()
    if not texto and not arquivo:
        raise ValueError("Escreva uma mensagem ou anexe um arquivo.")
    contrato = organizacao.contrato(funcionario, cfg)
    if not contrato:
        raise ValueError(f"Funcionário '{funcionario}' não existe.")
    tb = Trabalho(cfg)
    if conversa_id:
        conv = tb.conversa(conversa_id)
        if not conv:
            raise ValueError("Conversa não encontrada.")
        if conv["funcionario"] != funcionario:
            raise ValueError("Esta conversa é com outra pessoa.")
    else:
        conversa_id = tb.criar_conversa(funcionario, (texto or f"Arquivo {arquivo}")[:80], origem)
    ctx = tb.conversa(conversa_id)["contexto"]
    if arquivo:
        tb.anexar(conversa_id, arquivo)
        ctx = tb.atualizar_contexto(conversa_id, arquivo=str(arquivo))
    tb.mensagem(conversa_id, "dono", texto or f"(anexou {arquivo})", dados={"arquivo": str(arquivo)} if arquivo else None)

    respostas, sid = _responder(cfg, tb, conversa_id, contrato, texto, ctx, arquivo)
    for r in respostas:
        tb.mensagem(conversa_id, r["autor"], r["texto"], r["natureza"], r, sid)
    return {"conversa_id": conversa_id, "respostas": respostas, "solicitacao_id": sid}


def _registrar_pergunta(tb, contrato, texto, conversa_id, respostas) -> str:
    """Toda pergunta também entra na central de solicitações (tipo conversa), com a natureza da resposta."""
    ok = not all(r["natureza"] == "limitacao" for r in respostas)
    sid = tb.criar_solicitacao("conversa", texto[:120] or "(arquivo)", texto, "manual", contrato["id"], contrato["andar"],
                               conversa_id=conversa_id, resultado={"naturezas": [r["natureza"] for r in respostas],
                                                                   "respondido_por": [r["autor"] for r in respostas]})
    tb.mudar_estado(sid, "concluida" if ok else "falhou", contrato["id"],
                    "Respondida" if ok else "Não foi possível responder (limitação registrada)")
    return sid


def _responder(cfg, tb, conversa_id, contrato, texto, ctx, arquivo) -> tuple[list[dict], str | None]:
    pid = contrato["id"]
    t = _norm(texto)

    if not texto:  # só anexou
        r = ferramentas.resultado(True, "ferramenta", f"Recebi {arquivo}. Posso verificar a planilha, calcular sobre ela "
                                                      "ou montar uma análise completa — é só pedir.", evidencia=str(arquivo))
        return [_msg(pid, r)], None

    corr = _correcao(texto)
    if corr:
        if corr.get("limpar"):
            tb.atualizar_contexto(conversa_id, arquivo=None, base=None, ultimo_calculo=None, correcoes={})
            r = ferramentas.resultado(True, "ferramenta", "Pronto: esqueci o arquivo, a base e as correções desta conversa.")
        elif corr.get("base"):
            tb.atualizar_contexto(conversa_id, base=corr["base"])
            r = ferramentas.resultado(True, "ferramenta", f"Anotado: nesta conversa uso a base {corr['base']}.")
        else:
            errado, certo = corr["correcao"]
            correcoes = {**(ctx.get("correcoes") or {}), errado: certo}
            tb.atualizar_contexto(conversa_id, correcoes=correcoes)
            tb.lembrar("correcao", errado, f"Quando o dono diz '{errado}', é a coluna '{certo}'", "dono")
            r = ferramentas.resultado(True, "ferramenta", f"Anotado: quando você disser “{errado}”, uso a coluna “{certo}”. "
                                                          "Vale para esta conversa e fica registrado na memória da empresa.")
        msgs = [_msg(pid, r)]
        return msgs, _registrar_pergunta(tb, contrato, texto, conversa_id, msgs)

    if _sobre_mim(t):
        r = ferramentas.resultado(True, "conhecimento", _texto_contrato(contrato), evidencia="contrato de execução (registro único)")
        msgs = [_msg(pid, r)]
        return msgs, _registrar_pergunta(tb, contrato, texto, conversa_id, msgs)

    # pedido com objetivo → tarefa ou projeto
    tipo = orquestrador.classificar(texto)
    if tipo in ("tarefa", "projeto"):
        sid = orquestrador.criar(cfg, texto, pid, conversa_id, "manual", ctx.get("arquivo"), ctx.get("base"))
        s = tb.solicitacao(sid)
        tb.atualizar_contexto(conversa_id, tarefas=list(dict.fromkeys((ctx.get("tarefas") or []) + [sid])))
        return [_msg(pid, _texto_plano(cfg, s), solicitacao=sid)], sid

    # continuação de cálculo, com as correções da conversa
    pergunta = _continuacao(texto, ctx) or texto
    pergunta = _aplicar_correcoes(pergunta, ctx)
    ferr = _escolher_ferramenta(t, ctx)
    params = {"pergunta": pergunta, "arquivo": ctx.get("arquivo"), "base": ctx.get("base")}
    if not ferr:
        from robo.canal import INTENCOES, _pontuar
        sobre_o_robo = _pontuar(t, INTENCOES["erros"]) >= 2 or _pontuar(t, INTENCOES["status"]) >= 2
        calc = None if sobre_o_robo or re.match(r"^(como|o que|qual a diferenca|por que)\b", t) else \
            ferramentas.executar("calcular", cfg, **params)
        if calc and (calc["ok"] or "Não reconheci" not in calc["texto"]):
            ferr, pronto = "calcular", calc
        else:
            ferr, pronto = None, None
    else:
        pronto = None

    if not ferr:
        k = ferramentas.executar("conhecimento", cfg, pergunta=texto)
        if k["ok"]:
            msgs = [_msg(pid, k)]
            return msgs, _registrar_pergunta(tb, contrato, texto, conversa_id, msgs)
        # dados do dia (status, erros, sprint…) pelo mesmo motor do canal, que só lê o que aconteceu
        from robo.canal import responder
        r = responder(texto, cfg)[0]
        if r.get("intencao") not in ("nao_entendi", "apresentacao", "saudacao"):
            msgs = [_msg(r["autor"] if r["autor"] in organizacao.por_id(cfg) else pid,
                         ferramentas.resultado(True, "ferramenta", r["texto"], evidencia=f"canal ({r.get('intencao')})"))]
            return msgs, _registrar_pergunta(tb, contrato, texto, conversa_id, msgs)
        r = ferramentas.resultado(False, "limitacao",
                                  "Não tenho certeza do que você precisa — prefiro perguntar a chutar. Posso: responder sobre o "
                                  "meu trabalho (\"o que você faz?\"), calcular (\"nps por região\"), verificar uma planilha "
                                  "anexada (\"verifique esta planilha\"), montar uma análise completa, mostrar o histórico "
                                  "ou buscar no conhecimento da empresa.")
        msgs = [_msg(pid, r)]
        return msgs, _registrar_pergunta(tb, contrato, texto, conversa_id, msgs)

    # a ferramenta está no meu contrato? se não, encaminho para quem tem (e o colega responde aqui)
    msgs = []
    executor = pid
    if not organizacao.pode_usar(pid, ferr, cfg):
        executor = organizacao.quem_usa(ferr, cfg)
        colega = organizacao.contrato(executor, cfg) if executor else None
        aviso = ferramentas.resultado(False, "limitacao",
                                      f"Isso não está no meu contrato ({ferramentas.REGISTRO[ferr].nome}). "
                                      + (f"Quem faz é {colega['nome']} ({colega['cargo']}); já passei para responder aqui."
                                         if colega else "Ninguém no quadro tem essa ferramenta."))
        msgs.append(_msg(pid, aviso, encaminhado_para=executor))
        if not executor:
            return msgs, _registrar_pergunta(tb, contrato, texto, conversa_id, msgs)
        pronto = None  # o colega executa de novo, com o próprio contrato
    r = pronto or ferramentas.executar(ferr, cfg, **params)
    autor = executor
    if ferr == "calcular" and r["ok"]:
        tb.atualizar_contexto(conversa_id, ultimo_calculo=pergunta)
    msgs.append(_msg(autor, r))
    return msgs, _registrar_pergunta(tb, contrato, texto, conversa_id, msgs)


def _texto_plano(cfg, s: dict) -> dict:
    gente = organizacao.por_id(cfg)
    nome = lambda x: "você" if x == "dono" else (gente.get(x) or {}).get("nome", x)  # noqa: E731
    if s["estado"] == "aguardando_esclarecimento":
        motivo = next((e["texto"] for e in reversed(s["eventos"]) if e["para"] == "aguardando_esclarecimento"), "")
        return ferramentas.resultado(False, "precisa_confirmacao", f"Registrei {s['id']}, mas antes preciso de um esclarecimento: "
                                     f"{motivo}", evidencia=f"central de solicitações · {s['id']}")
    if s["tipo"] == "projeto":
        linhas = [f"Registrei o projeto {s['id']} com {len(s['tarefas'])} tarefa(s):"]
        linhas += [f"• {t['id']} — {t['titulo']} ({t['estado'].replace('_', ' ')})" for t in s["tarefas"]]
        return ferramentas.resultado(True, "ferramenta", "\n".join(linhas) + "\nAcompanhe em Solicitações.",
                                     evidencia=f"central de solicitações · {s['id']}")
    linhas = [f"Registrei a tarefa {s['id']}. Plano:"]
    for e in s["etapas"]:
        dep = f" (depois da {', '.join(map(str, e['depende']))})" if e["depende"] else ""
        extra = " — precisa da sua aprovação" if e["precisa_aprovacao"] else ""
        extra += " — sem ferramenta no robô: será marcada como não feita" if not e["ferramenta"] else ""
        linhas.append(f"{e['ordem']}. {e['titulo']} — {nome(e['funcionario'])}{dep}{extra}")
    linhas.append(f"Revisão independente: {nome(s['revisor'])}. Acompanhe o andamento em Solicitações.")
    precisa = any(e["precisa_aprovacao"] for e in s["etapas"])
    return ferramentas.resultado(True, "precisa_confirmacao" if precisa else "ferramenta", "\n".join(linhas),
                                 evidencia=f"central de solicitações · {s['id']}")
