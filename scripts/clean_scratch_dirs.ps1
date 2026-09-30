<#
.SYNOPSIS
Preview and remove ignored scratch directories in a repository root (D-467, S1).

.DESCRIPTION
Lists directories one level below the repository root that match the frozen
scratch patterns, are ignored by Git and hold no tracked file. Candidates are
classified before anything happens: readable directories are removable, while
unreadable ones, reparse points (junctions, symlinks) and directories with a
locked or recently written file are only reported. Nothing is removed without
-Execute, and -Execute requires the confirmation phrase printed by the preview,
which is bound to the exact removable list. Each directory is removed on its
own; failures are collected and reported at the end (exit code 1).

.EXAMPLE
powershell -File scripts/clean_scratch_dirs.ps1
powershell -File scripts/clean_scratch_dirs.ps1 -Root D:\other-checkout
powershell -File scripts/clean_scratch_dirs.ps1 -Execute -ConfirmPhrase "CLEAN-SCRATCH <hash>"
#>
[CmdletBinding()]
param(
    [switch]$Execute,
    [string]$ConfirmPhrase = "",
    # Repository root to clean; defaults to the checkout this script lives in.
    [string]$Root = "",
    # A directory written to within this many hours is treated as in use.
    [int]$RecentHours = 24
)

$ErrorActionPreference = "Stop"
if ($Root -eq "") { $Root = Join-Path $PSScriptRoot ".." }
$root = (Resolve-Path $Root).Path
if (-not (Test-Path (Join-Path $root ".git"))) { throw "SCRATCH_CLEAN_NOT_A_CHECKOUT: $root" }
if ($root.StartsWith("\\")) { throw "SCRATCH_CLEAN_UNC_ROOT_UNSUPPORTED: $root" }

# Frozen: directory-name patterns, evaluated only one level below the repository root.
# ``.tmp`` is deliberately absent: dev-server logs and PID files of other checkouts live there.
$patterns = @(
    ".codex-task-*", ".codex-tmp", ".codex-remote-attachments",
    "test-temp-*", "t07-pytest-*", "t6?",
    ".test-tmp", ".pytest-tmp", ".pytest_cache", ".test-artifacts"
)
$protected = @(
    ".git", ".tooling", ".venv", ".venv-*", "node_modules", "artifacts", "worktrees",
    "work", ".runtime", ".tmp", "apps", "packages", "services", "scripts", "ai_docs", ".claude"
)

function Test-Protected([string]$name) {
    foreach ($p in $protected) { if ($name -like $p) { return $true } }
    return $false
}

function Get-Blocker([object[]]$files) {
    # A file another process holds open cannot be opened without sharing; a read-only
    # file or ACL denial is reported separately, because Directory.Delete cannot remove it.
    foreach ($file in $files) {
        if ($file.PSIsContainer) { continue }
        if ($file.Attributes -band [IO.FileAttributes]::ReadOnly) { return "read-only file $($file.Name)" }
        try {
            $stream = [IO.File]::Open($file.FullName, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::None)
            $stream.Close()
        } catch [System.IO.IOException] {
            return "file open in another process: $($file.Name)"
        } catch [System.UnauthorizedAccessException] {
            return "access denied to $($file.Name)"
        }
    }
    return $null
}

$removable = @()
$skipped = @()
$recentLimit = (Get-Date).AddHours(-$RecentHours)
foreach ($dir in Get-ChildItem -Path $root -Directory -Force) {
    if (Test-Protected $dir.Name) { continue }
    $matched = $false
    foreach ($p in $patterns) { if ($dir.Name -like $p) { $matched = $true; break } }
    if (-not $matched) { continue }
    git -C $root check-ignore -q -- $dir.Name
    if ($LASTEXITCODE -ne 0) { $skipped += "$($dir.Name): not ignored by Git"; continue }
    $tracked = @(git -C $root ls-files -- $dir.Name)
    if ($tracked.Count -gt 0) { $skipped += "$($dir.Name): holds tracked files"; continue }
    if ($dir.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        $skipped += "$($dir.Name): reparse point (junction or symlink)"; continue
    }
    $files = $null
    try {
        $files = @(Get-ChildItem -LiteralPath $dir.FullName -Recurse -Force -ErrorAction Stop)
    } catch [System.UnauthorizedAccessException] {
        $skipped += "$($dir.Name): unreadable (remove with elevated rights)"; continue
    } catch {
        # PowerShell 5.1 cannot enumerate paths longer than 260 characters.
        $skipped += "$($dir.Name): cannot enumerate (long path or missing part): $($_.Exception.Message)"; continue
    }
    $nested = @($files | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint })
    if ($nested.Count -gt 0) { $skipped += "$($dir.Name): contains a reparse point"; continue }
    $recent = @($files | Where-Object { -not $_.PSIsContainer -and $_.LastWriteTime -gt $recentLimit })
    if ($recent.Count -gt 0) { $skipped += "$($dir.Name): written within $RecentHours h ($($recent[0].Name))"; continue }
    $blocker = Get-Blocker $files
    if ($null -ne $blocker) { $skipped += "$($dir.Name): $blocker"; continue }
    $bytes = ($files | Where-Object { -not $_.PSIsContainer } | Measure-Object -Property Length -Sum).Sum
    if ($null -eq $bytes) { $bytes = 0 }
    $removable += [pscustomobject]@{ Name = $dir.Name; Bytes = [int64]$bytes }
}

$removable = @($removable | Sort-Object -Property Name -Culture "en-US")
$total = ($removable | Measure-Object -Property Bytes -Sum).Sum
if ($null -eq $total) { $total = 0 }
$listing = ($removable | ForEach-Object { "$($_.Name)=$($_.Bytes)" }) -join "`n"
$sha = [BitConverter]::ToString(
    [System.Security.Cryptography.SHA256]::Create().ComputeHash(
        [System.Text.Encoding]::UTF8.GetBytes($listing))).Replace("-", "").ToLowerInvariant()
$phrase = "CLEAN-SCRATCH " + $sha.Substring(0, 16)

"Removable:"
$removable | Format-Table -AutoSize Name, @{ Name = "MiB"; Expression = { [math]::Round($_.Bytes / 1MB, 1) } } | Out-String
"{0} directories, {1:N1} MiB total" -f $removable.Count, ($total / 1MB)
if ($skipped.Count -gt 0) {
    ""
    "Skipped (not removed by this script):"
    $skipped | ForEach-Object { "  $_" }
}

if (-not $Execute) {
    ""
    "confirmation phrase: $phrase"
    exit 0
}
if ($ConfirmPhrase -ne $phrase) {
    Write-Error "SCRATCH_CLEAN_CONFIRMATION_MISMATCH: run the preview again and pass its phrase."
    exit 2
}
$failed = @()
foreach ($c in $removable) {
    $path = Join-Path $root $c.Name
    if (Test-Protected $c.Name) { $failed += "$($c.Name): protected"; continue }
    try {
        # Directory.Delete does not follow reparse points; the \\?\ prefix allows long paths.
        [IO.Directory]::Delete("\\?\$path", $true)
        "removed $($c.Name)"
    } catch {
        $failed += "$($c.Name): $($_.Exception.Message)"
    }
}
if ($failed.Count -gt 0) {
    ""
    "Failed:"
    $failed | ForEach-Object { "  $_" }
    exit 1
}
