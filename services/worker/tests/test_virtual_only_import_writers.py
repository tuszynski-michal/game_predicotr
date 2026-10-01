"""TASK-0790 (D-467): import writers accept only virtual boards and rollouts."""

from __future__ import annotations

from typing import cast
from uuid import uuid4

import pytest
from game_predictor_api.domain.jobs import Job, JobType, create_job
from game_predictor_worker.images import pipeline_store
from game_predictor_worker.images.pipeline_contract import (
    CellAssetRolloutMode,
    GeometryPipelineRolloutSnapshot,
    GeometryRolloutMode,
    StructuredGeometryCandidateSnapshot,
)
from game_predictor_worker.images.production_workflow import (
    NON_VIRTUAL_ROLLOUT_ERROR,
    ProductionImageImportWorkflow,
    _require_virtual_geometry_rollout,
)
from game_predictor_worker.images.structured_geometry.lattice_refinement_v3 import (
    structured_lattice_candidate_config_payload,
)
from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError


def _rollout(
    geometry_mode: GeometryRolloutMode,
    cell_asset_mode: CellAssetRolloutMode,
) -> GeometryPipelineRolloutSnapshot:
    return GeometryPipelineRolloutSnapshot(
        geometry_mode=geometry_mode,
        cell_asset_mode=cell_asset_mode,
        rollout_revision=0,
        geometry_engine_version="test-engine",
        virtual_renderer_version="test-renderer",
        preprocessing_version="test-preprocessing",
        candidate_geometry=(
            StructuredGeometryCandidateSnapshot.from_config_payload(
                structured_lattice_candidate_config_payload()
            )
            if geometry_mode is GeometryRolloutMode.STRUCTURED_SHADOW
            else None
        ),
    )


def _virtual_crop(position: int) -> dict[str, object]:
    return {
        "assetMode": "virtual_source",
        "cells": [{"assetMode": "virtual_source", "rowIndex": 0, "columnIndex": 0}],
        "positionIndex": position,
    }


@pytest.mark.parametrize(
    ("geometry_mode", "cell_asset_mode"),
    (
        (GeometryRolloutMode.LEGACY, CellAssetRolloutMode.LEGACY_FILES),
        (GeometryRolloutMode.STRUCTURED_SHADOW, CellAssetRolloutMode.VIRTUAL_SHADOW),
        (GeometryRolloutMode.STRUCTURED_REVIEW, CellAssetRolloutMode.VIRTUAL_SHADOW),
    ),
)
def test_import_refuses_a_removed_legacy_or_shadow_rollout(
    geometry_mode: GeometryRolloutMode,
    cell_asset_mode: CellAssetRolloutMode,
) -> None:
    with pytest.raises(JobHandlerError) as error:
        _require_virtual_geometry_rollout(_rollout(geometry_mode, cell_asset_mode))
    assert error.value.code == NON_VIRTUAL_ROLLOUT_ERROR


@pytest.mark.parametrize(
    "geometry_mode",
    (GeometryRolloutMode.STRUCTURED_DEFAULT,),
)
def test_import_accepts_a_virtual_default_rollout(geometry_mode: GeometryRolloutMode) -> None:
    _require_virtual_geometry_rollout(_rollout(geometry_mode, CellAssetRolloutMode.VIRTUAL_DEFAULT))


def test_job_without_rollout_snapshot_fails_before_any_write() -> None:
    """A historical job (no snapshot = legacy engine) fails with an explicit code."""

    job = create_job(
        JobType.IMPORT,
        game_id=uuid4(),
        input_payload={"import_kind": "image_directory", "schema_version": 2},
    )
    # No dependency is constructed: the gate must run before ingestion.
    workflow = object.__new__(ProductionImageImportWorkflow)
    with pytest.raises(JobHandlerError) as error:
        workflow(cast(JobExecutionContext, None), cast(Job, job))
    assert error.value.code == NON_VIRTUAL_ROLLOUT_ERROR


def test_writer_refuses_a_legacy_file_crop_board() -> None:
    legacy = {
        "boardRelativePath": "boards/0.png",
        "cells": [{"cropRelativePath": "cells/0.png", "rowIndex": 0, "columnIndex": 0}],
        "positionIndex": 0,
    }
    with pytest.raises(pipeline_store.ImagePipelineStoreError) as error:
        pipeline_store._require_virtual_crop_payload({"boards": [legacy]}, {0: legacy})
    assert error.value.code == pipeline_store.NON_VIRTUAL_BOARD_WRITE_ERROR


def test_writer_refuses_a_virtual_board_with_a_legacy_cell() -> None:
    mixed = _virtual_crop(0)
    mixed["cells"] = [{"cropRelativePath": "cells/0.png", "rowIndex": 0, "columnIndex": 0}]
    payload = {"assetMode": "virtual_source", "boards": [mixed]}
    with pytest.raises(pipeline_store.ImagePipelineStoreError) as error:
        pipeline_store._require_virtual_crop_payload(payload, {0: mixed})
    assert error.value.code == pipeline_store.NON_VIRTUAL_BOARD_WRITE_ERROR


def test_writer_accepts_virtual_boards_including_a_board_without_cells() -> None:
    empty = {**_virtual_crop(1), "cells": []}
    crops = {0: _virtual_crop(0), 1: empty}
    pipeline_store._require_virtual_crop_payload(
        {"assetMode": "virtual_source", "boards": list(crops.values())}, crops
    )


def test_writer_module_no_longer_writes_cell_observations() -> None:
    import inspect

    assert "CellObservationModel" not in inspect.getsource(pipeline_store)
