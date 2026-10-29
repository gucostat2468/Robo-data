"""Memória de cada funcionário, handover de erros por área e desempenho.

Onde fica: no mesmo logs/trabalho.db das conversas e tarefas, separado por funcionário (coluna `funcionario`).
Um banco único, e não um arquivo por pessoa: assim dá para cruzar dados (reunião semanal, área, período) numa
transação só. Para ler a memória de uma pessoa como documento, `exportar_dossie` grava logs/memoria/<id>.md.

O que entra na memória (só fatos que aconteceram, cada um com a sua origem):
  - experiências: acerto, erro, aprendizado, correção do dono e treinamento, vindos do pipeline, das tarefas,
    das revisões e das provas do RH;
  - handovers: todo erro vira uma regra para a área responsável (o que aconteceu, a causa provável, o que fazer para
    não repetir e como verificar). Erro repetido não cria outro handover: soma recorrência no mesmo;
  - desempenho: acertos ÷ (acertos + erros) no período, mais as provas técnicas.

Desempenho insuficiente segue o processo de uma empresa séria: primeiro um plano de melhoria (PDI) com treinamento;
se persistir na reunião seguinte, a liderança PROPÕE o desligamento e só o dono decide. Cargos fixos do pipeline são
código do robô: desempenho ruim de um deles é defeito de programa, vira handover para a TI (Diego) com teste
automatizado, e não "demissão" (demitir o código que lê as planilhas pararia a empresa).
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from pathlib import Path

from robo import organizacao
from robo.trabalho import Trabalho, _agora

# (padrão do erro, andar, responsável, causa provável, regra para não repetir, como verificar)
CATEGORIAS = [
    (r"desempenho insuficiente de cargo fixo", 5, "dev_pleno", "Cargo fixo é código do robô: erro repetido indica defeito",
     "Diego investiga os erros listados, corrige o código e cria um teste automatizado que reproduz o caso",
     "Taxa de acerto do cargo volta a 90% ou mais na reunião seguinte"),
    (r"configuracao invalida|esta com configuracao invalida", 1, "coord_engenharia",
     "Agente ou habilidade configurado para uma coluna que esta base não tem",
     "Restringir o 'padrão de arquivos' do agente às bases que têm a coluna, ou corrigir o nome da coluna na habilidade "
     "(tela Equipe → agente → habilidades)",
     "A próxima carga dessa base não reprova por configuração"),
    (r"colunas da dimensao nao existem|chave .* ja existe como coluna|coluna do calendario", 1, "modelagem",
     "O modelo (fato/dimensões) do config.yaml cita colunas que esta planilha não tem",
     "Ajustar 'modelo' na regra da base para os nomes de coluna reais (ou incluir sinônimos)",
     "Próxima carga dessa base passa pela modelagem"),
    (r"erro de formula", 1, "leitura", "Fórmula quebrada na planilha de origem (#REF!, #DIV/0!, #N/D)",
     "Quem gera a planilha procura #REF!/#DIV/0!/#N/D (Ctrl+L) e corrige antes de salvar em Bases-Limpeza",
     "Leo (leitura) barra automaticamente; conferir que a próxima carga dessa base veio sem erro de fórmula"),
    (r"obrigatorias ausentes|nao existe no arquivo|nao existem no arquivo", 1, "validacao",
     "O cabeçalho mudou na origem (coluna renomeada ou removida)",
     "Alinhar o nome da coluna com quem gera a planilha ou acrescentar o nome novo em 'sinonimos' na regra",
     "A próxima carga dessa base passa na validação sem este erro"),
    (r"vazias em coluna obrigatoria", 1, "validacao", "Campo obrigatório deixado em branco na origem",
     "Preencher na origem; se a coluna não precisa ser obrigatória, tirar de 'nao_nulos' na regra (decisão do dono)",
     "Contagem de vazios igual a zero na próxima carga"),
    (r"chave unica repetida", 1, "validacao", "Registro duplicado na origem",
     "Remover a duplicidade na origem ou revisar se a chave única está certa", "Zero chaves repetidas na próxima carga"),
    (r"fora da faixa|fora da lista|fora de \S+ a \S+", 1, "validacao", "Valor inválido ou categoria nova na origem",
     "Corrigir o valor na origem; se o valor novo é legítimo, atualizar 'faixas' ou 'valores_permitidos' na regra",
     "Próxima carga sem valor fora da regra"),
    (r"nao puderam ser convertidos|casas decimais|tipo .* invalido", 1, "limpeza", "Tipo de dado misturado na coluna",
     "Padronizar o formato na origem (número como número, data como data) ou ajustar 'tipos' na regra",
     "Próxima carga converte 100% da coluna"),
    (r"linha\(s\) de dados apos a limpeza|nenhuma coluna com dados|nao tem nenhuma aba", 1, "leitura",
     "Arquivo vazio ou com dados fora do lugar", "Conferir se o arquivo certo foi salvo e se os dados estão na primeira aba",
     "Próxima carga com linhas"),
    (r"supervisor de planilhas", 1, "supervisor", "Inconsistência que só aparece no conjunto (chave órfã, linhas sumidas)",
     "Ler o detalhe do supervisor e corrigir a relação entre as tabelas na origem", "Supervisor aprova a próxima carga"),
    (r"conferencia da equipe|coordenadora de engenharia", 1, "coord_engenharia",
     "Conferência do quadro barrou a produção", "Seguir o achado da conferência (tipos, espaços, auditoria, amostra)",
     "Checklist da coordenadora verde na próxima carga"),
    (r"futurewarning|deprecationwarning|depreciac", 5, "head_python", "Uma biblioteca avisou que vai mudar de comportamento",
     "O especialista da biblioteca troca o uso antigo pelo novo e cria teste com o caso", "A revisão da biblioteca volta sem aviso"),
    (r"revisao (da|de) biblioteca|biblioteca .* mudou", 5, "head_python", "Atualização de biblioteca mudou um comportamento do qual o robô depende",
     "Fixar a versão anterior em requisitos.txt até o código ser ajustado e testado", "Revisão da biblioteca toda verde"),
    (r"divergencia entre calculadora e postgresql", 1, "dba", "O mesmo cálculo deu números diferentes em dois caminhos",
     "Dora compara a consulta SQL com a calculadora linha a linha, acha a causa (tipo, nulo, linha duplicada, arquivo "
     "diferente) e cria um teste automatizado com o caso", "A mesma pergunta volta a dar 'Conferido no PostgreSQL'"),
    (r"postgresql", 1, "dba", "Carga no banco recusada", "Ver a mensagem do PostgreSQL; ajustar tipo da coluna ou a conexão",
     "Próxima carga confirmada pela Dora"),
    (r"gravar a saida|formato .* nao suportado", 1, "publicacao", "Arquivo de saída ou de entrada em formato/estado errado",
     "Fechar a planilha de saída no Excel antes do processamento; enviar só .xlsx/.xlsm/.xls/.csv/.txt",
     "Próxima publicação gravada"),
    (r"falha inesperada|nao conseguiu conferir|nao consegui concluir|nao consegui|falhou \(", 5, "dev_pleno",
     "Erro de programa (defeito no código do robô)",
     "Corrigir o código e criar um teste automatizado que reproduz o erro (assim ele nunca volta sem ser percebido)",
     "Teste automatizado novo passando e a mesma entrada processada sem falha"),
    (r"recalculo independente|sem texto ou evidencia|artefato", 2, "coord_analise", "Entrega sem evidência ou com número divergente",
     "Toda entrega precisa de evidência e de recálculo igual; refazer a etapa e revisar o método", "Revisão aprovada na próxima tarefa"),
    (r"reprovado na prova", 4, "canal_helena", "Funcionário sem a competência comprovada para a habilidade",
     "Treinamento da trilha da área e nova prova antes de voltar a executar", "Prova aprovada na próxima avaliação"),
]


def _norm(t: str) -> str:
    from robo.canal import normalizar
    return normalizar(t)


def _chave(texto: str, base: str) -> str:
    # só números SOLTOS viram '#' (valores: "12 linhas"); dígitos dentro de nomes ('nota1', 'nota2') continuam,
    # senão erros de colunas diferentes viravam um handover só
    t = re.sub(r"(?<![\w])\d+([.,]\d+)?(?![\w])", "#", _norm(texto))
    t = re.sub(r"\s+", " ", t)[:200]
    return hashlib.sha1(f"{base}|{t}".encode()).hexdigest()[:16]


def categorizar(texto: str) -> tuple:
    t = _norm(texto)
    for padrao, andar, resp, causa, regra, verificar in CATEGORIAS:
        if re.search(padrao, t):
            return andar, resp, causa, regra, verificar
    return 1, "coord_engenharia", CAUSA_DESCONHECIDA, "A coordenação analisa o caso e escreve a regra", \
        "Mesmo erro não aparece na próxima ocorrência"


CAUSA_DESCONHECIDA = "Causa ainda não classificada"


# --------------------------------------------------------------------------- registro
def experiencia(cfg, funcionario: str, tipo: str, resumo: str, origem: str, referencia: str = "", detalhe: str = "",
                tb: Trabalho | None = None) -> None:
    # colaboracao = ajudou ou ensinou um colega (conta como participação, NÃO como acerto do próprio trabalho)
    assert tipo in ("acerto", "erro", "aprendizado", "correcao", "treinamento", "colaboracao"), tipo
    tb = tb or Trabalho(cfg)
    andar = (organizacao.por_id(cfg).get(funcionario) or {}).get("andar")
    with tb.tx() as c:
        c.execute("INSERT INTO experiencias (funcionario, data_hora, tipo, resumo, detalhe, origem, referencia, andar) "
                  "VALUES (?,?,?,?,?,?,?,?)", (funcionario, _agora(), tipo, resumo[:500], detalhe[:4000], origem, referencia, andar))


def handover(cfg, erro: str, base: str = "", detectado_por: str = "", exemplo: str = "", tb: Trabalho | None = None,
             responsavel: str | None = None) -> str:
    """Erro → handover da área (um por tipo de erro e base; repetição soma recorrência). Devolve o id.
    responsavel: quando quem registra SABE quem cuida (ex.: o treino sabe a área dona da ferramenta); senão, a categoria
    do erro decide."""
    tb = tb or Trabalho(cfg)
    andar, resp, causa, regra, verificar = categorizar(erro)
    if responsavel:
        resp = responsavel
        andar = (organizacao.por_id(cfg).get(responsavel) or {}).get("andar", andar)
    chave = _chave(erro, base)
    agora = _agora()
    with tb.tx() as c:
        h = c.execute("SELECT id, estado FROM handovers WHERE chave=?", (chave,)).fetchone()
        if h:
            # erro que voltou depois de "aplicado" reabre o handover: a regra não segurou
            estado = "reaberto" if h["estado"] in ("aplicado", "verificado") else h["estado"]
            c.execute("UPDATE handovers SET recorrencias=recorrencias+1, ultima_ocorrencia=?, atualizado_em=?, estado=? WHERE id=?",
                      (agora, agora, estado, h["id"]))
            evento_handover(c, h["id"], "ocorrencia", h["estado"], estado, detectado_por, exemplo[:300])
            if estado == "reaberto" and h["estado"] == "verificado":
                _regressao(c, h["id"], f"o erro voltou em {agora} ({exemplo[:120] or base})")
            return h["id"]
        hid = f"HO-{datetime.now():%Y%m%d}-{chave[:12]}"
        c.execute("INSERT INTO handovers (id, chave, andar, area, responsavel, detectado_por, erro, causa, regra, como_verificar, "
                  "exemplo, criado_em, ultima_ocorrencia, atualizado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (hid, chave, andar, organizacao.NOME_ANDAR.get(andar, ""), resp, detectado_por,
                   (f"[{base}] " if base else "") + erro[:500], causa, regra, verificar, exemplo[:500], agora, agora, agora))
        evento_handover(c, hid, "criado", None, "aberto", detectado_por, exemplo[:300])
    return hid


def evento_handover(c, hid: str, tipo: str, de, para, quem: str = "", detalhe: str = "") -> None:
    """Histórico imutável do handover: cada ocorrência e cada mudança de estado (manual ou automática)."""
    c.execute("INSERT INTO handover_eventos (handover_id, data_hora, tipo, de, para, quem, detalhe) VALUES (?,?,?,?,?,?,?)",
              (hid, _agora(), tipo, de, para, quem or "robo", (detalhe or "")[:500]))


def _regressao(c, hid: str, motivo: str) -> None:
    """O erro voltou depois de verificado: a boa prática fica sob suspeita e quem tinha a lição como 'aplicada' volta
    para 'avaliada' (a prova antiga deixou de valer). Tudo registrado."""
    c.execute("UPDATE boas_praticas SET valida=0, invalidada_em=?, motivo_invalidacao=? WHERE handover_id=?",
              (_agora(), motivo[:300], hid))
    try:
        from robo import licoes
        afetados = c.execute(
            "SELECT lf.licao_id, lf.funcionario FROM licoes_funcionario lf JOIN licoes l ON l.id=lf.licao_id "
            "WHERE lf.estado='aplicada' AND ((l.origem_tipo='handover' AND l.origem_ref=?) OR "
            "(l.origem_tipo='boa_pratica' AND l.origem_ref=?))", (hid, hid.replace("HO-", "BP-"))).fetchall()
        for a in afetados:
            c.execute("UPDATE licoes_funcionario SET estado='avaliada', evidencia=? WHERE licao_id=? AND funcionario=?",
                      (f"regrediu: {motivo}"[:500], a["licao_id"], a["funcionario"]))
            licoes._registrar(c, "licao_regrediu", a["licao_id"], a["funcionario"], {"motivo": motivo[:300]})
    except Exception as e:  # caderno de lições ainda não existe neste banco
        if "no such table" not in str(e):
            raise


def mudar_handover(cfg, hid: str, estado: str, quem: str = "dono") -> None:
    if estado not in ("aberto", "em_aplicacao", "aplicado", "verificado", "reaberto"):
        raise ValueError("estado inválido")
    tb = Trabalho(cfg)
    with tb.tx() as c:
        h = c.execute("SELECT estado FROM handovers WHERE id=?", (hid,)).fetchone()
        if not h:
            raise ValueError("handover não existe")
        c.execute("UPDATE handovers SET estado=?, atualizado_em=? WHERE id=?", (estado, _agora(), hid))
        evento_handover(c, hid, "estado", h["estado"], estado, quem, "mudança manual")
    tb.lembrar("handover", hid, f"{quem} marcou {hid} como {estado}", quem)


def handovers(cfg, andar: int | None = None, abertos: bool = False, limite: int = 200) -> list[dict]:
    sql, args = "SELECT * FROM handovers WHERE 1=1", []
    if andar:
        sql += " AND andar=?"
        args.append(int(andar))
    if abertos:
        sql += " AND estado IN ('aberto','em_aplicacao','reaberto')"
    with Trabalho(cfg).tx() as c:
        linhas = [dict(r) for r in c.execute(sql + " ORDER BY recorrencias DESC, ultima_ocorrencia DESC LIMIT ?", args + [limite])]
        for h in linhas:  # categoria aprendida depois: reclassifica registros antigos (não fica "não classificada" para sempre)
            if h["causa"] == CAUSA_DESCONHECIDA:
                andar, resp, causa, regra, verificar = categorizar(re.sub(r"^\[[^\]]+\]\s*", "", h["erro"]))
                if causa != CAUSA_DESCONHECIDA:
                    c.execute("UPDATE handovers SET andar=?, area=?, responsavel=?, causa=?, regra=?, como_verificar=? WHERE id=?",
                              (andar, organizacao.NOME_ANDAR.get(andar, ""), resp, causa, regra, verificar, h["id"]))
                    evento_handover(c, h["id"], "reclassificado", h["responsavel"], resp, "robo",
                                    f"causa: {causa}; regra: {regra}")
                    h.update(andar=andar, area=organizacao.NOME_ANDAR.get(andar, ""), responsavel=resp, causa=causa,
                             regra=regra, como_verificar=verificar)
    gente = organizacao.por_id(cfg)
    return [h | explicar(h, gente) for h in linhas]


# erros que dependem de quem gera a planilha (o robô não pode "consertar" dado na origem: seria inventar dado)
RESPONSAVEIS_ORIGEM = {"validacao", "leitura", "limpeza"}
# erros simples: corrigidos em minutos numa configuração do painel
SIMPLES = ("configuracao invalida", "formato", "gravar a saida")
ESCALAR_APOS = 3


def explicar(h: dict, gente: dict | None = None) -> dict:
    """Por que aconteceu, por que ainda não foi resolvido, quem precisa agir e se é simples."""
    gente = gente or {}
    nome = lambda x: (gente.get(x) or {}).get("nome", x)  # noqa: E731
    texto = _norm(h.get("erro", ""))
    simples = any(x in texto for x in SIMPLES)
    origem = h.get("responsavel") in RESPONSAVEIS_ORIGEM and not simples
    por_que = h.get("causa", "") + (f" Exemplo: {h['exemplo']}." if h.get("exemplo") else "")
    estado = h.get("estado")
    if estado == "reaberto":
        nao_resolvido = (f"Foi marcado como corrigido, mas voltou a acontecer em {str(h.get('ultima_ocorrencia'))[:16]}. "
                         "A correção aplicada não atacou a causa: é preciso rever a regra.")
    elif estado == "em_aplicacao":
        nao_resolvido = (f"Já está no backlog da Estratégia (item {h.get('backlog_id') or '—'}) com {nome(h.get('responsavel'))}, "
                         "mas ninguém marcou como aplicado ainda.")
    elif estado in ("aplicado", "verificado"):
        nao_resolvido = "Resolvido: não voltou a acontecer desde a correção." if estado == "verificado" else             "Correção aplicada; falta confirmar na próxima carga que o erro não voltou."
    else:
        nao_resolvido = ("Ainda ninguém começou a correção: o handover existe desde "
                         f"{str(h.get('criado_em'))[:10]} e entra no backlog, com responsável e prazo, na próxima reunião semanal.")
    if origem and estado not in ("aplicado", "verificado"):
        nao_resolvido += (" Este erro está no DADO que chega: o robô barra e avisa, mas não muda dado da origem (seria "
                          "inventar informação). Resolve quem gera a planilha, ou você, se decidir mudar a regra.")
    quem = ("Você (no painel, em minutos)" if simples else
            "Quem gera a planilha (ou você, mudando a regra)" if origem else nome(h.get("responsavel")))
    escalado = int(h.get("recorrencias") or 0) >= ESCALAR_APOS and estado not in ("aplicado", "verificado")
    return {"por_que_aconteceu": por_que, "por_que_nao_resolvido": nao_resolvido, "quem_precisa_agir": quem,
            "simples": simples, "na_origem": origem, "escalado": escalado,
            "escalado_para": nome(organizacao.lider_do_andar(h.get("andar") or 1)) if escalado else None}


def experiencias(cfg, funcionario: str | None = None, desde: str | None = None, ate: str | None = None,
                 limite: int = 500) -> list[dict]:
    sql, args = "SELECT * FROM experiencias WHERE 1=1", []
    if funcionario:
        sql += " AND funcionario=?"
        args.append(funcionario)
    if desde:
        sql += " AND data_hora>=?"
        args.append(desde)
    if ate:
        sql += " AND data_hora<=?"
        args.append(ate)
    with Trabalho(cfg).tx() as c:
        return [dict(r) for r in c.execute(sql + " ORDER BY id DESC LIMIT ?", args + [limite])]


# --------------------------------------------------------------------------- de onde vêm as experiências
def _base(arquivo: str) -> str:
    return re.sub(r"[_\-\s]*\d[\d_\-]*$", "", Path(arquivo).stem.lower()) or Path(arquivo).stem.lower()


def registrar_execucao(cfg, r) -> None:
    """Depois de cada planilha processada: experiência de quem conferiu e handover de cada erro."""
    try:
        from robo.pipeline import REPROVADO, SUCESSO
        if r.status not in (SUCESSO, REPROVADO):
            return
        tb = Trabalho(cfg)
        nome, base = r.arquivo.name, _base(r.arquivo.name)
        gente = organizacao.por_id(cfg)
        for conf in r.quadro or []:
            pid = conf.get("id")
            if pid not in gente:
                continue
            achados = conf.get("achados") or []
            quebrou = [a for a in achados if a.startswith("não consegui concluir")]
            if quebrou:
                experiencia(cfg, pid, "erro", f"Não concluiu a conferência de {nome}", "pipeline", r.id, quebrou[0], tb)
                handover(cfg, quebrou[0], base, pid, nome, tb)
            elif achados and conf.get("bloqueia"):
                experiencia(cfg, pid, "acerto", f"Barrou {nome}: {achados[0][:150]}", "pipeline", r.id, "; ".join(achados), tb)
            elif achados:
                experiencia(cfg, pid, "aprendizado", f"Observou em {nome}: {achados[0][:150]}", "pipeline", r.id, "", tb)
            else:
                experiencia(cfg, pid, "acerto", f"Conferiu {nome} sem achados", "pipeline", r.id, "", tb)
        for e in r.relatorio.erros:
            msg = getattr(e, "mensagem", str(e))
            col = getattr(e, "coluna", "")
            texto = msg + (f" (coluna {col})" if col else "")
            hid = handover(cfg, texto, base, "validacao", ", ".join(getattr(e, "exemplos", [])[:3]), tb)
            _, resp, *_ = categorizar(texto)
            if resp in gente:
                experiencia(cfg, resp, "acerto", f"Detectou em {nome}: {msg[:150]}", "pipeline", hid, texto, tb)
        if r.id and r.relatorio.erros:
            tb.lembrar("handover_execucao", r.id, f"Erros de {nome} viraram handover", "pipeline")
        if r.status == SUCESSO:
            experiencia(cfg, "publicacao", "acerto", f"Publicou {nome} ({r.linhas_saida} linhas)", "pipeline", r.id, "", tb)
    except Exception:
        import logging
        logging.getLogger("robo").exception("Não consegui registrar a memória da execução")


def registrar_tarefa(cfg, sid: str) -> None:
    """Fim de tarefa: acerto/erro de cada executor, acerto do revisor que pegou problema e handover de cada falha."""
    tb = Trabalho(cfg)
    s = tb.solicitacao(sid)
    if not s:
        return
    for e in s["etapas"]:
        r = e["resultado"] or {}
        if e["estado"] == "concluida":
            experiencia(cfg, e["funcionario"], "acerto", f"{e['titulo']} ({s['id']})", "tarefa", sid, r.get("evidencia", ""), tb)
        elif e["estado"] == "falhou":
            experiencia(cfg, e["funcionario"], "erro", f"{e['titulo']} falhou ({s['id']})", "tarefa", sid, r.get("texto", ""), tb)
            handover(cfg, r.get("texto", "") or e["titulo"], e["ferramenta"] or "", e["funcionario"], s["titulo"], tb)
    achados = (s["revisao"] or {}).get("achados") or []
    if achados:
        if s["revisor"] and s["revisor"] != "dono":
            experiencia(cfg, s["revisor"], "acerto", f"Revisão pegou problema em {s['id']}", "revisao", sid, "; ".join(achados), tb)
        for a in achados:
            handover(cfg, a, s["modelo"] or "", s["revisor"] or "", s["titulo"], tb)


def registrar_avaliacao(cfg, registro: dict) -> None:
    """Resultado das provas técnicas (estratégia → avaliar_todos) entra na memória de cada um."""
    tb = Trabalho(cfg)
    for p in registro.get("pessoas") or []:
        if p["aprovado"]:
            experiencia(cfg, p["id"], "treinamento", f"Aprovado nas provas ({p['acertos']}/{p['total']})", "prova", "", "", tb)
        else:
            experiencia(cfg, p["id"], "erro", f"Reprovado nas provas ({p['acertos']}/{p['total']})", "prova", "",
                        "; ".join(p.get("bloqueios") or []), tb)
            for b in (p.get("bloqueios") or [])[:3]:
                handover(cfg, b, p["id"], "canal_helena", p["nome"], tb)


# --------------------------------------------------------------------------- desempenho
MINIMO_EVENTOS = 5
TAXA_MINIMA = 70.0


def situacao(acertos: int, erros: int, taxa_minima: float = TAXA_MINIMA) -> str:
    """Regra única de desempenho (política de RH): sem dados, ok, atenção ou insuficiente.
    taxa_minima é maior para quem é mais cobrado (guilda Python: 90%)."""
    n = acertos + erros
    if n < MINIMO_EVENTOS:
        return "sem_dados" if not n else ("atencao" if erros else "ok")
    taxa = 100 * acertos / n
    return "insuficiente" if taxa < taxa_minima else "atencao" if taxa < max(90, taxa_minima + 5) else "ok"


def desempenho(cfg, dias: int = 7, ate: datetime | None = None) -> list[dict]:
    """Por funcionário: acertos, erros, taxa e situação (ok / sem dados / atenção / insuficiente)."""
    ate = ate or datetime.now()
    desde = (ate - timedelta(days=dias)).isoformat(timespec="seconds")
    exps = experiencias(cfg, desde=desde, ate=ate.isoformat(timespec="seconds"), limite=100_000)
    por = {}
    for x in exps:
        d = por.setdefault(x["funcionario"], {"acertos": 0, "erros": 0, "aprendizados": 0, "ultimos_erros": []})
        if x["tipo"] == "acerto":
            d["acertos"] += 1
        elif x["tipo"] == "erro":
            d["erros"] += 1
            if len(d["ultimos_erros"]) < 3:
                d["ultimos_erros"].append(x["resumo"])
        elif x["tipo"] in ("aprendizado", "treinamento"):
            d["aprendizados"] += 1
    from robo.lideranca import EXIGENCIA as exigencia
    saida = []
    for p in organizacao.lista(cfg):
        d = por.get(p["id"], {"acertos": 0, "erros": 0, "aprendizados": 0, "ultimos_erros": []})
        n = d["acertos"] + d["erros"]
        taxa = round(100 * d["acertos"] / n, 1) if n else None
        saida.append({"id": p["id"], "nome": p["nome"], "andar": p["andar"], "grupo": p["grupo"], **d, "eventos": n,
                      "taxa": taxa, "situacao": situacao(d["acertos"], d["erros"], exigencia.get(p["id"], TAXA_MINIMA)),
                      "exigencia": exigencia.get(p["id"], TAXA_MINIMA), "pode_ser_desligado": p["grupo"] == "contratado"})
    return saida


def dossie(cfg, pid: str) -> dict | None:
    """Tudo o que a empresa sabe de uma pessoa: contrato, experiências, desempenho e handovers da área."""
    c = organizacao.contrato(pid, cfg)
    if not c:
        return None
    exps = experiencias(cfg, pid, limite=200)
    d30 = next((d for d in desempenho(cfg, 30) if d["id"] == pid), None)
    tb = Trabalho(cfg)
    with tb.tx() as conn:
        conversas = conn.execute("SELECT COUNT(*) FROM conversas WHERE funcionario=?", (pid,)).fetchone()[0]
        tarefas = conn.execute("SELECT COUNT(DISTINCT solicitacao_id) FROM etapas WHERE funcionario=?", (pid,)).fetchone()[0]
    from robo import licoes
    cad = licoes.caderno(cfg, pid)
    return {"contrato": c, "experiencias": exps, "desempenho_30d": d30, "conversas": conversas, "tarefas": tarefas,
            "caderno": {k: cad[k] for k in ("total", "por_estado", "pct_aplicada")} | {"licoes": cad["licoes"][:60]},
            "handovers_da_area": handovers(cfg, c["andar"], abertos=True, limite=30),
            "onde_pesquisa": c["fontes_conhecimento"] + ["handovers da área (regras aprendidas com erros)",
                                                         "caderno de lições (logs/trabalho.db → licoes)"],
            "onde_registra": [f"logs/trabalho.db → experiencias (funcionario = {pid})", "logs/trabalho.db → handovers",
                              f"logs/trabalho.db → licoes_funcionario (funcionario = {pid}) + registro_conhecimento",
                              f"logs/memoria/{pid}.md (dossiê exportado)"]}


def exportar_dossie(cfg, pid: str) -> Path | None:
    d = dossie(cfg, pid)
    if not d:
        return None
    c = d["contrato"]
    md = [f"# {c['nome']} — {c['cargo']}", "", f"{c['nivel_nome']} · {c['andar']}º andar ({c['nome_andar']}) · gestor: "
          f"{c['gestor_nome'] or '—'} · revisor: {c['revisor_nome']}", "", "## Escopo", ""]
    md += [f"- {r}" for r in c["responsabilidades"]] + ["", "## Ferramentas autorizadas", ""]
    md += [f"- {f}: entra {c['entradas'].get(f, '')} → sai {c['saidas'].get(f, '')}" for f in c["ferramentas"]]
    md += ["", "## Limites", ""] + [f"- {l}" for l in c["limites"]]
    md += ["", "## Onde pesquisa", ""] + [f"- {x}" for x in d["onde_pesquisa"]]
    md += ["", "## Onde registra", ""] + [f"- {x}" for x in d["onde_registra"]]
    dd = d["desempenho_30d"] or {}
    md += ["", "## Desempenho (30 dias)", "", f"Acertos {dd.get('acertos', 0)} · erros {dd.get('erros', 0)} · taxa "
           f"{dd.get('taxa') if dd.get('taxa') is not None else '—'}% · situação {dd.get('situacao', 'sem_dados')}"]
    md += ["", "## Experiências (mais recentes)", ""] + [f"- {x['data_hora'][:16]} [{x['tipo']}] {x['resumo']} ({x['origem']})"
                                                          for x in d["experiencias"][:50]]
    md += ["", "## Handovers abertos da área", ""] + [f"- {h['id']} ({h['recorrencias']}x): {h['erro']} → {h['regra']}"
                                                       for h in d["handovers_da_area"]]
    cad = d["caderno"]
    md += ["", f"## Caderno de lições ({cad['total']} · {cad['pct_aplicada']}% aplicadas)", "",
           " · ".join(f"{k}: {v}" for k, v in cad["por_estado"].items()), ""]
    md += [f"- [{l['estado']}] {l['titulo']} (v{l['versao']}, {l['origem_tipo']})" for l in cad["licoes"][:40]]
    pasta = Path(cfg.logs) / "memoria"
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / f"{pid}.md"
    arq.write_text("\n".join(md) + "\n", encoding="utf-8")
    return arq


# --------------------------------------------------------------------------- espelho no PostgreSQL
TABELAS_PG = {
    "experiencias": ("id BIGINT PRIMARY KEY, funcionario TEXT NOT NULL, data_hora TIMESTAMP, tipo TEXT, resumo TEXT, "
                     "detalhe TEXT, origem TEXT, referencia TEXT, andar INT",
                     ["id", "funcionario", "data_hora", "tipo", "resumo", "detalhe", "origem", "referencia", "andar"]),
    "handovers": ("id TEXT PRIMARY KEY, andar INT, area TEXT, responsavel TEXT, detectado_por TEXT, erro TEXT, causa TEXT, "
                  "regra TEXT, como_verificar TEXT, exemplo TEXT, recorrencias INT, estado TEXT, backlog_id TEXT, "
                  "criado_em TIMESTAMP, ultima_ocorrencia TIMESTAMP, atualizado_em TIMESTAMP",
                  ["id", "andar", "area", "responsavel", "detectado_por", "erro", "causa", "regra", "como_verificar", "exemplo",
                   "recorrencias", "estado", "backlog_id", "criado_em", "ultima_ocorrencia", "atualizado_em"]),
    # caderno de lições (robo/licoes.py) e erros de sistema (robo/erros.py): também ficam no banco da empresa
    "licoes": ("id TEXT PRIMARY KEY, origem_tipo TEXT, origem_ref TEXT, versao INT, substitui TEXT, andar INT, publico TEXT, "
               "titulo TEXT, conteudo TEXT, pergunta TEXT, como_aplicar TEXT, autor TEXT, criada_em TIMESTAMP, arquivada INT, "
               "motivo_arquivo TEXT",
               ["id", "origem_tipo", "origem_ref", "versao", "substitui", "andar", "publico", "titulo", "conteudo", "pergunta",
                "como_aplicar", "autor", "criada_em", "arquivada", "motivo_arquivo"]),
    "licoes_funcionario": ("licao_id TEXT, funcionario TEXT, estado TEXT, atribuida_em TIMESTAMP, estudada_em TIMESTAMP, "
                           "avaliada_em TIMESTAMP, aplicada_em TIMESTAMP, evidencia TEXT, tentativas INT, "
                           "PRIMARY KEY (licao_id, funcionario)",
                           ["licao_id", "funcionario", "estado", "atribuida_em", "estudada_em", "avaliada_em", "aplicada_em",
                            "evidencia", "tentativas"]),
    "registro_conhecimento": ("id BIGINT PRIMARY KEY, data_hora TIMESTAMP, tipo TEXT, ref TEXT, quem TEXT, dados TEXT, "
                              "hash_anterior TEXT, hash TEXT",
                              ["id", "data_hora", "tipo", "ref", "quem", "dados", "hash_anterior", "hash"]),
    "erros_sistema": ("id BIGINT PRIMARY KEY, impressao TEXT, primeira TIMESTAMP, ultima TIMESTAMP, ocorrencias INT, modulo TEXT, "
                      "funcao TEXT, tipo TEXT, mensagem TEXT, traceback_primeiro TEXT, traceback_ultimo TEXT, handover_id TEXT, "
                      "estado TEXT",
                      ["id", "impressao", "primeira", "ultima", "ocorrencias", "modulo", "funcao", "tipo", "mensagem",
                       "traceback_primeiro", "traceback_ultimo", "handover_id", "estado"]),
}
CHAVE_PG = {"licoes_funcionario": ["licao_id", "funcionario"]}
# tabelas só de inclusão: no PostgreSQL a linha já copiada NUNCA é sobrescrita (adulterar o SQLite não "conserta" a cópia)
IMUTAVEIS_PG = {"experiencias", "registro_conhecimento"}
# demais registros copiados com as colunas do próprio SQLite (tipos simples); o que não existir ainda é pulado
ESPELHO_EXTRA = {
    "boas_praticas": "atualiza", "memoria": "imutavel", "handover_eventos": "imutavel", "reunioes": "atualiza",
    "laboratorio_exercicios": "imutavel", "interacoes": "imutavel", "rotinas_execucoes": "imutavel",
    "propostas_regra": "atualiza", "regras_aprendidas": "atualiza", "uso_ferramentas": "imutavel",
    "sala_eventos": "imutavel", "salas_encerradas": "imutavel", "licoes_uso": "imutavel", "auditorias": "imutavel",
    "eventos": "imutavel", "mensagens": "imutavel", "laboratorio_medidas": "imutavel",
    # registro total (robo/registro_total.py) e demais registros só de inserção
    "logs_sistema": "imutavel", "canal_mensagens": "imutavel", "arquivos_linhas": "imutavel", "arquivos_versoes": "imutavel",
    "treino_tentativas": "imutavel", "treino_niveis_eventos": "imutavel", "backups_registro": "imutavel",
    "decisoes_eventos": "imutavel", "rh_movimentos": "imutavel", "rh_ciclos": "imutavel", "alcadas_decisoes": "imutavel",
    "vigia_eventos": "imutavel", "ideias_registro": "imutavel", "paineis_versoes": "imutavel", "paineis_planilhas": "imutavel",
    "aprendizados": "imutavel", "aprendizados_uso": "imutavel", "aprendizados_replay": "imutavel", "dialogo_ciclos": "imutavel", "demandas_ciclos": "imutavel", "demandas_registro": "imutavel", "telegram_mensagens": "imutavel", "telegram_vinculos": "imutavel",
    "demandas_avaliacoes": "imutavel",
    "voz_falas": "imutavel", "cobertura_persistencia": "imutavel",
    "caixa_dono_eventos": "imutavel", "caixa_dono_sugestoes": "imutavel", "jornada_execucoes": "imutavel",
    "ml_datasets": "imutavel", "ml_experimentos": "imutavel", "ml_modelos": "imutavel", "ml_modelos_eventos": "imutavel",
    "ml_inferencias": "imutavel", "tempo_turnos": "imutavel", "entregas": "imutavel",
}
# Toda tabela do trabalho.db vai para o PostgreSQL (inclusive as criadas no futuro): a que não está acima é copiada
# como "atualiza" (o estado mais novo substitui). "imutavel" = a cópia do banco nunca é sobrescrita.


def sincronizar_postgres(cfg) -> dict:
    """Copia a memória (experiências, handovers, lições, cadeia de registros e erros de sistema) para o schema de controle
    do PostgreSQL (padrão: robo).
    O SQLite continua sendo a fonte: funciona com o banco desligado e nada se perde; quando o banco volta, a cópia
    alcança. Tudo numa transação: ou entra tudo, ou nada."""
    if not cfg.banco.get("habilitado"):
        return {"ok": False, "motivo": "PostgreSQL não habilitado nas Configurações (a memória segue no SQLite local)"}
    from psycopg import sql
    from robo.banco import Banco
    b = Banco(cfg.banco, cfg.base)
    schema = b.schemas["controle"]
    from robo import erros, licoes
    tb = licoes._tb(cfg)
    erros._tb(cfg)
    copiados = {}
    b.criar_banco_se_preciso()  # 1º dia: a cópia pode rodar antes da 1ª carga criar o banco
    with b.conectar() as conn:
        with conn.transaction():
            conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
            for nome, (ddl, cols) in TABELAS_PG.items():
                tabela = sql.Identifier(schema, f"memoria_{nome}")
                conn.execute(sql.SQL("CREATE TABLE IF NOT EXISTS {} (" + ddl + ")").format(tabela))
                with tb.tx() as c:
                    linhas = [tuple(r[x] for x in cols) for r in c.execute(f"SELECT {', '.join(cols)} FROM {nome}")]
                chave = CHAVE_PG.get(nome, ["id"])
                atualizar = sql.SQL(", ").join(sql.SQL("{0} = EXCLUDED.{0}").format(sql.Identifier(x))
                                               for x in cols if x not in chave)
                comando = sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT ({}) DO UPDATE SET {}").format(
                    tabela, sql.SQL(", ").join(map(sql.Identifier, cols)), sql.SQL(", ").join(sql.Placeholder() * len(cols)),
                    sql.SQL(", ").join(map(sql.Identifier, chave)), atualizar)
                if nome in IMUTAVEIS_PG:
                    comando = sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT ({}) DO NOTHING").format(
                        tabela, sql.SQL(", ").join(map(sql.Identifier, cols)), sql.SQL(", ").join(sql.Placeholder() * len(cols)),
                        sql.SQL(", ").join(map(sql.Identifier, chave)))
                with conn.cursor() as cur:
                    cur.executemany(comando, linhas)
                copiados[nome] = len(linhas)
            copiados.update(_espelhar_extras(conn, sql, schema, tb))
    return {"ok": True, "schema": schema, **copiados}


def _espelhar_extras(conn, sql, schema: str, tb: Trabalho) -> dict:
    """Copia as demais tabelas de registro com as colunas que elas têm no SQLite.
    Tabela imutável com chave numérica única: INCREMENTAL (só as linhas com id maior que o maior já copiado) — assim a
    cópia continua leve mesmo com milhões de linhas de log. As demais: todas as linhas, com o estado mais novo."""
    tipos = {"INTEGER": "BIGINT", "REAL": "DOUBLE PRECISION"}
    feitos = {}
    with tb.tx() as c:
        existentes = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                                             "ORDER BY name")]
        estrutura = {nome: [(r[1], (r[2] or "TEXT").split()[0].upper(), r[5]) for r in c.execute(f"PRAGMA table_info({nome})")]
                     for nome in existentes if nome not in TABELAS_PG}
    for nome, info in estrutura.items():
        cols = [i[0] for i in info]
        pk = [i[0] for i in info if i[2]] or [cols[0]]
        tabela = sql.Identifier(schema, f"memoria_{nome}")
        ddl = sql.SQL(", ").join(sql.SQL("{} " + tipos.get(t, "TEXT")).format(sql.Identifier(n)) for n, t, _ in info)
        conn.execute(sql.SQL("CREATE TABLE IF NOT EXISTS {} ({}, PRIMARY KEY ({}))").format(
            tabela, ddl, sql.SQL(", ").join(map(sql.Identifier, pk))))
        for n, t, _ in info:  # tabela criada por uma versão anterior: acompanha as colunas novas (senão a cópia falha)
            conn.execute(sql.SQL("ALTER TABLE {} ADD COLUMN IF NOT EXISTS {} " + tipos.get(t, "TEXT")).format(
                tabela, sql.Identifier(n)))
        imutavel = ESPELHO_EXTRA.get(nome, "atualiza") == "imutavel" or not [x for x in cols if x not in pk]
        incremental = imutavel and len(pk) == 1 and dict((n, t) for n, t, _ in info).get(pk[0]) == "INTEGER"
        desde = None
        if incremental:
            desde = conn.execute(sql.SQL("SELECT MAX({}) FROM {}").format(sql.Identifier(pk[0]), tabela)).fetchone()[0]
        with tb.tx() as c:
            consulta = f"SELECT {', '.join(cols)} FROM {nome}"
            linhas = [tuple(r) for r in (c.execute(consulta + f" WHERE {pk[0]} > ? ORDER BY {pk[0]}", (desde,))
                                         if desde is not None else c.execute(consulta))]
            total = c.execute(f"SELECT COUNT(*) FROM {nome}").fetchone()[0]
        if imutavel:
            fim = sql.SQL("DO NOTHING")
        else:
            fim = sql.SQL("DO UPDATE SET ") + sql.SQL(", ").join(
                sql.SQL("{0} = EXCLUDED.{0}").format(sql.Identifier(x)) for x in cols if x not in pk)
        comando = sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT ({}) ").format(
            tabela, sql.SQL(", ").join(map(sql.Identifier, cols)), sql.SQL(", ").join(sql.Placeholder() * len(cols)),
            sql.SQL(", ").join(map(sql.Identifier, pk))) + fim
        if linhas:
            with conn.cursor() as cur:
                cur.executemany(comando, linhas)
        feitos[nome] = total  # linhas que a tabela tem (a cópia inclui todas; nesta rodada só subiram as novas)
    return feitos


# --------------------------------------------------------------------------- PDCA contínuo
# P (planejar) = handover aberto: causa + regra · D (fazer) = em aplicação, no backlog com responsável
# C (checar)   = aplicado: o robô verifica sozinho se o erro voltou · A (agir) = verificado → vira boa prática padronizada
FASE_PDCA = {"aberto": "P", "reaberto": "P", "em_aplicacao": "D", "aplicado": "C", "verificado": "A"}
DIAS_SEM_VOLTAR = 7


def _base_do_handover(h: dict) -> str:
    m = re.match(r"^\[([^\]]+)\]", h.get("erro") or "")
    return m.group(1) if m else ""


def checar_pdca(cfg, agora: datetime | None = None) -> dict:
    """Etapa C do PDCA, automática: handover 'aplicado' que não voltou passa a 'verificado' e vira boa prática.
    Prova de que não voltou: a mesma base foi processada com sucesso depois da correção sem repetir o erro,
    ou passaram 7 dias sem o erro. (Se o erro volta, `handover` já reabre na hora.)"""
    from robo import historico
    agora = agora or datetime.now()
    tb = Trabalho(cfg)
    hist = historico.ler(Path(cfg.logs), 3000)
    verificados = []
    for h in handovers(cfg, limite=1000):
        if h["estado"] != "aplicado":
            continue
        desde = str(h["atualizado_em"])
        base = _base_do_handover(h)
        sucesso_depois = [x for x in hist if x.get("status") == "sucesso" and _base(x.get("arquivo", "")) == base
                          and str(x.get("data_hora", "")).replace(" ", "T") >= desde] if base else []  # >=: o mesmo segundo conta
        prazo = datetime.fromisoformat(desde) + timedelta(days=DIAS_SEM_VOLTAR) <= agora
        if base:
            # erro de uma base: só uma carga aprovada DEPOIS da correção prova que não volta (tempo sozinho não prova:
            # a base pode simplesmente não ter chegado de novo)
            if not sucesso_depois:
                continue
            evidencia = f"{len(sucesso_depois)} carga(s) de {base} aprovada(s) depois da correção, sem o erro"
        else:
            # erro sem base (laboratório, rotinas, sistema): prazo + os detectores rodaram no período sem o erro voltar
            if not prazo:
                continue
            rodadas = _execucoes_desde(tb, desde)
            if not rodadas:
                continue
            evidencia = f"{DIAS_SEM_VOLTAR} dias sem o erro voltar, com {rodadas} execução(ões) de laboratório/rotinas no período"
        with tb.tx() as c:
            c.execute("UPDATE handovers SET estado='verificado', atualizado_em=? WHERE id=?", (_agora(), h["id"]))
            evento_handover(c, h["id"], "estado", "aplicado", "verificado", "pdca", evidencia)
            c.execute("INSERT INTO boas_praticas (id, handover_id, andar, area, responsavel, problema, pratica, como_verificar, "
                      "evidencia, criada_em, valida) VALUES (?,?,?,?,?,?,?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET "
                      "valida=1, evidencia=excluded.evidencia, invalidada_em=NULL, motivo_invalidacao=NULL",
                      (h["id"].replace("HO-", "BP-"), h["id"], h["andar"], h["area"], h["responsavel"], h["erro"],
                       h["regra"], h["como_verificar"], evidencia, _agora()))
        experiencia(cfg, h["responsavel"], "aprendizado", f"Boa prática padronizada: {h['regra'][:150]}", "pdca", h["id"],
                    evidencia, tb)
        verificados.append(h["id"])
    return {"verificados": verificados}


def _execucoes_desde(tb: Trabalho, desde: str) -> int:
    with tb.tx() as c:
        n = 0
        for tabela, coluna in (("laboratorio_exercicios", "data_hora"), ("rotinas_execucoes", "inicio")):
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabela,)).fetchone():
                n += c.execute(f"SELECT COUNT(*) FROM {tabela} WHERE {coluna} > ?", (desde,)).fetchone()[0]
        return n


def historico_handover(cfg, hid: str) -> list[dict]:
    with Trabalho(cfg).tx() as c:
        return [dict(r) for r in c.execute("SELECT * FROM handover_eventos WHERE handover_id=? ORDER BY id", (hid,))]


def boas_praticas(cfg, andar: int | None = None, limite: int = 200) -> list[dict]:
    sql, args = "SELECT * FROM boas_praticas", []
    if andar:
        sql += " WHERE andar=?"
        args.append(int(andar))
    with Trabalho(cfg).tx() as c:
        return [dict(r) for r in c.execute(sql + " ORDER BY criada_em DESC LIMIT ?", args + [limite])]


def resumo_pdca(cfg, andar: int | None = None) -> dict:
    fases = {"P": 0, "D": 0, "C": 0, "A": 0}
    for h in handovers(cfg, andar, limite=5000):
        fases[FASE_PDCA.get(h["estado"], "P")] += 1
    return {"planejar": fases["P"], "fazer": fases["D"], "checar": fases["C"], "agir": fases["A"],
            "boas_praticas": len(boas_praticas(cfg, andar, 5000))}
