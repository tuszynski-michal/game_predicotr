"""Owned disposable database: admission survives restart and never reserves foreign pixels."""

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from game_predictor_api.domain.image_sequence_canonical import (
    BrowserSequenceManifest,
    BrowserSequenceSource,
)
from game_predictor_api.domain.jobs import JobType, create_job
from game_predictor_api.domain.source_replacement import SourceReplacementError
from game_predictor_api.domain.source_replacement_retirement import scope_digest
from game_predictor_api.domain.symbol_readability import GAME_ID, digest
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import SourceImageModel
from game_predictor_api.storage.sequence_ownership_lock import (
    SequenceOwnershipLockMode,
    acquire_sequence_ownership_lock,
)
from game_predictor_api.storage.source_replacement import SourceReplacementRepository
from game_predictor_api.storage.source_replacement_admission import (
    SEQUENCE_OWNERSHIP_BUSY,
    materialize_admission,
    validate_ordinary_staging,
    validate_staging,
)
from game_predictor_api.storage.source_replacement_binding import admitted_source
from game_predictor_worker.images.orchestration_store import SqlAlchemyImageBatchStore
from sqlalchemy import text
from test_image_batch_store import PIPELINE, _image_job
from test_source_replacement_postgres import database as database  # noqa: F401
from test_source_replacement_postgres import pytestmark as pytestmark


def seed(factory, start):
    now, batch, entry, upload = datetime.now(UTC), uuid4(), uuid4(), uuid4()
    old_sha, new_sha = digest(str(uuid4())), digest(str(uuid4()))
    with game_storage_scope(GAME_ID), factory() as session:
        old_job = SqlAlchemyJobRepository(session).add_job(_image_job(GAME_ID, PIPELINE, now))
        session.commit()
    execution = SqlAlchemyImageBatchStore(factory).register_file(
        old_job.id,
        source_checksum_sha256=old_sha,
        pipeline_fingerprint=PIPELINE,
        source_relative_path="old.jpg",
        order_index=0,
        registered_at=now,
    )
    with game_storage_scope(GAME_ID), factory() as session:
        source = SourceImageModel(
            import_job_id=old_job.id,
            file_execution_key=execution.file_execution_key,
            relative_path="old.jpg",
            checksum_sha256=old_sha,
            width=100,
            height=100,
            status="completed",
            created_at=now,
        )
        session.add(source)
        session.flush()
        planned = {
            "id": str(entry),
            "source_ids": [str(source.id)],
            "source_sha256": old_sha,
            "range_start": start,
            "range_end": start + 1,
            "sequence_numbers": [start, start + 1],
        }
        params = {
            "game": GAME_ID,
            "batch": batch,
            "entry": entry,
            "source": source.id,
            "sha": old_sha,
            "doc": json.dumps(planned),
            "batch_doc": json.dumps({"entries": [planned]}),
            "seq": [start, start + 1],
        }
        session.execute(
            text(
                "INSERT INTO "
                "source_replacement_batches(game_id,id,revision,status,preview_token,document) "
                "VALUES(:game,:batch,2,'gap_open',repeat('a',64),CAST(:batch_doc AS jsonb))"
            ),
            params,
        )
        session.execute(
            text(
                "INSERT INTO "
                "source_replacement_entries(game_id,id,batch_id,source_id,source_sha256,"
                "phase,revision,document) "
                "VALUES(:game,:entry,:batch,:source,:sha,'gap_open',2,CAST(:doc AS jsonb))"
            ),
            params,
        )
        session.execute(
            text(
                "INSERT INTO source_replacement_sources(game_id,entry_id,source_id) "
                "VALUES(:game,:entry,:source)"
            ),
            params,
        )
        session.execute(
            text(
                "INSERT INTO "
                "source_replacement_slots(game_id,sequence_number,entry_id,batch_id,"
                "state,revision,document) "
                "SELECT :game,n,:entry,:batch,'reserved',1,'{}' FROM unnest(CAST(:seq AS "
                "bigint[])) n"
            ),
            params,
        )
        session.execute(
            text("UPDATE public.jobs SET status='completed' WHERE id=:id"), {"id": old_job.id}
        )
        session.commit()
    request = {
        "schemaVersion": "source-replacement-request-v1",
        "gameId": str(GAME_ID),
        "batchId": str(batch),
        "entries": [
            {
                "entryId": str(entry),
                "revision": 2,
                "digest": scope_digest(planned),
                "sourceSha256": old_sha,
                "sequenceNumbers": [start, start + 1],
            }
        ],
        "allowedRanges": [
            {"entryId": str(entry), "sequenceStart": start, "sequenceEnd": start + 1}
        ],
    }
    request["digest"] = digest(request)
    name = f"seq_{start}-{start + 1}.jpg"
    selection = {
        "request": request,
        "selectedEntryIds": [str(entry)],
        "files": [
            {
                "entryId": str(entry),
                "fileName": name,
                "checksumSha256": new_sha,
                "rangeStart": start,
                "rangeEnd": start + 1,
                "operationId": str(uuid4()),
            }
        ],
    }
    manifest = BrowserSequenceManifest(
        (BrowserSequenceSource(0, name, "00000000.jpg", 100, new_sha, (start, start + 1)),),
        (),
        digest(name),
    )
    return batch, entry, upload, selection, manifest, old_job.id


def test_admission_atomic_job_discovery_restart_and_immutable_scope(database):  # noqa: F811
    factory = create_session_factory(database)
    batch, entry, upload, selection, manifest, _ = seed(factory, 1101)
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
        session.rollback()
    with game_storage_scope(GAME_ID), factory() as session:
        assert (
            session.scalar(
                text("SELECT phase FROM source_replacement_entries WHERE id=:id"), {"id": entry}
            )
            == "gap_open"
        )
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM source_replacement_slots WHERE entry_id=:id AND "
                    "new_sha256 IS NOT NULL"
                ),
                {"id": entry},
            )
            == 0
        )
        SqlAlchemyJobRepository(session).add_source_bound_job(job, source_selection_id=upload)
        session.commit()
    file = manifest.files[0]
    execution = SqlAlchemyImageBatchStore(factory).register_file(
        job.id,
        source_checksum_sha256=file.checksum_sha256,
        pipeline_fingerprint=PIPELINE,
        source_relative_path=file.relative_path,
        order_index=0,
        registered_at=datetime.now(UTC),
    )
    with game_storage_scope(GAME_ID), factory() as session:
        source = SourceImageModel(
            import_job_id=job.id,
            file_execution_key=execution.file_execution_key,
            relative_path=file.relative_path,
            checksum_sha256=file.checksum_sha256,
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
        source = session.get(SourceImageModel, source_id)
        materialize_admission(session, game=GAME_ID, job=job.id, source=source)
        with session.begin_nested() as changed:
            payload = session.scalar(
                text("SELECT input_payload FROM public.jobs WHERE id=:id"), {"id": job.id}
            )
            payload["source_replacement"]["files"][0]["sizeBytes"] += 1
            session.execute(
                text("UPDATE public.jobs SET input_payload=CAST(:doc AS jsonb) WHERE id=:id"),
                {"id": job.id, "doc": json.dumps(payload)},
            )
            with pytest.raises(SourceReplacementError) as error:
                materialize_admission(session, game=GAME_ID, job=job.id, source=source)
            assert error.value.code == "SOURCE_REPLACEMENT_ADMISSION_INVALID"
            changed.rollback()
        proof = admitted_source(session, GAME_ID, source_id, job.id)
        assert proof.sequences == (1101, 1102)
        assert (
            session.scalar(
                text("SELECT count(*) FROM source_replacement_sources WHERE entry_id=:entry"),
                {"entry": entry},
            )
            == 2
        )
        assert (
            SourceReplacementRepository(session).get(GAME_ID, batch)["entries"][0]["scope_digest"]
            == selection["request"]["entries"][0]["digest"]
        )
        session.execute(
            text("UPDATE public.jobs SET status='completed' WHERE id=:id"), {"id": job.id}
        )
        session.commit()


def test_foreign_unknown_range_new_sha_refuses_before_reservation(database):  # noqa: F811
    factory = create_session_factory(database)
    _, entry, upload, selection, manifest, old_job = seed(factory, 1201)
    file = manifest.files[0]
    with factory() as session:
        session.execute(
            text("UPDATE public.jobs SET status='created' WHERE id=:id"), {"id": old_job}
        )
        session.commit()
    execution = SqlAlchemyImageBatchStore(factory).register_file(
        old_job,
        source_checksum_sha256=file.checksum_sha256,
        pipeline_fingerprint=PIPELINE,
        source_relative_path="seq_1200-1200.jpg",
        order_index=1,
        registered_at=datetime.now(UTC),
    )
    with game_storage_scope(GAME_ID), factory() as session:
        session.add(
            SourceImageModel(
                import_job_id=old_job,
                file_execution_key=execution.file_execution_key,
                relative_path="seq_1200-1200.jpg",
                checksum_sha256=file.checksum_sha256,
                width=100,
                height=100,
                status="completed",
                created_at=datetime.now(UTC),
            )
        )
        session.commit()
    with game_storage_scope(GAME_ID), factory() as session:
        with pytest.raises(SourceReplacementError) as error:
            validate_staging(
                session, game=GAME_ID, selection=selection, manifest=manifest, upload=upload
            )
        assert error.value.code == "SOURCE_REPLACEMENT_SHA_SCOPE_CONFLICT"
        assert (
            session.scalar(
                text("SELECT phase FROM source_replacement_entries WHERE id=:id"), {"id": entry}
            )
            == "gap_open"
        )
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM source_replacement_slots WHERE entry_id=:id AND "
                    "new_sha256 IS NOT NULL"
                ),
                {"id": entry},
            )
            == 0
        )


@pytest.mark.parametrize(
    ("held", "requested", "busy"),
    [
        # TASK-1190: symbol-cell decisions hold SHARED; the report preview must coexist.
        (SequenceOwnershipLockMode.SHARED, SequenceOwnershipLockMode.SHARED, False),
        # Admission still waits for every holder and reports a readable conflict.
        (SequenceOwnershipLockMode.SHARED, SequenceOwnershipLockMode.EXCLUSIVE, True),
        (SequenceOwnershipLockMode.EXCLUSIVE, SequenceOwnershipLockMode.SHARED, True),
    ],
)
def test_ordinary_staging_lock_contention(database, held, requested, busy):  # noqa: F811
    factory = create_session_factory(database)
    manifest = BrowserSequenceManifest(files=(), warnings=(), checksum_sha256="a" * 64)
    with game_storage_scope(GAME_ID), factory() as holder, factory() as session:
        acquire_sequence_ownership_lock(holder, game_id=GAME_ID, mode=held)
        if busy:
            with pytest.raises(SourceReplacementError) as error:
                validate_ordinary_staging(
                    session, game=GAME_ID, manifest=manifest, lock_mode=requested
                )
            assert error.value.code == SEQUENCE_OWNERSHIP_BUSY
        else:
            validate_ordinary_staging(session, game=GAME_ID, manifest=manifest, lock_mode=requested)
        session.rollback()
        holder.rollback()
