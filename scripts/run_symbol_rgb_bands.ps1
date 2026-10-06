# RGB v2 band driver (TASK-0873, plan SYMBOL_RGB_V2_REPROCESSING_PLAN).
#
# -Phase preview: for every symbol of the band, preview each part (read-only) and
#   stop at the operator gate with band-<band>-gate.json.
# -Phase apply (only after the operator approved the gate): for each part, bind the
#   approved preview to the current boards (manifest), write it, read it back.
#
# Every Python process runs with a hard 600 s limit; exit code 3 means "again".
# The driver is resumable: finished previews and parts with apply-verify.json are
# skipped. Logs go to <ArtifactsDir>\band-<band>-driver.log (UTC).
param(
    [Parameter(Mandatory)] [ValidateSet('lt60', '60-80', '80-90', '90-99', '99-100')] [string]$Band,
    [Parameter(Mandatory)] [ValidateSet('preview', 'apply')] [string]$Phase,
    [string[]]$Symbols = @('ARBUZ', 'CYTRYNA', 'GWIAZDA', 'POMARANCZ', 'SIEDEM', 'SLIWKA', 'WINOGRON', 'WISNIA'),
    [string]$RepoRoot = '',
    [string]$Python = '',
    [string]$ArtifactsDir = '',
    [string]$ArtifactRoot = '',
    [string]$LibraryDir = '',
    [string]$GameCode = '7',
    [int]$MaxCellsPerPart = 60000,
    # Delete a part's crop cache (~0.75 GB per 60 000 cells) once its preview is complete;
    # manifest, apply and verify do not read it. Needed for the 120 parts of 99-100%.
    [switch]$DropCropCache
)
$ErrorActionPreference = 'Stop'
# $PSScriptRoot is empty inside the param block of Windows PowerShell 5.1.
# -File passes 'A,B' as one string; accept both forms.
$Symbols = @($Symbols | ForEach-Object { $_ -split ',' } | Where-Object { $_ })
if (-not $RepoRoot) { $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path }
if (-not $Python) { $Python = Join-Path $RepoRoot '.venv\Scripts\python.exe' }
if (-not $ArtifactRoot) { $ArtifactRoot = Join-Path $RepoRoot 'artifacts' }
if (-not $ArtifactsDir) { $ArtifactsDir = Join-Path $ArtifactRoot 'symbol-rgb-v2' }
if (-not $LibraryDir) { $LibraryDir = Join-Path $ArtifactRoot 'grid-audit-symbols-20261005' }
$indexDir = Join-Path $ArtifactsDir 'index'
$runDir = Join-Path $ArtifactsDir "runs\$Band"
$log = Join-Path $ArtifactsDir "band-$Band-driver.log"
New-Item -ItemType Directory -Force $runDir | Out-Null

function Write-Log([string]$message) {
    $line = '{0:yyyy-MM-dd HH:mm:ss}Z {1}' -f (Get-Date).ToUniversalTime(), $message
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        try {
            $stream = [IO.File]::Open($log, 'Append', 'Write', 'ReadWrite')
            try {
                $bytes = [Text.Encoding]::UTF8.GetBytes($line + "`n")
                $stream.Write($bytes, 0, $bytes.Length)
            } finally { $stream.Dispose() }
            return
        } catch { Start-Sleep -Milliseconds 250 }
    }
}

function Invoke-Rgb([string[]]$arguments) {
    $out = [IO.Path]::GetTempFileName()
    $err = [IO.Path]::GetTempFileName()
    $quoted = ($arguments | ForEach-Object { '"' + $_ + '"' }) -join ' '
    $process = Start-Process -FilePath $Python -ArgumentList ('-m scripts.symbol_rgb_v2 ' + $quoted) `
        -WorkingDirectory $RepoRoot -NoNewWindow -PassThru `
        -RedirectStandardOutput $out -RedirectStandardError $err
    # Touching the handle keeps ExitCode available after WaitForExit (PowerShell 5.1).
    $null = $process.Handle
    if (-not $process.WaitForExit(600000)) {
        & taskkill.exe /PID $process.Id /T /F | Out-Null
        $process.WaitForExit()
        $code = 124
    } else {
        $code = $process.ExitCode
    }
    $text = (Get-Content $out -Raw -Encoding utf8) + (Get-Content $err -Raw -Encoding utf8)
    Remove-Item $out, $err -ErrorAction SilentlyContinue
    return @{ Code = $code; Text = "$text".Trim() }
}

function Invoke-Until-Done([string]$label, [string[]]$arguments) {
    $round = 0
    while ($true) {
        $round += 1
        $result = Invoke-Rgb $arguments
        $last = ($result.Text -split "`n" | Select-Object -Last 1)
        Write-Log "$label round=$round exit=$($result.Code) $last"
        if ($result.Code -eq 0) { return $result.Text }
        if ($result.Code -ne 3) {
            Write-Log "$label STOP: $($result.Text)"
            throw "$label failed with exit $($result.Code)"
        }
    }
}

function Get-Parts([string]$symbol) {
    # Parts of at most MaxCellsPerPart cells, split by the stable id hash (--shard).
    $summary = Get-Content (Join-Path $indexDir 'summary.json') -Raw -Encoding utf8 | ConvertFrom-Json
    $bands = $summary.symbols.$symbol
    $cells = 0
    if ($bands -and $bands.$Band) {
        foreach ($property in $bands.$Band.PSObject.Properties) { $cells += [int]$property.Value }
    }
    if ($cells -eq 0) { return }
    $count = [int][Math]::Max(1, [Math]::Ceiling($cells / $MaxCellsPerPart))
    for ($i = 0; $i -lt $count; $i++) {
        [pscustomobject]@{
            Symbol = $symbol
            Name = ('{0}-{1:D2}-of-{2:D2}' -f $symbol, ($i + 1), $count)
            Shard = "$i/$count"
        }
    }
}

trap {
    Write-Log "driver STOP error: $_"
    exit 1
}
if (-not (Test-Path (Join-Path $indexDir 'summary.json'))) { throw "Band index missing: $indexDir" }
Write-Log "driver start band=$Band phase=$Phase symbols=$($Symbols -join ',')"
$plan = @(foreach ($symbol in $Symbols) { Get-Parts $symbol })

if ($Phase -eq 'preview') {
    $gate = @()
    foreach ($entry in $plan) {
        $symbol, $name, $shard = $entry.Symbol, $entry.Name, $entry.Shard
        $output = Join-Path $runDir $name
        $doneMarker = Join-Path $output 'preview.done'
        if (Test-Path $doneMarker) {
            Write-Log "$name preview already complete; skipped"
        } else {
            $text = Invoke-Until-Done "$name preview" @(
                'preview', '--game-code', $GameCode, '--index-dir', $indexDir,
                '--output-dir', $output, '--library-dir', $LibraryDir, '--artifact-root', $ArtifactRoot,
                '--symbol', $symbol, '--band', $Band, '--shard', $shard, '--time-budget-seconds', '300'
            )
            # Written only after a complete preview; delete it to recompute a part.
            Set-Content -Path $doneMarker -Value (Get-Date).ToUniversalTime().ToString('o') -Encoding ascii
            if ($DropCropCache) {
                Remove-Item (Join-Path $output 'preview-crops.npz') -ErrorAction SilentlyContinue
            }
        }
        $report = Get-Content (Join-Path $output 'report.json') -Raw -Encoding utf8 | ConvertFrom-Json
        $gate += [ordered]@{
            part = $name; cells = $report.cells; writes = $report.writes
            status = $report.status; groups = $report.groups
            preview = (Join-Path $output 'preview.html')
        }
        Write-Log "$name preview done: cells=$($report.cells) writes=$($report.writes)"
    }
    $gatePath = Join-Path $ArtifactsDir "band-$Band-gate.json"
    ($gate | ConvertTo-Json -Depth 6) | Set-Content -Path $gatePath -Encoding utf8
    Write-Log "GATE band=${Band}: previews ready in $gatePath; write only after operator approval"
    exit 0
}

foreach ($entry in $plan) {
    $symbol, $name, $shard = $entry.Symbol, $entry.Name, $entry.Shard
    $output = Join-Path $runDir $name
    $manifest = Join-Path $output 'apply-manifest.json'
    if (Test-Path (Join-Path $output 'apply-verify.json')) {
        Write-Log "$name already verified; skipped"
        continue
    }
    if (-not (Test-Path (Join-Path $output 'report.json'))) { throw "$name has no approved preview" }
    if (Test-Path $manifest) {
        # Resume the part on its manifest; a board written without a receipt becomes stale.
        $sha = (Get-FileHash -Algorithm SHA256 $manifest).Hash.ToLowerInvariant()
        Write-Log "$name resume on manifest $($sha.Substring(0, 12))"
    } else {
        $text = Invoke-Until-Done "$name manifest" @('manifest', '--output-dir', $output)
        $sha = [regex]::Match($text, 'apply-manifest\.json sha256=([0-9a-f]{64})').Groups[1].Value
        if (-not $sha) { throw "$name manifest checksum missing" }
        Write-Log "$name manifest $($sha.Substring(0, 12))"
    }
    Invoke-Until-Done "$name apply" @(
        'apply', '--game-code', $GameCode, '--manifest', $manifest,
        '--expected-sha256', $sha, '--time-budget-seconds', '240'
    ) | Out-Null
    $verify = Invoke-Rgb @('verify', '--manifest', $manifest, '--expected-sha256', $sha)
    Write-Log "$name verify exit=$($verify.Code) $($verify.Text -replace "`r?`n", ' ')"
    if ($verify.Code -ne 0) { throw "$name verify failed" }
}
Write-Log "driver done band=$Band phase=apply"
