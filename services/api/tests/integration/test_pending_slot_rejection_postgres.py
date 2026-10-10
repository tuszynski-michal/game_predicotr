"""TASK-0970: rejection of a deferred slot and of a cropped board (PostgreSQL).

Runs on a dedicated ``*_test`` database only (fixtures of
``test_virtual_deferred_resolution_postgres`` and the import writer of
``test_image_geometry_completeness_gate``). Rejections go through the production
application services; the whole game store is compared before and after a
refusal or a revert. W8 (D-484): a rejected position stays a gap, so the image
stays ``geometry_incomplete`` and none of its other boards gets cells.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.geometry_correction_reverts import (
    GeometryCorrectionRevertService,
)
from game_predictor_api.application.image_reviews import OperationalImageReviewService
from game_predictor_api.domain.board_cell_geometry_pending import (
    BoardCellGeometryPendingStatus,
    BoardRejectionReason,
)
from game_predictor_api.domain.geometry_correction_reverts import (
    BOARD_REJECT_CANONICAL,
    GeometryCorrectionKind,
    RejectionTarget,
    RevertBlockingReason,
    encode_board_rejection_reason,
)
from game_predictor_api.domain.image_grid_reviews import (
    ImageGridReviewListFilter,
    ImageGridReviewView,
)
from game_predictor_api.domain.image_reviews import (
    ImageReviewAction,
    ImageReviewConflictError,
    ImageReviewResolutionCell,
)
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellReviewFilterState,
    SymbolCellReviewListFilter,
)
from game_predictor_api.domain.jobs import JobConflictError, JobError
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.geometry_correction_revert_repository import (
    SqlAlchemyGeometryCorrectionRevertRepository,
)
from game_predictor_api.storage.image_grid_review_repository import (
    SqlAlchemyImageGridReviewRepository,
)
from game_predictor_api.storage.image_review_repository import (
    SqlAlchemyOperationalImageReviewRepository,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemyImageSymbolReviewRepository,
    SqlAlchemySymbolCellReviewQueryRepository,
)
from game_predictor_api.storage.models import (
    ImageBoardGeometryPendingModel,
    ImageFileExecutionModel,
    ImageImportJobFileModel,
    ImageReviewItemModel,
    ImageReviewResolutionEventModel,
    ImageSequenceCanonicalModel,
    ImageSourceGeometryRevisionModel,
    ImageSymbolReviewCellModel,
    ImageSymbolReviewStateModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker
from test_geometry_correction_revert_pending_postgres import _world
from test_image_geometry_completeness_gate import (
    _add_image,
    _import,
    _report,
    _seeded,
    _sha,
    _state,
)
from test_reviewer_operational_geometry_postgres import _app
from test_virtual_deferred_resolution_postgres import (
    _PIPELINE,
    _Database,
    _pending_service,
    _points,
    _Seed,
    database,  # noqa: F401  (pytest fixture)
    pytestmark,  # noqa: F401  (PostgreSQL opt-in)
)

_ACTOR = "task-0970-operator"


def _add_replacement(
    factory: sessionmaker[Session], seed: _Seed, label: str, *, position: int, start: int
) -> None:
    """A second image whose live pending board owns ``start + position``."""

    with game_storage_scope(seed.game_id), factory.begin() as session:
        session.add(
            ImageFileExecutionModel(
                file_execution_key=_sha(f"{label}-execution"),
                source_checksum_sha256=_sha(f"{label}-checksum"),
                pipeline_fingerprint=_PIPELINE,
                checkpoint_payload={},
                status="waiting_for_review",
                review_required=True,
            )
        )
        session.flush()
        session.add(
            ImageImportJobFileModel(
                job_id=seed.import_job_id,
                file_execution_key=_sha(f"{label}-execution"),
                order_index=7,
                source_relative_path=f"originals/{label}.jpg",
                workflow_checkpoint_payload={},
                workflow_status="waiting_for_review",
                review_required=True,
            )
        )
        session.flush()
        _add_image(
            session,
            game_id=seed.game_id,
            job_id=seed.import_job_id,
            label=label,
            positions=[position],
            start=start,
        )


def _reject_slot(
    factory: sessionmaker[Session],
    artifact_root: Path,
    seed: _Seed,
    index: int,
    *,
    key: UUID | None = None,
    reason: BoardRejectionReason = BoardRejectionReason.CROPPED,
    note: str | None = None,
    expected_geometry_revision: int = 0,
) -> Any:
    with game_storage_scope(seed.game_id), factory.begin() as session:
        return _pending_service(session, artifact_root).reject(
            seed.pending_ids[index],
            game_id=seed.game_id,
            import_job_id=seed.import_job_id,
            idempotency_key=key or uuid4(),
            expected_geometry_revision=expected_geometry_revision,
            reason=reason,
            note=note,
            rejected_by=_ACTOR,
            rejected_at=datetime.now(UTC),
        )


def _revert_service(session: Session) -> GeometryCorrectionRevertService:
    return GeometryCorrectionRevertService(SqlAlchemyGeometryCorrectionRevertRepository(session))


def _entries(factory: sessionmaker[Session], seed: _Seed) -> Any:
    with game_storage_scope(seed.game_id), factory() as session:
        entries = _revert_service(session).list_recent(
            game_id=seed.game_id, import_job_id=seed.import_job_id
        )
        session.rollback()
    return entries


def _revert(
    factory: sessionmaker[Session],
    seed: _Seed,
    entry: Any,
    *,
    key: UUID,
    geometry_revision: int | None = None,
) -> Any:
    with game_storage_scope(seed.game_id), factory.begin() as session:
        return _revert_service(session).revert(
            game_id=seed.game_id,
            import_job_id=seed.import_job_id,
            board_geometry_revision_id=entry.board_geometry_revision_id,
            idempotency_key=key,
            expected_geometry_revision=(
                entry.geometry_revision if geometry_revision is None else geometry_revision
            ),
            expected_resolution_revision=entry.resolution_revision,
            actor=_ACTOR,
            reverted_at=datetime.now(UTC),
        )


def _queue(factory: sessionmaker[Session], seed: _Seed) -> tuple[set[UUID | None], int]:
    """The deferred slots of the correction view and its counter."""

    review_filter = ImageGridReviewListFilter(
        game_id=seed.game_id,
        view=ImageGridReviewView.CORRECTION,
        import_job_id=seed.import_job_id,
    )
    with game_storage_scope(seed.game_id), factory() as session:
        repository = SqlAlchemyImageGridReviewRepository(session)
        page = repository.list_grid_reviews(
            review_filter=review_filter, after_key=None, before_key=None, limit=50
        )
        counts = repository.grid_review_counts(review_filter=review_filter)
        session.rollback()
    slots = {item.pending_geometry_id for item in page.items if item.pending_geometry_id}
    return slots, counts.correction


def _pending_row(factory: sessionmaker[Session], seed: _Seed, index: int) -> dict[str, Any]:
    with game_storage_scope(seed.game_id), factory() as session:
        row = session.get(ImageBoardGeometryPendingModel, seed.pending_ids[index])
        assert row is not None
        value = {
            "status": row.status,
            "reason": row.rejection_reason,
            "note": row.rejection_note,
            "rejected_at": row.rejected_at,
            "rejected_by": row.rejected_by,
            "sequence_number": row.sequence_number,
        }
        session.rollback()
    return value


def test_a_rejected_slot_leaves_the_queue_and_the_image_stays_incomplete(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    factory, seed, artifact_root = _seeded(database, tmp_path, "task0949-slot", 3)
    _import(factory, seed, "task0949-slot", [1, 2])
    game_id = seed.game_id

    imported = _state(factory, game_id, seed.source_image_id)
    assert imported["status"] == "geometry_incomplete"
    assert imported["boards"] == 2 and imported["cells"] == 0
    slots, correction = _queue(factory, seed)
    assert seed.pending_ids[0] in slots
    assert correction >= 1

    rejection_key = uuid4()
    rejected = _reject_slot(factory, artifact_root, seed, 0, key=rejection_key)
    assert rejected.created is True
    assert rejected.pending.status is BoardCellGeometryPendingStatus.REJECTED
    assert rejected.pending.rejection_reason is BoardRejectionReason.CROPPED
    assert rejected.pending.rejected_by == _ACTOR
    # The slots of the two imported positions stay open rows under their boards.
    assert rejected.counts.rejected == 1 and rejected.counts.pending == 2
    assert rejected.counts.total == 3
    stored = _pending_row(factory, seed, 0)
    assert stored["status"] == "rejected" and stored["reason"] == "cropped"
    assert stored["note"] is None and stored["rejected_at"] is not None

    # W8: the position is a gap for the gate, so the image waits for a
    # replacement and none of its other boards is cut.
    after = _state(factory, game_id, seed.source_image_id)
    assert after["status"] == "geometry_incomplete"
    assert after["boards"] == 2 and after["cells"] == 0
    assert after["documents_with_evidence"] == 0
    report, _page = _report(factory, game_id, seed.import_job_id)
    assert report is not None and report.gate is not None
    assert report.gate.geometry_incomplete == 1
    assert report.gate.withheld_boards == 2
    # The slot left the correction queue and its counters.
    slots, correction_after = _queue(factory, seed)
    assert seed.pending_ids[0] not in slots
    assert correction_after == correction - 1

    # Idempotency is durable (the key is stored with the rejection): the same
    # key and command replay the stored result; the same key with another
    # command conflicts; another key on a rejected slot is "already rejected".
    world = _world(factory, game_id)
    replay = _reject_slot(factory, artifact_root, seed, 0, key=rejection_key)
    assert replay.created is False
    assert replay.rejection_id == rejected.rejection_id
    assert replay.pending.rejected_at == rejected.pending.rejected_at
    with pytest.raises(JobConflictError) as same_key:
        _reject_slot(
            factory,
            artifact_root,
            seed,
            0,
            key=rejection_key,
            reason=BoardRejectionReason.BLURRED,
        )
    assert same_key.value.code == "IMAGE_BOARD_CELL_PENDING_IDEMPOTENCY_CONFLICT"
    for other in (BoardRejectionReason.CROPPED, BoardRejectionReason.BLURRED):
        with pytest.raises(JobConflictError) as other_key:
            _reject_slot(factory, artifact_root, seed, 0, reason=other)
        assert other_key.value.code == "IMAGE_BOARD_CELL_PENDING_ALREADY_REJECTED"
    assert _world(factory, game_id) == world

    # A rejected slot is not editable by the manual resolution; a resolved
    # slot cannot be rejected before its correction is reverted.
    with game_storage_scope(game_id), factory.begin() as session:
        with pytest.raises(JobConflictError) as editable:
            _pending_service(session, artifact_root).resolve_manual(
                seed.pending_ids[0],
                game_id=game_id,
                import_job_id=seed.import_job_id,
                expected_manifest_checksum_sha256=seed.manifest_checksums[0],
                idempotency_key=uuid4(),
                expected_geometry_revision=0,
                expected_resolution_revision=0,
                corners=_points(),
                corrected_by=_ACTOR,
                resolved_at=datetime.now(UTC),
            )
        assert editable.value.code == "IMAGE_BOARD_CELL_PENDING_NOT_EDITABLE"
    with pytest.raises(JobConflictError) as occupied:
        _reject_slot(factory, artifact_root, seed, 1)
    assert occupied.value.code == "IMAGE_BOARD_CELL_PENDING_NOT_EDITABLE"
    with game_storage_scope(game_id), factory.begin() as session:
        session.execute(
            text(
                "UPDATE game_data_v2.image_board_geometry_pending SET status = 'resolved', "
                "resolved_geometry_revision = 1, resolved_at = now() WHERE id = :id"
            ),
            {"id": seed.pending_ids[2]},
        )
    world = _world(factory, game_id)
    with pytest.raises(JobConflictError) as resolved:
        _reject_slot(factory, artifact_root, seed, 2)
    assert resolved.value.code == "IMAGE_BOARD_CELL_PENDING_NOT_EDITABLE"
    assert _world(factory, game_id) == world

    # Reason ``other`` needs a note and an unknown slot is not found; neither writes.
    with pytest.raises(JobError) as no_note:
        _reject_slot(factory, artifact_root, seed, 0, reason=BoardRejectionReason.OTHER)
    assert no_note.value.code == "IMAGE_BOARD_CELL_PENDING_REJECTION_INVALID"
    with (
        pytest.raises(JobError) as unknown,
        game_storage_scope(game_id),
        factory.begin() as session,
    ):
        _pending_service(session, artifact_root).reject(
            uuid4(),
            game_id=game_id,
            import_job_id=seed.import_job_id,
            idempotency_key=uuid4(),
            expected_geometry_revision=0,
            reason=BoardRejectionReason.CROPPED,
            note=None,
            rejected_by=_ACTOR,
            rejected_at=datetime.now(UTC),
        )
    assert unknown.value.code == "IMAGE_BOARD_CELL_PENDING_NOT_FOUND"
    assert _world(factory, game_id) == world


def test_the_rejection_of_a_slot_is_listed_and_reverted_until_a_replacement_owns_the_sequence(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    factory, seed, artifact_root = _seeded(database, tmp_path, "task0949-revert", 3)
    _import(factory, seed, "task0949-revert", [1, 2])
    game_id = seed.game_id
    before = _world(factory, game_id)

    first_key = uuid4()
    first = _reject_slot(
        factory,
        artifact_root,
        seed,
        0,
        key=first_key,
        reason=BoardRejectionReason.OTHER,
        note="  Ucięty górny rząd  ",
    )
    [entry] = _entries(factory, seed)
    assert entry.kind is GeometryCorrectionKind.REJECTION
    assert entry.rejection_target is RejectionTarget.PENDING_SLOT
    # The entry is the durable rejection event, not the slot.
    assert entry.board_geometry_revision_id == first.rejection_id
    assert entry.board_geometry_revision_id != seed.pending_ids[0]
    assert entry.pending_geometry_id == seed.pending_ids[0]
    assert entry.recognized_board_id is None and entry.review_item_id is None
    assert entry.rejection_reason == "other"
    assert entry.rejection_note == "Ucięty górny rząd"
    assert entry.actor == _ACTOR
    assert entry.revertable, entry.blocking_reason
    rejected_world = _world(factory, game_id)

    with game_storage_scope(game_id), factory() as session:
        preview = _revert_service(session).preview(
            game_id=game_id,
            import_job_id=seed.import_job_id,
            board_geometry_revision_id=entry.board_geometry_revision_id,
        )
        session.rollback()
    assert preview.correction.kind is GeometryCorrectionKind.REJECTION
    assert preview.removes_board is False and preview.removed_cell_count == 0
    assert preview.reverted_source_geometry_revision_id is None
    assert _world(factory, game_id) == rejected_world

    with pytest.raises(ImageReviewConflictError) as stale:
        _revert(factory, seed, entry, key=uuid4(), geometry_revision=entry.geometry_revision + 1)
    assert stale.value.code == RevertBlockingReason.STALE.value
    assert _world(factory, game_id) == rejected_world

    revert_key = uuid4()
    result = _revert(factory, seed, entry, key=revert_key)
    assert result.created is True and result.kind is GeometryCorrectionKind.REJECTION
    assert result.pending_geometry_id == seed.pending_ids[0]
    assert (
        result.recognized_board_id is None and result.reverted_source_geometry_revision_id is None
    )
    # The store is as before the rejection and the slot is back in the queue.
    assert _world(factory, game_id) == before
    stored = _pending_row(factory, seed, 0)
    assert stored["status"] == "pending" and stored["reason"] is None
    assert stored["rejected_at"] is None and stored["rejected_by"] is None
    slots, _correction = _queue(factory, seed)
    assert seed.pending_ids[0] in slots
    assert _entries(factory, seed) == ()

    # The revert is stored with its key: a replay (a lost response) returns the
    # same result, a late replay of the first rejection does not reject again.
    replayed = _revert(factory, seed, entry, key=revert_key)
    assert replayed.created is False and replayed.revert_id == result.revert_id
    late = _reject_slot(
        factory,
        artifact_root,
        seed,
        0,
        key=first_key,
        reason=BoardRejectionReason.OTHER,
        note="Ucięty górny rząd",
    )
    assert late.created is False and late.rejection_id == first.rejection_id
    assert _pending_row(factory, seed, 0)["status"] == "pending"
    assert _world(factory, game_id) == before
    with pytest.raises(ImageReviewConflictError) as other_use:
        _revert(factory, seed, entry, key=first_key)
    assert other_use.value.code == "GEOMETRY_REVERT_IDEMPOTENCY_CONFLICT"

    # The entry is gone, so a second revert is refused; so is its preview, with a
    # controlled 409 built from the durable event (never a null time).
    with pytest.raises(ImageReviewConflictError) as again:
        _revert(factory, seed, entry, key=uuid4())
    assert again.value.code == RevertBlockingReason.NOT_LATEST.value
    with (
        game_storage_scope(game_id),
        factory() as session,
        pytest.raises(ImageReviewConflictError) as stale_preview,
    ):
        _revert_service(session).preview(
            game_id=game_id,
            import_job_id=seed.import_job_id,
            board_geometry_revision_id=entry.board_geometry_revision_id,
        )
    assert stale_preview.value.code == RevertBlockingReason.NOT_LATEST.value

    # A stale revision is refused and writes nothing.
    open_world = _world(factory, game_id)
    with pytest.raises(JobConflictError) as stale_slot:
        _reject_slot(factory, artifact_root, seed, 0, expected_geometry_revision=5)
    assert stale_slot.value.code == "IMAGE_BOARD_CELL_PENDING_REVISION_CONFLICT"
    assert _world(factory, game_id) == open_world

    # A new rejection is a new durable event: the old revert request (aimed at
    # the first rejection) must not undo it.
    second = _reject_slot(factory, artifact_root, seed, 0)
    assert second.created is True and second.rejection_id != first.rejection_id
    [rejected_again] = _entries(factory, seed)
    assert rejected_again.board_geometry_revision_id == second.rejection_id
    assert rejected_again.revertable
    newer_world = _world(factory, game_id)
    with pytest.raises(ImageReviewConflictError) as old_request:
        _revert(factory, seed, entry, key=uuid4())
    assert old_request.value.code == RevertBlockingReason.NOT_LATEST.value
    assert _pending_row(factory, seed, 0)["status"] == "rejected"
    assert _world(factory, game_id) == newer_world
    # The key of the first revert belongs to the first rejection: reusing it for
    # the newer one conflicts; the first revert still replays and undoes nothing.
    with pytest.raises(ImageReviewConflictError) as reused_key:
        _revert(factory, seed, rejected_again, key=revert_key)
    assert reused_key.value.code == "GEOMETRY_REVERT_IDEMPOTENCY_CONFLICT"
    replay_first = _revert(factory, seed, entry, key=revert_key)
    assert replay_first.created is False and replay_first.revert_id == result.revert_id
    assert _pending_row(factory, seed, 0)["status"] == "rejected"
    assert _world(factory, game_id) == newer_world

    # A replacement that owns the sequence blocks the revert (REPLACED).
    sequence = _pending_row(factory, seed, 0)["sequence_number"]
    _add_replacement(factory, seed, "task0949-replacement", position=0, start=sequence)
    replaced_world = _world(factory, game_id)
    [blocked] = _entries(factory, seed)
    assert blocked.revertable is False
    assert blocked.blocking_reason is RevertBlockingReason.REPLACED
    assert blocked.blocking_reason_message
    with pytest.raises(ImageReviewConflictError) as replaced:
        _revert(factory, seed, blocked, key=uuid4())
    assert replaced.value.code == "GEOMETRY_REVERT_REPLACED"
    assert _world(factory, game_id) == replaced_world


def _items(factory: sessionmaker[Session], seed: _Seed) -> dict[int, dict[str, Any]]:
    """Review item, board and sequence by position of the seeded image."""

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
            int(board.position_index): {
                "item": item.id,
                "board": board.id,
                "sequence": int(item.sequence_number or 0),
                "status": item.status,
                "revision": item.resolution_revision,
                "geometry_revision": board.geometry_revision,
            }
            for board, item in rows
        }
        session.rollback()
    return value


def _review_service(session: Session) -> OperationalImageReviewService:
    return OperationalImageReviewService(SqlAlchemyOperationalImageReviewRepository(session))


def _resolve_board(
    factory: sessionmaker[Session],
    seed: _Seed,
    entry: dict[str, Any],
    *,
    action: ImageReviewAction,
    reason: str | None = None,
    key: UUID | None = None,
) -> Any:
    with game_storage_scope(seed.game_id), factory.begin() as session:
        service = _review_service(session)
        item = service.get_item(
            entry["item"], game_id=seed.game_id, import_job_id=seed.import_job_id
        )
        accepted = action is not ImageReviewAction.REJECTED
        return service.resolve_item(
            entry["item"],
            game_id=seed.game_id,
            import_job_id=seed.import_job_id,
            idempotency_key=key or uuid4(),
            expected_revision=item.resolution_revision,
            action=action,
            sequence_number=item.suggested_sequence_number if accepted else None,
            geometry_revision=item.geometry_revision,
            cells=(
                tuple(
                    ImageReviewResolutionCell(
                        cell_index=cell.cell_index,
                        crop_sample_id=cell.crop_sample_id,
                        symbol_code=cell.predicted_symbol_code,
                    )
                    for cell in item.cells
                )
                if accepted
                else ()
            ),
            rejection_reason=reason,
            resolved_by=_ACTOR,
            allow_unknown_cells=True,
        )


def _visible_cells(
    factory: sessionmaker[Session], seed: _Seed, *, outside_only: bool = False
) -> int:
    review_filter = SymbolCellReviewListFilter(
        game_id=seed.game_id,
        symbol_id=None,
        state=SymbolCellReviewFilterState.ALL,
        include_all_symbols=not outside_only,
        outside_only=outside_only,
        storage_generation=2,
    )
    with game_storage_scope(seed.game_id), factory() as session:
        page = SqlAlchemySymbolCellReviewQueryRepository(session).list_items(
            review_filter=review_filter, after_key=None, before_key=None, limit=200
        )
        session.rollback()
    return len(page.items)


def _rebuild_symbol_counts(factory: sessionmaker[Session], seed: _Seed) -> None:
    """Exact symbol-review counters from the cell rows (the bounded rebuild)."""

    with game_storage_scope(seed.game_id), factory.begin() as session:
        state = session.get(ImageSymbolReviewStateModel, seed.game_id)
        assert state is not None
        # The write-through projection of the import is complete (a finished backfill).
        state.status = "ready"
        session.flush()
        repository = SqlAlchemyImageSymbolReviewRepository(session)
        repository.start_count_rebuild(seed.game_id)
        for _ in range(10):
            if repository.rebuild_count_projection_next_batch(seed.game_id, batch_size=100):
                return
    raise AssertionError("count rebuild did not finish")


def _symbol_counts(
    factory: sessionmaker[Session], seed: _Seed, *, outside_only: bool = False
) -> int:
    """The exact (incremental) counter of the game-wide (or the outside) scope."""

    review_filter = SymbolCellReviewListFilter(
        game_id=seed.game_id,
        symbol_id=None,
        state=SymbolCellReviewFilterState.ALL,
        include_all_symbols=not outside_only,
        outside_only=outside_only,
        storage_generation=2,
    )
    with game_storage_scope(seed.game_id), factory() as session:
        counts = SqlAlchemySymbolCellReviewQueryRepository(session).counts(
            review_filter=review_filter
        )
        session.rollback()
    return counts.all_count


def _cell_rows(factory: sessionmaker[Session], seed: _Seed) -> int:
    with game_storage_scope(seed.game_id), factory() as session:
        value = session.scalar(
            select(func.count())
            .select_from(ImageSymbolReviewCellModel)
            .where(ImageSymbolReviewCellModel.game_id == seed.game_id)
        )
        session.rollback()
    return int(value or 0)


def _documents(factory: sessionmaker[Session], seed: _Seed, review_item_id: UUID) -> int:
    with game_storage_scope(seed.game_id), factory() as session:
        value = session.execute(
            text(
                "SELECT count(*) FROM game_data_v2.image_board_search_fast_documents d "
                "WHERE d.game_id = :game_id AND d.review_item_id = :item "
                "AND EXISTS (SELECT 1 FROM unnest(d.primary_symbol_mobile_codes) code "
                "WHERE code IS NOT NULL)"
            ),
            {"game_id": seed.game_id, "item": review_item_id},
        ).scalar_one()
        session.rollback()
    return int(value)


def test_a_rejected_board_of_a_withheld_image_stays_out_of_symbol_review(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    factory, seed, _artifact_root = _seeded(database, tmp_path, "task0949-withheld", 3)
    _import(factory, seed, "task0949-withheld", [0, 1])
    game_id = seed.game_id
    items = _items(factory, seed)
    withheld = _state(factory, game_id, seed.source_image_id)
    assert withheld["status"] == "geometry_incomplete"
    assert withheld["boards"] == 2 and withheld["cells"] == 0

    # W7/W8: the cropped board is rejected with a reason; neither board of the
    # still incomplete image gets cells, in verification or in search.
    item, event, created = _resolve_board(
        factory,
        seed,
        items[1],
        action=ImageReviewAction.REJECTED,
        reason=encode_board_rejection_reason("other", "Ucięty górny rząd"),
    )
    assert created is True and item.status == "rejected"
    assert event.action == "rejected"
    assert _visible_cells(factory, seed) == 0 and _cell_rows(factory, seed) == 0
    assert _documents(factory, seed, items[1]["item"]) == 0
    after = _state(factory, game_id, seed.source_image_id)
    assert after["status"] == "geometry_incomplete"
    assert after["boards"] == 1 and after["cells"] == 0
    report, _page = _report(factory, game_id, seed.import_job_id)
    assert report is not None and report.gate is not None
    assert report.gate.geometry_incomplete == 1 and report.gate.withheld_boards == 1

    [entry] = _entries(factory, seed)
    assert entry.rejection_target is RejectionTarget.REVIEW_ITEM
    assert entry.rejection_reason == "other"
    assert entry.rejection_note == "Ucięty górny rząd"
    assert entry.revertable, entry.blocking_reason
    result = _revert(factory, seed, entry, key=uuid4())
    assert result.created is True
    assert _items(factory, seed)[1]["status"] == "pending"
    restored = _state(factory, game_id, seed.source_image_id)
    assert restored["status"] == "geometry_incomplete"
    assert restored["cells"] == 0 and _cell_rows(factory, seed) == 0


def test_a_rejected_board_leaves_the_search_and_the_canonical_owner_is_refused(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    factory, seed, _artifact_root = _seeded(database, tmp_path, "task0949-board", 2)
    _import(factory, seed, "task0949-board", [0, 1])
    game_id = seed.game_id
    items = _items(factory, seed)
    admitted = _state(factory, game_id, seed.source_image_id)
    assert admitted["status"] == "geometry_complete" and admitted["cells"] == 30
    _rebuild_symbol_counts(factory, seed)
    assert _visible_cells(factory, seed) == 30
    assert _symbol_counts(factory, seed) == 30

    # The canonical owner of a sequence cannot be rejected.
    _resolve_board(factory, seed, items[0], action=ImageReviewAction.ACCEPTED)
    with game_storage_scope(game_id), factory() as session:
        owner = session.scalar(
            select(ImageSequenceCanonicalModel.review_item_id).where(
                ImageSequenceCanonicalModel.game_id == game_id,
                ImageSequenceCanonicalModel.sequence_number == items[0]["sequence"],
            )
        )
        session.rollback()
    assert owner == items[0]["item"]
    accepted_world = _world(factory, game_id)
    with pytest.raises(ImageReviewConflictError) as canonical:
        _resolve_board(factory, seed, items[0], action=ImageReviewAction.REJECTED, reason="cropped")
    assert canonical.value.code == BOARD_REJECT_CANONICAL
    assert _world(factory, game_id) == accepted_world

    # A pending board is rejected with a reason: it leaves symbol verification
    # and search, the image becomes incomplete again (the position is a gap).
    reason_text = encode_board_rejection_reason("cropped", None)
    key = uuid4()
    _item, event, created = _resolve_board(
        factory, seed, items[1], action=ImageReviewAction.REJECTED, reason=reason_text, key=key
    )
    assert created is True and event.action == "rejected"
    # The rejected board leaves the search and symbol verification (list and
    # exact counters); its rows and decision history stay (D-485).
    assert _documents(factory, seed, items[1]["item"]) == 0
    assert _documents(factory, seed, items[0]["item"]) == 1
    assert _cell_rows(factory, seed) == 30
    assert _visible_cells(factory, seed) == 15
    assert _symbol_counts(factory, seed) == 15
    after = _state(factory, game_id, seed.source_image_id)
    assert after["status"] == "geometry_incomplete"
    assert after["boards"] == 1

    [entry] = _entries(factory, seed)
    assert entry.kind is GeometryCorrectionKind.REJECTION
    assert entry.rejection_target is RejectionTarget.REVIEW_ITEM
    assert entry.board_geometry_revision_id == event.id
    assert entry.review_item_id == items[1]["item"]
    assert entry.recognized_board_id == items[1]["board"]
    assert entry.pending_geometry_id is None
    assert entry.rejection_reason == "cropped" and entry.rejection_note is None
    assert entry.sequence_number == items[1]["sequence"]
    assert entry.revertable, entry.blocking_reason
    rejected_world = _world(factory, game_id)

    with pytest.raises(ImageReviewConflictError) as stale:
        _revert(factory, seed, entry, key=uuid4(), geometry_revision=entry.geometry_revision + 1)
    assert stale.value.code == RevertBlockingReason.STALE.value
    assert _world(factory, game_id) == rejected_world

    # The revert restores the item to pending through a new resolution event.
    revert_key = uuid4()
    result = _revert(factory, seed, entry, key=revert_key)
    assert result.created is True and result.kind is GeometryCorrectionKind.REJECTION
    assert result.review_item_id == items[1]["item"]
    assert result.recognized_board_id == items[1]["board"]
    restored = _items(factory, seed)[1]
    assert restored["status"] == "pending"
    assert restored["revision"] == items[1]["revision"] + 2
    with game_storage_scope(game_id), factory() as session:
        events = session.execute(
            select(ImageReviewResolutionEventModel.action, ImageReviewResolutionEventModel.id)
            .where(ImageReviewResolutionEventModel.review_item_id == items[1]["item"])
            .order_by(ImageReviewResolutionEventModel.revision)
        ).all()
        source_status = session.scalar(
            select(SourceImageModel.status).where(SourceImageModel.id == seed.source_image_id)
        )
        session.rollback()
    assert [action for action, _ in events] == ["rejected", "reopened"]
    assert result.revert_id == events[1][1]
    assert source_status == "waiting_for_review"
    assert _state(factory, game_id, seed.source_image_id)["status"] == "geometry_complete"
    assert _documents(factory, seed, items[1]["item"]) == 1
    # Undoing the rejection brings the board back into verification, unchanged.
    assert _visible_cells(factory, seed) == 30
    assert _symbol_counts(factory, seed) == 30
    assert _cell_rows(factory, seed) == 30
    assert _entries(factory, seed) == ()

    # The same key replays the stored result; a new key finds nothing to undo.
    replay = _revert(factory, seed, entry, key=revert_key)
    assert replay.created is False and replay.revert_id == result.revert_id
    settled = _world(factory, game_id)
    with pytest.raises(ImageReviewConflictError) as again:
        _revert(factory, seed, entry, key=uuid4())
    assert again.value.code == RevertBlockingReason.NOT_LATEST.value
    assert _world(factory, game_id) == settled

    # A replacement owning the sequence blocks the revert of a new rejection.
    _resolve_board(
        factory, seed, _items(factory, seed)[1], action=ImageReviewAction.REJECTED, reason="blurred"
    )
    assert _visible_cells(factory, seed) == 15
    assert _symbol_counts(factory, seed) == 15
    # A full rebuild of the counters from the rows agrees with the list.
    _rebuild_symbol_counts(factory, seed)
    assert _symbol_counts(factory, seed) == 15
    # The key that reverted the first rejection cannot revert this one (reject
    # A, revert with K, reject B, revert B with K); the first revert still replays.
    [second_entry] = _entries(factory, seed)
    second_world = _world(factory, game_id)
    with pytest.raises(ImageReviewConflictError) as reused_key:
        _revert(factory, seed, second_entry, key=revert_key)
    assert reused_key.value.code == "GEOMETRY_REVERT_IDEMPOTENCY_CONFLICT"
    first_replay = _revert(factory, seed, entry, key=revert_key)
    assert first_replay.created is False and first_replay.revert_id == result.revert_id
    assert _items(factory, seed)[1]["status"] == "rejected"
    assert _world(factory, game_id) == second_world
    _add_replacement(
        factory, seed, "task0949-board-replacement", position=0, start=items[1]["sequence"]
    )
    replaced_world = _world(factory, game_id)
    [blocked] = _entries(factory, seed)
    assert blocked.blocking_reason is RevertBlockingReason.REPLACED
    assert blocked.rejection_reason == "blurred"
    with pytest.raises(ImageReviewConflictError) as replaced:
        _revert(factory, seed, blocked, key=uuid4())
    assert replaced.value.code == "GEOMETRY_REVERT_REPLACED"
    assert _world(factory, game_id) == replaced_world


def _make_board_partial(factory: sessionmaker[Session], seed: _Seed, item: dict[str, Any]) -> None:
    """Turn a cut board into a qualified ``pending_partial`` one (cells 0 and 1 outside).

    Storage effects of a qualified manual save without pixels: the qualification,
    the pinned source slot with the cell quads, the partial render revision and the
    write-through of the cells (cells 0 and 1 become fully outside cells).
    """

    from _virtual_board_fixtures import replace_virtual_geometry
    from game_predictor_api.domain.geometry_qualification import GeometryQualification
    from game_predictor_api.storage.image_symbol_review_repository import (
        SymbolCellReviewWriteThroughCoordinator,
    )
    from sqlalchemy.orm.attributes import flag_modified

    cell_geometry = [
        {
            "rowIndex": index // 5,
            "columnIndex": index % 5,
            "sourceQuad": [
                {"x": x, "y": y}
                for x, y in (
                    ((-20, 10), (-10, 10), (-10, 20), (-20, 20))
                    if index in (0, 1)
                    else ((10, 10), (20, 10), (20, 20), (10, 20))
                )
            ],
        }
        for index in range(15)
    ]
    with game_storage_scope(seed.game_id), factory.begin() as session:
        board = session.get(RecognizedBoardModel, item["board"])
        assert board is not None
        board.completeness_status = "pending_partial"
        board.unavailable_cell_indices = [0, 1]
        board.geometry_qualification = GeometryQualification(
            "pending_partial",
            (0, 1),
            True,
            "missing_pixels",
            version="manual-geometry-qualification-v3",
            fully_unavailable_cell_indices=(0, 1),
        ).to_dict()
        board.board_geometry = {"cells": cell_geometry}
        source_geometry = session.get(
            ImageSourceGeometryRevisionModel, board.source_geometry_revision_id
        )
        assert source_geometry is not None
        slots = [dict(value) for value in source_geometry.board_geometries]
        slots[board.position_index] = {**slots[board.position_index], "cells": cell_geometry}
        source_geometry.board_geometries = slots
        flag_modified(source_geometry, "board_geometries")
        replace_virtual_geometry(
            session,
            game_id=seed.game_id,
            review_item_id=item["item"],
            board_id=item["board"],
            variant="partial",
            cell_indices=tuple(range(2, 15)),
        )
        coordinator = SymbolCellReviewWriteThroughCoordinator(session)
        assert coordinator.synchronize_after_geometry_change(
            game_id=seed.game_id, review_item_id=item["item"]
        )


def test_a_rejected_pending_partial_board_leaves_verification_with_its_outside_cells(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    """A qualified partial board with cut cells: rejected, hidden, counted exactly."""

    factory, seed, _artifact_root = _seeded(database, tmp_path, "task0949-partial", 2)
    _import(factory, seed, "task0949-partial", [0, 1])
    game_id = seed.game_id
    items = _items(factory, seed)
    _make_board_partial(factory, seed, items[1])
    with game_storage_scope(game_id), factory() as session:
        board = session.get(RecognizedBoardModel, items[1]["board"])
        assert board is not None and board.completeness_status == "pending_partial"
        partial = {
            cell.cell_index: (cell.source_available, cell.source_visibility)
            for cell in session.scalars(
                select(ImageSymbolReviewCellModel).where(
                    ImageSymbolReviewCellModel.review_item_id == items[1]["item"]
                )
            )
        }
        session.rollback()
    assert len(partial) == 15
    assert partial[0] == (False, "outside") and partial[1] == (False, "outside")
    assert all(partial[index][0] for index in range(2, 15))
    _rebuild_symbol_counts(factory, seed)
    assert _visible_cells(factory, seed) == 30
    assert _symbol_counts(factory, seed) == 30
    assert _visible_cells(factory, seed, outside_only=True) == 2
    assert _symbol_counts(factory, seed, outside_only=True) == 2

    _item, event, created = _resolve_board(
        factory, seed, items[1], action=ImageReviewAction.REJECTED, reason="cropped"
    )
    assert created is True and event.action == "rejected"
    with game_storage_scope(game_id), factory() as session:
        board = session.get(RecognizedBoardModel, items[1]["board"])
        assert board is not None
        assert board.status == "rejected" and board.completeness_status == "pending_partial"
        session.rollback()
    assert _items(factory, seed)[1]["status"] == "rejected"
    # The partial board's cells, the outside ones included, are out of verification
    # (list and exact counters) while the rows stay as history.
    assert _cell_rows(factory, seed) == 30
    assert _visible_cells(factory, seed) == 15
    assert _symbol_counts(factory, seed) == 15
    assert _visible_cells(factory, seed, outside_only=True) == 0
    assert _symbol_counts(factory, seed, outside_only=True) == 0
    # A full rebuild from the rows agrees with the incremental counters.
    _rebuild_symbol_counts(factory, seed)
    assert _symbol_counts(factory, seed) == 15
    assert _symbol_counts(factory, seed, outside_only=True) == 0

    # Undoing the rejection brings the partial board back, counted exactly once.
    [entry] = _entries(factory, seed)
    assert entry.revertable, entry.blocking_reason
    assert _revert(factory, seed, entry, key=uuid4()).created is True
    assert _items(factory, seed)[1]["status"] == "pending"
    assert _visible_cells(factory, seed) == 30
    assert _symbol_counts(factory, seed) == 30
    assert _visible_cells(factory, seed, outside_only=True) == 2
    assert _symbol_counts(factory, seed, outside_only=True) == 2


def test_a_rejected_board_resolved_directly_restores_the_counters_exactly_once(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    """P0-5: rejected -> accepted without the revert path (one release/restore rule)."""

    factory, seed, _artifact_root = _seeded(database, tmp_path, "task0949-direct", 2)
    _import(factory, seed, "task0949-direct", [0, 1])
    game_id = seed.game_id
    items = _items(factory, seed)
    _rebuild_symbol_counts(factory, seed)
    assert _visible_cells(factory, seed) == 30
    assert _symbol_counts(factory, seed) == 30

    _resolve_board(factory, seed, items[1], action=ImageReviewAction.REJECTED, reason="cropped")
    assert _visible_cells(factory, seed) == 15
    assert _symbol_counts(factory, seed) == 15

    # The rejected board is resolved again directly: its cells are back in the
    # exact counters once (no negative projection, no double count).
    resolved, _event, created = _resolve_board(
        factory, seed, _items(factory, seed)[1], action=ImageReviewAction.ACCEPTED
    )
    assert created is True and resolved.status == "accepted"
    assert _visible_cells(factory, seed) == 30
    assert _symbol_counts(factory, seed) == 30
    assert _cell_rows(factory, seed) == 30
    # A full rebuild from the rows agrees.
    _rebuild_symbol_counts(factory, seed)
    assert _symbol_counts(factory, seed) == 30
    assert _visible_cells(factory, seed) == 30
    assert _state(factory, game_id, seed.source_image_id)["status"] == "geometry_complete"


def test_the_key_of_a_revert_is_unique_within_the_game_across_every_store(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    """P0-7: audit, slot events and resolution events share one key space."""

    factory, seed, artifact_root = _seeded(database, tmp_path, "task0949-keys", 3)
    _import(factory, seed, "task0949-keys", [0, 1])
    game_id = seed.game_id
    items = _items(factory, seed)
    own_key_0, own_key_1 = uuid4(), uuid4()
    _resolve_board(
        factory, seed, items[0], action=ImageReviewAction.REJECTED, reason="cropped", key=own_key_0
    )
    _resolve_board(
        factory, seed, items[1], action=ImageReviewAction.REJECTED, reason="blurred", key=own_key_1
    )
    _reject_slot(factory, artifact_root, seed, 2)
    entries = {
        (entry.review_item_id or entry.pending_geometry_id): entry
        for entry in _entries(factory, seed)
    }
    board_0, board_1 = entries[items[0]["item"]], entries[items[1]["item"]]
    slot = entries[seed.pending_ids[2]]
    assert board_0.revertable and board_1.revertable and slot.revertable

    def refused(entry: Any, key: UUID) -> None:
        before = _world(factory, game_id)
        with pytest.raises(ImageReviewConflictError) as conflict:
            _revert(factory, seed, entry, key=key)
        assert conflict.value.code == "GEOMETRY_REVERT_IDEMPOTENCY_CONFLICT"
        assert _world(factory, game_id) == before

    # The key of a board's own rejection is a use of the key: a controlled 409
    # before any write, not a UNIQUE violation; so is another board's rejection key.
    refused(board_1, own_key_1)
    refused(board_1, own_key_0)
    refused(slot, own_key_0)

    # Revert A with K; B, the slot and A's own rejection cannot reuse K.
    key = uuid4()
    first = _revert(factory, seed, board_0, key=key)
    assert first.created is True
    refused(board_1, key)
    refused(slot, key)
    replay = _revert(factory, seed, board_0, key=key)
    assert replay.created is False and replay.revert_id == first.revert_id

    # The same holds from the slot side: a slot revert key is taken for the boards.
    slot_key = uuid4()
    reverted_slot = _revert(factory, seed, slot, key=slot_key)
    assert reverted_slot.created is True
    refused(board_1, slot_key)
    assert _items(factory, seed)[1]["status"] == "rejected"
    assert _revert(factory, seed, slot, key=slot_key).created is False

    # A free key still reverts the remaining board.
    assert _revert(factory, seed, board_1, key=uuid4()).created is True


def test_the_slot_rejection_and_revert_routes_work_over_http(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    from fastapi.testclient import TestClient

    factory, seed, artifact_root = _seeded(database, tmp_path, "task0949-http", 3)
    _import(factory, seed, "task0949-http", [1, 2])
    base = f"/api/v1/admin/games/{seed.game_id}/image-imports/{seed.import_job_id}"
    key = str(uuid4())
    body = {
        "idempotencyKey": key,
        "reason": "other",
        "note": "Ucięty górny rząd",
        "expectedGeometryRevision": 0,
    }
    app = _app(database, artifact_root)
    try:
        with TestClient(app) as client:
            url = f"{base}/board-cell-geometry-pending/{seed.pending_ids[0]}/rejection"
            first = client.post(url, json=body)
            assert first.status_code == 200, first.text
            payload = first.json()
            assert payload["created"] is True
            assert payload["item"]["status"] == "rejected"
            assert payload["item"]["rejectionReason"] == "other"
            assert payload["item"]["rejectionNote"] == "Ucięty górny rząd"
            assert payload["counts"]["rejected"] == 1
            assert client.post(url, json=body).json()["created"] is False
            invalid = client.post(url, json={**body, "idempotencyKey": str(uuid4()), "note": None})
            assert invalid.status_code in {409, 422}
            missing = client.post(url.replace(str(seed.pending_ids[0]), str(uuid4())), json=body)
            assert missing.status_code == 404
            assert missing.json()["code"] == "IMAGE_BOARD_CELL_PENDING_NOT_FOUND"

            listed = client.get(f"{base}/geometry-corrections")
            assert listed.status_code == 200, listed.text
            [entry] = listed.json()["items"]
            assert entry["kind"] == "rejection"
            assert entry["rejectionTarget"] == "pending_slot"
            assert entry["rejectionReason"] == "other"
            assert entry["boardGeometryRevisionId"] == payload["rejectionId"]
            assert entry["pendingGeometryId"] == str(seed.pending_ids[0])
            assert entry["revertable"] is True
            assert entry["recognizedBoardId"] is None and entry["reviewItemId"] is None

            revert_url = f"{base}/geometry-corrections/{entry['boardGeometryRevisionId']}"
            preview = client.get(f"{revert_url}/revert-preview")
            assert preview.status_code == 200, preview.text
            assert preview.json()["revertedSourceGeometryRevisionId"] is None
            reverted = client.post(
                f"{revert_url}/revert",
                json={
                    "idempotencyKey": str(uuid4()),
                    "expectedGeometryRevision": preview.json()["expectedGeometryRevision"],
                    "expectedResolutionRevision": preview.json()["expectedResolutionRevision"],
                },
            )
            assert reverted.status_code == 200, reverted.text
            assert reverted.json()["kind"] == "rejection"
            assert reverted.json()["reviewItemId"] is None
            assert client.get(f"{base}/geometry-corrections").json()["items"] == []
            # A stale list (the rejection was reverted elsewhere): a controlled 409,
            # not a 500, for the preview and for a repeated revert.
            stale = client.get(f"{revert_url}/revert-preview")
            assert stale.status_code == 409, stale.text
            assert stale.json()["code"] == "GEOMETRY_REVERT_NOT_LATEST"
            stale_revert = client.post(
                f"{revert_url}/revert",
                json={
                    "idempotencyKey": str(uuid4()),
                    "expectedGeometryRevision": 0,
                    "expectedResolutionRevision": 0,
                },
            )
            assert stale_revert.status_code == 409
            assert stale_revert.json()["code"] == "GEOMETRY_REVERT_NOT_LATEST"
    finally:
        app.state.database_engine.dispose()
    assert _pending_row(factory, seed, 0)["status"] == "pending"
