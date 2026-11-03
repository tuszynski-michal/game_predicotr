"""Owned PostgreSQL: working undo keeps its proof, reservations and frozen receipt."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from game_predictor_api.domain.board_cell_geometry_pending import BoardRejectionReason
from game_predictor_api.domain.image_reviews import (
    ImageReviewConflictError,
    ImageReviewGridIssueView,
    ImageReviewView,
)
from game_predictor_api.domain.source_replacement import SourceReplacementError
from game_predictor_api.domain.symbol_readability import GAME_ID
from game_predictor_api.storage.board_cell_geometry_pending_repository import (
    SqlAlchemyBoardCellGeometryPendingRepository,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.geometry_correction_revert_models import (
    ImageBoardGeometryPendingEventModel,
)
from game_predictor_api.storage.geometry_correction_revert_repository import (
    SqlAlchemyGeometryCorrectionRevertRepository,
)
from game_predictor_api.storage.image_review_repository import (
    SqlAlchemyOperationalImageReviewRepository,
)
from game_predictor_api.storage.models import ImageBoardGeometryPendingModel
from sqlalchemy import text
from test_source_replacement_manual_postgres import (
    prepare_working,
    resolve_slot,
    verify_restore,
)
from test_source_replacement_postgres import database as owned_database
from test_source_replacement_postgres import pytestmark as pytestmark


@pytest.fixture
def database():
    # Reuse the name/OID/capability receipt guards, with a fresh DB per scenario.
    yield from owned_database.__wrapped__()


def reject(session, seed, *, index=0, key=None):
    return SqlAlchemyBoardCellGeometryPendingRepository(session).reject(
        pending_id=seed.pending_ids[index],
        game_id=GAME_ID,
        import_job_id=seed.import_job_id,
        idempotency_key=key or uuid4(),
        expected_geometry_revision=0,
        reason=BoardRejectionReason.BLURRED,
        note=None,
        rejected_by="working-reviewer",
        rejected_at=datetime.now(UTC),
    )


def undo(session, seed, rejection, *, key=None, revision=0):
    return SqlAlchemyGeometryCorrectionRevertRepository(session).revert(
        game_id=GAME_ID,
        import_job_id=seed.import_job_id,
        board_geometry_revision_id=rejection,
        idempotency_key=key or uuid4(),
        expected_geometry_revision=revision,
        expected_resolution_revision=revision,
        actor="working-reviewer",
        reverted_at=datetime.now(UTC),
    )


def state(session, seed):
    """Include prior reasons/events, ownership and all revision-bearing proof."""
    return {
        table: session.execute(
            text(f"SELECT to_jsonb(t) FROM {table} t WHERE {predicate} ORDER BY id"),
            {"source": seed.source_image_id, "job": seed.import_job_id},
        )
        .scalars()
        .all()
        for table, predicate in (
            ("image_board_geometry_pending", "source_image_id=:source"),
            ("image_board_geometry_pending_events", "import_job_id=:job"),
            ("source_images", "id=:source"),
            ("image_review_items", "import_job_id=:job"),
        )
    }


def assert_reserved_only(session, seed, entry):
    rows = session.execute(
        text(
            "SELECT state,bound_review_id FROM source_replacement_slots "
            "WHERE entry_id=:entry ORDER BY sequence_number"
        ),
        {"entry": entry},
    ).all()
    assert rows == [("reserved", None), ("reserved", None)]
    assert (
        session.scalar(
            text("SELECT count(*) FROM image_sequence_canonical WHERE source_image_id=:source"),
            {"source": seed.source_image_id},
        )
        == 0
    )
    page = SqlAlchemyOperationalImageReviewRepository(session).list_items(
        game_id=GAME_ID,
        import_job_id=seed.import_job_id,
        view=ImageReviewView.PENDING,
        grid_issue_view=ImageReviewGridIssueView.ALL,
        after_key=None,
        before_key=None,
        expected_queue_version=None,
        sequence_number=None,
        resume_at_first_pending=False,
        limit=10,
    )
    assert not page.items


def historical_rejection(session, template, *, source=None, job=None, position=None, sequence=None):
    """Persist an interrupted old attempt; no public API can create an extra reserved slot."""
    values = {
        column.key: getattr(template, column.key)
        for column in ImageBoardGeometryPendingModel.__table__.columns
        if column.key != "id"
    }
    values.update(
        source_image_id=source or template.source_image_id,
        import_job_id=job or template.import_job_id,
        position_index=template.position_index if position is None else position,
        sequence_number=template.sequence_number if sequence is None else sequence,
        status="rejected",
        rejection_reason="blurred",
        rejection_note=None,
        rejected_by="historical-reviewer",
        rejected_at=datetime.now(UTC),
        recognized_board_id=None,
        review_item_id=None,
        resolved_geometry_revision=None,
        resolved_at=None,
        superseded_at=None,
    )
    pending = ImageBoardGeometryPendingModel(**values)
    session.add(pending)
    session.flush()
    event = ImageBoardGeometryPendingEventModel(
        id=uuid4(),
        game_id=GAME_ID,
        import_job_id=pending.import_job_id,
        pending_geometry_id=pending.id,
        rejection_revision=1,
        action="rejected",
        idempotency_key=uuid4(),
        command_sha256="d" * 64,
        reason="blurred",
        actor="historical-reviewer",
        created_at=pending.rejected_at,
    )
    session.add(event)
    session.flush()
    return pending.id, event.id


def test_working_reject_undo_restart_and_restored_orphan_stays_closed(database, tmp_path):
    factory = create_session_factory(database)
    seed, batch, entry = prepare_working(factory, tmp_path)
    reject_key, undo_key = uuid4(), uuid4()
    with game_storage_scope(GAME_ID), factory() as session:
        rejected, rejection_id, created = reject(session, seed, key=reject_key)
        assert created and rejected.status.value == "rejected"
        prior = state(session, seed)["image_board_geometry_pending_events"]
        assert_reserved_only(session, seed, entry)
        session.commit()
    with game_storage_scope(GAME_ID), factory() as session:
        receipt = undo(session, seed, rejection_id, key=undo_key)
        assert receipt.created
        pending = session.get(ImageBoardGeometryPendingModel, seed.pending_ids[0])
        assert pending.status == "pending" and pending.rejection_reason is None
        assert (
            pending.expected_geometry_revision == pending.expected_review_resolution_revision == 0
        )
        assert_reserved_only(session, seed, entry)
        session.commit()
    with game_storage_scope(GAME_ID), factory() as session:
        assert undo(session, seed, rejection_id, key=undo_key, revision=999) == replace(
            receipt, created=False
        )
        assert reject(session, seed, key=reject_key) == (rejected, rejection_id, False)
        _, second_rejection, _ = reject(session, seed)
        before = state(session, seed)
        assert undo(session, seed, rejection_id, key=undo_key) == replace(receipt, created=False)
        assert state(session, seed) == before  # old receipt cannot undo the newer rejection
        with pytest.raises(ImageReviewConflictError) as conflict:
            undo(session, seed, second_rejection, key=undo_key)
        assert conflict.value.code == "GEOMETRY_REVERT_IDEMPOTENCY_CONFLICT"
        undo(session, seed, second_rejection)
        assert_reserved_only(session, seed, entry)
        session.commit()
    with game_storage_scope(GAME_ID), factory() as session:
        resolve_slot(session, tmp_path, seed, 0, uuid4())
        assert_reserved_only(session, seed, entry)
        resolve_slot(session, tmp_path, seed, 1, uuid4())
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM source_replacement_slots "
                    "WHERE entry_id=:entry AND state='pending_bound'"
                ),
                {"entry": entry},
            )
            == 2
        )
        session.commit()
    orphan_ids = []
    orphan_snapshots = []

    def before_restore(session):
        # Persist the historical rejected attempt after canonical acceptance,
        # exactly at the closure boundary, without altering the current boards.
        pending_id, event_id = historical_rejection(
            session,
            session.get(ImageBoardGeometryPendingModel, seed.pending_ids[0]),
            position=3,
            sequence=2003,
        )
        orphan_ids.extend((pending_id, event_id))
        orphan_snapshots.append(
            session.scalar(
                text("SELECT to_jsonb(p) FROM image_board_geometry_pending p WHERE id=:id"),
                {"id": pending_id},
            )
        )

    verify_restore(factory, seed, batch, entry, before_restore=before_restore)
    orphan_id, orphan_event = orphan_ids
    orphan_prior = orphan_snapshots[0]
    # New session reconstructs the original immutable receipt after completeness changed.
    with game_storage_scope(GAME_ID), factory() as session:
        before = state(session, seed)
        assert undo(session, seed, rejection_id, key=undo_key) == replace(receipt, created=False)
        assert state(session, seed) == before
        with pytest.raises(SourceReplacementError) as closed:
            undo(session, seed, orphan_event, revision=-1)
        assert closed.value.code == "SOURCE_REPLACEMENT_ADMISSION_CLOSED"
        assert state(session, seed) == before
        orphan = session.get(ImageBoardGeometryPendingModel, orphan_id)
        assert orphan.status == "superseded" and orphan.rejection_reason == "blurred"
        restoration = session.scalar(
            text("SELECT document->'restoration' FROM source_replacement_entries WHERE id=:entry"),
            {"entry": entry},
        )
        assert {"prior": orphan_prior} in restoration["orphanGeometry"]
        assert (
            session.scalar(
                text("SELECT count(*) FROM image_sequence_canonical WHERE source_image_id=:source"),
                {"source": seed.source_image_id},
            )
            == 2
        )
        assert prior[0] in state(session, seed)["image_board_geometry_pending_events"]


def test_foreign_working_proof_and_retired_original_refuse_before_cas(database, tmp_path):
    factory = create_session_factory(database)
    seed, batch, entry = prepare_working(factory, tmp_path)
    with game_storage_scope(GAME_ID), factory() as session:
        _, rejection_id, _ = reject(session, seed)
        session.commit()
    invalid = {
        "gameId": str(uuid4()),
        "batchId": str(uuid4()),
        "entryId": str(uuid4()),
        "sourceId": str(uuid4()),
        "importJobId": str(uuid4()),
        "sourceSha256": "f" * 64,
        "entryRevision": 999,
        "sequenceNumbers": [2000],
        "schemaVersion": "foreign",
    }
    for field, value in invalid.items():
        with game_storage_scope(GAME_ID), factory() as session:
            document = session.scalar(
                text("SELECT document FROM source_replacement_entries WHERE id=:entry"),
                {"entry": entry},
            )
            document["replacementAdmission"][field] = value
            session.execute(
                text(
                    "UPDATE source_replacement_entries SET document=CAST(:doc AS jsonb) "
                    "WHERE id=:entry"
                ),
                {"entry": entry, "doc": json.dumps(document)},
            )
            before = state(session, seed)
            with pytest.raises(SourceReplacementError) as denied:
                undo(session, seed, rejection_id, revision=-1)
            assert denied.value.code == "SOURCE_REPLACEMENT_RESERVED", field
            assert state(session, seed) == before
            assert_reserved_only(session, seed, entry)
            session.rollback()
    with game_storage_scope(GAME_ID), factory() as session:
        # A replacement-command key cannot be stolen by a geometry undo.
        foreign_key = uuid4()
        session.execute(
            text(
                "INSERT INTO source_replacement_commands "
                "(game_id,idempotency_key,command_sha256,batch_id,response) "
                "VALUES(:game,:key,repeat('e',64),:batch,'{\"action\":\"restore\"}')"
            ),
            {"game": GAME_ID, "key": foreign_key, "batch": batch},
        )
        before = state(session, seed)
        with pytest.raises(ImageReviewConflictError) as conflict:
            undo(session, seed, rejection_id, key=foreign_key)
        assert conflict.value.code == "GEOMETRY_REVERT_IDEMPOTENCY_CONFLICT"
        assert state(session, seed) == before
        # Historical original with a rejected orphan still fails RETIRED first.
        old = session.execute(
            text(
                "SELECT s.id,s.import_job_id FROM source_replacement_entries e "
                "JOIN source_images s ON s.id=e.source_id WHERE e.id=:entry"
            ),
            {"entry": entry},
        ).one()
        _, retired_event = historical_rejection(
            session,
            session.get(ImageBoardGeometryPendingModel, seed.pending_ids[0]),
            source=old.id,
            job=old.import_job_id,
            position=4,
            sequence=1904,
        )
        original = replace(seed, source_image_id=old.id, import_job_id=old.import_job_id)
        before = state(session, original)
        with pytest.raises(SourceReplacementError) as retired:
            undo(session, original, retired_event, revision=-1)
        assert retired.value.code == "SOURCE_REPLACEMENT_RETIRED"
        assert state(session, original) == before
