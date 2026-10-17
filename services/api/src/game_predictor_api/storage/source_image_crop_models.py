"""Shared registry of verified crops of managed originals (migration 0167, D-562).

One row per content-addressed original, mirroring the attestation file stored
next to the crop. Constraints live in the migration; this mapping only reads
and writes rows.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from game_predictor_api.storage.metadata import Base


class SourceImageCropModel(Base):
    __tablename__ = "source_image_crops"
    __table_args__ = ({"schema": "public"},)

    original_checksum_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    original_relative_path: Mapped[str] = mapped_column(String(1000))
    original_size_bytes: Mapped[int] = mapped_column(BigInteger)
    original_normalized_pixel_checksum_sha256: Mapped[str] = mapped_column(String(64))
    original_width: Mapped[int] = mapped_column(Integer)
    original_height: Mapped[int] = mapped_column(Integer)
    original_exif_orientation: Mapped[int | None] = mapped_column(SmallInteger)
    crop_relative_path: Mapped[str] = mapped_column(String(1000))
    attestation_relative_path: Mapped[str] = mapped_column(String(1000))
    crop_checksum_sha256: Mapped[str] = mapped_column(String(64))
    crop_size_bytes: Mapped[int] = mapped_column(BigInteger)
    crop_normalized_pixel_checksum_sha256: Mapped[str] = mapped_column(String(64))
    canvas_pixel_checksum_sha256: Mapped[str] = mapped_column(String(64))
    attestation_sha256: Mapped[str] = mapped_column(String(64))
    crop_box: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    raw_crop_box: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    protected_box: Mapped[list[float]] = mapped_column(ARRAY(Float))
    margin_px: Mapped[int] = mapped_column(SmallInteger)
    imcu_width: Mapped[int] = mapped_column(SmallInteger)
    imcu_height: Mapped[int] = mapped_column(SmallInteger)
    edge_mismatch_pixels: Mapped[int] = mapped_column(Integer)
    tool_version: Mapped[str] = mapped_column(String(200))
    policy_version: Mapped[str] = mapped_column(String(40))
    state: Mapped[str] = mapped_column(String(20))
    job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="RESTRICT"))
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    original_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Migration 0168 (TASK-1048): the deletion job that removed the original.
    deletion_job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id"))


class SourceCropRunModel(Base):
    """One planned and optionally executed crop or original-deletion run (migration 0168)."""

    __tablename__ = "source_crop_runs"
    __table_args__ = ({"schema": "public"},)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(16))
    scope: Mapped[dict[str, object]] = mapped_column(JSONB)
    plan_job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="RESTRICT"))
    job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="RESTRICT"))
    manifest_relative_path: Mapped[str | None] = mapped_column(String(1000))
    manifest_checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    preview_token: Mapped[str | None] = mapped_column(String(64))
    eligible_count: Mapped[int] = mapped_column(Integer, default=0)
    excluded_count: Mapped[int] = mapped_column(Integer, default=0)
    exclusion_counts: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    candidate_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    estimated_saved_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    processed_count: Mapped[int] = mapped_column(Integer, default=0)
    succeeded_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    saved_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    checkpoint_index: Mapped[int] = mapped_column(Integer, default=0)
    outcome_counts: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    failures: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
