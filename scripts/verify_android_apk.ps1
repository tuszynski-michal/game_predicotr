[CmdletBinding()]
param(
    [string]$ApkPath = 'apps\mobile\android\app\build\outputs\apk\release\app-release.apk',

    [string]$SnapshotManifestPath = 'apps\mobile\assets\snapshot\manifest.json'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$resolvedApkPath = [System.IO.Path]::GetFullPath((Join-Path $repositoryRoot $ApkPath))
$manifestPath = [System.IO.Path]::GetFullPath(
    (Join-Path $repositoryRoot $SnapshotManifestPath)
)
$aaptPath = Join-Path $repositoryRoot '.tooling\android-sdk\build-tools\36.0.0\aapt.exe'
$apksignerPath = Join-Path $repositoryRoot '.tooling\android-sdk\build-tools\36.0.0\apksigner.bat'
$localJdkRoot = Join-Path $repositoryRoot '.tooling\jdk'

if (-not (Test-Path -LiteralPath $resolvedApkPath)) {
    throw "APK not found at $resolvedApkPath."
}
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Snapshot manifest not found at $manifestPath."
}
if (-not (Test-Path -LiteralPath $aaptPath)) {
    throw 'Android Asset Packaging Tool was not found. Run npm run android:toolchain:setup.'
}
if (-not (Test-Path -LiteralPath $apksignerPath)) {
    throw 'Android APK signer was not found. Run npm run android:toolchain:setup.'
}

$javaHome = $env:JAVA_HOME
if (-not $javaHome -and (Test-Path -LiteralPath $localJdkRoot)) {
    $javaHome = Get-ChildItem -LiteralPath $localJdkRoot -Directory |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'bin\java.exe') } |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $javaHome -or -not (Test-Path -LiteralPath (Join-Path $javaHome 'bin\java.exe'))) {
    throw 'JDK 17 was not found. Run npm run android:toolchain:setup or configure JAVA_HOME.'
}
$env:JAVA_HOME = $javaHome
$env:PATH = (Join-Path $javaHome 'bin') + ';' + $env:PATH

$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($resolvedApkPath)
try {
    $bundleEntry = $archive.GetEntry('assets/index.android.bundle')
    if ($null -eq $bundleEntry) {
        throw 'The standalone JavaScript bundle is missing from the APK.'
    }

    $bundleReader = [System.IO.StreamReader]::new(
        $bundleEntry.Open(),
        [System.Text.Encoding]::UTF8
    )
    try {
        $bundleText = $bundleReader.ReadToEnd()
    }
    finally {
        $bundleReader.Dispose()
    }

    if (-not $bundleText.Contains([string]$manifest.releaseVersion)) {
        throw 'The JavaScript bundle does not contain the expected snapshot release version.'
    }
    if (-not $bundleText.Contains([string]$manifest.snapshotFileSha256)) {
        throw 'The JavaScript bundle does not contain the expected snapshot checksum.'
    }
    if (-not $bundleText.Contains('local_data_error')) {
        throw 'The JavaScript bundle does not contain the controlled local data error code.'
    }

    $matchingDatabaseEntry = $null
    foreach ($databaseEntry in $archive.Entries | Where-Object { $_.FullName.EndsWith('.db') }) {
        $sha256 = [System.Security.Cryptography.SHA256]::Create()
        try {
            $databaseStream = $databaseEntry.Open()
            try {
                $hashBytes = $sha256.ComputeHash($databaseStream)
            }
            finally {
                $databaseStream.Dispose()
            }
        }
        finally {
            $sha256.Dispose()
        }

        $entryHash = [System.BitConverter]::ToString($hashBytes).Replace('-', '').ToLowerInvariant()
        if ($entryHash -eq [string]$manifest.snapshotFileSha256) {
            $matchingDatabaseEntry = $databaseEntry
            break
        }
    }

    if ($null -eq $matchingDatabaseEntry) {
        throw 'The APK does not contain the SQLite snapshot declared by the manifest.'
    }
}
finally {
    $archive.Dispose()
}

$badging = & $aaptPath dump badging $resolvedApkPath
if ($LASTEXITCODE -ne 0) {
    throw "aapt dump badging failed with exit code $LASTEXITCODE."
}

$badgingText = $badging -join "`n"
if ($badgingText -notmatch "package: name='com\.gamepredictor\.mobile'") {
    throw 'The APK has an unexpected Android applicationId.'
}
if ($badgingText -notmatch "native-code: 'arm64-v8a'") {
    throw 'The APK does not contain the required arm64-v8a native code.'
}
if ($badgingText.Contains('application-debuggable')) {
    throw 'The release APK is unexpectedly debuggable.'
}

$permissions = & $aaptPath dump permissions $resolvedApkPath
if ($LASTEXITCODE -ne 0) {
    throw "aapt dump permissions failed with exit code $LASTEXITCODE."
}
$hasInternetPermission = ($permissions -join "`n").Contains('android.permission.INTERNET')
if ($hasInternetPermission) {
    throw 'The release APK declares android.permission.INTERNET.'
}

$signatureVerification = & $apksignerPath verify --verbose --print-certs $resolvedApkPath
if ($LASTEXITCODE -ne 0) {
    throw "apksigner verification failed with exit code $LASTEXITCODE."
}
$signatureText = $signatureVerification -join "`n"
if ($signatureText.Contains('CN=Android Debug')) {
    throw 'The release APK is signed with the Android Debug certificate.'
}
if (-not $signatureText.Contains('CN=Game Predictor Private Release')) {
    throw 'The release APK does not use the expected private release certificate.'
}

$apk = Get-Item -LiteralPath $resolvedApkPath
$apkSha256 = (Get-FileHash -LiteralPath $resolvedApkPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "Verified standalone APK: $($apk.FullName)"
Write-Host "APK size: $($apk.Length) bytes"
Write-Host "APK SHA-256: $apkSha256"
Write-Host "Bundled SQLite: $($matchingDatabaseEntry.FullName)"
Write-Host "Bundled SQLite SHA-256: $($manifest.snapshotFileSha256)"
Write-Host "Internet permission declared: $hasInternetPermission"
Write-Host ($badging | Where-Object { $_ -match "^package:" } | Select-Object -First 1)
Write-Host ($signatureVerification | Where-Object { $_ -match 'certificate DN:' } | Select-Object -First 1)
