[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Source,

    [Parameter(Mandatory = $true)]
    [string]$FirstOutput,

    [Parameter(Mandatory = $true)]
    [string]$SecondOutput,

    [Parameter(Mandatory = $true)]
    [string]$GameId,

    [Parameter(Mandatory = $true)]
    [string]$ResumeUploadId,

    [Parameter(Mandatory = $true)]
    [string]$SecondSourceRunId,

    [Parameter(Mandatory = $true)]
    [string]$FirstReport,

    [Parameter(Mandatory = $true)]
    [string]$SecondReport,

    [Parameter(Mandatory = $true)]
    [string]$State,

    [string]$ApiBaseUrl = 'http://127.0.0.1:8000',

    [ValidateRange(1, 8)]
    [int]$UploadWorkers = 4,

    [ValidateRange(1, 100000)]
    [int]$FirstSequenceNumber = 45163,

    [ValidateRange(1, 100000)]
    [int]$SecondFirstSequenceNumber = 1,

    [ValidateRange(1, [long]::MaxValue)]
    [long]$ExpectedTotalBytes = 1
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$runnerPath = Join-Path $PSScriptRoot 'run_live_image_selection.py'
$sourcePath = (Resolve-Path -LiteralPath $Source).Path
$firstOutputPath = (Resolve-Path -LiteralPath $FirstOutput).Path
$secondOutputPath = (Resolve-Path -LiteralPath $SecondOutput).Path
$firstReportPath = [IO.Path]::GetFullPath((Join-Path $projectRoot $FirstReport))
$secondReportPath = [IO.Path]::GetFullPath((Join-Path $projectRoot $SecondReport))
$statePath = [IO.Path]::GetFullPath((Join-Path $projectRoot $State))

foreach ($path in @($firstReportPath, $secondReportPath)) {
    if (Test-Path -LiteralPath $path) {
        throw "Sequential image-selection report already exists: $path"
    }
}
foreach ($path in @($firstOutputPath, $secondOutputPath)) {
    if (@(Get-ChildItem -LiteralPath $path -Force).Count -ne 0) {
        throw "Sequential image-selection output directory is not empty: $path"
    }
}

function Write-QueueState {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Status,
        [int]$FirstExitCode = -1,
        [int]$SecondExitCode = -1
    )
    $payload = [ordered]@{
        schemaVersion = 1
        status = $Status
        updatedAt = (Get-Date).ToUniversalTime().ToString('o')
        source = $sourcePath
        firstOutput = $firstOutputPath
        secondOutput = $secondOutputPath
        resumeUploadId = $ResumeUploadId
        secondSourceRunId = $SecondSourceRunId
        firstReport = $firstReportPath
        secondReport = $secondReportPath
        firstExitCode = $FirstExitCode
        secondExitCode = $SecondExitCode
    }
    $temporary = "$statePath.tmp"
    [IO.File]::WriteAllText(
        $temporary,
        ($payload | ConvertTo-Json),
        [Text.UTF8Encoding]::new($false)
    )
    Move-Item -LiteralPath $temporary -Destination $statePath -Force
}

Write-QueueState -Status 'first_preparing'
$firstArguments = @(
    $runnerPath,
    '--source', $sourcePath,
    '--output', $firstOutputPath,
    '--game-id', $GameId,
    '--first-sequence-number', [string]$FirstSequenceNumber,
    '--api-base-url', $ApiBaseUrl,
    '--report', $firstReportPath,
    '--upload-workers', [string]$UploadWorkers,
    '--expected-total-bytes', [string]$ExpectedTotalBytes,
    '--resume-upload-id', $ResumeUploadId
)
& $pythonPath @firstArguments
$firstExitCode = $LASTEXITCODE
if ($firstExitCode -ne 0) {
    Write-QueueState -Status 'first_failed' -FirstExitCode $firstExitCode
    exit $firstExitCode
}

Write-QueueState -Status 'second_starting' -FirstExitCode $firstExitCode
$secondArguments = @(
    $runnerPath,
    '--rerun-id', $SecondSourceRunId,
    '--output', $secondOutputPath,
    '--first-sequence-number', [string]$SecondFirstSequenceNumber,
    '--api-base-url', $ApiBaseUrl,
    '--report', $secondReportPath
)
& $pythonPath @secondArguments
$secondExitCode = $LASTEXITCODE
if ($secondExitCode -ne 0) {
    Write-QueueState `
        -Status 'second_failed' `
        -FirstExitCode $firstExitCode `
        -SecondExitCode $secondExitCode
    exit $secondExitCode
}

Write-QueueState `
    -Status 'finished' `
    -FirstExitCode $firstExitCode `
    -SecondExitCode $secondExitCode
