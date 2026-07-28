"""Create normalized layout import validation staging.

Revision ID: 0012_layout_import_normalization
Revises: 0011_layout_import_staging
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_layout_import_normalization"
down_revision: str | Sequence[str] | None = "0011_layout_import_staging"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "layout_import_normalized_rows",
        sa.Column("validation_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("line_number", sa.BigInteger(), nullable=False),
        sa.Column("import_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rules_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=True),
        sa.Column(
            "cells",
            postgresql.ARRAY(sa.SmallInteger(), dimensions=1),
            nullable=True,
        ),
        sa.Column("signature", sa.String(length=500), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "line_number > 0",
            name="ck_layout_import_normalized_rows_line_positive",
        ),
        sa.CheckConstraint(
            "sequence_number IS NULL OR sequence_number > 0",
            name="ck_layout_import_normalized_rows_sequence_positive",
        ),
        sa.CheckConstraint(
            "cells IS NULL OR cardinality(cells) > 0",
            name="ck_layout_import_normalized_rows_cells_not_empty",
        ),
        sa.CheckConstraint(
            "cells IS NULL OR (1 <= ALL(cells) AND 32767 >= ALL(cells))",
            name="ck_layout_import_normalized_rows_cells_code_range",
        ),
        sa.CheckConstraint(
            "("
            "sequence_number IS NOT NULL AND cells IS NOT NULL "
            "AND signature IS NOT NULL AND length(signature) > 0 "
            "AND error_code IS NULL AND error_message IS NULL"
            ") OR ("
            "signature IS NULL AND error_code IS NOT NULL "
            "AND error_message IS NOT NULL "
            "AND length(btrim(error_code)) > 0 "
            "AND length(btrim(error_message)) > 0 "
            "AND ((sequence_number IS NULL AND cells IS NULL) "
            "OR (sequence_number IS NOT NULL AND cells IS NOT NULL))"
            ")",
            name="ck_layout_import_normalized_rows_result_variant",
        ),
        sa.ForeignKeyConstraint(
            ["validation_job_id"],
            ["jobs.id"],
            name="fk_layout_import_normalized_rows_validation_job",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["import_job_id", "line_number"],
            ["layout_import_rows.job_id", "layout_import_rows.line_number"],
            name="fk_layout_import_normalized_rows_raw_row",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rules_version_id"],
            ["rules_versions.id"],
            name="fk_layout_import_normalized_rows_rules_version",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "validation_job_id",
            "line_number",
            name="pk_layout_import_normalized_rows",
        ),
    )
    op.create_index(
        "ix_layout_import_normalized_rows_sequence",
        "layout_import_normalized_rows",
        ["validation_job_id", "sequence_number"],
        unique=False,
    )
    op.create_index(
        "ix_layout_import_normalized_rows_signature",
        "layout_import_normalized_rows",
        ["validation_job_id", "signature"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_layout_import_normalized_rows_signature",
        table_name="layout_import_normalized_rows",
    )
    op.drop_index(
        "ix_layout_import_normalized_rows_sequence",
        table_name="layout_import_normalized_rows",
    )
    op.drop_table("layout_import_normalized_rows")
