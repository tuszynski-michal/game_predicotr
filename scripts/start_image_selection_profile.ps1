[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourceRoot,

    [ValidateRange(0, 100000)]
    [int]$StartIndex = 0,

    [ValidateRange(1, 10000)]
    [int]$Limit = 5000,

    [ValidateRange(1, 21600)]
    [int]$MaxSeconds = 5100,

    [Parameter(Mandatory = $true)]
    [string]$Output
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$normalizerPath = Join-Path $PSScriptRoot 'windows_process_environment.ps1'
. $normalizerPath
Repair-WindowsProcessPath

$runtimeDirectory = Join-Path $projectRoot '.runtime'
New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null
$pidPath = Join-Path $runtimeDirectory 'image-selection-profile.pid.json'
if (Test-Path -LiteralPath $pidPath -PathType Leaf) {
    $previousPid = $null
    try {
        $previous = Get-Content -LiteralPath $pidPath -Raw -Encoding utf8 | ConvertFrom-Json
        if ($previous.PSObject.Properties.Name -contains 'pid') {
            $previousPid = [int]$previous.pid
        }
    }
    catch {
        $previousPid = $null
    }
    if ($null -ne $previousPid) {
        $previousProcess = Get-Process -Id $previousPid -ErrorAction SilentlyContinue
        if ($null -ne $previousProcess -and -not $previousProcess.HasExited) {
            throw "Image-selection profile is already running with PID $previousPid."
        }
    }
}

$resolvedSourceRoot = $(
    if ([IO.Path]::IsPathRooted($SourceRoot)) {
        [IO.Path]::GetFullPath($SourceRoot)
    }
    else {
        [IO.Path]::GetFullPath((Join-Path $projectRoot $SourceRoot))
    }
)
$sourceManifest = Join-Path $resolvedSourceRoot '_browser_manifest.json'
if (-not (Test-Path -LiteralPath $sourceManifest -PathType Leaf)) {
    throw "Image-selection source manifest does not exist: $sourceManifest"
}

$resolvedOutput = $(
    if ([IO.Path]::IsPathRooted($Output)) {
        [IO.Path]::GetFullPath($Output)
    }
    else {
        [IO.Path]::GetFullPath((Join-Path $projectRoot $Output))
    }
)
$rootPrefix = $projectRoot.TrimEnd('\') + '\'
if (-not $resolvedOutput.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Profile output must remain inside the repository workspace.'
}
if (Test-Path -LiteralPath $resolvedOutput) {
    throw "Profile output already exists: $resolvedOutput"
}

$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$profileScript = Join-Path $PSScriptRoot 'profile_image_selection_slice.py'
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Worker Python runtime does not exist: $pythonPath"
}
if (-not (Test-Path -LiteralPath $profileScript -PathType Leaf)) {
    throw "Image-selection profile script does not exist: $profileScript"
}

foreach ($name in @(
        'OMP_NUM_THREADS',
        'OPENBLAS_NUM_THREADS',
        'MKL_NUM_THREADS',
        'NUMEXPR_NUM_THREADS',
        'VECLIB_MAXIMUM_THREADS'
    )) {
    [Environment]::SetEnvironmentVariable($name, '1', 'Process')
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
$stdoutPath = Join-Path $runtimeDirectory "image-selection-profile-$stamp.out.log"
$stderrPath = Join-Path $runtimeDirectory "image-selection-profile-$stamp.error.log"
$arguments = @(
    $profileScript,
    '--source-root', $resolvedSourceRoot,
    '--start-index', [string]$StartIndex,
    '--limit', [string]$Limit,
    '--scan-workers', '3',
    '--verification-workers', '1',
    '--max-seconds', [string]$MaxSeconds,
    '--output', $resolvedOutput
)
$process = Start-Process `
    -FilePath $pythonPath `
    -ArgumentList $arguments `
    -WorkingDirectory $projectRoot `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath `
    -PassThru `
    -WindowStyle Hidden

Start-Sleep -Seconds 1
$process.Refresh()
if ($process.HasExited) {
    $errorTail = (Get-Content -LiteralPath $stderrPath -Tail 20 -ErrorAction SilentlyContinue) -join ' '
    throw "Image-selection profile exited during startup. $errorTail"
}

$record = [ordered]@{
    pid = $process.Id
    startedAt = (Get-Date).ToUniversalTime().ToString('o')
    sourceRoot = $resolvedSourceRoot
    startIndex = $StartIndex
    limit = $Limit
    maxSeconds = $MaxSeconds
    output = $resolvedOutput
    stdout = $stdoutPath
    stderr = $stderrPath
}
$record | ConvertTo-Json | Set-Content -LiteralPath $pidPath -Encoding utf8
$record | ConvertTo-Json
