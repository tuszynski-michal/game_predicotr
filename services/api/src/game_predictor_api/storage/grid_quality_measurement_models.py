"""Retained game-owned measurement evidence; only nullable links reference live sources."""

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from game_predictor_api.storage.metadata import Base


class GridQualityMeasurementModel(Base):
    __tablename__ = "grid_quality_measurements"
    __table_args__ = (CheckConstraint("jsonb_typeof(document)='object'"),)
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    manifest_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class GridQualityMeasurementMemberModel(Base):
    __tablename__ = "grid_quality_measurement_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["game_id", "measurement_id"],
            ["grid_quality_measurements.game_id", "grid_quality_measurements.id"],
        ),
        CheckConstraint("sample_kind IN ('random','hard') AND revision>=0"),
        CheckConstraint("live_source_image_id IS NULL OR live_source_image_id=source_id"),
        Index("ix_quality_member_live_source", "game_id", "live_source_image_id"),
    )
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    measurement_id: Mapped[UUID] = mapped_column(primary_key=True)
    source_id: Mapped[UUID] = mapped_column(primary_key=True)
    sample_kind: Mapped[str] = mapped_column(String(8), primary_key=True)
    # Migration enforces the composite game/live FK. The legacy ORM source
    # mapping omits game_id, exactly as in retained reinference sources.
    live_source_image_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_images.id"), nullable=True
    )
    revision: Mapped[int] = mapped_column(nullable=False, default=0)
    frozen: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    current: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class GridQualityMeasurementJudgmentModel(Base):
    __tablename__ = "grid_quality_measurement_judgments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["game_id", "measurement_id", "source_id", "sample_kind"],
            [
                "grid_quality_measurement_members.game_id",
                "grid_quality_measurement_members.measurement_id",
                "grid_quality_measurement_members.source_id",
                "grid_quality_measurement_members.sample_kind",
            ],
        ),
        CheckConstraint("revision>=1"),
    )
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    measurement_id: Mapped[UUID] = mapped_column(primary_key=True)
    source_id: Mapped[UUID] = mapped_column(primary_key=True)
    sample_kind: Mapped[str] = mapped_column(String(8), primary_key=True)
    revision: Mapped[int] = mapped_column(primary_key=True)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class GridQualityMeasurementCommandModel(Base):
    __tablename__ = "grid_quality_measurement_commands"
    __table_args__ = (
        ForeignKeyConstraint(
            ["game_id", "measurement_id"],
            ["grid_quality_measurements.game_id", "grid_quality_measurements.id"],
        ),
        CheckConstraint("kind IN ('capture','assess')"),
        CheckConstraint("command_sha256 ~ '^[0-9a-f]{64}$'"),
    )
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    idempotency_key: Mapped[UUID] = mapped_column(primary_key=True)
    measurement_id: Mapped[UUID] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    command_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class GridGeometryApprovalCommandModel(Base):
    __tablename__ = "grid_geometry_approval_commands"
    __table_args__ = (CheckConstraint("command_sha256 ~ '^[0-9a-f]{64}$'"),)
    game_id: Mapped[UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    idempotency_key: Mapped[UUID] = mapped_column(primary_key=True)
    review_item_id: Mapped[UUID] = mapped_column(nullable=False)
    import_job_id: Mapped[UUID] = mapped_column(nullable=False)
    command_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
