"""Pure contracts used by the fast image selector and its adapters."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Protocol

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FINGERPRINT = re.compile(r"^[0-9a-f]{16,256}$")


class SelectionContractError(ValueError):
    """Stable validation error for selector input or adapter output."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class SelectionGroupStatus(StrEnum):
    AUTO_SELECTED = "auto_selected"
    MANUAL_REQUIRED = "manual_required"
    SKIPPED_EXISTING_RANGE = "skipped_existing_range"


class CandidateDecision(StrEnum):
    ELIGIBLE = "eligible"
    REJECTED = "rejected"
    SELECTED_AUTOMATIC = "selected_automatic"


@dataclass(frozen=True, slots=True)
class SequenceRange:
    start: int
    end: int
    confidence: float

    def __post_init__(self) -> None:
        if self.start < 1 or self.end < self.start:
            raise SelectionContractError(
                "IMAGE_SELECTION_RANGE_INVALID",
                "A recognized range must be positive and ordered.",
            )
        if not 0 <= self.confidence <= 1:
            raise SelectionContractError(
                "IMAGE_SELECTION_RANGE_CONFIDENCE_INVALID",
                "Range confidence must be between zero and one.",
            )

    @property
    def board_count(self) -> int:
        return self.end - self.start + 1

    def to_dict(self) -> dict[str, int | float]:
        return {"confidence": self.confidence, "end": self.end, "start": self.start}


@dataclass(frozen=True, slots=True)
class ImageSelectionSource:
    order_index: int
    relative_path: str
    stored_relative_path: str
    checksum_sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        if self.order_index < 0 or self.size_bytes < 1:
            raise SelectionContractError(
                "IMAGE_SELECTION_SOURCE_INVALID",
                "Source order and byte size must be valid positive values.",
            )
        for value in (self.relative_path, self.stored_relative_path):
            path = PurePosixPath(value)
            if (
                not value
                or path.is_absolute()
                or ".." in path.parts
                or "\\" in value
                or (path.parts and ":" in path.parts[0])
            ):
                raise SelectionContractError(
                    "IMAGE_SELECTION_SOURCE_PATH_UNSAFE",
                    "Selection source paths must be managed relative POSIX paths.",
                )
        if _SHA256.fullmatch(self.checksum_sha256) is None:
            raise SelectionContractError(
                "IMAGE_SELECTION_SOURCE_CHECKSUM_INVALID",
                "Selection source checksum must be a lowercase SHA-256 value.",
            )


@dataclass(frozen=True, slots=True)
class ImageQualityMetrics:
    sharpness: float
    exposure: float
    highlight_retention: float
    glare_resistance: float
    perspective: float
    border_margin: float
    board_visibility: float
    overall_score: float

    def __post_init__(self) -> None:
        if any(not 0 <= value <= 1 for value in self.values()):
            raise SelectionContractError(
                "IMAGE_SELECTION_QUALITY_INVALID",
                "Every normalized quality metric must be between zero and one.",
            )

    def values(self) -> tuple[float, ...]:
        return (
            self.sharpness,
            self.exposure,
            self.highlight_retention,
            self.glare_resistance,
            self.perspective,
            self.border_margin,
            self.board_visibility,
            self.overall_score,
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "boardVisibility": self.board_visibility,
            "borderMargin": self.border_margin,
            "exposure": self.exposure,
            "glareResistance": self.glare_resistance,
            "highlightRetention": self.highlight_retention,
            "overallScore": self.overall_score,
            "perspective": self.perspective,
            "sharpness": self.sharpness,
        }


@dataclass(frozen=True, slots=True)
class CheapImageObservation:
    source: ImageSelectionSource
    width: int
    height: int
    fingerprint_hex: str
    geometry_signature: tuple[float, ...]
    board_count: int | None
    geometry_confidence: float
    quality: ImageQualityMetrics
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.width < 1 or self.height < 1:
            raise SelectionContractError(
                "IMAGE_SELECTION_DIMENSIONS_INVALID",
                "Observed image dimensions must be positive.",
            )
        if _FINGERPRINT.fullmatch(self.fingerprint_hex) is None:
            raise SelectionContractError(
                "IMAGE_SELECTION_FINGERPRINT_INVALID",
                "Image fingerprint must be lowercase hexadecimal data.",
            )
        if self.board_count is not None and not 1 <= self.board_count <= 9:
            raise SelectionContractError(
                "IMAGE_SELECTION_BOARD_COUNT_INVALID",
                "Observed board count must be between one and nine.",
            )
        if not 0 <= self.geometry_confidence <= 1:
            raise SelectionContractError(
                "IMAGE_SELECTION_GEOMETRY_CONFIDENCE_INVALID",
                "Geometry confidence must be between zero and one.",
            )


@dataclass(frozen=True, slots=True)
class CandidateVerification:
    recognized_range: SequenceRange | None
    board_count: int | None
    geometry_complete: bool
    full_frame_visible: bool
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CandidateResult:
    source: ImageSelectionSource
    decision: CandidateDecision
    quality: ImageQualityMetrics
    recognized_range: SequenceRange | None
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "checksumSha256": self.source.checksum_sha256,
            "decision": self.decision.value,
            "orderIndex": self.source.order_index,
            "qualityMetrics": self.quality.to_dict(),
            "range": (None if self.recognized_range is None else self.recognized_range.to_dict()),
            "reasonCodes": list(self.reason_codes),
            "sourceRelativePath": self.source.relative_path,
        }


@dataclass(frozen=True, slots=True)
class SelectionGroupResult:
    group_order: int
    source_count: int
    range: SequenceRange | None
    fingerprint_sha256: str
    board_count_consensus: int | None
    status: SelectionGroupStatus
    selected_candidate: CandidateResult | None
    top_candidates: tuple[CandidateResult, ...]
    duplicate_of_group_order: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "boardCountConsensus": self.board_count_consensus,
            "duplicateOfGroupOrder": self.duplicate_of_group_order,
            "fingerprintSha256": self.fingerprint_sha256,
            "groupOrder": self.group_order,
            "range": None if self.range is None else self.range.to_dict(),
            "selectedCandidate": (
                None if self.selected_candidate is None else self.selected_candidate.to_dict()
            ),
            "sourceCount": self.source_count,
            "status": self.status.value,
            "topCandidates": [candidate.to_dict() for candidate in self.top_candidates],
        }


@dataclass(frozen=True, slots=True)
class SelectorCheckpoint:
    schema_version: int
    selector_fingerprint: str
    next_order_index: int
    processed_count: int
    finalized_group_count: int

    def to_dict(self) -> dict[str, int | str]:
        return {
            "finalizedGroupCount": self.finalized_group_count,
            "nextOrderIndex": self.next_order_index,
            "processedCount": self.processed_count,
            "schemaVersion": self.schema_version,
            "selectorFingerprint": self.selector_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class ImageSelectionResult:
    selector_version: str
    selector_fingerprint: str
    input_count: int
    groups: tuple[SelectionGroupResult, ...]
    checkpoint: SelectorCheckpoint
    scan_failure_count: int
    verification_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "checkpoint": self.checkpoint.to_dict(),
            "groups": [group.to_dict() for group in self.groups],
            "inputCount": self.input_count,
            "scanFailureCount": self.scan_failure_count,
            "schemaVersion": 1,
            "selectorFingerprint": self.selector_fingerprint,
            "selectorVersion": self.selector_version,
            "verificationCount": self.verification_count,
        }


class CheapImageAnalyzer(Protocol):
    def analyze(self, source: ImageSelectionSource) -> CheapImageObservation:
        """Return bounded thumbnail metrics without OCR or cell crops."""


class CandidateVerifier(Protocol):
    def verify(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
    ) -> CandidateVerification:
        """Run bounded full verification for one top-k candidate."""


class SelectionAuditSink(Protocol):
    def candidate_scanned(
        self,
        observation: CheapImageObservation,
        *,
        group_order: int,
    ) -> None:
        """Persist or stream one cheap observation."""

    def checkpoint_saved(self, checkpoint: SelectorCheckpoint) -> None:
        """Persist a bounded progress checkpoint."""

    def group_finalized(self, group: SelectionGroupResult) -> None:
        """Persist the final bounded group decision and reason codes."""


class NullSelectionAuditSink:
    def candidate_scanned(
        self,
        observation: CheapImageObservation,
        *,
        group_order: int,
    ) -> None:
        del observation, group_order

    def checkpoint_saved(self, checkpoint: SelectorCheckpoint) -> None:
        del checkpoint

    def group_finalized(self, group: SelectionGroupResult) -> None:
        del group


__all__ = [
    "CandidateDecision",
    "CandidateResult",
    "CandidateVerification",
    "CandidateVerifier",
    "CheapImageAnalyzer",
    "CheapImageObservation",
    "ImageQualityMetrics",
    "ImageSelectionResult",
    "ImageSelectionSource",
    "NullSelectionAuditSink",
    "SelectionAuditSink",
    "SelectionContractError",
    "SelectionGroupResult",
    "SelectionGroupStatus",
    "SelectorCheckpoint",
    "SequenceRange",
]
