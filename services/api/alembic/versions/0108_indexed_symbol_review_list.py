"""Index the V2 current symbol-cell projection for bounded list reads."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0108_indexed_symbol_review_list"
down_revision: str | Sequence[str] | None = "0107_current_symbol_cell_projection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    for schema in ("public", "game_data_v2"):
        op.add_column(
            "image_symbol_review_cells",
            sa.Column("prediction_confidence", sa.Float(), nullable=True),
            schema=schema,
        )
        op.create_check_constraint(
            (
                "ck_v2_symbol_cell_prediction_confidence"
                if schema == "game_data_v2"
                else "ck_image_symbol_review_cells_prediction_confidence"
            ),
            "image_symbol_review_cells",
            "prediction_confidence IS NULL OR "
            "(prediction_confidence >= 0 AND prediction_confidence <= 1)",
            schema=schema,
        )

    op.execute(
        "CREATE INDEX v2_ix_symbol_review_list_all "
        "ON game_data_v2.image_symbol_review_cells "
        "(game_id, sequence_number, cell_index, id) WHERE source_available"
    )
    op.execute(
        "CREATE INDEX v2_ix_symbol_review_list_symbol_state "
        "ON game_data_v2.image_symbol_review_cells "
        "(game_id, assigned_symbol_id, review_state, sequence_number, cell_index, id) "
        "WHERE source_available AND quality_issue IS NULL"
    )
    op.execute(
        "CREATE INDEX v2_ix_symbol_review_list_unknown "
        "ON game_data_v2.image_symbol_review_cells "
        "(game_id, review_state, sequence_number, cell_index, id) "
        "WHERE source_available AND "
        "(assigned_symbol_id IS NULL OR quality_issue IN ('grid_issue', 'unreadable'))"
    )
    op.execute(
        "CREATE INDEX v2_ix_symbol_review_list_confidence "
        "ON game_data_v2.image_symbol_review_cells "
        "(game_id, prediction_confidence, sequence_number, cell_index, id) "
        "WHERE source_available"
    )
    op.execute(
        "CREATE INDEX v2_ix_symbol_review_active_cohort "
        "ON game_data_v2.verified_training_cohort_cells "
        "(game_id, cohort_id, cell_review_id)"
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    for name in (
        "v2_ix_symbol_review_active_cohort",
        "v2_ix_symbol_review_list_confidence",
        "v2_ix_symbol_review_list_unknown",
        "v2_ix_symbol_review_list_symbol_state",
        "v2_ix_symbol_review_list_all",
    ):
        op.execute(f"DROP INDEX game_data_v2.{name}")
    for schema in ("game_data_v2", "public"):
        op.drop_constraint(
            (
                "ck_v2_symbol_cell_prediction_confidence"
                if schema == "game_data_v2"
                else "ck_image_symbol_review_cells_prediction_confidence"
            ),
            "image_symbol_review_cells",
            schema=schema,
            type_="check",
        )
        op.drop_column("image_symbol_review_cells", "prediction_confidence", schema=schema)
