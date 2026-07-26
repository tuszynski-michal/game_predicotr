[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$virtualEnvironmentRoot = Join-Path $repositoryRoot '.venv'
$pythonPath = Join-Path $virtualEnvironmentRoot 'Scripts\python.exe'
$pytestTempPath = Join-Path $virtualEnvironmentRoot "pytest-tmp-$PID"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Python virtual environment is missing. Create .venv before running tests.'
}

try {
    & $pythonPath -m pytest services/api/tests services/worker/tests "--basetemp=$pytestTempPath"
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
        Remove-Item -LiteralPath $resolvedTempPath -Recurse -Force
    }
}
