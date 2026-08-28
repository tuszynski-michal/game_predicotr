[CmdletBinding()]
param(
    [ValidateSet('Start', 'Status', 'Stop')]
    [string]$Action = 'Status',

    [ValidateSet('all', 'general', 'image-selection')]
    [string]$Lane = 'all',

    [switch]$Json,

    [ValidateRange(1, 64)]
    [int]$GeneralThreadBudget = 2,

    [ValidateRange(1, 64)]
    [int]$ImageSelectionThreadBudget = 5,

    [ValidateRange(1, 30)]
    [int]$TimeoutSeconds = 10
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($null -eq ('WorkerProcessTree' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public static class WorkerProcessTree
{
    private const uint TH32CS_SNAPPROCESS = 0x00000002;
    private static readonly IntPtr InvalidHandleValue = new IntPtr(-1);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct PROCESSENTRY32
    {
        public uint dwSize;
        public uint cntUsage;
        public uint th32ProcessID;
        public IntPtr th32DefaultHeapID;
        public uint th32ModuleID;
        public uint cntThreads;
        public uint th32ParentProcessID;
        public int pcPriClassBase;
        public uint dwFlags;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)]
        public string szExeFile;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr CreateToolhelp32Snapshot(uint flags, uint processId);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool Process32FirstW(IntPtr snapshot, ref PROCESSENTRY32 entry);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool Process32NextW(IntPtr snapshot, ref PROCESSENTRY32 entry);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool CloseHandle(IntPtr handle);

    public static int[] Descendants(int rootProcessId)
    {
        var parentByProcess = new Dictionary<int, int>();
        IntPtr snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
        if (snapshot == InvalidHandleValue) {
            throw new InvalidOperationException("Unable to enumerate the Windows process tree.");
        }
        try {
            var entry = new PROCESSENTRY32();
            entry.dwSize = (uint)Marshal.SizeOf(typeof(PROCESSENTRY32));
            if (Process32FirstW(snapshot, ref entry)) {
                do {
                    parentByProcess[(int)entry.th32ProcessID] = (int)entry.th32ParentProcessID;
                    entry.dwSize = (uint)Marshal.SizeOf(typeof(PROCESSENTRY32));
                } while (Process32NextW(snapshot, ref entry));
            }
        }
        finally {
            CloseHandle(snapshot);
        }

        var result = new List<int>();
        var frontier = new Queue<int>();
        frontier.Enqueue(rootProcessId);
        while (frontier.Count > 0) {
            int parent = frontier.Dequeue();
            foreach (var pair in parentByProcess) {
                if (pair.Value == parent && !result.Contains(pair.Key)) {
                    result.Add(pair.Key);
                    frontier.Enqueue(pair.Key);
                }
            }
        }
        return result.ToArray();
    }
}
'@
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeDirectory = Join-Path $projectRoot '.runtime'
$statePath = Join-Path $runtimeDirectory 'worker-lanes.json'
$lockPath = Join-Path $runtimeDirectory 'worker-lanes.lock'
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$processEnvironmentScript = Join-Path $PSScriptRoot 'windows_process_environment.ps1'

if (-not (Test-Path -LiteralPath $processEnvironmentScript -PathType Leaf)) {
    throw "Windows process environment helper is unavailable: $processEnvironmentScript"
}
. $processEnvironmentScript
Repair-WindowsProcessPath

$laneDefinitions = [ordered]@{
    'general' = [ordered]@{
        argument = 'general'
        displayName = 'General worker'
        threadBudget = $GeneralThreadBudget
        nativeThreadBudget = 1
    }
    'image-selection' = [ordered]@{
        argument = 'image-selection'
        displayName = 'Image-selection worker'
        threadBudget = $ImageSelectionThreadBudget
        nativeThreadBudget = 1
    }
}

function Get-TargetLaneNames {
    if ($Lane -eq 'all') {
        return @($laneDefinitions.Keys)
    }
    return @($Lane)
}

function Enter-StateLock {
    New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null
    $attempts = [Math]::Max(1, $TimeoutSeconds * 4)
    for ($attempt = 0; $attempt -lt $attempts; $attempt++) {
        try {
            return [IO.File]::Open(
                $lockPath,
                [IO.FileMode]::OpenOrCreate,
                [IO.FileAccess]::ReadWrite,
                [IO.FileShare]::None
            )
        }
        catch [IO.IOException] {
            if ($attempt -eq ($attempts - 1)) {
                throw "Worker lane state is locked by another operation after $TimeoutSeconds seconds."
            }
            Start-Sleep -Milliseconds 250
        }
    }
}

function Read-State {
    if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
        return $null
    }

    try {
        $state = Get-Content -LiteralPath $statePath -Raw -Encoding utf8 |
            ConvertFrom-Json
    }
    catch {
        throw "Worker lane state is invalid: $statePath. No process was changed."
    }

    if ($state.schemaVersion -notin @(1, 2)) {
        throw "Unsupported worker lane state schema: $($state.schemaVersion)."
    }
    if ([string]$state.repositoryRoot -ine $projectRoot) {
        throw "Worker lane state belongs to another repository: $($state.repositoryRoot)."
    }
    return $state
}

function Test-ProcessIdentity {
    param(
        [AllowNull()]
        [object]$Identity
    )

    if ($null -eq $Identity) {
        return $null
    }
    $process = Get-Process -Id ([int]$Identity.pid) -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        return $null
    }
    try {
        $actualStart = $process.StartTime.ToUniversalTime().ToString('o')
    }
    catch {
        return $null
    }
    # ConvertFrom-Json materializes ISO 8601 values as DateTime on some
    # PowerShell versions. Casting that value back to string produces a
    # locale-specific timestamp (for example `08/19/2026 11:04:37`) and made a
    # healthy worker appear stale immediately after every script invocation.
    # Normalize either representation before comparing a process identity.
    $expectedStartValue = $Identity.startTimeUtc
    $expectedStart = if ($expectedStartValue -is [DateTime]) {
        $expectedStartValue.ToUniversalTime().ToString('o')
    }
    elseif ($expectedStartValue -is [DateTimeOffset]) {
        $expectedStartValue.UtcDateTime.ToString('o')
    }
    else {
        [string]$expectedStartValue
    }
    if (
        $process.ProcessName -ine [string]$Identity.processName -or
        $actualStart -ne $expectedStart
    ) {
        return $null
    }
    return $process
}

function Get-StateRecord {
    param(
        [AllowNull()]
        [object]$State,
        [Parameter(Mandatory = $true)]
        [string]$LaneName
    )

    if ($null -eq $State -or $null -eq $State.processes) {
        return $null
    }
    $property = $State.processes.PSObject.Properties[$LaneName]
    if ($null -eq $property) {
        return $null
    }
    return $property.Value
}

function Test-RecordProcess {
    param(
        [AllowNull()]
        [object]$Record
    )

    if ($null -eq $Record) {
        return $null
    }
    return Test-ProcessIdentity -Identity $Record
}

function Get-VerifiedRecordProcesses {
    param(
        [AllowNull()]
        [object]$Record
    )

    if ($null -eq $Record) {
        return @()
    }
    $result = [System.Collections.Generic.List[object]]::new()
    $root = Test-RecordProcess -Record $Record
    if ($null -ne $root) {
        $result.Add($root)
    }
    $treeProperty = $Record.PSObject.Properties['processTree']
    if ($null -ne $treeProperty -and $null -ne $treeProperty.Value) {
        foreach ($identity in @($treeProperty.Value)) {
            $process = Test-ProcessIdentity -Identity $identity
            if ($null -ne $process -and -not ($result.Id -contains $process.Id)) {
                $result.Add($process)
            }
        }
    }
    return $result.ToArray()
}

function Get-ActiveRecords {
    param(
        [AllowNull()]
        [object]$State
    )

    $records = [ordered]@{}
    foreach ($laneName in $laneDefinitions.Keys) {
        $record = Get-StateRecord -State $State -LaneName $laneName
        if (@(Get-VerifiedRecordProcesses -Record $record).Count -gt 0) {
            $records[$laneName] = $record
        }
    }
    return $records
}

function Write-State {
    param(
        [Parameter(Mandatory = $true)]
        [System.Collections.IDictionary]$Records
    )

    if ($Records.Count -eq 0) {
        if (Test-Path -LiteralPath $statePath -PathType Leaf) {
            Remove-Item -LiteralPath $statePath -Force
        }
        return
    }

    $state = [ordered]@{
        schemaVersion = 2
        repositoryRoot = $projectRoot
        updatedAtUtc = [DateTimeOffset]::UtcNow.ToString('o')
        processes = $Records
    }
    $temporaryPath = "$statePath.$([Guid]::NewGuid().ToString('N')).tmp"
    $stateJson = $state | ConvertTo-Json -Depth 8
    try {
        [IO.File]::WriteAllText(
            $temporaryPath,
            $stateJson,
            [Text.UTF8Encoding]::new($false)
        )
        Move-Item -LiteralPath $temporaryPath -Destination $statePath -Force
    }
    finally {
        if (Test-Path -LiteralPath $temporaryPath -PathType Leaf) {
            Remove-Item -LiteralPath $temporaryPath -Force
        }
    }
}

function New-WorkerProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LaneName
    )

    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        throw "Python virtual environment is unavailable: $pythonPath"
    }

    $timestamp = [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
    $instanceToken = [Guid]::NewGuid().ToString('D')
    $stdoutPath = Join-Path $runtimeDirectory "worker-$LaneName-$timestamp.out.log"
    $stderrPath = Join-Path $runtimeDirectory "worker-$LaneName-$timestamp.error.log"
    $arguments = @(
        '-m',
        'game_predictor_worker',
        '--poll',
        '--lane',
        [string]$laneDefinitions[$LaneName].argument,
        '--cpu-thread-budget',
        [string]$laneDefinitions[$LaneName].threadBudget,
        '--lane-instance-token',
        $instanceToken
    )
    $nativeThreadEnvironmentNames = @(
        'OMP_NUM_THREADS',
        'OPENBLAS_NUM_THREADS',
        'MKL_NUM_THREADS',
        'NUMEXPR_NUM_THREADS',
        'VECLIB_MAXIMUM_THREADS'
    )
    $previousThreadEnvironment = @{}
    $threadBudget = [string]$laneDefinitions[$LaneName].threadBudget
    $threadEnvironmentNames = @('GAME_PREDICTOR_WORKER_THREAD_BUDGET') + $nativeThreadEnvironmentNames
    foreach ($variableName in $threadEnvironmentNames) {
        $previousThreadEnvironment[$variableName] = [Environment]::GetEnvironmentVariable(
            $variableName,
            [EnvironmentVariableTarget]::Process
        )
        [Environment]::SetEnvironmentVariable(
            $variableName,
            $(if ($variableName -eq 'GAME_PREDICTOR_WORKER_THREAD_BUDGET') {
                $threadBudget
            } else {
                [string]$laneDefinitions[$LaneName].nativeThreadBudget
            }),
            [EnvironmentVariableTarget]::Process
        )
    }
    try {
        $process = Start-Process `
            -FilePath $pythonPath `
            -ArgumentList $arguments `
            -WorkingDirectory $projectRoot `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath `
            -PassThru `
            -WindowStyle Hidden
    }
    finally {
        foreach ($variableName in $threadEnvironmentNames) {
            [Environment]::SetEnvironmentVariable(
                $variableName,
                $previousThreadEnvironment[$variableName],
                [EnvironmentVariableTarget]::Process
            )
        }
    }

    for ($attempt = 0; $attempt -lt 4; $attempt++) {
        Start-Sleep -Milliseconds 250
        $process.Refresh()
        if ($process.HasExited) {
            $errorTail = ''
            if (Test-Path -LiteralPath $stderrPath -PathType Leaf) {
                $errorTail = (Get-Content -LiteralPath $stderrPath -Tail 10 -Encoding utf8) -join ' '
            }
            throw "$($laneDefinitions[$LaneName].displayName) exited during startup. $errorTail"
        }
    }

    $process.Refresh()
    $processTree = [System.Collections.Generic.List[object]]::new()
    $knownDescendants = @()
    for ($attempt = 0; $attempt -lt 8; $attempt++) {
        $knownDescendants = @([WorkerProcessTree]::Descendants($process.Id))
        if ($knownDescendants.Count -gt 0) {
            break
        }
        Start-Sleep -Milliseconds 250
    }
    foreach ($descendantProcessId in $knownDescendants) {
        $child = Get-Process -Id $descendantProcessId -ErrorAction SilentlyContinue
        if ($null -ne $child) {
            $processTree.Add([ordered]@{
                pid = $child.Id
                processName = $child.ProcessName
                startTimeUtc = $child.StartTime.ToUniversalTime().ToString('o')
            })
        }
    }
    return [ordered]@{
        lane = $LaneName
        pid = $process.Id
        processName = $process.ProcessName
        startTimeUtc = $process.StartTime.ToUniversalTime().ToString('o')
        stdoutLog = $stdoutPath
        stderrLog = $stderrPath
        threadBudget = [int]$laneDefinitions[$LaneName].threadBudget
        nativeThreadBudget = [int]$laneDefinitions[$LaneName].nativeThreadBudget
        instanceToken = $instanceToken
        processTree = @($processTree)
        workerPid = $(if ($processTree.Count -gt 0) { [int]$processTree[$processTree.Count - 1].pid } else { [int]$process.Id })
        command = "$pythonPath -m game_predictor_worker --poll --lane $($laneDefinitions[$LaneName].argument) --cpu-thread-budget $threadBudget"
    }
}

function Stop-WorkerProcess {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Record
    )

    $processes = @(Get-VerifiedRecordProcesses -Record $Record)
    if ($processes.Count -eq 0) {
        return 'stale'
    }
    $root = Test-RecordProcess -Record $Record
    if ($null -ne $root) {
        foreach ($descendantId in @([WorkerProcessTree]::Descendants($root.Id))) {
            $descendant = Get-Process -Id $descendantId -ErrorAction SilentlyContinue
            if ($null -ne $descendant -and -not ($processes.Id -contains $descendant.Id)) {
                $processes += $descendant
            }
        }
    }
    $processIds = @(
        $processes |
            Where-Object { $null -ne $_ -and $null -ne $_.Id } |
            ForEach-Object { @($_.Id) } |
            Where-Object { $null -ne $_ } |
            Sort-Object -Descending -Unique
    )
    foreach ($targetProcessId in $processIds) {
        try {
            $targetProcess = [System.Diagnostics.Process]::GetProcessById([int]$targetProcessId)
            $targetProcess.Kill()
        }
        catch [System.ArgumentException] {
            # The process exited after its identity was verified.
        }
        catch [System.InvalidOperationException] {
            # The process exited before Kill() reached it.
        }
    }
    $attempts = [Math]::Max(1, $TimeoutSeconds * 4)
    for ($attempt = 0; $attempt -lt $attempts; $attempt++) {
        $remaining = @($processIds | Where-Object {
            $null -ne (Get-Process -Id ([int]$_) -ErrorAction SilentlyContinue)
        })
        if ($remaining.Count -eq 0) {
            $instanceTokenProperty = $Record.PSObject.Properties['instanceToken']
            if ($null -eq $instanceTokenProperty -or [string]::IsNullOrWhiteSpace([string]$instanceTokenProperty.Value)) {
                return 'stopped'
            }
            $markArguments = @(
                '-m',
                'game_predictor_worker',
                '--lane',
                [string]$Record.lane,
                '--lane-instance-token',
                [string]$instanceTokenProperty.Value,
                '--mark-lane-stopped'
            )
            $markProcess = Start-Process `
                -FilePath $pythonPath `
                -ArgumentList $markArguments `
                -WorkingDirectory $projectRoot `
                -PassThru `
                -WindowStyle Hidden
            $markAttempts = [Math]::Max(1, $TimeoutSeconds * 4)
            for ($markAttempt = 0; $markAttempt -lt $markAttempts; $markAttempt++) {
                $markProcess.Refresh()
                if ($markProcess.HasExited) {
                    break
                }
                Start-Sleep -Milliseconds 250
            }
            $markProcess.Refresh()
            if (-not $markProcess.HasExited) {
                Stop-Process -Id $markProcess.Id -ErrorAction SilentlyContinue
                throw "Worker lane $($Record.lane) stopped, but finalizing its database status timed out."
            }
            if ($markProcess.ExitCode -ne 0) {
                throw "Worker lane $($Record.lane) stopped, but its database status could not be finalized."
            }
            return 'stopped'
        }
        Start-Sleep -Milliseconds 250
    }
    throw "Worker process tree for lane $($Record.lane) did not stop within $TimeoutSeconds seconds."
}

function New-StatusResult {
    param(
        [AllowNull()]
        [object]$State
    )

    $laneResults = @()
    foreach ($laneName in (Get-TargetLaneNames)) {
        $record = Get-StateRecord -State $State -LaneName $laneName
        $processes = @(Get-VerifiedRecordProcesses -Record $record)
        $root = Test-RecordProcess -Record $record
        $laneState = if ($null -ne $root -and $processes.Count -gt 0) {
            'running'
        }
        elseif ($processes.Count -gt 0) {
            'degraded'
        }
        elseif ($null -ne $record) {
            'stale'
        }
        else {
            'stopped'
        }
        $laneResults += [ordered]@{
            lane = $laneName
            displayName = [string]$laneDefinitions[$laneName].displayName
            state = $laneState
            pid = $(if ($null -ne $record) { [int]$record.pid } else { $null })
            workerPid = $(if ($null -ne $record -and $null -ne $record.PSObject.Properties['workerPid']) { [int]$record.workerPid } else { $null })
            startTimeUtc = $(if ($null -ne $record) { [string]$record.startTimeUtc } else { $null })
            stdoutLog = $(if ($null -ne $record) { [string]$record.stdoutLog } else { $null })
            stderrLog = $(if ($null -ne $record) { [string]$record.stderrLog } else { $null })
            threadBudget = $(if ($null -ne $record -and $null -ne $record.threadBudget) { [int]$record.threadBudget } else { [int]$laneDefinitions[$laneName].threadBudget })
            nativeThreadBudget = $(if ($null -ne $record -and $null -ne $record.nativeThreadBudget) { [int]$record.nativeThreadBudget } else { [int]$laneDefinitions[$laneName].nativeThreadBudget })
        }
    }
    $states = @($laneResults | ForEach-Object { $_.state })
    $overallState = if ($states -contains 'stale' -or $states -contains 'degraded') {
        'degraded'
    }
    elseif ($states -notcontains 'running') {
        'stopped'
    }
    elseif ($states -notcontains 'stopped') {
        'running'
    }
    else {
        'partial'
    }
    return [ordered]@{
        state = $overallState
        statePath = $statePath
        lanes = $laneResults
    }
}

function Write-Result {
    param(
        [Parameter(Mandatory = $true)]
        [System.Collections.IDictionary]$Result
    )

    if ($Json) {
        Write-Output ($Result | ConvertTo-Json -Depth 8 -Compress)
        return
    }
    Write-Host "Worker lanes: $($Result.state)"
    foreach ($laneResult in $Result.lanes) {
        $details = if ($laneResult.state -eq 'running') {
            "launcher PID $($laneResult.pid), worker PID $($laneResult.workerPid), since $($laneResult.startTimeUtc), threads $($laneResult.threadBudget), native $($laneResult.nativeThreadBudget)"
        }
        elseif ($laneResult.state -in @('stale', 'degraded')) {
            "stale PID $($laneResult.pid)"
        }
        else {
            'not running'
        }
        Write-Host "- $($laneResult.displayName): $($laneResult.state) ($details)"
        if ($null -ne $laneResult.stdoutLog) {
            Write-Host "  stdout: $($laneResult.stdoutLog)"
            Write-Host "  stderr: $($laneResult.stderrLog)"
        }
    }
}

if ($Action -eq 'Status') {
    Write-Result -Result (New-StatusResult -State (Read-State))
    exit 0
}

$stateLock = Enter-StateLock
try {
    $state = Read-State
    $activeRecords = Get-ActiveRecords -State $state
    Write-State -Records $activeRecords

    if ($Action -eq 'Start') {
        $startedThisInvocation = [System.Collections.Generic.List[string]]::new()
        try {
            foreach ($laneName in (Get-TargetLaneNames)) {
                if ($activeRecords.Contains($laneName)) {
                    continue
                }
                $activeRecords[$laneName] = New-WorkerProcess -LaneName $laneName
                $startedThisInvocation.Add($laneName)
                Write-State -Records $activeRecords
            }
        }
        catch {
            foreach ($laneName in $startedThisInvocation) {
                [void](Stop-WorkerProcess -Record $activeRecords[$laneName])
                $activeRecords.Remove($laneName)
            }
            Write-State -Records $activeRecords
            throw
        }
    }
    elseif ($Action -eq 'Stop') {
        foreach ($laneName in (Get-TargetLaneNames)) {
            if (-not $activeRecords.Contains($laneName)) {
                continue
            }
            [void](Stop-WorkerProcess -Record $activeRecords[$laneName])
            $activeRecords.Remove($laneName)
            Write-State -Records $activeRecords
        }
    }

    Write-Result -Result (New-StatusResult -State (Read-State))
}
finally {
    if ($null -ne $stateLock) {
        $stateLock.Dispose()
    }
}
