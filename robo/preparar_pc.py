"""Prepara o computador do dono de uma vez: `python -m robo preparar-pc --memoria trabalho_AAAAMMDD_HHMMSS.db.gz`.

Rode no Prompt de Comando ABERTO COMO ADMINISTRADOR (firewall, PostgreSQL e tarefa agendada pedem isso).
Cada passo é um comando que já existe (dá para rodar um por um também); a sequência para no primeiro que falhar e diz
qual foi. Pede a senha do usuário 'postgres' UMA vez e usa nos passos que precisam dela.
"""

from __future__ import annotations

import os
from pathlib import Path


def passos(memoria: str | None, tem_senha_painel: bool, windows: bool) -> list[tuple[str, list[str], bool]]:
    """(título, argumentos do comando, obrigatório). Não obrigatório = falha vira aviso e segue."""
    lista = [("Banco PostgreSQL real (usuários, schemas, senhas nas variáveis)", ["instalar-banco"], True)]
    if memoria:
        lista.append(("Memória da empresa (tudo o que já foi registrado)", ["importar-memoria", memoria], True))
    if not tem_senha_painel:
        lista.append(("Senha do painel (a mesma do celular)", ["senha"], True))
    lista.append(("App do celular (somente leitura, rede de casa)", ["celular", "--ligar"], True))
    if windows:
        lista += [("App de banco do celular (só robo_leitura, só a rede de casa)", ["liberar-banco-celular"], False),
                  ("Ligar junto com o Windows", ["inicializacao", "ligar"], True),
                  ("Vigia: religa o robô se ele cair", ["vigia", "ligar"], True)]
    lista.append(("Diagnóstico final do computador", ["diagnostico"], False))
    return lista


def preparar(principal, caminho_config: str | None, memoria: str | None) -> int:
    import getpass
    from robo.config import RAIZ_PROJETO
    arq = Path(caminho_config) if caminho_config else RAIZ_PROJETO / "config.yaml"
    if memoria and not Path(memoria).exists():
        print(f"Não achei o arquivo da memória: {memoria}")
        return 1
    if os.environ.get("ROBO_PG_SUPER_SENHA") is None:
        print("Senha do usuário 'postgres' do PostgreSQL (a que você criou ao instalar o PostgreSQL):")
        os.environ["ROBO_PG_SUPER_SENHA"] = getpass.getpass("Senha: ")
    tem_senha = False
    if arq.exists():
        import yaml
        tem_senha = bool(((yaml.safe_load(arq.read_text(encoding="utf-8")) or {}).get("painel") or {}).get("senha_hash"))
    base = ["--config", str(arq)] if caminho_config else []
    lista = passos(memoria, tem_senha, os.name == "nt")
    avisos = []
    for i, (titulo, args, obrigatorio) in enumerate(lista, 1):
        print(f"\n=== Passo {i}/{len(lista)}: {titulo}  (python -m robo {' '.join(args)})")
        codigo = principal(base + args)
        if codigo:
            if obrigatorio:
                print(f"\n✘ Parei no passo {i} ({titulo}). Corrija o que apareceu acima e rode de novo: os passos já feitos "
                      "não estragam nada se repetidos.")
                return codigo
            avisos.append(titulo)
    print("\n✔ Computador preparado." + (f" Pontos de atenção: {', '.join(avisos)}." if avisos else ""))
    print("Agora: feche esta janela e abra o robô pelo atalho (ou: python -m robo app). No celular, use o endereço que o "
          "passo do celular mostrou.")
    return 0
