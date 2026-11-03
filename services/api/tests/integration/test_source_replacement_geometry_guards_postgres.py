# ruff: noqa: F811
"""Real retired/provisional geometry fences across fresh PostgreSQL sessions."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from game_predictor_api.domain.board_cell_geometry_pending import BoardRejectionReason
from game_predictor_api.domain.page_geometry_overrides import ImagePageGeometryOverride
from game_predictor_api.domain.source_replacement import SourceReplacementError
from game_predictor_api.domain.symbol_readability import GAME_ID
from game_predictor_api.storage.board_cell_geometry_pending_repository import (
    SqlAlchemyBoardCellGeometryPendingRepository,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_geometry_approvals import (
    SqlAlchemyGridGeometryApprovalRepository,
)
from game_predictor_api.storage.grid_geometry_proposals import (
    SqlAlchemyGridGeometryProposalRepository,
)
from game_predictor_api.storage.image_geometry_v2_repository import (
    SqlAlchemyImageSourceGeometryRepository,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import ImageBoardGeometryPendingModel, RecognizedBoardModel
from game_predictor_api.storage.page_geometry_override_repository import (
    SqlAlchemyPageGeometryOverrideRepository,
)
from game_predictor_api.storage.virtual_grid_geometry_repository import (
    SqlAlchemyVirtualGridGeometryRepository,
)
from game_predictor_worker.images.orchestration_store import SqlAlchemyImageBatchStore
from sqlalchemy import text
from test_image_batch_store import PIPELINE, _add_review_projection_source, _image_job
from test_source_replacement_postgres import database, pytestmark  # noqa: F401


def seed_source(factory, sequence):
    now, sha = datetime.now(UTC), uuid4().hex * 2
    with game_storage_scope(GAME_ID), factory() as session:
        job = SqlAlchemyJobRepository(session).add_job(_image_job(GAME_ID, PIPELINE, now))
        session.commit()
        job_id = job.id
    execution = SqlAlchemyImageBatchStore(factory).register_file(
        job_id,
        source_checksum_sha256=sha,
        pipeline_fingerprint=PIPELINE,
        source_relative_path=f"fixture-{sha}.jpg",
        order_index=0,
        registered_at=now,
    )
    with game_storage_scope(GAME_ID), factory() as session:
        review, board_id = _add_review_projection_source(
            session,
            job_id=job_id,
            file_execution_key=execution.file_execution_key,
            source_checksum=sha,
            source_name=f"fixture-{sha}.jpg",
            position_index=0,
            sequence_number=sequence,
            status="pending",
            created_at=now,
        )
        board = session.get(RecognizedBoardModel, board_id)
        source = board.source_image_id
        pending = ImageBoardGeometryPendingModel(
            game_id=GAME_ID,
            import_job_id=job_id,
            source_image_id=source,
            sequence_number=sequence + 1,
            position_index=1,
            source_checksum_sha256=sha,
            source_relative_path=f"fixture-{sha}.jpg",
            status="pending",
            reason_code="incomplete_lattice",
            processing_manifest_checksum_sha256=sha,
            processing_manifest_relative_path="fixture.json",
            pipeline_fingerprint_sha256=sha,
            expected_geometry_revision=0,
            expected_review_resolution_revision=0,
        )
        session.add(pending)
        page = ImagePageGeometryOverride(
            id=uuid4(),
            game_id=GAME_ID,
            source_checksum_sha256=sha,
            image_width=100,
            image_height=100,
            final_quads=((dict(x=0, y=0), dict(x=99, y=0), dict(x=99, y=99), dict(x=0, y=99)),),
            revision=1,
            actor="fixture",
            decision_checksum_sha256=sha,
            created_at=now,
        )
        SqlAlchemyPageGeometryOverrideRepository(session).append(page)
        session.flush()
        pending_id = pending.id
        session.execute(
            text("UPDATE public.jobs SET status='waiting_for_review' WHERE id=:id"), {"id": job_id}
        )
        session.commit()
    return SimpleNamespace(
        job=job_id,
        source=source,
        review=review,
        board=board_id,
        pending=pending_id,
        sha=sha,
        page=page,
        sequence=sequence,
    )


def replacement(session, old, *, restored=False, new=None):
    batch, entry = uuid4(), uuid4()
    phase = "restored" if restored else "importing"
    document = {}
    if new is not None:
        document = {
            "sequence_numbers": [new.sequence + 1],
            "replacementAdmission": {
                "schemaVersion": "source-replacement-admission-v1",
                "gameId": str(GAME_ID),
                "batchId": str(batch),
                "entryId": str(entry),
                "sourceId": str(new.source),
                "importJobId": str(new.job),
                "sourceSha256": new.sha,
                "sequenceNumbers": [new.sequence + 1],
                "entryRevision": 1,
            },
        }
    params = dict(
        game=GAME_ID,
        batch=batch,
        entry=entry,
        old=old.source,
        sha=old.sha,
        phase=phase,
        document=json.dumps(document),
    )
    session.execute(
        text("""INSERT INTO source_replacement_batches
      (game_id,id,revision,status,preview_token,document)
      VALUES(:game,:batch,1,:phase,repeat('a',64),'{}')"""),
        params,
    )
    session.execute(
        text("""INSERT INTO source_replacement_entries
      (game_id,id,batch_id,source_id,source_sha256,phase,document)
      VALUES(:game,:entry,:batch,:old,:sha,:phase,CAST(:document AS jsonb))"""),
        params,
    )
    session.execute(
        text("""INSERT INTO source_replacement_sources(game_id,entry_id,source_id)
      VALUES(:game,:entry,:old)"""),
        params,
    )
    session.execute(
        text("""INSERT INTO source_replacement_retired
      (game_id,source_id,entry_id,source_sha256,document) VALUES(:game,:old,:entry,:sha,'{}')"""),
        params,
    )
    if new is not None:
        session.execute(
            text("""INSERT INTO source_replacement_slots
          (game_id,sequence_number,entry_id,batch_id,state,new_source_id,new_sha256,revision,document)
          VALUES(:game,:sequence,:entry,:batch,'reserved',:source,:new_sha,1,'{}')"""),
            dict(params, sequence=new.sequence + 1, source=new.source, new_sha=new.sha),
        )


@pytest.mark.parametrize("restored", [False, True])
def test_retired_commands_refuse_before_validation_after_restart(database, tmp_path, restored):
    factory = create_session_factory(database)
    old = seed_source(factory, 401 if restored else 301)
    with game_storage_scope(GAME_ID), factory() as session:
        replacement(session, old, restored=restored)
        session.execute(
            text("""UPDATE image_review_items SET status='superseded', resolved_at=now(),
            resolved_by='fixture', resolution_revision=1,
            resolved_value='{"reason":"source_replacement_retired","previous":"unchanged"}'
            WHERE id=:review"""),
            {"review": old.review},
        )
        session.commit()
    with game_storage_scope(GAME_ID), factory() as session:
        pending = SqlAlchemyBoardCellGeometryPendingRepository(session)
        operations = [
            lambda: pending.resolve(
                pending_id=old.pending,
                expected_manifest_checksum_sha256="wrong",
                resolved_geometry_revision=-1,
            ),
            lambda: pending.reject(
                pending_id=old.pending,
                game_id=GAME_ID,
                import_job_id=old.job,
                idempotency_key=uuid4(),
                expected_geometry_revision=-1,
                reason=BoardRejectionReason.BLURRED,
                note=None,
                rejected_by="late",
                rejected_at=datetime.now(UTC),
            ),
            lambda: SqlAlchemyImageSourceGeometryRepository(session).append(
                SimpleNamespace(game_id=GAME_ID, source_image_id=old.source)
            ),
            lambda: SqlAlchemyGridGeometryApprovalRepository(session, tmp_path).approve(
                GAME_ID, old.job, old.review, {"idempotencyKey": str(uuid4())}, "late"
            ),
            lambda: SqlAlchemyGridGeometryProposalRepository(session, tmp_path).command(
                GAME_ID,
                old.job,
                old.review,
                uuid4(),
                "reject",
                {"idempotencyKey": str(uuid4())},
                "late",
            ),
            lambda: SqlAlchemyPageGeometryOverrideRepository(session).append(
                replace(old.page, id=uuid4(), revision=2, decision_checksum_sha256="e" * 64)
            ),
        ]
        context = SimpleNamespace(
            game_id=GAME_ID,
            source_image_id=old.source,
            import_job_id=old.job,
            review_item_id=old.review,
            recognized_board_id=old.board,
            sequence_number=9999,
            position_index=0,
        )
        operations.append(
            lambda: SqlAlchemyVirtualGridGeometryRepository(session).save_virtual_geometry_revision(
                prepared=SimpleNamespace(context=context),
                idempotency_key=uuid4(),
                created_at=datetime.now(UTC),
            )
        )
        for operation in operations:
            with pytest.raises(SourceReplacementError) as caught:
                operation()
            assert caught.value.code == "SOURCE_REPLACEMENT_RETIRED"
        assert session.scalar(
            text("SELECT resolved_value FROM image_review_items WHERE id=:id"), {"id": old.review}
        ) == {"reason": "source_replacement_retired", "previous": "unchanged"}
        assert pending.get(old.pending).status.value == "pending"
        assert pending.counts(game_id=GAME_ID, import_job_id=old.job).total == 0
        pages = SqlAlchemyPageGeometryOverrideRepository(session)
        assert pages.get_current(game_id=GAME_ID, source_checksum_sha256=old.sha) is None
        assert pages.append(old.page) == old.page  # immutable exact receipt still available
        session.rollback()


def test_provisional_pending_hidden_but_verified_working_geometry_allowed(database):
    factory = create_session_factory(database)
    old, new, ordinary = (seed_source(factory, n) for n in (501, 601, 701))
    with game_storage_scope(GAME_ID), factory() as session:
        replacement(session, old, new=new)
        session.commit()
    with game_storage_scope(GAME_ID), factory() as session:
        repository = SqlAlchemyBoardCellGeometryPendingRepository(session)
        assert repository.counts(game_id=GAME_ID, import_job_id=new.job).total == 0
        assert (
            repository.list(
                game_id=GAME_ID, import_job_id=new.job, status=None, after_key=None, limit=10
            )
            == ()
        )
        assert repository.counts(game_id=GAME_ID, import_job_id=ordinary.job).pending == 1
        from game_predictor_api.domain.image_grid_reviews import (
            ImageGridReviewListFilter,
            ImageGridReviewView,
        )
        from game_predictor_api.storage.image_grid_review_repository import (
            SqlAlchemyImageGridReviewRepository,
        )

        grids = SqlAlchemyImageGridReviewRepository(session)
        for source, count in ((new, 0), (old, 0), (ordinary, 1)):
            grid_filter = ImageGridReviewListFilter(
                game_id=GAME_ID,
                import_job_id=source.job,
                view=ImageGridReviewView.ALL,
            )
            assert grids.grid_review_counts(review_filter=grid_filter).needs_correction == count
        repository._require_working_slot(
            game=GAME_ID, source=new.source, job=new.job, sequence=new.sequence + 1, review=None
        )
        with pytest.raises(SourceReplacementError):
            repository._require_working_slot(
                game=GAME_ID,
                source=new.source,
                job=ordinary.job,
                sequence=new.sequence + 1,
                review=None,
            )
        pages = SqlAlchemyPageGeometryOverrideRepository(session)
        checksums = {row.source_checksum_sha256 for row in pages.list_current(game_id=GAME_ID)}
        assert ordinary.sha in checksums and old.sha not in checksums and new.sha not in checksums
        assert (
            pages.get_by_decision_checksum(
                game_id=GAME_ID, source_checksum_sha256=old.sha, decision_checksum_sha256=old.sha
            )
            == old.page
        )


def test_ordinary_slot_rejection_revert_and_retired_replay(database):
    from game_predictor_api.storage.geometry_correction_revert_repository import (
        SqlAlchemyGeometryCorrectionRevertRepository,
    )

    factory = create_session_factory(database)
    old = seed_source(factory, 801)
    key = uuid4()
    now = datetime.now(UTC)
    arguments = dict(
        pending_id=old.pending,
        game_id=GAME_ID,
        import_job_id=old.job,
        idempotency_key=key,
        expected_geometry_revision=0,
        reason=BoardRejectionReason.BLURRED,
        note=None,
        rejected_by="reviewer",
        rejected_at=now,
    )
    with game_storage_scope(GAME_ID), factory() as session:
        repository = SqlAlchemyBoardCellGeometryPendingRepository(session)
        receipt, event_id, created = repository.reject(**arguments)
        assert created and receipt.status.value == "rejected"
        reverted = SqlAlchemyGeometryCorrectionRevertRepository(session).revert(
            game_id=GAME_ID,
            import_job_id=old.job,
            board_geometry_revision_id=event_id,
            idempotency_key=uuid4(),
            expected_geometry_revision=0,
            expected_resolution_revision=0,
            actor="reviewer",
            reverted_at=datetime.now(UTC),
        )
        assert reverted.created
        assert repository.get(old.pending).status.value == "pending"
        replacement(session, old, restored=True)
        session.commit()
    with game_storage_scope(GAME_ID), factory() as session:
        repository = SqlAlchemyBoardCellGeometryPendingRepository(session)
        replay, replayed_id, created = repository.reject(**arguments)
        assert not created and replayed_id == event_id and replay == receipt
        assert repository.get(old.pending).status.value == "pending"
        with pytest.raises(SourceReplacementError) as caught:
            SqlAlchemyGeometryCorrectionRevertRepository(session).revert(
                game_id=GAME_ID,
                import_job_id=old.job,
                board_geometry_revision_id=event_id,
                idempotency_key=uuid4(),
                expected_geometry_revision=-1,
                expected_resolution_revision=-1,
                actor="late",
                reverted_at=datetime.now(UTC),
            )
        assert caught.value.code == "SOURCE_REPLACEMENT_RETIRED"


def test_page_service_replay_after_retirement_precedes_mutable_cas(database):
    from game_predictor_api.application.page_geometry_overrides import PageGeometryOverrideService

    factory = create_session_factory(database)
    old = seed_source(factory, 901)
    arguments = dict(
        game_id=GAME_ID,
        source_checksum_sha256=old.sha,
        image_width=100,
        image_height=100,
        expected_board_count=1,
        final_quads=old.page.final_quads,
        actor="reviewer",
        expected_override_revision=1,
    )
    with game_storage_scope(GAME_ID), factory() as session:
        service = PageGeometryOverrideService(SqlAlchemyPageGeometryOverrideRepository(session))
        receipt, created = service.save(**arguments)
        assert created and receipt.revision == 2
        replacement(session, old, restored=True)
        session.commit()
    with game_storage_scope(GAME_ID), factory() as session:
        service = PageGeometryOverrideService(SqlAlchemyPageGeometryOverrideRepository(session))
        replay, created = service.save(**arguments)
        assert not created and replay == receipt
        with pytest.raises(SourceReplacementError) as caught:
            service.save(**dict(arguments, expected_override_revision=999))
        assert caught.value.code == "SOURCE_REPLACEMENT_RETIRED"
