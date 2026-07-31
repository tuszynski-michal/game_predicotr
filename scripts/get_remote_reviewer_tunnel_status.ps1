[CmdletBinding()]
param(
    [switch]$Json,
    [string]$ResultPath = ""
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$statePath = Join-Path $projectRoot ".runtime\remote-reviewer.json"
$reviewerUrl = "http://127.0.0.1:3001"

function Test-ReviewerReady {
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
    }
    else {
        Write-Host "Status: $($Value.state)"
        if ($null -ne $Value.publicOrigin) {
            Write-Host "Public URL: $($Value.publicOrigin)"
            Write-Host "Local target: $($Value.target)"
            Write-Host "PID: $($Value.pid)"
        }
    }
}

if (-not (Test-Path -LiteralPath $statePath)) {
    Write-Status @{
        state = "stopped"
        publicOrigin = $null
        target = $reviewerUrl
        startedAt = $null
        reviewerReady = (Test-ReviewerReady)
        pid = $null
    }
    exit 0
}

$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
$process = Get-Process -Id $state.pid -ErrorAction SilentlyContinue
if ($null -eq $process -or $process.ProcessName -notlike "cloudflared*") {
    Write-Status @{
        state = "stale"
        publicOrigin = $state.publicOrigin
        target = $state.target
        startedAt = $state.startedAt
        reviewerReady = (Test-ReviewerReady)
        pid = $state.pid
    }
    if (-not $Json) {
        Write-Host "Remove stale state with: npm run reviewer:remote:stop"
    }
    exit 0
}

$reviewerReady = Test-ReviewerReady
Write-Status @{
    state = $(if ($reviewerReady) { "running" } else { "degraded" })
    publicOrigin = $state.publicOrigin
    target = $state.target
    startedAt = $state.startedAt
    reviewerReady = $reviewerReady
    pid = $state.pid
}
