[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$composePath = Join-Path $repositoryRoot 'infra\docker\compose.yaml'
$pythonPath = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
$acceptanceTestPath = Join-Path $repositoryRoot 'services\api\tests\integration\test_m2_admin_acceptance.py'
$dockerDesktopUserPath = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
$dockerDesktopPath = 'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue

if ($null -ne $dockerCommand) {
    $dockerPath = $dockerCommand.Source
}
elseif (Test-Path -LiteralPath $dockerDesktopUserPath) {
    $dockerPath = $dockerDesktopUserPath
}
elseif (Test-Path -LiteralPath $dockerDesktopPath) {
    $dockerPath = $dockerDesktopPath
}
else {
    throw 'Docker CLI is missing. Install and start Docker Desktop before running M2 acceptance.'
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Python virtual environment is missing. Create .venv and install project dependencies.'
}

& $dockerPath compose -f $composePath up -d --wait postgres
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$previousTestFlag = [Environment]::GetEnvironmentVariable('GAME_PREDICTOR_RUN_POSTGRES_TESTS')
try {
    $env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
    & $pythonPath -m pytest $acceptanceTestPath -ra
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    if ($null -eq $previousTestFlag) {
        Remove-Item Env:\GAME_PREDICTOR_RUN_POSTGRES_TESTS -ErrorAction SilentlyContinue
    }
    else {
        $env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = $previousTestFlag
    }
}
