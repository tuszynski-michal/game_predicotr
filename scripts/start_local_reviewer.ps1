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
$statePath = Join-Path $runtimeDirectory "local-reviewer.json"
$reviewerUrl = "http://127.0.0.1:3001"
$reviewerStartupAttempts = 40

New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null

function Test-LocalReviewerReady {
    try {
        $response = Invoke-WebRequest -Uri $reviewerUrl -UseBasicParsing -TimeoutSec 2
        $csp = [string]$response.Headers["Content-Security-Policy"]
        $frameOptions = [string]$response.Headers["X-Frame-Options"]
        return (
            $response.StatusCode -ge 200 -and
            $response.StatusCode -lt 500 -and
            $csp -match "frame-ancestors 'none'" -and
            $frameOptions -eq "DENY"
        )
    }
    catch {
        return $false
    }
}

function Test-LocalReviewerCurrent {
    return (
        (Test-LocalReviewerReady) -and
        (Test-ReviewerBuildCurrent -ProjectRoot $projectRoot -ReviewerUrl $reviewerUrl)
    )
}

function Write-Result {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Value
    )
    if (-not $Json) {
        Write-Host $Value.message
        return
    }
    $resultJson = $Value | ConvertTo-Json -Compress
    if ([string]::IsNullOrWhiteSpace($ResultPath)) {
        Write-Output $resultJson
        return
    }
    [IO.File]::WriteAllText(
        $ResultPath,
        $resultJson,
        [Text.UTF8Encoding]::new($false)
    )
}

function Invoke-LocalReviewerStart {
    if (Test-LocalReviewerCurrent) {
        $existingStartedAt = $null
        $existingInstanceId = $null
        $existingState = Read-ReviewerJsonState -LiteralPath $statePath
        if ($null -ne $existingState) {
            if ($null -ne $existingState.PSObject.Properties["startedAt"]) {
                $existingStartedAt = $existingState.startedAt
            }
            if ($null -ne $existingState.PSObject.Properties["instanceId"]) {
                $existingInstanceId = $existingState.instanceId
            }
        }
        return @{
            state = "running"
            publicOrigin = $null
            target = $reviewerUrl
            startedAt = $existingStartedAt
            reviewerReady = $true
            instanceId = $existingInstanceId
            message = "Local Reviewer is already running."
        }
    }
    if (Test-LocalReviewerReady) {
        Stop-StaleReviewerLoopbackListener -Port 3001
    }

    $existingState = Read-ReviewerJsonState -LiteralPath $statePath
    if ($null -ne $existingState) {
        $identity = Test-ReviewerProcessIdentity -State $existingState
        if ($identity.isMatch) {
            Stop-Process -Id $identity.process.Id
        }
        Remove-Item -LiteralPath $statePath -Force
    }

    $npmCommand = Get-Command -Name "npm.cmd" -ErrorAction SilentlyContinue
    if ($null -eq $npmCommand) {
        throw "npm.cmd is unavailable. Run npm run windows:environment:check."
    }
    $nextBuildPath = Join-Path $projectRoot "apps\reviewer\.next\BUILD_ID"
    if (-not (Test-Path -LiteralPath $nextBuildPath -PathType Leaf)) {
        throw "Reviewer production build is missing. Run npm run reviewer:build."
    }

    $instanceId = [Guid]::NewGuid()
    $logs = New-ReviewerAttemptPaths `
        -RuntimeDirectory $runtimeDirectory `
        -Prefix "reviewer-app" `
        -InstanceId $instanceId
    $reviewerProcess = Start-Process `
        -FilePath $npmCommand.Source `
        -ArgumentList @("run", "reviewer:start") `
        -WorkingDirectory $projectRoot `
        -RedirectStandardOutput $logs.out `
        -RedirectStandardError $logs.error `
        -PassThru `
        -WindowStyle Hidden
    for ($attempt = 0; $attempt -lt $reviewerStartupAttempts; $attempt++) {
        Start-Sleep -Milliseconds 500
        if ($reviewerProcess.HasExited -or (Test-LocalReviewerCurrent)) {
            break
        }
    }
    if (-not (Test-LocalReviewerCurrent)) {
        if (-not $reviewerProcess.HasExited) {
            Stop-Process -Id $reviewerProcess.Id
        }
        throw "Reviewer did not become ready within 20 seconds. Check the unique reviewer-lifecycle-logs entry."
    }
    $reviewerListener = Get-ReviewerLoopbackListenerProcess -Port 3001
    if ($null -eq $reviewerListener) {
        throw "Reviewer became ready, but its loopback listener process is unavailable."
    }
    $processIdentity = New-ReviewerProcessIdentity `
        -Process $reviewerListener `
        -InstanceId $instanceId
    $verifiedIdentity = Test-ReviewerProcessIdentity -State ([pscustomobject]$processIdentity)
    if (-not $verifiedIdentity.isMatch) {
        if (-not $reviewerProcess.HasExited) {
            Stop-Process -Id $reviewerProcess.Id
        }
        throw "Reviewer process identity changed before local state publication."
    }

    $startedAt = [DateTimeOffset]::Now.ToString("o")
    $state = [ordered]@{
        schemaVersion = 2
        instanceId = $processIdentity.instanceId
        pid = $processIdentity.pid
        processStartedAt = $processIdentity.processStartedAt
        executablePath = $processIdentity.executablePath
        processName = $processIdentity.processName
        target = $reviewerUrl
        startedAt = $startedAt
        stdoutLogPath = $logs.out
        stderrLogPath = $logs.error
    }
    try {
        Write-ReviewerAtomicJson -LiteralPath $statePath -Value $state
    }
    catch {
        if (-not $reviewerProcess.HasExited) {
            Stop-Process -Id $reviewerProcess.Id
        }
        throw
    }

    return @{
        state = "running"
        publicOrigin = $null
        target = $reviewerUrl
        startedAt = $startedAt
        reviewerReady = $true
        instanceId = $processIdentity.instanceId
        message = "Local Reviewer is running."
    }
}

$lifecycleMutex = $null
$exitCode = 0
try {
    $lifecycleMutex = Enter-ReviewerLifecycleLock `
        -ProjectRoot $projectRoot `
        -TimeoutMilliseconds 25000
    Write-Result (Invoke-LocalReviewerStart)
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
