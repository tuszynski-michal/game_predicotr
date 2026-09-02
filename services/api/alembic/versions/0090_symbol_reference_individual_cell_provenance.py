"""Permit symbol references selected from individually approved cells.

Revision ID: 0090_symbol_reference_individual_cell_provenance
Revises: 0089_blurry_symbol_quality
Create Date: 2026-09-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0090_symbol_reference_individual_cell_provenance"
down_revision: str | None = "0089_blurry_symbol_quality"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "ck_symbol_reference_images_position"
_INDIVIDUAL_CELL_CONDITION = (
    "sequence_number > 0 AND cell_index BETWEEN 0 AND 14 "
    "AND resolution_revision >= 0 AND geometry_revision >= 0"
)
_LEGACY_CONDITION = (
    "sequence_number > 0 AND cell_index BETWEEN 0 AND 14 "
    "AND resolution_revision > 0 AND geometry_revision >= 0"
)


def _replace_check_constraint(condition: str) -> None:
    replacement = f"{_CONSTRAINT}_replacement"
    op.create_check_constraint(
        replacement,
        "symbol_reference_images",
        condition,
        postgresql_not_valid=True,
    )
    op.drop_constraint(_CONSTRAINT, "symbol_reference_images", type_="check")
    op.execute(
        f'ALTER TABLE "symbol_reference_images" '
        f'RENAME CONSTRAINT "{replacement}" TO "{_CONSTRAINT}"'
    )


def upgrade() -> None:
    _replace_check_constraint(_INDIVIDUAL_CELL_CONDITION)


def downgrade() -> None:
    op.execute("LOCK TABLE symbol_reference_images IN SHARE ROW EXCLUSIVE MODE")
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM symbol_reference_images WHERE resolution_revision = 0
          ) THEN
            RAISE EXCEPTION
              'Cannot downgrade while individually approved symbol references exist';
          END IF;
        END $$;
        """
    )
    _replace_check_constraint(_LEGACY_CONDITION)
