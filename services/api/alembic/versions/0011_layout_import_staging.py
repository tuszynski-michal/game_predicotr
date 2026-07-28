"""Create isolated raw layout import staging.

Revision ID: 0011_layout_import_staging
Revises: 0010_mobile_releases
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_layout_import_staging"
down_revision: str | Sequence[str] | None = "0010_mobile_releases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "layout_import_rows",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("line_number", sa.BigInteger(), nullable=False),
        sa.Column("byte_offset_end", sa.BigInteger(), nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=True),
        sa.Column(
            "cells",
            postgresql.ARRAY(sa.SmallInteger(), dimensions=1),
            nullable=True,
        ),
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
            name="ck_layout_import_rows_line_positive",
        ),
        sa.CheckConstraint(
            "byte_offset_end > 0",
            name="ck_layout_import_rows_offset_positive",
        ),
        sa.CheckConstraint(
            "sequence_number IS NULL OR sequence_number > 0",
            name="ck_layout_import_rows_sequence_positive",
        ),
        sa.CheckConstraint(
            "cells IS NULL OR cardinality(cells) > 0",
            name="ck_layout_import_rows_cells_not_empty",
        ),
        sa.CheckConstraint(
            "cells IS NULL OR (1 <= ALL(cells) AND 32767 >= ALL(cells))",
            name="ck_layout_import_rows_cells_mobile_code_range",
        ),
        sa.CheckConstraint(
            "("
            "sequence_number IS NOT NULL AND cells IS NOT NULL "
            "AND error_code IS NULL AND error_message IS NULL"
            ") OR ("
            "sequence_number IS NULL AND cells IS NULL "
            "AND error_code IS NOT NULL AND error_message IS NOT NULL "
            "AND length(btrim(error_code)) > 0 "
            "AND length(btrim(error_message)) > 0"
            ")",
            name="ck_layout_import_rows_result_variant",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name="fk_layout_import_rows_job_id_jobs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "job_id",
            "line_number",
            name="pk_layout_import_rows",
        ),
    )
    op.create_index(
        "ix_layout_import_rows_job_offset",
        "layout_import_rows",
        ["job_id", "byte_offset_end"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_layout_import_rows_job_offset",
        table_name="layout_import_rows",
    )
    op.drop_table("layout_import_rows")
