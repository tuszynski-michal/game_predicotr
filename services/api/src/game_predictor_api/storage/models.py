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
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from game_predictor_api.domain.catalog import GameStatus, SymbolStatus
from game_predictor_api.domain.datasets import DatasetVersionStatus
from game_predictor_api.domain.jobs import JobStatus, JobType
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.storage.metadata import Base


def _enum_values(
    enum_type: (
        type[DatasetVersionStatus]
        | type[GameStatus]
        | type[JobStatus]
        | type[JobType]
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
