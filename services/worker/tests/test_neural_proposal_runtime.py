from __future__ import annotations

import multiprocessing
import threading
import time
from pathlib import Path

import game_predictor_worker.geometry_core.proposal_runtime as runtime_module
import numpy as np
import pytest
from game_predictor_worker.geometry_core.bounded_runtime import GeometryRuntimeError
from game_predictor_worker.geometry_core.proposal_runtime import CPUGridProposalRunner


class FakeAnalyser:
    def analyse(self, _rgb: object) -> list[object]:
        return []


def factory(_bundle: Path, **_kwargs: object) -> FakeAnalyser:
    return FakeAnalyser()


def slow_factory(_bundle: Path, **_kwargs: object) -> FakeAnalyser:
    time.sleep(20)
    return FakeAnalyser()


def stalled_transport(connection: object, bundle: Path, *_args: object) -> None:
    (bundle / "ready.txt").write_text("ready", encoding="utf-8")
    connection.send(("ready", None))
    time.sleep(30)


def test_engine_process_is_cached_per_job_and_reaped_on_close(tmp_path: Path) -> None:
    runner = CPUGridProposalRunner(factory=factory)
    rgb = np.zeros((10, 10, 3), np.uint8)
    assert runner.run(tmp_path, "a" * 64, rgb, heartbeat=lambda: None, max_seconds=20) == []
    pid = runner._process.pid
    assert runner.run(tmp_path, "a" * 64, rgb, heartbeat=lambda: None, max_seconds=20) == []
    assert runner._process.pid == pid
    runner.close()
    runner.close()
    assert pid not in [child.pid for child in multiprocessing.active_children()]


def test_startup_deadline_and_cancellation_leave_no_child(tmp_path: Path) -> None:
    runner = CPUGridProposalRunner(factory=slow_factory)
    with pytest.raises(GeometryRuntimeError, match="deadline") as error:
        runner.run(
            tmp_path,
            "a" * 64,
            np.zeros((10, 10, 3), np.uint8),
            heartbeat=lambda: None,
            max_seconds=0.25,
        )
    assert error.value.code == "NEURAL_GRID_STARTUP_TIME_LIMIT"
    assert runner._process is None
    assert not [
        child for child in multiprocessing.active_children() if child.name == "neural-folder-source"
    ]


def test_cancel_during_startup_reaps_child(tmp_path: Path) -> None:
    runner = CPUGridProposalRunner(factory=slow_factory)

    def cancel() -> None:
        raise RuntimeError("operator cancelled")

    with pytest.raises(RuntimeError, match="operator cancelled"):
        runner.run(
            tmp_path, "a" * 64, np.zeros((10, 10, 3), np.uint8), heartbeat=cancel, max_seconds=20
        )
    assert runner._process is None


def test_ready_child_that_stops_receiving_large_rgb_cannot_block_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runtime_module, "_serve", stalled_transport)
    runner = CPUGridProposalRunner(factory=factory)
    started = time.monotonic()
    with pytest.raises(GeometryRuntimeError, match="deadline") as error:
        runner.run(
            tmp_path,
            "a" * 64,
            np.zeros((1024, 2048, 3), np.uint8),
            heartbeat=lambda: None,
            max_seconds=10,
        )
    assert error.value.code == "NEURAL_GRID_SOURCE_TIME_LIMIT"
    assert (tmp_path / "ready.txt").exists()
    assert time.monotonic() - started < 13
    assert runner._process is None
    assert not [
        thread for thread in threading.enumerate() if thread.name == "neural-folder-transport"
    ]
    assert not [
        child for child in multiprocessing.active_children() if child.name == "neural-folder-source"
    ]
