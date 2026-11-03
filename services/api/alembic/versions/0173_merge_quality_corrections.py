"""Join independently audited readability and grid-correction histories."""

revision = "0173_merge_quality_corrections"
down_revision = ("0171_grid_correction_learning", "0172_symbol_readability")
branch_labels = depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
