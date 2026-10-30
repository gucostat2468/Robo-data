"""Integração com o Windows: abrir pastas/arquivos, notificações, janela do app,
inicialização automática e atalho na área de trabalho. Em outros sistemas, faz o possível ou ignora."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

from robo.config import RAIZ_PROJETO

log = logging.getLogger("robo")

EH_WINDOWS = os.name == "nt"
NOME_ATALHO = "Robô de Planilhas"
ARQUIVO_INICIALIZACAO = "RoboPlanilhas.vbs"
SEM_JANELA = 0x08000000  # CREATE_NO_WINDOW


def abrir_no_sistema(caminho: Path) -> None:
    """Abre pasta no Explorador ou arquivo no programa padrão (ex.: Excel)."""
    if EH_WINDOWS:
        os.startfile(str(caminho))  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(caminho)])
    elif shutil.which("xdg-open"):
        subprocess.Popen(["xdg-open", str(caminho)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _powershell(script: str, esperar: bool = False) -> None:
    comando = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", "-"]
    proc = subprocess.Popen(comando, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=SEM_JANELA if EH_WINDOWS else 0)
    proc.stdin.write(script.encode("utf-8"))
    proc.stdin.close()
    if esperar:
        proc.wait(timeout=30)


def _ps_texto(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def notificar(titulo: str, mensagem: str) -> None:
    """Notificação nativa do Windows (canto inferior direito). Falhas são silenciosas."""
    if not EH_WINDOWS:
        return
    script = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$x = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$t = $x.GetElementsByTagName('text')
$t.Item(0).AppendChild($x.CreateTextNode({_ps_texto(titulo)})) > $null
$t.Item(1).AppendChild($x.CreateTextNode({_ps_texto(mensagem)})) > $null
$n = [Windows.UI.Notifications.ToastNotification]::new($x)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}}\\WindowsPowerShell\\v1.0\\powershell.exe').Show($n)
"""
    try:
        _powershell(script)
    except Exception:
        log.debug("Notificação não exibida", exc_info=True)


def _navegador_app() -> str | None:
    candidatos = []
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        if base:
            candidatos += [Path(base) / "Microsoft/Edge/Application/msedge.exe",
                           Path(base) / "Google/Chrome/Application/chrome.exe"]
    for c in candidatos:
        if c.exists():
            return str(c)
    return shutil.which("msedge") or shutil.which("chrome")


def abrir_janela(url: str) -> None:
    """Abre o painel numa janela própria (modo aplicativo do Edge/Chrome, sem barra de endereço)."""
    navegador = _navegador_app() if EH_WINDOWS else None
    if navegador:
        try:
            subprocess.Popen([navegador, f"--app={url}", "--window-size=1360,900"])
            return
        except OSError:
            pass
    webbrowser.open(url)


# ------------------------------------------------------------------ inicialização / atalhos
def pasta_inicializacao() -> Path | None:
    if not EH_WINDOWS or not os.environ.get("APPDATA"):
        return None
    return Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup"


def inicializacao_ligada() -> bool:
    pasta = pasta_inicializacao()
    return bool(pasta and (pasta / ARQUIVO_INICIALIZACAO).exists())


def definir_inicializacao(ligar: bool) -> bool:
    pasta = pasta_inicializacao()
    if pasta is None:
        raise RuntimeError("Inicialização automática só existe no Windows.")
    arquivo = pasta / ARQUIVO_INICIALIZACAO
    if ligar:
        lancador = RAIZ_PROJETO / "Abrir Robo de Planilhas.vbs"
        # UTF-16 com BOM: o Windows Script Host lê corretamente caminhos com acento
        arquivo.write_text(f'CreateObject("WScript.Shell").Run """{lancador}"" /oculto", 0, False\r\n', encoding="utf-16")
    elif arquivo.exists():
        arquivo.unlink()
    return inicializacao_ligada()


def criar_atalhos() -> list[str]:
    """Cria atalho na Área de Trabalho e no Menu Iniciar apontando para o lançador .vbs."""
    if not EH_WINDOWS:
        raise RuntimeError("Atalhos só podem ser criados no Windows.")
    lancador = RAIZ_PROJETO / "Abrir Robo de Planilhas.vbs"
    icone = RAIZ_PROJETO / "robo" / "painel" / "estaticos" / "robo.ico"
    script = f"""
$sh = New-Object -ComObject WScript.Shell
$destinos = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))
foreach ($d in $destinos) {{
  $l = $sh.CreateShortcut((Join-Path $d {_ps_texto(NOME_ATALHO + '.lnk')}))
  $l.TargetPath = 'wscript.exe'
  $l.Arguments = '"' + {_ps_texto(lancador)} + '"'
  $l.WorkingDirectory = {_ps_texto(RAIZ_PROJETO)}
  $l.IconLocation = {_ps_texto(icone)}
  $l.Description = 'Painel do Robo de Planilhas'
  $l.Save()
}}
"""
    _powershell(script, esperar=True)
    return ["Área de Trabalho", "Menu Iniciar"]


def criar_atalho_estudio() -> list[str]:
    """Atalho 'Robô de Planilhas — Estúdio' na Área de Trabalho e no Menu Iniciar: dois cliques abrem o Estúdio no
    navegador (sem janela preta: usa o pythonw do mesmo Python)."""
    if not EH_WINDOWS:
        raise RuntimeError("Atalhos só podem ser criados no Windows.")
    import sys
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    alvo = pythonw if pythonw.exists() else python
    icone = RAIZ_PROJETO / "robo" / "painel" / "estaticos" / "robo.ico"
    script = f"""
$sh = New-Object -ComObject WScript.Shell
$destinos = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))
foreach ($d in $destinos) {{
  $l = $sh.CreateShortcut((Join-Path $d {_ps_texto('Robô de Planilhas - Estúdio.lnk')}))
  $l.TargetPath = {_ps_texto(alvo)}
  $l.Arguments = '-m robo estudio'
  $l.WorkingDirectory = {_ps_texto(RAIZ_PROJETO)}
  $l.IconLocation = {_ps_texto(icone)}
  $l.Description = 'Tratar planilhas e consultar em SQL (Robô de Planilhas)'
  $l.Save()
}}
"""
    _powershell(script, esperar=True)
    return ["Área de Trabalho", "Menu Iniciar"]
