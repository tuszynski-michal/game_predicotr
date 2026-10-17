"""Game-owned frozen targets and acceptance receipts (manifest v8)."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from game_predictor_api.storage.metadata import Base


class HistoricalGridAcceptanceOperationModel(Base):
    __tablename__ = "historical_grid_acceptance_operations"
    __table_args__ = (UniqueConstraint("game_id", "idempotency_key"),)

    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    idempotency_key: Mapped[UUID] = mapped_column(nullable=False)
    command_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    phase: Mapped[str] = mapped_column(String(20), nullable=False)
    preparation_state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    preview_after_source_id: Mapped[UUID | None] = mapped_column(nullable=True)
    preview_cursor: Mapped[int] = mapped_column(BigInteger, default=0)
    run_cursor: Mapped[int] = mapped_column(BigInteger, default=0)
    revision_count: Mapped[int] = mapped_column(BigInteger, default=0)
    eligible_count: Mapped[int] = mapped_column(BigInteger, default=0)
    accepted_count: Mapped[int] = mapped_column(BigInteger, default=0)
    skipped_count: Mapped[int] = mapped_column(BigInteger, default=0)
    preview_reasons: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    run_reasons: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    confirm_key: Mapped[UUID | None] = mapped_column(nullable=True)
    confirm_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)


class HistoricalGridAcceptanceTargetModel(Base):
    __tablename__ = "historical_grid_acceptance_targets"
    __table_args__ = (UniqueConstraint("game_id", "operation_id", "source_image_id"),)

    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    operation_id: Mapped[UUID] = mapped_column(primary_key=True)
    ordinal: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_image_id: Mapped[UUID] = mapped_column(nullable=False)
    revision_id: Mapped[UUID | None] = mapped_column(nullable=True)
    revision_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fingerprint_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    reasons: Mapped[list[str]] = mapped_column(JSONB, nullable=False)


class HistoricalGridAcceptanceReceiptModel(Base):
    """A source receipt is also its acceptance event; no event is minted on replay."""

    __tablename__ = "historical_grid_acceptance_receipts"
    __table_args__ = (UniqueConstraint("game_id", "idempotency_key"),)

    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    operation_id: Mapped[UUID] = mapped_column(primary_key=True)
    ordinal: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    idempotency_key: Mapped[UUID] = mapped_column(nullable=False)
    command_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_image_id: Mapped[UUID] = mapped_column(nullable=False)
    revision_id: Mapped[UUID | None] = mapped_column(nullable=True)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    reasons: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
