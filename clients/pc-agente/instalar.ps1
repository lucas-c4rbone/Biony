# Instala o agente do Biony no PC (Windows). Rode no PowerShell COMO ADMINISTRADOR:
#   powershell -ExecutionPolicy Bypass -File clients\pc-agente\instalar.ps1
#
# O que faz:
#   1. Copia o agente para C:\ProgramData\Biony e cria um token novo (só SYSTEM e admins leem).
#   2. Cria a tarefa "Biony Agente", que roda como SYSTEM a cada boot, antes do login.
#   3. Libera a porta 8421 no firewall SOMENTE para a rede do Tailscale (100.64.0.0/10).
#   4. Mostra o token para você colocar no .env do servidor.

$ErrorActionPreference = "Stop"
$porta = 8421
$destino = Join-Path $env:ProgramData "Biony"
$script = Join-Path $destino "biony_agente.py"
$config = Join-Path $destino "agente.json"

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw "Abra o PowerShell como Administrador e rode de novo." }

# Python de verdade (não o atalho da Microsoft Store), e a versão sem janela (pythonw).
$python = & python -c "import sys; print(sys.executable)"
if (-not $python -or $python -like "*WindowsApps*") { throw "Python não encontrado. Instale o Python e rode de novo." }
$pythonw = Join-Path (Split-Path $python) "pythonw.exe"
if (-not (Test-Path $pythonw)) { throw "Não achei $pythonw." }

New-Item -ItemType Directory -Force -Path $destino | Out-Null
Copy-Item -Force (Join-Path $PSScriptRoot "biony_agente.py") $script

if (Test-Path $config) {
    $token = (Get-Content $config -Raw | ConvertFrom-Json).token
    Write-Host "Mantendo o token que já existia."
} else {
    $bytes = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $token = [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
    @{ token = $token; porta = $porta } | ConvertTo-Json | Set-Content -Encoding UTF8 $config
}
# Só SYSTEM e Administradores podem ler a pasta (o token fica nela).
icacls $destino /inheritance:r /grant:r "SYSTEM:(OI)(CI)F" "Administrators:(OI)(CI)F" | Out-Null

$acao = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$script`""
$gatilho = New-ScheduledTaskTrigger -AtStartup
$conta = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "Biony Agente" -Action $acao -Trigger $gatilho -Principal $conta `
    -Settings $ajustes -Force | Out-Null

Get-NetFirewallRule -DisplayName "Biony Agente" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName "Biony Agente" -Direction Inbound -Protocol TCP -LocalPort $porta `
    -RemoteAddress "100.64.0.0/10" -Action Allow | Out-Null

Stop-ScheduledTask -TaskName "Biony Agente" -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskName "Biony Agente"

$ip = (& tailscale ip -4 2>$null | Select-Object -First 1)
Write-Host ""
Write-Host "Agente instalado e rodando." -ForegroundColor Green
Write-Host "Coloque estas duas linhas no .env do SERVIDOR (~/biony/.env):"
Write-Host ""
Write-Host "PC_AGENT_URL=http://$($ip):$porta"
Write-Host "PC_AGENT_TOKEN=$token"
Write-Host ""
Write-Host "Depois: cd ~/biony/deploy && docker compose up -d --force-recreate"
