"""Add durable symbol-model candidate gate artifacts.

Revision ID: 0036_symbol_model_candidate_gate
Revises: 0035_symbol_model_training_jobs
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0036_symbol_model_candidate_gate"
down_revision: str | Sequence[str] | None = "0035_symbol_model_training_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_symbol_model_iterations_status",
        "symbol_model_iterations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_symbol_model_iterations_status",
        "symbol_model_iterations",
        "status IN ('created','dataset_build','training','trained','evaluating',"
        "'candidate_ready','rejected','failed','cancelled')",
    )
    op.add_column(
        "symbol_model_iterations",
        sa.Column("gate_configuration_fingerprint", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "symbol_model_iterations",
        sa.Column("gate_configuration_payload", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "symbol_model_iterations",
        sa.Column("candidate_manifest_checksum_sha256", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "symbol_model_iterations",
        sa.Column("candidate_manifest_relative_path", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "symbol_model_iterations",
        sa.Column("gate_report_checksum_sha256", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "symbol_model_iterations",
        sa.Column("gate_report_relative_path", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "symbol_model_iterations",
        sa.Column("gate_metrics", postgresql.JSONB(), server_default="{}", nullable=False),
    )
    op.add_column(
        "symbol_model_iterations",
        sa.Column(
            "rejection_reasons",
            postgresql.ARRAY(sa.String(length=100)),
            server_default="{}",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_symbol_model_iterations_gate_sha256",
        "symbol_model_iterations",
        "(gate_configuration_fingerprint IS NULL "
        "OR gate_configuration_fingerprint ~ '^[0-9a-f]{64}$') "
        "AND (candidate_manifest_checksum_sha256 IS NULL "
        "OR candidate_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$') "
        "AND (gate_report_checksum_sha256 IS NULL "
        "OR gate_report_checksum_sha256 ~ '^[0-9a-f]{64}$')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_symbol_model_iterations_gate_sha256",
        "symbol_model_iterations",
        type_="check",
    )
    for column in (
        "rejection_reasons",
        "gate_metrics",
        "gate_report_relative_path",
        "gate_report_checksum_sha256",
        "candidate_manifest_relative_path",
        "candidate_manifest_checksum_sha256",
        "gate_configuration_payload",
        "gate_configuration_fingerprint",
    ):
        op.drop_column("symbol_model_iterations", column)
    op.drop_constraint(
        "ck_symbol_model_iterations_status",
        "symbol_model_iterations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_symbol_model_iterations_status",
        "symbol_model_iterations",
        "status IN ('created','dataset_build','training','trained','failed','cancelled')",
    )
