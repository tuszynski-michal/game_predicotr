from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.game_data_v2_manifest_v1 import CREATE_TABLES
from game_predictor_api.storage.game_partition_lifecycle import (
    GamePartitionLifecycleKind,
    GamePartitionLifecycleRepository,
)
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit isolated PostgreSQL tests only",
)


@pytest.fixture
def lifecycle_database() -> Iterator[Engine]:
    name = "game_predictor_task0523_" + uuid4().hex[:12]
    assert re.fullmatch(r"game_predictor_task0523_[0-9a-f]{12}", name)
    url = make_url(ApiSettings.from_environment().database_url)
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
            assert active == 0
            connection.exec_driver_sql(f'DROP DATABASE "{name}"')
        maintenance.dispose()


def _insert_game(engine: Engine, game_id: UUID, code: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """INSERT INTO public.games
                (id, code, name, status, expected_layout_count)
                VALUES (:id, :code, :name, 'draft', 500000)"""
            ),
            {"id": game_id, "code": code, "name": code},
        )


def _run_to_done(engine: Engine, game_id: UUID, kind: GamePartitionLifecycleKind) -> None:
    with Session(engine) as session, session.begin():
        receipt = GamePartitionLifecycleRepository(session).start_or_resume(
            game_id=game_id, kind=kind
        )
        operation_id = receipt.operation_id
    for _ in range(len(CREATE_TABLES) + 2):
        with Session(engine) as session, session.begin():
            receipt = GamePartitionLifecycleRepository(session).run_next(operation_id)
        if receipt.status == "done":
            return
    raise AssertionError("lifecycle did not reach done")


def test_restartable_provision_and_delete_keep_other_game_isolated(
    lifecycle_database: Engine,
) -> None:
    first, second = uuid4(), uuid4()
    _insert_game(lifecycle_database, first, "first")
    _insert_game(lifecycle_database, second, "second")
    _run_to_done(lifecycle_database, first, GamePartitionLifecycleKind.PROVISION)
    _run_to_done(lifecycle_database, second, GamePartitionLifecycleKind.PROVISION)

    with Session(lifecycle_database) as session, session.begin():
        resumed = GamePartitionLifecycleRepository(session).start_or_resume(
            game_id=first, kind=GamePartitionLifecycleKind.PROVISION
        )
        assert resumed.status == "done"

    _run_to_done(lifecycle_database, first, GamePartitionLifecycleKind.DELETE)

    with lifecycle_database.connect() as connection:
        games = set(connection.execute(text("SELECT id FROM public.games")).scalars())
        locations = set(
            connection.execute(text("SELECT game_id FROM public.game_storage_locations")).scalars()
        )
        second_partition_count = connection.execute(
            text(
                """SELECT count(DISTINCT child.oid) FROM pg_inherits i
                JOIN pg_class child ON child.oid=i.inhrelid
                JOIN pg_namespace n ON n.oid=child.relnamespace
                WHERE n.nspname='game_data_v2' AND child.relkind = 'r'
                  AND child.relname LIKE :prefix"""
            ),
            {"prefix": f"gpv2_{second.hex[:12]}_%"},
        ).scalar_one()
    assert games == {second}
    assert locations == {second}
    assert second_partition_count == len(CREATE_TABLES)
