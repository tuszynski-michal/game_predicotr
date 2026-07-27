[CmdletBinding()]
param(
    [switch]$ConfirmReset
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not $ConfirmReset) {
    throw 'Reset deletes all local development data. Run again with -ConfirmReset.'
}

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$composePath = Join-Path $repositoryRoot 'infra\docker\compose.yaml'
$pythonPath = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
$defaultDatabaseUrl = 'postgresql+psycopg://game_predictor:game_predictor_local@127.0.0.1:5432/game_predictor'
$configuredDatabaseUrl = [Environment]::GetEnvironmentVariable('GAME_PREDICTOR_DATABASE_URL')
$databaseUrl = if ([string]::IsNullOrWhiteSpace($configuredDatabaseUrl)) {
    $defaultDatabaseUrl
}
else {
    $configuredDatabaseUrl
}

try {
    $parsedDatabaseUrl = [System.Uri]$databaseUrl
}
catch {
    throw 'GAME_PREDICTOR_DATABASE_URL is not a valid local PostgreSQL URL.'
}

$databaseName = $parsedDatabaseUrl.AbsolutePath.TrimStart('/')
$loopbackHosts = @('127.0.0.1', 'localhost', '::1')
if ($parsedDatabaseUrl.Scheme -ne 'postgresql+psycopg' -or $parsedDatabaseUrl.Host -notin $loopbackHosts) {
    throw 'Reset only supports a postgresql+psycopg database on the local loopback interface.'
}
if ($databaseName -ne 'game_predictor') {
    throw "Reset refused: expected the exact development database 'game_predictor', received '$databaseName'."
}

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
    throw 'Docker CLI is missing. Install and start Docker Desktop before resetting the database.'
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Python virtual environment is missing. Create .venv and install project dependencies.'
}

& $dockerPath compose -f $composePath up -d --wait postgres
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Push-Location $repositoryRoot
try {
    & $pythonPath -m alembic downgrade base
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    & $pythonPath -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}

Write-Host "Local development database 'game_predictor' was reset to the current Alembic head."
