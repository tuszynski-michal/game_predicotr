"""Persist remote manual image-selection state and append-only journals.

Revision ID: 0056_remote_manual_selection_persistence
Revises: 0055_board_cell_geometry_pipeline_stage
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0056_remote_manual_selection_persistence"
down_revision: str | Sequence[str] | None = "0055_board_cell_geometry_pipeline_stage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "remote_manual_selection_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("base_binding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("host_base_path", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("revision", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("code_salt", sa.LargeBinary(length=16), nullable=True),
        sa.Column("code_hash", sa.LargeBinary(length=32), nullable=True),
        sa.Column("token_hash", sa.LargeBinary(length=32), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_attempts", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("writer_client_instance_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("writer_lease_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("writer_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft','active','completed','expired','revoked')",
            name="ck_rms_sessions_status",
        ),
        sa.CheckConstraint(
            "revision >= 0 AND failed_attempts BETWEEN 0 AND 5",
            name="ck_rms_sessions_counters",
        ),
        sa.CheckConstraint(
            "length(btrim(host_base_path)) > 0 AND length(btrim(display_name)) > 0",
            name="ck_rms_sessions_names",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at AND expires_at > created_at",
            name="ck_rms_sessions_timestamps",
        ),
        sa.CheckConstraint(
            "(code_salt IS NULL AND code_hash IS NULL) OR "
            "(code_salt IS NOT NULL AND code_hash IS NOT NULL "
            "AND octet_length(code_salt) = 16 AND octet_length(code_hash) = 32)",
            name="ck_rms_sessions_code_hash",
        ),
        sa.CheckConstraint(
            "(token_hash IS NULL AND token_expires_at IS NULL) OR "
            "(token_hash IS NOT NULL AND octet_length(token_hash) = 32 "
            "AND token_expires_at IS NOT NULL)",
            name="ck_rms_sessions_token_hash",
        ),
        sa.CheckConstraint(
            "(writer_client_instance_id IS NULL AND writer_lease_token IS NULL "
            "AND writer_lease_expires_at IS NULL) OR "
            "(writer_client_instance_id IS NOT NULL AND writer_lease_token IS NOT NULL "
            "AND writer_lease_expires_at IS NOT NULL)",
            name="ck_rms_sessions_writer_lease",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rms_sessions"),
        sa.UniqueConstraint("id", "base_binding_id", name="uq_rms_sessions_binding_scope"),
    )
    op.create_index(
        "ix_rms_sessions_status_expiry",
        "remote_manual_selection_sessions",
        ["status", "expires_at", "id"],
    )

    op.create_table(
        "remote_manual_selection_collections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("revision", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("status IN ('active','completed')", name="ck_rms_collections_status"),
        sa.CheckConstraint(
            "revision >= 0 AND length(btrim(name)) > 0 AND length(btrim(normalized_name)) > 0",
            name="ck_rms_collections_values",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["remote_manual_selection_sessions.id"],
            name="fk_rms_collections_session",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rms_collections"),
        sa.UniqueConstraint(
            "session_id", "normalized_name", name="uq_rms_collections_session_name"
        ),
        sa.UniqueConstraint(
            "id", "session_id", "normalized_name", name="uq_rms_collections_scope_name"
        ),
    )
    op.create_index(
        "ix_rms_collections_session_status",
        "remote_manual_selection_collections",
        ["session_id", "status", "id"],
    )

    op.create_table(
        "remote_manual_selection_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("base_binding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("normalized_collection_name", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column("source_manifest_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("first_layout", sa.BigInteger(), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("cursor_index", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("server_revision", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("last_client_sequence", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("final_manifest_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("total_file_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("selected_file_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("transferred_file_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('draft','indexing','active','finalizing','completed','failed','abandoned')",
            name="ck_rms_batches_status",
        ),
        sa.CheckConstraint(
            "direction IN ('ascending','descending')", name="ck_rms_batches_direction"
        ),
        sa.CheckConstraint(
            "source_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$' AND "
            "(final_manifest_checksum_sha256 IS NULL OR "
            "final_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$')",
            name="ck_rms_batches_checksums",
        ),
        sa.CheckConstraint(
            "first_layout > 0 AND cursor_index >= 0 AND server_revision >= 0 "
            "AND last_client_sequence >= 0 AND total_file_count >= 0 "
            "AND selected_file_count >= 0 AND transferred_file_count >= 0 "
            "AND selected_file_count <= total_file_count "
            "AND transferred_file_count <= selected_file_count",
            name="ck_rms_batches_counters",
        ),
        sa.CheckConstraint(
            "length(btrim(name)) > 0 AND length(btrim(normalized_name)) > 0 "
            "AND length(btrim(normalized_collection_name)) > 0",
            name="ck_rms_batches_names",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "base_binding_id"],
            [
                "remote_manual_selection_sessions.id",
                "remote_manual_selection_sessions.base_binding_id",
            ],
            name="fk_rms_batches_session_binding",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["collection_id", "session_id", "normalized_collection_name"],
            [
                "remote_manual_selection_collections.id",
                "remote_manual_selection_collections.session_id",
                "remote_manual_selection_collections.normalized_name",
            ],
            name="fk_rms_batches_collection_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rms_batches"),
        sa.UniqueConstraint("id", "session_id", name="uq_rms_batches_scope"),
        sa.UniqueConstraint(
            "base_binding_id",
            "normalized_collection_name",
            "normalized_name",
            name="uq_rms_batches_base_mapping",
        ),
    )
    op.create_index(
        "ix_rms_batches_session_status",
        "remote_manual_selection_batches",
        ["session_id", "status", "updated_at", "id"],
    )

    op.create_table(
        "remote_manual_selection_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_index", sa.BigInteger(), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("last_modified_ms", sa.BigInteger(), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("desired_selected", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("selection_generation", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("range_start", sa.BigInteger(), nullable=True),
        sa.Column("range_end", sa.BigInteger(), nullable=True),
        sa.Column("output_name", sa.String(length=255), nullable=True),
        sa.Column("host_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("temp_relative_path", sa.Text(), nullable=True),
        sa.Column("final_relative_path", sa.Text(), nullable=True),
        sa.Column("last_server_revision", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('discovered','unselected','selection_queued','upload_queued',"
            "'uploading','stored_temporarily','verified','materialized','synced',"
            "'deselect_pending','removed','failed','retrying')",
            name="ck_rms_files_status",
        ),
        sa.CheckConstraint(
            "source_index >= 0 AND size_bytes >= 0 AND last_modified_ms >= 0 "
            "AND selection_generation >= 0 AND last_server_revision >= 0",
            name="ck_rms_files_counters",
        ),
        sa.CheckConstraint(
            "length(relative_path) > 0 AND relative_path !~ '(^/|(^|/)\\.\\.(/|$)|\\\\)'",
            name="ck_rms_files_relative_path",
        ),
        sa.CheckConstraint(
            "(range_start IS NULL AND range_end IS NULL) OR "
            "(range_start > 0 AND range_end = range_start + 8)",
            name="ck_rms_files_range",
        ),
        sa.CheckConstraint(
            "host_checksum_sha256 IS NULL OR host_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_rms_files_checksum",
        ),
        sa.CheckConstraint(
            "status <> 'synced' OR (desired_selected AND range_start IS NOT NULL "
            "AND output_name IS NOT NULL AND host_checksum_sha256 IS NOT NULL "
            "AND final_relative_path IS NOT NULL)",
            name="ck_rms_files_synced",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id", "session_id"],
            ["remote_manual_selection_batches.id", "remote_manual_selection_batches.session_id"],
            name="fk_rms_files_batch_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rms_files"),
        sa.UniqueConstraint("id", "batch_id", "session_id", name="uq_rms_files_scope"),
        sa.UniqueConstraint("batch_id", "source_index", name="uq_rms_files_source_index"),
        sa.UniqueConstraint("batch_id", "relative_path", name="uq_rms_files_relative_path"),
    )
    op.create_index(
        "ix_rms_files_delta",
        "remote_manual_selection_files",
        ["batch_id", "last_server_revision", "source_index", "id"],
    )
    op.create_index(
        "ix_rms_files_status",
        "remote_manual_selection_files",
        ["batch_id", "status", "source_index", "id"],
    )

    op.create_table(
        "remote_manual_selection_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("client_instance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_sequence", sa.BigInteger(), nullable=False),
        sa.Column("expected_server_revision", sa.BigInteger(), nullable=False),
        sa.Column("operation_type", sa.String(length=16), nullable=False),
        sa.Column("selection_generation", sa.BigInteger(), nullable=False),
        sa.Column("range_start", sa.BigInteger(), nullable=False),
        sa.Column("range_end", sa.BigInteger(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("image_path", sa.Text(), nullable=True),
        sa.Column("source_index", sa.BigInteger(), nullable=True),
        sa.Column("image_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("output_name", sa.String(length=255), nullable=True),
        sa.Column("visible_milliseconds", sa.BigInteger(), nullable=False),
        sa.Column("decoded", sa.Boolean(), nullable=False),
        sa.Column("target_operation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("command_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("applied_server_revision", sa.BigInteger(), nullable=False),
        sa.Column("outcome_code", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "operation_type IN ('viewed','select','skip','deselect','undo')",
            name="ck_rms_operations_type",
        ),
        sa.CheckConstraint(
            "status IN ('queued','sending','applied','retry','superseded','conflict','rejected')",
            name="ck_rms_operations_status",
        ),
        sa.CheckConstraint(
            "client_sequence > 0 AND expected_server_revision >= 0 "
            "AND selection_generation >= 0 AND applied_server_revision >= 0 "
            "AND visible_milliseconds >= 0 AND range_start > 0 "
            "AND range_end = range_start + 8",
            name="ck_rms_operations_counters",
        ),
        sa.CheckConstraint(
            "command_checksum_sha256 ~ '^[0-9a-f]{64}$' AND "
            "(image_checksum_sha256 IS NULL OR image_checksum_sha256 ~ '^[0-9a-f]{64}$')",
            name="ck_rms_operations_checksums",
        ),
        sa.CheckConstraint(
            "(operation_type = 'skip' AND file_id IS NULL) OR "
            "(operation_type <> 'skip' AND file_id IS NOT NULL)",
            name="ck_rms_operations_file_scope",
        ),
        sa.CheckConstraint(
            "operation_type <> 'select' OR (image_path IS NOT NULL "
            "AND source_index IS NOT NULL AND output_name IS NOT NULL)",
            name="ck_rms_operations_select_payload",
        ),
        sa.CheckConstraint(
            "operation_type NOT IN ('deselect','undo') OR target_operation_id IS NOT NULL",
            name="ck_rms_operations_target",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id", "session_id"],
            ["remote_manual_selection_batches.id", "remote_manual_selection_batches.session_id"],
            name="fk_rms_operations_batch_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["file_id", "batch_id", "session_id"],
            [
                "remote_manual_selection_files.id",
                "remote_manual_selection_files.batch_id",
                "remote_manual_selection_files.session_id",
            ],
            name="fk_rms_operations_file_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_operation_id", "batch_id", "session_id"],
            [
                "remote_manual_selection_operations.id",
                "remote_manual_selection_operations.batch_id",
                "remote_manual_selection_operations.session_id",
            ],
            name="fk_rms_operations_target_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rms_operations"),
        sa.UniqueConstraint("id", "batch_id", "session_id", name="uq_rms_operations_scope"),
        sa.UniqueConstraint(
            "batch_id",
            "client_instance_id",
            "client_sequence",
            name="uq_rms_operations_client_sequence",
        ),
    )
    op.create_index(
        "uq_rms_operations_applied_revision",
        "remote_manual_selection_operations",
        ["batch_id", "applied_server_revision"],
        unique=True,
        postgresql_where=sa.text("status = 'applied'"),
    )
    op.create_index(
        "ix_rms_operations_delta",
        "remote_manual_selection_operations",
        ["batch_id", "client_sequence", "id"],
    )

    op.create_table(
        "remote_manual_selection_transfers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("declared_bytes", sa.BigInteger(), nullable=False),
        sa.Column("received_bytes", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("declared_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("verified_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("temp_relative_path", sa.Text(), nullable=True),
        sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('queued','uploading','stored_temp','verified','materialized',"
            "'cancelled','failed','retrying')",
            name="ck_rms_transfers_status",
        ),
        sa.CheckConstraint(
            "generation >= 0 AND attempt > 0 AND declared_bytes >= 0 "
            "AND received_bytes >= 0 AND received_bytes <= declared_bytes",
            name="ck_rms_transfers_counters",
        ),
        sa.CheckConstraint(
            "(declared_checksum_sha256 IS NULL OR "
            "declared_checksum_sha256 ~ '^[0-9a-f]{64}$') AND "
            "(verified_checksum_sha256 IS NULL OR "
            "verified_checksum_sha256 ~ '^[0-9a-f]{64}$')",
            name="ck_rms_transfers_checksums",
        ),
        sa.ForeignKeyConstraint(
            ["file_id", "batch_id", "session_id"],
            [
                "remote_manual_selection_files.id",
                "remote_manual_selection_files.batch_id",
                "remote_manual_selection_files.session_id",
            ],
            name="fk_rms_transfers_file_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rms_transfers"),
        sa.UniqueConstraint(
            "id", "file_id", "batch_id", "session_id", name="uq_rms_transfers_scope"
        ),
        sa.UniqueConstraint("file_id", "generation", "attempt", name="uq_rms_transfers_attempt"),
    )
    op.create_index(
        "ix_rms_transfers_queue",
        "remote_manual_selection_transfers",
        ["status", "retry_at", "created_at", "id"],
    )

    op.create_table(
        "remote_manual_selection_host_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transfer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("action_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(length=200), nullable=True),
        sa.Column("lease_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "action_type IN ('verify','materialize','remove','reconcile')",
            name="ck_rms_host_actions_type",
        ),
        sa.CheckConstraint(
            "status IN ('queued','processing','completed','retry','failed','superseded')",
            name="ck_rms_host_actions_status",
        ),
        sa.CheckConstraint("generation >= 0 AND attempt >= 0", name="ck_rms_host_actions_counters"),
        sa.CheckConstraint(
            "(lease_owner IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL) OR "
            "(length(btrim(lease_owner)) > 0 AND lease_token IS NOT NULL "
            "AND lease_expires_at IS NOT NULL)",
            name="ck_rms_host_actions_lease",
        ),
        sa.ForeignKeyConstraint(
            ["file_id", "batch_id", "session_id"],
            [
                "remote_manual_selection_files.id",
                "remote_manual_selection_files.batch_id",
                "remote_manual_selection_files.session_id",
            ],
            name="fk_rms_host_actions_file_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["transfer_id", "file_id", "batch_id", "session_id"],
            [
                "remote_manual_selection_transfers.id",
                "remote_manual_selection_transfers.file_id",
                "remote_manual_selection_transfers.batch_id",
                "remote_manual_selection_transfers.session_id",
            ],
            name="fk_rms_host_actions_transfer_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rms_host_actions"),
    )
    op.create_index(
        "uq_rms_host_actions_active",
        "remote_manual_selection_host_actions",
        ["file_id", "generation", "action_type"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued','processing','retry')"),
    )
    op.create_index(
        "ix_rms_host_actions_queue",
        "remote_manual_selection_host_actions",
        ["status", "next_attempt_at", "created_at", "id"],
    )

    op.create_table(
        "remote_manual_selection_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("outcome_code", sa.String(length=100), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "length(btrim(event_type)) > 0 AND length(btrim(actor)) > 0 "
            "AND length(btrim(outcome_code)) > 0",
            name="ck_rms_audit_values",
        ),
        sa.CheckConstraint("jsonb_typeof(payload) = 'object'", name="ck_rms_audit_payload"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["remote_manual_selection_sessions.id"],
            name="fk_rms_audit_session",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id", "session_id"],
            ["remote_manual_selection_batches.id", "remote_manual_selection_batches.session_id"],
            name="fk_rms_audit_batch_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rms_audit"),
    )
    op.create_index(
        "ix_rms_audit_session_created",
        "remote_manual_selection_audit_events",
        ["session_id", "created_at", "id"],
    )

    op.execute(
        """
        CREATE FUNCTION deny_remote_manual_selection_append_only_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'remote manual selection journal is append-only'
                USING ERRCODE = '55000';
        END;
        $$
        """
    )
    for table_name in (
        "remote_manual_selection_operations",
        "remote_manual_selection_audit_events",
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_append_only
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION deny_remote_manual_selection_append_only_mutation()
            """
        )


def downgrade() -> None:
    for table_name in (
        "remote_manual_selection_audit_events",
        "remote_manual_selection_operations",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_append_only ON {table_name}")
    op.execute("DROP FUNCTION IF EXISTS deny_remote_manual_selection_append_only_mutation()")

    op.drop_index("ix_rms_audit_session_created", table_name="remote_manual_selection_audit_events")
    op.drop_table("remote_manual_selection_audit_events")
    op.drop_index("ix_rms_host_actions_queue", table_name="remote_manual_selection_host_actions")
    op.drop_index("uq_rms_host_actions_active", table_name="remote_manual_selection_host_actions")
    op.drop_table("remote_manual_selection_host_actions")
    op.drop_index("ix_rms_transfers_queue", table_name="remote_manual_selection_transfers")
    op.drop_table("remote_manual_selection_transfers")
    op.drop_index("ix_rms_operations_delta", table_name="remote_manual_selection_operations")
    op.drop_index(
        "uq_rms_operations_applied_revision", table_name="remote_manual_selection_operations"
    )
    op.drop_table("remote_manual_selection_operations")
    op.drop_index("ix_rms_files_status", table_name="remote_manual_selection_files")
    op.drop_index("ix_rms_files_delta", table_name="remote_manual_selection_files")
    op.drop_table("remote_manual_selection_files")
    op.drop_index("ix_rms_batches_session_status", table_name="remote_manual_selection_batches")
    op.drop_table("remote_manual_selection_batches")
    op.drop_index(
        "ix_rms_collections_session_status", table_name="remote_manual_selection_collections"
    )
    op.drop_table("remote_manual_selection_collections")
    op.drop_index("ix_rms_sessions_status_expiry", table_name="remote_manual_selection_sessions")
    op.drop_table("remote_manual_selection_sessions")
