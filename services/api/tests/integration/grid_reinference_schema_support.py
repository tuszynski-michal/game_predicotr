"""Schema assertions on the workflow owner's one disposable PostgreSQL database.

This module creates no database, role, service, image or inference process.
Call after fixture migration to head and application-role provisioning, before
workflow data. The caller owns the database and role cleanup receipt.
"""

import re
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.storage.game_data_v2_manifest_v12 import ADDED_GAME_TABLES, CREATE_TABLES
from game_predictor_api.storage.game_partition_lifecycle import (
    GamePartitionLifecycleKind,
    GamePartitionLifecycleRepository,
    partition_name,
)
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


def _lifecycle(engine: Engine, game_id: UUID, kind: GamePartitionLifecycleKind) -> None:
    with Session(engine) as session, session.begin():
        operation = (
            GamePartitionLifecycleRepository(session)
            .start_or_resume(game_id=game_id, kind=kind)
            .operation_id
        )
    for _ in range(len(CREATE_TABLES) + 2):
        with Session(engine) as session, session.begin():
            receipt = GamePartitionLifecycleRepository(session).run_next(operation)
        if receipt.status == "done":
            return
    raise AssertionError("Bounded reinference schema lifecycle did not complete")


def _scope(session: Session, role: str, game_id: UUID) -> None:
    session.connection().exec_driver_sql(f'SET LOCAL ROLE "{role}"')
    GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)


def assert_grid_reinference_schema_postgres(engine: Engine, config: Config, role: str) -> None:
    """Verify existing/new partitions, DML/RLS, composite identity and retention.

    The fixture must already have at least one v11-provisioned game migrated to
    head; the helper checks its new partitions, then creates and deletes exactly
    two small games through the production lifecycle. Call before any reinference
    operation has been inserted, because empty downgrade/up is tested first.
    """
    assert re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", role)
    assert engine.url.database and engine.url.database.endswith("_test")
    with engine.connect() as connection:
        existing_games = list(
            connection.scalars(
                text("SELECT game_id FROM public.game_storage_locations ORDER BY game_id")
            )
        )
        assert existing_games, "Provision one game at v11 before upgrading the fixture"
        for game_id in existing_games:
            for table in ADDED_GAME_TABLES:
                assert connection.scalar(
                    text("SELECT to_regclass(:name)"),
                    {"name": "game_data_v2." + partition_name(game_id, table)},
                )
    command.downgrade(config, "0158_new_game_v3_bootstrap")
    command.upgrade(config, "head")
    games = (uuid4(), uuid4())
    operations, sources, targets = {}, {}, {}
    for index, game_id in enumerate(games):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.games "
                    "(id,code,name,status,expected_layout_count) VALUES "
                    "(:id,:code,:code,'draft',100)"
                ),
                {"id": game_id, "code": "task0999-schema-" + game_id.hex[:12]},
            )
        _lifecycle(engine, game_id, GamePartitionLifecycleKind.PROVISION)
        operation_id, source_id, job_id = uuid4(), uuid4(), uuid4()
        operations[game_id], sources[game_id], targets[game_id] = operation_id, source_id, uuid4()
        checksum, execution = str(index + 1) * 64, uuid4().hex * 2
        with Session(engine) as session, session.begin():
            _scope(session, role, game_id)
            assert tuple(
                session.execute(
                    text("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user")
                ).one()
            ) == (False, False)
            session.execute(
                text(
                    "INSERT INTO public.jobs "
                    "(id,game_id,job_type,status,input_payload,input_key) "
                    "VALUES (:id,:game,'import','created','{}',:key)"
                ),
                {"id": job_id, "game": game_id, "key": uuid4().hex},
            )
            session.execute(
                text(
                    "INSERT INTO public.image_file_executions "
                    "(file_execution_key,source_checksum_sha256,pipeline_fingerprint,"
                    "checkpoint_payload,status) VALUES(:key,:sha,:sha,'{}','completed')"
                ),
                {"game": game_id, "key": execution, "sha": checksum},
            )
            session.execute(
                text(
                    "INSERT INTO game_data_v2.source_images "
                    "(game_id,id,import_job_id,file_execution_key,relative_path,checksum_sha256,"
                    "width,height,status) "
                    "VALUES(:game,:id,:job,:key,'schema.jpg',:sha,10,10,'completed')"
                ),
                {
                    "game": game_id,
                    "id": source_id,
                    "job": job_id,
                    "key": execution,
                    "sha": checksum,
                },
            )
            session.execute(
                text(
                    "INSERT INTO game_data_v2.grid_reinference_operations "
                    "(game_id,id,idempotency_key,command_sha256,job_id,document) "
                    "VALUES(:game,:id,:key,:sha,:job,'{}')"
                ),
                {
                    "game": game_id,
                    "id": operation_id,
                    "key": uuid4(),
                    "sha": checksum,
                    "job": job_id,
                },
            )
            session.execute(
                text(
                    "INSERT INTO game_data_v2.grid_reinference_sources "
                    "(game_id,operation_id,ordinal,source_image_id,live_source_image_id,document) "
                    "VALUES(:game,:op,1,:source,:source,'{}')"
                ),
                {"game": game_id, "op": operation_id, "source": source_id},
            )
            session.execute(
                text(
                    "INSERT INTO game_data_v2.grid_reinference_targets "
                    "(game_id,operation_id,ordinal,source_ordinal,source_image_id,position_index,"
                    "target_result_id,snapshot,fingerprint_sha256) "
                    "VALUES(:game,:op,11,1,:source,0,:result,'{}',:sha)"
                ),
                {
                    "game": game_id,
                    "op": operation_id,
                    "source": source_id,
                    "result": targets[game_id],
                    "sha": checksum,
                },
            )
    for game_id, other in (games, tuple(reversed(games))):
        with Session(engine) as session, session.begin():
            _scope(session, role, game_id)
            for table in ADDED_GAME_TABLES:
                assert session.scalar(text(f"SELECT count(*) FROM game_data_v2.{table}")) == 1
                assert (
                    session.scalar(
                        text(f"SELECT count(*) FROM game_data_v2.{table} WHERE game_id=:game"),
                        {"game": other},
                    )
                    == 0
                )
                child = partition_name(other, table)
                assert session.scalar(text(f"SELECT count(*) FROM game_data_v2.{child}")) == 0
            session.execute(
                text(
                    "UPDATE game_data_v2.grid_reinference_targets "
                    "SET outcome='unchanged',result='{}' WHERE target_result_id=:result"
                ),
                {"result": targets[game_id]},
            )
            assert (
                session.scalar(text("SELECT outcome FROM game_data_v2.grid_reinference_targets"))
                == "unchanged"
            )
            with pytest.raises(DBAPIError), session.begin_nested():
                session.execute(
                    text("UPDATE game_data_v2.grid_reinference_targets SET game_id=:other"),
                    {"other": other},
                )
            with pytest.raises(DBAPIError), session.begin_nested():
                session.execute(
                    text("UPDATE game_data_v2.grid_reinference_targets SET source_image_id=:other"),
                    {"other": sources[other]},
                )
            with pytest.raises(DBAPIError), session.begin_nested():
                session.execute(text("UPDATE game_data_v2.grid_reinference_targets SET ordinal=12"))
            with pytest.raises(DBAPIError), session.begin_nested():
                session.execute(
                    text(
                        "UPDATE game_data_v2.grid_reinference_sources "
                        "SET live_source_image_id=:other"
                    ),
                    {"other": sources[other]},
                )
            with pytest.raises(DBAPIError), session.begin_nested():
                session.execute(text("DELETE FROM game_data_v2.source_images"))
            frozen_before = session.execute(
                text(
                    "SELECT source_image_id,document,checkpoint "
                    "FROM game_data_v2.grid_reinference_sources"
                )
            ).one()
            target_before = session.execute(
                text(
                    "SELECT target_result_id,snapshot,fingerprint_sha256,outcome,result "
                    "FROM game_data_v2.grid_reinference_targets"
                )
            ).one()
            with session.begin_nested() as rollback:
                session.execute(
                    text(
                        "UPDATE game_data_v2.grid_reinference_sources SET live_source_image_id=NULL"
                    )
                )
                session.execute(text("DELETE FROM game_data_v2.source_images"))
                rollback.rollback()
            assert (
                session.scalar(
                    text("SELECT live_source_image_id FROM game_data_v2.grid_reinference_sources")
                )
                == sources[game_id]
            )
            session.execute(
                text("UPDATE game_data_v2.grid_reinference_sources SET live_source_image_id=NULL")
            )
            session.execute(text("DELETE FROM game_data_v2.source_images"))
            assert (
                session.execute(
                    text(
                        "SELECT source_image_id,document,checkpoint "
                        "FROM game_data_v2.grid_reinference_sources"
                    )
                ).one()
                == frozen_before
            )
            assert (
                session.execute(
                    text(
                        "SELECT target_result_id,snapshot,fingerprint_sha256,outcome,result "
                        "FROM game_data_v2.grid_reinference_targets"
                    )
                ).one()
                == target_before
            )
            assert (
                session.scalar(
                    text("SELECT live_source_image_id FROM game_data_v2.grid_reinference_sources")
                )
                is None
            )
    with pytest.raises(DBAPIError, match="GRID_REINFERENCE_DOWNGRADE_HAS_HISTORY"):
        command.downgrade(config, "0158_new_game_v3_bootstrap")
    # Failure rolls back migration metadata and every retained operation.
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM public.alembic_version"))
            == "0160_grid_geometry_proposals"
        )
    for game_id in games:
        _lifecycle(engine, game_id, GamePartitionLifecycleKind.DELETE)
        with engine.connect() as connection:
            for table in ADDED_GAME_TABLES:
                assert (
                    connection.scalar(
                        text("SELECT to_regclass(:name)"),
                        {"name": "game_data_v2." + partition_name(game_id, table)},
                    )
                    is None
                )
