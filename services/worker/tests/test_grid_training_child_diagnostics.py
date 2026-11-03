"""A disappearing child retains its Python failure without changing probe output."""

import json
import subprocess
import sys

import pytest
from game_predictor_worker.images import grid_training_child as child


def _spec(path, attempt):
    body = {"format": child.SPEC_FORMAT, "attempt": attempt}
    path.write_text(
        json.dumps({"payload": body, "sha256": child.sha256_bytes(child.canonical(body))}),
        encoding="utf-8",
    )


def test_unexpected_exception_and_stderr_survive_in_separate_attempt_files(tmp_path, monkeypatch):
    spec = tmp_path / "spec.json"

    def fail(_path):
        print("Python library warning", file=sys.stderr)
        raise RuntimeError("reproduced trainer failure")

    monkeypatch.setattr(child, "run", fail)
    for attempt in (1, 2):
        _spec(spec, attempt)
        with pytest.raises(RuntimeError, match="reproduced trainer failure"):
            child.main(["--spec", str(spec)])
        diagnostic = (tmp_path / f"diagnostic-{attempt}.log").read_text(encoding="utf-8")
        assert "Python library warning" in diagnostic
        assert "Traceback" in diagnostic
        assert "RuntimeError: reproduced trainer failure" in diagnostic
    assert (tmp_path / "diagnostic-1.log").exists()


def test_probe_never_reads_spec_or_opens_a_diagnostic_file(tmp_path, monkeypatch, capsys):
    def probe():
        print('{"cuda_available":true}')
        return 0

    def no_spec(*_args):
        raise AssertionError("probe must not read training inputs")

    monkeypatch.setattr(child, "probe", probe)
    monkeypatch.setattr(child, "read_spec", no_spec)
    monkeypatch.chdir(tmp_path)
    assert child.main(["--probe"]) == 0
    assert json.loads(capsys.readouterr().out) == {"cuda_available": True}
    assert list(tmp_path.iterdir()) == []


def test_unexpected_training_error_persists_failure_and_steps_before_releasing_lease(
    tmp_path, monkeypatch
):
    body = {
        "format": child.SPEC_FORMAT,
        "attempt": 3,
        "artifactRoot": str(tmp_path),
        "jobId": "11111111-1111-4111-8111-111111111111",
    }
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps({"payload": body, "sha256": child.sha256_bytes(child.canonical(body))}),
        encoding="utf-8",
    )
    released = []

    class Lease:
        def __init__(self, _path):
            pass

        def acquire(self, *_args):
            return "own-lease"

        def release(self, record):
            result = json.loads((tmp_path / "result-3.json").read_text(encoding="utf-8"))
            assert result["status"] == "failed"
            assert result["code"] == "GRID_TRAINING_UNEXPECTED_ERROR"
            assert result["steps"] == 12
            released.append(record)

    class Watchdog:
        def __init__(self, *_args):
            pass

        def start(self):
            pass

        def stop(self):
            pass

    def fail(_spec, _run_dir, _root, _lease, _record, counter):
        counter["step"] = 12
        raise RuntimeError("unexpected library failure")

    monkeypatch.setattr(child, "GpuLease", Lease)
    monkeypatch.setattr(child, "Watchdog", Watchdog)
    monkeypatch.setattr(child, "_train", fail)
    assert child.main(["--spec", str(spec)]) == 3
    assert released == ["own-lease"]
    diagnostic = (tmp_path / "diagnostic-3.log").read_text(encoding="utf-8")
    assert "RuntimeError: unexpected library failure" in diagnostic


def test_complete_python_stderr_line_survives_abrupt_process_exit(tmp_path):
    spec = tmp_path / "spec.json"
    _spec(spec, 4)
    code = """
import os, sys
from game_predictor_worker.images import grid_training_child as child
def disappear(_path):
    print('Python warning before abrupt exit', file=sys.stderr)
    os._exit(4)
child.run = disappear
child.main(['--spec', sys.argv[1]])
"""
    process = subprocess.run(
        [sys.executable, "-c", code, str(spec)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=15,
        check=False,
    )
    assert process.returncode == 4
    assert "Python warning before abrupt exit" in (tmp_path / "diagnostic-4.log").read_text(
        encoding="utf-8"
    )
    assert not (tmp_path / "result-4.json").exists()
