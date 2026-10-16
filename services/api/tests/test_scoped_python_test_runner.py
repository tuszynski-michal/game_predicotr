"""Bounded runner contracts without PostgreSQL or acceptance workloads."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from scripts import run_scoped_python_tests as runner


def test_scoped_runner_is_versioned_with_owned_temp_and_process_cleanup() -> None:
    source_path = Path(__file__).resolve().parents[3] / "scripts/run_scoped_python_tests.py"
    assert source_path.is_file()
    source = source_path.read_text(encoding="utf-8")
    assert "--git-common-dir" in source
    assert "--basetemp=" in source
    assert "TerminateJobObject" in source
    assert "subprocess.PIPE" not in source


@pytest.mark.parametrize("timeout", ["0", "121", "-1"])
def test_deadline_outside_one_to_120_seconds_is_rejected(timeout: str) -> None:
    with pytest.raises(SystemExit):
        runner.parse_arguments(
            [
                "--receipt",
                "artifacts/test.json",
                "--timeout-seconds",
                timeout,
                "--",
                "services/api/tests/test_scoped_python_test_runner.py",
            ]
        )


def test_no_default_broad_suite_or_basetemp_override() -> None:
    with pytest.raises(SystemExit):
        runner.parse_arguments(["--receipt", "artifacts/test.json", "--", "-q"])
    with pytest.raises(SystemExit):
        runner.parse_arguments(
            [
                "--receipt",
                "artifacts/test.json",
                "--",
                "test.py",
                "--basetemp=outside",
            ]
        )


def test_owned_temp_requires_unchanged_identity_and_marker(tmp_path: Path) -> None:
    temporary = runner.OwnedTemp(tmp_path)
    temporary.create()
    assert len(temporary.path.name) == 32
    assert temporary.created_here
    marker = temporary.path / "owner.json"
    marker.write_text("foreign", encoding="utf-8")
    with pytest.raises(RuntimeError, match="marker changed"):
        temporary.cleanup()
    assert temporary.path.exists()
    marker.write_text(temporary.nonce, encoding="utf-8")
    identity = temporary.identity
    temporary.identity = (0, 0)
    with pytest.raises(RuntimeError, match="identity changed"):
        temporary.cleanup()
    temporary.identity = identity
    temporary.cleanup()
    assert not temporary.path.exists()


def test_common_git_root_keeps_temp_short_for_worktrees(tmp_path: Path) -> None:
    common = tmp_path / "repository" / ".git"
    common.mkdir(parents=True)
    worktree = tmp_path / "nested" / "worktree"
    worktree.mkdir(parents=True)
    with patch.object(subprocess, "run", return_value=SimpleNamespace(stdout=str(common))) as run:
        root = runner._short_root(worktree)
    assert root == common.parent / "artifacts/t"
    assert run.call_args.kwargs["timeout"] == 5
    assert run.call_args.kwargs["cwd"] == worktree


def test_child_environment_uses_this_worktree_and_preserves_opt_ins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GAME_PREDICTOR_RUN_POSTGRES_TESTS", raising=False)
    monkeypatch.delenv("GAME_PREDICTOR_RUN_APPLICATION_ROLE_TESTS", raising=False)
    assert "GAME_PREDICTOR_RUN_POSTGRES_TESTS" not in runner._environment(
        tmp_path, tmp_path / "owned"
    )
    monkeypatch.setenv("GAME_PREDICTOR_RUN_POSTGRES_TESTS", "1")
    monkeypatch.setenv("GAME_PREDICTOR_RUN_APPLICATION_ROLE_TESTS", "requested")
    child = runner._environment(tmp_path, tmp_path / "owned")
    assert child["GAME_PREDICTOR_RUN_POSTGRES_TESTS"] == "1"
    assert child["GAME_PREDICTOR_RUN_APPLICATION_ROLE_TESTS"] == "requested"
    assert str(tmp_path / "services/api/tests/integration") in child["PYTHONPATH"]
    assert str(tmp_path / "services/api/src") in child["PYTHONPATH"]
    assert str(tmp_path / "services/worker/src") in child["PYTHONPATH"]
    assert str(tmp_path / "services/test_support") in child["PYTHONPATH"]
    assert child["TEMP"] == str(tmp_path / "owned")


def test_url_credentials_are_redacted_before_json_or_log_persistence() -> None:
    original = "postgresql+psycopg://owner:very%40secret@localhost/db"
    safe = runner.redact(original)
    assert safe == "postgresql+psycopg://[REDACTED]@localhost/db"
    assert "very" not in safe
    assert (
        runner.redact("https://name:password@example.com/a") == "https://[REDACTED]@example.com/a"
    )


def test_node_outcomes_preserve_setup_and_teardown_failures(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text(
        '{"nodeid":"test.py::setup", "outcome":"failed", "phase":"setup"}\n'
        '{"nodeid":"test.py::call", "outcome":"in_progress", "phase":"start"}\n'
        '{"nodeid":"test.py::call", "outcome":"passed", "phase":"call"}\n'
        '{"nodeid":"test.py::call", "outcome":"failed", "phase":"teardown"}\n'
        '{"sessionFinished":true,"exitstatus":1}\n{"partial":',
        encoding="utf-8",
    )
    outcomes, finished = runner._outcomes(events)
    assert finished
    assert [(row["nodeid"], row["outcome"]) for row in outcomes] == [
        ("test.py::setup", "failed"),
        ("test.py::call", "failed"),
    ]


def test_existing_receipt_is_not_adopted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    destination = tmp_path / "artifacts/receipt.json"
    runner._reserve_receipt(destination, "own")
    with pytest.raises(FileExistsError, match="refusing to adopt"):
        runner._reserve_receipt(destination, "foreign")
    with pytest.raises(RuntimeError, match="ownership marker changed"):
        runner._write_receipt(destination, "foreign", {})


def test_timeout_kills_only_owned_job_and_waits_for_zero_pids(tmp_path: Path) -> None:
    process = MagicMock()
    process.pid = 1234
    process.wait.side_effect = [subprocess.TimeoutExpired(["python"], 1), 124]
    process.poll.return_value = 124
    job = MagicMock()
    job.pids.side_effect = [[1234, 1235], []]
    with (
        patch.object(runner, "WindowsJob", return_value=job),
        patch.object(subprocess, "Popen", return_value=process) as launch,
    ):
        result = runner._run_child(["python", "-m", "pytest"], {}, tmp_path, tmp_path / "raw", 1)
    assert result["timedOut"] and result["processCleanup"]
    assert result["pidsBeforeCleanup"] == [1234, 1235]
    assert result["pidsAfterCleanup"] == []
    job.attach_and_resume.assert_called_once_with(process)
    job.terminate.assert_called_once()
    job.close.assert_called_once()
    assert launch.call_args.kwargs["stdout"] is not subprocess.PIPE
    assert process.wait.call_args_list[-1].kwargs["timeout"] == 5


def test_unavailable_common_root_writes_terminal_receipt_without_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    receipt = tmp_path / "artifacts/unavailable.json"
    with (
        patch.object(runner, "_short_root", side_effect=PermissionError("Common root unavailable")),
        patch.object(runner, "_run_child") as run_child,
    ):
        assert runner.main(["--receipt", str(receipt), "--", "test.py"]) == 1
    saved = json.loads(receipt.read_text(encoding="utf-8"))
    assert saved["result"] == "environment_error"
    assert saved["temp"] is None
    assert saved["tempCleanup"] and saved["processCleanup"]
    assert saved["nodeIDs"] == [] and saved["pid"] is None
    run_child.assert_not_called()
