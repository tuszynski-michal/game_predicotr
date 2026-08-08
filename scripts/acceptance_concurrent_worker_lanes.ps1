[CmdletBinding()]
param(
    [ValidateRange(30, 600)]
    [int]$TimeoutSeconds = 180,

    [ValidateRange(100, 10000)]
    [int]$SelectionImages = 600,

    [ValidateRange(10000, 500000)]
    [int]$LayoutRecords = 75000,

    [string]$Output = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pythonPath = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
$composePath = Join-Path $repositoryRoot 'infra\docker\compose.yaml'
$runnerPath = Join-Path $PSScriptRoot 'run_concurrent_worker_lane_acceptance.py'
$environmentScript = Join-Path $PSScriptRoot 'windows_process_environment.ps1'

if ([string]::IsNullOrWhiteSpace($Output)) {
    $Output = Join-Path $repositoryRoot 'artifacts\worker-lanes\concurrent-acceptance-report.json'
}
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Python virtual environment is unavailable: $pythonPath"
}
if (-not (Test-Path -LiteralPath $environmentScript -PathType Leaf)) {
    throw "Windows process environment helper is unavailable: $environmentScript"
}
. $environmentScript
Repair-WindowsProcessPath

$docker = Get-Command -Name 'docker.exe' -ErrorAction SilentlyContinue
if ($null -eq $docker) {
    $dockerCandidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'),
        'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
    )
    $dockerPath = $dockerCandidates |
        Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
        Select-Object -First 1
}
else {
    $dockerPath = $docker.Source
}
if ([string]::IsNullOrWhiteSpace([string]$dockerPath)) {
    throw 'Docker CLI is unavailable. Start Docker Desktop and check PATH.'
}

& $dockerPath compose -f $composePath up -d --wait postgres
if ($LASTEXITCODE -ne 0) {
    throw "PostgreSQL readiness failed with exit code $LASTEXITCODE."
}

$arguments = @(
    $runnerPath,
    '--output', [IO.Path]::GetFullPath($Output),
    '--timeout-seconds', [string]$TimeoutSeconds,
    '--selection-images', [string]$SelectionImages,
    '--layout-records', [string]$LayoutRecords
)
$startInfo = [Diagnostics.ProcessStartInfo]::new()
$startInfo.FileName = $pythonPath
$startInfo.WorkingDirectory = $repositoryRoot
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.RedirectStandardOutput = $true
$startInfo.RedirectStandardError = $true
$startInfo.Arguments = (
    $arguments | ForEach-Object {
        if ($_ -match '[\s"]') {
            '"' + $_.Replace('"', '\"') + '"'
        }
        else {
            $_
        }
    }
) -join ' '
$process = [Diagnostics.Process]::new()
$process.StartInfo = $startInfo
if (-not $process.Start()) {
    throw 'Concurrent lane acceptance process did not start.'
}
$stdoutTask = $process.StandardOutput.ReadToEndAsync()
$stderrTask = $process.StandardError.ReadToEndAsync()
try {
    if (-not $process.WaitForExit(($TimeoutSeconds + 45) * 1000)) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        [void]$process.WaitForExit(5000)
        throw "Concurrent lane acceptance exceeded $($TimeoutSeconds + 45) seconds."
    }
    $stdout = $stdoutTask.GetAwaiter().GetResult()
    $stderr = $stderrTask.GetAwaiter().GetResult()
    if (-not [string]::IsNullOrWhiteSpace($stdout)) {
        Write-Host $stdout.TrimEnd()
    }
    if (-not [string]::IsNullOrWhiteSpace($stderr)) {
        Write-Warning $stderr.TrimEnd()
    }
    if ($process.ExitCode -ne 0) {
        throw "Concurrent lane acceptance failed with exit code $($process.ExitCode). $stderr"
    }
}
finally {
    if (-not $process.HasExited) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
    $process.Dispose()
}

Write-Host "Concurrent lane acceptance passed. Report: $([IO.Path]::GetFullPath($Output))"
