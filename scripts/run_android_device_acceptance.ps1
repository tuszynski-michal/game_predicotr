[CmdletBinding()]
param(
    [string]$ApkPath = 'apps\mobile\android\app\build\outputs\apk\release\app-release.apk',

    [Parameter(Mandatory)]
    [string]$ExpectedModelPattern,

    [ValidateSet('Initial', 'Update')]
    [string]$Stage = 'Initial',

    [switch]$RequireAirplaneMode,

    [string]$ExpectedReleaseVersion,

    [ValidatePattern('^[a-f0-9]{64}$')]
    [string]$ExpectedSnapshotSha256
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$resolvedApkPath = [System.IO.Path]::GetFullPath((Join-Path $repositoryRoot $ApkPath))
$adbPath = Join-Path $repositoryRoot '.tooling\android-sdk\platform-tools\adb.exe'
$reportRoot = Join-Path $repositoryRoot '.tooling\device-acceptance'
$packageName = 'com.gamepredictor.mobile'

function Get-PackageInfo {
    param(
        [Parameter(Mandatory)]
        [string]$DeviceSerial
    )

    $dump = & $adbPath -s $DeviceSerial shell dumpsys package $packageName
    $text = $dump -join "`n"
    $versionCodeMatch = [regex]::Match($text, 'versionCode=(\d+)')
    $versionNameMatch = [regex]::Match($text, 'versionName=([^\s]+)')
    if (-not $versionCodeMatch.Success -or -not $versionNameMatch.Success) {
        return $null
    }
    $firstInstallTimeMatch = [regex]::Match($text, 'firstInstallTime=([^\r\n]+)')
    $lastUpdateTimeMatch = [regex]::Match($text, 'lastUpdateTime=([^\r\n]+)')
    return [pscustomobject]@{
        versionCode = [int]$versionCodeMatch.Groups[1].Value
        versionName = $versionNameMatch.Groups[1].Value
        firstInstallTime = if ($firstInstallTimeMatch.Success) {
            $firstInstallTimeMatch.Groups[1].Value.Trim()
        }
        else {
            $null
        }
        lastUpdateTime = if ($lastUpdateTimeMatch.Success) {
            $lastUpdateTimeMatch.Groups[1].Value.Trim()
        }
        else {
            $null
        }
    }
}

if (-not (Test-Path -LiteralPath $resolvedApkPath)) {
    throw "APK not found at $resolvedApkPath."
}
if (-not (Test-Path -LiteralPath $adbPath)) {
    throw 'ADB was not found. Run npm run android:toolchain:setup.'
}

$deviceLines = @(
    & $adbPath devices -l |
        Where-Object { $_ -match '^\S+\s+device(?:\s|$)' }
)
if ($deviceLines.Count -ne 1) {
    throw "Expected exactly one authorized Android device; found $($deviceLines.Count)."
}
$serial = ($deviceLines[0] -split '\s+')[0]
$model = (& $adbPath -s $serial shell getprop ro.product.model).Trim()
$manufacturer = (& $adbPath -s $serial shell getprop ro.product.manufacturer).Trim()
$androidVersion = (& $adbPath -s $serial shell getprop ro.build.version.release).Trim()
$sdkVersion = (& $adbPath -s $serial shell getprop ro.build.version.sdk).Trim()

if ($model -notmatch $ExpectedModelPattern) {
    throw "Connected model '$model' does not match '$ExpectedModelPattern'."
}
if ($RequireAirplaneMode) {
    $airplaneMode = (& $adbPath -s $serial shell settings get global airplane_mode_on).Trim()
    if ($airplaneMode -ne '1') {
        throw 'Airplane mode must be enabled before the offline acceptance run.'
    }
}

$previousPackage = Get-PackageInfo -DeviceSerial $serial
if ($Stage -eq 'Update' -and $null -eq $previousPackage) {
    throw 'Update acceptance requires an existing installation. Do not uninstall the app.'
}

$installStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
$installOutput = & $adbPath -s $serial install -r $resolvedApkPath
$installStopwatch.Stop()
if ($LASTEXITCODE -ne 0 -or -not (($installOutput -join "`n").Contains('Success'))) {
    throw "ADB install failed: $($installOutput -join "`n")"
}

$installedPackage = Get-PackageInfo -DeviceSerial $serial
if ($null -eq $installedPackage) {
    throw 'Installed package did not expose versionCode/versionName.'
}
if (
    $Stage -eq 'Update' -and
    $installedPackage.versionCode -le $previousPackage.versionCode
) {
    throw (
        "Update requires a higher versionCode; previous was " +
        "$($previousPackage.versionCode), installed is $($installedPackage.versionCode)."
    )
}
$updateWithoutUninstall = (
    $Stage -eq 'Update' -and
    $null -ne $previousPackage.firstInstallTime -and
    $previousPackage.firstInstallTime -eq $installedPackage.firstInstallTime
)
if ($Stage -eq 'Update' -and -not $updateWithoutUninstall) {
    throw 'The firstInstallTime changed, so an in-place update was not proven.'
}

& $adbPath -s $serial shell am force-stop $packageName | Out-Null
$launchStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
& $adbPath -s $serial shell monkey -p $packageName -c android.intent.category.LAUNCHER 1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Could not launch the installed application.'
}

$processId = ''
for ($attempt = 0; $attempt -lt 20 -and -not $processId; $attempt += 1) {
    Start-Sleep -Milliseconds 250
    $processId = (& $adbPath -s $serial shell pidof $packageName).Trim()
}
$launchStopwatch.Stop()
if (-not $processId) {
    throw 'Application process did not start within five seconds.'
}

New-Item -ItemType Directory -Force -Path $reportRoot | Out-Null
$safeModel = $model -replace '[^A-Za-z0-9_.-]', '_'
$reportPath = Join-Path $reportRoot "$($Stage.ToLowerInvariant())-$safeModel.json"
$report = [ordered]@{
    stage = $Stage
    capturedAtUtc = [DateTime]::UtcNow.ToString('o')
    serial = $serial
    manufacturer = $manufacturer
    model = $model
    androidVersion = $androidVersion
    sdkVersion = $sdkVersion
    packageName = $packageName
    previousVersionName = if ($null -eq $previousPackage) {
        $null
    }
    else {
        $previousPackage.versionName
    }
    previousVersionCode = if ($null -eq $previousPackage) {
        $null
    }
    else {
        $previousPackage.versionCode
    }
    versionName = $installedPackage.versionName
    versionCode = $installedPackage.versionCode
    firstInstallTime = $installedPackage.firstInstallTime
    lastUpdateTime = $installedPackage.lastUpdateTime
    updateWithoutUninstall = $updateWithoutUninstall
    expectedReleaseVersion = if ($ExpectedReleaseVersion) {
        $ExpectedReleaseVersion
    }
    else {
        $null
    }
    expectedSnapshotSha256 = if ($ExpectedSnapshotSha256) {
        $ExpectedSnapshotSha256
    }
    else {
        $null
    }
    apkSha256 = (Get-FileHash -LiteralPath $resolvedApkPath -Algorithm SHA256).Hash.ToLowerInvariant()
    apkSizeBytes = (Get-Item -LiteralPath $resolvedApkPath).Length
    installElapsedSeconds = [math]::Round($installStopwatch.Elapsed.TotalSeconds, 2)
    processStartElapsedSeconds = [math]::Round($launchStopwatch.Elapsed.TotalSeconds, 2)
    airplaneModeRequired = [bool]$RequireAirplaneMode
    automatedChecks = 'passed'
    manualScenario = 'pending'
}
$report | ConvertTo-Json | Set-Content -LiteralPath $reportPath -Encoding utf8

Write-Host "Installed and launched $packageName on $manufacturer $model."
Write-Host "Version: $($report.versionName) ($($report.versionCode))"
if ($Stage -eq 'Update') {
    Write-Host (
        "Updated in place from $($report.previousVersionName) " +
        "($($report.previousVersionCode)); firstInstallTime was preserved."
    )
}
Write-Host "Install elapsed: $($report.installElapsedSeconds) seconds"
Write-Host "Process start elapsed: $($report.processStartElapsedSeconds) seconds"
Write-Host "Device report: $reportPath"
Write-Host (
    'Confirm the displayed releaseVersion and snapshot SHA-256, then complete ' +
    'the manual checklist in ai_docs\quality\M1_DEVICE_ACCEPTANCE.md.'
)
