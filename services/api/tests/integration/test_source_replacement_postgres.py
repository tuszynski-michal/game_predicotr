"""Owned disposable PostgreSQL only: exact scope, persistence, chronology and RLS."""

import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from _recording_capability_fixture import OwnedRecordingCapability
from alembic import command
from alembic.config import Config
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.source_replacement import SourceReplacementError
from game_predictor_api.domain.symbol_readability import GAME_ID, crop_identity
from game_predictor_api.schemas.source_replacement import SourceReplacementCreateRequest
from game_predictor_api.schemas.symbol_readability import (
    ReadabilityLabelRequest,
    ReadabilityLabelTarget,
    ReadabilityStartRequest,
)
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_partition_lifecycle import (
    GamePartitionLifecycleKind,
    GamePartitionLifecycleRepository,
)
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemyImageSymbolReviewRepository,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.source_replacement import SourceReplacementRepository
from game_predictor_api.storage.symbol_readability import SqlAlchemyReadabilityRepository
from game_predictor_worker.images.orchestration_store import SqlAlchemyImageBatchStore
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_image_batch_store import PIPELINE, _add_review_projection_source, _image_job

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1", reason="Owned PostgreSQL opt-in"
)
ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(scope="module")
def database():
    original = make_url(ApiSettings.from_environment().owner_database_url)
    name = f"game_predictor_task1127_replacement_{uuid4().hex[:8]}"
    assert re.fullmatch(r"game_predictor_task1127_replacement_[0-9a-f]{8}", name)
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
    print(f"Disposable replacement database: {name}", flush=True)
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
                    """
INSERT INTO public.games(id,code,name,status)
VALUES(:game,'777a2','Fixture','active')
"""
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
        runtime = "gp_task1127_" + uuid4().hex[:12]
        with engine.begin() as connection:
            owned.create_runtime_role(connection, runtime)
            connection.exec_driver_sql(f'GRANT USAGE ON SCHEMA game_data_v2 TO "{runtime}"')
            connection.exec_driver_sql(
                f'GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA game_data_v2 TO "{runtime}"'
            )
        engine._task1127_runtime = runtime
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


def test_exact_alias_manifest_and_lost_response(database):
    factory = create_session_factory(database)
    now = datetime.now(UTC)
    sources = []
    for number in (1, 2):
        with game_storage_scope(GAME_ID), factory() as session:
            job = SqlAlchemyJobRepository(session).add_job(
                _image_job(GAME_ID, PIPELINE, now + timedelta(seconds=number))
            )
            session.commit()
        store = SqlAlchemyImageBatchStore(factory)
        execution = store.register_file(
            job.id,
            source_checksum_sha256="a" * 64,
            pipeline_fingerprint=PIPELINE,
            source_relative_path="seq_1-9.jpg",
            order_index=0,
            registered_at=now,
        )
        with game_storage_scope(GAME_ID), factory() as session:
            review, board = _add_review_projection_source(
                session,
                job_id=job.id,
                file_execution_key=execution.file_execution_key,
                source_checksum="a" * 64,
                source_name="seq_1-9.jpg",
                position_index=number - 1,
                sequence_number=number,
                status="pending",
                created_at=now,
            )
            source = session.scalar(
                text("SELECT source_image_id FROM recognized_boards WHERE id=:id"), {"id": board}
            )
            sources.append(source)
            session.execute(
                text("UPDATE public.jobs SET status='waiting_for_review' WHERE id=:id"),
                {"id": job.id},
            )
            session.commit()
    with game_storage_scope(GAME_ID), factory() as session:
        session.execute(
            text(
                """
UPDATE image_source_geometry_revisions SET
sequence_attestation_checksum_sha256=:sha WHERE game_id=:game
"""
            ),
            {"sha": "b" * 64, "game": GAME_ID},
        )
        SqlAlchemyBoardSearchProjectionRepository(session).rebuild_game(GAME_ID)
        session.commit()
    with game_storage_scope(GAME_ID), factory() as session:
        projection = SqlAlchemyImageSymbolReviewRepository(session)
        projection.start_or_resume_backfill(GAME_ID)
        step = projection.backfill_next_batch(GAME_ID, batch_size=100)
        assert step.processed_review_item_count == 2
        assert step.report.cell_count == 30
        session.execute(
            text(
                """
UPDATE image_symbol_review_cells SET quality_issue='unreadable' WHERE
game_id=:game
"""
            ),
            {"game": GAME_ID},
        )
        session.commit()
    with factory() as session:
        repo = SourceReplacementRepository(session)
        preview = repo.preview(GAME_ID, sources)
        assert len(preview["entries"]) == 1
        entry = preview["entries"][0]
        assert set(entry["source_ids"]) == set(map(str, sources))
        assert entry["sequence_numbers"] == list(range(1, 10))
        assert entry["reasons"] and not entry["blockers"], entry["blockers"]
        request = SourceReplacementCreateRequest(
            mode="replace_preserve_history",
            source_ids=sources,
            idempotency_key=uuid4(),
            expected_revision=0,
            preview_token=preview["preview_token"],
        )
        result = repo.create(GAME_ID, request)
        session.commit()
    # New connection simulates process restart and lost response.
    with factory() as session:
        repo = SourceReplacementRepository(session)
        assert repo.create(GAME_ID, request) == result
        loaded = repo.get(GAME_ID, UUID(result["id"]))
        assert loaded["id"] == result["id"] and loaded["revision"] == result["revision"]
        assert loaded["entries"][0]["boards"] == result["entries"][0]["boards"]
        assert loaded["entries"][0]["scope_digest"]
        assert session.scalar(text("SELECT count(*) FROM source_replacement_slots")) == 0
        assert session.scalar(text("SELECT count(*) FROM source_replacement_retired")) == 0
        assert session.scalar(text("SELECT count(*) FROM source_images")) == 2
        session.commit()
    with factory() as session:
        repo = SourceReplacementRepository(session)
        preview = repo.preview(GAME_ID, sources)
        session.execute(
            text("""
UPDATE image_symbol_review_cells SET revision=revision+1 WHERE game_id=:game
"""),
            {"game": GAME_ID},
        )
        with pytest.raises(SourceReplacementError) as error:
            repo.create(
                GAME_ID,
                request.model_copy(
                    update={"idempotency_key": uuid4(), "preview_token": preview["preview_token"]}
                ),
            )
        assert error.value.code == "SOURCE_REPLACEMENT_PREVIEW_STALE"
        session.rollback()


def test_human_ledger_atomic_retry_older_run_and_changed_pixels(database, monkeypatch):
    factory = create_session_factory(database)
    with factory() as session:
        repo = SqlAlchemyReadabilityRepository(session)
        older = repo.start(GAME_ID, ReadabilityStartRequest(idempotency_key=uuid4(), kind="pilot"))
        newer = repo.start(
            GAME_ID, ReadabilityStartRequest(idempotency_key=uuid4(), kind="pilot", seed="new")
        )
        session.execute(
            text(
                """
UPDATE public.jobs SET status='cancelled',finished_at=now() WHERE
game_id=:game AND job_type::text='symbol_readability'
"""
            ),
            {"game": GAME_ID},
        )
        cell = session.scalar(text("SELECT id FROM image_symbol_review_cells ORDER BY id LIMIT 1"))
        snapshot = repo.current(GAME_ID, cell)
        for run in (older, newer):
            session.execute(
                text("""
INSERT INTO symbol_readability_items(game_id,run_id,cell_id,source_id,
sequence_number,cell_index,snapshot,identity,sample_kind,historical_unreadable,processed)
VALUES(:game,:run,:cell,:source,:seq,:idx,CAST(:snap AS
jsonb),:identity,'pilot',true,true)
"""),
                dict(
                    game=GAME_ID,
                    run=run["id"],
                    cell=cell,
                    source=snapshot["source_id"],
                    seq=snapshot["sequence_number"],
                    idx=snapshot["cell_index"],
                    snap=json.dumps(snapshot),
                    identity=crop_identity(snapshot),
                ),
            )
        session.commit()

    def label(run, state, revision):
        return ReadabilityLabelRequest(
            idempotency_key=uuid4(),
            state=state,
            overlap=True,
            targets=[
                ReadabilityLabelTarget(
                    cell_id=cell,
                    expected_identity=crop_identity(snapshot),
                    expected_revision=revision,
                )
            ],
        )

    commands = [(newer, "unreadable", 0), (older, "readable", 0), (newer, "pending", 1)]
    for run, state, revision in commands:
        request = label(run, state, revision)
        with factory() as session:
            repo = SqlAlchemyReadabilityRepository(session)
            repo.label(GAME_ID, run["id"], request)
            session.commit()
        with factory() as session:
            repo = SqlAlchemyReadabilityRepository(session)
            repo.label(GAME_ID, run["id"], request)
            session.commit()
    with factory() as session:
        repo = SourceReplacementRepository(session)
        preview = repo.preview(GAME_ID, [UUID(snapshot["source_id"])])
        item = next(e for e in preview["entries"][0]["evidence"] if e["cell_id"] == str(cell))
        assert item["state"] == "readable"
        assert (
            session.scalar(
                text("SELECT count(*) FROM symbol_readability_decisions WHERE cell_id=:cell"),
                {"cell": cell},
            )
            == 3
        )
        assert not any(e["cell_id"] == str(cell) for e in preview["entries"][0]["reasons"])
        # Static schema assertion; cross-game runtime isolation is tested separately.
        assert session.scalar(
            text(
                """
SELECT relforcerowsecurity FROM pg_class WHERE
oid='game_data_v2.symbol_readability_decisions'::regclass
"""
            )
        )

    from game_predictor_api.domain.symbol_readability import ReadabilityWorkflowError
    from game_predictor_api.storage import source_replacement_decisions

    # Failure after ledger INSERT must roll back label, ledger and command receipt together.
    original_append = source_replacement_decisions.append_quality_decision

    def fail_after_append(*args, **kwargs):
        original_append(*args, **kwargs)
        raise RuntimeError("injected transaction failure")

    request = label(older, "unreadable", 1)
    with monkeypatch.context() as patch:
        patch.setattr(source_replacement_decisions, "append_quality_decision", fail_after_append)
        with factory() as session:
            with pytest.raises(RuntimeError, match="injected"):
                SqlAlchemyReadabilityRepository(session).label(GAME_ID, older["id"], request)
            session.rollback()
    with factory() as session:
        repo = SqlAlchemyReadabilityRepository(session)
        repo.bind(GAME_ID)
        assert (
            session.scalar(
                text("SELECT count(*) FROM symbol_readability_decisions WHERE cell_id=:cell"),
                {"cell": cell},
            )
            == 3
        )
        assert (
            session.scalar(
                text(
                    """
SELECT revision FROM symbol_readability_items WHERE run_id=:run AND
cell_id=:cell
"""
                ),
                {"run": older["id"], "cell": cell},
            )
            == 1
        )
        assert (
            session.scalar(
                text("SELECT count(*) FROM symbol_readability_commands WHERE idempotency_key=:key"),
                {"key": request.idempotency_key},
            )
            == 0
        )
        session.execute(
            text("UPDATE image_symbol_review_cells SET crop_checksum_sha256=:sha WHERE id=:cell"),
            {"sha": "e" * 64, "cell": cell},
        )
        with pytest.raises(ReadabilityWorkflowError) as error:
            repo.label(GAME_ID, older["id"], label(older, "readable", 1))
        assert error.value.code == "READABILITY_CROP_STALE"
        session.rollback()


def test_range_foreign_pending_alias_integrity_and_runtime_rls(database):
    factory = create_session_factory(database)
    with factory() as session:
        repo = SourceReplacementRepository(session)
        repo.bind(GAME_ID)
        sources = list(session.scalars(text("SELECT id FROM source_images ORDER BY id")))
        assert session.scalar(text("SELECT count(*) FROM source_replacement_sources")) == 2
        # Both alias references have validated source FKs, not only the representative.
        assert (
            session.scalar(
                text(
                    """
SELECT count(*) FROM pg_constraint WHERE
conrelid='game_data_v2.source_replacement_sources'::regclass AND contype='f' AND
confrelid='game_data_v2.source_images'::regclass AND convalidated
"""
                )
            )
            == 1
        )
        session.execute(
            text(
                """
UPDATE image_source_geometry_revisions SET sequence_range_end=2,
active_board_slots=ARRAY[0,1]::smallint[],
board_geometries=jsonb_build_array(board_geometries->0,board_geometries->1) WHERE game_id=:game
"""
            ),
            {"game": GAME_ID},
        )
        entry = repo.preview(GAME_ID, [sources[0]])["entries"][0]
        assert entry["sequence_numbers"] == [1, 2]
        assert not entry["blockers"]
        session.rollback()
    with factory() as session:
        repo = SourceReplacementRepository(session)
        repo.bind(GAME_ID)
        session.execute(
            text("UPDATE source_images SET checksum_sha256=:sha WHERE id=:id"),
            {"sha": "f" * 64, "id": sources[1]},
        )
        entry = repo.preview(GAME_ID, [sources[0]])["entries"][0]
        assert "SOURCE_REPLACEMENT_SLOT_PENDING_CONFLICT" in entry["blockers"]
        session.rollback()
    with database.connect() as connection, connection.begin():
        connection.exec_driver_sql(f'SET LOCAL ROLE "{database._task1127_runtime}"')
        assert not connection.scalar(
            text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user")
        )
        connection.execute(
            text("SELECT set_config('game_predictor.game_id',:game,true)"),
            {"game": str(GAME_ID)},
        )
        assert (
            connection.scalar(text("SELECT count(*) FROM game_data_v2.source_replacement_batches"))
            == 1
        )
        assert (
            connection.scalar(
                text("SELECT count(*) FROM game_data_v2.symbol_readability_decisions")
            )
            == 3
        )
        connection.execute(
            text("SELECT set_config('game_predictor.game_id',:game,true)"),
            {"game": str(uuid4())},
        )
        assert (
            connection.scalar(text("SELECT count(*) FROM game_data_v2.source_replacement_batches"))
            == 0
        )
        assert (
            connection.scalar(
                text("SELECT count(*) FROM game_data_v2.symbol_readability_decisions")
            )
            == 0
        )
        with pytest.raises(DBAPIError, match="row-level security"):
            connection.execute(
                text(
                    """
INSERT INTO game_data_v2.source_replacement_batches
(game_id,id,revision,status,preview_token,document) VALUES(:game,:id,1,'planned',:token,'{}')
"""
                ),
                {"game": GAME_ID, "id": uuid4(), "token": "a" * 64},
            )


def test_pre_ledger_conflict_survives_pending_skipped_until_new_decisive(database):
    factory = create_session_factory(database)
    with factory() as session:
        repo = SqlAlchemyReadabilityRepository(session)
        repo.bind(GAME_ID)
        cell = session.scalar(
            text("""
SELECT c.id FROM image_symbol_review_cells c WHERE NOT EXISTS
(SELECT 1 FROM symbol_readability_decisions d WHERE d.cell_id=c.id)
ORDER BY c.id LIMIT 1
""")
        )
        snapshot = repo.current(GAME_ID, cell)
        runs = list(
            session.scalars(text("SELECT id FROM symbol_readability_runs ORDER BY id LIMIT 2"))
        )
        for run, state in zip(runs, ["readable", "unreadable"], strict=True):
            session.execute(
                text("""
INSERT INTO symbol_readability_items
(game_id,run_id,cell_id,source_id,sequence_number,cell_index,snapshot,identity,
sample_kind,historical_unreadable,processed,ever_labelled,state,revision)
VALUES(:game,:run,:cell,:source,:seq,:idx,CAST(:snap AS jsonb),:identity,
'pilot',true,true,true,:state,7)
"""),
                dict(
                    game=GAME_ID,
                    run=run,
                    cell=cell,
                    source=snapshot["source_id"],
                    seq=snapshot["sequence_number"],
                    idx=snapshot["cell_index"],
                    snap=json.dumps(snapshot),
                    identity=crop_identity(snapshot),
                    state=state,
                ),
            )
        session.commit()

    def evidence():
        with factory() as session:
            result = SourceReplacementRepository(session).preview(
                GAME_ID, [UUID(snapshot["source_id"])]
            )
            return next(
                row for row in result["entries"][0]["evidence"] if row["cell_id"] == str(cell)
            )

    assert evidence()["blocker"] == "SOURCE_REPLACEMENT_JUDGMENT_AMBIGUOUS"
    for run, state in zip(runs, ["pending", "skipped"], strict=True):
        with factory() as session:
            SqlAlchemyReadabilityRepository(session).label(
                GAME_ID,
                run,
                ReadabilityLabelRequest(
                    idempotency_key=uuid4(),
                    overlap=None,
                    state=state,
                    targets=[
                        ReadabilityLabelTarget(
                            cell_id=cell,
                            expected_identity=crop_identity(snapshot),
                            expected_revision=7,
                        )
                    ],
                ),
            )
            session.commit()
        retained = evidence()
        assert retained["blocker"] == "SOURCE_REPLACEMENT_JUDGMENT_AMBIGUOUS"
        assert {row["state"] for row in retained["proof"]} == {"readable", "unreadable"}
        assert all(row["revision"] == 7 and "ordinal" not in row for row in retained["proof"])
    with factory() as session:
        SqlAlchemyReadabilityRepository(session).label(
            GAME_ID,
            runs[0],
            ReadabilityLabelRequest(
                idempotency_key=uuid4(),
                overlap=None,
                state="readable",
                targets=[
                    ReadabilityLabelTarget(
                        cell_id=cell, expected_identity=crop_identity(snapshot), expected_revision=8
                    )
                ],
            ),
        )
        session.commit()
    assert evidence()["state"] == "readable" and evidence()["blocker"] is None
    with factory() as session:
        repo = SourceReplacementRepository(session)
        repo.bind(GAME_ID)
        session.execute(
            text("""
UPDATE image_symbol_review_cells SET crop_checksum_sha256=:sha, quality_issue=NULL WHERE id=:cell
"""),
            {"sha": "e" * 64, "cell": cell},
        )
        result = repo.preview(GAME_ID, [UUID(snapshot["source_id"])])
        changed = next(
            row for row in result["entries"][0]["evidence"] if row["cell_id"] == str(cell)
        )
        assert changed["state"] is None and changed["proof"] == []
        session.rollback()
