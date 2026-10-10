<#
.SYNOPSIS
Copies the git-ignored data of a checkout to another drive incrementally and
verifies the copy with SHA-256 manifests (TASK-0953, plan
ai_docs/delivery/DISK_D_MIGRATION_PLAN_20261009.md).

.DESCRIPTION
Modes (exactly one):

-Inventory   Lists the git-ignored entries of -Source
             (git ls-files --others --ignored --exclude-standard --directory),
             classifies each as preserved, reproducible or worktree and writes
             INVENTORY.md to the run directory. Nothing is copied.
-Mode Initial  Copies every selected entry with robocopy while services may still
             run. Files that cannot be read (bit 8) mark the run INCOMPLETE but
             the script exits 0; bit 16 (fatal) exits 1. Size-only manifests of
             both sides are written for information.
-Mode Final  Same copy, then SHA-256 manifests of both sides are compared. Any
             robocopy result >= 8, bit 4 (mismatch), a missing or different file,
             or an extra destination file exits 1 (-AllowExtras is refused).
-VerifyOnly  No copy. Without -Manifest both sides are hashed and compared like
             Final. With -Manifest the destination is compared with saved source
             manifests only: missing or different files fail, files that are not
             in the manifest are ignored and the source is never read.

Entries: by default all "preserved" entries of the inventory; preserved entries
that are not in the known list of the plan are copied and reported as "new".
-Directories selects entries explicitly (paths relative to -Source, "./" is
stripped, "." and ".." segments and absolute paths are rejected; a comma
separated string is accepted because powershell.exe -File cannot pass arrays).
The worktree roots "worktrees" and ".claude/worktrees" are never copied, even
when listed or when a parent such as ".claude" is selected: their .git files
point at the source repository; TASK-0954 secures their data.

Inside every directory entry the directory names node_modules, .next,
__pycache__, .pytest_cache and *pytest-run* (unreadable pytest temp roots
left by earlier runs, access denied) are excluded; inside .runtime also pytest-*,
task0* and t928* (temporary test output) and *.log files (reproducible logs).
The manifests and robocopy use the same exclusions, so a verification never
reports them; every report line states how many files each rule skipped.

Paths under .tooling are written to manifests, summaries, error messages and
robocopy logs as "redacted:<sha256 of the lower-case relative path>" so signing
key file names never reach a log.

Logs and manifests go to -LogRoot\<timestamp>-<mode>; -LogRoot must lie
outside both the source and the destination. robocopy output is captured in
memory and written only after redaction. Entries below .tooling cannot be
selected on their own.

-TimeoutMinutes (or -TimeoutSeconds, which overrides it) limits the whole
work on one entry: listing, copy and hashing; exceeding it exits 2. -Mirror
never deletes anything when the copy of the entry failed or any listing or
hash error occurred.

Exit codes: 0 success (Initial may be INCOMPLETE); 1 validation error, fatal
robocopy error or failed verification; 2 robocopy timeout.

This file is ASCII-only so Windows PowerShell 5.1 parses it without a BOM.

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/sync_data_directories_to_d.ps1 -Inventory
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/sync_data_directories_to_d.ps1 -Mode Initial
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/sync_data_directories_to_d.ps1 -Mode Final -Directories "examples\imgs,work"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/sync_data_directories_to_d.ps1 -VerifyOnly -Manifest D:\game_predictor_backup\sync-logs\20261010-0500-Final
#>
[CmdletBinding()]
param(
    [string]$Source = 'C:\Users\tuszy\Documents\game_predicotr',
    [string]$Destination = 'D:\game_predicotr',
    [ValidateSet('', 'Initial', 'Final')]
    [string]$Mode = '',
    [switch]$Inventory,
    [switch]$VerifyOnly,
    [string[]]$Manifest = @(),
    [string[]]$Directories = @(),
    [string]$LogRoot = 'D:\game_predictor_backup\sync-logs',
    [switch]$AllowExtras,
    [switch]$Mirror,
    [switch]$Confirm,
    [string]$MirrorApprovedList = '',
    [ValidateRange(1, 1440)]
    [int]$TimeoutMinutes = 240,
    [ValidateRange(0, 86400)]
    [int]$TimeoutSeconds = 0,
    [ValidateRange(1, 64)]
    [int]$Threads = 8
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
try { [Console]::OutputEncoding = $utf8NoBom } catch { }
$OutputEncoding = $utf8NoBom

$script:WorktreeRoots = @('worktrees', '.claude/worktrees')
$script:ReproduciblePatterns = @(
    '(^|/)node_modules$', '(^|/)\.next$', '^\.venv[^/]*$', '^\.pnpm-store$',
    '(^|/)__pycache__$', '(^|/)\.pytest_cache$', '(^|/)\.mypy_cache$', '(^|/)\.ruff_cache$',
    '^(packages|apps)/[^/]+/dist$', '\.tsbuildinfo$', '\.egg-info$', '^\.claude/scheduled_tasks\.lock$',
    '(^|/)next-env\.d\.ts$', '^(apps/[^/]+/)?\.expo$', '^((apps|packages)/[^/]+/)?coverage$',
    '^\.t$', '^\.test-tmp$', '^\.pytest-tmp$', '^test-temp-', '^t07-pytest-', '^t6.$', '^\.codex-task-'
)
# Preserved entries that existed when the plan was written. Any other preserved
# entry is still copied but reported as "new" so the operator can review it.
$script:KnownPreservedPatterns = @(
    '^artifacts(/|$)', '^imports(/|$)', '^examples/imgs(/|$)', '^\.runtime$', '^\.tooling$',
    '^\.tmp$', '^work$', '^v7-output$', '^\.claude/settings\.local\.json$', '^\.claude$',
    '^TEMP PLAN .*\.md$', '^tmp-.*\.(out|err)$', '^\.serena/'
)
$script:GlobalExcludeDirs = @('node_modules', '.next', '__pycache__', '.pytest_cache', '*pytest-run*')
$script:RuntimeExcludeDirs = @('pytest-*', 'task0*', 't928*')
$script:RuntimeExcludeFiles = @('*.log')
$script:Sha = [System.Security.Cryptography.SHA256]::Create()

function Fail([string]$message, [int]$code = 1) {
    # Protect-Text and $script:Sha exist before any call reaches this point.
    Write-Host ('ERROR: ' + (Protect-Text $message))
    exit $code
}

function Split-List([string[]]$values) {
    $result = New-Object System.Collections.Generic.List[string]
    foreach ($value in $values) {
        if ($null -eq $value) { continue }
        foreach ($part in ($value -split ',')) {
            $trimmed = $part.Trim()
            if ($trimmed) { $result.Add($trimmed) }
        }
    }
    return , $result.ToArray()
}

function ConvertTo-Rel([string]$value) {
    $rel = ($value -replace '\\', '/').Trim().TrimEnd('/')
    while ($rel.StartsWith('./')) { $rel = $rel.Substring(2) }
    $rel = $rel -replace '/+', '/'
    if (-not $rel -or $rel -eq '.') { Fail "empty or root entry is not allowed: '$value'" }
    if ($rel -match '^[A-Za-z]:' -or $rel.StartsWith('/')) { Fail "entry must be relative to -Source: '$value'" }
    foreach ($segment in $rel.Split('/')) {
        if ($segment -eq '..' -or $segment -eq '.') { Fail "entry must not contain '.' or '..' segments: '$value'" }
    }
    return $rel
}

function Test-RelUnder([string]$rel, [string]$root) {
    return $rel.Equals($root, [System.StringComparison]::OrdinalIgnoreCase) -or
        $rel.StartsWith($root + '/', [System.StringComparison]::OrdinalIgnoreCase)
}

function Protect-Text([string]$text) {
    # Signing key names under .tooling must never reach a log or report. File
    # names may contain spaces, so everything after ".tooling\" up to the end of
    # the line (or a closing quote) is replaced by its hash.
    if ($null -eq $text) { return $text }
    return [regex]::Replace($text, '(?i)\.tooling[\\/][^\r\n]*', {
            param($match)
            'redacted:' + (Get-StringSha256 (($match.Value -replace '\\', '/').TrimEnd().TrimEnd('/').ToLowerInvariant()))
        })
}

$script:Deadline = [datetime]::MaxValue
$script:EntryTimeoutSeconds = if ($TimeoutSeconds -gt 0) { $TimeoutSeconds } else { $TimeoutMinutes * 60 }
function Assert-Deadline {
    if ((Get-Date) -gt $script:Deadline) { throw (New-Object System.TimeoutException('entry time limit exceeded')) }
}

function ConvertTo-LongPath([string]$path) {
    if ($path.StartsWith('\\?\')) { return $path }
    if ($path.StartsWith('\\')) { return '\\?\UNC\' + $path.Substring(2) }
    return '\\?\' + $path
}

function Get-StringSha256([string]$text) {
    $bytes = $script:Sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($text))
    return ([System.BitConverter]::ToString($bytes) -replace '-', '').ToLowerInvariant()
}

function Get-FileSha256([string]$path) {
    # Chunked hashing so the per-entry time limit also stops a large file;
    # the deadline is also checked before and after, so empty files count.
    Assert-Deadline
    $stream = New-Object System.IO.FileStream($path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read,
        ([System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete), 1048576)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $buffer = New-Object byte[] 4194304
        while (($read = $stream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            [void]$sha.TransformBlock($buffer, 0, $read, $null, 0)
            Assert-Deadline
        }
        [void]$sha.TransformFinalBlock($buffer, 0, 0)
        $bytes = $sha.Hash
        Assert-Deadline
    }
    finally { $stream.Dispose(); $sha.Dispose() }
    return ([System.BitConverter]::ToString($bytes) -replace '-', '').ToLowerInvariant()
}

function Get-Key([string]$relPath) {
    if (Test-RelUnder $relPath '.tooling') {
        return 'redacted:' + (Get-StringSha256 $relPath.ToLowerInvariant())
    }
    return $relPath
}

function Get-SafeName([string]$rel) {
    # The hash suffix keeps names unique: "work/a_b" and "work/a/b" would
    # otherwise both become "work_a_b" and overwrite each other's results.
    $readable = ($rel -replace '[\\/ :*?"<>|'']', '_')
    return '{0}-{1}' -f $readable, (Get-StringSha256 $rel.ToLowerInvariant()).Substring(0, 12)
}

function Test-WorktreeRoot([string]$rel) {
    foreach ($root in $script:WorktreeRoots) {
        if (Test-RelUnder $rel $root) { return $true }
    }
    return $false
}

function Get-EntryClass([string]$rel) {
    if (Test-WorktreeRoot $rel) { return 'worktree' }
    foreach ($pattern in $script:ReproduciblePatterns) {
        if ($rel -match $pattern) { return 'reproducible' }
    }
    return 'preserved'
}

function Test-KnownPreserved([string]$rel) {
    foreach ($pattern in $script:KnownPreservedPatterns) {
        if ($rel -match $pattern) { return $true }
    }
    return $false
}

# An explicitly selected entry must not itself be (or lie inside) something the
# copy excludes: a reproducible entry or a directory matched by an exclusion.
function Get-SelectionExclusion([string]$rel) {
    $segments = $rel.Split('/')
    for ($i = 0; $i -lt $segments.Count; $i++) {
        $prefix = ($segments[0..$i] -join '/')
        if ((Get-EntryClass $prefix) -eq 'reproducible') { return "reproducible entry $prefix" }
        foreach ($pattern in $script:GlobalExcludeDirs) {
            if ($segments[$i] -like $pattern) { return "excluded directory name $pattern" }
        }
        if ($i -ge 1 -and $segments[0] -ieq '.runtime') {
            foreach ($pattern in $script:RuntimeExcludeDirs) {
                if ($segments[$i] -like $pattern) { return "excluded .runtime directory $pattern" }
            }
            if ($i -eq $segments.Count - 1) {
                foreach ($pattern in $script:RuntimeExcludeFiles) {
                    if ($segments[$i] -like $pattern) { return "excluded .runtime file $pattern" }
                }
            }
        }
    }
    return $null
}

function Get-EntryExcludeDirs([string]$rel) {
    $result = @($script:GlobalExcludeDirs)
    if ($rel -ieq '.runtime') { $result += $script:RuntimeExcludeDirs }
    return , $result
}

function Get-EntryExcludeFiles([string]$rel) {
    if ($rel -ieq '.runtime') { return , @($script:RuntimeExcludeFiles) }
    return , @()
}

# Worktree roots nested below a selected entry (for example ".claude" contains
# ".claude/worktrees"); they are excluded at every level of the copy and listing.
function Get-EntryExcludePaths([string]$rel) {
    $result = New-Object System.Collections.Generic.List[string]
    foreach ($root in $script:WorktreeRoots) {
        if ($root.StartsWith($rel + '/', [System.StringComparison]::OrdinalIgnoreCase)) { $result.Add($root) }
    }
    return , $result.ToArray()
}

function Get-FileCount([string]$directory) {
    # Manual traversal so the entry deadline also stops a large excluded tree.
    [int64]$count = 0
    $stack = New-Object System.Collections.Generic.Stack[string]
    $stack.Push($directory)
    try {
        while ($stack.Count -gt 0) {
            Assert-Deadline
            $info = New-Object System.IO.DirectoryInfo($stack.Pop())
            foreach ($sub in $info.EnumerateDirectories()) {
                Assert-Deadline
                if (($sub.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -eq 0) { $stack.Push($sub.FullName) }
            }
            foreach ($file in $info.EnumerateFiles()) {
                $count++
                if (($count % 2000) -eq 0) { Assert-Deadline }
            }
        }
        return $count
    }
    catch [System.TimeoutException] { throw }
    catch { return [int64]-1 }
}

# One time budget per entry across all phases (pre-copy listing, copy, listing
# and hashing): each phase gets the remaining time of that entry only.
$script:EntryUsedSeconds = @{}
function Start-EntryBudget([string]$rel) {
    if (-not $script:EntryUsedSeconds.ContainsKey($rel)) { $script:EntryUsedSeconds[$rel] = 0.0 }
    $script:EntryPhaseStart = Get-Date
    $script:Deadline = $script:EntryPhaseStart.AddSeconds($script:EntryTimeoutSeconds - $script:EntryUsedSeconds[$rel])
    Assert-Deadline
}
function Stop-EntryBudget([string]$rel) {
    Assert-Deadline
    $script:EntryUsedSeconds[$rel] += ((Get-Date) - $script:EntryPhaseStart).TotalSeconds
    $script:Deadline = [datetime]::MaxValue
}

function Get-IgnoredEntries([string]$root) {
    # Ignored entries plus untracked, not ignored ones (for example v7-output/):
    # both exist only in this directory, so both belong to the copy.
    $entries = New-Object System.Collections.Generic.List[object]
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($kind in @('ignored', 'untracked')) {
        if ($kind -eq 'ignored') {
            $lines = & git -c core.quotepath=false -C $root ls-files --others --ignored --exclude-standard --directory
        }
        else {
            $lines = & git -c core.quotepath=false -C $root ls-files --others --exclude-standard --directory
        }
        if ($LASTEXITCODE -ne 0) { Fail "git ls-files ($kind) failed in $root (exit $LASTEXITCODE)." }
        foreach ($line in @($lines)) {
            $text = [string]$line
            if (-not $text) { continue }
            $rel = ConvertTo-Rel $text
            if (-not $seen.Add($rel)) { continue }
            $class = Get-EntryClass $rel
            $entries.Add([pscustomobject]@{
                    Rel = $rel; Class = $class; Untracked = ($kind -eq 'untracked')
                    New = ($class -eq 'preserved' -and -not (Test-KnownPreserved $rel))
                })
        }
    }
    return , $entries.ToArray()
}

function Get-EntryFiles([string]$root, [string]$rel, [switch]$CountExcluded) {
    $excludeDirs = Get-EntryExcludeDirs $rel
    $excludeFiles = Get-EntryExcludeFiles $rel
    $excludePaths = Get-EntryExcludePaths $rel
    $map = New-Object 'System.Collections.Generic.Dictionary[string,object]' ([System.StringComparer]::OrdinalIgnoreCase)
    $errors = New-Object System.Collections.Generic.List[string]
    $excluded = [ordered]@{}
    $base = ConvertTo-LongPath (Join-Path $root ($rel -replace '/', '\'))
    if ([System.IO.File]::Exists($base)) {
        $info = New-Object System.IO.FileInfo($base)
        $map[$rel] = [pscustomobject]@{ Path = $base; Size = [int64]$info.Length }
        return @{ Files = $map; Errors = $errors; Exists = $true; Excluded = $excluded }
    }
    if (-not [System.IO.Directory]::Exists($base)) {
        return @{ Files = $map; Errors = $errors; Exists = $false; Excluded = $excluded }
    }
    $prefixLength = $base.Length
    [int64]$seen = 0
    $stack = New-Object System.Collections.Generic.Stack[string]
    $stack.Push($base)
    while ($stack.Count -gt 0) {
        Assert-Deadline
        $directory = $stack.Pop()
        try {
            $info = New-Object System.IO.DirectoryInfo($directory)
            foreach ($sub in $info.EnumerateDirectories()) {
                Assert-Deadline
                if (($sub.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { continue }
                $subRel = $rel + ($sub.FullName.Substring($prefixLength) -replace '\\', '/')
                $rule = $null
                foreach ($pattern in $excludeDirs) {
                    if ($sub.Name -like $pattern) { $rule = "dir:$pattern"; break }
                }
                if ($null -eq $rule) {
                    foreach ($path in $excludePaths) {
                        if ($subRel.Equals($path, [System.StringComparison]::OrdinalIgnoreCase)) { $rule = "worktree:$path"; break }
                    }
                }
                if ($null -eq $rule) { $stack.Push($sub.FullName); continue }
                if ($CountExcluded) {
                    $count = Get-FileCount $sub.FullName
                    if (-not $excluded.Contains($rule)) { $excluded[$rule] = [int64]0 }
                    if ($count -lt 0 -or $excluded[$rule] -lt 0) { $excluded[$rule] = [int64]-1 } else { $excluded[$rule] += $count }
                }
            }
            foreach ($file in $info.EnumerateFiles()) {
                $seen++
                if (($seen % 2000) -eq 0) { Assert-Deadline }
                $fileRule = $null
                foreach ($pattern in $excludeFiles) {
                    if ($file.Name -like $pattern) { $fileRule = "file:$pattern"; break }
                }
                if ($null -ne $fileRule) {
                    if ($CountExcluded) {
                        if (-not $excluded.Contains($fileRule)) { $excluded[$fileRule] = [int64]0 }
                        $excluded[$fileRule] += 1
                    }
                    continue
                }
                $relPath = $rel + ($file.FullName.Substring($prefixLength) -replace '\\', '/')
                $map[$relPath] = [pscustomobject]@{ Path = $file.FullName; Size = [int64]$file.Length }
            }
        }
        catch [System.TimeoutException] { throw }
        catch {
            $errors.Add((Protect-Text ('{0}: {1}' -f (Get-Key ($rel + ($directory.Substring($prefixLength) -replace '\\', '/'))), $_.Exception.Message)))
        }
    }
    return @{ Files = $map; Errors = $errors; Exists = $true; Excluded = $excluded }
}

function Format-Excluded($excluded) {
    if ($null -eq $excluded -or $excluded.Count -eq 0) { return 'excluded=none' }
    $parts = foreach ($key in $excluded.Keys) {
        $value = $excluded[$key]
        '{0}:{1}' -f $key, $(if ($value -lt 0) { 'unreadable' } else { $value })
    }
    return 'excluded=' + ($parts -join ',')
}

function Get-TotalBytes($files) {
    [int64]$sum = 0
    foreach ($value in $files.Values) { $sum += $value.Size }
    return $sum
}

function Build-Manifest($files, [bool]$withHash, $errors) {
    $manifest = New-Object 'System.Collections.Generic.Dictionary[string,object]' ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($pair in $files.GetEnumerator()) {
        Assert-Deadline
        $hash = '-'
        if ($withHash) {
            try { $hash = Get-FileSha256 $pair.Value.Path }
            catch [System.TimeoutException] { throw }
            catch { $errors.Add((Protect-Text ('{0}: {1}' -f (Get-Key $pair.Key), $_.Exception.Message))); $hash = 'ERROR' }
        }
        $manifest[(Get-Key $pair.Key)] = [pscustomobject]@{ Size = $pair.Value.Size; Hash = $hash }
    }
    return $manifest
}

function Write-Manifest([string]$path, [string]$rel, [string]$root, [string]$kind, $manifest) {
    $keys = [string[]]@($manifest.Keys)
    [System.Array]::Sort($keys, [System.StringComparer]::Ordinal)
    $builder = New-Object System.Text.StringBuilder
    [void]$builder.AppendLine(("# entry={0}`tkind={1}`troot={2}" -f $rel, $kind, $root))
    foreach ($key in $keys) {
        $value = $manifest[$key]
        [void]$builder.AppendLine(("{0}`t{1}`t{2}" -f $key, $value.Size, $value.Hash))
    }
    [System.IO.File]::WriteAllText($path, $builder.ToString(), $utf8NoBom)
}

function Read-Manifest([string]$path) {
    $lines = [System.IO.File]::ReadAllLines($path, $utf8NoBom)
    if ($lines.Count -eq 0 -or -not $lines[0].StartsWith('# ')) { Fail "manifest without header: $path" }
    $header = @{}
    foreach ($field in $lines[0].Substring(2).Split("`t")) {
        $index = $field.IndexOf('=')
        if ($index -gt 0) { $header[$field.Substring(0, $index)] = $field.Substring($index + 1) }
    }
    if (-not $header.ContainsKey('entry') -or $header['kind'] -ne 'sha256') { Fail "manifest is not a sha256 manifest: $path" }
    $manifest = New-Object 'System.Collections.Generic.Dictionary[string,object]' ([System.StringComparer]::OrdinalIgnoreCase)
    for ($i = 1; $i -lt $lines.Count; $i++) {
        if (-not $lines[$i]) { continue }
        $parts = $lines[$i].Split("`t")
        if ($parts.Count -ne 3) { Fail "malformed manifest line $($i + 1) in $path" }
        $manifest[$parts[0]] = [pscustomobject]@{ Size = [int64]$parts[1]; Hash = $parts[2] }
    }
    return @{ Entry = $header['entry']; Manifest = $manifest }
}

function Compare-Manifests($sourceManifest, $destinationManifest, [bool]$checkHash, [bool]$reportExtras) {
    $missing = New-Object System.Collections.Generic.List[string]
    $different = New-Object System.Collections.Generic.List[string]
    $extra = New-Object System.Collections.Generic.List[string]
    foreach ($pair in $sourceManifest.GetEnumerator()) {
        Assert-Deadline
        if (-not $destinationManifest.ContainsKey($pair.Key)) { $missing.Add($pair.Key); continue }
        $other = $destinationManifest[$pair.Key]
        if ($other.Size -ne $pair.Value.Size) { $different.Add($pair.Key); continue }
        if ($checkHash -and ($other.Hash -ne $pair.Value.Hash -or $other.Hash -eq 'ERROR')) { $different.Add($pair.Key) }
    }
    if ($reportExtras) {
        foreach ($key in $destinationManifest.Keys) {
            Assert-Deadline
            if (-not $sourceManifest.ContainsKey($key)) { $extra.Add($key) }
        }
    }
    return @{ Missing = $missing; Different = $different; Extra = $extra }
}

function Write-Comparison([string]$path, $comparison) {
    $builder = New-Object System.Text.StringBuilder
    foreach ($kind in @('Missing', 'Different', 'Extra')) {
        foreach ($key in $comparison[$kind]) { [void]$builder.AppendLine(("{0}`t{1}" -f $kind.ToLowerInvariant(), $key)) }
    }
    [System.IO.File]::WriteAllText($path, $builder.ToString(), $utf8NoBom)
}

function Get-RobocopyFailedCount([string[]]$lines) {
    $pattern = '^\s*\S+\s*:\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$'
    $rows = @($lines | Where-Object { $_ -match $pattern })
    if ($rows.Count -lt 2) { return $null }
    $null = $rows[1] -match $pattern
    return @{ Total = [int64]$Matches[1]; Copied = [int64]$Matches[2]; Skipped = [int64]$Matches[3]; Mismatch = [int64]$Matches[4]; Failed = [int64]$Matches[5]; Extras = [int64]$Matches[6] }
}

function Write-ProtectedLog([string]$logPath, [string]$text) {
    # robocopy writes to stdout (no /LOG), so raw paths never touch the disk;
    # only the redacted text is written.
    $lines = @($text -split "`r?`n")
    $protected = foreach ($line in $lines) { Protect-Text $line }
    [System.IO.File]::WriteAllLines($logPath, [string[]]@($protected), $utf8NoBom)
    return , $lines
}

function Invoke-Robocopy([string]$rel, [string]$logPath) {
    $sourcePath = Join-Path $Source ($rel -replace '/', '\')
    $destinationPath = Join-Path $Destination ($rel -replace '/', '\')
    if ([System.IO.File]::Exists((ConvertTo-LongPath $sourcePath))) {
        $arguments = '"{0}" "{1}" "{2}" /COPY:DAT /R:1 /W:1 /NP /NFL /NDL' -f (Split-Path $sourcePath -Parent), (Split-Path $destinationPath -Parent), (Split-Path $sourcePath -Leaf)
    }
    else {
        # Assign first: the helpers return wrapped arrays, and piping them
        # directly would pass the whole array as one quoted robocopy argument.
        $excludeDirs = Get-EntryExcludeDirs $rel
        $excludePaths = Get-EntryExcludePaths $rel
        $excludeFiles = Get-EntryExcludeFiles $rel
        $xd = @()
        foreach ($pattern in $excludeDirs) { $xd += '"' + $pattern + '"' }
        foreach ($path in $excludePaths) { $xd += '"' + (Join-Path $Source ($path -replace '/', '\')) + '"' }
        $xf = @()
        foreach ($pattern in $excludeFiles) { $xf += '"' + $pattern + '"' }
        $fileExclusion = if ($xf.Count -gt 0) { ' /XF ' + ($xf -join ' ') } else { '' }
        $arguments = '"{0}" "{1}" /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /MT:{2} /NP /NFL /NDL /XJ /XD {3}{4}' -f $sourcePath, $destinationPath, $Threads, ($xd -join ' '), $fileExclusion
    }
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = 'robocopy.exe'
    $startInfo.Arguments = $arguments
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.StandardOutputEncoding = [System.Text.Encoding]::GetEncoding([System.Globalization.CultureInfo]::CurrentCulture.TextInfo.OEMCodePage)
    $process = [System.Diagnostics.Process]::Start($startInfo)
    $outputTask = $process.StandardOutput.ReadToEndAsync()
    $remaining = [int][Math]::Max(1000, [Math]::Min([int]::MaxValue, ($script:Deadline - (Get-Date)).TotalMilliseconds))
    if (-not $process.WaitForExit($remaining)) {
        try { $process.Kill() } catch { }
        $null = $process.WaitForExit(10000)
        $null = Write-ProtectedLog $logPath $outputTask.Result
        return @{ Code = -1; TimedOut = $true; Counts = $null }
    }
    $process.WaitForExit()
    $code = $process.ExitCode
    $lines = Write-ProtectedLog $logPath $outputTask.Result
    return @{ Code = $code; TimedOut = $false; Counts = (Get-RobocopyFailedCount $lines) }
}

# --- validation -------------------------------------------------------------

$modeCount = @($Inventory.IsPresent, $VerifyOnly.IsPresent, [bool]$Mode) | Where-Object { $_ } | Measure-Object | Select-Object -ExpandProperty Count
if ($modeCount -ne 1) { Fail 'choose exactly one of -Inventory, -VerifyOnly or -Mode Initial|Final.' }
if ($Mirror -and ($Mode -ne 'Final' -or -not $Confirm -or -not $MirrorApprovedList)) {
    Fail '-Mirror needs -Mode Final, -Confirm and -MirrorApprovedList with the extra destination keys approved for deletion.'
}
if ($Manifest.Count -gt 0 -and -not $VerifyOnly) { Fail '-Manifest is only valid with -VerifyOnly.' }
if ($AllowExtras -and -not ($VerifyOnly -and $Manifest.Count -eq 0)) {
    Fail '-AllowExtras is only valid with -VerifyOnly without -Manifest; Final requires equal manifests (use -Mirror for approved extras).'
}

$Source = [System.IO.Path]::GetFullPath($Source).TrimEnd('\')
$Destination = [System.IO.Path]::GetFullPath($Destination).TrimEnd('\')
if ($Source -eq $Destination -or $Destination.StartsWith($Source + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
    Fail 'destination must differ from the source and must not be inside it.'
}
$manifestOnly = $VerifyOnly -and $Manifest.Count -gt 0
if (-not $manifestOnly -and -not (Test-Path -LiteralPath $Source -PathType Container)) { Fail "source not found: $Source" }
$LogRoot = [System.IO.Path]::GetFullPath($LogRoot).TrimEnd('\')
foreach ($tree in @($Source, $Destination)) {
    if ($LogRoot.Equals($tree, [System.StringComparison]::OrdinalIgnoreCase) -or
        $LogRoot.StartsWith($tree + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        Fail "-LogRoot must be outside the source and the destination: $LogRoot"
    }
}

$modeName = if ($Inventory) { 'Inventory' } elseif ($VerifyOnly) { 'VerifyOnly' } else { $Mode }
$runDirectory = Join-Path $LogRoot ('{0}-{1}' -f (Get-Date -Format 'yyyyMMdd-HHmmss'), $modeName)
New-Item -ItemType Directory -Force -Path $runDirectory | Out-Null
$summaryPath = Join-Path $runDirectory 'SUMMARY.txt'
function Report([string]$line) {
    $safeLine = Protect-Text $line
    Write-Host $safeLine
    Add-Content -LiteralPath $summaryPath -Value $safeLine -Encoding UTF8
}
Report ('mode={0} source={1} destination={2} started={3:o}' -f $modeName, $Source, $Destination, (Get-Date))

# --- VerifyOnly against saved manifests --------------------------------------

if ($manifestOnly) {
    $manifestFiles = New-Object System.Collections.Generic.List[string]
    foreach ($item in (Split-List $Manifest)) {
        if (Test-Path -LiteralPath $item -PathType Container) {
            Get-ChildItem -LiteralPath $item -Filter '*.source.tsv' | ForEach-Object { $manifestFiles.Add($_.FullName) }
        }
        elseif (Test-Path -LiteralPath $item -PathType Leaf) { $manifestFiles.Add($item) }
        else { Fail "manifest not found: $item" }
    }
    if ($manifestFiles.Count -eq 0) { Fail 'no *.source.tsv manifests found.' }
    $failed = $false
    foreach ($file in $manifestFiles) {
        $script:Deadline = (Get-Date).AddSeconds($script:EntryTimeoutSeconds)
        $rel = '(unread manifest)'
        try {
            $saved = Read-Manifest $file
            $rel = $saved.Entry
            # Only the files listed in the saved manifest are checked. Plain keys
            # are resolved directly; redacted keys (.tooling) need a listing of the
            # entry, and listing errors count only when a redacted key stays
            # unresolved. New destination files and unreadable new branches are
            # outside the contract and never fail the check.
            $errors = New-Object System.Collections.Generic.List[string]
            $current = New-Object 'System.Collections.Generic.Dictionary[string,object]' ([System.StringComparer]::OrdinalIgnoreCase)
            $redactedKeys = New-Object System.Collections.Generic.List[string]
            foreach ($key in $saved.Manifest.Keys) {
                Assert-Deadline
                if ($key.StartsWith('redacted:')) { $redactedKeys.Add($key); continue }
                $path = ConvertTo-LongPath (Join-Path $Destination ($key -replace '/', '\'))
                if (-not [System.IO.File]::Exists($path)) { continue }
                try {
                    $size = (New-Object System.IO.FileInfo($path)).Length
                    $current[$key] = [pscustomobject]@{ Size = [int64]$size; Hash = (Get-FileSha256 $path) }
                }
                catch [System.TimeoutException] { throw }
                catch { $errors.Add((Protect-Text ('{0}: {1}' -f $key, $_.Exception.Message))); $current[$key] = [pscustomobject]@{ Size = [int64]-1; Hash = 'ERROR' } }
            }
            if ($redactedKeys.Count -gt 0) {
                $listing = Get-EntryFiles $Destination $rel
                $wanted = New-Object 'System.Collections.Generic.Dictionary[string,object]' ([System.StringComparer]::OrdinalIgnoreCase)
                foreach ($pair in $listing.Files.GetEnumerator()) {
                    if ($saved.Manifest.ContainsKey((Get-Key $pair.Key)) -and (Get-Key $pair.Key).StartsWith('redacted:')) { $wanted[$pair.Key] = $pair.Value }
                }
                $resolved = Build-Manifest $wanted $true $errors
                foreach ($pair in $resolved.GetEnumerator()) { $current[$pair.Key] = $pair.Value }
                $unresolved = @($redactedKeys | Where-Object { -not $current.ContainsKey($_) }).Count
                if ($unresolved -gt 0) { foreach ($e in $listing.Errors) { $errors.Add($e) } }
            }
            $comparison = Compare-Manifests $saved.Manifest $current $true $false
            Assert-Deadline
        }
        catch [System.TimeoutException] {
            Report ('TIMEOUT entry={0} after {1} s' -f (Get-Key $rel), $script:EntryTimeoutSeconds)
            Report 'RESULT: TIMEOUT'
            exit 2
        }
        Write-Comparison (Join-Path $runDirectory ((Get-SafeName (Get-Key $rel)) + '.compare.tsv')) $comparison
        $ok = $comparison.Missing.Count -eq 0 -and $comparison.Different.Count -eq 0 -and $errors.Count -eq 0
        if (-not $ok) { $failed = $true }
        Report ('{0} entry={1} files={2} missing={3} different={4} errors={5}' -f $(if ($ok) { 'OK' } else { 'FAIL' }), $rel, $saved.Manifest.Count, $comparison.Missing.Count, $comparison.Different.Count, $errors.Count)
        foreach ($key in @($comparison.Missing | Select-Object -First 10)) { Report "  missing $key" }
        foreach ($key in @($comparison.Different | Select-Object -First 10)) { Report "  different $key" }
        foreach ($e in @($errors | Select-Object -First 10)) { Report "  error $e" }
    }
    Report $(if ($failed) { 'RESULT: FAILED' } else { 'RESULT: OK' })
    if ($failed) { exit 1 } else { exit 0 }
}

# --- inventory and entry selection ------------------------------------------

$inventoryEntries = Get-IgnoredEntries $Source
if ($Inventory) {
    $inventoryPath = Join-Path $runDirectory 'INVENTORY.md'
    $builder = New-Object System.Text.StringBuilder
    [void]$builder.AppendLine("# Ignored entries of $Source")
    [void]$builder.AppendLine('')
    [void]$builder.AppendLine('| Class | New | Entry | Files | Bytes | Excluded |')
    [void]$builder.AppendLine('|---|---|---|---|---|---|')
    foreach ($entry in ($inventoryEntries | Sort-Object Class, Rel)) {
        $files = '-'; $bytes = '-'; $excludedText = '-'
        if ($entry.Class -eq 'preserved') {
            $listing = Get-EntryFiles $Source $entry.Rel -CountExcluded
            $files = $listing.Files.Count; $bytes = Get-TotalBytes $listing.Files
            $excludedText = Format-Excluded $listing.Excluded
        }
        [void]$builder.AppendLine((Protect-Text ('| {0} | {1} | {2} | {3} | {4} | {5} |' -f $entry.Class, ((@($(if ($entry.New) { 'new' }), $(if ($entry.Untracked) { 'untracked' })) | Where-Object { $_ }) -join ','), $entry.Rel, $files, $bytes, $excludedText)))
    }
    [System.IO.File]::WriteAllText($inventoryPath, $builder.ToString(), $utf8NoBom)
    foreach ($class in @('preserved', 'reproducible', 'worktree')) {
        $names = @($inventoryEntries | Where-Object { $_.Class -eq $class } | ForEach-Object { $_.Rel })
        Report ('{0} ({1}): {2}' -f $class, $names.Count, ($names -join ', '))
    }
    $newNames = @($inventoryEntries | Where-Object { $_.New } | ForEach-Object { $_.Rel })
    Report ('new ({0}): {1}' -f $newNames.Count, ($newNames -join ', '))
    Report "inventory written to $inventoryPath"
    Report 'RESULT: OK'
    exit 0
}

$selected = New-Object System.Collections.Generic.List[string]
if ($Directories.Count -gt 0) {
    foreach ($item in (Split-List $Directories)) {
        $rel = ConvertTo-Rel $item
        if (Test-WorktreeRoot $rel) { Report "WARNING: skipped worktree root $rel (secured by TASK-0954, never copied)"; continue }
        $exclusion = Get-SelectionExclusion $rel
        if ($null -ne $exclusion) { Report "WARNING: skipped $rel ($exclusion; never copied)"; continue }
        if ((Test-RelUnder $rel '.tooling') -and -not ($rel -ieq '.tooling')) {
            # A path below .tooling would put a key file name into headers and
            # result file names; only the whole directory may be selected.
            Fail 'select .tooling as a whole; entries below it are not allowed.'
        }
        $selected.Add($rel)
    }
}
else {
    foreach ($entry in $inventoryEntries) {
        if ($entry.Class -eq 'preserved') {
            $selected.Add($entry.Rel)
            if ($entry.New) { Report "NOTICE: new preserved entry $($entry.Rel) (copied; review it)" }
        }
    }
}
if ($selected.Count -eq 0) { Fail 'no entries selected.' }
Report ('entries ({0}): {1}' -f $selected.Count, ($selected -join ', '))

# --- pre-copy listing and free space -----------------------------------------

$doCopy = -not $VerifyOnly
[int64]$needed = 0
foreach ($rel in $selected) {
    try {
        Start-EntryBudget $rel
        $sourceListing = Get-EntryFiles $Source $rel
        if (-not $sourceListing.Exists) { Fail "selected entry not found in source: $rel" }
        if ($doCopy) {
            # Only source files missing or different in size on the destination
            # need space; unrelated destination files never offset new data.
            $destinationListing = Get-EntryFiles $Destination $rel
            foreach ($pair in $sourceListing.Files.GetEnumerator()) {
                $other = $null
                if (-not $destinationListing.Files.TryGetValue($pair.Key, [ref]$other) -or $other.Size -ne $pair.Value.Size) {
                    $needed += $pair.Value.Size
                }
            }
        }
        Stop-EntryBudget $rel
    }
    catch [System.TimeoutException] {
        Report ('TIMEOUT entry={0} while listing, after {1} s' -f $rel, $script:EntryTimeoutSeconds)
        Report 'RESULT: TIMEOUT'
        exit 2
    }
}
if ($doCopy) {
    $drive = Get-PSDrive -Name $Destination.Substring(0, 1)
    $margin = [int64]5GB
    Report ('free_bytes={0} needed_bytes={1} margin_bytes={2}' -f $drive.Free, $needed, $margin)
    if ($drive.Free -lt ($needed + $margin)) { Fail 'not enough free space on the destination drive.' }
}

# --- copy and verification, one entry at a time -------------------------------

$incomplete = $false
$failed = $false
$withHash = ($Mode -eq 'Final') -or $VerifyOnly
$kind = if ($withHash) { 'sha256' } else { 'size' }
foreach ($rel in $selected) {
    # -TimeoutMinutes covers the whole entry: pre-copy listing, copy,
    # listing and hashing share one budget per entry.
    $safe = Get-SafeName $rel
    $copyOk = $true
    try {
        Start-EntryBudget $rel
        if ($doCopy) {
            $started = Get-Date
            $result = Invoke-Robocopy $rel (Join-Path $runDirectory "$safe.robocopy.log")
            $seconds = ((Get-Date) - $started).TotalSeconds
            if ($result.TimedOut) { throw (New-Object System.TimeoutException('robocopy')) }
            $code = [int]$result.Code
            $counts = $result.Counts
            $countText = if ($null -eq $counts) { 'counts=unknown' } else { 'total={0} copied={1} skipped={2} mismatch={3} failed={4} extras={5}' -f $counts.Total, $counts.Copied, $counts.Skipped, $counts.Mismatch, $counts.Failed, $counts.Extras }
            $status = 'OK'
            if (($code -band 16) -ne 0) { $status = 'FATAL'; $failed = $true }
            elseif ($Mode -eq 'Final' -and ($code -ge 8 -or ($code -band 4) -ne 0)) { $status = 'FAIL'; $failed = $true }
            elseif (($code -band 8) -ne 0) { $status = 'INCOMPLETE'; $incomplete = $true }
            $copyOk = $status -eq 'OK'
            Report ('{0} entry={1} robocopy={2} seconds={3:n0} {4}' -f $status, $rel, $code, $seconds, $countText)
            if ($status -eq 'FATAL') {
                Report 'RESULT: FAILED'
                exit 1
            }
        }

        $errors = New-Object System.Collections.Generic.List[string]
        $sourceListing = Get-EntryFiles $Source $rel -CountExcluded
        $destinationListing = Get-EntryFiles $Destination $rel
        foreach ($e in $sourceListing.Errors) { $errors.Add("source $e") }
        foreach ($e in $destinationListing.Errors) { $errors.Add("destination $e") }
        $sourceManifest = Build-Manifest $sourceListing.Files $withHash $errors
        $destinationManifest = Build-Manifest $destinationListing.Files $withHash $errors
        Write-Manifest (Join-Path $runDirectory "$safe.source.tsv") $rel $Source $kind $sourceManifest
        $comparison = Compare-Manifests $sourceManifest $destinationManifest $withHash $true

        if ($Mirror -and $comparison.Extra.Count -gt 0) {
            $approved = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
            foreach ($line in [System.IO.File]::ReadAllLines($MirrorApprovedList, $utf8NoBom)) { if ($line.Trim()) { [void]$approved.Add($line.Trim()) } }
            $notApproved = @($comparison.Extra | Where-Object { -not $approved.Contains($_) })
            if (-not $copyOk -or $errors.Count -gt 0) {
                # An incomplete copy or listing can make a source file look extra;
                # nothing is deleted unless both sides were read completely.
                Report ('FAIL entry={0} mirror refused: copy status or {1} listing/hash errors make the extra set unreliable' -f $rel, $errors.Count)
                $failed = $true
            }
            elseif ($notApproved.Count -gt 0) {
                Report ('FAIL entry={0} mirror refused: {1} extra files are not in the approved list' -f $rel, $notApproved.Count)
                $failed = $true
            }
            else {
                # Delete only files that are both approved and extra right now; an
                # approved key that also exists in the source is never touched.
                $extraNow = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
                foreach ($key in $comparison.Extra) { [void]$extraNow.Add($key) }
                $deleted = 0
                foreach ($pair in $destinationListing.Files.GetEnumerator()) {
                    $key = Get-Key $pair.Key
                    if ($extraNow.Contains($key) -and $approved.Contains($key)) { [System.IO.File]::Delete($pair.Value.Path); $deleted++ }
                }
                Report ('mirror entry={0} deleted {1} approved extra files' -f $rel, $deleted)
                $destinationListing = Get-EntryFiles $Destination $rel
                foreach ($e in $destinationListing.Errors) { $errors.Add("destination $e") }
                $destinationManifest = Build-Manifest $destinationListing.Files $withHash $errors
                $comparison = Compare-Manifests $sourceManifest $destinationManifest $withHash $true
            }
        }
        Stop-EntryBudget $rel
    }
    catch [System.TimeoutException] {
        Report ('TIMEOUT entry={0} after {1} s' -f $rel, $script:EntryTimeoutSeconds)
        Report 'RESULT: TIMEOUT'
        exit 2
    }

    Write-Manifest (Join-Path $runDirectory "$safe.destination.tsv") $rel $Destination $kind $destinationManifest
    Write-Comparison (Join-Path $runDirectory "$safe.compare.tsv") $comparison
    $extrasFail = ($comparison.Extra.Count -gt 0) -and $withHash -and -not ($VerifyOnly -and $AllowExtras)
    $mismatch = $comparison.Missing.Count -gt 0 -or $comparison.Different.Count -gt 0 -or $extrasFail -or ($errors.Count -gt 0)
    $label = 'OK'
    if ($mismatch) {
        if ($withHash) { $label = 'FAIL'; $failed = $true } else { $label = 'DIFF'; $incomplete = $true }
    }
    Report ('{0} verify entry={1} source_files={2} source_bytes={3} destination_files={4} missing={5} different={6} extra={7} errors={8} kind={9} {10}' -f $label, $rel, $sourceManifest.Count, (Get-TotalBytes $sourceListing.Files), $destinationManifest.Count, $comparison.Missing.Count, $comparison.Different.Count, $comparison.Extra.Count, $errors.Count, $kind, (Format-Excluded $sourceListing.Excluded))
    foreach ($key in @($comparison.Missing | Select-Object -First 10)) { Report "  missing $key" }
    foreach ($key in @($comparison.Different | Select-Object -First 10)) { Report "  different $key" }
    foreach ($key in @($comparison.Extra | Select-Object -First 10)) { Report "  extra $key" }
    foreach ($e in @($errors | Select-Object -First 10)) { Report "  error $e" }
}

if ($failed) { Report 'RESULT: FAILED'; exit 1 }
if ($incomplete) { Report 'RESULT: INCOMPLETE'; exit 0 }
Report 'RESULT: OK'
exit 0
