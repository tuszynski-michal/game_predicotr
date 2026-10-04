"""Allow the grid engine profiles as a game's page format (TASK-0830).

``public.games.shape_geometry_configuration`` additionally accepts
``grid_profile_777_v2`` and ``grid_profile_mumie_v1``. The existing values and
historical ``NULL`` keep their meaning; no row is changed. The models behind
the profiles are files in the managed artifacts directory, not database rows.

Downgrade restores the 0116 constraint, but refuses
(``GRID_ENGINE_PROFILE_IN_USE``) while any game uses a grid engine profile:
the operator's choice would be lost and the old constraint could not hold.

Revision ID: 0140_grid_engine_profiles
Revises: 0139_source_image_geometry_completeness
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0140_grid_engine_profiles"
down_revision: str | Sequence[str] | None = "0139_source_image_geometry_completeness"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "ck_games_shape_geometry_configuration"
PREVIOUS_VALUES = ("framed_full_page_v2", "requires_clarification")
GRID_ENGINE_PROFILE_VALUES = ("grid_profile_777_v2", "grid_profile_mumie_v1")


def _expression(values: Sequence[str]) -> str:
    rendered = ", ".join(f"'{value}'" for value in values)
    return f"shape_geometry_configuration IS NULL OR shape_geometry_configuration IN ({rendered})"


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.drop_constraint(CONSTRAINT, "games", schema="public")
    op.create_check_constraint(
        CONSTRAINT,
        "games",
        _expression(PREVIOUS_VALUES + GRID_ENGINE_PROFILE_VALUES),
        schema="public",
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.execute("LOCK TABLE public.games IN SHARE ROW EXCLUSIVE MODE")
    profiles = ", ".join(f"'{value}'" for value in GRID_ENGINE_PROFILE_VALUES)
    op.execute(f"""DO $guard$ BEGIN
        IF EXISTS (
            SELECT 1 FROM public.games
            WHERE shape_geometry_configuration IN ({profiles})
        ) THEN
            RAISE EXCEPTION 'GRID_ENGINE_PROFILE_IN_USE: a game uses a grid engine '
                'profile as its page format; change it before downgrading';
        END IF;
    END $guard$""")
    op.drop_constraint(CONSTRAINT, "games", schema="public")
    op.create_check_constraint(CONSTRAINT, "games", _expression(PREVIOUS_VALUES), schema="public")
