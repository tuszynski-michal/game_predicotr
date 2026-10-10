"""TASK-0967: revert of a correction of an existing board (case A, PostgreSQL).

Runs on a dedicated ``*_test`` database only (fixtures of
``test_virtual_deferred_resolution_postgres`` and the import writer of
``test_image_geometry_completeness_gate``). Boards are imported through the
worker's writer, corrected through the production application path
(``VirtualGridGeometryService.save``, D-488 symbols included) and reverted
through the production repository; the game store is compared with its state
before the correction.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.geometry_correction_reverts import (
    RestoredRenderRequest,
    VirtualRestoredRenderVerifier,
)
from game_predictor_api.application.image_symbol_review_mutations import (
    SymbolCellReviewMutationCommand,
)
from game_predictor_api.application.virtual_grid_geometry import (
    VirtualGridCellSymbol,
    VirtualGridGeometryService,
)
from game_predictor_api.domain.board_render_manifests import sha256_canonical_json
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
from game_predictor_api.domain.image_reviews import (
    ImageReviewConflictError,
    ImageReviewGeometryPoint,
)
from game_predictor_api.domain.image_symbol_reviews import SymbolCellReviewAction
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_grid_review_repository import (
    SqlAlchemyImageGridReviewRepository,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemySymbolCellReviewMutationRepository,
)
from game_predictor_api.storage.models import (
    ImageReviewItemModel,
    ImageSymbolReviewCellModel,
    ImageSymbolReviewStateModel,
    RecognizedBoardModel,
)
from game_predictor_api.storage.virtual_grid_geometry_repository import (
    SqlAlchemyVirtualGridGeometryRepository,
)
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker
from test_geometry_correction_revert_pending_postgres import (
    _ACTOR,
    _entries,
    _refused,
    _revert,
    _service,
    _symbol_id,
    _world,
)
from test_image_geometry_completeness_gate import _import, _seeded
from test_virtual_deferred_resolution_postgres import (
    _Database,
    _Seed,
    database,  # noqa: F401  (pytest fixture)
    pytestmark,  # noqa: F401  (PostgreSQL opt-in)
)

# Inside the imported quad (60,50)-(560,350) of the seeded source image.
_FIRST_CORNERS = ((64, 54), (556, 52), (558, 346), (62, 348))
_SECOND_CORNERS = ((70, 58), (552, 56), (554, 342), (68, 344))
# Tables a case-A save or revert appends to (history, never rewritten).
_APPEND_ONLY = (
    "image_board_geometry_revisions",
    "board_render_manifests",
    "image_board_geometry_review_events",
    "image_symbol_review_events",
    "image_source_geometry_revisions",
    "image_geometry_correction_reverts",
)
# Cell columns a revert legitimately moves forward: the new revision N + 1,
# the cell revision, the approval rebound to N + 1 and the reviewing actor.
_CELL_MOVED = ("geometry_revision", "revision", "approved_geometry_revision", "last_reviewed_by")


def _points(corners: tuple[tuple[int, int], ...]) -> tuple[ImageReviewGeometryPoint, ...]:
    return tuple(ImageReviewGeometryPoint(x=x, y=y) for x, y in corners)


def _board_game(
    db: _Database, tmp_path: Path, code: str, slots: int = 1
) -> tuple[sessionmaker[Session], _Seed, Path]:
    """Every slot imported (revision 0, cells cut), symbol review ready."""

    factory, seed, artifact_root = _seeded(db, tmp_path, code, slots)
    with game_storage_scope(seed.game_id), factory.begin() as session:
        # A finished symbol-review backfill with exact counters before the
        # import: the imported cells are counted, D-488 symbols need a ready
        # projection, and the counters must come back exactly.
        state = session.get(ImageSymbolReviewStateModel, seed.game_id)
        if state is None:
            state = ImageSymbolReviewStateModel(game_id=seed.game_id, status="ready")
            session.add(state)
        state.status = "ready"
        state.count_projection_status = "ready"
        state.count_projection = {"_semantics": {"version": 2}}
    _import(factory, seed, code, list(range(slots)))
    return factory, seed, artifact_root


def _item(factory: sessionmaker[Session], seed: _Seed, position: int) -> UUID:
    with game_storage_scope(seed.game_id), factory() as session:
        item_id = session.scalar(
            select(ImageReviewItemModel.id)
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
            )
            .where(
                RecognizedBoardModel.source_image_id == seed.source_image_id,
                RecognizedBoardModel.position_index == position,
            )
        )
        session.rollback()
    assert item_id is not None
    return item_id


def _mutate(
    factory: sessionmaker[Session],
    seed: _Seed,
    item_id: UUID,
    cell_index: int,
    action: SymbolCellReviewAction,
    symbol_id: UUID | None = None,
) -> None:
    with game_storage_scope(seed.game_id), factory.begin() as session:
        cell = session.scalar(
            select(ImageSymbolReviewCellModel).where(
                ImageSymbolReviewCellModel.review_item_id == item_id,
                ImageSymbolReviewCellModel.cell_index == cell_index,
            )
        )
        assert cell is not None
        SqlAlchemySymbolCellReviewMutationRepository(session).apply_mutation(
            SymbolCellReviewMutationCommand(
                game_id=seed.game_id,
                cell_review_id=cell.id,
                action=action,
                expected_revision=cell.revision,
                expected_geometry_revision=cell.geometry_revision,
                expected_crop_sample_id=cell.crop_sample_id,
                expected_crop_checksum_sha256=cell.crop_checksum_sha256,
                target_symbol_id=symbol_id,
                actor=_ACTOR,
            )
        )


def _correct(
    factory: sessionmaker[Session],
    artifact_root: Path,
    seed: _Seed,
    item_id: UUID,
    corners: tuple[tuple[int, int], ...],
    *,
    key: UUID,
    cell_symbols: tuple[VirtualGridCellSymbol, ...] = (),
) -> Any:
    """A manual correction through the production application path."""

    with game_storage_scope(seed.game_id), factory.begin() as session:
        repository = SqlAlchemyVirtualGridGeometryRepository(session)
        context = repository.virtual_geometry_context(
            game_id=seed.game_id,
            import_job_id=seed.import_job_id,
            review_item_id=item_id,
            pending_geometry_id=None,
        )
        return VirtualGridGeometryService(repository, artifact_root).save(
            game_id=seed.game_id,
            import_job_id=seed.import_job_id,
            review_item_id=item_id,
            idempotency_key=key,
            expected_geometry_revision=context.geometry_revision,
            expected_resolution_revision=context.resolution_revision,
            expected_source_checksum_sha256=context.source_checksum_sha256,
            expected_source_width=context.oriented_width,
            expected_source_height=context.oriented_height,
            expected_grid_rows=context.topology.rows,
            expected_grid_columns=context.topology.columns,
            corners=_points(corners),
            actor=_ACTOR,
            created_at=datetime.now(UTC),
            cell_symbols=cell_symbols,
        )


def _entry(factory: sessionmaker[Session], seed: _Seed, item_id: UUID) -> Any:
    """The newest correction of the item's board."""

    return next(entry for entry in _entries(factory, seed) if entry.review_item_id == item_id)


def _rows(world: dict[str, Any], table: str, **match: Any) -> list[dict[str, Any]]:
    return [
        row
        for row in world[table]
        if all(row.get(column) == value for column, value in match.items())
    ]


def _without(row: dict[str, Any], columns: tuple[str, ...]) -> dict[str, Any]:
    return {column: value for column, value in row.items() if column not in columns}


def _assert_restored(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    board_id: UUID,
    written_revision: int,
    board_moved: tuple[str, ...] = ("geometry_revision",),
) -> None:
    """The store after the revert equals the store before the correction.

    Allowed differences: appended history rows, the reverted source revision,
    the board's revision ``N + 1`` (and an approval carried over to it) and
    the moved cell columns.
    """

    for table in _APPEND_ONLY:
        if table == "image_source_geometry_revisions":
            kept = [row for row in after[table] if row["status"] != "reverted"]
            assert kept == before[table]
        else:
            # History is append-only: every earlier row is still there.
            assert all(row in after[table] for row in before[table]), table
    boards_before = {row["id"]: row for row in before["recognized_boards"]}
    boards_after = {row["id"]: row for row in after["recognized_boards"]}
    assert boards_after.keys() == boards_before.keys()
    for board, row in boards_after.items():
        if board == str(board_id):
            assert row["geometry_revision"] == written_revision
            assert _without(row, board_moved) == _without(boards_before[board], board_moved)
        else:
            assert row == boards_before[board]
    cells_before = {row["id"]: row for row in before["image_symbol_review_cells"]}
    cells_after = {row["id"]: row for row in after["image_symbol_review_cells"]}
    assert cells_after.keys() == cells_before.keys()
    for cell, row in cells_after.items():
        previous = cells_before[cell]
        if row["recognized_board_id"] != str(board_id):
            assert row == previous
            continue
        assert row["geometry_revision"] == written_revision
        assert _without(row, _CELL_MOVED) == _without(previous, _CELL_MOVED), cell
        expected_approval = (
            None if previous["approved_geometry_revision"] is None else written_revision
        )
        if previous["review_state"] == "approved":
            assert row["approved_geometry_revision"] == expected_approval
        else:
            assert row["approved_geometry_revision"] == previous["approved_geometry_revision"]
    for table in before:
        if table in _APPEND_ONLY or table in {"recognized_boards", "image_symbol_review_cells"}:
            continue
        assert after[table] == before[table], table


def test_revert_of_a_first_correction_restores_the_imported_board(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    """N = 1, N - 1 = 0: grid issues, approvals and D-488 symbols come back."""

    factory, seed, artifact_root = _board_game(database, tmp_path, "task0946-first")
    game_id = seed.game_id
    item_id = _item(factory, seed, 0)
    cherry = _symbol_id(factory, game_id, "WISNIA")
    lemon = _symbol_id(factory, game_id, "CYTRYNA")
    # The reviewer approved two cells and reported a grid issue on three.
    _mutate(factory, seed, item_id, 5, SymbolCellReviewAction.REASSIGN, cherry)
    _mutate(factory, seed, item_id, 6, SymbolCellReviewAction.REASSIGN, lemon)
    for index in (0, 1, 2):
        _mutate(factory, seed, item_id, index, SymbolCellReviewAction.MARK_GRID_ISSUE)
    before = _world(factory, game_id)
    [board_before] = before["recognized_boards"]
    board_id = UUID(board_before["id"])
    grid_issues = sorted(
        row["cell_index"]
        for row in before["image_symbol_review_cells"]
        if row["quality_issue"] == "grid_issue"
    )
    assert grid_issues == [0, 1, 2]
    with game_storage_scope(game_id), factory() as session:
        queue_before = _correction_queue(session, seed)
        session.rollback()
    assert item_id in queue_before

    # The correction: new corners and D-488 symbols on two grid-issue cells.
    save_key = uuid4()
    saved = _correct(
        factory,
        artifact_root,
        seed,
        item_id,
        _FIRST_CORNERS,
        key=save_key,
        cell_symbols=(
            VirtualGridCellSymbol(cell_index=0, symbol_id=lemon),
            VirtualGridCellSymbol(cell_index=1, symbol_id=None),
        ),
    )
    assert saved.created is True and saved.revision.revision == 1
    corrected = _world(factory, game_id)
    assert not _rows(corrected, "image_symbol_review_cells", quality_issue="grid_issue")

    # Z1: every cell event of the correction shares the transaction's now();
    # the D-488 events of a cell follow its invalidation by cell revision.
    [manifest_1] = _rows(corrected, "board_render_manifests", geometry_revision=1)
    with game_storage_scope(game_id), factory() as session:
        stamps = session.execute(
            text(
                "SELECT e.created_at, e.cell_index_events, m.created_at, s.created_at "
                "FROM (SELECT min(created_at) AS created_at, "
                "             count(DISTINCT created_at) AS distinct_stamps, "
                "             count(*) AS cell_index_events "
                "      FROM game_data_v2.image_symbol_review_events "
                "      WHERE game_id = :game_id AND geometry_revision = 1) e, "
                "game_data_v2.board_render_manifests m, "
                "game_data_v2.image_source_geometry_revisions s "
                "WHERE m.game_id = :game_id AND m.recognized_board_id = :board_id "
                "AND m.geometry_revision = 1 AND s.game_id = :game_id AND s.revision = 1"
            ),
            {"game_id": game_id, "board_id": board_id},
        ).one()
        distinct = session.execute(
            text(
                "SELECT count(DISTINCT created_at) FROM game_data_v2.image_symbol_review_events "
                "WHERE game_id = :game_id AND geometry_revision = 1"
            ),
            {"game_id": game_id},
        ).scalar_one()
        ordered = session.execute(
            text(
                "SELECT c.cell_index, array_agg(e.action ORDER BY e.cell_revision) "
                "FROM game_data_v2.image_symbol_review_events e "
                "JOIN game_data_v2.image_symbol_review_cells c "
                "  ON c.game_id = e.game_id AND c.id = e.cell_review_id "
                "WHERE e.game_id = :game_id AND e.geometry_revision = 1 "
                "GROUP BY c.cell_index ORDER BY c.cell_index"
            ),
            {"game_id": game_id},
        ).all()
        session.rollback()
    assert distinct == 1
    assert stamps[0] == stamps[2] == stamps[3]
    assert stamps[1] == 17  # 15 invalidations + 2 operator symbols
    actions = dict(ordered)
    assert actions[0] == ["geometry_invalidated", "reassign"]
    assert actions[1] == ["geometry_invalidated", "mark_unreadable"]
    assert actions[2] == ["geometry_invalidated"]
    assert manifest_1["source_geometry_revision_id"] != board_before["source_geometry_revision_id"]

    [entry] = [value for value in _entries(factory, seed) if value.review_item_id == item_id]
    assert entry.kind is GeometryCorrectionKind.BOARD_REVISION
    assert entry.revertable, entry.blocking_reason
    with game_storage_scope(game_id), factory() as session:
        preview = _service(session).preview(
            game_id=game_id,
            import_job_id=seed.import_job_id,
            board_geometry_revision_id=entry.board_geometry_revision_id,
        )
        session.rollback()
    assert preview.removes_board is False
    assert preview.restored_cell_decision_count == 15
    assert (
        str(preview.restored_source_geometry_revision_id)
        == board_before["source_geometry_revision_id"]
    )
    assert _world(factory, game_id) == corrected

    _refused(
        factory,
        seed,
        entry,
        RevertBlockingReason.STALE,
        geometry_revision=entry.geometry_revision + 1,
    )
    # A board revert renders the restored cells; without a renderer: refused.
    with pytest.raises(ImageReviewConflictError) as unavailable:
        _revert(factory, seed, entry, key=uuid4())
    assert unavailable.value.code == "GEOMETRY_REVERT_RENDERER_UNAVAILABLE"
    assert _world(factory, game_id) == corrected
    [manifest_0] = _rows(before, "board_render_manifests", geometry_revision=0)
    imported_render = _RecordedRenderVerifier(manifest_0["cells"])
    revert_key = uuid4()
    result = _revert(factory, seed, entry, key=revert_key, verifier=imported_render)
    assert result.created is True
    assert result.kind is GeometryCorrectionKind.BOARD_REVISION
    assert result.restored_geometry_revision == 2
    assert result.restored_cell_decision_count == 15
    assert result.removed_cell_count == 0
    assert (
        str(result.restored_source_geometry_revision_id)
        == board_before["source_geometry_revision_id"]
    )
    reverted = _world(factory, game_id)
    _assert_restored(before, reverted, board_id=board_id, written_revision=2)

    # Revision 2 reuses the imported render; the board is back in the queue.
    assert imported_render.rendered == set(range(15))
    [manifest_2] = _rows(reverted, "board_render_manifests", geometry_revision=2)
    assert manifest_2["cells"] == manifest_0["cells"]
    assert manifest_2["source_geometry_revision_id"] == board_before["source_geometry_revision_id"]
    [revision_2] = _rows(reverted, "image_board_geometry_revisions", revision=2)
    assert revision_2["virtual_render_spec"] == manifest_0["cells"]
    assert revision_2["geometry"] == board_before["board_geometry"]
    [reverted_event] = _rows(reverted, "image_board_geometry_review_events", geometry_revision=2)
    assert reverted_event["action"] == "geometry_reverted"
    assert reverted_event["previous_approved_geometry_revision"] == 1
    cell_events = _rows(reverted, "image_symbol_review_events", action="geometry_reverted")
    assert len(cell_events) == 15
    # Full previous_* columns: the corrected state the revert replaced.
    assert all(row["previous_assignment_source"] is not None for row in cell_events)
    assert {row["previous_source_geometry_revision_id"] for row in cell_events} == {
        manifest_1["source_geometry_revision_id"]
    }
    assert {row["source_geometry_revision_id"] for row in cell_events} == {
        board_before["source_geometry_revision_id"]
    }
    restored_approvals = [row for row in cell_events if row["review_state"] == "approved"]
    assert len(restored_approvals) == 2
    assert all(
        row["previous_approved_rendered_pixel_checksum_sha256"] is not None
        and row["approved_rendered_pixel_checksum_sha256"] == row["rendered_pixel_checksum_sha256"]
        for row in restored_approvals
    )
    statuses = {
        row["revision"]: row["status"] for row in reverted["image_source_geometry_revisions"]
    }
    assert statuses[1] == "reverted"
    with game_storage_scope(game_id), factory() as session:
        queue_after = _correction_queue(session, seed)
        session.rollback()
    assert item_id in queue_after

    # The audit holds the cells before and after with a verifiable checksum.
    [audit] = reverted["image_geometry_correction_reverts"]
    snapshot = audit["snapshot"]
    assert snapshot_checksum_sha256(snapshot) == audit["snapshot_checksum_sha256"]
    assert audit["kind"] == "board_revision"
    assert audit["restored_geometry_revision"] == 2
    assert len(snapshot["cells"]["before"]) == len(snapshot["cells"]["after"]) == 15
    assert snapshot["restoredApprovalCount"] == 2
    assert snapshot["pendingSuggestionCount"] == 0

    # Replays, a second revert and a retry of the reverted save.
    replay = _revert(factory, seed, entry, key=revert_key)
    assert replay.created is False and replay.revert_id == result.revert_id
    _refused(factory, seed, entry, RevertBlockingReason.NOT_LATEST)
    [listed] = [value for value in _entries(factory, seed) if value.review_item_id == item_id]
    assert listed.blocking_reason is RevertBlockingReason.NOT_LATEST
    with pytest.raises(ImageGridReviewError) as retried:
        _correct(factory, artifact_root, seed, item_id, _FIRST_CORNERS, key=save_key)
    assert retried.value.code == "GEOMETRY_CORRECTION_REVERTED"

    # A new correction after the revert writes revision N + 2.
    again = _correct(factory, artifact_root, seed, item_id, _FIRST_CORNERS, key=uuid4())
    assert again.created is True and again.revision.revision == 3
    resaved = _world(factory, game_id)
    statuses = {
        row["revision"]: row["status"] for row in resaved["image_source_geometry_revisions"]
    }
    assert statuses == {0: "accepted", 1: "reverted", 2: "accepted"}
    newest = _entry(factory, seed, item_id)
    assert newest.geometry_revision == 3 and newest.revertable, newest.blocking_reason

    # P0-5: the second cycle restores revision 2, written by the revert; the
    # board gets the imported engine and projection back, not ``manual_v1``.
    _revert(factory, seed, newest, key=uuid4(), verifier=imported_render)
    twice = _world(factory, game_id)
    [board_twice] = twice["recognized_boards"]
    for column in (
        "geometry_engine_name",
        "geometry_engine_version",
        "board_geometry",
        "source_geometry_revision_id",
        "geometry_checksum_sha256",
        "approved_geometry_revision",
        "geometry_approved_at",
        "geometry_approved_by",
    ):
        assert board_twice[column] == board_before[column], column
    assert board_twice["geometry_revision"] == 4
    assert board_before["geometry_engine_name"] == "structured_opencv_v1"


def _correction_queue(session: Session, seed: _Seed) -> set[UUID]:
    page = SqlAlchemyImageGridReviewRepository(session).list_grid_reviews(
        review_filter=ImageGridReviewListFilter(
            game_id=seed.game_id,
            view=ImageGridReviewView.CORRECTION,
            import_job_id=seed.import_job_id,
        ),
        after_key=None,
        before_key=None,
        limit=50,
    )
    return {item.review_item_id for item in page.items if item.review_item_id is not None}


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


class _RecordedRenderVerifier:
    """Renders of the import fixture by their recorded pixels.

    The worker writer of ``test_image_geometry_completeness_gate`` stores
    synthetic render specs (no source quad), which no renderer can draw; a
    revert of the imported revision gets the pixels recorded for each spec.
    Revisions written by a manual save carry real specs and are rendered by
    ``VirtualRestoredRenderVerifier``.
    """

    def __init__(self, document: dict[str, Any]) -> None:
        self._pixels = {
            str(entry["renderSpecChecksumSha256"]): str(entry["renderedPixelChecksumSha256"])
            for entry in document["cells"]
        }
        self.rendered: set[int] = set()

    def rendered_pixel_checksums(self, request: RestoredRenderRequest) -> dict[int, str]:
        result: dict[int, str] = {}
        for index, spec in request.render_specs.items():
            result[index] = self._pixels[sha256_canonical_json(dict(spec))]
            self.rendered.add(index)
        return result


class _ChangedRenderer(VirtualRestoredRenderVerifier):
    """The real render, except other pixels for some cells (a renderer change)."""

    def __init__(self, artifact_root: Path, changed: set[int]) -> None:
        super().__init__(artifact_root)
        self._changed = changed
        self.real: dict[int, str] = {}

    def rendered_pixel_checksums(self, request: RestoredRenderRequest) -> dict[int, str]:
        self.real = dict(super().rendered_pixel_checksums(request))
        return {
            index: _sha(f"changed-renderer:{index}") if index in self._changed else pixels
            for index, pixels in self.real.items()
        }


def _insert_prediction_revision(
    factory: sessionmaker[Session],
    seed: _Seed,
    entry: Any,
    *,
    predictions: list[dict[str, Any]] | None = None,
    age: str = "0 seconds",
) -> UUID:
    revision_id = uuid4()
    with game_storage_scope(seed.game_id), factory.begin() as session:
        session.execute(
            text(
                """INSERT INTO game_data_v2.image_symbol_prediction_revisions (
                    id, game_id, review_item_id, recognized_board_id, source_job_id,
                    model_version, model_checksum_sha256, crop_manifest_checksum_sha256,
                    predictions, created_at)
                VALUES (:id, :game_id, :item_id, :board_id, :job_id, 'task-0967-model',
                    :model, :crops, CAST(:predictions AS jsonb),
                    now() - CAST(:age AS interval))"""
            ),
            {
                "id": revision_id,
                "game_id": seed.game_id,
                "item_id": entry.review_item_id,
                "board_id": entry.recognized_board_id,
                "job_id": seed.import_job_id,
                "model": _sha("task-0967-model"),
                "crops": _sha(f"task-0967-crops:{revision_id}"),
                "predictions": json.dumps({} if predictions is None else predictions),
                "age": age,
            },
        )
    return revision_id


def _delete(
    factory: sessionmaker[Session], seed: _Seed, table: str, column: str, value: UUID
) -> None:
    with game_storage_scope(seed.game_id), factory.begin() as session:
        session.execute(
            text(
                f"DELETE FROM game_data_v2.{table} WHERE game_id = :game_id AND {column} = :value"
            ),
            {"game_id": seed.game_id, "value": value},
        )


def _insert_bulk_target(
    factory: sessionmaker[Session], seed: _Seed, item_id: UUID, *, expected_geometry_revision: int
) -> UUID:
    operation_id = uuid4()
    with game_storage_scope(seed.game_id), factory.begin() as session:
        cell = session.scalar(
            select(ImageSymbolReviewCellModel).where(
                ImageSymbolReviewCellModel.review_item_id == item_id,
                ImageSymbolReviewCellModel.cell_index == 0,
            )
        )
        assert cell is not None
        session.execute(
            text(
                """INSERT INTO game_data_v2.image_symbol_review_bulk_operations (
                    id, game_id, job_id, action, selection_kind, idempotency_key,
                    command_sha256, actor, status, target_count)
                VALUES (:id, :game_id, :job_id, 'approve', 'explicit', :key, :command,
                    :actor, 'completed', 1)"""
            ),
            {
                "id": operation_id,
                "game_id": seed.game_id,
                "job_id": seed.import_job_id,
                "key": uuid4(),
                "command": _sha(f"bulk:{operation_id}"),
                "actor": _ACTOR,
            },
        )
        session.execute(
            text(
                """INSERT INTO game_data_v2.image_symbol_review_bulk_targets (
                    game_id, operation_id, cell_review_id, review_item_id, recognized_board_id,
                    sequence_number, cell_index, expected_revision, expected_geometry_revision,
                    status)
                VALUES (:game_id, :operation_id, :cell_id, :item_id, :board_id, :sequence, 0,
                    :revision, :geometry_revision, 'applied')"""
            ),
            {
                "game_id": seed.game_id,
                "operation_id": operation_id,
                "cell_id": cell.id,
                "item_id": item_id,
                "board_id": cell.recognized_board_id,
                "sequence": cell.sequence_number,
                "revision": cell.revision,
                "geometry_revision": expected_geometry_revision,
            },
        )
    return operation_id


def _delete_bulk(factory: sessionmaker[Session], seed: _Seed, operation_id: UUID) -> None:
    _delete(factory, seed, "image_symbol_review_bulk_targets", "operation_id", operation_id)
    _delete(factory, seed, "image_symbol_review_bulk_operations", "id", operation_id)


def _manifest_cells(world: dict[str, Any], revision: int) -> dict[int, dict[str, Any]]:
    [manifest] = _rows(world, "board_render_manifests", geometry_revision=revision)
    return {int(entry["cellIndex"]): entry for entry in manifest["cells"]["cells"]}


def _cells(world: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {int(row["cell_index"]): row for row in world["image_symbol_review_cells"]}


_APPROVED_COLUMNS = (
    "approved_crop_sample_id",
    "approved_crop_checksum_sha256",
    "approved_geometry_revision",
    "approved_asset_mode",
    "approved_source_geometry_revision_id",
    "approved_render_spec_checksum_sha256",
    "approved_rendered_pixel_checksum_sha256",
)


def test_revert_of_a_second_correction_restores_the_first_revision(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    """N = 2: the geometry and render of revision 1 come back as revision 3.

    Then a third correction and its revert: the approval kept by the first
    revert is restored with its original time and actor (P0-1).
    """

    factory, seed, artifact_root = _board_game(database, tmp_path, "task0946-second")
    game_id = seed.game_id
    item_id = _item(factory, seed, 0)
    cherry = _symbol_id(factory, game_id, "WISNIA")
    renderer = VirtualRestoredRenderVerifier(artifact_root)
    _correct(factory, artifact_root, seed, item_id, _FIRST_CORNERS, key=uuid4())
    first = _entry(factory, seed, item_id)
    # A human decision on revision 1, then a grid report, then correction 2.
    _mutate(factory, seed, item_id, 3, SymbolCellReviewAction.REASSIGN, cherry)
    _mutate(factory, seed, item_id, 4, SymbolCellReviewAction.MARK_GRID_ISSUE)
    before = _world(factory, game_id)
    [board_before] = before["recognized_boards"]
    assert board_before["approved_geometry_revision"] == 1
    _correct(factory, artifact_root, seed, item_id, _SECOND_CORNERS, key=uuid4())
    second = _entry(factory, seed, item_id)
    assert second.geometry_revision == 2 and second.revertable, second.blocking_reason
    # Only the newest correction of a board is revertable.
    first = next(
        entry
        for entry in _entries(factory, seed)
        if entry.board_geometry_revision_id == first.board_geometry_revision_id
    )
    assert first.blocking_reason is RevertBlockingReason.NOT_LATEST
    _refused(factory, seed, first, RevertBlockingReason.NOT_LATEST)

    result = _revert(factory, seed, second, key=uuid4(), verifier=renderer)
    assert result.restored_geometry_revision == 3
    reverted = _world(factory, game_id)
    # Lead decision (D-542): the approval of revision 1 follows its geometry
    # to revision 3 with its original time and actor.
    _assert_restored(
        before,
        reverted,
        board_id=UUID(board_before["id"]),
        written_revision=3,
        board_moved=("geometry_revision", "approved_geometry_revision"),
    )
    [board_after] = reverted["recognized_boards"]
    assert board_after["approved_geometry_revision"] == 3
    assert board_after["geometry_approved_at"] == board_before["geometry_approved_at"]
    assert board_after["geometry_approved_by"] == board_before["geometry_approved_by"]
    [revision_1] = _rows(before, "image_board_geometry_revisions", revision=1)
    [revision_3] = _rows(reverted, "image_board_geometry_revisions", revision=3)
    for column in ("corners", "geometry", "virtual_render_spec", "source_geometry_revision_id"):
        assert revision_3[column] == revision_1[column], column
    # Z2 on real pixels: the stored revision-1 specs render the same today.
    assert _manifest_cells(reverted, 3) == _manifest_cells(before, 1)
    [reverted_event] = _rows(reverted, "image_board_geometry_review_events", geometry_revision=3)
    assert reverted_event["approved_geometry_revision"] == 3
    cells = _cells(reverted)
    assert (cells[3]["review_state"], cells[3]["assigned_symbol_id"]) == ("approved", str(cherry))
    assert cells[4]["quality_issue"] == "grid_issue"

    # A new correction after the revert, and its revert (P0-1, P0-5).
    _correct(factory, artifact_root, seed, item_id, _FIRST_CORNERS, key=uuid4())
    third = _entry(factory, seed, item_id)
    assert third.geometry_revision == 4 and third.revertable, third.blocking_reason
    _revert(factory, seed, third, key=uuid4(), verifier=renderer)
    again = _world(factory, game_id)
    [board_again] = again["recognized_boards"]
    assert board_again["geometry_revision"] == 5
    assert board_again["approved_geometry_revision"] == 5
    # Never the revert's own time or actor.
    assert board_again["geometry_approved_at"] == board_before["geometry_approved_at"]
    assert board_again["geometry_approved_by"] == board_before["geometry_approved_by"]
    for column in ("geometry_engine_name", "geometry_engine_version", "board_geometry"):
        assert board_again[column] == board_before[column], column
    assert _manifest_cells(again, 5) == _manifest_cells(before, 1)


def test_a_renderer_change_returns_approvals_as_suggestions_and_pins_by_identity(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    """D-462 on the pixels rendered today (P0-3) and the case-A pins (P1-1).

    The renderer is changed for one cell; no history row is modified.
    """

    factory, seed, artifact_root = _board_game(database, tmp_path, "task0946-pixels")
    game_id = seed.game_id
    item_id = _item(factory, seed, 0)
    cherry = _symbol_id(factory, game_id, "WISNIA")
    lemon = _symbol_id(factory, game_id, "CYTRYNA")
    _correct(factory, artifact_root, seed, item_id, _FIRST_CORNERS, key=uuid4())
    _mutate(factory, seed, item_id, 5, SymbolCellReviewAction.REASSIGN, cherry)
    _mutate(factory, seed, item_id, 6, SymbolCellReviewAction.REASSIGN, lemon)
    before = _world(factory, game_id)
    _correct(factory, artifact_root, seed, item_id, _SECOND_CORNERS, key=uuid4())
    entry = _entry(factory, seed, item_id)
    assert entry.revertable, entry.blocking_reason
    corrected = _world(factory, game_id)
    discarded = _manifest_cells(corrected, 2)
    restored = _manifest_cells(corrected, 1)

    def virtual_cell(manifest_entry: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "symbolCode": "WISNIA",
                "virtualCell": {
                    "cropChecksumSha256": manifest_entry["renderedPixelChecksumSha256"],
                    "renderSpecChecksumSha256": manifest_entry["renderSpecChecksumSha256"],
                },
            }
        ]

    # A prediction of the discarded render pins even when dated earlier.
    pinned = _insert_prediction_revision(
        factory, seed, entry, predictions=virtual_cell(discarded[0]), age="1 day"
    )
    _refused(factory, seed, entry, RevertBlockingReason.PINNED)
    _delete(factory, seed, "image_symbol_prediction_revisions", "id", pinned)
    # Without a render identity the time decides: written after the correction.
    unidentified = _insert_prediction_revision(factory, seed, entry)
    _refused(factory, seed, entry, RevertBlockingReason.PINNED)
    _delete(factory, seed, "image_symbol_prediction_revisions", "id", unidentified)
    # A bulk target expecting the discarded revision pins.
    operation = _insert_bulk_target(factory, seed, item_id, expected_geometry_revision=2)
    _refused(factory, seed, entry, RevertBlockingReason.PINNED)
    _delete_bulk(factory, seed, operation)
    # References to the restored render (or older) never pin, whatever their age.
    _insert_prediction_revision(factory, seed, entry, predictions=virtual_cell(restored[0]))
    _insert_bulk_target(factory, seed, item_id, expected_geometry_revision=1)
    entry = _entry(factory, seed, item_id)
    assert entry.revertable, entry.blocking_reason

    renderer = _ChangedRenderer(artifact_root, {5})
    result = _revert(factory, seed, entry, key=uuid4(), verifier=renderer)
    assert result.restored_geometry_revision == 3
    reverted = _world(factory, game_id)
    # The unchanged renderer reproduces every stored revision-1 pixel.
    assert renderer.real == {
        index: value["renderedPixelChecksumSha256"] for index, value in restored.items()
    }
    cells, previous = _cells(reverted), _cells(before)
    changed = _sha("changed-renderer:5")
    # Cell 5: other pixels -> the old symbol as a pending human suggestion,
    # the approval stays as history; the render records today's pixels.
    assert (cells[5]["review_state"], cells[5]["assigned_symbol_id"]) == ("pending", str(cherry))
    assert cells[5]["assignment_source"] == "human"
    assert cells[5]["verification_outcome"] == "requires_review"
    assert cells[5]["rendered_pixel_checksum_sha256"] == changed
    assert cells[5]["crop_checksum_sha256"] == changed
    for column in _APPROVED_COLUMNS:
        assert cells[5][column] == previous[5][column], column
    # Cell 6: identical pixels -> approved again on revision 3.
    assert cells[6]["review_state"] == "approved"
    assert cells[6]["approved_geometry_revision"] == 3
    assert (
        cells[6]["approved_rendered_pixel_checksum_sha256"]
        == previous[6]["rendered_pixel_checksum_sha256"]
    )
    manifest_3 = _manifest_cells(reverted, 3)
    assert manifest_3[5]["renderedPixelChecksumSha256"] == changed
    assert {index: value for index, value in manifest_3.items() if index != 5} == {
        index: value for index, value in restored.items() if index != 5
    }
    assert manifest_3[5]["renderSpec"] == restored[5]["renderSpec"]
    [audit] = reverted["image_geometry_correction_reverts"]
    assert audit["snapshot"]["restoredApprovalCount"] == 1
    assert audit["snapshot"]["pendingSuggestionCount"] == 1


def test_an_approval_without_recorded_provenance_is_never_reconstructed(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    """P0-2 and the ``assignment_source`` rule for events before 0154/0967.

    Cell 5 was approved on revision 1; correction 2 left that approval as
    history and a D-488 symbol overwrote the cell's approval columns. Its
    events are rewritten to the format before TASK-0967 (no approval
    provenance, no ``previous_assignment_source``).
    """

    factory, seed, artifact_root = _board_game(database, tmp_path, "task0946-history")
    game_id = seed.game_id
    item_id = _item(factory, seed, 0)
    cherry = _symbol_id(factory, game_id, "WISNIA")
    lemon = _symbol_id(factory, game_id, "CYTRYNA")
    _correct(factory, artifact_root, seed, item_id, _FIRST_CORNERS, key=uuid4())
    _mutate(factory, seed, item_id, 5, SymbolCellReviewAction.REASSIGN, cherry)
    _mutate(factory, seed, item_id, 7, SymbolCellReviewAction.MARK_GRID_ISSUE)
    before = _world(factory, game_id)
    _correct(
        factory,
        artifact_root,
        seed,
        item_id,
        _SECOND_CORNERS,
        key=uuid4(),
        cell_symbols=(VirtualGridCellSymbol(cell_index=5, symbol_id=lemon),),
    )
    corrected = _cells(_world(factory, game_id))
    assert corrected[5]["approved_geometry_revision"] == 2  # overwritten by D-488
    extras = (
        "approved_asset_mode",
        "approved_source_geometry_revision_id",
        "approved_render_spec_checksum_sha256",
        "approved_rendered_pixel_checksum_sha256",
    )
    nulls = ", ".join(f"{column} = NULL, previous_{column} = NULL" for column in extras)
    cell_5 = corrected[5]["id"]
    with game_storage_scope(game_id), factory.begin() as session:
        approval_event = session.execute(
            text(
                f"SELECT id, {', '.join(extras)} FROM game_data_v2.image_symbol_review_events "
                "WHERE game_id = :game_id AND cell_review_id = :cell AND action = 'reassign' "
                "AND geometry_revision = 1"
            ),
            {"game_id": game_id, "cell": cell_5},
        ).one()
        session.execute(
            text(
                f"UPDATE game_data_v2.image_symbol_review_events SET {nulls} "
                "WHERE game_id = :game_id AND cell_review_id = :cell"
            ),
            {"game_id": game_id, "cell": cell_5},
        )
        session.execute(
            text(
                "UPDATE game_data_v2.image_symbol_review_events "
                "SET previous_assignment_source = NULL "
                "WHERE game_id = :game_id AND review_item_id = :item AND geometry_revision = 2"
            ),
            {"game_id": game_id, "item": item_id},
        )
    entry = _entry(factory, seed, item_id)
    assert entry.blocking_reason is RevertBlockingReason.HISTORY_INCOMPLETE
    _refused(factory, seed, entry, RevertBlockingReason.HISTORY_INCOMPLETE)

    # The event that recorded the approval on revision 1 is the evidence.
    with game_storage_scope(game_id), factory.begin() as session:
        session.execute(
            text(
                "UPDATE game_data_v2.image_symbol_review_events SET "
                + ", ".join(f"{column} = :{column}" for column in extras)
                + " WHERE game_id = :game_id AND id = :id"
            ),
            {"game_id": game_id, **approval_event._mapping},
        )
    entry = _entry(factory, seed, item_id)
    assert entry.revertable, entry.blocking_reason
    _revert(factory, seed, entry, key=uuid4(), verifier=_ChangedRenderer(artifact_root, {5}))
    cells, previous = _cells(_world(factory, game_id)), _cells(before)
    assert (cells[5]["review_state"], cells[5]["assigned_symbol_id"]) == ("pending", str(cherry))
    # The exact approval of revision 1, not a mix with another render.
    for column in _APPROVED_COLUMNS:
        assert cells[5][column] == previous[5][column], column
    # Rule without a recorded source: approved -> human, pending -> model,
    # also for cell 7 whose grid report the reviewer made (the rule is lossy).
    assert cells[5]["assignment_source"] == "human"
    assert previous[7]["assignment_source"] == "human"
    assert (cells[7]["quality_issue"], cells[7]["assignment_source"]) == ("grid_issue", "model")


def test_a_correction_that_reopened_a_resolved_board_is_not_revertable(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    factory, seed, artifact_root = _board_game(database, tmp_path, "task0946-reopened")
    game_id = seed.game_id
    item_id = _item(factory, seed, 0)
    cherry = _symbol_id(factory, game_id, "WISNIA")
    # Fifteen verified cells close the board.
    for index in range(15):
        _mutate(factory, seed, item_id, index, SymbolCellReviewAction.REASSIGN, cherry)
    with game_storage_scope(game_id), factory() as session:
        status = session.scalar(
            select(ImageReviewItemModel.status).where(ImageReviewItemModel.id == item_id)
        )
        session.rollback()
    assert status in {"accepted", "corrected"}
    # The correction reopens it; the new pixels keep it open.
    _correct(factory, artifact_root, seed, item_id, _FIRST_CORNERS, key=uuid4())
    entry = _entry(factory, seed, item_id)
    with game_storage_scope(game_id), factory() as session:
        reopened = session.execute(
            text(
                "SELECT i.status, count(e.*) FROM game_data_v2.image_review_items i "
                "JOIN game_data_v2.image_review_resolution_events e "
                "  ON e.game_id = i.game_id AND e.review_item_id = i.id AND e.action = 'reopened' "
                "WHERE i.game_id = :game_id AND i.id = :item_id GROUP BY i.status"
            ),
            {"game_id": game_id, "item_id": item_id},
        ).one()
        session.rollback()
    assert tuple(reopened) == ("pending", 1)
    assert entry.blocking_reason is RevertBlockingReason.REOPENED_RESOLUTION
    _refused(factory, seed, entry, RevertBlockingReason.REOPENED_RESOLUTION)


def test_later_changes_of_the_image_and_cells_refuse_a_board_revert(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    factory, seed, artifact_root = _board_game(database, tmp_path, "task0946-refusals", 2)
    game_id = seed.game_id
    item_0, item_1 = _item(factory, seed, 0), _item(factory, seed, 1)
    _correct(factory, artifact_root, seed, item_0, _FIRST_CORNERS, key=uuid4())
    # A later correction of the other board advances the source geometry.
    _correct(factory, artifact_root, seed, item_1, _FIRST_CORNERS, key=uuid4())
    entry_0, entry_1 = _entry(factory, seed, item_0), _entry(factory, seed, item_1)
    assert entry_0.blocking_reason is RevertBlockingReason.SOURCE_ADVANCED
    _refused(factory, seed, entry_0, RevertBlockingReason.SOURCE_ADVANCED)
    assert entry_1.revertable, entry_1.blocking_reason
    with game_storage_scope(game_id), factory() as session:
        [manifest_0] = session.execute(
            text(
                "SELECT m.cells FROM game_data_v2.board_render_manifests m "
                "JOIN game_data_v2.image_review_items i "
                "  ON i.game_id = m.game_id AND i.recognized_board_id = m.recognized_board_id "
                "WHERE m.game_id = :game_id AND i.id = :item AND m.geometry_revision = 0"
            ),
            {"game_id": game_id, "item": item_1},
        ).one()
        session.rollback()
    _revert(factory, seed, entry_1, key=uuid4(), verifier=_RecordedRenderVerifier(manifest_0))
    # Board 1 is back on the revision board 0's correction wrote, so that
    # source revision cannot be reverted any more.
    entry_0 = _entry(factory, seed, item_0)
    assert entry_0.blocking_reason is RevertBlockingReason.SHARED_SOURCE_REVISION
    _refused(factory, seed, entry_0, RevertBlockingReason.SHARED_SOURCE_REVISION)

    # A symbol verification after a correction.
    _correct(factory, artifact_root, seed, item_1, _SECOND_CORNERS, key=uuid4())
    entry_1 = _entry(factory, seed, item_1)
    assert entry_1.geometry_revision == 3 and entry_1.revertable, entry_1.blocking_reason
    _mutate(
        factory,
        seed,
        item_1,
        2,
        SymbolCellReviewAction.REASSIGN,
        _symbol_id(factory, game_id, "WISNIA"),
    )
    entry_1 = _entry(factory, seed, item_1)
    assert entry_1.blocking_reason is RevertBlockingReason.CELLS_CHANGED
    _refused(factory, seed, entry_1, RevertBlockingReason.CELLS_CHANGED)
