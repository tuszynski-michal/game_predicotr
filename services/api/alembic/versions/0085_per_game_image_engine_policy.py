"""Initialize one safe image-import engine policy for every game.

Revision ID: 0085_per_game_image_engine_policy
Revises: 0084_additive_virtual_geometry_contracts
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0085_per_game_image_engine_policy"
down_revision: str | Sequence[str] | None = "0084_additive_virtual_geometry_contracts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTOR = "system:migration-0085"


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO image_geometry_rollout_states (
            game_id, geometry_mode, cell_asset_mode, revision,
            backfill_status, updated_by
        )
        SELECT id, 'legacy', 'legacy_files', 0, 'not_started', '{_ACTOR}'
        FROM games
        ON CONFLICT (game_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        DELETE FROM image_geometry_rollout_states
        WHERE updated_by = '{_ACTOR}'
          AND revision = 0
          AND geometry_mode = 'legacy'
          AND cell_asset_mode = 'legacy_files'
          AND backfill_status = 'not_started'
          AND last_source_image_id IS NULL
          AND validation_job_id IS NULL
          AND failure_code IS NULL
        """
    )
