param(
  [Parameter(Mandatory=$true)][string]$LabRoot,
  [Parameter(Mandatory=$true)][string]$SnapshotId,
  [Parameter(Mandatory=$true)][string]$ManifestId,
  [ValidateSet('development','validation')][string]$Partition = 'development',
  [int]$Offset = 0,
  [ValidateRange(1,8)][int]$Limit = 2
)
$ErrorActionPreference = 'Stop'
$repository = Split-Path $PSScriptRoot -Parent
$prefix = Join-Path $repository "artifacts/vision-lab/t05-preflight-$Partition-$Offset"
$arguments = @(
  (Join-Path $PSScriptRoot 'preflight_vision_lab_hybrid.py'),
  '--snapshot', (Join-Path $LabRoot "snapshots/$SnapshotId"),
  '--annotations', (Join-Path $LabRoot "annotations/$SnapshotId"),
  '--manifest', (Join-Path $LabRoot "manifests/$ManifestId.json"),
  '--partition', $Partition, '--offset', "$Offset", '--limit', "$Limit"
)
$quotedArguments = $arguments | ForEach-Object { '"' + $_ + '"' }
$process = Start-Process -FilePath (Join-Path $repository '.venv-vision-lab/Scripts/python.exe') -ArgumentList $quotedArguments -WindowStyle Hidden -PassThru -RedirectStandardOutput "$prefix.stdout.json" -RedirectStandardError "$prefix.stderr.log"
Write-Output "Read-only preflight PID $($process.Id), partition $Partition, offset $Offset, limit $Limit"
$lastProgress = Get-Date
$deadline = (Get-Date).AddSeconds(115)
$seen = ''
while (-not $process.WaitForExit(1000)) {
  $content = Get-Content "$prefix.stderr.log" -Raw
  if ($content -and $content -ne $seen) {
    Write-Output $content.Substring($seen.Length)
    $lastProgress = Get-Date
    $seen = $content
  }
  if ((Get-Date) -gt $deadline -or ((Get-Date) - $lastProgress).TotalSeconds -gt 60) {
    & taskkill /PID $process.Id /T /F
    throw 'Preflight timeout: no geometry classification was inferred from the timeout.'
  }
}
if ($process.ExitCode -ne 0) {
  Get-Content "$prefix.stderr.log"
  throw "Preflight exit $($process.ExitCode)"
}
$result = Get-Content "$prefix.stdout.json" -Raw | ConvertFrom-Json
Write-Output ($result.coverage | ConvertTo-Json -Depth 8 -Compress)
