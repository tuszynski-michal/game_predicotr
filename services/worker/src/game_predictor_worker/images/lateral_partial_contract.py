"""Immutable opt-in policy for lateral partial boards; not an activation flag."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

LATERAL_PARTIAL_POLICY_VERSION = "structured-lattice-v4-lateral-partial-v1"
LATERAL_PARTIAL_SNAPSHOT_VERSION = "lateral-partial-geometry-snapshot-v1"
AUTOMATIC_PARTIAL_PROPOSAL_VERSION = "automatic-lateral-partial-proposal-v1"
# Release is a reviewed code decision, never an environment/client override.
# TASK-0515 accepted the checksum-bound real-image gate. This remains a
# deliberately explicit code release decision, not an environment override.
LATERAL_PARTIAL_RELEASED = True


class GeometryEngineVariant(StrEnum):
    STRUCTURED_LATTICE_V4_PARTIAL_SIDES = "structured_lattice_v4_partial_sides"


class LateralPartialContractError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class LateralPartialGeometrySnapshot:
    """One fixed policy: changed constants require a new policy version.

    Keep safety parameters in the snapshot rather than resolving current process
    defaults during retry. This contract does not authorize pipeline dispatch.
    """

    def to_payload(self, *, include_checksum: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schemaVersion": LATERAL_PARTIAL_SNAPSHOT_VERSION,
            "variant": GeometryEngineVariant.STRUCTURED_LATTICE_V4_PARTIAL_SIDES.value,
            "policyVersion": LATERAL_PARTIAL_POLICY_VERSION,
            "proposalVersion": AUTOMATIC_PARTIAL_PROPOSAL_VERSION,
            "topologyRows": 3,
            "topologyColumns": 5,
            "analysisWidth": 500,
            "analysisHeight": 300,
            "maximumAdditionalPasses": 1,
            "minimumVisibleRows": 3,
            "minimumVisibleColumns": 3,
            "minimumInliers": 9,
            "verticalClippingAllowed": False,
            "requiresManualConfirmation": True,
            "excludeFromGeometryTraining": True,
            "excludeFromPageAnchors": True,
        }
        if include_checksum:
            payload["checksumSha256"] = self.checksum_sha256
        return payload

    @property
    def checksum_sha256(self) -> str:
        encoded = json.dumps(
            self.to_payload(include_checksum=False), sort_keys=True, separators=(",", ":")
        ).encode("ascii")
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def from_payload(cls, value: object) -> LateralPartialGeometrySnapshot:
        snapshot = cls()
        expected = snapshot.to_payload()
        if not isinstance(value, Mapping) or set(value) != set(expected):
            raise LateralPartialContractError(
                "IMAGE_LATERAL_PARTIAL_SNAPSHOT_INVALID",
                "Incomplete or unknown partial policy fields.",
            )
        # Strict type equality avoids accepting bool for integer gates.
        if any(
            type(value[key]) is not type(item) or value[key] != item
            for key, item in expected.items()
        ):
            raise LateralPartialContractError(
                "IMAGE_LATERAL_PARTIAL_SNAPSHOT_DRIFT",
                "The pinned partial policy version or parameters changed.",
            )
        return snapshot


def require_geometry_engine_variant_available(variant: GeometryEngineVariant | str | None) -> None:
    """Explicit release gate, independent of the immutable run policy."""
    if variant is None:
        return
    try:
        GeometryEngineVariant(variant)
    except (TypeError, ValueError) as error:
        raise LateralPartialContractError(
            "IMAGE_GEOMETRY_ENGINE_VARIANT_UNSUPPORTED",
            "The requested geometry engine variant is unknown.",
        ) from error
    if LATERAL_PARTIAL_RELEASED:
        return
    raise LateralPartialContractError(
        "IMAGE_GEOMETRY_ENGINE_VARIANT_NOT_ENABLED",
        "v0.10.4 is unavailable until its real-data quality gate is accepted.",
    )
