from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError
from game_predictor_api.storage.models import ImageBoardGeometryRevisionModel
from game_predictor_api.storage.virtual_grid_geometry_repository import (
    SqlAlchemyVirtualGridGeometryRepository,
    _reset_grid_issue_after_virtual_recrop,
)
from sqlalchemy.dialects import postgresql


@pytest.mark.parametrize("backfill_status", ("not_started", "rebuilding", "failed"))
def test_current_virtual_source_context_is_not_blocked_by_another_source_backfill(
    backfill_status: str,
) -> None:
    session = Mock()
    session.scalars.return_value = tuple(_review_cell() for _ in range(15))
    repository = SqlAlchemyVirtualGridGeometryRepository(session)

    context = repository._context_from_row(  # noqa: SLF001 - repository boundary regression
        _complete_current_virtual_row(backfill_status=backfill_status)
    )

    assert context.active_board_slots == (0,)
    assert context.position_index == 0
    assert context.topology.cell_count == 15


def test_current_virtual_source_context_still_rejects_incomplete_cell_projection() -> None:
    session = Mock()
    session.scalars.return_value = tuple(_review_cell() for _ in range(14))
    repository = SqlAlchemyVirtualGridGeometryRepository(session)

    with pytest.raises(ImageGridReviewError, match="every review cell") as raised:
        repository._context_from_row(  # noqa: SLF001 - repository boundary regression
            _complete_current_virtual_row(backfill_status="not_started")
        )

    assert raised.value.code == "IMAGE_GRID_REVIEW_CELLS_INCOMPLETE"


def test_virtual_geometry_crop_artifacts_none_binds_as_sql_null() -> None:
    column_type = ImageBoardGeometryRevisionModel.__table__.c.crop_artifacts.type
    processor = column_type.bind_processor(postgresql.dialect())

    assert column_type.none_as_null is True
    assert processor is not None
    assert processor(None) is None


def test_virtual_recrop_resets_grid_issue_to_pending_model_suggestion() -> None:
    predicted_symbol_id = uuid4()
    cell = SimpleNamespace(
        assigned_symbol_id=uuid4(),
        assignment_source="human",
        prediction_symbol_code="cherry",
        quality_issue="grid_issue",
        review_state="pending",
    )

    _reset_grid_issue_after_virtual_recrop(
        cell,
        active_symbol_ids_by_code={"cherry": predicted_symbol_id},
    )

    assert cell.review_state == "pending"
    assert cell.quality_issue is None
    assert cell.assignment_source == "model"
    assert cell.assigned_symbol_id == predicted_symbol_id


def _complete_current_virtual_row(*, backfill_status: str) -> tuple[object, ...]:
    game_id = uuid4()
    import_job_id = uuid4()
    source_geometry_id = uuid4()
    source_checksum = "a" * 64
    normalized_checksum = "b" * 64
    geometry_checksum = "c" * 64
    return (
        SimpleNamespace(id=uuid4(), resolution_revision=0),
        SimpleNamespace(
            id=uuid4(),
            asset_mode="virtual_source",
            source_geometry_revision_id=source_geometry_id,
            geometry_checksum_sha256=geometry_checksum,
            grid_rows=3,
            grid_columns=5,
            position_index=0,
            geometry_revision=0,
        ),
        SimpleNamespace(
            id=uuid4(),
            import_job_id=import_job_id,
            file_execution_key="f" * 64,
            relative_path="originals/current.jpg",
            checksum_sha256=source_checksum,
            raw_width=1080,
            raw_height=1920,
            oriented_width=1080,
            oriented_height=1920,
            exif_orientation=1,
            normalized_pixel_checksum_sha256=normalized_checksum,
            normalization_adapter_version="image-normalization-v2-in-memory-source-v1",
        ),
        SimpleNamespace(
            id=source_geometry_id,
            revision=1,
            topology_rules_version_id=uuid4(),
            sequence_range_start=1,
            sequence_range_end=1,
            active_board_slots=[0],
            global_initialization=None,
            board_geometries=[{"positionIndex": 0, "sequenceNumber": 1}],
            geometry_checksum_sha256=geometry_checksum,
        ),
        SimpleNamespace(game_id=game_id, backfill_status=backfill_status),
        SimpleNamespace(sequence_number=1),
    )


def _review_cell() -> SimpleNamespace:
    return SimpleNamespace(
        render_spec={
            "configuration": {
                "extractorVersion": "virtual-cell-renderer-v1",
                "preprocessingVersion": "rgb-v1",
                "interpolation": "bilinear-v1",
                "outputWidth": 64,
                "outputHeight": 64,
                "paddingFraction": 0.0,
            }
        }
    )
