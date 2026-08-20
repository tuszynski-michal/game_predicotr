"""Accepted production snapshot for pending-only board-cell recropping.

The snapshot is shared by the API job creator and the worker validator.  This
keeps a queued job reproducible and prevents a later code change from silently
altering the geometry or raster contract that the owner explicitly started.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from .board_cell_geometry_contract import BOARD_CELL_GEOMETRY_VERSION
from .board_cell_geometry_crops import CROPPER_VERSION, cropper_fingerprint_sha256
from .board_cell_geometry_estimator import (
    ESTIMATOR_VERSION,
    HOMOGRAPHY_VERSION,
    LOCATOR_VERSION,
    THRESHOLDS_VERSION,
    estimator_thresholds,
)

PENDING_BOARD_CELL_RECROP_VERSION = "pending-board-cell-recrop-v19-v1"
ACCEPTED_AUDIT_REPORT_CHECKSUM_SHA256 = (
    "320c9b1089b1481e8e4eea71c955eaf796c61554391783d2ac34020aa2421691"
)


class BoardCellRecropSnapshotError(ValueError):
    """Stable invalid-input error for a pinned v19 recrop snapshot."""


def board_cell_recrop_snapshot(*, cell_output_size: int) -> dict[str, object]:
    """Build the immutable v19 configuration accepted by the 100-page gate."""

    if (
        isinstance(cell_output_size, bool)
        or not isinstance(cell_output_size, int)
        or cell_output_size < 16
    ):
        raise ValueError("cell_output_size must be an integer of at least 16")
    thresholds = estimator_thresholds()
    thresholds_fingerprint = _sha256(thresholds)
    snapshot: dict[str, object] = {
        "activationVersion": PENDING_BOARD_CELL_RECROP_VERSION,
        "auditReportChecksumSha256": ACCEPTED_AUDIT_REPORT_CHECKSUM_SHA256,
        "cropperFingerprintSha256": cropper_fingerprint_sha256(cell_output_size=cell_output_size),
        "cropperVersion": CROPPER_VERSION,
        "estimatorVersion": ESTIMATOR_VERSION,
        "geometryVersion": BOARD_CELL_GEOMETRY_VERSION,
        "homographyVersion": HOMOGRAPHY_VERSION,
        "locatorVersion": LOCATOR_VERSION,
        "thresholdsFingerprintSha256": thresholds_fingerprint,
        "thresholdsVersion": THRESHOLDS_VERSION,
    }
    snapshot["configurationFingerprintSha256"] = _sha256(
        {**snapshot, "cellOutputSize": cell_output_size}
    )
    return snapshot


def validate_board_cell_recrop_snapshot(
    value: object,
    *,
    cell_output_size: int,
) -> dict[str, object]:
    """Return the canonical snapshot or reject any queued-payload drift."""

    if not isinstance(value, Mapping):
        raise BoardCellRecropSnapshotError("The board-cell recrop snapshot is missing.")
    expected = board_cell_recrop_snapshot(cell_output_size=cell_output_size)
    if dict(value) != expected:
        raise BoardCellRecropSnapshotError(
            "The board-cell recrop snapshot differs from the accepted v19 contract."
        )
    return expected


def _sha256(value: Mapping[str, object]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "ACCEPTED_AUDIT_REPORT_CHECKSUM_SHA256",
    "PENDING_BOARD_CELL_RECROP_VERSION",
    "BoardCellRecropSnapshotError",
    "board_cell_recrop_snapshot",
    "validate_board_cell_recrop_snapshot",
]
