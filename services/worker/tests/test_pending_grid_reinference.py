from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from game_predictor_api.domain.jobs import Job
from game_predictor_worker.images.board_cell_geometry_activation import (
    BoardCellRecropSnapshotError,
    board_cell_recrop_snapshot,
    validate_board_cell_recrop_snapshot,
)
from game_predictor_worker.images.board_cell_geometry_contract import (
    BOARD_CELL_GEOMETRY_VERSION,
)
from game_predictor_worker.images.board_cell_geometry_crops import CROPPER_VERSION
from game_predictor_worker.images.pending_grid_reinference import (
    PendingGridReinferenceHandler,
)
from game_predictor_worker.jobs.runtime import JobHandlerError


def _job(payload: dict[str, object]) -> Job:
    return cast(Job, SimpleNamespace(input_payload=payload))


def test_v2_snapshot_is_pinned_to_the_accepted_estimator_cropper_and_audit() -> None:
    snapshot = board_cell_recrop_snapshot(cell_output_size=64)

    assert snapshot["geometryVersion"] == BOARD_CELL_GEOMETRY_VERSION
    assert snapshot["cropperVersion"] == CROPPER_VERSION
    assert len(str(snapshot["auditReportChecksumSha256"])) == 64
    assert validate_board_cell_recrop_snapshot(snapshot, cell_output_size=64) == snapshot

    changed = {**snapshot, "geometryVersion": "changed"}
    with pytest.raises(BoardCellRecropSnapshotError):
        validate_board_cell_recrop_snapshot(changed, cell_output_size=64)


@pytest.mark.parametrize("schema_version", [1, 2])
def test_retired_file_crop_job_fails_explicitly_without_touching_storage(
    tmp_path: Path, schema_version: int
) -> None:
    """D-467 S6 (TASK-0796): both payloads wrote v19 crop files for legacy boards."""

    session_factory = MagicMock()
    context = MagicMock()
    handler = PendingGridReinferenceHandler(cast(Any, session_factory), tmp_path)

    with pytest.raises(JobHandlerError) as error:
        handler(context, _job({"schema_version": schema_version}))

    assert error.value.code == "IMAGE_GRID_REINFERENCE_LEGACY_UNSUPPORTED"
    session_factory.assert_not_called()
    context.checkpoint.assert_not_called()
    assert not any(tmp_path.iterdir())


def test_unknown_schema_is_still_rejected_as_unsupported(tmp_path: Path) -> None:
    handler = PendingGridReinferenceHandler(cast(Any, MagicMock()), tmp_path)

    with pytest.raises(JobHandlerError) as error:
        handler(MagicMock(), _job({"schema_version": 3}))

    assert error.value.code == "IMAGE_GRID_REINFERENCE_SCHEMA_UNSUPPORTED"
