"""Central ORM declarations for the private geometry-only registry."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Sequence,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .metadata import Base

DOCUMENT = JSONB().with_variant(JSON(), "sqlite")
UUID_LIST = ARRAY(Uuid()).with_variant(JSON(), "sqlite")


class RecordingGroupModel(Base):
    __tablename__ = "recording_groups"
    __table_args__ = (
        UniqueConstraint("origin_provider_sha256", "external_ref_sha256"),
        {"schema": "public"},
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    origin: Mapped[str] = mapped_column(Text, default="MAIN")
    game_id: Mapped[UUID | None] = mapped_column()
    external_ref_sha256: Mapped[str | None] = mapped_column(Text)
    origin_provider_sha256: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(BigInteger)
    manifest_id: Mapped[UUID] = mapped_column(unique=True)
    manifest_sha256: Mapped[str] = mapped_column(Text)
    expected_sources: Mapped[int] = mapped_column()
    page_count: Mapped[int] = mapped_column()
    origin_import_job_id: Mapped[UUID | None] = mapped_column()
    membership_complete: Mapped[bool] = mapped_column(default=False)
    declared: Mapped[bool] = mapped_column(default=False)
    independent: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecordingOccurrenceModel(Base):
    __tablename__ = "recording_occurrences"
    __table_args__ = (
        UniqueConstraint("group_id", "game_id", "source_id"),
        UniqueConstraint("group_id", "origin_provider_sha256", "external_ref_sha256"),
        {"schema": "public"},
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    group_id: Mapped[UUID] = mapped_column(ForeignKey("public.recording_groups.id"))
    origin: Mapped[str] = mapped_column(Text, default="MAIN")
    game_id: Mapped[UUID | None] = mapped_column()
    source_id: Mapped[UUID | None] = mapped_column()
    external_ref_sha256: Mapped[str | None] = mapped_column(Text)
    origin_provider_sha256: Mapped[str | None] = mapped_column(Text)
    source_sha256: Mapped[str] = mapped_column(Text)
    pixel_sha256: Mapped[str] = mapped_column(Text)
    pixel_algorithm: Mapped[str] = mapped_column(Text)
    width: Mapped[int] = mapped_column()
    height: Mapped[int] = mapped_column()
    attestation: Mapped[dict[str, Any]] = mapped_column(DOCUMENT)


class RecordingEvidenceModel(Base):
    __tablename__ = "recording_evidence"
    __table_args__ = ({"schema": "public"},)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    ordinal: Mapped[int] = mapped_column(
        BigInteger, Sequence("recording_evidence_ordinal_seq", schema="public"), unique=True
    )
    kind: Mapped[str] = mapped_column(Text)
    group_ids: Mapped[list[UUID]] = mapped_column(UUID_LIST)
    dependency_group_ids: Mapped[list[UUID]] = mapped_column(UUID_LIST)
    payload: Mapped[dict[str, Any]] = mapped_column(DOCUMENT)
    payload_sha256: Mapped[str] = mapped_column(Text)
    proof_sha256: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecordingRoleHeadModel(Base):
    __tablename__ = "recording_role_heads"
    __table_args__ = ({"schema": "public"},)
    family_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.grid_model_families.id"), primary_key=True
    )
    group_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.recording_groups.id"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(BigInteger)
    role: Mapped[str] = mapped_column(Text)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("public.recording_evidence.id"))


class RecordingCommandModel(Base):
    __tablename__ = "recording_commands"
    __table_args__ = (
        UniqueConstraint("game_id", "kind", "idempotency_key"),
        UniqueConstraint("external_ref_sha256", "kind", "idempotency_key"),
        {"schema": "public"},
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    origin: Mapped[str] = mapped_column(Text, default="MAIN")
    game_id: Mapped[UUID | None] = mapped_column()
    external_ref_sha256: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[UUID] = mapped_column()
    command_json: Mapped[dict[str, Any]] = mapped_column(DOCUMENT)
    command_sha256: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(64))
    receipt: Mapped[dict[str, Any]] = mapped_column(DOCUMENT)
