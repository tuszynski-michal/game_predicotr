"""Local larger budgets, exact request binding, admission and export guards."""

import sys

import pytest
from game_predictor_worker.training_core.runtime import TrainingInterrupted
from game_predictor_worker.vision_lab.annotations import digest, write_atomic
from game_predictor_worker.vision_lab.run_contracts import RunMutation, TrainingConfiguration
from game_predictor_worker.vision_lab.runs import checkpoint_binding, token
from game_predictor_worker.vision_lab.symbol_large_rgb_protocol import (
    MODEL,
    PREPROCESSING,
    PROTOCOL_DIGEST,
    LargeRgbConfiguration,
    LargeRgbRequest,
    LargeRgbRunState,
    admit,
    validate_request,
)
from game_predictor_worker.vision_lab.symbol_large_rgb_runs import (
    BOOT,
    LargeRgbRunManager,
    build_manager,
)
from game_predictor_worker.vision_lab.symbol_runs import BOOT as ORIGINAL_BOOT
from game_predictor_worker.vision_lab.symbol_runs import SymbolRunManager
from pydantic import ValidationError


def request(**updates):
    value = LargeRgbRequest(
        request_id="large-rgb-unit-start",
        manifest_id="a" * 64,
        model_version=MODEL,
        preprocessing_version=PREPROCESSING,
        seed=20261005,
        purpose="train",
        configuration=LargeRgbConfiguration(epochs=20, batch_size=32),
    )
    return value.model_copy(update=updates)


def manager(root, launches, **kwargs):
    return LargeRgbRunManager(
        root,
        validate=validate_request,
        models=(MODEL,),
        state_type=LargeRgbRunState,
        admit=admit,
        launcher=lambda row: launches.append(row.id),
        identity=lambda _: None,
        **kwargs,
    )


def test_larger_contract_does_not_relax_public_contract():
    req = request()
    assert req.configuration.max_seconds == 7200
    assert req.configuration.max_steps == 50000
    with pytest.raises(ValidationError):
        TrainingConfiguration(max_seconds=7200)
    with pytest.raises(ValidationError):
        LargeRgbConfiguration(max_seconds=7201)
    with pytest.raises(ValidationError):
        LargeRgbConfiguration(max_steps=50001)


@pytest.mark.parametrize(
    "change",
    [
        {"model_version": "mumie-symbol-rgb-v4-ai"},
        {"protocol_digest": "a" * 64},
        {"symbol_protocol_digest": "b" * 64},
        {"seed": 1},
        {"purpose": "smoke"},
        {"preprocessing_version": "gray"},
        {"configuration": LargeRgbConfiguration(epochs=2, batch_size=32)},
    ],
)
def test_resigned_request_and_model_copy_cannot_weaken_protocol(change):
    with pytest.raises(ValidationError):
        validate_request(request(**change))


def test_local_digest_is_in_checkpoint_binding_without_hybrid_protocol():
    binding = checkpoint_binding(request())
    assert binding["symbol_protocol_digest"] == PROTOCOL_DIGEST
    assert "protocol" not in binding and "protocol_digest" not in binding
    changed = checkpoint_binding(request(symbol_protocol_digest="b" * 64))
    assert changed["inputFingerprint"] != binding["inputFingerprint"]


def test_lost_response_restart_and_single_variant_admission(tmp_path):
    launches = []
    first = manager(tmp_path, launches).create_or_get_run(request())
    restarted = manager(tmp_path, launches)
    assert restarted.create_or_get_run(request()).id == first.id
    assert launches == [first.id]
    restored = restarted.detail(first.id)
    assert isinstance(restored.request, LargeRgbRequest)
    assert restored.request.symbol_protocol_digest == PROTOCOL_DIGEST
    restarted.cancel_run(first.id, RunMutation(request_id="large-unit-cancel", expected_attempt=1))
    with pytest.raises(ValueError, match="ALREADY_ADMITTED"):
        restarted.create_or_get_run(request(request_id="large-unit-second"))


def test_another_root_cannot_admit_same_manifest(tmp_path):
    manifest_dir = tmp_path / "manifest"
    manifest_dir.mkdir()
    payload = {
        "run_root": str(tmp_path / "fixed-runs"),
        "bundle": str(tmp_path / "bundle"),
        "live_bindings": {},
    }
    manifest = manifest_dir / (digest(payload) + ".json")
    write_atomic(manifest, payload)
    settings = {"manifest": str(manifest), "python": sys.executable, "pythonpath": str(tmp_path)}
    with pytest.raises(ValueError, match="FROZEN_RUN_ROOT_REQUIRED"):
        build_manager(tmp_path / "another-runs", settings, launcher=lambda _: None)


def test_new_boot_and_old_default_are_separate():
    assert SymbolRunManager.worker_boot == ORIGINAL_BOOT
    assert LargeRgbRunManager.worker_boot == BOOT
    assert "symbol_large_rgb_runs" in BOOT
    assert "symbol_large_rgb_runs" not in ORIGINAL_BOOT


def test_missing_exports_cannot_be_reported_as_success(tmp_path):
    run_manager = manager(tmp_path, [])
    run = run_manager.create_or_get_run(request())
    run_manager.claim(run.id, token(run))
    with pytest.raises(ValueError, match="SUCCESS_EXPORT_REQUIRED"):
        run_manager.finish(run.id, token(run), status="succeeded", metrics={})
    assert run_manager.detail(run.id).status == "running"


def test_large_retry_preserves_cumulative_budget_and_fences_previous_attempt(tmp_path):
    now = [1000.0]
    first_manager = manager(tmp_path, [], clock=lambda: now[0])
    first = first_manager.create_or_get_run(request())
    first_manager.claim(first.id, token(first))
    first_manager.heartbeat(first.id, token(first), reserve_step=True)
    now[0] += 70
    failed = first_manager.detail(first.id)
    assert failed.status == "failed" and failed.reserved_steps == 1
    assert failed.used_seconds == failed.conservative_seconds == 70
    restarted = manager(tmp_path, [], clock=lambda: now[0])
    retry_request = RunMutation(request_id="large-unit-retry", expected_attempt=1)
    second = restarted.retry_run(first.id, retry_request)
    assert second.used_seconds == 70 and second.reserved_steps == 1
    assert restarted.retry_run(first.id, retry_request).attempt == 2
    assert token(first) != token(second)
    with pytest.raises(ValueError, match="FENCED"):
        restarted.heartbeat(first.id, token(first), reserve_step=True)
    restarted.claim(second.id, token(second))
    restarted.heartbeat(second.id, token(second), reserve_step=True)
    assert restarted.detail(second.id).reserved_steps == 2


def test_large_cancel_stops_next_batch_without_waiting_for_last_epoch(tmp_path):
    run_manager = manager(tmp_path, [])
    run = run_manager.create_or_get_run(request())
    run_manager.claim(run.id, token(run))
    run_manager.cancel_run(run.id, RunMutation(request_id="large-batch-cancel", expected_attempt=1))
    with pytest.raises(TrainingInterrupted, match="RUN_CANCELLED"):
        run_manager.heartbeat(run.id, token(run), reserve_step=True)
    terminal = run_manager.finish(run.id, token(run), status="cancelled", error="RUN_CANCELLED")
    assert terminal.status == "cancelled" and terminal.reserved_steps == 1
