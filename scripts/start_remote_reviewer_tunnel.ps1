[CmdletBinding()]
param(
    [switch]$Json,
    [string]$ResultPath = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeDirectory = Join-Path $projectRoot ".runtime"
$statePath = Join-Path $runtimeDirectory "remote-reviewer.json"
$logPath = Join-Path $runtimeDirectory "remote-reviewer-cloudflared.log"
$reviewerOutPath = Join-Path $runtimeDirectory "remote-reviewer-app.out.log"
$reviewerErrorPath = Join-Path $runtimeDirectory "remote-reviewer-app.error.log"
$reviewerUrl = "http://127.0.0.1:3001"

New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null

function Test-ReviewerReady {
    try {
        $response = Invoke-WebRequest -Uri $reviewerUrl -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    }
    catch {
        return $false
    }
}

function Test-ReviewerProductionReady {
    try {
        $response = Invoke-WebRequest -Uri $reviewerUrl -UseBasicParsing -TimeoutSec 2
        $csp = [string]$response.Headers["Content-Security-Policy"]
        return (
            $response.StatusCode -ge 200 -and
            $response.StatusCode -lt 500 -and
            $csp -notmatch "'unsafe-eval'"
        )
    }
    catch {
        return $false
    }
}

function Write-Result {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Value
    )
    if ($Json) {
        $resultJson = $Value | ConvertTo-Json -Compress
        if ([string]::IsNullOrWhiteSpace($ResultPath)) {
            Write-Output $resultJson
        }
        else {
            [IO.File]::WriteAllText(
                $ResultPath,
                $resultJson,
                [Text.UTF8Encoding]::new($false)
            )
        }
    }
    else {
        Write-Host $Value.message
    }
}

try {
    $reviewerManagedPid = $null
    if ((Test-ReviewerReady) -and -not (Test-ReviewerProductionReady)) {
        throw "Port 3001 is used by a development Reviewer. Stop npm run reviewer:dev before publishing online."
    }
    if (-not (Test-ReviewerProductionReady)) {
        $npm = Get-Command -Name "npm.cmd" -ErrorAction SilentlyContinue
        if ($null -eq $npm) {
            throw "npm.cmd is unavailable. Run npm run windows:environment:check."
        }
        $nextBuildPath = Join-Path $projectRoot "apps\reviewer\.next\BUILD_ID"
        if (-not (Test-Path -LiteralPath $nextBuildPath)) {
            throw "Reviewer production build is missing. Run npm run reviewer:build."
        }

        $reviewerProcess = Start-Process `
            -FilePath $npm.Source `
            -ArgumentList @("run", "reviewer:start") `
            -WorkingDirectory $projectRoot `
            -RedirectStandardOutput $reviewerOutPath `
            -RedirectStandardError $reviewerErrorPath `
            -PassThru `
            -WindowStyle Hidden
        $reviewerManagedPid = $reviewerProcess.Id
        for ($attempt = 0; $attempt -lt 20; $attempt++) {
            Start-Sleep -Milliseconds 500
            if ($reviewerProcess.HasExited) {
                break
            }
            if (Test-ReviewerProductionReady) {
                break
            }
        }
        if (-not (Test-ReviewerProductionReady)) {
            if (-not $reviewerProcess.HasExited) {
                Stop-Process -Id $reviewerProcess.Id
            }
            throw "Reviewer did not become ready within 10 seconds. Check .runtime remote-reviewer-app logs."
        }
    }

    if (Test-Path -LiteralPath $statePath) {
        $existing = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        $existingProcess = Get-Process -Id $existing.pid -ErrorAction SilentlyContinue
        if ($null -ne $existingProcess -and $existingProcess.ProcessName -like "cloudflared*") {
            Write-Result @{
                state = "running"
                publicOrigin = $existing.publicOrigin
                target = $existing.target
                startedAt = $existing.startedAt
                reviewerReady = (Test-ReviewerProductionReady)
                message = "Tunnel is already running: $($existing.publicOrigin)"
            }
            exit 0
        }
        Remove-Item -LiteralPath $statePath -Force
    }

    $cloudflared = Get-Command -Name "cloudflared" -ErrorAction SilentlyContinue
    $cloudflaredPath = if ($null -ne $cloudflared) {
        $cloudflared.Source
    }
    elseif (Test-Path -LiteralPath "C:\Program Files (x86)\cloudflared\cloudflared.exe") {
        "C:\Program Files (x86)\cloudflared\cloudflared.exe"
    }
    elseif (Test-Path -LiteralPath "C:\Program Files\cloudflared\cloudflared.exe") {
        "C:\Program Files\cloudflared\cloudflared.exe"
    }
    else {
        $null
    }
    if ($null -eq $cloudflaredPath) {
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
        "--url", $reviewerUrl
    )
    $process = Start-Process -FilePath $cloudflaredPath -ArgumentList $arguments -PassThru -WindowStyle Hidden

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

    $startedAt = [DateTimeOffset]::Now.ToString("o")
    $state = [ordered]@{
        pid = $process.Id
        publicOrigin = $publicOrigin
        target = $reviewerUrl
        startedAt = $startedAt
        reviewerManagedPid = $reviewerManagedPid
    }
    $stateJson = $state | ConvertTo-Json
    [IO.File]::WriteAllText(
        $statePath,
        $stateJson,
        [Text.UTF8Encoding]::new($false)
    )

    Write-Result @{
        state = "running"
        publicOrigin = $publicOrigin
        target = $reviewerUrl
        startedAt = $startedAt
        reviewerReady = $true
        message = "Remote Reviewer is running: $publicOrigin"
    }
}
catch {
    if ($Json) {
        $errorJson = @{
            state = "error"
            publicOrigin = $null
            target = $reviewerUrl
            startedAt = $null
            reviewerReady = $false
            message = $_.Exception.Message
        } | ConvertTo-Json -Compress
        if ([string]::IsNullOrWhiteSpace($ResultPath)) {
            Write-Output $errorJson
        }
        else {
            [IO.File]::WriteAllText(
                $ResultPath,
                $errorJson,
                [Text.UTF8Encoding]::new($false)
            )
        }
    }
    else {
        Write-Error $_
    }
    exit 1
}
