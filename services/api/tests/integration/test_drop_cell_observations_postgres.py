"""TASK-0759 (D-467 S5): migration 0134 on an isolated ``*_test`` database.

The database is built at 0133 and three games are provisioned with the
storage manifest v3 lifecycle (current code provisions v4, so the lifecycle
and router are pinned to v3 for the seed only).  Every preflight refusal must
leave the schema untouched; the upgrade drops the three tables with their
partitions and moves the registry to v4; downgrade refuses; a game
provisioned afterwards gets only manifest v4 partitions.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.storage import game_data_v2_manifest_v3 as manifest_v3
from game_predictor_api.storage import game_data_v2_manifest_v4 as manifest_v4
from game_predictor_api.storage import game_partition_lifecycle, game_storage_routing
from game_predictor_api.storage.database import GameStorageSession
from game_predictor_api.storage.game_partition_lifecycle import (
    GamePartitionLifecycleKind,
    GamePartitionLifecycleRepository,
)
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
    game_storage_scope,
)
from game_predictor_api.storage.models import (
    ImageFileExecutionModel,
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

_ALEMBIC_INI = Path(__file__).resolve().parents[4] / "alembic.ini"
_BEFORE = "0133_virtual_only_import_policies"
_HEAD = "0134_drop_cell_observations_and_legacy_archive"
_FINGERPRINT = "b" * 64
_DROPPED = (
    "cell_observations",
    "legacy_board_search_archive_documents",
    "legacy_board_search_archive_states",
)


@dataclass(frozen=True)
class _Database:
    engine: Engine
    config: Config


@pytest.fixture
def database() -> Iterator[_Database]:
    name = "game_predictor_task0759_" + uuid4().hex[:12] + "_test"
    assert re.fullmatch(r"game_predictor_task0759_[0-9a-f]{12}_test", name)
    url = make_url(ApiSettings.from_environment().owner_database_url)
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
        command.upgrade(config, _BEFORE)
        with engine.begin() as connection:
            # The current ORM maps the geometry gate columns of migration 0139
            # (TASK-0807); this pre-0134 schema gets them on the test database only.
            connection.exec_driver_sql(
                "ALTER TABLE game_data_v2.source_images "
                "ADD COLUMN geometry_completeness_status varchar(24), "
                "ADD COLUMN geometry_completeness_evaluated_at timestamptz, "
                "ADD COLUMN geometry_exception_reason text, "
                "ADD COLUMN geometry_exception_by varchar(200), "
                "ADD COLUMN geometry_exception_at timestamptz"
            )
        yield _Database(engine=engine, config=config)
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
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


@contextmanager
def _manifest_v3_code(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Run the lifecycle and router as the v3 code that preceded 0134."""

    with monkeypatch.context() as patch:
        patch.setattr(game_partition_lifecycle, "VERSION", manifest_v3.VERSION)
        patch.setattr(game_partition_lifecycle, "CREATE_TABLES", manifest_v3.CREATE_TABLES)
        patch.setattr(game_partition_lifecycle, "DELETE_TABLES", manifest_v3.DELETE_TABLES)
        patch.setattr(game_storage_routing, "VERSION", manifest_v3.VERSION)
        patch.setattr(game_storage_routing, "GAME_TABLES", manifest_v3.GAME_TABLES)
        yield


def _partition(game_id: UUID, table: str) -> str:
    suffix = hashlib.sha256(table.encode("ascii")).hexdigest()[:12]
    return f"gpv2_{game_id.hex[:12]}_{suffix}"


def _provision_game(engine: Engine, code: str, tables: tuple[str, ...]) -> UUID:
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
    for _ in range(len(tables) + 2):
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


@dataclass(frozen=True)
class _Seeded:
    source_image_id: UUID
    source_geometry_id: UUID
    complete: UUID


def _seed_game(factory: sessionmaker[Session], game_id: UUID, label: str) -> _Seeded:
    """One source with a complete virtual board that has a manifest and a cell record."""

    now = datetime.now(UTC)
    key = hashlib.sha256(f"source-{label}".encode()).hexdigest()
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
        source = SourceImageModel(
            import_job_id=job.id,
            file_execution_key=key,
            relative_path=f"{label}.jpg",
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
            sequence_range_end=9,
            active_board_slots=list(range(9)),
            coordinate_space="exif-normalized-rgb-pixels-v1",
            source_checksum_sha256=key,
            normalized_pixel_checksum_sha256="c" * 64,
            oriented_width=1920,
            oriented_height=1080,
            normalization_adapter_version="normalization-test-v1",
            global_initialization={},
            board_geometries=[{"positionIndex": slot} for slot in range(9)],
            engine_kind="structured_opencv_v1",
            engine_version="structured-test-v1",
            geometry_source="auto",
            status="accepted",
            geometry_checksum_sha256="d" * 64,
            processing_time_ms=1,
            warnings=[],
            created_by="task-0759-test",
            created_at=now,
        )
        session.add(geometry)
        session.flush()
        complete = _board(session, source.id, geometry.id, position=0)
        seeded = _Seeded(source.id, geometry.id, complete)
    _add_manifest(factory, game_id, complete, geometry_id=seeded.source_geometry_id)
    with game_storage_scope(game_id), factory.begin() as session:
        # One historical per-cell import record: the drop removes real data.
        session.execute(
            text(
                """INSERT INTO cell_observations (game_id, id, recognized_board_id,
                    row_index, column_index, asset_mode, crop_relative_path,
                    crop_checksum_sha256, cropper_version, prediction)
                VALUES (:game, :id, :board, 0, 0, 'legacy_file', 'cells/0.png',
                    :checksum, 'v19', '{}'::jsonb)"""
            ),
            {"game": game_id, "id": uuid4(), "board": complete, "checksum": "e" * 64},
        )
    return seeded


def _board(
    session: Session,
    source_image_id: UUID,
    geometry_id: UUID,
    *,
    position: int,
    virtual: bool = True,
    **values: object,
) -> UUID:
    record = RecognizedBoardModel(
        source_image_id=source_image_id,
        position_index=position,
        sequence_number_raw=str(position + 1),
        sequence_number=position + 1,
        sequence_confidence=1.0,
        board_geometry={},
        asset_mode="virtual_source" if virtual else "legacy_file",
        source_geometry_revision_id=geometry_id if virtual else None,
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
    return record.id


def _add_manifest(
    factory: sessionmaker[Session], game_id: UUID, board_id: UUID, *, geometry_id: UUID
) -> None:
    with game_storage_scope(game_id), factory.begin() as session:
        session.execute(
            text(
                """INSERT INTO board_render_manifests (game_id, recognized_board_id,
                    geometry_revision, source_geometry_revision_id, extractor_version,
                    cells, manifest_checksum_sha256)
                VALUES (:game, :board, 0, :geometry, 'renderer-test-v1',
                    '{"cells": [{"cellIndex": 0}]}'::jsonb, :checksum)"""
            ),
            {"game": game_id, "board": board_id, "geometry": geometry_id, "checksum": "f" * 64},
        )


def _add_board(
    factory: sessionmaker[Session],
    game_id: UUID,
    seeded: _Seeded,
    *,
    position: int,
    **values: object,
) -> UUID:
    with game_storage_scope(game_id), factory.begin() as session:
        return _board(
            session, seeded.source_image_id, seeded.source_geometry_id, position=position, **values
        )


def _delete_board(factory: sessionmaker[Session], game_id: UUID, board_id: UUID) -> None:
    with game_storage_scope(game_id), factory.begin() as session:
        session.execute(text("DELETE FROM recognized_boards WHERE id = :id"), {"id": board_id})


def _version(engine: Engine) -> str:
    with engine.connect() as connection:
        return str(connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one())


def _relations(engine: Engine, names: list[str]) -> set[str]:
    with engine.connect() as connection:
        return {
            name
            for name in names
            if connection.execute(
                text("SELECT to_regclass(:name) IS NOT NULL"), {"name": f"game_data_v2.{name}"}
            ).scalar_one()
        }


def _locations(engine: Engine) -> dict[UUID, tuple[str, int]]:
    with engine.connect() as connection:
        return {
            UUID(str(row[0])): (str(row[1]), int(row[2]))
            for row in connection.execute(
                text(
                    "SELECT game_id, manifest_version, revision FROM public.game_storage_locations"
                )
            )
        }


def _refused(database: _Database, code: str, untouched: list[str]) -> None:
    locations = _locations(database.engine)
    with pytest.raises(Exception, match=code):
        command.upgrade(database.config, _HEAD)
    assert _version(database.engine) == _BEFORE
    assert _relations(database.engine, untouched) == set(untouched)
    assert _locations(database.engine) == locations


def test_migration_0134_refuses_unsafe_states_then_drops_and_moves_to_v4(
    database: _Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = database.engine
    factory = _factory(engine)
    with _manifest_v3_code(monkeypatch):
        games = [
            _provision_game(engine, f"drop-{label}", manifest_v3.CREATE_TABLES)
            for label in ("a", "b", "c")
        ]
        seeded = {game: _seed_game(factory, game, str(index)) for index, game in enumerate(games)}
    first = games[0]
    dropped_relations = [*_DROPPED] + [
        _partition(game, table) for game in games for table in _DROPPED
    ]
    assert _relations(engine, dropped_relations) == set(dropped_relations)
    before = _locations(engine)
    assert {version for version, _revision in before.values()} == {manifest_v3.VERSION}

    with _manifest_v3_code(monkeypatch):
        # A virtual board with available cells but no manifest of its revision.
        missing = _add_board(factory, first, seeded[first], position=1)
        _refused(database, "BOARD_RENDER_MANIFEST_MISSING", dropped_relations)
        _delete_board(factory, first, missing)
        # A board whose every cell is outside the photo has no manifest by design.
        _add_board(
            factory,
            first,
            seeded[first],
            position=2,
            completeness_status="pending_partial",
            unavailable_cell_indices=list(range(15)),
        )
        # A legacy board at revision 0 still reads its crops from the records.
        legacy = _add_board(factory, first, seeded[first], position=3, virtual=False)
        _refused(database, "CELL_OBSERVATIONS_LEGACY_REVISION_ZERO_PRESENT", dropped_relations)
        _delete_board(factory, first, legacy)

    # A store registered with another manifest version.
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "ALTER TABLE public.game_storage_locations "
            "DROP CONSTRAINT ck_game_storage_locations_manifest_version_v3"
        )
        connection.execute(
            text(
                "UPDATE public.game_storage_locations "
                "SET manifest_version = 'game-data-v2-manifest-v1' WHERE game_id = :game"
            ),
            {"game": games[1]},
        )
    _refused(database, "GAME_STORAGE_MANIFEST_UNEXPECTED", dropped_relations)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE public.game_storage_locations "
                "SET manifest_version = :version WHERE game_id = :game"
            ),
            {"version": manifest_v3.VERSION, "game": games[1]},
        )
        connection.exec_driver_sql(
            "ALTER TABLE public.game_storage_locations ADD CONSTRAINT "
            "ck_game_storage_locations_manifest_version_v3 "
            "CHECK (manifest_version = 'game-data-v2-manifest-v3')"
        )

    # A foreign key from outside the dropped set.
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE public.task0759_probe (game_id UUID, id UUID, "
            "FOREIGN KEY (game_id, id) REFERENCES game_data_v2.cell_observations (game_id, id))"
        )
    _refused(database, "GAME_STORAGE_DROP_FOREIGN_KEY_PRESENT", dropped_relations)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE public.task0759_probe")

    # A non-empty frozen archive.
    with engine.begin() as connection:
        connection.execute(
            text(
                """INSERT INTO game_data_v2.legacy_board_search_archive_states (game_id, status,
                    sequence_start, sequence_end, document_count, source_preview_fingerprint,
                    archive_fingerprint) VALUES (:game, 'building', 1, 1, 0, :fp, :fp)"""
            ),
            {"game": first, "fp": "a" * 64},
        )
    _refused(database, "LEGACY_BOARD_SEARCH_ARCHIVE_NOT_EMPTY", dropped_relations)
    with engine.begin() as connection:
        connection.exec_driver_sql("DELETE FROM game_data_v2.legacy_board_search_archive_states")

    command.upgrade(database.config, _HEAD)
    assert _version(engine) == _HEAD
    assert _relations(engine, dropped_relations) == set()
    after = _locations(engine)
    assert after == {
        game: (manifest_v4.VERSION, revision + 1) for game, (_v, revision) in before.items()
    }
    with engine.connect() as connection:
        registered = set(
            connection.execute(
                text(
                    "SELECT table_name FROM public.game_storage_table_manifest "
                    "WHERE manifest_version = :version AND partitioned"
                ),
                {"version": manifest_v4.VERSION},
            ).scalars()
        )
        manifests = connection.execute(
            text("SELECT count(*) FROM game_data_v2.board_render_manifests")
        ).scalar_one()
        boards = connection.execute(
            text("SELECT count(*) FROM game_data_v2.recognized_boards")
        ).scalar_one()
    assert registered == set(manifest_v4.GAME_TABLES)
    assert not registered & set(_DROPPED)
    # Boards and manifests are untouched; only the dropped tables are gone.
    assert manifests == 3 and boards == 4
    # The current (v4) router binds every migrated store.
    for game in games:
        with Session(engine) as session, session.begin():
            location = GameStorageRouter().bind(session, game, intent=GameStorageIntent.READ)
            assert location.manifest_version == manifest_v4.VERSION

    # Downgrade is refused and leaves the schema at 0134.
    with pytest.raises(Exception, match="CELL_OBSERVATIONS_DROP_IRREVERSIBLE"):
        command.downgrade(database.config, _BEFORE)
    assert _version(engine) == _HEAD

    # 0132 cannot restore the reference observation once the records are gone.
    command.stamp(database.config, "0132_symbol_reference_images_cell_identity")
    with pytest.raises(Exception, match="SYMBOL_REFERENCE_OBSERVATIONS_DROPPED"):
        command.downgrade(database.config, "0131_board_render_manifests")
    assert _version(engine) == "0132_symbol_reference_images_cell_identity"
    command.stamp(database.config, _HEAD)

    # A game provisioned after 0134 gets exactly the manifest v4 partitions.
    later = _provision_game(engine, "drop-later", manifest_v4.CREATE_TABLES)
    assert _relations(engine, [_partition(later, table) for table in _DROPPED]) == set()
    v4_partitions = [_partition(later, table) for table in manifest_v4.CREATE_TABLES]
    assert _relations(engine, v4_partitions) == set(v4_partitions)
    assert _locations(engine)[later][0] == manifest_v4.VERSION
