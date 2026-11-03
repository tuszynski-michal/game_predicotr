"""An empty history must never execute the large-corpus exclusion joins."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from game_predictor_api.domain.symbol_readability import GAME_ID
from sqlalchemy import text
from test_source_replacement_postgres import database as database  # noqa: F401
from test_source_replacement_postgres import pytestmark as pytestmark

ROOT = Path(__file__).resolve().parents[4]


def test_empty_history_skips_impl_for_owner_and_runtime(database):  # noqa: F811
    with database.connect() as connection:
        transaction = connection.begin()
        connection.execute(text("SET LOCAL statement_timeout='2s'"))
        connection.execute(
            text("SELECT set_config('game_predictor.game_id',:game,true)"),
            {"game": str(GAME_ID)},
        )
        connection.execute(
            text("""
CREATE OR REPLACE FUNCTION public.source_replacement_excluded_reviews_impl_v1(g uuid)
RETURNS SETOF uuid LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
BEGIN RAISE EXCEPTION 'EMPTY_HISTORY_EXECUTED_EXCLUSION_JOINS'; END;
$$;
""")
        )
        query = text("SELECT count(*) FROM public.source_replacement_excluded_reviews_v1(:game)")
        assert connection.scalar(query, {"game": GAME_ID}) == 0
        runtime = database._task1127_runtime
        connection.exec_driver_sql(f'SET LOCAL ROLE "{runtime}"')
        assert connection.scalar(query, {"game": GAME_ID}) == 0
        transaction.rollback()


def test_migration_roundtrip_preserves_original_impl(database):  # noqa: F811
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url", database.url.render_as_string(hide_password=False).replace("%", "%%")
    )
    with database.connect() as connection:
        original = connection.scalar(
            text(
                "SELECT pg_get_functiondef("
                "'public.source_replacement_excluded_reviews_impl_v1(uuid)'::regprocedure)"
            )
        )
    command.downgrade(config, "0178_grid_correction_growth")
    with database.connect() as connection:
        restored = connection.scalar(
            text(
                "SELECT pg_get_functiondef("
                "'public.source_replacement_excluded_reviews_v1(uuid)'::regprocedure)"
            )
        )
        assert restored.replace("excluded_reviews_v1", "excluded_reviews_impl_v1") == original
    command.upgrade(config, "head")
    with database.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT pg_get_functiondef("
                    "'public.source_replacement_excluded_reviews_impl_v1(uuid)'::regprocedure)"
                )
            )
            == original
        )
