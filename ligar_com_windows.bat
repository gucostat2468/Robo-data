@echo off
REM Faz o robo ligar sozinho (sem janela) toda vez que voce entrar no Windows.
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
echo CreateObject("WScript.Shell").Run """%~dp0iniciar_robo_oculto.vbs""", 0, False > "%STARTUP%\RoboPlanilhas.vbs"
echo Pronto! O robo vai ligar automaticamente no proximo login.
echo Para desfazer, apague o arquivo: "%STARTUP%\RoboPlanilhas.vbs"
pause
