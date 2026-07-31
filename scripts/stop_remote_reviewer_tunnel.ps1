[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$statePath = Join-Path $projectRoot ".runtime\remote-reviewer.json"

if (-not (Test-Path -LiteralPath $statePath)) {
    Write-Host "Reviewer tunnel is not running."
    exit 0
}

$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
$process = Get-Process -Id $state.pid -ErrorAction SilentlyContinue
if ($null -ne $process) {
    if ($process.ProcessName -notlike "cloudflared*") {
        throw "PID $($state.pid) does not belong to cloudflared. State was not changed."
    }
    Stop-Process -Id $process.Id
}
Remove-Item -LiteralPath $statePath -Force
Write-Host "Reviewer tunnel stopped. The public link is inactive."
