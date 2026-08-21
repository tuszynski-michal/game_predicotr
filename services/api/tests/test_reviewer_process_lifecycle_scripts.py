import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
LIFECYCLE_HELPER = REPOSITORY_ROOT / "scripts" / "reviewer_process_lifecycle.ps1"
CONTROLLER_SCRIPTS = (
    REPOSITORY_ROOT / "scripts" / "start_remote_reviewer_tunnel.ps1",
    REPOSITORY_ROOT / "scripts" / "get_remote_reviewer_tunnel_status.ps1",
    REPOSITORY_ROOT / "scripts" / "stop_remote_reviewer_tunnel.ps1",
    REPOSITORY_ROOT / "scripts" / "start_local_reviewer.ps1",
)
POWERSHELL = shutil.which("powershell.exe") or shutil.which("pwsh.exe")

pytestmark = pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is unavailable.")


def _run_powershell(
    script: str,
    *,
    environment: dict[str, str] | None = None,
    timeout: float = 10,
) -> subprocess.CompletedProcess[str]:
    assert POWERSHELL is not None
    return subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        check=False,
        capture_output=True,
        env=os.environ | (environment or {}),
        text=True,
        timeout=timeout,
    )


def test_lifecycle_helper_writes_atomic_state_and_rejects_pid_reuse_metadata(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "state.json"
    environment = {
        "GP_LIFECYCLE_HELPER": str(LIFECYCLE_HELPER),
        "GP_STATE_PATH": str(state_path),
        "GP_RUNTIME_PATH": str(tmp_path),
    }
    completed = _run_powershell(
        """
. $env:GP_LIFECYCLE_HELPER
$process = Get-Process -Id $PID
$identity = New-ReviewerProcessIdentity -Process $process -InstanceId ([Guid]::NewGuid())
$state = [ordered]@{
    schemaVersion = 2
    instanceId = $identity.instanceId
    pid = $identity.pid
    processStartedAt = $identity.processStartedAt
    executablePath = $identity.executablePath
    processName = $identity.processName
}
Write-ReviewerAtomicJson -LiteralPath $env:GP_STATE_PATH -Value $state
$loaded = Read-ReviewerJsonState -LiteralPath $env:GP_STATE_PATH
$matched = Test-ReviewerProcessIdentity `
    -State $loaded `
    -ExpectedProcessName "$($process.ProcessName)*"
$loaded.processStartedAt = '2000-01-01T00:00:00.0000000Z'
$reusedPid = Test-ReviewerProcessIdentity `
    -State $loaded `
    -ExpectedProcessName "$($process.ProcessName)*"
$firstPaths = New-ReviewerAttemptPaths `
    -RuntimeDirectory $env:GP_RUNTIME_PATH `
    -Prefix 'cloudflared' `
    -InstanceId ([Guid]::NewGuid())
$secondPaths = New-ReviewerAttemptPaths `
    -RuntimeDirectory $env:GP_RUNTIME_PATH `
    -Prefix 'cloudflared' `
    -InstanceId ([Guid]::NewGuid())
@{
    instanceId = $state.instanceId
    executablePath = $state.executablePath
    matched = $matched.isMatch
    reusedPidMatched = $reusedPid.isMatch
    reusedPidReason = $reusedPid.reason
    firstLog = $firstPaths.process
    secondLog = $secondPaths.process
} | ConvertTo-Json -Compress
""",
        environment=environment,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.splitlines()[-1])
    assert payload["matched"] is True
    assert Path(payload["executablePath"]).resolve() == Path(POWERSHELL).resolve()
    assert payload["reusedPidMatched"] is False
    assert payload["reusedPidReason"] == "start-time"
    assert payload["firstLog"] != payload["secondLog"]
    assert json.loads(state_path.read_text(encoding="utf-8"))["instanceId"] == payload["instanceId"]
    assert list(tmp_path.glob(".*.tmp")) == []


def test_named_lifecycle_mutex_serializes_independent_powershell_processes(
    tmp_path: Path,
) -> None:
    ready_path = tmp_path / "holder-ready.txt"
    environment = os.environ | {
        "GP_LIFECYCLE_HELPER": str(LIFECYCLE_HELPER),
        "GP_MUTEX_ROOT": str(tmp_path),
        "GP_MUTEX_READY": str(ready_path),
    }
    assert POWERSHELL is not None
    holder = subprocess.Popen(
        [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            """
. $env:GP_LIFECYCLE_HELPER
$mutex = Enter-ReviewerLifecycleLock -ProjectRoot $env:GP_MUTEX_ROOT -TimeoutMilliseconds 1000
try {
    [IO.File]::WriteAllText($env:GP_MUTEX_READY, 'ready')
    Start-Sleep -Milliseconds 1500
}
finally {
    Exit-ReviewerLifecycleLock -Mutex $mutex
}
""",
        ],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 3
        while not ready_path.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready_path.exists(), "The mutex holder did not become ready."

        contender = _run_powershell(
            """
. $env:GP_LIFECYCLE_HELPER
try {
    $mutex = Enter-ReviewerLifecycleLock -ProjectRoot $env:GP_MUTEX_ROOT -TimeoutMilliseconds 100
    Exit-ReviewerLifecycleLock -Mutex $mutex
    'unexpected-acquire'
}
catch {
    'blocked'
}
""",
            environment={
                "GP_MUTEX_ROOT": str(tmp_path),
                "GP_LIFECYCLE_HELPER": str(LIFECYCLE_HELPER),
            },
        )
        assert contender.returncode == 0, contender.stderr
        assert contender.stdout.strip() == "blocked"

        _stdout, stderr = holder.communicate(timeout=5)
        assert holder.returncode == 0, stderr
        acquired = _run_powershell(
            """
. $env:GP_LIFECYCLE_HELPER
$mutex = Enter-ReviewerLifecycleLock -ProjectRoot $env:GP_MUTEX_ROOT -TimeoutMilliseconds 1000
try { 'acquired' } finally { Exit-ReviewerLifecycleLock -Mutex $mutex }
""",
            environment={
                "GP_MUTEX_ROOT": str(tmp_path),
                "GP_LIFECYCLE_HELPER": str(LIFECYCLE_HELPER),
            },
        )
        assert acquired.returncode == 0, acquired.stderr
        assert acquired.stdout.strip() == "acquired"
    finally:
        if holder.poll() is None:
            holder.kill()
            holder.communicate(timeout=5)


def test_public_origin_probe_can_bypass_only_a_negative_local_dns_cache() -> None:
    completed = _run_powershell(
        """
. $env:GP_LIFECYCLE_HELPER
$script:resolvedHost = $null
$script:probeHost = $null
$script:probeUsesSystemDns = $null
$ready = Test-ReviewerPublicOriginReady `
    -PublicOrigin 'https://bounded-review.trycloudflare.com' `
    -Resolver {
        param($hostName)
        $script:resolvedHost = $hostName
        [pscustomobject]@{
            usesSystemDns = $false
            addresses = @('203.0.113.10', '203.0.113.11')
        }
    } `
    -Probe {
        param($publicUri, $resolution)
        $script:probeHost = $publicUri.DnsSafeHost
        $script:probeUsesSystemDns = [bool]$resolution.usesSystemDns
        return @($resolution.addresses).Count -eq 2
    }
$invalid = Test-ReviewerPublicOriginReady `
    -PublicOrigin 'https://example.invalid/admin' `
    -Resolver { throw 'invalid origins must not resolve' } `
    -Probe { throw 'invalid origins must not probe' }
$parsedAddresses = @(Get-ReviewerDnsJsonIpv4Address -Response ([pscustomobject]@{
    Answer = @(
        [pscustomobject]@{ type = 1; data = '203.0.113.20' },
        [pscustomobject]@{ type = 28; data = '2001:db8::1' },
        [pscustomobject]@{ type = 1; data = 'not-an-address' },
        [pscustomobject]@{ type = 1; data = '203.0.113.20' },
        [pscustomobject]@{ type = 1; data = '203.0.113.21' }
    )
}))
@{
    ready = $ready
    invalid = $invalid
    resolvedHost = $script:resolvedHost
    probeHost = $script:probeHost
    probeUsesSystemDns = $script:probeUsesSystemDns
    parsedAddresses = $parsedAddresses
} | ConvertTo-Json -Compress
""",
        environment={"GP_LIFECYCLE_HELPER": str(LIFECYCLE_HELPER)},
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.splitlines()[-1])
    assert payload == {
        "invalid": False,
        "parsedAddresses": ["203.0.113.20", "203.0.113.21"],
        "probeHost": "bounded-review.trycloudflare.com",
        "probeUsesSystemDns": False,
        "ready": True,
        "resolvedHost": "bounded-review.trycloudflare.com",
    }


def test_all_reviewer_lifecycle_controllers_are_valid_powershell() -> None:
    environment = {"GP_CONTROLLER_PATHS": os.pathsep.join(map(str, CONTROLLER_SCRIPTS))}
    completed = _run_powershell(
        """
$failures = @()
foreach ($path in ($env:GP_CONTROLLER_PATHS -split [IO.Path]::PathSeparator)) {
    $tokens = $null
    $errors = $null
    [Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors) | Out-Null
    foreach ($error in $errors) {
        $failures += "$path`:$($error.Extent.StartLineNumber): $($error.Message)"
    }
}
if ($failures.Count -gt 0) {
    $failures | Write-Error
    exit 1
}
'valid'
""",
        environment=environment,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "valid"


def test_status_and_compare_stop_never_kill_a_reused_or_newer_instance(
    tmp_path: Path,
) -> None:
    assert POWERSHELL is not None
    scripts_directory = tmp_path / "scripts"
    runtime_directory = tmp_path / ".runtime"
    scripts_directory.mkdir()
    runtime_directory.mkdir()
    for source in (
        LIFECYCLE_HELPER,
        REPOSITORY_ROOT / "scripts" / "get_remote_reviewer_tunnel_status.ps1",
        REPOSITORY_ROOT / "scripts" / "stop_remote_reviewer_tunnel.ps1",
    ):
        shutil.copy2(source, scripts_directory / source.name)

    command_processor = Path(os.environ["COMSPEC"])
    fake_cloudflared = tmp_path / "cloudflared.exe"
    shutil.copy2(command_processor, fake_cloudflared)
    process = subprocess.Popen(
        [str(fake_cloudflared), "/c", "ping", "-n", "30", "127.0.0.1"],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    instance_id = uuid4()
    state_path = runtime_directory / "remote-reviewer.json"
    environment = {
        "GP_LIFECYCLE_HELPER": str(scripts_directory / LIFECYCLE_HELPER.name),
        "GP_FAKE_PID": str(process.pid),
        "GP_INSTANCE_ID": str(instance_id),
        "GP_STATE_PATH": str(state_path),
    }
    try:
        state_created = _run_powershell(
            """
. $env:GP_LIFECYCLE_HELPER
$process = Get-Process -Id ([int]$env:GP_FAKE_PID)
$identity = New-ReviewerProcessIdentity -Process $process -InstanceId ([Guid]$env:GP_INSTANCE_ID)
$state = [ordered]@{
    schemaVersion = 2
    instanceId = $identity.instanceId
    pid = $identity.pid
    processStartedAt = $identity.processStartedAt
    executablePath = $identity.executablePath
    processName = $identity.processName
    publicOrigin = 'https://safe-name.trycloudflare.com'
    target = 'http://127.0.0.1:3001'
    startedAt = '2026-08-20T12:00:00+00:00'
}
Write-ReviewerAtomicJson -LiteralPath $env:GP_STATE_PATH -Value $state
""",
            environment=environment,
        )
        assert state_created.returncode == 0, state_created.stderr

        status_result = runtime_directory / "status.json"
        status = subprocess.run(
            [
                POWERSHELL,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(scripts_directory / "get_remote_reviewer_tunnel_status.ps1"),
                "-Json",
                "-ResultPath",
                str(status_result),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert status.returncode == 0, status.stderr
        status_payload = json.loads(status_result.read_text(encoding="utf-8"))
        assert status_payload["state"] in {"running", "degraded"}
        assert status_payload["instanceId"] == str(instance_id)

        rejected_result = runtime_directory / "rejected-stop.json"
        rejected = subprocess.run(
            [
                POWERSHELL,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(scripts_directory / "stop_remote_reviewer_tunnel.ps1"),
                "-Json",
                "-ResultPath",
                str(rejected_result),
                "-ExpectedInstanceId",
                str(uuid4()),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert rejected.returncode == 0, rejected.stderr
        assert json.loads(rejected_result.read_text(encoding="utf-8"))["state"] == "running"
        assert process.poll() is None
        assert state_path.is_file()

        stopped_result = runtime_directory / "stopped.json"
        stopped = subprocess.run(
            [
                POWERSHELL,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(scripts_directory / "stop_remote_reviewer_tunnel.ps1"),
                "-Json",
                "-ResultPath",
                str(stopped_result),
                "-ExpectedInstanceId",
                str(instance_id),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert stopped.returncode == 0, stopped.stderr
        assert json.loads(stopped_result.read_text(encoding="utf-8"))["state"] == "stopped"
        process.wait(timeout=5)
        assert not state_path.exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
