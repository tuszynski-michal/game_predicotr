[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourceRunId,

    [Parameter(Mandatory = $true)]
    [string]$Output,

    [Parameter(Mandatory = $true)]
    [string]$Report,

    [Parameter(Mandatory = $true)]
    [string]$PidState,

    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 2147483647)]
    [int]$FirstSequenceNumber,

    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 2147483647)]
    [int]$LastSequenceNumber,

    [string]$ApiBaseUrl = 'http://127.0.0.1:8000',

    [ValidateRange(1, 600)]
    [int]$TimeoutSeconds = 30
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$runnerPath = Join-Path $PSScriptRoot 'run_live_image_selection.py'
$environmentScript = Join-Path $PSScriptRoot 'windows_process_environment.ps1'
$outputPath = (Resolve-Path -LiteralPath $Output).Path
$reportPath = [IO.Path]::GetFullPath((Join-Path $projectRoot $Report))
$pidStatePath = [IO.Path]::GetFullPath((Join-Path $projectRoot $PidState))

if (Test-Path -LiteralPath $reportPath) {
    throw "Image-selection report already exists: $reportPath"
}
if (Test-Path -LiteralPath $pidStatePath) {
    throw "Image-selection PID state already exists: $pidStatePath"
}
if (@(Get-ChildItem -LiteralPath $outputPath -Force).Count -ne 0) {
    throw "Image-selection output directory is not empty: $outputPath"
}

. $environmentScript
Repair-WindowsProcessPath

$runtimeDirectory = Join-Path $projectRoot '.runtime'
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
$stdoutPath = Join-Path $runtimeDirectory "image-selection-rerun-$stamp.out.log"
$stderrPath = Join-Path $runtimeDirectory "image-selection-rerun-$stamp.error.log"
$arguments = @(
    ('"{0}"' -f $runnerPath),
    '--rerun-id', $SourceRunId,
    '--output', ('"{0}"' -f $outputPath),
    '--first-sequence-number', [string]$FirstSequenceNumber,
    '--last-sequence-number', [string]$LastSequenceNumber,
    '--api-base-url', $ApiBaseUrl,
    '--report', ('"{0}"' -f $reportPath)
)

$process = Start-Process `
    -FilePath $pythonPath `
    -ArgumentList $arguments `
    -WorkingDirectory $projectRoot `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath `
    -WindowStyle Hidden `
    -PassThru

$state = [ordered]@{
    pid = $process.Id
    startedAt = (Get-Date).ToUniversalTime().ToString('o')
    sourceRunId = $SourceRunId
    firstSequenceNumber = $FirstSequenceNumber
    lastSequenceNumber = $LastSequenceNumber
    output = $outputPath
    report = $reportPath
    stdout = $stdoutPath
    stderr = $stderrPath
    api = $ApiBaseUrl
}
$temporaryStatePath = "$pidStatePath.tmp"
[IO.File]::WriteAllText(
    $temporaryStatePath,
    ($state | ConvertTo-Json),
    [Text.UTF8Encoding]::new($false)
)
Move-Item -LiteralPath $temporaryStatePath -Destination $pidStatePath -Force

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$reportState = $null
do {
    if ($null -eq (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
        $stderrTail = if (Test-Path -LiteralPath $stderrPath) {
            (Get-Content -LiteralPath $stderrPath -Tail 20 -Encoding utf8) -join "`n"
        } else {
            ''
        }
        throw "Controlled image-selection rerun exited before readiness. $stderrTail"
    }
    if (Test-Path -LiteralPath $reportPath) {
        $reportState = Get-Content -LiteralPath $reportPath -Raw -Encoding utf8 |
            ConvertFrom-Json
        if ($null -ne $reportState.status) {
            break
        }
    }
    Start-Sleep -Milliseconds 250
} while ((Get-Date) -lt $deadline)

if ($null -eq $reportState) {
    throw "Image-selection rerun report was not created within $TimeoutSeconds seconds."
}

[pscustomobject]@{
    pid = $process.Id
    sourceRunId = $SourceRunId
    firstSequenceNumber = $FirstSequenceNumber
    lastSequenceNumber = $LastSequenceNumber
    output = $outputPath
    report = $reportPath
    pidState = $pidStatePath
    stdout = $stdoutPath
    stderr = $stderrPath
    status = $reportState.status
} | ConvertTo-Json -Depth 5
