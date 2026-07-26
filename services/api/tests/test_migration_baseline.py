from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
BASELINE_REVISION = "0001_empty_baseline"
CATALOG_REVISION = "0002_games_symbols"
TEST_DATABASE_URL = (
    "postgresql+psycopg://"
    "game_predictor:game_predictor_local@127.0.0.1:5432/game_predictor"
)


def create_alembic_config(*, output_buffer: StringIO | None = None) -> Config:
    config = Config(str(ALEMBIC_INI), output_buffer=output_buffer)
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return config


def test_catalog_migration_is_the_only_head_and_follows_empty_baseline() -> None:
    script = ScriptDirectory.from_config(create_alembic_config())
    baseline = script.get_revision(BASELINE_REVISION)
    catalog = script.get_revision(CATALOG_REVISION)

    assert script.get_heads() == [CATALOG_REVISION]
    assert baseline is not None
    assert baseline.down_revision is None
    assert catalog is not None
    assert catalog.down_revision == BASELINE_REVISION


def test_empty_baseline_generates_only_alembic_bookkeeping_sql() -> None:
    output = StringIO()

    command.upgrade(
        create_alembic_config(output_buffer=output),
        BASELINE_REVISION,
        sql=True,
    )

    sql = output.getvalue().lower()
    assert "create table alembic_version" in sql
    assert BASELINE_REVISION in sql
    for domain_table in (
        "games",
        "game_versions",
        "symbols",
        "layouts",
        "paylines",
        "payout_rules",
    ):
        assert f"create table {domain_table}" not in sql


def test_empty_baseline_has_an_offline_downgrade_path() -> None:
    output = StringIO()

    command.downgrade(
        create_alembic_config(output_buffer=output),
        f"{BASELINE_REVISION}:base",
        sql=True,
    )

    sql = output.getvalue().lower()
    expected_delete = (
        "delete from alembic_version where "
        f"alembic_version.version_num = '{BASELINE_REVISION}'"
    )
    assert expected_delete in sql


def test_catalog_migration_generates_games_symbols_constraints_and_downgrade() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()

    command.upgrade(create_alembic_config(output_buffer=upgrade_output), "head", sql=True)
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{CATALOG_REVISION}:{BASELINE_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "create table games" in upgrade_sql
    assert "create table symbols" in upgrade_sql
    assert "uq_games_code" in upgrade_sql
    assert "uq_symbols_game_code" in upgrade_sql
    assert "uq_symbols_game_mobile_code" in upgrade_sql
    assert "ck_symbols_mobile_code_range" in upgrade_sql

    downgrade_sql = downgrade_output.getvalue().lower()
    assert "drop table symbols" in downgrade_sql
    assert "drop table games" in downgrade_sql
