@echo off
REM ==============================================================
REM  Instala o Robo de Planilhas (rodar UMA vez, ou apos atualizar)
REM ==============================================================
cd /d "%~dp0"
title Instalando Robo de Planilhas

set "PY=python"
where py >nul 2>nul
if %errorlevel%==0 set "PY=py -3"

%PY% --version >nul 2>nul
if not %errorlevel%==0 (
  echo.
  echo [ERRO] Python nao encontrado.
  echo Instale em https://www.python.org/downloads/ e marque a opcao "Add python.exe to PATH".
  pause
  exit /b 1
)

echo [1/4] Criando ambiente virtual (.venv)...
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv

echo [2/4] Instalando bibliotecas (pandas, openpyxl, xlrd, PyYAML)...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet
if not %errorlevel%==0 (
  echo [ERRO] Falha ao instalar as bibliotecas. Verifique sua internet/proxy.
  pause
  exit /b 1
)

echo [3/4] Criando config.yaml (se ainda nao existir)...
if not exist "config.yaml" copy "config.exemplo.yaml" "config.yaml" >nul

echo [4/4] Verificando pastas do OneDrive...
".venv\Scripts\python.exe" -m robo status

echo.
echo Instalacao concluida. Para ligar o robo, de dois cliques em iniciar_robo.bat
pause
