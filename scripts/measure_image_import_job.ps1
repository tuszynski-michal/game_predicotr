[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [Guid]$JobId,

    [string]$ApiBaseUrl = 'http://127.0.0.1:8000',

    [ValidateRange(1, 1440)]
    [int]$TimeoutMinutes = 240,

    [ValidateRange(1, 30)]
    [int]$PollSeconds = 2,

    [string]$OutputPath = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$statePath = Join-Path $projectRoot '.runtime\worker-lanes.json'
if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
    throw "Worker lane state is unavailable: $statePath"
}
$state = Get-Content -LiteralPath $statePath -Raw -Encoding utf8 | ConvertFrom-Json
$general = @($state.processes | Where-Object { $_.lane -eq 'general' }) | Select-Object -First 1
if ($null -eq $general) {
    throw 'The general worker lane is not registered.'
}
$headers = @{ 'X-Admin-Intent' = 'local-owner' }
$base = $ApiBaseUrl.TrimEnd('/')
$deadline = [DateTimeOffset]::UtcNow.AddMinutes($TimeoutMinutes)
$samples = [System.Collections.Generic.List[object]]::new()
$peakWorkingSet = 0L
$terminal = @('waiting_for_review', 'completed', 'failed', 'cancelled')
$job = $null

while ([DateTimeOffset]::UtcNow -lt $deadline) {
    $job = Invoke-RestMethod `
        -Method Get `
        -Uri "$base/api/v1/admin/jobs/$JobId" `
        -Headers $headers `
        -TimeoutSec 10
    $process = Get-Process -Id ([int]$general.pid) -ErrorAction SilentlyContinue
    if ($null -ne $process) {
        $process.Refresh()
        $workingSet = [long]$process.WorkingSet64
        $peakWorkingSet = [Math]::Max($peakWorkingSet, $workingSet)
        $samples.Add([ordered]@{
            atUtc = [DateTimeOffset]::UtcNow.ToString('o')
            progressCurrent = [long]$job.progress.current
            progressTotal = $job.progress.total
            stage = $job.stage
            workingSetBytes = $workingSet
        })
    }
    if ($terminal -contains [string]$job.status) {
        break
    }
    Start-Sleep -Seconds $PollSeconds
}

if ($null -eq $job) {
    throw 'The job could not be read before timeout.'
}
if (-not ($terminal -contains [string]$job.status)) {
    throw "Measurement timed out while job remained in status $($job.status)."
}
$operations = Invoke-RestMethod `
    -Method Get `
    -Uri "$base/api/v1/admin/image-jobs/$JobId/operations?file_limit=1" `
    -Headers $headers `
    -TimeoutSec 10
$imageCount = [long]$operations.total
$elapsedSeconds = if ($null -eq $operations.elapsedSeconds) {
    $null
} else {
    [double]$operations.elapsedSeconds
}
$report = [ordered]@{
    schemaVersion = 1
    jobId = $JobId.ToString('D')
    status = [string]$job.status
    imageCount = $imageCount
    elapsedSeconds = $elapsedSeconds
    secondsPerImage = if ($null -eq $elapsedSeconds -or $imageCount -eq 0) {
        $null
    } else {
        $elapsedSeconds / $imageCount
    }
    imagesPerMinute = $operations.filesPerMinute
    peakGeneralWorkerWorkingSetBytes = $peakWorkingSet
    stageCounts = $operations.stageCounts
    samples = @($samples)
}
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $report | ConvertTo-Json -Depth 8
    exit 0
}
$resolvedOutput = [IO.Path]::GetFullPath($OutputPath, $projectRoot)
$outputDirectory = Split-Path -Parent $resolvedOutput
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
[IO.File]::WriteAllText(
    $resolvedOutput,
    ($report | ConvertTo-Json -Depth 8),
    [Text.UTF8Encoding]::new($false)
)
Write-Host "Image import measurement saved: $resolvedOutput"
