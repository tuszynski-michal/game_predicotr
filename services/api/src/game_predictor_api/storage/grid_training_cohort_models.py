"""Game-owned immutable geometry training evidence and replay receipts."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from game_predictor_api.storage.metadata import Base


class GridTrainingCohortModel(Base):
    __tablename__ = "grid_training_cohorts"
    __table_args__ = (
        CheckConstraint("revision>=1"),
        CheckConstraint(
            "status IN ('preparing','preview_ready','materializing','ready_to_freeze',"
            "'frozen','failed','canceled')"
        ),
        CheckConstraint("jsonb_typeof(document)='object' AND jsonb_typeof(summary)='object'"),
    )
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    revision: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(24), default="preparing")
    document: Mapped[dict[str, Any]] = mapped_column(JSONB)
    manifest_path: Mapped[str | None] = mapped_column(String(1000))
    manifest_sha256: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GridTrainingCohortMemberModel(Base):
    __tablename__ = "grid_training_cohort_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["game_id", "cohort_id"], ["grid_training_cohorts.game_id", "grid_training_cohorts.id"]
        ),
        UniqueConstraint("game_id", "cohort_id", "ordinal"),
        CheckConstraint("ordinal>=0 AND role IN ('TRAIN','VALIDATION','REGRESSION')"),
        CheckConstraint("live_source_image_id IS NULL OR live_source_image_id=source_id"),
        Index("ix_grid_cohort_source", "game_id", "source_id"),
        Index("ix_grid_cohort_live_source", "game_id", "live_source_image_id"),
        Index("ix_grid_cohort_boards", "board_ids", postgresql_using="gin"),
        Index("ix_grid_cohort_reviews", "review_ids", postgresql_using="gin"),
        Index("ix_grid_cohort_cells", "cell_ids", postgresql_using="gin"),
    )
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    cohort_id: Mapped[UUID] = mapped_column(primary_key=True)
    source_id: Mapped[UUID] = mapped_column(primary_key=True)
    # Alembic installs the composite FK; source_id itself is retained evidence.
    live_source_image_id: Mapped[UUID | None] = mapped_column(ForeignKey("source_images.id"))
    ordinal: Mapped[int] = mapped_column()
    role: Mapped[str | None] = mapped_column(String(16))
    frozen: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    board_ids: Mapped[list[UUID]] = mapped_column(ARRAY(Uuid()), default=list)
    review_ids: Mapped[list[UUID]] = mapped_column(ARRAY(Uuid()), default=list)
    cell_ids: Mapped[list[UUID]] = mapped_column(ARRAY(Uuid()), default=list)


class GridTrainingCohortPageModel(Base):
    __tablename__ = "grid_training_cohort_pages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["game_id", "cohort_id"], ["grid_training_cohorts.game_id", "grid_training_cohorts.id"]
        ),
        CheckConstraint("kind IN ('capture','materialization') AND page_index>=0"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'"),
    )
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    cohort_id: Mapped[UUID] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    page_index: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(String(1000))
    sha256: Mapped[str] = mapped_column(String(64))
    document: Mapped[dict[str, Any]] = mapped_column(JSONB)


class GridTrainingCohortCommandModel(Base):
    __tablename__ = "grid_training_cohort_commands"
    __table_args__ = (
        ForeignKeyConstraint(
            ["game_id", "cohort_id"], ["grid_training_cohorts.game_id", "grid_training_cohorts.id"]
        ),
        CheckConstraint("command_sha256 ~ '^[0-9a-f]{64}$'"),
    )
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    idempotency_key: Mapped[UUID] = mapped_column(primary_key=True)
    cohort_id: Mapped[UUID | None] = mapped_column()
    command_sha256: Mapped[str] = mapped_column(String(64))
    document: Mapped[dict[str, Any]] = mapped_column(JSONB)


class GridTrainingCohortEventModel(Base):
    __tablename__ = "grid_training_cohort_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["game_id", "cohort_id"], ["grid_training_cohorts.game_id", "grid_training_cohorts.id"]
        ),
        Index("ix_grid_cohort_event", "game_id", "cohort_id", "created_at"),
        Index("ix_grid_cohort_event_source", "game_id", "source_id"),
        Index("ix_grid_cohort_event_board", "game_id", "board_id"),
    )
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    cohort_id: Mapped[UUID] = mapped_column()
    kind: Mapped[str] = mapped_column(String(64))
    source_id: Mapped[UUID | None] = mapped_column()
    board_id: Mapped[UUID | None] = mapped_column()
    review_id: Mapped[UUID | None] = mapped_column()
    cell_id: Mapped[UUID | None] = mapped_column()
    document: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GridSourceIdentityCommandModel(Base):
    __tablename__ = "grid_source_identity_commands"
    __table_args__ = (CheckConstraint("command_sha256 ~ '^[0-9a-f]{64}$'"),)
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    idempotency_key: Mapped[UUID] = mapped_column(primary_key=True)
    command_sha256: Mapped[str] = mapped_column(String(64))
    document: Mapped[dict[str, Any]] = mapped_column(JSONB)
