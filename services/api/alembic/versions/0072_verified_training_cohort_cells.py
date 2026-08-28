"""Persist selected cells of immutable v2 training cohorts.

Revision ID: 0072_verified_training_cohort_cells
Revises: 0071_symbol_cell_training_cohorts
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0072_verified_training_cohort_cells"
down_revision: str | Sequence[str] | None = "0071_symbol_cell_training_cohorts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE verified_training_cohort_cells (
          id uuid PRIMARY KEY,
          cohort_id uuid NOT NULL REFERENCES verified_training_cohorts(id) ON DELETE RESTRICT,
          sample_order integer NOT NULL,
          cell_review_id uuid NOT NULL REFERENCES image_symbol_review_cells(id) ON DELETE RESTRICT,
          review_item_id uuid NOT NULL REFERENCES image_review_items(id) ON DELETE RESTRICT,
          recognized_board_id uuid NOT NULL REFERENCES recognized_boards(id) ON DELETE RESTRICT,
          source_image_id uuid NOT NULL REFERENCES source_images(id) ON DELETE RESTRICT,
          sequence_number bigint NOT NULL,
          cell_index smallint NOT NULL,
          symbol_code varchar(64) NOT NULL,
          crop_checksum_sha256 varchar(64) NOT NULL,
          sample_checksum_sha256 varchar(64) NOT NULL,
          cell_manifest jsonb NOT NULL,
          CONSTRAINT ck_verified_training_cohort_cells_position
            CHECK (sample_order >= 0 AND sequence_number > 0 AND cell_index BETWEEN 0 AND 14),
          CONSTRAINT ck_verified_training_cohort_cells_checksums
            CHECK (sample_checksum_sha256 ~ '^[0-9a-f]{64}$'
               AND crop_checksum_sha256 ~ '^[0-9a-f]{64}$'),
          CONSTRAINT ck_verified_training_cohort_cells_manifest
            CHECK (jsonb_typeof(cell_manifest) = 'object'),
          CONSTRAINT uq_verified_training_cohort_cells_order
            UNIQUE (cohort_id, sample_order),
          CONSTRAINT uq_verified_training_cohort_cells_review
            UNIQUE (cohort_id, cell_review_id)
        )
        """
    )
    op.create_index(
        "ix_verified_training_cohort_cells_cohort_symbol",
        "verified_training_cohort_cells",
        ["cohort_id", "symbol_code"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_verified_training_cohort_cells_cohort_symbol",
        table_name="verified_training_cohort_cells",
    )
    op.drop_table("verified_training_cohort_cells")
