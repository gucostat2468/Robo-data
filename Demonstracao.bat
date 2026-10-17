@echo off
REM Abre a empresa de DEMONSTRACAO (pasta separada, planilhas de 6 areas). Nao mexe na sua producao.
REM Para recomecar do zero:  Demonstracao.bat --recomecar
cd /d "%~dp0"
".venv\Scripts\python.exe" -m robo demo %*
pause
