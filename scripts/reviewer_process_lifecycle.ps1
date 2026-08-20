Set-StrictMode -Version Latest

function Get-ReviewerLifecycleMutexName {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $normalizedRoot = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\').ToLowerInvariant()
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $digest = $sha256.ComputeHash([Text.Encoding]::UTF8.GetBytes($normalizedRoot))
    }
    finally {
        $sha256.Dispose()
    }
    $identity = ([BitConverter]::ToString($digest)).Replace('-', '').Substring(0, 24)
    return "Local\GamePredictor.ReviewerLifecycle.$identity"
}

function Enter-ReviewerLifecycleLock {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [ValidateRange(1, 60000)]
        [int]$TimeoutMilliseconds
    )

    $mutexName = Get-ReviewerLifecycleMutexName -ProjectRoot $ProjectRoot
    $createdNew = $false
    $mutex = [Threading.Mutex]::new($false, $mutexName, [ref]$createdNew)
    $acquired = $false
    try {
        try {
            $acquired = $mutex.WaitOne($TimeoutMilliseconds)
        }
        catch [Threading.AbandonedMutexException] {
            $acquired = $true
        }
        if (-not $acquired) {
            throw "Reviewer lifecycle is busy in another Windows process. Retry the operation."
        }
        return $mutex
    }
    catch {
        if (-not $acquired) {
            $mutex.Dispose()
        }
        throw
    }
}

function Exit-ReviewerLifecycleLock {
    param(
        [Parameter(Mandatory = $true)]
        [Threading.Mutex]$Mutex
    )

    try {
        $Mutex.ReleaseMutex()
    }
    finally {
        $Mutex.Dispose()
    }
}

function Write-ReviewerAtomicJson {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LiteralPath,
        [Parameter(Mandatory = $true)]
        [object]$Value
    )

    $directory = Split-Path -Parent $LiteralPath
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $temporaryPath = Join-Path $directory (
        ".{0}.{1}.tmp" -f ([IO.Path]::GetFileName($LiteralPath)), ([Guid]::NewGuid().ToString('N'))
    )
    try {
        [IO.File]::WriteAllText(
            $temporaryPath,
            ($Value | ConvertTo-Json -Depth 8),
            [Text.UTF8Encoding]::new($false)
        )
        if (Test-Path -LiteralPath $LiteralPath -PathType Leaf) {
            [IO.File]::Replace($temporaryPath, $LiteralPath, $null, $true)
        }
        else {
            [IO.File]::Move($temporaryPath, $LiteralPath)
        }
    }
    finally {
        if (Test-Path -LiteralPath $temporaryPath -PathType Leaf) {
            Remove-Item -LiteralPath $temporaryPath -Force
        }
    }
}

function Read-ReviewerJsonState {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LiteralPath
    )

    if (-not (Test-Path -LiteralPath $LiteralPath -PathType Leaf)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $LiteralPath -Raw -Encoding utf8 | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function New-ReviewerProcessIdentity {
    param(
        [Parameter(Mandatory = $true)]
        [Diagnostics.Process]$Process,
        [Parameter(Mandatory = $true)]
        [Guid]$InstanceId
    )

    $Process.Refresh()
    $executablePath = $Process.Path
    if ([string]::IsNullOrWhiteSpace($executablePath)) {
        throw "Cannot determine the executable path for PID $($Process.Id)."
    }
    return [ordered]@{
        instanceId = $InstanceId.ToString('D')
        pid = $Process.Id
        processStartedAt = $Process.StartTime.ToUniversalTime().ToString('o')
        executablePath = [IO.Path]::GetFullPath($executablePath)
        processName = $Process.ProcessName
    }
}

function Test-ReviewerProcessIdentity {
    param(
        [Parameter(Mandatory = $true)]
        [object]$State,
        [string]$ExpectedProcessName = ""
    )

    try {
        $instanceId = [Guid]::Parse([string]$State.instanceId)
        if ($instanceId -eq [Guid]::Empty) {
            throw "Empty instance id."
        }
        $expectedPid = [int]$State.pid
        $expectedStartedAt = [DateTimeOffset]::Parse([string]$State.processStartedAt)
        $expectedExecutable = [IO.Path]::GetFullPath([string]$State.executablePath)
        $process = Get-Process -Id $expectedPid -ErrorAction SilentlyContinue
        if ($null -eq $process) {
            return [pscustomobject]@{ isMatch = $false; process = $null; reason = "missing" }
        }
        $process.Refresh()
        if (
            -not [string]::IsNullOrWhiteSpace($ExpectedProcessName) -and
            $process.ProcessName -notlike $ExpectedProcessName
        ) {
            return [pscustomobject]@{ isMatch = $false; process = $process; reason = "name" }
        }
        if ($process.StartTime.ToUniversalTime().Ticks -ne $expectedStartedAt.UtcDateTime.Ticks) {
            return [pscustomobject]@{ isMatch = $false; process = $process; reason = "start-time" }
        }
        $actualExecutable = [IO.Path]::GetFullPath($process.Path)
        if (-not $actualExecutable.Equals($expectedExecutable, [StringComparison]::OrdinalIgnoreCase)) {
            return [pscustomobject]@{ isMatch = $false; process = $process; reason = "executable" }
        }
        return [pscustomobject]@{ isMatch = $true; process = $process; reason = "matched" }
    }
    catch {
        return [pscustomobject]@{ isMatch = $false; process = $null; reason = "invalid-state" }
    }
}

function New-ReviewerAttemptPaths {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RuntimeDirectory,
        [Parameter(Mandatory = $true)]
        [ValidatePattern('^[a-z0-9-]+$')]
        [string]$Prefix,
        [Parameter(Mandatory = $true)]
        [Guid]$InstanceId,
        [ValidateRange(0, 99)]
        [int]$Attempt = 0
    )

    $logDirectory = Join-Path $RuntimeDirectory "reviewer-lifecycle-logs"
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    $stem = "{0}-{1}-{2:D2}" -f $Prefix, $InstanceId.ToString('N'), $Attempt
    return [pscustomobject]@{
        out = Join-Path $logDirectory "$stem.out.log"
        error = Join-Path $logDirectory "$stem.error.log"
        process = Join-Path $logDirectory "$stem.process.log"
    }
}
