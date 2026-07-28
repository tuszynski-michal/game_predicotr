"""Protect idempotent dataset publication from a source job.

Revision ID: 0013_layout_import_publication
Revises: 0012_layout_import_normalization
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_layout_import_publication"
down_revision: str | Sequence[str] | None = "0012_layout_import_normalization"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_dataset_versions_source_job",
        "dataset_versions",
        ["source_job_id"],
        unique=True,
        postgresql_where=sa.text("source_job_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_dataset_versions_source_job",
        table_name="dataset_versions",
    )
