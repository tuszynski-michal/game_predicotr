"""Join the V3 grid fine-tuning history with main's board-search panels without DDL."""

revision = "0164_merge_main_board_search_panels"
down_revision = ("0163_grid_training_cohorts", "0155_board_search_panels")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
