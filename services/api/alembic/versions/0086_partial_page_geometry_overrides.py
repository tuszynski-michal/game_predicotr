"""Allow page geometry overrides for attested final-page prefixes.

Revision ID: 0086_partial_page_geometry_overrides
Revises: 0085_per_game_image_engine_policy
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0086_partial_page_geometry_overrides"
down_revision: str | Sequence[str] | None = "0085_per_game_image_engine_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_image_page_geometry_overrides_quads",
        "image_page_geometry_overrides",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_page_geometry_overrides_quads",
        "image_page_geometry_overrides",
        "jsonb_typeof(final_quads) = 'array' AND jsonb_array_length(final_quads) BETWEEN 1 AND 9",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_image_page_geometry_overrides_quads",
        "image_page_geometry_overrides",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_page_geometry_overrides_quads",
        "image_page_geometry_overrides",
        sa.text("jsonb_typeof(final_quads) = 'array' AND jsonb_array_length(final_quads) = 9"),
    )
