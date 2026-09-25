"""Regression coverage for V2 qualification checks introduced in migration 0123."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.config import ApiSettings
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests.",
)

_CONSTRAINTS = {
    "recognized_boards": "ck_recognized_boards_qualification",
    "image_import_geometry_guard_decisions": "ck_guard_decisions_qualification",
}
_VERSIONS = (
    "manual-geometry-qualification-v1",
    "manual-geometry-qualification-v2",
    "manual-geometry-qualification-v3",
)
_PARTIAL_VISIBILITY_CONSTRAINTS = {
    ("image_symbol_review_cells", "ck_image_symbol_review_cells_source"): "geometry_partial",
    (
        "image_symbol_review_cells",
        "ck_image_symbol_review_cells_quality_issue",
    ): "partial_visibility",
    (
        "image_symbol_review_events",
        "ck_image_symbol_review_events_quality_issue",
    ): "partial_visibility",
}


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


@pytest.fixture(scope="module")
def database() -> Iterator[Engine]:
    name = "game_predictor_task0664_" + uuid4().hex[:12]
    url = make_url(ApiSettings.from_environment().database_url)
    maintenance = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5},
    )
    engine = create_engine(url.set(database=name), connect_args={"connect_timeout": 5})
    with maintenance.connect() as connection:
        connection.execute(text("SET statement_timeout='10s'"))
        connection.execute(text(f"CREATE DATABASE {_quote(name)}"))
    try:
        config = Config(str(Path(__file__).resolve().parents[4] / "alembic.ini"))
        config.set_main_option(
            "sqlalchemy.url",
            url.set(database=name).render_as_string(hide_password=False).replace("%", "%%"),
        )
        command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
            connection.execute(text(f"DROP DATABASE {_quote(name)}"))
        maintenance.dispose()


def _checks(engine: Engine) -> dict[str, str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT c.relname, pg_get_constraintdef(con.oid) "
                "FROM pg_constraint con "
                "JOIN pg_class c ON c.oid = con.conrelid "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'game_data_v2' "
                "AND c.relname IN ('recognized_boards', 'image_import_geometry_guard_decisions') "
                "AND con.conname IN ('ck_recognized_boards_qualification', "
                "'ck_guard_decisions_qualification')"
            )
        ).all()
    return {table: definition for table, definition in rows}


def test_v2_parents_accept_all_current_qualification_contract_versions(database: Engine) -> None:
    checks = _checks(database)

    assert set(checks) == set(_CONSTRAINTS)
    for definition in checks.values():
        for version in _VERSIONS:
            assert version in definition


def test_new_v2_partitions_inherit_the_current_qualification_contract(database: Engine) -> None:
    game_id = uuid4()
    children = {
        table: f"task0664_{table}_{game_id.hex[:12]}" for table in _CONSTRAINTS
    }
    with database.begin() as connection:
        for table, child in children.items():
            connection.execute(
                text(
                    f"CREATE TABLE game_data_v2.{child} PARTITION OF "
                    f"game_data_v2.{table} FOR VALUES IN ('{game_id}')"
                )
            )
        child_names = ", ".join(f"'{child}'" for child in children.values())
        rows = connection.execute(
            text(
                "SELECT c.relname, pg_get_constraintdef(con.oid) "
                "FROM pg_constraint con "
                "JOIN pg_class c ON c.oid = con.conrelid "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'game_data_v2' "
                f"AND c.relname IN ({child_names}) "
                "AND con.conname IN ('ck_recognized_boards_qualification', "
                "'ck_guard_decisions_qualification')"
            )
        ).all()

    checks = {table: definition for table, definition in rows}
    assert set(checks) == set(children.values())
    for definition in checks.values():
        for version in _VERSIONS:
            assert version in definition


def test_v2_partial_visibility_parents_accept_the_public_contract(database: Engine) -> None:
    with database.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT c.relname, con.conname, pg_get_constraintdef(con.oid) "
                "FROM pg_constraint con "
                "JOIN pg_class c ON c.oid = con.conrelid "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'game_data_v2' "
                "AND ((c.relname = 'image_symbol_review_cells' AND con.conname IN "
                "('ck_image_symbol_review_cells_source', "
                "'ck_image_symbol_review_cells_quality_issue')) "
                "OR (c.relname = 'image_symbol_review_events' "
                "AND con.conname = 'ck_image_symbol_review_events_quality_issue'))"
            )
        ).all()

    checks = {(table, name): definition for table, name, definition in rows}
    assert set(checks) == set(_PARTIAL_VISIBILITY_CONSTRAINTS)
    for key, expected_value in _PARTIAL_VISIBILITY_CONSTRAINTS.items():
        assert expected_value in checks[key]


def test_new_v2_partitions_inherit_partial_visibility_contract(database: Engine) -> None:
    game_id = uuid4()
    children = {
        table: f"task0664_partial_{table}_{game_id.hex[:12]}"
        for table, _name in _PARTIAL_VISIBILITY_CONSTRAINTS
    }
    with database.begin() as connection:
        for table, child in children.items():
            connection.execute(
                text(
                    f"CREATE TABLE game_data_v2.{child} PARTITION OF "
                    f"game_data_v2.{table} FOR VALUES IN ('{game_id}')"
                )
            )
        child_names = ", ".join(f"'{child}'" for child in children.values())
        rows = connection.execute(
            text(
                "SELECT c.relname, con.conname, pg_get_constraintdef(con.oid) "
                "FROM pg_constraint con "
                "JOIN pg_class c ON c.oid = con.conrelid "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'game_data_v2' "
                f"AND c.relname IN ({child_names}) "
                "AND con.conname IN ('ck_image_symbol_review_cells_source', "
                "'ck_image_symbol_review_cells_quality_issue', "
                "'ck_image_symbol_review_events_quality_issue')"
            )
        ).all()

    child_checks = {(table, name): definition for table, name, definition in rows}
    expected = {
        (children[table], name): value
        for (table, name), value in _PARTIAL_VISIBILITY_CONSTRAINTS.items()
    }
    assert set(child_checks) == set(expected)
    for key, expected_value in expected.items():
        assert expected_value in child_checks[key]
