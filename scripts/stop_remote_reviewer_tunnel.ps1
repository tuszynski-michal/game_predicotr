[CmdletBinding()]
param(
    [switch]$Json,
    [string]$ResultPath = "",
    [string]$ExpectedInstanceId = ""
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
        return
    }
    Write-Host $Value.message
}

function Invoke-RemoteReviewerStop {
    if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
        return @{
            state = "stopped"
            publicOrigin = $null
            target = $reviewerUrl
            startedAt = $null
            reviewerReady = $null
            instanceId = $null
            message = "Reviewer tunnel is not running."
        }
    }

    $state = Read-ReviewerJsonState -LiteralPath $statePath
    if ($null -eq $state -or $null -eq $state.PSObject.Properties["instanceId"]) {
        return @{
            state = "stale"
            publicOrigin = $null
            target = $reviewerUrl
            startedAt = $null
            reviewerReady = $null
            instanceId = $null
            message = "Reviewer tunnel state is not identity-safe; no process was stopped."
        }
    }
    foreach ($requiredProperty in @("publicOrigin", "target", "startedAt")) {
        if ($null -eq $state.PSObject.Properties[$requiredProperty]) {
            return @{
                state = "stale"
                publicOrigin = $null
                target = $reviewerUrl
                startedAt = $null
                reviewerReady = $null
                instanceId = $state.instanceId
                message = "Reviewer tunnel state is incomplete; no process was stopped."
            }
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($ExpectedInstanceId)) {
        $expected = [Guid]::Parse($ExpectedInstanceId).ToString('D')
        $current = [Guid]::Parse([string]$state.instanceId).ToString('D')
        if ($expected -ne $current) {
            return @{
                state = "running"
                publicOrigin = $state.publicOrigin
                target = $state.target
                startedAt = $state.startedAt
                reviewerReady = $null
                instanceId = $state.instanceId
                message = "Reviewer tunnel instance changed; the newer instance was not stopped."
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
            reviewerReady = $null
            instanceId = $state.instanceId
            message = "Reviewer tunnel state does not match the current process; no process was stopped."
        }
    }

    Stop-Process -Id $identity.process.Id
    try {
        Wait-Process -Id $identity.process.Id -Timeout 5 -ErrorAction SilentlyContinue
    }
    catch {
        # A process that already exited satisfies the stop operation.
    }
    Remove-Item -LiteralPath $statePath -Force
    return @{
        state = "stopped"
        publicOrigin = $null
        target = $state.target
        startedAt = $null
        reviewerReady = $null
        instanceId = $null
        message = "Reviewer tunnel stopped. The public link is inactive."
    }
}

$lifecycleMutex = $null
$exitCode = 0
try {
    $lifecycleMutex = Enter-ReviewerLifecycleLock `
        -ProjectRoot $projectRoot `
        -TimeoutMilliseconds 7000
    Write-Result (Invoke-RemoteReviewerStop)
}
catch {
    $exitCode = 1
    Write-Result @{
        state = "error"
        publicOrigin = $null
        target = $reviewerUrl
        startedAt = $null
        reviewerReady = $null
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
