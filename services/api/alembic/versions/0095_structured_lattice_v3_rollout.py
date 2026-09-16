"""Allow the accepted structured lattice v3 rollout mode.

Revision ID: 0095_structured_lattice_v3_rollout
Revises: 0094_grid_profile_gate_revisions
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0095_structured_lattice_v3_rollout"
down_revision: str | Sequence[str] | None = "0094_grid_profile_gate_revisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_image_geometry_rollout_states_geometry_mode",
        "image_geometry_rollout_states",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_geometry_rollout_states_geometry_mode",
        "image_geometry_rollout_states",
        "geometry_mode IN ('legacy', 'structured_shadow', 'structured_review', "
        "'structured_default', 'structured_lattice_v3')",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE image_geometry_rollout_states "
        "SET geometry_mode = 'structured_default' "
        "WHERE geometry_mode = 'structured_lattice_v3'"
    )
    op.drop_constraint(
        "ck_image_geometry_rollout_states_geometry_mode",
        "image_geometry_rollout_states",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_geometry_rollout_states_geometry_mode",
        "image_geometry_rollout_states",
        "geometry_mode IN ('legacy', 'structured_shadow', 'structured_review', "
        "'structured_default')",
    )
