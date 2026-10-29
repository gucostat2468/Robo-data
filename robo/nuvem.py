"""Empresa na nuvem GRÁTIS: trabalha em turnos no GitHub Actions e guarda tudo num PostgreSQL gratuito (ex.: Neon).

    python -m robo turno --minutos 20

Como funciona um turno (o arquivo .github/workflows/empresa_nuvem.yml chama de 2 em 2 horas):
  1. RESTAURA a memória: baixa do PostgreSQL o último instantâneo do SQLite (conferido por SHA-256). Na 1ª vez, usa a
     memória que já existia no projeto (nuvem/memoria_inicial.db.gz, conferida pelo manifesto);
  2. TRABALHA: as mesmas rotinas do robô (treino de todos os andares, laboratório, RH, alçadas, PDCA, lições, estudo,
     reunião, auditoria, ronda de TI, canal e registro total), no ritmo normal da empresa;
  3. SALVA a cada 10 minutos e no fim, nesta ordem: registro total → instantâneo do SQLite → cópia incremental de todas
     as tabelas para o schema robo. A ordem garante que, se a máquina do GitHub cair no meio, nada que já foi salvo
     se perde e nada fica com número repetido (o próximo turno continua do último instantâneo).

A ESTEIRA também roda na nuvem: a fábrica gera planilhas sintéticas (TREINO_*) e o monitor as processa como se fossem
reais. Elas vão só para os schemas laboratorio e treino do PostgreSQL (nunca para bruto, tratado, analitico ou analise).

O que NÃO roda na nuvem: o backup com pg_dump (o próprio PostgreSQL gratuito guarda o histórico, e os instantâneos
ficam lá dentro). Planilhas suas não chegam à nuvem: a pasta de entrada da nuvem só recebe as da fábrica.

Variáveis (Secrets do GitHub — nunca no código, nunca no log):
  ROBO_PG_URL            postgresql://usuario:senha@host/banco?sslmode=require (copiada do painel do Neon)
  ROBO_PG_SENHA_LEITURA  senha que VOCÊ escolhe para o usuário robo_leitura (o do app do celular)
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("robo")

RAIZ = Path(__file__).resolve().parents[1]
MEMORIA_INICIAL = RAIZ / "nuvem" / "memoria_inicial.db.gz"
MANTER_INSTANTANEOS = 6
NAO_RODAM_NA_NUVEM = {"memoria_pg", "registro", "canal", "treino", "laboratorio"}  # cuidadas à parte no turno
# Cada turno começa numa máquina NOVA, sem planilhas: estas rotinas só rodam depois que a fábrica gerou e a esteira
# tratou a planilha do turno. Antes a 1ª distribuição de demandas vinha antes e o trabalho que precisa de planilha
# ficava bloqueado (virava estudo "Consultar o conhecimento").
DEPOIS_DA_ESTEIRA = ("demandas",)
# Laço interno do turno: ordem fixa fábrica → esteira → demandas. O resto entra por rotinas.vencidas().
LACO_ANTES_DA_ESTEIRA = ("canal", "registro", "treino", "laboratorio", "fabrica")
LACO_DEPOIS_DA_ESTEIRA = ("demandas", "telegram")
FORA_DAS_VENCIDAS = {*LACO_ANTES_DA_ESTEIRA, *LACO_DEPOIS_DA_ESTEIRA, "memoria_pg"}  # memoria_pg: salvar() a cada 10 min
LIMITE_MB_PADRAO = 500  # plano gratuito: avisa com 80% (o Neon gratuito dá 0,5 a 1 GB por projeto)


# =============================================================================== configuração
def url_do_ambiente(amb: dict | None = None) -> str:
    """Endereço do PostgreSQL montado SÓ de variáveis de ambiente (nunca de arquivo). Duas formas:
      ROBO_PG_URL                         a URL inteira (GitHub Actions + Neon, o caminho grátis de hoje);
      DB_USER, DB_PASS, DB_NAME           o padrão do Google Cloud Run + Cloud SQL. Com INSTANCE_CONNECTION_NAME a
                                          conexão vai pelo Unix socket /cloudsql/<instância> (sem IP público, sem
                                          porta aberta); sem ela, por DB_HOST e DB_PORT.
    Devolve '' quando nada está definido."""
    from psycopg.conninfo import make_conninfo
    amb = os.environ if amb is None else amb
    url = (amb.get("ROBO_PG_URL") or "").strip()
    if url:
        return url
    if not (amb.get("DB_USER") and amb.get("DB_NAME")):
        return ""
    instancia = (amb.get("INSTANCE_CONNECTION_NAME") or "").strip()
    host = f"/cloudsql/{instancia}" if instancia else (amb.get("DB_HOST") or "localhost")
    return make_conninfo("", host=host, port=None if instancia else (amb.get("DB_PORT") or "5432"),
                         user=amb["DB_USER"], password=amb.get("DB_PASS") or "", dbname=amb["DB_NAME"])


def config_da_nuvem(pasta: Path, url: str, senha_leitura: str = ""):
    """Config montada só da memória (nada de senha em arquivo). As pastas ficam na máquina temporária do turno."""
    from psycopg.conninfo import conninfo_to_dict
    from robo.config import carregar_config
    c = conninfo_to_dict(url)
    pasta = Path(pasta)
    for sub in ("entrada", "logs", "agentes", "habilidades"):
        (pasta / sub).mkdir(parents=True, exist_ok=True)
    host = c.get("host", "localhost")
    local = host in ("localhost", "127.0.0.1") or host.startswith("/")  # Unix socket (Cloud SQL) não usa SSL
    banco = {"habilitado": True, "host": host, "porta": int(c.get("port") or 5432),
             "banco": c.get("dbname", "neondb"), "usuario": c.get("user", "postgres"), "senha": c.get("password", ""),
             "sslmode": c.get("sslmode") or ("" if local else "require"),
             "usuario_leitura": "robo_leitura", "senha_leitura": senha_leitura, "tempo_limite_conexao": 20}
    return carregar_config(pasta / "config_nuvem_inexistente.yaml", sobrescrever={
        "pastas": {k: str(pasta / k) for k in ("entrada", "logs", "agentes", "habilidades")},
        "banco": banco, "rotinas": {"agendador": "robo"}, "backup": {"copia_extra": "", "postgres": False},
        # lotes menores na nuvem: cabem no turno de 20 min e no plano gratuito do banco
        "fabrica": {"linhas_min": 1000, "linhas_max": 5000},
        # o grupo do Telegram também atende pela nuvem (token em ROBO_TELEGRAM_TOKEN, nos Secrets do GitHub)
        "telegram": {"habilitado": bool(os.environ.get("ROBO_TELEGRAM_TOKEN") or os.environ.get("ROBO_TELEGRAM_CHAT")),
                     "codigo_vinculo": os.environ.get("ROBO_TELEGRAM_CODIGO", ""),
                     "chat_id": os.environ.get("ROBO_TELEGRAM_CHAT", ""), "dono_id": os.environ.get("ROBO_TELEGRAM_DONO", "")}})


def _conectar(cfg):
    from robo.banco import Banco
    return Banco(cfg.banco, cfg.base).conectar()


# =============================================================================== instantâneos (o SQLite inteiro)
ESQUEMA_PG = """CREATE SCHEMA IF NOT EXISTS robo;
CREATE TABLE IF NOT EXISTS robo.instantaneos_sqlite (
  id BIGSERIAL PRIMARY KEY, data_hora TIMESTAMPTZ DEFAULT now(), sha256 TEXT NOT NULL, tamanho BIGINT, linhas BIGINT,
  tabelas INTEGER, conteudo BYTEA NOT NULL);"""


def _sha_descompactado(dados_gz: bytes) -> str:
    return hashlib.sha256(gzip.decompress(dados_gz)).hexdigest()


# --------------------------------------------------------------------- memória fora do banco (arquivo do GitHub Actions)
# 27/10: o Neon grátis estourou a cota e bloqueou as conexões; sem banco o turno nem começava e a empresa parou.
# Agora cada salvamento também grava a memória num ARQUIVO criptografado que o GitHub Actions guarda como artefato
# (grátis no repositório público). O turno seguinte baixa esse arquivo e usa a cópia MAIS NOVA entre ele e o banco.
# Sem banco, o turno trabalha só com o SQLite e o arquivo; quando o banco volta, a cópia incremental o alcança.
# O repositório é público, então o arquivo é criptografado (AES-256, openssl) com ROBO_MEMORIA_CHAVE ou, sem ela, com
# uma chave derivada do segredo ROBO_PG_URL. Sem chave nenhuma, o arquivo não é gravado (nunca vai em claro).
ARQ_MEMORIA, ARQ_META = "memoria.db.gz.enc", "memoria.json"
_sem_banco: dict = {"motivo": None}


def _chave() -> str | None:
    chave = os.environ.get("ROBO_MEMORIA_CHAVE") or ""
    if not chave and os.environ.get("ROBO_PG_URL"):
        chave = hashlib.sha256(("robo-memoria|" + os.environ["ROBO_PG_URL"]).encode()).hexdigest()
    return chave or None


def _openssl(dados: bytes, chave: str, abrir: bool) -> bytes:
    import subprocess
    r = subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-salt",
                        *(["-d"] if abrir else []), "-pass", "env:ROBO_CHAVE_ARQUIVO"],
                       input=dados, capture_output=True, timeout=300, env={**os.environ, "ROBO_CHAVE_ARQUIVO": chave})
    if r.returncode != 0:
        raise RuntimeError(f"openssl falhou: {r.stderr.decode(errors='replace').strip()[:160]}")
    return r.stdout


def guardar_arquivo(dados_gz: bytes, sha256: str, linhas: int) -> Path | None:
    """Grava a memória criptografada em ROBO_MEMORIA_SAIDA (o workflow sobe como artefato). None = não configurado."""
    pasta, chave = os.environ.get("ROBO_MEMORIA_SAIDA"), _chave()
    if not pasta or not chave:
        return None
    destino = Path(pasta)
    destino.mkdir(parents=True, exist_ok=True)
    tmp = destino / (ARQ_MEMORIA + ".parcial")
    tmp.write_bytes(_openssl(dados_gz, chave, abrir=False))
    tmp.replace(destino / ARQ_MEMORIA)  # troca atômica: nunca fica um arquivo pela metade
    from datetime import timezone
    (destino / ARQ_META).write_text(json.dumps({"gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                                "sha256": sha256, "linhas": linhas}), encoding="utf-8")
    return destino / ARQ_MEMORIA


def ler_arquivo() -> dict | None:
    """A memória do turno anterior baixada pelo workflow (ROBO_MEMORIA_ENTRADA), conferida pelo SHA-256."""
    pasta, chave = os.environ.get("ROBO_MEMORIA_ENTRADA"), _chave()
    if not pasta or not chave:
        return None
    arq, meta = Path(pasta) / ARQ_MEMORIA, Path(pasta) / ARQ_META
    if not arq.exists() or not meta.exists():
        return None
    try:
        m = json.loads(meta.read_text(encoding="utf-8"))
        dados = _openssl(arq.read_bytes(), chave, abrir=True)
        if _sha_descompactado(dados) != m["sha256"]:
            raise RuntimeError("SHA-256 não confere")
    except Exception as e:  # chave trocada, arquivo corrompido: não usa (e diz por quê)
        log.warning("Memória do arquivo do GitHub ignorada: %s: %s", type(e).__name__, str(e)[:200])
        return None
    return {"gerado_em": datetime.fromisoformat(m["gerado_em"]), "sha256": m["sha256"], "dados": dados}


def _erros_de_banco() -> tuple:
    from robo.banco import ErroBancoIndisponivel
    try:
        import psycopg
        return (ErroBancoIndisponivel, psycopg.OperationalError)
    except ImportError:
        return (ErroBancoIndisponivel,)


def banco_ligado(cfg) -> bool:
    return bool((cfg.banco or {}).get("habilitado"))


def desligar_banco(cfg, motivo: str) -> None:
    """O resto do turno segue só com o SQLite e o arquivo: rotinas que precisam do banco ficam bloqueadas com motivo."""
    if banco_ligado(cfg):
        log.warning("Turno SEM banco a partir de agora: %s", motivo[:300])
    cfg.banco["habilitado"] = False
    _sem_banco["motivo"] = motivo[:300]


def restaurar(cfg) -> dict:
    """Traz a memória para a máquina do turno: a cópia MAIS NOVA entre o último instantâneo do banco e o arquivo do
    GitHub; sem as duas, a memória inicial do projeto; senão começa vazia (e diz isso). Banco fora do ar não impede
    o turno: ele segue sem banco. Sempre confere o SHA-256 antes de usar."""
    destino = Path(cfg.logs) / "trabalho.db"
    if destino.exists():
        return {"origem": "local", "arquivo": str(destino)}
    candidatos = []
    if banco_ligado(cfg):
        try:
            with _conectar(cfg) as conn:
                conn.execute(ESQUEMA_PG)
                r = conn.execute("SELECT id, sha256, conteudo, data_hora FROM robo.instantaneos_sqlite "
                                 "ORDER BY id DESC LIMIT 1").fetchone()
            if r:
                candidatos.append({"origem": f"instantaneo {r[0]}", "sha256": r[1], "dados": bytes(r[2]),
                                   "gerado_em": r[3]})
        except _erros_de_banco() as e:
            desligar_banco(cfg, f"{type(e).__name__}: {e}")
    arq = ler_arquivo()
    if arq:
        candidatos.append({**arq, "origem": "arquivo do GitHub"})
    from robo import registro_total
    if candidatos:
        c = max(candidatos, key=lambda x: x["gerado_em"])
        if _sha_descompactado(c["dados"]) != c["sha256"]:
            raise RuntimeError(f"a memória de {c['origem']} não confere com o próprio SHA-256: não vou usar memória corrompida")
        destino.write_bytes(gzip.decompress(c["dados"]))
        saida = {"origem": c["origem"], "sha256": c["sha256"], "gerado_em": str(c["gerado_em"])}
    elif _sem_banco["motivo"]:
        # o banco está configurado mas fora do ar e não há arquivo: a memória mais nova está presa no banco. Começar
        # da memória inicial criaria uma 2ª história com os mesmos números de registro, e a cópia para o banco, quando
        # ele voltar, misturaria as duas. Melhor parar (e dizer por quê) do que arriscar perder registro.
        raise RuntimeError("banco fora do ar e nenhuma memória em arquivo ainda: a memória mais nova está no banco; "
                           f"o turno não começa de uma memória antiga ({_sem_banco['motivo'][:160]})")
    elif MEMORIA_INICIAL.exists():
        from robo import backup
        r = backup.restaurar_sqlite(cfg, MEMORIA_INICIAL)
        saida = {"origem": "memoria_inicial", "sha256": r["sha256"], "linhas": r["linhas"]}
    else:
        return {"origem": "vazia", "banco": banco_ligado(cfg)}
    saida["arquivos"] = registro_total.restaurar_arquivos(cfg)  # canal, estado da TI, âncora, equipe… de volta
    saida["banco"] = banco_ligado(cfg)
    if not saida["banco"]:
        saida["sem_banco"] = _sem_banco["motivo"]
    return saida


def salvar_instantaneo(cfg) -> dict:
    """A cópia conferida do SQLite vai para o arquivo do GitHub (sempre) e para o banco (quando ligado)."""
    from robo import backup
    b = backup.backup_sqlite(cfg)  # cópia online conferida (integrity_check) e compactada
    if not b.get("ok"):
        raise RuntimeError(f"não consegui copiar a memória: {b.get('motivo')}")
    arq = backup.pasta_sqlite(cfg) / b["arquivo"]
    dados = arq.read_bytes()
    saida = {"linhas": b["linhas"], "tabelas": b["tabelas"], "tamanho_kb": round(len(dados) / 1024)}
    try:
        saida["arquivo_github"] = bool(guardar_arquivo(dados, b["sha256"], b["linhas"]))
    except Exception as e:
        log.warning("Memória não gravada no arquivo do GitHub: %s: %s", type(e).__name__, str(e)[:200])
        saida["arquivo_github"] = False
    if not banco_ligado(cfg):
        return {**saida, "banco": False}
    try:
        with _conectar(cfg) as conn:
            conn.execute(ESQUEMA_PG)
            conn.execute("INSERT INTO robo.instantaneos_sqlite (sha256, tamanho, linhas, tabelas, conteudo) "
                         "VALUES (%s,%s,%s,%s,%s)", (b["sha256"], len(dados), b["linhas"], b["tabelas"], dados))
            # só os instantâneos (cópias do arquivo) giram; a memória de verdade fica nas tabelas robo.memoria_*,
            # que nunca perdem linha
            conn.execute("DELETE FROM robo.instantaneos_sqlite WHERE id NOT IN (SELECT id FROM robo.instantaneos_sqlite "
                         "ORDER BY id DESC LIMIT %s)", (MANTER_INSTANTANEOS,))
    except _erros_de_banco() as e:
        desligar_banco(cfg, f"{type(e).__name__}: {e}")
        return {**saida, "banco": False}
    return {**saida, "banco": True}


def garantir_leitura(cfg) -> bool:
    """Usuário robo_leitura (o do app do celular e dos exercícios de SQL): só SELECT, transações somente leitura.
    Lê o schema robo (memória) e os schemas SINTÉTICOS laboratorio e treino (planilhas da fábrica: sem dado de
    cliente). Sem os dois últimos, todo exercício de SQL na nuvem falhava por falta de permissão."""
    senha = (cfg.banco or {}).get("senha_leitura")
    if not senha:
        return False
    from psycopg import sql
    with _conectar(cfg) as conn:
        existe = conn.execute("SELECT 1 FROM pg_roles WHERE rolname='robo_leitura'").fetchone()
        comando = "ALTER ROLE robo_leitura WITH LOGIN PASSWORD {}" if existe else "CREATE ROLE robo_leitura WITH LOGIN PASSWORD {}"
        conn.execute(sql.SQL(comando).format(sql.Literal(senha)))
        conn.execute("ALTER ROLE robo_leitura SET default_transaction_read_only = on")
        banco = sql.Identifier(cfg.banco["banco"])
        conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO robo_leitura").format(banco))
        from robo.pipeline import SCHEMAS_SINTETICOS
        for nome in ["robo", *sorted(set(SCHEMAS_SINTETICOS.values()))]:
            schema = sql.Identifier(nome)
            conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(schema))
            conn.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO robo_leitura").format(schema))
            conn.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO robo_leitura").format(schema))
            conn.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA {} GRANT SELECT ON TABLES TO robo_leitura").format(schema))
    return True


def tamanho_mb(cfg) -> float:
    with _conectar(cfg) as conn:
        return round(conn.execute("SELECT pg_database_size(current_database())").fetchone()[0] / 1024 ** 2, 1)


# =============================================================================== o turno
COBERTURA_A_CADA_S = 60 * 60
_cobertura = {"t": None}


def salvar(cfg, completo: bool = False) -> dict:
    """Registro total → instantâneo → cópia incremental (essa ordem nunca deixa número repetido para trás).
    O levantamento de cobertura (COUNT exato de ~200 tabelas no SQLite e no PostgreSQL) é o que menos muda: roda no
    1º salvamento, a cada hora e no salvamento final (completo=True), não a cada 10 min. Cada parte é cronometrada
    (em "tempos") para o próximo corte de custo ser decidido por medida: no turno real, salvar custou 25% do turno."""
    from robo import cobertura_banco, memoria, registro_total, rotinas
    tempos = {}

    def parte(nome, f):
        t = time.perf_counter()
        try:
            return f()
        finally:
            tempos[nome] = round(time.perf_counter() - t, 2)
    parte("registro", lambda: rotinas.executar(cfg, "registro", lambda: registro_total.capturar(cfg)))
    agora = time.monotonic()
    if completo or _cobertura["t"] is None or agora - _cobertura["t"] >= COBERTURA_A_CADA_S:
        try:  # quais tabelas têm dados e por que as vazias estão vazias (vai junto no instantâneo e no espelho)
            parte("cobertura", lambda: cobertura_banco.salvar_relatorio(cfg, cobertura_banco.levantar(cfg)))
            _cobertura["t"] = agora
        except Exception:
            log.exception("Turno na nuvem: levantamento de cobertura falhou")
    inst = parte("instantaneo", lambda: salvar_instantaneo(cfg))
    if banco_ligado(cfg):
        parte("memoria_pg", lambda: rotinas.executar(cfg, "memoria_pg", lambda: memoria.sincronizar_postgres(cfg)))
        try:
            parte("leitura", lambda: garantir_leitura(cfg))  # tabelas novas também ficam legíveis no celular
        except _erros_de_banco() as e:
            desligar_banco(cfg, f"{type(e).__name__}: {e}")
    log.info("Salvamento: %s", ", ".join(f"{k} {v:.1f}s" for k, v in tempos.items()))
    return {**inst, "tempos": tempos}


def _esteira(monitor) -> int:
    """Uma passada do monitor na pasta de entrada da nuvem (planilhas da fábrica). Falha aqui não derruba o turno."""
    try:
        return len(monitor.ciclo(forcar=True))
    except Exception:
        log.exception("Turno na nuvem: a esteira falhou nesta volta")
        return 0


def freio_de_espaco(cfg, mb: float | None = None, limite: float | None = None) -> bool:
    """Trabalho sem teto enche o banco grátis mais rápido. Com 80% ou mais do limite, as demandas voltam ao ritmo
    antigo (demandas.FREIO) neste turno e o canal avisa; nada é apagado. Devolve se o freio foi puxado."""
    from robo import demandas
    try:
        mb = tamanho_mb(cfg) if mb is None else mb
    except Exception:
        return False  # sem medir não freia: o alerta do fim do turno continua valendo
    limite = float(limite or os.environ.get("ROBO_LIMITE_MB") or LIMITE_MB_PADRAO)
    if mb < 0.8 * limite:
        return False
    cfg.dados["demandas"] = {**(cfg.dados.get("demandas") or {}), **demandas.FREIO}
    log.warning("Freio de espaço: banco com %s MB de %.0f MB; demandas no ritmo antigo neste turno", mb, limite)
    return True


def garantir_base(cfg, monitor) -> int:
    """Máquina nova não tem planilha nenhuma. Sem planilha tratada, quase todo trabalho das áreas de dados fica
    bloqueado. No início do turno a fábrica produz o que falta e a esteira trata antes da 1ª distribuição:
      - uma pesquisa NPS com atributos, se não houver (o projeto NPS entre andares precisa dela);
      - um lote do RODÍZIO de regras (churn, RFM, estoque, folha, vendas...), produzido por último para ser a base
        mais recente que as demandas usam. Antes só saía NPS: 14 das 15 últimas planilhas eram NPS (27/10) e todo
        trabalho de base virava análise de NPS.
    Devolve as planilhas tratadas."""
    from robo import demandas, fabrica
    tem_base = demandas.base_tratada(cfg) and demandas.base_original(cfg)
    tem_nps = tem_base and not isinstance(demandas._com_indicador(cfg, {}), str)
    pedir = ([] if tem_nps else ["nps"]) + ([] if tem_base and tem_nps else [None])  # None = próxima do rodízio
    if not pedir:
        return 0
    for regra in pedir:
        try:
            lote = fabrica.produzir_lote(cfg, regra_id=regra)
            log.info("Turno na nuvem: a fábrica produziu %s (%s) para o trabalho do turno", lote.get("arquivo"),
                     regra or "rodízio")
        except Exception:
            log.exception("Turno na nuvem: não consegui produzir a planilha do início do turno (%s)", regra or "rodízio")
            continue
        _esteira(monitor)
    return len(pedir)


def turno(cfg, minutos: float = 20, salvar_a_cada_min: float = 10, pausa_s: float = 15, parar=None) -> dict:
    """parar: threading.Event opcional. Quando é ligado (SIGTERM do Cloud Run, Ctrl+C), o turno sai do laço e SALVA
    a memória antes de devolver (encerramento gracioso: nada do que foi feito se perde)."""
    from robo import rotinas, tempo_turno
    from robo.monitor import Monitor
    inicio = time.monotonic()
    fim = inicio + minutos * 60
    crono = tempo_turno.Cronometro()  # cada segundo do turno vai para uma natureza (robo/tempo_turno.py)
    with crono.medir("inicio"):
        origem = restaurar(cfg)
        log.info("Turno na nuvem: memória restaurada de %s", origem["origem"])
        if banco_ligado(cfg):
            freio_de_espaco(cfg)
        sessao = rotinas.abrir_sessao(cfg)["sessao"]
        if banco_ligado(cfg):
            try:
                garantir_leitura(cfg)
            except _erros_de_banco() as e:
                desligar_banco(cfg, f"{type(e).__name__}: {e}")
    from robo import pos_processamento
    monitor = Monitor(cfg, ao_processar=lambda r: pos_processamento.registrar(cfg, r))
    planilhas = 0
    for nome in rotinas.ROTINAS:  # cada uma decide se está na hora (backup diário, reunião semanal…)
        if nome in NAO_RODAM_NA_NUVEM or nome in DEPOIS_DA_ESTEIRA:
            continue
        crono.rotina(cfg, nome, rotinas.executar, rotinas.funcao(cfg, nome))
        if nome == "fabrica":  # a planilha do turno é tratada ANTES de distribuir trabalho que precisa dela
            with crono.medir("esteira"):
                planilhas += _esteira(monitor)
    with crono.medir("esteira"):
        planilhas += _esteira(monitor)
        planilhas += garantir_base(cfg, monitor)
    for nome in DEPOIS_DA_ESTEIRA:
        crono.rotina(cfg, nome, rotinas.executar, rotinas.funcao(cfg, nome))
    ultimo_salvo = time.monotonic()
    voltas = 0
    from robo import boletim
    inicio_txt = datetime.now().isoformat(timespec="seconds")
    inicio_epoca = time.time()
    previsto = (datetime.now() + timedelta(minutes=minutos)).isoformat(timespec="seconds")

    def _boletim(estado: str, final: bool = False) -> None:  # o celular acompanha o turno, só no GitHub Actions
        if not banco_ligado(cfg):  # o dono vê no celular que o banco está fora e onde a memória está
            estado += " · SEM BANCO (memória guardada no arquivo do GitHub; o banco é alcançado quando voltar)"
        if boletim.ligado():
            boletim.publicar(cfg, RAIZ, Path(cfg.logs).parent / "boletim_git",
                             {"estado": estado, "inicio": inicio_txt, "fim_previsto": previsto, "voltas": voltas,
                              "planilhas": planilhas})
            # o painel completo (mesmo do computador, com o escritório 3D) lê este espelho no app do celular
            from robo import painel_espelho
            painel_espelho.publicar(cfg, RAIZ, Path(cfg.logs).parent / "espelho_git", forcar=final,
                                    ligado_desde=None if final else inicio_epoca)
    with crono.medir("boletim"):
        _boletim("trabalhando")
    ultimo_boletim = time.monotonic()
    while time.monotonic() < fim and not (parar is not None and parar.is_set()):
        voltas += 1
        for nome in LACO_ANTES_DA_ESTEIRA:
            crono.rotina(cfg, nome, rotinas.executar, rotinas.funcao(cfg, nome))
        with crono.medir("esteira"):
            planilhas += _esteira(monitor)
        for nome in LACO_DEPOIS_DA_ESTEIRA:
            crono.rotina(cfg, nome, rotinas.executar, rotinas.funcao(cfg, nome))
        # as demais (diálogo a cada 20 min, ronda de TI, lições...) rodam quando vencem, não só no começo do turno
        for nome in rotinas.vencidas(cfg, excluir=FORA_DAS_VENCIDAS):
            crono.rotina(cfg, nome, rotinas.executar, rotinas.funcao(cfg, nome))
        with crono.medir("registro"):
            rotinas.batimento(cfg, sessao)
        if time.monotonic() - ultimo_salvo >= salvar_a_cada_min * 60:
            with crono.medir("salvar"):
                salvar(cfg)
            ultimo_salvo = time.monotonic()
        if time.monotonic() - ultimo_boletim >= 5 * 60:
            with crono.medir("boletim"):
                _boletim("trabalhando")
            ultimo_boletim = time.monotonic()
        espera = max(0.0, min(pausa_s, fim - time.monotonic()))
        with crono.medir("pausa"):
            if parar is not None:
                parar.wait(espera)
            else:
                time.sleep(espera)
    with crono.medir("esteira"):
        planilhas += _esteira(monitor)
    for nome in ("fabrica", "ronda_ti", "rh_desempenho", "alcadas"):  # fecham o turno (a fábrica confere o gabarito)
        if nome in rotinas.ROTINAS:
            crono.rotina(cfg, nome, rotinas.executar, rotinas.funcao(cfg, nome))
    # o tempo é gravado ANTES do salvamento final: gravado depois, ficava só na máquina descartada (achado no 1º
    # turno real). O salvamento final em si fica fora da medição deste turno.
    try:
        tempo = tempo_turno.fechar(cfg, crono, voltas)
    except Exception as e:  # medir nunca derruba o turno; a falha fica no log
        log.warning("Tempo do turno não registrado: %s: %s", type(e).__name__, e)
        tempo = None
    inst = salvar(cfg, completo=True)
    _boletim("entre turnos: memória salva; o próximo turno começa em poucos minutos", final=True)
    mb = None
    if banco_ligado(cfg):
        try:
            mb = tamanho_mb(cfg)
        except _erros_de_banco() as e:
            desligar_banco(cfg, f"{type(e).__name__}: {e}")
    limite = float(os.environ.get("ROBO_LIMITE_MB") or LIMITE_MB_PADRAO)
    alerta = mb is not None and mb >= 0.8 * limite
    if alerta:
        try:
            from robo.canal import Canal
            Canal(cfg).postar("dba", f"O banco gratuito da nuvem está com {mb} MB de {limite:.0f} MB (80%+). Nada foi apagado; "
                                     "é hora de decidir: arquivar em backup criptografado ou mudar de plano.", "banco", "alerta")
        except Exception:
            pass
    return {"origem": origem["origem"], "minutos": round((time.monotonic() - inicio) / 60, 1), "voltas": voltas,
            "planilhas_processadas": planilhas, "tempo": tempo,
            "memoria": inst, "banco_mb": mb, "limite_mb": limite, "alerta_espaco": alerta,
            "banco": banco_ligado(cfg), "sem_banco": None if banco_ligado(cfg) else _sem_banco["motivo"]}


def resumo_do_turno(cfg) -> dict:
    """Números do que aconteceu (sem nenhum segredo): vão para o log público do GitHub."""
    import sqlite3
    c = sqlite3.connect(f"file:{Path(cfg.logs) / 'trabalho.db'}?mode=ro", uri=True)
    try:
        q = lambda s: c.execute(s).fetchone()[0]  # noqa: E731
        hoje = datetime.now().strftime("%Y-%m-%d")
        return {"tentativas_total": q("SELECT COUNT(*) FROM treino_tentativas"),
                "tentativas_hoje": q(f"SELECT COUNT(*) FROM treino_tentativas WHERE data_hora >= '{hoje}'"),
                "acertos_hoje": q(f"SELECT COALESCE(SUM(acertou),0) FROM treino_tentativas WHERE data_hora >= '{hoje}'"),
                "pessoas_hoje": q(f"SELECT COUNT(DISTINCT funcionario) FROM treino_tentativas WHERE data_hora >= '{hoje}'"),
                "conversas_total": q("SELECT COUNT(*) FROM interacoes"),
                "registros_de_log": q("SELECT COUNT(*) FROM logs_sistema") if c.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='logs_sistema'").fetchone() else 0}
    finally:
        c.close()


def mascarar_para_o_github(url: str) -> None:
    """No GitHub Actions, esconde host, usuário e senha do log público (o GitHub troca por ***)."""
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    from psycopg.conninfo import conninfo_to_dict
    c = conninfo_to_dict(url)
    for valor in (c.get("host"), c.get("user"), c.get("password"), os.environ.get("ROBO_PG_SENHA_LEITURA")):
        if valor:
            print(f"::add-mask::{valor}", flush=True)


def manifesto_inicial() -> dict | None:
    m = MEMORIA_INICIAL.with_name(MEMORIA_INICIAL.name.replace(".db.gz", ".db.manifesto.json"))
    return json.loads(m.read_text(encoding="utf-8")) if m.exists() else None
