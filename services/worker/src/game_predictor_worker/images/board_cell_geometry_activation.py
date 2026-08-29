"""Accepted production snapshot for pending-only board-cell recropping.

The snapshot is shared by the API job creator and the worker validator.  This
keeps a queued job reproducible and prevents a later code change from silently
altering the geometry or raster contract that the owner explicitly started.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from .board_cell_geometry_contract import (
    BOARD_CELL_GEOMETRY_VERSION,
    LEGACY_BOARD_CELL_TOPOLOGY,
    BoardCellTopology,
)
from .board_cell_geometry_crops import CROPPER_VERSION, cropper_fingerprint_sha256
from .board_cell_geometry_estimator import (
    ESTIMATOR_VERSION,
    HOMOGRAPHY_VERSION,
    LOCATOR_VERSION,
    THRESHOLDS_VERSION,
    estimator_thresholds,
)

PENDING_BOARD_CELL_RECROP_VERSION = "pending-board-cell-recrop-v19-v1"
BOARD_CELL_PROCESSING_VERSION = "board-cell-processing-v20-verified-v19-v1"
ACCEPTED_AUDIT_REPORT_CHECKSUM_SHA256 = (
    "320c9b1089b1481e8e4eea71c955eaf796c61554391783d2ac34020aa2421691"
)
SHADOW_BENCHMARK_MANIFEST_CHECKSUM_SHA256 = (
    "8640084933f74586e2a429120ac29835c7e7fa20d9ac52d91c9c2f271c22473f"
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


def board_cell_processing_snapshot(
    *,
    cell_output_size: int,
    topology: BoardCellTopology | None = None,
) -> dict[str, object]:
    """Build the pinned default full-import v20/v19 processing contract."""

    recrop = board_cell_recrop_snapshot(cell_output_size=cell_output_size)
    snapshot = {
        **recrop,
        "activationVersion": BOARD_CELL_PROCESSING_VERSION,
        "estimatorFingerprintSha256": _sha256(
            {
                "estimatorVersion": ESTIMATOR_VERSION,
                "geometryVersion": BOARD_CELL_GEOMETRY_VERSION,
                "homographyVersion": HOMOGRAPHY_VERSION,
                "locatorVersion": LOCATOR_VERSION,
                "thresholds": estimator_thresholds(),
                "thresholdsVersion": THRESHOLDS_VERSION,
            }
        ),
        "rolloutMode": "default_v19",
        "shadowBenchmarkManifestChecksumSha256": (SHADOW_BENCHMARK_MANIFEST_CHECKSUM_SHA256),
    }
    if topology is not None:
        snapshot["cropperFingerprintSha256"] = cropper_fingerprint_sha256(
            cell_output_size=cell_output_size,
            topology=topology,
        )
        snapshot["gridRows"] = topology.rows
        snapshot["gridColumns"] = topology.columns
        snapshot["topologyRulesVersionId"] = topology.rules_version_id
        snapshot["topologyFingerprintSha256"] = _sha256(
            {
                "gridRows": topology.rows,
                "gridColumns": topology.columns,
                "topologyRulesVersionId": topology.rules_version_id,
            }
        )
    snapshot["configurationFingerprintSha256"] = _sha256(
        {**snapshot, "cellOutputSize": cell_output_size}
    )
    return snapshot


def validate_board_cell_processing_snapshot(
    value: object,
    *,
    cell_output_size: int,
) -> dict[str, object]:
    """Reject drift in an explicitly pinned v20 full-import snapshot."""

    if not isinstance(value, Mapping):
        raise BoardCellRecropSnapshotError("The board-cell processing snapshot is missing.")
    has_topology = any(
        key in value for key in ("gridRows", "gridColumns", "topologyRulesVersionId")
    )
    topology: BoardCellTopology | None = None
    if has_topology:
        try:
            topology = BoardCellTopology(
                rows=_topology_dimension(value, "gridRows"),
                columns=_topology_dimension(value, "gridColumns"),
                rules_version_id=_topology_rules_version(value),
            )
        except (TypeError, ValueError) as error:
            raise BoardCellRecropSnapshotError(
                "The board-cell processing topology is invalid."
            ) from error
    expected = board_cell_processing_snapshot(
        cell_output_size=cell_output_size,
        topology=topology,
    )
    if dict(value) != expected:
        raise BoardCellRecropSnapshotError(
            "The board-cell processing snapshot differs from the accepted v20 contract."
        )
    return expected


def require_v20_supported_topology(snapshot: Mapping[str, object]) -> BoardCellTopology:
    """Return the pinned topology or reject unsupported automatic v20 geometry."""

    topology = BoardCellTopology(
        rows=_topology_dimension(
            snapshot,
            "gridRows",
            default=LEGACY_BOARD_CELL_TOPOLOGY.rows,
        ),
        columns=_topology_dimension(
            snapshot,
            "gridColumns",
            default=LEGACY_BOARD_CELL_TOPOLOGY.columns,
        ),
        rules_version_id=_topology_rules_version(snapshot),
    )
    if not topology.is_legacy_3x5:
        raise BoardCellRecropSnapshotError(
            "IMAGE_PIPELINE_TOPOLOGY_UNSUPPORTED: "
            "board-cell-processing-v20-verified-v19-v1 supports only 3x5 boards."
        )
    return topology


def _topology_dimension(
    value: Mapping[str, object],
    field: str,
    *,
    default: int | None = None,
) -> int:
    result = value.get(field, default)
    if isinstance(result, bool) or not isinstance(result, int):
        raise BoardCellRecropSnapshotError("The board-cell processing topology is invalid.")
    return result


def _topology_rules_version(value: Mapping[str, object]) -> str | None:
    result = value.get("topologyRulesVersionId")
    if result is None:
        return None
    if not isinstance(result, str):
        raise BoardCellRecropSnapshotError("The board-cell processing topology is invalid.")
    return result


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
    "BOARD_CELL_PROCESSING_VERSION",
    "PENDING_BOARD_CELL_RECROP_VERSION",
    "SHADOW_BENCHMARK_MANIFEST_CHECKSUM_SHA256",
    "BoardCellRecropSnapshotError",
    "board_cell_processing_snapshot",
    "board_cell_recrop_snapshot",
    "require_v20_supported_topology",
    "validate_board_cell_processing_snapshot",
    "validate_board_cell_recrop_snapshot",
]
