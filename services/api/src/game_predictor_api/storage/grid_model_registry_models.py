"""Shared geometry control catalogue and game catalog assignments (public only)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from game_predictor_api.storage.metadata import Base


class GridModelFamilyModel(Base):
    __tablename__ = "grid_model_families"
    __table_args__ = (UniqueConstraint("code"), {"schema": "public"})
    id: Mapped[UUID] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64))
    descriptor_json: Mapped[str] = mapped_column(Text)


class GridModelVersionModel(Base):
    __tablename__ = "grid_model_versions"
    __table_args__ = (
        UniqueConstraint("family_id", "version"),
        CheckConstraint("length(manifest_sha256) = 64"),
        {"schema": "public"},
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    family_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.grid_model_families.id", ondelete="RESTRICT")
    )
    version: Mapped[str] = mapped_column(String(64))
    base_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("public.grid_model_versions.id", ondelete="RESTRICT")
    )
    manifest_json: Mapped[str] = mapped_column(Text)
    manifest_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GridModelRegistrationReceiptModel(Base):
    __tablename__ = "grid_model_registration_receipts"
    __table_args__ = ({"schema": "public"},)
    idempotency_key: Mapped[UUID] = mapped_column(primary_key=True)
    command_sha256: Mapped[str] = mapped_column(String(64))
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.grid_model_versions.id", ondelete="RESTRICT")
    )


class GridModelVersionEventModel(Base):
    __tablename__ = "grid_model_version_events"
    __table_args__ = (UniqueConstraint("version_id", "kind"), {"schema": "public"})
    id: Mapped[UUID] = mapped_column(primary_key=True)
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.grid_model_versions.id", ondelete="RESTRICT")
    )
    kind: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GameGridModelAssignmentModel(Base):
    __tablename__ = "game_grid_model_assignments"
    __table_args__ = (
        UniqueConstraint("game_id", "revision"),
        CheckConstraint("revision > 0"),
        {"schema": "public"},
    )
    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), primary_key=True
    )
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.grid_model_versions.id", ondelete="RESTRICT")
    )
    revision: Mapped[int] = mapped_column()


class GameGridModelAssignmentEventModel(Base):
    __tablename__ = "game_grid_model_assignment_events"
    __table_args__ = (
        UniqueConstraint("game_id", "idempotency_key"),
        ForeignKeyConstraint(
            ["game_id"], ["public.game_grid_model_assignments.game_id"], ondelete="CASCADE"
        ),
        {"schema": "public"},
    )
    game_id: Mapped[UUID] = mapped_column(primary_key=True)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    idempotency_key: Mapped[UUID] = mapped_column()
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.grid_model_versions.id", ondelete="RESTRICT")
    )
    revision: Mapped[int] = mapped_column()
    kind: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
