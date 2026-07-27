[CmdletBinding()]
param(
    [ValidateSet('Debug', 'Release')]
    [string]$Variant = 'Debug',

    [ValidatePattern('^[a-z0-9_,-]+$')]
    [string]$Architectures = 'arm64-v8a',

    [ValidatePattern('^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$')]
    [string]$VersionName = '0.1.0',

    [ValidateRange(1, 2100000000)]
    [int]$VersionCode = 1
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$mobileRoot = Join-Path $repositoryRoot 'apps\mobile'
$localToolingRoot = Join-Path $repositoryRoot '.tooling'
$localJdkRoot = Join-Path $localToolingRoot 'jdk'
$localAndroidSdkRoot = Join-Path $localToolingRoot 'android-sdk'

$javaHome = $env:JAVA_HOME
if (-not $javaHome -and (Test-Path -LiteralPath $localJdkRoot)) {
    $javaHome = Get-ChildItem -LiteralPath $localJdkRoot -Directory |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'bin\java.exe') } |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $javaHome -or -not (Test-Path -LiteralPath (Join-Path $javaHome 'bin\java.exe'))) {
    throw 'JDK 17 was not found. Run npm run android:toolchain:setup or configure JAVA_HOME.'
}

$androidSdkRoot = $env:ANDROID_HOME
if (-not $androidSdkRoot) {
    $androidSdkRoot = $env:ANDROID_SDK_ROOT
}
if (-not $androidSdkRoot -and (Test-Path -LiteralPath $localAndroidSdkRoot)) {
    $androidSdkRoot = $localAndroidSdkRoot
}
if (-not $androidSdkRoot -or -not (Test-Path -LiteralPath (Join-Path $androidSdkRoot 'platforms\android-36'))) {
    throw 'Android SDK Platform 36 was not found. Run npm run android:toolchain:setup or configure ANDROID_HOME.'
}

$env:JAVA_HOME = $javaHome
$env:ANDROID_HOME = $androidSdkRoot
$env:ANDROID_SDK_ROOT = $androidSdkRoot
# Native Android dependencies still contain tools that hit the legacy Windows
# MAX_PATH limit. A physically short cache can be supplied for release builds
# while keeping the repository and node_modules on one canonical filesystem root.
$configuredGradleUserHome = $env:GAME_PREDICTOR_GRADLE_USER_HOME
if ($configuredGradleUserHome) {
    if ([System.IO.Path]::IsPathRooted($configuredGradleUserHome)) {
        $env:GRADLE_USER_HOME = [System.IO.Path]::GetFullPath($configuredGradleUserHome)
    }
    else {
        $env:GRADLE_USER_HOME = [System.IO.Path]::GetFullPath(
            (Join-Path $repositoryRoot $configuredGradleUserHome)
        )
    }
}
else {
    $env:GRADLE_USER_HOME = Join-Path $repositoryRoot '.g'
}
$env:CI = '1'
$env:NODE_ENV = 'development'
$env:GAME_PREDICTOR_VERSION_NAME = $VersionName
$env:GAME_PREDICTOR_VERSION_CODE = [string]$VersionCode
$env:PATH = (Join-Path $javaHome 'bin') + ';' + (Join-Path $androidSdkRoot 'platform-tools') + ';' + $env:PATH

$buildStopwatch = [System.Diagnostics.Stopwatch]::StartNew()

Push-Location $mobileRoot
try {
    $expoCommand = Join-Path $repositoryRoot 'node_modules\.bin\expo.cmd'
    if (-not (Test-Path -LiteralPath $expoCommand)) {
        throw 'Expo CLI was not found. Run npm install from the repository root.'
    }

    if ($Variant -eq 'Release') {
        & (Join-Path $PSScriptRoot 'ensure_android_release_signing.ps1')
        if ($LASTEXITCODE -ne 0) {
            throw "Release signing setup failed with exit code $LASTEXITCODE."
        }
    }

    & $expoCommand prebuild --clean --platform android --no-install
    if ($LASTEXITCODE -ne 0) {
        throw "Expo prebuild failed with exit code $LASTEXITCODE."
    }

    Push-Location (Join-Path $mobileRoot 'android')
    try {
        $gradleTask = "assemble$Variant"
        & .\gradlew.bat `
            --no-daemon `
            --no-watch-fs `
            --max-workers=1 `
            '-Dkotlin.compiler.execution.strategy=in-process' `
            $gradleTask `
            "-PreactNativeArchitectures=$Architectures"
        if ($LASTEXITCODE -ne 0) {
            throw "Gradle $Variant build failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    Pop-Location
}

$variantName = $Variant.ToLowerInvariant()
$apkPath = Join-Path $mobileRoot "android\app\build\outputs\apk\$variantName\app-$variantName.apk"
if (-not (Test-Path -LiteralPath $apkPath)) {
    throw "Gradle reported success but the APK was not found at $apkPath."
}

$apk = Get-Item -LiteralPath $apkPath
$apkSha256 = (Get-FileHash -LiteralPath $apkPath -Algorithm SHA256).Hash.ToLowerInvariant()
$buildStopwatch.Stop()
Write-Host "Built $variantName APK for ${Architectures}: $($apk.FullName)"
Write-Host "Version: $VersionName ($VersionCode)"
Write-Host "APK size: $($apk.Length) bytes"
Write-Host "APK SHA-256: $apkSha256"
Write-Host "Build elapsed: $([math]::Round($buildStopwatch.Elapsed.TotalSeconds, 2)) seconds"
