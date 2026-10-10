"""Add reviewed V7 delivery metadata; keep every activation gate blocked.

Revision ID: 0144_v7_reviewed_delivery
Revises: 0143_merge_share_grid_shadow
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0144_v7_reviewed_delivery"
down_revision: str | Sequence[str] | None = "0143_merge_share_grid_shadow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEMA = "public"
_RANGES = "semi_automatic_image_selection_ranges"
_GATE = "semi_automatic_selection_v7_activation_gate"
_SOURCES = "semi_automatic_selection_v7_source_observations"
_OPERATIONS = "semi_automatic_selection_v7_output_operations"
_RANGE_COLUMNS = (
    ("v7_review", postgresql.JSONB()),
    ("v7_projection_fingerprint", sa.String(64)),
    ("v7_confirmed_range_start", sa.BigInteger()),
    ("v7_confirmed_range_end", sa.BigInteger()),
    ("v7_output_owner_operation_id", sa.Uuid()),
    ("v7_output_generation", sa.BigInteger()),
)
_GATE_NULLABLE_COLUMNS = (
    ("pilot_geometry_family_id", sa.String(200)),
    ("pilot_source_game_ref", sa.String(200)),
    ("pilot_profile_fingerprint", sa.String(64)),
    ("pilot_observer_fingerprint", sa.String(64)),
    ("pilot_ocr_model_fingerprint", sa.String(64)),
    ("pilot_acceptance_receipt_fingerprint", sa.String(64)),
    ("pilot_accepted_at", sa.DateTime(timezone=True)),
    ("pilot_accepted_by", sa.String(200)),
)


def upgrade() -> None:
    for name, column_type in _RANGE_COLUMNS:
        op.add_column(_RANGES, sa.Column(name, column_type, nullable=True), schema=_SCHEMA)
    op.drop_constraint(
        "ck_semi_automatic_selection_ranges_status", _RANGES, type_="check", schema=_SCHEMA
    )
    op.create_check_constraint(
        "ck_semi_automatic_selection_ranges_status",
        _RANGES,
        "status IN ('missing', 'proposed', 'auto_selected', 'output_synced', 'conflict')",
        schema=_SCHEMA,
    )
    op.create_check_constraint(
        "ck_v7_range_output_identity",
        _RANGES,
        "(v7_output_generation IS NULL OR v7_output_generation >= 0) AND "
        "((v7_confirmed_range_start IS NULL AND v7_confirmed_range_end IS NULL) OR "
        "(v7_confirmed_range_start >= range_start AND v7_confirmed_range_end <= range_end AND "
        "v7_confirmed_range_end >= v7_confirmed_range_start)) AND "
        "(v7_projection_fingerprint IS NULL OR v7_projection_fingerprint ~ '^[0-9a-f]{64}$')",
        schema=_SCHEMA,
    )
    op.add_column(
        _GATE,
        sa.Column("pilot_status", sa.String(16), nullable=False, server_default="blocked"),
        schema=_SCHEMA,
    )
    op.add_column(
        _GATE,
        sa.Column("pilot_generation", sa.BigInteger(), nullable=False, server_default="0"),
        schema=_SCHEMA,
    )
    op.add_column(
        _GATE,
        sa.Column("pilot_mode", sa.String(32), nullable=False, server_default="semi_automatic"),
        schema=_SCHEMA,
    )
    op.add_column(
        _GATE,
        sa.Column(
            "pilot_source_bindings",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        schema=_SCHEMA,
    )
    for name, gate_column_type in _GATE_NULLABLE_COLUMNS:
        op.add_column(_GATE, sa.Column(name, gate_column_type, nullable=True), schema=_SCHEMA)
    op.create_check_constraint(
        "ck_v7_pilot_gate_policy",
        _GATE,
        "pilot_status IN ('blocked', 'active') AND pilot_generation >= 0 AND "
        "pilot_mode = 'semi_automatic' AND jsonb_typeof(pilot_source_bindings) = 'array'",
        schema=_SCHEMA,
    )
    op.create_check_constraint(
        "ck_v7_pilot_gate_active_identity",
        _GATE,
        "pilot_status <> 'active' OR (pilot_geometry_family_id IS NOT NULL AND "
        "pilot_source_game_ref IS NOT NULL AND pilot_profile_fingerprint IS NOT NULL AND "
        "pilot_observer_fingerprint IS NOT NULL AND pilot_ocr_model_fingerprint IS NOT NULL AND "
        "pilot_acceptance_receipt_fingerprint IS NOT NULL AND pilot_accepted_at IS NOT NULL AND "
        "pilot_accepted_by IS NOT NULL AND jsonb_array_length(pilot_source_bindings) > 0)",
        schema=_SCHEMA,
    )
    op.create_table(
        _SOURCES,
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("source_index", sa.BigInteger(), nullable=False),
        sa.Column("source_checksum_sha256", sa.String(64), nullable=False),
        sa.Column("payload_fingerprint", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("run_id", "source_index"),
        sa.ForeignKeyConstraint(
            ["run_id"], [f"{_SCHEMA}.semi_automatic_image_selection_runs.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint("source_index >= 0", name="ck_v7_source_observation_index"),
        sa.CheckConstraint(
            "source_checksum_sha256 ~ '^[0-9a-f]{64}$' AND "
            "payload_fingerprint ~ '^[0-9a-f]{64}$' AND jsonb_typeof(payload) = 'object'",
            name="ck_v7_source_observation_payload",
        ),
        schema=_SCHEMA,
    )
    op.create_table(
        _OPERATIONS,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("range_id", sa.Uuid(), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("request_payload", postgresql.JSONB(), nullable=False),
        sa.Column("context_payload", postgresql.JSONB(), nullable=False),
        sa.Column("decision_generation", sa.BigInteger(), nullable=False),
        sa.Column("reserved_revision", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("receipt", postgresql.JSONB(), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], [f"{_SCHEMA}.semi_automatic_image_selection_runs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["range_id"], [f"{_SCHEMA}.{_RANGES}.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "state IN ('reserved', 'recovery_required', 'committed', 'conflict', 'failed') AND "
            "decision_generation >= 0 AND reserved_revision >= 0",
            name="ck_v7_output_operation_state",
        ),
        sa.CheckConstraint(
            "request_fingerprint ~ '^[0-9a-f]{64}$' AND jsonb_typeof(request_payload) = 'object' "
            "AND jsonb_typeof(context_payload) = 'object'",
            name="ck_v7_output_operation_payload",
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        "uq_v7_output_operation_pending_run",
        _OPERATIONS,
        ["run_id"],
        unique=True,
        postgresql_where=sa.text("state IN ('reserved', 'recovery_required')"),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_v7_output_operation_range_created",
        _OPERATIONS,
        ["range_id", "created_at"],
        schema=_SCHEMA,
    )


def downgrade() -> None:
    op.execute(
        f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM {_SCHEMA}.{_OPERATIONS}) OR "
        f"EXISTS (SELECT 1 FROM {_SCHEMA}.{_SOURCES}) OR "
        f"EXISTS (SELECT 1 FROM {_SCHEMA}.{_RANGES} WHERE v7_review IS NOT NULL) OR "
        f"EXISTS (SELECT 1 FROM {_SCHEMA}.{_GATE} WHERE pilot_generation <> 0 OR "
        "pilot_status <> 'blocked' OR pilot_acceptance_receipt_fingerprint IS NOT NULL) "
        "THEN RAISE EXCEPTION 'Cannot discard V7 delivery history'; END IF; END $$"
    )
    op.drop_table(_OPERATIONS, schema=_SCHEMA)
    op.drop_table(_SOURCES, schema=_SCHEMA)
    op.drop_constraint("ck_v7_pilot_gate_active_identity", _GATE, type_="check", schema=_SCHEMA)
    op.drop_constraint("ck_v7_pilot_gate_policy", _GATE, type_="check", schema=_SCHEMA)
    for name, _ in reversed(_GATE_NULLABLE_COLUMNS):
        op.drop_column(_GATE, name, schema=_SCHEMA)
    for name in ("pilot_source_bindings", "pilot_mode", "pilot_generation", "pilot_status"):
        op.drop_column(_GATE, name, schema=_SCHEMA)
    op.drop_constraint("ck_v7_range_output_identity", _RANGES, type_="check", schema=_SCHEMA)
    op.drop_constraint(
        "ck_semi_automatic_selection_ranges_status", _RANGES, type_="check", schema=_SCHEMA
    )
    op.create_check_constraint(
        "ck_semi_automatic_selection_ranges_status",
        _RANGES,
        "status IN ('missing', 'auto_selected', 'output_synced', 'conflict')",
        schema=_SCHEMA,
    )
    for name, _ in reversed(_RANGE_COLUMNS):
        op.drop_column(_RANGES, name, schema=_SCHEMA)
