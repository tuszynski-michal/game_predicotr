"""Run explicit pytest modules with short owned Windows TEMP and a hard deadline.

Invoke with the intended venv Python and ``--receipt artifacts/.../run.json --
path/to/test.py::test_name``. PostgreSQL opt-ins are inherited only from the
caller. No services or database resources are started or cleaned by this tool.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
_URL_CREDENTIALS = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://)[^\s/@]+@")
_PLUGIN = """import json
from pathlib import Path

def emit(value):
    with Path(OUTPUT).open("a", encoding="utf-8") as target:
        target.write(json.dumps(value) + "\\n")

def pytest_runtest_logstart(nodeid, location):
    emit({"nodeid": nodeid, "outcome": "in_progress", "phase": "start"})

def pytest_runtest_logreport(report):
    if report.when == "call" or report.failed or report.skipped:
        emit({"nodeid": report.nodeid, "outcome": report.outcome, "phase": report.when})

def pytest_collectreport(report):
    if report.failed:
        emit({"nodeid": report.nodeid, "outcome": "failed", "phase": "collection"})

def pytest_sessionfinish(session, exitstatus):
    emit({"sessionFinished": True, "exitstatus": int(exitstatus)})
"""


def redact(value: str) -> str:
    return _URL_CREDENTIALS.sub(r"\1[REDACTED]@", value)


def _no_links(path: Path) -> None:
    for entry in (path, *path.parents):
        if entry.is_symlink() or entry.is_junction():
            raise RuntimeError("Refusing a symbolic link or junction in an owned path.")


def _short_root(worktree: Path) -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=worktree,
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    common = Path(result.stdout.strip())
    if not common.is_absolute():
        common = worktree / common
    _no_links(common)
    root = common.resolve().parent / "artifacts" / "t"
    _no_links(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


class OwnedTemp:
    """An exclusive UUID directory, never an adopted or fallback TEMP."""

    def __init__(self, root: Path) -> None:
        _no_links(root)
        self.root = root.resolve()
        self.path = self.root / uuid4().hex
        self.nonce = uuid4().hex
        self.created_here = False
        self.identity: tuple[int, int] | None = None

    def create(self) -> None:
        _no_links(self.root)
        self.path.mkdir(exist_ok=False)
        self.created_here = True
        metadata = self.path.stat()
        self.identity = metadata.st_dev, metadata.st_ino
        with (self.path / "owner.json").open("x", encoding="utf-8") as target:
            target.write(self.nonce)

    def cleanup(self) -> None:
        if not self.created_here:
            return
        _no_links(self.path)
        if self.path.parent != self.root or self.path.resolve() != self.path:
            raise RuntimeError("Owned TEMP parent changed.")
        metadata = self.path.stat()
        if (metadata.st_dev, metadata.st_ino) != self.identity:
            raise RuntimeError("Owned TEMP identity changed.")
        if (self.path / "owner.json").read_text(encoding="utf-8") != self.nonce:
            raise RuntimeError("Owned TEMP ownership marker changed.")
        for directory, directories, files in os.walk(self.path, followlinks=False):
            for name in (*directories, *files):
                candidate = Path(directory) / name
                if candidate.is_symlink() or candidate.is_junction():
                    raise RuntimeError("Owned TEMP contains a symbolic link or junction; retained.")
        shutil.rmtree(self.path)
        self.created_here = False


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_int64),
        ("job_time", ctypes.c_int64),
        ("flags", wintypes.DWORD),
        ("minimum_working_set", ctypes.c_size_t),
        ("maximum_working_set", ctypes.c_size_t),
        ("active_process_limit", wintypes.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority", wintypes.DWORD),
        ("scheduling", wintypes.DWORD),
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", _BasicLimits),
        ("io_counters", ctypes.c_uint64 * 6),
        ("process_memory", ctypes.c_size_t),
        ("job_memory", ctypes.c_size_t),
        ("peak_process_memory", ctypes.c_size_t),
        ("peak_job_memory", ctypes.c_size_t),
    ]


class WindowsJob:
    """Contain a suspended own child before it can launch descendants."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("This scoped runner requires Windows Job Objects.")
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.GetProcessId.argtypes = [wintypes.HANDLE]
        self.kernel.GetProcessId.restype = wintypes.DWORD
        self.kernel.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
        ]
        self.kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = _ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(
            self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            self.close()
            raise RuntimeError("Cannot configure the owned Windows Job Object.")

    def attach_and_resume(self, process: subprocess.Popen[bytes]) -> None:
        process_handle = getattr(process, "_handle", None)
        if process_handle is None:
            raise RuntimeError("The own Windows child has no process handle.")
        handle = int(process_handle)
        if self.kernel.GetProcessId(handle) != process.pid:
            raise RuntimeError("Own process handle identity differs from the recorded PID.")
        if not self.kernel.AssignProcessToJobObject(self.handle, handle):
            raise ctypes.WinError(ctypes.get_last_error())
        native = ctypes.WinDLL("ntdll")
        native.NtResumeProcess.argtypes = [wintypes.HANDLE]
        native.NtResumeProcess.restype = wintypes.LONG
        if native.NtResumeProcess(handle) != 0:
            raise RuntimeError("Cannot resume the suspended own test process.")

    def pids(self) -> list[int]:
        # Bounded buffer: far beyond a scoped unit suite, never an unbounded query.
        buffer = ctypes.create_string_buffer(65536)
        if not self.kernel.QueryInformationJobObject(
            self.handle, 3, buffer, ctypes.sizeof(buffer), None
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        count = ctypes.c_uint32.from_buffer(buffer, 4).value
        if count > (len(buffer) - 8) // ctypes.sizeof(ctypes.c_size_t):
            raise RuntimeError("Owned test process list exceeded its bounded buffer.")
        return [
            int(
                ctypes.c_size_t.from_buffer(
                    buffer, 8 + index * ctypes.sizeof(ctypes.c_size_t)
                ).value
            )
            for index in range(count)
        ]

    def terminate(self) -> None:
        if not self.kernel.TerminateJobObject(self.handle, 124):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def _environment(worktree: Path, temporary: Path) -> dict[str, str]:
    environment = os.environ.copy()
    paths = [
        temporary,
        worktree / "services/api/src",
        worktree / "services/worker/src",
        worktree / "services/test_support",
        worktree / "services/api/tests/integration",
        worktree,
    ]
    environment["PYTHONPATH"] = os.pathsep.join(
        [*(str(path) for path in paths), environment.get("PYTHONPATH", "")]
    )
    # Only the child gets these values. New invocations repeat this versioned
    # workflow; system/user TEMP, PATH and all opt-in flags are untouched.
    for name in ("TEMP", "TMP", "TMPDIR"):
        environment[name] = str(temporary)
    return environment


def _outcomes(events: Path) -> tuple[list[dict[str, Any]], bool]:
    outcomes: dict[str, dict[str, Any]] = {}
    finished = False
    if not events.exists():
        return [], False
    if events.stat().st_size > 4 * 1024 * 1024:
        raise RuntimeError("Scoped node outcomes exceeded their bounded size.")
    for line in events.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue  # A timeout can interrupt the final append.
        if event.get("sessionFinished"):
            finished = True
        elif isinstance(event.get("nodeid"), str):
            previous = outcomes.get(event["nodeid"])
            if previous is None or previous["outcome"] != "failed":
                outcomes[event["nodeid"]] = event
    return list(outcomes.values()), finished


def _run_child(
    command: list[str],
    environment: dict[str, str],
    worktree: Path,
    raw_log: Path,
    timeout: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {"pid": None, "timedOut": False, "processCleanup": False}
    job = WindowsJob()
    process: subprocess.Popen[bytes] | None = None
    attached = False
    started = time.monotonic()
    try:
        with raw_log.open("xb") as output:
            process = subprocess.Popen(
                command,
                cwd=worktree,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                creationflags=0x00000004 | 0x08000000,  # CREATE_SUSPENDED | CREATE_NO_WINDOW
            )
            result["pid"] = process.pid
            job.attach_and_resume(process)
            attached = True
            try:
                result["returncode"] = process.wait(
                    timeout=max(0.001, timeout - (time.monotonic() - started))
                )
            except subprocess.TimeoutExpired:
                result["timedOut"] = True
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        result["executionError"] = redact(f"{type(error).__name__}: {error}")
    finally:
        try:
            if process is not None and not attached and process.poll() is None:
                process.kill()
            result["pidsBeforeCleanup"] = job.pids()
            if result["pidsBeforeCleanup"]:
                job.terminate()
            if process is not None:
                if process.poll() is None and not result["pidsBeforeCleanup"]:
                    # Assignment can fail while our direct child is suspended.
                    # It has not run or spawned a descendant; Popen owns its handle.
                    process.kill()
                process.wait(timeout=5)
            cleanup_deadline = time.monotonic() + 5
            remaining = job.pids()
            while remaining and time.monotonic() < cleanup_deadline:
                time.sleep(0.05)
                remaining = job.pids()
            result["pidsAfterCleanup"] = remaining
            result["processCleanup"] = not remaining
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            result["cleanupError"] = redact(str(error))
        finally:
            job.close()  # KILL_ON_JOB_CLOSE also protects exceptional exits.
        result["processElapsedSeconds"] = round(time.monotonic() - started, 4)
    return result


def _reserve_receipt(destination: Path, nonce: str) -> Path:
    if not destination.is_absolute():
        destination = ROOT / destination
    if not destination.is_relative_to(ROOT / "artifacts") or destination.suffix != ".json":
        raise ValueError("Receipt must be a JSON file under this worktree's artifacts directory.")
    _no_links(destination)
    if ".." in destination.parts:
        raise ValueError("Receipt path cannot contain parent traversal.")
    log = destination.with_suffix(".log")
    if destination.exists() or log.exists():
        raise FileExistsError("Receipt or safe log already exists; refusing to adopt it.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as target:
        json.dump({"ownershipNonce": nonce, "result": "running"}, target)
    with log.open("x", encoding="utf-8"):
        pass
    return destination


def _write_receipt(destination: Path, nonce: str, payload: dict[str, Any]) -> None:
    _no_links(destination)
    if json.loads(destination.read_text(encoding="utf-8")).get("ownershipNonce") != nonce:
        raise RuntimeError("Receipt ownership marker changed.")
    pending = destination.with_name(destination.name + f".{uuid4().hex}.pending")
    with pending.open("x", encoding="utf-8") as target:
        target.write(redact(json.dumps(payload, ensure_ascii=False, indent=2)))
    pending.replace(destination)


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    values = parser.parse_args(argv)
    if not 1 <= values.timeout_seconds <= 120:
        parser.error("--timeout-seconds must be between 1 and 120")
    if values.pytest_args[:1] == ["--"]:
        values.pytest_args = values.pytest_args[1:]
    if not any(".py" in value and not value.startswith("-") for value in values.pytest_args):
        parser.error("Provide at least one explicit pytest module or node ID.")
    if any("--basetemp" in value for value in values.pytest_args):
        parser.error("The runner exclusively controls --basetemp.")
    return values


def main(argv: list[str] | None = None) -> int:
    options = parse_arguments(argv)
    nonce = uuid4().hex
    destination = _reserve_receipt(options.receipt, nonce)
    receipt: dict[str, Any] = {
        "schemaVersion": "scoped-python-tests-v1",
        "ownershipNonce": nonce,
        "timeoutSeconds": options.timeout_seconds,
        "result": "environment_error",
        "worktree": str(ROOT),
        "safeLog": str(destination.with_suffix(".log")),
        "command": [],
        "pid": None,
        "pidsBeforeCleanup": [],
        "pidsAfterCleanup": [],
        "temp": None,
        "nodeIDs": [],
        "nodeOutcomes": [],
        "sessionFinished": False,
        "tempCleanup": False,
        "processCleanup": True,
    }
    temporary: OwnedTemp | None = None
    started = time.monotonic()
    try:
        temporary = OwnedTemp(_short_root(ROOT))
        temporary.create()
        receipt["temp"] = {
            "path": str(temporary.path),
            "createdHere": temporary.created_here,
            "identity": temporary.identity,
            "ownershipNonce": temporary.nonce,
        }
        plugin_name = f"_scoped_pytest_{uuid4().hex}"
        events = temporary.path / "events.jsonl"
        (temporary.path / f"{plugin_name}.py").write_text(
            f"OUTPUT = {str(events)!r}\n" + _PLUGIN, encoding="utf-8"
        )
        command = [
            sys.executable,
            "-m",
            "pytest",
            *options.pytest_args,
            f"--basetemp={temporary.path / 'p'}",
            "-p",
            plugin_name,
        ]
        receipt["command"] = command
        raw_log = temporary.path / "raw.log"
        receipt.update(
            _run_child(
                command, _environment(ROOT, temporary.path), ROOT, raw_log, options.timeout_seconds
            )
        )
        if raw_log.exists():
            _no_links(destination.with_suffix(".log"))
            with (
                raw_log.open(encoding="utf-8", errors="replace") as source,
                destination.with_suffix(".log").open("w", encoding="utf-8") as target,
            ):
                for line in source:
                    target.write(redact(line))
        receipt["nodeOutcomes"], receipt["sessionFinished"] = _outcomes(events)
        receipt["nodeIDs"] = [event["nodeid"] for event in receipt["nodeOutcomes"]]
        if receipt.get("executionError"):
            receipt["result"] = "environment_error"
        elif receipt.get("timedOut"):
            receipt["result"] = "timeout"
        elif receipt.get("returncode") == 0 and receipt["sessionFinished"]:
            receipt["result"] = "passed"
        else:
            receipt["result"] = "failed"
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        receipt["error"] = redact(f"{type(error).__name__}: {error}")
    finally:
        if temporary is not None:
            receipt["temp"] = {
                "path": str(temporary.path),
                "createdHere": temporary.created_here or temporary.identity is not None,
                "identity": temporary.identity,
                "ownershipNonce": temporary.nonce,
            }
            if not temporary.created_here:
                receipt["tempCleanup"] = True
        else:
            receipt["tempCleanup"] = True
        if temporary is not None and temporary.created_here and receipt["processCleanup"]:
            try:
                temporary.cleanup()
                receipt["tempCleanup"] = True
            except (OSError, RuntimeError) as error:
                receipt["tempCleanupError"] = redact(str(error))
        if not receipt["processCleanup"] or (temporary is not None and not receipt["tempCleanup"]):
            receipt["result"] = "cleanup_failed"
        receipt["elapsedSeconds"] = round(time.monotonic() - started, 4)
        _write_receipt(destination, nonce, receipt)
    print(redact(json.dumps(receipt, ensure_ascii=False)))
    return 0 if receipt["result"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
