"""Persist additive v2 virtual-geometry contracts without a read cutover.

Revision ID: 0084_additive_virtual_geometry_contracts
Revises: 0083_image_geometry_rollout_backfill_job_type
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0084_additive_virtual_geometry_contracts"
down_revision: str | Sequence[str] | None = "0083_image_geometry_rollout_backfill_job_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SHA256 = r"'^[0-9a-f]{64}$'"
_OUTCOMES = "'unassigned','unknown','unreadable','grid_issue','requires_review','verified_symbol'"


def _add_not_valid_check(table: str, name: str, expression: str) -> None:
    op.execute(f'ALTER TABLE "{table}" ADD CONSTRAINT "{name}" CHECK ({expression}) NOT VALID')


def upgrade() -> None:
    _extend_source_geometry_revisions()
    _extend_rollout_validation_binding()
    _extend_cell_observations()
    _extend_symbol_review_cells()
    _extend_symbol_review_events()
    _extend_verified_training_cells()


def downgrade() -> None:
    # Once v2 values are written, disabling dual-read/write is the supported
    # rollback.  Dropping the columns would destroy identities and outcomes.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM image_source_geometry_revisions
            WHERE topology_fingerprint_sha256 IS NOT NULL
               OR sequence_attestation_checksum_sha256 IS NOT NULL
            LIMIT 1
          ) OR EXISTS (
            SELECT 1 FROM cell_observations
            WHERE logical_cell_key_v2 IS NOT NULL OR render_identity_v2_sha256 IS NOT NULL
            LIMIT 1
          ) OR EXISTS (
            SELECT 1 FROM image_symbol_review_cells
            WHERE logical_cell_key_v2 IS NOT NULL OR verification_outcome IS NOT NULL
            LIMIT 1
          ) OR EXISTS (
            SELECT 1 FROM image_symbol_review_events
            WHERE logical_cell_key_v2 IS NOT NULL OR verification_outcome IS NOT NULL
            LIMIT 1
          ) OR EXISTS (
            SELECT 1 FROM verified_training_cohort_cells
            WHERE logical_cell_key_v2 IS NOT NULL OR render_identity_v2_sha256 IS NOT NULL
            LIMIT 1
          ) THEN
            RAISE EXCEPTION '0084 downgrade blocked: additive v2 provenance exists';
          END IF;
        END $$
        """
    )
    _drop_verified_training_cells()
    _drop_symbol_review_events()
    _drop_symbol_review_cells()
    _drop_cell_observations()
    _drop_rollout_validation_binding()
    _drop_source_geometry_revisions()


def _extend_source_geometry_revisions() -> None:
    table = "image_source_geometry_revisions"
    op.add_column(table, sa.Column("topology_fingerprint_sha256", sa.String(64)))
    op.add_column(table, sa.Column("sequence_attestation_schema_version", sa.String(80)))
    op.add_column(table, sa.Column("sequence_attestation_checksum_sha256", sa.String(64)))
    _add_not_valid_check(
        table,
        "ck_image_source_geometry_revisions_v2_contracts",
        "(topology_fingerprint_sha256 IS NULL "
        "AND sequence_attestation_schema_version IS NULL "
        "AND sequence_attestation_checksum_sha256 IS NULL) OR "
        f"(topology_fingerprint_sha256 ~ {_SHA256} "
        "AND length(btrim(sequence_attestation_schema_version)) > 0 "
        f"AND sequence_attestation_checksum_sha256 ~ {_SHA256})",
    )


def _extend_rollout_validation_binding() -> None:
    table = "image_geometry_rollout_states"
    op.add_column(table, sa.Column("validation_rollout_revision", sa.Integer()))
    op.add_column(table, sa.Column("validation_input_checksum_sha256", sa.String(64)))
    op.add_column(table, sa.Column("validation_job_id", sa.Uuid()))
    op.create_foreign_key(
        "fk_image_geometry_rollout_states_validation_job",
        table,
        "jobs",
        ["validation_job_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    _add_not_valid_check(
        table,
        "ck_image_geometry_rollout_states_validation_binding",
        "(validation_rollout_revision IS NULL "
        "AND validation_input_checksum_sha256 IS NULL "
        "AND validation_job_id IS NULL) OR "
        "(validation_rollout_revision >= 0 "
        f"AND validation_input_checksum_sha256 ~ {_SHA256} "
        "AND validation_job_id IS NOT NULL)",
    )


def _extend_cell_observations() -> None:
    table = "cell_observations"
    op.add_column(table, sa.Column("logical_cell_key_v2", sa.String(64)))
    op.add_column(table, sa.Column("render_identity_v2_sha256", sa.String(64)))
    _add_identity_check(table, "ck_cell_observations_v2_identity")


def _extend_symbol_review_cells() -> None:
    table = "image_symbol_review_cells"
    op.add_column(table, sa.Column("logical_cell_key_v2", sa.String(64)))
    op.add_column(table, sa.Column("render_identity_v2_sha256", sa.String(64)))
    op.add_column(table, sa.Column("verification_outcome", sa.String(30)))
    op.add_column(table, sa.Column("verified_symbol_id_v2", sa.Uuid()))
    op.create_foreign_key(
        "fk_image_symbol_review_cells_verified_symbol_v2",
        table,
        "symbols",
        ["verified_symbol_id_v2"],
        ["id"],
        ondelete="RESTRICT",
    )
    _add_identity_check(table, "ck_image_symbol_review_cells_v2_identity")
    _add_not_valid_check(
        table,
        "ck_image_symbol_review_cells_verification_outcome",
        "(verification_outcome IS NULL AND verified_symbol_id_v2 IS NULL) OR "
        f"(verification_outcome IN ({_OUTCOMES}) AND "
        "((verification_outcome = 'verified_symbol' AND verified_symbol_id_v2 IS NOT NULL) OR "
        "(verification_outcome <> 'verified_symbol' AND verified_symbol_id_v2 IS NULL)))",
    )


def _extend_symbol_review_events() -> None:
    table = "image_symbol_review_events"
    for column in (
        sa.Column("previous_logical_cell_key_v2", sa.String(64)),
        sa.Column("logical_cell_key_v2", sa.String(64)),
        sa.Column("previous_render_identity_v2_sha256", sa.String(64)),
        sa.Column("render_identity_v2_sha256", sa.String(64)),
        sa.Column("previous_verification_outcome", sa.String(30)),
        sa.Column("verification_outcome", sa.String(30)),
        sa.Column("previous_verified_symbol_id_v2", sa.Uuid()),
        sa.Column("verified_symbol_id_v2", sa.Uuid()),
    ):
        op.add_column(table, column)
    op.create_foreign_key(
        "fk_image_symbol_review_events_previous_verified_symbol_v2",
        table,
        "symbols",
        ["previous_verified_symbol_id_v2"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_image_symbol_review_events_verified_symbol_v2",
        table,
        "symbols",
        ["verified_symbol_id_v2"],
        ["id"],
        ondelete="RESTRICT",
    )
    _add_not_valid_check(
        table,
        "ck_image_symbol_review_events_v2_identity",
        _optional_identity_pair("previous_") + " AND " + _optional_identity_pair(""),
    )
    _add_not_valid_check(
        table,
        "ck_image_symbol_review_events_verification_outcome",
        _optional_outcome("previous_") + " AND " + _optional_outcome(""),
    )


def _extend_verified_training_cells() -> None:
    table = "verified_training_cohort_cells"
    op.add_column(table, sa.Column("logical_cell_key_v2", sa.String(64)))
    op.add_column(table, sa.Column("render_identity_v2_sha256", sa.String(64)))
    _add_identity_check(table, "ck_verified_training_cohort_cells_v2_identity")


def _add_identity_check(table: str, name: str) -> None:
    _add_not_valid_check(table, name, _optional_identity_pair(""))


def _optional_identity_pair(prefix: str) -> str:
    logical = f"{prefix}logical_cell_key_v2"
    render = f"{prefix}render_identity_v2_sha256"
    return (
        f"(({logical} IS NULL AND {render} IS NULL) OR "
        f"({logical} ~ {_SHA256} AND {render} ~ {_SHA256}))"
    )


def _optional_outcome(prefix: str) -> str:
    outcome = f"{prefix}verification_outcome"
    assigned = f"{prefix}verified_symbol_id_v2"
    return (
        f"(({outcome} IS NULL AND {assigned} IS NULL) OR "
        f"({outcome} IN ({_OUTCOMES}) AND "
        f"(({outcome} = 'verified_symbol' AND {assigned} IS NOT NULL) OR "
        f"({outcome} <> 'verified_symbol' AND {assigned} IS NULL))))"
    )


def _drop_source_geometry_revisions() -> None:
    table = "image_source_geometry_revisions"
    op.drop_constraint("ck_image_source_geometry_revisions_v2_contracts", table, type_="check")
    for column in (
        "sequence_attestation_checksum_sha256",
        "sequence_attestation_schema_version",
        "topology_fingerprint_sha256",
    ):
        op.drop_column(table, column)


def _drop_rollout_validation_binding() -> None:
    table = "image_geometry_rollout_states"
    op.drop_constraint("ck_image_geometry_rollout_states_validation_binding", table, type_="check")
    op.drop_constraint("fk_image_geometry_rollout_states_validation_job", table, type_="foreignkey")
    for column in (
        "validation_job_id",
        "validation_input_checksum_sha256",
        "validation_rollout_revision",
    ):
        op.drop_column(table, column)


def _drop_cell_observations() -> None:
    _drop_identity_columns("cell_observations", "ck_cell_observations_v2_identity")


def _drop_symbol_review_cells() -> None:
    table = "image_symbol_review_cells"
    op.drop_constraint("ck_image_symbol_review_cells_verification_outcome", table, type_="check")
    op.drop_constraint("fk_image_symbol_review_cells_verified_symbol_v2", table, type_="foreignkey")
    op.drop_column(table, "verified_symbol_id_v2")
    op.drop_column(table, "verification_outcome")
    _drop_identity_columns(table, "ck_image_symbol_review_cells_v2_identity")


def _drop_symbol_review_events() -> None:
    table = "image_symbol_review_events"
    op.drop_constraint("ck_image_symbol_review_events_verification_outcome", table, type_="check")
    op.drop_constraint("ck_image_symbol_review_events_v2_identity", table, type_="check")
    op.drop_constraint(
        "fk_image_symbol_review_events_verified_symbol_v2", table, type_="foreignkey"
    )
    op.drop_constraint(
        "fk_image_symbol_review_events_previous_verified_symbol_v2",
        table,
        type_="foreignkey",
    )
    for column in (
        "verified_symbol_id_v2",
        "previous_verified_symbol_id_v2",
        "verification_outcome",
        "previous_verification_outcome",
        "render_identity_v2_sha256",
        "previous_render_identity_v2_sha256",
        "logical_cell_key_v2",
        "previous_logical_cell_key_v2",
    ):
        op.drop_column(table, column)


def _drop_verified_training_cells() -> None:
    _drop_identity_columns(
        "verified_training_cohort_cells",
        "ck_verified_training_cohort_cells_v2_identity",
    )


def _drop_identity_columns(table: str, constraint: str) -> None:
    op.drop_constraint(constraint, table, type_="check")
    op.drop_column(table, "render_identity_v2_sha256")
    op.drop_column(table, "logical_cell_key_v2")
