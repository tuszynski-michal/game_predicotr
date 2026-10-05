"""Join independently tested share-correction and grid-shadow migration heads.

Each parent retains its original schema changes. This revision only joins the
graph; it never rewrites images, geometry, symbol decisions, or shadow history.
"""

from collections.abc import Sequence

revision: str = "0143_merge_share_grid_shadow"
down_revision: str | Sequence[str] | None = (
    "0141_share_symbol_corrections",
    "0142_grid_geometry_shadow_results",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
