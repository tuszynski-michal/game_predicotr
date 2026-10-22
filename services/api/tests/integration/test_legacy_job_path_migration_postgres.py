"""Exercise the actual relocation transaction only in a UUID-owned test database."""

import hashlib
import json
import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import GameStatus
from game_predictor_api.domain.jobs import JobStatus, JobType, create_job
from game_predictor_api.storage.catalog_repository import SqlAlchemyCatalogRepository
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import SymbolModel
from game_predictor_api.storage.owned_tool_database import OwnedToolDatabase
from game_predictor_worker.images.source_ingestion import ManagedOriginalStore
from PIL import Image
from psycopg.rows import dict_row
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from scripts import legacy_job_path_migration as migration
from scripts import scan_legacy_database_paths as scanner
from scripts.prepare_legacy_copy_retirement import verify_files

ROOT = Path(__file__).resolve().parents[4]
pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit disposable PostgreSQL database only",
)


def test_relocation_transaction_conflict_lock_rollback_retry_and_full_scan(tmp_path, monkeypatch):
    with OwnedToolDatabase(
        ApiSettings.from_environment().owner_database_url,
        prefix="game_predictor_task1086",
        alembic_ini=ROOT / "alembic.ini",
    ) as database:
        url = database.owner_url

        def connect(*, readonly=False):
            return psycopg.connect(
                host=url.host,
                port=url.port or 5432,
                dbname=url.database,
                user=url.username,
                password=url.password,
                connect_timeout=5,
                options="-c statement_timeout=10000 -c lock_timeout=2000"
                + (" -c default_transaction_read_only=on" if readonly else ""),
                row_factory=dict_row,
            )

        monkeypatch.setattr(migration, "connect", connect)
        monkeypatch.setattr(scanner, "connect", connect)
        source, destination, artifacts = [tmp_path / p for p in ("legacy", "active", "artifacts")]
        for root in (source, destination):
            folder = root / "imports/selection"
            folder.mkdir(parents=True)
            Image.new("RGB", (8, 8), "red").save(folder / "a.jpg")
        assert verify_files(source, destination, tmp_path / "receipts")["complete"]
        engine = create_engine(url)
        try:
            with Session(engine) as session:
                game = CatalogService(SqlAlchemyCatalogRepository(session)).create_game(
                    idempotency_key=uuid4(),
                    code="relocation",
                    name="Relocation",
                    status=GameStatus.ACTIVE,
                )
                for index in range(2):
                    job = replace(
                        create_job(
                            JobType.IMPORT,
                            game_id=game.id,
                            input_payload={
                                "schema_version": 1,
                                "import_kind": "image_directory",
                                "source_directory": str(source / "imports/selection"),
                                "pipeline_fingerprint": ("a" if index == 0 else "b") * 64,
                            },
                            created_at=datetime.now(UTC),
                        ),
                        status=JobStatus.WAITING_FOR_REVIEW,
                    )
                    SqlAlchemyJobRepository(session).add_job(job)
                    ManagedOriginalStore(artifacts).load_or_create_manifest(
                        job, source_directory=source / "imports/selection"
                    )
                session.commit()
            plan = migration.preview(
                source, destination, tmp_path / "receipts/files-summary.json", artifacts
            )
            assert not plan["blockers"] and len(plan["manifests"]) == 2
            path = tmp_path / "preview.json"
            path.write_text(json.dumps(plan), encoding="utf-8")
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            ids = [item["before"]["id"] for item in plan["jobs"]]

            def rows():
                with connect(readonly=True) as connection:
                    return connection.execute(migration.SELECT_JOBS).fetchall()

            original = rows()
            with connect() as connection:
                connection.execute(
                    "update jobs set updated_at=updated_at+interval '1 second' where id=%s",
                    (ids[-1],),
                )
            with pytest.raises(ValueError, match="changed"):
                migration.apply(path, sha)
            assert rows()[0] == original[0]
            with connect() as connection:
                connection.execute(
                    "update jobs set updated_at=%s::timestamptz where id=%s",
                    (original[-1]["updated_at"], ids[-1]),
                )
            with connect() as locked:
                locked.execute("select id from jobs where id=%s for update", (ids[0],))
                with pytest.raises(psycopg.errors.LockNotAvailable):
                    migration.apply(path, sha)
            assert rows() == original

            class FailingConnection:
                def __init__(self):
                    self.connection = connect()
                    self.updates = 0

                def __enter__(self):
                    self.connection.__enter__()
                    return self

                def __exit__(self, *args):
                    return self.connection.__exit__(*args)

                def execute(self, query, *args):
                    if isinstance(query, str) and query.startswith("update public.jobs"):
                        self.updates += 1
                        if self.updates == 2:
                            raise RuntimeError("Injected lost connection before second update")
                    return self.connection.execute(query, *args)

            monkeypatch.setattr(migration, "connect", lambda **_: FailingConnection())
            with pytest.raises(RuntimeError, match="Injected"):
                migration.apply(path, sha)
            assert rows() == original
            monkeypatch.setattr(migration, "connect", connect)
            assert migration.apply(path, sha) == 2
            after = rows()
            for before, current in zip(original, after, strict=True):
                assert current["input_payload"] == next(
                    item["after_payload"]
                    for item in plan["jobs"]
                    if item["before"]["id"] == before["id"]
                )
                assert {
                    k: v for k, v in current.items() if k not in {"updated_at", "input_payload"}
                } == {k: v for k, v in before.items() if k not in {"updated_at", "input_payload"}}
            with pytest.raises(ValueError, match="changed"):
                migration.apply(path, sha)
            with connect() as connection:
                connection.execute(
                    "update jobs set error_message=%s,checkpoint_payload=%s::jsonb where id=%s",
                    (
                        str(source).upper().replace("\\", "/"),
                        json.dumps({str(source) + "/key": 42}),
                        ids[0],
                    ),
                )
            result = scanner.scan(str(source), seconds=90)
            assert result["complete"] and result["read_only"] == "on"
            assert any(
                item["table"] == "jobs" and item["column"] == "input_payload" and item["count"] == 2
                for item in result["matches"]
            )
            assert any(
                item["table"] == "jobs"
                and item["column"] == "checkpoint_payload"
                and item["count"] == 1
                for item in result["matches"]
            )
            assert any(
                item["table"] == "jobs" and item["column"] == "error_message" and item["count"] == 1
                for item in result["matches"]
            )
            incomplete = scanner.scan(str(source), seconds=0)
            assert not incomplete["complete"]
            assert scanner.scan(str(source), previous=incomplete)["complete"]
            parts = [scanner.scan(str(source), partition=index, partitions=2) for index in range(2)]
            assert all(part["complete"] for part in parts)
            assert sum(len(part["columns"]) for part in parts) == len(result["columns"])
            with Session(engine) as session:
                session.add(
                    SymbolModel(
                        game_id=game.id,
                        mobile_code=1,
                        code="path",
                        name="Path",
                        image_path=str(source / "a.jpg"),
                        display_order=0,
                    )
                )
                session.commit()
            operational = scanner.scan(str(source), operational=True)
            assert operational["complete"] and operational["read_only"] == "on"
            assert operational["scope"] == "operational-path-columns"
            assert any(
                item["table"] == "symbols" and item["column"] == "image_path" and item["count"] == 1
                for item in operational["matches"]
            )
            assert not any(item["table"] == "jobs" for item in operational["matches"])
            with pytest.raises(ValueError, match="different scan scope"):
                scanner.scan(str(source), previous=incomplete, operational=True)
        finally:
            engine.dispose()
