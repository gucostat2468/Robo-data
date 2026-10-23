"""Voz de cada funcionário — fala natural SEM modelo de IA (determinística e conferível).

Como funciona:
  - cada pessoa tem um TOM derivado do cargo (diretor e head: executivo; gerente e coordenador: líder; especialista e
    sênior: técnico; pleno: parceiro; júnior e estagiário: aprendiz) e frases de abertura próprias;
  - cada ATO de fala (status, erro, elogio, dúvida, recusa honesta, handover, cobrança, pedido de ajuda, resposta a
    cálculo, explicação, apresentação) tem vários fechamentos;
  - a escolha do molde vem de hash(pessoa + dia + mensagem + quantas vezes ela já respondeu isso hoje): a MESMA pergunta
    em dois momentos sai com frases diferentes e os MESMOS números. Nenhum parágrafo idêntico se repete em 24 h;
  - o corpo da fala é o FATO apurado pelo robô; a voz só limpa símbolos e costura abertura e fechamento — nenhum número
    novo entra (as aberturas e os fechamentos não têm número);
  - vocabulário de robô é proibido ("Não tenho certeza do que você precisa", "Posso ajudar com:", "intenção",
    "processando").
Toda fala fica registrada em voz_falas (quem, ato, molde, hash do texto) — é o que garante a variação e a auditoria.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from pathlib import Path

from robo.trabalho import Trabalho, _agora

PROIBIDAS = [r"n[ãa]o tenho certeza do que voc[eê] precisa", r"posso ajudar com\s*:", r"\binten[çc][ãa]o\b",
             r"\bprocessando\b", r"\bcomo um modelo de linguagem\b", r"\bsou apenas um rob[ôo]\b"]
_PROIBIDAS_RE = [re.compile(p, re.IGNORECASE) for p in PROIBIDAS]

TOM_DO_NIVEL = {"diretor": "executivo", "head": "executivo", "gerente": "lider", "coordenador": "lider",
                "especialista": "tecnico", "senior": "tecnico", "pleno": "parceiro", "junior": "aprendiz",
                "estagiario": "aprendiz"}

ABERTURAS = {
    "executivo": ["Direto ao ponto:", "Resumindo para você:", "O quadro é este:", "Vou ser objetivo.", "Em poucas palavras:"],
    "lider": ["Organizei aqui para você.", "Olhei com a equipe e é isso:", "Deixa eu te situar.", "Conferi agora e te conto:",
              "Vamos lá, com os números de agora."],
    "tecnico": ["Olhei os dados e explico:", "Conferi na fonte.", "Pelo que está registrado,", "Vou te mostrar o que achei.",
                "Fiz a conta por conta própria e bate:"],
    "parceiro": ["Dei uma olhada aqui.", "Te conto o que vi.", "Conferi agora mesmo.", "Olha só o que está registrado.",
                 "Vi isso há pouco."],
    "aprendiz": ["Conferi com cuidado e vi isto:", "Olhei os registros e encontrei isto:", "Deixa eu te mostrar o que vi:",
                 "Fiz a verificação e é isto:", "Pelo que eu levantei,"],
}
FECHAMENTOS = {
    "status": ["Se quiser, detalho por arquivo.", "Qualquer mudança eu aviso aqui.", "Sigo acompanhando.", "",
               "Se algo mudar na próxima hora, você fica sabendo por mim."],
    "erro": ["O arquivo está em Bases-Erros esperando correção.", "Corrigindo na origem e reenviando, a esteira trata de novo.",
             "Se quiser, eu te digo exatamente qual linha corrigir.", "Já deixei registrado para a equipe aprender com isso."],
    "elogio": ["Bom trabalho de todo mundo.", "Isso foi time.", "Vale registrar como boa prática.", ""],
    "duvida": ["Me diz isso e eu respondo com os dados de hoje.", "Com essa resposta eu consigo te ajudar de verdade.",
               "Prefiro perguntar a te dar um número errado."],
    "recusa": ["Não vou chutar um número que eu não tenho.", "Assim que o dado existir, eu te mostro.",
               "Prefiro ser honesto a inventar."],
    "handover": ["Passei para quem cuida disso e fico de olho.", "Já está com a pessoa certa.", "Registrei a passagem com o motivo."],
    "cobranca": ["Preciso disso para seguir.", "Sem isso a fila fica parada.", "Me avisa quando puder."],
    "pedido_ajuda": ["Pode me dar uma mão?", "Quem souber, me chama.", "Aprendo rápido se alguém me mostrar uma vez."],
    "resposta_calculo": ["A conta está registrada e dá para conferir.", "Se quiser, faço o mesmo recorte por outra coluna.",
                         "Usei só as bases publicadas.", ""],
    "explicacao": ["Se quiser, te mostro com um exemplo da sua base.", "Qualquer dúvida, é só perguntar de novo.", "",
                   "Isso está no conhecimento da empresa, com a fonte."],
    "apresentacao": ["Me pergunte algo da minha área que eu respondo com os dados de hoje.",
                     "Pode contar comigo para isso.", "Estou por aqui."],
}
# atos sociais têm abertura própria (não faz sentido "conferi os dados" antes de se apresentar ou de perguntar)
ABERTURAS_DO_ATO = {"apresentacao": ["Oi!", "Olá!", "Oi, tudo bem?", "Prazer em falar com você."],
                    "duvida": ["", "Quero te responder certo.", "Deixa eu entender melhor."],
                    "pedido_ajuda": ["Gente,", "Pessoal,", "Preciso de uma ajuda."]}
SEM_PROBLEMA = re.compile(r"^(nenhum|nenhuma|nada|tudo certo|sem problema)", re.IGNORECASE)
ATO_DA_INTENCAO = {"status": "status", "erros": "erro", "sprint": "status", "ideias": "explicacao", "banco": "status",
                   "equipe": "explicacao", "ajuda": "explicacao", "saudacao": "apresentacao", "conhecimento": "explicacao",
                   "manual": "explicacao", "calculo": "resposta_calculo", "amostra": "resposta_calculo",
                   "apresentacao": "apresentacao", "nao_entendi": "duvida"}

ESQUEMA = """CREATE TABLE IF NOT EXISTS voz_falas (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, funcionario TEXT, ato TEXT, chave TEXT, molde TEXT, hash_texto TEXT,
  natureza TEXT);
CREATE INDEX IF NOT EXISTS ix_voz_falas ON voz_falas(funcionario, data_hora);"""
_prontos: set[str] = set()


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    chave = str(Path(cfg.logs).resolve())
    if chave not in _prontos:
        from robo.trabalho import proteger
        with tb.tx() as c:
            c.executescript(ESQUEMA)
            proteger(c)
        _prontos.add(chave)
    return tb


def tom_de(pid: str, cfg=None) -> str:
    from robo import organizacao
    try:
        pessoa = organizacao.por_id(cfg).get(pid) if cfg is not None else None
        return TOM_DO_NIVEL.get(organizacao.nivel_de(pid, pessoa), "parceiro")
    except Exception:
        return "parceiro"


def limpar(texto: str) -> str:
    """Fala de gente: sem marcadores, sem # e *, sem barras verticais, sem setas, frases completas."""
    t = str(texto or "")
    t = re.sub(r"[#*•▪►]+", " ", t)
    t = re.sub(r"\s*\|\s*", ". ", t)
    t = re.sub(r"\s*→\s*", " para ", t)
    t = re.sub(r"\s+—\s+", ", ", t)
    t = _ponto_e_virgula_fora_de_parenteses(t)
    t = re.sub(r"(?m)^\s*[-–]\s+", "", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    t = re.sub(r"\.\s*\.", ".", t)
    t = re.sub(r"\s+([,.!?])", r"\1", t)
    # primeira letra de cada frase em maiúscula (depois de trocar ';' e '|' por ponto), fora de parênteses
    t = re.sub(r"([.!?]\s+)([a-zà-ú])", lambda m: m.group(1) + m.group(2).upper() if t[:m.start()].count("(") <= t[:m.start()].count(")") else m.group(0), t)
    if t and t[-1] not in ".!?…":
        t += "."
    for r in _PROIBIDAS_RE:
        t = r.sub("", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def _ponto_e_virgula_fora_de_parenteses(t: str) -> str:
    """'A; B' vira 'A. B', mas =PROCX(a; b; c) fica intacto (no Excel em português o ; separa argumentos)."""
    saida, nivel, i = [], 0, 0
    while i < len(t):
        ch = t[i]
        nivel += 1 if ch == "(" else -1 if ch == ")" and nivel > 0 else 0
        if ch == ";" and nivel == 0:
            saida.append(".")
            while i + 1 < len(t) and t[i + 1] == " ":
                i += 1
            saida.append(" ")
        else:
            saida.append(ch)
        i += 1
    return "".join(saida)


def tem_vocabulario_de_robo(texto: str) -> bool:
    return any(r.search(texto or "") for r in _PROIBIDAS_RE)


def _indice(*partes) -> int:
    return int(hashlib.sha256("|".join(str(p) for p in partes).encode()).hexdigest()[:12], 16)


def compor(cfg, pid: str, ato: str, conteudo: str, chave: str | None = None, natureza: str = "regra") -> dict:
    """Costura abertura + fato + fechamento na voz da pessoa. Devolve {texto, molde, tom}. Registra a fala."""
    tom = tom_de(pid, cfg)
    corpo = limpar(conteudo)
    chave = chave or hashlib.sha256(corpo.encode()).hexdigest()[:16]
    dia = datetime.now().strftime("%Y-%m-%d")
    tb = _tb(cfg)
    with tb.tx() as c:
        vezes = c.execute("SELECT COUNT(*) FROM voz_falas WHERE funcionario=? AND chave=? AND data_hora >= ?",
                          (pid, chave, dia)).fetchone()[0]
        desde = (datetime.now() - timedelta(hours=24)).isoformat(timespec="seconds")
        recentes = {r[0] for r in c.execute("SELECT hash_texto FROM voz_falas WHERE funcionario=? AND data_hora >= ?",
                                            (pid, desde))}
    if ato == "erro" and SEM_PROBLEMA.match(corpo):
        ato = "status"  # "nenhum arquivo barrado" não pede fechamento de erro
    aberturas = ABERTURAS_DO_ATO.get(ato) or ABERTURAS[tom]
    fechamentos = FECHAMENTOS.get(ato) or FECHAMENTOS["explicacao"]
    base = _indice(pid, dia, chave, vezes)
    texto, molde = corpo, "sem_molde"
    for passo in range(len(aberturas) * len(fechamentos)):
        i = base + passo
        a, f = aberturas[i % len(aberturas)], fechamentos[(i // len(aberturas)) % len(fechamentos)]
        miolo = corpo[:1].lower() + corpo[1:] if a.endswith(",") and corpo[1:2].islower() else corpo
        candidato = " ".join(x for x in (a, miolo, f) if x).strip()
        candidato = re.sub(r"\s{2,}", " ", candidato)
        h = hashlib.sha256(candidato.encode()).hexdigest()[:16]
        texto, molde = candidato, f"{tom}:{i % len(aberturas)}/{ato}:{(i // len(aberturas)) % len(fechamentos)}"
        if h not in recentes:
            break
    with tb.tx() as c:
        c.execute("INSERT INTO voz_falas (data_hora, funcionario, ato, chave, molde, hash_texto, natureza) VALUES (?,?,?,?,?,?,?)",
                  (_agora(), pid, ato, chave, molde, hashlib.sha256(texto.encode()).hexdigest()[:16], natureza))
    return {"texto": texto, "molde": molde, "tom": tom}


def duvida_honesta(pergunta: str) -> str:
    """Quando não há fato para responder: uma frase honesta e uma pergunta de esclarecimento (nunca um menu)."""
    vazias = {"o", "a", "os", "as", "de", "do", "da", "dos", "das", "e", "que", "um", "uma", "para", "por", "com", "me", "se",
              "em", "no", "na", "eu", "voce", "você", "qual", "quais", "como", "quanto", "isso", "esse", "essa", "tem", "ta", "tá"}
    palavras = [p for p in re.findall(r"[\wÀ-ú]+", str(pergunta or "").lower()) if p not in vazias and len(p) > 2][:4]
    if palavras:
        tema = ", ".join(palavras[:-1]) + (" e " if len(palavras) > 1 else "") + palavras[-1]
        return (f"Não achei nos registros de hoje nada que responda sobre {tema}. "
                f"Pode me dizer em uma frase o que você quer saber sobre isso?")
    return "Não consegui entender a sua mensagem. Pode me dizer em uma frase o que você quer saber?"
