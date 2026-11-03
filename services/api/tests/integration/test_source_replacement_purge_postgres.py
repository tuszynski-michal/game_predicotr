"""Physical filesystem deletion on the existing owned/OID-guarded PostgreSQL fixture."""

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.cleanup import CleanupService, ManagedCleanupArtifactStore
from game_predictor_api.domain.source_replacement import SourceReplacementError
from game_predictor_api.domain.symbol_readability import GAME_ID
from game_predictor_api.schemas.source_replacement import (
    SourcePurgeCommand,
    SourcePurgePreviewRequest,
    SourceReplacementCreateRequest,
)
from game_predictor_api.storage.cleanup_repository import SqlAlchemyCleanupRepository
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.models import (
    ImageBoardGeometryRevisionModel,
    ImageReviewItemModel,
    ImageSymbolReviewCellModel,
    RecognizedBoardModel,
)
from game_predictor_api.storage.source_purge_retention import SourcePurgeRetention
from game_predictor_api.storage.source_replacement import SourceReplacementRepository
from game_predictor_api.storage.source_replacement_guards import require_active_sha
from sqlalchemy import inspect, select, text
from test_source_replacement_postgres import database as _owned_database
from test_source_replacement_postgres import pytestmark as pytestmark
from test_source_replacement_postgres import test_exact_alias_manifest_and_lost_response as _seed


@pytest.fixture(scope="module")
def database():
    yield from _owned_database.__wrapped__()


def service(session, factory, root):
    store = ManagedCleanupArtifactStore(
        root, operation_retention_guard=SourcePurgeRetention(factory).dispatch
    )
    return CleanupService(
        SqlAlchemyCleanupRepository(session, factory), store, SourceReplacementRepository(session)
    )


def test_physical_purge_manifest_replay_rollback_and_recovery(database, tmp_path: Path):
    _seed(database)
    factory = create_session_factory(database)
    neighbor_id = _add_shared_neighbors(factory)
    (tmp_path / "neighbor.jpg").write_bytes(b"neighbor in the same job")
    (tmp_path / "shared.jpg").write_bytes(b"other game owns these pixels")
    (tmp_path / "exclusive.jpg").write_bytes(b"obsolete crop")
    with factory() as session:
        SourceReplacementRepository(session).bind(GAME_ID)
        board = session.scalar(
            select(RecognizedBoardModel).where(RecognizedBoardModel.sequence_number == 1)
        )
        review = session.scalar(
            select(ImageReviewItemModel).where(ImageReviewItemModel.recognized_board_id == board.id)
        )
        cells = list(
            session.scalars(
                select(ImageSymbolReviewCellModel).where(
                    ImageSymbolReviewCellModel.review_item_id == review.id
                )
            )
        )
        session.add(
            ImageBoardGeometryRevisionModel(
                review_item_id=review.id,
                recognized_board_id=board.id,
                revision=2,
                idempotency_key=uuid4(),
                command_sha256="e" * 64,
                corners=[
                    {"x": 0, "y": 0},
                    {"x": 10, "y": 0},
                    {"x": 10, "y": 10},
                    {"x": 0, "y": 10},
                ],
                geometry={},
                asset_mode="legacy_file",
                board_relative_path="exclusive.jpg",
                board_checksum_sha256="f" * 64,
                cropper_version="legacy-fixture",
                crop_artifacts=[{"cropRelativePath": "shared.jpg"}] * 15,
                corrected_by="fixture",
            )
        )

        def copy_values(row):
            return {
                column.key: getattr(row, column.key)
                for column in inspect(type(row)).columns
                if column.key != "id" and getattr(row, column.key) is not None
            }

        for sequence in range(3, 10):
            new_board = RecognizedBoardModel(
                **{
                    **copy_values(board),
                    "position_index": sequence - 1,
                    "sequence_number": sequence,
                    "sequence_number_raw": str(sequence),
                }
            )
            session.add(new_board)
            session.flush()
            new_review = ImageReviewItemModel(
                **{
                    **copy_values(review),
                    "recognized_board_id": new_board.id,
                    "sequence_number": sequence,
                    "snapshot": {"sequenceNumber": sequence},
                }
            )
            session.add(new_review)
            session.flush()
            for cell in cells:
                session.add(
                    ImageSymbolReviewCellModel(
                        **{
                            **copy_values(cell),
                            "recognized_board_id": new_board.id,
                            "review_item_id": new_review.id,
                            "sequence_number": sequence,
                        }
                    )
                )
        session.commit()
    original = tmp_path / "seq_1-9.jpg"
    original.write_bytes(b"owned old image pixels")
    with factory() as session:
        repo = SourceReplacementRepository(session)
        repo.bind(GAME_ID)
        sources = list(
            session.scalars(
                text(
                    "SELECT id FROM source_images WHERE game_id=:game AND "
                    "checksum_sha256=repeat('a',64)"
                ),
                {"game": GAME_ID},
            )
        )
        preview = repo.preview(GAME_ID, sources, mode="replace_delete_source")
        create = SourceReplacementCreateRequest(
            mode="replace_delete_source",
            source_ids=sources,
            idempotency_key=uuid4(),
            expected_revision=0,
            preview_token=preview["preview_token"],
        )
        manifest = repo.create(GAME_ID, create)
        assert manifest["entries"][0]["boards"] == []
        assert manifest["entries"][0]["reasons"]
        session.commit()
    batch, entry = UUID(manifest["id"]), UUID(manifest["entries"][0]["id"])
    preview_request = SourcePurgePreviewRequest(
        mode="replace_delete_source",
        action="purge",
        batch_id=batch,
        entry_id=entry,
        expected_revision=1,
    )
    with factory() as session:
        with pytest.raises(SourceReplacementError) as error:
            service(session, factory, tmp_path).physical_sources.preview(GAME_ID, preview_request)
        assert error.value.code == "SOURCE_REPLACEMENT_PURGE_IMPORT_UNFINISHED"
        assert original.exists()
        session.rollback()
    # Settling the import changes the planned dependency snapshot; create a fresh exact plan.
    with factory() as session:
        repo = SourceReplacementRepository(session)
        repo.bind(GAME_ID)
        session.execute(
            text("UPDATE public.jobs SET status='completed',finished_at=now() WHERE game_id=:game"),
            {"game": GAME_ID},
        )
        preview = repo.preview(GAME_ID, sources, mode="replace_delete_source")
        manifest = repo.create(
            GAME_ID,
            create.model_copy(
                update={"idempotency_key": uuid4(), "preview_token": preview["preview_token"]}
            ),
        )
        session.commit()
    batch, entry = UUID(manifest["id"]), UUID(manifest["entries"][0]["id"])
    preview_request = preview_request.model_copy(update={"batch_id": batch, "entry_id": entry})
    with factory() as session:
        cleanup = service(session, factory, tmp_path)
        import json
        from datetime import UTC, datetime

        from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
        from test_image_batch_store import PIPELINE, _image_job

        cleanup.replacement_plans.bind(GAME_ID)
        with session.begin_nested() as busy:
            active = SqlAlchemyJobRepository(session).add_job(
                _image_job(GAME_ID, PIPELINE, datetime.now(UTC))
            )
            session.execute(
                text(
                    "UPDATE public.jobs SET job_type='grid_training',"
                    "input_payload=CAST(:payload AS jsonb) "
                    "WHERE id=:id"
                ),
                {"id": active.id, "payload": json.dumps({"sourceId": str(sources[0])})},
            )
            with pytest.raises(SourceReplacementError) as error:
                cleanup.physical_sources.preview(GAME_ID, preview_request)
            assert error.value.code == "SOURCE_REPLACEMENT_PURGE_GRID_BUSY"
            assert original.exists()
            busy.rollback()
        preview = cleanup.physical_sources.preview(GAME_ID, preview_request)
        assert preview["file_count"] == 2 and preview["shared_file_count"] == 1
        assert preview["record_counts"]["boards"] == 9
        command = SourcePurgeCommand(
            **preview_request.model_dump(),
            idempotency_key=uuid4(),
            confirmed=True,
            preview_token=preview["preview_token"],
        )
        result = cleanup.physical_sources.execute(GAME_ID, command)
        assert not original.exists()
        assert not (tmp_path / "exclusive.jpg").exists()
        assert (tmp_path / "shared.jpg").read_bytes() == b"other game owns these pixels"
        assert (tmp_path / "neighbor.jpg").read_bytes() == b"neighbor in the same job"
        assert session.scalar(
            text("SELECT purged_at IS NULL FROM source_images WHERE game_id=:game AND id=:id"),
            {"game": GAME_ID, "id": neighbor_id},
        )
        session.rollback()
        cleanup.restore_uncommitted_artifacts()
        assert original.exists()
    with factory() as session:
        cleanup = service(session, factory, tmp_path)
        result = cleanup.physical_sources.execute(GAME_ID, command)
        session.commit()
        # Simulate successful COMMIT followed by lost acknowledgement and an exception restore.
        cleanup.restore_uncommitted_artifacts()
        assert original.exists()
    with factory() as session:
        cleanup = service(session, factory, tmp_path)
        view = cleanup.physical_sources.manifest(GAME_ID, batch)
        assert view["entries"][0]["purge"]["fileStatus"] == "recovery_pending"
        replay_command = SourcePurgeCommand.model_validate(view["entries"][0]["purge"]["command"])
        replay = cleanup.physical_sources.execute(GAME_ID, replay_command)
        assert replay["purge"]["fileStatus"] == "finalized"
        assert not original.exists()
        assert (
            session.scalar(
                text("SELECT count(*) FROM recognized_boards WHERE game_id=:game"),
                {"game": GAME_ID},
            )
            == 0
        )
        assert (
            session.scalar(
                text("SELECT count(*) FROM image_review_items WHERE game_id=:game"),
                {"game": GAME_ID},
            )
            == 0
        )
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM source_images WHERE game_id=:game AND "
                    "purged_at IS NOT NULL"
                ),
                {"game": GAME_ID},
            )
            == 2
        )
        exported = cleanup.replacement_plans.replacement_request(GAME_ID, batch, [entry])
        assert exported["entries"][0]["sequenceNumbers"] == list(range(1, 10))
        with pytest.raises(SourceReplacementError):
            require_active_sha(session, GAME_ID, "a" * 64)
        from game_predictor_api.domain.image_reviews import ImageReviewNotFoundError
        from game_predictor_api.storage.image_geometry_completeness_repository import (
            SqlAlchemyImageGeometryCompletenessRepository,
        )

        with pytest.raises(ImageReviewNotFoundError) as purged:
            SqlAlchemyImageGeometryCompletenessRepository(session).source_image_asset(
                GAME_ID, sources[0]
            )
        assert purged.value.code == "SOURCE_PURGED"
        assert result["scope_digest"] == replay["scope_digest"]
    _assert_new_admission(factory, exported)


def _add_shared_neighbors(factory):
    from datetime import UTC, datetime

    from game_predictor_api.storage.game_partition_lifecycle import (
        GamePartitionLifecycleKind,
        GamePartitionLifecycleRepository,
    )
    from game_predictor_api.storage.game_storage_routing import game_storage_scope
    from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
    from game_predictor_api.storage.models import SourceImageModel
    from game_predictor_worker.images.orchestration_store import SqlAlchemyImageBatchStore
    from test_image_batch_store import PIPELINE, _image_job

    other, now = uuid4(), datetime.now(UTC)
    with factory() as session:
        session.execute(
            text(
                "INSERT INTO public.games(id,code,name,status) "
                "VALUES(:id,:code,'Foreign fixture','active')"
            ),
            {"id": other, "code": "purge-" + other.hex},
        )
        lifecycle = GamePartitionLifecycleRepository(session)
        receipt = lifecycle.start_or_resume(
            game_id=other, kind=GamePartitionLifecycleKind.PROVISION
        )
        session.commit()
        for _ in range(250):
            receipt = lifecycle.run_next(receipt.operation_id)
            session.commit()
            if receipt.status == "done":
                break
        assert receipt.status == "done"
    with game_storage_scope(GAME_ID), factory() as session:
        job = session.scalar(text("SELECT import_job_id FROM source_images LIMIT 1"))
        session.execute(text("UPDATE public.jobs SET status='created' WHERE id=:job"), {"job": job})
        session.commit()
    ids = []
    for game, path, sha in ((GAME_ID, "neighbor.jpg", "c" * 64), (other, "shared.jpg", "d" * 64)):
        if game == other:
            with game_storage_scope(game), factory() as session:
                job = SqlAlchemyJobRepository(session).add_job(_image_job(game, PIPELINE, now)).id
                session.commit()
        execution = SqlAlchemyImageBatchStore(factory).register_file(
            job,
            source_checksum_sha256=sha,
            pipeline_fingerprint=PIPELINE,
            source_relative_path=path,
            order_index=1,
            registered_at=now,
        )
        with game_storage_scope(game), factory() as session:
            source = SourceImageModel(
                import_job_id=job,
                file_execution_key=execution.file_execution_key,
                relative_path=path,
                checksum_sha256=sha,
                width=100,
                height=100,
                status="completed",
                created_at=now,
            )
            session.add(source)
            session.flush()
            ids.append(source.id)
            if game == GAME_ID:
                session.execute(
                    text("UPDATE public.jobs SET status='waiting_for_review' WHERE id=:id"),
                    {"id": job},
                )
            session.commit()
    return ids[0]


def _assert_new_admission(factory, exported):
    from datetime import UTC, datetime

    from game_predictor_api.domain.image_sequence_canonical import (
        BrowserSequenceManifest,
        BrowserSequenceSource,
    )
    from game_predictor_api.domain.jobs import JobType, create_job
    from game_predictor_api.domain.symbol_readability import digest
    from game_predictor_api.storage.game_storage_routing import game_storage_scope
    from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
    from game_predictor_api.storage.models import SourceImageModel
    from game_predictor_api.storage.source_replacement_admission import (
        materialize_admission,
        validate_staging,
    )
    from game_predictor_api.storage.source_replacement_binding import admitted_source
    from game_predictor_worker.images.orchestration_store import SqlAlchemyImageBatchStore
    from test_image_batch_store import PIPELINE

    entry = exported["entries"][0]
    upload, new_sha = uuid4(), digest(str(uuid4()))
    selection = {
        "request": exported,
        "selectedEntryIds": [entry["entryId"]],
        "files": [
            {
                "entryId": entry["entryId"],
                "fileName": "seq_1-9.jpg",
                "checksumSha256": new_sha,
                "rangeStart": 1,
                "rangeEnd": 9,
                "operationId": str(uuid4()),
            }
        ],
    }
    manifest = BrowserSequenceManifest(
        (BrowserSequenceSource(0, "seq_1-9.jpg", "00000000.jpg", 100, new_sha, (1, 9)),),
        (),
        digest("new manifest"),
    )
    with game_storage_scope(GAME_ID), factory() as session:
        pin = validate_staging(
            session, game=GAME_ID, selection=selection, manifest=manifest, upload=upload
        )
        job = create_job(
            JobType.IMPORT,
            game_id=GAME_ID,
            input_payload={
                "schema_version": 2,
                "import_kind": "image_directory",
                "pipeline_fingerprint": PIPELINE,
                "source_selection_id": str(upload),
                "source_manifest_sha256": manifest.checksum_sha256,
                "source_replacement": pin,
            },
        )
        SqlAlchemyJobRepository(session).add_source_bound_job(job, source_selection_id=upload)
        session.commit()
    execution = SqlAlchemyImageBatchStore(factory).register_file(
        job.id,
        source_checksum_sha256=new_sha,
        pipeline_fingerprint=PIPELINE,
        source_relative_path="seq_1-9.jpg",
        order_index=0,
        registered_at=datetime.now(UTC),
    )
    with game_storage_scope(GAME_ID), factory() as session:
        source = SourceImageModel(
            import_job_id=job.id,
            file_execution_key=execution.file_execution_key,
            relative_path="seq_1-9.jpg",
            checksum_sha256=new_sha,
            width=100,
            height=100,
            status="processing",
            created_at=datetime.now(UTC),
        )
        session.add(source)
        session.flush()
        materialize_admission(session, game=GAME_ID, job=job.id, source=source)
        source_id = source.id
        session.commit()
    with game_storage_scope(GAME_ID), factory() as session:
        assert admitted_source(session, GAME_ID, source_id, job.id).sequences == tuple(range(1, 10))
        assert (
            session.scalar(
                text("SELECT count(*) FROM recognized_boards WHERE game_id=:game"),
                {"game": GAME_ID},
            )
            == 0
        )
