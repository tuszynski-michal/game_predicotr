"""Preserve exact neural source binding and distinguish its geometry engine."""

from collections.abc import Sequence

from alembic import op
from game_predictor_api.storage.neural_page_geometry_constraints import NEURAL_PAGE_BINDING_CHECK

revision: str = "0145_neural_page_geometry_binding"
down_revision: str | Sequence[str] | None = "0144_lab_symbol_candidate_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BINDING_CHECK = NEURAL_PAGE_BINDING_CHECK


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
    op.execute("""ALTER TABLE game_data_v2.image_page_geometry_overrides
        ADD COLUMN neural_proposal_binding JSONB,
        DROP CONSTRAINT ck_image_page_geometry_overrides_quads,
        ADD CONSTRAINT ck_image_page_geometry_overrides_quads CHECK (
            jsonb_typeof(final_quads) = 'array' AND (
                (neural_proposal_binding IS NULL
                 AND jsonb_array_length(final_quads) BETWEEN 1 AND 9)
                OR (neural_proposal_binding IS NOT NULL
                    AND jsonb_array_length(final_quads) = 0)))""")
    op.execute(f"""ALTER TABLE game_data_v2.image_page_geometry_overrides
        ADD CONSTRAINT ck_page_override_neural_binding CHECK ({BINDING_CHECK})""")
    op.execute("""ALTER TABLE game_data_v2.image_source_geometry_revisions
        DROP CONSTRAINT ck_image_source_geometry_revisions_engine,
        ADD CONSTRAINT ck_image_source_geometry_revisions_engine CHECK (
            engine_kind IN ('legacy_v20','structured_opencv_v1','manual_v1',
                           'keypoint_fallback_v1','neural_grid_v1')
            AND length(btrim(engine_version)) > 0)""")


def downgrade() -> None:
    _guard()
    op.execute("SET LOCAL row_security = off")
    op.execute(
        "LOCK TABLE game_data_v2.image_page_geometry_overrides, "
        "game_data_v2.image_source_geometry_revisions IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $guard$ BEGIN
        IF EXISTS (SELECT 1 FROM game_data_v2.image_page_geometry_overrides
                   WHERE neural_proposal_binding IS NOT NULL)
           OR EXISTS (SELECT 1 FROM game_data_v2.image_source_geometry_revisions
                      WHERE engine_kind = 'neural_grid_v1') THEN
            RAISE EXCEPTION 'NEURAL_PAGE_GEOMETRY_DOWNGRADE_HAS_HISTORY';
        END IF;
    END $guard$""")
    op.execute("""ALTER TABLE game_data_v2.image_source_geometry_revisions
        DROP CONSTRAINT ck_image_source_geometry_revisions_engine,
        ADD CONSTRAINT ck_image_source_geometry_revisions_engine CHECK (
            engine_kind IN ('legacy_v20','structured_opencv_v1','manual_v1','keypoint_fallback_v1')
            AND length(btrim(engine_version)) > 0)""")
    op.execute("""ALTER TABLE game_data_v2.image_page_geometry_overrides
        DROP CONSTRAINT ck_page_override_neural_binding,
        DROP CONSTRAINT ck_image_page_geometry_overrides_quads,
        ADD CONSTRAINT ck_image_page_geometry_overrides_quads CHECK (
            jsonb_typeof(final_quads) = 'array'
            AND jsonb_array_length(final_quads) BETWEEN 1 AND 9),
        DROP COLUMN neural_proposal_binding""")
