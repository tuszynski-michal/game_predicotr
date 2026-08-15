[CmdletBinding()]
param(
    [switch]$Json,
    [string]$ResultPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$processEnvironmentScript = Join-Path $PSScriptRoot "windows_process_environment.ps1"
if (-not (Test-Path -LiteralPath $processEnvironmentScript -PathType Leaf)) {
    throw "Windows process environment helper is unavailable: $processEnvironmentScript"
}
. $processEnvironmentScript
Repair-WindowsProcessPath

$runtimeDirectory = Join-Path $projectRoot ".runtime"
$statePath = Join-Path $runtimeDirectory "local-reviewer.json"
$reviewerOutPath = Join-Path $runtimeDirectory "local-reviewer-app.out.log"
$reviewerErrorPath = Join-Path $runtimeDirectory "local-reviewer-app.error.log"
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

try {
    if (Test-LocalReviewerReady) {
        $existingStartedAt = $null
        if (Test-Path -LiteralPath $statePath -PathType Leaf) {
            try {
                $existingState = Get-Content -LiteralPath $statePath -Raw -Encoding utf8 |
                    ConvertFrom-Json
                $existingStartedAt = $existingState.startedAt
            }
            catch {
                $existingStartedAt = $null
            }
        }
        Write-Result @{
            state = "running"
            publicOrigin = $null
            target = $reviewerUrl
            startedAt = $existingStartedAt
            reviewerReady = $true
            message = "Local Reviewer is already running."
        }
        exit 0
    }

    $npmCommand = Get-Command -Name "npm.cmd" -ErrorAction SilentlyContinue
    if ($null -eq $npmCommand) {
        throw "npm.cmd is unavailable. Run npm run windows:environment:check."
    }
    $nextBuildPath = Join-Path $projectRoot "apps\reviewer\.next\BUILD_ID"
    if (-not (Test-Path -LiteralPath $nextBuildPath -PathType Leaf)) {
        throw "Reviewer production build is missing. Run npm run reviewer:build."
    }

    $reviewerProcess = Start-Process `
        -FilePath $npmCommand.Source `
        -ArgumentList @("run", "reviewer:start") `
        -WorkingDirectory $projectRoot `
        -RedirectStandardOutput $reviewerOutPath `
        -RedirectStandardError $reviewerErrorPath `
        -PassThru `
        -WindowStyle Hidden

    for ($attempt = 0; $attempt -lt $reviewerStartupAttempts; $attempt++) {
        Start-Sleep -Milliseconds 500
        if ($reviewerProcess.HasExited -or (Test-LocalReviewerReady)) {
            break
        }
    }
    if (-not (Test-LocalReviewerReady)) {
        if (-not $reviewerProcess.HasExited) {
            Stop-Process -Id $reviewerProcess.Id
        }
        throw "Reviewer did not become ready within 20 seconds. Check .runtime local-reviewer-app logs."
    }

    $startedAt = [DateTimeOffset]::Now.ToString("o")
    $state = [ordered]@{
        pid = $reviewerProcess.Id
        target = $reviewerUrl
        startedAt = $startedAt
    }
    $temporaryStatePath = "$statePath.tmp"
    [IO.File]::WriteAllText(
        $temporaryStatePath,
        ($state | ConvertTo-Json),
        [Text.UTF8Encoding]::new($false)
    )
    Move-Item -LiteralPath $temporaryStatePath -Destination $statePath -Force

    Write-Result @{
        state = "running"
        publicOrigin = $null
        target = $reviewerUrl
        startedAt = $startedAt
        reviewerReady = $true
        message = "Local Reviewer is running."
    }
}
catch {
    if ($Json) {
        Write-Result @{
            state = "error"
            publicOrigin = $null
            target = $reviewerUrl
            startedAt = $null
            reviewerReady = $false
            message = $_.Exception.Message
        }
    }
    else {
        Write-Error $_
    }
    exit 1
}
