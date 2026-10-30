# Remove o agente do Biony do PC. Rode no PowerShell COMO ADMINISTRADOR.
$ErrorActionPreference = "Stop"
Stop-ScheduledTask -TaskName "Biony Agente" -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "Biony Agente" -Confirm:$false -ErrorAction SilentlyContinue
Get-NetFirewallRule -DisplayName "Biony Agente" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
Get-Process pythonw -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*biony_agente.py*" } | Stop-Process -Force
Remove-Item -Recurse -Force (Join-Path $env:ProgramData "Biony") -ErrorAction SilentlyContinue
Write-Host "Agente do Biony removido." -ForegroundColor Green
