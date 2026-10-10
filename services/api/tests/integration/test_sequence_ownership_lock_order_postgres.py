"""TASK-0971 (audit round 4): the global lock order of takeovers and their neighbours.

Runs on a dedicated ``*_test`` database only. P0-6: a direct resolution must
not wait for the job row the worker of the same import holds. P0-7: a takeover
that cuts several candidate images must not deadlock with the revert of a
board rejection. The lock-order probe checks the main entry points.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from _lock_order_probe import lock_order_probe
from game_predictor_api.domain.board_cell_geometry_pending import BoardRejectionReason
from game_predictor_api.domain.geometry_correction_reverts import (
    GeometryCorrectionKind,
    RejectionTarget,
)
from game_predictor_api.domain.image_reviews import ImageReviewAction
from game_predictor_api.storage import pending_sequence_ownership
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_review_repository import (
    SqlAlchemyOperationalImageReviewRepository,
)
from game_predictor_api.storage.models import ImageImportJobFileModel
from sqlalchemy import text, update
from sqlalchemy.orm import Session, sessionmaker
from test_image_geometry_completeness_gate import _import, _seeded, _state
from test_pending_slot_rejection_postgres import (
    _entries,
    _items,
    _reject_slot,
    _resolve_board,
    _revert,
)
from test_replacement_photo_takeover_postgres import _items_of, _mutations, _owner_ids
from test_virtual_deferred_resolution_postgres import (
    _Database,
    _Seed,
    _seed,
    database,  # noqa: F401  (pytest fixture)
    pytestmark,  # noqa: F401  (PostgreSQL opt-in)
)


def _move_to_job(factory: sessionmaker[Session], photo: _Seed, job_id: Any) -> _Seed:
    """Re-home a seeded photo into another import job of the game (a next file)."""

    with game_storage_scope(photo.game_id), factory.begin() as session:
        parameters = {"game_id": photo.game_id, "old": photo.import_job_id, "new": job_id}
        for statement in (
            "UPDATE game_data_v2.source_images SET import_job_id = :new "
            "WHERE game_id = :game_id AND import_job_id = :old",
            "UPDATE game_data_v2.image_board_geometry_pending SET import_job_id = :new "
            "WHERE game_id = :game_id AND import_job_id = :old",
        ):
            session.execute(text(statement), parameters)
        session.execute(
            update(ImageImportJobFileModel)
            .where(ImageImportJobFileModel.job_id == photo.import_job_id)
            .values(job_id=job_id, order_index=1)
        )
    return _Seed(
        photo.game_id, job_id, photo.source_image_id, photo.pending_ids, photo.manifest_checksums
    )


def test_a_decision_and_the_projection_of_the_next_photo_of_its_job_never_deadlock(
    database: _Database,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0-6: the worker holds its job's lease row, then waits for the ownership lock.

    The direct resolution holds the ownership lock and then locks its item; it
    must never wait for that job row (``FOR UPDATE OF`` without ``jobs``).
    """

    factory, first, artifact_root = _seeded(database, tmp_path, "task0950-p06", 1)
    _import(factory, first, "task0950-p06", [0])
    second = _seed(
        factory,
        first.game_id,
        artifact_root,
        label="task0950-p06-next",
        slot_count=1,
        sequence_base=200,
    )
    second = _move_to_job(factory, second, first.import_job_id)
    item = _items(factory, first)[0]

    holds_ownership = threading.Event()
    original = SqlAlchemyOperationalImageReviewRepository._acquire_review_sequence_locks

    def slow_locks(self: Any, **kwargs: Any) -> Any:
        result = original(self, **kwargs)
        # Ownership and sequence are held; let the worker take its job row.
        holds_ownership.set()
        time.sleep(1.5)
        return result

    monkeypatch.setattr(
        SqlAlchemyOperationalImageReviewRepository, "_acquire_review_sequence_locks", slow_locks
    )
    errors: list[BaseException] = []

    def decide() -> None:
        try:
            _resolve_board(factory, first, item, action=ImageReviewAction.ACCEPTED)
        except BaseException as error:  # noqa: BLE001 - reported by the test
            errors.append(error)

    def project_next_photo() -> None:
        try:
            assert holds_ownership.wait(timeout=60)
            _import(factory, second, "task0950-p06-next", [0])
        except BaseException as error:  # noqa: BLE001 - reported by the test
            errors.append(error)

    threads = [threading.Thread(target=decide), threading.Thread(target=project_next_photo)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert not any(thread.is_alive() for thread in threads)
    assert errors == []
    assert _items_of(factory, first)[100]["status"] == "accepted"
    assert _items_of(factory, second)[200]["status"] == "pending"


def test_a_multi_image_takeover_and_a_board_rejection_revert_never_deadlock(
    database: _Database,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0-7: C and A reject sequence 100, A also rejected its board 102.

    The import of B takes 100 over and recomputes (and cuts) C and A; the
    revert of A's board rejection locks A's source and the counters state.
    """

    factory, other, artifact_root = _seeded(database, tmp_path, "task0950-p07-c", 2)
    _import(factory, other, "task0950-p07-c", [1])
    _reject_slot(factory, artifact_root, other, 0, reason=BoardRejectionReason.CROPPED)
    game_id = other.game_id
    old = _seed(
        factory, game_id, artifact_root, label="task0950-p07-aa", slot_count=3, sequence_base=100
    )
    _import(factory, old, "task0950-p07-aa", [2])
    _reject_slot(factory, artifact_root, old, 0, reason=BoardRejectionReason.CROPPED)
    board = _items(factory, old)[2]
    _resolve_board(factory, old, board, action=ImageReviewAction.REJECTED, reason="cropped")
    [rejection] = [
        entry
        for entry in _entries(factory, old)
        if entry.kind is GeometryCorrectionKind.REJECTION
        and entry.rejection_target is RejectionTarget.REVIEW_ITEM
    ]
    assert rejection.revertable, rejection.blocking_reason
    assert _state(factory, game_id, other.source_image_id)["status"] == "geometry_incomplete"

    candidates_locked = threading.Event()
    original = pending_sequence_ownership.recompute_source_images

    def slow_recompute(*args: Any, **kwargs: Any) -> Any:
        candidates_locked.set()
        time.sleep(1.5)
        return original(*args, **kwargs)

    monkeypatch.setattr(pending_sequence_ownership, "recompute_source_images", slow_recompute)
    new = _seed(
        factory, game_id, artifact_root, label="task0950-p07-bbb", slot_count=1, sequence_base=100
    )
    errors: list[BaseException] = []

    def take_over() -> None:
        try:
            _import(factory, new, "task0950-p07-bbb", [0])
        except BaseException as error:  # noqa: BLE001 - reported by the test
            errors.append(error)

    def revert_rejection() -> None:
        try:
            assert candidates_locked.wait(timeout=60)
            _revert(factory, old, rejection, key=uuid4())
        except BaseException as error:  # noqa: BLE001 - reported by the test
            errors.append(error)

    threads = [threading.Thread(target=take_over), threading.Thread(target=revert_rejection)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert not any(thread.is_alive() for thread in threads)
    assert errors == []
    assert _owner_ids(factory, game_id, 100) == [_items_of(factory, new)[100]["item"]]
    assert _items_of(factory, old)[102]["status"] == "pending"
    # C has 100 covered by B and its own 101: admitted and cut.
    cut = _state(factory, game_id, other.source_image_id)
    assert cut["status"] == "geometry_complete" and cut["cells"] == 15


def test_the_main_entry_points_follow_the_global_lock_order(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    """Takeover projection, slot rejection, cell decision, resolution and revert."""

    factory, old, artifact_root = _seeded(database, tmp_path, "task0950-order", 3)
    game_id = old.game_id
    engine = database.engine
    sequences = range(100, 104)
    with lock_order_probe(engine, game_id=game_id, sequence_numbers=sequences) as setup:
        _import(factory, old, "task0950-order", [1, 2])
        _reject_slot(factory, artifact_root, old, 0, reason=BoardRejectionReason.CROPPED)
    other = _seed(
        factory, game_id, artifact_root, label="task0950-order-bb", slot_count=1, sequence_base=100
    )
    with lock_order_probe(engine, game_id=game_id, sequence_numbers=sequences) as takeover:
        _import(factory, other, "task0950-order-bb", [0])
    items = _items(factory, old)
    from test_pending_slot_rejection_postgres import _rebuild_symbol_counts

    _rebuild_symbol_counts(factory, old)
    cell_id, revision, geometry, sample, checksum = _first_cell(factory, game_id, 101)
    with lock_order_probe(engine, game_id=game_id, sequence_numbers=sequences) as decisions:
        with game_storage_scope(game_id), factory.begin() as session:
            _mutations(session).mark_unreadable(
                game_id=game_id,
                cell_review_id=cell_id,
                expected_revision=revision,
                expected_geometry_revision=geometry,
                expected_crop_sample_id=sample,
                expected_crop_checksum_sha256=checksum,
                actor="task-0971-operator",
            )
        _resolve_board(factory, old, items[2], action=ImageReviewAction.REJECTED, reason="cropped")
        [rejection] = [
            entry
            for entry in _entries(factory, old)
            if entry.rejection_target is RejectionTarget.REVIEW_ITEM
        ]
        _revert(factory, old, rejection, key=uuid4())
    for log in (setup, takeover, decisions):
        assert log.categories(), "the probe saw no lock"
        assert log.violations() == []
    # The takeover locked the ownership before any sequence and source.
    assert any(
        locks.index("ownership") < locks.index("source")
        for locks in takeover.categories()
        if "ownership" in locks and "source" in locks
    )


def _first_cell(
    factory: sessionmaker[Session], game_id: Any, sequence: int
) -> tuple[Any, int, int, str, str]:
    with game_storage_scope(game_id), factory() as session:
        row = session.execute(
            text(
                "SELECT id, revision, geometry_revision, crop_sample_id, crop_checksum_sha256 "
                "FROM game_data_v2.image_symbol_review_cells "
                "WHERE game_id = :game_id AND sequence_number = :sequence "
                "ORDER BY cell_index LIMIT 1"
            ),
            {"game_id": game_id, "sequence": sequence},
        ).one()
        session.rollback()
    return row[0], int(row[1]), int(row[2]), str(row[3]), str(row[4])
