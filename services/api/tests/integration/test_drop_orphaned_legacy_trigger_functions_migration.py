"""Isolated PostgreSQL proof for migration 0129 (D-467, S1)."""

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

PREVIOUS = "0128_partial_board_reconciliation_receipts"
REVISION = "0129_drop_orphaned_legacy_trigger_functions"
FUNCTIONS = (
    "guard_image_review_queue_topology",
    "populate_image_review_item_sequence_scope",
    "project_image_review_queue_delete",
    "project_image_review_queue_insert",
    "project_image_review_queue_status",
    "synchronize_image_review_item_sequence_number",
    "synchronize_image_review_job_status",
)

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit isolated PostgreSQL tests only",
)


@pytest.fixture
def database() -> Iterator[tuple[Engine, Config]]:
    name = "game_predictor_task0752_" + uuid4().hex[:12]
    assert re.fullmatch(r"game_predictor_task0752_[0-9a-f]{12}", name)
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
            connection.exec_driver_sql(f'DROP DATABASE "{name}"')
        maintenance.dispose()


def _public_functions(engine: Engine) -> set[str]:
    with engine.connect() as connection:
        return set(
            connection.scalars(
                text(
                    "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                    "WHERE n.nspname = 'public' AND p.proname = ANY(:names)"
                ),
                {"names": list(FUNCTIONS)},
            )
        )


def _create_orphans(engine: Engine) -> None:
    # Historical migrations still create these functions on a fresh head (0125 dropped the
    # legacy tables and their triggers, not the functions); add whichever are missing.
    present = _public_functions(engine)
    with engine.begin() as connection:
        for name in set(FUNCTIONS) - present:
            connection.execute(
                text(
                    f'CREATE FUNCTION public."{name}"() RETURNS trigger LANGUAGE plpgsql '
                    "AS $$ BEGIN RETURN NEW; END $$"
                )
            )


def test_orphaned_functions_are_dropped_and_others_kept(database: tuple[Engine, Config]) -> None:
    engine, config = database
    command.upgrade(config, PREVIOUS)
    _create_orphans(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE FUNCTION public.keep_me() RETURNS trigger LANGUAGE plpgsql "
                "AS $$ BEGIN RETURN NEW; END $$"
            )
        )
    assert _public_functions(engine) == set(FUNCTIONS)

    command.upgrade(config, REVISION)

    assert _public_functions(engine) == set()
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT count(*) FROM pg_proc WHERE proname = 'keep_me'")) == 1
        )
        assert connection.scalar(text("SELECT version_num FROM public.alembic_version")) == (
            REVISION
        )


def test_fresh_head_orphans_are_dropped_without_triggers(
    database: tuple[Engine, Config],
) -> None:
    engine, config = database
    command.upgrade(config, PREVIOUS)
    with engine.connect() as connection:
        triggers = connection.scalar(
            text(
                "SELECT count(*) FROM pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid "
                "WHERE p.proname = ANY(:names)"
            ),
            {"names": list(FUNCTIONS)},
        )
    assert triggers == 0

    command.upgrade(config, REVISION)

    assert _public_functions(engine) == set()


def test_referenced_function_blocks_the_migration(database: tuple[Engine, Config]) -> None:
    engine, config = database
    command.upgrade(config, PREVIOUS)
    _create_orphans(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE public.t0752_probe (id integer)"))
        connection.execute(
            text(
                "CREATE TRIGGER t0752_probe_trigger BEFORE INSERT ON public.t0752_probe "
                'FOR EACH ROW EXECUTE FUNCTION public."synchronize_image_review_job_status"()'
            )
        )

    with pytest.raises(RuntimeError, match="LEGACY_TRIGGER_FUNCTION_STILL_REFERENCED"):
        command.upgrade(config, REVISION)

    assert _public_functions(engine) == set(FUNCTIONS)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM public.alembic_version")) == (
            PREVIOUS
        )


def test_downgrade_is_refused(database: tuple[Engine, Config]) -> None:
    _engine, config = database
    command.upgrade(config, REVISION)

    with pytest.raises(RuntimeError, match="LEGACY_TRIGGER_FUNCTION_DOWNGRADE_UNSUPPORTED"):
        command.downgrade(config, PREVIOUS)


def test_partially_dropped_set_and_v2_functions_survive(database: tuple[Engine, Config]) -> None:
    engine, config = database
    command.upgrade(config, PREVIOUS)
    _create_orphans(engine)
    with engine.begin() as connection:
        for name in FUNCTIONS[:3]:
            connection.execute(text(f'DROP FUNCTION public."{name}"()'))
        v2_before = connection.scalar(
            text(
                "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = 'game_data_v2' AND p.prorettype = 'pg_catalog.trigger'::regtype"
            )
        )
        triggers_before = connection.scalar(
            text(
                "SELECT count(*) FROM pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid "
                "JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'game_data_v2'"
            )
        )
    assert v2_before and triggers_before

    command.upgrade(config, REVISION)

    assert _public_functions(engine) == set()
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                    "WHERE n.nspname = 'game_data_v2' "
                    "AND p.prorettype = 'pg_catalog.trigger'::regtype"
                )
            )
            == v2_before
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid "
                    "JOIN pg_namespace n ON n.oid = p.pronamespace "
                    "WHERE n.nspname = 'game_data_v2'"
                )
            )
            == triggers_before
        )
