@echo off
REM Arraste uma planilha para cima deste arquivo: mostra o que o robo faria, SEM gravar nem mover nada.
cd /d "%~dp0"
if "%~1"=="" (
  echo Arraste uma planilha para cima deste arquivo .bat
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m robo diagnosticar "%~1"
pause
