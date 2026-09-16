from __future__ import annotations

from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def create_alembic_config(*, output_buffer: StringIO) -> Config:
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"), output_buffer=output_buffer)
    config.set_main_option(
        "sqlalchemy.url",
        "postgresql+psycopg://game_predictor:game_predictor_local@127.0.0.1:5432/game_predictor",
    )
    return config


def test_partial_grid_training_migration_versions_checks_and_guards_downgrade() -> None:
    output = StringIO()
    command.upgrade(
        create_alembic_config(output_buffer=output),
        "0110_game_partition_lifecycle:0111_partial_grid_training_qualification",
        sql=True,
    )
    sql = output.getvalue().lower()
    assert "manual-geometry-qualification-v2" in sql
    assert "includeinpartialgridtraining" in sql
    assert "delete from" not in sql

    downgrade = StringIO()
    command.downgrade(
        create_alembic_config(output_buffer=downgrade),
        "0111_partial_grid_training_qualification:0110_game_partition_lifecycle",
        sql=True,
    )
    sql = downgrade.getvalue().lower()
    assert "partial_grid_training_qualification_downgrade_has_data" in sql
    assert sql.index("raise exception") < sql.rindex("manual-geometry-qualification-v1")
