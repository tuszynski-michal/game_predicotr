[CmdletBinding()]
param()

$projectRoot = Split-Path -Parent $PSScriptRoot
$statePath = Join-Path $projectRoot ".runtime\remote-reviewer.json"

if (-not (Test-Path -LiteralPath $statePath)) {
    Write-Host "Status: stopped"
    exit 1
}

$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
$process = Get-Process -Id $state.pid -ErrorAction SilentlyContinue
if ($null -eq $process -or $process.ProcessName -notlike "cloudflared*") {
    Write-Host "Status: stale"
    Write-Host "Remove stale state with: npm run reviewer:remote:stop"
    exit 1
}

Write-Host "Status: running"
Write-Host "Public URL: $($state.publicOrigin)"
Write-Host "Local target: $($state.target)"
Write-Host "PID: $($state.pid)"
