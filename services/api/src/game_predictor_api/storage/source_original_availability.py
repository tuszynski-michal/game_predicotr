"""Which managed originals were replaced by their verified crop (D-562, TASK-1048).

Whole-frame consumers that choose sources from the database (calibration
anchors, V3 cohorts) ask the shared crop registry before they read files, so a
deleted original is skipped or refused up front instead of failing halfway.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from game_predictor_api.storage.source_image_crop_models import SourceImageCropModel

_CHUNK = 1000


def deleted_original_checksums(session: Session, checksums: Iterable[str]) -> frozenset[str]:
    """The subset of ``checksums`` whose original file was deleted after its crop."""

    values = sorted(set(checksums))
    deleted: set[str] = set()
    for start in range(0, len(values), _CHUNK):
        deleted.update(
            session.scalars(
                select(SourceImageCropModel.original_checksum_sha256).where(
                    SourceImageCropModel.state == "original_deleted",
                    SourceImageCropModel.original_checksum_sha256.in_(
                        values[start : start + _CHUNK]
                    ),
                )
            )
        )
    return frozenset(deleted)


__all__ = ["deleted_original_checksums"]
