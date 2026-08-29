from dataclasses import replace
from uuid import uuid4

import pytest
from game_predictor_api.storage.image_geometry_v2_repository import (
    ImageGeometryPersistenceError,
    SourceGeometryRevisionInput,
    SqlAlchemyImageGeometryRolloutRepository,
    SqlAlchemyImageSourceGeometryRepository,
)
from game_predictor_api.storage.models import (
    CellObservationModel,
    ImageGeometryRolloutStateModel,
    ImageSourceGeometryRevisionModel,
    ImageSymbolReviewCellModel,
    RecognizedBoardModel,
)

_SHA = "a" * 64


def _source_geometry_input() -> SourceGeometryRevisionInput:
    return SourceGeometryRevisionInput(
        game_id=uuid4(),
        source_image_id=uuid4(),
        topology_rules_version_id=uuid4(),
        sequence_range_start=10,
        sequence_range_end=11,
        active_board_slots=(0, 1),
        source_checksum_sha256=_SHA,
        normalized_pixel_checksum_sha256="b" * 64,
        oriented_width=3000,
        oriented_height=2000,
        normalization_adapter_version="image-normalization-v2",
        global_initialization=None,
        board_geometries=({"positionIndex": 0}, {"positionIndex": 1}),
        engine_kind="structured_opencv_v1",
        engine_version="structured-page-geometry-v1",
        geometry_source="auto",
        status="pending",
        geometry_checksum_sha256="c" * 64,
        processing_time_ms=10,
        warnings=(),
        created_by="test",
    )


def test_dual_asset_models_allow_null_paths_only_through_conditional_constraints() -> None:
    assert RecognizedBoardModel.__table__.c.board_relative_path.nullable is True
    assert CellObservationModel.__table__.c.crop_relative_path.nullable is True
    assert ImageSymbolReviewCellModel.__table__.c.crop_relative_path.nullable is True

    observation_constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in CellObservationModel.__table__.constraints
        if constraint.name is not None and hasattr(constraint, "sqltext")
    }
    provenance = observation_constraints["ck_cell_observations_asset_provenance"]
    assert "asset_mode = 'legacy_file'" in provenance
    assert "asset_mode = 'virtual_source'" in provenance
    assert "crop_relative_path IS NULL" in provenance
    assert "render_spec_checksum_sha256" in provenance
    assert "rendered_pixel_checksum_sha256" in provenance


def test_virtual_geometry_tables_default_rollout_to_legacy() -> None:
    assert ImageSourceGeometryRevisionModel.__table__.c.board_geometries.nullable is False
    assert ImageSourceGeometryRevisionModel.__table__.c.source_checksum_sha256.nullable is False
    assert ImageGeometryRolloutStateModel.__table__.c.geometry_mode.server_default is not None
    assert ImageGeometryRolloutStateModel.__table__.c.cell_asset_mode.server_default is not None
    assert (
        str(ImageGeometryRolloutStateModel.__table__.c.geometry_mode.server_default.arg)
        == "'legacy'"
    )
    assert (
        str(ImageGeometryRolloutStateModel.__table__.c.cell_asset_mode.server_default.arg)
        == "'legacy_files'"
    )


def test_source_geometry_repository_rejects_non_contiguous_attested_slots() -> None:
    value = _source_geometry_input()
    invalid = replace(value, active_board_slots=(0, 2))

    with pytest.raises(ImageGeometryPersistenceError) as error:
        SqlAlchemyImageSourceGeometryRepository._validate_input(invalid)

    assert error.value.code == "IMAGE_GEOMETRY_SEQUENCE_ATTESTATION_INVALID"


@pytest.mark.parametrize("limit", [0, 501])
def test_rollout_backfill_rejects_unbounded_batch_sizes(limit: int) -> None:
    repository = SqlAlchemyImageGeometryRolloutRepository(session=None)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="limit must be between"):
        repository.backfill_legacy_states(limit=limit)
