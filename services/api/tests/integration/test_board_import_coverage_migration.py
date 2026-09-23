"""Isolated PostgreSQL coverage of migration 0122 (D-437 coverage indexes).

Guards the two failure modes found on the dev database: the canonical
``pg_get_indexdef`` predicate must be recognised as our own index on retry,
and the partitioned ``game_data_v2`` parents must not use CONCURRENTLY.
"""

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

PREVIOUS = "0121_partial_visibility_quality_issue"
PENDING_PARTIAL = "((completeness_status)::text = 'pending_partial'::text)"
EXPECTED = {
    ("public", "ix_image_review_items_game_sequence_status"): (
        "CREATE INDEX ix_image_review_items_game_sequence_status ON public.image_review_items "
        "USING btree (game_id, sequence_number, status)"
    ),
    ("public", "ix_recognized_boards_pending_partial"): (
        "CREATE INDEX ix_recognized_boards_pending_partial ON public.recognized_boards "
        f"USING btree (id) WHERE {PENDING_PARTIAL}"
    ),
    ("game_data_v2", "v2_ix_image_review_items_game_sequence_status"): (
        "CREATE INDEX v2_ix_image_review_items_game_sequence_status ON ONLY "
        "game_data_v2.image_review_items USING btree (game_id, sequence_number, status)"
    ),
    ("game_data_v2", "v2_ix_recognized_boards_pending_partial"): (
        "CREATE INDEX v2_ix_recognized_boards_pending_partial ON ONLY "
        f"game_data_v2.recognized_boards USING btree (game_id, id) WHERE {PENDING_PARTIAL}"
    ),
}


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


@pytest.fixture(scope="module")
def migrated() -> Iterator[tuple[Engine, Config]]:
    name = "game_predictor_task0629_mig_" + uuid4().hex[:12]
    url = make_url(ApiSettings.from_environment().database_url)
    maintenance = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5},
    )
    engine = create_engine(
        url.set(database=name),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5},
    )
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
        yield engine, config
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
            connection.execute(text(f"DROP DATABASE {_quote(name)}"))
        maintenance.dispose()


def _indexes(engine: Engine) -> dict[tuple[str, str], tuple[str, bool]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT n.nspname, c.relname, pg_get_indexdef(c.oid), i.indisvalid "
                "FROM pg_class c JOIN pg_index i ON i.indexrelid=c.oid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE (n.nspname, c.relname) IN "
                "(('public','ix_image_review_items_game_sequence_status'),"
                "('public','ix_recognized_boards_pending_partial'),"
                "('game_data_v2','v2_ix_image_review_items_game_sequence_status'),"
                "('game_data_v2','v2_ix_recognized_boards_pending_partial'))"
            )
        ).all()
    return {(row[0], row[1]): (row[2], row[3]) for row in rows}


def _assert_all_present(engine: Engine) -> None:
    assert _indexes(engine) == {key: (definition, True) for key, definition in EXPECTED.items()}


def test_upgrade_builds_exact_canonical_indexes(migrated: tuple[Engine, Config]) -> None:
    engine, _config = migrated
    _assert_all_present(engine)


def test_downgrade_removes_indexes_and_upgrade_restores_them(
    migrated: tuple[Engine, Config],
) -> None:
    engine, config = migrated
    command.downgrade(config, PREVIOUS)
    assert _indexes(engine) == {}
    command.upgrade(config, "head")
    _assert_all_present(engine)


def test_retry_after_partial_run_reuses_committed_public_indexes(
    migrated: tuple[Engine, Config],
) -> None:
    engine, config = migrated
    command.downgrade(config, PREVIOUS)
    # A failed first run leaves the concurrently built public indexes committed.
    with engine.connect() as connection:
        connection.execute(
            text(
                "CREATE INDEX ix_image_review_items_game_sequence_status "
                "ON public.image_review_items (game_id, sequence_number, status)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX ix_recognized_boards_pending_partial "
                "ON public.recognized_boards (id) WHERE completeness_status = 'pending_partial'"
            )
        )
    command.upgrade(config, "head")
    _assert_all_present(engine)


def test_foreign_index_with_same_name_is_a_conflict(migrated: tuple[Engine, Config]) -> None:
    engine, config = migrated
    command.downgrade(config, PREVIOUS)
    with engine.connect() as connection:
        connection.execute(
            text(
                "CREATE INDEX ix_recognized_boards_pending_partial ON public.recognized_boards (id)"
            )
        )
    try:
        with pytest.raises(
            RuntimeError,
            match="BOARD_IMPORT_COVERAGE_INDEX_NAME_CONFLICT: ix_recognized_boards_pending_partial",
        ):
            command.upgrade(config, "head")
    finally:
        with engine.connect() as connection:
            connection.execute(
                text("DROP INDEX IF EXISTS public.ix_recognized_boards_pending_partial")
            )
        command.upgrade(config, "head")
    _assert_all_present(engine)
