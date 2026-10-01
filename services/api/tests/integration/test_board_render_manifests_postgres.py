"""TASK-0757: board render manifest table, migration 0131 and resumable backfill.

Runs on a dedicated ``*_test`` database only.  The game is provisioned through
the real partition lifecycle, so every row lives in ``game_data_v2`` under RLS.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.board_render_manifests import sha256_canonical_json
from game_predictor_api.domain.image_geometry_v2 import canonical_json_bytes
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.storage.board_render_manifest_backfill import (
    BackfillBatchResult,
    preview_counts,
    run_game,
)
from game_predictor_api.storage.database import GameStorageSession
from game_predictor_api.storage.game_data_v2_manifest_v3 import CREATE_TABLES
from game_predictor_api.storage.game_partition_lifecycle import (
    GamePartitionLifecycleKind,
    GamePartitionLifecycleRepository,
    partition_name,
)
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.models import (
    CellObservationModel,
    ImageBoardGeometryRevisionModel,
    ImageFileExecutionModel,
    ImageImportJobFileModel,
    ImageReviewItemModel,
    ImageSourceGeometryRevisionModel,
    JobModel,
    RecognizedBoardModel,
    RulesVersionModel,
    SourceImageModel,
)
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit isolated PostgreSQL tests only",
)

_FINGERPRINT = "b" * 64
_ALEMBIC_INI = Path(__file__).resolve().parents[4] / "alembic.ini"


@dataclass(frozen=True)
class _Database:
    engine: Engine
    config: Config


@pytest.fixture
def database() -> Iterator[_Database]:
    name = "game_predictor_task0757_" + uuid4().hex[:12] + "_test"
    assert re.fullmatch(r"game_predictor_task0757_[0-9a-f]{12}_test", name)
    url = make_url(ApiSettings.from_environment().database_url)
    assert url.database != name
    maintenance = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"},
    )
    engine = create_engine(url.set(database=name), connect_args={"connect_timeout": 5})
    config = Config(str(_ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        url.set(database=name).render_as_string(hide_password=False).replace("%", "%%"),
    )
    with maintenance.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    try:
        command.upgrade(config, "head")
        yield _Database(engine=engine, config=config)
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
            # Backends of just-closed pools (Alembic, lifecycle) can linger for
            # a moment in pg_stat_activity; wait briefly before refusing.
            active = -1
            for _attempt in range(50):
                active = connection.execute(
                    text("SELECT count(*) FROM pg_stat_activity WHERE datname=:name"),
                    {"name": name},
                ).scalar_one()
                if active == 0:
                    break
                time.sleep(0.1)
            assert active == 0, "Refusing DROP while a test connection remains"
            connection.exec_driver_sql(f'DROP DATABASE "{name}"')
        maintenance.dispose()


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


def _factory(engine: Engine) -> sessionmaker[Session]:
    return cast(
        "sessionmaker[Session]",
        sessionmaker(bind=engine, class_=GameStorageSession, expire_on_commit=False),
    )


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _spec(board: str, index: int) -> dict[str, object]:
    return {
        "boardLabel": board,
        "cellIndex": index,
        "quad": [[10.5, 20.25], [30.125, 20.25], [30.125, 40.0], [10.5, 40.0]],
        "scale": 1e-07,
        "outputSize": [96, 96],
        "logicalCellKeyV2Sha256": _sha(f"{board}:key2:{index}"),
        "renderIdentityV2Sha256": _sha(f"{board}:id2:{index}"),
    }


@dataclass(frozen=True)
class _Seed:
    game_id: UUID
    good: UUID
    bad: UUID
    partial: UUID
    legacy: UUID
    revised: UUID


def _observation(
    board: RecognizedBoardModel,
    label: str,
    index: int,
    source_geometry_id: UUID,
    *,
    checksum_override: str | None = None,
) -> CellObservationModel:
    spec = _spec(label, index)
    pixel = _sha(f"{label}:px:{index}")
    return CellObservationModel(
        recognized_board_id=board.id,
        row_index=index // 5,
        column_index=index % 5,
        asset_mode="virtual_source",
        source_geometry_revision_id=source_geometry_id,
        logical_cell_key=_sha(f"{label}:key:{index}"),
        logical_cell_key_v2=_sha(f"{label}:key2:{index}"),
        render_identity_v2_sha256=_sha(f"{label}:id2:{index}"),
        render_spec=spec,
        render_spec_checksum_sha256=checksum_override or sha256_canonical_json(spec),
        rendered_pixel_checksum_sha256=pixel,
        extractor_version="virtual-cell-renderer-test-v1",
        crop_relative_path=None,
        crop_checksum_sha256=pixel,
        cropper_version="virtual-cell-renderer-test-v1",
        prediction={"symbolCode": "A", "confidence": 0.9, "alternatives": []},
    )


def _seed(factory: sessionmaker[Session], game_id: UUID) -> _Seed:
    now = datetime.now(UTC)
    key = _sha("source-a")
    with factory.begin() as session:
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
    with game_storage_scope(game_id), factory.begin() as session:
        job = JobModel(
            game_id=game_id,
            job_type="import",
            status="waiting_for_review",
            input_payload={"import_kind": "image_directory"},
            input_key=uuid4().hex,
        )
        session.add(job)
        session.flush()
        session.add(
            ImageImportJobFileModel(
                job_id=job.id,
                file_execution_key=key,
                order_index=0,
                source_relative_path="seq_1.jpg",
                workflow_checkpoint_payload={},
                workflow_status="waiting_for_review",
                review_required=True,
            )
        )
        source = SourceImageModel(
            import_job_id=job.id,
            file_execution_key=key,
            relative_path="seq_1.jpg",
            checksum_sha256=key,
            width=1920,
            height=1080,
            status="waiting_for_review",
        )
        session.add(source)
        rules = RulesVersionModel(
            game_id=game_id,
            version=1,
            rows=3,
            columns=5,
            spin_cost=0,
            status=RulesVersionStatus.DRAFT,
            created_at=now,
            published_at=None,
        )
        session.add(rules)
        session.flush()
        geometry = ImageSourceGeometryRevisionModel(
            game_id=game_id,
            source_image_id=source.id,
            topology_rules_version_id=rules.id,
            revision=0,
            sequence_range_start=1,
            sequence_range_end=5,
            active_board_slots=[0, 1, 2, 3, 4],
            coordinate_space="exif-normalized-rgb-pixels-v1",
            source_checksum_sha256=key,
            normalized_pixel_checksum_sha256="c" * 64,
            oriented_width=1920,
            oriented_height=1080,
            normalization_adapter_version="normalization-test-v1",
            global_initialization={},
            board_geometries=[{"positionIndex": slot} for slot in range(5)],
            engine_kind="structured_opencv_v1",
            engine_version="structured-test-v1",
            geometry_source="auto",
            status="accepted",
            geometry_checksum_sha256="d" * 64,
            processing_time_ms=1,
            warnings=[],
            created_by="task-0757-test",
            created_at=now,
        )
        session.add(geometry)
        session.flush()

        def board(position: int, *, virtual: bool = True, **values: object) -> RecognizedBoardModel:
            record = RecognizedBoardModel(
                source_image_id=source.id,
                position_index=position,
                sequence_number_raw=str(position + 1),
                sequence_number=position + 1,
                sequence_confidence=1.0,
                board_geometry={},
                asset_mode="virtual_source" if virtual else "legacy_file",
                source_geometry_revision_id=geometry.id if virtual else None,
                geometry_engine_name="structured_opencv_v1" if virtual else None,
                geometry_engine_version="structured-test-v1" if virtual else None,
                geometry_checksum_sha256="d" * 64 if virtual else None,
                board_relative_path=None if virtual else f"boards/{position}.png",
                board_checksum_sha256=None if virtual else "e" * 64,
                cells_prediction={"cells": [], "modelVersion": "test"},
                board_confidence=1.0,
                pipeline_fingerprint=_FINGERPRINT,
                grid_rows=3,
                grid_columns=5,
                status="pending_review",
                **values,
            )
            session.add(record)
            session.flush()
            return record

        good = board(0)
        bad = board(1)
        partial = board(2, completeness_status="pending_partial", unavailable_cell_indices=[14])
        legacy = board(3, virtual=False)
        revised = board(4)
        for index in range(15):
            session.add(_observation(good, "good", index, geometry.id))
            session.add(
                _observation(
                    bad,
                    "bad",
                    index,
                    geometry.id,
                    checksum_override=("f" * 64 if index == 7 else None),
                )
            )
            session.add(_observation(revised, "revised", index, geometry.id))
            if index != 14:
                session.add(_observation(partial, "partial", index, geometry.id))
        review = ImageReviewItemModel(
            game_id=game_id,
            import_job_id=job.id,
            recognized_board_id=revised.id,
            status="pending",
            snapshot={},
            resolution_revision=0,
            created_at=now,
        )
        session.add(review)
        session.flush()
        virtual_spec: dict[str, object] = {
            "assetMode": "virtual_source",
            "cells": [
                {
                    "cellIndex": index,
                    "renderSpec": _spec("revised-r1", index),
                    "renderSpecChecksumSha256": sha256_canonical_json(_spec("revised-r1", index)),
                }
                for index in range(15)
            ],
            "schemaVersion": "virtual-board-render-manifest-v2-dual-identity-v1",
        }
        session.add(
            ImageBoardGeometryRevisionModel(
                review_item_id=review.id,
                recognized_board_id=revised.id,
                revision=1,
                idempotency_key=uuid4(),
                command_sha256="a" * 64,
                corners=[{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}, {"x": 0, "y": 1}],
                geometry={},
                asset_mode="virtual_source",
                source_geometry_revision_id=geometry.id,
                geometry_checksum_sha256="d" * 64,
                virtual_render_spec=virtual_spec,
                virtual_render_spec_checksum_sha256=hashlib.sha256(
                    canonical_json_bytes(virtual_spec)
                ).hexdigest(),
                cropper_version="virtual-cell-renderer-test-v2",
                corrected_by="task-0757-test",
                created_at=now,
            )
        )
        revised.geometry_revision = 1
    return _Seed(game_id, good.id, bad.id, partial.id, legacy.id, revised.id)


def _manifests(engine: Engine, game_id: UUID) -> dict[tuple[UUID, int], dict[str, object]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """SELECT recognized_board_id, geometry_revision, cells,
                          manifest_checksum_sha256, extractor_version
                FROM game_data_v2.board_render_manifests WHERE game_id = :game_id"""
            ),
            {"game_id": game_id},
        ).mappings()
        return {
            (UUID(str(row["recognized_board_id"])), int(row["geometry_revision"])): dict(row)
            for row in rows
        }


def test_backfill_builds_verified_manifests_once_and_reports_refusals(
    database: _Database,
) -> None:
    engine = database.engine
    game_id = _provision_game(engine, "manifest-a")
    factory = _factory(engine)
    seed = _seed(factory, game_id)

    with Session(engine) as session, session.begin():
        before = preview_counts(session, game_id)
    assert before["boards_total"] == 5
    assert before["legacy_boards"] == 1
    assert before["revision_zero_boards"] == 3
    assert before["revision_zero_to_build"] == 3
    assert before["revision_positive_to_copy"] == 1
    assert before["revision_zero_without_observations"] == 0

    batches: list[BackfillBatchResult] = []
    last, exhausted = run_game(
        factory, game_id, after_board_id=None, batch_size=2, on_batch=batches.append
    )
    assert exhausted and last is not None
    totals: dict[str, int] = {}
    for batch in batches:
        for name, value in batch.counts.items():
            totals[name] = totals.get(name, 0) + value
    assert totals == {
        "built_revision_zero": 2,
        "copied": 1,
        "legacy_skipped": 1,
        "refused": 1,
    }
    refused = [board for batch in batches for board in batch.refused]
    assert [(board.recognized_board_id, board.code, board.cell_index) for board in refused] == [
        (seed.bad, "BOARD_RENDER_MANIFEST_CELL_CHECKSUM_MISMATCH", 7)
    ]

    stored = _manifests(engine, game_id)
    assert set(stored) == {(seed.good, 0), (seed.partial, 0), (seed.revised, 1)}
    for row in stored.values():
        # The JSONB round trip keeps the canonical checksum byte-exact.
        assert sha256_canonical_json(row["cells"]) == row["manifest_checksum_sha256"]
    good_cells = cast(dict[str, list[dict[str, object]]], stored[(seed.good, 0)]["cells"])
    assert [cell["cellIndex"] for cell in good_cells["cells"]] == list(range(15))
    assert good_cells["cells"][3]["renderSpec"] == _spec("good", 3)
    partial_cells = cast(dict[str, list[dict[str, object]]], stored[(seed.partial, 0)]["cells"])
    assert [cell["cellIndex"] for cell in partial_cells["cells"]] == list(range(14))
    assert stored[(seed.revised, 1)]["extractor_version"] == "virtual-cell-renderer-test-v2"

    # A second full run is a no-op: existing manifests are skipped unread.
    second: list[BackfillBatchResult] = []
    run_game(factory, game_id, after_board_id=None, batch_size=10, on_batch=second.append)
    assert sum(batch.counts["existing_skipped"] for batch in second) == 3
    assert (
        sum(batch.counts["built_revision_zero"] + batch.counts["copied"] for batch in second) == 0
    )
    assert _manifests(engine, game_id) == stored

    # Resume from a checkpoint cursor processes only later boards.
    ordered = sorted([seed.good, seed.bad, seed.partial, seed.legacy, seed.revised])
    resumed: list[BackfillBatchResult] = []
    run_game(factory, game_id, after_board_id=ordered[3], batch_size=10, on_batch=resumed.append)
    assert sum(batch.scanned for batch in resumed) == 1

    with Session(engine) as session, session.begin():
        after = preview_counts(session, game_id)
    assert after["revision_zero_to_build"] == 1  # the refused board
    assert after["revision_positive_to_copy"] == 0

    # Board deletion cascades to its manifests (cleanup deletes boards).
    with game_storage_scope(game_id), factory.begin() as session:
        session.execute(
            text("DELETE FROM cell_observations WHERE recognized_board_id = :board"),
            {"board": seed.good},
        )
        session.execute(
            text("DELETE FROM recognized_boards WHERE id = :board"), {"board": seed.good}
        )
    assert (seed.good, 0) not in _manifests(engine, game_id)


def test_import_writer_and_backfill_build_the_same_manifest(database: _Database) -> None:
    from game_predictor_worker.images.pipeline_store import (
        ImagePipelineStoreError,
        _ensure_import_render_manifest,
    )

    engine = database.engine
    game_id = _provision_game(engine, "manifest-writer")
    factory = _factory(engine)
    seed = _seed(factory, game_id)

    def crops(pixel_suffix: str = "") -> list[dict[str, object]]:
        return [
            {
                "assetMode": "virtual_source",
                "rowIndex": index // 5,
                "columnIndex": index % 5,
                "renderSpec": _spec("good", index),
                "renderSpecChecksumSha256": sha256_canonical_json(_spec("good", index)),
                "renderedPixelChecksumSha256": _sha(f"good:px:{index}{pixel_suffix}"),
                "logicalCellKeySha256": _sha(f"good:key:{index}"),
                "extractorVersion": "virtual-cell-renderer-test-v1",
            }
            for index in range(15)
        ]

    with game_storage_scope(game_id), factory.begin() as session:
        board = session.get(RecognizedBoardModel, seed.good)
        assert board is not None and board.source_geometry_revision_id is not None
        source_geometry_id = board.source_geometry_revision_id
        _ensure_import_render_manifest(
            session,
            board,
            crops(),
            cropper_version="virtual-cell-renderer-test-v1",
            game_id=game_id,
            source_geometry_revision_id=source_geometry_id,
        )
    # Re-import of the same board is idempotent; different pixels conflict.
    with game_storage_scope(game_id), factory.begin() as session:
        board = session.get(RecognizedBoardModel, seed.good)
        assert board is not None
        _ensure_import_render_manifest(
            session,
            board,
            crops(),
            cropper_version="virtual-cell-renderer-test-v1",
            game_id=game_id,
            source_geometry_revision_id=source_geometry_id,
        )
        with pytest.raises(ImagePipelineStoreError) as conflict:
            _ensure_import_render_manifest(
                session,
                board,
                crops(":changed"),
                cropper_version="virtual-cell-renderer-test-v1",
                game_id=game_id,
                source_geometry_revision_id=source_geometry_id,
            )
        assert conflict.value.code == "BOARD_RENDER_MANIFEST_CONFLICT"
    written = _manifests(engine, game_id)[(seed.good, 0)]

    # The backfill from the same board's observations yields a byte-identical manifest.
    with engine.begin() as connection:
        connection.execute(
            text(
                "DELETE FROM game_data_v2.board_render_manifests "
                "WHERE game_id = :game_id AND recognized_board_id = :board"
            ),
            {"game_id": game_id, "board": seed.good},
        )
    run_game(factory, game_id, after_board_id=None, batch_size=50)
    rebuilt = _manifests(engine, game_id)[(seed.good, 0)]
    assert rebuilt["manifest_checksum_sha256"] == written["manifest_checksum_sha256"]
    assert rebuilt["cells"] == written["cells"]
    assert rebuilt["extractor_version"] == written["extractor_version"]


def test_boards_without_renderable_cells_have_no_manifest(database: _Database) -> None:
    from game_predictor_api.storage.virtual_grid_geometry_repository import (
        SqlAlchemyVirtualGridGeometryRepository,
    )
    from game_predictor_worker.images.pipeline_store import _ensure_import_render_manifest

    engine = database.engine
    game_id = _provision_game(engine, "manifest-empty")
    factory = _factory(engine)
    seed = _seed(factory, game_id)
    now = datetime.now(UTC)
    empty_spec: dict[str, object] = {"assetMode": "virtual_source", "cells": []}
    with game_storage_scope(game_id), factory.begin() as session:
        template = session.get(RecognizedBoardModel, seed.good)
        assert template is not None and template.source_geometry_revision_id is not None
        source = session.get(SourceImageModel, template.source_image_id)
        assert source is not None

        def board(position: int) -> RecognizedBoardModel:
            record = RecognizedBoardModel(
                source_image_id=template.source_image_id,
                position_index=position,
                sequence_number_raw=str(position + 1),
                sequence_number=position + 1,
                sequence_confidence=1.0,
                board_geometry={},
                asset_mode="virtual_source",
                source_geometry_revision_id=template.source_geometry_revision_id,
                geometry_engine_name="structured_opencv_v1",
                geometry_engine_version="structured-test-v1",
                geometry_checksum_sha256="d" * 64,
                cells_prediction={"cells": [], "modelVersion": "test"},
                completeness_status="pending_partial",
                unavailable_cell_indices=list(range(15)),
                board_confidence=1.0,
                pipeline_fingerprint=_FINGERPRINT,
                grid_rows=3,
                grid_columns=5,
                status="pending_review",
            )
            session.add(record)
            session.flush()
            return record

        # Import path: every cell outside the source, so no crops and no observations.
        imported = board(5)
        _ensure_import_render_manifest(
            session,
            imported,
            [],
            cropper_version="virtual-cell-renderer-test-v1",
            game_id=game_id,
            source_geometry_revision_id=template.source_geometry_revision_id,
        )
        # Manual path: a saved virtual revision whose render has no cells.
        manual = board(6)
        review = ImageReviewItemModel(
            game_id=game_id,
            import_job_id=source.import_job_id,
            recognized_board_id=manual.id,
            status="pending",
            snapshot={},
            resolution_revision=0,
            created_at=now,
        )
        session.add(review)
        session.flush()
        revision = ImageBoardGeometryRevisionModel(
            review_item_id=review.id,
            recognized_board_id=manual.id,
            revision=1,
            idempotency_key=uuid4(),
            command_sha256="a" * 64,
            corners=[{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}, {"x": 0, "y": 1}],
            geometry={},
            asset_mode="virtual_source",
            source_geometry_revision_id=template.source_geometry_revision_id,
            geometry_checksum_sha256="d" * 64,
            virtual_render_spec=empty_spec,
            virtual_render_spec_checksum_sha256=sha256_canonical_json(empty_spec),
            cropper_version="virtual-cell-renderer-test-v2",
            corrected_by="task-0757-test",
            created_at=now,
        )
        session.add(revision)
        SqlAlchemyVirtualGridGeometryRepository(session)._add_render_manifest(
            revision, game_id=game_id
        )
        manual.geometry_revision = 1
        empty_ids = {imported.id, manual.id}

    batches: list[BackfillBatchResult] = []
    run_game(factory, game_id, after_board_id=None, batch_size=50, on_batch=batches.append)
    assert sum(batch.counts["no_cells_skipped"] for batch in batches) == 2
    refused = {board.recognized_board_id for batch in batches for board in batch.refused}
    assert refused == {seed.bad}
    stored = _manifests(engine, game_id)
    assert not {board_id for board_id, _revision in stored} & empty_ids
    assert set(stored) == {(seed.good, 0), (seed.partial, 0), (seed.revised, 1)}


def _reset_to_revision(database: _Database, revision: str) -> None:
    """Rebuild the isolated database at ``revision``.

    Migration 0133 (TASK-0790) refuses to downgrade, so a test of an older
    migration's downgrade cannot start from head.
    """

    database.engine.dispose()
    with database.engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA IF EXISTS game_data_v2 CASCADE")
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
    command.upgrade(database.config, revision)


def test_migration_0131_partitions_registered_games_and_downgrades(database: _Database) -> None:
    engine = database.engine
    _reset_to_revision(database, "0132_symbol_reference_images_cell_identity")
    game_id = _provision_game(engine, "manifest-b")
    child = partition_name(game_id, "board_render_manifests")

    def state() -> tuple[bool, str, int]:
        with engine.connect() as connection:
            exists = connection.execute(
                text("SELECT to_regclass(:name) IS NOT NULL"),
                {"name": f"game_data_v2.{child}"},
            ).scalar_one()
            version, revision = connection.execute(
                text(
                    "SELECT manifest_version, revision FROM public.game_storage_locations "
                    "WHERE game_id = :game_id"
                ),
                {"game_id": game_id},
            ).one()
        return bool(exists), str(version), int(revision)

    exists, version, revision = state()
    assert exists and version == "game-data-v2-manifest-v3"

    command.downgrade(database.config, "0130_board_search_share_sessions")
    exists, version, downgraded_revision = state()
    assert not exists and version == "game-data-v2-manifest-v1"
    assert downgraded_revision == revision + 1
    with engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM public.game_storage_table_manifest "
                    "WHERE manifest_version = 'game-data-v2-manifest-v3'"
                )
            ).scalar_one()
            == 0
        )

    command.upgrade(database.config, "0132_symbol_reference_images_cell_identity")
    exists, version, _revision = state()
    assert exists and version == "game-data-v2-manifest-v3"
    with engine.connect() as connection:
        rls = connection.execute(
            text(
                "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
                "WHERE oid = 'game_data_v2.board_render_manifests'::regclass"
            )
        ).scalar_one()
        registered = connection.execute(
            text(
                "SELECT ownership, partitioned FROM public.game_storage_table_manifest "
                "WHERE manifest_version = 'game-data-v2-manifest-v3' "
                "AND table_name = 'board_render_manifests'"
            )
        ).one()
    assert rls is True
    assert tuple(registered) == ("game", True)

    # A game provisioned after the upgrade gets the partition from the lifecycle.
    later = _provision_game(engine, "manifest-c")
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT to_regclass(:name) IS NOT NULL"),
            {"name": f"game_data_v2.{partition_name(later, 'board_render_manifests')}"},
        ).scalar_one()
