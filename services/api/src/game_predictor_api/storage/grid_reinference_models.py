"""Game-owned reinference state, immutable membership and terminal target receipts."""

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from game_predictor_api.storage.metadata import Base


class GridReinferenceOperationModel(Base):
    __tablename__ = "grid_reinference_operations"
    __table_args__ = (
        UniqueConstraint("game_id", "idempotency_key"),
        UniqueConstraint("game_id", "job_id"),
        ForeignKeyConstraint(
            ["game_id", "job_id"], ["jobs.game_id", "jobs.id"], ondelete="RESTRICT"
        ),
        CheckConstraint("command_sha256 ~ '^[0-9a-f]{64}$'"),
        CheckConstraint("jsonb_typeof(document) = 'object'"),
    )

    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    idempotency_key: Mapped[UUID] = mapped_column(nullable=False)
    command_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    job_id: Mapped[UUID] = mapped_column(nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class GridReinferenceSourceModel(Base):
    __tablename__ = "grid_reinference_sources"
    __table_args__ = (
        UniqueConstraint("game_id", "operation_id", "source_image_id"),
        UniqueConstraint("game_id", "operation_id", "ordinal", "source_image_id"),
        ForeignKeyConstraint(
            ["game_id", "operation_id"],
            ["grid_reinference_operations.game_id", "grid_reinference_operations.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("ordinal > 0"),
        CheckConstraint("live_source_image_id IS NULL OR live_source_image_id = source_image_id"),
        CheckConstraint("jsonb_typeof(document) = 'object'"),
        CheckConstraint("checkpoint IS NULL OR jsonb_typeof(checkpoint) = 'object'"),
    )

    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    operation_id: Mapped[UUID] = mapped_column(primary_key=True)
    ordinal: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # Frozen occurrence identity survives an explicitly confirmed source cleanup.
    source_image_id: Mapped[UUID] = mapped_column(nullable=False)
    # The V2 parent enforces (game_id, live_source_image_id). The legacy source
    # metadata mapping has no game_id column; routing supplies that scope.
    live_source_image_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_images.id", ondelete="RESTRICT"), nullable=True
    )
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    checkpoint: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )


class GridReinferenceTargetModel(Base):
    __tablename__ = "grid_reinference_targets"
    __table_args__ = (
        UniqueConstraint("game_id", "target_result_id"),
        UniqueConstraint("game_id", "operation_id", "source_image_id", "position_index"),
        ForeignKeyConstraint(
            ["game_id", "operation_id", "source_ordinal", "source_image_id"],
            [
                "grid_reinference_sources.game_id",
                "grid_reinference_sources.operation_id",
                "grid_reinference_sources.ordinal",
                "grid_reinference_sources.source_image_id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("source_ordinal > 0 AND position_index BETWEEN 0 AND 8"),
        CheckConstraint("ordinal = source_ordinal * 10 + position_index + 1"),
        CheckConstraint("fingerprint_sha256 ~ '^[0-9a-f]{64}$'"),
        CheckConstraint("jsonb_typeof(snapshot) = 'object'"),
        CheckConstraint(
            "(outcome IS NULL AND result IS NULL) OR "
            "(outcome IS NOT NULL AND result IS NOT NULL "
            "AND jsonb_typeof(result) = 'object')"
        ),
    )

    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    operation_id: Mapped[UUID] = mapped_column(primary_key=True)
    ordinal: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_ordinal: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_image_id: Mapped[UUID] = mapped_column(nullable=False)
    position_index: Mapped[int] = mapped_column(Integer, nullable=False)
    target_result_id: Mapped[UUID] = mapped_column(nullable=False, default=uuid4)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    fingerprint_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
