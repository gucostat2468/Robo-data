@echo off
REM Mostra pastas, arquivos na fila, reprovados e ultimos processamentos.
cd /d "%~dp0.."
".venv\Scripts\python.exe" -m robo status
pause
