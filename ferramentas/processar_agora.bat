@echo off
REM Processa uma unica vez tudo o que estiver em Bases-Limpeza (nao use com o robo aberto).
cd /d "%~dp0.."
".venv\Scripts\python.exe" -m robo varrer
pause
