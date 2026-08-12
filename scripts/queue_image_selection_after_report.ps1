[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$PredecessorReport,

    [Parameter(Mandatory = $true)]
    [string]$Source,

    [Parameter(Mandatory = $true)]
    [string]$Output,

    [Parameter(Mandatory = $true)]
    [string]$GameId,

    [Parameter(Mandatory = $true)]
    [string]$Report,

    [Parameter(Mandatory = $true)]
    [string]$PidState,

    [Parameter(Mandatory = $true)]
    [string]$QueueState,

    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 2147483647)]
    [int]$FirstSequenceNumber,

    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 1000000)]
    [int]$ExpectedJpegCount,

    [string]$ApiBaseUrl = 'http://127.0.0.1:8000',

    [ValidateRange(5, 60)]
    [int]$PollSeconds = 15,

    [ValidateRange(1, 72)]
    [int]$MaxWaitHours = 24
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $PSScriptRoot 'start_controlled_image_selection.ps1'
$predecessorReportPath = [IO.Path]::GetFullPath((Join-Path $projectRoot $PredecessorReport))
$reportPath = [IO.Path]::GetFullPath((Join-Path $projectRoot $Report))
$pidStatePath = [IO.Path]::GetFullPath((Join-Path $projectRoot $PidState))
$queueStatePath = [IO.Path]::GetFullPath((Join-Path $projectRoot $QueueState))
$sourcePath = (Resolve-Path -LiteralPath $Source).Path
$outputPath = (Resolve-Path -LiteralPath $Output).Path

function Write-QueueState {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Status,
        [string]$Detail = ''
    )
    $payload = [ordered]@{
        schemaVersion = 1
        status = $Status
        detail = $Detail
        updatedAt = (Get-Date).ToUniversalTime().ToString('o')
        predecessorReport = $predecessorReportPath
        source = $sourcePath
        output = $outputPath
        report = $reportPath
        pidState = $pidStatePath
        firstSequenceNumber = $FirstSequenceNumber
        expectedJpegCount = $ExpectedJpegCount
    }
    $temporary = "$queueStatePath.tmp"
    [IO.File]::WriteAllText(
        $temporary,
        ($payload | ConvertTo-Json),
        [Text.UTF8Encoding]::new($false)
    )
    Move-Item -LiteralPath $temporary -Destination $queueStatePath -Force
}

if (Test-Path -LiteralPath $reportPath) {
    throw "Queued image-selection report already exists: $reportPath"
}
if (Test-Path -LiteralPath $pidStatePath) {
    throw "Queued image-selection PID state already exists: $pidStatePath"
}
if (@(Get-ChildItem -LiteralPath $outputPath -Force).Count -ne 0) {
    throw "Queued image-selection output directory is not empty: $outputPath"
}

$deadline = (Get-Date).AddHours($MaxWaitHours)
Write-QueueState -Status 'waiting_for_predecessor'
while ((Get-Date) -lt $deadline) {
    if (Test-Path -LiteralPath $predecessorReportPath) {
        $predecessor = Get-Content -LiteralPath $predecessorReportPath -Raw -Encoding utf8 |
            ConvertFrom-Json
        if ($predecessor.status -in 'waiting_for_review', 'completed') {
            break
        }
        if ($predecessor.status -in 'failed', 'cancelled') {
            Write-QueueState `
                -Status 'predecessor_not_successful' `
                -Detail "Predecessor ended with status $($predecessor.status)."
            exit 1
        }
    }
    Start-Sleep -Seconds $PollSeconds
}

if ((Get-Date) -ge $deadline) {
    Write-QueueState -Status 'timed_out' -Detail 'Predecessor did not finish in time.'
    exit 1
}

$headers = @{ 'X-Admin-Intent' = 'local-owner' }
$jobs = Invoke-RestMethod `
    -Uri "$ApiBaseUrl/api/v1/admin/jobs?jobType=image_selection&limit=100" `
    -Headers $headers `
    -TimeoutSec 10
$itemsProperty = $jobs.PSObject.Properties['items']
$items = if ($null -ne $itemsProperty) { @($itemsProperty.Value) } else { @($jobs) }
$active = @($items | Where-Object { $_.status -in 'queued', 'processing', 'cancelling' })
if ($active.Count -ne 0) {
    Write-QueueState `
        -Status 'blocked_by_active_job' `
        -Detail "Found $($active.Count) active image-selection job(s)."
    exit 1
}

Write-QueueState -Status 'starting'
& powershell.exe `
    -NoProfile `
    -ExecutionPolicy Bypass `
    -File $launcher `
    -Source $sourcePath `
    -Output $outputPath `
    -GameId $GameId `
    -Report $Report `
    -PidState $PidState `
    -FirstSequenceNumber $FirstSequenceNumber `
    -ApiBaseUrl $ApiBaseUrl `
    -UploadWorkers 4 `
    -ExpectedJpegCount $ExpectedJpegCount `
    -TimeoutSeconds 600
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    Write-QueueState -Status 'start_failed' -Detail "Launcher exited with code $exitCode."
    exit $exitCode
}

Write-QueueState -Status 'started'
