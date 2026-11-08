"""Retained content annotations; no geometry revision or role assignment columns."""

from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .metadata import Base


class GridCellContentRevisionModel(Base):
    __tablename__ = "grid_cell_content_revisions"
    __table_args__ = (
        CheckConstraint("revision>=1 AND position_index BETWEEN 0 AND 8"),
        CheckConstraint("live_source_image_id IS NULL OR live_source_image_id=source_id"),
        CheckConstraint("pixel_sha256 ~ '^[0-9a-f]{64}$' AND document_sha256 ~ '^[0-9a-f]{64}$'"),
        Index("ix_content_source", "game_id", "source_id"),
        Index("ix_content_live_source", "game_id", "live_source_image_id"),
    )
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    pixel_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    position_index: Mapped[int] = mapped_column(primary_key=True)
    revision: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[UUID] = mapped_column()
    live_source_image_id: Mapped[UUID | None] = mapped_column(ForeignKey("source_images.id"))
    document_sha256: Mapped[str] = mapped_column(String(64))
    document: Mapped[dict[str, Any]] = mapped_column(JSONB)
    oracle: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))


class GridCellContentSessionModel(Base):
    __tablename__ = "grid_cell_content_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["game_id", "cohort_id"], ["grid_training_cohorts.game_id", "grid_training_cohorts.id"]
        ),
        CheckConstraint("revision>=1 AND phase IN ('pass1','pass2','frozen')"),
    )
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    cohort_id: Mapped[UUID] = mapped_column()
    revision: Mapped[int] = mapped_column(default=1)
    phase: Mapped[str] = mapped_column(String(16), default="pass1")
    document: Mapped[dict[str, Any]] = mapped_column(JSONB)
    progress: Mapped[dict[str, Any]] = mapped_column(JSONB)
    report: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))


class GridCellContentCommandModel(Base):
    __tablename__ = "grid_cell_content_commands"
    __table_args__ = (CheckConstraint("command_sha256 ~ '^[0-9a-f]{64}$'"),)
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    idempotency_key: Mapped[UUID] = mapped_column(primary_key=True)
    command_sha256: Mapped[str] = mapped_column(String(64))
    document: Mapped[dict[str, Any]] = mapped_column(JSONB)
