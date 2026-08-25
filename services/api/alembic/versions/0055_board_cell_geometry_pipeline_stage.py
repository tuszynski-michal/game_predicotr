"""Allow the explicitly pinned v20 board-cell geometry stage.

Revision ID: 0055_board_cell_geometry_pipeline_stage
Revises: 0054_image_board_geometry_pending
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0055_board_cell_geometry_pipeline_stage"
down_revision: str | Sequence[str] | None = "0054_image_board_geometry_pending"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_V18_STAGES = (
    "stage IN ('discovery', 'normalization', 'board_detection', "
    "'board_crops', 'sequence_ocr', 'symbol_inference')"
)
_V20_STAGES = (
    "stage IN ('discovery', 'normalization', 'board_detection', "
    "'board_cell_geometry', 'board_crops', 'sequence_ocr', 'symbol_inference')"
)


def upgrade() -> None:
    op.drop_constraint(
        "ck_image_pipeline_stage_results_stage",
        "image_pipeline_stage_results",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_pipeline_stage_results_stage",
        "image_pipeline_stage_results",
        _V20_STAGES,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_image_pipeline_stage_results_stage",
        "image_pipeline_stage_results",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_pipeline_stage_results_stage",
        "image_pipeline_stage_results",
        _V18_STAGES,
    )
