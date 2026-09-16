[CmdletBinding()]
param(
    [ValidateSet('All', 'Api', 'Worker')]
    [string]$Suite = 'All'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$virtualEnvironmentRoot = Join-Path $repositoryRoot '.venv'
$pythonPath = Join-Path $virtualEnvironmentRoot 'Scripts\python.exe'
$pytestTempPath = Join-Path $virtualEnvironmentRoot "pytest-tmp-$PID"
$testPaths = switch ($Suite) {
    'Api' { @('services/api/tests') }
    'Worker' { @('services/worker/tests') }
    default { @('services/api/tests', 'services/worker/tests') }
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Python virtual environment is missing. Create .venv before running tests.'
}

try {
    & $pythonPath -m pytest @testPaths "--basetemp=$pytestTempPath"
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    if (Test-Path -LiteralPath $pytestTempPath) {
        $resolvedTempPath = (Resolve-Path -LiteralPath $pytestTempPath).Path
        $resolvedVenvPath = (Resolve-Path -LiteralPath $virtualEnvironmentRoot).Path
        if ([System.IO.Path]::GetDirectoryName($resolvedTempPath) -ne $resolvedVenvPath) {
            throw 'Refusing to remove a Pytest path outside .venv.'
        }
        $cleanupSucceeded = $false
        for ($attempt = 1; $attempt -le 5; $attempt++) {
            if (-not (Test-Path -LiteralPath $resolvedTempPath)) {
                $cleanupSucceeded = $true
                break
            }
            try {
                Remove-Item `
                    -LiteralPath $resolvedTempPath `
                    -Recurse `
                    -Force `
                    -ErrorAction Stop
                $cleanupSucceeded = $true
                break
            }
            catch {
                if ($attempt -eq 5) {
                    throw
                }
                Start-Sleep -Milliseconds 100
            }
        }
        if (-not $cleanupSucceeded -and (Test-Path -LiteralPath $resolvedTempPath)) {
            throw 'Pytest temporary directory cleanup did not finish.'
        }
    }
}
