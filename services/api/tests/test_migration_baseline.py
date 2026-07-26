from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
BASELINE_REVISION = "0001_empty_baseline"
TEST_DATABASE_URL = (
    "postgresql+psycopg://"
    "game_predictor:game_predictor_local@127.0.0.1:5432/game_predictor"
)


def create_alembic_config(*, output_buffer: StringIO | None = None) -> Config:
    config = Config(str(ALEMBIC_INI), output_buffer=output_buffer)
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return config


def test_empty_baseline_is_the_only_migration_head() -> None:
    script = ScriptDirectory.from_config(create_alembic_config())
    revision = script.get_revision(BASELINE_REVISION)

    assert script.get_heads() == [BASELINE_REVISION]
    assert revision is not None
    assert revision.down_revision is None


def test_empty_baseline_generates_only_alembic_bookkeeping_sql() -> None:
    output = StringIO()

    command.upgrade(create_alembic_config(output_buffer=output), "head", sql=True)

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
