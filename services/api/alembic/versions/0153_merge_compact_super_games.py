"""Join compact management and super-game histories without additional DDL."""

revision = "0153_merge_compact_super_games"
down_revision = ("0152_super_game_series", "0152_management_compact_panel")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
