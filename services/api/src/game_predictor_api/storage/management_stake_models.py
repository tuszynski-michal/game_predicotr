"""Public metadata only; no game-store ownership or image blobs."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from game_predictor_api.storage.management_models import now
from game_predictor_api.storage.metadata import Base


class ManagementSearchContextModel(Base):
    __tablename__ = "management_search_contexts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["machine_id", "game_id"],
            ["public.management_assignments.machine_id", "public.management_assignments.game_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("stake_grosze IN (2000,1000,600,400,200,120)"),
        {"schema": "public"},
    )
    id: Mapped[UUID] = mapped_column(
        ForeignKey("public.management_operations.operation_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    machine_id: Mapped[UUID] = mapped_column()
    game_id: Mapped[UUID] = mapped_column()
    stake_grosze: Mapped[int] = mapped_column(Integer)
    actor: Mapped[str] = mapped_column(String(200))
    query: Mapped[dict[str, object]] = mapped_column(JSON)
    sequence_numbers: Mapped[list[int]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ManagementResultVersionModel(Base):
    __tablename__ = "management_result_versions"
    __table_args__ = (UniqueConstraint("game_id", "content_sha256"), {"schema": "public"})
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id", ondelete="RESTRICT"))
    content_sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    summary: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ManagementStakeSlotModel(Base):
    __tablename__ = "management_stake_slots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["machine_id", "game_id"],
            ["public.management_assignments.machine_id", "public.management_assignments.game_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("stake_grosze IN (2000,1000,600,400,200,120)"),
        CheckConstraint("revision >= 1"),
        CheckConstraint("spin_count IS NULL OR spin_count BETWEEN 1 AND 100000"),
        CheckConstraint("start_sequence_number IS NULL OR start_sequence_number >= 1"),
        CheckConstraint(
            "(result_version_id IS NULL AND search_context_id IS NULL "
            "AND start_sequence_number IS NULL AND spin_count IS NULL) OR "
            "(result_version_id IS NOT NULL AND search_context_id IS NOT NULL "
            "AND start_sequence_number IS NOT NULL AND spin_count IS NOT NULL)"
        ),
        {"schema": "public"},
    )
    machine_id: Mapped[UUID] = mapped_column(primary_key=True)
    game_id: Mapped[UUID] = mapped_column(primary_key=True)
    stake_grosze: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    search_context_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("public.management_search_contexts.id", ondelete="RESTRICT")
    )
    start_sequence_number: Mapped[int | None] = mapped_column(Integer)
    spin_count: Mapped[int | None] = mapped_column(Integer)
    pinned_spin_positions: Mapped[list[int]] = mapped_column(JSON, default=list)
    pinned_points: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    result_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("public.management_result_versions.id", ondelete="RESTRICT"), index=True
    )
    stale_error_code: Mapped[str | None] = mapped_column(String(100))
    saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
