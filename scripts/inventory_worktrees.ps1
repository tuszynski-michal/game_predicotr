<#
.SYNOPSIS
Inventories and secures every worktree of a repository before its directory is
abandoned (TASK-0954, plan ai_docs/delivery/DISK_D_MIGRATION_PLAN_20261009.md).

.DESCRIPTION
For each entry of "git worktree list --porcelain" (main checkout, linked and
detached worktrees) the script records HEAD, branch and the counts of staged,
unstaged and untracked changes, then writes into -OutputRoot\<name>\:

  staged.patch      git diff --binary --cached (written by git --output)
  unstaged.patch    git diff --binary (written by git --output)
  untracked\...     copies of untracked, not ignored files
  status-raw.txt    git status --porcelain=v1 --untracked-files=all
  status.txt        the same without " M" lines that have no content diff
                    (line-ending or stat-only changes)

Ignored and untracked data of linked worktrees is classified and copied by
scripts/sync_data_directories_to_d.ps1 (-Inventory, then -Mode <IgnoredMode>,
default Final with SHA-256 manifests) into -OutputRoot\<name>\ignored. The main
checkout's data is copied to the new checkout by TASK-0953, so it is only
inventoried here unless -IncludeMainIgnored is given. A copy that does not end
with exit code 0 makes the whole run fail (exit 1) after the inventory is
written.

-CreateRefs writes refs/c-migration/<name> for every worktree HEAD in the
repository, so "git bundle create <file> --all" also carries detached HEADs.

-VerifyClone <clone> -Bundle <file> checks a previous run (inventory.json in
-OutputRoot): the bundle refs/c-migration/* are fetched into the clone, every
worktree with changes is recreated as a temporary detached worktree of the
clone (staged.patch with --index, then unstaged.patch, then the untracked
copies), and both the filtered status and the content digest (status, both
diffs, untracked file contents) must equal the inventory. Every ignored-data
copy made in Final mode is checked against its saved manifest. The temporary
worktrees are removed afterwards.

Each record also carries IgnoredDigest, a digest over the SHA-256 manifests of
the worktree's preserved ignored/untracked data (from the Final copy, or from a
-ManifestOnly pass of the sync script for the main checkout and for skipped or
failed copies). refs.txt lists every local ref with its hash (remote-tracking
refs and refs/c-migration/* excluded).

-CompareWith takes an earlier inventory.json (read before anything is written;
it must not be the inventory.json of -OutputRoot) together with the refs.txt
next to it, and reports worktrees whose HEAD, working-tree digest or preserved
data digest changed, and any added, moved or removed ref; a baseline without
those fields counts as changed (TASK-0957 gate before deleting the old
directory). Run with -CreateRefs before creating the bundle.

Every git call runs with a time limit (-GitTimeoutSeconds); the sync script
gets -SyncTimeoutMinutes per entry.

Exit codes: 0 success; 1 validation, git, copy or verification error;
2 timeout; 3 -CompareWith found changes. ASCII-only for Windows PowerShell 5.1.

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/inventory_worktrees.ps1 -OutputRoot D:\game_predictor_backup\repo-20261010 -CreateRefs
#>
[CmdletBinding()]
param(
    [string]$Repository = 'C:\Users\tuszy\Documents\game_predicotr',
    [Parameter(Mandatory = $true)]
    [string]$OutputRoot,
    [ValidateSet('Initial', 'Final')]
    [string]$IgnoredMode = 'Final',
    [switch]$IncludeMainIgnored,
    [switch]$SkipIgnoredCopy,
    [string]$CompareWith = '',
    [switch]$CreateRefs,
    [string]$VerifyClone = '',
    [string]$Bundle = '',
    [ValidateRange(10, 86400)]
    [int]$GitTimeoutSeconds = 600,
    [ValidateRange(1, 1440)]
    [int]$SyncTimeoutMinutes = 120
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
try { [Console]::OutputEncoding = $utf8NoBom } catch { }
$OutputEncoding = $utf8NoBom

$syncScript = Join-Path $PSScriptRoot 'sync_data_directories_to_d.ps1'

function Fail([string]$message, [int]$code = 1) {
    Write-Host "ERROR: $message"
    exit $code
}

function ConvertTo-QuotedArgument([string]$value) {
    if ($value -notmatch '[\s"]' -and $value.Length -gt 0) { return $value }
    $escaped = $value -replace '(\\*)"', '$1$1\"'
    $escaped = $escaped -replace '(\\+)$', '$1$1'
    return '"' + $escaped + '"'
}

# Runs git with a time limit and captured output. Returns exit code and lines;
# a timeout always fails the run with exit code 2.
function Invoke-GitRaw([string]$directory, [string[]]$arguments) {
    $all = @('-c', 'core.quotepath=false', '-C', $directory) + $arguments
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = 'git'
    $startInfo.Arguments = (@($all | ForEach-Object { ConvertTo-QuotedArgument ([string]$_) })) -join ' '
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.StandardOutputEncoding = $utf8NoBom
    $startInfo.StandardErrorEncoding = $utf8NoBom
    $process = [System.Diagnostics.Process]::Start($startInfo)
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit($GitTimeoutSeconds * 1000)) {
        try { $process.Kill() } catch { }
        Fail ("git {0} timed out after {1} s in {2}" -f ($arguments -join ' '), $GitTimeoutSeconds, $directory) 2
    }
    $process.WaitForExit()
    $lines = @($stdout.Result -split "`n" | ForEach-Object { $_.TrimEnd("`r") })
    if ($lines.Count -gt 0 -and $lines[$lines.Count - 1] -eq '') { $lines = @($lines | Select-Object -First ($lines.Count - 1)) }
    return @{ Code = $process.ExitCode; Lines = $lines; Error = $stderr.Result }
}

function Invoke-Git([string]$directory, [string[]]$arguments) {
    $result = Invoke-GitRaw $directory $arguments
    if ($result.Code -ne 0) { Fail ("git {0} failed in {1} (exit {2}): {3}" -f ($arguments -join ' '), $directory, $result.Code, $result.Error.Trim()) }
    return , @($result.Lines)
}

function Get-SafeName([string]$path, [string]$repositoryRoot) {
    # The leaf name alone can repeat (two worktrees named "task" elsewhere), so
    # every linked worktree gets a hash of its full path as a suffix.
    if ($path.TrimEnd('\') -ieq $repositoryRoot.TrimEnd('\')) { return 'main' }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $bytes = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($path.TrimEnd('\').ToLowerInvariant()))
    $suffix = ([System.BitConverter]::ToString($bytes) -replace '-', '').Substring(0, 10).ToLowerInvariant()
    return '{0}-{1}' -f ((Split-Path $path -Leaf) -replace '[^A-Za-z0-9._-]', '_'), $suffix
}

function ConvertTo-IoPath([string]$path) {
    if ($path.Length -lt 240 -or $path.StartsWith('\\?\')) { return $path }
    return '\\?\' + $path
}

function Copy-FileSafe([string]$sourceFile, [string]$destinationFile) {
    New-Item -ItemType Directory -Force -Path (Split-Path $destinationFile -Parent) | Out-Null
    [System.IO.File]::Copy((ConvertTo-IoPath $sourceFile), (ConvertTo-IoPath $destinationFile), $true)
}

# Raw status and the status without " M" lines that have no content diff
# (line-ending or stat-only changes): those are not work to secure and cannot
# be reproduced by a patch.
function Get-WorktreeStatus([string]$directory) {
    $raw = Invoke-Git $directory @('status', '--porcelain=v1', '--untracked-files=all')
    $changedNames = New-Object 'System.Collections.Generic.HashSet[string]'
    foreach ($changedName in (Invoke-Git $directory @('diff', '--name-only'))) { if ($changedName) { [void]$changedNames.Add([string]$changedName) } }
    $filtered = @($raw | ForEach-Object { [string]$_ } | Where-Object {
            $_ -and -not ($_.StartsWith(' M ') -and -not $changedNames.Contains($_.Substring(3).Trim('"')))
        })
    return @{ Raw = @($raw); Filtered = $filtered }
}

function Get-ContentDigest([string]$directory, [string[]]$statusLines) {
    # Status names alone miss edits inside already modified or untracked files,
    # so the digest also covers both diffs and every untracked file's content.
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $builder = New-Object System.Text.StringBuilder
    [void]$builder.AppendLine(($statusLines -join "`n"))
    foreach ($arguments in @(, @('diff', '--binary', '--cached')) + @(, @('diff', '--binary'))) {
        $diff = (Invoke-Git $directory $arguments) -join "`n"
        $bytes = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($diff))
        [void]$builder.AppendLine(([System.BitConverter]::ToString($bytes) -replace '-', ''))
    }
    foreach ($file in (Invoke-Git $directory @('ls-files', '--others', '--exclude-standard'))) {
        $rel = [string]$file
        if (-not $rel) { continue }
        $stream = [System.IO.File]::OpenRead((ConvertTo-IoPath (Join-Path $directory ($rel -replace '/', '\'))))
        try { $bytes = $sha.ComputeHash($stream) } finally { $stream.Dispose() }
        [void]$builder.AppendLine(('{0} {1}' -f $rel, ([System.BitConverter]::ToString($bytes) -replace '-', '')))
    }
    $total = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($builder.ToString()))
    return ([System.BitConverter]::ToString($total) -replace '-', '').ToLowerInvariant()
}

function Get-ManifestDirDigest([string]$directory) {
    # Digest over every source manifest of one sync run (headers skipped, so the
    # root path does not matter); equal digests mean equal preserved data.
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $builder = New-Object System.Text.StringBuilder
    $files = @(Get-ChildItem -LiteralPath $directory -Filter '*.source.tsv' | Sort-Object { $_.Name })
    foreach ($file in $files) {
        $lines = [System.IO.File]::ReadAllLines($file.FullName, $utf8NoBom)
        [void]$builder.AppendLine($file.Name)
        for ($i = 1; $i -lt $lines.Count; $i++) { [void]$builder.AppendLine($lines[$i]) }
    }
    $bytes = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($builder.ToString()))
    return ([System.BitConverter]::ToString($bytes) -replace '-', '').ToLowerInvariant()
}

function Get-LatestRun([string]$logRoot, [string]$mode) {
    return Get-ChildItem -LiteralPath $logRoot -Directory | Where-Object { $_.Name -like "*-$mode" } | Sort-Object Name | Select-Object -Last 1
}

# Local refs that carry work (branches, tags, stash, other namespaces); remote
# tracking refs and the refs/c-migration/* written by this script are left out.
function Get-RefLines([string]$repository) {
    $lines = Invoke-Git $repository @('for-each-ref', '--format=%(refname) %(objectname)')
    return , @($lines | Where-Object { $_ -and $_ -notlike 'refs/remotes/*' -and $_ -notlike 'refs/c-migration/*' } | Sort-Object)
}

function Read-Inventory([string]$path) {
    return @((Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json) | ForEach-Object { $_ })
}

$Repository = [System.IO.Path]::GetFullPath($Repository).TrimEnd('\')
if (-not (Test-Path -LiteralPath (Join-Path $Repository '.git'))) { Fail "not a repository: $Repository" }
$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot).TrimEnd('\')
$inventoryJson = Join-Path $OutputRoot 'inventory.json'

# The baseline is read before anything is written, and it may not be the file
# this run is about to overwrite.
$previous = $null
if ($CompareWith) {
    $CompareWith = [System.IO.Path]::GetFullPath($CompareWith)
    if ($CompareWith -ieq $inventoryJson) { Fail '-CompareWith must not point at the inventory.json of -OutputRoot; use a new -OutputRoot.' }
    if (-not (Test-Path -LiteralPath $CompareWith -PathType Leaf)) { Fail "baseline not found: $CompareWith" }
    $previous = Read-Inventory $CompareWith
    $previousRefsPath = Join-Path (Split-Path $CompareWith -Parent) 'refs.txt'
    $previousRefs = if (Test-Path -LiteralPath $previousRefsPath) { @([System.IO.File]::ReadAllLines($previousRefsPath, $utf8NoBom) | Where-Object { $_ }) } else { $null }
}
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

if ($VerifyClone) {
    if (-not $Bundle) { Fail '-VerifyClone needs -Bundle.' }
    if (-not (Test-Path -LiteralPath $inventoryJson)) { Fail "inventory.json not found in $OutputRoot" }
    $records = Read-Inventory $inventoryJson
    $VerifyClone = [System.IO.Path]::GetFullPath($VerifyClone).TrimEnd('\')
    $null = Invoke-Git $VerifyClone @('bundle', 'verify', $Bundle)
    $null = Invoke-Git $VerifyClone @('fetch', '--quiet', $Bundle, '+refs/c-migration/*:refs/c-migration/*')
    $failures = 0
    foreach ($r in $records) {
        if (-not $r.Exists) { Write-Host "SKIP missing $($r.Name)"; continue }
        $objectType = Invoke-GitRaw $VerifyClone @('cat-file', '-t', $r.Head)
        if ($objectType.Code -ne 0 -or (@($objectType.Lines) -join '') -ne 'commit') { Write-Host "FAIL $($r.Name): HEAD $($r.Head) not in clone after bundle fetch"; $failures++; continue }
        $source = Join-Path $OutputRoot $r.Name

        if (($r.Staged + $r.Unstaged + $r.Untracked) -eq 0) { Write-Host "OK $($r.Name): clean, HEAD present" }
        else {
            $temporary = Join-Path (Split-Path $VerifyClone -Parent) ('c-restore-test-' + $r.Name)
            if (Test-Path -LiteralPath $temporary) { Fail "temporary path exists: $temporary" }
            $null = Invoke-Git $VerifyClone @('worktree', 'add', '--quiet', '--detach', $temporary, $r.Head)
            try {
                if ($r.Staged -gt 0) { $null = Invoke-Git $temporary @('apply', '--index', '--binary', (Join-Path $source 'staged.patch')) }
                if ($r.Unstaged -gt 0) { $null = Invoke-Git $temporary @('apply', '--binary', (Join-Path $source 'unstaged.patch')) }
                if ($r.Untracked -gt 0) {
                    $untrackedRoot = Join-Path $source 'untracked'
                    Get-ChildItem -LiteralPath $untrackedRoot -Recurse -File -Force | ForEach-Object {
                        Copy-FileSafe $_.FullName (Join-Path $temporary $_.FullName.Substring($untrackedRoot.Length + 1))
                    }
                }
                $expected = @([System.IO.File]::ReadAllLines((Join-Path $source 'status.txt'), $utf8NoBom) | Where-Object { $_ })
                $restored = Get-WorktreeStatus $temporary
                $difference = @(Compare-Object -ReferenceObject $expected -DifferenceObject @($restored.Filtered))
                $digest = Get-ContentDigest $temporary ([string[]]$restored.Filtered)
                if ($difference.Count -eq 0 -and $digest -eq $r.StatusDigest) {
                    Write-Host ("OK {0}: restored status and content digest equal the inventory ({1} lines)" -f $r.Name, $expected.Count)
                }
                else {
                    Write-Host ("FAIL {0}: status differences {1}, content digest {2}" -f $r.Name, $difference.Count, $(if ($digest -eq $r.StatusDigest) { 'equal' } else { 'different' }))
                    $difference | Select-Object -First 10 | ForEach-Object { Write-Host ("  {0} {1}" -f $_.SideIndicator, $_.InputObject) }
                    $failures++
                }
            }
            finally {
                $cleanup = Invoke-GitRaw $VerifyClone @('worktree', 'remove', '--force', $temporary)
                if ($cleanup.Code -ne 0 -or (Test-Path -LiteralPath $temporary)) {
                    Write-Host ("FAIL {0}: temporary worktree {1} not removed (git exit {2}); remove it before the next verification" -f $r.Name, $temporary, $cleanup.Code)
                    $failures++
                }
            }
        }

        # Every preserved entry of a linked worktree must have a Final copy whose
        # manifests cover exactly the inventoried entries, and the copy must
        # still equal those manifests. The main checkout's data is TASK-0953's.
        $copy = [string]$r.IgnoredCopy
        $preserved = @($r.IgnoredPreserved | Where-Object { $_ })
        if ($r.Name -eq 'main') { Write-Host "NOTE main: ignored data is covered by TASK-0953 (copy and B1 manifest), not by this backup"; continue }
        if ($preserved.Count -eq 0) { Write-Host "OK $($r.Name): nothing preserved to copy"; continue }
        if ($copy -notlike 'exit 0 (Final)') { Write-Host "FAIL $($r.Name): $($preserved.Count) preserved entries but ignored copy is '$copy' (needs a successful Final copy)"; $failures++; continue }
        $finalRun = Get-ChildItem -LiteralPath (Join-Path $source 'ignored-logs') -Directory | Where-Object { $_.Name -like '*-Final' } | Sort-Object Name | Select-Object -Last 1
        if ($null -eq $finalRun) { Write-Host "FAIL $($r.Name): no Final manifest for the ignored copy"; $failures++; continue }
        $covered = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
        foreach ($manifestFile in (Get-ChildItem -LiteralPath $finalRun.FullName -Filter '*.source.tsv')) {
            $header = [System.IO.File]::ReadAllLines($manifestFile.FullName, $utf8NoBom) | Select-Object -First 1
            if ($header -match "entry=([^`t]+)") { [void]$covered.Add($Matches[1]) }
        }
        $savedDigest = if ($r.PSObject.Properties['IgnoredDigest']) { [string]$r.IgnoredDigest } else { '' }
        if (-not $savedDigest -or (Get-ManifestDirDigest $finalRun.FullName) -ne $savedDigest) {
            Write-Host "FAIL $($r.Name): manifests of $($finalRun.Name) do not match the inventory's IgnoredDigest (missing, truncated or replaced)"; $failures++; continue
        }
        $uncovered = @($preserved | Where-Object { -not $covered.Contains($_) })
        if ($uncovered.Count -gt 0) { Write-Host ("FAIL {0}: {1} preserved entries without a manifest: {2}" -f $r.Name, $uncovered.Count, ($uncovered -join ', ')); $failures++; continue }
        & powershell -NoProfile -ExecutionPolicy Bypass -File $syncScript -VerifyOnly -Manifest $finalRun.FullName -Destination (Join-Path $source 'ignored') -LogRoot (Join-Path $source 'verify-logs') -TimeoutMinutes $SyncTimeoutMinutes | Out-Null
        if ($LASTEXITCODE -eq 0) { Write-Host ("OK {0}: ignored copy equals its Final manifests ({1} entries)" -f $r.Name, $preserved.Count) }
        else { Write-Host "FAIL $($r.Name): ignored copy verification exit $LASTEXITCODE"; $failures++ }
    }
    if ($failures -gt 0) { Write-Host "RESULT: FAILED ($failures)"; exit 1 }
    Write-Host 'RESULT: OK'
    exit 0
}

$porcelain = Invoke-Git $Repository @('worktree', 'list', '--porcelain')
$worktrees = New-Object System.Collections.Generic.List[object]
$current = $null
foreach ($line in $porcelain) {
    $text = [string]$line
    if ($text.StartsWith('worktree ')) {
        if ($null -ne $current) { $worktrees.Add($current) }
        $current = [ordered]@{ Path = ($text.Substring(9) -replace '/', '\'); Head = ''; Branch = ''; Detached = $false; Prunable = $false }
    }
    elseif ($text.StartsWith('HEAD ')) { $current.Head = $text.Substring(5) }
    elseif ($text.StartsWith('branch ')) { $current.Branch = $text.Substring(7) -replace '^refs/heads/', '' }
    elseif ($text -eq 'detached') { $current.Detached = $true }
    elseif ($text.StartsWith('prunable')) { $current.Prunable = $true }
}
if ($null -ne $current) { $worktrees.Add($current) }

$results = New-Object System.Collections.Generic.List[object]
$usedNames = @{}
$copyFailures = New-Object System.Collections.Generic.List[string]
foreach ($worktree in $worktrees) {
    $name = Get-SafeName $worktree.Path $Repository
    if ($usedNames.ContainsKey($name)) { Fail "duplicate backup name $name for $($worktree.Path); nothing written for it" }
    $usedNames[$name] = $true
    $target = Join-Path $OutputRoot $name
    $record = [ordered]@{
        Name = $name; Path = $worktree.Path; Head = $worktree.Head; Branch = $worktree.Branch
        Detached = $worktree.Detached; Exists = $false; Staged = 0; Unstaged = 0; Untracked = 0; StatOnly = 0
        StatusDigest = ''; StagedPatch = ''; UnstagedPatch = ''; UntrackedCopied = 0
        IgnoredPreserved = @(); IgnoredCopy = 'not run'; IgnoredDigest = ''
    }
    if (-not (Test-Path -LiteralPath $worktree.Path -PathType Container)) {
        Write-Host ("MISSING {0} {1}" -f $name, $worktree.Path)
        $results.Add([pscustomobject]$record)
        continue
    }
    $record.Exists = $true
    New-Item -ItemType Directory -Force -Path $target | Out-Null

    $statusInfo = Get-WorktreeStatus $worktree.Path
    [System.IO.File]::WriteAllLines((Join-Path $target 'status-raw.txt'), [string[]]$statusInfo.Raw, $utf8NoBom)
    $status = $statusInfo.Filtered
    $record.StatOnly = @($statusInfo.Raw).Count - $status.Count
    [System.IO.File]::WriteAllLines((Join-Path $target 'status.txt'), [string[]]$status, $utf8NoBom)
    $record.StatusDigest = Get-ContentDigest $worktree.Path ([string[]]$status)
    foreach ($entry in $status) {
        $text = [string]$entry
        if ($text.Length -lt 3) { continue }
        if ($text.StartsWith('??')) { $record.Untracked++; continue }
        if ($text[0] -ne ' ') { $record.Staged++ }
        if ($text[1] -ne ' ') { $record.Unstaged++ }
    }

    if ($record.Staged -gt 0) {
        $patch = Join-Path $target 'staged.patch'
        $null = Invoke-Git $worktree.Path @('diff', '--binary', '--cached', "--output=$patch")
        $record.StagedPatch = $patch
    }
    if ($record.Unstaged -gt 0) {
        $patch = Join-Path $target 'unstaged.patch'
        $null = Invoke-Git $worktree.Path @('diff', '--binary', "--output=$patch")
        $record.UnstagedPatch = $patch
    }
    if ($record.Untracked -gt 0) {
        foreach ($file in (Invoke-Git $worktree.Path @('ls-files', '--others', '--exclude-standard'))) {
            $rel = [string]$file
            if (-not $rel) { continue }
            Copy-FileSafe (Join-Path $worktree.Path ($rel -replace '/', '\')) (Join-Path (Join-Path $target 'untracked') ($rel -replace '/', '\'))
            $record.UntrackedCopied++
        }
    }

    $isMain = $name -eq 'main'
    $logRoot = Join-Path $target 'ignored-logs'
    & powershell -NoProfile -ExecutionPolicy Bypass -File $syncScript -Inventory -Source $worktree.Path -LogRoot $logRoot | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "ignored inventory failed for $name (exit $LASTEXITCODE)" }
    $inventoryFile = Get-ChildItem -LiteralPath $logRoot -Recurse -Filter 'INVENTORY.md' | Sort-Object LastWriteTime | Select-Object -Last 1
    # INVENTORY.md columns: | Class | New | Entry | Files | Bytes | Excluded |
    $preserved = @(Get-Content -LiteralPath $inventoryFile.FullName -Encoding UTF8 | Where-Object { $_ -like '| preserved |*' } | ForEach-Object { ($_ -split '\|')[3].Trim() })
    $record.IgnoredPreserved = $preserved
    if ($SkipIgnoredCopy -or ($isMain -and -not $IncludeMainIgnored)) {
        $record.IgnoredCopy = if ($isMain) { 'main checkout: copied by TASK-0953' } else { 'skipped' }
    }
    elseif ($preserved.Count -eq 0) {
        $record.IgnoredCopy = 'nothing preserved'
    }
    else {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $syncScript -Mode $IgnoredMode -Source $worktree.Path -Destination (Join-Path $target 'ignored') -LogRoot $logRoot -Directories ($preserved -join ',') -TimeoutMinutes $SyncTimeoutMinutes | Out-Null
        $syncExit = $LASTEXITCODE
        $record.IgnoredCopy = 'exit {0} ({1})' -f $syncExit, $IgnoredMode
        if ($syncExit -ne 0) { $copyFailures.Add(('{0}: sync exit {1} ({2}), see {3}' -f $name, $syncExit, $IgnoredMode, $logRoot)) }
    }
    # Digest of the preserved data: from the Final copy's manifests, otherwise
    # from a manifest-only pass (main checkout, skipped or failed copies).
    if ($preserved.Count -eq 0) { $record.IgnoredDigest = 'none' }
    else {
        $digestRun = $null
        if ($record.IgnoredCopy -eq 'exit 0 (Final)') { $digestRun = Get-LatestRun $logRoot 'Final' }
        else {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $syncScript -ManifestOnly -Source $worktree.Path -LogRoot $logRoot -Directories ($preserved -join ',') -TimeoutMinutes $SyncTimeoutMinutes | Out-Null
            if ($LASTEXITCODE -eq 0) { $digestRun = Get-LatestRun $logRoot 'ManifestOnly' }
            else { $copyFailures.Add(('{0}: manifest-only pass exit {1}, see {2}' -f $name, $LASTEXITCODE, $logRoot)) }
        }
        if ($null -ne $digestRun) { $record.IgnoredDigest = Get-ManifestDirDigest $digestRun.FullName }
    }
    Write-Host ("{0} head={1} branch={2} staged={3} unstaged={4} untracked={5} stat_only={8} ignored_preserved={6} ignored_copy={7}" -f $name, $worktree.Head.Substring(0, 8), $(if ($worktree.Detached) { '(detached)' } else { $worktree.Branch }), $record.Staged, $record.Unstaged, $record.Untracked, $preserved.Count, $record.IgnoredCopy, $record.StatOnly)
    $results.Add([pscustomobject]$record)
}

if ($CreateRefs) {
    foreach ($r in $results) {
        if ($r.Head) { $null = Invoke-Git $Repository @('update-ref', ('refs/c-migration/' + $r.Name), $r.Head) }
    }
    Write-Host "refs/c-migration/* written for $($results.Count) worktrees"
}
$refLines = Get-RefLines $Repository
[System.IO.File]::WriteAllLines((Join-Path $OutputRoot 'refs.txt'), [string[]]$refLines, $utf8NoBom)

$json = $results | ConvertTo-Json -Depth 4
[System.IO.File]::WriteAllText($inventoryJson, $json, $utf8NoBom)
$builder = New-Object System.Text.StringBuilder
[void]$builder.AppendLine("# Worktree inventory of $Repository")
[void]$builder.AppendLine('')
[void]$builder.AppendLine(('Generated {0:o}.' -f (Get-Date)))
[void]$builder.AppendLine('')
[void]$builder.AppendLine('| Name | Path | HEAD | Branch | Staged | Unstaged | Untracked | Ignored preserved | Ignored copy |')
[void]$builder.AppendLine('|---|---|---|---|---|---|---|---|---|')
foreach ($r in $results) {
    $branch = if ($r.Detached) { '(detached)' } else { $r.Branch }
    $head = if ($r.Head) { $r.Head.Substring(0, 8) } else { '-' }
    [void]$builder.AppendLine(('| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} | {8} |' -f $r.Name, $r.Path, $head, $branch, $r.Staged, $r.Unstaged, $r.Untracked, (@($r.IgnoredPreserved) -join ', '), $r.IgnoredCopy))
}
[System.IO.File]::WriteAllText((Join-Path $OutputRoot 'INVENTORY.md'), $builder.ToString(), $utf8NoBom)
Write-Host "inventory written to $OutputRoot"

$exitCode = 0
if ($copyFailures.Count -gt 0) {
    foreach ($failure in $copyFailures) { Write-Host "FAIL ignored copy $failure" }
    $exitCode = 1
}
if ($null -ne $previous) {
    $changed = 0
    foreach ($r in $results) {
        $old = @($previous | Where-Object { $_.Path -eq $r.Path })
        if ($old.Count -eq 0) { Write-Host "CHANGED new worktree $($r.Path)"; $changed++; continue }
        if ($old[0].Head -ne $r.Head -or $old[0].StatusDigest -ne $r.StatusDigest) { Write-Host "CHANGED $($r.Path) (HEAD or working tree)"; $changed++; continue }
        $oldDigest = if ($old[0].PSObject.Properties['IgnoredDigest']) { [string]$old[0].IgnoredDigest } else { '' }
        if (-not $oldDigest) { Write-Host "CHANGED $($r.Path) (baseline has no preserved-data digest; secure again)"; $changed++; continue }
        if ($oldDigest -ne $r.IgnoredDigest) { Write-Host "CHANGED $($r.Path) (preserved ignored/untracked data)"; $changed++ }
    }
    if ($null -eq $previousRefs) { Write-Host 'CHANGED refs (baseline has no refs.txt; secure again)'; $changed++ }
    else {
        $refDifference = @(Compare-Object -ReferenceObject @($previousRefs) -DifferenceObject @($refLines))
        if ($refDifference.Count -gt 0) {
            Write-Host ("CHANGED refs ({0} differences)" -f $refDifference.Count)
            $refDifference | Select-Object -First 10 | ForEach-Object { Write-Host ("  {0} {1}" -f $_.SideIndicator, $_.InputObject) }
            $changed++
        }
    }
    foreach ($o in $previous) {
        if (-not ($results | Where-Object { $_.Path -eq $o.Path })) { Write-Host "CHANGED removed worktree $($o.Path)"; $changed++ }
    }
    if ($changed -gt 0) { Write-Host "COMPARE: CHANGED ($changed)"; if ($exitCode -eq 0) { $exitCode = 3 } }
    else { Write-Host 'COMPARE: UNCHANGED' }
}
Write-Host $(if ($exitCode -eq 0) { 'RESULT: OK' } elseif ($exitCode -eq 3) { 'RESULT: CHANGED' } else { 'RESULT: FAILED' })
exit $exitCode
