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


def _manifest_cell(index: int) -> dict[str, object]:
    return {
        "cellIndex": index,
        "logicalCellKeySha256": f"{index + 1:064x}",
        "logicalCellKeyV2Sha256": f"{index + 2:064x}",
        "renderIdentityV2Sha256": f"{index + 3:064x}",
        "renderSpec": {"cellIndex": index},
        "renderSpecChecksumSha256": f"{index + 4:064x}",
        "renderedPixelChecksumSha256": f"{index + 5:064x}",
    }


def test_rollout_validation_accepts_a_manifest_only_virtual_board(monkeypatch) -> None:
    """D-467 (TASK-0790): new virtual boards have a manifest and no observations."""

    from types import SimpleNamespace
    from uuid import uuid4

    import pytest
    from game_predictor_api.storage import image_geometry_rollout_backfill_repository as module

    geometry = SimpleNamespace(id=uuid4())
    source = SimpleNamespace(id=uuid4())
    board = SimpleNamespace(
        id=uuid4(),
        grid_rows=3,
        grid_columns=5,
        unavailable_cell_indices=[],
        geometry_qualification=None,
        asset_mode="virtual_source",
    )
    manifests: dict[str, object] = {}

    def load(_session, *, game_id, board):  # type: ignore[no-untyped-def]
        return manifests.get("value")

    monkeypatch.setattr(module, "load_current_render_manifest", load)
    repository = module.SqlAlchemyImageGeometryRolloutBackfillRepository(None)  # type: ignore[arg-type]
    complete = SimpleNamespace(
        cell_indices=tuple(range(15)),
        source_geometry_revision_id=geometry.id,
        cells=tuple(_manifest_cell(index) for index in range(15)),
    )
    manifests["value"] = complete
    repository._validate_manifest_cells(
        game_id=uuid4(), source=source, board=board, geometry=geometry
    )
    for broken in (
        None,
        SimpleNamespace(**{**complete.__dict__, "cell_indices": tuple(range(14))}),
        SimpleNamespace(**{**complete.__dict__, "source_geometry_revision_id": uuid4()}),
        SimpleNamespace(
            **{
                **complete.__dict__,
                "cells": (
                    {**_manifest_cell(0), "renderSpecChecksumSha256": "x"},
                    *complete.cells[1:],
                ),
            }
        ),
    ):
        manifests["value"] = broken
        with pytest.raises(module.ImageGeometryRolloutBackfillError) as error:
            repository._validate_manifest_cells(
                game_id=uuid4(), source=source, board=board, geometry=geometry
            )
        assert error.value.code == "IMAGE_GEOMETRY_ROLLOUT_CELL_PROVENANCE_INVALID"
