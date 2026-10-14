@echo off
setlocal EnableDelayedExpansion
REM ==============================================================
REM  Instala o Robo de Planilhas (rodar UMA vez, ou apos atualizar)
REM ==============================================================
cd /d "%~dp0"
title Instalando Robo de Planilhas

REM Versoes suportadas: 3.11 a 3.14. Versoes mais novas (ex.: 3.15) ainda nao tem
REM pandas/PyYAML prontos para Windows e o pip tentaria compilar (exige Visual C++).
set "VERIFICA=import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,14) else 1)"

echo [1/5] Procurando uma versao compativel do Python (3.11 a 3.14)...
set "PY="
for %%V in (3.13 3.12 3.14 3.11) do (
  if not defined PY (
    py -%%V -c "%VERIFICA%" >nul 2>nul && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "%VERIFICA%" >nul 2>nul && set "PY=python"
)
if not defined PY (
  where py >nul 2>nul
  if !errorlevel!==0 (
    echo     Nenhuma versao compativel instalada. Instalando Python 3.13 ao lado da sua versao atual...
    echo     ^(sua versao atual NAO sera removida^)
    py install 3.13
    py -3.13 -c "%VERIFICA%" >nul 2>nul && set "PY=py -3.13"
  )
)
if not defined PY (
  echo.
  echo [ERRO] Nao encontrei Python 3.11 a 3.14 neste computador.
  echo Instale o Python 3.13: https://www.python.org/downloads/release/python-3139/
  echo Na instalacao, marque "Add python.exe to PATH". Depois rode este arquivo de novo.
  pause
  exit /b 1
)
for /f "delims=" %%I in ('%PY% -c "import sys; print(sys.version.split()[0])"') do echo     Usando Python %%I

echo [2/5] Conferindo o ambiente virtual (.venv)...
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "%VERIFICA%" >nul 2>nul
  if errorlevel 1 (
    echo     Ambiente antigo criado com versao incompativel. Recriando...
    rmdir /s /q ".venv"
  )
)
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv
if not exist ".venv\Scripts\python.exe" (
  echo [ERRO] Nao consegui criar o ambiente virtual.
  pause
  exit /b 1
)

echo [3/5] Instalando bibliotecas (pandas, openpyxl, xlrd, PyYAML)...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
REM --only-binary: usa apenas pacotes prontos (nunca tenta compilar)
".venv\Scripts\python.exe" -m pip install -r requirements.txt --only-binary=:all: --quiet
if errorlevel 1 (
  echo [ERRO] Falha ao instalar as bibliotecas. Copie a mensagem acima e envie para analise.
  pause
  exit /b 1
)

echo [4/5] Criando config.yaml (se ainda nao existir)...
if not exist "config.yaml" copy "config.exemplo.yaml" "config.yaml" >nul

echo [5/5] Verificando pastas do OneDrive...
".venv\Scripts\python.exe" -m robo status

echo.
echo Instalacao concluida. Para ligar o robo, de dois cliques em iniciar_robo.bat
pause
