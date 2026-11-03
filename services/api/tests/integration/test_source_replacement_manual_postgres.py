"""Real two-slot manual workflow with a reserved whole-photo admission."""

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from game_predictor_api.application.virtual_grid_geometry import VirtualGridGeometryService
from game_predictor_api.domain.symbol_readability import GAME_ID
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_review_repository import (
    SqlAlchemyOperationalImageReviewRepository,
)
from game_predictor_api.storage.models import SourceImageModel
from game_predictor_api.storage.source_replacement_binding import admitted_source
from game_predictor_api.storage.virtual_grid_geometry_repository import (
    SqlAlchemyVirtualGridGeometryRepository,
)
from sqlalchemy import text
from test_source_replacement_postgres import database as database  # noqa: F401
from test_source_replacement_postgres import pytestmark as pytestmark
from test_virtual_deferred_resolution_postgres import _pending_service, _points, _seed


def prepare_working(factory, artifact_root):
    old = _seed(
        factory, GAME_ID, artifact_root, label="old-manual-photo", slot_count=1, sequence_base=1900
    )
    new = _seed(
        factory, GAME_ID, artifact_root, label="new-working-photo", slot_count=2, sequence_base=2000
    )
    batch, entry = uuid4(), uuid4()
    with game_storage_scope(GAME_ID), factory() as session:
        old_source = session.get(SourceImageModel, old.source_image_id)
        new_source = session.get(SourceImageModel, new.source_image_id)
        planned = {
            "id": str(entry),
            "source_ids": [str(old.source_image_id)],
            "source_sha256": old_source.checksum_sha256,
            "range_start": 2000,
            "range_end": 2001,
            "sequence_numbers": [2000, 2001],
            "reasons": [{"sequence_number": 2000, "cell_index": 0}],
        }
        document = {
            **planned,
            "replacementStaging": {"importJobId": str(new.import_job_id)},
            "replacementAdmission": {
                "schemaVersion": "source-replacement-admission-v1",
                "gameId": str(GAME_ID),
                "batchId": str(batch),
                "entryId": str(entry),
                "sourceId": str(new.source_image_id),
                "importJobId": str(new.import_job_id),
                "sourceSha256": new_source.checksum_sha256,
                "entryRevision": 1,
                "sequenceNumbers": [2000, 2001],
            },
        }
        params = {
            "game": GAME_ID,
            "batch": batch,
            "entry": entry,
            "old": old.source_image_id,
            "source": new.source_image_id,
            "sha": old_source.checksum_sha256,
            "newsha": new_source.checksum_sha256,
            "doc": json.dumps(document),
            "planned": json.dumps({"entries": [planned]}),
        }
        session.execute(
            text(
                "INSERT INTO "
                "source_replacement_batches(game_id,id,revision,status,preview_token,document) "
                "VALUES(:game,:batch,1,'importing',repeat('a',64),CAST(:planned AS jsonb))"
            ),
            params,
        )
        session.execute(
            text(
                "INSERT INTO "
                "source_replacement_entries(game_id,id,batch_id,source_id,source_sha256,"
                "phase,document) "
                "VALUES(:game,:entry,:batch,:old,:sha,'importing',CAST(:doc AS jsonb))"
            ),
            params,
        )
        session.execute(
            text(
                "INSERT INTO source_replacement_sources(game_id,entry_id,source_id) "
                "VALUES(:game,:entry,:old),(:game,:entry,:source)"
            ),
            params,
        )
        session.execute(
            text(
                "INSERT INTO "
                "source_replacement_retired(game_id,source_id,entry_id,source_sha256,document) "
                "VALUES(:game,:old,:entry,:sha,'{}')"
            ),
            params,
        )
        session.execute(
            text(
                "INSERT INTO "
                "source_replacement_slots(game_id,sequence_number,entry_id,batch_id,state,"
                "new_source_id,new_sha256,revision,document) "
                "SELECT :game,n,:entry,:batch,'reserved',:source,:newsha,1,'{}' FROM "
                "unnest(ARRAY[2000,2001]) n"
            ),
            params,
        )
        session.commit()
    return new, batch, entry


def resolve_slot(session, root, seed, index, key):
    return _pending_service(session, root).resolve_manual(
        seed.pending_ids[index],
        game_id=GAME_ID,
        import_job_id=seed.import_job_id,
        expected_manifest_checksum_sha256=seed.manifest_checksums[index],
        idempotency_key=key,
        expected_geometry_revision=0,
        expected_resolution_revision=0,
        corners=_points(),
        corrected_by="reviewer",
        resolved_at=datetime.now(UTC),
    )


def test_repeated_manual_provisional_keeps_one_review_and_binds_entire_photo(database, tmp_path):  # noqa: F811
    factory = create_session_factory(database)
    seed, batch, entry = prepare_working(factory, tmp_path)
    key = uuid4()
    with game_storage_scope(GAME_ID), factory() as session:
        first = resolve_slot(session, tmp_path, seed, 0, key)
        first_id = first.review_item_id
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM source_replacement_slots WHERE entry_id=:entry "
                    "AND state='pending_bound'"
                ),
                {"entry": entry},
            )
            == 0
        )
        session.commit()
    with game_storage_scope(GAME_ID), factory() as session:
        replay = resolve_slot(session, tmp_path, seed, 0, key)
        assert not replay.created and replay.review_item_id == first_id
        assert (
            SqlAlchemyOperationalImageReviewRepository(session).get_item(
                first_id, game_id=GAME_ID, import_job_id=seed.import_job_id
            )
            is not None
        )
        service = VirtualGridGeometryService(
            SqlAlchemyVirtualGridGeometryRepository(session), tmp_path
        )
        service.save_review_item(
            game_id=GAME_ID,
            import_job_id=seed.import_job_id,
            review_item_id=first_id,
            idempotency_key=uuid4(),
            expected_geometry_revision=1,
            expected_resolution_revision=0,
            corners=_points(),
            actor="reviewer",
            created_at=datetime.now(UTC),
        )
        assert (
            session.scalar(
                text("SELECT count(*) FROM image_review_items WHERE import_job_id=:job"),
                {"job": seed.import_job_id},
            )
            == 1
        )
        session.commit()
    with game_storage_scope(GAME_ID), factory() as session:
        resolve_slot(session, tmp_path, seed, 1, uuid4())
        assert (
            admitted_source(session, GAME_ID, seed.source_image_id, seed.import_job_id) is not None
        )
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM source_replacement_slots WHERE entry_id=:entry "
                    "AND state='pending_bound'"
                ),
                {"entry": entry},
            )
            == 2
        )
        assert (
            session.scalar(
                text("SELECT count(*) FROM image_review_items WHERE import_job_id=:job"),
                {"job": seed.import_job_id},
            )
            == 2
        )
        session.commit()
    verify_restore(factory, seed, batch, entry)
    with game_storage_scope(GAME_ID), factory() as session:
        repo = SqlAlchemyOperationalImageReviewRepository(session)
        winner = repo.get_item(first_id, game_id=GAME_ID, import_job_id=seed.import_job_id)
        result = VirtualGridGeometryService(
            SqlAlchemyVirtualGridGeometryRepository(session), tmp_path
        ).save_review_item(
            game_id=GAME_ID,
            import_job_id=seed.import_job_id,
            review_item_id=first_id,
            idempotency_key=uuid4(),
            expected_geometry_revision=winner.geometry_revision,
            expected_resolution_revision=winner.resolution_revision,
            corners=_points(),
            actor="reviewer-after-restored",
            created_at=datetime.now(UTC),
        )
        assert result.created
        session.commit()


def verify_restore(factory, seed, batch, entry, *, before_restore=None):
    from game_predictor_api.application.image_reviews import OperationalImageReviewService
    from game_predictor_api.domain.image_reviews import ImageReviewAction, ImageReviewResolutionCell
    from game_predictor_api.domain.source_replacement import SourceReplacementError
    from game_predictor_api.schemas.source_replacement import SourceReplacementRestoreCommand
    from game_predictor_api.storage.models import (
        ImageBoardGeometryPendingModel,
        ImageReviewItemModel,
        RecognizedBoardModel,
        SymbolModel,
    )
    from game_predictor_api.storage.source_replacement import SourceReplacementRepository
    from game_predictor_api.storage.source_replacement_admission import require_open_admission
    from game_predictor_api.storage.source_replacement_restore import SourceReplacementRestore

    with game_storage_scope(GAME_ID), factory() as session:
        session.add(
            SymbolModel(
                game_id=GAME_ID, mobile_code=1, code="CYTRYNA", name="Cytryna", display_order=0
            )
        )
        session.flush()
        repo = SqlAlchemyOperationalImageReviewRepository(session)
        ids = (
            session.execute(
                text(
                    "SELECT id FROM image_review_items WHERE import_job_id=:job ORDER BY "
                    "sequence_number"
                ),
                {"job": seed.import_job_id},
            )
            .scalars()
            .all()
        )
        assert (
            session.scalar(
                text("SELECT count(*) FROM image_review_queue_items WHERE import_job_id=:job"),
                {"job": seed.import_job_id},
            )
            == 2
        )
        service = OperationalImageReviewService(repo)
        for index, review in enumerate(ids):
            item = repo.get_item(review, game_id=GAME_ID, import_job_id=seed.import_job_id)
            service.resolve_item(
                review,
                game_id=GAME_ID,
                import_job_id=seed.import_job_id,
                idempotency_key=uuid4(),
                expected_revision=item.resolution_revision,
                action=ImageReviewAction.CORRECTED,
                sequence_number=2000 + index,
                geometry_revision=item.geometry_revision,
                cells=tuple(
                    ImageReviewResolutionCell(c.cell_index, c.crop_sample_id, "CYTRYNA")
                    for c in item.cells
                ),
                rejection_reason=None,
                resolved_by="reviewer",
            )
            if index == 0:
                assert not SourceReplacementRestore(SourceReplacementRepository(session)).working(
                    GAME_ID, batch, entry
                )["ready_to_restore"]
        session.commit()
    with game_storage_scope(GAME_ID), factory() as session:
        restore = SourceReplacementRestore(SourceReplacementRepository(session))
        view = restore.working(GAME_ID, batch, entry)
        assert view["ready_to_restore"] and len(view["readability"]) == 1
        if before_restore is not None:
            before_restore(session)
        # Persisted orphan from an interrupted historical attempt: unknown seq,
        # no binding and no canonical. Closing the entry must not expose it.
        template = session.get(
            RecognizedBoardModel, session.get(ImageReviewItemModel, ids[0]).recognized_board_id
        )
        values = {
            column.key: getattr(template, column.key)
            for column in RecognizedBoardModel.__table__.columns
            if column.key
            not in {"id", "position_index", "sequence_number", "sequence_number_raw", "status"}
        }
        orphan_board = RecognizedBoardModel(
            **values,
            position_index=2,
            sequence_number=None,
            sequence_number_raw="?",
            status="pending_review",
        )
        session.add(orphan_board)
        session.flush()
        orphan = ImageReviewItemModel(
            game_id=GAME_ID,
            import_job_id=seed.import_job_id,
            recognized_board_id=orphan_board.id,
            sequence_number=None,
            status="pending",
            snapshot={},
            resolution_revision=0,
        )
        session.add(orphan)
        orphan_pending = ImageBoardGeometryPendingModel(
            game_id=GAME_ID,
            import_job_id=seed.import_job_id,
            source_image_id=seed.source_image_id,
            position_index=2,
            sequence_number=2002,
            source_checksum_sha256=session.get(
                SourceImageModel, seed.source_image_id
            ).checksum_sha256,
            source_relative_path="orphan",
            status="pending",
            reason_code="incomplete_lattice",
            processing_manifest_checksum_sha256="e" * 64,
            processing_manifest_relative_path="orphan.json",
            pipeline_fingerprint_sha256="f" * 64,
            expected_geometry_revision=0,
            expected_review_resolution_revision=0,
        )
        session.add(orphan_pending)
        session.flush()
        orphan_id, orphan_pending_id = orphan.id, orphan_pending.id
        session.commit()
    with game_storage_scope(GAME_ID), factory() as session:
        restore = SourceReplacementRestore(SourceReplacementRepository(session))
        view = restore.working(GAME_ID, batch, entry)
        args = dict(
            batch_id=batch,
            entry_id=entry,
            expected_revision=view["revision"],
            idempotency_key=uuid4(),
            confirmed=True,
            actor="reviewer",
            readability=[{**c, "readable": True} for c in view["readability"]],
        )
        # Only the explicit identity/revision fields belong to the command.
        args["readability"] = [
            {k: c[k] for k in ("cell_id", "identity", "revision", "readable")}
            for c in args["readability"]
        ]
        command = SourceReplacementRestoreCommand(**args)
        stale = command.model_copy(update={"expected_revision": view["revision"] + 1})
        with pytest.raises(SourceReplacementError):
            restore.restore(GAME_ID, stale)
        assert (
            session.scalar(
                text("SELECT count(*) FROM source_replacement_slots WHERE entry_id=:id"),
                {"id": entry},
            )
            == 2
        )
        result = restore.restore(GAME_ID, command)
        session.rollback()
    with game_storage_scope(GAME_ID), factory() as session:
        restore = SourceReplacementRestore(SourceReplacementRepository(session))
        assert restore.restore(GAME_ID, command) == result
        session.commit()
    with game_storage_scope(GAME_ID), factory() as session:
        restore = SourceReplacementRestore(SourceReplacementRepository(session))
        assert restore.restore(GAME_ID, command) == result
        assert (
            session.scalar(
                text("SELECT count(*) FROM source_replacement_slots WHERE entry_id=:id"),
                {"id": entry},
            )
            == 0
        )
        assert (
            session.scalar(
                text("SELECT count(*) FROM source_replacement_sources WHERE entry_id=:id"),
                {"id": entry},
            )
            == 2
        )
        assert session.get(ImageReviewItemModel, orphan_id).status == "superseded"
        assert session.get(ImageBoardGeometryPendingModel, orphan_pending_id).status == "superseded"
        from game_predictor_api.storage.source_replacement_guards import require_current_review

        with pytest.raises(SourceReplacementError):
            require_current_review(session, GAME_ID, orphan_id)
        for winner in ids:
            require_current_review(session, GAME_ID, winner)
        from game_predictor_api.storage.source_replacement_guards import require_sequence_binding

        for review in (None, orphan_id):
            with pytest.raises(SourceReplacementError):
                require_sequence_binding(
                    session, game=GAME_ID, source=seed.source_image_id, sequence=2000, review=review
                )
        assert (
            session.scalar(
                text(
                    "SELECT public.source_replacement_source_current_v1(:game,id,checksum_sha256) "
                    "FROM source_images WHERE id=:source"
                ),
                {"game": GAME_ID, "source": seed.source_image_id},
            )
            is True
        )
        direct = session.scalar(
            text(
                "SELECT "
                "public.source_replacement_current_v1(:game,id,checksum_sha256,2000,:review) "
                "FROM source_images WHERE id=:source"
            ),
            {"game": GAME_ID, "source": seed.source_image_id, "review": orphan_id},
        )
        assert direct is False
        assert not session.scalar(
            text("SELECT EXISTS(SELECT 1 FROM image_sequence_canonical WHERE review_item_id=:id)"),
            {"id": orphan_id},
        )
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM image_review_queue_items WHERE "
                    "review_item_id=:id AND status='pending'"
                ),
                {"id": orphan_id},
            )
            == 0
        )
        with pytest.raises(SourceReplacementError) as error:
            require_open_admission(session, game=GAME_ID, job=seed.import_job_id)
        assert error.value.code == "SOURCE_REPLACEMENT_ADMISSION_CLOSED"
