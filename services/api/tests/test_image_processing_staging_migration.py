from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
REVISION = "0017_image_processing"
PREVIOUS_REVISION = "0016_image_orchestration"
TEST_DATABASE_URL = (
    "postgresql+psycopg://game_predictor:game_predictor_local@127.0.0.1:5432/game_predictor"
)


def _config(output: StringIO) -> Config:
    config = Config(str(ALEMBIC_INI), output_buffer=output)
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return config


def test_image_processing_staging_migration_is_reversible() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()

    command.upgrade(_config(upgrade_output), "head", sql=True)
    command.downgrade(
        _config(downgrade_output),
        f"{REVISION}:{PREVIOUS_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    for table in (
        "image_pipeline_stage_results",
        "source_images",
        "recognized_boards",
        "cell_observations",
        "image_review_items",
        "image_layout_staging_rows",
    ):
        assert f"create table {table}" in upgrade_sql
        assert f"drop table {table}" in downgrade_output.getvalue().lower()
    assert "uq_source_images_job_execution" in upgrade_sql
    assert "uq_recognized_boards_source_position" in upgrade_sql
    assert "uq_cell_observations_board_cell" in upgrade_sql
    assert "uq_image_review_items_board" in upgrade_sql
    assert "uq_image_layout_staging_review" in upgrade_sql
    assert "cardinality(cells) = 15" in upgrade_sql
