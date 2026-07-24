[CmdletBinding()]
param(
    [switch]$AcceptAndroidSdkLicenses
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not $AcceptAndroidSdkLicenses) {
    throw 'Android SDK licenses were not accepted. Re-run with -AcceptAndroidSdkLicenses after reviewing the Google Android SDK License Agreement.'
}

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$toolingRoot = Join-Path $repositoryRoot '.tooling'
$downloadsRoot = Join-Path $toolingRoot 'downloads'
$jdkRoot = Join-Path $toolingRoot 'jdk'
$androidSdkRoot = Join-Path $toolingRoot 'android-sdk'

New-Item -ItemType Directory -Force -Path $downloadsRoot, $jdkRoot, $androidSdkRoot | Out-Null

function Get-VerifiedDownload {
    param(
        [Parameter(Mandatory)]
        [string]$Uri,
        [Parameter(Mandatory)]
        [string]$Destination,
        [Parameter(Mandatory)]
        [string]$ExpectedSha256
    )

    if (Test-Path -LiteralPath $Destination) {
        $existingSha256 = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($existingSha256 -ne $ExpectedSha256.ToLowerInvariant()) {
            Remove-Item -LiteralPath $Destination -Force
        }
    }

    if (-not (Test-Path -LiteralPath $Destination)) {
        Invoke-WebRequest -UseBasicParsing -Uri $Uri -OutFile $Destination
    }

    $actualSha256 = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualSha256 -ne $ExpectedSha256.ToLowerInvariant()) {
        throw "Checksum mismatch for $Destination. Expected $ExpectedSha256, got $actualSha256."
    }
}

$jdkArchive = Join-Path $downloadsRoot 'microsoft-jdk-17.0.20-windows-x64.zip'
$jdkChecksumFile = Join-Path $downloadsRoot 'microsoft-jdk-17.0.20-windows-x64.zip.sha256sum.txt'
$jdkDownloadUri = 'https://aka.ms/download-jdk/microsoft-jdk-17.0.20-windows-x64.zip'
$jdkChecksumUri = 'https://aka.ms/download-jdk/microsoft-jdk-17.0.20-windows-x64.zip.sha256sum.txt'

if (-not (Test-Path -LiteralPath $jdkChecksumFile)) {
    Invoke-WebRequest -UseBasicParsing -Uri $jdkChecksumUri -OutFile $jdkChecksumFile
}
$jdkExpectedSha256 = ((Get-Content -LiteralPath $jdkChecksumFile -Raw).Trim() -split '\s+')[0]
Get-VerifiedDownload -Uri $jdkDownloadUri -Destination $jdkArchive -ExpectedSha256 $jdkExpectedSha256

$jdkHome = Get-ChildItem -LiteralPath $jdkRoot -Directory |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'bin\java.exe') } |
    Select-Object -First 1 -ExpandProperty FullName

if (-not $jdkHome) {
    Expand-Archive -LiteralPath $jdkArchive -DestinationPath $jdkRoot
    $jdkHome = Get-ChildItem -LiteralPath $jdkRoot -Directory |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'bin\java.exe') } |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $jdkHome) {
    throw 'The downloaded JDK archive did not contain bin\java.exe.'
}

$commandLineToolsVersion = '15859902'
$commandLineToolsArchive = Join-Path $downloadsRoot "commandlinetools-win-$commandLineToolsVersion`_latest.zip"
$commandLineToolsUri = "https://dl.google.com/android/repository/commandlinetools-win-$commandLineToolsVersion`_latest.zip"
$commandLineToolsSha256 = '90ae805d20434428bffcb699c290860f19bb5f66a67e6b330067e3de801fb04a'
Get-VerifiedDownload -Uri $commandLineToolsUri -Destination $commandLineToolsArchive -ExpectedSha256 $commandLineToolsSha256

$commandLineToolsRoot = Join-Path $androidSdkRoot 'cmdline-tools'
$latestToolsRoot = Join-Path $commandLineToolsRoot 'latest'
$sdkManager = Join-Path $latestToolsRoot 'bin\sdkmanager.bat'

if (-not (Test-Path -LiteralPath $sdkManager)) {
    $stagingRoot = Join-Path $toolingRoot 'android-commandline-staging'
    if (Test-Path -LiteralPath $stagingRoot) {
        $resolvedStagingRoot = [System.IO.Path]::GetFullPath($stagingRoot)
        if (-not $resolvedStagingRoot.StartsWith($toolingRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw 'Android command-line staging directory escaped .tooling.'
        }
        Remove-Item -LiteralPath $resolvedStagingRoot -Recurse -Force
    }

    Expand-Archive -LiteralPath $commandLineToolsArchive -DestinationPath $stagingRoot
    New-Item -ItemType Directory -Force -Path $commandLineToolsRoot | Out-Null
    Move-Item -LiteralPath (Join-Path $stagingRoot 'cmdline-tools') -Destination $latestToolsRoot
    Remove-Item -LiteralPath $stagingRoot -Force
}

$env:JAVA_HOME = $jdkHome
$env:ANDROID_HOME = $androidSdkRoot
$env:ANDROID_SDK_ROOT = $androidSdkRoot
$env:PATH = (Join-Path $jdkHome 'bin') + ';' + (Join-Path $androidSdkRoot 'platform-tools') + ';' + $env:PATH

$licenseAnswers = 1..20 | ForEach-Object { 'y' }
$licenseAnswers | & $sdkManager "--sdk_root=$androidSdkRoot" --licenses
if ($LASTEXITCODE -ne 0) {
    throw "sdkmanager --licenses failed with exit code $LASTEXITCODE."
}

& $sdkManager `
    "--sdk_root=$androidSdkRoot" `
    'platform-tools' `
    'platforms;android-36' `
    'build-tools;36.0.0'
if ($LASTEXITCODE -ne 0) {
    throw "Android SDK package installation failed with exit code $LASTEXITCODE."
}

Write-Host "JDK home: $jdkHome"
Write-Host "Android SDK: $androidSdkRoot"
& (Join-Path $jdkHome 'bin\java.exe') -version
& (Join-Path $androidSdkRoot 'platform-tools\adb.exe') version
