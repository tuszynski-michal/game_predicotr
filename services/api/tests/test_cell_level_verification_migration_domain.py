from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.cell_level_verification_migration import (
    BoardMigrationPlan,
    CellFingerprint,
    CellLevelMigrationError,
    board_fingerprint,
    build_manifest,
    plan_board_migration,
    validate_manifest,
)

GAME_ID = UUID("bfc4f949-5c14-4850-b02a-db99610bcfa5")


def _plan(**overrides: object) -> BoardMigrationPlan:
    values: dict[str, object] = {
        "review_item_id": uuid4(),
        "sequence_number": 7,
        "status": "pending",
        "fingerprint": "f" * 64,
        "changed_pixel_approvals": (),
        "resolution_after_recheck": None,
        "projection_stale": False,
    }
    values.update(overrides)
    return plan_board_migration(**values)  # type: ignore[arg-type]


def test_an_approval_of_other_pixels_goes_back_to_verification() -> None:
    plan = _plan(changed_pixel_approvals=(4, 1, 4))

    assert plan.recheck_cell_indices == (1, 4)
    assert plan.reopen is False
    assert plan.close_action is None
    assert plan.has_actions


def test_a_board_resolved_on_other_pixels_is_reopened() -> None:
    plan = _plan(status="accepted", changed_pixel_approvals=(2,))

    assert plan.reopen is True
    assert plan.recheck_cell_indices == (2,)
    # A resolved board without such approvals is left alone.
    assert not _plan(status="corrected").has_actions


def test_only_a_pending_board_with_complete_evidence_closes() -> None:
    assert _plan(resolution_after_recheck="corrected").close_action == "corrected"
    # A rechecked cell is pending, so the board cannot close in the same run.
    assert (
        _plan(resolution_after_recheck="accepted", changed_pixel_approvals=(0,)).close_action
        is None
    )
    assert _plan(status="accepted", resolution_after_recheck="accepted").close_action is None


def test_a_board_without_any_action_is_not_part_of_the_manifest() -> None:
    assert not _plan().has_actions
    assert _plan(projection_stale=True).has_actions


def test_invalid_inputs_are_rejected() -> None:
    with pytest.raises(CellLevelMigrationError):
        _plan(status="superseded")
    with pytest.raises(CellLevelMigrationError):
        _plan(resolution_after_recheck="rejected")


def test_the_fingerprint_changes_with_any_cell_value() -> None:
    cell = CellFingerprint(
        cell_index=0,
        revision=3,
        review_state="approved",
        crop_checksum_sha256="a" * 64,
        rendered_pixel_checksum_sha256=None,
    )
    base = board_fingerprint(
        status="pending", resolution_revision=1, geometry_revision=2, cells=(cell,)
    )
    moved = CellFingerprint(
        cell_index=0,
        revision=4,
        review_state="approved",
        crop_checksum_sha256="a" * 64,
        rendered_pixel_checksum_sha256=None,
    )
    assert base == board_fingerprint(
        status="pending", resolution_revision=1, geometry_revision=2, cells=[cell]
    )
    assert base != board_fingerprint(
        status="pending", resolution_revision=1, geometry_revision=2, cells=(moved,)
    )
    assert base != board_fingerprint(
        status="pending", resolution_revision=2, geometry_revision=2, cells=(cell,)
    )


def test_the_manifest_round_trips_and_its_checksum_guards_the_content() -> None:
    plans = [
        _plan(changed_pixel_approvals=(3,)),
        _plan(status="accepted", changed_pixel_approvals=(0, 1)),
        _plan(resolution_after_recheck="accepted"),
        _plan(projection_stale=True),
    ]
    manifest = build_manifest(
        game_id=GAME_ID,
        plans=plans,
        scanned=10,
        generated_at="2026-09-29T12:00:00+00:00",
        notes={"SYMBOL_CELL_REVIEW_CELLS_INCOMPLETE": ["b", "a"]},
    )

    assert manifest["counts"] == {
        "scannedBoards": 10,
        "boards": 4,
        "recheckCells": 3,
        "recheckBoards": 2,
        "reopenBoards": 1,
        "closeBoards": 1,
        "refreshProjectionBoards": 1,
    }
    assert manifest["notes"] == {"SYMBOL_CELL_REVIEW_CELLS_INCOMPLETE": ["a", "b"]}
    game_id, restored = validate_manifest(manifest)
    assert game_id == GAME_ID
    assert sorted(restored, key=lambda plan: str(plan.review_item_id)) == sorted(
        plans, key=lambda plan: str(plan.review_item_id)
    )
    # The generation time is not part of the checksum.
    again = build_manifest(
        game_id=GAME_ID,
        plans=list(reversed(plans)),
        scanned=10,
        generated_at="later",
        notes={"SYMBOL_CELL_REVIEW_CELLS_INCOMPLETE": ["a", "b"]},
    )
    assert again["previewSha256"] == manifest["previewSha256"]

    tampered = dict(manifest)
    tampered["boards"] = [dict(manifest["boards"][0], recheckCellIndices=[3, 4])]
    with pytest.raises(CellLevelMigrationError) as error:
        validate_manifest(tampered)
    assert error.value.code == "CELL_MIGRATION_MANIFEST_CHECKSUM"


def test_a_manifest_entry_without_an_action_is_invalid() -> None:
    with pytest.raises(CellLevelMigrationError):
        BoardMigrationPlan.from_manifest(
            {
                "reviewItemId": str(uuid4()),
                "sequenceNumber": 1,
                "status": "pending",
                "fingerprint": "f" * 64,
                "reopen": False,
                "recheckCellIndices": [],
                "closeAction": None,
                "refreshProjection": False,
            }
        )
