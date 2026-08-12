[CmdletBinding()]
param(
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
    [ValidateRange(1, 2147483647)]
    [int]$FirstSequenceNumber,

    [string]$ApiBaseUrl = 'http://127.0.0.1:8000',

    [ValidateRange(1, 8)]
    [int]$UploadWorkers = 4,

    [ValidateRange(1, 100000)]
    [int]$ExpectedJpegCount = 1,

    [ValidateRange(1, 600)]
    [int]$TimeoutSeconds = 30,

    [string]$ResumeUploadId
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$runnerPath = Join-Path $PSScriptRoot 'run_live_image_selection.py'
$environmentScript = Join-Path $PSScriptRoot 'windows_process_environment.ps1'
$sourcePath = (Resolve-Path -LiteralPath $Source).Path
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

$jpegFiles = @(
    Get-ChildItem -LiteralPath $sourcePath -Recurse -File |
        Where-Object { $_.Extension -in '.jpg', '.jpeg', '.JPG', '.JPEG' }
)
$jpegCount = $jpegFiles.Count
$jpegBytes = ($jpegFiles | Measure-Object -Property Length -Sum).Sum
if ($jpegCount -ne $ExpectedJpegCount) {
    throw "Expected $ExpectedJpegCount JPEG files, found $jpegCount in $sourcePath."
}

. $environmentScript
Repair-WindowsProcessPath

$runtimeDirectory = Join-Path $projectRoot '.runtime'
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
$stdoutPath = Join-Path $runtimeDirectory "image-selection-live-$stamp.out.log"
$stderrPath = Join-Path $runtimeDirectory "image-selection-live-$stamp.error.log"
$arguments = @(
    ('"{0}"' -f $runnerPath),
    '--source', ('"{0}"' -f $sourcePath),
    '--output', ('"{0}"' -f $outputPath),
    '--game-id', $GameId,
    '--first-sequence-number', [string]$FirstSequenceNumber,
    '--api-base-url', $ApiBaseUrl,
    '--report', ('"{0}"' -f $reportPath),
    '--upload-workers', [string]$UploadWorkers,
    '--expected-total-bytes', [string]$jpegBytes
)
if (-not [string]::IsNullOrWhiteSpace($ResumeUploadId)) {
    $arguments += @('--resume-upload-id', $ResumeUploadId)
}

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
    source = $sourcePath
    sourceCount = $jpegCount
    sourceBytes = $jpegBytes
    firstSequenceNumber = $FirstSequenceNumber
    output = $outputPath
    report = $reportPath
    stdout = $stdoutPath
    stderr = $stderrPath
    api = $ApiBaseUrl
    resumeUploadId = $ResumeUploadId
}
$temporaryStatePath = "$pidStatePath.tmp"
[IO.File]::WriteAllText(
    $temporaryStatePath,
    ($state | ConvertTo-Json),
    [Text.UTF8Encoding]::new($false)
)
Move-Item -LiteralPath $temporaryStatePath -Destination $pidStatePath -Force

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
do {
    if ($null -eq (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
        $stderrTail = if (Test-Path -LiteralPath $stderrPath) {
            (Get-Content -LiteralPath $stderrPath -Tail 20 -Encoding utf8) -join "`n"
        } else {
            ''
        }
        throw "Controlled image-selection process exited before readiness. $stderrTail"
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

if (-not (Test-Path -LiteralPath $reportPath)) {
    throw "Image-selection report was not created within $TimeoutSeconds seconds."
}

[pscustomobject]@{
    pid = $process.Id
    sourceCount = $jpegCount
    output = $outputPath
    report = $reportPath
    pidState = $pidStatePath
    stdout = $stdoutPath
    stderr = $stderrPath
    status = $reportState.status
} | ConvertTo-Json -Depth 5
