"""Shared registry of verified crops of managed originals (migration 0167, D-562).

One row per content-addressed original, mirroring the attestation file stored
next to the crop. Constraints live in the migration; this mapping only reads
and writes rows.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, SmallInteger, String
from sqlalchemy.dialects.postgresql import ARRAY
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
