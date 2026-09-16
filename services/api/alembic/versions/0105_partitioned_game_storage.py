"""Empty partitioned game store and durable ownership registry.

No game is registered, copied, partitioned or routed by this migration.
Runtime write-through triggers and routing belong to TASK-0519.
"""

from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from game_predictor_api.storage.game_data_v2_manifest_v1 import (
    CATALOG,
    CONTROL_TABLES,
    GAME_TABLES,
    SHARED,
    VERSION,
    ownership,
)
from sqlalchemy.dialects import postgresql

revision: str = "0105_partitioned_game_storage"
down_revision: str | Sequence[str] | None = "0104_game_deletion_access_paths"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _statements() -> tuple[str, ...]:
    path = Path(__file__).resolve().parents[1] / "sql" / "game_data_v2_schema_v1.sql"
    return tuple(
        part.strip().removesuffix(";") for part in path.read_text().split(";\n") if part.strip()
    )


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.execute("SET LOCAL search_path = pg_catalog, public")
    op.execute("CREATE SCHEMA game_data_v2")
    for table in ("symbols", "rules_versions", "jobs"):
        op.create_unique_constraint(
            f"uq_v2_{table}_game_id_id", table, ["game_id", "id"], schema="public"
        )

    op.create_table(
        "game_storage_table_manifest",
        sa.Column("manifest_version", sa.Text(), nullable=False),
        sa.Column("table_name", sa.Text(), nullable=False),
        sa.Column("ownership", sa.Text(), nullable=False),
        sa.Column("partitioned", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("manifest_version", "table_name"),
        sa.UniqueConstraint("manifest_version", "table_name", "ownership"),
        sa.CheckConstraint("ownership IN ('catalog', 'game', 'shared')"),
        sa.CheckConstraint("partitioned = (ownership = 'game')"),
        schema="public",
    )
    op.create_table(
        "game_storage_locations",
        sa.Column("game_id", sa.Uuid(), primary_key=True),
        sa.Column("store_schema", sa.Text(), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("manifest_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["game_id"], ["public.games.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("store_schema IN ('public', 'game_data_v2')"),
        sa.CheckConstraint("generation >= 1 AND revision >= 0"),
        sa.CheckConstraint("status IN ('active', 'migrating', 'deleting', 'blocked')"),
        sa.CheckConstraint(f"manifest_version = '{VERSION}'"),
        schema="public",
    )
    op.create_table(
        "game_storage_migrations",
        sa.Column("id", sa.Uuid(), nullable=False),
        # Intentionally no games FK: audit receipts must survive game deletion.
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("manifest_version", sa.Text(), nullable=False),
        sa.Column("source_schema", sa.Text(), nullable=False),
        sa.Column("target_schema", sa.Text(), nullable=False),
        sa.Column("source_generation", sa.BigInteger(), nullable=False),
        sa.Column("target_generation", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("failure_code", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("game_id", "id"),
        sa.UniqueConstraint("game_id", "target_generation"),
        sa.UniqueConstraint("game_id", "id", "manifest_version"),
        sa.CheckConstraint("source_schema = 'public' AND target_schema = 'game_data_v2'"),
        sa.CheckConstraint("source_generation >= 1 AND target_generation = source_generation + 1"),
        sa.CheckConstraint("revision >= 0"),
        sa.CheckConstraint(f"manifest_version = '{VERSION}'"),
        sa.CheckConstraint(
            "status IN ('prepared', 'copying', 'validating', 'ready', "
            "'completed', 'failed', 'cancelled')"
        ),
        schema="public",
    )
    op.create_index(
        "uq_game_storage_one_active_migration",
        "game_storage_migrations",
        ["game_id"],
        unique=True,
        schema="public",
        postgresql_where=sa.text("status NOT IN ('completed', 'cancelled')"),
    )
    op.create_table(
        "game_storage_table_progress",
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("migration_id", sa.Uuid(), nullable=False),
        sa.Column("manifest_version", sa.Text(), nullable=False),
        sa.Column("table_name", sa.Text(), nullable=False),
        sa.Column("ownership", sa.Text(), nullable=False, server_default="game"),
        sa.Column("cursor", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("copied_rows", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("source_sha256", sa.String(64), nullable=True),
        sa.Column("target_sha256", sa.String(64), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("game_id", "migration_id", "table_name"),
        sa.ForeignKeyConstraint(
            ["game_id", "migration_id", "manifest_version"],
            [
                "public.game_storage_migrations.game_id",
                "public.game_storage_migrations.id",
                "public.game_storage_migrations.manifest_version",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["manifest_version", "table_name", "ownership"],
            [
                "public.game_storage_table_manifest.manifest_version",
                "public.game_storage_table_manifest.table_name",
                "public.game_storage_table_manifest.ownership",
            ],
        ),
        sa.CheckConstraint("copied_rows >= 0 AND revision >= 0"),
        sa.CheckConstraint("ownership = 'game'"),
        sa.CheckConstraint("status IN ('pending', 'copying', 'copied', 'validated', 'failed')"),
        sa.CheckConstraint("octet_length(cursor::text) <= 65536"),
        schema="public",
    )
    op.create_index(
        "ix_game_storage_progress_manifest",
        "game_storage_table_progress",
        ["manifest_version", "table_name", "ownership"],
        schema="public",
    )
    manifest = sa.table(
        "game_storage_table_manifest",
        sa.column("manifest_version", sa.Text()),
        sa.column("table_name", sa.Text()),
        sa.column("ownership", sa.Text()),
        sa.column("partitioned", sa.Boolean()),
        schema="public",
    )
    op.bulk_insert(
        manifest,
        [
            {
                "manifest_version": VERSION,
                "table_name": table,
                "ownership": ownership(table),
                "partitioned": table in GAME_TABLES,
            }
            for table in sorted(CATALOG | SHARED | set(GAME_TABLES) | set(CONTROL_TABLES))
        ],
    )
    for statement in _statements():
        op.execute(statement)


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    # Hold all table locks before checking: concurrent writes cannot turn an empty
    # downgrade into implicit deletion. No CASCADE; unknown dependencies block it.
    checked = [f"game_data_v2.{name}" for name in GAME_TABLES] + [
        f"public.{name}" for name in CONTROL_TABLES if name != "game_storage_table_manifest"
    ]
    op.execute("LOCK TABLE " + ", ".join(checked) + " IN ACCESS EXCLUSIVE MODE")
    for table in checked:
        op.execute(f"""DO $guard$ BEGIN
            IF EXISTS (SELECT 1 FROM {table} LIMIT 1) THEN
                RAISE EXCEPTION 'GAME_STORAGE_DOWNGRADE_NOT_EMPTY: {table}';
            END IF;
        END $guard$""")
    for statement in reversed(_statements()):
        if statement.startswith("ALTER TABLE "):
            prefix, suffix = statement.split(" ADD CONSTRAINT ", 1)
            constraint = suffix.split(" ", 1)[0]
            op.execute(f"{prefix} DROP CONSTRAINT {constraint}")
    for table in reversed(GAME_TABLES):
        op.drop_table(table, schema="game_data_v2")
    op.execute("DROP SCHEMA game_data_v2")
    for table in reversed(CONTROL_TABLES):
        op.drop_table(table, schema="public")
    for table in ("symbols", "rules_versions", "jobs"):
        op.drop_constraint(f"uq_v2_{table}_game_id_id", table, type_="unique", schema="public")
