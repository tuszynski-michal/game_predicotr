[CmdletBinding()]
param(
    [switch]$Json,
    [string]$ResultPath = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$processEnvironmentScript = Join-Path $PSScriptRoot "windows_process_environment.ps1"
if (-not (Test-Path -LiteralPath $processEnvironmentScript -PathType Leaf)) {
    throw "Windows process environment helper is unavailable: $processEnvironmentScript"
}
. $processEnvironmentScript
Repair-WindowsProcessPath

$runtimeDirectory = Join-Path $projectRoot ".runtime"
$statePath = Join-Path $runtimeDirectory "remote-reviewer.json"
$logPath = Join-Path $runtimeDirectory "remote-reviewer-cloudflared.log"
$reviewerOutPath = Join-Path $runtimeDirectory "remote-reviewer-app.out.log"
$reviewerErrorPath = Join-Path $runtimeDirectory "remote-reviewer-app.error.log"
$reviewerUrl = "http://127.0.0.1:3001"
$reviewerStartupAttempts = 40
$tunnelStartupAttempts = 60
$cloudflareProvisioningHost = "api.trycloudflare.com"
$cloudflareProvisioningPort = 443
$cloudflareConnectTimeoutMilliseconds = 5000

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

function Test-TcpEndpoint {
    param(
        [Parameter(Mandatory = $true)]
        [string]$HostName,
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [int]$TimeoutMilliseconds
    )

    $client = [Net.Sockets.TcpClient]::new()
    try {
        $connectTask = $client.ConnectAsync($HostName, $Port)
        if (-not $connectTask.Wait($TimeoutMilliseconds)) {
            return $false
        }
        return $client.Connected
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
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
        for ($attempt = 0; $attempt -lt $reviewerStartupAttempts; $attempt++) {
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
            throw "Reviewer did not become ready within 20 seconds. Check .runtime remote-reviewer-app logs."
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

    if (-not (Test-TcpEndpoint `
        -HostName $cloudflareProvisioningHost `
        -Port $cloudflareProvisioningPort `
        -TimeoutMilliseconds $cloudflareConnectTimeoutMilliseconds)) {
        throw (
            "Cloudflare Quick Tunnel endpoint $cloudflareProvisioningHost`:$cloudflareProvisioningPort " +
            "is unreachable from the API process. Check the internet connection or firewall and " +
            "start npm run api:dev from a normal Windows PowerShell process that allows outbound HTTPS."
        )
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
    for ($attempt = 0; $attempt -lt $tunnelStartupAttempts; $attempt++) {
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
        $processExitedBeforeCleanup = $process.HasExited
        if (-not $processExitedBeforeCleanup) {
            Stop-Process -Id $process.Id
        }
        $failureKind = if ($processExitedBeforeCleanup) {
            "cloudflared exited before publishing an address"
        }
        else {
            "the provisioning endpoint was reachable but did not publish an address"
        }
        throw (
            "Cloudflare Quick Tunnel could not start within 30 seconds: $failureKind. " +
            "Retry once; if it repeats, check: $logPath"
        )
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
