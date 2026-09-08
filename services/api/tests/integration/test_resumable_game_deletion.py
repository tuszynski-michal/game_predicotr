"""Small real PostgreSQL fixtures; never reset or migrate the application DB."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.game_deletion_policy_v1 import (
    CONFIRMATION,
    LEGACY_ID,
    PROTECTED_ID,
    SELF_LINKS,
    DeletionError,
    deletion_order,
    digest,
    quote,
)
from game_predictor_api.storage.game_deletion_repository import (
    GameDeletionRepository,
    load_schema,
    select_owned_batch,
)
from game_predictor_api.storage.models import (
    CellObservationModel,
    GameModel,
    ImageFileExecutionModel,
    ImageImportJobFileModel,
    ImageReviewItemModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
    SymbolModel,
)
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit isolated PostgreSQL tests only",
)


@pytest.fixture(scope="module")
def database() -> Iterator[Engine]:
    name = "game_predictor_task0516_" + uuid4().hex[:12]
    url = make_url(ApiSettings.from_environment().database_url)
    maintenance = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5},
    )
    engine = create_engine(url.set(database=name), connect_args={"connect_timeout": 5})
    with maintenance.connect() as connection:
        connection.execute(text("SET statement_timeout='10s'"))
        connection.execute(text(f"CREATE DATABASE {quote(name)}"))
    try:
        config = Config(str(Path(__file__).resolve().parents[4] / "alembic.ini"))
        config.set_main_option(
            "sqlalchemy.url",
            url.set(database=name).render_as_string(hide_password=False).replace("%", "%%"),
        )
        command.upgrade(config, "head")
        print("TASK-0516 isolated schema ready", flush=True)
        yield engine
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
            connection.execute(text(f"DROP DATABASE {quote(name)}"))
        maintenance.dispose()


def add_sources(session: Session, game: str) -> UUID:
    job = JobModel(
        game_id=UUID(game),
        job_type="import",
        status="cancelled",
        input_payload={"artifact_paths": ["data/fixture/report.json"]},
        input_key=uuid4().hex,
    )
    session.add(job)
    session.flush()
    for source_index in range(3):
        checksum = uuid4().hex * 2
        session.add(
            ImageFileExecutionModel(
                file_execution_key=checksum,
                source_checksum_sha256=checksum,
                pipeline_fingerprint="b" * 64,
                checkpoint_payload={},
                status="waiting_for_review",
                review_required=True,
            )
        )
        session.flush()
        session.add(
            ImageImportJobFileModel(
                job_id=job.id,
                file_execution_key=checksum,
                order_index=source_index,
                source_relative_path=f"seq_{source_index}.jpg",
                workflow_checkpoint_payload={},
                workflow_status="waiting_for_review",
                review_required=True,
            )
        )
        session.flush()
        source = SourceImageModel(
            import_job_id=job.id,
            file_execution_key=checksum,
            relative_path=f"seq_{source_index}.jpg",
            checksum_sha256=checksum,
            width=100,
            height=100,
            status="waiting_for_review",
        )
        session.add(source)
        session.flush()
        for position in range(4):
            number = source_index * 9 + position + 1
            board = RecognizedBoardModel(
                source_image_id=source.id,
                position_index=position,
                sequence_number_raw=str(number),
                sequence_number=number,
                sequence_confidence=1,
                board_geometry={},
                board_relative_path=f"boards/{number}.jpg",
                board_checksum_sha256="b" * 64,
                cells_prediction={},
                board_confidence=1,
                pipeline_fingerprint="b" * 64,
                status="pending_review",
            )
            session.add(board)
            session.flush()
            session.add(
                ImageReviewItemModel(
                    game_id=UUID(game),
                    import_job_id=job.id,
                    recognized_board_id=board.id,
                    sequence_number=number,
                    status="pending",
                    snapshot={},
                )
            )
            session.add_all(
                CellObservationModel(
                    recognized_board_id=board.id,
                    row_index=n // 5,
                    column_index=n % 5,
                    crop_relative_path=f"cells/{number}_{n}.jpg",
                    crop_checksum_sha256="c" * 64,
                    cropper_version="fixture",
                    prediction={},
                )
                for n in range(15)
            )
    return job.id


def test_schema_and_committed_restart(database: Engine) -> None:
    with Session(database) as session, session.begin():
        session.add_all(
            [
                GameModel(id=UUID(LEGACY_ID), code="777", name="777 v0.1"),
                GameModel(id=UUID(PROTECTED_ID), code="new-siedem", name="777"),
            ]
        )
        session.flush()
        for game in (LEGACY_ID, PROTECTED_ID):
            for index in range(3):
                session.add(
                    SymbolModel(
                        game_id=UUID(game),
                        mobile_code=index + 1,
                        code=f"s{index}",
                        name=f"s{index}",
                        display_order=index,
                    )
                )
        legacy_job = add_sources(session, LEGACY_ID)
        protected_job = add_sources(session, PROTECTED_ID)
    repo = GameDeletionRepository(database)
    archive = {
        "sha256": "a" * 64,
        "layoutCount": 0,
        "layoutFingerprint": hashlib.sha256().hexdigest(),
        "symbolsSha256": digest([(n + 1, f"s{n}", f"s{n}") for n in range(3)]),
    }
    with pytest.raises(DeletionError, match="ARCHIVE_CONTENT_MISMATCH"):
        repo.preview({**archive, "layoutCount": 1})
    report = repo.preview(archive)
    assert report["missingIndexes"] == []
    assert report["ready"] is True
    with database.begin() as connection:
        schema = load_schema(connection)
        cursor: list[dict[str, Any]] = []
        seen: list[UUID] = []
        for _ in range(20):
            rows, exhausted = select_owned_batch(
                connection, schema, "cell_observations", cursor, 47
            )
            seen.extend(row["id"] for row in rows)
            # Simulate durable JSON roundtrip between byte/row-limited portions.
            cursor = json.loads(json.dumps(cursor, default=str))
            if exhausted:
                break
        assert len(seen) == len(set(seen)) == 180
        assert len(rows) < 47
    # Parent ownership cannot change while an indirect writer resolves it.
    with database.begin() as first:
        first.execute(
            text("UPDATE source_images SET width=101 WHERE import_job_id=:j"), {"j": protected_job}
        )
        with pytest.raises(DBAPIError) as blocked, database.begin() as second:
            second.execute(text("SET LOCAL lock_timeout='200ms'"))
            second.execute(
                text("UPDATE jobs SET game_id=:g WHERE id=:j"), {"g": LEGACY_ID, "j": protected_job}
            )
        assert getattr(blocked.value.orig, "sqlstate", None) == "55P03"
    repo.start(report, CONFIRMATION)
    with (
        pytest.raises(DBAPIError, match="GAME_DELETE_WRITE_FENCED"),
        database.begin() as connection,
    ):
        connection.execute(
            text("UPDATE symbols SET name='blocked' WHERE game_id=:g"), {"g": LEGACY_ID}
        )
    with (
        pytest.raises(DBAPIError, match="GAME_DELETE_WRITE_FENCED"),
        database.begin() as connection,
    ):
        connection.execute(
            text("UPDATE source_images SET width=999 WHERE import_job_id=:j"), {"j": legacy_job}
        )
    with database.begin() as connection:
        connection.execute(
            text("UPDATE symbols SET name='permitted' WHERE game_id=:g"), {"g": PROTECTED_ID}
        )
    with database.begin() as connection:
        schema = load_schema(connection)
    stages = (
        ("unlink:games",)
        + tuple(f"unlink:{t}" for t in sorted(SELF_LINKS))
        + deletion_order(schema.foreign_keys)
    )
    # Advance only empty stages until the first populated, heavy leaf table.
    for _ in range(len(stages)):
        state = repo.status()
        assert state is not None
        if stages[state["stage_index"]] == "cell_observations":
            break
        repo.step(schema)
    # Failure after deleting rows but before checkpoint must roll back both.
    before = repo.status()
    with (
        patch.object(repo, "_save", side_effect=DeletionError("INJECTED", "rollback")),
        pytest.raises(DeletionError, match="INJECTED"),
    ):
        repo.step(schema)
    assert repo.status() == before
    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM cell_observations")) == 360
    # Lost progress response: already committed state is resumed, not recounted.
    repo.step(schema)
    repo = GameDeletionRepository(database)
    repo.start(report, CONFIRMATION)
    states: list[dict[str, Any]] = []
    repo.run(schema, max_steps=300, on_progress=states.append)
    assert states[-1]["status"] == "database_done"
    assert not any(
        s["deleted_counts"].get("games") and s["status"] != "database_done" for s in states
    )
    restarted = GameDeletionRepository(database)
    final = restarted.status()
    assert final is not None
    assert final["deleted_counts"]["symbols"] == 3
    assert final["deleted_counts"]["cell_observations"] == 180
    assert final["deleted_counts"]["image_review_items"] == 12
    assert final["deleted_counts"]["image_review_queue_items"] == 12
    assert final["deleted_counts"]["image_review_queue_states"] == 1
    assert restarted.step(schema)["status"] == "database_done"
    restarted.start(restarted.preview(archive), CONFIRMATION)
    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM games")) == 1
        assert connection.scalar(text("SELECT count(*) FROM symbols WHERE name='permitted'")) == 3
        assert connection.scalar(text("SELECT count(*) FROM cell_observations")) == 180
        assert connection.scalar(text("SELECT count(*) FROM image_review_queue_items")) == 12
        assert connection.scalar(text("SELECT count(*) FROM image_file_executions")) == 6
        batches = (
            connection.execute(text("SELECT asset_references FROM game_deletion_batches"))
            .scalars()
            .all()
        )
        assert "data/fixture/report.json" in str(batches)
