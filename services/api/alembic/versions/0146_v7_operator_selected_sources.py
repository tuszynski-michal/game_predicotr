"""Separate reviewed model acceptance from the operator-selected run source.

Revision ID: 0146_v7_operator_sources
Revises: 0145_v7_pilot_acceptances
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0146_v7_operator_sources"
down_revision: str | Sequence[str] | None = "0145_v7_pilot_acceptances"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GATE = "semi_automatic_selection_v7_activation_gate"
_PINS = (
    "pilot_status <> 'active' OR (pilot_geometry_family_id IS NOT NULL AND "
    "pilot_profile_fingerprint IS NOT NULL AND pilot_observer_fingerprint IS NOT NULL AND "
    "pilot_ocr_model_fingerprint IS NOT NULL AND "
    "pilot_acceptance_receipt_fingerprint IS NOT NULL AND pilot_accepted_at IS NOT NULL AND "
    "pilot_accepted_by IS NOT NULL AND "
)


def upgrade() -> None:
    op.add_column(
        _GATE,
        sa.Column(
            "pilot_source_policy", sa.String(40), nullable=False, server_default="exact_sources"
        ),
        schema="public",
    )
    op.create_check_constraint(
        "ck_v7_pilot_gate_source_policy",
        _GATE,
        "pilot_source_policy IN ('exact_sources', 'operator_selected_local_folder')",
        schema="public",
    )
    op.drop_constraint("ck_v7_pilot_gate_active_identity", _GATE, type_="check", schema="public")
    op.create_check_constraint(
        "ck_v7_pilot_gate_active_identity",
        _GATE,
        _PINS + "((pilot_source_policy = 'exact_sources' AND pilot_source_game_ref IS NOT NULL AND "
        "jsonb_array_length(pilot_source_bindings) > 0) OR "
        "(pilot_source_policy = 'operator_selected_local_folder' AND "
        "pilot_source_game_ref IS NULL AND jsonb_array_length(pilot_source_bindings) = 0)))",
        schema="public",
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM public."
        + _GATE
        + " WHERE pilot_status = 'active' AND "
        "pilot_source_policy = 'operator_selected_local_folder') THEN "
        "RAISE EXCEPTION 'Cannot downgrade an active operator-selected V7 gate'; "
        "END IF; END $$"
    )
    op.drop_constraint("ck_v7_pilot_gate_active_identity", _GATE, type_="check", schema="public")
    op.drop_constraint("ck_v7_pilot_gate_source_policy", _GATE, type_="check", schema="public")
    op.create_check_constraint(
        "ck_v7_pilot_gate_active_identity",
        _GATE,
        _PINS
        + "pilot_source_game_ref IS NOT NULL AND jsonb_array_length(pilot_source_bindings) > 0)",
        schema="public",
    )
    op.drop_column(_GATE, "pilot_source_policy", schema="public")
