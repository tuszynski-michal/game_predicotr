"""Allow explicit lab-origin candidates and append-only model deactivation."""

from collections.abc import Sequence

from alembic import op

revision: str = "0144_lab_symbol_candidate_registry"
down_revision: str | Sequence[str] | None = "0143_merge_share_grid_shadow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORIGIN_CHECK = """
    (origin = 'production_training' AND cohort_id IS NOT NULL
     AND origin_fingerprint IS NULL AND origin_manifest_relative_path IS NULL
     AND origin_manifest_checksum_sha256 IS NULL) OR
    (origin = 'lab_import' AND cohort_id IS NULL
     AND origin_fingerprint IS NOT NULL AND origin_fingerprint ~ '^[0-9a-f]{64}$'
     AND origin_manifest_checksum_sha256 IS NOT NULL
     AND origin_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$'
     AND origin_manifest_relative_path IS NOT NULL AND btrim(origin_manifest_relative_path) <> '')
"""


def _guard() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.execute("LOCK TABLE public.game_storage_locations IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $guard$ BEGIN
        IF EXISTS (SELECT 1 FROM public.game_storage_lifecycle_operations WHERE status <> 'done')
           OR EXISTS (SELECT 1 FROM public.game_storage_locations
                      WHERE status NOT IN ('active','blocked')
                        OR manifest_version <> 'game-data-v2-manifest-v5'
                        OR store_schema <> 'game_data_v2') THEN
            RAISE EXCEPTION 'GAME_STORAGE_LIFECYCLE_IN_PROGRESS';
        END IF;
    END $guard$""")


def upgrade() -> None:
    _guard()
    op.execute("""ALTER TABLE game_data_v2.symbol_model_iterations
        ADD COLUMN origin VARCHAR(30) NOT NULL DEFAULT 'production_training',
        ADD COLUMN origin_fingerprint VARCHAR(64),
        ADD COLUMN origin_manifest_relative_path VARCHAR(1000),
        ADD COLUMN origin_manifest_checksum_sha256 VARCHAR(64),
        ALTER COLUMN cohort_id DROP NOT NULL""")
    op.execute(f"""ALTER TABLE game_data_v2.symbol_model_iterations
        ADD CONSTRAINT ck_symbol_model_iterations_origin CHECK ({ORIGIN_CHECK}),
        ADD CONSTRAINT uq_symbol_model_iterations_origin UNIQUE(game_id,origin_fingerprint)""")
    op.execute("""ALTER TABLE game_data_v2.game_symbol_model_activations
        ALTER COLUMN model_iteration_id DROP NOT NULL,
        DROP CONSTRAINT ck_game_symbol_model_activations_action,
        ADD CONSTRAINT ck_game_symbol_model_activations_action
            CHECK(action IN ('activate','rollback','deactivate')),
        ADD CONSTRAINT ck_game_symbol_model_activations_target
            CHECK((action = 'deactivate' AND model_iteration_id IS NULL) OR
                  (action IN ('activate','rollback') AND model_iteration_id IS NOT NULL))""")
    op.execute("""CREATE UNIQUE INDEX uq_jobs_lab_symbol_import_request ON public.jobs
        (game_id,(input_payload->>'idempotency_key'))
        WHERE job_type = 'validate'
            AND input_payload->>'validation_kind' = 'symbol_model_lab_import'""")


def downgrade() -> None:
    _guard()
    op.execute("SET LOCAL row_security = off")
    op.execute(
        "LOCK TABLE game_data_v2.symbol_model_iterations, "
        "game_data_v2.game_symbol_model_activations IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $guard$ BEGIN
        IF EXISTS (SELECT 1 FROM game_data_v2.symbol_model_iterations WHERE origin = 'lab_import')
           OR EXISTS (SELECT 1 FROM game_data_v2.game_symbol_model_activations
                      WHERE action = 'deactivate')
           OR EXISTS (SELECT 1 FROM public.jobs
                      WHERE input_payload->>'validation_kind' = 'symbol_model_lab_import') THEN
            RAISE EXCEPTION 'LAB_SYMBOL_REGISTRY_DOWNGRADE_HAS_HISTORY';
        END IF;
    END $guard$""")
    op.execute("DROP INDEX public.uq_jobs_lab_symbol_import_request")
    op.execute("""ALTER TABLE game_data_v2.game_symbol_model_activations
        DROP CONSTRAINT ck_game_symbol_model_activations_target,
        DROP CONSTRAINT ck_game_symbol_model_activations_action,
        ADD CONSTRAINT ck_game_symbol_model_activations_action
            CHECK(action IN ('activate','rollback')),
        ALTER COLUMN model_iteration_id SET NOT NULL""")
    op.execute("""ALTER TABLE game_data_v2.symbol_model_iterations
        DROP CONSTRAINT uq_symbol_model_iterations_origin,
        DROP CONSTRAINT ck_symbol_model_iterations_origin,
        ALTER COLUMN cohort_id SET NOT NULL,
        DROP COLUMN origin, DROP COLUMN origin_fingerprint,
        DROP COLUMN origin_manifest_relative_path, DROP COLUMN origin_manifest_checksum_sha256""")
