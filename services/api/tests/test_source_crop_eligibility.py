from __future__ import annotations

from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.source_crop_eligibility import (
    CropBoardGeometry,
    CropExclusion,
    CropSourceFacts,
    classify_blob,
    managed_original_relative_path,
)

SHA = "ab" + "c" * 62
QUAD = [[100, 50], [300, 50], [300, 200], [100, 200]]


def _facts(**changes: object) -> CropSourceFacts:
    values: dict[str, object] = {
        "game_id": UUID(int=1),
        "source_image_id": uuid4(),
        "import_job_id": uuid4(),
        "checksum_sha256": SHA,
        "relative_path": managed_original_relative_path(SHA),
        "coordinate_space": "exif-normalized-rgb-pixels-v1",
        "oriented_width": 1080,
        "oriented_height": 589,
        "exif_orientation": None,
        "normalized_pixel_checksum_sha256": "d" * 64,
        "geometry_completeness_status": "geometry_complete",
        "game_storage_status": "active",
        "import_status": "completed",
        "active_board_count": 1,
        "unapproved_board_count": 0,
        "incomplete_board_count": 0,
        "unaccepted_revision_board_count": 0,
        "pending_geometry_count": 0,
        "grid_issue_count": 0,
        "pending_proposal_count": 0,
        "page_exclusion_count": 0,
        "active_image_job_count": 0,
        "registration_anchor_count": 0,
    }
    values.update(changes)
    return CropSourceFacts(**values)  # type: ignore[arg-type]


def _board(source: CropSourceFacts, *documents: object) -> CropBoardGeometry:
    return CropBoardGeometry(
        source_image_id=source.source_image_id, board_id=uuid4(), documents=documents
    )


def _quads(*sources: CropSourceFacts) -> list[CropBoardGeometry]:
    return [_board(source, {"finalQuad": QUAD}) for source in sources]


def test_a_fully_approved_blob_is_eligible_with_its_quads() -> None:
    source = _facts()

    result = classify_blob(SHA, [source], _quads(source))

    assert result.eligible
    assert result.original_relative_path == f"originals/ab/{SHA}.jpg"
    assert len(result.protected_points) == 4


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"relative_path": "seq_1.jpg"}, CropExclusion.UNMANAGED_PATH),
        ({"coordinate_space": None}, CropExclusion.NO_COORDINATE_METADATA),
        ({"exif_orientation": 5}, CropExclusion.ORIENTATION_UNSUPPORTED),
        ({"game_storage_status": "migrating"}, CropExclusion.GAME_STORAGE_NOT_ACTIVE),
        ({"import_status": "created"}, CropExclusion.IMPORT_NOT_SETTLED),
        ({"import_status": "processing"}, CropExclusion.IMPORT_NOT_SETTLED),
        ({"import_status": "failed"}, CropExclusion.IMPORT_NOT_SETTLED),
        ({"import_status": "cancelled"}, CropExclusion.IMPORT_NOT_SETTLED),
        ({"geometry_completeness_status": "geometry_exception"}, CropExclusion.GEOMETRY_INCOMPLETE),
        ({"unapproved_board_count": 1}, CropExclusion.GEOMETRY_NOT_APPROVED),
        ({"incomplete_board_count": 1}, CropExclusion.BOARD_NOT_COMPLETE),
        ({"unaccepted_revision_board_count": 1}, CropExclusion.SOURCE_REVISION_NOT_ACCEPTED),
        ({"pending_geometry_count": 1}, CropExclusion.PENDING_GEOMETRY_CORRECTION),
        ({"grid_issue_count": 2}, CropExclusion.GRID_ISSUE),
        ({"pending_proposal_count": 1}, CropExclusion.PENDING_GRID_PROPOSAL),
        ({"page_exclusion_count": 1}, CropExclusion.PAGE_SOURCE_EXCLUDED),
        ({"active_image_job_count": 1}, CropExclusion.ACTIVE_IMAGE_JOB),
        ({"registration_anchor_count": 1}, CropExclusion.PAGE_REGISTRATION_ANCHOR),
    ],
)
def test_each_source_condition_excludes_the_blob(
    changes: dict[str, object], reason: CropExclusion
) -> None:
    source = _facts(**changes)

    result = classify_blob(SHA, [source], _quads(source))

    assert not result.eligible
    assert reason in result.exclusions
    assert result.protected_points == ()


def test_a_source_without_active_boards_is_excluded() -> None:
    source = _facts(active_board_count=0)

    assert CropExclusion.NO_ACTIVE_BOARDS in classify_blob(SHA, [source], []).exclusions


def test_one_ineligible_sharing_source_excludes_every_game() -> None:
    good = _facts()
    other_game = replace(_facts(), game_id=UUID(int=2), pending_geometry_count=1)

    result = classify_blob(SHA, [good, other_game], _quads(good, other_game))

    assert result.exclusions == (CropExclusion.PENDING_GEOMETRY_CORRECTION,)
    assert result.game_ids == (UUID(int=1), UUID(int=2))


def test_sharing_sources_must_agree_on_the_image_identity() -> None:
    first, second = _facts(), _facts(oriented_width=1081)

    result = classify_blob(SHA, [first, second], _quads(first, second))

    assert CropExclusion.IDENTITY_MISMATCH in result.exclusions


def test_a_board_without_quads_is_not_hidden_by_the_other_boards() -> None:
    source = _facts(active_board_count=2)
    boards = [_board(source, {"finalQuad": QUAD}), _board(source, {"cells": []})]

    result = classify_blob(SHA, [source], boards)

    assert result.exclusions == (CropExclusion.BOARD_GEOMETRY_MISSING,)


def test_a_missing_board_row_is_detected_from_the_board_count() -> None:
    source = _facts(active_board_count=2)

    result = classify_blob(SHA, [source], _quads(source))

    assert result.exclusions == (CropExclusion.BOARD_GEOMETRY_MISSING,)


def test_malformed_quads_exclude() -> None:
    source = _facts()

    result = classify_blob(SHA, [source], [_board(source, {"finalQuad": [[1, 2]]})])

    assert result.exclusions == (CropExclusion.PROTECTED_QUADS_INVALID,)


def test_facts_of_another_blob_or_board_are_rejected() -> None:
    with pytest.raises(ValueError):
        classify_blob("f" * 64, [_facts()], [])
    with pytest.raises(ValueError):
        classify_blob(SHA, [_facts()], [_board(_facts(), {"finalQuad": QUAD})])


@pytest.mark.parametrize("status", ["completed", "waiting_for_review"])
def test_settled_imports_qualify(status: str) -> None:
    """D-563: the review trigger moves an import between these two states."""

    source = _facts(import_status=status)

    assert classify_blob(SHA, [source], _quads(source)).eligible
