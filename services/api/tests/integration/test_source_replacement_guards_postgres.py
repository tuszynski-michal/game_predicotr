"""Actual nondeferred FK bootstrap, whole-photo rollback, persistence and fences."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from game_predictor_api.domain.source_replacement import SourceReplacementError
from game_predictor_api.domain.symbol_readability import GAME_ID
from game_predictor_api.schemas.source_replacement import SourceReplacementCreateRequest
from game_predictor_api.storage.cleanup_repository import SqlAlchemyCleanupRepository
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_training_cohort_models import (
    GridTrainingCohortMemberModel,
    GridTrainingCohortModel,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import JobModel, RecognizedBoardModel, SourceImageModel
from game_predictor_api.storage.pending_sequence_ownership import create_owned_pending_review_item
from game_predictor_api.storage.sequence_ownership_lock import acquire_sequence_ownership_lock
from game_predictor_api.storage.source_replacement import SourceReplacementRepository
from game_predictor_api.storage.source_replacement_binding import (
    admitted_source,
    bind_complete_source,
)
from game_predictor_api.storage.source_replacement_guards import (
    current_review_clause,
    referenced_artifact,
    referenced_sources,
    require_active_sha,
    require_active_source,
    require_current_review,
    require_unreferenced_sources,
)
from game_predictor_worker.images.orchestration_store import SqlAlchemyImageBatchStore
from sqlalchemy import literal, select, text
from sqlalchemy.exc import DBAPIError
from test_image_batch_store import PIPELINE, _add_review_projection_source, _image_job
from test_source_replacement_postgres import database as database  # noqa: F401
from test_source_replacement_postgres import pytestmark as pytestmark


def test_bootstrap_all_slots_atomic_restart_foreign_proof_and_retention(database, monkeypatch):  # noqa: F811
    factory = create_session_factory(database)
    batch, entry = uuid4(), uuid4()
    now = datetime.now(UTC)
    with game_storage_scope(GAME_ID), factory() as session:
        job = SqlAlchemyJobRepository(session).add_job(_image_job(GAME_ID, PIPELINE, now))
        session.commit()
        executions = [
            SqlAlchemyImageBatchStore(factory).register_file(
                job.id,
                source_checksum_sha256=sha,
                pipeline_fingerprint=PIPELINE,
                source_relative_path=f"fixture-{index}.jpg",
                order_index=index,
                registered_at=now,
            )
            for index, sha in enumerate(("c" * 64, "d" * 64))
        ]
        sources, templates = [], []
        for index, sha in enumerate(("c" * 64, "d" * 64)):
            _, board_id = _add_review_projection_source(
                session,
                job_id=job.id,
                file_execution_key=executions[index].file_execution_key,
                source_checksum=sha,
                source_name=f"fixture-{index}.jpg",
                position_index=0,
                sequence_number=900 + index,
                status="rejected",
                created_at=now,
            )
            template = session.get(RecognizedBoardModel, board_id)
            sources.append(template.source_image_id)
            templates.append(template)
        old, source = sources
        with session.begin_nested() as ambiguous:
            session.execute(
                text("UPDATE public.jobs SET status='completed' WHERE id=:job"), {"job": job.id}
            )
            other_job = SqlAlchemyJobRepository(session).add_job(
                _image_job(GAME_ID, PIPELINE, now + timedelta(seconds=1))
            )
            session.flush()
            session.execute(
                text(
                    "UPDATE source_images SET checksum_sha256=repeat('c',64), import_job_id=:job "
                    "WHERE id=:source"
                ),
                {"source": source, "job": other_job.id},
            )
            repo = SourceReplacementRepository(session)
            preview = repo.preview(GAME_ID, [old])
            assert "SOURCE_REPLACEMENT_SHA_SCOPE_CONFLICT" in preview["entries"][0]["blockers"]
            assert preview["entries"][0]["source_ids"] == [str(old)]
            with pytest.raises(SourceReplacementError):
                repo.create(
                    GAME_ID,
                    SourceReplacementCreateRequest(
                        mode="replace_preserve_history",
                        source_ids=[old],
                        idempotency_key=uuid4(),
                        expected_revision=0,
                        preview_token=preview["preview_token"],
                    ),
                )
            assert session.scalar(text("SELECT count(*) FROM source_replacement_batches")) == 0
            ambiguous.rollback()
        with session.begin_nested() as unknown:
            session.execute(
                text("UPDATE public.jobs SET status='completed' WHERE id=:job"), {"job": job.id}
            )
            unknown_job = SqlAlchemyJobRepository(session).add_job(
                _image_job(GAME_ID, PIPELINE, now + timedelta(seconds=2))
            )
            session.flush()
            session.add(
                SourceImageModel(
                    import_job_id=unknown_job.id,
                    file_execution_key=executions[0].file_execution_key,
                    relative_path="unknown-range.jpg",
                    checksum_sha256="c" * 64,
                    width=100,
                    height=100,
                    status="waiting_for_review",
                )
            )
            session.flush()
            assert (
                "SOURCE_REPLACEMENT_SHA_SCOPE_CONFLICT"
                in SourceReplacementRepository(session).preview(GAME_ID, [old])["entries"][0][
                    "blockers"
                ]
            )
            unknown.rollback()
        job_id = job.id
        pin = dict(
            schemaVersion="source-replacement-admission-v1",
            gameId=str(GAME_ID),
            batchId=str(batch),
            entryId=str(entry),
            sourceId=str(source),
            importJobId=str(job_id),
            sourceSha256="d" * 64,
            sequenceNumbers=[101, 102],
            entryRevision=1,
        )
        params = dict(
            game=GAME_ID,
            batch=batch,
            entry=entry,
            old=old,
            source=source,
            document=json.dumps({"sequence_numbers": [101, 102], "replacementAdmission": pin}),
        )
        session.execute(
            text("""INSERT INTO source_replacement_batches
          (game_id,id,revision,status,preview_token,document)
          VALUES(:game,:batch,1,'importing',repeat('a',64),'{}')"""),
            params,
        )
        session.execute(
            text("""INSERT INTO source_replacement_entries
          (game_id,id,batch_id,source_id,source_sha256,phase,document)
          VALUES(:game,:entry,:batch,:old,repeat('c',64),'importing',CAST(:document AS jsonb))"""),
            params,
        )
        session.execute(
            text("""INSERT INTO source_replacement_sources(game_id,entry_id,source_id)
          VALUES(:game,:entry,:old)"""),
            params,
        )
        _transitive_model_retention(session, factory, old, source, job_id, now)
        session.execute(
            text("""INSERT INTO source_replacement_slots
          (game_id,sequence_number,entry_id,batch_id,state,new_source_id,new_sha256,revision,document)
          SELECT :game,n,:entry,:batch,'reserved',:source,repeat('d',64),1,'{}'
          FROM unnest(ARRAY[101,102]) n"""),
            params,
        )
        _reserved_sha_alias_is_not_current(session, executions[1].file_execution_key, now)
        board_ids = []
        for position, number in enumerate((101, 102), start=1):
            values = {
                col.key: getattr(templates[1], col.key)
                for col in RecognizedBoardModel.__table__.columns
                if col.key
                not in {"id", "position_index", "sequence_number", "sequence_number_raw", "status"}
            }
            board = RecognizedBoardModel(
                **values,
                position_index=position,
                sequence_number=number,
                sequence_number_raw=str(number),
                status="pending_review",
            )
            session.add(board)
            session.flush()
            board_ids.append(board.id)
        session.commit()

    reviews = []
    for board_id in board_ids:
        with game_storage_scope(GAME_ID), factory() as session:
            acquire_sequence_ownership_lock(session, game_id=GAME_ID)
            item, _ = create_owned_pending_review_item(
                session,
                board=session.get(RecognizedBoardModel, board_id),
                game_id=GAME_ID,
                import_job=session.get(JobModel, job_id),
                snapshot={},
                created_at=now,
            )
            assert item.status == "pending"
            reviews.append(item.id)
            assert (
                session.scalar(
                    select(current_review_clause(type(item).id)).where(type(item).id == item.id)
                )
                is False
            )
            with pytest.raises(SourceReplacementError) as blocked:
                require_current_review(session, GAME_ID, item.id)
            assert blocked.value.code == "SOURCE_REPLACEMENT_RESERVED"
            if len(reviews) == 1:
                assert not bind_complete_source(session, game=GAME_ID, source=source, job=job_id)
            session.commit()

    with game_storage_scope(GAME_ID), factory() as session:
        execute = session.execute

        def fail_second_binding(statement, parameters=None, *args, **kwargs):
            if (
                str(statement).lstrip().startswith("UPDATE source_replacement_slots")
                and parameters["seq"] == 102
            ):
                raise RuntimeError("failure between slot bindings")
            return execute(statement, parameters, *args, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(session, "execute", fail_second_binding)
            with pytest.raises(RuntimeError, match="between slot"):
                bind_complete_source(session, game=GAME_ID, source=source, job=job_id)
        session.rollback()
    with game_storage_scope(GAME_ID), factory() as session:
        assert (
            session.scalar(
                text("SELECT count(*) FROM source_replacement_slots WHERE state='pending_bound'")
            )
            == 0
        )
        assert bind_complete_source(session, game=GAME_ID, source=source, job=job_id)
        session.commit()
    with game_storage_scope(GAME_ID), factory() as session:
        assert bind_complete_source(session, game=GAME_ID, source=source, job=job_id)
        assert session.scalar(text("SELECT max(revision) FROM source_replacement_slots")) == 2
        for review in reviews:
            require_current_review(session, GAME_ID, review)
        _stale_search_reads_and_rebuild(session, source, reviews[0], entry, job_id)
        with pytest.raises(SourceReplacementError):
            admitted_source(session, GAME_ID, source, uuid4())
        assert referenced_sources(session, GAME_ID, [source])
        with session.begin_nested() as partial:
            session.execute(
                text(
                    "DELETE FROM source_replacement_slots WHERE game_id=:game AND "
                    "sequence_number=102"
                ),
                params,
            )
            narrowed = dict(pin, sequenceNumbers=[101])
            session.execute(
                text(
                    "UPDATE source_replacement_entries SET "
                    "document=jsonb_set(document,'{replacementAdmission}',CAST(:pin AS jsonb)) "
                    "WHERE id=:entry"
                ),
                {"entry": entry, "pin": json.dumps(narrowed)},
            )
            with pytest.raises(SourceReplacementError):
                admitted_source(session, GAME_ID, source, job_id)
            partial.rollback()
        assert referenced_sources(session, GAME_ID, [old])
        with pytest.raises(SourceReplacementError):
            require_unreferenced_sources(session, GAME_ID, [old])
        session.execute(
            text("""INSERT INTO source_replacement_retired
          (game_id,source_id,entry_id,source_sha256,document)
          VALUES(:game,:old,:entry,repeat('c',64),'{}')"""),
            params,
        )
        with pytest.raises(SourceReplacementError):
            require_active_source(session, GAME_ID, old)
        with pytest.raises(SourceReplacementError):
            require_active_sha(session, GAME_ID, "c" * 64)
        assert (
            session.scalar(
                text(
                    "SELECT "
                    "public.source_replacement_source_current_v1(:game,:unknown,repeat('c',64))"
                ),
                {"game": GAME_ID, "unknown": uuid4()},
            )
            is False
        )
        assert (
            session.scalar(
                text(
                    "SELECT "
                    "public.source_replacement_source_current_v1(:other,:unknown,repeat('c',64))"
                ),
                {"other": uuid4(), "unknown": uuid4()},
            )
            is True
        )
        for phase in ("planned", "gap_open", "restored"):
            session.execute(
                text("UPDATE source_replacement_entries SET phase=:phase WHERE id=:entry"),
                {"phase": phase, "entry": entry},
            )
            assert referenced_sources(session, GAME_ID, [old])
            assert referenced_sources(session, GAME_ID, [source])
            cleanup = SqlAlchemyCleanupRepository(session, factory)
            snapshot = cleanup.game_snapshot(GAME_ID)
            assert "SOURCE_REPLACEMENT_REFERENCED" in snapshot.blockers
            count = session.scalar(text("SELECT count(*) FROM source_images"))
            with pytest.raises(SourceReplacementError):
                cleanup.reset_game(snapshot, None)
            assert session.scalar(text("SELECT count(*) FROM source_images")) == count
        session.execute(
            text("DELETE FROM source_replacement_slots WHERE game_id=:game"), {"game": GAME_ID}
        )
        assert referenced_sources(session, GAME_ID, [source])
        session.commit()
    with game_storage_scope(GAME_ID), factory() as session:
        _recording_replay_after_retirement(session, old)
        session.commit()


def _reserved_sha_alias_is_not_current(session, execution, now):
    with session.begin_nested() as alias_fixture:
        alias_job = uuid4()
        session.execute(
            text("""INSERT INTO public.jobs
          (id,game_id,job_type,status,input_payload,input_key)
          VALUES(:id,:game,'import','completed','{}',:key)"""),
            {"id": alias_job, "game": GAME_ID, "key": str(alias_job)},
        )
        session.execute(
            text("""INSERT INTO image_import_job_files
          (game_id,job_id,file_execution_key,order_index,source_relative_path,
           workflow_checkpoint_payload,workflow_status)
          VALUES(:game,:job,:execution,0,'same-new-sha-alias.jpg','{}','completed')"""),
            {"game": GAME_ID, "job": alias_job, "execution": execution},
        )
        review, board = _add_review_projection_source(
            session,
            job_id=alias_job,
            file_execution_key=execution,
            source_checksum="d" * 64,
            source_name="same-new-sha-alias.jpg",
            position_index=0,
            sequence_number=1200,
            status="pending",
            created_at=now,
        )
        alias_source = session.get(RecognizedBoardModel, board).source_image_id
        assert (
            session.scalar(
                text("""SELECT public.source_replacement_source_current_v1(
          :game,:source,repeat('d',64))"""),
                {"game": GAME_ID, "source": alias_source},
            )
            is False
        )
        assert session.scalar(select(current_review_clause(literal(review)))) is False
        with pytest.raises(SourceReplacementError) as blocked:
            require_current_review(session, GAME_ID, review)
        assert blocked.value.code == "SOURCE_REPLACEMENT_RESERVED"
        alias_fixture.rollback()


def _transitive_model_retention(session, factory, retained_source, deleted_source, job, now):
    from game_predictor_api.domain.cleanup import CleanupConflictError
    from game_predictor_api.storage.models import (
        ImageSymbolPredictionRevisionModel,
        SymbolModelIterationModel,
        VerifiedTrainingCohortItemModel,
        VerifiedTrainingCohortModel,
    )

    with session.begin_nested() as fixture:
        cohort = VerifiedTrainingCohortModel(
            game_id=GAME_ID,
            iteration_number=1,
            manifest_schema_version=1,
            manifest_checksum_sha256="1" * 64,
            idempotency_key=uuid4(),
            command_sha256="2" * 64,
            resolved_layout_count=1,
            cell_sample_count=15,
            source_image_count=1,
            pending_item_count=0,
            rejected_item_count=0,
            incomplete_item_count=0,
            artifact_relative_path="datasets/retained-test/manifest.json",
            created_by="fixture",
        )
        session.add(cohort)
        session.flush()
        rows = session.execute(
            text("""SELECT b.source_image_id,b.id,ri.id,ri.sequence_number
          FROM recognized_boards b JOIN image_review_items ri ON ri.recognized_board_id=b.id
          WHERE b.source_image_id IN (:retained,:deleted)"""),
            {"retained": retained_source, "deleted": deleted_source},
        ).all()
        values = {row[0]: row for row in rows}
        row = values[deleted_source]
        session.add(
            VerifiedTrainingCohortItemModel(
                cohort_id=cohort.id,
                item_order=0,
                source_image_id=deleted_source,
                recognized_board_id=row[1],
                review_item_id=row[2],
                import_job_id=job,
                sequence_number=row[3],
                decision_status="accepted",
                resolution_revision=1,
                geometry_revision=1,
                source_checksum_sha256="d" * 64,
                board_checksum_sha256="3" * 64,
                pipeline_fingerprint=PIPELINE,
                item_checksum_sha256="4" * 64,
                board_manifest={"cells": [{}] * 15},
            )
        )
        session.flush()
        model = SymbolModelIterationModel(
            game_id=GAME_ID,
            cohort_id=cohort.id,
            job_id=job,
            iteration_number=1,
            status="candidate_ready",
            configuration_fingerprint="5" * 64,
            configuration_payload={},
            checkpoint_relative_path="models/inactive/checkpoint.pt",
            candidate_manifest_relative_path="models/inactive/candidate.json",
        )
        session.add(model)
        session.flush()
        row = values[retained_source]
        prediction = ImageSymbolPredictionRevisionModel(
            game_id=GAME_ID,
            review_item_id=row[2],
            recognized_board_id=row[1],
            source_job_id=job,
            model_iteration_id=model.id,
            model_version="fixture",
            model_checksum_sha256="6" * 64,
            crop_manifest_checksum_sha256="7" * 64,
            predictions=[],
        )
        session.add(prediction)
        session.flush()
        cleanup = SqlAlchemyCleanupRepository(session, factory)
        scope = cleanup._board_source_scope_for_ranges(GAME_ID, ((901, 909),))
        assert model.id in scope.model_ids and retained_source not in scope.source_ids
        assert "SOURCE_REPLACEMENT_REFERENCED" in cleanup._board_source_blockers(scope)
        # The real deletion scope removes this model AND predictions on other photos.
        # It must refuse before either immutable evidence or inactive artifacts change.
        from dataclasses import replace

        snapshot = cleanup.game_snapshot(GAME_ID)
        snapshot = replace(snapshot, confirmation_target=f"{GAME_ID}:901-909")
        with pytest.raises(CleanupConflictError) as blocked:
            cleanup.delete_board_sources(snapshot, None)
        assert blocked.value.code == "SOURCE_REPLACEMENT_REFERENCED"
        assert session.get(SymbolModelIterationModel, model.id).status == "candidate_ready"
        assert session.get(ImageSymbolPredictionRevisionModel, prediction.id) is not None
        assert referenced_artifact(session, "models/inactive")
        assert referenced_artifact(session, "models/inactive/checkpoint.pt")
        assert not referenced_artifact(session, "models/unrelated-missing")
        fixture.rollback()


def _recording_replay_after_retirement(session, source):
    session.execute(
        text(
            "UPDATE public.games SET shape_geometry_configuration='neural_grid_v3' WHERE id=:game"
        ),
        {"game": GAME_ID},
    )
    cohort, key = uuid4(), uuid4()
    header = GridTrainingCohortModel(
        game_id=GAME_ID,
        id=cohort,
        status="preparing",
        document={"policyVersion": "application-grid-cohort-v1"},
        summary={},
        manifest_sha256="a" * 64,
        manifest_path="data/fixture-cohort/root.json",
        created_by="fixture",
    )
    session.add(header)
    session.flush()
    session.add(
        GridTrainingCohortMemberModel(
            game_id=GAME_ID,
            cohort_id=cohort,
            source_id=source,
            live_source_image_id=source,
            ordinal=0,
            role="TRAIN",
            frozen={"used": False},
        )
    )
    session.flush()
    for state in ("preview_ready", "materializing", "ready_to_freeze", "frozen"):
        header.status = state
        header.revision += 1
        session.flush()
    request = dict(
        kind="bind_existing_report",
        cohortId=str(cohort),
        idempotencyKey=str(key),
        expectedRevision=1,
        manifestSha256="a" * 64,
        reportId=str(uuid4()),
    )
    receipt = {"statusCode": 200, "reportId": request["reportId"], "immutable": True}
    params = {
        "game": GAME_ID,
        "key": key,
        "request": json.dumps(request),
        "receipt": json.dumps(receipt),
    }
    session.execute(
        text("""INSERT INTO public.recording_commands(game_id,kind,idempotency_key,
      command_json,command_sha256,actor,receipt) VALUES(:game,'bind_existing_report',:key,
      CAST(:request AS jsonb),public.recording_digest_v1(CAST(:request AS jsonb)),
      'fixture',CAST(:receipt AS jsonb))"""),
        params,
    )
    for function in ("recording_cohort_command_v3", "recording_correction_report_bind_v1"):
        actual = session.scalar(
            text(f"SELECT public.{function}(:game,CAST(:request AS jsonb),'fixture')"), params
        )
        assert actual == receipt
    with pytest.raises(DBAPIError, match="RECORDING_COMMAND_CONFLICT"), session.begin_nested():
        changed = dict(request, expectedRevision=2)
        session.scalar(
            text(
                "SELECT public.recording_cohort_command_v3(:game,CAST(:request AS jsonb),'fixture')"
            ),
            {"game": GAME_ID, "request": json.dumps(changed)},
        )
    for kind in ("register_cohort_use", "validate_cohort_use"):
        with pytest.raises(DBAPIError, match="SOURCE_REPLACEMENT_RETIRED"), session.begin_nested():
            fresh = {key: value for key, value in request.items() if key != "reportId"}
            fresh.update(kind=kind, idempotencyKey=str(uuid4()))
            session.scalar(
                text(
                    "SELECT public.recording_cohort_command_v3(:game,CAST(:request AS "
                    "jsonb),'fixture')"
                ),
                {"game": GAME_ID, "request": json.dumps(fresh)},
            )
    assert session.get(GridTrainingCohortModel, (GAME_ID, cohort)).document == {
        "policyVersion": "application-grid-cohort-v1"
    }


def _stale_search_reads_and_rebuild(session, source, review, entry, job):
    from game_predictor_api.domain.board_search import BoardSearchQueryCell, BoardSearchScope
    from game_predictor_api.storage.board_search_projection_repository import (
        SqlAlchemyBoardSearchProjectionRepository,
    )
    from game_predictor_api.storage.models import (
        ImageBoardSearchCandidateModel,
        ImageBoardSearchProjectionStateModel,
        SymbolModel,
    )

    board = session.scalar(
        text("SELECT recognized_board_id FROM image_review_items WHERE id=:id"), {"id": review}
    )
    session.add(
        SymbolModel(
            game_id=GAME_ID, code="guard-symbol", name="Fixture", mobile_code=32000, display_order=0
        )
    )
    session.add(
        ImageBoardSearchCandidateModel(
            game_id=GAME_ID,
            review_item_id=review,
            recognized_board_id=board,
            import_job_id=job,
            sequence_number=101,
            status="accepted",
            board_checksum_sha256="e" * 64,
            board_confidence=1.0,
            sequence_confidence=1.0,
            source_pixel_count=100,
            primary_symbol_codes=["guard-symbol"] * 15,
            alternative_symbol_codes=[[] for _ in range(15)],
            known_evidence_positions=[str(i) for i in range(15)],
            primary_symbol_mobile_codes=[32000] * 15,
            alternative_rank_1_mobile_codes=[None] * 15,
            alternative_rank_2_mobile_codes=[None] * 15,
            alternative_rank_3_mobile_codes=[None] * 15,
            alternative_rank_4_mobile_codes=[None] * 15,
        )
    )
    session.add(
        ImageBoardSearchProjectionStateModel(
            game_id=GAME_ID,
            status="ready",
            candidate_count=1,
            document_count=1,
            skipped_review_item_count=0,
        )
    )
    session.flush()
    projection = SqlAlchemyBoardSearchProjectionRepository(session)
    projection.reconcile_sequence(GAME_ID, 101)  # Legacy accepted fallback stays valid.
    assert projection.board_document(game_id=GAME_ID, sequence_number=101)[1] is not None
    query = dict(
        game_id=GAME_ID,
        query=(BoardSearchQueryCell(0, "guard-symbol"),),
        scope=BoardSearchScope.ALL_SEARCHABLE,
        limit=10,
    )
    assert len(projection.search(**query)) == 1
    with session.begin_nested() as retired:
        session.execute(
            text("""INSERT INTO source_replacement_retired
          (game_id,source_id,entry_id,source_sha256,document)
          VALUES(:game,:source,:entry,repeat('d',64),'{}')"""),
            {"game": GAME_ID, "source": source, "entry": entry},
        )
        # Existing fast documents are stale; all direct reads must fence immediately.
        assert projection.search(**query) == ()
        assert projection.board_document(game_id=GAME_ID, sequence_number=101)[1] is None
        assert (
            projection.range_documents(
                game_id=GAME_ID, first_sequence_number=101, last_sequence_number=101
            )[1]
            == ()
        )
        projection.reconcile_sequence(GAME_ID, 101)
        assert projection.board_document(game_id=GAME_ID, sequence_number=101)[1] is None
        projection._rebuild_fast_documents(GAME_ID)
        assert projection.board_document(game_id=GAME_ID, sequence_number=101)[1] is None
        retired.rollback()
