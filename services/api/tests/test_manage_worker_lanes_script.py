"""TASK-1001: the grid-training lane of ``scripts/manage_worker_lanes.ps1``.

A GPU worker started with ``-GridTrainingPython`` must stay visible to ``Status`` and be
stopped by ``Stop`` from a later invocation that cannot find any CUDA interpreter; only
``Start`` skips the lane without one. Runs on an isolated copy of the script with a fake
recorded process, never against the operator's workers.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
POWERSHELL = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
VARIABLE = "GAME_PREDICTOR_GRID_TRAINING_PYTHON"


def _user_variable_set() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            return bool(winreg.QueryValueEx(key, VARIABLE)[0])
    except OSError:
        return False


pytestmark = [
    pytest.mark.skipif(
        os.name != "nt" or POWERSHELL is None, reason="Windows PowerShell is required."
    ),
    pytest.mark.skipif(
        _user_variable_set(), reason="A user-level CUDA interpreter is configured here."
    ),
]


def _fixture(tmp_path: Path) -> Path:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "manage_worker_lanes.ps1"
    shutil.copyfile(ROOT / "scripts" / script.name, script)
    (scripts / "windows_process_environment.ps1").write_text(
        "function Repair-WindowsProcessPath {}\n", encoding="utf-8"
    )
    python = tmp_path / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"")
    return script


def _run(script: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = {key: value for key, value in os.environ.items() if key != VARIABLE}
    assert POWERSHELL is not None
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *arguments],
        capture_output=True,
        text=True,
        timeout=60,
        env=environment,
        check=False,
    )


def _lanes(result: subprocess.CompletedProcess[str]) -> dict[str, str]:
    assert result.returncode == 0, result.stderr
    document = json.loads(result.stdout.strip().splitlines()[-1])
    return {lane["lane"]: lane["state"] for lane in document["lanes"]}


def _record_running_gpu_worker(tmp_path: Path) -> subprocess.Popen[bytes]:
    assert POWERSHELL is not None
    worker = subprocess.Popen(
        [POWERSHELL, "-NoProfile", "-Command", "Start-Sleep -Seconds 120"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    identity = subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-Command",
            f"$p = Get-Process -Id {worker.pid}; "
            "$p.ProcessName; $p.StartTime.ToUniversalTime().ToString('o')",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    ).stdout.split()
    runtime = tmp_path / ".runtime"
    runtime.mkdir()
    (runtime / "worker-lanes.json").write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "repositoryRoot": str(tmp_path),
                "updatedAtUtc": datetime.now(UTC).isoformat(),
                "processes": {
                    "grid-training": {
                        "lane": "grid-training",
                        "pid": worker.pid,
                        "processName": identity[0],
                        "startTimeUtc": identity[1],
                        "stdoutLog": str(runtime / "out.log"),
                        "stderrLog": str(runtime / "err.log"),
                        "threadBudget": 1,
                        "nativeThreadBudget": 1,
                        "processTree": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return worker


def test_status_and_stop_cover_a_gpu_worker_without_any_cuda_interpreter(tmp_path):
    script = _fixture(tmp_path)
    worker = _record_running_gpu_worker(tmp_path)
    try:
        assert _lanes(_run(script, "-Action", "Status", "-Lane", "all", "-Json")) == {
            "general": "stopped",
            "image-selection": "stopped",
            "grid-training": "running",
        }
        stopped = _lanes(_run(script, "-Action", "Stop", "-Lane", "all", "-Json"))
        assert stopped["grid-training"] == "stopped"
        deadline = time.monotonic() + 15
        while worker.poll() is None and time.monotonic() < deadline:
            time.sleep(0.2)
        assert worker.poll() is not None, "the recorded GPU worker must be stopped"
        assert not (tmp_path / ".runtime" / "worker-lanes.json").exists()
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.wait(timeout=10)


def test_explicit_gpu_start_without_an_interpreter_refuses_and_records_nothing(tmp_path):
    script = _fixture(tmp_path)
    result = _run(script, "-Action", "Start", "-Lane", "grid-training")
    assert result.returncode != 0
    assert "CUDA interpreter" in result.stdout + result.stderr
    assert not (tmp_path / ".runtime" / "worker-lanes.json").exists()
