@echo off
REM Desliga o robo que esta rodando em segundo plano (painel ou modo texto).
powershell -NoProfile -Command "try { Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/api/sair -Headers @{'X-Robo-Painel'='1'} -TimeoutSec 3 | Out-Null; Write-Host 'Robo encerrado.' } catch { Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'pythonw.exe' -or $_.Name -eq 'python.exe') -and $_.CommandLine -like '*-m robo*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host ('Robo encerrado (PID ' + $_.ProcessId + ')') } }"
pause
