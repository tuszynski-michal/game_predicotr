<#
.SYNOPSIS
  Start, stop or inspect the assisted complete-photo annotation page (TASK-0824, D-490).

.DESCRIPTION
  Start runs the loopback page http://127.0.0.1:<Port> as a hidden background process
  (Python from the repository .venv) and waits at most 60 s for readiness. Decisions are
  written only to the existing lab annotation store; proposals are read from the proposal
  sets under <LabRoot>\assisted-annotation\proposals (one base set plus fine-tune sets). Stop ends exactly the
  processes whose command line is this page on this port. Status prints progress.
  Export writes the create-only list of complete photos to
  <LabRoot>\assisted-annotation\exports.
  CloseFinished (TASK-0825) previews the photos whose boards are all accepted but which
  were never confirmed; with -Apply it closes them (count = accepted boards).
  -Games limits the queue and counters (default: mumie; Blazing and Gang stay untouched).
  The page shows the newest proposal set (fine-tune iterations) without a restart.
#>
param(
  [ValidateSet('Start', 'Stop', 'Status', 'Export', 'CloseFinished')]
  [string]$Action = 'Start',
  [string]$LabRoot = 'C:\Users\tuszy\Documents\game_predictor_vision_data',
  [string]$SnapshotId = '0cdc0770b3535596fdbfa0a8f403cbf32d6a8b134fb52047f5a1f7bda33772c2',
  [string]$Annotations = '',
  [string]$Proposals = '',
  [ValidateSet('mumie', 'blazing', 'gang')]
  [string[]]$Games = @('mumie'),
  [switch]$Apply,
  [int]$Port = 8105
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'
$work = Join-Path $LabRoot 'assisted-annotation'
$snapshot = Join-Path $LabRoot "snapshots\$SnapshotId"
if (-not $Annotations) { $Annotations = Join-Path $LabRoot "annotations\$SnapshotId" }
if (-not $Proposals) { $Proposals = Join-Path $work 'proposals' }
$module = 'game_predictor_worker.vision_lab.assisted_annotation'
$common = @('--snapshot', ('"' + $snapshot + '"'), '--annotations', ('"' + $Annotations + '"'),
  '--proposals', ('"' + $Proposals + '"'), '--games') + $Games

function Get-PageProcess {
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
    $_.CommandLine -like "*$module*serve*" -and $_.CommandLine -match "--port\s+$Port(\s|$)"
  }
}

function Invoke-Module([string[]]$Arguments, [int]$TimeoutMs) {
  $process = Start-Process -FilePath $python -ArgumentList (@('-m', $module) + $Arguments) `
    -WorkingDirectory $repo -NoNewWindow -PassThru
  $null = $process.Handle
  if (-not $process.WaitForExit($TimeoutMs)) { $process.Kill(); throw "Timeout $($TimeoutMs / 1000) s" }
  if ($process.ExitCode -ne 0) { throw "Exit $($process.ExitCode)" }
}

switch ($Action) {
  'Start' {
    $url = "http://127.0.0.1:$Port"
    if (Get-PageProcess) { "Strona już działa: $url"; return }
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
      throw "Port $Port jest zajęty przez inny proces; nie uruchamiam drugiej kopii."
    }
    $logs = Join-Path $work 'logs'
    New-Item -ItemType Directory -Path $logs -Force | Out-Null
    $server = Start-Process -FilePath $python -ArgumentList (@('-m', $module, 'serve') + $common + @('--port', "$Port")) `
      -WorkingDirectory $repo -WindowStyle Hidden -PassThru `
      -RedirectStandardOutput (Join-Path $logs 'page.stdout.log') `
      -RedirectStandardError (Join-Path $logs 'page.stderr.log')
    for ($attempt = 0; $attempt -lt 120; $attempt++) {
      try {
        $null = Invoke-WebRequest -Uri "$url/api/queue" -UseBasicParsing -TimeoutSec 2
        "Gotowe: $url (PID $($server.Id); zatrzymanie: -Action Stop)"
        return
      } catch {
        if ($server.HasExited) { break }
        Start-Sleep -Milliseconds 500
      }
    }
    Get-Content (Join-Path $logs 'page.stderr.log') -Tail 20 -ErrorAction SilentlyContinue
    if (-not $server.HasExited) { Get-PageProcess | ForEach-Object { Stop-Process -Id $_.ProcessId -Force } }
    throw "Strona nie wystartowała; sprawdź $logs"
  }
  'Stop' {
    $found = @(Get-PageProcess)
    foreach ($item in $found) { Stop-Process -Id $item.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 300
    if (Get-PageProcess) { throw 'Proces strony nadal działa.' }
    "Zatrzymano procesów: $($found.Count)"
  }
  'Status' { Invoke-Module (@('status') + $common) 120000 }
  'CloseFinished' {
    $closeArgs = @('close-finished') + $common
    if ($Apply) { $closeArgs += '--apply' }
    Invoke-Module $closeArgs 300000
  }
  'Export' {
    Invoke-Module (@('export') + $common + @('--output', ('"' + (Join-Path $work 'exports') + '"'))) 300000
  }
}
