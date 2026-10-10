[CmdletBinding()]
param(
    [switch]$Index
)

# Starts the Serena MCP server (stdio) from the isolated venv .tooling/venv-tokens
# (TASK-0939). All Serena and uv state is redirected under .tooling/, so nothing is
# written to the user profile. The process uses stdio: stdout must stay clean, hence
# no Write-Host here. With -Index it only builds the project symbol cache
# (`serena project index`, about 50 s) and exits. Used by `claude mcp add` (see ai_docs/guides/TOKEN_TOOLING.md).

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$toolingRoot = Join-Path $projectRoot '.tooling'
$venvScripts = Join-Path $toolingRoot 'venv-tokens\Scripts'
$serena = Join-Path $venvScripts 'serena.exe'

if (-not (Test-Path -LiteralPath $serena -PathType Leaf)) {
    $message = @(
        "Serena is not installed: $serena",
        'Prepare the isolated tools in this checkout (repository root):',
        '  python -m venv .tooling\venv-tokens',
        '  .\.tooling\venv-tokens\Scripts\python.exe -m pip install serena-agent==1.7.0 graphifyy==0.9.82 uv==0.12.24',
        '  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_serena_mcp.ps1 -Index',
        'Details: ai_docs/guides/TOKEN_TOOLING.md'
    ) -join [Environment]::NewLine
    [Console]::Error.WriteLine($message)
    exit 2
}

$env:SERENA_HOME = Join-Path $toolingRoot 'serena-home'
$env:UV_CACHE_DIR = Join-Path $toolingRoot 'uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $toolingRoot 'uv-python'
$env:UV_TOOL_DIR = Join-Path $toolingRoot 'uv-tools'
$env:PATH = "$venvScripts;$env:PATH"

if ($Index) {
    $venvPython = Join-Path $venvScripts 'python.exe'
    Write-Output 'Installed tool versions:'
    & $venvPython -m pip list --format=freeze 2>$null |
        Where-Object { $_ -match '^(serena-agent|graphifyy|uv|mcp)==' } |
        ForEach-Object { Write-Output "  $_" }
    & $serena project index $projectRoot --timeout 60
    exit $LASTEXITCODE
}

& $serena start-mcp-server --project $projectRoot --context claude-code --enable-web-dashboard false --open-web-dashboard false
exit $LASTEXITCODE
