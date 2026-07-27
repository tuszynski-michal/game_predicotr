"""Create immutable mobile release selections.

Revision ID: 0010_mobile_releases
Revises: 0009_layout_payouts
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_mobile_releases"
down_revision: str | Sequence[str] | None = "0009_layout_payouts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

mobile_release_status = postgresql.ENUM(
    "draft",
    "building",
    "ready",
    "failed",
    "archived",
    name="mobile_release_status",
    create_type=False,
)


def upgrade() -> None:
    mobile_release_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "mobile_releases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            mobile_release_status,
            server_default="draft",
            nullable=False,
        ),
        sa.Column("algorithm_version", sa.String(length=100), nullable=False),
        sa.Column("snapshot_schema_version", sa.Integer(), nullable=False),
        sa.Column("snapshot_path", sa.String(length=1000), nullable=True),
        sa.Column("snapshot_checksum", sa.String(length=64), nullable=True),
        sa.Column("apk_path", sa.String(length=1000), nullable=True),
        sa.Column("apk_checksum", sa.String(length=64), nullable=True),
        sa.Column("build_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$'",
            name="ck_mobile_releases_version_safe",
        ),
        sa.CheckConstraint(
            "length(btrim(algorithm_version)) > 0",
            name="ck_mobile_releases_algorithm_not_blank",
        ),
        sa.CheckConstraint(
            "snapshot_schema_version > 0",
            name="ck_mobile_releases_schema_positive",
        ),
        sa.CheckConstraint(
            "snapshot_checksum IS NULL OR snapshot_checksum ~ '^[0-9a-f]{64}$'",
            name="ck_mobile_releases_snapshot_checksum",
        ),
        sa.CheckConstraint(
            "apk_checksum IS NULL OR apk_checksum ~ '^[0-9a-f]{64}$'",
            name="ck_mobile_releases_apk_checksum",
        ),
        sa.CheckConstraint(
            "(snapshot_path IS NULL) = (snapshot_checksum IS NULL)",
            name="ck_mobile_releases_snapshot_complete",
        ),
        sa.CheckConstraint(
            "(apk_path IS NULL) = (apk_checksum IS NULL)",
            name="ck_mobile_releases_apk_complete",
        ),
        sa.ForeignKeyConstraint(
            ["build_job_id"],
            ["jobs.id"],
            name="fk_mobile_releases_build_job_id_jobs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mobile_releases"),
        sa.UniqueConstraint(
            "version",
            name="uq_mobile_releases_version",
        ),
        sa.UniqueConstraint(
            "build_job_id",
            name="uq_mobile_releases_build_job_id",
        ),
    )
    op.create_table(
        "mobile_release_games",
        sa.Column(
            "mobile_release_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "dataset_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "rules_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("layout_count", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "layout_count > 0",
            name="ck_mobile_release_games_layout_count_positive",
        ),
        sa.ForeignKeyConstraint(
            ["mobile_release_id"],
            ["mobile_releases.id"],
            name="fk_mobile_release_games_release",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["games.id"],
            name="fk_mobile_release_games_game",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name="fk_mobile_release_games_dataset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rules_version_id"],
            ["rules_versions.id"],
            name="fk_mobile_release_games_rules",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "mobile_release_id",
            "game_id",
            name="pk_mobile_release_games",
        ),
    )
    op.create_index(
        "ix_mobile_release_games_game_id",
        "mobile_release_games",
        ["game_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mobile_release_games_game_id",
        table_name="mobile_release_games",
    )
    op.drop_table("mobile_release_games")
    op.drop_table("mobile_releases")
    mobile_release_status.drop(op.get_bind(), checkfirst=True)
