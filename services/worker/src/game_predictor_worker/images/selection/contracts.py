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
    MANUALLY_SELECTED = "manually_selected"
    MISSING_IMAGE = "missing_image"
    SKIPPED_EXISTING_RANGE = "skipped_existing_range"


class CandidateDecision(StrEnum):
    ELIGIBLE = "eligible"
    REJECTED = "rejected"
    SELECTED_AUTOMATIC = "selected_automatic"
    SELECTED_MANUAL = "selected_manual"


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

    def to_dict(self) -> dict[str, int | str]:
        return {
            "checksumSha256": self.checksum_sha256,
            "orderIndex": self.order_index,
            "relativePath": self.relative_path,
            "sizeBytes": self.size_bytes,
            "storedRelativePath": self.stored_relative_path,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> ImageSelectionSource:
        try:
            return cls(
                order_index=_int_value(value["orderIndex"]),
                relative_path=str(value["relativePath"]),
                stored_relative_path=str(value["storedRelativePath"]),
                checksum_sha256=str(value["checksumSha256"]),
                size_bytes=_int_value(value["sizeBytes"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise SelectionContractError(
                "IMAGE_SELECTION_CHECKPOINT_INVALID",
                "The selector checkpoint contains an invalid source.",
            ) from error


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

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> ImageQualityMetrics:
        try:
            return cls(
                sharpness=_float_value(value["sharpness"]),
                exposure=_float_value(value["exposure"]),
                highlight_retention=_float_value(value["highlightRetention"]),
                glare_resistance=_float_value(value["glareResistance"]),
                perspective=_float_value(value["perspective"]),
                border_margin=_float_value(value["borderMargin"]),
                board_visibility=_float_value(value["boardVisibility"]),
                overall_score=_float_value(value["overallScore"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise SelectionContractError(
                "IMAGE_SELECTION_CHECKPOINT_INVALID",
                "The selector checkpoint contains invalid quality metrics.",
            ) from error


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

    def to_checkpoint_dict(self) -> dict[str, object]:
        return {
            "boardCount": self.board_count,
            "fingerprintHex": self.fingerprint_hex,
            "geometryConfidence": self.geometry_confidence,
            "geometrySignature": list(self.geometry_signature),
            "height": self.height,
            "qualityMetrics": self.quality.to_dict(),
            "reasonCodes": list(self.reason_codes),
            "source": self.source.to_dict(),
            "width": self.width,
        }

    @classmethod
    def from_checkpoint_dict(cls, value: dict[str, object]) -> CheapImageObservation:
        try:
            source_value = value["source"]
            quality_value = value["qualityMetrics"]
            signature_value = value["geometrySignature"]
            reasons_value = value["reasonCodes"]
            if not isinstance(source_value, dict) or not isinstance(quality_value, dict):
                raise TypeError
            if not isinstance(signature_value, list) or not isinstance(reasons_value, list):
                raise TypeError
            board_count_value = value.get("boardCount")
            return cls(
                source=ImageSelectionSource.from_dict(source_value),
                width=_int_value(value["width"]),
                height=_int_value(value["height"]),
                fingerprint_hex=str(value["fingerprintHex"]),
                geometry_signature=tuple(_float_value(item) for item in signature_value),
                board_count=(None if board_count_value is None else _int_value(board_count_value)),
                geometry_confidence=_float_value(value["geometryConfidence"]),
                quality=ImageQualityMetrics.from_dict(quality_value),
                reason_codes=tuple(str(item) for item in reasons_value),
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, SelectionContractError):
                raise
            raise SelectionContractError(
                "IMAGE_SELECTION_CHECKPOINT_INVALID",
                "The selector checkpoint contains an invalid observation.",
            ) from error


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
    width: int = 1
    height: int = 1

    def to_dict(self) -> dict[str, object]:
        return {
            "checksumSha256": self.source.checksum_sha256,
            "decision": self.decision.value,
            "orderIndex": self.source.order_index,
            "qualityMetrics": self.quality.to_dict(),
            "range": (None if self.recognized_range is None else self.recognized_range.to_dict()),
            "reasonCodes": list(self.reason_codes),
            "sourceRelativePath": self.source.relative_path,
            "width": self.width,
            "height": self.height,
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
    reference_fingerprint_hex: str | None = None

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
            "referenceFingerprintHex": self.reference_fingerprint_hex,
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
class SelectorOpenGroupState:
    group_order: int
    source_count: int
    top_observations: tuple[CheapImageObservation, ...]
    board_counts: tuple[tuple[int, int], ...]
    last_observation: CheapImageObservation | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "boardCounts": [
                {"boardCount": board_count, "count": count}
                for board_count, count in self.board_counts
            ],
            "groupOrder": self.group_order,
            "lastObservation": (
                None
                if self.last_observation is None
                else self.last_observation.to_checkpoint_dict()
            ),
            "sourceCount": self.source_count,
            "topObservations": [
                observation.to_checkpoint_dict() for observation in self.top_observations
            ],
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> SelectorOpenGroupState:
        try:
            observations_value = value["topObservations"]
            board_counts_value = value["boardCounts"]
            last_observation_value = value.get("lastObservation")
            if not isinstance(observations_value, list) or not isinstance(board_counts_value, list):
                raise TypeError
            if any(not isinstance(item, dict) for item in observations_value):
                raise TypeError
            board_counts: list[tuple[int, int]] = []
            for item in board_counts_value:
                if not isinstance(item, dict):
                    raise TypeError
                board_counts.append((_int_value(item["boardCount"]), _int_value(item["count"])))
            state = cls(
                group_order=_int_value(value["groupOrder"]),
                source_count=_int_value(value["sourceCount"]),
                top_observations=tuple(
                    CheapImageObservation.from_checkpoint_dict(item)
                    for item in observations_value
                    if isinstance(item, dict)
                ),
                board_counts=tuple(board_counts),
                last_observation=(
                    None
                    if last_observation_value is None
                    else CheapImageObservation.from_checkpoint_dict(last_observation_value)
                    if isinstance(last_observation_value, dict)
                    else _invalid_observation()
                ),
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, SelectionContractError):
                raise
            raise SelectionContractError(
                "IMAGE_SELECTION_CHECKPOINT_INVALID",
                "The selector checkpoint contains an invalid open group.",
            ) from error
        if (
            state.group_order < 0
            or state.source_count < 1
            or not state.top_observations
            or (
                state.last_observation is not None
                and state.last_observation.source.order_index
                < max(observation.source.order_index for observation in state.top_observations)
            )
            or any(board_count < 1 or count < 1 for board_count, count in state.board_counts)
            or sum(count for _, count in state.board_counts) > state.source_count
        ):
            raise SelectionContractError(
                "IMAGE_SELECTION_CHECKPOINT_INVALID",
                "The selector checkpoint open group is inconsistent.",
            )
        return state


@dataclass(frozen=True, slots=True)
class SelectorResumeState:
    checkpoint: SelectorCheckpoint
    current_group: SelectorOpenGroupState | None
    pending_observations: tuple[CheapImageObservation, ...]
    scan_failure_count: int
    verification_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "checkpoint": self.checkpoint.to_dict(),
            "currentGroup": (None if self.current_group is None else self.current_group.to_dict()),
            "pendingObservations": [
                observation.to_checkpoint_dict() for observation in self.pending_observations
            ],
            "scanFailureCount": self.scan_failure_count,
            "verificationCount": self.verification_count,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> SelectorResumeState:
        try:
            checkpoint_value = value["checkpoint"]
            pending_value = value["pendingObservations"]
            current_value = value.get("currentGroup")
            if not isinstance(checkpoint_value, dict) or not isinstance(pending_value, list):
                raise TypeError
            if any(not isinstance(item, dict) for item in pending_value):
                raise TypeError
            checkpoint = SelectorCheckpoint(
                schema_version=_int_value(checkpoint_value["schemaVersion"]),
                selector_fingerprint=str(checkpoint_value["selectorFingerprint"]),
                next_order_index=_int_value(checkpoint_value["nextOrderIndex"]),
                processed_count=_int_value(checkpoint_value["processedCount"]),
                finalized_group_count=_int_value(checkpoint_value["finalizedGroupCount"]),
            )
            return cls(
                checkpoint=checkpoint,
                current_group=(
                    None
                    if current_value is None
                    else SelectorOpenGroupState.from_dict(current_value)
                    if isinstance(current_value, dict)
                    else _invalid_open_group()
                ),
                pending_observations=tuple(
                    CheapImageObservation.from_checkpoint_dict(item)
                    for item in pending_value
                    if isinstance(item, dict)
                ),
                scan_failure_count=_int_value(value["scanFailureCount"]),
                verification_count=_int_value(value["verificationCount"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, SelectionContractError):
                raise
            raise SelectionContractError(
                "IMAGE_SELECTION_CHECKPOINT_INVALID",
                "The selector checkpoint cannot be restored.",
            ) from error


def _invalid_open_group() -> SelectorOpenGroupState:
    raise SelectionContractError(
        "IMAGE_SELECTION_CHECKPOINT_INVALID",
        "The selector checkpoint contains an invalid open group.",
    )


def _invalid_observation() -> CheapImageObservation:
    raise SelectionContractError(
        "IMAGE_SELECTION_CHECKPOINT_INVALID",
        "The selector checkpoint contains an invalid last observation.",
    )


def _int_value(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        raise TypeError
    return int(value)


def _float_value(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        raise TypeError
    return float(value)


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
        """Return bounded metrics without OCR; production adapters are thread-safe."""


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
    "SelectorOpenGroupState",
    "SelectorResumeState",
    "SequenceRange",
]
