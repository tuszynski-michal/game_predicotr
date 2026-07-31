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
LAYOUT_PAYOUTS_REVISION = "0009_layout_payouts"
MOBILE_RELEASES_REVISION = "0010_mobile_releases"
LAYOUT_IMPORT_STAGING_REVISION = "0011_layout_import_staging"
LAYOUT_IMPORT_NORMALIZATION_REVISION = "0012_layout_import_normalization"
LAYOUT_IMPORT_PUBLICATION_REVISION = "0013_layout_import_publication"
REVIEW_BATCHES_REVISION = "0014_review_batches"
REVIEW_FEEDBACK_REVISION = "0015_review_feedback"
IMAGE_ORCHESTRATION_REVISION = "0016_image_orchestration"
IMAGE_PROCESSING_REVISION = "0017_image_processing"
IMAGE_FAILURE_RETRY_REVISION = "0018_image_failure_retry"
IMAGE_REVIEW_GEOMETRY_REVISION = "0019_review_geometry"
IMAGE_VERIFIED_COHORTS_REVISION = "0020_verified_cohorts"
REVIEWER_ACCESS_REVISION = "0021_reviewer_access"
DATASET_QUALITY_REVISION = "0022_dataset_quality"
SYMBOL_BOOTSTRAP_REVISION = "0023_symbol_bootstrap"
TEST_DATABASE_URL = (
    "postgresql+psycopg://game_predictor:game_predictor_local@127.0.0.1:5432/game_predictor"
)


def create_alembic_config(*, output_buffer: StringIO | None = None) -> Config:
    config = Config(str(ALEMBIC_INI), output_buffer=output_buffer)
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return config


def test_symbol_bootstrap_migration_is_the_only_head() -> None:
    script = ScriptDirectory.from_config(create_alembic_config())
    baseline = script.get_revision(BASELINE_REVISION)
    catalog = script.get_revision(CATALOG_REVISION)
    rules = script.get_revision(RULES_REVISION)
    paylines = script.get_revision(PAYLINES_REVISION)
    payouts = script.get_revision(PAYOUTS_REVISION)
    datasets = script.get_revision(DATASETS_REVISION)
    jobs = script.get_revision(JOBS_REVISION)
    job_leases = script.get_revision(JOB_LEASES_REVISION)
    layout_payouts = script.get_revision(LAYOUT_PAYOUTS_REVISION)
    mobile_releases = script.get_revision(MOBILE_RELEASES_REVISION)
    layout_import_staging = script.get_revision(LAYOUT_IMPORT_STAGING_REVISION)
    layout_import_normalization = script.get_revision(LAYOUT_IMPORT_NORMALIZATION_REVISION)
    layout_import_publication = script.get_revision(LAYOUT_IMPORT_PUBLICATION_REVISION)
    review_batches = script.get_revision(REVIEW_BATCHES_REVISION)
    review_feedback = script.get_revision(REVIEW_FEEDBACK_REVISION)
    image_orchestration = script.get_revision(IMAGE_ORCHESTRATION_REVISION)
    image_processing = script.get_revision(IMAGE_PROCESSING_REVISION)
    image_failure_retry = script.get_revision(IMAGE_FAILURE_RETRY_REVISION)
    image_review_geometry = script.get_revision(IMAGE_REVIEW_GEOMETRY_REVISION)
    image_verified_cohorts = script.get_revision(IMAGE_VERIFIED_COHORTS_REVISION)
    reviewer_access = script.get_revision(REVIEWER_ACCESS_REVISION)
    dataset_quality = script.get_revision(DATASET_QUALITY_REVISION)
    symbol_bootstrap = script.get_revision(SYMBOL_BOOTSTRAP_REVISION)

    assert script.get_heads() == [SYMBOL_BOOTSTRAP_REVISION]
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
    assert layout_payouts is not None
    assert layout_payouts.down_revision == JOB_LEASES_REVISION
    assert mobile_releases is not None
    assert mobile_releases.down_revision == LAYOUT_PAYOUTS_REVISION
    assert layout_import_staging is not None
    assert layout_import_staging.down_revision == MOBILE_RELEASES_REVISION
    assert layout_import_normalization is not None
    assert layout_import_normalization.down_revision == LAYOUT_IMPORT_STAGING_REVISION
    assert layout_import_publication is not None
    assert layout_import_publication.down_revision == LAYOUT_IMPORT_NORMALIZATION_REVISION
    assert review_batches is not None
    assert review_batches.down_revision == LAYOUT_IMPORT_PUBLICATION_REVISION
    assert review_feedback is not None
    assert review_feedback.down_revision == REVIEW_BATCHES_REVISION
    assert image_orchestration is not None
    assert image_orchestration.down_revision == REVIEW_FEEDBACK_REVISION
    assert image_processing is not None
    assert image_processing.down_revision == IMAGE_ORCHESTRATION_REVISION
    assert image_failure_retry is not None
    assert image_failure_retry.down_revision == IMAGE_PROCESSING_REVISION
    assert image_review_geometry is not None
    assert image_review_geometry.down_revision == IMAGE_FAILURE_RETRY_REVISION
    assert image_verified_cohorts is not None
    assert image_verified_cohorts.down_revision == IMAGE_REVIEW_GEOMETRY_REVISION
    assert reviewer_access is not None
    assert reviewer_access.down_revision == IMAGE_VERIFIED_COHORTS_REVISION
    assert dataset_quality is not None
    assert dataset_quality.down_revision == REVIEWER_ACCESS_REVISION
    assert symbol_bootstrap is not None
    assert symbol_bootstrap.down_revision == DATASET_QUALITY_REVISION


def test_dataset_quality_migration_adds_expected_counts_and_override_audit() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()

    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        f"{REVIEWER_ACCESS_REVISION}:{DATASET_QUALITY_REVISION}",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{DATASET_QUALITY_REVISION}:{REVIEWER_ACCESS_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "expected_layout_count" in upgrade_sql
    assert "create table image_sequence_source_override_events" in upgrade_sql
    assert "uq_image_sequence_source_override_revision" in upgrade_sql
    downgrade_sql = downgrade_output.getvalue().lower()
    assert "drop table image_sequence_source_override_events" in downgrade_sql


def test_symbol_bootstrap_migration_adds_checksum_bound_runs() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()
    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        f"{DATASET_QUALITY_REVISION}:{SYMBOL_BOOTSTRAP_REVISION}",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{SYMBOL_BOOTSTRAP_REVISION}:{DATASET_QUALITY_REVISION}",
        sql=True,
    )
    upgrade_sql = upgrade_output.getvalue().lower()
    assert "create table symbol_bootstrap_runs" in upgrade_sql
    assert "uq_symbol_bootstrap_source_expectation" in upgrade_sql
    assert "ck_symbol_bootstrap_applied_state" in upgrade_sql
    assert "drop table symbol_bootstrap_runs" in downgrade_output.getvalue().lower()


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


def test_verified_cohort_migration_adds_immutable_context_versions() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()

    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        f"{IMAGE_REVIEW_GEOMETRY_REVISION}:{IMAGE_VERIFIED_COHORTS_REVISION}",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{IMAGE_VERIFIED_COHORTS_REVISION}:{IMAGE_REVIEW_GEOMETRY_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "create table image_verified_cohort_exports" in upgrade_sql
    assert "uq_image_verified_cohort_exports_state" in upgrade_sql
    assert "sample_count = board_count * 15" in upgrade_sql
    assert "artifact_relative_path" in upgrade_sql
    assert "drop table image_verified_cohort_exports" in downgrade_output.getvalue().lower()


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


def test_layout_payouts_migration_generates_versioned_results_and_audit() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()

    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        "head",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{LAYOUT_PAYOUTS_REVISION}:{JOB_LEASES_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "create table layout_payouts" in upgrade_sql
    assert "pk_layout_payouts" in upgrade_sql
    assert "fk_layout_payouts_layout" in upgrade_sql
    assert "ck_layout_payouts_total_nonnegative" in upgrade_sql
    assert "audit_path varchar(1000)" in upgrade_sql

    downgrade_sql = downgrade_output.getvalue().lower()
    assert "drop table layout_payouts" in downgrade_sql


def test_mobile_releases_migration_generates_immutable_selections() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()

    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        "head",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{MOBILE_RELEASES_REVISION}:{LAYOUT_PAYOUTS_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "create table mobile_releases" in upgrade_sql
    assert "create table mobile_release_games" in upgrade_sql
    assert "create type mobile_release_status" in upgrade_sql
    assert "uq_mobile_releases_version" in upgrade_sql
    assert "ck_mobile_releases_version_safe" in upgrade_sql
    assert "ck_mobile_releases_snapshot_complete" in upgrade_sql
    assert "ck_mobile_releases_apk_complete" in upgrade_sql
    assert "ck_mobile_release_games_layout_count_positive" in upgrade_sql
    assert "fk_mobile_release_games_dataset" in upgrade_sql
    assert "fk_mobile_release_games_rules" in upgrade_sql

    downgrade_sql = downgrade_output.getvalue().lower()
    assert "drop table mobile_release_games" in downgrade_sql
    assert "drop table mobile_releases" in downgrade_sql
    assert "drop type mobile_release_status" in downgrade_sql


def test_layout_import_staging_migration_generates_isolated_rows() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()

    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        "head",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{LAYOUT_IMPORT_STAGING_REVISION}:{MOBILE_RELEASES_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "create table layout_import_rows" in upgrade_sql
    assert "pk_layout_import_rows" in upgrade_sql
    assert "fk_layout_import_rows_job_id_jobs" in upgrade_sql
    assert "ck_layout_import_rows_result_variant" in upgrade_sql
    assert "ix_layout_import_rows_job_offset" in upgrade_sql

    downgrade_sql = downgrade_output.getvalue().lower()
    assert "drop table layout_import_rows" in downgrade_sql


def test_layout_import_normalization_migration_generates_staging_and_indexes() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()

    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        "head",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{LAYOUT_IMPORT_NORMALIZATION_REVISION}:{LAYOUT_IMPORT_STAGING_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "create table layout_import_normalized_rows" in upgrade_sql
    assert "pk_layout_import_normalized_rows" in upgrade_sql
    assert "fk_layout_import_normalized_rows_raw_row" in upgrade_sql
    assert "ck_layout_import_normalized_rows_result_variant" in upgrade_sql
    assert "ix_layout_import_normalized_rows_sequence" in upgrade_sql
    assert "ix_layout_import_normalized_rows_signature" in upgrade_sql

    downgrade_sql = downgrade_output.getvalue().lower()
    assert "drop table layout_import_normalized_rows" in downgrade_sql


def test_layout_import_publication_migration_adds_unique_source_job() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()

    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        "head",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{LAYOUT_IMPORT_PUBLICATION_REVISION}:{LAYOUT_IMPORT_NORMALIZATION_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "uq_dataset_versions_source_job" in upgrade_sql
    assert "where source_job_id is not null" in upgrade_sql

    downgrade_sql = downgrade_output.getvalue().lower()
    assert "drop index uq_dataset_versions_source_job" in downgrade_sql


def test_review_batches_migration_adds_immutable_whole_layout_storage() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()

    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        "head",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{REVIEW_BATCHES_REVISION}:{LAYOUT_IMPORT_PUBLICATION_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "create table review_batches" in upgrade_sql
    assert "create table review_items" in upgrade_sql
    assert "create type review_item_status" in upgrade_sql
    assert "uq_review_batches_source_report_sha256" in upgrade_sql
    assert "uq_review_items_batch_board" in upgrade_sql
    assert "uq_review_items_batch_rank" in upgrade_sql
    assert "ck_review_items_resolution_state" in upgrade_sql
    assert "ix_review_items_batch_status_rank" in upgrade_sql

    downgrade_sql = downgrade_output.getvalue().lower()
    assert "drop table review_items" in downgrade_sql
    assert "drop table review_batches" in downgrade_sql
    assert "drop type review_item_status" in downgrade_sql


def test_review_feedback_migration_adds_audit_and_immutable_exports() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()

    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        "head",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{REVIEW_FEEDBACK_REVISION}:{REVIEW_BATCHES_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "create table review_resolutions" in upgrade_sql
    assert "create table review_feedback_exports" in upgrade_sql
    assert "create type review_resolution_action" in upgrade_sql
    assert "resolution_revision" in upgrade_sql
    assert "uq_review_resolutions_item_idempotency" in upgrade_sql
    assert "uq_review_feedback_exports_batch_state" in upgrade_sql

    downgrade_sql = downgrade_output.getvalue().lower()
    assert "drop table review_feedback_exports" in downgrade_sql
    assert "drop table review_resolutions" in downgrade_sql
    assert "drop type review_resolution_action" in downgrade_sql
