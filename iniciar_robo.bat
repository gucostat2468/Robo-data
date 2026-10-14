@echo off
REM Liga o robo com uma janela aberta (voce ve tudo o que ele faz). Feche a janela para desligar.
cd /d "%~dp0"
title Robo de Planilhas - monitorando Bases-Limpeza
".venv\Scripts\python.exe" -m robo monitorar
pause
