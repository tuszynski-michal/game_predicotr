from pathlib import Path
from types import SimpleNamespace

import pytest
from game_predictor_api.application.storage_capacity import StorageCapacityGuard
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.domain.storage_capacity import (
    GIB,
    StorageCapacityPolicy,
    conservative_image_storage_estimate,
    evaluate_storage_capacity,
)


class _Usage:
    total = 200 * GIB
    used = 150 * GIB
    free = 50 * GIB


def test_capacity_deduplicates_roots_on_the_same_volume(monkeypatch, tmp_path: Path) -> None:
    calls: list[Path] = []
    monkeypatch.setattr(
        "game_predictor_api.domain.storage_capacity.shutil.disk_usage",
        lambda path: calls.append(path) or _Usage(),
    )
    decision = evaluate_storage_capacity(
        {"artifact": tmp_path / "artifacts", "import": tmp_path / "imports"},
        estimated_bytes=1 * GIB,
        policy=StorageCapacityPolicy(),
    )
    assert len(calls) == 1
    assert len(decision.volumes) == 1
    assert decision.automatic_gc_required is True
    assert decision.permitted is True


def test_capacity_guard_triggers_gc_then_blocks_below_reserve(monkeypatch, tmp_path: Path) -> None:
    class _LowUsage:
        total = 200 * GIB
        used = 196 * GIB
        free = 4 * GIB

    monkeypatch.setattr(
        "game_predictor_api.domain.storage_capacity.shutil.disk_usage",
        lambda _path: _LowUsage(),
    )
    triggered: list[bool] = []
    guard = StorageCapacityGuard(
        {"artifact": tmp_path},
        policy=StorageCapacityPolicy(),
        ensure_automatic_gc=lambda: triggered.append(True),
    )
    with pytest.raises(JobConflictError, match="managed storage capacity") as error:
        guard.check_image_write(1)
    assert error.value.code == "STORAGE_CAPACITY_INSUFFICIENT"
    assert triggered == [True]


def test_default_hard_reserve_is_five_gib_and_allows_exact_remaining_space(
    monkeypatch, tmp_path: Path
) -> None:
    policy = StorageCapacityPolicy(conservative_multiplier=1, safety_percent=0)
    assert policy.hard_reserve_bytes == 5 * GIB

    monkeypatch.setattr(
        "game_predictor_api.domain.storage_capacity.shutil.disk_usage",
        lambda _path: SimpleNamespace(free=5 * GIB + 1),
    )
    permitted = evaluate_storage_capacity({"artifact": tmp_path}, estimated_bytes=1, policy=policy)

    assert permitted.permitted is True

    monkeypatch.setattr(
        "game_predictor_api.domain.storage_capacity.shutil.disk_usage",
        lambda _path: SimpleNamespace(free=5 * GIB),
    )
    blocked = evaluate_storage_capacity({"artifact": tmp_path}, estimated_bytes=1, policy=policy)

    assert blocked.permitted is False


def test_conservative_estimate_includes_multiplier_and_margin() -> None:
    assert conservative_image_storage_estimate(100, policy=StorageCapacityPolicy()) == 960
