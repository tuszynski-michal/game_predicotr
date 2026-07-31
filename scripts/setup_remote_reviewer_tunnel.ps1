[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$installedCloudflared = Get-Command -Name "cloudflared" -ErrorAction SilentlyContinue
$knownInstallPath = @(
    "C:\Program Files (x86)\cloudflared\cloudflared.exe",
    "C:\Program Files\cloudflared\cloudflared.exe"
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if ($null -ne $installedCloudflared) {
    Write-Host "cloudflared is already available."
    & $installedCloudflared.Source --version
    exit 0
}

if ($null -ne $knownInstallPath) {
    Write-Host "cloudflared is already installed at $knownInstallPath."
    & $knownInstallPath --version
    exit 0
}

if (-not (Get-Command -Name "winget" -ErrorAction SilentlyContinue)) {
    throw "cloudflared and winget are unavailable. Install Cloudflare cloudflared and retry."
}

Write-Host "Installing the official Cloudflare cloudflared package for the current user..."
winget install --id Cloudflare.cloudflared --exact --source winget --accept-package-agreements --accept-source-agreements
if ($LASTEXITCODE -ne 0) {
    throw "cloudflared installation failed with exit code $LASTEXITCODE."
}

Write-Host "Installation complete. Open a new PowerShell window before starting the tunnel."
