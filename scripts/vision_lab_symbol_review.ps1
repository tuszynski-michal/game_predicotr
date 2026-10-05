<#
.SYNOPSIS
  Start, inspect or stop the existing symbol editor with an explicit labels-only version.
.DESCRIPTION
  Config is a persistent JSON file with absolute Repository, Python, Node, Snapshot,
  Annotations, Symbols, DatasetVersion and Logs paths. No training or database writes.
  Start returns saved process identities; Status bounds readiness probes to 8 seconds.
  A matching assisted geometry page on 8105 is stopped before switching to 8102.
  Other listeners are never killed. Stop only terminates recorded, matching identities.
#>
param(
  [ValidateSet('Start', 'Status', 'Stop')][string]$Action = 'Status',
  [Parameter(Mandatory = $true)][string]$Config
)
$ErrorActionPreference = 'Stop'
$settings = Get-Content -LiteralPath $Config -Raw | ConvertFrom-Json
foreach ($field in @('Repository', 'Python', 'Node', 'Snapshot', 'Annotations', 'Symbols', 'DatasetVersion', 'Logs')) {
  $value = $settings.$field
  if (-not $value -or -not [System.IO.Path]::IsPathFullyQualified($value)) {
    throw "Config field $field must be an absolute path."
  }
}
$processFile = Join-Path $settings.Logs 'processes.json'
$module = 'game_predictor_worker.vision_lab'

function Test-Identity($record) {
  $actual = Get-CimInstance Win32_Process -Filter "ProcessId=$($record.pid)"
  return ($actual -and $actual.CreationDate.ToUniversalTime().Ticks -eq [long]$record.creation_ticks `
    -and $actual.CommandLine -eq $record.command_line)
}

function Stop-Owned($record) {
  if (-not (Test-Identity $record)) { return }
  $kill = Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\taskkill.exe') `
    -ArgumentList @('/PID', "$($record.pid)", '/T', '/F') -WindowStyle Hidden -PassThru
  if (-not $kill.WaitForExit(10000)) { throw 'Controlled process termination timed out.' }
  if (Test-Identity $record) { throw "Owned process $($record.pid) is still running." }
}

function Save-Process($process, [string]$kind) {
  $actual = Get-CimInstance Win32_Process -Filter "ProcessId=$($process.Id)"
  if (-not $actual) { throw "$kind exited during startup; inspect saved logs." }
  return @{ kind = $kind; pid = $actual.ProcessId; command_line = $actual.CommandLine;
    creation_ticks = $actual.CreationDate.ToUniversalTime().Ticks;
    creation_utc = $actual.CreationDate.ToUniversalTime().ToString('o') }
}

function Show-Status {
  if (Test-Path -LiteralPath $processFile) {
    $saved = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
    foreach ($record in $saved.processes) { "Owned=$((Test-Identity $record)) $($record.kind) PID=$($record.pid)" }
  }
  foreach ($url in @('http://127.0.0.1:8102/sources?limit=1', 'http://127.0.0.1:3102/symbols')) {
    $ready = $false
    for ($attempt = 0; $attempt -lt 3; $attempt++) {
      try { $null = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 1; $ready = $true; break }
      catch { Start-Sleep -Milliseconds 100 }
    }
    "Ready=$ready $url"
  }
}

if ($Action -eq 'Status') { Show-Status; return }
if ($Action -eq 'Stop') {
  if (Test-Path -LiteralPath $processFile) {
    $saved = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
    foreach ($record in $saved.processes) { Stop-Owned $record }
  }
  'Recorded symbol review processes stopped; files and decisions retained.'
  return
}

if (Test-Path -LiteralPath $processFile) {
  $saved = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
  $alive = @($saved.processes | Where-Object { Test-Identity $_ })
  if ($alive.Count -eq 2) { Show-Status; return }
  if ($alive.Count) { throw 'Partial startup still alive. Inspect Status/logs, then Stop before restarting.' }
}
foreach ($port in @(8102, 3102)) {
  if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $port is occupied. Inspect its owner before starting another copy."
  }
}
if (-not (Test-Path -LiteralPath (Join-Path $settings.Repository 'apps\vision-lab\.next\BUILD_ID'))) {
  throw 'Build the existing Vision Lab UI before Start.'
}
if (-not (Test-Path -LiteralPath (Join-Path $settings.DatasetVersion 'manifest.json'))) {
  throw 'Dataset version manifest is missing.'
}
$geometryProcesses = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
  $_.CommandLine -like '*game_predictor_worker.vision_lab.assisted_annotation*serve*' `
    -and $_.CommandLine -match '--port\s+8105(\s|$)' `
    -and $_.CommandLine.Contains($settings.Annotations)
})
foreach ($actual in $geometryProcesses) {
  Stop-Owned @{ pid = $actual.ProcessId; command_line = $actual.CommandLine;
    creation_ticks = $actual.CreationDate.ToUniversalTime().Ticks;
    creation_utc = $actual.CreationDate.ToUniversalTime().ToString('o') }
}
if (Get-NetTCPConnection -LocalPort 8105 -State Listen -ErrorAction SilentlyContinue) {
  throw 'Geometry page on 8105 still owns a listener. No simultaneous geometry writer is allowed.'
}
New-Item -ItemType Directory -Path $settings.Logs -Force | Out-Null
$env:PYTHONPATH = Join-Path $settings.Repository 'services\worker\src'
$env:PYTHONIOENCODING = 'utf-8'
$records = @()
try {
  $api = Start-Process -FilePath $settings.Python -ArgumentList @(
    '-m', $module, '--snapshot', ('"' + $settings.Snapshot + '"'),
    '--annotations', ('"' + $settings.Annotations + '"'),
    '--symbols', ('"' + $settings.Symbols + '"'),
    '--symbol-dataset-version', ('"' + $settings.DatasetVersion + '"')
  ) -WorkingDirectory $settings.Repository -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $settings.Logs 'api.stdout.log') `
    -RedirectStandardError (Join-Path $settings.Logs 'api.stderr.log')
  $records += Save-Process $api 'api'
  @{ config = [System.IO.Path]::GetFullPath($Config); processes = $records } | ConvertTo-Json -Depth 5 `
    | Set-Content -LiteralPath $processFile -Encoding UTF8
  $ui = Start-Process -FilePath $settings.Node -ArgumentList @(
    ('"' + (Join-Path $settings.Repository 'node_modules\next\dist\bin\next') + '"'),
    'start', ('"' + (Join-Path $settings.Repository 'apps\vision-lab') + '"'),
    '--hostname', '127.0.0.1', '--port', '3102'
  ) -WorkingDirectory $settings.Repository -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $settings.Logs 'ui.stdout.log') `
    -RedirectStandardError (Join-Path $settings.Logs 'ui.stderr.log')
  $records += Save-Process $ui 'ui'
  @{ config = [System.IO.Path]::GetFullPath($Config); processes = $records } | ConvertTo-Json -Depth 5 `
    | Set-Content -LiteralPath $processFile -Encoding UTF8
  "Started API PID=$($api.Id), UI PID=$($ui.Id). Verify readiness with -Action Status."
} catch {
  foreach ($record in $records) { Stop-Owned $record }
  throw
}
