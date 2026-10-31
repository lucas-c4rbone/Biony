<#
Biony por palavra de ativação: inicia sozinho quando você entra no Windows, em segundo plano (sem janela).

  .\instalar_ativacao.ps1            instala (atalho na pasta Inicializar) e já inicia
  .\instalar_ativacao.ps1 -Parar     para o programa agora (volta a iniciar no próximo login)
  .\instalar_ativacao.ps1 -Remover   para o programa e tira da inicialização

Opções: -Modelo small|base   -Espera 8   -SemIniciar
O que ele faz fica em clients\pc\ativacao.log. Não precisa de administrador.
#>
param(
    [switch]$Remover,
    [switch]$Parar,
    [switch]$SemIniciar,
    [string]$Modelo = "small",
    [double]$Espera = 8,
    [string]$PastaInicializacao = [Environment]::GetFolderPath("Startup")  # só muda em testes
)

$ErrorActionPreference = "Stop"
$aqui = Split-Path -Parent $MyInvocation.MyCommand.Path
$programa = Join-Path $aqui "biony_ativacao.py"
$log = Join-Path $aqui "ativacao.log"
$atalho = Join-Path $PastaInicializacao "Biony Ativacao.lnk"

function Parar-Ativacao {
    $achou = $false
    Get-CimInstance Win32_Process |
        Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*biony_ativacao.py*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $achou = $true; "Parado (PID $($_.ProcessId))." }
    if (-not $achou) { "Não havia nenhuma cópia rodando." }
}

if ($Parar) {
    Parar-Ativacao
    return
}

if ($Remover) {
    Parar-Ativacao
    if (Test-Path $atalho) { Remove-Item $atalho; "Removido da inicialização." } else { "Já não estava na inicialização." }
    return
}

# Python sem janela (pythonw) e as dependências
$python = (Get-Command python -ErrorAction Stop).Source
$pythonw = Join-Path (Split-Path -Parent $python) "pythonw.exe"
if (-not (Test-Path $pythonw)) { throw "Não achei o pythonw.exe ao lado de $python." }
& $python -c "import faster_whisper, sounddevice, httpx, numpy" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Faltam bibliotecas. Rode:  pip install -r `"$aqui\requirements.txt`" -r `"$aqui\requirements-ativacao.txt`""
}

$argumentos = '"{0}" --persistente --log "{1}" --modelo {2} --espera {3}' -f $programa, $log, $Modelo, $Espera.ToString([cultureinfo]::InvariantCulture)

New-Item -ItemType Directory -Force -Path $PastaInicializacao | Out-Null
$atalhoCom = (New-Object -ComObject WScript.Shell).CreateShortcut($atalho)
$atalhoCom.TargetPath = $pythonw
$atalhoCom.Arguments = $argumentos
$atalhoCom.WorkingDirectory = $aqui
$atalhoCom.WindowStyle = 7
$atalhoCom.Description = "Biony: palavra de ativação (microfone sempre ouvindo; a detecção é local)"
$atalhoCom.Save()
"Instalado: $atalho"

if (-not $SemIniciar) {
    Parar-Ativacao | Out-Null
    Start-Process -FilePath $pythonw -ArgumentList $argumentos -WorkingDirectory $aqui -WindowStyle Hidden
    "Iniciado em segundo plano. Para acompanhar:  Get-Content `"$log`" -Wait -Tail 20"
    "Na primeira vez ele baixa o modelo de reconhecimento; leva alguns minutos até dizer 'Pronto' no log."
}
