"""TASK-0950 (D-539): a replacement photo takes over only rejected or unowned sequences.

Runs on a dedicated ``*_test`` database only (fixtures of
``test_virtual_deferred_resolution_postgres``). Every import goes through the
worker's import writer (``SqlAlchemyImagePipelineStore.project_recognition``)
and every rejection through the production services, so the API slot path and
the worker path share the ownership rule under test.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.image_symbol_review_mutations import (
    SymbolCellReviewMutationService,
)
from game_predictor_api.domain.board_cell_geometry_pending import BoardRejectionReason
from game_predictor_api.domain.image_reviews import ImageReviewAction
from game_predictor_api.domain.neural_crop_policy import (
    NEURAL_AUTO_CROP_PAYLOAD_KEY,
    NEURAL_AUTO_CROP_POLICY,
)
from game_predictor_api.domain.sequence_takeover import (
    CANONICAL_ALTERNATIVE_REASON,
    EXISTING_OWNER_KEPT_REASON,
)
from game_predictor_api.storage import pending_sequence_ownership
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.geometry_correction_revert_models import (
    ImageBoardGeometryPendingEventModel,
)
from game_predictor_api.storage.image_geometry_completeness_state_repository import (
    recompute_source_image_geometry_completeness,
)
from game_predictor_api.storage.image_review_repository import (
    SqlAlchemyOperationalImageReviewRepository,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemySymbolCellReviewMutationRepository,
)
from game_predictor_api.storage.lateral_reprocess_protection import has_protected_lateral_owner
from game_predictor_api.storage.models import (
    ImageBoardGeometryPendingModel,
    ImageReviewItemModel,
    ImageSequenceAlternativeModel,
    ImageSequenceCanonicalModel,
    ImageSymbolReviewCellModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
    SymbolModel,
)
from game_predictor_api.storage.sequence_ownership_lock import (
    SequenceOwnershipLockMode,
    acquire_sequence_ownership_lock,
)
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from test_image_geometry_completeness_gate import (
    _import,
    _report,
    _resolve_slot,
    _seeded,
    _state,
)
from test_pending_slot_rejection_postgres import (
    _cell_rows,
    _entries,
    _items,
    _make_board_partial,
    _rebuild_symbol_counts,
    _reject_slot,
    _resolve_board,
    _symbol_counts,
    _visible_cells,
)
from test_reviewer_operational_geometry_postgres import _app
from test_virtual_deferred_resolution_postgres import (
    _Database,
    _pending_service,
    _points,
    _Seed,
    _seed,
    database,  # noqa: F401  (pytest fixture)
    pytestmark,  # noqa: F401  (PostgreSQL opt-in)
)


def _replacement(
    factory: sessionmaker[Session],
    old: _Seed,
    artifact_root: Path,
    *,
    label: str,
    slots: int,
    start: int,
) -> _Seed:
    """A second photo of the same game, imported later through the worker."""

    seed = _seed(
        factory, old.game_id, artifact_root, label=label, slot_count=slots, sequence_base=start
    )
    _import(factory, seed, label, range(slots))
    return seed


def _items_of(factory: sessionmaker[Session], seed: _Seed) -> dict[int, dict[str, Any]]:
    """Review item, board status and resolution of every board of one photo."""

    with game_storage_scope(seed.game_id), factory() as session:
        rows = session.execute(
            select(RecognizedBoardModel, ImageReviewItemModel)
            .join(
                ImageReviewItemModel,
                ImageReviewItemModel.recognized_board_id == RecognizedBoardModel.id,
            )
            .where(RecognizedBoardModel.source_image_id == seed.source_image_id)
        ).all()
        value = {
            int(item.sequence_number or 0): {
                "item": item.id,
                "status": item.status,
                "board_status": board.status,
                "resolved_value": item.resolved_value,
            }
            for board, item in rows
        }
        session.rollback()
    return value


def _alternatives(factory: sessionmaker[Session], seed: _Seed) -> dict[int, tuple[str, str]]:
    with game_storage_scope(seed.game_id), factory() as session:
        rows = session.scalars(
            select(ImageSequenceAlternativeModel).where(
                ImageSequenceAlternativeModel.game_id == seed.game_id,
                ImageSequenceAlternativeModel.import_job_id == seed.import_job_id,
            )
        ).all()
        value = {int(row.sequence_number): (row.reason, row.source_checksum_sha256) for row in rows}
        session.rollback()
    return value


def _checksum(factory: sessionmaker[Session], seed: _Seed) -> str:
    with game_storage_scope(seed.game_id), factory() as session:
        source = session.get(SourceImageModel, seed.source_image_id)
        assert source is not None
        value = source.checksum_sha256
        session.rollback()
    return value


def _ownership(factory: sessionmaker[Session], seed: _Seed) -> Any:
    report, _page = _report(factory, seed.game_id, seed.import_job_id)
    assert report is not None
    return report.sequence_ownership


def test_a_replacement_takes_over_only_the_rejected_slot_and_the_old_photo_is_cut(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    """Acceptance: A has a rejected slot for S and eight good boards; B covers all."""

    factory, old, artifact_root = _seeded(database, tmp_path, "task0950-a", 9)
    _import(factory, old, "task0950-a", range(1, 9))
    game_id = old.game_id
    _reject_slot(factory, artifact_root, old, 0, reason=BoardRejectionReason.CROPPED)
    withheld = _state(factory, game_id, old.source_image_id)
    assert withheld["status"] == "geometry_incomplete"
    assert withheld["boards"] == 8 and withheld["cells"] == 0
    old_items = _items_of(factory, old)
    assert sorted(old_items) == list(range(101, 109))
    # The exact counters are live (a finished projection) before the replacement.
    _rebuild_symbol_counts(factory, old)
    assert _symbol_counts(factory, old) == 0

    new = _replacement(factory, old, artifact_root, label="task0950-bb", slots=9, start=100)

    # B owns only S = 100; A keeps its eight sequences.
    new_items = _items_of(factory, new)
    assert new_items[100]["status"] == "pending"
    assert new_items[100]["board_status"] == "pending_review"
    for sequence in range(101, 109):
        superseded = new_items[sequence]
        assert superseded["status"] == "superseded"
        assert superseded["board_status"] == "rejected"
        assert superseded["resolved_value"] == {
            "action": "superseded",
            "ownerReviewItemId": str(old_items[sequence]["item"]),
            "reason": EXISTING_OWNER_KEPT_REASON,
            "sequenceNumber": sequence,
        }
    assert {sequence: value["status"] for sequence, value in _items_of(factory, old).items()} == {
        sequence: "pending" for sequence in range(101, 109)
    }
    checksum = _checksum(factory, new)
    assert _alternatives(factory, new) == {
        sequence: (EXISTING_OWNER_KEPT_REASON, checksum) for sequence in range(101, 109)
    }

    # A's rejected slot is closed as superseded and keeps its rejection as history.
    with game_storage_scope(game_id), factory() as session:
        slot = session.get(ImageBoardGeometryPendingModel, old.pending_ids[0])
        assert slot is not None
        assert slot.status == "superseded" and slot.superseded_at is not None
        assert slot.rejection_reason == "cropped" and slot.rejected_at is not None
        events = session.scalars(
            select(ImageBoardGeometryPendingEventModel)
            .where(ImageBoardGeometryPendingEventModel.pending_geometry_id == slot.id)
            .order_by(ImageBoardGeometryPendingEventModel.created_at)
        ).all()
        assert [(event.action, event.rejection_revision) for event in events] == [
            ("rejected", 1),
            ("superseded", 1),
        ]
        assert events[1].successor_review_item_id == new_items[100]["item"]
        assert events[1].import_job_id == old.import_job_id
        session.rollback()
    # The rejection is no longer offered for a revert.
    assert all(entry.pending_geometry_id != old.pending_ids[0] for entry in _entries(factory, old))

    # A's gate was recomputed in the same transaction: admitted and cut.
    admitted = _state(factory, game_id, old.source_image_id)
    assert admitted["status"] == "geometry_complete"
    assert admitted["boards"] == 8
    assert admitted["cells"] == 120 and admitted["distinct_cells"] == 120
    assert admitted["documents_with_evidence"] == 8
    replacement = _state(factory, game_id, new.source_image_id)
    assert replacement["status"] == "geometry_complete"
    assert replacement["boards"] == 1 and replacement["cells"] == 15

    # Exact counters agree with the visible list and with a full rebuild.
    assert _visible_cells(factory, old) == 135
    assert _symbol_counts(factory, old) == 135
    _rebuild_symbol_counts(factory, old)
    assert _symbol_counts(factory, old) == 135

    # The import report shows the replaced and the skipped sequences.
    ownership = _ownership(factory, new)
    assert ownership.replaced_count == 1
    assert ownership.replaced_sequence_numbers == (100,)
    assert ownership.skipped_count == 8
    assert ownership.skipped_sequence_numbers == tuple(range(101, 109))
    old_ownership = _ownership(factory, old)
    assert old_ownership.replaced_count == 0 and old_ownership.skipped_count == 0
    game_report, _page = _report(factory, game_id, None)
    assert game_report is not None and game_report.sequence_ownership is None

    # The HTTP contract carries the same numbers.
    app = _app(database, artifact_root)
    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/admin/image-review-items/geometry-completeness/{game_id}",
                params={"importJobId": str(new.import_job_id)},
            )
    finally:
        app.state.database_engine.dispose()
    assert response.status_code == 200, response.text
    assert response.json()["sequenceOwnership"] == {
        "replacedCount": 1,
        "replacedSequenceNumbers": [100],
        "skippedCount": 8,
        "skippedSequenceNumbers": list(range(101, 109)),
    }


def test_a_rejected_cut_board_is_replaced_without_double_counting_its_cells(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    """The owner is a rejected review item whose cells left the counters on rejection."""

    factory, old, artifact_root = _seeded(database, tmp_path, "task0950-item", 2)
    _import(factory, old, "task0950-item", [0, 1])
    game_id = old.game_id
    _rebuild_symbol_counts(factory, old)
    assert _visible_cells(factory, old) == 30 and _symbol_counts(factory, old) == 30
    items = _items(factory, old)
    _resolve_board(factory, old, items[1], action=ImageReviewAction.REJECTED, reason="cropped")
    assert _visible_cells(factory, old) == 15 and _symbol_counts(factory, old) == 15

    new = _replacement(factory, old, artifact_root, label="task0950-item-b", slots=1, start=101)

    new_items = _items_of(factory, new)
    assert new_items[101]["status"] == "pending"
    # The rejected item stays rejected (its rejection is history, not reopened).
    assert _items_of(factory, old)[101]["status"] == "rejected"
    assert _alternatives(factory, new) == {}
    assert _state(factory, game_id, new.source_image_id)["status"] == "geometry_complete"
    assert _state(factory, game_id, old.source_image_id)["status"] == "geometry_complete"
    # The logical cells of the sequence moved to the replacement (one row per
    # cell and sequence) and are counted once; nothing was deleted.
    assert _cell_rows(factory, old) == 30
    with game_storage_scope(game_id), factory() as session:
        owners = set(
            session.scalars(
                select(ImageSymbolReviewCellModel.review_item_id).where(
                    ImageSymbolReviewCellModel.game_id == game_id,
                    ImageSymbolReviewCellModel.sequence_number == 101,
                )
            )
        )
        session.rollback()
    assert owners == {new_items[101]["item"]}
    assert _visible_cells(factory, old) == 30
    assert _symbol_counts(factory, old) == 30
    _rebuild_symbol_counts(factory, old)
    assert _symbol_counts(factory, old) == 30
    ownership = _ownership(factory, new)
    assert ownership.replaced_sequence_numbers == (101,) and ownership.skipped_count == 0


def test_an_unowned_sequence_rejected_before_the_import_is_taken_over(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    """A position rejected in the Admin guard before import has no slot and no board."""

    factory, old, artifact_root = _seeded(database, tmp_path, "task0950-guard", 9)
    _import(factory, old, "task0950-guard", range(1, 9))
    game_id = old.game_id
    # The guard decision left no open slot and no board at position 0.
    with game_storage_scope(game_id), factory.begin() as session:
        session.execute(
            text(
                "UPDATE game_data_v2.image_board_geometry_pending SET status = 'superseded', "
                "superseded_at = now() WHERE id = :id"
            ),
            {"id": old.pending_ids[0]},
        )
        recompute_source_image_geometry_completeness(session, game_id, old.source_image_id)
    assert _state(factory, game_id, old.source_image_id)["status"] == "geometry_incomplete"

    new = _replacement(factory, old, artifact_root, label="task0950-guard-b", slots=1, start=100)

    assert _items_of(factory, new)[100]["status"] == "pending"
    assert _alternatives(factory, new) == {}
    # The gap of A is covered by B now: A is admitted and cut.
    admitted = _state(factory, game_id, old.source_image_id)
    assert admitted["status"] == "geometry_complete" and admitted["cells"] == 120
    ownership = _ownership(factory, new)
    assert ownership.replaced_count == 0 and ownership.skipped_count == 0


def test_a_canonical_owner_still_wins_first_save(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    factory, old, artifact_root = _seeded(database, tmp_path, "task0950-canon", 1)
    _import(factory, old, "task0950-canon", [0])
    item = _items(factory, old)[0]
    _resolve_board(factory, old, item, action=ImageReviewAction.ACCEPTED)

    new = _replacement(factory, old, artifact_root, label="task0950-canon-b", slots=1, start=100)

    with game_storage_scope(old.game_id), factory() as session:
        canonical = session.scalar(
            select(ImageSequenceCanonicalModel).where(
                ImageSequenceCanonicalModel.game_id == old.game_id,
                ImageSequenceCanonicalModel.sequence_number == 100,
            )
        )
        assert canonical is not None and canonical.review_item_id == item["item"]
        session.rollback()
    # The worker's first-save-wins path is unchanged: no board, one alternative.
    assert _items_of(factory, new) == {}
    assert _alternatives(factory, new) == {
        100: (CANONICAL_ALTERNATIVE_REASON, _checksum(factory, new))
    }
    ownership = _ownership(factory, new)
    assert ownership.replaced_count == 0
    assert ownership.skipped_sequence_numbers == (100,)


def _owner_ids(factory: sessionmaker[Session], game_id: UUID, sequence: int) -> list[UUID]:
    with game_storage_scope(game_id), factory() as session:
        value = list(
            session.scalars(
                select(ImageReviewItemModel.id).where(
                    ImageReviewItemModel.game_id == game_id,
                    ImageReviewItemModel.sequence_number == sequence,
                    ImageReviewItemModel.status == "pending",
                )
            )
        )
        session.rollback()
    return value


def test_a_pending_slot_of_the_old_photo_resolved_later_keeps_the_live_owner(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    """The API slot path uses the same rule: a live pending board of another photo stays."""

    factory, old, artifact_root = _seeded(database, tmp_path, "task0950-slot", 2)
    _import(factory, old, "task0950-slot", [1])
    new = _replacement(factory, old, artifact_root, label="task0950-slot-bb", slots=1, start=100)
    [owner] = _owner_ids(factory, old.game_id, 100)
    assert owner == _items_of(factory, new)[100]["item"]

    app = _app(database, artifact_root)
    path = (
        f"/api/v1/admin/games/{old.game_id}/image-imports/{old.import_job_id}/"
        f"board-cell-geometry-pending/{old.pending_ids[0]}/manual-resolution"
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                path,
                json={
                    "corners": [
                        {"x": 60, "y": 50},
                        {"x": 560, "y": 50},
                        {"x": 560, "y": 350},
                        {"x": 60, "y": 350},
                    ],
                    "correctedBy": "task-0950-operator",
                    "expectedGeometryRevision": 0,
                    "expectedManifestChecksumSha256": old.manifest_checksums[0],
                    "expectedResolutionRevision": 0,
                    "idempotencyKey": "6b0e0d8a-2f6e-4b8a-9f43-0d1c2a3b4c5d",
                },
            )
    finally:
        app.state.database_engine.dispose()
    assert response.status_code == 200, response.text

    # D-539: the newer slot board of the old photo does not replace B.
    assert _owner_ids(factory, old.game_id, 100) == [owner]
    resolved = _items_of(factory, old)[100]
    assert resolved["status"] == "superseded"
    assert resolved["resolved_value"]["reason"] == EXISTING_OWNER_KEPT_REASON
    assert _alternatives(factory, old) == {
        100: (EXISTING_OWNER_KEPT_REASON, _checksum(factory, old))
    }


def test_a_protected_owner_of_another_photo_skips_a_neural_import_with_an_alternative(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    """P0-1: the lateral protection keeps the owner and the skip is recorded."""

    factory, old, artifact_root = _seeded(database, tmp_path, "task0950-lateral", 1)
    resolved = _resolve_slot(database, artifact_root, old, 0, str(uuid4()))
    assert resolved.status_code == 200, resolved.text
    [owner] = _owner_ids(factory, old.game_id, 100)
    new = _seed(
        factory,
        old.game_id,
        artifact_root,
        label="task0950-lateral-bb",
        slot_count=1,
        sequence_base=100,
    )
    with game_storage_scope(new.game_id), factory.begin() as session:
        job = session.get(JobModel, new.import_job_id)
        assert job is not None
        job.input_payload = {
            **job.input_payload,
            NEURAL_AUTO_CROP_PAYLOAD_KEY: NEURAL_AUTO_CROP_POLICY,
        }
        session.flush()
        # The manually drawn owner is protected for the neural import.
        assert has_protected_lateral_owner(
            session,
            job=job,
            sequence_number=100,
            source_checksum_sha256=_checksum(factory, new),
        )

    _import(factory, new, "task0950-lateral-bb", [0])

    assert _owner_ids(factory, old.game_id, 100) == [owner]
    skipped = _items_of(factory, new)[100]
    assert skipped["status"] == "superseded" and skipped["board_status"] == "rejected"
    assert skipped["resolved_value"]["reason"] == EXISTING_OWNER_KEPT_REASON
    assert skipped["resolved_value"]["ownerReviewItemId"] == str(owner)
    assert _alternatives(factory, new) == {
        100: (EXISTING_OWNER_KEPT_REASON, _checksum(factory, new))
    }
    ownership = _ownership(factory, new)
    assert ownership.skipped_count == 1 and ownership.skipped_sequence_numbers == (100,)
    assert ownership.replaced_count == 0


def _sequence_cells(
    factory: sessionmaker[Session], game_id: UUID, sequence: int
) -> dict[int, ImageSymbolReviewCellModel]:
    with game_storage_scope(game_id), factory() as session:
        value = {
            cell.cell_index: cell
            for cell in session.scalars(
                select(ImageSymbolReviewCellModel).where(
                    ImageSymbolReviewCellModel.game_id == game_id,
                    ImageSymbolReviewCellModel.sequence_number == sequence,
                )
            )
        }
        # Detached snapshots: the rollback must not expire them.
        session.expunge_all()
        session.rollback()
    return value


def _symbol_id(factory: sessionmaker[Session], game_id: UUID, code: str) -> UUID:
    with factory() as session:
        value = session.scalar(
            select(SymbolModel.id).where(SymbolModel.game_id == game_id, SymbolModel.code == code)
        )
        session.rollback()
    assert value is not None
    return value


def _mutations(session: Session) -> SymbolCellReviewMutationService:
    return SymbolCellReviewMutationService(SqlAlchemySymbolCellReviewMutationRepository(session))


def test_a_rejected_partial_board_with_outside_cells_is_replaced_by_a_full_photo(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    """P0-2: the old history lacks the outside crops; the new cells are complete."""

    factory, old, artifact_root = _seeded(database, tmp_path, "task0950-partial", 2)
    _import(factory, old, "task0950-partial", [0, 1])
    game_id = old.game_id
    items = _items(factory, old)
    _make_board_partial(factory, old, items[1])
    cherry = _symbol_id(factory, game_id, "WISNIA")
    outside = _sequence_cells(factory, game_id, 101)[0]
    assert outside.source_visibility == "outside" and outside.crop_sample_id is None
    _rebuild_symbol_counts(factory, old)
    # A logical decision on a position without an image (D-451).
    with game_storage_scope(game_id), factory.begin() as session:
        _mutations(session).reassign(
            game_id=game_id,
            cell_review_id=outside.id,
            expected_revision=outside.revision,
            expected_geometry_revision=outside.geometry_revision,
            expected_crop_sample_id=None,
            expected_crop_checksum_sha256=None,
            target_symbol_id=cherry,
            actor="task-0950-operator",
        )
    _rebuild_symbol_counts(factory, old)
    _resolve_board(factory, old, items[1], action=ImageReviewAction.REJECTED, reason="cropped")
    assert _symbol_counts(factory, old) == 15

    new = _replacement(factory, old, artifact_root, label="task0950-partial-b", slots=1, start=101)

    new_item = _items_of(factory, new)[101]["item"]
    cells = _sequence_cells(factory, game_id, 101)
    assert sorted(cells) == list(range(15))
    assert {cell.review_item_id for cell in cells.values()} == {new_item}
    assert all(
        cell.source_available
        and cell.source_visibility != "outside"
        and cell.crop_sample_id is not None
        for cell in cells.values()
    )
    # The decision of the position that had no image is kept as a suggestion.
    assert cells[0].assigned_symbol_id == cherry
    assert cells[0].assignment_source == "human" and cells[0].review_state == "pending"
    assert _visible_cells(factory, old) == 30 and _symbol_counts(factory, old) == 30
    assert _visible_cells(factory, old, outside_only=True) == 0
    assert _symbol_counts(factory, old, outside_only=True) == 0
    _rebuild_symbol_counts(factory, old)
    assert _symbol_counts(factory, old) == 30


def test_an_old_approval_of_other_pixels_keeps_its_provenance_across_boards(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    """P0-3: revision 0 -> 0 of another board is no rebind of the approval."""

    factory, old, artifact_root = _seeded(database, tmp_path, "task0950-approval", 2)
    _import(factory, old, "task0950-approval", [0, 1])
    game_id = old.game_id
    items = _items(factory, old)
    _rebuild_symbol_counts(factory, old)
    approved = _sequence_cells(factory, game_id, 101)[3]
    with game_storage_scope(game_id), factory.begin() as session:
        _mutations(session).approve(
            game_id=game_id,
            cell_review_id=approved.id,
            expected_revision=approved.revision,
            expected_geometry_revision=approved.geometry_revision,
            expected_crop_sample_id=approved.crop_sample_id,
            expected_crop_checksum_sha256=approved.crop_checksum_sha256,
            actor="task-0950-operator",
        )
    before = _sequence_cells(factory, game_id, 101)[3]
    assert before.review_state == "approved" and before.approved_geometry_revision == 0
    history_keys = (
        "approved_crop_sample_id",
        "approved_crop_checksum_sha256",
        "approved_geometry_revision",
        "approved_asset_mode",
        "approved_source_geometry_revision_id",
        "approved_render_spec_checksum_sha256",
        "approved_rendered_pixel_checksum_sha256",
    )
    history = {key: getattr(before, key) for key in history_keys}
    _resolve_board(factory, old, items[1], action=ImageReviewAction.REJECTED, reason="cropped")

    new = _replacement(factory, old, artifact_root, label="task0950-approval-b", slots=1, start=101)

    after = _sequence_cells(factory, game_id, 101)[3]
    assert after.review_item_id == _items_of(factory, new)[101]["item"]
    assert after.geometry_revision == 0
    assert after.crop_checksum_sha256 != before.crop_checksum_sha256
    # D-462: other pixels need a new check; the old approval stays as history
    # with its own provenance, never the new photo's render.
    assert after.review_state == "pending" and after.assignment_source == "human"
    assert {key: getattr(after, key) for key in history_keys} == history
    assert after.approved_source_geometry_revision_id != after.source_geometry_revision_id


def _resolve_in_thread(
    factory: sessionmaker[Session],
    artifact_root: Path,
    seed: _Seed,
    index: int,
    barrier: threading.Barrier,
    errors: list[BaseException],
) -> None:
    try:
        barrier.wait(timeout=30)
        with game_storage_scope(seed.game_id), factory.begin() as session:
            _pending_service(session, artifact_root).resolve_manual(
                seed.pending_ids[index],
                game_id=seed.game_id,
                import_job_id=seed.import_job_id,
                expected_manifest_checksum_sha256=seed.manifest_checksums[index],
                idempotency_key=uuid4(),
                expected_geometry_revision=0,
                expected_resolution_revision=0,
                corners=_points(),
                corrected_by="task-0950-operator",
                resolved_at=datetime.now(UTC),
            )
    except BaseException as error:  # noqa: BLE001 - reported by the test
        errors.append(error)


def test_concurrent_takeovers_of_crossed_images_never_deadlock(
    database: _Database,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0-4: A resolves its slot 100 and B its slot 101 at the same time.

    Both images are incomplete and cover 100-108, so each takeover recomputes
    the other image's gate. The recompute is slowed down so both transactions
    hold their own image when they reach the other one; the game's
    sequence-ownership lock serializes them instead of a deadlock.
    """

    factory, first, artifact_root = _seeded(database, tmp_path, "task0950-crossed", 9)
    _import(factory, first, "task0950-crossed", range(2, 9))
    second = _seed(
        factory,
        first.game_id,
        artifact_root,
        label="task0950-crossed-second",
        slot_count=2,
        sequence_base=100,
    )
    game_id = first.game_id
    assert _state(factory, game_id, first.source_image_id)["status"] == "geometry_incomplete"
    assert _state(factory, game_id, second.source_image_id)["status"] == "geometry_incomplete"

    original = pending_sequence_ownership.recompute_source_images

    def slow_recompute(*args: Any, **kwargs: Any) -> Any:
        time.sleep(1.0)
        return original(*args, **kwargs)

    monkeypatch.setattr(pending_sequence_ownership, "recompute_source_images", slow_recompute)
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []
    threads = [
        threading.Thread(
            target=_resolve_in_thread,
            args=(factory, artifact_root, first, 0, barrier, errors),
        ),
        threading.Thread(
            target=_resolve_in_thread,
            args=(factory, artifact_root, second, 1, barrier, errors),
        ),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert not any(thread.is_alive() for thread in threads)
    assert errors == []

    # Each image owns the sequence it resolved and covers the other one.
    assert _owner_ids(factory, game_id, 100) == [_items_of(factory, first)[100]["item"]]
    assert _owner_ids(factory, game_id, 101) == [_items_of(factory, second)[101]["item"]]
    first_state = _state(factory, game_id, first.source_image_id)
    second_state = _state(factory, game_id, second.source_image_id)
    assert first_state["status"] == "geometry_complete" and first_state["boards"] == 8
    assert first_state["cells"] == 120
    assert second_state["status"] == "geometry_complete" and second_state["boards"] == 1
    assert second_state["cells"] == 15


def test_a_cell_decision_and_a_concurrent_import_of_its_sequence_never_deadlock(
    database: _Database,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0-5: the cell decision holds sequence 101 when a neural import wants it.

    The decision (a grid-issue mark on an accepted board) reopens the board
    after its sequence lock; the import takes the exclusive ownership lock and
    then all its sequence locks. The decision took the shared ownership lock
    first, so the import waits for it instead of a cycle.
    """

    factory, old, artifact_root = _seeded(database, tmp_path, "task0950-cellrace", 2)
    _import(factory, old, "task0950-cellrace", [0, 1])
    game_id = old.game_id
    items = _items(factory, old)
    _resolve_board(factory, old, items[1], action=ImageReviewAction.ACCEPTED)
    _rebuild_symbol_counts(factory, old)
    new = _seed(
        factory,
        game_id,
        artifact_root,
        label="task0950-cellrace-b",
        slot_count=1,
        sequence_base=101,
    )
    with game_storage_scope(game_id), factory.begin() as session:
        job = session.get(JobModel, new.import_job_id)
        assert job is not None
        job.input_payload = {
            **job.input_payload,
            NEURAL_AUTO_CROP_PAYLOAD_KEY: NEURAL_AUTO_CROP_POLICY,
        }
    cell = _sequence_cells(factory, game_id, 101)[4]

    holds_sequence = threading.Event()
    original = SqlAlchemyOperationalImageReviewRepository.reopen_for_symbol_cell_issue

    def slow_reopen(self: Any, **kwargs: Any) -> Any:
        # The decision holds the sequence lock here; let the import queue up.
        holds_sequence.set()
        time.sleep(1.5)
        return original(self, **kwargs)

    monkeypatch.setattr(
        SqlAlchemyOperationalImageReviewRepository, "reopen_for_symbol_cell_issue", slow_reopen
    )
    errors: list[BaseException] = []

    def decide() -> None:
        try:
            with game_storage_scope(game_id), factory.begin() as session:
                _mutations(session).mark_grid_issue(
                    game_id=game_id,
                    cell_review_id=cell.id,
                    expected_revision=cell.revision,
                    expected_geometry_revision=cell.geometry_revision,
                    expected_crop_sample_id=cell.crop_sample_id,
                    expected_crop_checksum_sha256=cell.crop_checksum_sha256,
                    actor="task-0950-operator",
                )
        except BaseException as error:  # noqa: BLE001 - reported by the test
            errors.append(error)

    def import_replacement() -> None:
        try:
            assert holds_sequence.wait(timeout=60)
            _import(factory, new, "task0950-cellrace-b", [0])
        except BaseException as error:  # noqa: BLE001 - reported by the test
            errors.append(error)

    threads = [threading.Thread(target=decide), threading.Thread(target=import_replacement)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert not any(thread.is_alive() for thread in threads)
    assert errors == []
    # The decision reopened the board; the import kept it as the live owner.
    assert _items_of(factory, old)[101]["status"] == "pending"
    assert _items_of(factory, new)[101]["status"] == "superseded"
    assert _alternatives(factory, new) == {
        101: (EXISTING_OWNER_KEPT_REASON, _checksum(factory, new))
    }


def test_shared_ownership_holders_never_block_each_other(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    factory, old, _artifact_root = _seeded(database, tmp_path, "task0950-shared", 1)
    game_id = old.game_id
    first, second, writer = factory(), factory(), factory()
    try:
        first.begin()
        acquire_sequence_ownership_lock(
            first, game_id=game_id, mode=SequenceOwnershipLockMode.SHARED
        )
        second.begin()
        second.execute(text("SET LOCAL lock_timeout = '2s'"))
        # A second shared holder (another cell decision) is granted at once.
        acquire_sequence_ownership_lock(
            second, game_id=game_id, mode=SequenceOwnershipLockMode.SHARED
        )
        writer.begin()
        writer.execute(text("SET LOCAL lock_timeout = '300ms'"))
        # An exclusive writer (an import) waits for both.
        with pytest.raises(OperationalError) as blocked:
            acquire_sequence_ownership_lock(writer, game_id=game_id)
        assert "lock timeout" in str(blocked.value).lower()
    finally:
        for session in (writer, second, first):
            session.rollback()
            session.close()
    # Once released, the exclusive writer gets it.
    with factory.begin() as session:
        acquire_sequence_ownership_lock(session, game_id=game_id)
