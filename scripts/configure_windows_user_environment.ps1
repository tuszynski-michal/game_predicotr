[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$ConfigurePowerShellExecutionPolicy
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$processEnvironmentScript = Join-Path $PSScriptRoot 'windows_process_environment.ps1'
if (-not (Test-Path -LiteralPath $processEnvironmentScript -PathType Leaf)) {
    throw "Windows process environment helper is unavailable: $processEnvironmentScript"
}
. $processEnvironmentScript
Repair-WindowsProcessPath

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$nodeRoot = Join-Path $repositoryRoot '.tooling\node'
$jdkHome = Get-ChildItem -LiteralPath (Join-Path $repositoryRoot '.tooling\jdk') -Directory |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'bin\java.exe') } |
    Select-Object -First 1 -ExpandProperty FullName
$androidSdkRoot = Join-Path $repositoryRoot '.tooling\android-sdk'
$gradleUserHome = if (Test-Path -LiteralPath 'C:\gpg' -PathType Container) {
    'C:\gpg'
}
else {
    Join-Path $repositoryRoot '.tooling\gradle-home'
}
$dockerBin = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin'

$requiredFiles = [ordered]@{
    Node = Join-Path $nodeRoot 'node.exe'
    Npm = Join-Path $nodeRoot 'npm.cmd'
    Java = if ($jdkHome) { Join-Path $jdkHome 'bin\java.exe' } else { '' }
    Adb = Join-Path $androidSdkRoot 'platform-tools\adb.exe'
    SdkManager = Join-Path $androidSdkRoot 'cmdline-tools\latest\bin\sdkmanager.bat'
}

foreach ($entry in $requiredFiles.GetEnumerator()) {
    if (-not $entry.Value -or -not (Test-Path -LiteralPath $entry.Value -PathType Leaf)) {
        throw "$($entry.Key) was not found at '$($entry.Value)'. Restore the local toolchain before configuring the user environment."
    }
}

$nodeVersion = & $requiredFiles.Node --version
$npmVersion = & $requiredFiles.Npm --version
$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$javaVersion = & $requiredFiles.Java -version 2>&1 | Select-Object -First 1
$ErrorActionPreference = $previousErrorActionPreference
$adbVersion = & $requiredFiles.Adb version | Select-Object -First 1

if ($nodeVersion -notmatch '^v(22|23|24)\.') {
    throw "Node.js $nodeVersion does not satisfy the repository range >=22.13 <25."
}
if ($npmVersion -notmatch '^11\.') {
    throw "npm $npmVersion does not satisfy the repository range >=11 <12."
}

$pathEntries = @(
    $nodeRoot,
    (Join-Path $jdkHome 'bin'),
    (Join-Path $androidSdkRoot 'platform-tools'),
    (Join-Path $androidSdkRoot 'cmdline-tools\latest\bin')
)
if (Test-Path -LiteralPath (Join-Path $dockerBin 'docker.exe') -PathType Leaf) {
    $pathEntries += $dockerBin
}

$variables = [ordered]@{
    GAME_PREDICTOR_NODE_HOME = $nodeRoot
    JAVA_HOME = $jdkHome
    ANDROID_HOME = $androidSdkRoot
    ANDROID_SDK_ROOT = $androidSdkRoot
    GAME_PREDICTOR_GRADLE_USER_HOME = $gradleUserHome
}

if ($CheckOnly) {
    foreach ($entry in $variables.GetEnumerator()) {
        $persistedValue = [Environment]::GetEnvironmentVariable(
            $entry.Key,
            'User'
        )
        if ($persistedValue -ine $entry.Value) {
            throw (
                "User environment variable $($entry.Key) is not persisted. " +
                "Run npm run windows:environment:setup."
            )
        }
    }

    $persistedUserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $persistedPathEntries = @($persistedUserPath -split ';') |
        Where-Object { $_ } |
        ForEach-Object { $_.Trim().TrimEnd('\') }
    foreach ($requiredPathEntry in $pathEntries) {
        $normalizedRequiredEntry = $requiredPathEntry.TrimEnd('\')
        if (-not ($persistedPathEntries | Where-Object {
                    $_ -ieq $normalizedRequiredEntry
                })) {
            throw (
                "User PATH does not persist '$requiredPathEntry'. " +
                "Run npm run windows:environment:setup."
            )
        }
    }
}

if (-not $CheckOnly) {
    if ($ConfigurePowerShellExecutionPolicy) {
        if ((Get-ExecutionPolicy -Scope CurrentUser) -ne 'RemoteSigned') {
            $previousPolicyErrorActionPreference = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
            $ErrorActionPreference = $previousPolicyErrorActionPreference
        }
        if ((Get-ExecutionPolicy -Scope CurrentUser) -ne 'RemoteSigned') {
            throw 'PowerShell CurrentUser execution policy was not set to RemoteSigned.'
        }
        foreach ($scriptName in @('npm.ps1', 'npx.ps1', 'corepack.ps1')) {
            $scriptPath = Join-Path $nodeRoot $scriptName
            if (Test-Path -LiteralPath $scriptPath -PathType Leaf) {
                Unblock-File -LiteralPath $scriptPath
            }
        }
    }

    foreach ($entry in $variables.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'User')
        Set-Item -Path "Env:$($entry.Key)" -Value $entry.Value
    }

    $existingUserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $mergedPath = [System.Collections.Generic.List[string]]::new()
    foreach ($entry in $pathEntries + ($existingUserPath -split ';')) {
        $candidate = $entry.Trim()
        if (-not $candidate) {
            continue
        }
        if (-not ($mergedPath | Where-Object {
                    $_.TrimEnd('\') -ieq $candidate.TrimEnd('\')
                })) {
            $mergedPath.Add($candidate)
        }
    }
    $persistedPath = ($mergedPath -join ';') + ';'
    [Environment]::SetEnvironmentVariable('Path', $persistedPath, 'User')
    Repair-WindowsProcessPath -PreferredEntries $pathEntries

    Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class EnvironmentBroadcast {
    [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    public static extern IntPtr SendMessageTimeout(
        IntPtr hWnd,
        uint Msg,
        UIntPtr wParam,
        string lParam,
        uint fuFlags,
        uint uTimeout,
        out UIntPtr lpdwResult);
}
'@
    $broadcastResult = [UIntPtr]::Zero
    [void][EnvironmentBroadcast]::SendMessageTimeout(
        [IntPtr]0xffff,
        0x001A,
        [UIntPtr]::Zero,
        'Environment',
        0x0002,
        5000,
        [ref]$broadcastResult
    )
}

[pscustomobject]@{
    Mode = if ($CheckOnly) { 'check-only' } else { 'persisted for current user' }
    Node = $nodeVersion
    Npm = $npmVersion
    Java = $javaVersion
    Adb = $adbVersion
    NodeHome = $nodeRoot
    JavaHome = $jdkHome
    AndroidHome = $androidSdkRoot
    GradleUserHome = $gradleUserHome
    DockerCliAdded = Test-Path -LiteralPath (Join-Path $dockerBin 'docker.exe')
    PowerShellPolicy = Get-ExecutionPolicy -Scope CurrentUser
} | Format-List
