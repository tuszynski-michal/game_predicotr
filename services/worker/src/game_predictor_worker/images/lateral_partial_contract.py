"""Immutable opt-in policy for lateral partial boards; not an activation flag."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from .partial_grid_learning import PartialGridLearningError, PartialGridTrainingProfile

LATERAL_PARTIAL_POLICY_VERSION = "structured-lattice-v4-lateral-partial-v1"
LATERAL_PARTIAL_SNAPSHOT_VERSION = "lateral-partial-geometry-snapshot-v1"
AUTOMATIC_PARTIAL_PROPOSAL_VERSION = "automatic-lateral-partial-proposal-v1"
LATERAL_PARTIAL_POLICY_VERSION_V2 = "structured-lattice-v4-lateral-partial-v2"
LATERAL_PARTIAL_SNAPSHOT_VERSION_V2 = "lateral-partial-geometry-snapshot-v2"
AUTOMATIC_PARTIAL_PROPOSAL_VERSION_V2 = "automatic-lateral-partial-proposal-v2"
LATERAL_PARTIAL_POLICY_VERSION_V3 = "structured-lattice-v4-lateral-partial-v3"
LATERAL_PARTIAL_SNAPSHOT_VERSION_V3 = "lateral-partial-geometry-snapshot-v3"
AUTOMATIC_PARTIAL_PROPOSAL_VERSION_V3 = "automatic-lateral-partial-proposal-v3"
AUTOMATIC_FRAME_PROPOSAL_VERSION = "automatic-frame-geometry-proposal-v1"
SELECTIVE_FRAME_POLICY_VERSION = "structured-lattice-v4-selective-frame-v1"
SELECTIVE_FRAME_SNAPSHOT_VERSION = "selective-frame-geometry-snapshot-v1"
SELECTIVE_FRAME_PARTIAL_PROPOSAL_VERSION = "automatic-lateral-partial-proposal-v4"
SELECTIVE_FRAME_PROPOSAL_VERSION = "automatic-frame-geometry-proposal-v2"
MINIMUM_SELECTIVE_CONFIDENT_SLOTS = 7
MAXIMUM_SELECTIVE_REVIEW_SLOTS = 2
MINIMUM_AUTOMATIC_BOARD_RED_EDGE_COVERAGE = 0.65
MINIMUM_REVIEWABLE_BOARD_RED_EDGE_COVERAGE = 0.30
MINIMUM_REVIEWABLE_PAGE_MEAN_RED_EDGE_COVERAGE = 0.70
MAXIMUM_FRAME_REVIEW_SLOTS = 3
# Release is a reviewed code decision, never an environment/client override.
# TASK-0515 accepted the checksum-bound real-image gate. This remains a
# deliberately explicit code release decision, not an environment override.
LATERAL_PARTIAL_RELEASED = True


class GeometryEngineVariant(StrEnum):
    STRUCTURED_LATTICE_V4_PARTIAL_SIDES = "structured_lattice_v4_partial_sides"
    SELECTIVE_BOARD_REVIEW_V1_1 = "selective_board_review_v1_1"
    CONTRAST_FRAME_GRID_V1_2 = "contrast_frame_grid_v1_2"


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

    training_profile: PartialGridTrainingProfile | None = None
    # TASK-0561 rolled back v3 for new runs after the real staging regression
    # (40 review items with v2 versus 355 with v3). Historical pinned v3
    # snapshots still opt in explicitly through from_payload().
    frame_support_review: bool = False
    selective_frame_review: bool = False

    def __post_init__(self) -> None:
        if self.selective_frame_review and not self.frame_support_review:
            raise ValueError("Selective review requires pinned frame support evidence.")

    @property
    def policy_version(self) -> str:
        if self.selective_frame_review:
            return SELECTIVE_FRAME_POLICY_VERSION
        if self.frame_support_review:
            return LATERAL_PARTIAL_POLICY_VERSION_V3
        return (
            LATERAL_PARTIAL_POLICY_VERSION
            if self.training_profile is None
            else LATERAL_PARTIAL_POLICY_VERSION_V2
        )

    @property
    def proposal_version(self) -> str:
        if self.selective_frame_review:
            return SELECTIVE_FRAME_PARTIAL_PROPOSAL_VERSION
        if self.frame_support_review:
            return AUTOMATIC_PARTIAL_PROPOSAL_VERSION_V3
        return (
            AUTOMATIC_PARTIAL_PROPOSAL_VERSION
            if self.training_profile is None
            else AUTOMATIC_PARTIAL_PROPOSAL_VERSION_V2
        )

    def to_payload(self, *, include_checksum: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schemaVersion": (
                SELECTIVE_FRAME_SNAPSHOT_VERSION
                if self.selective_frame_review
                else LATERAL_PARTIAL_SNAPSHOT_VERSION_V3
                if self.frame_support_review
                else (
                    LATERAL_PARTIAL_SNAPSHOT_VERSION
                    if self.training_profile is None
                    else LATERAL_PARTIAL_SNAPSHOT_VERSION_V2
                )
            ),
            "variant": (
                GeometryEngineVariant.SELECTIVE_BOARD_REVIEW_V1_1.value
                if self.selective_frame_review
                else GeometryEngineVariant.STRUCTURED_LATTICE_V4_PARTIAL_SIDES.value
            ),
            "policyVersion": self.policy_version,
            "proposalVersion": self.proposal_version,
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
        if self.frame_support_review:
            payload.update(
                {
                    "frameSupportReviewEnabled": True,
                    "automaticFrameProposalVersion": AUTOMATIC_FRAME_PROPOSAL_VERSION,
                    "minimumAutomaticBoardRedEdgeCoverage": (
                        MINIMUM_AUTOMATIC_BOARD_RED_EDGE_COVERAGE
                    ),
                    "minimumReviewableBoardRedEdgeCoverage": (
                        MINIMUM_REVIEWABLE_BOARD_RED_EDGE_COVERAGE
                    ),
                    "minimumReviewablePageMeanRedEdgeCoverage": (
                        MINIMUM_REVIEWABLE_PAGE_MEAN_RED_EDGE_COVERAGE
                    ),
                    "maximumFrameReviewSlots": MAXIMUM_FRAME_REVIEW_SLOTS,
                }
            )
        if self.selective_frame_review:
            payload.update(
                {
                    "automaticFrameProposalVersion": SELECTIVE_FRAME_PROPOSAL_VERSION,
                    "maximumFrameReviewSlots": MAXIMUM_SELECTIVE_REVIEW_SLOTS,
                    "minimumConfidentSlots": MINIMUM_SELECTIVE_CONFIDENT_SLOTS,
                    "baselineFirst": True,
                    "reviewDraftRequiresHumanConfirmation": True,
                }
            )
        if self.training_profile is not None:
            payload["partialGridTrainingProfile"] = self.training_profile.to_payload()
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
        if not isinstance(value, Mapping):
            raise LateralPartialContractError(
                "IMAGE_LATERAL_PARTIAL_SNAPSHOT_INVALID",
                "Incomplete or unknown partial policy fields.",
            )
        if value.get("schemaVersion") == LATERAL_PARTIAL_SNAPSHOT_VERSION:
            snapshot = cls(frame_support_review=False)
        elif value.get("schemaVersion") == LATERAL_PARTIAL_SNAPSHOT_VERSION_V2:
            try:
                v2_profile = PartialGridTrainingProfile.from_payload(
                    value.get("partialGridTrainingProfile")
                )
            except PartialGridLearningError as error:
                raise LateralPartialContractError(
                    "IMAGE_LATERAL_PARTIAL_SNAPSHOT_INVALID", str(error)
                ) from error
            snapshot = cls(training_profile=v2_profile, frame_support_review=False)
        elif value.get("schemaVersion") == LATERAL_PARTIAL_SNAPSHOT_VERSION_V3:
            raw_profile = value.get("partialGridTrainingProfile")
            try:
                v3_profile = (
                    None
                    if raw_profile is None
                    else PartialGridTrainingProfile.from_payload(raw_profile)
                )
            except PartialGridLearningError as error:
                raise LateralPartialContractError(
                    "IMAGE_LATERAL_PARTIAL_SNAPSHOT_INVALID", str(error)
                ) from error
            snapshot = cls(training_profile=v3_profile, frame_support_review=True)
        elif value.get("schemaVersion") == SELECTIVE_FRAME_SNAPSHOT_VERSION:
            raw_profile = value.get("partialGridTrainingProfile")
            try:
                selective_profile = (
                    None
                    if raw_profile is None
                    else PartialGridTrainingProfile.from_payload(raw_profile)
                )
            except PartialGridLearningError as error:
                raise LateralPartialContractError(
                    "IMAGE_LATERAL_PARTIAL_SNAPSHOT_INVALID", str(error)
                ) from error
            snapshot = cls(
                training_profile=selective_profile,
                frame_support_review=True,
                selective_frame_review=True,
            )
        else:
            raise LateralPartialContractError(
                "IMAGE_LATERAL_PARTIAL_SNAPSHOT_INVALID",
                "Incomplete or unknown partial policy fields.",
            )
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
        "The requested geometry engine is unavailable until its quality gate is accepted.",
    )
