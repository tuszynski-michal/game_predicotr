[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeDirectory = Join-Path $projectRoot ".runtime"
$statePath = Join-Path $runtimeDirectory "remote-reviewer.json"
$logPath = Join-Path $runtimeDirectory "remote-reviewer-cloudflared.log"

New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null

if (Test-Path -LiteralPath $statePath) {
    $existing = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    $existingProcess = Get-Process -Id $existing.pid -ErrorAction SilentlyContinue
    if ($null -ne $existingProcess) {
        Write-Host "Tunnel is already running: $($existing.publicOrigin)"
        exit 0
    }
    Remove-Item -LiteralPath $statePath -Force
}

$cloudflared = Get-Command -Name "cloudflared" -ErrorAction SilentlyContinue
if ($null -eq $cloudflared) {
    throw "cloudflared is unavailable. First run: npm run reviewer:remote:setup"
}

if (Test-Path -LiteralPath $logPath) {
    Remove-Item -LiteralPath $logPath -Force
}

$arguments = @(
    "tunnel",
    "--no-autoupdate",
    "--loglevel", "info",
    "--logfile", $logPath,
    "--url", "http://127.0.0.1:3001"
)
$process = Start-Process -FilePath $cloudflared.Source -ArgumentList $arguments -PassThru -WindowStyle Hidden

$publicOrigin = $null
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    Start-Sleep -Milliseconds 500
    if ($process.HasExited) {
        break
    }
    if (Test-Path -LiteralPath $logPath) {
        $match = Select-String -LiteralPath $logPath -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -AllMatches
        if ($null -ne $match) {
            $publicOrigin = $match.Matches[-1].Value
            break
        }
    }
}

if ($null -eq $publicOrigin) {
    if (-not $process.HasExited) {
        Stop-Process -Id $process.Id
    }
    throw "Cloudflare did not return an HTTPS URL within 10 seconds. Check: $logPath"
}

[ordered]@{
    pid = $process.Id
    publicOrigin = $publicOrigin
    target = "http://127.0.0.1:3001"
    startedAt = [DateTimeOffset]::Now.ToString("o")
} | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8

Write-Host "Remote Reviewer is running: $publicOrigin"
Write-Host "Create a new session in Admin. Its link will use this address."
