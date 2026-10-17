"""Exact-owned two-connection guard proof; metadata fixtures are not human labels."""

import json
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.storage_retention import StorageRetentionPolicy
from game_predictor_api.storage import storage_gc_repository as repository_module
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.grid_cohort_asset_retention import (
    ASSET_GUARD_NAMESPACE,
    acquire_cohort_asset_guard,
)
from game_predictor_api.storage.grid_training_cohort_artifacts import GridCohortArtifactStore
from game_predictor_api.storage.grid_training_cohort_models import (
    GridTrainingCohortEventModel,
    GridTrainingCohortModel,
    GridTrainingCohortPageModel,
)
from game_predictor_worker import storage_gc as worker
from game_predictor_worker.filesystem import long_path_aware
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Exact-owned disposable PostgreSQL opt-in required",
)


@pytest.fixture(autouse=True)
def owned_long_path_cleanup(tmp_path):
    identity = tmp_path.stat().st_dev, tmp_path.stat().st_ino
    marker = str(uuid4())
    (tmp_path / "fixture-owner").write_text(marker, encoding="utf-8")
    yield
    assert identity == (tmp_path.stat().st_dev, tmp_path.stat().st_ino)
    assert (tmp_path / "fixture-owner").read_text(encoding="utf-8") == marker
    target = long_path_aware(tmp_path)
    assert all(not p.is_symlink() and not p.is_junction() for p in (target, *target.rglob("*")))
    shutil.rmtree(target)


def test_publication_receipt_and_gc_quarantine_are_serialized(tmp_path, monkeypatch):
    evidence = Path(os.environ["GAME_PREDICTOR_GC_TEST_EVIDENCE_ROOT"]).resolve()
    assert evidence.is_relative_to(Path(__file__).resolve().parents[4] / "artifacts/audits")
    evidence.mkdir(parents=True, exist_ok=False)
    monkeypatch.setenv("GAME_PREDICTOR_RECORDING_TEST_RESOURCE_ROOT", str(evidence / "resources"))
    started, stages = time.monotonic(), []

    def stage(value):
        assert time.monotonic() - started < 100, "Owned guard proof exceeded its soft budget"
        stages.append(value)
        (evidence / "progress.json").write_text(json.dumps(stages), encoding="utf-8")
        print("0995 GC " + value, flush=True)

    stage("starting_owned_fixture")
    try:
        with application_role_database("t0995gc", ("cohort-gc",)) as db:
            stage("fixture_ready")
            game, cohort = db.games["cohort-gc"], uuid4()
            now = datetime.now(UTC)
            old = now - timedelta(hours=25)
            with Session(db.owner_engine) as owner:
                GameStorageRouter().bind(owner, game, intent=GameStorageIntent.WRITE)
                owner.add(
                    GridTrainingCohortModel(
                        game_id=game,
                        id=cohort,
                        revision=1,
                        status="preparing",
                        document={},
                        summary={},
                        created_by="fixture:gc",
                        created_at=old,
                    )
                )
                owner.commit()
            db.owner_engine.dispose()
            artifact, imports = tmp_path / "a", tmp_path / "i"
            artifact.mkdir()
            imports.mkdir()
            store = GridCohortArtifactStore(artifact)
            handler = worker.StorageGcHandler(sessionmaker(db.app_engine), artifact, imports)
            states, pids = [], {}
            original_context = handler._repository.cohort_asset_gc_guard

            @contextmanager
            def observed_context(relative):
                with original_context(relative) as state:
                    states.append(state)
                    yield state

            handler._repository.cohort_asset_gc_guard = observed_context
            attempting = threading.Event()
            real_acquire = repository_module.acquire_cohort_asset_guard

            def traced_acquire(session, *args, **kwargs):
                if kwargs.get("exclusive"):
                    pids["gc"] = session.scalar(text("SELECT pg_backend_pid()"))
                    attempting.set()
                return real_acquire(session, *args, **kwargs)

            monkeypatch.setattr(repository_module, "acquire_cohort_asset_guard", traced_acquire)

            def entry(pin):
                path = store.safe(pin["path"])
                stat = path.stat()
                return {
                    "rootKind": "artifact",
                    "artifactClass": "grid_cohort_asset",
                    "relativePath": pin["path"],
                    "sizeBytes": pin["bytes"],
                    "observationChecksumSha256": worker._file_observation_checksum(path, stat),
                }

            def persist(session, pin, index):
                GameStorageRouter().bind(session, game, intent=GameStorageIntent.WRITE)
                session.add(
                    GridTrainingCohortPageModel(
                        game_id=game,
                        cohort_id=cohort,
                        kind="capture",
                        page_index=index,
                        path=pin["path"],
                        sha256=pin["sha256"],
                        document={"assets": [pin]},
                    )
                )
                session.add(
                    GridTrainingCohortEventModel(
                        game_id=game,
                        cohort_id=cohort,
                        id=uuid4(),
                        kind="fixture_receipt",
                        document={},
                        created_at=now,
                    )
                )

            with Session(db.app_engine) as publisher, ThreadPoolExecutor(max_workers=1) as executor:
                pids["publisher"] = publisher.scalar(text("SELECT pg_backend_pid()"))
                acquire_cohort_asset_guard(publisher, game, cohort)
                pin = store.publish_json(game, cohort, {"fixture": "publication_before_receipt"})
                os.utime(store.safe(pin["path"]), (old.timestamp(), old.timestamp()))
                saved = entry(pin)
                future = executor.submit(
                    handler._process_entry,
                    uuid4(),
                    0,
                    saved,
                    current={},
                    policy=StorageRetentionPolicy(),
                    now=now + timedelta(hours=25),
                )
                assert attempting.wait(2)
                waiting = False
                for _ in range(20):
                    waiting = bool(
                        publisher.scalar(
                            text("""SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_locks
                        WHERE pid=:pid AND locktype='advisory'
                          AND NOT granted AND classid=:namespace)"""),
                            {"pid": pids["gc"], "namespace": ASSET_GUARD_NAMESPACE},
                        )
                    )
                    if waiting:
                        break
                    time.sleep(0.02)
                assert waiting and not future.done()
                stage("exclusive_waiting_for_shared_publication")
                persist(publisher, pin, 0)
                publisher.flush()
                publisher.execute(
                    text("""UPDATE game_data_v2.grid_training_cohorts
                    SET status='canceled',revision=revision+1
                    WHERE game_id=:game AND id=:cohort"""),
                    {"game": game, "cohort": cohort},
                )
                publisher.commit()
                assert future.result(timeout=5) == ("protectedCount", 0)
                assert states[-1].referenced and not states[-1].unresolved
                assert store.safe(pin["path"]).exists()
                assert pids["gc"] != pids["publisher"]
            stage("fresh_receipt_retained_under_exclusive")

            payload = {"fixture": "unreferenced_before_quarantine"}
            with Session(db.app_engine) as publisher:
                acquire_cohort_asset_guard(publisher, game, cohort)
                orphan = store.publish_json(game, cohort, payload)
                publisher.commit()
            os.utime(store.safe(orphan["path"]), (old.timestamp(), old.timestamp()))
            saved, run = entry(orphan), uuid4()
            delete = worker._delete_trash

            def crash(path):
                raise OSError("fixture crash after quarantine")

            monkeypatch.setattr(worker, "_delete_trash", crash)
            with pytest.raises(worker.JobHandlerError):
                handler._process_entry(
                    run,
                    0,
                    saved,
                    current={},
                    policy=StorageRetentionPolicy(),
                    now=now + timedelta(hours=25),
                )
            assert not store.safe(orphan["path"]).exists()
            trash = worker._trash_path(artifact, run, 0, orphan["path"])
            assert trash.exists() and not states[-1].referenced and not states[-1].unresolved
            monkeypatch.setattr(worker, "_delete_trash", delete)
            assert handler._process_entry(
                run,
                0,
                saved,
                current={},
                policy=StorageRetentionPolicy(),
                now=now + timedelta(hours=25),
            ) == ("deletedCount", saved["sizeBytes"])
            assert not trash.exists()
            stage("quarantine_retry_rechecked_and_completed")
            (evidence / "proof.json").write_text(
                json.dumps(
                    {
                        "actorPids": pids,
                        "exclusiveWaitObserved": waiting,
                        "freshReceiptRetained": True,
                        "quarantineRetry": True,
                        "metadataOnlyFixture": True,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        stage("fixture_cleanup_complete")
    finally:
        receipts = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in (evidence / "resources").glob("*.json")
        ]
        checks = []
        if receipts:
            engine = create_engine(
                make_url(ApiSettings.from_environment().owner_database_url).set(
                    database="postgres"
                ),
                isolation_level="AUTOCOMMIT",
                poolclass=NullPool,
                connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"},
            )
            try:
                with engine.connect() as connection:
                    for receipt in receipts:
                        name = receipt["databaseName"]
                        assert (
                            name.startswith("game_predictor_t0995gc_")
                            and receipt["databaseCreatedHere"]
                        )
                        roles = [
                            receipt[key]["name"]
                            for key in ("capabilityRole", "runtimeRole")
                            if receipt.get(key) and receipt[key]["createdHere"]
                        ]
                        check = {
                            "database": name,
                            "databaseOid": receipt["databaseOid"],
                            "remainingDb": connection.scalar(
                                text("SELECT count(*) FROM pg_database WHERE datname=:name"),
                                {"name": name},
                            ),
                            "remainingRoles": connection.scalar(
                                text(
                                    "SELECT count(*) FROM pg_roles "
                                    "WHERE rolname=ANY(CAST(:roles AS text[]))"
                                ),
                                {"roles": roles},
                            ),
                            "pids": list(
                                connection.scalars(
                                    text("SELECT pid FROM pg_stat_activity WHERE datname=:name"),
                                    {"name": name},
                                )
                            ),
                        }
                        checks.append(check)
                        assert (
                            check["remainingDb"] == check["remainingRoles"] == 0
                            and not check["pids"]
                        )
            finally:
                engine.dispose()
        (evidence / "cleanup.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
