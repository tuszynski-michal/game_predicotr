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
    training_family_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("public.grid_model_families.id", ondelete="RESTRICT")
    )


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
    # Nullable only for the immutable historical rows written by migration0156.
    expected_revision: Mapped[int | None] = mapped_column()
    command_sha256: Mapped[str | None] = mapped_column(String(64))
    command_json: Mapped[str | None] = mapped_column(Text)
    receipt_json: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str | None] = mapped_column(String(64))
    evidence_sha256: Mapped[str | None] = mapped_column(String(64))


class GridModelEvaluationReportModel(Base):
    __tablename__ = "grid_model_evaluation_reports"
    __table_args__ = ({"schema": "public"},)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.grid_model_versions.id", ondelete="RESTRICT")
    )
    producer: Mapped[str] = mapped_column(String(64))
    report_json: Mapped[str] = mapped_column(Text)
    report_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GridModelEvaluationInvalidationModel(Base):
    __tablename__ = "grid_model_evaluation_invalidations"
    __table_args__ = ({"schema": "public"},)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    report_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.grid_model_evaluation_reports.id", ondelete="RESTRICT")
    )
    reason: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GridModelPublicationModel(Base):
    __tablename__ = "grid_model_publications"
    __table_args__ = ({"schema": "public"},)
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.grid_model_versions.id", ondelete="RESTRICT"), primary_key=True
    )
    evaluation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("public.grid_model_evaluation_reports.id", ondelete="RESTRICT")
    )
    evidence_json: Mapped[str] = mapped_column(Text)
    evidence_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GridModelControlEventModel(Base):
    __tablename__ = "grid_model_control_events"
    __table_args__ = ({"schema": "public"},)
    idempotency_key: Mapped[UUID] = mapped_column(primary_key=True)
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.grid_model_versions.id", ondelete="RESTRICT")
    )
    kind: Mapped[str] = mapped_column(String(32))
    revision: Mapped[int] = mapped_column()
    expected_revision: Mapped[int] = mapped_column()
    command_sha256: Mapped[str] = mapped_column(String(64))
    command_json: Mapped[str] = mapped_column(Text)
    receipt_json: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(64))
    evidence_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GridModelDefaultModel(Base):
    __tablename__ = "grid_model_default"
    __table_args__ = (CheckConstraint("id = 'geometry-v3'"), {"schema": "public"})
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.grid_model_versions.id", ondelete="RESTRICT")
    )
    revision: Mapped[int] = mapped_column()


class GameCreateReceiptModel(Base):
    """A deleted game must never free its original create command key."""

    __tablename__ = "game_create_receipts"
    __table_args__ = (UniqueConstraint("game_id"), {"schema": "public"})
    idempotency_key: Mapped[UUID] = mapped_column(primary_key=True)
    game_id: Mapped[UUID] = mapped_column()
    command_json: Mapped[str] = mapped_column(Text)
    command_sha256: Mapped[str] = mapped_column(String(64))
    reservation_json: Mapped[str] = mapped_column(Text)
    reservation_sha256: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GridModelFamilyForkModel(Base):
    __tablename__ = "grid_model_family_forks"
    __table_args__ = ({"schema": "public"},)
    family_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.grid_model_families.id", ondelete="RESTRICT"), primary_key=True
    )
    base_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.grid_model_versions.id", ondelete="RESTRICT")
    )
    base_manifest_sha256: Mapped[str] = mapped_column(String(64))
    lineage_json: Mapped[str] = mapped_column(Text)
    lineage_sha256: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
