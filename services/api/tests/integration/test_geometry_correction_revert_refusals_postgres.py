"""TASK-0945 audit round 1: refusals, history and concurrency of the revert (PostgreSQL).

Every refusal is read from real rows by the production repository and must
leave the game store unchanged. Concurrency tests use two real connections
with a controlled commit point. Runs on a dedicated ``*_test`` database only.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.geometry_correction_reverts import (
    GeometryCorrectionRevertService,
    VirtualRestoredRenderVerifier,
)
from game_predictor_api.domain.geometry_correction_reverts import (
    GeometryCorrectionKind,
    RevertBlockingReason,
)
from game_predictor_api.domain.image_reviews import ImageReviewConflictError
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.geometry_correction_revert_repository import (
    SqlAlchemyGeometryCorrectionRevertRepository,
    _idempotency_lock_key,
)
from game_predictor_api.storage.image_geometry_completeness_state_repository import (
    SqlAlchemyImageGeometryCompletenessStateRepository,
)
from game_predictor_api.storage.models import (
    ImageBoardGeometryReviewEventModel,
    ImageBoardGeometryRevisionModel,
    RecognizedBoardModel,
)
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker
from test_geometry_correction_revert_pending_postgres import (
    _ACTOR,
    _entries,
    _excepted_game,
    _refused,
    _resolve,
    _revert,
    _world,
)
from test_image_geometry_completeness_gate import _import, _seeded
from test_reviewer_operational_geometry_postgres import _SHIFTED_CORNERS, _app
from test_virtual_deferred_resolution_postgres import (
    _Database,
    _Seed,
    _seed,
    database,  # noqa: F401  (pytest fixture)
    pytestmark,  # noqa: F401  (PostgreSQL opt-in)
)


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _review_path(seed: _Seed, review_item_id: UUID) -> tuple[str, dict[str, str]]:
    return (
        f"/api/v1/admin/image-review-items/{review_item_id}",
        {"gameId": str(seed.game_id), "importJobId": str(seed.import_job_id)},
    )


def test_a_historical_legacy_correction_is_listed_as_not_revertable(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    """P0-1: a ``legacy_file`` correction without a source revision."""

    factory, seed, artifact_root = _excepted_game(database, tmp_path, "task0945-legacy")
    _resolve(factory, artifact_root, seed, 0, key=uuid4())
    with game_storage_scope(seed.game_id), factory.begin() as session:
        neighbour = session.scalar(
            select(RecognizedBoardModel).where(RecognizedBoardModel.position_index == 1)
        )
        assert neighbour is not None
        review_item_id = session.execute(
            text(
                "SELECT id FROM game_data_v2.image_review_items "
                "WHERE game_id = :game_id AND recognized_board_id = :board_id"
            ),
            {"game_id": seed.game_id, "board_id": neighbour.id},
        ).scalar_one()
        long_ago = datetime.now(UTC) - timedelta(days=400)
        # A pre-D-467 save: file crops, no source geometry revision.
        session.add(
            ImageBoardGeometryRevisionModel(
                review_item_id=review_item_id,
                recognized_board_id=neighbour.id,
                revision=7,
                idempotency_key=uuid4(),
                command_sha256=_sha("legacy-command"),
                corners=[{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}, {"x": 0, "y": 1}],
                geometry={},
                asset_mode="legacy_file",
                source_geometry_revision_id=None,
                geometry_checksum_sha256=None,
                virtual_render_spec=None,
                virtual_render_spec_checksum_sha256=None,
                board_relative_path="legacy/boards/board.png",
                board_checksum_sha256=_sha("legacy-board"),
                cropper_version="legacy-cropper",
                crop_artifacts=[{"cellIndex": index} for index in range(15)],
                corrected_by="legacy-operator",
                created_at=long_ago,
            )
        )
        session.add(
            ImageBoardGeometryReviewEventModel(
                review_item_id=review_item_id,
                recognized_board_id=neighbour.id,
                geometry_revision=7,
                grid_rows=3,
                grid_columns=5,
                board_checksum_sha256=_sha("legacy-board"),
                action="geometry_saved",
                previous_approved_geometry_revision=None,
                approved_geometry_revision=7,
                actor="legacy-operator",
                created_at=long_ago,
            )
        )

    entries = _entries(factory, seed)
    assert [entry.kind for entry in entries] == [
        GeometryCorrectionKind.PENDING_SLOT,
        GeometryCorrectionKind.BOARD_REVISION,
    ]
    slot, legacy = entries
    assert slot.revertable, slot.blocking_reason
    assert legacy.blocking_reason is RevertBlockingReason.NOT_SUPPORTED
    with game_storage_scope(seed.game_id), factory() as session:
        with pytest.raises(ImageReviewConflictError) as preview:
            GeometryCorrectionRevertService(
                SqlAlchemyGeometryCorrectionRevertRepository(session)
            ).preview(
                game_id=seed.game_id,
                import_job_id=seed.import_job_id,
                board_geometry_revision_id=legacy.board_geometry_revision_id,
            )
        session.rollback()
    assert preview.value.code == RevertBlockingReason.NOT_SUPPORTED.value
    _refused(factory, seed, legacy, RevertBlockingReason.NOT_SUPPORTED)
    # The current slot correction stays revertable next to the history.
    assert _revert(factory, seed, slot, key=uuid4()).created is True


def _wait_for_key_lock_waiter(db: _Database, game_id: UUID, key: UUID) -> None:
    """Wait until a request blocks on the revert's idempotency-key lock.

    The waiter must queue on exactly that advisory lock (taken before the
    first read), not on a later sequence or row lock.
    """

    lock = _idempotency_lock_key(game_id, key) & 0xFFFFFFFFFFFFFFFF
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        with db.engine.connect() as connection:
            waiting = connection.execute(
                text(
                    "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
                    "AND NOT granted AND classid = :high AND objid = :low AND objsubid = 1"
                ),
                {"high": lock >> 32, "low": lock & 0xFFFFFFFF},
            ).scalar_one()
        if waiting:
            return
        time.sleep(0.1)
    raise AssertionError("the retry never waited on the idempotency-key lock")


def test_a_retry_racing_the_first_commit_returns_the_stored_result(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    """P0-2: the same idempotency key while the first revert commits."""

    factory, seed, artifact_root = _seeded(database, tmp_path, "task0945-race", 2)
    _resolve(factory, artifact_root, seed, 0, key=uuid4())
    [entry] = _entries(factory, seed)
    key = uuid4()
    second: dict[str, Any] = {}

    def retry() -> None:
        try:
            second["result"] = _revert(factory, seed, entry, key=key)
        except Exception as error:  # noqa: BLE001 - reported to the main thread
            second["error"] = error

    with game_storage_scope(seed.game_id), factory() as session, session.begin():
        first = GeometryCorrectionRevertService(
            SqlAlchemyGeometryCorrectionRevertRepository(session)
        ).revert(
            game_id=seed.game_id,
            import_job_id=seed.import_job_id,
            board_geometry_revision_id=entry.board_geometry_revision_id,
            idempotency_key=key,
            expected_geometry_revision=entry.geometry_revision,
            expected_resolution_revision=entry.resolution_revision,
            actor=_ACTOR,
            reverted_at=datetime.now(UTC),
        )
        thread = threading.Thread(target=retry)
        thread.start()
        # The retry must be blocked by the uncommitted first revert.
        _wait_for_key_lock_waiter(database, seed.game_id, key)
    # The first transaction committed when the ``begin()`` block ended.
    thread.join(timeout=60)
    assert not thread.is_alive()
    assert "error" not in second, second.get("error")
    result = second["result"]
    assert first.created is True
    assert result.created is False
    assert result.revert_id == first.revert_id
    with game_storage_scope(seed.game_id), factory() as session:
        audits = session.execute(
            text(
                "SELECT count(*) FROM game_data_v2.image_geometry_correction_reverts "
                "WHERE game_id = :game_id"
            ),
            {"game_id": seed.game_id},
        ).scalar_one()
        session.rollback()
    assert audits == 1


def test_listing_skips_a_correction_reverted_between_its_reads(
    database: _Database,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0-3: a revert commits after the id query of the list."""

    factory, seed, artifact_root = _excepted_game(database, tmp_path, "task0945-listrace", 4)
    _resolve(factory, artifact_root, seed, 0, key=uuid4())
    _resolve(factory, artifact_root, seed, 2, key=uuid4())
    newest, older = _entries(factory, seed)
    assert newest.position_index == 2 and newest.revertable
    assert older.blocking_reason is RevertBlockingReason.SOURCE_ADVANCED

    original = SqlAlchemyGeometryCorrectionRevertRepository._correction
    reverted: list[object] = []
    triggered: list[bool] = []

    def correction_after_a_concurrent_revert(
        self: SqlAlchemyGeometryCorrectionRevertRepository, game_id: UUID, revision_id: UUID
    ) -> Any:
        # Only the listing's first detail read triggers the concurrent
        # revert (which itself reads corrections through this method).
        if not triggered:
            triggered.append(True)
            # Another request commits a revert in its own connection.
            thread = threading.Thread(
                target=lambda: reverted.append(_revert(factory, seed, newest, key=uuid4()))
            )
            thread.start()
            thread.join(timeout=60)
            assert reverted, "the concurrent revert did not finish"
        return original(self, game_id, revision_id)

    monkeypatch.setattr(
        SqlAlchemyGeometryCorrectionRevertRepository,
        "_correction",
        correction_after_a_concurrent_revert,
    )
    [listed] = _entries(factory, seed)
    monkeypatch.undo()
    assert listed.board_geometry_revision_id == older.board_geometry_revision_id
    assert listed.revertable, listed.blocking_reason


def test_a_resolved_review_item_refuses_the_revert(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    factory, seed, artifact_root = _seeded(database, tmp_path, "task0945-resolved", 2)
    _resolve(factory, artifact_root, seed, 0, key=uuid4())
    [entry] = _entries(factory, seed)
    base, query = _review_path(seed, entry.review_item_id)
    app = _app(database, artifact_root)
    try:
        with TestClient(app) as client:
            rejected = client.post(
                f"{base}/resolution",
                params=query,
                json={
                    "idempotencyKey": str(uuid4()),
                    "expectedRevision": entry.resolution_revision,
                    "action": "rejected",
                    "geometryRevision": entry.geometry_revision,
                    "rejectionReason": "Plansza przycięta",
                    "resolvedBy": _ACTOR,
                },
            )
    finally:
        app.state.database_engine.dispose()
    assert rejected.status_code == 200, rejected.text
    [entry] = _entries(factory, seed)
    assert entry.blocking_reason is RevertBlockingReason.RESOLVED
    _refused(factory, seed, entry, RevertBlockingReason.RESOLVED)


def _ownership_game(
    db: _Database, tmp_path: Path, code: str
) -> tuple[sessionmaker[Session], _Seed, _Seed, Path]:
    """Sequence 100 imported by an older job, then deferred by a newer one."""

    factory, older, artifact_root = _seeded(db, tmp_path, code, 1)
    _import(factory, older, code, [0])
    newer = _seed(factory, older.game_id, artifact_root, label=f"{code}-newer", slot_count=2)
    # Admitted by an operator exception: the new owner is cut at once.
    with game_storage_scope(newer.game_id), factory.begin() as session:
        SqlAlchemyImageGeometryCompletenessStateRepository(session).set_exception(
            newer.game_id, newer.source_image_id, reason="Slot 2 poza kadrem", actor=_ACTOR
        )
    return factory, older, newer, artifact_root


def test_a_correction_that_superseded_the_sequence_owner_refuses_the_revert(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    factory, older, newer, artifact_root = _ownership_game(database, tmp_path, "task0945-owner")
    _resolve(factory, artifact_root, newer, 0, key=uuid4())
    with game_storage_scope(older.game_id), factory() as session:
        superseded = session.execute(
            text(
                "SELECT count(*) FROM game_data_v2.image_review_resolution_events "
                "WHERE game_id = :game_id AND action = 'superseded'"
            ),
            {"game_id": older.game_id},
        ).scalar_one()
        session.rollback()
    assert superseded == 1
    [entry] = _entries(factory, newer)
    assert entry.blocking_reason is RevertBlockingReason.SEQUENCE_OWNERSHIP
    _refused(factory, newer, entry, RevertBlockingReason.SEQUENCE_OWNERSHIP)


def test_cells_re_owned_from_the_previous_owner_refuse_the_revert(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    factory, older, newer, artifact_root = _ownership_game(database, tmp_path, "task0945-cells")
    _resolve(factory, artifact_root, newer, 0, key=uuid4())
    [entry] = _entries(factory, newer)
    with game_storage_scope(newer.game_id), factory.begin() as session:
        re_owned = session.execute(
            text(
                "SELECT count(*) FROM game_data_v2.image_symbol_review_cells c "
                "JOIN game_data_v2.board_render_manifests m ON m.game_id = c.game_id "
                "AND m.recognized_board_id = :board_id AND m.geometry_revision = :revision "
                "WHERE c.game_id = :game_id AND c.review_item_id = :item_id "
                "AND c.created_at < m.created_at"
            ),
            {
                "game_id": newer.game_id,
                "board_id": entry.recognized_board_id,
                "revision": entry.geometry_revision,
                "item_id": entry.review_item_id,
            },
        ).scalar_one()
        # Isolate the cell signal: without the supersession event the cells
        # taken over from the older owner alone refuse the revert.
        session.execute(
            text(
                "DELETE FROM game_data_v2.image_review_resolution_events "
                "WHERE game_id = :game_id AND action = 'superseded'"
            ),
            {"game_id": newer.game_id},
        )
    assert re_owned == 15
    [entry] = _entries(factory, newer)
    assert entry.blocking_reason is RevertBlockingReason.SEQUENCE_OWNERSHIP
    _refused(factory, newer, entry, RevertBlockingReason.SEQUENCE_OWNERSHIP)


def test_a_pinned_board_refuses_the_revert(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    factory, seed, artifact_root = _seeded(database, tmp_path, "task0945-pinned", 2)
    _resolve(factory, artifact_root, seed, 0, key=uuid4())
    [entry] = _entries(factory, seed)
    with game_storage_scope(seed.game_id), factory.begin() as session:
        # A stored prediction revision pins the board's crops.
        session.execute(
            text(
                """INSERT INTO game_data_v2.image_symbol_prediction_revisions (
                    id, game_id, review_item_id, recognized_board_id, source_job_id,
                    model_version, model_checksum_sha256, crop_manifest_checksum_sha256,
                    predictions, created_at)
                VALUES (:id, :game_id, :item_id, :board_id, :job_id, 'task-0945-model',
                    :model, :crops, '{}'::jsonb, now())"""
            ),
            {
                "id": uuid4(),
                "game_id": seed.game_id,
                "item_id": entry.review_item_id,
                "board_id": entry.recognized_board_id,
                "job_id": seed.import_job_id,
                "model": _sha("task-0945-model"),
                "crops": _sha("task-0945-crops"),
            },
        )
    [entry] = _entries(factory, seed)
    assert entry.blocking_reason is RevertBlockingReason.PINNED
    _refused(factory, seed, entry, RevertBlockingReason.PINNED)


def test_a_board_revision_correction_of_a_withheld_board_is_reverted(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    """Case A on a slot board without cells (TASK-0946; was NOT_SUPPORTED in 0945)."""

    factory, seed, artifact_root = _seeded(database, tmp_path, "task0945-case-a", 2)
    _resolve(factory, artifact_root, seed, 0, key=uuid4())
    [slot] = _entries(factory, seed)
    before = _world(factory, seed.game_id)
    base, query = _review_path(seed, slot.review_item_id)
    app = _app(database, artifact_root)
    try:
        with TestClient(app) as client:
            saved = client.post(
                f"{base}/geometry-revisions",
                params=query,
                json={
                    "corners": _SHIFTED_CORNERS,
                    "expectedGeometryRevision": slot.geometry_revision,
                    "expectedResolutionRevision": slot.resolution_revision,
                    "idempotencyKey": str(uuid4()),
                    "correctedBy": _ACTOR,
                },
            )
    finally:
        app.state.database_engine.dispose()
    assert saved.status_code == 200, saved.text
    board_revision, slot = _entries(factory, seed)
    assert board_revision.kind is GeometryCorrectionKind.BOARD_REVISION
    assert board_revision.geometry_revision == slot.geometry_revision + 1
    assert board_revision.revertable, board_revision.blocking_reason
    assert slot.kind is GeometryCorrectionKind.PENDING_SLOT
    assert slot.blocking_reason is RevertBlockingReason.NOT_LATEST
    _refused(factory, seed, slot, RevertBlockingReason.NOT_LATEST)

    result = _revert(
        factory,
        seed,
        board_revision,
        key=uuid4(),
        verifier=VirtualRestoredRenderVerifier(artifact_root),
    )
    assert result.kind is GeometryCorrectionKind.BOARD_REVISION
    assert result.restored_geometry_revision == board_revision.geometry_revision + 1
    assert result.restored_cell_decision_count == 0
    after = _world(factory, seed.game_id)
    assert after["image_symbol_review_cells"] == []
    [board_before] = before["recognized_boards"]
    [board_after] = after["recognized_boards"]
    # The slot save's geometry and approval come back on revision N + 1.
    moved = ("geometry_revision", "approved_geometry_revision")
    assert {k: v for k, v in board_after.items() if k not in moved} == {
        k: v for k, v in board_before.items() if k not in moved
    }
    assert board_after["approved_geometry_revision"] == board_after["geometry_revision"]
    assert len(after["image_geometry_correction_reverts"]) == 1
    # The slot correction stays behind the board's newer revisions.
    _refused(factory, seed, slot, RevertBlockingReason.NOT_LATEST)


def _pin_in_cohort(factory: sessionmaker[Session], seed: _Seed, board_id: UUID) -> None:
    """A verified training cohort with the board and one of its cells (raw seed)."""

    with game_storage_scope(seed.game_id), factory.begin() as session:
        cell = session.execute(
            text(
                "SELECT * FROM game_data_v2.image_symbol_review_cells "
                "WHERE game_id = :game_id AND recognized_board_id = :board_id "
                "ORDER BY cell_index LIMIT 1"
            ),
            {"game_id": seed.game_id, "board_id": board_id},
        ).one()
        board = session.get(RecognizedBoardModel, board_id)
        assert board is not None
        cohort_id = uuid4()
        session.execute(
            text(
                """INSERT INTO game_data_v2.verified_training_cohorts
                (id, game_id, iteration_number, manifest_schema_version, dataset_kind,
                 manifest_checksum_sha256, idempotency_key, command_sha256,
                 resolved_layout_count, cell_sample_count, source_image_count,
                 pending_item_count, rejected_item_count, incomplete_item_count,
                 artifact_relative_path, created_by)
                VALUES (:id, :game_id, 1, 1, 'verified-training-cohort-v1', :sha, :key, :sha,
                        1, 1, 1, 0, 0, 0, 'task-0945/cohort.json', 'task-0945')"""
            ),
            {"id": cohort_id, "game_id": seed.game_id, "sha": _sha("cohort"), "key": uuid4()},
        )
        session.execute(
            text(
                """INSERT INTO game_data_v2.verified_training_cohort_items
                (id, game_id, cohort_id, item_order, review_item_id, recognized_board_id,
                 source_image_id, import_job_id, sequence_number, decision_status,
                 resolution_revision, geometry_revision, source_checksum_sha256,
                 board_checksum_sha256, pipeline_fingerprint, item_checksum_sha256,
                 board_manifest)
                VALUES (:id, :game_id, :cohort_id, 0, :item_id, :board_id, :source_id,
                        :job_id, :sequence, 'accepted', 1, :geometry_revision, :sha, :sha,
                        :sha, :sha, CAST(:manifest AS jsonb))"""
            ),
            {
                "id": uuid4(),
                "game_id": seed.game_id,
                "cohort_id": cohort_id,
                "item_id": cell.review_item_id,
                "board_id": board_id,
                "source_id": board.source_image_id,
                "job_id": seed.import_job_id,
                "sequence": board.sequence_number,
                "geometry_revision": board.geometry_revision,
                "sha": _sha("cohort-item"),
                "manifest": json.dumps({"cells": [{"cellIndex": i} for i in range(15)]}),
            },
        )
        session.execute(
            text(
                """INSERT INTO game_data_v2.verified_training_cohort_cells
                (id, game_id, cohort_id, sample_order, cell_review_id, review_item_id,
                 recognized_board_id, source_image_id, sequence_number, cell_index,
                 symbol_code, asset_mode, source_geometry_revision_id, logical_cell_key,
                 render_spec, render_spec_checksum_sha256, rendered_pixel_checksum_sha256,
                 extractor_version, crop_checksum_sha256, sample_checksum_sha256,
                 cell_manifest)
                VALUES (:id, :game_id, :cohort_id, 0, :cell_id, :item_id, :board_id,
                        :source_id, :sequence, :cell_index, 'CYTRYNA', 'virtual_source',
                        :source_revision_id, :logical_key, '{}'::jsonb, :spec, :pixels,
                        :extractor, :crop, :sample, '{}'::jsonb)"""
            ),
            {
                "id": uuid4(),
                "game_id": seed.game_id,
                "cohort_id": cohort_id,
                "cell_id": cell.id,
                "item_id": cell.review_item_id,
                "board_id": board_id,
                "source_id": board.source_image_id,
                "sequence": cell.sequence_number,
                "cell_index": cell.cell_index,
                "source_revision_id": cell.source_geometry_revision_id,
                "logical_key": cell.logical_cell_key,
                "spec": cell.render_spec_checksum_sha256,
                "pixels": cell.rendered_pixel_checksum_sha256,
                "extractor": cell.extractor_version,
                "crop": cell.crop_checksum_sha256,
                "sample": _sha("cohort-sample"),
            },
        )


def _cohort_rows(factory: sessionmaker[Session], game_id: UUID) -> list[Any]:
    with game_storage_scope(game_id), factory() as session:
        rows = [
            session.execute(
                text(f"SELECT to_jsonb(t)::text FROM game_data_v2.{table} t ORDER BY t.id")
            )
            .scalars()
            .all()
            for table in (
                "verified_training_cohorts",
                "verified_training_cohort_items",
                "verified_training_cohort_cells",
            )
        ]
        session.rollback()
    return rows


def test_a_corrected_board_in_a_training_cohort_refuses_the_revert(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    factory, seed, artifact_root = _excepted_game(database, tmp_path, "task0945-cohort")
    _resolve(factory, artifact_root, seed, 0, key=uuid4())
    [entry] = _entries(factory, seed)
    assert entry.revertable
    _pin_in_cohort(factory, seed, entry.recognized_board_id)
    cohort = _cohort_rows(factory, seed.game_id)
    assert [len(rows) for rows in cohort] == [1, 1, 1]
    [entry] = _entries(factory, seed)
    assert entry.blocking_reason is RevertBlockingReason.PINNED
    _refused(factory, seed, entry, RevertBlockingReason.PINNED)
    assert _cohort_rows(factory, seed.game_id) == cohort


def test_a_repointed_neighbour_in_a_training_cohort_refuses_the_revert(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    factory, seed, artifact_root = _excepted_game(database, tmp_path, "task0945-cohort-n")
    _resolve(factory, artifact_root, seed, 0, key=uuid4())
    with game_storage_scope(seed.game_id), factory() as session:
        neighbour_id = session.scalar(
            select(RecognizedBoardModel.id).where(RecognizedBoardModel.position_index == 1)
        )
        session.rollback()
    assert neighbour_id is not None
    _pin_in_cohort(factory, seed, neighbour_id)
    cohort = _cohort_rows(factory, seed.game_id)
    [entry] = _entries(factory, seed)
    # A pinned neighbour cannot move back to the previous source revision.
    assert entry.blocking_reason is RevertBlockingReason.SHARED_SOURCE_REVISION
    _refused(factory, seed, entry, RevertBlockingReason.SHARED_SOURCE_REVISION)
    assert _cohort_rows(factory, seed.game_id) == cohort
