@echo off
REM Desliga o robo que esta rodando em segundo plano.
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'pythonw.exe' -or $_.Name -eq 'python.exe') -and $_.CommandLine -like '*robo monitorar*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host ('Robo encerrado (PID ' + $_.ProcessId + ')') }"
pause
