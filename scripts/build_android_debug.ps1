[CmdletBinding()]
param(
    [ValidateSet('Debug', 'Release')]
    [string]$Variant = 'Debug',

    [ValidatePattern('^[a-z0-9_,-]+$')]
    [string]$Architectures = 'arm64-v8a',

    [ValidatePattern('^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$')]
    [string]$VersionName = '0.1.0',

    [ValidateRange(1, 2100000000)]
    [int]$VersionCode = 1,

    [switch]$CleanNativeProject,

    [ValidateRange(60, 1800)]
    [int]$PrebuildTimeoutSeconds = 300,

    [ValidateRange(120, 3600)]
    [int]$GradleTimeoutSeconds = 1800,

    [ValidateRange(1, 8)]
    [int]$NativeBuildParallelism = 2
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Invoke-BoundedProcess {
    param(
        [Parameter(Mandatory)]
        [string]$FilePath,

        [string[]]$ArgumentList = @(),

        [Parameter(Mandatory)]
        [string]$WorkingDirectory,

        [Parameter(Mandatory)]
        [ValidateRange(1, 3600)]
        [int]$TimeoutSeconds,

        [Parameter(Mandatory)]
        [string]$Description
    )

    $quotedArguments = foreach ($argument in $ArgumentList) {
        if ($argument.Contains('"')) {
            throw "$Description contains an unsupported double quote in an argument."
        }
        if ($argument -match '\s') {
            '"' + $argument + '"'
        }
        else {
            $argument
        }
    }
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $env:ComSpec
    $startInfo.Arguments = (
        '/d /s /c ""' +
        $FilePath +
        '" ' +
        ($quotedArguments -join ' ') +
        '"'
    )
    $startInfo.WorkingDirectory = $WorkingDirectory
    $startInfo.UseShellExecute = $false
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    try {
        if (-not $process.Start()) {
            throw "$Description could not be started."
        }
        $completed = $process.WaitForExit([int]($TimeoutSeconds * 1000))
        if (-not $completed) {
            $taskKill = Join-Path $env:SystemRoot 'System32\taskkill.exe'
            & $taskKill /PID $process.Id /T /F | Out-Null
            $process.WaitForExit(5000) | Out-Null
            throw (
                "$Description timed out after $TimeoutSeconds seconds. " +
                "The complete process tree was terminated."
            )
        }
        $process.WaitForExit()
        if ($process.ExitCode -ne 0) {
            throw "$Description failed with exit code $($process.ExitCode)."
        }
    }
    finally {
        $process.Dispose()
    }
}

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$mobileRoot = Join-Path $repositoryRoot 'apps\mobile'
$localToolingRoot = Join-Path $repositoryRoot '.tooling'
$localJdkRoot = Join-Path $localToolingRoot 'jdk'
$localAndroidSdkRoot = Join-Path $localToolingRoot 'android-sdk'
$localNodeRoot = Join-Path $localToolingRoot 'node'

$nodeExecutable = Get-Command 'node.exe' -ErrorAction SilentlyContinue |
    Select-Object -First 1 -ExpandProperty Source
if (-not $nodeExecutable) {
    $nodeCandidates = @()
    if ($env:GAME_PREDICTOR_NODE_HOME) {
        $nodeCandidates += Join-Path $env:GAME_PREDICTOR_NODE_HOME 'node.exe'
    }
    $nodeCandidates += Join-Path $localNodeRoot 'node.exe'
    if ($env:USERPROFILE) {
        $nodeCandidates += Join-Path `
            $env:USERPROFILE `
            '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
    }
    if ($env:ProgramFiles) {
        $nodeCandidates += Join-Path $env:ProgramFiles 'nodejs\node.exe'
    }

    $nodeExecutable = $nodeCandidates |
        Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
        Select-Object -First 1
}
if (-not $nodeExecutable) {
    throw 'Node.js was not found. Install Node.js 22 LTS, configure GAME_PREDICTOR_NODE_HOME, or place node.exe in .tooling\node.'
}
$nodeDirectory = Split-Path -Parent $nodeExecutable

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
    $shortGradleRoot = Join-Path $env:SystemDrive 'gpg'
    if (Test-Path -LiteralPath $shortGradleRoot -PathType Container) {
        $env:GRADLE_USER_HOME = $shortGradleRoot
    }
    else {
        $env:GRADLE_USER_HOME = Join-Path $repositoryRoot '.g'
    }
}
$env:CI = '1'
$env:NODE_ENV = 'development'
$env:CMAKE_BUILD_PARALLEL_LEVEL = [string]$NativeBuildParallelism
$env:GAME_PREDICTOR_VERSION_NAME = $VersionName
$env:GAME_PREDICTOR_VERSION_CODE = [string]$VersionCode
$env:PATH = $nodeDirectory + ';' + (Join-Path $javaHome 'bin') + ';' + (Join-Path $androidSdkRoot 'platform-tools') + ';' + $env:PATH

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

    $prebuildArguments = @('prebuild', '--platform', 'android', '--no-install')
    if (-not $CleanNativeProject) {
        $prebuildArguments += '--no-clean'
    }
    Invoke-BoundedProcess `
        -FilePath $expoCommand `
        -ArgumentList $prebuildArguments `
        -WorkingDirectory $mobileRoot `
        -TimeoutSeconds $PrebuildTimeoutSeconds `
        -Description 'Expo prebuild'

    if ($Variant -eq 'Release' -and $CleanNativeProject) {
        $nodeModulesRoot = [System.IO.Path]::GetFullPath(
            (Join-Path $repositoryRoot 'node_modules')
        )
        $nodeModulesPrefix = $nodeModulesRoot.TrimEnd(
            [System.IO.Path]::DirectorySeparatorChar
        ) + [System.IO.Path]::DirectorySeparatorChar
        $nativeCaches = @(
            Get-ChildItem `
                -LiteralPath $nodeModulesRoot `
                -Directory `
                -Filter '.cxx' `
                -Recurse `
                -Force `
                -ErrorAction SilentlyContinue
        )
        foreach ($nativeCache in $nativeCaches) {
            $resolvedNativeCache = [System.IO.Path]::GetFullPath($nativeCache.FullName)
            if (-not $resolvedNativeCache.StartsWith(
                $nodeModulesPrefix,
                [System.StringComparison]::OrdinalIgnoreCase
            )) {
                throw "Refusing to remove native cache outside node_modules: $resolvedNativeCache"
            }
            Remove-Item -LiteralPath $resolvedNativeCache -Recurse -Force
        }
        Write-Host "Removed $($nativeCaches.Count) generated native .cxx cache(s)."
    }

    Push-Location (Join-Path $mobileRoot 'android')
    try {
        $gradleTask = ":app:assemble$Variant"
        $gradleArguments = @(
            '--no-daemon',
            '--no-parallel',
            '--no-watch-fs',
            '--max-workers=1',
            '-Pkotlin.compiler.execution.strategy=in-process'
        )
        if ($CleanNativeProject) {
            $gradleArguments += 'clean'
        }
        $gradleArguments += @(
            $gradleTask,
            "-PreactNativeArchitectures=$Architectures"
        )
        Invoke-BoundedProcess `
            -FilePath (Join-Path (Get-Location) 'gradlew.bat') `
            -ArgumentList $gradleArguments `
            -WorkingDirectory (Get-Location) `
            -TimeoutSeconds $GradleTimeoutSeconds `
            -Description "Gradle $Variant build"
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
