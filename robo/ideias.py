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


def _ideias_do_treino(tb, nome) -> list[dict]:
    """Expansão a partir do treino: onde a empresa trava, onde ficou fácil demais (hora de subir o teto) e mentorias
    que não estão funcionando. Só fala com número na mão."""
    from robo.treino_casos import CATALOGO
    nome_comp = lambda c: CATALOGO[c].nome if c in CATALOGO else c  # noqa: E731
    ideias = []
    with tb.tx() as c:
        tabelas = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "treino_tentativas" not in tabelas:
            return []
        desde = (datetime.now() - timedelta(days=14)).isoformat(timespec="seconds")
        gargalos = c.execute("SELECT competencia, nivel, COUNT(*) n, AVG(acertou) taxa FROM treino_tentativas WHERE data_hora>=? "
                             "GROUP BY 1, 2 HAVING n >= 10 AND taxa < 0.8 ORDER BY taxa LIMIT 2", (desde,)).fetchall()
        faceis = c.execute("SELECT t.competencia, COUNT(*) n, AVG(t.acertou) taxa, "
                           "(SELECT COUNT(*) FROM treino_niveis v WHERE v.competencia=t.competencia AND v.nivel=5) no_topo, "
                           "(SELECT COUNT(*) FROM treino_niveis v WHERE v.competencia=t.competencia) pessoas "
                           "FROM treino_tentativas t WHERE t.data_hora>=? AND t.nivel=5 GROUP BY 1 "
                           "HAVING n >= 20 AND taxa >= 0.95", (desde,)).fetchall()
        mentores = c.execute("SELECT mentor, SUM(situacao='ajudou') ok, SUM(situacao='nao_ajudou') nao FROM mentorias "
                             "GROUP BY mentor HAVING nao >= 3 AND nao > ok").fetchall() if "mentorias" in tabelas else []
    for g in gargalos:
        ideias.append({"impacto": 4, "titulo": f"Gargalo de aprendizado: {nome_comp(g['competencia'])} no nível {g['nivel']}",
                       "motivo": f"{g['n']} tentativas nos últimos 14 dias com só {g['taxa'] * 100:.0f}% de acerto",
                       "primeiro_passo": "A Sala de Casos revisa os casos desse nível e o dono da ferramenta confere se o erro é "
                                         "da pessoa ou do código (o treino já achou falhas reais do robô assim)",
                       "dono": CATALOGO[g["competencia"]].designer if g["competencia"] in CATALOGO else "head_casos"})
    for f in faceis:
        if f["pessoas"] and f["no_topo"] / f["pessoas"] >= 0.5:
            ideias.append({"impacto": 3, "titulo": f"Subir o teto: {nome_comp(f['competencia'])} ficou fácil no nível máximo",
                           "motivo": f"{f['taxa'] * 100:.0f}% de acerto em {f['n']} tentativas no nível 5; {f['no_topo']} de "
                                     f"{f['pessoas']} pessoas já estão no topo",
                           "primeiro_passo": "A Sala de Casos desenha um desafio novo (dados mais sujos, casos de borda) com "
                                             "gabarito e revisão independente",
                           "dono": "head_casos"})
    for m in mentores:
        ideias.append({"impacto": 3, "titulo": f"Mentoria que não está funcionando: {nome(m['mentor'])}",
                       "motivo": f"{m['nao']} mentorias sem efeito contra {m['ok']} que ajudaram",
                       "primeiro_passo": "O RH revê as conversas registradas e pareia essa pessoa com um mentor mais experiente",
                       "dono": "rh_td"})
    return ideias


ESQUEMA_REGISTRO = """CREATE TABLE IF NOT EXISTS ideias_registro (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, titulo TEXT, motivo TEXT, primeiro_passo TEXT, dono TEXT,
  impacto INTEGER, chave TEXT);
CREATE INDEX IF NOT EXISTS ix_ideias_chave ON ideias_registro(chave, data_hora);
CREATE TRIGGER IF NOT EXISTS ideias_registro_sem_alterar BEFORE UPDATE ON ideias_registro
BEGIN SELECT RAISE(ABORT, 'registro permanente: ideias_registro não pode ser alterado'); END;"""


def _tb_registro(cfg) -> Trabalho:
    from robo.trabalho import proteger
    tb = Trabalho(cfg)
    with tb.tx() as c:
        c.executescript(ESQUEMA_REGISTRO)
        proteger(c)
    return tb


def rotina(cfg, dias_sem_repetir: int = 7) -> dict | None:
    """Iara (ideias e expansão), uma vez por dia: gera as ideias pela memória e REGISTRA as novas. A mesma ideia só
    volta a ser registrada depois de 7 dias (se o problema continuar, ela insiste — com o número novo)."""
    import hashlib
    tb = _tb_registro(cfg)
    agora = datetime.now()
    with tb.tx() as c:
        ultima = c.execute("SELECT MAX(data_hora) FROM ideias_registro").fetchone()[0]
    if ultima and agora - datetime.fromisoformat(ultima) < timedelta(hours=24):
        return None
    limite = (agora - timedelta(days=dias_sem_repetir)).isoformat(timespec="seconds")
    novas = []
    for i in gerar(cfg, limite=15):
        if i["impacto"] <= 1:
            continue
        chave = hashlib.sha256(i["titulo"].encode()).hexdigest()[:16]
        with tb.tx() as c:
            if c.execute("SELECT 1 FROM ideias_registro WHERE chave=? AND data_hora>=?", (chave, limite)).fetchone():
                continue
            c.execute("INSERT INTO ideias_registro (data_hora, titulo, motivo, primeiro_passo, dono, impacto, chave) "
                      "VALUES (?,?,?,?,?,?,?)", (agora.isoformat(timespec="seconds"), i["titulo"], i["motivo"],
                                                 i["primeiro_passo"], i["dono"], i["impacto"], chave))
        novas.append(i)
    if novas:
        try:
            from robo.canal import Canal
            Canal(cfg).postar("canal_iara", f"Ideias do dia ({len(novas)}): " + " | ".join(f"{i['titulo']} → {i['dono_nome']}"
                                                                                       for i in novas[:5]), "geral", "ideia")
        except Exception:
            pass
    return {"registradas": len(novas)} if novas else {"registradas": 0}


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
    ideias += _ideias_do_treino(tb, nome)
    if not ideias:
        ideias.append({"impacto": 1, "titulo": "Nada urgente na memória agora",
                       "motivo": "Sem erro repetido, sem handover parado, sem pedido sem resposta",
                       "primeiro_passo": "Seguir o PDCA e as rodadas de estudo", "dono": "canal_iara"})
    for i in ideias:
        i["dono_nome"] = nome(i["dono"])
    return sorted(ideias, key=lambda i: -i["impacto"])[:limite]
