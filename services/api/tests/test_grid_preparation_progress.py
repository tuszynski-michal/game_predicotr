"""Preparation may grow indefinitely; a heartbeat must not hide stalled data work."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from game_predictor_api.application.grid_learning_preparation import (
    acquire_learning_game_lock,
    prepare,
)
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.storage import grid_preparation_progress as progress
from game_predictor_api.storage import grid_training_cohort_repository as repository
from sqlalchemy.exc import DBAPIError


def test_real_progress_renews_stall_budget_without_a_total_deadline(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(repository.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(progress, "monotonic", lambda: clock[0])
    units = []
    with progress.preparation_progress(lambda *unit: units.append(unit)):
        deadline = progress.preparation_deadline()
        for current in range(10):
            clock[0] += 200
            progress.report_preparation("geometry_evidence", current, 10)
        assert clock[0] > 300
        deadline.check()
        clock[0] += 301
        with pytest.raises(GridCohortError, match="No preparation progress"):
            progress.report_preparation("geometry_evidence", 10, 10)
    assert len(units) == 10
    assert isinstance(progress.preparation_deadline(), repository.CohortDeadline)
    assert not isinstance(progress.preparation_deadline(), progress.PreparationDeadline)


def test_repeated_same_unit_does_not_renew_and_nested_scope_restores(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(repository.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(progress, "monotonic", lambda: clock[0])
    with progress.preparation_progress(lambda *_: None):
        outer = progress.preparation_deadline()
        progress.report_preparation("reading", 0, 1)
        with progress.preparation_progress(lambda *_: None):
            assert progress.preparation_deadline() is not outer
        assert progress.preparation_deadline() is outer
        clock[0] = 200
        progress.report_preparation("reading", 0, 1)
        clock[0] = 301
        with pytest.raises(GridCohortError):
            outer.check()


@pytest.mark.parametrize("blockers", [[], ["SCREEN_FULL_PHOTOS_REQUIRED"]])
def test_preparation_rejects_changed_default_or_failed_quality_before_publishing(
    tmp_path, blockers
):
    base = str(uuid4())
    preview = {
        "canStart": not blockers,
        "blockers": blockers,
        "baseVersionId": str(uuid4()),
        "defaultRevision": 6,
    }
    service = SimpleNamespace(_preview=lambda *_: (preview, {}), artifact_root=tmp_path)
    job = SimpleNamespace(
        game_id=uuid4(),
        input_payload={
            "command": {"trainingMode": "screen+grid", "prepareInBackground": True},
            "preview": {"baseVersionId": base, "defaultRevision": 5},
        },
    )
    with pytest.raises(GridCohortError) as error, prepare(service, job):
        pytest.fail("Blocked data must not be published.")
    assert error.value.code == (blockers[0] if blockers else "GRID_LEARNING_DEFAULT_CHANGED")
    assert not list(tmp_path.iterdir())


def test_busy_game_admission_lock_maps_to_retryable_conflict():
    class Busy(Exception):
        sqlstate = "55P03"

    def execute(*_):
        raise DBAPIError("advisory lock", {}, Busy(), False)

    with pytest.raises(GridCohortError) as error:
        acquire_learning_game_lock(SimpleNamespace(execute=execute), uuid4())
    assert error.value.code == "GRID_LEARNING_BUSY"
    assert error.value.status == 409
