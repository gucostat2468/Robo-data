"""O que acontece depois que a esteira processa uma planilha: um só lugar, usado pelo painel e pelo turno da nuvem.

Antes, isso morava só no painel (robo/painel/controle.py), e na nuvem nenhuma planilha virava solicitação, memória ou
aprendizado. Agora os dois chamam esta função.

  - toda planilha vira uma solicitação automática na central (origem 'sintetica' para as da fábrica);
  - planilha REAL: experiências e handovers de cada área (memória) e aprendizado de regras (proposta ao dono);
  - planilha SINTÉTICA: não gera proposta de regra nem handover. Regra nascida de dado inventado não deve chegar ao
    dono como se viesse da produção; o que a fábrica ensina já fica em aprendizados (robo/aprendizados.py).
"""

from __future__ import annotations

import logging

log = logging.getLogger("robo")


def registrar(cfg, r) -> str | None:
    """Nunca levanta exceção: falha aqui é registrada no log e não derruba a esteira. Devolve o id da solicitação."""
    from robo.historico import eh_sintetico
    sintetico = eh_sintetico(r.arquivo.name)
    sid = None
    try:
        from robo import orquestrador
        sid = orquestrador.registrar_execucao_automatica(cfg, r, origem="sintetica" if sintetico else "automatica")
    except Exception:
        log.exception("Não consegui registrar a execução na central de solicitações")
    if sintetico:
        return sid
    try:
        from robo import memoria
        memoria.registrar_execucao(cfg, r)  # experiências e handovers de cada área
    except Exception:
        log.exception("Não consegui registrar a execução na memória")
    try:  # aprendizado operacional: reprovou → proposta de regra; regra aprovada → prova de que mudou
        from robo import aprendizado
        aprendizado.comprovar(cfg, r)
        aprendizado.propor(cfg, r)
    except Exception:
        log.exception("Não consegui registrar o aprendizado da execução")
    return sid
