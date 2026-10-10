"""Execute actual launcher guards on process doubles; no live process actions."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def test_launcher_json_creation_roundtrip_and_reused_parent_guard(tmp_path):
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("PowerShell 7 launcher requires pwsh.")
    probe = tmp_path / "probe.ps1"
    probe.write_text(
        r"""
param([string]$Launcher)
$ErrorActionPreference = 'Stop'
$tokens=$null; $errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($Launcher,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw 'Launcher syntax is invalid.' }
$ast.FindAll({ param($node)
    $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
    $node.Name -in @('Get-OwnedPilotProcess','Get-PilotOwnedTree','Stop-PilotOwnedProcess')
},$true) | ForEach-Object { Invoke-Expression $_.Extent.Text }
$pilotEntry='C:\owned\entry.py'
function Get-CimInstance { param($ClassName,$Filter) return $script:fakeProcess }
$roundtrips=0
$stamp=[DateTimeOffset]'2026-10-05T21:11:22.123456Z'
foreach ($original in @($stamp.UtcDateTime,$stamp.LocalDateTime)) {
    $record=@{pid=910001; launchToken='exact-token';processCreationUtc=$original} |
        ConvertTo-Json | ConvertFrom-Json
    $script:fakeProcess=[pscustomobject]@{
        ProcessId=910001;CommandLine='C:\owned\entry.py exact-token';CreationDate=$original
    }
    if (-not (Get-OwnedPilotProcess $record)) { throw 'Valid JSON roundtrip was rejected.' }
    $roundtrips++
    $script:fakeProcess.CreationDate=$original.AddSeconds(1)
    $refused=$false
    try { Get-OwnedPilotProcess $record | Out-Null } catch { $refused=$true }
    if (-not $refused) { throw 'Reused root PID was accepted.' }
}
$root=[pscustomobject]@{ProcessId=910001;ParentProcessId=0;CreationDate=[datetime]'2026-10-05T00:00:00Z'}
$foreign=[pscustomobject]@{ProcessId=910002;ParentProcessId=910001;CreationDate=[datetime]'2026-10-04T00:00:00Z'}
$child=[pscustomobject]@{ProcessId=910003;ParentProcessId=910001;CreationDate=[datetime]'2026-10-05T00:00:01Z'}
$grandchild=[pscustomobject]@{ProcessId=910004;ParentProcessId=910003;CreationDate=[datetime]'2026-10-05T00:00:02Z'}
$owned=@(Get-PilotOwnedTree $root @($root,$foreign,$child,$grandchild))
if (($owned.ProcessId -join ',') -ne '910001,910003,910004') {
    throw 'Foreign older child was adopted.'
}
function Stop-Process {
    [CmdletBinding()]param($Id,[switch]$Force)
    if ($script:stopCase -eq 'disappeared') {
        $script:fakeProcess=$null
        Write-Error 'Already exited' -Category ObjectNotFound -ErrorAction Stop
    } else {
        Write-Error 'Still alive, denied' -Category PermissionDenied -ErrorAction Stop
    }
}
$script:stopCase='disappeared'; $script:fakeProcess=$root
Stop-PilotOwnedProcess $root
$script:stopCase='denied'; $script:fakeProcess=$root
$deniedRefused=$false
try { Stop-PilotOwnedProcess $root } catch { $deniedRefused=$true }
if (-not $deniedRefused) { throw 'Permission denial was hidden.' }
@{status='passed';roundtrips=$roundtrips;owned=$owned.ProcessId;realProcessActions=0} |
    ConvertTo-Json -Compress
""",
        encoding="utf-8",
    )
    result = subprocess.run(
        [pwsh, "-NoProfile", "-File", str(probe), str(ROOT / "scripts/run_v7_reviewed_pilot.ps1")],
        timeout=20,
        check=True,
        capture_output=True,
        text=True,
    )
    proof = json.loads(result.stdout)
    assert proof == {
        "status": "passed",
        "roundtrips": 2,
        "owned": [910001, 910003, 910004],
        "realProcessActions": 0,
    }
