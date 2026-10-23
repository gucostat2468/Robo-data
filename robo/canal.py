"""Canal da equipe: conversa com o dono, sprints de 15 dias e ideias — 100% offline.

Nada aqui usa internet nem API de IA. Quem "entende" a mensagem é um roteador de intenções feito em Python:
  1. normaliza o texto (minúsculas, sem acento);
  2. pontua cada intenção (status do dia, erros, sprint, ideias, banco, equipe...) e cada verbete da base de
     conhecimento (Excel, Power BI/DAX, pesquisa, trade marketing) pelas palavras-chave encontradas;
  3. quem tem a maior pontuação responde, com dados reais do robô quando a pergunta é sobre o trabalho.
Quando nada bate com segurança, a resposta é honesta: "não entendi", com sugestões do que perguntar.

Armazenamento: logs/canal/mensagens.jsonl (uma mensagem por linha) e logs/canal/estado.json.
"""

from __future__ import annotations

import json
import math
import re
import threading
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

from robo import historico


def _num_br(v) -> float:
    """Número do histórico (gravado com vírgula decimal: '0,3')."""
    try:
        return float(str(v or 0).replace(".", "").replace(",", ".")) if "," in str(v or "") else float(v or 0)
    except ValueError:
        return 0.0

CANAIS = {
    "geral": "Geral (tudo e todos)",
    "engenharia": "Engenharia de dados (1º andar)",
    "analise": "Análise e qualidade (2º andar)",
    "excel": "Sala Excel (3º andar)",
    "lideranca": "Liderança e produção",
    "banco": "PostgreSQL",
    "rh": "RH e contratações",
    "ideias": "Ideias e evolução da plataforma",
    "ti": "TI, DevOps, infraestrutura e segurança (5º andar)",
}

EQUIPE_CANAL = [
    {"id": "canal_nina", "nome": "Nina", "papel": "Assistente do canal", "cor": "#0369A1", "andar": 4,
     "descricao": "Lê cada mensagem sua, entende o que você precisa e chama a pessoa certa para responder. "
                  "Quando não tem certeza, diz que não entendeu e sugere o que perguntar — nunca inventa."},
    {"id": "canal_iara", "nome": "Iara", "papel": "Ideias e evolução da plataforma", "cor": "#EA580C", "andar": 4,
     "descricao": "Olha os números do robô e propõe melhorias concretas, uma de cada vez, sempre com o motivo "
                  "(o dado que a fez pensar nisso) e o primeiro passo."},
    {"id": "canal_helena", "nome": "Helena", "papel": "RH e desenvolvimento da equipe", "cor": "#BE185D", "andar": 4,
     "descricao": "Conduz o processo seletivo técnico, acompanha níveis (estagiário a especialista) e conta, na sprint, "
                  "quem está aprovado, quem está em observação e quem precisa de treinamento."},
]

DONO = {"id": "dono", "nome": "Você"}
DIAS_SPRINT = 15
_trava = threading.Lock()


# ----------------------------------------------------------------------------- utilidades
def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9%.,=()\-/ ]", " ", t)).strip()


def _pasta(cfg) -> Path:
    p = Path(cfg.logs) / "canal"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _num(v) -> str:
    return f"{int(v):,}".replace(",", ".")


def pessoas() -> dict:
    """id -> {nome, papel, canal} de todo mundo que pode falar no canal (registro único + dono)."""
    from robo import organizacao
    p = {x["id"]: {"nome": x["nome"], "papel": x["papel"], "canal": x["canal"]} for x in organizacao.lista()}
    p[DONO["id"]] = {"nome": DONO["nome"], "papel": "Dono da empresa", "canal": "geral"}
    return p


# ----------------------------------------------------------------------------- armazenamento
class Canal:
    def __init__(self, cfg):
        self.cfg = cfg
        self.pasta = _pasta(cfg)
        self.arquivo = self.pasta / "mensagens.jsonl"
        self.arquivo_estado = self.pasta / "estado.json"

    # -- estado
    def estado(self) -> dict:
        try:
            return json.loads(self.arquivo_estado.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def salvar_estado(self, e: dict) -> None:
        tmp = self.arquivo_estado.with_suffix(".tmp")
        tmp.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.arquivo_estado)

    # -- mensagens
    def ler(self) -> list[dict]:
        if not self.arquivo.exists():
            return []
        msgs = []
        with open(self.arquivo, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha:
                    try:
                        msgs.append(json.loads(linha))
                    except json.JSONDecodeError:
                        continue  # linha corrompida (ex.: desligou no meio da gravação) não derruba o canal
        return msgs

    def postar(self, autor: str, texto: str, canal: str = "geral", tipo: str = "mensagem", **extra) -> dict:
        canal = canal if canal in CANAIS else "geral"
        quem = pessoas().get(autor, {"nome": autor, "papel": ""})
        with _trava:
            e = self.estado()
            seq = int(e.get("seq", 0)) + 1
            e["seq"] = seq
            msg = {"id": seq, "data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "canal": canal,
                   "autor": autor, "nome": quem["nome"], "papel": quem.get("papel", ""), "tipo": tipo,
                   "texto": str(texto).strip(), **extra}
            with open(self.arquivo, "a", encoding="utf-8") as f:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")
            self.salvar_estado(e)
        return msg

    def listar(self, canal: str = "", autor: str = "", tipo: str = "", busca: str = "", dias: int = 0,
               desde_id: int = 0, limite: int = 300) -> list[dict]:
        msgs = self.ler()
        if canal and canal != "geral":
            msgs = [m for m in msgs if m["canal"] == canal]
        if autor:
            msgs = [m for m in msgs if m["autor"] == autor]
        if tipo:
            msgs = [m for m in msgs if m["tipo"] == tipo]
        if busca:
            b = normalizar(busca)
            msgs = [m for m in msgs if b in normalizar(m["texto"]) or b in normalizar(m["nome"])]
        if dias:
            corte = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d %H:%M:%S")
            msgs = [m for m in msgs if m["data_hora"] >= corte]
        if desde_id:
            msgs = [m for m in msgs if m["id"] > desde_id]
        return msgs[-limite:]

    # -- conversa com o dono
    def perguntar(self, texto: str, canal: str = "geral") -> list[dict]:
        texto = str(texto or "").strip()[:2000]
        if not texto:
            return []
        enviada = self.postar(DONO["id"], texto, canal, "pergunta")
        respostas = [self.postar(r["autor"], r["texto"], canal, "resposta", pergunta=enviada["id"], intencao=r["intencao"],
                                 natureza=r.get("natureza", "regra"), **({"modelo": r["modelo"]} if r.get("modelo") else {}))
                     for r in responder(texto, self.cfg)]
        return [enviada, *respostas]

    # -- acontecimentos do robô viram mensagens das pessoas que trabalharam
    def sincronizar(self) -> int:
        """Posta no canal o que aconteceu desde a última vez (aprovações, reprovações, análises, entregas Excel)."""
        e = self.estado()
        vistos = set(e.get("execucoes_postadas") or [])
        linhas = list(reversed(historico.ler(self.cfg.logs, 300)))  # mais antigas primeiro
        primeira_vez = "execucoes_postadas" not in e
        if primeira_vez:
            linhas = linhas[-10:]  # ao ligar o canal pela 1ª vez, não inunda com o passado
        novos = 0
        for h in linhas:
            i = h.get("id") or ""
            if not i or i in vistos:
                continue
            exe = historico.ler_execucao(self.cfg.logs, i) or {}
            for autor, canal, texto in _mensagens_execucao(h, exe):
                self.postar(autor, texto, canal, "acontecimento", execucao=i)
            vistos.add(i)
            novos += 1
        e = self.estado()
        e["execucoes_postadas"] = sorted(vistos)[-2000:]
        self.salvar_estado(e)
        self._sprint_automatica()
        _boletim_automatico(self)
        return novos

    # -- sprints
    def inicio_sprints(self) -> date:
        e = self.estado()
        if e.get("inicio_sprints"):
            return date.fromisoformat(e["inicio_sprints"])
        hist = historico.ler(self.cfg.logs)
        datas = [h["data_hora"][:10] for h in hist if h.get("data_hora")]
        inicio = date.fromisoformat(min(datas)) if datas else date.today()
        e["inicio_sprints"] = inicio.isoformat()
        self.salvar_estado(e)
        return inicio

    def sprint_de(self, dia: date) -> tuple[int, date, date]:
        inicio = self.inicio_sprints()
        n = max(0, (dia - inicio).days) // DIAS_SPRINT
        ini = inicio + timedelta(days=n * DIAS_SPRINT)
        return n + 1, ini, ini + timedelta(days=DIAS_SPRINT - 1)

    def _sprint_automatica(self) -> None:
        numero, ini, _ = self.sprint_de(date.today())
        e = self.estado()
        if numero > 1 and int(e.get("ultima_sprint_reportada", 0)) < numero - 1:
            self.publicar_sprint(self.sprint_de(ini - timedelta(days=1))[0], parcial=False)

    def publicar_sprint(self, numero: int | None = None, parcial: bool | None = None) -> list[dict]:
        hoje = date.today()
        atual = self.sprint_de(hoje)[0]
        numero = numero or atual
        ini = self.inicio_sprints() + timedelta(days=(numero - 1) * DIAS_SPRINT)
        fim = ini + timedelta(days=DIAS_SPRINT - 1)
        parcial = (numero == atual) if parcial is None else parcial
        falas = relatorio_sprint(self.cfg, ini, min(fim, hoje), numero, parcial)
        postadas = [self.postar(a, t, c, "sprint", sprint=numero) for a, c, t in falas]
        if not parcial:
            e = self.estado()
            e["ultima_sprint_reportada"] = max(int(e.get("ultima_sprint_reportada", 0)), numero)
            self.salvar_estado(e)
        return postadas


# ----------------------------------------------------------------------------- acontecimentos
def _mensagens_execucao(h: dict, exe: dict) -> list[tuple[str, str, str]]:
    arq = h.get("arquivo") or exe.get("arquivo") or "arquivo"
    ocorr = exe.get("ocorrencias") or []
    msgs = []
    if h.get("status") == "sucesso":
        destino = "Bases-Tratadas" + (" e no PostgreSQL" if exe.get("tabelas_banco") else "")
        msgs.append(("publicacao", "engenharia",
                     f"Publiquei {arq}: {_num(h.get('linhas_saida') or 0)} linha(s) prontas em {destino}. "
                     f"Conferência do supervisor e checklist de produção aprovados."))
        removidas = int(h.get("linhas_entrada") or 0) - int(h.get("linhas_saida") or 0)
        if removidas > 0:
            msgs.append(("limpeza", "engenharia",
                         f"Em {arq}, tirei {_num(removidas)} linha(s) — cada uma com o motivo registrado no relatório de qualidade."))
        analise = exe.get("analise") or {}
        resumo = [r.get("resumo_executivo") if isinstance(r, dict) else r for r in (analise.get("resumo") or [])]
        resumo = [str(x).strip() for x in resumo if x and str(x).strip()]
        if analise.get("manchete"):
            msgs.append(("ger_analise", "analise", f"Manchete de {arq}: {analise['manchete']}."))
        if resumo:
            msgs.append(("analise_relator", "analise", f"Resumo de {arq}: " + " ".join(str(x).strip() for x in resumo[:3])))
        ressalvas = (exe.get("checklist_analise") or {}).get("ressalvas") or []
        if ressalvas:
            msgs.append(("coord_analise", "analise", f"Revisei {arq} com ressalva(s): {'; '.join(ressalvas)}."))
        excel = exe.get("excel") or {}
        if excel:
            msgs.append(("excel_supervisor", "excel",
                         f"Assinei a entrega {Path(excel['arquivo']).name}: {excel.get('conferencias', 0)} conferência(s) de "
                         f"fórmula contra o Python. Abra a aba Resumo e confira o status no topo."))
    elif h.get("status") == "reprovado":
        erros = [o for o in ocorr if o.get("nivel") == "ERRO"]
        motivo = erros[0]["mensagem"] if erros else "veja o relatório de erros"
        autor = "supervisor" if "Supervisor" in motivo else "dba" if "DBA" in motivo else "validacao"
        canal = "lideranca" if autor == "supervisor" else "banco" if autor == "dba" else "engenharia"
        msgs.append((autor, canal, f"Barrei {arq} ({len(erros) or h.get('erros') or 1} erro(s)). Principal: {motivo}. "
                                   f"O arquivo está em Bases-Erros com o _ERROS.txt explicando o que corrigir."))
    return msgs


# ----------------------------------------------------------------------------- sprint de 15 dias
def _periodo(cfg, ini: date, fim: date) -> tuple[list[dict], list[dict]]:
    hist = [h for h in historico.ler(cfg.logs) if ini.isoformat() <= (h.get("data_hora") or "")[:10] <= fim.isoformat()]
    exes = [historico.ler_execucao(cfg.logs, h.get("id") or "") or {} for h in hist[:500]]
    return hist, exes


def relatorio_sprint(cfg, ini: date, fim: date, numero: int, parcial: bool) -> list[tuple[str, str, str]]:
    """Cada pessoa conta, de forma direta e sincera, o que fez, o que foi bom, o que travou e o que está no backlog."""
    hist, exes = _periodo(cfg, ini, fim)
    ok = [h for h in hist if h.get("status") == "sucesso"]
    ruim = [h for h in hist if h.get("status") == "reprovado"]
    soma = lambda lista, campo: sum(int(h.get(campo) or 0) for h in lista)
    periodo = f"{ini.strftime('%d/%m')} a {fim.strftime('%d/%m')}"
    titulo = f"Sprint {numero} ({periodo}{', parcial' if parcial else ''})"
    falas: list[tuple[str, str, str]] = []

    def fala(autor, canal, feito, bom="", travou="", backlog=""):
        partes = [f"{titulo} — Feito: {feito}"]
        partes += [f"Bom: {bom}"] if bom else []
        partes += [f"Travou: {travou}"] if travou else []
        partes += [f"Backlog: {backlog}"] if backlog else []
        falas.append((autor, canal, " · ".join(partes)))

    if not hist:
        fala("canal_nina", "geral", "nenhum arquivo chegou em Bases-Limpeza neste período.",
             travou="sem planilhas não há o que tratar — se você esperava arquivos, confira se o OneDrive está sincronizando.")
        falas.extend(_ideias_falas(cfg, hist, exes, titulo))
        return falas

    erros_por_motivo: dict[str, int] = {}
    for exe in exes:
        for o in exe.get("ocorrencias") or []:
            if o.get("nivel") == "ERRO":
                chave = re.sub(r"\d+", "N", str(o.get("mensagem", "")))[:90]
                erros_por_motivo[chave] = erros_por_motivo.get(chave, 0) + 1
    top = sorted(erros_por_motivo.items(), key=lambda x: -x[1])[:2]
    taxa = len(ok) / len(hist) * 100

    fala("recepcao", "engenharia", f"recebi {_num(len(hist))} arquivo(s): {_num(len(ok))} aprovados e {_num(len(ruim))} barrados "
                                   f"({taxa:.0f}% de aprovação).",
         bom="nenhum arquivo foi lido pela metade: só entra o que terminou de sincronizar." if hist else "")
    removidas = soma(ok, "linhas_entrada") - soma(ok, "linhas_saida")
    fala("limpeza", "engenharia", f"tratei {_num(soma(ok, 'linhas_entrada'))} linha(s) e tirei {_num(removidas)} "
                                  f"(vazias, duplicadas ou de total), todas com motivo registrado.")
    fala("validacao", "engenharia", f"barrei {_num(len(ruim))} arquivo(s).",
         bom="nada com erro chegou em Bases-Tratadas." if ruim else "todos os arquivos vieram dentro das regras.",
         travou=("motivos mais frequentes: " + "; ".join(f"{m} ({n}x)" for m, n in top)) if top else "",
         backlog="combinar com quem gera esses arquivos a correção na origem." if top else "")
    com_banco = [e for e in exes if e.get("tabelas_banco")]
    if cfg.banco.get("habilitado"):
        fala("banco", "banco", f"carreguei {_num(len(com_banco))} base(s) no PostgreSQL (bruto → tratado → analítico).")
        fala("dba", "banco", f"reconciliei {_num(len(com_banco))} carga(s) antes do commit.",
             bom="nenhuma carga ficou pela metade: o que não bate é desfeito inteiro.")
    else:
        fala("banco", "banco", "deixei as tabelas e os modelos SQL prontos, mas não carreguei nada.",
             travou="o PostgreSQL ainda não está configurado.",
             backlog="instalar o PostgreSQL e preencher Configurações → Banco de dados no painel.")
    barrados_sup = sum(1 for e in exes for o in (e.get("ocorrencias") or []) if "Supervisor" in str(o.get("mensagem")))
    fala("supervisor", "lideranca", f"conferi {_num(len(hist))} arquivo(s) antes da publicação; barrei {_num(barrados_sup)}.",
         bom="a conciliação de linhas fechou em todos os aprovados.")
    liberados = sum(1 for e in exes if (e.get("checklist_producao") or {}).get("liberado"))
    fala("coord_engenharia", "lideranca", f"assinei {_num(liberados)} liberação(ões) para produção.")
    analisadas = [e for e in exes if e.get("analise")]
    ressalvas = sum(1 for e in exes if (e.get("checklist_analise") or {}).get("ressalvas"))
    fala("coord_analise", "analise", f"revisei {_num(len(analisadas))} análise(s); {_num(ressalvas)} com ressalva.",
         travou="ressalvas costumam ser base pequena — leia esses destaques com cuidado." if ressalvas else "")
    entregas = [e["excel"] for e in exes if e.get("excel")]
    fala("excel_supervisor", "excel", f"assinei {_num(len(entregas))} entrega(s) Excel com "
                                      f"{_num(sum(int(x.get('conferencias') or 0) for x in entregas))} conferência(s) de fórmula.",
         bom="toda entrega tem a aba Conferência; se um número divergir, o Resumo avisa no topo." if entregas else "",
         travou="" if entregas else "nenhuma base aprovada chegou à Sala Excel neste período.")
    from robo.producao import agentes_reprovados_no_rh
    reprovados = agentes_reprovados_no_rh()
    fala("canal_helena", "rh", "processo seletivo técnico rodado para toda a equipe nativa.",
         bom="todos aprovados nas provas técnicas." if not reprovados else "",
         travou=f"reprovados nas provas: {', '.join(reprovados)}." if reprovados else "")
    falas.extend(_ideias_falas(cfg, hist, exes, titulo))
    return falas


# ----------------------------------------------------------------------------- ideias (Iara)
def ideias(cfg, hist: list[dict] | None = None, exes: list[dict] | None = None) -> list[str]:
    """Ideias concretas, cada uma com o dado que a motivou e o primeiro passo. Ordem = impacto esperado."""
    if hist is None:
        hist = historico.ler(cfg.logs, 300)
        exes = [historico.ler_execucao(cfg.logs, h.get("id") or "") or {} for h in hist[:150]]
    exes = exes or []
    out = []
    if not cfg.banco.get("habilitado"):
        out.append("Ligar o PostgreSQL. Motivo: hoje tudo fica só em planilha, sem histórico consultável. "
                   "Primeiro passo: instalar o PostgreSQL e preencher Configurações → Banco de dados.")
    ruim = [h for h in hist if h.get("status") == "reprovado"]
    if hist and len(ruim) / len(hist) > 0.2:
        out.append(f"Atacar a causa das reprovações ({len(ruim)} de {len(hist)} arquivos). Motivo: mais de 20% barrados. "
                   "Primeiro passo: abrir Reprovados, ver o erro mais comum e combinar a correção com quem gera o arquivo.")
    sem_regra = {h.get("arquivo") for h, e in zip(hist, exes) if e and not e.get("checklist_producao")}
    if len(sem_regra) > 2:
        out.append("Criar regras para os arquivos que chegam sem regra específica. Motivo: sem regra, só a limpeza genérica roda. "
                   "Primeiro passo: em config.yaml, adicionar um bloco em 'regras' com colunas obrigatórias e tipos.")
    alertas = sum(1 for e in exes for a in ((e.get("analise") or {}).get("alertas") or []) if a.get("nivel") == "atenção")
    if alertas:
        out.append(f"Revisar os {alertas} alerta(s) de monitoramento. Motivo: o indicador mudou mais que o normal entre cargas. "
                   "Primeiro passo: abrir o _analise.xlsx da base e ler a aba de alertas.")
    out.append("Montar o painel executivo no Power BI direto do schema 'analitico' (ou de Bases-Tratadas). Motivo: as tabelas "
               "já saem em modelo estrela (fato + dimensões). Primeiro passo: Obter Dados → PostgreSQL → tabelas fato_ e dim_.")
    out.append("Padronizar o nome dos arquivos (ex.: nps_2026_10.xlsx). Motivo: o monitoramento compara cargas da mesma base "
               "pelo nome. Primeiro passo: combinar o padrão com quem envia as planilhas.")
    out.append("Depois de 6 meses de histórico, testar um modelo simples de previsão de churn (regressão logística). "
               "Motivo: com histórico limpo, dá para saber quem tende a sair. Primeiro passo: garantir um ID de cliente estável.")
    return out


def _ideias_falas(cfg, hist, exes, titulo) -> list[tuple[str, str, str]]:
    lista = ideias(cfg, hist, exes)[:3]
    return [("canal_iara", "ideias", f"{titulo} — Ideias para a próxima sprint: " + " | ".join(f"{i}. {t}" for i, t in enumerate(lista, 1)))]


# ----------------------------------------------------------------------------- base de conhecimento (offline)
# Cada verbete: palavras-chave (sem acento), quem responde, e a resposta didática. Nomes de função em PT-BR e EN.
CONHECIMENTO = [
    {"chaves": ["procx", "xlookup", "procv", "vlookup", "buscar valor", "trazer valor de outra"], "autor": "excel_supervisor",
     "texto": "Use PROCX (XLOOKUP) — ele substitui o PROCV com menos erro. Sintaxe: =PROCX(o_que_procuro; onde_procuro; o_que_devolvo; "
              "\"Não encontrado\"). Passo a passo: 1) clique na célula do resultado; 2) digite =PROCX( ; 3) clique no valor a "
              "procurar; 4) selecione a coluna onde ele está; 5) selecione a coluna com o valor a trazer; 6) feche o parêntese "
              "e Enter. Por que não PROCV: ele quebra quando alguém insere coluna e só procura para a direita. Se o seu Excel "
              "não tem PROCX (2016 ou antes), use =ÍNDICE(coluna_resultado; CORRESP(valor; coluna_busca; 0))."},
    {"chaves": ["indice", "corresp", "index match", "index", "match"], "autor": "excel_supervisor",
     "texto": "ÍNDICE + CORRESP: =ÍNDICE(coluna_que_quero; CORRESP(valor_procurado; coluna_onde_procuro; 0)). O 0 no final "
              "significa correspondência exata — sem ele o resultado pode vir errado sem aviso. Funciona em qualquer versão do Excel."},
    {"chaves": ["somases", "sumifs", "somar com condicao", "soma com criterio", "somase"], "autor": "excel_trade",
     "texto": "SOMASES (SUMIFS) soma com uma ou mais condições: =SOMASES(coluna_a_somar; coluna_criterio1; criterio1; "
              "coluna_criterio2; criterio2). Exemplo de trade: venda da loja L1 no canal Atacarejo = SOMASES(Vendas[valor]; "
              "Vendas[loja]; \"L1\"; Vendas[canal]; \"Atacarejo\"). Cuidado: * e ? funcionam como curinga — para buscar o "
              "texto literal use ~* e ~?."},
    {"chaves": ["cont.ses", "contses", "countifs", "contar com condicao", "cont.se", "contse", "countif", "contar"],
     "autor": "excel_pesquisa",
     "texto": "CONT.SES (COUNTIFS) conta linhas que atendem a todas as condições: =CONT.SES(coluna1; criterio1; coluna2; "
              "criterio2). Em pesquisa, é a base de um segmento: =CONT.SES(Dados[regiao]; \"Sul\"). Percentual = essa "
              "contagem ÷ base total. É assim que a aba Plano Tabular das nossas entregas é montada."},
    {"chaves": ["tabela dinamica", "pivot", "dinamica"], "autor": "excel_dinamicas",
     "texto": "Tabela dinâmica: 1) clique em qualquer célula dos dados; 2) aba Inserir → Tabela Dinâmica; 3) confirme o "
              "intervalo e escolha 'Nova Planilha'; 4) arraste a dimensão (ex.: região) para Linhas e a métrica (ex.: venda) "
              "para Valores; 5) em Valores, clique na seta → Configurações do Campo de Valor para trocar Soma/Contagem/Média. "
              "Dica: transforme os dados em Tabela antes (Ctrl+Alt+T) para a dinâmica crescer sozinha quando chegarem linhas. "
              "Atualize com Dados → Atualizar Tudo."},
    {"chaves": ["power query", "obter dados", "transformar dados", "etl no excel"], "autor": "excel_formulas",
     "texto": "Power Query no Excel: aba Dados → Obter Dados → De Arquivo → Da Pasta de Trabalho → escolha o arquivo → "
              "selecione a tabela → Transformar Dados. Lá você remove colunas, troca tipos e filtra, e cada passo fica gravado "
              "em 'Etapas Aplicadas' (à direita). No fim, Fechar e Carregar. Para apontar para as nossas bases, use a pasta "
              "Bases-Tratadas: ela só tem arquivos que passaram em todas as conferências."},
    {"chaves": ["seerro", "iferror", "n/d", "div/0", "erro na formula", "erro de formula"], "autor": "excel_formulas",
     "texto": "SEERRO (IFERROR) troca um erro por um valor: =SEERRO(sua_fórmula; 0). Use com moderação: ele esconde QUALQUER "
              "erro, inclusive os que você precisava ver. Prefira tratar a causa — #N/D é valor não encontrado, #DIV/0! é "
              "divisão por zero (use =SE(base=0; \"\"; a/base)), #VALOR! é texto onde deveria ter número."},
    {"chaves": ["remover duplicadas", "duplicados", "duplicatas", "duplicidade"], "autor": "excel_supervisor",
     "texto": "Para ver duplicados sem apagar: Página Inicial → Formatação Condicional → Realçar Regras → Valores Duplicados. "
              "Para remover: Dados → Remover Duplicadas → marque só as colunas que formam a chave (ex.: id_resposta). "
              "Atenção: remover olhando todas as colunas pode manter duplicatas que diferem só num espaço. O robô já faz isso "
              "e registra quantas linhas saíram no relatório de qualidade."},
    {"chaves": ["procurar e substituir", "texto para colunas", "dividir coluna", "separar texto"], "autor": "excel_formulas",
     "texto": "Para separar uma coluna (ex.: 'São Paulo - SP'): selecione a coluna → Dados → Texto para Colunas → Delimitado "
              "→ marque Outros e digite '-' → Concluir. Antes, insira colunas vazias à direita para não sobrescrever dados. "
              "Alternativa dinâmica (Microsoft 365): =DIVIDIRTEXTO(A2; \" - \")."},
    {"chaves": ["formatacao condicional", "pintar celula", "colorir"], "autor": "excel_dinamicas",
     "texto": "Formatação condicional: selecione o intervalo → Página Inicial → Formatação Condicional → escolha a regra "
              "(Maior que, Escala de Cor...). Para NPS, use 3 cores fixas (vermelho < 0, amarelo 0–49, verde ≥ 50) em vez de "
              "escala contínua — o leitor executivo entende na hora."},
    {"chaves": ["congelar", "congelar paineis", "fixar cabecalho"], "autor": "excel_dinamicas",
     "texto": "Clique na célula logo abaixo do cabeçalho e à direita das colunas que quer fixar → aba Exibir → Congelar Painéis "
              "→ Congelar Painéis. Para desfazer, mesmo caminho → Descongelar."},
    {"chaves": ["validacao de dados", "lista suspensa", "dropdown"], "autor": "excel_formulas",
     "texto": "Lista suspensa: selecione as células → Dados → Validação de Dados → Permitir: Lista → em Fonte, selecione a lista "
              "de opções → OK. Isso evita digitação errada na origem — a melhor limpeza é a que não precisa acontecer."},
    {"chaves": ["data", "datas", "texto em data", "converter data", "datavalor"], "autor": "excel_formulas",
     "texto": "Data que virou texto: teste com =ÉNÚM(A2) — FALSO significa texto. Conserte com Dados → Texto para Colunas → "
              "Avançar → Avançar → Data: DMA → Concluir. Para extrair partes: =ANO(A2), =MÊS(A2), =TEXTO(A2; \"mmm/aaaa\"). "
              "O robô já converte datas e avisa quando não consegue."},
    {"chaves": ["se(", "funcao se", "condicional se", "ses(", "if("], "autor": "excel_formulas",
     "texto": "=SE(condição; valor_se_verdadeiro; valor_se_falso). Ex.: classificar NPS: =SE(B2>=9; \"Promotor\"; SE(B2>=7; "
              "\"Neutro\"; \"Detrator\")). No Microsoft 365 use SES para evitar SE dentro de SE: =SES(B2>=9; \"Promotor\"; "
              "B2>=7; \"Neutro\"; VERDADEIRO; \"Detrator\")."},
    {"chaves": ["atalho", "atalhos", "ctrl"], "autor": "excel_supervisor",
     "texto": "Atalhos que mais economizam tempo: Ctrl+T (vira Tabela), Ctrl+Shift+L (filtro), Ctrl+seta (vai ao fim dos dados), "
              "Ctrl+Shift+seta (seleciona até o fim), F4 (trava referência $A$1), Ctrl+; (data de hoje), Alt+= (AutoSoma), "
              "Ctrl+1 (formatar células)."},
    {"chaves": ["referencia absoluta", "cifrao", "referencia fixa", "travar celula", "f4"], "autor": "excel_supervisor",
     "texto": "O $ trava a referência ao arrastar a fórmula: $A$1 trava linha e coluna; A$1 só a linha; $A1 só a coluna. "
              "Atalho: clique na referência dentro da fórmula e aperte F4 para alternar."},
    {"chaves": ["dax", "medida", "calculate", "sumx", "power bi", "powerbi"], "autor": "excel_formulas",
     "texto": "No Power BI, prefira MEDIDAS a colunas calculadas para números agregados. Exemplo de NPS: "
              "NPS = VAR Total = COUNTROWS(fato_nps) VAR Prom = CALCULATE(COUNTROWS(fato_nps); fato_nps[nota_nps] >= 9) "
              "VAR Det = CALCULATE(COUNTROWS(fato_nps); fato_nps[nota_nps] <= 6) RETURN DIVIDE(Prom - Det; Total) * 100. "
              "CALCULATE muda o contexto de filtro (aplica a condição por cima do que o visual já filtra); DIVIDE evita erro "
              "de divisão por zero. Crie em: Página Inicial → Nova Medida."},
    {"chaves": ["relacionamento", "modelo estrela", "star schema", "cardinalidade", "fato", "dimensao"], "autor": "modelagem",
     "texto": "Modelo estrela: uma tabela FATO (os eventos, ex.: cada resposta) ligada a DIMENSÕES (quem/onde/quando, ex.: curso, "
              "calendário). No Power BI: Exibição de Modelo → arraste a chave da dimensão (ex.: id_curso) até a mesma coluna "
              "na fato. Deve ficar 1:* (um para muitos) e filtro em direção única (da dimensão para a fato). Eu já entrego "
              "fato_ e dim_ prontas, com chave única conferida pelo supervisor."},
    {"chaves": ["nps", "net promoter"], "autor": "analise_indicadores",
     "texto": "NPS = % promotores (notas 9–10) − % detratores (0–6), de −100 a +100. Neutros (7–8) entram só na base. Sempre "
              "leia com a base (n) e a margem de erro: com 100 respostas a margem fica perto de ±15 pontos, então 40 vs 48 "
              "pode ser só ruído. Eu calculo isso para cada base; o Davi diz se a diferença entre segmentos é real."},
    {"chaves": ["csat", "satisfacao"], "autor": "analise_indicadores",
     "texto": "CSAT = % de notas nas duas caixas de cima (top-2-box), ex.: 4 e 5 numa escala de 1 a 5. Mede satisfação com uma "
              "interação específica; NPS mede relacionamento. Não compare CSAT de escalas diferentes sem converter."},
    {"chaves": ["ces", "esforco"], "autor": "analise_indicadores",
     "texto": "CES (Customer Effort Score) mede o esforço do cliente para resolver algo — quanto menor o esforço, maior a chance "
              "de retenção. Use logo após a interação (atendimento, compra), não em pesquisa anual."},
    {"chaves": ["significancia", "significativo", "teste t", "qui-quadrado", "diferenca real", "p-valor", "p valor"],
     "autor": "analise_estatistica",
     "texto": "Diferença 'significativa' = provavelmente não é acaso. Eu uso teste z de proporções com 95% de confiança e "
              "corrijo por Holm quando são muitas comparações (senão, testando 20 segmentos, 1 'acerta' por sorte). "
              "Segmento com menos de 30 respostas eu nem destaco. Significativo não quer dizer importante: olhe também o tamanho da diferença."},
    {"chaves": ["margem de erro", "intervalo de confianca"], "autor": "analise_estatistica",
     "texto": "Margem de erro (95%) de uma proporção ≈ 1,96 × √(p×(1−p)/n). Com n=400 e p=50%, ±4,9 pontos. Para NPS a fórmula "
              "considera promotores e detratores juntos, por isso a margem é maior. Se quiser, me mande o tamanho da amostra "
              "que eu calculo (ex.: 'margem de erro com 400 respostas')."},
    {"chaves": ["questionario", "pergunta dupla", "vies", "escala likert", "survey"], "autor": "excel_pesquisa",
     "texto": "Antes de montar um questionário, defina: 1) objetivo; 2) a decisão que ele vai apoiar; 3) público; 4) amostra; "
              "5) duração (ideal até 10 minutos); 6) hipóteses. Evite pergunta dupla ('preço e qualidade são bons?'), "
              "pergunta que induz ('o quanto você gostou do nosso ótimo atendimento?') e escalas sem ponto neutro quando "
              "a neutralidade é legítima. Mande o rascunho aqui que eu reviso."},
    {"chaves": ["sell out", "sell-out", "sellout", "sell in", "sell-in", "sellin"], "autor": "excel_trade",
     "texto": "Sell-in = o que a indústria vende para o varejo; sell-out = o que o varejo vende para o consumidor. Estoque no "
              "canal ≈ sell-in acumulado − sell-out acumulado. Sell-in subindo com sell-out parado é estoque encalhando: "
              "sinal de risco de devolução ou promoção forçada."},
    {"chaves": ["share", "participacao de mercado", "market share"], "autor": "excel_trade",
     "texto": "Share = venda da marca ÷ venda total da categoria, no mesmo período e no mesmo recorte (loja, canal, região). "
              "Em Excel: =SOMASES(valor; marca; \"X\")/SOMASES(valor; categoria; \"Y\"). Compare share, não volume: "
              "a categoria inteira pode ter caído."},
    {"chaves": ["ruptura", "positivacao", "cobertura", "numerica", "ponderada", "pdv"], "autor": "excel_trade",
     "texto": "Positivação (distribuição numérica) = % de PDVs que compraram o produto no período. Ponderada = a mesma coisa "
              "pesada pelo tamanho da loja. Ruptura = produto cadastrado mas sem estoque na gôndola. Juntas mostram onde "
              "a venda está sendo perdida."},
    {"chaves": ["preco medio", "ticket medio", "mix"], "autor": "excel_trade",
     "texto": "Preço médio = faturamento ÷ unidades (nunca a média simples dos preços, que distorce quando o mix muda). "
              "Ticket médio = faturamento ÷ número de compras. Na entrega Excel eu já calculo preço médio por loja/canal com SOMASES."},
    {"chaves": ["grafico", "visual", "dashboard", "layout"], "autor": "excel_dinamicas",
     "texto": "Escolha pelo tipo de pergunta: comparar categorias → barras horizontais ordenadas; evolução no tempo → linhas; "
              "composição de um total → barras 100% (evite pizza com mais de 3 fatias); de onde veio uma variação → "
              "cascata (waterfall); número-chave → cartão com a variação ao lado. Layout executivo: KPIs no topo, "
              "tendência no meio, detalhe embaixo — o olho lê em Z."},
]

INTENCOES = {
    "status": ["como esta", "como estao", "status", "resumo do dia", "hoje", "como foi", "andamento", "o que aconteceu",
               "novidade", "situacao", "tudo certo", "como vai"],
    "erros": ["erro", "erros", "reprovad", "barrad", "falhou", "falha", "problema", "deu ruim", "bases-erros", "travou"],
    "sprint": ["sprint", "quinzena", "15 dias", "retrospectiva", "status report"],
    "ideias": ["ideia", "ideias", "sugest", "melhorar", "evolu", "proximo passo", "proximos passos", "roadmap", "inovar"],
    "banco": ["postgres", "postgre", "banco de dados", "banco", "sql", "dba"],
    "equipe": ["quem", "equipe", "time", "funcionario", "agentes", "contratar", "contratacao", "rh", "nivel", "promov"],
    "ajuda": ["ajuda", "o que voce faz", "o que voces fazem", "como funciona", "comandos", "help"],
    "amostra": ["amostra", "tamanho de amostra", "quantas respostas", "quantos entrevistados", "calculo amostral"],
    "saudacao": ["oi", "ola", "bom dia", "boa tarde", "boa noite", "e ai"],
}


PALAVRAS_VAZIAS = set("""funciona funcionam pessoa pessoas como para qual quais quem onde quando porque sobre esta este essa esse isso isto voce voces
fazer faco pode podem tenho temos preciso quero queria seria muito mais menos entre pela pelo pelos pelas numa num
uma umas dos das nos nas com sem que nao sim tem ter""".split())


def _secoes_markdown(cfg) -> list[dict]:
    """Seções (## título + texto) dos manuais dos agentes (agentes/*.md) e da pasta conhecimento/."""
    from robo.config import RAIZ_PROJETO
    fontes = []
    pasta_agentes = Path(getattr(cfg, "agentes", "") or "")
    if pasta_agentes.is_dir():
        fontes += [(arq, arq.stem) for arq in sorted(pasta_agentes.glob("*.md"))]
    pasta_conhecimento = Path(RAIZ_PROJETO) / "conhecimento"
    if pasta_conhecimento.is_dir():
        fontes += [(arq, "canal_nina") for arq in sorted(pasta_conhecimento.glob("*.md")) if not arq.name.startswith("_")]
    secoes = []
    for arq, autor in fontes[:300]:
        try:
            texto = arq.read_text(encoding="utf-8")[:200_000]
        except OSError:
            continue
        partes = re.split(r"(?m)^#{1,3}\s+", texto)
        for parte in partes:
            if not parte.strip():
                continue
            titulo, _, corpo = parte.partition("\n")
            secoes.append({"arquivo": arq.name, "autor": autor, "titulo": titulo.strip(), "corpo": corpo.strip()})
    return secoes


def _buscar_markdown(cfg, t: str) -> tuple[int, dict | None]:
    termos = {w for w in t.split() if len(w) >= 4 and w not in PALAVRAS_VAZIAS}
    if not termos:
        return 0, None
    melhor = (0, None)
    for sec in _secoes_markdown(cfg):
        titulo, corpo = normalizar(sec["titulo"]), normalizar(sec["corpo"])
        achados = {w for w in termos if w in titulo or w in corpo}
        pontos = sum(3 if w in titulo else 1 for w in achados)
        # duas palavras em comum, ou uma palavra forte (6+ letras) que está no título da seção
        forte = any(len(w) >= 6 and w in titulo for w in achados)
        if (len(achados) >= 2 or forte) and pontos > melhor[0]:
            melhor = (pontos, sec)
    return melhor


def _pontuar(texto: str, chaves: list[str]) -> int:
    pontos = 0
    palavras = set(texto.split())
    for c in chaves:
        if " " in c or not c.isalnum():
            pontos += 3 if c in texto else 0
        elif c in palavras:
            pontos += 2
        elif len(c) >= 5 and c in texto:  # radical (reprovad, sugest...)
            pontos += 1
    return pontos


def _numeros(texto: str) -> list[float]:
    return [float(x.replace(".", "").replace(",", ".")) for x in re.findall(r"\d[\d.]*(?:,\d+)?", texto)]


def responder(texto: str, cfg) -> list[dict]:
    """Duas camadas: 1) _apurar = FATOS (determinístico: quem responde, sobre o quê, com qual conteúdo e números);
    2) _compor = REDAÇÃO na voz de quem responde (IA, se ligada e conferida; senão a voz determinística de robo/voz.py).
    Devolve 1+ respostas [{autor, texto, intencao, natureza, fatos}]. Nunca inventa número."""
    return [_compor(f, texto, cfg) for f in _apurar(texto, cfg)]


def _compor(fato: dict, pergunta: str, cfg) -> dict:
    from robo import ia, voz
    autor, intencao = fato.get("autor") or "canal_nina", fato.get("intencao") or "conversa"
    if intencao == "nao_entendi":
        conteudo = voz.duvida_honesta(pergunta)
    else:
        conteudo = fato.get("texto") or ""
    fatos = {"pergunta": pergunta, "quem_responde": autor, "assunto": intencao, "conteudo": conteudo}
    saida = {**fato, "fatos": fatos}
    if intencao not in ("nao_entendi",) and ia.status(cfg).get("configurado"):
        p = pessoas().get(autor) or {}
        sistema = (f"Você é {p.get('nome', autor)}, {p.get('papel', '')} numa empresa de dados. Responda ao dono da empresa "
                   f"na primeira pessoa, com naturalidade, em até 5 frases.")
        r = ia.conversar(cfg, sistema, [{"role": "user", "content": pergunta}], fatos, timeout=45)
        if r["ok"]:
            voz.compor(cfg, autor, voz.ATO_DA_INTENCAO.get(intencao, "explicacao"), r["texto"], natureza="hipotese")
            return {**saida, "texto": r["texto"], "natureza": "hipotese", "modelo": r["modelo"], "aviso": r["aviso"]}
        saida["aviso_ia"] = r["aviso"]
    falado = voz.compor(cfg, autor, voz.ATO_DA_INTENCAO.get(intencao, "explicacao"), conteudo,
                        chave=f"{intencao}:{normalizar(pergunta)[:120]}")
    return {**saida, "texto": falado["texto"], "natureza": "regra", "molde": falado["molde"]}


def _apurar(texto: str, cfg) -> list[dict]:
    """Camada de FATOS: decide quem responde e com qual conteúdo factual (sem redação final)."""
    t = normalizar(texto)
    gente = pessoas()
    # 1) chamou alguém pelo nome? ("Ricardo, ...", "@Dora ...")
    nomes = {normalizar(p["nome"]): pid for pid, p in gente.items() if pid != DONO["id"]}
    chamado = next((pid for nome, pid in nomes.items() if re.search(rf"(^|[@\s]){re.escape(nome)}([\s,:?!.]|$)", t)), None)

    pont_int = {k: _pontuar(t, v) for k, v in INTENCOES.items()}
    pont_kb = [(_pontuar(t, v["chaves"]), i) for i, v in enumerate(CONHECIMENTO)]
    melhor_kb = max(pont_kb) if pont_kb else (0, -1)
    # em empate, a intenção mais específica vence (erros antes de status; status é a mais genérica)
    ordem = ["erros", "sprint", "banco", "ideias", "amostra", "equipe", "ajuda", "status", "saudacao"]
    melhor_int = max(pont_int.items(), key=lambda x: (x[1], -ordem.index(x[0]) if x[0] in ordem else -99))

    # cálculo amostral/margem com números na mensagem tem prioridade (resposta exata, não texto pronto)
    if (pont_int["amostra"] or "margem" in t) and _numeros(t):
        return [_calculo_amostral(t)]
    # pedido de cálculo sobre as bases publicadas ("nps por região", "média de valor por loja onde canal = App")
    # perguntas sobre o próprio robô ("quantos erros tivemos", "como está hoje") não são cálculo sobre bases
    sobre_o_robo = pont_int["erros"] >= 2 or pont_int["status"] >= 2 or pont_int["sprint"] or pont_int["equipe"] >= 2
    if not sobre_o_robo and not re.match(r"^(como|o que|qual a diferenca|por que)\b", t):
        try:
            from robo.calculos import calcular
            r = calcular(cfg, texto)
        except Exception as e:  # cálculo com problema vira resposta honesta, nunca derruba o canal
            r = {"autor": "canal_nina", "texto": f"Não consegui fazer esse cálculo ({type(e).__name__}: {e})."}
        if r:
            return [{**r, "intencao": "calculo"}]
    # manuais e conhecimento em .md escritos por você/pela equipe têm prioridade quando batem melhor
    pontos_md, secao = _buscar_markdown(cfg, t)
    if secao and pontos_md >= 4 and pontos_md > max(melhor_kb[0], melhor_int[1]):
        gente = pessoas()
        autor = secao["autor"] if secao["autor"] in gente else "canal_nina"
        corpo = secao["corpo"] if len(secao["corpo"]) <= 1200 else secao["corpo"][:1200].rsplit(" ", 1)[0] + "…"
        return [{"autor": autor, "intencao": "manual",
                 "texto": f"Do manual {secao['arquivo']} — {secao['titulo']}: {corpo}"}]
    # pergunta técnica ("como faço PROCX") vence intenção genérica; dados do robô vencem em empate
    if melhor_kb[0] > melhor_int[1] or (melhor_kb[0] >= 2 and melhor_int[0] in ("ajuda", "saudacao", "equipe")):
        v = CONHECIMENTO[melhor_kb[1]]
        return [{"autor": v["autor"], "texto": v["texto"], "intencao": "conhecimento"}]
    if melhor_int[1] > 0:
        r = _RESPOSTAS[melhor_int[0]](cfg, t)
        if chamado and chamado != r["autor"] and melhor_int[0] in ("status", "saudacao"):
            r = _resposta_pessoal(chamado, cfg)
        return [r]
    if chamado:
        return [_resposta_pessoal(chamado, cfg)]
    return [{"autor": "canal_nina", "intencao": "nao_entendi", "texto": ""}]  # a voz pergunta, com honestidade


def _resposta_pessoal(pid: str, cfg) -> dict:
    from robo import rh
    p = pessoas().get(pid, {})
    f = rh.FICHAS.get(pid) or {}
    itens = [r[0].lower() + r[1:] for r in (f.get("responsabilidades") or [])[:2] if r]
    resp = " e ".join(itens)
    return {"autor": pid, "intencao": "apresentacao",
            "texto": f"Sou {p.get('nome')}, {f.get('cargo') or p.get('papel')}."
                     + (f" Cuido de {resp}." if resp else "")}


def _hoje(cfg) -> tuple[list[dict], list[dict], list[dict]]:
    hoje = date.today().isoformat()
    h = [x for x in historico.ler(cfg.logs, 3000) if (x.get("data_hora") or "").startswith(hoje)]
    return h, [x for x in h if x.get("status") == "sucesso"], [x for x in h if x.get("status") == "reprovado"]


def _r_status(cfg, _t) -> dict:
    h, ok, ruim = _hoje(cfg)
    if not h:
        return {"autor": "coord_engenharia", "intencao": "status",
                "texto": "Hoje ainda não chegou nenhuma planilha em Bases-Limpeza. A equipe está de prontidão: assim que "
                         "um arquivo terminar de sincronizar, ele entra na fila."}
    linhas = sum(int(x.get("linhas_saida") or 0) for x in ok)
    return {"autor": "coord_engenharia", "intencao": "status",
            "texto": f"Hoje: {len(h)} arquivo(s) recebido(s), {len(ok)} aprovado(s) e publicado(s) com {_num(linhas)} linha(s), "
                     f"{len(ruim)} barrado(s)." + (f" Último barrado: {ruim[0].get('arquivo')} — pergunte 'quais erros?' "
                                                   "para ver o motivo." if ruim else " Nenhum problema em aberto.")}


def _r_erros(cfg, _t) -> dict:
    ruins = [x for x in historico.ler(cfg.logs, 300) if x.get("status") == "reprovado"][:3]
    if not ruins:
        return {"autor": "validacao", "intencao": "erros",
                "texto": "Nenhum arquivo barrado recentemente. Tudo o que chegou passou nas regras e nas conferências."}
    itens = []
    for x in ruins:
        exe = historico.ler_execucao(cfg.logs, x.get("id") or "") or {}
        erro = next((o["mensagem"] for o in exe.get("ocorrencias") or [] if o.get("nivel") == "ERRO"), "ver _ERROS.txt")
        itens.append(f"{x.get('arquivo')} ({x.get('data_hora', '')[:16]}): {erro}")
    return {"autor": "validacao", "intencao": "erros",
            "texto": "Últimos barrados — " + " | ".join(itens) + ". Os arquivos estão em Bases-Erros; corrija na origem e "
                     "reenvie, ou use Reprovados → Reprocessar no painel."}


def _r_sprint(cfg, _t) -> dict:
    c = Canal(cfg)
    numero, ini, fim = c.sprint_de(date.today())
    falas = relatorio_sprint(cfg, ini, min(fim, date.today()), numero, True)
    return {"autor": "canal_nina", "intencao": "sprint",
            "texto": f"Sprint {numero} vai de {ini.strftime('%d/%m')} a {fim.strftime('%d/%m')}. Parcial até agora: "
                     + " ".join(t.split(" — ", 1)[-1] for _a, _c, t in falas[:3])
                     + " Para o relatório completo, com cada pessoa falando, clique em 'Rodar sprint' no canal."}


def _r_ideias(cfg, _t) -> dict:
    lista = ideias(cfg)[:3]
    return {"autor": "canal_iara", "intencao": "ideias",
            "texto": "Minhas 3 ideias de maior impacto agora: " + " | ".join(f"{i}. {x}" for i, x in enumerate(lista, 1))}


def _r_banco(cfg, _t) -> dict:
    b = cfg.banco
    if not b.get("habilitado"):
        return {"autor": "dba", "intencao": "banco",
                "texto": "O PostgreSQL ainda não está ligado. Para ligar: 1) instale o PostgreSQL no seu PC (instalador oficial "
                         "da EDB, porta 5432); 2) no painel, vá em Configurações → Banco de dados; 3) preencha servidor "
                         "127.0.0.1, porta 5432, banco robo_dados, usuário postgres e a senha; 4) clique em Testar conexão "
                         "e depois em Salvar. Se preferir não gravar a senha no arquivo, crie a variável de ambiente ROBO_PG_SENHA."}
    return {"autor": "dba", "intencao": "banco",
            "texto": f"PostgreSQL ligado em {b.get('host')}:{b.get('porta')}, banco {b.get('banco')}. Toda carga passa por "
                     f"bruto → tratado → analítico e eu reconcilio as contagens antes do commit — se não bater, desfaço tudo. "
                     f"Para consultar, use a tela Consultas no painel."}


def _r_equipe(cfg, _t) -> dict:
    from robo.agentes import NATIVOS
    from robo.analise import ANALISTAS
    from robo.excel import EQUIPE_EXCEL
    from robo.producao import SUPERVISORES, agentes_reprovados_no_rh
    from robo.quadro import lotacao
    andares = lotacao()
    total = sum(len(p) for niveis in andares.values() for p in niveis.values())
    reprovados = agentes_reprovados_no_rh()
    return {"autor": "canal_helena", "intencao": "equipe",
            "texto": f"Somos {total} pessoas em {len(andares)} andares: 1º Engenharia de dados, 2º Análise e qualidade, "
                     f"3º Sala Excel, 4º Diretoria e canal, 5º TI e segurança — todos com gerente, coordenação, "
                     f"sêniores, plenos, juniores e estagiários. "
                     + ("Todos aprovados no processo seletivo técnico. " if not reprovados else
                        f"Reprovados nas provas: {', '.join(reprovados)}. ")
                     + "Para contratar (estagiário, júnior, pleno, sênior), vá em Agentes no painel: cada contratação "
                       "passa pelas provas técnicas das habilidades e só entra quem for aprovado."}


def _r_ajuda(cfg, t) -> dict:
    return responder("xyzzy", cfg)[0] | {"autor": "canal_nina", "intencao": "ajuda"}


def _r_saudacao(cfg, t) -> dict:
    r = _r_status(cfg, t)
    return {"autor": "canal_nina", "intencao": "saudacao", "texto": "Oi! " + r["texto"]}


def _r_amostra(cfg, t) -> dict:
    return {"autor": "analise_estatistica", "intencao": "amostra",
            "texto": "Para calcular a amostra, me diga a margem de erro que você aceita e, se souber, o tamanho do público. "
                     "Ex.: \"amostra para margem de 5% numa base de 2000 clientes\". Regra de bolso (95%, público grande): "
                     "±5 pontos → 385 respostas; ±3 → 1.068; ±10 → 97. E lembre: cada segmento que você quer ler sozinho "
                     "precisa de pelo menos 30 respostas (idealmente 100)."}


def _calculo_amostral(t: str) -> dict:
    nums = _numeros(t)
    # margem: número seguido de % ou "pontos"; população: o maior número restante
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(%|pontos|p\.p\.|pp)", t)
    margem = float(m.group(1).replace(",", ".")) / 100 if m else None
    resto = [n for n in nums if not m or n != float(m.group(1).replace(",", "."))]
    if margem is None and ("respostas" in t or "entrevist" in t or "com " in t) and resto:
        n = resto[0]
        if n < 2:
            return _r_amostra(None, t)
        e = 1.96 * math.sqrt(0.25 / n)
        return {"autor": "analise_estatistica", "intencao": "amostra",
                "texto": f"Com {_num(n)} respostas, a margem de erro (95% de confiança, pior caso p=50%) é de ±{e * 100:.1f} "
                         f"pontos percentuais. Para NPS ela é maior (até ±{e * 200:.1f} pontos), porque soma a incerteza de "
                         f"promotores e detratores."}
    if margem is None or not 0 < margem < 0.5:
        return _r_amostra(None, t)
    n0 = 1.96 ** 2 * 0.25 / margem ** 2
    populacao = max(resto) if resto else None
    if populacao and populacao > 1:
        n = n0 / (1 + (n0 - 1) / populacao)
        extra = f" numa população de {_num(populacao)} (com correção para população finita)"
    else:
        n, extra = n0, " (público grande)"
    return {"autor": "analise_estatistica", "intencao": "amostra",
            "texto": f"Para ±{margem * 100:g} pontos com 95% de confiança{extra}, você precisa de {_num(math.ceil(n))} "
                     f"respostas completas. Some uma folga para descarte (≈10%) e lembre que cada segmento lido "
                     f"separadamente precisa da própria base mínima."}


_RESPOSTAS = {"status": _r_status, "erros": _r_erros, "sprint": _r_sprint, "ideias": _r_ideias, "banco": _r_banco,
              "equipe": _r_equipe, "ajuda": _r_ajuda, "saudacao": _r_saudacao, "amostra": _r_amostra}


# ----------------------------------------------------------------------------- boletim diário (Renata, gerente)
def boletim_diario(cfg, dia: date) -> str:
    h = [x for x in historico.ler(cfg.logs, 5000) if (x.get("data_hora") or "").startswith(dia.isoformat())]
    if not h:
        return f"Boletim de {dia.strftime('%d/%m')}: nenhum arquivo recebido. Equipe de prontidão, nada pendente."
    ok = [x for x in h if x.get("status") == "sucesso"]
    ruim = [x for x in h if x.get("status") == "reprovado"]
    linhas = sum(int(x.get("linhas_saida") or 0) for x in ok)
    lentos = [x for x in ok if _num_br(x.get("duracao_seg")) > float((cfg.dados.get("quadro") or {}).get("sla_segundos", 120))]
    return (f"Boletim de {dia.strftime('%d/%m')}: {len(h)} arquivo(s), {len(ok)} publicado(s) ({_num(linhas)} linhas), "
            f"{len(ruim)} barrado(s)" + (f", {len(lentos)} acima do prazo" if lentos else ", todos dentro do prazo") + ". "
            + ("Prioridade de amanhã: tratar os barrados na origem." if ruim else "Sem pendências para amanhã."))


def _boletim_automatico(canal: "Canal") -> None:
    e = canal.estado()
    ontem = date.today() - timedelta(days=1)
    if e.get("ultimo_boletim") != ontem.isoformat() and "execucoes_postadas" in e:
        canal.postar("ger_operacoes", boletim_diario(canal.cfg, ontem), "geral", "boletim")
        e = canal.estado()
        e["ultimo_boletim"] = ontem.isoformat()
        canal.salvar_estado(e)


# ----------------------------------------------------------------------------- provas técnicas (RH)
def provas_canal() -> dict:
    import tempfile

    class _Cfg:
        pass
    with tempfile.TemporaryDirectory() as d:
        cfg = _Cfg()
        cfg.logs = Path(d)
        cfg.banco = {"habilitado": False}
        cfg.dados = {}
        r = lambda texto: responder(texto, cfg)[0]
        excel = r("Ricardo, como faço um procx entre duas planilhas?")
        nada = r("asdf qwer zxcv")
        amostra = r("qual a amostra para margem de erro de 5% numa base de 2000 clientes?")
        lista = ideias(cfg, [], [])
        historico.registrar(Path(d), {"data_hora": "2026-01-05 10:00:00", "arquivo": "a.xlsx", "status": "sucesso",
                                      "linhas_entrada": 10, "linhas_saida": 9, "erros": 0, "avisos": 0, "duracao_seg": 3,
                                      "saidas": "", "id": "x1"})
        boletim = boletim_diario(cfg, date(2026, 1, 5))
        vazio = boletim_diario(cfg, date(2026, 1, 6))
    from robo.rh import nivel_permite, provas_da_habilidade, risco_de

    def helena_aprova(nivel: str, hab: str, params: dict) -> bool:
        # mesma regra do processo seletivo: provas da habilidade aprovadas E nível compatível com o risco
        return all(p["aprovado"] for p in provas_da_habilidade(hab)) and nivel_permite(nivel, risco_de(hab, params))
    ruim = {"aprovado": helena_aprova("junior", "filtrar_linhas", {"condicao": "x > 1"})}
    bom = {"aprovado": helena_aprova("junior", "validar_email", {"colunas": ["email"]})}
    return {
        "canal_nina": [("Encaminha dúvida de Excel ao especialista", excel["autor"] == "excel_supervisor"),
                       ("Diz que não entendeu em vez de inventar", nada["intencao"] == "nao_entendi")],
        "canal_iara": [("Propõe ligar o banco quando está desligado", any("PostgreSQL" in i for i in lista)),
                       ("Toda ideia tem motivo e primeiro passo", all("Motivo" in i and "Primeiro passo" in i for i in lista[:2]))],
        "canal_helena": [("Barra júnior em habilidade de risco alto", not ruim["aprovado"]),
                         ("Aprova júnior em habilidade de risco baixo", bom["aprovado"])],
        "analise_estatistica_canal": [("Amostra: 5% em 2.000 → 323 respostas", "323" in amostra["texto"])],
        "ger_operacoes": [("Boletim com números do dia", "1 arquivo(s), 1 publicado(s) (9 linhas)" in boletim),
                          ("Dia sem arquivo dito com clareza", "nenhum arquivo" in vazio)],
    }
