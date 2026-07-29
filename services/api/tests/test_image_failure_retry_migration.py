from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
REVISION = "0018_image_failure_retry"
PREVIOUS_REVISION = "0017_image_processing"
TEST_DATABASE_URL = (
    "postgresql+psycopg://game_predictor:game_predictor_local@127.0.0.1:5432/game_predictor"
)


def _config(output: StringIO) -> Config:
    config = Config(str(ALEMBIC_INI), output_buffer=output)
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return config


def test_image_failure_retry_migration_is_reversible() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()

    command.upgrade(_config(upgrade_output), "head", sql=True)
    command.downgrade(
        _config(downgrade_output),
        f"{REVISION}:{PREVIOUS_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "failed_stage" in upgrade_sql
    assert "retry_count" in upgrade_sql
    assert "workflow_checkpoint_payload" in upgrade_sql
    assert "ix_image_import_job_files_job_workflow" in upgrade_sql
    assert "create table image_review_resolution_events" in upgrade_sql
    assert "uq_image_review_resolution_events_item_idempotency" in upgrade_sql

    downgrade_sql = downgrade_output.getvalue().lower()
    assert "drop table image_review_resolution_events" in downgrade_sql
    assert "drop column workflow_checkpoint_payload" in downgrade_sql
    assert "drop column failed_stage" in downgrade_sql
