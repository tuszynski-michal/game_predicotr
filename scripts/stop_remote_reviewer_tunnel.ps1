[CmdletBinding()]
param(
    [switch]$Json,
    [string]$ResultPath = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$statePath = Join-Path $projectRoot ".runtime\remote-reviewer.json"

if (-not (Test-Path -LiteralPath $statePath)) {
    if ($Json) {
        $resultJson = @{
            state = "stopped"
            publicOrigin = $null
            target = "http://127.0.0.1:3001"
            startedAt = $null
            reviewerReady = $null
            message = "Reviewer tunnel is not running."
        } | ConvertTo-Json -Compress
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
        Write-Host "Reviewer tunnel is not running."
    }
    exit 0
}

$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
$process = Get-Process -Id $state.pid -ErrorAction SilentlyContinue
if ($null -ne $process) {
    if ($process.ProcessName -notlike "cloudflared*") {
        throw "PID $($state.pid) does not belong to cloudflared. State was not changed."
    }
    Stop-Process -Id $process.Id
}
Remove-Item -LiteralPath $statePath -Force
if ($Json) {
    $resultJson = @{
        state = "stopped"
        publicOrigin = $null
        target = $state.target
        startedAt = $null
        reviewerReady = $null
        message = "Reviewer tunnel stopped. The public link is inactive."
    } | ConvertTo-Json -Compress
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
    Write-Host "Reviewer tunnel stopped. The public link is inactive."
}
