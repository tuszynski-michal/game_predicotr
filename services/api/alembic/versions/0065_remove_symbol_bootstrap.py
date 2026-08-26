"""Remove the retired automatic symbol-catalog bootstrap.

Revision ID: 0065_remove_symbol_bootstrap
Revises: 0064_symbol_reference_images
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0065_remove_symbol_bootstrap"
down_revision: str | Sequence[str] | None = "0064_symbol_reference_images"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_symbol_bootstrap_game_created", table_name="symbol_bootstrap_runs")
    op.drop_table("symbol_bootstrap_runs")


def downgrade() -> None:
    # Historical downgrade restores the schema only. Existing manual symbols
    # remain untouched; no obsolete bootstrap runs are reconstructed.
    op.execute(
        """
        CREATE TABLE symbol_bootstrap_runs (
          id UUID PRIMARY KEY,
          game_id UUID NOT NULL REFERENCES games(id) ON DELETE RESTRICT,
          expected_symbol_count SMALLINT NOT NULL,
          detected_cluster_count SMALLINT NOT NULL,
          source_state_sha256 VARCHAR(64) NOT NULL,
          status VARCHAR(20) NOT NULL,
          candidates JSONB NOT NULL,
          resolution JSONB NULL,
          created_by VARCHAR(200) NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          applied_at TIMESTAMPTZ NULL,
          CONSTRAINT ck_symbol_bootstrap_expected_count_range
            CHECK (expected_symbol_count BETWEEN 1 AND 32767),
          CONSTRAINT ck_symbol_bootstrap_detected_count_positive
            CHECK (detected_cluster_count > 0),
          CONSTRAINT ck_symbol_bootstrap_source_sha256
            CHECK (source_state_sha256 ~ '^[0-9a-f]{64}$'),
          CONSTRAINT ck_symbol_bootstrap_status
            CHECK (status IN ('ready', 'conflict', 'applied')),
          CONSTRAINT ck_symbol_bootstrap_applied_state CHECK (
            (status = 'applied' AND resolution IS NOT NULL AND applied_at IS NOT NULL)
            OR (status <> 'applied' AND resolution IS NULL AND applied_at IS NULL)
          ),
          CONSTRAINT uq_symbol_bootstrap_source_expectation UNIQUE
            (game_id, source_state_sha256, expected_symbol_count)
        )
        """
    )
    op.create_index(
        "ix_symbol_bootstrap_game_created",
        "symbol_bootstrap_runs",
        ["game_id", "created_at"],
    )
