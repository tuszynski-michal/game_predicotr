"""Retirement on the owned, disposable PostgreSQL fixture only."""

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.mobile_releases import MobileReleaseConflictError
from game_predictor_api.domain.source_replacement import SourceReplacementError
from game_predictor_api.domain.symbol_readability import GAME_ID
from game_predictor_api.schemas.source_replacement import (
    SourceReplacementCreateRequest,
    SourceReplacementManifestResponse,
    SourceRetirementCommand,
    SourceRetirementPreviewRequest,
    SourceRetirementResult,
)
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemyImageSymbolReviewRepository,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import ImageBoardGeometryPendingModel
from game_predictor_api.storage.source_replacement import SourceReplacementRepository
from game_predictor_api.storage.source_replacement_retirement import SourceRetirement
from game_predictor_worker.images.orchestration_store import SqlAlchemyImageBatchStore
from game_predictor_worker.releases.store import SqlAlchemyReleaseWorkflowStore
from sqlalchemy import text
from test_image_batch_store import (
    PIPELINE,
    _add_review_projection_source,
    _image_job,
    _set_complete_resolution,
)
from test_source_replacement_postgres import (
    database as _owned_database,
)
from test_source_replacement_postgres import (
    pytestmark as pytestmark,
)
from test_source_replacement_postgres import (
    test_exact_alias_manifest_and_lost_response as _seed,
)


@pytest.fixture(scope="module")
def database():
    yield from _owned_database.__wrapped__()


def test_atomic_photo_retirement_drift_replay_and_export(database, monkeypatch):
    _seed(database)
    factory = create_session_factory(database)
    with factory() as session:
        repo = SourceReplacementRepository(session)
        repo.bind(GAME_ID)
        sources = list(
            session.scalars(
                text("SELECT id FROM source_images WHERE game_id=:game"), {"game": GAME_ID}
            )
        )
        # Pending resolved_value is NULL by constraint; the complete prior row still matters.
        session.execute(
            text(
                "UPDATE image_review_items SET snapshot=snapshot || CAST(:value AS jsonb) "
                "WHERE game_id=:game"
            ),
            {"game": GAME_ID, "value": json.dumps({"nested": {"prior": [1, {"x": "y"}]}})},
        )
        preview = repo.preview(GAME_ID, sources)
        plan = repo.create(
            GAME_ID,
            SourceReplacementCreateRequest(
                mode="replace_preserve_history",
                source_ids=sources,
                idempotency_key=uuid4(),
                expected_revision=0,
                preview_token=preview["preview_token"],
            ),
        )
        session.commit()
    batch = UUID(plan["id"])
    entry = UUID(plan["entries"][0]["id"])
    request = SourceRetirementPreviewRequest(
        mode="replace_preserve_history",
        action="retire",
        batch_id=batch,
        entry_id=entry,
        expected_revision=1,
    )
    from game_predictor_api.storage.sequence_ownership_lock import sequence_ownership_lock_key

    release = SimpleNamespace(games=(SimpleNamespace(game_id=GAME_ID, dataset_version_id=uuid4()),))
    with SqlAlchemyReleaseWorkflowStore(factory).publication_fence(release), factory() as other:
        assert (
            other.scalar(
                text("SELECT pg_try_advisory_xact_lock(:key)"),
                {"key": sequence_ownership_lock_key(GAME_ID)},
            )
            is False
        )
    with factory() as session:
        repo = SourceReplacementRepository(session)
        repo.bind(GAME_ID)
        old = (
            session.execute(
                text(
                    "SELECT id,batch_id FROM source_replacement_entries "
                    "WHERE game_id=:game AND batch_id<>:batch AND phase='planned' LIMIT 1"
                ),
                {"game": GAME_ID, "batch": batch},
            )
            .mappings()
            .one()
        )
        with pytest.raises(SourceReplacementError) as error:
            repo.replacement_request(GAME_ID, old["batch_id"], [old["id"]])
        assert error.value.code == "SOURCE_REPLACEMENT_PHASE_CONFLICT"
        cancellation = SourceRetirementCommand(
            mode="replace_preserve_history",
            action="cancel",
            batch_id=old["batch_id"],
            entry_id=old["id"],
            expected_revision=1,
            idempotency_key=uuid4(),
            confirmed=True,
        )
        cancelled = repo.retirement_command(GAME_ID, cancellation)
        assert cancelled["phase"] == "cancelled"
        assert session.scalar(text("SELECT count(*) FROM source_replacement_slots")) == 0
        session.commit()
    with factory() as session:
        assert (
            SourceReplacementRepository(session).retirement_command(GAME_ID, cancellation)
            == cancelled
        )
    with factory() as session:
        repo = SourceReplacementRepository(session)
        fresh = repo.retirement_preview(GAME_ID, request)
        command = SourceRetirementCommand(
            **request.model_dump(),
            confirmed=True,
            idempotency_key=uuid4(),
            preview_token=fresh["preview_token"],
        )
        session.execute(
            text("UPDATE image_symbol_review_cells SET revision=revision+1 WHERE game_id=:game"),
            {"game": GAME_ID},
        )
        with pytest.raises(SourceReplacementError, match="Wymagany nowy plan"):
            repo.retirement_command(GAME_ID, command)
        session.rollback()
    original = SourceRetirement._invalidate

    def fail_after_changes(self, game):
        raise RuntimeError("injected after markers and pending updates")

    monkeypatch.setattr(SourceRetirement, "_invalidate", fail_after_changes)
    with factory() as session:
        repo = SourceReplacementRepository(session)
        with pytest.raises(RuntimeError, match="injected"):
            repo.retirement_command(GAME_ID, command)
        session.rollback()
    monkeypatch.setattr(SourceRetirement, "_invalidate", original)
    with factory() as session:
        repo = SourceReplacementRepository(session)
        loaded = repo.get(GAME_ID, batch)
        assert loaded["entries"][0]["phase"] == "planned"
        assert session.scalar(text("SELECT count(*) FROM source_replacement_retired")) == 0
        result = repo.retirement_command(GAME_ID, command)
        SourceRetirementResult.model_validate(result)
        session.commit()
    with factory() as session:
        repo = SourceReplacementRepository(session)
        assert repo.retirement_command(GAME_ID, command) == result
        assert result["phase"] == "gap_open"
        current = SourceReplacementManifestResponse.model_validate(repo.get(GAME_ID, batch))
        assert len(current.entries[0].retired) == 2
        assert current.entries[0].retired[0]["action"] == "source_replacement_retired"
        assert session.scalar(text("SELECT count(*) FROM source_replacement_retired")) == 2
        assert session.scalar(text("SELECT count(*) FROM source_replacement_slots")) == 9
        assert session.scalar(text("SELECT count(*) FROM source_images")) == 2
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM image_review_resolution_events WHERE action='superseded'"
                )
            )
            == 2
        )
        assert (
            session.scalar(text("SELECT count(*) FROM image_review_items WHERE status='pending'"))
            == 0
        )
        assert session.scalar(text("SELECT count(*) FROM image_board_search_fast_documents")) == 0
        assert session.scalar(text("SELECT count(*) FROM image_symbol_review_cells")) == 30
        values = list(session.scalars(text("SELECT resolved_value FROM image_review_items")))
        assert all(value["previous"]["resolved_value"] is None for value in values)
        assert all(
            value["previous"]["snapshot"]["nested"] == {"prior": [1, {"x": "y"}]}
            for value in values
        )
        assert all("canonicalReviewItemId" not in value for value in values)
        assert (
            session.scalar(
                text("SELECT document FROM source_replacement_batches WHERE id=:id"), {"id": batch}
            )
            == plan
        )
        exported = repo.replacement_request(GAME_ID, batch, [entry])
        assert exported["allowedRanges"] == [
            {"entryId": str(entry), "sequenceStart": 1, "sequenceEnd": 9}
        ]
        assert exported["entries"][0]["revision"] == 2
        assert "batchRevision" not in exported
        Path("D:/game_predicotr/artifacts/t1129-export.json").write_text(
            json.dumps(exported, indent=2), encoding="utf-8"
        )
        with pytest.raises(SourceReplacementError) as error:
            repo.retirement_command(
                GAME_ID,
                command.model_copy(
                    update={"action": "cancel", "idempotency_key": uuid4(), "expected_revision": 2}
                ),
            )
        assert error.value.code == "SOURCE_REPLACEMENT_PHASE_CONFLICT"
        session.rollback()


def _photo(factory, sequence, sha, *, status="pending"):
    now = datetime.now(UTC)
    with game_storage_scope(GAME_ID), factory() as session:
        job = SqlAlchemyJobRepository(session).add_job(_image_job(GAME_ID, PIPELINE, now))
        session.commit()
    execution = SqlAlchemyImageBatchStore(factory).register_file(
        job.id,
        source_checksum_sha256=sha,
        pipeline_fingerprint=PIPELINE,
        source_relative_path=f"seq_{sequence}-{sequence + 8}.jpg",
        order_index=0,
        registered_at=now,
    )
    with game_storage_scope(GAME_ID), factory() as session:
        review, board = _add_review_projection_source(
            session,
            job_id=job.id,
            file_execution_key=execution.file_execution_key,
            source_checksum=sha,
            source_name=f"seq_{sequence}-{sequence + 8}.jpg",
            position_index=0,
            sequence_number=sequence,
            status=status,
            created_at=now,
        )
        if status != "pending":
            _set_complete_resolution(
                session,
                review_item_id=review,
                board_id=board,
                sequence_number=sequence,
                action=status,
                resolved_at=now,
            )
        source = session.scalar(
            text("SELECT source_image_id FROM recognized_boards WHERE id=:id"), {"id": board}
        )
        session.execute(
            text("UPDATE public.jobs SET status='waiting_for_review' WHERE id=:id"), {"id": job.id}
        )
        session.execute(
            text(
                "UPDATE image_source_geometry_revisions SET "
                "sequence_attestation_checksum_sha256=:sha WHERE source_image_id=:id"
            ),
            {"id": source, "sha": sha},
        )
        session.commit()
    return source, review, board, job.id


def test_two_entries_internal_derive_deferred_canonical_and_mobile_fence(database):
    factory = create_session_factory(database)
    first, review, board, job = _photo(factory, 101, "c" * 64)
    second, _, _, _ = _photo(factory, 201, "d" * 64)
    with game_storage_scope(GAME_ID), factory() as session:
        session.execute(
            text(
                "UPDATE image_source_geometry_revisions SET sequence_range_end=203, "
                "active_board_slots=ARRAY[0,1,2]::smallint[], "
                "board_geometries=jsonb_build_array(board_geometries->0,board_geom"
                "etries->1,board_geometries->2) "
                "WHERE source_image_id=:source"
            ),
            {"source": second},
        )
        session.flush()
        SqlAlchemyBoardSearchProjectionRepository(session).rebuild_game(GAME_ID)
        projection = SqlAlchemyImageSymbolReviewRepository(session)
        session.execute(
            text(
                "UPDATE image_symbol_review_states SET last_review_item_id=NULL WHERE game_id=:game"
            ),
            {"game": GAME_ID},
        )
        projection.start_or_resume_backfill(GAME_ID)
        projection.backfill_next_batch(GAME_ID, batch_size=100)
        _set_complete_resolution(
            session,
            review_item_id=review,
            board_id=board,
            sequence_number=101,
            action="accepted",
            resolved_at=datetime.now(UTC),
        )
        session.add(
            ImageBoardGeometryPendingModel(
                game_id=GAME_ID,
                import_job_id=job,
                source_image_id=first,
                sequence_number=102,
                position_index=1,
                source_checksum_sha256="c" * 64,
                source_relative_path="seq_101-109.jpg",
                status="pending",
                reason_code="incomplete_lattice",
                processing_manifest_checksum_sha256="c" * 64,
                processing_manifest_relative_path="pending.json",
                pipeline_fingerprint_sha256="c" * 64,
                expected_geometry_revision=0,
                expected_review_resolution_revision=0,
            )
        )
        session.execute(
            text(
                "INSERT INTO "
                "image_sequence_canonical(game_id,sequence_number,review_item_id,r"
                "ecognized_board_id,import_job_id,source_image_id,source_checksum_"
                "sha256,board_checksum_sha256,status,resolution_revision,geometry_"
                "revision) "
                "VALUES(:game,101,:review,:board,:job,:source,:sha,:sha,'accepted',1,1)"
            ),
            {
                "game": GAME_ID,
                "review": review,
                "board": board,
                "job": job,
                "source": first,
                "sha": "c" * 64,
            },
        )
        session.flush()
        session.execute(
            text(
                "UPDATE image_symbol_review_cells SET quality_issue='unreadable' WHERE "
                "review_item_id IN (SELECT id FROM image_review_items WHERE "
                "sequence_number>=101)"
            )
        )
        session.execute(
            text("UPDATE public.games SET super_game_kind='free_spins' WHERE id=:game"),
            {"game": GAME_ID},
        )
        session.commit()
    with factory() as session:
        repo = SourceReplacementRepository(session)
        pre = repo.preview(GAME_ID, [first, second])
        assert all(not item["blockers"] for item in pre["entries"]), [
            (e["range_start"], e["blockers"], len(e["evidence"])) for e in pre["entries"]
        ]
        plan = repo.create(
            GAME_ID,
            SourceReplacementCreateRequest(
                mode="replace_preserve_history",
                source_ids=[first, second],
                idempotency_key=uuid4(),
                expected_revision=0,
                preview_token=pre["preview_token"],
            ),
        )
        session.commit()
    entries = sorted(plan["entries"], key=lambda item: item["range_start"])
    batch = UUID(plan["id"])

    def req(item):
        return SourceRetirementPreviewRequest(
            mode="replace_preserve_history",
            action="retire",
            batch_id=batch,
            entry_id=UUID(item["id"]),
            expected_revision=1,
        )

    with factory() as session:
        repo = SourceReplacementRepository(session)
        repo.bind(GAME_ID, write=True)
        session.execute(
            text(
                "UPDATE image_board_geometry_pending SET source_image_id=:foreign, "
                "sequence_number=101 WHERE source_image_id=:own"
            ),
            {"foreign": second, "own": first},
        )
        with pytest.raises(SourceReplacementError) as error:
            repo.retirement_preview(GAME_ID, req(entries[0]))
        assert error.value.code == "SOURCE_REPLACEMENT_SLOT_PENDING_CONFLICT"
        assert error.value.details["resolutionUrls"]
        assert (
            session.scalar(
                text("SELECT count(*) FROM source_replacement_retired WHERE source_id=:id"),
                {"id": first},
            )
            == 0
        )
        session.rollback()
    with factory() as session:
        repo = SourceReplacementRepository(session)
        fresh = repo.retirement_preview(GAME_ID, req(entries[0]))
        result = repo.retirement_command(
            GAME_ID,
            SourceRetirementCommand(
                **req(entries[0]).model_dump(),
                confirmed=True,
                idempotency_key=uuid4(),
                preview_token=fresh["preview_token"],
            ),
        )
        assert len(result["createdDerivations"]) == 1
        session.commit()
    with factory() as session:
        repo = SourceReplacementRepository(session)
        fresh = repo.retirement_preview(GAME_ID, req(entries[1]))
        assert fresh["entry"]["sequence_numbers"] == [201, 202, 203]
        marker = session.scalar(
            text("SELECT document FROM source_replacement_retired WHERE source_id=:id"),
            {"id": first},
        )
        assert marker["prior"]["canonical"][0]["review_item_id"] == str(review)
        from game_predictor_api.storage.super_game_series_repository import _POSITION_BOARDS_SQL

        assert not session.execute(
            _POSITION_BOARDS_SQL, {"game_id": GAME_ID, "positions": [101]}
        ).all()
        assert marker["prior"]["pending_slots"][0]["status"] == "pending"
        assert (
            session.scalar(
                text("SELECT status FROM image_board_geometry_pending WHERE source_image_id=:id"),
                {"id": first},
            )
            == "superseded"
        )
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM image_board_geometry_pending_events e "
                    "JOIN image_board_geometry_pending p ON p.id=e.pending_geometry_id "
                    "WHERE p.source_image_id=:id"
                ),
                {"id": first},
            )
            == 0
        )
        assert (
            session.scalar(
                text("SELECT status FROM image_review_items WHERE id=:id"), {"id": review}
            )
            == "accepted"
        )
        # A proven ID with changed immutable payload is no longer exempt.
        session.execute(
            text(
                "UPDATE public.jobs SET input_payload=input_payload || "
                "CAST(:payload AS jsonb) WHERE id=:id"
            ),
            {"id": result["createdDerivations"][0]["id"], "payload": json.dumps({"foreign": True})},
        )
        with pytest.raises(SourceReplacementError) as error:
            repo.retirement_preview(GAME_ID, req(entries[1]))
        assert error.value.code == "SOURCE_REPLACEMENT_ACTIVE_JOB"
        session.rollback()
    with factory() as session:
        repo = SourceReplacementRepository(session)
        repo.bind(GAME_ID, write=True)
        # Same job type without a batch receipt is never a permitted difference.
        from game_predictor_api.domain.jobs import JobType, create_job

        SqlAlchemyJobRepository(session).add_job(
            create_job(
                JobType.SUPER_GAME_SERIES_DERIVE,
                game_id=GAME_ID,
                input_payload={
                    "schema_version": 1,
                    "reason": "foreign",
                    "request_id": str(uuid4()),
                },
            )
        )
        session.flush()
        with pytest.raises(SourceReplacementError) as error:
            repo.retirement_preview(GAME_ID, req(entries[1]))
        assert error.value.code == "SOURCE_REPLACEMENT_ACTIVE_JOB"
        session.rollback()
    with factory() as session:
        repo = SourceReplacementRepository(session)
        fresh = repo.retirement_preview(GAME_ID, req(entries[1]))
        before = repo.replacement_request(GAME_ID, batch, [UUID(entries[0]["id"])])
        repo.retirement_command(
            GAME_ID,
            SourceRetirementCommand(
                **req(entries[1]).model_dump(),
                confirmed=True,
                idempotency_key=uuid4(),
                preview_token=fresh["preview_token"],
            ),
        )
        assert repo.replacement_request(GAME_ID, batch, [UUID(entries[0]["id"])]) == before
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM public.jobs WHERE game_id=:game AND "
                    "job_type='super_game_series_derive' AND status='created'"
                ),
                {"game": GAME_ID},
            )
            == 1
        )
        # Rebuild cannot resurrect retired accepted history.
        SqlAlchemyBoardSearchProjectionRepository(session).rebuild_game(GAME_ID)
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM image_board_search_fast_documents WHERE "
                    "sequence_number=101"
                )
            )
            == 0
        )
        session.commit()
    store = SqlAlchemyReleaseWorkflowStore(factory)
    release = SimpleNamespace(games=(SimpleNamespace(game_id=GAME_ID, dataset_version_id=uuid4()),))
    with pytest.raises(MobileReleaseConflictError) as error, store.publication_fence(release):
        pytest.fail("Publisher must never run with an open reservation")
    assert error.value.code == "SOURCE_REPLACEMENT_RESERVED"
