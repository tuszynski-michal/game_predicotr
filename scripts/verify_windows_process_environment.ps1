[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$normalizerPath = Join-Path $PSScriptRoot 'windows_process_environment.ps1'
. $normalizerPath
Repair-WindowsProcessPath

$pathKeys = @(
    [Environment]::GetEnvironmentVariables('Process').Keys |
        Where-Object { [string]$_ -ieq 'Path' }
)
if ($pathKeys.Count -ne 1 -or $pathKeys[0] -cne 'Path') {
    throw "Expected one canonical Path variable, got: $($pathKeys -join ', ')."
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeDirectory = Join-Path $projectRoot '.runtime'
New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null
$stdoutPath = Join-Path $runtimeDirectory 'path-normalization-smoke.out.log'
$stderrPath = Join-Path $runtimeDirectory 'path-normalization-smoke.err.log'

try {
    $process = Start-Process `
        -FilePath $env:ComSpec `
        -ArgumentList @('/d', '/c', 'echo', 'path-ok') `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -PassThru `
        -WindowStyle Hidden
    if (-not $process.WaitForExit(10000)) {
        Stop-Process -Id $process.Id -Force
        throw 'Redirected child process did not finish within 10 seconds.'
    }
    $output = (Get-Content -LiteralPath $stdoutPath -Raw).Trim()
    if ($output -ne 'path-ok') {
        throw "Redirected child process returned unexpected output: $output"
    }
}
finally {
    Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
}

Write-Output 'Windows process environment uses one canonical Path and supports redirected child processes.'
