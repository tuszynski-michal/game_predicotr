"""Create dataset versions and compact layout staging.

Revision ID: 0006_dataset_staging
Revises: 0005_symbol_payouts
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_dataset_staging"
down_revision: str | Sequence[str] | None = "0005_symbol_payouts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    dataset_status = postgresql.ENUM(
        "staging",
        "published",
        "archived",
        name="dataset_version_status",
        create_type=False,
    )
    dataset_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "dataset_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("rows", sa.SmallInteger(), nullable=False),
        sa.Column("columns", sa.SmallInteger(), nullable=False),
        sa.Column("signature_cell_width", sa.SmallInteger(), nullable=False),
        sa.Column("layout_count", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            dataset_status,
            server_default="staging",
            nullable=False,
        ),
        sa.Column("generation_seed", sa.BigInteger(), nullable=False),
        sa.Column("generator_version", sa.String(length=64), nullable=False),
        sa.Column("source_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "version > 0",
            name="ck_dataset_versions_version_positive",
        ),
        sa.CheckConstraint(
            "rows BETWEEN 1 AND 32767",
            name="ck_dataset_versions_rows_range",
        ),
        sa.CheckConstraint(
            "columns BETWEEN 1 AND 32767",
            name="ck_dataset_versions_columns_range",
        ),
        sa.CheckConstraint(
            "signature_cell_width BETWEEN 1 AND 5",
            name="ck_dataset_versions_signature_width_range",
        ),
        sa.CheckConstraint(
            "layout_count >= 0",
            name="ck_dataset_versions_layout_count_nonnegative",
        ),
        sa.CheckConstraint(
            "generation_seed BETWEEN 0 AND 2147483647",
            name="ck_dataset_versions_generation_seed_range",
        ),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["games.id"],
            name="fk_dataset_versions_game_id_games",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_dataset_versions"),
        sa.UniqueConstraint(
            "game_id",
            "version",
            name="uq_dataset_versions_game_version",
        ),
    )
    op.create_index(
        "ix_dataset_versions_game_id",
        "dataset_versions",
        ["game_id"],
        unique=False,
    )

    op.create_table(
        "layouts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "dataset_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("signature", sa.String(), nullable=False),
        sa.Column(
            "cells",
            postgresql.ARRAY(sa.SmallInteger(), dimensions=1),
            nullable=False,
        ),
        sa.Column("source_board_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "sequence_number > 0",
            name="ck_layouts_sequence_number_positive",
        ),
        sa.CheckConstraint(
            "cardinality(cells) > 0",
            name="ck_layouts_cells_not_empty",
        ),
        sa.CheckConstraint(
            "1 <= ALL(cells) AND 32767 >= ALL(cells)",
            name="ck_layouts_cells_mobile_code_range",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name="fk_layouts_dataset_version_id_dataset_versions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_layouts"),
        sa.UniqueConstraint(
            "dataset_version_id",
            "sequence_number",
            name="uq_layouts_dataset_sequence",
        ),
    )
    op.create_index(
        "ix_layouts_dataset_version_id",
        "layouts",
        ["dataset_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_layouts_dataset_signature",
        "layouts",
        ["dataset_version_id", "signature"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_layouts_dataset_signature", table_name="layouts")
    op.drop_index("ix_layouts_dataset_version_id", table_name="layouts")
    op.drop_table("layouts")
    op.drop_index(
        "ix_dataset_versions_game_id",
        table_name="dataset_versions",
    )
    op.drop_table("dataset_versions")
    postgresql.ENUM(
        name="dataset_version_status",
        create_type=False,
    ).drop(
        op.get_bind(),
        checkfirst=True,
    )
