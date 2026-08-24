[CmdletBinding()]
param(
    [switch]$Json,
    [string]$ResultPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$lifecycleScript = Join-Path $PSScriptRoot "reviewer_process_lifecycle.ps1"
if (-not (Test-Path -LiteralPath $lifecycleScript -PathType Leaf)) {
    throw "Reviewer lifecycle helper is unavailable: $lifecycleScript"
}
. $lifecycleScript

$statePath = Join-Path $projectRoot ".runtime\remote-reviewer.json"
$reviewerUrl = "http://127.0.0.1:3001"

function Test-ReviewerReady {
    try {
        $response = Invoke-WebRequest -Uri $reviewerUrl -UseBasicParsing -TimeoutSec 2
        $csp = [string]$response.Headers["Content-Security-Policy"]
        return (
            $response.StatusCode -ge 200 -and
            $response.StatusCode -lt 500 -and
            $csp -notmatch "'unsafe-eval'" -and
            (Test-ReviewerBuildCurrent -ProjectRoot $projectRoot -ReviewerUrl $reviewerUrl)
        )
    }
    catch {
        return $false
    }
}

function Write-Status {
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
        return
    }
    Write-Host "Status: $($Value.state)"
    if ($null -ne $Value.publicOrigin) {
        Write-Host "Public URL: $($Value.publicOrigin)"
        Write-Host "Local target: $($Value.target)"
        Write-Host "Instance: $($Value.instanceId)"
    }
}

function Get-RemoteReviewerStatus {
    if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
        return @{
            state = "stopped"
            publicOrigin = $null
            target = $reviewerUrl
            startedAt = $null
            reviewerReady = (Test-ReviewerReady)
            instanceId = $null
        }
    }

    $state = Read-ReviewerJsonState -LiteralPath $statePath
    if ($null -eq $state) {
        return @{
            state = "stale"
            publicOrigin = $null
            target = $reviewerUrl
            startedAt = $null
            reviewerReady = (Test-ReviewerReady)
            instanceId = $null
            message = "Reviewer tunnel state is invalid and no process identity was trusted."
        }
    }

    $stateInstanceId = if ($null -ne $state.PSObject.Properties["instanceId"]) {
        $state.instanceId
    }
    else {
        $null
    }
    foreach ($requiredProperty in @("publicOrigin", "target", "startedAt")) {
        if ($null -eq $state.PSObject.Properties[$requiredProperty]) {
            return @{
                state = "stale"
                publicOrigin = $null
                target = $reviewerUrl
                startedAt = $null
                reviewerReady = (Test-ReviewerReady)
                instanceId = $stateInstanceId
                message = "Reviewer tunnel state is incomplete and no process identity was trusted."
            }
        }
    }

    $identity = Test-ReviewerProcessIdentity `
        -State $state `
        -ExpectedProcessName "cloudflared*"
    if (-not $identity.isMatch) {
        return @{
            state = "stale"
            publicOrigin = $state.publicOrigin
            target = $state.target
            startedAt = $state.startedAt
            reviewerReady = (Test-ReviewerReady)
            instanceId = $stateInstanceId
            message = "Reviewer tunnel state does not match the current Windows process identity."
        }
    }

    $reviewerReady = Test-ReviewerReady
    return @{
        state = $(if ($reviewerReady) { "running" } else { "degraded" })
        publicOrigin = $state.publicOrigin
        target = $state.target
        startedAt = $state.startedAt
        reviewerReady = $reviewerReady
        instanceId = $stateInstanceId
    }
}

$lifecycleMutex = $null
$exitCode = 0
try {
    $lifecycleMutex = Enter-ReviewerLifecycleLock `
        -ProjectRoot $projectRoot `
        -TimeoutMilliseconds 7000
    Write-Status (Get-RemoteReviewerStatus)
}
catch {
    $exitCode = 1
    Write-Status @{
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
