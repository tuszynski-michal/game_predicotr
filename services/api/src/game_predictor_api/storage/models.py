"""SQLAlchemy mappings for canonical administrative records."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from game_predictor_api.domain.catalog import GameStatus, SymbolStatus
from game_predictor_api.domain.datasets import DatasetVersionStatus
from game_predictor_api.domain.image_selections import (
    IMAGE_SELECTION_ORDERING_POLICY,
    ImageSelectionCandidateDecision,
    ImageSelectionGroupStatus,
)
from game_predictor_api.domain.jobs import JobStatus, JobType
from game_predictor_api.domain.mobile_releases import MobileReleaseStatus
from game_predictor_api.domain.reviews import (
    ReviewItemStatus,
    ReviewResolutionAction,
)
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.domain.worker_lanes import WorkerLaneName
from game_predictor_api.storage.metadata import Base


def _enum_values(
    enum_type: (
        type[DatasetVersionStatus]
        | type[GameStatus]
        | type[JobStatus]
        | type[JobType]
        | type[MobileReleaseStatus]
        | type[ReviewItemStatus]
        | type[ReviewResolutionAction]
        | type[SymbolStatus]
        | type[RulesVersionStatus]
        | type[WorkerLaneName]
    ),
) -> list[str]:
    return [member.value for member in enum_type]


class GameModel(Base):
    __tablename__ = "games"
    __table_args__ = (
        CheckConstraint(
            "expected_layout_count BETWEEN 1 AND 10000000",
            name="ck_games_expected_layout_count_range",
        ),
        UniqueConstraint("code", name="uq_games_code"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[GameStatus] = mapped_column(
        Enum(
            GameStatus,
            name="game_status",
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=GameStatus.DRAFT,
    )
    expected_layout_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=500_000,
        server_default=text("500000"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CleanupOperationModel(Base):
    __tablename__ = "cleanup_operations"
    __table_args__ = (
        CheckConstraint(
            "operation_type IN ('mobile_release', 'game_layout_data')",
            name="ck_cleanup_operations_type",
        ),
        CheckConstraint(
            "preview_token ~ '^[0-9a-f]{64}$'",
            name="ck_cleanup_operations_preview_token",
        ),
        UniqueConstraint(
            "operation_type",
            "target_id",
            "preview_token",
            name="uq_cleanup_operations_target_preview",
        ),
        Index(
            "ix_cleanup_operations_target_created",
            "operation_type",
            "target_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    operation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_id: Mapped[UUID] = mapped_column(nullable=False)
    preview_token: Mapped[str] = mapped_column(String(64), nullable=False)
    result_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class SymbolModel(Base):
    __tablename__ = "symbols"
    __table_args__ = (
        CheckConstraint(
            "mobile_code BETWEEN 1 AND 32767",
            name="ck_symbols_mobile_code_range",
        ),
        CheckConstraint(
            "display_order >= 0",
            name="ck_symbols_display_order_nonnegative",
        ),
        CheckConstraint(
            "name_pl IS NULL OR length(btrim(name_pl)) > 0",
            name="ck_symbols_name_pl_nonblank",
        ),
        CheckConstraint(
            "name_en IS NULL OR length(btrim(name_en)) > 0",
            name="ck_symbols_name_en_nonblank",
        ),
        UniqueConstraint("game_id", "mobile_code", name="uq_symbols_game_mobile_code"),
        UniqueConstraint("game_id", "code", name="uq_symbols_game_code"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    mobile_code: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_pl: Mapped[str | None] = mapped_column(String(200), nullable=True)
    name_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_wildcard: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[SymbolStatus] = mapped_column(
        Enum(
            SymbolStatus,
            name="symbol_status",
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=SymbolStatus.ACTIVE,
    )


class SymbolBootstrapRunModel(Base):
    __tablename__ = "symbol_bootstrap_runs"
    __table_args__ = (
        CheckConstraint(
            "expected_symbol_count BETWEEN 1 AND 32767",
            name="ck_symbol_bootstrap_expected_count_range",
        ),
        CheckConstraint(
            "detected_cluster_count > 0",
            name="ck_symbol_bootstrap_detected_count_positive",
        ),
        CheckConstraint(
            "source_state_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_symbol_bootstrap_source_sha256",
        ),
        CheckConstraint(
            "status IN ('ready', 'conflict', 'applied')",
            name="ck_symbol_bootstrap_status",
        ),
        CheckConstraint(
            "(status = 'applied' AND resolution IS NOT NULL AND applied_at IS NOT NULL) "
            "OR (status <> 'applied' AND resolution IS NULL AND applied_at IS NULL)",
            name="ck_symbol_bootstrap_applied_state",
        ),
        UniqueConstraint(
            "game_id",
            "source_state_sha256",
            "expected_symbol_count",
            name="uq_symbol_bootstrap_source_expectation",
        ),
        Index("ix_symbol_bootstrap_game_created", "game_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"),
        nullable=False,
    )
    expected_symbol_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    detected_cluster_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    source_state_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    candidates: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    resolution: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True,
    )
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class RulesVersionModel(Base):
    __tablename__ = "rules_versions"
    __table_args__ = (
        CheckConstraint(
            "version > 0",
            name="ck_rules_versions_version_positive",
        ),
        CheckConstraint(
            "rows BETWEEN 1 AND 32767",
            name="ck_rules_versions_rows_range",
        ),
        CheckConstraint(
            "columns BETWEEN 1 AND 32767",
            name="ck_rules_versions_columns_range",
        ),
        CheckConstraint(
            "spin_cost >= 0",
            name="ck_rules_versions_spin_cost_nonnegative",
        ),
        UniqueConstraint(
            "game_id",
            "version",
            name="uq_rules_versions_game_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    rows: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    columns: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    spin_cost: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[RulesVersionStatus] = mapped_column(
        Enum(
            RulesVersionStatus,
            name="rules_version_status",
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=RulesVersionStatus.DRAFT,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class PaylineModel(Base):
    __tablename__ = "paylines"
    __table_args__ = (
        CheckConstraint(
            "cardinality(row_path) > 0",
            name="ck_paylines_row_path_not_empty",
        ),
        CheckConstraint(
            "0 <= ALL(row_path)",
            name="ck_paylines_row_path_nonnegative",
        ),
        CheckConstraint(
            "display_order >= 0",
            name="ck_paylines_display_order_nonnegative",
        ),
        UniqueConstraint(
            "rules_version_id",
            "code",
            name="uq_paylines_rules_version_code",
        ),
        UniqueConstraint(
            "rules_version_id",
            "row_path",
            name="uq_paylines_rules_version_row_path",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    rules_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("rules_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    row_path: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger, dimensions=1),
        nullable=False,
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )


class RulesVersionSymbolModel(Base):
    __tablename__ = "rules_version_symbols"
    __table_args__ = (
        CheckConstraint(
            "minimum_match_length IS NULL OR minimum_match_length BETWEEN 2 AND 32767",
            name="ck_rules_version_symbols_minimum_range",
        ),
    )

    rules_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("rules_versions.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    symbol_id: Mapped[UUID] = mapped_column(
        ForeignKey("symbols.id", ondelete="RESTRICT"),
        primary_key=True,
        index=True,
    )
    minimum_match_length: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )


class PayoutRuleModel(Base):
    __tablename__ = "payout_rules"
    __table_args__ = (
        CheckConstraint(
            "match_length BETWEEN 2 AND 32767",
            name="ck_payout_rules_match_length_range",
        ),
        CheckConstraint(
            "payout_credits >= 0",
            name="ck_payout_rules_credits_nonnegative",
        ),
        ForeignKeyConstraint(
            ["rules_version_id", "symbol_id"],
            [
                "rules_version_symbols.rules_version_id",
                "rules_version_symbols.symbol_id",
            ],
            name="fk_payout_rules_rules_version_symbol",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "rules_version_id",
            "symbol_id",
            "match_length",
            name="uq_payout_rules_version_symbol_length",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    rules_version_id: Mapped[UUID] = mapped_column(
        nullable=False,
        index=True,
    )
    symbol_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    match_length: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    payout_credits: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )


class JobModel(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "progress_current >= 0",
            name="ck_jobs_progress_current_nonnegative",
        ),
        CheckConstraint(
            "progress_total IS NULL OR progress_total >= 0",
            name="ck_jobs_progress_total_nonnegative",
        ),
        CheckConstraint(
            "progress_total IS NULL OR progress_current <= progress_total",
            name="ck_jobs_progress_within_total",
        ),
        CheckConstraint(
            "success_count >= 0 AND failure_count >= 0 AND review_count >= 0",
            name="ck_jobs_outcome_counts_nonnegative",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_jobs_attempt_count_nonnegative",
        ),
        CheckConstraint(
            "(status = 'processing' "
            "AND ((job_type = 'image_selection' AND execution_slot = 2) "
            "OR (job_type <> 'image_selection' AND execution_slot = 1)) "
            "AND lease_owner IS NOT NULL AND lease_token IS NOT NULL "
            "AND lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL) "
            "OR (status <> 'processing' AND execution_slot IS NULL "
            "AND lease_owner IS NULL AND lease_token IS NULL "
            "AND lease_expires_at IS NULL AND heartbeat_at IS NULL)",
            name="ck_jobs_processing_lease_fields",
        ),
        UniqueConstraint("input_key", name="uq_jobs_input_key"),
        UniqueConstraint("execution_slot", name="uq_jobs_execution_slot"),
        Index("ix_jobs_status_created_at", "status", "created_at"),
        Index("ix_jobs_status_lease_expires", "status", "lease_expires_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_type: Mapped[JobType] = mapped_column(
        Enum(
            JobType,
            name="job_type",
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
    )
    game_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(
            JobStatus,
            name="job_status",
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=JobStatus.CREATED,
    )
    input_payload: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
    )
    input_key: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    progress_current: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
    )
    progress_total: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    success_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
    )
    failure_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
    )
    review_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    worker_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    checkpoint_payload: Mapped[dict[str, object] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    execution_slot: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
    )
    lease_owner: Mapped[str | None] = mapped_column(String(200), nullable=True)
    lease_token: Mapped[UUID | None] = mapped_column(nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class WorkerLaneRuntimeModel(Base):
    __tablename__ = "worker_lane_runtime"
    __table_args__ = (
        CheckConstraint(
            "process_id > 0",
            name="ck_worker_lane_runtime_process_id_positive",
        ),
        CheckConstraint(
            "thread_budget BETWEEN 1 AND 64",
            name="ck_worker_lane_runtime_thread_budget",
        ),
        CheckConstraint(
            "heartbeat_at >= started_at",
            name="ck_worker_lane_runtime_heartbeat_order",
        ),
        CheckConstraint(
            "stopped_at IS NULL OR stopped_at >= started_at",
            name="ck_worker_lane_runtime_stopped_order",
        ),
    )

    lane: Mapped[WorkerLaneName] = mapped_column(
        Enum(
            WorkerLaneName,
            name="worker_lane_name",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        primary_key=True,
    )
    instance_token: Mapped[UUID] = mapped_column(nullable=False)
    worker_id: Mapped[str] = mapped_column(String(200), nullable=False)
    worker_version: Mapped[str] = mapped_column(String(100), nullable=False)
    process_id: Mapped[int] = mapped_column(Integer, nullable=False)
    thread_budget: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ImageSelectionRunModel(Base):
    __tablename__ = "image_selection_runs"
    __table_args__ = (
        CheckConstraint(
            "input_manifest_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_selection_runs_input_manifest_sha256",
        ),
        CheckConstraint(
            "selector_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_image_selection_runs_selector_fingerprint",
        ),
        CheckConstraint(
            "contract_version = 1",
            name="ck_image_selection_runs_contract_version",
        ),
        CheckConstraint(
            f"ordering_policy = '{IMAGE_SELECTION_ORDERING_POLICY}'",
            name="ck_image_selection_runs_ordering_policy",
        ),
        CheckConstraint(
            "sequence_direction IN ('ascending', 'descending')",
            name="ck_image_selection_runs_sequence_direction",
        ),
        CheckConstraint(
            "first_sequence_number >= 0",
            name="ck_image_selection_runs_first_sequence_positive",
        ),
        CheckConstraint(
            "last_sequence_number >= 0",
            name="ck_image_selection_runs_last_sequence_positive",
        ),
        CheckConstraint(
            "last_sequence_number = 0 OR "
            "(first_sequence_number > 0 AND "
            "((sequence_direction = 'ascending' AND "
            "last_sequence_number >= first_sequence_number) OR "
            "(sequence_direction = 'descending' AND "
            "last_sequence_number <= first_sequence_number)))",
            name="ck_image_selection_runs_sequence_bounds",
        ),
        CheckConstraint(
            "execution_mode IN ('full', 'range_recovery')",
            name="ck_image_selection_runs_execution_mode",
        ),
        CheckConstraint(
            "(execution_mode = 'full' AND source_run_id IS NULL AND "
            "source_snapshot_sha256 IS NULL) OR "
            "(execution_mode = 'range_recovery' AND source_run_id IS NOT NULL AND "
            "source_run_id <> id AND source_snapshot_sha256 ~ '^[0-9a-f]{64}$')",
            name="ck_image_selection_runs_recovery_source",
        ),
        CheckConstraint(
            "(output_manifest_sha256 IS NULL AND "
            "output_manifest_relative_path IS NULL) OR "
            "(output_manifest_sha256 ~ '^[0-9a-f]{64}$' AND "
            "output_manifest_relative_path IS NOT NULL)",
            name="ck_image_selection_runs_output_manifest_state",
        ),
        CheckConstraint(
            "output_manifest_relative_path IS NULL OR "
            "(output_manifest_relative_path !~ '(^|/)\\.\\.(/|$)' AND "
            "output_manifest_relative_path !~ '^[A-Za-z]:' AND "
            "output_manifest_relative_path NOT LIKE '/%' AND "
            "output_manifest_relative_path NOT LIKE '%\\\\%')",
            name="ck_image_selection_runs_output_path_safe",
        ),
        UniqueConstraint("job_id", name="uq_image_selection_runs_job_id"),
        Index(
            "uq_image_selection_runs_full_identity",
            "game_id",
            "input_manifest_sha256",
            "selector_fingerprint",
            "sequence_direction",
            "first_sequence_number",
            "last_sequence_number",
            unique=True,
            postgresql_where=text("execution_mode = 'full'"),
        ),
        Index(
            "uq_image_selection_runs_recovery_identity",
            "source_run_id",
            "selector_fingerprint",
            "source_snapshot_sha256",
            "last_sequence_number",
            unique=True,
            postgresql_where=text("execution_mode = 'range_recovery'"),
        ),
        Index(
            "ix_image_selection_runs_game_created",
            "game_id",
            "created_at",
        ),
        Index(
            "ix_image_selection_runs_source_selection_id",
            "source_selection_id",
        ),
        Index("ix_image_selection_runs_source_run_id", "source_run_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"),
        nullable=False,
    )
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_selection_id: Mapped[UUID] = mapped_column(nullable=False)
    input_manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    selector_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    ordering_policy: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default=IMAGE_SELECTION_ORDERING_POLICY,
    )
    sequence_direction: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="ascending",
    )
    first_sequence_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    last_sequence_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    execution_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="full",
    )
    source_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("image_selection_runs.id", ondelete="RESTRICT"),
        nullable=True,
    )
    source_snapshot_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contract_version: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
    )
    output_manifest_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    output_manifest_relative_path: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CuratedImageImportSourceModel(Base):
    __tablename__ = "curated_image_import_sources"
    __table_args__ = (
        CheckConstraint(
            "manifest_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_curated_image_import_sources_manifest_checksum",
        ),
        CheckConstraint(
            "manifest_relative_path !~ '(^|/)\\.\\.(/|$)' AND "
            "manifest_relative_path !~ '^[A-Za-z]:' AND "
            "manifest_relative_path NOT LIKE '/%' AND "
            "manifest_relative_path NOT LIKE '%\\\\%'",
            name="ck_curated_image_import_sources_manifest_path",
        ),
        CheckConstraint(
            "total_entries > 0 AND next_entry_index >= 0 AND next_entry_index <= total_entries",
            name="ck_curated_image_import_sources_cursor",
        ),
        UniqueConstraint(
            "image_selection_run_id",
            name="uq_curated_image_import_sources_selection_run",
        ),
        Index(
            "ix_curated_image_import_sources_game_created",
            "game_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"),
        nullable=False,
    )
    image_selection_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("image_selection_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    manifest_relative_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    manifest_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    total_entries: Mapped[int] = mapped_column(BigInteger, nullable=False)
    next_entry_index: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CuratedImageImportBatchModel(Base):
    __tablename__ = "curated_image_import_batches"
    __table_args__ = (
        CheckConstraint(
            "batch_number > 0 AND start_index >= 0 AND end_index > start_index",
            name="ck_curated_image_import_batches_range",
        ),
        UniqueConstraint(
            "source_id",
            "batch_number",
            name="uq_curated_image_import_batches_number",
        ),
        UniqueConstraint(
            "source_id",
            "start_index",
            name="uq_curated_image_import_batches_start",
        ),
        UniqueConstraint("job_id", name="uq_curated_image_import_batches_job"),
        Index(
            "ix_curated_image_import_batches_source_created",
            "source_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("curated_image_import_sources.id", ondelete="RESTRICT"),
        nullable=False,
    )
    batch_number: Mapped[int] = mapped_column(Integer, nullable=False)
    start_index: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_index: Mapped[int] = mapped_column(BigInteger, nullable=False)
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ImageSelectionGroupModel(Base):
    __tablename__ = "image_selection_groups"
    __table_args__ = (
        CheckConstraint(
            "group_order >= 0",
            name="ck_image_selection_groups_order_nonnegative",
        ),
        CheckConstraint(
            "(range_start IS NULL AND range_end IS NULL) OR "
            "(range_start >= 1 AND range_end >= range_start)",
            name="ck_image_selection_groups_range",
        ),
        CheckConstraint(
            "fingerprint_sha256 IS NULL OR fingerprint_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_selection_groups_fingerprint_sha256",
        ),
        CheckConstraint(
            "board_count_consensus IS NULL OR board_count_consensus BETWEEN 1 AND 9",
            name="ck_image_selection_groups_board_count",
        ),
        CheckConstraint(
            "status IN ('collecting', 'auto_selected', 'manual_required', "
            "'manually_selected', 'missing_image', 'skipped_existing_range', "
            "'range_required', 'range_confirmed', 'skipped_unreadable', "
            "'rejected_by_user')",
            name="ck_image_selection_groups_status",
        ),
        CheckConstraint(
            "(status = 'rejected_by_user' AND rejection_origin_status IN "
            "('manual_required', 'range_required')) OR "
            "(status <> 'rejected_by_user' AND rejection_origin_status IS NULL)",
            name="ck_image_selection_groups_rejection_origin",
        ),
        UniqueConstraint(
            "run_id",
            "group_order",
            name="uq_image_selection_groups_run_order",
        ),
        UniqueConstraint(
            "run_id",
            "id",
            name="uq_image_selection_groups_run_id_id",
        ),
        Index(
            "uq_image_selection_groups_selected_range",
            "run_id",
            "range_start",
            "range_end",
            unique=True,
            postgresql_where=text(
                "status IN ('auto_selected', 'manually_selected', 'missing_image', "
                "'range_confirmed') "
                "AND range_start IS NOT NULL"
            ),
        ),
        Index("ix_image_selection_groups_origin_group_id", "origin_group_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("image_selection_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    group_order: Mapped[int] = mapped_column(BigInteger, nullable=False)
    range_start: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    range_end: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    fingerprint_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    board_count_consensus: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
    )
    status: Mapped[ImageSelectionGroupStatus] = mapped_column(
        String(40),
        nullable=False,
        default=ImageSelectionGroupStatus.COLLECTING,
    )
    rejection_origin_status: Mapped[ImageSelectionGroupStatus | None] = mapped_column(
        String(40),
        nullable=True,
    )
    origin_group_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("image_selection_groups.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ImageSelectionCandidateModel(Base):
    __tablename__ = "image_selection_candidates"
    __table_args__ = (
        CheckConstraint(
            "order_index >= 0",
            name="ck_image_selection_candidates_order_nonnegative",
        ),
        CheckConstraint(
            "source_relative_path !~ '(^|/)\\.\\.(/|$)' AND "
            "source_relative_path !~ '^[A-Za-z]:' AND "
            "source_relative_path NOT LIKE '/%' AND "
            "source_relative_path NOT LIKE '%\\\\%'",
            name="ck_image_selection_candidates_source_path_safe",
        ),
        CheckConstraint(
            "checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_selection_candidates_checksum_sha256",
        ),
        CheckConstraint(
            "width >= 1 AND height >= 1",
            name="ck_image_selection_candidates_dimensions",
        ),
        CheckConstraint(
            "jsonb_typeof(quality_metrics) = 'object'",
            name="ck_image_selection_candidates_quality_metrics",
        ),
        CheckConstraint(
            "range_confidence IS NULL OR range_confidence BETWEEN 0 AND 1",
            name="ck_image_selection_candidates_range_confidence",
        ),
        CheckConstraint(
            "jsonb_typeof(reason_codes) = 'array'",
            name="ck_image_selection_candidates_reason_codes",
        ),
        CheckConstraint(
            "decision IN ('eligible', 'rejected', 'selected_automatic', 'selected_manual')",
            name="ck_image_selection_candidates_decision",
        ),
        CheckConstraint(
            "decision NOT IN ('selected_automatic', 'selected_manual') OR group_id IS NOT NULL",
            name="ck_image_selection_candidates_selected_group",
        ),
        ForeignKeyConstraint(
            ["run_id", "group_id"],
            ["image_selection_groups.run_id", "image_selection_groups.id"],
            name="fk_image_selection_candidates_run_group",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "run_id",
            "order_index",
            name="uq_image_selection_candidates_run_order",
        ),
        UniqueConstraint(
            "run_id",
            "source_relative_path",
            name="uq_image_selection_candidates_run_path",
        ),
        Index(
            "ix_image_selection_candidates_group_order",
            "run_id",
            "group_id",
            "order_index",
        ),
        Index(
            "uq_image_selection_candidates_selected_group",
            "run_id",
            "group_id",
            unique=True,
            postgresql_where=text("decision IN ('selected_automatic', 'selected_manual')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("image_selection_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    group_id: Mapped[UUID | None] = mapped_column(nullable=True)
    order_index: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_relative_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    quality_metrics: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    range_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    decision: Mapped[ImageSelectionCandidateDecision] = mapped_column(
        String(40),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ImageSelectionManualDecisionModel(Base):
    __tablename__ = "image_selection_manual_decisions"
    __table_args__ = (
        CheckConstraint(
            "(range_start IS NULL AND range_end IS NULL) OR "
            "(range_start >= 1 AND range_end >= range_start)",
            name="ck_image_selection_manual_decisions_range",
        ),
        CheckConstraint(
            "revision >= 1",
            name="ck_image_selection_manual_decisions_revision",
        ),
        CheckConstraint(
            "payload_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_selection_manual_decisions_payload_sha256",
        ),
        CheckConstraint(
            "resolution IN ('selected_image', 'missing_image', 'duplicate_range', "
            "'range_confirmed', 'rejected_group', 'restored_group')",
            name="ck_image_selection_manual_decisions_resolution",
        ),
        CheckConstraint(
            "(resolution IN ('selected_image', 'range_confirmed') "
            "AND candidate_id IS NOT NULL) OR "
            "(resolution IN ('missing_image', 'duplicate_range', "
            "'rejected_group', 'restored_group') "
            "AND candidate_id IS NULL)",
            name="ck_image_selection_manual_decisions_candidate_resolution",
        ),
        ForeignKeyConstraint(
            ["run_id", "group_id"],
            ["image_selection_groups.run_id", "image_selection_groups.id"],
            name="fk_image_selection_manual_decisions_group",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "run_id",
            "group_id",
            "revision",
            name="uq_image_selection_manual_decisions_revision",
        ),
        Index(
            "ix_image_selection_manual_decisions_group_revision",
            "run_id",
            "group_id",
            "revision",
        ),
    )

    idempotency_key: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("image_selection_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    group_id: Mapped[UUID] = mapped_column(nullable=False)
    candidate_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("image_selection_candidates.id", ondelete="RESTRICT"),
        nullable=True,
    )
    resolution: Mapped[str] = mapped_column(String(32), nullable=False)
    range_start: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    range_end: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ImageFileExecutionModel(Base):
    __tablename__ = "image_file_executions"
    __table_args__ = (
        CheckConstraint(
            "file_execution_key ~ '^[0-9a-f]{64}$'",
            name="ck_image_file_executions_key",
        ),
        CheckConstraint(
            "source_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_file_executions_source_checksum",
        ),
        CheckConstraint(
            "pipeline_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_image_file_executions_pipeline_fingerprint",
        ),
        CheckConstraint(
            "status IN ('processing', 'waiting_for_review', 'completed', 'failed')",
            name="ck_image_file_executions_status",
        ),
        CheckConstraint(
            "retry_count >= 0",
            name="ck_image_file_executions_retry_nonnegative",
        ),
        CheckConstraint(
            "(status = 'failed' AND failed_stage IS NOT NULL "
            "AND error_code IS NOT NULL AND error_message IS NOT NULL "
            "AND last_failed_at IS NOT NULL) OR "
            "(status <> 'failed' AND failed_stage IS NULL "
            "AND error_code IS NULL AND error_message IS NULL "
            "AND last_failed_at IS NULL)",
            name="ck_image_file_executions_failure_state",
        ),
        UniqueConstraint(
            "source_checksum_sha256",
            "pipeline_fingerprint",
            name="uq_image_file_executions_source_pipeline",
        ),
        Index(
            "ix_image_file_executions_pipeline_status",
            "pipeline_fingerprint",
            "status",
        ),
    )

    file_execution_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    pipeline_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    checkpoint_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    review_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    failed_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    last_failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class ImageImportJobFileModel(Base):
    __tablename__ = "image_import_job_files"
    __table_args__ = (
        CheckConstraint(
            "order_index >= 0",
            name="ck_image_import_job_files_order_nonnegative",
        ),
        CheckConstraint(
            "source_relative_path <> '' "
            "AND source_relative_path !~ '(^|/)\\.\\.(/|$)' "
            "AND source_relative_path !~ '^/' "
            "AND source_relative_path !~ '\\\\'",
            name="ck_image_import_job_files_relative_path",
        ),
        CheckConstraint(
            "workflow_status IN ('processing', 'waiting_for_review', 'completed', 'failed')",
            name="ck_image_import_job_files_workflow_status",
        ),
        CheckConstraint(
            "retry_count >= 0",
            name="ck_image_import_job_files_retry_nonnegative",
        ),
        CheckConstraint(
            "(workflow_status = 'failed' AND failed_stage IS NOT NULL "
            "AND error_code IS NOT NULL AND error_message IS NOT NULL "
            "AND last_failed_at IS NOT NULL) OR "
            "(workflow_status <> 'failed' AND failed_stage IS NULL "
            "AND error_code IS NULL AND error_message IS NULL "
            "AND last_failed_at IS NULL)",
            name="ck_image_import_job_files_failure_state",
        ),
        UniqueConstraint(
            "job_id",
            "order_index",
            name="uq_image_import_job_files_job_order",
        ),
        Index(
            "ix_image_import_job_files_execution",
            "file_execution_key",
        ),
        Index(
            "ix_image_import_job_files_job_workflow",
            "job_id",
            "workflow_status",
            "order_index",
        ),
    )

    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    file_execution_key: Mapped[str] = mapped_column(
        ForeignKey(
            "image_file_executions.file_execution_key",
            ondelete="RESTRICT",
        ),
        primary_key=True,
    )
    order_index: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_relative_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    workflow_checkpoint_payload: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
    )
    workflow_status: Mapped[str] = mapped_column(String(30), nullable=False)
    review_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    failed_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    last_failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ImagePipelineStageResultModel(Base):
    __tablename__ = "image_pipeline_stage_results"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('discovery', 'normalization', 'board_detection', "
            "'board_cell_geometry', 'board_crops', 'sequence_ocr', 'symbol_inference')",
            name="ck_image_pipeline_stage_results_stage",
        ),
        CheckConstraint(
            "length(btrim(adapter_version)) > 0",
            name="ck_image_pipeline_stage_results_adapter_version",
        ),
    )

    file_execution_key: Mapped[str] = mapped_column(
        ForeignKey("image_file_executions.file_execution_key", ondelete="RESTRICT"),
        primary_key=True,
    )
    stage: Mapped[str] = mapped_column(String(40), primary_key=True)
    adapter_version: Mapped[str] = mapped_column(String(150), nullable=False)
    result_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class SourceImageModel(Base):
    __tablename__ = "source_images"
    __table_args__ = (
        CheckConstraint(
            "checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_source_images_checksum",
        ),
        CheckConstraint(
            "width > 0 AND height > 0",
            name="ck_source_images_dimensions_positive",
        ),
        CheckConstraint(
            "status IN ('discovered', 'processing', 'waiting_for_review', "
            "'accepted', 'rejected', 'completed', 'failed')",
            name="ck_source_images_status",
        ),
        CheckConstraint(
            r"length(btrim(relative_path)) > 0 "
            r"AND relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'",
            name="ck_source_images_relative_path",
        ),
        UniqueConstraint(
            "import_job_id",
            "checksum_sha256",
            name="uq_source_images_job_checksum",
        ),
        UniqueConstraint(
            "import_job_id",
            "file_execution_key",
            name="uq_source_images_job_execution",
        ),
        Index("ix_source_images_job_status", "import_job_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    import_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    file_execution_key: Mapped[str] = mapped_column(
        ForeignKey("image_file_executions.file_execution_key", ondelete="RESTRICT"),
        nullable=False,
    )
    relative_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class RecognizedBoardModel(Base):
    __tablename__ = "recognized_boards"
    __table_args__ = (
        CheckConstraint(
            "position_index BETWEEN 0 AND 8",
            name="ck_recognized_boards_position",
        ),
        CheckConstraint(
            "sequence_number IS NULL OR sequence_number > 0",
            name="ck_recognized_boards_sequence_positive",
        ),
        CheckConstraint(
            "sequence_confidence BETWEEN 0 AND 1 AND board_confidence BETWEEN 0 AND 1",
            name="ck_recognized_boards_confidence",
        ),
        CheckConstraint(
            "board_checksum_sha256 ~ '^[0-9a-f]{64}$' AND pipeline_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_recognized_boards_sha256",
        ),
        CheckConstraint(
            r"length(btrim(board_relative_path)) > 0 "
            r"AND board_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'",
            name="ck_recognized_boards_relative_path",
        ),
        CheckConstraint(
            "status IN ('pending_review', 'accepted', 'corrected', 'rejected')",
            name="ck_recognized_boards_status",
        ),
        CheckConstraint(
            "geometry_revision >= 0",
            name="ck_recognized_boards_geometry_revision",
        ),
        UniqueConstraint(
            "source_image_id",
            "position_index",
            name="uq_recognized_boards_source_position",
        ),
        Index(
            "ix_recognized_boards_source_status",
            "source_image_id",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_image_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_images.id", ondelete="RESTRICT"),
        nullable=False,
    )
    position_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    sequence_number_raw: Mapped[str] = mapped_column(String(100), nullable=False)
    sequence_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sequence_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    board_geometry: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    board_relative_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    board_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    cells_prediction: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    board_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    pipeline_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    geometry_revision: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class CellObservationModel(Base):
    __tablename__ = "cell_observations"
    __table_args__ = (
        CheckConstraint(
            "row_index BETWEEN 0 AND 2 AND column_index BETWEEN 0 AND 4",
            name="ck_cell_observations_coordinates",
        ),
        CheckConstraint(
            "crop_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_cell_observations_checksum",
        ),
        CheckConstraint(
            r"length(btrim(crop_relative_path)) > 0 "
            r"AND crop_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'",
            name="ck_cell_observations_relative_path",
        ),
        UniqueConstraint(
            "recognized_board_id",
            "row_index",
            "column_index",
            name="uq_cell_observations_board_cell",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    recognized_board_id: Mapped[UUID] = mapped_column(
        ForeignKey("recognized_boards.id", ondelete="RESTRICT"),
        nullable=False,
    )
    row_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    column_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    crop_relative_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    crop_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    cropper_version: Mapped[str] = mapped_column(String(150), nullable=False)
    prediction: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ImageReviewItemModel(Base):
    __tablename__ = "image_review_items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'accepted', 'corrected', 'rejected', 'superseded')",
            name="ck_image_review_items_status",
        ),
        CheckConstraint(
            "(status = 'pending' AND resolved_value IS NULL "
            "AND resolved_by IS NULL AND resolved_at IS NULL "
            "AND resolution_revision >= 0) OR "
            "(status <> 'pending' AND resolved_value IS NOT NULL "
            "AND resolved_by IS NOT NULL AND resolved_at IS NOT NULL "
            "AND resolution_revision > 0)",
            name="ck_image_review_items_resolution_state",
        ),
        UniqueConstraint(
            "recognized_board_id",
            name="uq_image_review_items_board",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    recognized_board_id: Mapped[UUID] = mapped_column(
        ForeignKey("recognized_boards.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    resolved_value: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    resolution_revision: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ImageReviewQueueStateModel(Base):
    __tablename__ = "image_review_queue_states"
    __table_args__ = (
        CheckConstraint(
            "queue_version > 0 AND total_count >= 0 "
            "AND pending_count >= 0 AND accepted_count >= 0 "
            "AND corrected_count >= 0 AND rejected_count >= 0 "
            "AND superseded_count >= 0",
            name="ck_image_review_queue_states_nonnegative",
        ),
        CheckConstraint(
            "total_count = pending_count + accepted_count + corrected_count "
            "+ rejected_count + superseded_count",
            name="ck_image_review_queue_states_total",
        ),
    )

    import_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    queue_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pending_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    accepted_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    corrected_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rejected_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    superseded_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ImageReviewQueueItemModel(Base):
    __tablename__ = "image_review_queue_items"
    __table_args__ = (
        CheckConstraint(
            "source_order_index >= 0 AND position_index BETWEEN 0 AND 8",
            name="ck_image_review_queue_items_position",
        ),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'corrected', 'rejected', 'superseded')",
            name="ck_image_review_queue_items_status",
        ),
        UniqueConstraint(
            "import_job_id",
            "source_order_index",
            "position_index",
            "review_item_id",
            name="uq_image_review_queue_items_order_key",
        ),
        Index(
            "ix_image_review_queue_items_job_status_order",
            "import_job_id",
            "status",
            "source_order_index",
            "position_index",
            "review_item_id",
        ),
    )

    review_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("image_review_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    import_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_order_index: Mapped[int] = mapped_column(BigInteger, nullable=False)
    position_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ImageReviewResolutionEventModel(Base):
    __tablename__ = "image_review_resolution_events"
    __table_args__ = (
        CheckConstraint(
            "revision > 0",
            name="ck_image_review_resolution_events_revision",
        ),
        CheckConstraint(
            "action IN ('accepted', 'corrected', 'rejected', 'reopened', 'superseded')",
            name="ck_image_review_resolution_events_action",
        ),
        CheckConstraint(
            "command_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_review_resolution_events_command",
        ),
        UniqueConstraint(
            "review_item_id",
            "revision",
            name="uq_image_review_resolution_events_item_revision",
        ),
        UniqueConstraint(
            "review_item_id",
            "idempotency_key",
            name="uq_image_review_resolution_events_item_idempotency",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    review_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("image_review_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    command_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    resolved_value: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    resolved_by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ImageSequenceSourceOverrideEventModel(Base):
    __tablename__ = "image_sequence_source_override_events"
    __table_args__ = (
        CheckConstraint(
            "sequence_number > 0",
            name="ck_image_sequence_source_override_sequence_positive",
        ),
        CheckConstraint(
            "revision > 0",
            name="ck_image_sequence_source_override_revision_positive",
        ),
        UniqueConstraint(
            "game_id",
            "sequence_number",
            "revision",
            name="uq_image_sequence_source_override_revision",
        ),
        Index(
            "ix_image_sequence_source_override_current",
            "game_id",
            "sequence_number",
            "revision",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    selected_review_item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("image_review_items.id", ondelete="RESTRICT"),
        nullable=True,
    )
    selected_by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ImageBoardGeometryRevisionModel(Base):
    __tablename__ = "image_board_geometry_revisions"
    __table_args__ = (
        CheckConstraint(
            "revision > 0",
            name="ck_image_board_geometry_revisions_revision",
        ),
        CheckConstraint(
            "command_sha256 ~ '^[0-9a-f]{64}$' AND board_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_board_geometry_revisions_sha256",
        ),
        CheckConstraint(
            "jsonb_typeof(corners) = 'array' AND jsonb_array_length(corners) = 4",
            name="ck_image_board_geometry_revisions_corners",
        ),
        CheckConstraint(
            "jsonb_typeof(crop_artifacts) = 'array' AND jsonb_array_length(crop_artifacts) = 15",
            name="ck_image_board_geometry_revisions_crops",
        ),
        CheckConstraint(
            r"length(btrim(board_relative_path)) > 0 "
            r"AND board_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'",
            name="ck_image_board_geometry_revisions_relative_path",
        ),
        UniqueConstraint(
            "recognized_board_id",
            "revision",
            name="uq_image_board_geometry_revisions_board_revision",
        ),
        UniqueConstraint(
            "review_item_id",
            "idempotency_key",
            name="uq_image_board_geometry_revisions_item_idempotency",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    review_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("image_review_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    recognized_board_id: Mapped[UUID] = mapped_column(
        ForeignKey("recognized_boards.id", ondelete="RESTRICT"),
        nullable=False,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(nullable=False)
    command_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    corners: Mapped[list[dict[str, int]]] = mapped_column(JSONB, nullable=False)
    geometry: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    board_relative_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    board_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    cropper_version: Mapped[str] = mapped_column(String(150), nullable=False)
    crop_artifacts: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
    )
    corrected_by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ImagePageGeometryOverrideModel(Base):
    """Revisioned human correction for all nine quads on one source photo."""

    __tablename__ = "image_page_geometry_overrides"
    __table_args__ = (
        CheckConstraint(
            "image_width > 0 AND image_height > 0 AND revision > 0",
            name="ck_image_page_geometry_overrides_values",
        ),
        CheckConstraint(
            "source_checksum_sha256 ~ '^[0-9a-f]{64}$' "
            "AND decision_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_page_geometry_overrides_checksums",
        ),
        CheckConstraint(
            "jsonb_typeof(final_quads) = 'array' AND jsonb_array_length(final_quads) = 9",
            name="ck_image_page_geometry_overrides_quads",
        ),
        UniqueConstraint(
            "game_id",
            "source_checksum_sha256",
            "revision",
            name="uq_image_page_geometry_overrides_revision",
        ),
        Index(
            "ix_image_page_geometry_overrides_current",
            "game_id",
            "source_checksum_sha256",
            "revision",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"), nullable=False
    )
    source_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    image_width: Mapped[int] = mapped_column(Integer, nullable=False)
    image_height: Mapped[int] = mapped_column(Integer, nullable=False)
    final_quads: Mapped[list[list[dict[str, int]]]] = mapped_column(JSONB, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    decision_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ImageBoardGeometryPendingModel(Base):
    """A board for which verified cell geometry is not yet available."""

    __tablename__ = "image_board_geometry_pending"
    __table_args__ = (
        CheckConstraint(
            "sequence_number > 0 AND position_index BETWEEN 0 AND 8 "
            "AND expected_geometry_revision >= 0 "
            "AND expected_review_resolution_revision >= 0",
            name="ck_image_board_geometry_pending_values",
        ),
        CheckConstraint(
            "source_checksum_sha256 ~ '^[0-9a-f]{64}$' "
            "AND processing_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$' "
            "AND pipeline_fingerprint_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_board_geometry_pending_checksums",
        ),
        CheckConstraint(
            "status IN ('pending', 'resolved', 'superseded')",
            name="ck_image_board_geometry_pending_status",
        ),
        CheckConstraint(
            "reason_code IN ('insufficient_centers', 'incomplete_lattice', "
            "'residual_too_high', 'source_unavailable')",
            name="ck_image_board_geometry_pending_reason",
        ),
        CheckConstraint(
            "(status = 'pending' AND resolved_geometry_revision IS NULL "
            "AND resolved_at IS NULL AND superseded_at IS NULL) OR "
            "(status = 'resolved' AND resolved_geometry_revision IS NOT NULL "
            "AND resolved_geometry_revision > expected_geometry_revision "
            "AND resolved_at IS NOT NULL AND superseded_at IS NULL) OR "
            "(status = 'superseded' AND resolved_geometry_revision IS NULL "
            "AND resolved_at IS NULL AND superseded_at IS NOT NULL)",
            name="ck_image_board_geometry_pending_lifecycle",
        ),
        CheckConstraint(
            r"length(btrim(source_relative_path)) > 0 "
            r"AND source_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)' "
            r"AND length(btrim(processing_manifest_relative_path)) > 0 "
            r"AND processing_manifest_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'",
            name="ck_image_board_geometry_pending_paths",
        ),
        UniqueConstraint(
            "import_job_id",
            "source_image_id",
            "position_index",
            "processing_manifest_checksum_sha256",
            name="uq_image_board_geometry_pending_manifest",
        ),
        Index(
            "ix_image_board_geometry_pending_job_status_sequence",
            "import_job_id",
            "status",
            "sequence_number",
            "position_index",
            "id",
        ),
        Index(
            "uq_image_board_geometry_pending_current",
            "import_job_id",
            "source_image_id",
            "position_index",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"), nullable=False
    )
    import_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False
    )
    source_image_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_images.id", ondelete="RESTRICT"), nullable=False
    )
    recognized_board_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("recognized_boards.id", ondelete="RESTRICT"), nullable=True
    )
    review_item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("image_review_items.id", ondelete="RESTRICT"), nullable=True
    )
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    position_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    source_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_relative_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(40), nullable=False)
    processing_manifest_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    processing_manifest_relative_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    pipeline_fingerprint_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_geometry_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_review_resolution_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    resolved_geometry_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewerAccessSessionModel(Base):
    __tablename__ = "reviewer_access_sessions"
    __table_args__ = (
        CheckConstraint(
            "expires_at > created_at",
            name="ck_reviewer_access_sessions_expiration",
        ),
        CheckConstraint(
            "failed_attempts BETWEEN 0 AND 5",
            name="ck_reviewer_access_sessions_failed_attempts",
        ),
        UniqueConstraint(
            "id",
            "game_id",
            "import_job_id",
            name="uq_reviewer_access_sessions_scope_identity",
        ),
        Index("ix_reviewer_access_sessions_token_hash", "token_hash", unique=True),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    import_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    code_salt: Mapped[bytes] = mapped_column(LargeBinary(16), nullable=False)
    code_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    failed_attempts: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    token_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32), nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_unlocked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


class ReviewerAccessAuditEventModel(Base):
    __tablename__ = "reviewer_access_audit_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('created', 'unlock_failed', 'unlocked', 'locked', 'revoked')",
            name="ck_reviewer_access_audit_events_type",
        ),
        Index(
            "ix_reviewer_access_audit_events_session_created",
            "session_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("reviewer_access_sessions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ReviewerWorkAssignmentModel(Base):
    __tablename__ = "reviewer_work_assignments"
    __table_args__ = (
        CheckConstraint(
            "assignment_type IN ('local', 'online')",
            name="ck_reviewer_work_assignments_type",
        ),
        CheckConstraint(
            "(assignment_type = 'local' AND reviewer_access_session_id IS NULL) "
            "OR (assignment_type = 'online' AND reviewer_access_session_id IS NOT NULL)",
            name="ck_reviewer_work_assignments_session_mode",
        ),
        CheckConstraint(
            "length(btrim(lease_owner)) BETWEEN 1 AND 200",
            name="ck_reviewer_work_assignments_lease_owner",
        ),
        CheckConstraint(
            "heartbeat_at >= created_at AND lease_expires_at > heartbeat_at "
            "AND updated_at >= heartbeat_at",
            name="ck_reviewer_work_assignments_lease_timestamps",
        ),
        CheckConstraint(
            "(closed_at IS NULL AND close_reason IS NULL AND closed_by IS NULL) "
            "OR (closed_at IS NOT NULL AND closed_at >= heartbeat_at "
            "AND close_reason IS NOT NULL AND closed_by IS NOT NULL "
            "AND length(btrim(close_reason)) BETWEEN 1 AND 100 "
            "AND length(btrim(closed_by)) BETWEEN 1 AND 200)",
            name="ck_reviewer_work_assignments_closure",
        ),
        Index(
            "uq_reviewer_work_assignments_active_import",
            "import_job_id",
            unique=True,
            postgresql_where=text("closed_at IS NULL"),
        ),
        Index(
            "ix_reviewer_work_assignments_active_lease",
            "lease_expires_at",
            "import_job_id",
            postgresql_where=text("closed_at IS NULL"),
        ),
        Index(
            "ix_reviewer_work_assignments_scope_history",
            "game_id",
            "import_job_id",
            "created_at",
            "id",
        ),
        Index(
            "uq_reviewer_work_assignments_access_session",
            "reviewer_access_session_id",
            unique=True,
            postgresql_where=text("reviewer_access_session_id IS NOT NULL"),
        ),
        ForeignKeyConstraint(
            ["reviewer_access_session_id", "game_id", "import_job_id"],
            [
                "reviewer_access_sessions.id",
                "reviewer_access_sessions.game_id",
                "reviewer_access_sessions.import_job_id",
            ],
            name="fk_reviewer_work_assignments_session_scope",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"),
        nullable=False,
    )
    import_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assignment_type: Mapped[str] = mapped_column(String(16), nullable=False)
    reviewer_access_session_id: Mapped[UUID | None] = mapped_column(nullable=True)
    lease_owner: Mapped[str] = mapped_column(String(200), nullable=False)
    lease_token: Mapped[UUID] = mapped_column(nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    closed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ImageVerifiedCohortExportModel(Base):
    __tablename__ = "image_verified_cohort_exports"
    __table_args__ = (
        CheckConstraint(
            "version > 0",
            name="ck_image_verified_cohort_exports_version",
        ),
        CheckConstraint(
            "input_state_sha256 ~ '^[0-9a-f]{64}$' AND payload_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_verified_cohort_exports_sha256",
        ),
        CheckConstraint(
            "board_count > 0 AND sample_count = board_count * 15 "
            "AND pending_item_count >= 0 AND rejected_item_count >= 0",
            name="ck_image_verified_cohort_exports_counts",
        ),
        CheckConstraint(
            r"length(btrim(artifact_relative_path)) > 0 "
            r"AND artifact_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'",
            name="ck_image_verified_cohort_exports_relative_path",
        ),
        UniqueConstraint(
            "game_id",
            "import_job_id",
            "version",
            name="uq_image_verified_cohort_exports_version",
        ),
        UniqueConstraint(
            "game_id",
            "import_job_id",
            "input_state_sha256",
            name="uq_image_verified_cohort_exports_state",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"),
        nullable=False,
    )
    import_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    input_state_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_relative_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    board_count: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    pending_item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected_item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class VerifiedTrainingCohortModel(Base):
    __tablename__ = "verified_training_cohorts"
    __table_args__ = (
        CheckConstraint(
            "iteration_number > 0 AND manifest_schema_version > 0",
            name="ck_verified_training_cohorts_versions",
        ),
        CheckConstraint(
            "manifest_checksum_sha256 ~ '^[0-9a-f]{64}$' AND command_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_verified_training_cohorts_sha256",
        ),
        CheckConstraint(
            "resolved_layout_count > 0 "
            "AND cell_sample_count = resolved_layout_count * 15 "
            "AND source_image_count > 0 "
            "AND pending_item_count >= 0 "
            "AND rejected_item_count >= 0 "
            "AND incomplete_item_count >= 0",
            name="ck_verified_training_cohorts_counts",
        ),
        CheckConstraint(
            r"length(btrim(artifact_relative_path)) > 0 "
            r"AND artifact_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'",
            name="ck_verified_training_cohorts_relative_path",
        ),
        UniqueConstraint(
            "game_id",
            "iteration_number",
            name="uq_verified_training_cohorts_iteration",
        ),
        UniqueConstraint(
            "game_id",
            "manifest_checksum_sha256",
            name="uq_verified_training_cohorts_manifest",
        ),
        UniqueConstraint(
            "game_id",
            "idempotency_key",
            name="uq_verified_training_cohorts_idempotency",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"),
        nullable=False,
    )
    iteration_number: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(nullable=False)
    command_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    resolved_layout_count: Mapped[int] = mapped_column(Integer, nullable=False)
    cell_sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_image_count: Mapped[int] = mapped_column(Integer, nullable=False)
    pending_item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected_item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    incomplete_item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_relative_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class VerifiedTrainingCohortItemModel(Base):
    __tablename__ = "verified_training_cohort_items"
    __table_args__ = (
        CheckConstraint(
            "item_order >= 0 AND sequence_number > 0 "
            "AND resolution_revision > 0 AND geometry_revision >= 0",
            name="ck_verified_training_cohort_items_values",
        ),
        CheckConstraint(
            "decision_status IN ('accepted', 'corrected')",
            name="ck_verified_training_cohort_items_status",
        ),
        CheckConstraint(
            "item_checksum_sha256 ~ '^[0-9a-f]{64}$' "
            "AND source_checksum_sha256 ~ '^[0-9a-f]{64}$' "
            "AND board_checksum_sha256 ~ '^[0-9a-f]{64}$' "
            "AND pipeline_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_verified_training_cohort_items_sha256",
        ),
        CheckConstraint(
            "jsonb_typeof(board_manifest) = 'object' "
            "AND jsonb_array_length(board_manifest -> 'cells') = 15",
            name="ck_verified_training_cohort_items_manifest",
        ),
        UniqueConstraint(
            "cohort_id",
            "item_order",
            name="uq_verified_training_cohort_items_order",
        ),
        UniqueConstraint(
            "cohort_id",
            "review_item_id",
            name="uq_verified_training_cohort_items_review",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    cohort_id: Mapped[UUID] = mapped_column(
        ForeignKey("verified_training_cohorts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    item_order: Mapped[int] = mapped_column(Integer, nullable=False)
    review_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("image_review_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    recognized_board_id: Mapped[UUID] = mapped_column(
        ForeignKey("recognized_boards.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_image_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_images.id", ondelete="RESTRICT"),
        nullable=False,
    )
    import_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    decision_status: Mapped[str] = mapped_column(String(20), nullable=False)
    resolution_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    geometry_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    source_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    board_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    pipeline_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    item_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    board_manifest: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class SymbolModelIterationModel(Base):
    __tablename__ = "symbol_model_iterations"
    __table_args__ = (
        CheckConstraint(
            "iteration_number > 0 AND last_completed_epoch >= 0",
            name="ck_symbol_model_iterations_numbers",
        ),
        CheckConstraint(
            "status IN ('created','dataset_build','training','trained','evaluating',"
            "'candidate_ready','rejected','failed','cancelled')",
            name="ck_symbol_model_iterations_status",
        ),
        CheckConstraint(
            "(gate_configuration_fingerprint IS NULL "
            "OR gate_configuration_fingerprint ~ '^[0-9a-f]{64}$') "
            "AND (candidate_manifest_checksum_sha256 IS NULL "
            "OR candidate_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$') "
            "AND (gate_report_checksum_sha256 IS NULL "
            "OR gate_report_checksum_sha256 ~ '^[0-9a-f]{64}$')",
            name="ck_symbol_model_iterations_gate_sha256",
        ),
        UniqueConstraint("game_id", "iteration_number", name="uq_symbol_model_iterations_number"),
        UniqueConstraint("job_id", name="uq_symbol_model_iterations_job"),
        UniqueConstraint(
            "game_id",
            "cohort_id",
            "configuration_fingerprint",
            name="uq_symbol_model_iterations_input",
        ),
        Index("ix_symbol_model_iterations_game_status", "game_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"), nullable=False
    )
    cohort_id: Mapped[UUID] = mapped_column(
        ForeignKey("verified_training_cohorts.id", ondelete="RESTRICT"), nullable=False
    )
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False)
    iteration_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    configuration_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    dataset_manifest_checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    dataset_manifest_relative_path: Mapped[str | None] = mapped_column(String(1000))
    checkpoint_checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    checkpoint_relative_path: Mapped[str | None] = mapped_column(String(1000))
    gate_configuration_fingerprint: Mapped[str | None] = mapped_column(String(64))
    gate_configuration_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    candidate_manifest_checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    candidate_manifest_relative_path: Mapped[str | None] = mapped_column(String(1000))
    gate_report_checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    gate_report_relative_path: Mapped[str | None] = mapped_column(String(1000))
    gate_metrics: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    rejection_reasons: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)), nullable=False, default=list
    )
    last_completed_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    partial_metrics: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class GameSymbolModelActivationModel(Base):
    __tablename__ = "game_symbol_model_activations"
    __table_args__ = (
        CheckConstraint(
            "action IN ('activate','rollback')",
            name="ck_game_symbol_model_activations_action",
        ),
        CheckConstraint(
            "activation_number > 0 AND btrim(actor) <> '' AND command_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_game_symbol_model_activations_values",
        ),
        UniqueConstraint(
            "game_id",
            "idempotency_key",
            name="uq_game_symbol_model_activations_idempotency",
        ),
        UniqueConstraint(
            "game_id",
            "activation_number",
            name="uq_game_symbol_model_activations_number",
        ),
        Index(
            "ix_game_symbol_model_activations_current",
            "game_id",
            "activation_number",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"), nullable=False
    )
    model_iteration_id: Mapped[UUID] = mapped_column(
        ForeignKey("symbol_model_iterations.id", ondelete="RESTRICT"), nullable=False
    )
    previous_model_iteration_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("symbol_model_iterations.id", ondelete="RESTRICT")
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    activation_number: Mapped[int] = mapped_column(Integer, nullable=False)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[UUID] = mapped_column(nullable=False)
    command_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class GridGeometryCohortModel(Base):
    __tablename__ = "grid_geometry_cohorts"
    __table_args__ = (
        CheckConstraint(
            "cohort_number > 0 AND sample_count > 0 AND source_image_count > 0 "
            "AND training_count >= 0 AND validation_count >= 0 "
            "AND training_count + validation_count = sample_count",
            name="ck_grid_geometry_cohorts_counts",
        ),
        CheckConstraint(
            "manifest_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_grid_geometry_cohorts_manifest_checksum",
        ),
        UniqueConstraint("game_id", "cohort_number", name="uq_grid_geometry_cohorts_number"),
        UniqueConstraint(
            "game_id",
            "manifest_checksum_sha256",
            name="uq_grid_geometry_cohorts_manifest",
        ),
        Index("ix_grid_geometry_cohorts_game_created", "game_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"), nullable=False
    )
    cohort_number: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_image_count: Mapped[int] = mapped_column(Integer, nullable=False)
    training_count: Mapped[int] = mapped_column(Integer, nullable=False)
    validation_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class GridCalibrationProfileModel(Base):
    __tablename__ = "grid_calibration_profiles"
    __table_args__ = (
        CheckConstraint(
            "profile_number > 0 AND status IN ('candidate_ready','rejected')",
            name="ck_grid_calibration_profiles_values",
        ),
        CheckConstraint(
            "profile_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_grid_calibration_profiles_checksum",
        ),
        UniqueConstraint("game_id", "profile_number", name="uq_grid_calibration_profiles_number"),
        UniqueConstraint("cohort_id", name="uq_grid_calibration_profiles_cohort"),
        Index("ix_grid_calibration_profiles_game_status", "game_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"), nullable=False
    )
    cohort_id: Mapped[UUID] = mapped_column(
        ForeignKey("grid_geometry_cohorts.id", ondelete="RESTRICT"), nullable=False
    )
    profile_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    profile_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    gate_metrics: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    rejection_reasons: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)), nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class GameGridProfileActivationModel(Base):
    __tablename__ = "game_grid_profile_activations"
    __table_args__ = (
        CheckConstraint(
            "action IN ('activate','rollback')",
            name="ck_game_grid_profile_activations_action",
        ),
        CheckConstraint(
            "activation_number > 0 AND btrim(actor) <> '' AND command_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_game_grid_profile_activations_values",
        ),
        UniqueConstraint(
            "game_id",
            "idempotency_key",
            name="uq_game_grid_profile_activations_idempotency",
        ),
        UniqueConstraint(
            "game_id",
            "activation_number",
            name="uq_game_grid_profile_activations_number",
        ),
        Index("ix_game_grid_profile_activations_current", "game_id", "activation_number"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"), nullable=False
    )
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("grid_calibration_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    previous_profile_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("grid_calibration_profiles.id", ondelete="RESTRICT")
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    activation_number: Mapped[int] = mapped_column(Integer, nullable=False)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[UUID] = mapped_column(nullable=False)
    command_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ImageLayoutStagingRowModel(Base):
    __tablename__ = "image_layout_staging_rows"
    __table_args__ = (
        CheckConstraint(
            "sequence_number > 0",
            name="ck_image_layout_staging_sequence_positive",
        ),
        CheckConstraint(
            "cardinality(cells) = 15 AND 1 <= ALL(cells) AND 32767 >= ALL(cells)",
            name="ck_image_layout_staging_cells",
        ),
        UniqueConstraint(
            "review_item_id",
            name="uq_image_layout_staging_review",
        ),
        Index(
            "ix_image_layout_staging_job_sequence",
            "import_job_id",
            "sequence_number",
        ),
    )

    import_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    recognized_board_id: Mapped[UUID] = mapped_column(
        ForeignKey("recognized_boards.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    review_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("image_review_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cells: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger, dimensions=1),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class LayoutImportRowModel(Base):
    __tablename__ = "layout_import_rows"
    __table_args__ = (
        CheckConstraint(
            "line_number > 0",
            name="ck_layout_import_rows_line_positive",
        ),
        CheckConstraint(
            "byte_offset_end > 0",
            name="ck_layout_import_rows_offset_positive",
        ),
        CheckConstraint(
            "sequence_number IS NULL OR sequence_number > 0",
            name="ck_layout_import_rows_sequence_positive",
        ),
        CheckConstraint(
            "cells IS NULL OR cardinality(cells) > 0",
            name="ck_layout_import_rows_cells_not_empty",
        ),
        CheckConstraint(
            "cells IS NULL OR (1 <= ALL(cells) AND 32767 >= ALL(cells))",
            name="ck_layout_import_rows_cells_mobile_code_range",
        ),
        CheckConstraint(
            "("
            "sequence_number IS NOT NULL AND cells IS NOT NULL "
            "AND error_code IS NULL AND error_message IS NULL"
            ") OR ("
            "sequence_number IS NULL AND cells IS NULL "
            "AND error_code IS NOT NULL AND error_message IS NOT NULL "
            "AND length(btrim(error_code)) > 0 "
            "AND length(btrim(error_message)) > 0"
            ")",
            name="ck_layout_import_rows_result_variant",
        ),
        Index(
            "ix_layout_import_rows_job_offset",
            "job_id",
            "byte_offset_end",
        ),
    )

    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    line_number: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    byte_offset_end: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sequence_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cells: Mapped[list[int] | None] = mapped_column(
        ARRAY(SmallInteger, dimensions=1),
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class LayoutImportNormalizedRowModel(Base):
    __tablename__ = "layout_import_normalized_rows"
    __table_args__ = (
        CheckConstraint(
            "line_number > 0",
            name="ck_layout_import_normalized_rows_line_positive",
        ),
        CheckConstraint(
            "sequence_number IS NULL OR sequence_number > 0",
            name="ck_layout_import_normalized_rows_sequence_positive",
        ),
        CheckConstraint(
            "cells IS NULL OR cardinality(cells) > 0",
            name="ck_layout_import_normalized_rows_cells_not_empty",
        ),
        CheckConstraint(
            "cells IS NULL OR (1 <= ALL(cells) AND 32767 >= ALL(cells))",
            name="ck_layout_import_normalized_rows_cells_code_range",
        ),
        CheckConstraint(
            "("
            "sequence_number IS NOT NULL AND cells IS NOT NULL "
            "AND signature IS NOT NULL AND length(signature) > 0 "
            "AND error_code IS NULL AND error_message IS NULL"
            ") OR ("
            "signature IS NULL AND error_code IS NOT NULL "
            "AND error_message IS NOT NULL "
            "AND length(btrim(error_code)) > 0 "
            "AND length(btrim(error_message)) > 0 "
            "AND ((sequence_number IS NULL AND cells IS NULL) "
            "OR (sequence_number IS NOT NULL AND cells IS NOT NULL))"
            ")",
            name="ck_layout_import_normalized_rows_result_variant",
        ),
        ForeignKeyConstraint(
            ["import_job_id", "line_number"],
            ["layout_import_rows.job_id", "layout_import_rows.line_number"],
            name="fk_layout_import_normalized_rows_raw_row",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_layout_import_normalized_rows_sequence",
            "validation_job_id",
            "sequence_number",
        ),
        Index(
            "ix_layout_import_normalized_rows_signature",
            "validation_job_id",
            "signature",
        ),
    )

    validation_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    line_number: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    import_job_id: Mapped[UUID] = mapped_column(nullable=False)
    rules_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("rules_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sequence_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cells: Mapped[list[int] | None] = mapped_column(
        ARRAY(SmallInteger, dimensions=1),
        nullable=True,
    )
    signature: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class DatasetVersionModel(Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (
        CheckConstraint(
            "version > 0",
            name="ck_dataset_versions_version_positive",
        ),
        CheckConstraint(
            "rows BETWEEN 1 AND 32767",
            name="ck_dataset_versions_rows_range",
        ),
        CheckConstraint(
            "columns BETWEEN 1 AND 32767",
            name="ck_dataset_versions_columns_range",
        ),
        CheckConstraint(
            "signature_cell_width BETWEEN 1 AND 5",
            name="ck_dataset_versions_signature_width_range",
        ),
        CheckConstraint(
            "expected_layout_count BETWEEN 1 AND 10000000",
            name="ck_dataset_versions_expected_layout_count_range",
        ),
        CheckConstraint(
            "layout_count >= 0",
            name="ck_dataset_versions_layout_count_nonnegative",
        ),
        CheckConstraint(
            "generation_seed BETWEEN 0 AND 2147483647",
            name="ck_dataset_versions_generation_seed_range",
        ),
        UniqueConstraint(
            "game_id",
            "version",
            name="uq_dataset_versions_game_version",
        ),
        Index(
            "uq_dataset_versions_source_job",
            "source_job_id",
            unique=True,
            postgresql_where=text("source_job_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    rows: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    columns: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    signature_cell_width: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )
    expected_layout_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    layout_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[DatasetVersionStatus] = mapped_column(
        Enum(
            DatasetVersionStatus,
            name="dataset_version_status",
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=DatasetVersionStatus.STAGING,
    )
    generation_seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    generator_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class LayoutModel(Base):
    __tablename__ = "layouts"
    __table_args__ = (
        CheckConstraint(
            "sequence_number > 0",
            name="ck_layouts_sequence_number_positive",
        ),
        CheckConstraint(
            "cardinality(cells) > 0",
            name="ck_layouts_cells_not_empty",
        ),
        CheckConstraint(
            "1 <= ALL(cells) AND 32767 >= ALL(cells)",
            name="ck_layouts_cells_mobile_code_range",
        ),
        UniqueConstraint(
            "dataset_version_id",
            "sequence_number",
            name="uq_layouts_dataset_sequence",
        ),
        Index(
            "ix_layouts_dataset_signature",
            "dataset_version_id",
            "signature",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    dataset_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    signature: Mapped[str] = mapped_column(String, nullable=False)
    cells: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger, dimensions=1),
        nullable=False,
    )
    source_board_id: Mapped[UUID | None] = mapped_column(nullable=True)


class LayoutPayoutModel(Base):
    __tablename__ = "layout_payouts"
    __table_args__ = (
        CheckConstraint(
            "sequence_number > 0",
            name="ck_layout_payouts_sequence_positive",
        ),
        CheckConstraint(
            "length(btrim(algorithm_version)) > 0",
            name="ck_layout_payouts_algorithm_not_blank",
        ),
        CheckConstraint(
            "total_payout >= 0",
            name="ck_layout_payouts_total_nonnegative",
        ),
        CheckConstraint(
            "audit_path IS NULL OR length(btrim(audit_path)) > 0",
            name="ck_layout_payouts_audit_path_not_blank",
        ),
        ForeignKeyConstraint(
            ["dataset_version_id", "sequence_number"],
            ["layouts.dataset_version_id", "layouts.sequence_number"],
            name="fk_layout_payouts_layout",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_layout_payouts_rules_version_id",
            "rules_version_id",
        ),
    )

    dataset_version_id: Mapped[UUID] = mapped_column(primary_key=True)
    rules_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("rules_versions.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    sequence_number: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
    )
    algorithm_version: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
    )
    total_payout: Mapped[int] = mapped_column(BigInteger, nullable=False)
    audit_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class MobileReleaseModel(Base):
    __tablename__ = "mobile_releases"
    __table_args__ = (
        CheckConstraint(
            "version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$'",
            name="ck_mobile_releases_version_safe",
        ),
        CheckConstraint(
            "length(btrim(algorithm_version)) > 0",
            name="ck_mobile_releases_algorithm_not_blank",
        ),
        CheckConstraint(
            "snapshot_schema_version > 0",
            name="ck_mobile_releases_schema_positive",
        ),
        CheckConstraint(
            "snapshot_checksum IS NULL OR snapshot_checksum ~ '^[0-9a-f]{64}$'",
            name="ck_mobile_releases_snapshot_checksum",
        ),
        CheckConstraint(
            "apk_checksum IS NULL OR apk_checksum ~ '^[0-9a-f]{64}$'",
            name="ck_mobile_releases_apk_checksum",
        ),
        CheckConstraint(
            "(snapshot_path IS NULL) = (snapshot_checksum IS NULL)",
            name="ck_mobile_releases_snapshot_complete",
        ),
        CheckConstraint(
            "(apk_path IS NULL) = (apk_checksum IS NULL)",
            name="ck_mobile_releases_apk_complete",
        ),
        UniqueConstraint(
            "version",
            name="uq_mobile_releases_version",
        ),
        UniqueConstraint(
            "build_job_id",
            name="uq_mobile_releases_build_job_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[MobileReleaseStatus] = mapped_column(
        Enum(
            MobileReleaseStatus,
            name="mobile_release_status",
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=MobileReleaseStatus.DRAFT,
    )
    algorithm_version: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    snapshot_schema_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    snapshot_path: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )
    snapshot_checksum: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    apk_path: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )
    apk_checksum: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    build_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    ready_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class MobileReleaseGameModel(Base):
    __tablename__ = "mobile_release_games"
    __table_args__ = (
        CheckConstraint(
            "layout_count > 0",
            name="ck_mobile_release_games_layout_count_positive",
        ),
        Index("ix_mobile_release_games_game_id", "game_id"),
    )

    mobile_release_id: Mapped[UUID] = mapped_column(
        ForeignKey("mobile_releases.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    dataset_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rules_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("rules_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    layout_count: Mapped[int] = mapped_column(BigInteger, nullable=False)


class ReviewBatchModel(Base):
    __tablename__ = "review_batches"
    __table_args__ = (
        CheckConstraint(
            "source_report_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_review_batches_source_report_sha256",
        ),
        CheckConstraint(
            "model_artifact_sha256 ~ '^[0-9a-f]{64}$' "
            "AND calibration_report_sha256 ~ '^[0-9a-f]{64}$' "
            "AND dataset_sha256 ~ '^[0-9a-f]{64}$' "
            "AND split_sha256 ~ '^[0-9a-f]{64}$' "
            "AND inventory_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_review_batches_provenance_sha256",
        ),
        CheckConstraint(
            "temperature > 0",
            name="ck_review_batches_temperature_positive",
        ),
        CheckConstraint(
            "item_count BETWEEN 1 AND 100",
            name="ck_review_batches_item_count",
        ),
        UniqueConstraint(
            "source_report_sha256",
            name="uq_review_batches_source_report_sha256",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_report_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    active_learning_version: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    model_artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    calibration_report_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    split_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    inventory_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    item_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    source_report: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ReviewItemModel(Base):
    __tablename__ = "review_items"
    __table_args__ = (
        CheckConstraint(
            "board_id ~ '^[0-9a-f]{64}$' AND source_image_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_review_items_identity_sha256",
        ),
        CheckConstraint(
            "selection_rank BETWEEN 1 AND 100",
            name="ck_review_items_selection_rank",
        ),
        CheckConstraint(
            "sequence_number > 0",
            name="ck_review_items_sequence_positive",
        ),
        CheckConstraint(
            r"length(btrim(board_relative_path)) > 0 "
            r"AND board_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'",
            name="ck_review_items_board_path_safe",
        ),
        CheckConstraint(
            "(status = 'pending' AND resolved_value IS NULL "
            "AND resolved_by IS NULL AND resolved_at IS NULL "
            "AND resolution_revision = 0) "
            "OR (status <> 'pending' AND resolved_by IS NOT NULL "
            "AND resolved_at IS NOT NULL AND resolution_revision > 0)",
            name="ck_review_items_resolution_state",
        ),
        UniqueConstraint(
            "review_batch_id",
            "board_id",
            name="uq_review_items_batch_board",
        ),
        UniqueConstraint(
            "review_batch_id",
            "selection_rank",
            name="uq_review_items_batch_rank",
        ),
        UniqueConstraint(
            "review_batch_id",
            "sequence_number",
            name="uq_review_items_batch_sequence",
        ),
        Index(
            "ix_review_items_batch_status_rank",
            "review_batch_id",
            "status",
            "selection_rank",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    review_batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("review_batches.id", ondelete="RESTRICT"),
        nullable=False,
    )
    board_id: Mapped[str] = mapped_column(String(64), nullable=False)
    selection_rank: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_image_id: Mapped[str] = mapped_column(String(200), nullable=False)
    source_image_checksum_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    source_group: Mapped[str] = mapped_column(String(200), nullable=False)
    board_relative_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[ReviewItemStatus] = mapped_column(
        Enum(
            ReviewItemStatus,
            name="review_item_status",
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=ReviewItemStatus.PENDING,
    )
    prediction_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    resolved_value: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    resolution_revision: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ReviewResolutionModel(Base):
    __tablename__ = "review_resolutions"
    __table_args__ = (
        CheckConstraint("revision > 0", name="ck_review_resolutions_revision_positive"),
        CheckConstraint(
            "command_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_review_resolutions_command_sha256",
        ),
        UniqueConstraint(
            "review_item_id",
            "revision",
            name="uq_review_resolutions_item_revision",
        ),
        UniqueConstraint(
            "review_item_id",
            "idempotency_key",
            name="uq_review_resolutions_item_idempotency",
        ),
        Index(
            "ix_review_resolutions_item_created",
            "review_item_id",
            "revision",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    review_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("review_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(nullable=False)
    action: Mapped[ReviewResolutionAction] = mapped_column(
        Enum(
            ReviewResolutionAction,
            name="review_resolution_action",
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
    )
    command_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    resolved_value: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    resolved_by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ReviewFeedbackExportModel(Base):
    __tablename__ = "review_feedback_exports"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_review_feedback_exports_version_positive"),
        CheckConstraint(
            "source_state_sha256 ~ '^[0-9a-f]{64}$' AND payload_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_review_feedback_exports_sha256",
        ),
        CheckConstraint(
            "sample_count >= 0 AND rejected_item_count >= 0",
            name="ck_review_feedback_exports_counts",
        ),
        UniqueConstraint(
            "game_id",
            "version",
            name="uq_review_feedback_exports_game_version",
        ),
        UniqueConstraint(
            "review_batch_id",
            "source_state_sha256",
            name="uq_review_feedback_exports_batch_state",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    review_batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("review_batches.id", ondelete="RESTRICT"),
        nullable=False,
    )
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_state_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected_item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ImageSymbolPredictionRevisionModel(Base):
    """Append-only predictions produced by explicit pending-only inference."""

    __tablename__ = "image_symbol_prediction_revisions"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(model_version)) > 0 AND model_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_symbol_prediction_revisions_model",
        ),
        CheckConstraint(
            "crop_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_symbol_prediction_revisions_crop_manifest",
        ),
        UniqueConstraint(
            "review_item_id",
            "model_checksum_sha256",
            "crop_manifest_checksum_sha256",
            name="uq_image_symbol_prediction_revision_snapshot",
        ),
        Index(
            "ix_image_symbol_prediction_revisions_item_created",
            "review_item_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"), nullable=False
    )
    review_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("image_review_items.id", ondelete="RESTRICT"), nullable=False
    )
    recognized_board_id: Mapped[UUID] = mapped_column(
        ForeignKey("recognized_boards.id", ondelete="RESTRICT"), nullable=False
    )
    source_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False
    )
    model_iteration_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("symbol_model_iterations.id", ondelete="RESTRICT")
    )
    model_version: Mapped[str] = mapped_column(String(150), nullable=False)
    model_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    crop_manifest_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    predictions: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ImageSequenceCanonicalModel(Base):
    """The immutable owner of one resolved sequence number for a game."""

    __tablename__ = "image_sequence_canonical"
    __table_args__ = (
        CheckConstraint(
            "sequence_number > 0 AND resolution_revision > 0 AND geometry_revision >= 0",
            name="ck_image_sequence_canonical_values",
        ),
        CheckConstraint(
            "status IN ('accepted', 'corrected')",
            name="ck_image_sequence_canonical_status",
        ),
        CheckConstraint(
            "source_checksum_sha256 ~ '^[0-9a-f]{64}$' "
            "AND board_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_sequence_canonical_checksums",
        ),
        UniqueConstraint(
            "game_id",
            "sequence_number",
            name="uq_image_sequence_canonical_game_sequence",
        ),
        Index(
            "ix_image_sequence_canonical_game_sequence",
            "game_id",
            "sequence_number",
        ),
    )

    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"), primary_key=True
    )
    sequence_number: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    review_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("image_review_items.id", ondelete="RESTRICT"), nullable=False
    )
    recognized_board_id: Mapped[UUID] = mapped_column(
        ForeignKey("recognized_boards.id", ondelete="RESTRICT"), nullable=False
    )
    import_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False
    )
    source_image_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_images.id", ondelete="RESTRICT"), nullable=False
    )
    source_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    board_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    resolution_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    geometry_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ImageBoardSearchCandidateModel(Base):
    """Compact current symbol evidence for a review item search candidate."""

    __tablename__ = "image_board_search_candidates"
    __table_args__ = (
        CheckConstraint(
            "sequence_number > 0",
            name="ck_image_board_search_candidates_sequence_positive",
        ),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'corrected')",
            name="ck_image_board_search_candidates_status",
        ),
        CheckConstraint(
            "board_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_board_search_candidates_checksum",
        ),
        CheckConstraint(
            "board_confidence BETWEEN 0 AND 1 AND sequence_confidence BETWEEN 0 AND 1 "
            "AND source_pixel_count > 0",
            name="ck_image_board_search_candidates_scores",
        ),
        CheckConstraint(
            "jsonb_typeof(primary_symbol_codes) = 'array' "
            "AND jsonb_array_length(primary_symbol_codes) = 15",
            name="ck_image_board_search_candidates_primary_cells",
        ),
        CheckConstraint(
            "jsonb_typeof(alternative_symbol_codes) = 'array' "
            "AND jsonb_array_length(alternative_symbol_codes) = 15",
            name="ck_image_board_search_candidates_alternative_cells",
        ),
        Index(
            "ix_image_board_search_candidates_game_sequence",
            "game_id",
            "sequence_number",
        ),
        Index(
            "ix_image_board_search_candidates_game_status_sequence",
            "game_id",
            "status",
            "sequence_number",
        ),
    )

    review_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("image_review_items.id", ondelete="CASCADE"), primary_key=True
    )
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"), nullable=False
    )
    import_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False
    )
    recognized_board_id: Mapped[UUID] = mapped_column(
        ForeignKey("recognized_boards.id", ondelete="RESTRICT"), nullable=False
    )
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    board_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    board_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    sequence_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source_pixel_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    primary_symbol_codes: Mapped[list[str | None]] = mapped_column(JSONB, nullable=False)
    alternative_symbol_codes: Mapped[list[list[str | None]]] = mapped_column(JSONB, nullable=False)
    primary_match_tokens: Mapped[list[str]] = mapped_column(ARRAY(String(80)), nullable=False)
    alternative_rank_1_match_tokens: Mapped[list[str]] = mapped_column(
        ARRAY(String(80)), nullable=False
    )
    alternative_rank_2_match_tokens: Mapped[list[str]] = mapped_column(
        ARRAY(String(80)), nullable=False
    )
    alternative_rank_3_match_tokens: Mapped[list[str]] = mapped_column(
        ARRAY(String(80)), nullable=False
    )
    alternative_rank_4_match_tokens: Mapped[list[str]] = mapped_column(
        ARRAY(String(80)), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ImageBoardSearchDocumentModel(Base):
    """Single current search owner for one game sequence number."""

    __tablename__ = "image_board_search_documents"
    __table_args__ = (
        CheckConstraint(
            "sequence_number > 0",
            name="ck_image_board_search_documents_sequence_positive",
        ),
        CheckConstraint(
            "selection_kind IN ('canonical', 'pending')",
            name="ck_image_board_search_documents_selection_kind",
        ),
        UniqueConstraint(
            "review_item_id",
            name="uq_image_board_search_documents_review_item",
        ),
        Index(
            "ix_image_board_search_documents_game_review",
            "game_id",
            "review_item_id",
        ),
    )

    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"), primary_key=True
    )
    sequence_number: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    review_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("image_board_search_candidates.review_item_id", ondelete="CASCADE"),
        nullable=False,
    )
    selection_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ImageBoardSearchProjectionStateModel(Base):
    """Readiness marker for a game's compact board-search projection."""

    __tablename__ = "image_board_search_projection_states"
    __table_args__ = (
        CheckConstraint(
            "status IN ('rebuilding', 'ready', 'failed')",
            name="ck_image_board_search_projection_states_status",
        ),
        CheckConstraint(
            "candidate_count >= 0 AND document_count >= 0 AND skipped_review_item_count >= 0",
            name="ck_image_board_search_projection_states_counts",
        ),
    )

    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    candidate_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    document_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    skipped_review_item_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    failure_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ImageSequenceAlternativeModel(Base):
    """A skipped source for an already canonical sequence."""

    __tablename__ = "image_sequence_alternatives"
    __table_args__ = (
        CheckConstraint(
            "sequence_number > 0 AND source_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_image_sequence_alternatives_values",
        ),
        UniqueConstraint(
            "game_id",
            "sequence_number",
            "source_checksum_sha256",
            "import_job_id",
            name="uq_image_sequence_alternatives_source",
        ),
        Index(
            "ix_image_sequence_alternatives_game_sequence",
            "game_id",
            "sequence_number",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"), nullable=False
    )
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    import_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False
    )
    source_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_relative_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    reason: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RepresentativeRankingCohortModel(Base):
    __tablename__ = "representative_ranking_cohorts"
    __table_args__ = (
        CheckConstraint(
            "iteration_number > 0 AND manifest_schema_version > 0",
            name="ck_representative_ranking_cohorts_versions",
        ),
        CheckConstraint(
            "manifest_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_representative_ranking_cohorts_checksum",
        ),
        CheckConstraint(
            "positive_count >= 0 AND pair_count >= 0 AND excluded_ambiguous_count >= 0 "
            "AND folder_count >= 0 AND group_count >= 0",
            name="ck_representative_ranking_cohorts_counts",
        ),
        UniqueConstraint(
            "game_id",
            "iteration_number",
            name="uq_representative_ranking_cohorts_iteration",
        ),
        UniqueConstraint(
            "game_id",
            "manifest_checksum_sha256",
            name="uq_representative_ranking_cohorts_manifest",
        ),
        Index("ix_representative_ranking_cohorts_game_created", "game_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"), nullable=False
    )
    iteration_number: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    positive_count: Mapped[int] = mapped_column(Integer, nullable=False)
    pair_count: Mapped[int] = mapped_column(Integer, nullable=False)
    excluded_ambiguous_count: Mapped[int] = mapped_column(Integer, nullable=False)
    folder_count: Mapped[int] = mapped_column(Integer, nullable=False)
    group_count: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_relative_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RepresentativeRankingIterationModel(Base):
    __tablename__ = "representative_ranking_iterations"
    __table_args__ = (
        CheckConstraint(
            "model_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_representative_ranking_iterations_checksum",
        ),
        CheckConstraint(
            "feature_version <> '' AND model_version <> '' AND btrim(status) <> ''",
            name="ck_representative_ranking_iterations_values",
        ),
        UniqueConstraint(
            "cohort_id",
            "model_checksum_sha256",
            name="uq_representative_ranking_iterations_model",
        ),
        Index("ix_representative_ranking_iterations_cohort_created", "cohort_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    cohort_id: Mapped[UUID] = mapped_column(
        ForeignKey("representative_ranking_cohorts.id", ondelete="RESTRICT"), nullable=False
    )
    feature_version: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    model_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    model_artifact_relative_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    report: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RepresentativeRankingActivationModel(Base):
    __tablename__ = "representative_ranking_activations"
    __table_args__ = (
        CheckConstraint(
            "action IN ('activate','rollback') AND activation_number > 0",
            name="ck_representative_ranking_activations_values",
        ),
        CheckConstraint(
            "command_sha256 ~ '^[0-9a-f]{64}$' AND btrim(actor) <> ''",
            name="ck_representative_ranking_activations_checksum",
        ),
        UniqueConstraint(
            "game_id",
            "activation_number",
            name="uq_representative_ranking_activations_number",
        ),
        UniqueConstraint(
            "game_id",
            "idempotency_key",
            name="uq_representative_ranking_activations_idempotency",
        ),
        Index("ix_representative_ranking_activations_game_created", "game_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"), nullable=False
    )
    iteration_id: Mapped[UUID] = mapped_column(
        ForeignKey("representative_ranking_iterations.id", ondelete="RESTRICT"), nullable=False
    )
    previous_iteration_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("representative_ranking_iterations.id", ondelete="RESTRICT")
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    activation_number: Mapped[int] = mapped_column(Integer, nullable=False)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[UUID] = mapped_column(nullable=False)
    command_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RemoteManualSelectionSessionModel(Base):
    __tablename__ = "remote_manual_selection_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','active','completed','expired','revoked')",
            name="ck_rms_sessions_status",
        ),
        CheckConstraint(
            "revision >= 0 AND failed_attempts BETWEEN 0 AND 5",
            name="ck_rms_sessions_counters",
        ),
        CheckConstraint(
            "length(btrim(host_base_path)) > 0 AND length(btrim(display_name)) > 0",
            name="ck_rms_sessions_names",
        ),
        CheckConstraint(
            "updated_at >= created_at AND expires_at > created_at",
            name="ck_rms_sessions_timestamps",
        ),
        CheckConstraint(
            "(code_salt IS NULL AND code_hash IS NULL) OR "
            "(code_salt IS NOT NULL AND code_hash IS NOT NULL "
            "AND octet_length(code_salt) = 16 AND octet_length(code_hash) = 32)",
            name="ck_rms_sessions_code_hash",
        ),
        CheckConstraint(
            "(token_hash IS NULL AND token_expires_at IS NULL) OR "
            "(token_hash IS NOT NULL AND octet_length(token_hash) = 32 "
            "AND token_expires_at IS NOT NULL)",
            name="ck_rms_sessions_token_hash",
        ),
        CheckConstraint(
            "(writer_client_instance_id IS NULL AND writer_lease_token IS NULL "
            "AND writer_lease_expires_at IS NULL) OR "
            "(writer_client_instance_id IS NOT NULL AND writer_lease_token IS NOT NULL "
            "AND writer_lease_expires_at IS NOT NULL)",
            name="ck_rms_sessions_writer_lease",
        ),
        UniqueConstraint("id", "base_binding_id", name="uq_rms_sessions_binding_scope"),
        Index("ix_rms_sessions_status_expiry", "status", "expires_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    base_binding_id: Mapped[UUID] = mapped_column(nullable=False)
    host_base_path: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    revision: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    code_salt: Mapped[bytes | None] = mapped_column(LargeBinary(16), nullable=True)
    code_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32), nullable=True)
    token_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32), nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_attempts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    writer_client_instance_id: Mapped[UUID | None] = mapped_column(nullable=True)
    writer_lease_token: Mapped[UUID | None] = mapped_column(nullable=True)
    writer_lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RemoteManualSelectionCollectionModel(Base):
    __tablename__ = "remote_manual_selection_collections"
    __table_args__ = (
        CheckConstraint("status IN ('active','completed')", name="ck_rms_collections_status"),
        CheckConstraint(
            "revision >= 0 AND length(btrim(name)) > 0 AND length(btrim(normalized_name)) > 0",
            name="ck_rms_collections_values",
        ),
        UniqueConstraint("session_id", "normalized_name", name="uq_rms_collections_session_name"),
        UniqueConstraint(
            "id", "session_id", "normalized_name", name="uq_rms_collections_scope_name"
        ),
        Index("ix_rms_collections_session_status", "session_id", "status", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("remote_manual_selection_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    revision: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RemoteManualSelectionBatchModel(Base):
    __tablename__ = "remote_manual_selection_batches"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','indexing','active','finalizing','completed','failed','abandoned')",
            name="ck_rms_batches_status",
        ),
        CheckConstraint("direction IN ('ascending','descending')", name="ck_rms_batches_direction"),
        CheckConstraint(
            "source_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$' AND "
            "(final_manifest_checksum_sha256 IS NULL OR "
            "final_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$')",
            name="ck_rms_batches_checksums",
        ),
        CheckConstraint(
            "first_layout > 0 AND cursor_index >= 0 AND server_revision >= 0 "
            "AND last_client_sequence >= 0 AND total_file_count >= 0 "
            "AND selected_file_count >= 0 AND transferred_file_count >= 0 "
            "AND selected_file_count <= total_file_count "
            "AND transferred_file_count <= selected_file_count",
            name="ck_rms_batches_counters",
        ),
        CheckConstraint(
            "length(btrim(name)) > 0 AND length(btrim(normalized_name)) > 0 "
            "AND length(btrim(normalized_collection_name)) > 0",
            name="ck_rms_batches_names",
        ),
        ForeignKeyConstraint(
            ["session_id", "base_binding_id"],
            [
                "remote_manual_selection_sessions.id",
                "remote_manual_selection_sessions.base_binding_id",
            ],
            name="fk_rms_batches_session_binding",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["collection_id", "session_id", "normalized_collection_name"],
            [
                "remote_manual_selection_collections.id",
                "remote_manual_selection_collections.session_id",
                "remote_manual_selection_collections.normalized_name",
            ],
            name="fk_rms_batches_collection_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "session_id", name="uq_rms_batches_scope"),
        UniqueConstraint(
            "base_binding_id",
            "normalized_collection_name",
            "normalized_name",
            name="uq_rms_batches_base_mapping",
        ),
        Index("ix_rms_batches_session_status", "session_id", "status", "updated_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(nullable=False)
    collection_id: Mapped[UUID] = mapped_column(nullable=False)
    base_binding_id: Mapped[UUID] = mapped_column(nullable=False)
    normalized_collection_name: Mapped[str] = mapped_column(String(200), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_manifest_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    first_layout: Mapped[int] = mapped_column(BigInteger, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    cursor_index: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    server_revision: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    last_client_sequence: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    final_manifest_checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    total_file_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    selected_file_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    transferred_file_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RemoteManualSelectionFileModel(Base):
    __tablename__ = "remote_manual_selection_files"
    __table_args__ = (
        CheckConstraint(
            "status IN ('discovered','unselected','selection_queued','upload_queued',"
            "'uploading','stored_temporarily','verified','materialized','synced',"
            "'deselect_pending','removed','failed','retrying')",
            name="ck_rms_files_status",
        ),
        CheckConstraint(
            "source_index >= 0 AND size_bytes >= 0 AND last_modified_ms >= 0 "
            "AND selection_generation >= 0 AND last_server_revision >= 0",
            name="ck_rms_files_counters",
        ),
        CheckConstraint(
            r"length(relative_path) > 0 AND relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'",
            name="ck_rms_files_relative_path",
        ),
        CheckConstraint(
            "(range_start IS NULL AND range_end IS NULL) OR "
            "(range_start > 0 AND range_end = range_start + 8)",
            name="ck_rms_files_range",
        ),
        CheckConstraint(
            "host_checksum_sha256 IS NULL OR host_checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_rms_files_checksum",
        ),
        CheckConstraint(
            "status <> 'synced' OR (desired_selected AND range_start IS NOT NULL "
            "AND output_name IS NOT NULL AND host_checksum_sha256 IS NOT NULL "
            "AND final_relative_path IS NOT NULL)",
            name="ck_rms_files_synced",
        ),
        ForeignKeyConstraint(
            ["batch_id", "session_id"],
            ["remote_manual_selection_batches.id", "remote_manual_selection_batches.session_id"],
            name="fk_rms_files_batch_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "batch_id", "session_id", name="uq_rms_files_scope"),
        UniqueConstraint("batch_id", "source_index", name="uq_rms_files_source_index"),
        UniqueConstraint("batch_id", "relative_path", name="uq_rms_files_relative_path"),
        Index("ix_rms_files_delta", "batch_id", "last_server_revision", "source_index", "id"),
        Index("ix_rms_files_status", "batch_id", "status", "source_index", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(nullable=False)
    batch_id: Mapped[UUID] = mapped_column(nullable=False)
    source_index: Mapped[int] = mapped_column(BigInteger, nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_modified_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    desired_selected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    selection_generation: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    range_start: Mapped[int | None] = mapped_column(BigInteger)
    range_end: Mapped[int | None] = mapped_column(BigInteger)
    output_name: Mapped[str | None] = mapped_column(String(255))
    host_checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    temp_relative_path: Mapped[str | None] = mapped_column(Text)
    final_relative_path: Mapped[str | None] = mapped_column(Text)
    last_server_revision: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RemoteManualSelectionOperationModel(Base):
    __tablename__ = "remote_manual_selection_operations"
    __table_args__ = (
        CheckConstraint(
            "operation_type IN ('viewed','select','skip','deselect','undo')",
            name="ck_rms_operations_type",
        ),
        CheckConstraint(
            "status IN ('queued','sending','applied','retry','superseded','conflict','rejected')",
            name="ck_rms_operations_status",
        ),
        CheckConstraint(
            "client_sequence > 0 AND expected_server_revision >= 0 "
            "AND selection_generation >= 0 AND applied_server_revision >= 0 "
            "AND visible_milliseconds >= 0 AND range_start > 0 "
            "AND range_end = range_start + 8",
            name="ck_rms_operations_counters",
        ),
        CheckConstraint(
            "command_checksum_sha256 ~ '^[0-9a-f]{64}$' AND "
            "(image_checksum_sha256 IS NULL OR image_checksum_sha256 ~ '^[0-9a-f]{64}$')",
            name="ck_rms_operations_checksums",
        ),
        CheckConstraint(
            "(operation_type = 'skip' AND file_id IS NULL) OR "
            "(operation_type <> 'skip' AND file_id IS NOT NULL)",
            name="ck_rms_operations_file_scope",
        ),
        CheckConstraint(
            "operation_type <> 'select' OR (image_path IS NOT NULL "
            "AND source_index IS NOT NULL AND output_name IS NOT NULL)",
            name="ck_rms_operations_select_payload",
        ),
        CheckConstraint(
            "operation_type NOT IN ('deselect','undo') OR target_operation_id IS NOT NULL",
            name="ck_rms_operations_target",
        ),
        ForeignKeyConstraint(
            ["batch_id", "session_id"],
            ["remote_manual_selection_batches.id", "remote_manual_selection_batches.session_id"],
            name="fk_rms_operations_batch_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["file_id", "batch_id", "session_id"],
            [
                "remote_manual_selection_files.id",
                "remote_manual_selection_files.batch_id",
                "remote_manual_selection_files.session_id",
            ],
            name="fk_rms_operations_file_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["target_operation_id", "batch_id", "session_id"],
            [
                "remote_manual_selection_operations.id",
                "remote_manual_selection_operations.batch_id",
                "remote_manual_selection_operations.session_id",
            ],
            name="fk_rms_operations_target_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "batch_id", "session_id", name="uq_rms_operations_scope"),
        UniqueConstraint(
            "batch_id",
            "client_instance_id",
            "client_sequence",
            name="uq_rms_operations_client_sequence",
        ),
        Index(
            "uq_rms_operations_applied_revision",
            "batch_id",
            "applied_server_revision",
            unique=True,
            postgresql_where=text("status = 'applied'"),
        ),
        Index("ix_rms_operations_delta", "batch_id", "client_sequence", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    session_id: Mapped[UUID] = mapped_column(nullable=False)
    batch_id: Mapped[UUID] = mapped_column(nullable=False)
    file_id: Mapped[UUID | None] = mapped_column(nullable=True)
    client_instance_id: Mapped[UUID] = mapped_column(nullable=False)
    client_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_server_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    operation_type: Mapped[str] = mapped_column(String(16), nullable=False)
    selection_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    range_start: Mapped[int] = mapped_column(BigInteger, nullable=False)
    range_end: Mapped[int] = mapped_column(BigInteger, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    image_path: Mapped[str | None] = mapped_column(Text)
    source_index: Mapped[int | None] = mapped_column(BigInteger)
    image_checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    output_name: Mapped[str | None] = mapped_column(String(255))
    visible_milliseconds: Mapped[int] = mapped_column(BigInteger, nullable=False)
    decoded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    target_operation_id: Mapped[UUID | None] = mapped_column(nullable=True)
    command_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    applied_server_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    outcome_code: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RemoteManualSelectionTransferModel(Base):
    __tablename__ = "remote_manual_selection_transfers"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','uploading','stored_temp','verified','materialized',"
            "'cancelled','failed','retrying')",
            name="ck_rms_transfers_status",
        ),
        CheckConstraint(
            "generation >= 0 AND attempt > 0 AND declared_bytes >= 0 "
            "AND received_bytes >= 0 AND received_bytes <= declared_bytes",
            name="ck_rms_transfers_counters",
        ),
        CheckConstraint(
            "(declared_checksum_sha256 IS NULL OR "
            "declared_checksum_sha256 ~ '^[0-9a-f]{64}$') AND "
            "(verified_checksum_sha256 IS NULL OR "
            "verified_checksum_sha256 ~ '^[0-9a-f]{64}$')",
            name="ck_rms_transfers_checksums",
        ),
        ForeignKeyConstraint(
            ["file_id", "batch_id", "session_id"],
            [
                "remote_manual_selection_files.id",
                "remote_manual_selection_files.batch_id",
                "remote_manual_selection_files.session_id",
            ],
            name="fk_rms_transfers_file_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "file_id", "batch_id", "session_id", name="uq_rms_transfers_scope"),
        UniqueConstraint("file_id", "generation", "attempt", name="uq_rms_transfers_attempt"),
        Index("ix_rms_transfers_queue", "status", "retry_at", "created_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(nullable=False)
    batch_id: Mapped[UUID] = mapped_column(nullable=False)
    file_id: Mapped[UUID] = mapped_column(nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    declared_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    received_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    declared_checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    verified_checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    temp_relative_path: Mapped[str | None] = mapped_column(Text)
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RemoteManualSelectionHostActionModel(Base):
    __tablename__ = "remote_manual_selection_host_actions"
    __table_args__ = (
        CheckConstraint(
            "action_type IN ('verify','materialize','remove','reconcile')",
            name="ck_rms_host_actions_type",
        ),
        CheckConstraint(
            "status IN ('queued','processing','completed','retry','failed','superseded')",
            name="ck_rms_host_actions_status",
        ),
        CheckConstraint("generation >= 0 AND attempt >= 0", name="ck_rms_host_actions_counters"),
        CheckConstraint(
            "(lease_owner IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL) OR "
            "(length(btrim(lease_owner)) > 0 AND lease_token IS NOT NULL "
            "AND lease_expires_at IS NOT NULL)",
            name="ck_rms_host_actions_lease",
        ),
        ForeignKeyConstraint(
            ["file_id", "batch_id", "session_id"],
            [
                "remote_manual_selection_files.id",
                "remote_manual_selection_files.batch_id",
                "remote_manual_selection_files.session_id",
            ],
            name="fk_rms_host_actions_file_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
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
        Index(
            "uq_rms_host_actions_active",
            "file_id",
            "generation",
            "action_type",
            unique=True,
            postgresql_where=text("status IN ('queued','processing','retry')"),
        ),
        Index("ix_rms_host_actions_queue", "status", "next_attempt_at", "created_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(nullable=False)
    batch_id: Mapped[UUID] = mapped_column(nullable=False)
    file_id: Mapped[UUID] = mapped_column(nullable=False)
    transfer_id: Mapped[UUID | None] = mapped_column(nullable=True)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(200))
    lease_token: Mapped[UUID | None] = mapped_column(nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RemoteManualSelectionAuditEventModel(Base):
    __tablename__ = "remote_manual_selection_audit_events"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(event_type)) > 0 AND length(btrim(actor)) > 0 "
            "AND length(btrim(outcome_code)) > 0",
            name="ck_rms_audit_values",
        ),
        CheckConstraint("jsonb_typeof(payload) = 'object'", name="ck_rms_audit_payload"),
        ForeignKeyConstraint(
            ["batch_id", "session_id"],
            ["remote_manual_selection_batches.id", "remote_manual_selection_batches.session_id"],
            name="fk_rms_audit_batch_scope",
            ondelete="RESTRICT",
        ),
        Index("ix_rms_audit_session_created", "session_id", "created_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("remote_manual_selection_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    batch_id: Mapped[UUID | None] = mapped_column(nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    outcome_code: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
