from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest
from game_predictor_api.api.image_grid_reviews import _require_expected_source
from game_predictor_api.domain.geometry_qualification import (
    GeometryQualification,
    GeometryQualificationError,
    parse_slot_qualifications,
    qualification_from_geometry,
)
from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError
from game_predictor_api.domain.page_geometry_overrides import ImagePageGeometryOverride
from game_predictor_api.schemas.geometry_qualification import GeometryQualificationPayload
from game_predictor_api.schemas.image_grid_reviews import ImageGridReviewGeometryPreviewCommand
from game_predictor_api.storage.image_import_geometry_guard_repository import (
    _decision as read_guard_decision,
)
from game_predictor_api.storage.models import (
    ImageImportGeometryGuardDecisionModel,
    ImagePageGeometryOverrideModel,
    RecognizedBoardModel,
)
from game_predictor_api.storage.page_geometry_override_repository import (
    SqlAlchemyPageGeometryOverrideRepository,
)
from game_predictor_api.storage.virtual_grid_geometry_repository import (
    _project_geometry_qualification,
)
from sqlalchemy.dialects import postgresql


@pytest.mark.parametrize("missing", [(), (0,), (0, 4, 10, 14), tuple(range(15))])
def test_qualification_roundtrips_including_all_unavailable(missing: tuple[int, ...]) -> None:
    value = GeometryQualification(
        completeness_status="pending_partial" if missing else "complete",
        unavailable_cell_indices=missing,
        exclude_from_geometry_training=bool(missing),
        exclusion_reason="missing_pixels" if missing else None,
    )
    assert GeometryQualification.from_dict(value.to_dict()) == value
    assert GeometryQualificationPayload.model_validate(value.to_dict()).to_domain() == value


@pytest.mark.parametrize(
    "changes",
    [
        {"completenessStatus": "pending_partial"},
        {"completenessStatus": []},
        {"unavailableCellIndices": [True]},
        {"unavailableCellIndices": [1.0]},
        {"unavailableCellIndices": [1, 1]},
        {"unavailableCellIndices": [2, 1]},
        {"unavailableCellIndices": [-1]},
        {"unavailableCellIndices": [15]},
        {"excludeFromGeometryTraining": 1},
        {"excludeFromGeometryTraining": True},
        {"exclusionReason": "missing_pixels"},
        {"version": "future"},
        {"unknownField": True},
    ],
)
def test_invalid_decision_is_never_coerced(changes: dict[str, object]) -> None:
    with pytest.raises(GeometryQualificationError):
        GeometryQualification.from_dict(GeometryQualification().to_dict() | changes)


def test_partial_exclusion_cannot_be_removed() -> None:
    partial = GeometryQualification("pending_partial", (0,), True, "missing_pixels")
    with pytest.raises(GeometryQualificationError):
        replace(partial, exclude_from_geometry_training=False)


def test_slots_require_exact_count_and_legacy_stays_absent() -> None:
    full = GeometryQualification().to_dict()
    assert parse_slot_qualifications(None, expected_board_count=9) is None
    for size in (0, 8, 10):
        with pytest.raises(GeometryQualificationError):
            parse_slot_qualifications([full] * size, expected_board_count=9)
    assert len(parse_slot_qualifications([full] * 5, expected_board_count=5)) == 5


def test_legacy_partial_read_is_excluded_without_rewriting_geometry() -> None:
    geometry = {"finalQuad": []}
    result = qualification_from_geometry(
        geometry, completeness_status="pending_partial", unavailable_cell_indices=(0,)
    )
    assert result.exclude_from_geometry_training
    assert geometry == {"finalQuad": []}


def test_override_repository_roundtrip_after_new_repository_instance() -> None:
    values = (
        GeometryQualification(),
        GeometryQualification("complete", (), True, "manual_exclusion"),
        GeometryQualification("pending_partial", tuple(range(15)), True, "missing_pixels"),
    )
    point = {"x": 1, "y": 1}
    value = ImagePageGeometryOverride(
        id=uuid4(),
        game_id=uuid4(),
        source_checksum_sha256="a" * 64,
        image_width=100,
        image_height=100,
        final_quads=((point,) * 4,) * 3,
        revision=1,
        actor="test",
        decision_checksum_sha256="b" * 64,
        created_at=datetime.now(UTC),
        slot_qualifications=values,
    )
    session = Mock()
    SqlAlchemyPageGeometryOverrideRepository(session).append(value)
    stored = session.add.call_args.args[0]
    # Exercise SQLAlchemy JSON serialization, not a shared in-memory domain object.
    column = ImagePageGeometryOverrideModel.__table__.c.slot_qualifications.type
    bind = column.bind_processor(postgresql.dialect())
    read = column.result_processor(postgresql.dialect(), None)
    stored.slot_qualifications = read(bind(stored.slot_qualifications))
    session.scalar.return_value = stored
    restored = SqlAlchemyPageGeometryOverrideRepository(session).get_current(
        game_id=value.game_id, source_checksum_sha256=value.source_checksum_sha256
    )
    assert restored == value
    assert bind(None) is None


def test_projection_uses_source_revision_decision() -> None:
    value = GeometryQualification("pending_partial", tuple(range(15)), True, "missing_pixels")
    slot = {"positionIndex": 0, "geometryQualification": value.to_dict()}
    board = RecognizedBoardModel(board_geometry=slot)
    _project_geometry_qualification(board, slot)
    assert board.completeness_status == "pending_partial"
    assert board.unavailable_cell_indices == list(range(15))
    assert board.geometry_qualification == value.to_dict()


def test_guard_database_projection_roundtrips_complete_exclusion() -> None:
    qualification = GeometryQualification("complete", (), True, "manual_exclusion")
    row = ImageImportGeometryGuardDecisionModel(
        id=uuid4(),
        game_id=uuid4(),
        browser_selection_id=uuid4(),
        guard_job_id=uuid4(),
        guard_report_checksum_sha256="a" * 64,
        source_checksum_sha256="b" * 64,
        source_relative_path="seq_1-9.jpg",
        position_index=0,
        sequence_number=1,
        revision=1,
        disposition="corrected_full",
        symbol_grid_quad=[{"x": 1, "y": 1}] * 4,
        unavailable_cell_indices=[],
        geometry_qualification=qualification.to_dict(),
        reason=None,
        actor="test",
        decision_checksum_sha256="c" * 64,
        created_at=datetime.now(UTC),
    )
    result = read_guard_decision(row)
    assert result.geometry_qualification == qualification
    assert result.unavailable_cell_indices == ()


def test_old_grid_writer_rejects_new_metadata_before_loading_or_mutating() -> None:
    service = Mock()
    command = ImageGridReviewGeometryPreviewCommand.model_validate(
        {
            "expectedGeometryRevision": 0,
            "expectedResolutionRevision": 0,
            "expectedSourceChecksumSha256": "a" * 64,
            "expectedSourceWidth": 320,
            "expectedSourceHeight": 320,
            "expectedGridRows": 3,
            "expectedGridColumns": 5,
            "corners": [{"x": 0, "y": 0}, {"x": 20, "y": 0}, {"x": 20, "y": 20}, {"x": 0, "y": 20}],
            "geometryQualification": GeometryQualification().to_dict(),
        }
    )
    with pytest.raises(ImageGridReviewError) as error:
        _require_expected_source(service, uuid4(), uuid4(), command)
    assert error.value.code == "IMAGE_GRID_REVIEW_QUALIFICATION_NOT_ENABLED"
    assert service.mock_calls == []
