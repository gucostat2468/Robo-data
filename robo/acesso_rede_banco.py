"""Libera o PostgreSQL do seu computador para o app de banco do CELULAR — só o usuário robo_leitura, só na rede de casa.

  python -m robo liberar-banco-celular       (no Windows: Prompt de Comando "Executar como administrador")

O que faz, em ordem (pode rodar de novo: não duplica nada):
  1. descobre o IP do computador na rede de casa e a rede dele (ex.: 192.168.0.0/24) — só aceita rede privada;
  2. faz uma cópia de segurança do pg_hba.conf (o "porteiro" do PostgreSQL) com data e hora no nome;
  3. acrescenta UMA linha no fim, marcada com '# robo: celular (somente leitura)':
        host  robo_dados  robo_leitura  192.168.0.0/24  scram-sha-256
     — nenhuma linha existente é alterada; nenhum outro usuário (nem o postgres, nem o robo_app) ganha acesso pela rede;
  4. ALTER SYSTEM SET listen_addresses = '*' (o PostgreSQL passa a ouvir na placa de rede; quem entra continua
     decidido pelo pg_hba.conf e pela senha);
  5. Windows: reinicia o serviço do PostgreSQL e cria a regra de firewall só para "Redes privadas" e só para a sub-rede local;
  6. imprime os campos exatos para preencher no app do celular. A senha NUNCA é impressa nem gravada: fica na variável
     de ambiente ROBO_PG_SENHA_LEITURA criada pelo 'instalar-banco'.
"""

from __future__ import annotations

import ipaddress
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

MARCADOR = "# robo: celular (somente leitura)"
NOME_REGRA_FIREWALL = "PostgreSQL robo (rede local)"


class PrecisaAdministrador(RuntimeError):
    pass


def rede_de(ip: str, prefixo: int = 24) -> str:
    """Rede /24 do IP (ex.: 192.168.0.23 → 192.168.0.0/24). Recusa IP que não seja de rede privada."""
    rede = ipaddress.ip_network(f"{ip}/{prefixo}", strict=False)
    validar_rede(str(rede))
    return str(rede)


def validar_rede(rede: str) -> str:
    r = ipaddress.ip_network(rede, strict=False)
    privadas = [ipaddress.ip_network(x) for x in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10")]
    if r.version != 4 or not any(r.subnet_of(p) for p in privadas):
        raise ValueError(f"{rede} não é uma rede privada de casa (192.168.x.x, 10.x.x.x, 172.16–31.x.x ou VPN 100.64.x.x): "
                         "nunca libere o banco para a internet")
    tailscale = r.subnet_of(ipaddress.ip_network("100.64.0.0/10"))  # a rede da VPN só tem aparelhos seus
    if r.prefixlen < 16 and not tailscale:
        raise ValueError(f"{rede} é larga demais: use a rede da sua casa (normalmente /24)")
    return str(r)


def linha_hba(banco: str, usuario: str, rede: str) -> str:
    return f"host    {banco}    {usuario}    {rede}    scram-sha-256    {MARCADOR}"


def incluir_no_hba(arquivo: Path, banco: str, usuario: str, rede: str) -> dict:
    """Acrescenta a linha (idempotente). Antes de mexer, guarda uma cópia com data e hora. Nunca altera linhas existentes."""
    arquivo = Path(arquivo)
    texto = arquivo.read_text(encoding="utf-8")
    nova = linha_hba(banco, usuario, rede)
    normal = lambda l: " ".join(l.split())  # noqa: E731 — compara sem depender de espaços/tabs
    if any(normal(l) == normal(nova) for l in texto.splitlines()):
        return {"alterado": False, "linha": nova, "copia": None}
    copia = arquivo.with_name(f"{arquivo.name}.antes_robo_{datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy2(arquivo, copia)
    if texto and not texto.endswith("\n"):
        texto += "\n"
    arquivo.write_text(texto + nova + "\n", encoding="utf-8")
    return {"alterado": True, "linha": nova, "copia": str(copia)}


def listen_inclui(valor: str, ip: str) -> bool:
    partes = {p.strip() for p in (valor or "").split(",")}
    return "*" in partes or "0.0.0.0" in partes or ip in partes


def _servico_windows() -> str | None:
    saida = subprocess.run(["sc", "query", "state=", "all"], capture_output=True, text=True, errors="replace").stdout
    nomes = [l.split(":", 1)[1].strip() for l in saida.splitlines() if l.strip().upper().startswith("SERVICE_NAME")]
    candidatos = sorted((n for n in nomes if n.lower().startswith("postgresql")), reverse=True)
    return candidatos[0] if candidatos else None


def _rodar_admin(comando: list[str]) -> None:
    r = subprocess.run(comando, capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        texto = (r.stdout + r.stderr).lower()
        if "acesso negado" in texto or "access is denied" in texto or "elevation" in texto or "elevação" in texto or r.returncode == 5:
            raise PrecisaAdministrador("Sem permissão: abra o Prompt como Administrador (botão direito em 'Prompt de Comando' "
                                       "→ 'Executar como administrador') e rode o comando de novo.")
        raise RuntimeError(f"{' '.join(comando[:3])} falhou: {(r.stdout + r.stderr).strip()[:300]}")


def liberar(superusuario: str, senha_super: str, host: str = "localhost", porta: int = 5432, banco: str = "robo_dados",
            usuario_leitura: str = "robo_leitura", rede: str | None = None, ip: str | None = None,
            reiniciar=None, windows: bool | None = None) -> dict:
    """reiniciar: função chamada para reiniciar o PostgreSQL quando listen_addresses mudar (None = Windows faz sozinho)."""
    import psycopg
    from psycopg import sql

    from robo.painel.celular import ip_da_rede
    windows = (os.name == "nt") if windows is None else windows
    ip = ip or ip_da_rede()
    if not ip:
        raise RuntimeError("Não achei o IP deste computador na rede: confira se o Wi-Fi está conectado.")
    rede = validar_rede(rede) if rede else rede_de(ip)
    passos = [f"IP deste computador na rede de casa: {ip} (rede {rede})"]
    base = {"host": host, "port": int(porta), "user": superusuario, "password": senha_super, "connect_timeout": 10}
    with psycopg.connect(dbname="postgres", autocommit=True, **base) as c:
        if not c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (usuario_leitura,)).fetchone():
            raise RuntimeError(f"O usuário {usuario_leitura} não existe: rode antes 'python -m robo instalar-banco'.")
        hba = Path(c.execute("SHOW hba_file").fetchone()[0])
        try:
            r = incluir_no_hba(hba, banco, usuario_leitura, rede)
        except PermissionError as e:
            raise PrecisaAdministrador("Sem permissão para editar o pg_hba.conf: abra o Prompt como Administrador "
                                       "e rode o comando de novo.") from e
        passos.append(f"pg_hba.conf: linha incluída ({r['linha'].split('#')[0].strip()}); cópia de antes em {r['copia']}"
                      if r["alterado"] else "pg_hba.conf: a linha do celular já existia (nada mudou)")
        c.execute("SELECT pg_reload_conf()")
        cifra = c.execute("SHOW password_encryption").fetchone()[0]
        if cifra != "scram-sha-256":
            passos.append(f"ATENÇÃO: o PostgreSQL guarda senhas como '{cifra}'. Rode: ALTER SYSTEM SET password_encryption = "
                          "'scram-sha-256'; reinicie e rode de novo 'python -m robo instalar-banco' para refazer a senha.")
        atual = c.execute("SHOW listen_addresses").fetchone()[0]
        precisa_reiniciar = not listen_inclui(atual, ip)
        if precisa_reiniciar:
            c.execute(sql.SQL("ALTER SYSTEM SET listen_addresses = {}").format(sql.Literal("*")))
            passos.append(f"listen_addresses: era '{atual}', agora '*' (quem entra continua sendo decidido pelo pg_hba.conf)")
        else:
            passos.append(f"listen_addresses já aceita a rede ('{atual}')")
    if precisa_reiniciar:
        if reiniciar:
            reiniciar()
            passos.append("PostgreSQL reiniciado")
        elif windows:
            servico = _servico_windows()
            if not servico:
                raise RuntimeError("Não achei o serviço do PostgreSQL (sc query). Reinicie o computador para aplicar.")
            _rodar_admin(["net", "stop", servico])
            _rodar_admin(["net", "start", servico])
            passos.append(f"serviço {servico} reiniciado")
        else:
            passos.append("fora do Windows: reinicie o PostgreSQL você mesmo para aplicar o listen_addresses")
    if windows:
        subprocess.run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={NOME_REGRA_FIREWALL}"],
                       capture_output=True, text=True, errors="replace")
        _rodar_admin(["netsh", "advfirewall", "firewall", "add", "rule", f"name={NOME_REGRA_FIREWALL}", "dir=in",
                      "action=allow", "protocol=TCP", f"localport={int(porta)}", "remoteip=localsubnet", "profile=private"])
        passos.append(f"firewall: porta {porta} liberada só para a sub-rede local e só em 'Redes privadas'")
    else:
        passos.append("fora do Windows: regra de firewall não aplicada (configure a do seu sistema, se houver)")
    return {"ok": True, "ip": ip, "rede": rede, "passos": passos,
            "app": {"Name": "Robô de Planilhas", "Hostname": ip, "Port": int(porta), "Database": banco,
                    "User": usuario_leitura,
                    "Password": "o valor de %ROBO_PG_SENHA_LEITURA% (no Prompt, digite: echo %ROBO_PG_SENHA_LEITURA%)",
                    "SSL": "desligado (ou 'prefer') — só dentro da rede de casa"}}
