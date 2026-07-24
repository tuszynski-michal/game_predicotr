[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$signingRoot = Join-Path $repositoryRoot '.tooling\android-signing'
$keystorePath = Join-Path $signingRoot 'game-predictor-release.jks'
$propertiesPath = Join-Path $signingRoot 'release-signing.json'
$localJdkRoot = Join-Path $repositoryRoot '.tooling\jdk'

$javaHome = $env:JAVA_HOME
if (-not $javaHome -and (Test-Path -LiteralPath $localJdkRoot)) {
    $javaHome = Get-ChildItem -LiteralPath $localJdkRoot -Directory |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'bin\keytool.exe') } |
        Select-Object -First 1 -ExpandProperty FullName
}
$keytoolPath = if ($javaHome) { Join-Path $javaHome 'bin\keytool.exe' } else { $null }
if (-not $keytoolPath -or -not (Test-Path -LiteralPath $keytoolPath)) {
    throw 'JDK keytool was not found. Run npm run android:toolchain:setup or configure JAVA_HOME.'
}

function New-SigningSecret {
    $bytes = [byte[]]::new(32)
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

$keystoreExists = Test-Path -LiteralPath $keystorePath
$propertiesExist = Test-Path -LiteralPath $propertiesPath
if ($keystoreExists -xor $propertiesExist) {
    throw 'Release signing state is incomplete. Restore both the keystore and release-signing.json from backup.'
}

if (-not $keystoreExists) {
    New-Item -ItemType Directory -Force -Path $signingRoot | Out-Null
    $secret = New-SigningSecret
    $signing = [ordered]@{
        keyAlias = 'game-predictor-release'
        keyPassword = $secret
        storePassword = $secret
    }

    & $keytoolPath `
        -genkeypair `
        -keystore $keystorePath `
        -storetype JKS `
        -storepass $signing.storePassword `
        -alias $signing.keyAlias `
        -keypass $signing.keyPassword `
        -keyalg RSA `
        -keysize 4096 `
        -validity 10000 `
        -dname 'CN=Game Predictor Private Release, OU=Private Testing, O=Local, C=PL' `
        -noprompt
    if ($LASTEXITCODE -ne 0) {
        throw "keytool failed with exit code $LASTEXITCODE."
    }

    $signing | ConvertTo-Json | Set-Content -LiteralPath $propertiesPath -Encoding utf8
}

$signingConfig = Get-Content -LiteralPath $propertiesPath -Raw -Encoding utf8 |
    ConvertFrom-Json
foreach ($requiredProperty in 'keyAlias', 'keyPassword', 'storePassword') {
    if (-not $signingConfig.$requiredProperty) {
        throw "Release signing configuration is missing $requiredProperty."
    }
}

& $keytoolPath `
    -list `
    -keystore $keystorePath `
    -storepass $signingConfig.storePassword `
    -alias $signingConfig.keyAlias | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Existing release signing key could not be opened.'
}

$env:GAME_PREDICTOR_RELEASE_STORE_FILE = $keystorePath
$env:GAME_PREDICTOR_RELEASE_STORE_PASSWORD = [string]$signingConfig.storePassword
$env:GAME_PREDICTOR_RELEASE_KEY_ALIAS = [string]$signingConfig.keyAlias
$env:GAME_PREDICTOR_RELEASE_KEY_PASSWORD = [string]$signingConfig.keyPassword

Write-Host "Release signing key ready: $keystorePath"
Write-Host 'Back up the complete .tooling\android-signing directory outside the repository.'
