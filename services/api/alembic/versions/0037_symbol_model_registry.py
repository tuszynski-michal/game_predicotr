"""Add append-only symbol-model activation history.

Revision ID: 0037_symbol_model_registry
Revises: 0036_symbol_model_candidate_gate
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0037_symbol_model_registry"
down_revision: str | Sequence[str] | None = "0036_symbol_model_candidate_gate"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "game_symbol_model_activations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_iteration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("previous_model_iteration_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("activation_number", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('activate','rollback')",
            name="ck_game_symbol_model_activations_action",
        ),
        sa.CheckConstraint(
            "activation_number > 0 AND btrim(actor) <> '' AND command_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_game_symbol_model_activations_values",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["model_iteration_id"], ["symbol_model_iterations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["previous_model_iteration_id"],
            ["symbol_model_iterations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "game_id",
            "idempotency_key",
            name="uq_game_symbol_model_activations_idempotency",
        ),
        sa.UniqueConstraint(
            "game_id",
            "activation_number",
            name="uq_game_symbol_model_activations_number",
        ),
    )
    op.create_index(
        "ix_game_symbol_model_activations_current",
        "game_symbol_model_activations",
        ["game_id", "activation_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_game_symbol_model_activations_current",
        table_name="game_symbol_model_activations",
    )
    op.drop_table("game_symbol_model_activations")
