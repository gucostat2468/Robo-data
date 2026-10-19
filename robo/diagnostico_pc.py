"""Autodiagnóstico do computador onde a empresa roda: `python -m robo diagnostico`.

Só LÊ e testa — não altera nada (a única escrita é um arquivo de teste na pasta de logs, apagado em seguida).
Existe porque várias partes do robô só acontecem no Windows (registro do setx, trava de arquivo msvcrt, firewall,
serviço do PostgreSQL) e precisam ser conferidas no SEU computador, não só nos testes automáticos.

Cada item volta como (situação, título, detalhe, como corrigir); situação: ok | atencao | falha | nao_se_aplica.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

OK, ATENCAO, FALHA, NA = "ok", "atencao", "falha", "nao_se_aplica"


def _rodar(comando: list[str], tempo: int = 20) -> tuple[int, str]:
    try:
        r = subprocess.run(comando, capture_output=True, text=True, errors="replace", timeout=tempo)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, str(e)


def _python(cfg) -> tuple:
    v = sys.version_info
    if v >= (3, 11):
        return OK, "Python", f"{sys.version.split()[0]} em {sys.executable}", ""
    return FALHA, "Python", f"{sys.version.split()[0]} é antigo", "instale o Python 3.12 ou 3.13 (python.org) e rode instalar.bat"


def _dependencias(cfg) -> tuple:
    from robo import ti
    achados = ti.chk_dependencias(cfg)
    return (OK, "Bibliotecas", "todas no mínimo exigido", "") if not achados else \
        (FALHA, "Bibliotecas", "; ".join(achados), "rode instalar.bat de novo")


def _pastas(cfg) -> tuple:
    problemas = []
    for nome, p in cfg.pastas().items():
        try:
            Path(p).mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=p, prefix=".diag_", delete=True):
                pass
        except OSError as e:
            problemas.append(f"{nome}: {e}")
    return (OK, "Pastas de trabalho", f"{len(cfg.pastas())} pastas graváveis", "") if not problemas else \
        (FALHA, "Pastas de trabalho", "; ".join(problemas), "confira o OneDrive sincronizado e as permissões da pasta")


def _disco(cfg) -> tuple:
    livre = shutil.disk_usage(Path(cfg.logs).anchor or "/").free / 1024 ** 3
    if livre >= 10:
        return OK, "Espaço em disco", f"{livre:.0f} GB livres", ""
    return (ATENCAO if livre >= 2 else FALHA), "Espaço em disco", f"só {livre:.1f} GB livres", \
        "libere espaço: a memória e os backups crescem com o tempo"


def _senha_painel(cfg) -> tuple:
    return (OK, "Senha do painel", "definida", "") if (cfg.painel or {}).get("senha_hash") else \
        (FALHA, "Senha do painel", "o painel está sem senha", "rode: python -m robo senha")


def _trava_entre_programas(cfg) -> tuple:
    """Testa de verdade a trava que impede o robô e o Airflow de rodarem a mesma rotina juntos (msvcrt no Windows)."""
    raiz = Path(__file__).resolve().parents[1]
    nome = "diagnostico_trava"
    codigo = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {str(raiz)!r})
        from types import SimpleNamespace
        from robo import rotinas
        cfg = SimpleNamespace(logs={str(cfg.logs)!r})
        with rotinas._trava_entre_programas(cfg, {nome!r}) as ok:
            print("TRAVADO" if ok else "FALHOU", flush=True)
            time.sleep(8)
    """)
    from types import SimpleNamespace
    from robo import rotinas
    outro = subprocess.Popen([sys.executable, "-c", codigo], stdout=subprocess.PIPE, text=True)
    try:
        primeira = (outro.stdout.readline() or "").strip()
        with rotinas._trava_entre_programas(SimpleNamespace(logs=str(cfg.logs)), nome) as obtida:
            segundo_conseguiu = obtida
    finally:
        outro.kill()
        outro.wait()
    try:
        (Path(cfg.logs) / "rotinas" / f"{nome}.trava").unlink(missing_ok=True)
    except OSError:
        pass
    if primeira == "TRAVADO" and not segundo_conseguiu:
        return OK, "Trava entre programas", "o 2º programa foi barrado enquanto o 1º trabalhava", ""
    return FALHA, "Trava entre programas", f"1º: {primeira or 'sem resposta'}; 2º conseguiu travar: {segundo_conseguiu}", \
        "avise: o robô e o Airflow poderiam rodar a mesma rotina juntos"


def _variaveis(cfg) -> tuple:
    from robo.banco import variavel_ambiente
    b = cfg.banco or {}
    if not b.get("habilitado"):
        return NA, "Senhas do banco", "PostgreSQL desligado no config.yaml", "rode: python -m robo instalar-banco"
    faltam = [v for v in (b.get("senha_variavel_ambiente"), b.get("senha_leitura_variavel_ambiente")) if v and not variavel_ambiente(v)]
    if not faltam:
        origem = "no processo" if all(os.environ.get(v) for v in (b.get("senha_variavel_ambiente"),) if v) else "no registro do Windows (setx)"
        if b.get("senha"):
            return ATENCAO, "Senhas do banco", f"encontradas ({origem}), MAS há senha gravada no config.yaml", \
                "apague a linha 'senha:' do config.yaml (a variável de ambiente basta)"
        return OK, "Senhas do banco", f"encontradas ({origem}); nenhuma senha no config.yaml", ""
    return FALHA, "Senhas do banco", f"não achei: {', '.join(faltam)}", "rode de novo: python -m robo instalar-banco"


def _postgres(cfg) -> tuple:
    b = cfg.banco or {}
    if not b.get("habilitado"):
        return NA, "PostgreSQL", "desligado no config.yaml", ""
    from robo.banco import Banco
    try:
        banco = Banco(b, Path(cfg.base))
        with banco.conectar() as c:
            versao = c.execute("SHOW server_version").fetchone()[0]
            schemas = [r[0] for r in c.execute("SELECT nspname FROM pg_namespace WHERE nspname IN "
                                               "('bruto','tratado','analitico','robo','analise','laboratorio','treino')")]
            memoria = c.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='robo'").fetchone()[0]
        leitura_ok = None
        if b.get("usuario_leitura"):
            try:
                with banco.conectar(leitura=True) as c:
                    c.execute("CREATE TABLE robo.diag_escrita_proibida (x int)")
                leitura_ok = False
            except Exception:
                leitura_ok = True
        det = f"versão {versao}; {len(schemas)}/7 schemas; {memoria} tabelas da memória no schema robo"
        if leitura_ok is False:
            return FALHA, "PostgreSQL", det + "; o usuário de leitura CONSEGUIU escrever", "rode de novo: python -m robo instalar-banco"
        return (OK if len(schemas) == 7 else ATENCAO), "PostgreSQL", det + ("; usuário de leitura só lê" if leitura_ok else ""), \
            "" if len(schemas) == 7 else "rode: python -m robo instalar-banco"
    except Exception as e:
        return FALHA, "PostgreSQL", f"{type(e).__name__}: {e}"[:300], "Windows: Serviços → postgresql-x64 → Iniciar"


def _pg_dump(cfg) -> tuple:
    from robo import backup
    caminho = backup.localizar_pg_dump()
    if caminho:
        return OK, "pg_dump (backup do PostgreSQL)", caminho, ""
    if not (cfg.banco or {}).get("habilitado"):
        return NA, "pg_dump (backup do PostgreSQL)", "PostgreSQL desligado", ""
    return ATENCAO, "pg_dump (backup do PostgreSQL)", "não encontrado: o backup do PostgreSQL vira cópia em CSV", \
        "instale o PostgreSQL com as 'Command Line Tools' marcadas"


def _backups(cfg) -> tuple:
    from robo import backup
    u = backup.ultimo_sqlite(cfg)
    if not u:
        return ATENCAO, "Backups", "ainda nenhum backup da memória", "abra o robô: o 1º backup sai na 1ª hora"
    return OK, "Backups", f"último da memória: {u.get('data_hora')} ({u.get('tabelas')} tabelas, {u.get('linhas')} linhas)", \
        "copie a pasta logs\\backups_sqlite para um HD externo 1× por mês"


def _rede(cfg) -> tuple:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # UDP não envia nada: só pergunta ao sistema qual placa sairia
        ip = s.getsockname()[0]
        s.close()
    except OSError:
        return ATENCAO, "Rede de casa", "sem rede (o celular não alcança o notebook)", "conecte o Wi-Fi"
    if os.name != "nt":
        return OK, "Rede de casa", f"IP {ip}", ""
    cod, saida = _rodar(["powershell", "-NoProfile", "-Command",
                         "Get-NetConnectionProfile | Select-Object -ExpandProperty NetworkCategory"])
    if cod == 0 and "Public" in saida and "Private" not in saida:
        return ATENCAO, "Rede de casa", f"IP {ip}, mas o Windows marcou a rede como PÚBLICA: o celular não vai alcançar",\
            "Configurações → Rede e Internet → Wi-Fi → (sua rede) → Tipo de perfil de rede: Privada"
    return OK, "Rede de casa", f"IP {ip}" + (f" (perfil: {saida.strip()})" if cod == 0 and saida else ""), ""


def _celular(cfg) -> tuple:
    conf = (cfg.dados.get("celular") or {})
    if not conf.get("habilitado"):
        return NA, "App do celular", "desligado", "para ligar: python -m robo celular --ligar"
    porta = int(conf.get("porta") or 8766)
    if os.name != "nt":
        return OK, "App do celular", f"ligado na porta {porta}", ""
    cod, saida = _rodar(["netsh", "advfirewall", "firewall", "show", "rule", "name=all", "dir=in"], 30)
    tem_python = cod == 0 and "python" in saida.lower()
    return (OK if tem_python else ATENCAO), "App do celular", f"ligado na porta {porta}" + \
        ("; o firewall tem regra para o Python" if tem_python else "; não vi regra de firewall para o Python"), \
        "" if tem_python else "abra o robô: na 1ª vez o Windows pergunta — marque SÓ 'Redes privadas'"


def _servico_postgres(cfg) -> tuple:
    if os.name != "nt":
        return NA, "Serviço do PostgreSQL", "só no Windows", ""
    cod, saida = _rodar(["sc", "query", "state=", "all"])
    nomes = [l.split(":", 1)[1].strip() for l in saida.splitlines() if l.strip().upper().startswith("SERVICE_NAME")
             and "postgresql" in l.lower()]
    if not nomes:
        return ATENCAO, "Serviço do PostgreSQL", "não encontrei serviço do PostgreSQL", "instale o PostgreSQL 16 (postgresql.org)"
    cod, cfg_saida = _rodar(["sc", "qc", nomes[0]])
    automatico = "AUTO_START" in cfg_saida
    return (OK if automatico else ATENCAO), "Serviço do PostgreSQL", f"{nomes[0]} ({'inicia sozinho' if automatico else 'início MANUAL'})", \
        "" if automatico else "Serviços → " + nomes[0] + " → Tipo de inicialização: Automático"


def _inicializacao(cfg) -> tuple:
    if os.name != "nt":
        return NA, "Ligar com o Windows", "só no Windows", ""
    try:
        from robo.painel import sistema
        ligado = sistema.inicializacao_ligada()
    except Exception as e:
        return ATENCAO, "Ligar com o Windows", f"não consegui verificar ({e})", ""
    return (OK if ligado else ATENCAO), "Ligar com o Windows", "sim" if ligado else "não: se o notebook reiniciar, a empresa para", \
        "" if ligado else "rode: python -m robo inicializacao ligar"


def _vigia(cfg) -> tuple:
    from robo import vigia
    ligada = vigia.tarefa_ligada()
    if ligada is None:
        return NA, "Vigia (religa se cair)", "só no Windows", ""
    return (OK if ligada else ATENCAO), "Vigia (religa se cair)", "tarefa agendada ativa (a cada 5 min)" if ligada else \
        "desligado: se o robô cair, ninguém religa", "" if ligada else "rode: python -m robo vigia ligar"


def _registro_total(cfg) -> tuple:
    from robo import registro_total
    faltando = registro_total.cobertura(cfg)
    if faltando:
        return ATENCAO, "Tudo registrado no banco", f"{len(faltando)} arquivo(s) fora do banco: {', '.join(faltando[:5])}", \
            "me mande esta lista: é um tipo de arquivo novo que precisa entrar no registro total"
    return OK, "Tudo registrado no banco", "nenhum arquivo de texto da pasta de logs fica fora do banco", ""


VERIFICACOES = [_python, _dependencias, _pastas, _disco, _senha_painel, _trava_entre_programas, _variaveis, _postgres,
                _servico_postgres, _pg_dump, _backups, _rede, _celular, _inicializacao,
                _vigia, _registro_total]


def rodar(cfg) -> list[dict]:
    itens = []
    for f in VERIFICACOES:
        try:
            situacao, titulo, detalhe, corrigir = f(cfg)
        except Exception as e:
            situacao, titulo, detalhe, corrigir = FALHA, f.__name__.strip("_"), f"a verificação quebrou: {type(e).__name__}: {e}", \
                "me mande esta linha"
        itens.append({"situacao": situacao, "titulo": titulo, "detalhe": detalhe, "corrigir": corrigir})
    return itens
