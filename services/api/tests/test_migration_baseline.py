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
CLEANUP_OPERATIONS_REVISION = "0024_cleanup_operations"
SYMBOL_LOCALIZED_NAMES_REVISION = "0025_symbol_localized_names"
IMAGE_SELECTION_REVISION = "0025_image_selection"
MIGRATION_MERGE_REVISION = "0026_merge_v03_v04_heads"
IMAGE_SELECTION_MANUAL_DECISIONS_REVISION = "0027_image_selection_manual_decisions"
IMAGE_SELECTION_VERSIONED_RERUNS_REVISION = "0028_image_selection_versioned_reruns"
IMAGE_SELECTION_MISSING_IMAGES_REVISION = "0029_image_selection_missing_images"
IMAGE_SELECTION_OPTIONAL_EXCEPTIONS_REVISION = "0030_image_selection_optional_exceptions"
JOB_EXECUTION_LANES_REVISION = "0031_job_execution_lanes"
WORKER_LANE_RUNTIME_REVISION = "0032_worker_lane_runtime"
IMAGE_SELECTION_SEQUENCE_ORDER_REVISION = "0033_image_selection_sequence_order"
VERIFIED_TRAINING_COHORTS_REVISION = "0034_verified_training_cohorts"
SYMBOL_MODEL_TRAINING_REVISION = "0035_symbol_model_training_jobs"
SYMBOL_MODEL_CANDIDATE_GATE_REVISION = "0036_symbol_model_candidate_gate"
SYMBOL_MODEL_REGISTRY_REVISION = "0037_symbol_model_registry"
CURATED_IMAGE_IMPORT_BATCHES_REVISION = "0038_curated_image_import_batches"
GRID_CALIBRATION_PROFILES_REVISION = "0039_grid_calibration_profiles"
IMAGE_SELECTION_DUPLICATE_RANGE_DECISIONS_REVISION = (
    "0040_image_selection_duplicate_range_decisions"
)
IMAGE_SELECTION_REVIEW_QUEUES_REVISION = "0041_image_selection_review_queues"
IMAGE_SELECTION_DERIVED_RECOVERY_REVISION = "0042_image_selection_derived_recovery"
IMAGE_SELECTION_SEQUENCE_BOUNDS_REVISION = "0043_image_selection_sequence_bounds"
REPRESENTATIVE_RANKING_REVISION = "0044_representative_ranking"
CANONICAL_IMAGE_SEQUENCES_REVISION = "0045_canonical_image_sequences"
IMAGE_SYMBOL_PREDICTION_REVISIONS_REVISION = "0046_image_symbol_prediction_revisions"
PENDING_SYMBOL_REINFERENCE_JOB_REVISION = "0047_pending_symbol_reinference_job"
IMAGE_PAGE_GEOMETRY_OVERRIDES_REVISION = "0048_image_page_geometry_overrides"
IMAGE_REVIEW_QUEUE_PROJECTION_REVISION = "0049_image_review_queue_projection"
IMAGE_REVIEW_FIRST_SAVE_WINS_REVISION = "0050_image_review_first_save_wins"
REVIEWER_WORK_ASSIGNMENTS_REVISION = "0051_reviewer_work_assignments"
REVIEWER_ASSIGNMENT_SESSIONS_REVISION = "0052_reviewer_assignment_sessions"
IMAGE_REVIEW_JOB_COMPLETION_REVISION = "0053_image_review_job_completion"
IMAGE_BOARD_GEOMETRY_PENDING_REVISION = "0054_image_board_geometry_pending"
BOARD_CELL_GEOMETRY_PIPELINE_STAGE_REVISION = "0055_board_cell_geometry_pipeline_stage"
TEST_DATABASE_URL = (
    "postgresql+psycopg://game_predictor:game_predictor_local@127.0.0.1:5432/game_predictor"
)


def create_alembic_config(*, output_buffer: StringIO | None = None) -> Config:
    config = Config(str(ALEMBIC_INI), output_buffer=output_buffer)
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return config


def test_parallel_feature_migrations_converge_on_one_head() -> None:
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
    cleanup_operations = script.get_revision(CLEANUP_OPERATIONS_REVISION)
    symbol_localized_names = script.get_revision(SYMBOL_LOCALIZED_NAMES_REVISION)
    image_selection = script.get_revision(IMAGE_SELECTION_REVISION)
    migration_merge = script.get_revision(MIGRATION_MERGE_REVISION)
    manual_decisions = script.get_revision(IMAGE_SELECTION_MANUAL_DECISIONS_REVISION)
    versioned_reruns = script.get_revision(IMAGE_SELECTION_VERSIONED_RERUNS_REVISION)
    missing_images = script.get_revision(IMAGE_SELECTION_MISSING_IMAGES_REVISION)
    optional_exceptions = script.get_revision(IMAGE_SELECTION_OPTIONAL_EXCEPTIONS_REVISION)
    job_execution_lanes = script.get_revision(JOB_EXECUTION_LANES_REVISION)
    worker_lane_runtime = script.get_revision(WORKER_LANE_RUNTIME_REVISION)
    image_selection_sequence_order = script.get_revision(IMAGE_SELECTION_SEQUENCE_ORDER_REVISION)
    verified_training_cohorts = script.get_revision(VERIFIED_TRAINING_COHORTS_REVISION)
    symbol_model_training = script.get_revision(SYMBOL_MODEL_TRAINING_REVISION)
    symbol_model_candidate_gate = script.get_revision(SYMBOL_MODEL_CANDIDATE_GATE_REVISION)
    symbol_model_registry = script.get_revision(SYMBOL_MODEL_REGISTRY_REVISION)
    curated_image_import_batches = script.get_revision(CURATED_IMAGE_IMPORT_BATCHES_REVISION)
    grid_calibration_profiles = script.get_revision(GRID_CALIBRATION_PROFILES_REVISION)
    duplicate_range_decisions = script.get_revision(
        IMAGE_SELECTION_DUPLICATE_RANGE_DECISIONS_REVISION
    )
    image_selection_review_queues = script.get_revision(IMAGE_SELECTION_REVIEW_QUEUES_REVISION)
    image_selection_derived_recovery = script.get_revision(
        IMAGE_SELECTION_DERIVED_RECOVERY_REVISION
    )
    image_selection_sequence_bounds = script.get_revision(IMAGE_SELECTION_SEQUENCE_BOUNDS_REVISION)
    representative_ranking = script.get_revision(REPRESENTATIVE_RANKING_REVISION)

    canonical_image_sequences = script.get_revision(CANONICAL_IMAGE_SEQUENCES_REVISION)
    image_symbol_prediction_revisions = script.get_revision(
        IMAGE_SYMBOL_PREDICTION_REVISIONS_REVISION
    )
    pending_symbol_reinference_job = script.get_revision(PENDING_SYMBOL_REINFERENCE_JOB_REVISION)
    image_page_geometry_overrides = script.get_revision(IMAGE_PAGE_GEOMETRY_OVERRIDES_REVISION)
    image_review_queue_projection = script.get_revision(IMAGE_REVIEW_QUEUE_PROJECTION_REVISION)
    image_review_first_save_wins = script.get_revision(IMAGE_REVIEW_FIRST_SAVE_WINS_REVISION)
    reviewer_work_assignments = script.get_revision(REVIEWER_WORK_ASSIGNMENTS_REVISION)
    reviewer_assignment_sessions = script.get_revision(REVIEWER_ASSIGNMENT_SESSIONS_REVISION)
    image_review_job_completion = script.get_revision(IMAGE_REVIEW_JOB_COMPLETION_REVISION)
    image_board_geometry_pending = script.get_revision(IMAGE_BOARD_GEOMETRY_PENDING_REVISION)
    board_cell_geometry_pipeline_stage = script.get_revision(
        BOARD_CELL_GEOMETRY_PIPELINE_STAGE_REVISION
    )
    assert script.get_heads() == [BOARD_CELL_GEOMETRY_PIPELINE_STAGE_REVISION]
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
    assert cleanup_operations is not None
    assert cleanup_operations.down_revision == SYMBOL_BOOTSTRAP_REVISION
    assert symbol_localized_names is not None
    assert symbol_localized_names.down_revision == CLEANUP_OPERATIONS_REVISION
    assert image_selection is not None
    assert image_selection.down_revision == CLEANUP_OPERATIONS_REVISION
    assert migration_merge is not None
    assert migration_merge.down_revision == (
        SYMBOL_LOCALIZED_NAMES_REVISION,
        IMAGE_SELECTION_REVISION,
    )
    assert manual_decisions is not None
    assert manual_decisions.down_revision == MIGRATION_MERGE_REVISION
    assert versioned_reruns is not None
    assert versioned_reruns.down_revision == IMAGE_SELECTION_MANUAL_DECISIONS_REVISION
    assert missing_images is not None
    assert missing_images.down_revision == IMAGE_SELECTION_VERSIONED_RERUNS_REVISION
    assert optional_exceptions is not None
    assert optional_exceptions.down_revision == IMAGE_SELECTION_MISSING_IMAGES_REVISION
    assert job_execution_lanes is not None
    assert job_execution_lanes.down_revision == IMAGE_SELECTION_OPTIONAL_EXCEPTIONS_REVISION
    assert worker_lane_runtime is not None
    assert worker_lane_runtime.down_revision == JOB_EXECUTION_LANES_REVISION
    assert image_selection_sequence_order is not None
    assert image_selection_sequence_order.down_revision == WORKER_LANE_RUNTIME_REVISION
    assert verified_training_cohorts is not None
    assert verified_training_cohorts.down_revision == IMAGE_SELECTION_SEQUENCE_ORDER_REVISION
    assert symbol_model_training is not None
    assert symbol_model_training.down_revision == VERIFIED_TRAINING_COHORTS_REVISION
    assert symbol_model_candidate_gate is not None
    assert symbol_model_candidate_gate.down_revision == SYMBOL_MODEL_TRAINING_REVISION
    assert symbol_model_registry is not None
    assert symbol_model_registry.down_revision == SYMBOL_MODEL_CANDIDATE_GATE_REVISION
    assert curated_image_import_batches is not None
    assert curated_image_import_batches.down_revision == SYMBOL_MODEL_REGISTRY_REVISION
    assert grid_calibration_profiles is not None
    assert grid_calibration_profiles.down_revision == CURATED_IMAGE_IMPORT_BATCHES_REVISION
    assert duplicate_range_decisions is not None
    assert duplicate_range_decisions.down_revision == GRID_CALIBRATION_PROFILES_REVISION
    assert image_selection_review_queues is not None
    assert (
        image_selection_review_queues.down_revision
        == IMAGE_SELECTION_DUPLICATE_RANGE_DECISIONS_REVISION
    )
    assert image_selection_derived_recovery is not None
    assert image_selection_derived_recovery.down_revision == IMAGE_SELECTION_REVIEW_QUEUES_REVISION
    assert image_selection_sequence_bounds is not None
    assert (
        image_selection_sequence_bounds.down_revision == IMAGE_SELECTION_DERIVED_RECOVERY_REVISION
    )
    assert canonical_image_sequences is not None
    assert representative_ranking is not None
    assert representative_ranking.down_revision == IMAGE_SELECTION_SEQUENCE_BOUNDS_REVISION
    assert canonical_image_sequences.down_revision == REPRESENTATIVE_RANKING_REVISION
    assert image_symbol_prediction_revisions.down_revision == CANONICAL_IMAGE_SEQUENCES_REVISION
    assert (
        pending_symbol_reinference_job.down_revision == IMAGE_SYMBOL_PREDICTION_REVISIONS_REVISION
    )
    assert image_page_geometry_overrides is not None
    assert image_page_geometry_overrides.down_revision == PENDING_SYMBOL_REINFERENCE_JOB_REVISION
    assert image_review_queue_projection is not None
    assert image_review_queue_projection.down_revision == IMAGE_PAGE_GEOMETRY_OVERRIDES_REVISION
    assert image_review_first_save_wins is not None
    assert image_review_first_save_wins.down_revision == IMAGE_REVIEW_QUEUE_PROJECTION_REVISION
    assert reviewer_work_assignments is not None
    assert reviewer_work_assignments.down_revision == IMAGE_REVIEW_FIRST_SAVE_WINS_REVISION
    assert reviewer_assignment_sessions is not None
    assert reviewer_assignment_sessions.down_revision == REVIEWER_WORK_ASSIGNMENTS_REVISION
    assert image_review_job_completion is not None
    assert image_review_job_completion.down_revision == REVIEWER_ASSIGNMENT_SESSIONS_REVISION
    assert image_board_geometry_pending is not None
    assert image_board_geometry_pending.down_revision == IMAGE_REVIEW_JOB_COMPLETION_REVISION
    assert board_cell_geometry_pipeline_stage is not None
    assert (
        board_cell_geometry_pipeline_stage.down_revision
        == IMAGE_BOARD_GEOMETRY_PENDING_REVISION
    )


def test_board_cell_geometry_pipeline_stage_migration_is_scoped_and_reversible() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()
    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        f"{IMAGE_BOARD_GEOMETRY_PENDING_REVISION}:{BOARD_CELL_GEOMETRY_PIPELINE_STAGE_REVISION}",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{BOARD_CELL_GEOMETRY_PIPELINE_STAGE_REVISION}:{IMAGE_BOARD_GEOMETRY_PENDING_REVISION}",
        sql=True,
    )

    assert "'board_cell_geometry'" in upgrade_output.getvalue().lower()
    assert "'board_cell_geometry'" not in downgrade_output.getvalue().lower()


def test_image_board_geometry_pending_migration_is_scoped_and_reversible() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()
    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        f"{IMAGE_REVIEW_JOB_COMPLETION_REVISION}:{IMAGE_BOARD_GEOMETRY_PENDING_REVISION}",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{IMAGE_BOARD_GEOMETRY_PENDING_REVISION}:{IMAGE_REVIEW_JOB_COMPLETION_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "create table image_board_geometry_pending" in upgrade_sql
    assert "uq_image_board_geometry_pending_manifest" in upgrade_sql
    assert "uq_image_board_geometry_pending_current" in upgrade_sql
    assert "ck_image_board_geometry_pending_lifecycle" in upgrade_sql
    assert "bytea" not in upgrade_sql
    downgrade_sql = downgrade_output.getvalue().lower()
    assert "drop table image_board_geometry_pending" in downgrade_sql


def test_reviewer_assignment_sessions_migration_is_scoped_and_reversible() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()
    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        f"{REVIEWER_WORK_ASSIGNMENTS_REVISION}:{REVIEWER_ASSIGNMENT_SESSIONS_REVISION}",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{REVIEWER_ASSIGNMENT_SESSIONS_REVISION}:{REVIEWER_WORK_ASSIGNMENTS_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "add column reviewer_access_session_id uuid" in upgrade_sql
    assert "ck_reviewer_work_assignments_session_mode" in upgrade_sql
    assert "fk_reviewer_work_assignments_session_scope" in upgrade_sql
    assert "uq_reviewer_work_assignments_access_session" in upgrade_sql
    assert "reviewer_access_session_id is not null" in upgrade_sql
    downgrade_sql = downgrade_output.getvalue().lower()
    assert "drop column reviewer_access_session_id" in downgrade_sql
    assert "drop constraint uq_reviewer_access_sessions_scope_identity" in downgrade_sql


def test_reviewer_work_assignments_migration_is_scoped_fenced_and_reversible() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()
    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        f"{IMAGE_REVIEW_FIRST_SAVE_WINS_REVISION}:{REVIEWER_WORK_ASSIGNMENTS_REVISION}",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{REVIEWER_WORK_ASSIGNMENTS_REVISION}:{IMAGE_REVIEW_FIRST_SAVE_WINS_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "create table reviewer_work_assignments" in upgrade_sql
    assert "assignment_type in ('local', 'online')" in upgrade_sql
    assert "uq_reviewer_work_assignments_active_import" in upgrade_sql
    assert "where closed_at is null" in upgrade_sql
    assert "lease_expires_at > heartbeat_at" in upgrade_sql
    assert "ck_reviewer_work_assignments_closure" in upgrade_sql
    assert "drop table reviewer_work_assignments" in downgrade_output.getvalue().lower()


def test_image_review_first_save_wins_migration_is_durable_and_reversible() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()
    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        f"{IMAGE_REVIEW_QUEUE_PROJECTION_REVISION}:{IMAGE_REVIEW_FIRST_SAVE_WINS_REVISION}",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{IMAGE_REVIEW_FIRST_SAVE_WINS_REVISION}:{IMAGE_REVIEW_QUEUE_PROJECTION_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "add column superseded_count bigint" in upgrade_sql
    assert "'superseded'" in upgrade_sql
    assert "create or replace function project_image_review_queue_status" in upgrade_sql
    assert "superseded_count = superseded_count" in upgrade_sql

    downgrade_sql = downgrade_output.getvalue().lower()
    assert "cannot downgrade first-save-wins while superseded audit rows exist" in downgrade_sql
    assert "drop column superseded_count" in downgrade_sql


def test_image_review_job_completion_migration_is_durable_and_reversible() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()
    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        f"{REVIEWER_ASSIGNMENT_SESSIONS_REVISION}:{IMAGE_REVIEW_JOB_COMPLETION_REVISION}",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{IMAGE_REVIEW_JOB_COMPLETION_REVISION}:{REVIEWER_ASSIGNMENT_SESSIONS_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "create function synchronize_image_review_job_status" in upgrade_sql
    assert "create trigger trg_image_review_job_status" in upgrade_sql
    assert "new.pending_count = 0" in upgrade_sql
    assert "status = 'completed'" in upgrade_sql
    assert "status = 'waiting_for_review'" in upgrade_sql
    assert "from image_review_queue_states as state" in upgrade_sql

    downgrade_sql = downgrade_output.getvalue().lower()
    assert "drop trigger trg_image_review_job_status" in downgrade_sql
    assert "drop function synchronize_image_review_job_status" in downgrade_sql


def test_image_review_queue_projection_migration_is_durable_and_reversible() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()
    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        f"{IMAGE_PAGE_GEOMETRY_OVERRIDES_REVISION}:{IMAGE_REVIEW_QUEUE_PROJECTION_REVISION}",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{IMAGE_REVIEW_QUEUE_PROJECTION_REVISION}:{IMAGE_PAGE_GEOMETRY_OVERRIDES_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "create table image_review_queue_states" in upgrade_sql
    assert "create table image_review_queue_items" in upgrade_sql
    assert "uq_image_review_queue_items_order_key" in upgrade_sql
    assert "create function project_image_review_queue_insert" in upgrade_sql
    assert "create function project_image_review_queue_status" in upgrade_sql
    assert "create function guard_image_review_queue_topology" in upgrade_sql
    assert "create trigger trg_image_review_queue_insert" in upgrade_sql
    assert "create trigger trg_image_review_queue_status" in upgrade_sql
    assert "source_order_index" in upgrade_sql
    assert "queue_version" in upgrade_sql

    downgrade_sql = downgrade_output.getvalue().lower()
    assert "drop trigger trg_image_review_queue_insert" in downgrade_sql
    assert "drop function project_image_review_queue_insert" in downgrade_sql
    assert "drop table image_review_queue_items" in downgrade_sql
    assert "drop table image_review_queue_states" in downgrade_sql


def test_symbol_model_registry_migration_adds_append_only_activation_history() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()
    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        f"{SYMBOL_MODEL_CANDIDATE_GATE_REVISION}:{SYMBOL_MODEL_REGISTRY_REVISION}",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{SYMBOL_MODEL_REGISTRY_REVISION}:{SYMBOL_MODEL_CANDIDATE_GATE_REVISION}",
        sql=True,
    )
    upgrade_sql = upgrade_output.getvalue().lower()
    assert "create table game_symbol_model_activations" in upgrade_sql
    assert "uq_game_symbol_model_activations_idempotency" in upgrade_sql
    assert "uq_game_symbol_model_activations_number" in upgrade_sql
    assert "activation_number" in upgrade_sql
    assert "previous_model_iteration_id" in upgrade_sql
    assert "drop table game_symbol_model_activations" in downgrade_output.getvalue().lower()


def test_symbol_model_candidate_gate_migration_adds_fail_closed_artifact_state() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()
    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        f"{SYMBOL_MODEL_TRAINING_REVISION}:{SYMBOL_MODEL_CANDIDATE_GATE_REVISION}",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{SYMBOL_MODEL_CANDIDATE_GATE_REVISION}:{SYMBOL_MODEL_TRAINING_REVISION}",
        sql=True,
    )
    upgrade_sql = upgrade_output.getvalue().lower()
    assert "candidate_ready" in upgrade_sql
    assert "candidate_manifest_checksum_sha256" in upgrade_sql
    assert "gate_report_checksum_sha256" in upgrade_sql
    assert "rejection_reasons" in upgrade_sql
    downgrade_sql = downgrade_output.getvalue().lower()
    assert "drop column candidate_manifest_checksum_sha256" in downgrade_sql


def test_symbol_model_training_migration_adds_durable_iteration_state() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()
    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        f"{VERIFIED_TRAINING_COHORTS_REVISION}:{SYMBOL_MODEL_TRAINING_REVISION}",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{SYMBOL_MODEL_TRAINING_REVISION}:{VERIFIED_TRAINING_COHORTS_REVISION}",
        sql=True,
    )
    upgrade_sql = upgrade_output.getvalue().lower()
    assert "add value if not exists 'symbol_training'" in upgrade_sql
    assert "create table symbol_model_iterations" in upgrade_sql
    assert "uq_symbol_model_iterations_input" in upgrade_sql
    assert "checkpoint_checksum_sha256" in upgrade_sql
    assert "last_completed_epoch" in upgrade_sql
    assert "drop table symbol_model_iterations" in downgrade_output.getvalue().lower()


def test_verified_training_cohort_migration_adds_manifest_and_positions() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()
    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        f"{IMAGE_SELECTION_SEQUENCE_ORDER_REVISION}:{VERIFIED_TRAINING_COHORTS_REVISION}",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{VERIFIED_TRAINING_COHORTS_REVISION}:{IMAGE_SELECTION_SEQUENCE_ORDER_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "create table verified_training_cohorts" in upgrade_sql
    assert "create table verified_training_cohort_items" in upgrade_sql
    assert "uq_verified_training_cohorts_manifest" in upgrade_sql
    assert "uq_verified_training_cohorts_idempotency" in upgrade_sql
    assert "jsonb_array_length(board_manifest -> 'cells') = 15" in upgrade_sql
    downgrade_sql = downgrade_output.getvalue().lower()
    assert "drop table verified_training_cohort_items" in downgrade_sql
    assert "drop table verified_training_cohorts" in downgrade_sql


def test_job_execution_lanes_allow_general_and_image_selection_slots() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()

    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        f"{IMAGE_SELECTION_OPTIONAL_EXCEPTIONS_REVISION}:{JOB_EXECUTION_LANES_REVISION}",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{JOB_EXECUTION_LANES_REVISION}:{IMAGE_SELECTION_OPTIONAL_EXCEPTIONS_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "job_type = 'image_selection' and execution_slot = 2" in upgrade_sql
    assert "job_type <> 'image_selection' and execution_slot = 1" in upgrade_sql
    assert "drop constraint ck_jobs_processing_lease_fields" in upgrade_sql
    downgrade_sql = downgrade_output.getvalue().lower()
    assert "execution_slot = 2" in downgrade_sql
    assert "execution_slot = 1" in downgrade_sql


def test_image_selection_versioned_reruns_replace_source_uniqueness_with_index() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()

    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        f"{IMAGE_SELECTION_MANUAL_DECISIONS_REVISION}:{IMAGE_SELECTION_VERSIONED_RERUNS_REVISION}",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{IMAGE_SELECTION_VERSIONED_RERUNS_REVISION}:{IMAGE_SELECTION_MANUAL_DECISIONS_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "drop constraint uq_image_selection_runs_source_selection_id" in upgrade_sql
    assert "create index ix_image_selection_runs_source_selection_id" in upgrade_sql
    downgrade_sql = downgrade_output.getvalue().lower()
    assert "drop index ix_image_selection_runs_source_selection_id" in downgrade_sql
    assert "unique (source_selection_id)" in downgrade_sql


def test_image_selection_missing_images_adds_terminal_range_resolution() -> None:
    upgrade_output = StringIO()
    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        f"{IMAGE_SELECTION_VERSIONED_RERUNS_REVISION}:{IMAGE_SELECTION_MISSING_IMAGES_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "missing_image" in upgrade_sql
    assert "add column resolution" in upgrade_sql
    assert "alter column candidate_id drop not null" in upgrade_sql


def test_image_selection_optional_exceptions_allow_missing_ranges() -> None:
    upgrade_output = StringIO()
    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        f"{IMAGE_SELECTION_MISSING_IMAGES_REVISION}:{IMAGE_SELECTION_OPTIONAL_EXCEPTIONS_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "alter column range_start drop not null" in upgrade_sql
    assert "alter column range_end drop not null" in upgrade_sql
    assert "range_start is null and range_end is null" in upgrade_sql


def test_image_selection_sequence_bounds_add_complete_range_cardinality_contract() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()

    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        f"{IMAGE_SELECTION_DERIVED_RECOVERY_REVISION}:{IMAGE_SELECTION_SEQUENCE_BOUNDS_REVISION}",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{IMAGE_SELECTION_SEQUENCE_BOUNDS_REVISION}:{IMAGE_SELECTION_DERIVED_RECOVERY_REVISION}",
        sql=True,
    )

    upgrade_sql = upgrade_output.getvalue().lower()
    assert "add column last_sequence_number" in upgrade_sql
    assert "ck_image_selection_runs_sequence_bounds" in upgrade_sql
    assert "create unique index uq_image_selection_runs_full_identity" in upgrade_sql
    assert "create unique index uq_image_selection_runs_recovery_identity" in upgrade_sql
    downgrade_sql = downgrade_output.getvalue().lower()
    assert "drop column last_sequence_number" in downgrade_sql
    assert "create unique index uq_image_selection_runs_full_identity" in downgrade_sql


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


def test_cleanup_operations_migration_adds_append_only_receipts() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()
    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        f"{SYMBOL_BOOTSTRAP_REVISION}:{CLEANUP_OPERATIONS_REVISION}",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{CLEANUP_OPERATIONS_REVISION}:{SYMBOL_BOOTSTRAP_REVISION}",
        sql=True,
    )
    upgrade_sql = upgrade_output.getvalue().lower()
    assert "create table cleanup_operations" in upgrade_sql
    assert "uq_cleanup_operations_target_preview" in upgrade_sql
    assert "drop table cleanup_operations" in downgrade_output.getvalue().lower()


def test_image_selection_migration_adds_bounded_domain_storage() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()
    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        f"{CLEANUP_OPERATIONS_REVISION}:{IMAGE_SELECTION_REVISION}",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{IMAGE_SELECTION_REVISION}:{CLEANUP_OPERATIONS_REVISION}",
        sql=True,
    )
    upgrade_sql = upgrade_output.getvalue().lower()
    assert "alter type job_type add value if not exists 'image_selection'" in upgrade_sql
    assert "create table image_selection_runs" in upgrade_sql
    assert "create table image_selection_groups" in upgrade_sql
    assert "create table image_selection_candidates" in upgrade_sql
    assert "uq_image_selection_runs_identity" in upgrade_sql
    assert "uq_image_selection_candidates_selected_group" in upgrade_sql
    downgrade_sql = downgrade_output.getvalue().lower()
    assert "drop table image_selection_candidates" in downgrade_sql
    assert "drop type job_type_with_image_selection" in downgrade_sql


def test_manual_image_selection_migration_adds_append_only_decisions() -> None:
    upgrade_output = StringIO()
    downgrade_output = StringIO()
    command.upgrade(
        create_alembic_config(output_buffer=upgrade_output),
        f"{MIGRATION_MERGE_REVISION}:{IMAGE_SELECTION_MANUAL_DECISIONS_REVISION}",
        sql=True,
    )
    command.downgrade(
        create_alembic_config(output_buffer=downgrade_output),
        f"{IMAGE_SELECTION_MANUAL_DECISIONS_REVISION}:{MIGRATION_MERGE_REVISION}",
        sql=True,
    )
    upgrade_sql = upgrade_output.getvalue().lower()
    assert "alter table alembic_version alter column version_num type varchar(128)" in (upgrade_sql)
    assert "create table image_selection_manual_decisions" in upgrade_sql
    assert "uq_image_selection_manual_decisions_revision" in upgrade_sql
    assert "drop table image_selection_manual_decisions" in downgrade_output.getvalue().lower()


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
