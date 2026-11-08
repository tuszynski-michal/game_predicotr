"""Independent content annotations, blind sessions and immutable replay receipts."""

from game_predictor_api.storage.grid_cell_content_migration import downgrade, upgrade

revision = "0182_cell_content_references"
down_revision = "0181_validation_purposes"
branch_labels = depends_on = None

__all__ = ["upgrade", "downgrade"]
