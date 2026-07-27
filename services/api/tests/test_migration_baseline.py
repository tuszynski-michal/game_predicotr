from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
BASELINE_REVISION = "0001_empty_baseline"
CATALOG_REVISION = "0002_games_symbols"
RULES_REVISION = "0003_rules_versions"
PAYLINES_REVISION = "0004_paylines"
PAYOUTS_REVISION = "0005_symbol_payouts"
DATASETS_REVISION = "0006_dataset_staging"
JOBS_REVISION = "0007_jobs"
JOB_LEASES_REVISION = "0008_job_leases"
TEST_DATABASE_URL = (
    "postgresql+psycopg://game_predictor:game_predictor_local@127.0.0.1:5432/game_predictor"
)


def create_alembic_config(*, output_buffer: StringIO | None = None) -> Config:
    config = Config(str(ALEMBIC_INI), output_buffer=output_buffer)
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return config


def test_job_leases_migration_is_the_only_head_and_follows_jobs() -> None:
    script = ScriptDirectory.from_config(create_alembic_config())
    baseline = script.get_revision(BASELINE_REVISION)
    catalog = script.get_revision(CATALOG_REVISION)
    rules = script.get_revision(RULES_REVISION)
    paylines = script.get_revision(PAYLINES_REVISION)
    payouts = script.get_revision(PAYOUTS_REVISION)
    datasets = script.get_revision(DATASETS_REVISION)
    jobs = script.get_revision(JOBS_REVISION)
    job_leases = script.get_revision(JOB_LEASES_REVISION)

    assert script.get_heads() == [JOB_LEASES_REVISION]
    assert baseline is not None
    assert baseline.down_revision is None
    assert catalog is not None
    assert catalog.down_revision == BASELINE_REVISION
    assert rules is not None
    assert rules.down_revision == CATALOG_REVISION
    assert paylines is not None
    assert paylines.down_revision == RULES_REVISION
    assert payouts is not None
    assert payouts.down_revision == PAYLINES_REVISION
    assert datasets is not None
    assert datasets.down_revision == PAYOUTS_REVISION
    assert jobs is not None
    assert jobs.down_revision == DATASETS_REVISION
    assert job_leases is not None
    assert job_leases.down_revision == JOBS_REVISION


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
        f"delete from alembic_version where alembic_version.version_num = '{BASELINE_REVISION}'"
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


def test_rules_migration_generates_constraints_and_downgrade() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()

    command.upgrade(create_alembic_config(output_buffer=upgrade_output), "head", sql=True)
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{RULES_REVISION}:{CATALOG_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "create table rules_versions" in upgrade_sql
    assert "uq_rules_versions_game_version" in upgrade_sql
    assert "ck_rules_versions_rows_range" in upgrade_sql
    assert "ck_rules_versions_columns_range" in upgrade_sql
    assert "ck_rules_versions_spin_cost_nonnegative" in upgrade_sql
    assert "fk_rules_versions_game_id_games" in upgrade_sql

    downgrade_sql = downgrade_output.getvalue().lower()
    assert "drop table rules_versions" in downgrade_sql
    assert "drop type rules_version_status" in downgrade_sql


def test_paylines_migration_generates_array_constraints_and_downgrade() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()

    command.upgrade(create_alembic_config(output_buffer=upgrade_output), "head", sql=True)
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{PAYLINES_REVISION}:{RULES_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "create table paylines" in upgrade_sql
    assert "smallint[]" in upgrade_sql
    assert "uq_paylines_rules_version_code" in upgrade_sql
    assert "uq_paylines_rules_version_row_path" in upgrade_sql
    assert "ck_paylines_row_path_nonnegative" in upgrade_sql
    assert "fk_paylines_rules_version_id_rules_versions" in upgrade_sql

    downgrade_sql = downgrade_output.getvalue().lower()
    assert "drop table paylines" in downgrade_sql


def test_symbol_payout_migration_generates_constraints_and_downgrade() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()

    command.upgrade(create_alembic_config(output_buffer=upgrade_output), "head", sql=True)
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{PAYOUTS_REVISION}:{PAYLINES_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "create table rules_version_symbols" in upgrade_sql
    assert "create table payout_rules" in upgrade_sql
    assert "ck_rules_version_symbols_minimum_range" in upgrade_sql
    assert "ck_payout_rules_match_length_range" in upgrade_sql
    assert "ck_payout_rules_credits_nonnegative" in upgrade_sql
    assert "uq_payout_rules_version_symbol_length" in upgrade_sql
    assert "fk_payout_rules_rules_version_symbol" in upgrade_sql

    downgrade_sql = downgrade_output.getvalue().lower()
    assert "drop table payout_rules" in downgrade_sql
    assert "drop table rules_version_symbols" in downgrade_sql


def test_dataset_staging_migration_generates_constraints_and_downgrade() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()

    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        "head",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{DATASETS_REVISION}:{PAYOUTS_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "create table dataset_versions" in upgrade_sql
    assert "create table layouts" in upgrade_sql
    assert "smallint[]" in upgrade_sql
    assert "uq_dataset_versions_game_version" in upgrade_sql
    assert "uq_layouts_dataset_sequence" in upgrade_sql
    assert "ix_layouts_dataset_signature" in upgrade_sql
    assert "ck_layouts_cells_mobile_code_range" in upgrade_sql

    downgrade_sql = downgrade_output.getvalue().lower()
    assert "drop table layouts" in downgrade_sql
    assert "drop table dataset_versions" in downgrade_sql
    assert "drop type dataset_version_status" in downgrade_sql


def test_jobs_migration_generates_enums_constraints_indexes_and_downgrade() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()

    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        "head",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{JOBS_REVISION}:{DATASETS_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "create table jobs" in upgrade_sql
    assert "create type job_type" in upgrade_sql
    assert "create type job_status" in upgrade_sql
    assert "uq_jobs_input_key" in upgrade_sql
    assert "ck_jobs_progress_within_total" in upgrade_sql
    assert "ix_jobs_status_created_at" in upgrade_sql
    assert "fk_dataset_versions_source_job_id_jobs" in upgrade_sql

    downgrade_sql = downgrade_output.getvalue().lower()
    assert "drop table jobs" in downgrade_sql
    assert "drop type job_status" in downgrade_sql
    assert "drop type job_type" in downgrade_sql


def test_job_leases_migration_generates_fencing_and_checkpoint_schema() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()

    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        "head",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{JOB_LEASES_REVISION}:{JOBS_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "checkpoint_payload jsonb" in upgrade_sql
    assert "lease_token uuid" in upgrade_sql
    assert "uq_jobs_execution_slot" in upgrade_sql
    assert "ck_jobs_processing_lease_fields" in upgrade_sql
    assert "ix_jobs_status_lease_expires" in upgrade_sql

    downgrade_sql = downgrade_output.getvalue().lower()
    assert "drop column checkpoint_payload" in downgrade_sql
    assert "drop column lease_token" in downgrade_sql
    assert "drop constraint uq_jobs_execution_slot" in downgrade_sql
