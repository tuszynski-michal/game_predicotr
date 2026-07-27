[CmdletBinding()]
param(
    [string]$Serial,

    [ValidateRange(60, 1800)]
    [int]$TimeoutSeconds = 900,

    [string]$OutputDirectory = 'ai_docs\quality\device-benchmarks',

    [ValidateSet('passed', 'failed')]
    [string]$VirtualizedTargetTableScrolling
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$androidSdkRoot = $env:ANDROID_HOME
if (-not $androidSdkRoot) {
    $androidSdkRoot = $env:ANDROID_SDK_ROOT
}
if (-not $androidSdkRoot) {
    $androidSdkRoot = Join-Path $repositoryRoot '.tooling\android-sdk'
}
$adb = Join-Path $androidSdkRoot 'platform-tools\adb.exe'
if (-not (Test-Path -LiteralPath $adb)) {
    throw 'adb.exe was not found. Configure ANDROID_HOME or run the Android toolchain setup.'
}

$deviceLines = & $adb devices |
    Select-Object -Skip 1 |
    Where-Object { $_ -match '^\S+\s+device$' }
if (-not $Serial) {
    if ($deviceLines.Count -ne 1) {
        throw "Expected exactly one connected device; found $($deviceLines.Count). Use -Serial."
    }
    $Serial = ($deviceLines[0] -split '\s+')[0]
}
elseif (-not ($deviceLines | Where-Object { $_ -match "^$([regex]::Escape($Serial))\s+device$" })) {
    throw "Device $Serial is not connected and authorized."
}

function Invoke-Adb {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)

    $result = & $adb -s $Serial @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "adb failed with exit code ${LASTEXITCODE}: $($Arguments -join ' ')"
    }
    return $result
}

function Read-DeviceProperty {
    param([string]$Name)

    return ((Invoke-Adb shell getprop $Name) -join '').Trim()
}

$manufacturer = Read-DeviceProperty 'ro.product.manufacturer'
$model = Read-DeviceProperty 'ro.product.model'
$androidVersion = Read-DeviceProperty 'ro.build.version.release'
$androidSdk = Read-DeviceProperty 'ro.build.version.sdk'
$airplaneMode = ((Invoke-Adb shell settings get global airplane_mode_on) -join '').Trim()
$wifiEnabled = ((Invoke-Adb shell settings get global wifi_on) -join '').Trim()

Invoke-Adb logcat -c | Out-Null
Invoke-Adb shell am force-stop com.gamepredictor.mobile | Out-Null
$launchOutput = Invoke-Adb shell am start -W -n com.gamepredictor.mobile/.MainActivity

$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
$peakTotalPssKb = 0
$peakTotalRssKb = 0
$benchmarkJson = $null
while ($stopwatch.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
    $memory = (Invoke-Adb shell dumpsys meminfo com.gamepredictor.mobile) -join "`n"
    if ($memory -match 'TOTAL PSS:\s+([0-9,]+).*TOTAL RSS:\s+([0-9,]+)') {
        $currentPss = [int64](($Matches[1] -replace ',', ''))
        $currentRss = [int64](($Matches[2] -replace ',', ''))
        $peakTotalPssKb = [math]::Max($peakTotalPssKb, $currentPss)
        $peakTotalRssKb = [math]::Max($peakTotalRssKb, $currentRss)
    }

    $logs = Invoke-Adb logcat -d -v raw 'ReactNativeJS:I' '*:S'
    $line = $logs |
        Where-Object { $_ -like '*M35_BENCHMARK_RESULT*' } |
        Select-Object -Last 1
    if ($line) {
        $prefixIndex = $line.IndexOf('M35_BENCHMARK_RESULT')
        $jsonIndex = $line.IndexOf('{', $prefixIndex)
        if ($jsonIndex -ge 0) {
            $benchmarkJson = $line.Substring($jsonIndex)
            break
        }
    }
    Start-Sleep -Milliseconds 1000
}
$stopwatch.Stop()
if (-not $benchmarkJson) {
    throw "Timed out after $TimeoutSeconds seconds waiting for M35_BENCHMARK_RESULT."
}

$benchmark = $benchmarkJson | ConvertFrom-Json
if (
    $benchmark.report.dataset.layoutCount -ne 500000 -or
    $benchmark.report.dataset.releaseVersion -ne 'm35-benchmark.1'
) {
    throw 'The device result does not describe the expected M3.5 benchmark snapshot.'
}

$scrollingPassed = $null
if ($VirtualizedTargetTableScrolling -eq 'passed') {
    $scrollingPassed = $true
}
elseif ($VirtualizedTargetTableScrolling -eq 'failed') {
    $scrollingPassed = $false
}

$envelope = [ordered]@{
    capturedAt = [DateTimeOffset]::UtcNow.ToString('o')
    collection = [ordered]@{
        adbSerial = $Serial
        airplaneMode = $airplaneMode
        androidSdk = $androidSdk
        androidVersion = $androidVersion
        durationSeconds = [math]::Round($stopwatch.Elapsed.TotalSeconds, 3)
        launchOutput = @($launchOutput)
        manufacturer = $manufacturer
        model = $model
        peakTotalPssKb = $peakTotalPssKb
        peakTotalRssKb = $peakTotalRssKb
        wifiEnabled = $wifiEnabled
    }
    benchmark = $benchmark
    manualAcceptance = [ordered]@{
        virtualizedTargetTableScrollingPassed = $scrollingPassed
    }
}

$safeDeviceName = "$manufacturer-$model-$Serial" -replace '[^A-Za-z0-9._-]', '-'
$resolvedOutputDirectory = [System.IO.Path]::GetFullPath(
    (Join-Path $repositoryRoot $OutputDirectory)
)
if (-not $resolvedOutputDirectory.StartsWith(
    $repositoryRoot + [System.IO.Path]::DirectorySeparatorChar,
    [StringComparison]::OrdinalIgnoreCase
)) {
    throw 'Output directory must remain inside the repository.'
}
[System.IO.Directory]::CreateDirectory($resolvedOutputDirectory) | Out-Null
$outputPath = Join-Path $resolvedOutputDirectory "$safeDeviceName.json"
$json = $envelope | ConvertTo-Json -Depth 20
[System.IO.File]::WriteAllText(
    $outputPath,
    $json + [Environment]::NewLine,
    [System.Text.UTF8Encoding]::new($false)
)
Write-Host "Saved device benchmark to $outputPath"
Write-Host "Peak TOTAL PSS: $peakTotalPssKb KB"
Write-Host "Peak TOTAL RSS: $peakTotalRssKb KB"
