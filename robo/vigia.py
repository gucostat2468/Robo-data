"""Vigia: a empresa não fica parada se o robô cair. `python -m robo vigia ligar|desligar|status|checar`.

- `checar` (o que a tarefa agendada roda a cada 5 minutos): se o robô NÃO está rodando (a trava robo.lock está livre),
  liga o robô em segundo plano; se está rodando mas o painel não responde, registra 'sem_resposta' e avisa no canal
  (não mata nada sozinho: matar processo travado no meio de uma gravação é pior que esperar). Cada checagem que achou
  algo vira registro em vigia_eventos (imutável) — dá para ver no banco cada queda e cada religada.
- `ligar` (Windows): cria a tarefa agendada "RoboPlanilhas\\Vigia" (a cada 5 min, com o seu usuário, sem janela).
  Junto com "inicializacao ligar", a empresa volta sozinha depois de reiniciar o Windows, de atualizações e de quedas.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from robo.trabalho import Trabalho, _agora, proteger

NOME_TAREFA = r"RoboPlanilhas\Vigia"
ESQUEMA = """CREATE TABLE IF NOT EXISTS vigia_eventos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, evento TEXT, detalhe TEXT);
CREATE TRIGGER IF NOT EXISTS vigia_eventos_sem_alterar BEFORE UPDATE ON vigia_eventos
BEGIN SELECT RAISE(ABORT, 'registro permanente: vigia_eventos não pode ser alterado'); END;"""


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    with tb.tx() as c:
        c.executescript(ESQUEMA)
        proteger(c)
    return tb


def _registrar(cfg, evento: str, detalhe: str = "") -> None:
    with _tb(cfg).tx() as c:
        c.execute("INSERT INTO vigia_eventos (data_hora, evento, detalhe) VALUES (?,?,?)", (_agora(), evento, detalhe[:1000]))


def robo_rodando(cfg) -> bool:
    """A trava do robô (robo.lock) está presa = há um robô rodando (o sistema solta a trava se o processo morrer)."""
    from robo.monitor import TravaInstancia
    try:
        with TravaInstancia(Path(cfg.logs)):
            return False
    except RuntimeError:
        return True


def _comando_app(caminho_config: str | None) -> list[str]:
    exe = Path(sys.executable)
    if os.name == "nt" and (exe.parent / "pythonw.exe").exists():
        exe = exe.parent / "pythonw.exe"  # sem janela preta
    cmd = [str(exe), "-m", "robo"]
    if caminho_config:
        cmd += ["--config", str(caminho_config)]
    return cmd + ["app", "--sem-janela"]


def ligar_robo(caminho_config: str | None = None) -> int:
    from robo.config import RAIZ_PROJETO
    opcoes = {"cwd": str(RAIZ_PROJETO), "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        opcoes["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        opcoes["start_new_session"] = True
    return subprocess.Popen(_comando_app(caminho_config), **opcoes).pid


def checar(cfg, caminho_config: str | None = None, porta: int | None = None) -> dict:
    from robo.painel.servidor import ja_rodando
    porta = int(porta or (cfg.painel or {}).get("porta", 8765))
    if not robo_rodando(cfg):
        pid = ligar_robo(caminho_config)
        _registrar(cfg, "religou", f"o robô não estava rodando; liguei de novo (processo {pid})")
        return {"situacao": "religou", "pid": pid}
    if not ja_rodando(porta):
        _registrar(cfg, "sem_resposta", f"o robô está rodando, mas o painel (porta {porta}) não respondeu")
        try:
            from robo.canal import Canal
            Canal(cfg).postar("coord_devops", f"Vigia: o robô está rodando mas o painel não respondeu às "
                                              f"{datetime.now():%H:%M}. Se repetir, feche e abra o robô.", "ti", "alerta")
        except Exception:
            pass
        return {"situacao": "sem_resposta"}
    return {"situacao": "ok"}


def eventos(cfg, limite: int = 50) -> list[dict]:
    with _tb(cfg).tx() as c:
        return [dict(r) for r in c.execute("SELECT * FROM vigia_eventos ORDER BY id DESC LIMIT ?", (limite,))]


# ------------------------------------------------------------------------------------------- tarefa agendada (Windows)
def _lancador() -> Path:
    """Arquivo .pyw na pasta do projeto: o pythonw roda sem janela e já entra na pasta certa."""
    from robo.config import RAIZ_PROJETO
    arq = RAIZ_PROJETO / "robo_vigia.pyw"
    arq.write_text("import os, sys\n"
                   f"os.chdir({str(RAIZ_PROJETO)!r})\n"
                   f"sys.path.insert(0, {str(RAIZ_PROJETO)!r})\n"
                   "from robo.comandos import principal\n"
                   "raise SystemExit(principal(['vigia', 'checar']))\n", encoding="utf-8")
    return arq


def ligar_tarefa(minutos: int = 5) -> str:
    if os.name != "nt":
        raise RuntimeError("A tarefa agendada só existe no Windows. Fora dele, use o agendador do sistema (cron/systemd) "
                           "chamando: python -m robo vigia checar")
    exe = Path(sys.executable)
    pythonw = exe.parent / "pythonw.exe" if (exe.parent / "pythonw.exe").exists() else exe
    acao = f'"{pythonw}" "{_lancador()}"'
    r = subprocess.run(["schtasks", "/Create", "/F", "/SC", "MINUTE", "/MO", str(int(minutos)), "/TN", NOME_TAREFA,
                        "/TR", acao], capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        raise RuntimeError((r.stdout + r.stderr).strip()[:400] or "schtasks falhou")
    return acao


def desligar_tarefa() -> None:
    if os.name == "nt":
        subprocess.run(["schtasks", "/Delete", "/F", "/TN", NOME_TAREFA], capture_output=True, text=True, errors="replace")


def tarefa_ligada() -> bool | None:
    if os.name != "nt":
        return None
    r = subprocess.run(["schtasks", "/Query", "/TN", NOME_TAREFA], capture_output=True, text=True, errors="replace")
    return r.returncode == 0
