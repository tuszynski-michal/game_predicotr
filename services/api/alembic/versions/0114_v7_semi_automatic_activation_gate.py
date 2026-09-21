"""Add V7 semi-automatic selection metadata and a blocked activation gate.

Revision ID: 0114_v7_semi_automatic_activation_gate
Revises: 0113_reconcile_browser_staging_board_import_status
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0114_v7_semi_automatic_activation_gate"
down_revision: str | Sequence[str] | None = "0113_reconcile_browser_staging_board_import_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RUN_TABLE = "semi_automatic_image_selection_runs"
_WORKFLOW_CONSTRAINT = "ck_semi_automatic_selection_runs_workflow_mode"
_CHECKSUM_CONSTRAINT = "ck_semi_automatic_selection_runs_checksums"
_JSON_CONSTRAINT = "ck_semi_automatic_selection_runs_json"


def upgrade() -> None:
    op.add_column(_RUN_TABLE, sa.Column("v7_configuration", postgresql.JSONB(), nullable=True))
    op.add_column(
        _RUN_TABLE,
        sa.Column("v7_calibration_fingerprint", sa.String(length=64), nullable=True),
    )
    op.drop_constraint(_WORKFLOW_CONSTRAINT, _RUN_TABLE, type_="check")
    op.create_check_constraint(
        _WORKFLOW_CONSTRAINT,
        _RUN_TABLE,
        "workflow_mode IN ('selection', 'filename_verification', 'v7_selection')",
    )
    op.drop_constraint(_CHECKSUM_CONSTRAINT, _RUN_TABLE, type_="check")
    op.create_check_constraint(
        _CHECKSUM_CONSTRAINT,
        _RUN_TABLE,
        "source_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$' AND "
        "source_fingerprint ~ '^[0-9a-f]{64}$' AND "
        "expected_ranges_fingerprint ~ '^[0-9a-f]{64}$' AND "
        "recognizer_fingerprint ~ '^[0-9a-f]{64}$' AND "
        "grouping_policy_fingerprint ~ '^[0-9a-f]{64}$' AND "
        "identity_key ~ '^[0-9a-f]{64}$' AND "
        "(diagnostics_checksum_sha256 IS NULL OR "
        "diagnostics_checksum_sha256 ~ '^[0-9a-f]{64}$') AND "
        "(v7_calibration_fingerprint IS NULL OR "
        "v7_calibration_fingerprint ~ '^[0-9a-f]{64}$')",
    )
    op.drop_constraint(_JSON_CONSTRAINT, _RUN_TABLE, type_="check")
    op.create_check_constraint(
        _JSON_CONSTRAINT,
        _RUN_TABLE,
        "jsonb_typeof(checkpoint) = 'object' AND jsonb_typeof(counters) = 'object' AND "
        "(v7_configuration IS NULL OR jsonb_typeof(v7_configuration) = 'object')",
    )
    op.create_table(
        "semi_automatic_selection_v7_activation_gate",
        sa.Column("singleton", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "singleton = TRUE", name="ck_semi_automatic_v7_activation_gate_singleton"
        ),
        sa.CheckConstraint(
            "status IN ('blocked', 'active')",
            name="ck_semi_automatic_v7_activation_gate_status",
        ),
        sa.CheckConstraint(
            "generation >= 0", name="ck_semi_automatic_v7_activation_gate_generation"
        ),
        sa.PrimaryKeyConstraint("singleton"),
    )
    op.execute(
        "INSERT INTO semi_automatic_selection_v7_activation_gate "
        "(singleton, status, generation, accepted_at, accepted_by, created_at, updated_at) "
        "VALUES (TRUE, 'blocked', 0, NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM semi_automatic_image_selection_runs "
        "WHERE workflow_mode = 'v7_selection') THEN "
        "RAISE EXCEPTION 'Cannot downgrade while V7 selection runs exist'; "
        "END IF; END $$"
    )
    op.drop_table("semi_automatic_selection_v7_activation_gate")
    op.drop_constraint(_JSON_CONSTRAINT, _RUN_TABLE, type_="check")
    op.create_check_constraint(
        _JSON_CONSTRAINT,
        _RUN_TABLE,
        "jsonb_typeof(checkpoint) = 'object' AND jsonb_typeof(counters) = 'object'",
    )
    op.drop_constraint(_CHECKSUM_CONSTRAINT, _RUN_TABLE, type_="check")
    op.create_check_constraint(
        _CHECKSUM_CONSTRAINT,
        _RUN_TABLE,
        "source_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$' AND "
        "source_fingerprint ~ '^[0-9a-f]{64}$' AND "
        "expected_ranges_fingerprint ~ '^[0-9a-f]{64}$' AND "
        "recognizer_fingerprint ~ '^[0-9a-f]{64}$' AND "
        "grouping_policy_fingerprint ~ '^[0-9a-f]{64}$' AND "
        "identity_key ~ '^[0-9a-f]{64}$' AND "
        "(diagnostics_checksum_sha256 IS NULL OR diagnostics_checksum_sha256 ~ '^[0-9a-f]{64}$')",
    )
    op.drop_constraint(_WORKFLOW_CONSTRAINT, _RUN_TABLE, type_="check")
    op.create_check_constraint(
        _WORKFLOW_CONSTRAINT,
        _RUN_TABLE,
        "workflow_mode IN ('selection', 'filename_verification')",
    )
    op.drop_column(_RUN_TABLE, "v7_calibration_fingerprint")
    op.drop_column(_RUN_TABLE, "v7_configuration")
