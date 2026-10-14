@echo off
REM Processa uma unica vez tudo o que estiver em Bases-Limpeza (sem ficar monitorando).
cd /d "%~dp0"
".venv\Scripts\python.exe" -m robo varrer
pause
