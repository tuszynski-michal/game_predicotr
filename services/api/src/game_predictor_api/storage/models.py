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
from game_predictor_api.domain.jobs import JobStatus, JobType
from game_predictor_api.domain.mobile_releases import MobileReleaseStatus
from game_predictor_api.domain.reviews import (
    ReviewItemStatus,
    ReviewResolutionAction,
)
from game_predictor_api.domain.rules import RulesVersionStatus
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
    ),
) -> list[str]:
    return [member.value for member in enum_type]


class GameModel(Base):
    __tablename__ = "games"
    __table_args__ = (UniqueConstraint("code", name="uq_games_code"),)

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
            "(status = 'processing' AND execution_slot = 1 "
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
        UniqueConstraint(
            "job_id",
            "order_index",
            name="uq_image_import_job_files_job_order",
        ),
        Index(
            "ix_image_import_job_files_execution",
            "file_execution_key",
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
