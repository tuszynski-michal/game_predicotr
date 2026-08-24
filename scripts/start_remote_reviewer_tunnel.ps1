[CmdletBinding()]
param(
    [switch]$Json,
    [string]$ResultPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$processEnvironmentScript = Join-Path $PSScriptRoot "windows_process_environment.ps1"
$lifecycleScript = Join-Path $PSScriptRoot "reviewer_process_lifecycle.ps1"
foreach ($requiredScript in @($processEnvironmentScript, $lifecycleScript)) {
    if (-not (Test-Path -LiteralPath $requiredScript -PathType Leaf)) {
        throw "Reviewer lifecycle helper is unavailable: $requiredScript"
    }
    . $requiredScript
}
Repair-WindowsProcessPath

$runtimeDirectory = Join-Path $projectRoot ".runtime"
$statePath = Join-Path $runtimeDirectory "remote-reviewer.json"
$reviewerUrl = "http://127.0.0.1:3001"
$reviewerStartupAttempts = 40
$tunnelStartupAttempts = 30
$tunnelReachabilityAttempts = 30
$maximumTunnelStarts = 2
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

function Test-ReviewerCurrentProductionReady {
    return (
        (Test-ReviewerProductionReady) -and
        (Test-ReviewerBuildCurrent -ProjectRoot $projectRoot -ReviewerUrl $reviewerUrl)
    )
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

function Test-PublicOriginReady {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PublicOrigin
    )

    return Test-ReviewerPublicOriginReady -PublicOrigin $PublicOrigin
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

function Convert-LegacyRemoteState {
    param(
        [Parameter(Mandatory = $true)]
        [object]$State
    )

    if ($null -ne $State.PSObject.Properties["instanceId"]) {
        return $State
    }
    try {
        $process = Get-Process -Id ([int]$State.pid) -ErrorAction SilentlyContinue
        if (
            $null -eq $process -or
            $process.ProcessName -notlike "cloudflared*" -or
            -not (Test-PublicOriginReady -PublicOrigin ([string]$State.publicOrigin)) -or
            -not (Test-ReviewerCurrentProductionReady)
        ) {
            return $State
        }
        $identity = New-ReviewerProcessIdentity `
            -Process $process `
            -InstanceId ([Guid]::NewGuid())
        $adopted = [ordered]@{
            schemaVersion = 2
            instanceId = $identity.instanceId
            pid = $identity.pid
            processStartedAt = $identity.processStartedAt
            executablePath = $identity.executablePath
            processName = $identity.processName
            publicOrigin = [string]$State.publicOrigin
            target = [string]$State.target
            startedAt = [string]$State.startedAt
            cloudflaredLogPath = $null
            reviewerManagedProcess = $null
        }
        Write-ReviewerAtomicJson -LiteralPath $statePath -Value $adopted
        return [pscustomobject]$adopted
    }
    catch {
        return $State
    }
}

function Invoke-RemoteReviewerStart {
    $reviewerManagedProcess = $null
    if ((Test-ReviewerReady) -and -not (Test-ReviewerProductionReady)) {
        throw "Port 3001 is used by a development Reviewer. Stop npm run reviewer:dev before publishing online."
    }
    if ((Test-ReviewerProductionReady) -and -not (Test-ReviewerCurrentProductionReady)) {
        Stop-StaleReviewerLoopbackListener -Port 3001
    }
    if (-not (Test-ReviewerProductionReady)) {
        $npm = Get-Command -Name "npm.cmd" -ErrorAction SilentlyContinue
        if ($null -eq $npm) {
            throw "npm.cmd is unavailable. Run npm run windows:environment:check."
        }
        $nextBuildPath = Join-Path $projectRoot "apps\reviewer\.next\BUILD_ID"
        if (-not (Test-Path -LiteralPath $nextBuildPath -PathType Leaf)) {
            throw "Reviewer production build is missing. Run npm run reviewer:build."
        }

        $reviewerInstanceId = [Guid]::NewGuid()
        $reviewerLogs = New-ReviewerAttemptPaths `
            -RuntimeDirectory $runtimeDirectory `
            -Prefix "reviewer-app" `
            -InstanceId $reviewerInstanceId
        $reviewerProcess = Start-Process `
            -FilePath $npm.Source `
            -ArgumentList @("run", "reviewer:start") `
            -WorkingDirectory $projectRoot `
            -RedirectStandardOutput $reviewerLogs.out `
            -RedirectStandardError $reviewerLogs.error `
            -PassThru `
            -WindowStyle Hidden
        for ($attempt = 0; $attempt -lt $reviewerStartupAttempts; $attempt++) {
            Start-Sleep -Milliseconds 500
            if ($reviewerProcess.HasExited -or (Test-ReviewerCurrentProductionReady)) {
                break
            }
        }
        if (-not (Test-ReviewerCurrentProductionReady)) {
            if (-not $reviewerProcess.HasExited) {
                Stop-Process -Id $reviewerProcess.Id
            }
            throw "Reviewer did not become ready within 20 seconds. Check the unique reviewer-lifecycle-logs entry."
        }
        $reviewerListener = Get-ReviewerLoopbackListenerProcess -Port 3001
        if ($null -eq $reviewerListener) {
            throw "Reviewer became ready, but its loopback listener process is unavailable."
        }
        $reviewerManagedProcess = New-ReviewerProcessIdentity `
            -Process $reviewerListener `
            -InstanceId $reviewerInstanceId
    }

    $existing = Read-ReviewerJsonState -LiteralPath $statePath
    if ($null -ne $existing) {
        $existing = Convert-LegacyRemoteState -State $existing
        $existingIdentity = Test-ReviewerProcessIdentity `
            -State $existing `
            -ExpectedProcessName "cloudflared*"
        if (
            $existingIdentity.isMatch -and
            (Test-PublicOriginReady -PublicOrigin ([string]$existing.publicOrigin)) -and
            (Test-ReviewerCurrentProductionReady)
        ) {
            return @{
                state = "running"
                publicOrigin = $existing.publicOrigin
                target = $existing.target
                startedAt = $existing.startedAt
                reviewerReady = $true
                instanceId = $existing.instanceId
                message = "Tunnel is already running: $($existing.publicOrigin)"
            }
        }
        if ($existingIdentity.isMatch) {
            Stop-Process -Id $existingIdentity.process.Id
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

    $publicOrigin = $null
    $process = $null
    $processIdentity = $null
    $successfulLogPath = $null
    for ($tunnelStart = 0; $tunnelStart -lt $maximumTunnelStarts; $tunnelStart++) {
        $instanceId = [Guid]::NewGuid()
        $logs = New-ReviewerAttemptPaths `
            -RuntimeDirectory $runtimeDirectory `
            -Prefix "cloudflared" `
            -InstanceId $instanceId `
            -Attempt $tunnelStart
        $arguments = @(
            "tunnel",
            "--no-autoupdate",
            "--loglevel", "info",
            "--logfile", $logs.process,
            "--url", $reviewerUrl
        )
        $process = Start-Process `
            -FilePath $cloudflaredPath `
            -ArgumentList $arguments `
            -PassThru `
            -WindowStyle Hidden
        try {
            $processIdentity = New-ReviewerProcessIdentity `
                -Process $process `
                -InstanceId $instanceId
        }
        catch {
            if (-not $process.HasExited) {
                Stop-Process -Id $process.Id
            }
            throw
        }
        $candidateOrigin = $null
        for ($attempt = 0; $attempt -lt $tunnelStartupAttempts; $attempt++) {
            Start-Sleep -Milliseconds 500
            if ($process.HasExited) {
                break
            }
            if (Test-Path -LiteralPath $logs.process -PathType Leaf) {
                $match = Select-String `
                    -LiteralPath $logs.process `
                    -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" `
                    -AllMatches
                if ($null -ne $match) {
                    $candidateOrigin = $match.Matches[-1].Value
                    break
                }
            }
        }

        if ($null -ne $candidateOrigin) {
            for ($attempt = 0; $attempt -lt $tunnelReachabilityAttempts; $attempt++) {
                if ($process.HasExited) {
                    break
                }
                if (Test-PublicOriginReady -PublicOrigin $candidateOrigin) {
                    $publicOrigin = $candidateOrigin
                    $successfulLogPath = $logs.process
                    break
                }
                Start-Sleep -Milliseconds 500
            }
        }

        if ($null -ne $publicOrigin) {
            break
        }
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id
        }
    }

    if ($null -eq $publicOrigin -or $null -eq $process -or $null -eq $processIdentity) {
        throw (
            "Cloudflare Quick Tunnel published no reachable public address after " +
            "$maximumTunnelStarts bounded attempts. Check the unique reviewer-lifecycle-logs entries."
        )
    }
    if (-not (Test-ReviewerCurrentProductionReady)) {
        Stop-Process -Id $process.Id
        throw "Reviewer lost readiness before tunnel state publication."
    }
    $verifiedIdentity = Test-ReviewerProcessIdentity `
        -State ([pscustomobject]$processIdentity) `
        -ExpectedProcessName "cloudflared*"
    if (-not $verifiedIdentity.isMatch) {
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id
        }
        throw "Cloudflared identity changed before tunnel state publication."
    }

    $startedAt = [DateTimeOffset]::Now.ToString("o")
    $state = [ordered]@{
        schemaVersion = 2
        instanceId = $processIdentity.instanceId
        pid = $processIdentity.pid
        processStartedAt = $processIdentity.processStartedAt
        executablePath = $processIdentity.executablePath
        processName = $processIdentity.processName
        publicOrigin = $publicOrigin
        target = $reviewerUrl
        startedAt = $startedAt
        cloudflaredLogPath = $successfulLogPath
        reviewerManagedProcess = $reviewerManagedProcess
    }
    try {
        Write-ReviewerAtomicJson -LiteralPath $statePath -Value $state
    }
    catch {
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id
        }
        throw
    }

    return @{
        state = "running"
        publicOrigin = $publicOrigin
        target = $reviewerUrl
        startedAt = $startedAt
        reviewerReady = $true
        instanceId = $processIdentity.instanceId
        message = "Remote Reviewer is running: $publicOrigin"
    }
}

$lifecycleMutex = $null
$exitCode = 0
try {
    $lifecycleMutex = Enter-ReviewerLifecycleLock `
        -ProjectRoot $projectRoot `
        -TimeoutMilliseconds 55000
    Write-Result (Invoke-RemoteReviewerStart)
}
catch {
    $exitCode = 1
    Write-Result @{
        state = "error"
        publicOrigin = $null
        target = $reviewerUrl
        startedAt = $null
        reviewerReady = $false
        instanceId = $null
        message = $_.Exception.Message
    }
}
finally {
    if ($null -ne $lifecycleMutex) {
        Exit-ReviewerLifecycleLock -Mutex $lifecycleMutex
    }
}
exit $exitCode
