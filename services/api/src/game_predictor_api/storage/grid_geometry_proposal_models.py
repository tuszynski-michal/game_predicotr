"""Retained proposal evidence and append-only command outcomes; no live image FKs."""

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from game_predictor_api.storage.metadata import Base


class GridGeometryProposalModel(Base):
    __tablename__ = "grid_geometry_proposals"
    __table_args__ = (
        UniqueConstraint("game_id", "target_result_id"),
        UniqueConstraint("game_id", "operation_id", "target_ordinal"),
        ForeignKeyConstraint(
            ["game_id", "target_result_id"],
            ["grid_reinference_targets.game_id", "grid_reinference_targets.target_result_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("state IN ('pending','accepted','rejected','stale') AND revision >= 1"),
        CheckConstraint("jsonb_typeof(document) = 'object'"),
        CheckConstraint("(state='accepted') = (accepted IS NOT NULL)"),
    )
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    target_result_id: Mapped[UUID] = mapped_column(nullable=False)
    operation_id: Mapped[UUID] = mapped_column(nullable=False)
    target_ordinal: Mapped[int] = mapped_column(nullable=False)
    import_job_id: Mapped[UUID] = mapped_column(nullable=False)
    review_item_id: Mapped[UUID] = mapped_column(nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    revision: Mapped[int] = mapped_column(nullable=False, default=1)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    accepted: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))


class GridGeometryProposalEventModel(Base):
    __tablename__ = "grid_geometry_proposal_events"
    __table_args__ = (
        UniqueConstraint("game_id", "proposal_id", "ordinal"),
        CheckConstraint("ordinal >= 1"),
        ForeignKeyConstraint(
            ["game_id", "proposal_id"],
            ["grid_geometry_proposals.game_id", "grid_geometry_proposals.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "proposal_id IS NOT NULL OR (kind='command_rejected' AND command_kind='create')"
        ),
        CheckConstraint(
            "kind IN ('created','accepted','rejected','stale',"
            "'command_completed','command_rejected')"
        ),
        CheckConstraint("command_kind IN ('create','accept','reject')"),
        CheckConstraint("command_sha256 ~ '^[0-9a-f]{64}$'"),
        CheckConstraint("jsonb_typeof(document) = 'object'"),
        Index(
            "uq_geometry_proposal_create_key",
            "game_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("command_kind='create'"),
        ),
        Index(
            "uq_geometry_proposal_command_key",
            "game_id",
            "proposal_id",
            "command_kind",
            "idempotency_key",
            unique=True,
            postgresql_where=text("command_kind<>'create'"),
        ),
    )
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    proposal_id: Mapped[UUID | None] = mapped_column(nullable=True)
    ordinal: Mapped[int] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    command_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(nullable=False)
    command_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
