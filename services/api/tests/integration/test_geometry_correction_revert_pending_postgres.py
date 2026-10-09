"""TASK-0945: revert of a deferred-slot grid-geometry correction (PostgreSQL).

Runs on a dedicated ``*_test`` database only (fixtures of
``test_virtual_deferred_resolution_postgres`` and the import writer of
``test_image_geometry_completeness_gate``). A deferred slot is resolved through
the production application path (``resolve_manual``), reverted through the
production repository, and the whole game store is compared with its state
before the save: projections, counters, queue, job, search and the gate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.geometry_correction_reverts import (
    GeometryCorrectionRevertService,
)
from game_predictor_api.application.virtual_grid_geometry import VirtualGridCellSymbol
from game_predictor_api.domain.geometry_correction_reverts import (
    GeometryCorrectionKind,
    RevertBlockingReason,
    snapshot_checksum_sha256,
)
from game_predictor_api.domain.image_grid_reviews import (
    ImageGridReviewError,
    ImageGridReviewListFilter,
    ImageGridReviewView,
)
from game_predictor_api.domain.image_reviews import ImageReviewConflictError
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.geometry_correction_revert_models import (
    ImageGeometryCorrectionRevertModel,
)
from game_predictor_api.storage.geometry_correction_revert_repository import (
    SqlAlchemyGeometryCorrectionRevertRepository,
)
from game_predictor_api.storage.image_geometry_completeness_repository import (
    SqlAlchemyImageGeometryCompletenessRepository,
)
from game_predictor_api.storage.image_geometry_completeness_state_repository import (
    SqlAlchemyImageGeometryCompletenessStateRepository,
)
from game_predictor_api.storage.image_grid_review_repository import (
    SqlAlchemyImageGridReviewRepository,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemyGridCorrectionSymbolRepository,
)
from game_predictor_api.storage.models import ImageSymbolReviewStateModel, SymbolModel
from game_predictor_api.storage.virtual_grid_geometry_repository import (
    SqlAlchemyVirtualGridGeometryRepository,
)
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker
from test_image_geometry_completeness_gate import _import, _seeded
from test_virtual_deferred_resolution_postgres import (
    _Database,
    _pending_service,
    _points,
    _Seed,
    database,  # noqa: F401  (pytest fixture)
    pytestmark,  # noqa: F401  (PostgreSQL opt-in)
)

_ACTOR = "task-0945-operator"
# Columns that legitimately move forward (clocks, monotonic counters).
_VOLATILE = (
    "created_at",
    "updated_at",
    "last_reviewed_at",
    "processed_at",
    "geometry_completeness_evaluated_at",
    "queue_version",
    "catalog_revision",
    "count_projection_revision",
)
_WORLD_TABLES = (
    "image_board_geometry_pending",
    "recognized_boards",
    "image_review_items",
    "image_symbol_review_cells",
    "image_symbol_review_events",
    "image_board_geometry_revisions",
    "image_board_geometry_review_events",
    "board_render_manifests",
    "image_source_geometry_revisions",
    "image_review_queue_items",
    "image_review_queue_states",
    "image_board_search_candidates",
    "image_board_search_fast_documents",
    "image_symbol_review_states",
    "source_images",
    "image_review_resolution_events",
    "image_sequence_canonical",
    "image_geometry_correction_reverts",
)


def _sorted_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: json.dumps(row, sort_keys=True))


def _exact(row: dict[str, Any]) -> dict[str, Any]:
    """An exact counter scope with zero rows equals an absent one."""

    projection = row.get("count_projection")
    if isinstance(projection, dict):
        row["count_projection"] = {
            scope: kept
            for scope, counts in projection.items()
            if (
                kept := counts
                if scope.startswith("_") or not isinstance(counts, dict)
                else {state: count for state, count in counts.items() if count != 0}
            )
        }
    return row


def _world(factory: sessionmaker[Session], game_id: UUID) -> dict[str, Any]:
    """Every row of the game's store that a slot save or its revert can touch."""

    strip = " - ".join(f"'{column}'" for column in _VOLATILE)
    world: dict[str, Any] = {}
    with game_storage_scope(game_id), factory() as session:
        for table in _WORLD_TABLES:
            rows = session.execute(
                text(
                    f"SELECT (to_jsonb(t) - {strip})::text FROM game_data_v2.{table} t "
                    "WHERE t.game_id = :game_id"
                ),
                {"game_id": game_id},
            ).scalars()
            world[table] = _sorted_rows([_exact(json.loads(row)) for row in rows])
        world["jobs"] = sorted(
            session.execute(
                text("SELECT id::text, status::text FROM public.jobs WHERE game_id = :game_id"),
                {"game_id": game_id},
            ).all()
        )
        session.rollback()
    return world


def _service(session: Session) -> GeometryCorrectionRevertService:
    return GeometryCorrectionRevertService(SqlAlchemyGeometryCorrectionRevertRepository(session))


def _symbol_id(factory: sessionmaker[Session], game_id: UUID, code: str) -> UUID:
    with factory() as session:
        value = session.scalar(
            select(SymbolModel.id).where(SymbolModel.game_id == game_id, SymbolModel.code == code)
        )
        session.rollback()
    assert value is not None
    return value


def _resolve(
    factory: sessionmaker[Session],
    artifact_root: Path,
    seed: _Seed,
    index: int,
    *,
    key: UUID,
    cell_symbols: tuple[VirtualGridCellSymbol, ...] = (),
) -> Any:
    from datetime import UTC, datetime

    with game_storage_scope(seed.game_id), factory.begin() as session:
        return _pending_service(session, artifact_root).resolve_manual(
            seed.pending_ids[index],
            game_id=seed.game_id,
            import_job_id=seed.import_job_id,
            expected_manifest_checksum_sha256=seed.manifest_checksums[index],
            idempotency_key=key,
            expected_geometry_revision=0,
            expected_resolution_revision=0,
            corners=_points(),
            corrected_by=_ACTOR,
            resolved_at=datetime.now(UTC),
            cell_symbols=cell_symbols,
        )


def _entries(factory: sessionmaker[Session], seed: _Seed) -> Any:
    with game_storage_scope(seed.game_id), factory() as session:
        entries = _service(session).list_recent(
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
    from datetime import UTC, datetime

    with game_storage_scope(seed.game_id), factory.begin() as session:
        return _service(session).revert(
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


def _refused(
    factory: sessionmaker[Session], seed: _Seed, entry: Any, reason: RevertBlockingReason, **kw: Any
) -> None:
    before = _world(factory, seed.game_id)
    with pytest.raises(ImageReviewConflictError) as refused:
        _revert(factory, seed, entry, key=uuid4(), **kw)
    assert refused.value.code == reason.value
    # Refused before any write (or rolled back as a whole).
    assert _world(factory, seed.game_id) == before


def _excepted_game(
    db: _Database, tmp_path: Path, code: str, slots: int = 3
) -> tuple[sessionmaker[Session], _Seed, Path]:
    """Slot 1 imported (geometry revision 0), the others deferred; exception set."""

    factory, seed, artifact_root = _seeded(db, tmp_path, code, slots)
    _import(factory, seed, code, [1])
    with game_storage_scope(seed.game_id), factory.begin() as session:
        exception = SqlAlchemyImageGeometryCompletenessStateRepository(session).set_exception(
            seed.game_id, seed.source_image_id, reason="Slot 2 poza kadrem", actor=_ACTOR
        )
    assert exception is not None and exception.materialized_review_item_count == 1
    with game_storage_scope(seed.game_id), factory.begin() as session:
        # A finished symbol-review backfill with exact counters: D-488 symbols
        # need a ready projection, and the counters must come back exactly.
        state = session.get(ImageSymbolReviewStateModel, seed.game_id)
        if state is None:
            state = ImageSymbolReviewStateModel(game_id=seed.game_id, status="ready")
            session.add(state)
        state.status = "ready"
        state.count_projection_status = "ready"
        state.count_projection = {"_semantics": {"version": 2}}
    return factory, seed, artifact_root


def test_slot_revert_restores_the_store_as_before_the_correction(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    factory, seed, artifact_root = _excepted_game(database, tmp_path, "task0945-revert")
    game_id = seed.game_id
    before = _world(factory, game_id)
    neighbour_cells = [
        row for row in before["image_symbol_review_cells"] if row["source_geometry_revision_id"]
    ]
    assert len(neighbour_cells) == 15
    [revision_0] = before["image_source_geometry_revisions"]

    # D-488: the operator labels part of the cells in the save transaction.
    symbol_id = _symbol_id(factory, game_id, "CYTRYNA")
    save_key = uuid4()
    saved = _resolve(
        factory,
        artifact_root,
        seed,
        0,
        key=save_key,
        cell_symbols=(
            VirtualGridCellSymbol(cell_index=0, symbol_id=symbol_id),
            VirtualGridCellSymbol(cell_index=1, symbol_id=None),
        ),
    )
    assert saved.created is True
    after_save = _world(factory, game_id)
    assert len(after_save["recognized_boards"]) == 2
    assert len(after_save["image_symbol_review_cells"]) == 30
    assert len(after_save["image_symbol_review_events"]) >= 2
    revision_1 = next(
        row for row in after_save["image_source_geometry_revisions"] if row["revision"] == 1
    )
    neighbour = next(row for row in after_save["recognized_boards"] if row["position_index"] == 1)
    assert neighbour["source_geometry_revision_id"] == revision_1["id"]
    # The new slot board is an operator-approved position under the exception.
    assert after_save["source_images"][0]["geometry_completeness_status"] == "geometry_exception"

    [entry] = _entries(factory, seed)
    assert entry.kind is GeometryCorrectionKind.PENDING_SLOT
    assert entry.pending_geometry_id == seed.pending_ids[0]
    assert entry.revertable, entry.blocking_reason
    with game_storage_scope(game_id), factory() as session:
        preview = _service(session).preview(
            game_id=game_id,
            import_job_id=seed.import_job_id,
            board_geometry_revision_id=entry.board_geometry_revision_id,
        )
        session.rollback()
    assert preview.removes_board is True
    assert preview.removed_cell_count == 15
    assert preview.repointed_board_count == 1
    assert str(preview.restored_source_geometry_revision_id) == revision_0["id"]
    assert preview.restored_source_status == "accepted"
    # The preview wrote nothing.
    assert _world(factory, game_id) == after_save

    with pytest.raises(ImageReviewConflictError) as stale:
        _revert(factory, seed, entry, key=uuid4(), geometry_revision=entry.geometry_revision + 1)
    assert stale.value.code == RevertBlockingReason.STALE.value
    assert _world(factory, game_id) == after_save

    revert_key = uuid4()
    result = _revert(factory, seed, entry, key=revert_key)
    assert result.created is True
    assert result.kind is GeometryCorrectionKind.PENDING_SLOT
    assert result.removed_cell_count == 15
    assert len(result.repointed_board_ids) == 1
    assert str(result.restored_source_geometry_revision_id) == revision_0["id"]
    reverted_world = _world(factory, game_id)

    # The only difference to the state before the save: the correction's
    # source revision is kept as ``reverted`` and the audit row exists.
    [audit] = reverted_world.pop("image_geometry_correction_reverts")
    assert before.pop("image_geometry_correction_reverts") == []
    reverted_revisions = reverted_world.pop("image_source_geometry_revisions")
    assert [row["status"] for row in reverted_revisions if row["revision"] == 1] == ["reverted"]
    assert [row for row in reverted_revisions if row["revision"] != 1] == before.pop(
        "image_source_geometry_revisions"
    )
    assert reverted_world == before

    # The audit holds every deleted row with a verifiable checksum and no FK.
    snapshot = audit["snapshot"]
    assert snapshot_checksum_sha256(snapshot) == audit["snapshot_checksum_sha256"]
    deleted = {part["table"]: part["rows"] for part in snapshot["deleted"]}
    assert len(deleted["image_symbol_review_cells"]) == 15
    assert len(deleted["image_symbol_review_events"]) >= 2
    assert len(deleted["image_board_geometry_revisions"]) == 1
    assert len(deleted["image_board_geometry_review_events"]) == 1
    assert len(deleted["board_render_manifests"]) == 1
    assert len(deleted["recognized_boards"]) == 1
    assert len(deleted["image_review_items"]) == 1
    assert len(deleted["image_review_queue_items"]) == 1
    assert snapshot["updated"]["image_board_geometry_pending"]["status"] == "resolved"
    with game_storage_scope(game_id), factory() as session:
        foreign_keys = session.execute(
            text(
                "SELECT count(*) FROM pg_constraint WHERE contype = 'f' AND conparentid = 0 "
                "AND conrelid = 'game_data_v2.image_geometry_correction_reverts'::regclass"
            )
        ).scalar_one()
        # The slot is open again; its proposal comes from the previous revision.
        context = SqlAlchemyVirtualGridGeometryRepository(session).virtual_geometry_context(
            game_id=game_id,
            import_job_id=seed.import_job_id,
            review_item_id=None,
            pending_geometry_id=seed.pending_ids[0],
        )
        # The "latest" queries skip the reverted revision: the correction
        # queue proposes the deferred entry of revision 0 again, and the
        # completeness report evaluates the image against revision 0.
        queue = SqlAlchemyImageGridReviewRepository(session).list_grid_reviews(
            review_filter=ImageGridReviewListFilter(
                game_id=game_id,
                view=ImageGridReviewView.CORRECTION,
                import_job_id=seed.import_job_id,
            ),
            after_key=None,
            before_key=None,
            limit=10,
        )
        report = SqlAlchemyImageGeometryCompletenessRepository(session).incomplete_images(
            game_id, import_job_id=seed.import_job_id
        )
        session.rollback()
    assert foreign_keys == 2  # the game and the import job only
    slots = {item.pending_geometry_id: item for item in queue.items}
    assert set(slots) == {seed.pending_ids[0], seed.pending_ids[2]}
    assert slots[seed.pending_ids[0]].geometry["disposition"] == "needs_manual_review"
    assert report is not None
    [image] = report.images
    assert image.source_revision == 0
    assert str(context.source_geometry_revision_id) == revision_0["id"]
    assert context.review_item_id is None

    # Same key: the stored result; a second revert of the same save: refused.
    replay = _revert(factory, seed, entry, key=revert_key)
    assert replay.created is False and replay.revert_id == result.revert_id
    with pytest.raises(ImageReviewConflictError) as second:
        _revert(factory, seed, entry, key=uuid4())
    assert second.value.code == RevertBlockingReason.NOT_LATEST.value
    assert _entries(factory, seed) == ()

    # A retry of the reverted save is refused instead of writing it again.
    with pytest.raises(ImageGridReviewError) as retried:
        _resolve(factory, artifact_root, seed, 0, key=save_key)
    assert retried.value.code == "GEOMETRY_CORRECTION_REVERTED"

    # The same geometry saved again appends a new revision (no resurrection).
    again = _resolve(factory, artifact_root, seed, 0, key=uuid4())
    assert again.created is True
    resaved = _world(factory, game_id)
    statuses = {
        row["revision"]: row["status"] for row in resaved["image_source_geometry_revisions"]
    }
    assert statuses == {0: "accepted", 1: "reverted", 2: "accepted"}
    revision_2 = next(
        row for row in resaved["image_source_geometry_revisions"] if row["revision"] == 2
    )
    assert revision_2["geometry_checksum_sha256"] == revision_1["geometry_checksum_sha256"]
    neighbour = next(row for row in resaved["recognized_boards"] if row["position_index"] == 1)
    assert neighbour["source_geometry_revision_id"] == revision_2["id"]

    # The worker's import writer resolves its geometry by checksum: the
    # reverted twin of revision 2 is never chosen.
    _import(factory, seed, "task0945-revert", [2])
    imported = _world(factory, game_id)
    board_2 = next(row for row in imported["recognized_boards"] if row["position_index"] == 2)
    assert board_2["source_geometry_revision_id"] == revision_2["id"]


def test_later_changes_refuse_the_revert_without_writing(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    # Four slots: after slots 0 and 2 are drawn, slot 3 keeps the image incomplete.
    factory, seed, artifact_root = _excepted_game(database, tmp_path, "task0945-blocked", 4)
    game_id = seed.game_id
    _resolve(factory, artifact_root, seed, 0, key=uuid4())
    [slot_0] = _entries(factory, seed)
    assert slot_0.revertable

    # A later correction of another slot of the image advances the source.
    _resolve(factory, artifact_root, seed, 2, key=uuid4())
    entries = {entry.position_index: entry for entry in _entries(factory, seed)}
    assert entries[0].blocking_reason is RevertBlockingReason.SOURCE_ADVANCED
    assert entries[2].revertable
    _refused(factory, seed, entries[0], RevertBlockingReason.SOURCE_ADVANCED)

    # Reverting the newer one makes the older the newest live revision again.
    _revert(factory, seed, entries[2], key=uuid4())
    [slot_0] = _entries(factory, seed)
    assert slot_0.position_index == 0 and slot_0.revertable

    # A human symbol decision after the correction.
    symbol_id = _symbol_id(factory, game_id, "WISNIA")
    with game_storage_scope(game_id), factory.begin() as session:
        SqlAlchemyGridCorrectionSymbolRepository(session).assign(
            game_id=game_id,
            review_item_id=slot_0.review_item_id,
            symbol_id_by_cell_index={3: symbol_id},
            actor=_ACTOR,
        )
    [slot_0] = _entries(factory, seed)
    assert slot_0.blocking_reason is RevertBlockingReason.CELLS_CHANGED
    _refused(factory, seed, slot_0, RevertBlockingReason.CELLS_CHANGED)


def test_a_neighbour_that_cannot_move_back_refuses_the_revert(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    factory, seed, artifact_root = _excepted_game(database, tmp_path, "task0945-shared")
    _resolve(factory, artifact_root, seed, 0, key=uuid4())
    with game_storage_scope(seed.game_id), factory.begin() as session:
        # The re-pointed neighbour was rejected after the correction.
        session.execute(
            text(
                "UPDATE game_data_v2.recognized_boards SET status = 'rejected' "
                "WHERE game_id = :game_id AND position_index = 1"
            ),
            {"game_id": seed.game_id},
        )
    [entry] = _entries(factory, seed)
    assert entry.blocking_reason is RevertBlockingReason.SHARED_SOURCE_REVISION
    _refused(factory, seed, entry, RevertBlockingReason.SHARED_SOURCE_REVISION)


def test_a_correction_that_admitted_the_image_is_not_revertable(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    factory, seed, artifact_root = _seeded(database, tmp_path, "task0945-admitted", 2)
    _import(factory, seed, "task0945-admitted", [1])
    _resolve(factory, artifact_root, seed, 0, key=uuid4())
    world = _world(factory, seed.game_id)
    assert world["source_images"][0]["geometry_completeness_status"] == "geometry_complete"
    [entry] = _entries(factory, seed)
    assert entry.blocking_reason is RevertBlockingReason.IMAGE_ADMITTED
    _refused(factory, seed, entry, RevertBlockingReason.IMAGE_ADMITTED)
    with game_storage_scope(seed.game_id), factory() as session:
        assert session.scalar(select(ImageGeometryCorrectionRevertModel.id)) is None
        session.rollback()


def test_migration_0153_downgrade_refuses_revert_history_and_round_trips(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    from alembic import command

    factory, seed, _artifact_root = _seeded(database, tmp_path, "task0945-migration", 1)
    game_id = seed.game_id
    histories = (
        (
            "UPDATE game_data_v2.image_source_geometry_revisions SET status = 'reverted' "
            "WHERE game_id = :game_id",
            "UPDATE game_data_v2.image_source_geometry_revisions SET status = 'accepted' "
            "WHERE game_id = :game_id",
        ),
        (
            "UPDATE game_data_v2.image_board_geometry_pending SET status = 'rejected', "
            "rejection_reason = 'cropped', rejected_at = now(), rejected_by = 'task-0945' "
            "WHERE game_id = :game_id",
            "UPDATE game_data_v2.image_board_geometry_pending SET status = 'pending', "
            "rejection_reason = NULL, rejected_at = NULL, rejected_by = NULL "
            "WHERE game_id = :game_id",
        ),
    )
    for apply, undo in histories:
        with database.engine.begin() as connection:
            connection.execute(text(apply), {"game_id": game_id})
        with pytest.raises(Exception, match="GEOMETRY_CORRECTION_REVERT_DOWNGRADE_HAS_HISTORY"):
            command.downgrade(database.config, "0152_super_game_series")
        with database.engine.begin() as connection:
            connection.execute(text(undo), {"game_id": game_id})

    # Rejected-slot rules of the lifecycle CHECK (W7 schema).
    with database.engine.begin() as connection, pytest.raises(Exception, match="rejection"):
        connection.execute(
            text(
                "UPDATE game_data_v2.image_board_geometry_pending SET status = 'rejected', "
                "rejection_reason = 'other', rejected_at = now(), rejected_by = 'task-0945' "
                "WHERE game_id = :game_id"
            ),
            {"game_id": game_id},
        )

    database.engine.dispose()
    command.downgrade(database.config, "0152_super_game_series")
    with database.engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT DISTINCT manifest_version FROM public.game_storage_locations")
            ).scalar_one()
            == "game-data-v2-manifest-v6"
        )
        assert (
            connection.execute(
                text("SELECT to_regclass('game_data_v2.image_geometry_correction_reverts')")
            ).scalar_one()
            is None
        )
        unique = connection.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'v2_uq_fd29b81bdd3878e81e86' AND conparentid = 0"
            )
        ).scalar_one()
        assert unique == "UNIQUE (game_id, source_image_id, geometry_checksum_sha256)"
    database.engine.dispose()
    command.upgrade(database.config, "head")
    with database.engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT DISTINCT manifest_version FROM public.game_storage_locations")
            ).scalar_one()
            == "game-data-v2-manifest-v7"
        )
        # The provisioned game got its partition of the new audit table back.
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM pg_inherits WHERE inhparent = "
                    "'game_data_v2.image_geometry_correction_reverts'::regclass"
                )
            ).scalar_one()
            == 1
        )


def test_a_withheld_slot_without_cells_or_neighbours_is_reverted(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    # Two deferred slots and nothing imported: the drawn board stays withheld
    # (the other slot keeps the image incomplete), so it has no cells and no
    # board was re-pointed by the save.
    factory, seed, artifact_root = _seeded(database, tmp_path, "task0945-withheld", 2)
    before = _world(factory, seed.game_id)
    _resolve(factory, artifact_root, seed, 0, key=uuid4())
    saved = _world(factory, seed.game_id)
    assert len(saved["recognized_boards"]) == 1
    assert saved["image_symbol_review_cells"] == []
    [entry] = _entries(factory, seed)
    assert entry.revertable, entry.blocking_reason

    result = _revert(factory, seed, entry, key=uuid4())
    assert result.removed_cell_count == 0
    assert result.repointed_board_ids == ()
    assert result.source_image_geometry_status is not None
    assert result.source_image_geometry_status.value == "geometry_incomplete"
    after = _world(factory, seed.game_id)
    assert len(after.pop("image_geometry_correction_reverts")) == 1
    before.pop("image_geometry_correction_reverts")
    revisions = after.pop("image_source_geometry_revisions")
    assert {row["revision"]: row["status"] for row in revisions} == {
        0: "accepted",
        1: "reverted",
    }
    assert [row for row in revisions if row["revision"] == 0] == before.pop(
        "image_source_geometry_revisions"
    )
    # The save's write-through initialized the game's symbol-review state row
    # (a game-level control row, never a per-board record); the revert keeps
    # it, empty: no cell and no count was left behind.
    assert before.pop("image_symbol_review_states") == []
    [state] = after.pop("image_symbol_review_states")
    assert (state["status"], state["cell_count"], state["count_projection"]) == (
        "rebuilding",
        0,
        {},
    )
    assert after == before
