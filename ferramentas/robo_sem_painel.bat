@echo off
REM Liga o robo SEM o painel, mostrando o log nesta janela (util para diagnostico).
REM Feche a janela para desligar. No dia a dia, prefira o atalho "Robo de Planilhas".
cd /d "%~dp0.."
title Robo de Planilhas - modo texto
".venv\Scripts\python.exe" -m robo monitorar
pause
