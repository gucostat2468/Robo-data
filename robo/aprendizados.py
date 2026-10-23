"""Memória de acertos e erros: o que cada funcionário acertou e errou, com causa, correção e evidência — para aprender.

Diferença para robo/aprendizado.py (regras aprendidas com aprovação do dono): aqui é a MEMÓRIA BRUTA de cada decisão.
  - registrar(...) é chamado em todo ponto de decisão: esteira real (aprovou ou barrou), planilha sintética da fábrica,
    treino, laboratório e conversas (dialogo.py);
  - consultar(...) responde "o que eu já errei parecido" ANTES de agir — a esteira escreve isso no log da etapa;
  - replay(...) refaz os últimos erros da esteira (arquivo em Bases-Erros, em modo diagnóstico) e mede a reincidência;
  - reincidencia(...) mostra, por competência, os erros dos últimos 30 dias e quantos já têm lição;
  - semente: ~200 lições plausíveis (26 habilidades × erros típicos) para o banco não nascer vazio; ficam com
    origem='semente' e NUNCA contam como acerto real em indicador nenhum.
Tudo só de inclusão (proteger), copiado para o PostgreSQL pela rotina memoria_pg.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from robo.trabalho import Trabalho, _agora

ORIGENS = ("pipeline", "validacao", "treino", "dialogo", "laboratorio", "semente", "replay")
ESQUEMA = """
CREATE TABLE IF NOT EXISTS aprendizados (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, funcionario TEXT, competencia TEXT, nivel INTEGER, contexto TEXT,
  acao TEXT, resultado TEXT, causa TEXT, correcao TEXT, evidencia_id TEXT, origem TEXT, reaproveitado_em TEXT,
  vezes INTEGER DEFAULT 1);
CREATE INDEX IF NOT EXISTS ix_aprend_comp ON aprendizados(competencia, resultado, data_hora);
CREATE INDEX IF NOT EXISTS ix_aprend_pessoa ON aprendizados(funcionario, data_hora);
CREATE TABLE IF NOT EXISTS aprendizados_uso (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, aprendizado_id INTEGER, onde TEXT, quem TEXT);
CREATE TABLE IF NOT EXISTS aprendizados_replay (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, aprendizado_id INTEGER, arquivo TEXT, reincidiu INTEGER, detalhe TEXT);
CREATE TRIGGER IF NOT EXISTS aprendizados_sem_alterar BEFORE UPDATE ON aprendizados
BEGIN SELECT RAISE(ABORT, 'registro permanente: aprendizados não pode ser alterado'); END;
"""
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


def registrar(cfg, funcionario: str | None, competencia: str, resultado: str, *, acao: str = "", causa: str = "",
              correcao: str = "", contexto: dict | None = None, nivel: int | None = None, evidencia_id=None,
              origem: str = "pipeline") -> int:
    """resultado: acerto | erro | quase. Nunca levanta exceção para quem chamou? Levanta só se o banco falhar."""
    if resultado not in ("acerto", "erro", "quase"):
        raise ValueError(f"resultado inválido: {resultado}")
    if origem not in ORIGENS:
        raise ValueError(f"origem inválida: {origem}")
    with _tb(cfg).tx() as c:
        return c.execute(
            "INSERT INTO aprendizados (data_hora, funcionario, competencia, nivel, contexto, acao, resultado, causa, correcao, "
            "evidencia_id, origem) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (_agora(), funcionario, competencia, nivel, json.dumps(contexto or {}, ensure_ascii=False, default=str),
             acao[:500], resultado, causa[:1000], correcao[:1000], None if evidencia_id is None else str(evidencia_id),
             origem)).lastrowid


def consultar(cfg, competencia: str, contexto: dict | None = None, n: int = 5, onde: str = "", quem: str = "") -> list[dict]:
    """O que JÁ se errou parecido nessa competência (erros e 'quase', com correção primeiro). Registra o uso."""
    contexto = {k: str(v).lower() for k, v in (contexto or {}).items() if v not in (None, "")}
    with _tb(cfg).tx() as c:
        linhas = [dict(r) for r in c.execute(
            "SELECT * FROM aprendizados WHERE competencia=? AND resultado IN ('erro','quase') ORDER BY id DESC LIMIT 500",
            (competencia,))]

    def nota(x):
        try:
            ctx = {k: str(v).lower() for k, v in json.loads(x["contexto"] or "{}").items()}
        except ValueError:
            ctx = {}
        iguais = sum(1 for k, v in contexto.items() if ctx.get(k) == v)
        return (iguais, bool(x["correcao"]), x["origem"] != "semente", x["id"])
    escolhidos = sorted(linhas, key=nota, reverse=True)[:n]
    if escolhidos and onde:
        with _tb(cfg).tx() as c:
            for x in escolhidos:
                c.execute("INSERT INTO aprendizados_uso (data_hora, aprendizado_id, onde, quem) VALUES (?,?,?,?)",
                          (_agora(), x["id"], onde, quem))
    return escolhidos


def reincidencia(cfg, dias: int = 30) -> list[dict]:
    """Por competência: erros REAIS (sem semente) do período, quantos têm correção conhecida e quantos se repetiram."""
    desde = (datetime.now() - timedelta(days=dias)).isoformat(timespec="seconds")
    with _tb(cfg).tx() as c:
        return [dict(r) for r in c.execute(
            "SELECT competencia, COUNT(*) AS erros, SUM(CASE WHEN correcao <> '' THEN 1 ELSE 0 END) AS com_licao, "
            "COUNT(*) - COUNT(DISTINCT causa) AS repetidos FROM aprendizados WHERE resultado='erro' AND origem <> 'semente' "
            "AND data_hora >= ? GROUP BY competencia ORDER BY erros DESC", (desde,))]


def por_origem(cfg) -> dict:
    with _tb(cfg).tx() as c:
        return {r[0]: r[1] for r in c.execute("SELECT origem, COUNT(*) FROM aprendizados GROUP BY origem")}


# ------------------------------------------------------------------------------------------------ esteira
def _quem_barrou(mensagem: str) -> str:
    m = mensagem.lower()
    if "formato" in m or "não suportado" in m:
        return "recepcao"
    if "cabeçalho" in m or "aba" in m or "ler" in m:
        return "leitura"
    if "duplic" in m or "vazi" in m:
        return "limpeza"
    return "validacao"


def da_esteira(cfg, r, job_id=None) -> int:
    """Depois de cada planilha: erro barrado vira aprendizado de quem barrou (com causa e como corrigir); aprovação vira
    acerto das etapas. Planilha sintética (TREINO_) entra com origem 'laboratorio'."""
    from robo.historico import eh_sintetico
    origem = "laboratorio" if eh_sintetico(r.arquivo.name) else "pipeline"
    feitos = 0
    erros = [o for o in r.relatorio.ocorrencias if o.nivel == "ERRO"]
    for o in erros[:20]:
        quem = _quem_barrou(o.mensagem)
        registrar(cfg, quem, f"esteira:{quem}", "erro", acao=f"tratar {r.arquivo.name}", causa=o.mensagem,
                  correcao=_correcao_sugerida(o.mensagem), contexto={"arquivo": r.arquivo.name, "coluna": o.coluna,
                                                                      "tabela": o.tabela, "arquivo_erros": str(r.destino_original or "")},
                  evidencia_id=job_id or r.id, origem=origem)
        feitos += 1
    if not erros and r.status == "sucesso":
        registrar(cfg, "validacao", "esteira:validacao", "acerto", acao=f"tratar {r.arquivo.name}",
                  contexto={"arquivo": r.arquivo.name, "linhas": r.linhas_saida}, evidencia_id=job_id or r.id, origem=origem)
        feitos += 1
    return feitos


def _correcao_sugerida(msg: str) -> str:
    m = msg.lower()
    for chave, texto in (
            ("obrigat", "Conferir o nome da coluna obrigatória na origem; se veio com outro nome, propor sinônimo para o dono aprovar."),
            ("fora da faixa", "Conferir na origem os valores fora da faixa; não forçar a passagem (a reprovação protege o dado)."),
            ("permitid", "Ver se é grafia diferente de um valor permitido; se for, propor correção de valor."),
            ("duplic", "Identificar a chave da linha e remover cópias exatas; se não houver chave, perguntar à área."),
            ("data", "Padronizar a data (dd/mm/aaaa) e conferir datas no futuro ou antes de 2000."),
            ("formato", "Salvar em .xlsx ou .csv antes de enviar."),
            ("vazi", "Conferir se a coluna veio vazia por erro de exportação.")):
        if chave in m:
            return texto
    return "Abrir o relatório de qualidade do arquivo (Bases-Relatorios) e corrigir na origem o que a validação apontou."


# ------------------------------------------------------------------------------------------------ replay
def replay(cfg, limite: int = 20) -> dict:
    """Refaz os últimos erros REAIS da esteira (o arquivo guardado em Bases-Erros), em modo diagnóstico, e confere se o
    mesmo motivo ainda barra. Reincidência alta = a lição ainda não virou comportamento."""
    from robo.pipeline import processar_arquivo
    with _tb(cfg).tx() as c:
        erros = [dict(r) for r in c.execute(
            "SELECT * FROM aprendizados WHERE resultado='erro' AND origem='pipeline' ORDER BY id DESC LIMIT ?", (limite,))]
    testados = reincidiram = 0
    vistos = set()
    for e in erros:
        ctx = json.loads(e["contexto"] or "{}")
        arq = ctx.get("arquivo_erros")
        if not arq or arq in vistos or not Path(arq).exists():
            continue
        vistos.add(arq)
        r = processar_arquivo(arq, cfg, gravar=False)
        reincidiu = any(o.nivel == "ERRO" and o.mensagem == e["causa"] for o in r.relatorio.ocorrencias)
        testados += 1
        reincidiram += reincidiu
        with _tb(cfg).tx() as c:
            c.execute("INSERT INTO aprendizados_replay (data_hora, aprendizado_id, arquivo, reincidiu, detalhe) VALUES (?,?,?,?,?)",
                      (_agora(), e["id"], arq, int(reincidiu), e["causa"][:300]))
    return {"testados": testados, "reincidiram": reincidiram,
            "taxa_reincidencia": round(reincidiram / testados, 4) if testados else None}


# ------------------------------------------------------------------------------------------------ semente
ERROS_TIPICOS = {
    "Qualidade e validação": [
        ("CPF com dígito verificador errado", "cpf", "Validar o DV do CPF; registro com DV errado vai para Bases-Erros com a linha."),
        ("data em texto (ex.: '3 de março')", "data", "Converter a data por padrão dd/mm/aaaa e conferir as que não convertem."),
        ("nota 99 usada como 'não sabe'", "nota_nps", "Tratar 99 como não resposta e tirar da base do indicador."),
        ("coluna 100% vazia", "coluna", "Avisar a área: coluna vazia costuma ser erro de exportação."),
        ("outlier por IQR (valor 30 vezes a mediana)", "valor", "Marcar como fora do padrão e confirmar com a área antes de excluir."),
        ("e-mail no meio de texto livre", "email", "Extrair o e-mail e tratar como dado pessoal (LGPD)."),
        ("duplicata pela chave", "id", "Remover a cópia exata pela chave e registrar quantas foram removidas."),
        ("linha de Total no meio da tabela", "linha", "Remover linhas de Total e Subtotal antes de somar."),
    ],
    "Padronização": [
        ("mesma categoria escrita de jeitos diferentes (SP, São Paulo, Sao Paulo)", "categoria", "Mapear grafias para um valor só."),
        ("espaços sobrando no começo e no fim", "texto", "Aparar espaços antes de comparar ou agrupar."),
        ("número no padrão americano (1,234.56)", "valor", "Detectar o separador decimal pela coluna inteira antes de converter."),
        ("#REF! vindo de fórmula quebrada", "celula", "Tratar como vazio e avisar a área de origem."),
        ("maiúsculas e minúsculas misturadas", "texto", "Padronizar a caixa antes de agrupar."),
        ("valor com 'R$' e texto", "valor", "Remover o símbolo e converter para número com vírgula decimal."),
        ("menos no fim do número (formato SAP: 1.234,56-)", "valor", "Reconhecer o sinal no fim e converter para negativo."),
        ("'1,2 mil' escrito por extenso", "valor", "Converter 'mil' multiplicando por mil."),
    ],
    "Documentos e contato": [
        ("telefone sem DDD", "telefone", "Pedir o DDD na origem; não inventar."),
        ("CEP com 7 dígitos (zero da frente perdido)", "cep", "Recolocar o zero à esquerda e validar 8 dígitos."),
        ("CNPJ com máscara misturada", "cnpj", "Tirar a máscara, validar o DV e guardar só dígitos."),
        ("e-mail sem domínio", "email", "Marcar como inválido e devolver para correção."),
        ("telefone com +55 e sem", "telefone", "Normalizar para o mesmo padrão com DDD."),
        ("documento lido como número (perde zeros)", "documento", "Ler a coluna como texto desde o começo."),
        ("dois telefones na mesma célula", "telefone", "Separar e manter o principal."),
        ("CPF de teste (111.111.111-11)", "cpf", "Reprovar sequências repetidas."),
    ],
    "Pesquisa e Customer Insights": [
        ("escala invertida (1 = melhor)", "nota", "Confirmar a escala no questionário antes de calcular."),
        ("base pequena (n < 30) virando conclusão", "segmento", "Sinalizar base pequena e não destacar o resultado."),
        ("NPS calculado com neutros fora da base", "nps", "Neutros entram no denominador; só não somam nem subtraem."),
        ("CSAT top-2-box calculado com escala errada", "csat", "Usar as duas notas mais altas da escala do questionário."),
        ("comentário aberto em coluna de nota", "nota", "Separar texto livre da nota numérica."),
        ("resposta duplicada do mesmo respondente", "id", "Manter a mais recente pela chave do respondente."),
        ("diferença entre segmentos sem teste de significância", "segmento", "Testar a diferença (com correção de Holm)."),
        ("nota fora de 0 a 10", "nota_nps", "Barrar a nota fora da escala; não forçar a passagem."),
    ],
    "Enriquecimento": [
        ("faixa etária com limites sobrepostos", "faixa", "Definir faixas sem sobreposição (18-24, 25-34…)."),
        ("coluna calculada dividindo por zero", "coluna", "Proteger a divisão e deixar vazio quando o divisor é zero."),
        ("data extraída no formato errado", "data", "Conferir dia e mês invertidos antes de extrair."),
        ("junção de colunas com separador ambíguo", "coluna", "Usar separador que não aparece nos dados."),
        ("divisão de coluna com quantidade variável de partes", "coluna", "Tratar a falta de partes como vazio."),
        ("preenchimento de vazios com média em dado categórico", "coluna", "Preencher categórico com 'não informado'."),
        ("categoria criada por palavra-chave muito genérica", "texto", "Usar palavras-chave específicas e revisar amostra."),
        ("arredondamento antes de somar", "valor", "Somar primeiro e arredondar só no fim."),
    ],
    "Estrutura": [
        ("cabeçalho em duas linhas", "cabecalho", "Juntar as linhas de cabeçalho antes de ler."),
        ("título acima do cabeçalho", "cabecalho", "Detectar a linha real do cabeçalho."),
        ("coluna renomeada entre meses", "coluna", "Propor sinônimo para o dono aprovar."),
        ("coluna obrigatória faltando", "coluna", "Barrar e avisar a área com o nome esperado."),
        ("abas empilhadas com cabeçalhos diferentes", "aba", "Ler aba por aba e alinhar pelas colunas comuns."),
        ("rodapé de sistema no fim da planilha", "linha", "Remover rodapé (linhas sem dados nas colunas-chave)."),
        ("coluna vazia no meio da tabela", "coluna", "Ignorar coluna sem cabeçalho e sem dados."),
        ("células mescladas no cabeçalho", "cabecalho", "Repetir o valor mesclado nas colunas que ele cobre."),
    ],
    "Privacidade (LGPD)": [
        ("CPF completo exposto na saída", "cpf", "Anonimizar antes de publicar."),
        ("e-mail pessoal em base de análise", "email", "Remover ou mascarar dados pessoais que a análise não precisa."),
        ("nome completo junto com nota de pesquisa", "nome", "Separar identificação da resposta."),
        ("telefone em relatório executivo", "telefone", "Nunca levar dado pessoal para relatório executivo."),
        ("dado sensível (saúde) sem base legal", "coluna", "Barrar e perguntar ao dono a base legal."),
        ("arquivo com dados pessoais na pasta pública", "arquivo", "Mover para pasta restrita e avisar a governança."),
        ("chave de pseudonimização guardada junto", "chave", "Guardar a chave separada dos dados."),
        ("exportação para fora sem anonimizar", "arquivo", "Anonimizar antes de qualquer envio."),
    ],
}


def gerar_semente(destino: Path) -> int:
    """Gera dados/semente_aprendizado.json: cada habilidade nativa × os erros típicos da categoria dela."""
    from robo import habilidades
    itens = []
    for nome, h in habilidades.REGISTRO.items():
        for causa, coluna, correcao in ERROS_TIPICOS.get(h.categoria, []):
            itens.append({"competencia": f"habilidade:{nome}", "categoria": h.categoria, "causa": causa,
                          "correcao": correcao, "contexto": {"coluna": coluna}})
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(itens, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(itens)


def semear(cfg, arquivo: Path | None = None) -> int:
    """Importa a semente (origem='semente'). Idempotente: o que já foi semeado não entra de novo."""
    from robo.config import RAIZ_PROJETO
    arquivo = Path(arquivo or Path(RAIZ_PROJETO) / "dados" / "semente_aprendizado.json")
    if not arquivo.exists():
        gerar_semente(arquivo)
    itens = json.loads(arquivo.read_text(encoding="utf-8"))
    with _tb(cfg).tx() as c:
        ja = {(r[0], r[1]) for r in c.execute("SELECT competencia, causa FROM aprendizados WHERE origem='semente'")}
    novos = 0
    for x in itens:
        if (x["competencia"], x["causa"]) in ja:
            continue
        registrar(cfg, None, x["competencia"], "erro", causa=x["causa"], correcao=x["correcao"], contexto=x.get("contexto"),
                  origem="semente")
        novos += 1
    return novos
