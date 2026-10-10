"""Lost replies, fencing, conservative budgets and genuine process restarts."""

import os
import pickle
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import torch
from fastapi.testclient import TestClient
from game_predictor_worker.training_core.checkpoint import checkpoint_bytes, make_checkpoint
from game_predictor_worker.training_core.runtime import TrainingInterrupted
from game_predictor_worker.vision_lab.api import create_app
from game_predictor_worker.vision_lab.run_contracts import RunMutation, StartRunRequest
from game_predictor_worker.vision_lab.runs import RunManager, checkpoint_binding, token


def request(request_id="test-request"):
    return StartRunRequest(
        request_id=request_id,
        manifest_id="a" * 64,
        model_version="test",
        preprocessing_version="rgb",
        seed=1,
        purpose="smoke",
        configuration={"epochs": 1, "max_steps": 5, "max_seconds": 120},
    )


def checkpoint_content(run, epoch):
    model = torch.nn.Linear(1, 1)
    return checkpoint_bytes(
        make_checkpoint(
            model,
            torch.optim.AdamW(model.parameters()),
            None,
            torch.Generator().manual_seed(1),
            binding=checkpoint_binding(run.request),
            epoch=epoch,
            global_step=epoch,
            history=[],
        )
    )


def manager_at(tmp_path, **kwargs):
    return RunManager(
        tmp_path,
        validate=lambda request: None,
        models=("test",),
        launcher=lambda run: None,
        **kwargs,
    )


def test_lost_start_cancel_retry_replies_and_fencing(tmp_path):
    now = [1000.0]
    manager = manager_at(tmp_path, clock=lambda: now[0], identity=lambda pid: None)
    first = manager.create_or_get_run(request())
    assert manager_at(tmp_path).create_or_get_run(request()).id == first.id
    with pytest.raises(ValueError, match="CONFLICT"):
        manager.create_or_get_run(request().model_copy(update={"seed": 2}))
    with pytest.raises(ValueError, match="BUSY"):
        manager.create_or_get_run(request("other-request"))
    cancelled = manager.cancel_run(
        first.id, RunMutation(request_id="cancel-request", expected_attempt=1)
    )
    assert cancelled.status == "cancelled"
    assert (
        manager.cancel_run(first.id, RunMutation(request_id="cancel-request", expected_attempt=1))
        == cancelled
    )
    retry = RunMutation(request_id="retry-request", expected_attempt=1)
    second = manager.retry_run(first.id, retry)
    assert second.attempt == 2 and token(second) != token(first)
    assert manager.retry_run(first.id, retry).attempt == 2
    # Replaying an old cancel must not cancel the new attempt.
    assert not manager.cancel_run(
        first.id, RunMutation(request_id="cancel-request", expected_attempt=1)
    ).cancel_requested
    for operation in (
        lambda: manager.heartbeat(first.id, token(first)),
        lambda: manager.checkpoint(first.id, token(first), b"stale", 0),
        lambda: manager.finish(first.id, token(first), status="succeeded"),
    ):
        with pytest.raises(ValueError, match="FENCED"):
            operation()


def test_queued_crash_expiry_and_concurrent_start(tmp_path):
    now = [1000.0]
    manager = manager_at(tmp_path, clock=lambda: now[0])
    first = manager.create_or_get_run(request())
    now[0] += 61
    assert manager.detail(first.id).error == "RUN_LAUNCH_EXPIRED"
    # Fresh manager observes durable failed rather than relaunching it.
    assert manager_at(tmp_path).detail(first.id).status == "failed"
    other = tmp_path / "parallel"

    def start():
        for _ in range(30):
            try:
                return manager_at(other).create_or_get_run(request()).id
            except ValueError as error:
                assert str(error) == "ANNOTATION_STORE_BUSY"
                time.sleep(0.01)
        raise TimeoutError()

    with ThreadPoolExecutor(2) as pool:
        ids = list(pool.map(lambda _: start(), range(2)))
    assert ids[0] == ids[1] and manager_at(other).list().total == 1


def test_live_process_stale_heartbeat_not_failed_and_pid_reuse(tmp_path):
    now = [1000.0]
    identities = {}
    manager = manager_at(tmp_path, clock=lambda: now[0], identity=lambda pid: identities.get(pid))
    run = manager.create_or_get_run(request())
    run = manager.claim(run.id, token(run))
    identities[run.pid] = run.process_created
    now[0] += 70
    observed = manager.detail(run.id)
    assert observed.status == "running" and observed.diagnostics == ["RUN_UNRESPONSIVE"]
    identities[run.pid] = "reused"
    failed = manager.detail(run.id)
    assert failed.status == "failed" and failed.conservative_seconds == 70
    second = manager.retry_run(run.id, RunMutation(request_id="retry-request", expected_attempt=1))
    assert second.used_seconds == 70


def test_budget_reservation_survives_crash_and_clock_reversal(tmp_path):
    now = [1000.0]
    manager = manager_at(tmp_path, clock=lambda: now[0], identity=lambda pid: None)
    run = manager.create_or_get_run(request())
    manager.claim(run.id, token(run))
    manager.heartbeat(run.id, token(run), reserve_step=True)
    manager.checkpoint(run.id, token(run), checkpoint_content(run, 0), 0)
    now[0] += 70
    failed = manager.detail(run.id)
    assert failed.reserved_steps == 1 and failed.checkpoint_epoch == 0
    retry = manager.retry_run(run.id, RunMutation(request_id="retry-request", expected_attempt=1))
    manager.claim(retry.id, token(retry))
    now[0] -= 1
    with pytest.raises(TrainingInterrupted, match="BUDGET"):
        manager.heartbeat(retry.id, token(retry), reserve_step=True)
    assert manager.detail(run.id).reserved_steps == 1
    manager.finish(run.id, token(retry), status="cancelled", error="RUN_BUDGET_EXHAUSTED")
    with pytest.raises(TrainingInterrupted, match="BUDGET"):
        manager.retry_run(run.id, RunMutation(request_id="retry-again", expected_attempt=2))


def test_checkpoint_failure_preserves_last_and_success_has_checked_report(tmp_path):
    manager = manager_at(tmp_path)
    run = manager.create_or_get_run(request())
    manager.claim(run.id, token(run))
    manager.checkpoint(run.id, token(run), checkpoint_content(run, 0), 0)
    original = manager.detail(run.id).checkpoint
    with pytest.raises(pickle.UnpicklingError):
        manager.checkpoint(run.id, token(run), b"corrupted", 1)
    assert manager.detail(run.id).checkpoint == original
    manager.checkpoint(run.id, token(run), checkpoint_content(run, 1), 1)
    success = manager.finish(run.id, token(run), status="succeeded", metrics={"loss": 0.1})
    assert manager_at(tmp_path).detail(run.id).report == success.report
    (tmp_path / success.report.relative_path).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="CHECKSUM"):
        manager.detail(run.id)


def test_checkpoint_data_drift_preserves_last_good_pointer_after_restart(tmp_path):
    manager = manager_at(tmp_path)
    run = manager.create_or_get_run(request())
    manager.claim(run.id, token(run))
    manager.checkpoint(run.id, token(run), checkpoint_content(run, 0), 0)
    original = manager.detail(run.id).checkpoint
    artifacts = set(tmp_path.rglob("*.pt"))

    def drift(request):
        raise ValueError("RUN_DATA_DRIFT")

    manager.validate = drift
    with pytest.raises(ValueError, match="^RUN_DATA_DRIFT$"):
        manager.checkpoint(run.id, token(run), checkpoint_content(run, 1), 1)
    observed = manager_at(tmp_path).detail(run.id)
    assert observed.checkpoint == original
    assert observed.checkpoint_epoch == 0
    assert set(tmp_path.rglob("*.pt")) == artifacts
    manager.finish(run.id, token(run), status="failed", error="RUN_DATA_DRIFT")
    failed = manager_at(tmp_path).detail(run.id)
    assert failed.status == "failed" and failed.error == "RUN_DATA_DRIFT"
    assert failed.checkpoint == original and failed.checkpoint_epoch == 0


def test_http_contract_requests_and_no_model_fallback(tmp_path):
    manager = manager_at(tmp_path)
    client = TestClient(create_app(run_manager=manager), base_url="http://127.0.0.1:8102")
    headers = {"Origin": "http://127.0.0.1:3102"}
    body = request().model_dump()
    first = client.post("/runs", json=body, headers=headers)
    assert first.status_code == 200
    run_id = first.json()["id"]
    assert client.post("/runs", json=body, headers=headers).json()["id"] == run_id
    assert client.get("/runs?offset=0&limit=1").json()["total"] == 1
    assert client.get(f"/runs/{run_id}").status_code == 200
    assert client.get("/runs/missing").status_code == 404
    assert (
        client.post("/runs", json={**body, "path": "private"}, headers=headers).status_code == 422
    )
    assert client.post("/runs", json=body).status_code == 403
    mutation = {"request_id": "cancel-http", "expected_attempt": 1}
    assert (
        client.post(f"/runs/{run_id}/cancel", json=mutation, headers=headers).json()["status"]
        == "cancelled"
    )
    assert (
        client.post(
            f"/runs/{run_id}/retry", json={**mutation, "request_id": "retry-http"}, headers=headers
        ).json()["attempt"]
        == 2
    )
    no_model = RunManager(tmp_path / "disabled", validate=lambda req: None)
    with pytest.raises(ValueError, match="MODEL_NOT_AVAILABLE"):
        no_model.create_or_get_run(request())


@pytest.mark.parametrize("mode", ["wait", "crash", "success", "watchdog"])
def test_real_child_identity_restart_cancel_and_crash(tmp_path, mode):
    children = []

    def launch(run):
        environment = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
        child = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).with_name("vision_lab_run_probe.py")),
                str(tmp_path),
                run.id,
                str(run.attempt),
                str(run.fence),
                run.lease,
                mode,
            ],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        children.append(child)

    manager = RunManager(tmp_path, validate=lambda req: None, models=("test",), launcher=launch)
    try:
        start = request()
        if mode == "watchdog":
            start.configuration.max_seconds = 3
        first = manager.create_or_get_run(start)
        fresh = manager_at(tmp_path)
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            try:
                observed = fresh.detail(first.id)
                if observed.checkpoint is not None:
                    break
            except ValueError as error:
                assert str(error) == "ANNOTATION_STORE_BUSY"
            time.sleep(0.05)
        else:
            raise AssertionError("worker did not checkpoint")
        assert fresh.create_or_get_run(start).id == first.id and len(children) == 1
        if mode == "wait":
            assert observed.status == "running"
            fresh.cancel_run(first.id, RunMutation(request_id="cancel-child", expected_attempt=1))
        out, err = children[0].communicate(timeout=25)
        assert children[0].returncode == ({"crash": 7, "watchdog": 124}.get(mode, 0)), (out, err)
        if mode in {"crash", "watchdog"}:
            future = manager_at(tmp_path, clock=lambda: time.time() + 70)
            ended = future.detail(first.id)
            assert ended.status == "failed" and ended.checkpoint is not None
            if mode == "watchdog":
                assert ended.used_seconds == 3
                assert ended.conservative_seconds == pytest.approx(3 - observed.used_seconds)
            else:
                assert ended.reserved_steps == 1
        else:
            ended = fresh.detail(first.id)
            assert ended.status == ("cancelled" if mode == "wait" else "succeeded")
            assert ended.checkpoint_epoch == 1
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)


def test_polling_does_not_fail_checkpoint_writer(tmp_path):
    manager = manager_at(tmp_path)
    run = manager.create_or_get_run(request())
    manager.claim(run.id, token(run))
    content = checkpoint_content(run, 0)

    def poll():
        for _ in range(20):
            assert manager_at(tmp_path).detail(run.id).status == "running"

    def write():
        for _ in range(5):
            manager.checkpoint(run.id, token(run), content, 0)
            manager.heartbeat(run.id, token(run))

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(poll), pool.submit(write)]
        for future in futures:
            future.result(timeout=30)
    assert manager.detail(run.id).checkpoint is not None


def test_identity_unavailable_never_retries_and_data_drift_never_succeeds(tmp_path):
    manager = manager_at(tmp_path)
    run = manager.create_or_get_run(request())
    manager.claim(run.id, token(run))
    manager.checkpoint(run.id, token(run), checkpoint_content(run, 0), 0)

    def unavailable(pid):
        raise ValueError("RUN_PROCESS_IDENTITY_UNAVAILABLE")

    manager.identity = unavailable
    assert manager.detail(run.id).diagnostics == ["RUN_PROCESS_IDENTITY_UNAVAILABLE"]
    manager.finish(run.id, token(run), status="failed", error="test")
    with pytest.raises(ValueError, match="IDENTITY_UNAVAILABLE"):
        manager.retry_run(run.id, RunMutation(request_id="unknown-pid", expected_attempt=1))
    other = manager_at(tmp_path / "other")
    second = other.create_or_get_run(request())
    other.claim(second.id, token(second))
    other.checkpoint(second.id, token(second), checkpoint_content(second, 1), 1)

    def drift(request):
        raise ValueError("RUN_DATA_DRIFT")

    other.validate = drift
    with pytest.raises(ValueError, match="DATA_DRIFT"):
        other.finish(second.id, token(second), status="succeeded")
    assert other.detail(second.id).status == "running"


def test_run_directory_cannot_overlap_inputs(tmp_path):
    from game_predictor_worker.vision_lab.run_worker import configured_manager

    with pytest.raises(ValueError, match="OVERLAP"):
        configured_manager(
            tmp_path,
            {
                "snapshot": str(tmp_path / "snapshot"),
                "annotations": str(tmp_path / "annotations"),
                "manifests": str(tmp_path / "manifests"),
                "python": sys.executable,
            },
        )
