"""Disposable DB only: migration, lost response and source checkpoint recovery."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np
import pytest
from _recording_capability_fixture import OwnedRecordingCapability
from alembic import command
from alembic.config import Config
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.jobs import JobExecutionSlot
from game_predictor_api.domain.symbol_readability import (
    GAME_ID,
    ReadabilityWorkflowError,
    crop_identity,
)
from game_predictor_api.schemas.symbol_readability import ReadabilityStartRequest
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_partition_lifecycle import (
    GamePartitionLifecycleKind,
    GamePartitionLifecycleRepository,
)
from game_predictor_api.storage.symbol_readability import SqlAlchemyReadabilityRepository
from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore
from game_predictor_worker.symbols import readability_workflow as workflow
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Disposable PostgreSQL test opt-in.",
)
ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(scope="module")
def database():
    original = make_url(ApiSettings.from_environment().owner_database_url)
    name = f"game_predictor_task1125_readability_{uuid4().hex[:8]}"
    assert re.fullmatch(r"game_predictor_task1125_readability_[0-9a-f]{8}", name)
    assert name != original.database and name not in {"postgres", "game_predictor"}
    url = original.set(database=name)
    maintenance = create_engine(
        original.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5},
    )
    owned = OwnedRecordingCapability(url)
    created = False
    engine = None
    print(f"Disposable readability database: {name}", flush=True)
    try:
        with maintenance.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
            created = True
            owned.record_created_database(connection)
            owned.provision()
        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option(
            "sqlalchemy.url", url.render_as_string(hide_password=False).replace("%", "%%")
        )
        command.upgrade(config, "head")
        engine = create_engine(url, connect_args={"connect_timeout": 5})
        with engine.begin() as connection:
            assert connection.scalar(text("SELECT current_database()")) == name
            connection.execute(
                text(
                    "INSERT INTO public.games(id,code,name,status) "
                    "VALUES(:game,'777a2','Fixture','active')"
                ),
                {"game": GAME_ID},
            )
        with Session(engine) as session:
            lifecycle = GamePartitionLifecycleRepository(session)
            receipt = lifecycle.start_or_resume(
                game_id=GAME_ID, kind=GamePartitionLifecycleKind.PROVISION
            )
            session.commit()
            for _ in range(250):
                receipt = lifecycle.run_next(receipt.operation_id)
                session.commit()
                if receipt.status == "done":
                    break
            assert receipt.status == "done"
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with maintenance.connect() as connection:
                owned.assert_database_identity(connection)
                connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
                owned.cleanup(connection)
        maintenance.dispose()


def test_migration_and_lost_start_response_are_durable(database):
    request = ReadabilityStartRequest(idempotency_key=uuid4(), kind="pilot")
    with Session(database) as session:
        result = SqlAlchemyReadabilityRepository(session).start(GAME_ID, request)
        session.commit()
    with Session(database) as session:
        retry = SqlAlchemyReadabilityRepository(session).start(GAME_ID, request)
        session.commit()
        assert str(result["id"]) == str(retry["id"])
        assert (
            session.scalar(
                text("SELECT count(*) FROM public.jobs WHERE job_type::text='symbol_readability'")
            )
            == 1
        )
        with pytest.raises(ReadabilityWorkflowError, match="Klucz"):
            SqlAlchemyReadabilityRepository(session).start(
                GAME_ID, request.model_copy(update={"seed": "changed"})
            )
        session.rollback()
    with Session(database) as session:
        repo = SqlAlchemyReadabilityRepository(session)
        with pytest.raises(ReadabilityWorkflowError) as caught:
            repo.start(GAME_ID, ReadabilityStartRequest(idempotency_key=uuid4(), kind="scan"))
        assert caught.value.code == "READABILITY_MODEL_REQUIRED"


def test_restart_after_committed_source_does_not_decode_or_score_it_again(
    database, monkeypatch, tmp_path
):
    factory = create_session_factory(database)
    # Reuse the only created job from the previous lost-response test.
    store = SqlAlchemyWorkerJobStore(factory)
    now = datetime.now(UTC)
    job = store.claim_next(
        worker_id="quality-fixture",
        worker_version="test",
        lease_duration=timedelta(minutes=5),
        claimed_at=now,
        execution_slot=JobExecutionSlot.GENERAL,
    )
    assert job is not None
    from game_predictor_worker.symbols.readability_features import FrozenBase, ReadabilityError

    with pytest.raises(ReadabilityError) as stopped:
        workflow.ReadabilityHandler(factory, tmp_path).inventory(
            job,
            UUID(str(job.input_payload["identifier"])),
            FrozenBase("c", "d", "s", ("x", "y"), ()),
        )
    assert stopped.value.code == "READABILITY_PILOT_STOP"
    run_id = UUID(str(job.input_payload["identifier"]))
    source = uuid4()
    rows = []
    for i in range(135):
        cell = uuid4()
        row = dict(
            cell_id=str(cell),
            source_id=str(source),
            source_sha256="a" * 64,
            source_path="source.jpg",
            normalized_pixel_checksum_sha256="b" * 64,
            recognized_board_id=str(uuid4()),
            review_item_id=str(uuid4()),
            import_job_id=str(uuid4()),
            sequence_number=i // 15 + 1,
            cell_index=i % 15,
            row_index=i % 15 // 5,
            column_index=i % 5,
            geometry_revision=0,
            board_geometry_revision=0,
            source_geometry_revision_id=str(source),
            board_source_geometry_revision_id=str(source),
            asset_mode="virtual_source",
            source_visibility="full",
            board_status="accepted",
            render_spec_checksum_sha256="c" * 64,
            rendered_pixel_checksum_sha256="d" * 64,
            render_identity_v2_sha256="e" * 64,
            crop_sample_id="f" * 64,
            crop_checksum_sha256="d" * 64,
            logical_cell_key="1" * 64,
            logical_cell_key_v2="2" * 64,
            extractor_version="fixture",
            symbol_class="test",
        )
        rows.append(row)
    with factory() as session, session.begin():
        repo = SqlAlchemyReadabilityRepository(session)
        repo.bind(GAME_ID, write=True)
        session.execute(
            text(
                "UPDATE symbol_readability_runs SET "
                "item_count=135,inventory_fingerprint=:sha WHERE game_id=:game "
                "AND id=:run"
            ),
            {"game": GAME_ID, "run": run_id, "sha": "a" * 64},
        )
        session.execute(
            text("""INSERT INTO symbol_readability_items(game_id,run_id,cell_id,source_id,
          sequence_number,cell_index,snapshot,identity,sample_kind,historical_unreadable)
          VALUES(:game,:run,:cell,:source,:seq,:index,CAST(:snapshot AS
jsonb),:identity,'pilot',false)"""),
            [
                dict(
                    game=GAME_ID,
                    run=run_id,
                    cell=row["cell_id"],
                    source=source,
                    seq=row["sequence_number"],
                    index=row["cell_index"],
                    snapshot=json.dumps(row),
                    identity=crop_identity(row),
                )
                for row in rows
            ],
        )
    by_id = {row["cell_id"]: row for row in rows}
    monkeypatch.setattr(
        SqlAlchemyReadabilityRepository,
        "current",
        lambda self, game, cell, lock=False: by_id[str(cell)],
    )
    monkeypatch.setattr(
        workflow, "load_cell_render_specs", lambda session, game_id, keys: {key: {} for key in keys}
    )
    monkeypatch.setattr(
        workflow,
        "render_persisted_virtual_cell_rgb",
        lambda *a, **k: np.zeros((2, 2, 3), dtype=np.uint8),
    )
    calls = []

    class Loader:
        def __init__(self, **kw):
            pass

        def load(self, *a, **kw):
            calls.append("decode")
            return type(
                "Frame",
                (),
                {"source": type("Source", (), {"normalized_pixel_checksum_sha256": "b" * 64})()},
            )()

        def clear(self):
            calls.append("clear")

    monkeypatch.setattr(workflow, "CanonicalSourceLoader", Loader)
    monkeypatch.setattr(
        workflow, "extract_features", lambda model, crops: np.zeros((len(crops), 1032))
    )

    class LostResponse:
        def checkpoint(
            self,
            *,
            checkpoint_payload,
            stage,
            current,
            total,
            success_count,
            failure_count,
            review_count,
        ):
            assert (current, total, success_count, failure_count, review_count) == (
                135,
                135,
                135,
                0,
                0,
            )
            raise ConnectionError("response lost after source commit")

    handler = workflow.ReadabilityHandler(factory, tmp_path)
    with pytest.raises(ConnectionError):
        handler.process(LostResponse(), job, run_id, None, object())
    assert calls == ["decode", "clear"]

    with factory() as session, session.begin():
        repo = SqlAlchemyReadabilityRepository(session)
        repo.bind(GAME_ID)
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM symbol_readability_items WHERE "
                    "game_id=:game AND run_id=:run AND processed"
                ),
                {"game": GAME_ID, "run": run_id},
            )
            == 135
        )

    class Context:
        def checkpoint(self, **kw):
            pass

    # A new handler/session represents restart; persisted target rows are the checkpoint.
    workflow.ReadabilityHandler(factory, tmp_path).process(Context(), job, run_id, None, object())
    assert calls == ["decode", "clear"]
    with factory() as session, session.begin():
        repo = SqlAlchemyReadabilityRepository(session)
        repo.bind(GAME_ID, write=True)
        session.execute(
            text(
                "UPDATE symbol_readability_items SET "
                "processed=false,state='pending' WHERE game_id=:game AND "
                "run_id=:run"
            ),
            {"game": GAME_ID, "run": run_id},
        )
        session.execute(
            text(
                "UPDATE symbol_readability_runs SET "
                "processed_count=0,receipt='{}' WHERE game_id=:game AND id=:run"
            ),
            {"game": GAME_ID, "run": run_id},
        )
    broken_calls = []

    class BrokenLoader:
        def __init__(self, **kw):
            pass

        def load(self, *a, **kw):
            broken_calls.append("decode")
            raise workflow.CanonicalSourceLoadError("READABILITY_FIXTURE_CORRUPT", "broken source")

        def clear(self):
            broken_calls.append("clear")

    monkeypatch.setattr(workflow, "CanonicalSourceLoader", BrokenLoader)
    workflow.ReadabilityHandler(factory, tmp_path).process(Context(), job, run_id, None, object())
    assert broken_calls == ["decode", "clear"]
    with factory() as session, session.begin():
        repo = SqlAlchemyReadabilityRepository(session)
        repo.bind(GAME_ID)
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM symbol_readability_items WHERE "
                    "game_id=:game AND run_id=:run AND state='error'"
                ),
                {"game": GAME_ID, "run": run_id},
            )
            == 135
        )


def test_unreadable_uses_real_mutation_once_readable_preserves_issue_and_geometry_drift_is_stale(
    database,
):
    from game_predictor_api.domain.jobs import JobStatus
    from game_predictor_api.schemas.symbol_readability import ReadabilityLabelRequest
    from game_predictor_api.storage.board_search_projection_repository import (
        SqlAlchemyBoardSearchProjectionRepository,
    )
    from game_predictor_api.storage.game_storage_routing import game_storage_scope
    from game_predictor_api.storage.image_symbol_review_repository import (
        SqlAlchemyImageSymbolReviewRepository,
    )
    from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
    from game_predictor_api.storage.models import JobModel
    from game_predictor_worker.images.orchestration_store import SqlAlchemyImageBatchStore
    from test_image_batch_store import PIPELINE, _add_review_projection_source, _image_job

    factory = create_session_factory(database)
    now = datetime.now(UTC)
    with factory() as session, session.begin():
        session.execute(
            text(
                "INSERT INTO "
                "public.symbols(id,game_id,mobile_code,code,name,is_wildcard,displ"
                "ay_order,status) "
                "VALUES(:id,:game,1,'test','Test',false,0,'active')"
            ),
            {"id": uuid4(), "game": GAME_ID},
        )
        job = SqlAlchemyJobRepository(session).add_job(_image_job(GAME_ID, PIPELINE, now))
    execution = SqlAlchemyImageBatchStore(factory).register_file(
        job.id,
        source_checksum_sha256="1" * 64,
        pipeline_fingerprint=PIPELINE,
        source_relative_path="readability-fixture.jpg",
        order_index=0,
        registered_at=now,
    )
    with game_storage_scope(GAME_ID), factory() as session, session.begin():
        _add_review_projection_source(
            session,
            job_id=job.id,
            file_execution_key=execution.file_execution_key,
            source_checksum="1" * 64,
            source_name="readability-fixture.jpg",
            position_index=0,
            sequence_number=100,
            status="pending",
            created_at=now,
        )
        session.get(JobModel, job.id).status = JobStatus.WAITING_FOR_REVIEW
        SqlAlchemyBoardSearchProjectionRepository(session).rebuild_game(GAME_ID)
    with game_storage_scope(GAME_ID), factory() as session, session.begin():
        backfill = SqlAlchemyImageSymbolReviewRepository(session)
        backfill.start_or_resume_backfill(GAME_ID)
        assert not backfill.backfill_next_batch(GAME_ID, batch_size=50).has_more
        assert backfill.backfill_next_batch(GAME_ID, batch_size=50).report.status == "ready"
        repo = SqlAlchemyReadabilityRepository(session)
        run = repo.start(GAME_ID, ReadabilityStartRequest(idempotency_key=uuid4(), kind="pilot"))
        cell = session.scalar(
            text(
                "SELECT id FROM image_symbol_review_cells WHERE game_id=:game "
                "ORDER BY cell_index LIMIT 1"
            ),
            {"game": GAME_ID},
        )
        row = repo.current(GAME_ID, cell)
        identity = crop_identity(row)
        initial_revision = row["revision"]
        session.execute(
            text("""INSERT INTO symbol_readability_items(game_id,run_id,cell_id,source_id,
          sequence_number,cell_index,snapshot,identity,sample_kind,historical_unreadable,processed)
          VALUES(:game,:run,:cell,:source,100,0,CAST(:snapshot AS
jsonb),:identity,'pilot',false,true)"""),
            dict(
                game=GAME_ID,
                run=run["id"],
                cell=cell,
                source=row["source_id"],
                snapshot=json.dumps(row),
                identity=identity,
            ),
        )
    request = ReadabilityLabelRequest(
        idempotency_key=uuid4(),
        targets=[dict(cell_id=cell, expected_identity=identity, expected_revision=0)],
        state="unreadable",
        overlap=True,
    )
    for _ in range(2):
        with factory() as session, session.begin():
            SqlAlchemyReadabilityRepository(session).label(GAME_ID, run["id"], request)
    with factory() as session, session.begin():
        repo = SqlAlchemyReadabilityRepository(session)
        page = repo.page(GAME_ID, run["id"])
        assert page["items"][0]["state"] == "unreadable"
        assert page["confirmed_fields"] == 1
        current = repo.current(GAME_ID, cell)
        assert current["revision"] == initial_revision + 1
        assert current["quality_issue"] == "unreadable"
        assert crop_identity(current) == identity
        readable = request.model_copy(
            update={
                "idempotency_key": uuid4(),
                "state": "readable",
                "targets": [request.targets[0].model_copy(update={"expected_revision": 1})],
            }
        )
        repo.label(GAME_ID, run["id"], readable)
        assert repo.current(GAME_ID, cell)["quality_issue"] == "unreadable"
        assert repo.page(GAME_ID, run["id"])["confirmed_fields"] == 0
        session.execute(
            text(
                "UPDATE recognized_boards SET "
                "geometry_revision=geometry_revision+1 WHERE game_id=:game AND "
                "id=:board"
            ),
            {"game": GAME_ID, "board": row["recognized_board_id"]},
        )
    with factory() as session, session.begin():
        repo = SqlAlchemyReadabilityRepository(session)
        assert repo.page(GAME_ID, run["id"])["items"][0]["state"] == "stale"
        with pytest.raises(ReadabilityWorkflowError) as caught:
            repo.label(
                GAME_ID,
                run["id"],
                readable.model_copy(
                    update={
                        "idempotency_key": uuid4(),
                        "targets": [request.targets[0].model_copy(update={"expected_revision": 2})],
                    }
                ),
            )
        assert caught.value.code == "READABILITY_CROP_STALE"


def test_bounded_scan_inventory_survives_lost_checkpoint_and_includes_approved(
    database, tmp_path, monkeypatch
):
    factory = create_session_factory(database)
    with factory() as session, session.begin():
        repo = SqlAlchemyReadabilityRepository(session)
        repo.bind(GAME_ID, write=True)
        # The previous test deliberately drifted this board. Restore its current revision;
        # this is an isolated fixture, never the operator database.
        session.execute(
            text(
                "UPDATE recognized_boards SET "
                "geometry_revision=geometry_revision-1 WHERE game_id=:game AND "
                "sequence_number=100"
            ),
            {"game": GAME_ID},
        )
        pilot = repo.start(GAME_ID, ReadabilityStartRequest(idempotency_key=uuid4(), kind="pilot"))
        model = uuid4()
        session.execute(
            text(
                "INSERT INTO "
                "symbol_readability_models(game_id,id,pilot_run_id,"
                "pilot_revision,"
                "job_id,status,fingerprint,artifact_path,accepted,report) "
                "VALUES(:game,:id,:run,0,:job,'completed',:sha,'data/readability/f"
                'ixture.json\',false,\'{"status":"PA'
                "SS\"}')"
            ),
            dict(game=GAME_ID, id=model, run=pilot["id"], job=pilot["job_id"], sha="a" * 64),
        )
        from game_predictor_api.schemas.symbol_readability import ReadabilityCommandRequest

        with session.begin_nested():
            with pytest.raises(ReadabilityWorkflowError) as blocked:
                repo.start(
                    GAME_ID,
                    ReadabilityStartRequest(idempotency_key=uuid4(), kind="scan", model_id=model),
                )
            assert blocked.value.code == "READABILITY_ACCEPTANCE_REQUIRED"
        accepted = repo.accept(
            GAME_ID, model, ReadabilityCommandRequest(idempotency_key=uuid4(), expected_revision=0)
        )
        assert accepted["accepted"] and accepted["report"]["fullScanAllowed"] is True
        run = repo.start(
            GAME_ID, ReadabilityStartRequest(idempotency_key=uuid4(), kind="scan", model_id=model)
        )
        # A claim-shaped fixture bound to the real durable job row.
        session.execute(
            text(
                "UPDATE public.jobs SET status='cancelled',finished_at=now() "
                "WHERE game_id=:game AND status='created' AND id<>:job"
            ),
            {"game": GAME_ID, "job": run["job_id"]},
        )
    store = SqlAlchemyWorkerJobStore(factory)
    job = store.claim_next(
        worker_id="scan-fixture",
        worker_version="test",
        lease_duration=timedelta(minutes=5),
        claimed_at=datetime.now(UTC),
        execution_slot=JobExecutionSlot.GENERAL,
    )
    # Finish the former source fixture lease before the scan claim when it still occupies the slot.
    if job is None:
        with factory() as session, session.begin():
            session.execute(
                text(
                    "UPDATE public.jobs SET "
                    "status='cancelled',finished_at=now(),execution_slot=NULL,lease_ow"
                    "ner=NULL,lease_token=NULL,lease_expires_at=NULL,heartbeat_at=NULL"
                    " WHERE game_id=:game AND status='processing'"
                ),
                {"game": GAME_ID},
            )
        job = store.claim_next(
            worker_id="scan-fixture",
            worker_version="test",
            lease_duration=timedelta(minutes=5),
            claimed_at=datetime.now(UTC),
            execution_slot=JobExecutionSlot.GENERAL,
        )
    assert job is not None and str(job.id) == str(run["job_id"])

    class Lost:
        def checkpoint(self, **kw):
            raise ConnectionError("lost inventory checkpoint response")

    with pytest.raises(ConnectionError):
        workflow.ReadabilityHandler(factory, tmp_path).scan_inventory(
            job, UUID(str(run["id"])), Lost()
        )
    workflow.ReadabilityHandler(factory, tmp_path).scan_inventory(job, UUID(str(run["id"])), None)
    with factory() as session, session.begin():
        repo = SqlAlchemyReadabilityRepository(session)
        repo.bind(GAME_ID)
        persisted = repo.row("runs", GAME_ID, UUID(str(run["id"])))
        assert persisted["item_count"] == 15 and persisted["inventory_fingerprint"]
        cells = session.scalars(
            text(
                "SELECT cell_id FROM symbol_readability_items WHERE game_id=:game "
                "AND run_id=:run ORDER BY cell_index LIMIT 2"
            ),
            {"game": GAME_ID, "run": run["id"]},
        ).all()
        for cell, reason in zip(cells, ("unreadable_score", "overlap_score"), strict=True):
            session.execute(
                text(
                    "UPDATE symbol_readability_items SET processed=true,state='pending',"
                    "overlap=NULL,candidate=true,reasons=CAST(:reasons AS jsonb) "
                    "WHERE game_id=:game AND run_id=:run AND cell_id=:cell"
                ),
                {"game": GAME_ID, "run": run["id"], "cell": cell, "reasons": json.dumps([reason])},
            )
        overlap = repo.page(GAME_ID, UUID(str(run["id"])), problem="overlap")
        unreadable = repo.page(GAME_ID, UUID(str(run["id"])), problem="unreadable")
        assert [item["cell_id"] for item in overlap["items"]] == [cells[1]]
        assert [item["cell_id"] for item in unreadable["items"]] == [cells[0]]
        session.execute(
            text(
                "UPDATE symbol_readability_items SET overlap=true WHERE game_id=:game "
                "AND run_id=:run AND cell_id=:cell"
            ),
            {"game": GAME_ID, "run": run["id"], "cell": cells[0]},
        )
        assert {
            item["cell_id"]
            for item in repo.page(GAME_ID, UUID(str(run["id"])), problem="overlap")["items"]
        } == set(cells)
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM symbol_readability_items WHERE "
                    "game_id=:game AND run_id=:run"
                ),
                {"game": GAME_ID, "run": run["id"]},
            )
            == 15
        )
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from types import SimpleNamespace

    from game_predictor_api.schemas.symbol_readability import ReadabilityLabelRequest

    with factory() as session, session.begin():
        repo = SqlAlchemyReadabilityRepository(session)
        repo.bind(GAME_ID, write=True)
        current_items = (
            session.execute(
                text(
                    "SELECT * FROM symbol_readability_items WHERE game_id=:game AND "
                    "run_id=:run ORDER BY cell_index"
                ),
                {"game": GAME_ID, "run": run["id"]},
            )
            .mappings()
            .all()
        )
        source_snapshot = current_items[0]["snapshot"]
        targets = [
            dict(
                cell_id=item["cell_id"],
                expected_identity=item["identity"],
                expected_revision=item["revision"],
            )
            for item in reversed(current_items[:2])
        ]
        session.execute(
            text(
                "UPDATE symbol_readability_items SET processed=false WHERE "
                "game_id=:game AND run_id=:run"
            ),
            {"game": GAME_ID, "run": run["id"]},
        )
        session.execute(
            text(
                "UPDATE symbol_readability_runs SET "
                "processed_count=0,receipt=receipt-'successCount'-'failureCount'-'"
                "reviewCount' WHERE game_id=:game AND id=:run"
            ),
            {"game": GAME_ID, "run": run["id"]},
        )
    decoding, release, label_started, label_finished = Event(), Event(), Event(), Event()

    class BlockingLoader:
        def __init__(self, **kw):
            pass

        def load(self, *a, **kw):
            decoding.set()
            assert release.wait(5)
            return SimpleNamespace(
                source=SimpleNamespace(
                    normalized_pixel_checksum_sha256=source_snapshot[
                        "normalized_pixel_checksum_sha256"
                    ]
                )
            )

        def clear(self):
            pass

    artifact = SimpleNamespace(
        overlap=SimpleNamespace(threshold=0.5),
        unreadable=SimpleNamespace(threshold=0.5),
        score=lambda values: (np.full(len(values), 0.8), np.full(len(values), 0.1)),
    )
    monkeypatch.setattr(workflow, "CanonicalSourceLoader", BlockingLoader)
    monkeypatch.setattr(workflow, "load_artifact", lambda *a, **kw: artifact)
    monkeypatch.setattr(
        workflow.ReadabilityHandler,
        "render_snapshot",
        lambda *a, **kw: np.zeros((2, 2, 3), dtype=np.uint8),
    )
    monkeypatch.setattr(
        workflow, "extract_features", lambda model, crops: np.zeros((len(crops), 1032))
    )

    class Context:
        def checkpoint(self, **kw):
            pass

    def label_while_scan():
        with factory() as session, session.begin():
            label_started.set()
            result = SqlAlchemyReadabilityRepository(session).label(
                GAME_ID,
                UUID(str(run["id"])),
                ReadabilityLabelRequest(
                    idempotency_key=uuid4(), targets=targets, state="readable", overlap=False
                ),
            )
        label_finished.set()
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        scan = pool.submit(
            workflow.ReadabilityHandler(factory, tmp_path).process,
            Context(),
            job,
            UUID(str(run["id"])),
            None,
            object(),
        )
        assert decoding.wait(5)
        label = pool.submit(label_while_scan)
        try:
            assert label_started.wait(5)
            assert not label_finished.wait(0.2)
        finally:
            release.set()
        scan.result(timeout=10)
        label.result(timeout=10)
    assert label_finished.is_set()
    with factory() as session, session.begin():
        repo = SqlAlchemyReadabilityRepository(session)
        repo.bind(GAME_ID, write=True)
        assert repo.row("runs", GAME_ID, UUID(str(run["id"])))["status"] == "completed"
        # Conservative policy: changed pilot pixels invalidate readiness for a NEW scan.
        session.execute(
            text("""INSERT INTO symbol_readability_items(game_id,run_id,cell_id,
          source_id,sequence_number,cell_index,snapshot,identity,state,sample_kind,
          historical_unreadable,processed)
          SELECT game_id,:pilot,cell_id,source_id,sequence_number,cell_index,snapshot,identity,
            'readable','pilot',false,true FROM symbol_readability_items
          WHERE game_id=:game AND run_id=:run AND cell_id=:cell"""),
            {"game": GAME_ID, "run": run["id"], "pilot": pilot["id"], "cell": cells[0]},
        )
        session.execute(
            text(
                "UPDATE symbol_readability_runs SET "
                "item_count=1,processed_count=1 WHERE game_id=:game AND id=:pilot"
            ),
            {"game": GAME_ID, "pilot": pilot["id"]},
        )
        session.execute(
            text(
                "UPDATE recognized_boards SET "
                "geometry_revision=geometry_revision+1 WHERE game_id=:game AND "
                "id=:board"
            ),
            {"game": GAME_ID, "board": source_snapshot["recognized_board_id"]},
        )
        with pytest.raises(ReadabilityWorkflowError) as stale:
            repo.start(
                GAME_ID,
                ReadabilityStartRequest(idempotency_key=uuid4(), kind="scan", model_id=model),
            )
        assert stale.value.code == "READABILITY_CROP_STALE"
