[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,

    [ValidateRange(1, 60)]
    [int]$TimeoutSeconds = 10,

    [string]$StateName = 'api-controlled'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeDirectory = Join-Path $projectRoot '.runtime'
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$environmentScript = Join-Path $PSScriptRoot 'windows_process_environment.ps1'

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Repository Python is unavailable: $pythonPath"
}
if (-not (Test-Path -LiteralPath $environmentScript -PathType Leaf)) {
    throw "Windows process environment helper is unavailable: $environmentScript"
}

. $environmentScript
Repair-WindowsProcessPath
$env:GAME_PREDICTOR_API_PORT = [string]$Port

New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
$stdoutPath = Join-Path $runtimeDirectory "$StateName-$stamp.out.log"
$stderrPath = Join-Path $runtimeDirectory "$StateName-$stamp.error.log"
$statePath = Join-Path $runtimeDirectory "$StateName.pid.json"
$temporaryStatePath = "$statePath.tmp"

$process = Start-Process `
    -FilePath $pythonPath `
    -ArgumentList @('-m', 'game_predictor_api') `
    -WorkingDirectory $projectRoot `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath `
    -WindowStyle Hidden `
    -PassThru

$state = [ordered]@{
    pid = $process.Id
    startedAt = (Get-Date).ToUniversalTime().ToString('o')
    port = $Port
    stdout = $stdoutPath
    stderr = $stderrPath
}
[IO.File]::WriteAllText(
    $temporaryStatePath,
    ($state | ConvertTo-Json),
    [Text.UTF8Encoding]::new($false)
)
Move-Item -LiteralPath $temporaryStatePath -Destination $statePath -Force

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$health = $null
do {
    if ($null -eq (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
        $stderrTail = if (Test-Path -LiteralPath $stderrPath) {
            (Get-Content -LiteralPath $stderrPath -Tail 20 -Encoding utf8) -join "`n"
        } else {
            ''
        }
        throw "Controlled API exited before readiness. $stderrTail"
    }
    try {
        $health = Invoke-RestMethod `
            -Uri "http://127.0.0.1:$Port/api/v1/health" `
            -TimeoutSec 2
    } catch {
        Start-Sleep -Milliseconds 250
    }
} while ($null -eq $health -and (Get-Date) -lt $deadline)

if ($null -eq $health) {
    throw "Controlled API did not become ready within $TimeoutSeconds seconds."
}

[pscustomobject]@{
    pid = $process.Id
    port = $Port
    state = $statePath
    stdout = $stdoutPath
    stderr = $stderrPath
    health = $health
} | ConvertTo-Json -Depth 5
