"""TASK-0756: pipeline compaction over global executions and per-game V2 guards.

Runs on a dedicated ``*_test`` database only. Two games are provisioned through
the real partition lifecycle, so every game-owned guard (import links, source
images, board geometry) is read from ``game_data_v2`` under RLS.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.jobs import JobType, create_job
from game_predictor_api.domain.pipeline_state_compaction import DISPOSABLE_STAGE_PAYLOADS
from game_predictor_api.storage.database import GameStorageSession
from game_predictor_api.storage.game_data_v2_manifest_v4 import CREATE_TABLES
from game_predictor_api.storage.game_partition_lifecycle import (
    GamePartitionLifecycleKind,
    GamePartitionLifecycleRepository,
)
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.models import (
    ImageBoardGeometryPendingModel,
    ImageFileExecutionModel,
    ImageImportJobFileModel,
    ImagePipelineStageResultModel,
    JobModel,
    SourceImageModel,
)
from game_predictor_api.storage.pipeline_state_compaction_repository import (
    SqlAlchemyPipelineStateCompactionRepository,
)
from game_predictor_worker.pipeline_state_compaction import PipelineStateCompactionHandler
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit isolated PostgreSQL tests only",
)

_FINGERPRINT = "b" * 64
_STAGES = ("board_detection", "board_crops", "symbol_inference")


@pytest.fixture
def database() -> Iterator[Engine]:
    name = "game_predictor_task0756_" + uuid4().hex[:12] + "_test"
    assert re.fullmatch(r"game_predictor_task0756_[0-9a-f]{12}_test", name)
    url = make_url(ApiSettings.from_environment().owner_database_url)
    assert url.database != name
    maintenance = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"},
    )
    engine = create_engine(url.set(database=name), connect_args={"connect_timeout": 5})
    config = Config(str(Path(__file__).resolve().parents[4] / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url",
        url.set(database=name).render_as_string(hide_password=False).replace("%", "%%"),
    )
    with maintenance.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    try:
        command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
            active = connection.execute(
                text("SELECT count(*) FROM pg_stat_activity WHERE datname=:name"),
                {"name": name},
            ).scalar_one()
            assert active == 0, "Refusing DROP while a test connection remains"
            connection.exec_driver_sql(f'DROP DATABASE "{name}"')
        maintenance.dispose()


@dataclass
class _Context:
    checkpoints: list[dict[str, object]] = field(default_factory=list)

    def now(self) -> datetime:
        return datetime.now(UTC)

    def checkpoint(self, **values: object) -> None:
        self.checkpoints.append(dict(values))


def _key(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _provision_game(engine: Engine, code: str) -> UUID:
    game_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                """INSERT INTO public.games (id, code, name, status, expected_layout_count)
                VALUES (:id, :code, :name, 'draft', 500000)"""
            ),
            {"id": game_id, "code": code, "name": code},
        )
    with Session(engine) as session, session.begin():
        operation_id = (
            GamePartitionLifecycleRepository(session)
            .start_or_resume(game_id=game_id, kind=GamePartitionLifecycleKind.PROVISION)
            .operation_id
        )
    for _ in range(len(CREATE_TABLES) + 2):
        with Session(engine) as session, session.begin():
            receipt = GamePartitionLifecycleRepository(session).run_next(operation_id)
        if receipt.status == "done":
            return game_id
    raise AssertionError("provisioning did not reach done")


def _add_executions(factory: sessionmaker[Session], keys: tuple[str, ...]) -> None:
    with factory.begin() as session:
        for key in keys:
            session.add(
                ImageFileExecutionModel(
                    file_execution_key=key,
                    source_checksum_sha256=key,
                    pipeline_fingerprint=_FINGERPRINT,
                    checkpoint_payload={},
                    status="waiting_for_review",
                    review_required=True,
                )
            )
        session.flush()
        for key in keys:
            for stage in _STAGES:
                session.add(
                    ImagePipelineStageResultModel(
                        file_execution_key=key,
                        stage=stage,
                        adapter_version=f"{stage}-v1",
                        result_payload={"stage": stage, "key": key, "blob": "x" * 200},
                    )
                )


def _add_import_job(
    factory: sessionmaker[Session],
    game_id: UUID,
    *,
    status: str,
    links: tuple[tuple[str, str], ...],
    pending_geometry_keys: tuple[str, ...] = (),
) -> dict[str, UUID]:
    """Add one import job with links ``(key, workflow_status)`` and source images."""

    sources: dict[str, UUID] = {}
    with game_storage_scope(game_id), factory.begin() as session:
        job = JobModel(
            game_id=game_id,
            job_type="import",
            status=status,
            input_payload={"import_kind": "image_directory"},
            input_key=uuid4().hex,
        )
        session.add(job)
        session.flush()
        for order_index, (key, workflow_status) in enumerate(links):
            failed = workflow_status == "failed"
            session.add(
                ImageImportJobFileModel(
                    job_id=job.id,
                    file_execution_key=key,
                    order_index=order_index,
                    source_relative_path=f"seq_{order_index}.jpg",
                    workflow_checkpoint_payload={},
                    workflow_status=workflow_status,
                    review_required=not failed,
                    failed_stage="board_crops" if failed else None,
                    error_code="FIXTURE_FAILED" if failed else None,
                    error_message="fixture failure" if failed else None,
                    last_failed_at=datetime.now(UTC) if failed else None,
                )
            )
            source = SourceImageModel(
                import_job_id=job.id,
                file_execution_key=key,
                relative_path=f"seq_{order_index}.jpg",
                checksum_sha256=key,
                width=100,
                height=100,
                status="waiting_for_review",
            )
            session.add(source)
            session.flush()
            sources[key] = source.id
        for key in pending_geometry_keys:
            session.add(
                ImageBoardGeometryPendingModel(
                    game_id=game_id,
                    import_job_id=job.id,
                    source_image_id=sources[key],
                    sequence_number=1,
                    position_index=0,
                    source_checksum_sha256=key,
                    source_relative_path="seq_pending.jpg",
                    status="pending",
                    reason_code="incomplete_lattice",
                    processing_manifest_checksum_sha256="e" * 64,
                    processing_manifest_relative_path="manifests/pending.json",
                    pipeline_fingerprint_sha256=_FINGERPRINT,
                    expected_geometry_revision=0,
                    expected_review_resolution_revision=0,
                )
            )
    return sources


def _stages_by_key(engine: Engine) -> dict[str, set[str]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT file_execution_key, stage FROM public.image_pipeline_stage_results")
        ).all()
    grouped: dict[str, set[str]] = {}
    for key, stage in rows:
        grouped.setdefault(str(key), set()).add(str(stage))
    return grouped


def test_preview_and_worker_apply_per_game_v2_guards(database: Engine, tmp_path: Path) -> None:
    factory = cast(
        "sessionmaker[Session]",
        sessionmaker(bind=database, class_=GameStorageSession, expire_on_commit=False),
    )
    game_a = _provision_game(database, "compaction-a")
    game_b = _provision_game(database, "compaction-b")
    plain, late, active, geometry, orphan, shared = (
        _key(label) for label in ("plain", "late", "active", "geometry", "orphan", "shared")
    )
    everything = (plain, late, active, geometry, orphan, shared)
    _add_executions(factory, everything)

    sources_a = _add_import_job(
        factory,
        game_a,
        status="completed",
        links=(
            (plain, "waiting_for_review"),
            (late, "waiting_for_review"),
            (geometry, "waiting_for_review"),
            (shared, "waiting_for_review"),
        ),
        pending_geometry_keys=(geometry,),
    )
    # (b) active import job in game A.
    _add_import_job(factory, game_a, status="created", links=((active, "processing"),))
    # Key in two games: plain in A, failed link in B -> excluded.
    _add_import_job(factory, game_b, status="completed", links=((shared, "failed"),))
    # (d) the orphan execution belongs to no game.

    repository = SqlAlchemyPipelineStateCompactionRepository(factory, tmp_path)
    preview = repository.create_preview(cutoff_at=datetime.now(UTC) + timedelta(hours=1))

    manifest = tmp_path / Path(preview.manifest_relative_path)
    lines = manifest.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    entries = [json.loads(line) for line in lines[1:]]
    assert [entry["fileExecutionKey"] for entry in entries] == sorted((plain, late))
    assert preview.candidate_count == header["candidateCount"] == 2
    assert preview.stage_result_count == 4
    assert preview.candidate_bytes == sum(entry["disposableBytes"] for entry in entries) > 0
    by_key = {entry["fileExecutionKey"]: entry for entry in entries}
    final_ids = by_key[plain]["terminalManifest"]["finalResultIds"]
    assert final_ids["sourceImages"] == [str(sources_a[plain])]
    assert {item["stage"] for item in by_key[plain]["terminalManifest"]["stages"]} == set(_STAGES)

    # After the preview, game B starts an import that links "late": the
    # worker's per-game re-check must keep it (conflict), not delete it.
    _add_import_job(factory, game_b, status="created", links=((late, "processing"),))

    job = create_job(
        JobType.STORAGE_PIPELINE_COMPACTION,
        game_id=None,
        input_payload={
            "schema_version": 1,
            "mode": "execute",
            "manifest_relative_path": preview.manifest_relative_path,
            "manifest_checksum_sha256": preview.manifest_checksum_sha256,
        },
    )
    context = _Context()
    PipelineStateCompactionHandler(factory, tmp_path, database)(cast(Any, context), job)

    final = context.checkpoints[-1]["checkpoint_payload"]
    assert isinstance(final, dict)
    assert final["compacted_count"] == 1
    assert final["conflict_count"] == 1
    stages = _stages_by_key(database)
    # (a) the plain candidate lost its disposable payloads; board_detection stays.
    assert stages[plain] == {"board_detection"}
    assert "board_detection" not in DISPOSABLE_STAGE_PAYLOADS
    # (b)-(d), the shared key and the late-blocked key are untouched.
    for key in (late, active, geometry, orphan, shared):
        assert stages[key] == set(_STAGES), key
    with database.connect() as connection:
        manifests = connection.execute(
            text("SELECT file_execution_key FROM public.image_pipeline_terminal_manifests")
        ).scalars()
        assert list(manifests) == [plain]
