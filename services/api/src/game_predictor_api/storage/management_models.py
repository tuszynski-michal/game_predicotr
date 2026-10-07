"""Shared control-plane records. Archives and detachments never delete history."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from game_predictor_api.storage.metadata import Base


def now() -> datetime:
    return datetime.now(UTC)


class ManagementPointModel(Base):
    __tablename__ = "management_points"
    __table_args__ = (CheckConstraint("revision >= 1"), {"schema": "public"})
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(200))
    street: Mapped[str] = mapped_column(String(200))
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ManagementMachineModel(Base):
    __tablename__ = "management_machines"
    __table_args__ = (CheckConstraint("revision >= 1"), {"schema": "public"})
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    point_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.management_points.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ManagementAssignmentModel(Base):
    __tablename__ = "management_assignments"
    __table_args__ = {"schema": "public"}
    machine_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.management_machines.id", ondelete="RESTRICT"), primary_key=True
    )
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"), primary_key=True
    )
    attached: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ManagementOperationModel(Base):
    __tablename__ = "management_operations"
    __table_args__ = {"schema": "public"}
    operation_id: Mapped[UUID] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(200))
    request_checksum: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ManagementJournalModel(Base):
    __tablename__ = "management_journal"
    __table_args__ = {"schema": "public"}
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    operation_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.management_operations.operation_id", ondelete="RESTRICT"), index=True
    )
    actor: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(80))
    point_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.management_points.id", ondelete="RESTRICT"), index=True
    )
    machine_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("public.management_machines.id", ondelete="RESTRICT"), index=True
    )
    game_id: Mapped[UUID | None] = mapped_column(ForeignKey("games.id", ondelete="RESTRICT"))
    stake_grosze: Mapped[int | None] = mapped_column(Integer)
    before_result_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("public.management_result_versions.id", ondelete="RESTRICT")
    )
    after_result_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("public.management_result_versions.id", ondelete="RESTRICT")
    )
    before: Mapped[dict[str, object]] = mapped_column(JSON)
    after: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
