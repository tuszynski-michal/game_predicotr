"""Isolated PostgreSQL lifecycle of migration 0140 (TASK-0830)."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.config import ApiSettings
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

PREVIOUS = "0139_source_image_geometry_completeness"
REVISION = "0140_grid_engine_profiles"

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit isolated PostgreSQL tests only",
)


@pytest.fixture
def database() -> Iterator[tuple[Engine, Config]]:
    name = "game_predictor_task0830_" + uuid4().hex[:12] + "_test"
    assert re.fullmatch(r"game_predictor_task0830_[0-9a-f]{12}_test", name)
    url = make_url(ApiSettings.from_environment().owner_database_url)
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
        yield engine, config
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
        maintenance.dispose()


def _insert_game(engine: Engine, code: str, configuration: str | None) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO public.games (id, code, name, status, shape_geometry_configuration) "
                "VALUES (:id, :code, :code, 'draft', :configuration)"
            ),
            {"id": uuid4(), "code": code, "configuration": configuration},
        )


def _configurations(engine: Engine) -> dict[str, str | None]:
    with engine.connect() as connection:
        return {
            str(row[0]): row[1]
            for row in connection.execute(
                text("SELECT code, shape_geometry_configuration FROM public.games")
            )
        }


def _revision(engine: Engine) -> str:
    with engine.connect() as connection:
        return str(connection.scalar(text("SELECT version_num FROM public.alembic_version")))


def test_0140_accepts_profiles_keeps_old_values_and_guards_the_downgrade(
    database: tuple[Engine, Config],
) -> None:
    engine, config = database
    command.upgrade(config, PREVIOUS)
    _insert_game(engine, "legacy", None)
    _insert_game(engine, "framed", "framed_full_page_v2")
    _insert_game(engine, "unclear", "requires_clarification")
    with pytest.raises(IntegrityError):
        _insert_game(engine, "too-early", "grid_profile_mumie_v1")

    command.upgrade(config, REVISION)

    assert _revision(engine) == REVISION
    _insert_game(engine, "mumie", "grid_profile_mumie_v1")
    _insert_game(engine, "777-v2", "grid_profile_777_v2")
    with pytest.raises(IntegrityError):
        _insert_game(engine, "unknown", "grid_profile_777_v3")
    assert _configurations(engine) == {
        "legacy": None,
        "framed": "framed_full_page_v2",
        "unclear": "requires_clarification",
        "mumie": "grid_profile_mumie_v1",
        "777-v2": "grid_profile_777_v2",
    }

    # A game that uses a profile blocks the downgrade; nothing changes.
    with pytest.raises(Exception, match="GRID_ENGINE_PROFILE_IN_USE"):
        command.downgrade(config, PREVIOUS)
    assert _revision(engine) == REVISION
    assert _configurations(engine)["mumie"] == "grid_profile_mumie_v1"

    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE public.games SET shape_geometry_configuration = 'framed_full_page_v2' "
                "WHERE code IN ('mumie', '777-v2')"
            )
        )
    command.downgrade(config, PREVIOUS)

    assert _revision(engine) == PREVIOUS
    with pytest.raises(IntegrityError):
        _insert_game(engine, "after-downgrade", "grid_profile_777_v2")
    assert _configurations(engine)["legacy"] is None

    command.upgrade(config, "head")
    assert _revision(engine) == REVISION
    _insert_game(engine, "again", "grid_profile_777_v2")
