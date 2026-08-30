from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest
from game_predictor_api.domain.jobs import JobType
from game_predictor_api.storage.image_geometry_rollout_backfill_repository import (
    ImageGeometryRolloutBackfillError,
    SqlAlchemyImageGeometryRolloutBackfillRepository,
)
from sqlalchemy.orm import Session


class _BindingSession:
    def __init__(self, job: object) -> None:
        self.job = job

    def get(self, _model: object, _identity: object) -> object:
        return self.job


def _job(*, rollout_revision: int = 4) -> SimpleNamespace:
    return SimpleNamespace(
        id=UUID("30000000-0000-0000-0000-000000000001"),
        game_id=UUID("30000000-0000-0000-0000-000000000002"),
        job_type=JobType.IMAGE_GEOMETRY_ROLLOUT_BACKFILL,
        input_payload={
            "schema_version": 2,
            "workflow": "image_geometry_rollout_backfill",
            "generation": 1,
            "rollout_revision": rollout_revision,
            "geometry_mode": "structured_opencv",
            "cell_asset_mode": "virtual_source",
        },
    )


def _state() -> SimpleNamespace:
    return SimpleNamespace(
        game_id=UUID("30000000-0000-0000-0000-000000000002"),
        revision=4,
        validation_rollout_revision=None,
        validation_input_checksum_sha256=None,
        validation_job_id=None,
        updated_by="test",
    )


def test_rollout_ready_binding_is_exactly_tied_to_job_input() -> None:
    job = _job()
    state = _state()
    repository = SqlAlchemyImageGeometryRolloutBackfillRepository(
        cast(Session, _BindingSession(job))
    )

    repository._bind_validation_job(state=state, job=job)  # type: ignore[arg-type]
    repository._require_current_validation_binding(state)  # type: ignore[arg-type]

    assert state.validation_rollout_revision == 4
    assert len(state.validation_input_checksum_sha256) == 64
    assert state.validation_job_id == job.id


def test_rollout_binding_rejects_a_policy_revision_drift() -> None:
    job = _job()
    state = _state()
    repository = SqlAlchemyImageGeometryRolloutBackfillRepository(
        cast(Session, _BindingSession(job))
    )
    repository._bind_validation_job(state=state, job=job)  # type: ignore[arg-type]
    state.revision = 5

    with pytest.raises(ImageGeometryRolloutBackfillError) as raised:
        repository._require_current_validation_binding(state)  # type: ignore[arg-type]

    assert raised.value.code == "IMAGE_GEOMETRY_ROLLOUT_VALIDATION_BINDING_STALE"
