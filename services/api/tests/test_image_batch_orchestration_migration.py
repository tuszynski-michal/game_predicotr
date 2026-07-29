from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
REVISION = "0016_image_orchestration"
PREVIOUS_REVISION = "0015_review_feedback"
TEST_DATABASE_URL = (
    "postgresql+psycopg://game_predictor:game_predictor_local@127.0.0.1:5432/game_predictor"
)


def _config(output: StringIO) -> Config:
    config = Config(str(ALEMBIC_INI), output_buffer=output)
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return config


def test_image_orchestration_migration_has_reversible_constraints() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()

    command.upgrade(_config(upgrade_output), "head", sql=True)
    command.downgrade(
        _config(downgrade_output),
        f"{REVISION}:{PREVIOUS_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "create table image_file_executions" in upgrade_sql
    assert "create table image_import_job_files" in upgrade_sql
    assert "pk_image_file_executions" in upgrade_sql
    assert "uq_image_file_executions_source_pipeline" in upgrade_sql
    assert "pk_image_import_job_files" in upgrade_sql
    assert "uq_image_import_job_files_job_order" in upgrade_sql
    assert "fk_image_import_job_files_execution" in upgrade_sql
    assert "fk_image_import_job_files_job_id_jobs" in upgrade_sql
    assert "ck_image_import_job_files_relative_path" in upgrade_sql

    downgrade_sql = downgrade_output.getvalue().lower()
    assert "drop table image_import_job_files" in downgrade_sql
    assert "drop table image_file_executions" in downgrade_sql
