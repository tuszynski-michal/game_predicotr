[CmdletBinding()]
param(
    [ValidateSet('Start', 'Status', 'Stop')][string]$Action = 'Status',
    [ValidateSet('api', 'worker', 'admin')][string]$Role = 'api',
    [ValidateSet('real_pilot', 'technical_fixture')][string]$Scope = 'real_pilot'
)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core') { throw 'Use PowerShell 7 (pwsh.exe) for this controlled launcher.' }
. (Join-Path $PSScriptRoot 'windows_process_environment.ps1')
Repair-WindowsProcessPath
$pilotRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pilotRuntime = Join-Path $pilotRoot '.claude/v7-pilot-runtime'
$pilotEntry = Join-Path $PSScriptRoot 'v7_pilot_runtime_entry.py'
$pilotPython = Join-Path $pilotRoot '.venv/Scripts/python.exe'
$pilotRegistry = Join-Path $pilotRuntime "process-$Role.json"
$pilotPort = @{ api = 8020; admin = 3020 }[$Role]

function Get-PilotRecord {
    if (-not (Test-Path -LiteralPath $pilotRegistry)) { return $null }
    $record = Get-Content -LiteralPath $pilotRegistry -Raw | ConvertFrom-Json
    if ($record.task -ne 'TASK-0853' -or $record.role -ne $Role -or $record.scope -notin @('real_pilot','technical_fixture') -or $record.worktree -ne $pilotRoot -or $record.entryPath -ne $pilotEntry) {
        throw 'Process registry belongs to another task/worktree.'
    }
    if ($record.scope -ne $Scope) {
        if ($Action -ne 'Start' -or (Get-OwnedPilotProcess $record)) { throw 'Live registry belongs to another composition; refuse adoption.' }
        # A dead/stopped owned record can be replaced; the entry's lifetime lock is authoritative.
    }
    return $record
}

function Get-OwnedPilotProcess($record, [switch]$Registration) {
    if ($null -eq $record) { return $null }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($record.pid)"
    if ($null -eq $process) { return $null }
    if (-not $process.CommandLine.Contains($pilotEntry) -or -not $process.CommandLine.Contains($record.launchToken)) {
        throw 'PID was reused or is not owned by this launch token.'
    }
    if ($record.PSObject.Properties.Name -contains 'processCreationUtc') {
        if (([DateTimeOffset]$record.processCreationUtc).UtcDateTime -ne $process.CreationDate.ToUniversalTime()) { throw 'Root PID creation differs from its immutable registration.' }
    } elseif (-not $Registration) { throw 'Root process creation was never confirmed; refuse adoption.' }
    return $process
}

function Get-PilotOwnedTree($root, $snapshot) {
    $owned = @($root)
    for ($depth = 0; $depth -lt 8; $depth++) {
        $children = @($snapshot | Where-Object {
            $candidateChild = $_
            $parent = @($owned | Where-Object { $_.ProcessId -eq $candidateChild.ParentProcessId })
            $parent.Count -eq 1 -and $candidateChild.CreationDate -ge $parent[0].CreationDate -and $owned.ProcessId -notcontains $candidateChild.ProcessId
        })
        if ($children.Count -eq 0) { return $owned }
        $owned += $children
    }
    throw 'Process tree exceeds the bounded ownership depth; refuse stop.'
}

function Stop-PilotOwnedProcess($candidate) {
    $current = Get-CimInstance Win32_Process -Filter "ProcessId=$($candidate.ProcessId)"
    if (-not $current) { return }
    if ($current.CreationDate -ne $candidate.CreationDate) { throw 'Child PID was reused; refuse stop.' }
    try { Stop-Process -Id $current.ProcessId -Force -ErrorAction Stop }
    catch {
        if ($_.CategoryInfo.Category -ne [Management.Automation.ErrorCategory]::ObjectNotFound) { throw }
        if (Get-CimInstance Win32_Process -Filter "ProcessId=$($candidate.ProcessId)") { throw }
        # Killing a descendant can make its verified parent exit before Stop-Process.
        # Only a missing PID rechecked after the specific missing-process error is harmless.
    }
}

$launcherLock = [IO.File]::Open((Join-Path $pilotRuntime "launcher-$Role.lock"), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
try {
if ($Action -eq 'Start') {
    $record = Get-PilotRecord
    if ($null -ne (Get-OwnedPilotProcess $record)) { throw 'Owned process already runs; inspect Status first.' }
    if ($pilotPort -and (Get-NetTCPConnection -State Listen -LocalPort $pilotPort -ErrorAction SilentlyContinue)) {
        throw "Port $pilotPort is occupied; no process will be stopped or adopted."
    }
    $pilotLogs = Join-Path $pilotRuntime 'logs'
    New-Item -ItemType Directory -Path $pilotLogs -Force | Out-Null
    $pilotToken = [guid]::NewGuid().ToString()
    $pilotOutput = Join-Path $pilotLogs "$Role-$pilotToken.stdout.log"
    $pilotError = Join-Path $pilotLogs "$Role-$pilotToken.stderr.log"
    $launch = Start-Process -FilePath $pilotPython -ArgumentList @('"' + $pilotEntry + '"', '--role', $Role, '--scope', $Scope, '--launch-token', $pilotToken) -WorkingDirectory $pilotRoot -WindowStyle Hidden -RedirectStandardOutput $pilotOutput -RedirectStandardError $pilotError -PassThru
    # The Python entry records its actual PID, rather than the Windows venv launcher PID.
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        Start-Sleep -Milliseconds 200
        $record = Get-PilotRecord
        if ($record -and $record.launchToken -eq $pilotToken) { break }
        $launch.Refresh()
        if ($launch.HasExited) { throw "Launch failed; inspect task-owned logs $pilotError" }
    } while ([DateTime]::UtcNow -lt $deadline)
    if (-not $record -or $record.launchToken -ne $pilotToken) {
        throw 'No PID registration within 10 seconds; inspect the first launch before retrying.'
    }
    $registeredProcess = Get-OwnedPilotProcess $record -Registration
    if (-not $registeredProcess) { throw 'Registered process exited before ownership confirmation.' }
    $record | Add-Member -NotePropertyName processCreationUtc -NotePropertyValue $registeredProcess.CreationDate.ToUniversalTime().ToString('o') -Force
    $record | Add-Member -NotePropertyName launcherPid -NotePropertyValue $launch.Id -Force
    $record | Add-Member -NotePropertyName stdoutLog -NotePropertyValue $pilotOutput -Force
    $record | Add-Member -NotePropertyName stderrLog -NotePropertyValue $pilotError -Force
    $record | ConvertTo-Json | Set-Content -LiteralPath $pilotRegistry -Encoding utf8
}

$record = Get-PilotRecord
$process = Get-OwnedPilotProcess $record
if ($Action -eq 'Stop' -and $process) {
    # Finite read-only isolated DB proof; calibration mutations are refused by this composition.
    $stopProof = & $pilotPython -c 'import subprocess,sys; sys.exit(subprocess.run([sys.executable,sys.argv[1],"--role",sys.argv[2],"--check-stop"],timeout=15).returncode)' $pilotEntry $Role
    if ($LASTEXITCODE -ne 0) { throw 'Read-only stop safety proof refused; process remains running.' }
    $safe = $stopProof | ConvertFrom-Json
    if ($safe.status -ne 'safe_to_stop' -or $safe.database -ne 'game_predictor_v7_pilot' -or -not $safe.calibrationReadOnly) { throw 'Stop safety identity differs.' }
    # Child process ownership follows only the verified unique-token root PID.
    $snapshot = @(Get-CimInstance Win32_Process)
    $owned = @(Get-PilotOwnedTree $process $snapshot)
    [array]::Reverse($owned)
    foreach ($candidate in $owned) {
        Stop-PilotOwnedProcess $candidate
    }
    $record.status = 'stopped'
    $record | ConvertTo-Json | Set-Content -LiteralPath $pilotRegistry -Encoding utf8
    $process = $null
}

$ready = $false
if ($process) {
    $readyDeadline = [DateTime]::UtcNow.AddSeconds(10)
    $dbProof = & $pilotPython -c 'import subprocess,sys; sys.exit(subprocess.run([sys.executable,sys.argv[1],"--role",sys.argv[2],"--launch-token",sys.argv[3],"--check-ready"],timeout=8).returncode)' $pilotEntry $Role $record.launchToken
    if ($LASTEXITCODE -eq 0) { $ready = [bool](($dbProof | ConvertFrom-Json).ready) }
    if ($ready -and $pilotPort) {
    $url = if ($Role -eq 'api') { 'http://127.0.0.1:8020/api/v1/health' } else { 'http://127.0.0.1:3020' }
    do {
        try { $ready = (Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 1).StatusCode -eq 200 } catch { $ready = $false }
        if ($ready) { break }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $readyDeadline)
    }
}
$recordedPid = if ($record) { $record.pid } else { $null }
[pscustomobject]@{ role = $Role; scope = $Scope; running = [bool]$process; ready = $ready; pid = $recordedPid; port = $pilotPort; database = 'game_predictor_v7_pilot'; registry = $pilotRegistry } | ConvertTo-Json
} finally { $launcherLock.Dispose() }
