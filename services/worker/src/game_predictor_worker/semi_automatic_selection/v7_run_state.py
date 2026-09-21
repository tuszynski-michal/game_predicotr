"""Durable, fail-closed V7 scan state before any output mutation.

The existing local source manifest is the frozen identity of the folder.  This
module combines that identity with T03 occurrences and T04 quality so a worker
can resume an interrupted scan without recreating choices.  It intentionally
does not create an output operation or touch a JPEG; T08 owns that critical
section and must verify the same manifest again while holding its directory
lock.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import NoReturn, cast
from uuid import UUID

from .contracts import SemiAutomaticSelectionRange, SemiAutomaticSelectionSource
from .local_source_manifest import LocalSourceManifest
from .v7_configuration import V7BorderStyle
from .v7_occurrences import (
    V7AnalysisPhase,
    V7OccurrenceError,
    V7OccurrenceObservation,
    V7OccurrenceTracker,
    V7RunCursors,
)
from .v7_quality import (
    V7BlurSeverity,
    V7BoardQuality,
    V7BoardReadability,
    V7BoardVisibility,
    V7CropEdge,
    V7DecorationVisibility,
    V7FrameQuality,
    V7FrameQualitySummary,
    V7OcclusionSeverity,
    V7QualityError,
    V7QualityWarning,
    V7RepresentativeSelection,
    V7SymbolContentLoss,
    rank_v7_representatives,
)
from .v7_range_proof import V7RangeProofKind, V7RangeProofResult

V7_RUN_STATE_VERSION = "v7-scan-run-state-v1"
V7_RUN_STATE_CHECKPOINT_SCHEMA_VERSION = 1
_SOURCE_ID_VERSION = "v7-pinned-source-v1"
_REASON_CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,127}$")


class V7RunStateError(ValueError):
    """A run-state request or checkpoint violates its durable contract."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class V7RunStatePhase(StrEnum):
    SCANNING = "scanning"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    FINALIZATION_PENDING = "finalization_pending"
    FINALIZED = "finalized"
    BLOCKED_SOURCE_DRIFT = "blocked_source_drift"


@dataclass(frozen=True, slots=True)
class V7PinnedSource:
    """A source identity tied to its ordinal and immutable manifest entry."""

    source_index: int
    source_id: str
    relative_path: str
    size_bytes: int
    checksum_sha256: str

    @classmethod
    def from_source(cls, source: SemiAutomaticSelectionSource) -> V7PinnedSource:
        return cls(
            source_index=source.source_index,
            source_id=_source_id(source),
            relative_path=source.relative_path,
            size_bytes=source.size_bytes,
            checksum_sha256=source.checksum_sha256,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "checksumSha256": self.checksum_sha256,
            "relativePath": self.relative_path,
            "sizeBytes": self.size_bytes,
            "sourceId": self.source_id,
            "sourceIndex": self.source_index,
        }


@dataclass(frozen=True, slots=True)
class V7PinnedSourceManifest:
    """The full input identity required to resume or finalize one V7 scan."""

    selection_id: UUID
    source_root: Path
    manifest_checksum_sha256: str
    source_fingerprint: str
    sources: tuple[V7PinnedSource, ...]

    @classmethod
    def from_local_manifest(cls, manifest: LocalSourceManifest) -> V7PinnedSourceManifest:
        return cls(
            selection_id=manifest.selection_id,
            source_root=manifest.source_root,
            manifest_checksum_sha256=manifest.checksum_sha256,
            source_fingerprint=manifest.source_fingerprint,
            sources=tuple(V7PinnedSource.from_source(source) for source in manifest.sources),
        )

    def __post_init__(self) -> None:
        if not self.sources or tuple(item.source_index for item in self.sources) != tuple(
            range(len(self.sources))
        ):
            _fail("V7_SOURCE_MANIFEST_INVALID", "The v7 source manifest order is invalid.")
        if len({item.source_id for item in self.sources}) != len(self.sources):
            _fail("V7_SOURCE_MANIFEST_INVALID", "The v7 source manifest has duplicate IDs.")
        if len({item.relative_path for item in self.sources}) != len(self.sources):
            _fail("V7_SOURCE_MANIFEST_INVALID", "The v7 source manifest has duplicate paths.")
        if any(
            item.source_id
            != _source_id(
                SemiAutomaticSelectionSource(
                    item.source_index,
                    item.relative_path,
                    item.size_bytes,
                    item.checksum_sha256,
                )
            )
            for item in self.sources
        ):
            _fail("V7_SOURCE_MANIFEST_INVALID", "The v7 source manifest identity is invalid.")

    def as_dict(self) -> dict[str, object]:
        return {
            "manifestChecksumSha256": self.manifest_checksum_sha256,
            "selectionId": str(self.selection_id),
            "sourceFingerprint": self.source_fingerprint,
            "sourceRoot": str(self.source_root),
            "sources": [item.as_dict() for item in self.sources],
        }

    @classmethod
    def from_dict(cls, value: object) -> V7PinnedSourceManifest:
        raw = _mapping(value, "V7 source manifest checkpoint must be an object.")
        try:
            sources = tuple(_pinned_source(item) for item in _items(raw["sources"]))
            return cls(
                selection_id=UUID(_string(raw["selectionId"])),
                source_root=Path(_string(raw["sourceRoot"])),
                manifest_checksum_sha256=_sha256(raw["manifestChecksumSha256"]),
                source_fingerprint=_sha256(raw["sourceFingerprint"]),
                sources=sources,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise V7RunStateError(
                "V7_RUN_STATE_CHECKPOINT_INVALID", "The v7 source manifest checkpoint is invalid."
            ) from error

    def require_matches(self, manifest: LocalSourceManifest) -> None:
        """Reject every source-list change, including an unselected JPEG."""

        current = type(self).from_local_manifest(manifest)
        if current != self:
            _fail(
                "V7_SOURCE_MANIFEST_DRIFT",
                "The pinned V7 source manifest changed; automatic finalization is blocked.",
            )


@dataclass(frozen=True, slots=True)
class V7ScanObservation:
    """One complete source result.  IDs always come from the pinned manifest."""

    source_index: int
    proof: V7RangeProofResult
    quality: V7FrameQuality | None
    source_error_code: str | None = None

    def __post_init__(self) -> None:
        if self.source_index < 0:
            _fail("V7_SCAN_OBSERVATION_INVALID", "V7 source index is invalid.")
        if self.source_error_code is not None:
            if (
                not _REASON_CODE.fullmatch(self.source_error_code)
                or self.proof.kind is not V7RangeProofKind.NONE
                or self.quality is not None
            ):
                _fail("V7_SCAN_OBSERVATION_INVALID", "A V7 source error is invalid.")
        elif self.quality is None:
            _fail("V7_SCAN_OBSERVATION_INVALID", "A decoded V7 source needs frame quality.")


@dataclass(frozen=True, slots=True)
class V7RunFinalization:
    """Immutable selection proposals, before T08 creates output operations."""

    selections: tuple[V7RepresentativeSelection, ...]

    def as_dict(self) -> dict[str, object]:
        return {"selections": [_selection_as_dict(item) for item in self.selections]}


class V7ScanRunState:
    """One checkpointable source scan and its idempotent EOF finalization."""

    def __init__(
        self,
        manifest: LocalSourceManifest,
        *,
        expected_ranges: tuple[SemiAutomaticSelectionRange, ...],
        border_style: V7BorderStyle,
        checkpoint: dict[str, object] | None = None,
    ) -> None:
        self._manifest = V7PinnedSourceManifest.from_local_manifest(manifest)
        self._expected_ranges = expected_ranges
        self._border_style = border_style
        self._tracker = V7OccurrenceTracker(expected_ranges)
        self._phase = V7RunStatePhase.SCANNING
        self._qualities: dict[int, V7FrameQuality] = {}
        self._source_errors: dict[int, str] = {}
        self._finalization: V7RunFinalization | None = None
        if checkpoint is not None:
            self._restore(checkpoint)

    @property
    def phase(self) -> V7RunStatePhase:
        return self._phase

    @property
    def cursors(self) -> V7RunCursors:
        return self._tracker.cursors

    @property
    def source_manifest(self) -> V7PinnedSourceManifest:
        return self._manifest

    @property
    def source_errors(self) -> Mapping[int, str]:
        return dict(self._source_errors)

    @property
    def finalization(self) -> V7RunFinalization | None:
        return self._finalization

    def set_viewed_source_index(self, source_index: int | None) -> None:
        self._tracker.set_viewed_source_index(source_index)

    def pause(self) -> None:
        self._require_phase(V7RunStatePhase.SCANNING)
        self._tracker.pause()
        self._phase = V7RunStatePhase.PAUSED

    def resume(self) -> None:
        self._require_phase(V7RunStatePhase.PAUSED)
        self._tracker.resume()
        self._phase = V7RunStatePhase.SCANNING

    def cancel(self) -> None:
        if self._phase not in {V7RunStatePhase.SCANNING, V7RunStatePhase.PAUSED}:
            _fail("V7_RUN_STATE_PHASE_INVALID", "Only an unfinished V7 scan can be cancelled.")
        self._tracker.cancel()
        self._phase = V7RunStatePhase.CANCELLED

    def consume(self, observation: V7ScanObservation) -> None:
        self._require_phase(V7RunStatePhase.SCANNING)
        if observation.source_index != self._tracker.cursors.next_source_index:
            _fail(
                "V7_RUN_STATE_ORDER_INVALID",
                "V7 sources must be consumed in pinned manifest order.",
            )
        source = self._source_for(observation.source_index)
        if observation.source_error_code is None:
            quality = observation.quality
            assert quality is not None
            if (quality.source_id, quality.source_index) != (source.source_id, source.source_index):
                _fail(
                    "V7_SCAN_OBSERVATION_INVALID",
                    "V7 frame quality does not belong to its pinned source.",
                )
            self._qualities[source.source_index] = quality
        else:
            self._source_errors[source.source_index] = observation.source_error_code
        try:
            self._tracker.consume(
                V7OccurrenceObservation(source.source_index, source.source_id, observation.proof)
            )
        except V7OccurrenceError as error:
            self._qualities.pop(source.source_index, None)
            self._source_errors.pop(source.source_index, None)
            raise V7RunStateError("V7_SCAN_OBSERVATION_INVALID", str(error)) from error

    def complete_scan(self) -> None:
        """Close only after every pinned source produced one durable result."""

        self._require_phase(V7RunStatePhase.SCANNING)
        if self._tracker.cursors.next_source_index != len(self._manifest.sources):
            _fail(
                "V7_SCAN_INCOMPLETE", "V7 scan cannot reach EOF before every source is processed."
            )
        try:
            self._tracker.finish()
        except V7OccurrenceError as error:
            raise V7RunStateError("V7_SCAN_FINALIZATION_INVALID", str(error)) from error
        self._phase = V7RunStatePhase.FINALIZATION_PENDING

    def finalize(self, current_manifest: LocalSourceManifest) -> V7RunFinalization:
        """Return exactly one deterministic proposal set after checking folder drift."""

        if self._phase is V7RunStatePhase.BLOCKED_SOURCE_DRIFT:
            _fail(
                "V7_SOURCE_MANIFEST_DRIFT",
                "The V7 run is blocked because its source manifest changed.",
            )
        if self._phase not in {V7RunStatePhase.FINALIZATION_PENDING, V7RunStatePhase.FINALIZED}:
            _fail("V7_SCAN_FINALIZATION_REQUIRED", "V7 output proposals require a complete scan.")
        try:
            self._manifest.require_matches(current_manifest)
        except V7RunStateError as error:
            if error.code == "V7_SOURCE_MANIFEST_DRIFT":
                self._phase = V7RunStatePhase.BLOCKED_SOURCE_DRIFT
            raise
        if self._finalization is None:
            try:
                selections = rank_v7_representatives(
                    self._tracker,
                    self._qualities.values(),
                    border_style=self._border_style,
                )
            except (V7OccurrenceError, V7QualityError) as error:
                raise V7RunStateError("V7_SCAN_FINALIZATION_INVALID", str(error)) from error
            self._finalization = V7RunFinalization(selections)
        self._phase = V7RunStatePhase.FINALIZED
        return self._finalization

    def checkpoint(self) -> dict[str, object]:
        return {
            "borderStyle": self._border_style.value,
            "expectedRanges": [[item.start, item.end] for item in self._expected_ranges],
            "finalization": None if self._finalization is None else self._finalization.as_dict(),
            "frameQualities": [
                _frame_quality_as_dict(self._qualities[index]) for index in sorted(self._qualities)
            ],
            "phase": self._phase.value,
            "runStateVersion": V7_RUN_STATE_VERSION,
            "schemaVersion": V7_RUN_STATE_CHECKPOINT_SCHEMA_VERSION,
            "sourceErrors": [
                {"reasonCode": reason, "sourceIndex": index}
                for index, reason in sorted(self._source_errors.items())
            ],
            "sourceManifest": self._manifest.as_dict(),
            "tracker": self._tracker.checkpoint(),
        }

    def _restore(self, checkpoint: dict[str, object]) -> None:
        try:
            if (
                checkpoint.get("schemaVersion") != V7_RUN_STATE_CHECKPOINT_SCHEMA_VERSION
                or checkpoint.get("runStateVersion") != V7_RUN_STATE_VERSION
                or _ranges(checkpoint["expectedRanges"]) != self._expected_ranges
                or V7BorderStyle(_string(checkpoint["borderStyle"])) is not self._border_style
            ):
                raise ValueError("checkpoint contract mismatch")
            checkpoint_manifest = V7PinnedSourceManifest.from_dict(checkpoint["sourceManifest"])
            if checkpoint_manifest != self._manifest:
                _fail(
                    "V7_SOURCE_MANIFEST_DRIFT",
                    "The checkpoint was created for another V7 source manifest.",
                )
            tracker = V7OccurrenceTracker(
                self._expected_ranges,
                checkpoint=_mapping(checkpoint["tracker"], "V7 tracker checkpoint is invalid."),
            )
            phase = V7RunStatePhase(_string(checkpoint["phase"]))
            qualities = _frame_qualities(checkpoint["frameQualities"], self._manifest)
            source_errors = _source_errors(checkpoint["sourceErrors"], self._manifest)
            finalization = _finalization(checkpoint.get("finalization"))
        except V7RunStateError:
            raise
        except (KeyError, TypeError, ValueError, V7OccurrenceError, V7QualityError) as error:
            raise V7RunStateError(
                "V7_RUN_STATE_CHECKPOINT_INVALID", "The V7 scan checkpoint is invalid."
            ) from error
        _validate_restored_state(
            manifest=self._manifest,
            tracker=tracker,
            phase=phase,
            qualities=qualities,
            source_errors=source_errors,
            finalization=finalization,
            border_style=self._border_style,
        )
        self._tracker = tracker
        self._phase = phase
        self._qualities = qualities
        self._source_errors = source_errors
        self._finalization = finalization

    def _source_for(self, source_index: int) -> V7PinnedSource:
        if not 0 <= source_index < len(self._manifest.sources):
            _fail("V7_RUN_STATE_ORDER_INVALID", "The source is outside the pinned V7 manifest.")
        return self._manifest.sources[source_index]

    def _require_phase(self, expected: V7RunStatePhase) -> None:
        if self._phase is not expected:
            _fail(
                "V7_RUN_STATE_PHASE_INVALID",
                f"V7 operation requires {expected.value}, received {self._phase.value}.",
            )


def _validate_restored_state(
    *,
    manifest: V7PinnedSourceManifest,
    tracker: V7OccurrenceTracker,
    phase: V7RunStatePhase,
    qualities: dict[int, V7FrameQuality],
    source_errors: dict[int, str],
    finalization: V7RunFinalization | None,
    border_style: V7BorderStyle,
) -> None:
    next_index = tracker.cursors.next_source_index
    processed = set(range(next_index))
    if (
        set(qualities).intersection(source_errors)
        or set(qualities).union(source_errors) != processed
    ):
        _fail(
            "V7_RUN_STATE_CHECKPOINT_INVALID",
            "Each processed V7 source needs exactly one quality or source error result.",
        )
    if any(
        (quality.source_id, quality.source_index) != (manifest.sources[index].source_id, index)
        for index, quality in qualities.items()
    ):
        _fail("V7_RUN_STATE_CHECKPOINT_INVALID", "V7 checkpoint quality has a foreign source.")
    expected_tracker_phase = {
        V7RunStatePhase.SCANNING: V7AnalysisPhase.RUNNING,
        V7RunStatePhase.PAUSED: V7AnalysisPhase.PAUSED,
        V7RunStatePhase.CANCELLED: V7AnalysisPhase.CANCELLED,
        V7RunStatePhase.FINALIZATION_PENDING: V7AnalysisPhase.COMPLETE,
        V7RunStatePhase.FINALIZED: V7AnalysisPhase.COMPLETE,
        V7RunStatePhase.BLOCKED_SOURCE_DRIFT: V7AnalysisPhase.COMPLETE,
    }[phase]
    if tracker.phase is not expected_tracker_phase:
        _fail("V7_RUN_STATE_CHECKPOINT_INVALID", "V7 phase disagrees with tracker state.")
    requires_complete_scan = {
        V7RunStatePhase.FINALIZATION_PENDING,
        V7RunStatePhase.FINALIZED,
        V7RunStatePhase.BLOCKED_SOURCE_DRIFT,
    }
    if phase in requires_complete_scan and next_index != len(manifest.sources):
        _fail("V7_RUN_STATE_CHECKPOINT_INVALID", "V7 finalization lacks a complete source scan.")
    if phase is V7RunStatePhase.FINALIZED and finalization is None:
        _fail("V7_RUN_STATE_CHECKPOINT_INVALID", "V7 finalization state is inconsistent.")
    if (
        phase
        not in {
            V7RunStatePhase.FINALIZED,
            V7RunStatePhase.BLOCKED_SOURCE_DRIFT,
        }
        and finalization is not None
    ):
        _fail("V7_RUN_STATE_CHECKPOINT_INVALID", "Only finalized V7 runs may contain proposals.")
    if finalization is not None:
        try:
            expected = V7RunFinalization(
                rank_v7_representatives(tracker, qualities.values(), border_style=border_style)
            )
        except (V7OccurrenceError, V7QualityError) as error:
            raise V7RunStateError("V7_RUN_STATE_CHECKPOINT_INVALID", str(error)) from error
        if finalization != expected:
            _fail("V7_RUN_STATE_CHECKPOINT_INVALID", "V7 proposals do not match durable ranking.")


def _source_id(source: SemiAutomaticSelectionSource) -> str:
    payload = {"source": source.as_dict(), "version": _SOURCE_ID_VERSION}
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _frame_quality_as_dict(value: V7FrameQuality) -> dict[str, object]:
    return {
        "boards": [
            {
                "blur": board.blur.value,
                "croppedEdges": sorted(edge.value for edge in board.cropped_edges),
                "decoration": board.decoration.value,
                "occlusion": board.occlusion.value,
                "positionIndex": board.position_index,
                "readability": board.readability.value,
                "symbolContentLoss": board.symbol_content_loss.value,
                "visibility": board.visibility.value,
            }
            for board in value.boards
        ],
        "sourceId": value.source_id,
        "sourceIndex": value.source_index,
    }


def _frame_qualities(
    value: object,
    manifest: V7PinnedSourceManifest,
) -> dict[int, V7FrameQuality]:
    result: dict[int, V7FrameQuality] = {}
    for item in _items(value):
        raw = _mapping(item, "V7 frame quality checkpoint must be an object.")
        boards = tuple(_board_quality(board) for board in _items(raw["boards"]))
        quality = V7FrameQuality(
            source_id=_string(raw["sourceId"]),
            source_index=_int(raw["sourceIndex"]),
            boards=boards,
        )
        if (
            quality.source_index in result
            or not 0 <= quality.source_index < len(manifest.sources)
            or quality.source_id != manifest.sources[quality.source_index].source_id
        ):
            _fail("V7_RUN_STATE_CHECKPOINT_INVALID", "V7 frame quality is duplicated or foreign.")
        result[quality.source_index] = quality
    return result


def _board_quality(value: object) -> V7BoardQuality:
    raw = _mapping(value, "V7 board quality checkpoint must be an object.")
    try:
        return V7BoardQuality(
            position_index=_int(raw["positionIndex"]),
            symbol_content_loss=V7SymbolContentLoss(_string(raw["symbolContentLoss"])),
            readability=V7BoardReadability(_string(raw["readability"])),
            visibility=V7BoardVisibility(_string(raw["visibility"])),
            blur=V7BlurSeverity(_string(raw["blur"])),
            occlusion=V7OcclusionSeverity(_string(raw["occlusion"])),
            decoration=V7DecorationVisibility(_string(raw["decoration"])),
            cropped_edges=frozenset(
                V7CropEdge(_string(edge)) for edge in _items(raw["croppedEdges"])
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise V7RunStateError(
            "V7_RUN_STATE_CHECKPOINT_INVALID", "V7 board quality checkpoint is invalid."
        ) from error


def _source_errors(value: object, manifest: V7PinnedSourceManifest) -> dict[int, str]:
    result: dict[int, str] = {}
    for item in _items(value):
        raw = _mapping(item, "V7 source-error checkpoint must be an object.")
        source_index = _int(raw["sourceIndex"])
        reason = _string(raw["reasonCode"])
        if (
            source_index in result
            or not 0 <= source_index < len(manifest.sources)
            or not _REASON_CODE.fullmatch(reason)
        ):
            _fail("V7_RUN_STATE_CHECKPOINT_INVALID", "V7 source error is invalid.")
        result[source_index] = reason
    return result


def _selection_as_dict(value: V7RepresentativeSelection) -> dict[str, object]:
    return {
        "expectedIndex": value.expected_index,
        "occurrenceCenterDistanceNumerator": value.occurrence_center_distance_numerator,
        "occurrenceId": value.occurrence_id,
        "proofKinds": [item.value for item in value.proof_kinds],
        "quality": _summary_as_dict(value.quality),
        "rangeEnd": value.sequence_range.end,
        "rangeStart": value.sequence_range.start,
        "sourceId": value.source_id,
        "sourceIndex": value.source_index,
    }


def _summary_as_dict(value: V7FrameQualitySummary) -> dict[str, object]:
    return {
        "blur": value.blur,
        "decoration": value.decoration,
        "occlusion": value.occlusion,
        "readability": value.readability,
        "symbolContentLoss": value.symbol_content_loss,
        "visibility": value.visibility,
        "warnings": [item.value for item in value.warnings],
    }


def _finalization(value: object) -> V7RunFinalization | None:
    if value is None:
        return None
    raw = _mapping(value, "V7 finalization checkpoint must be an object.")
    selections = tuple(_selection(item) for item in _items(raw["selections"]))
    indexes = tuple(item.expected_index for item in selections)
    if indexes != tuple(sorted(set(indexes))):
        _fail("V7_RUN_STATE_CHECKPOINT_INVALID", "V7 finalization ranges are not unique.")
    return V7RunFinalization(selections)


def _selection(value: object) -> V7RepresentativeSelection:
    raw = _mapping(value, "V7 selection checkpoint must be an object.")
    try:
        return V7RepresentativeSelection(
            expected_index=_int(raw["expectedIndex"]),
            sequence_range=SemiAutomaticSelectionRange(
                _int(raw["rangeStart"]), _int(raw["rangeEnd"])
            ),
            occurrence_id=_string(raw["occurrenceId"]),
            source_id=_string(raw["sourceId"]),
            source_index=_int(raw["sourceIndex"]),
            proof_kinds=tuple(
                V7RangeProofKind(_string(item)) for item in _items(raw["proofKinds"])
            ),
            quality=_summary(raw["quality"]),
            occurrence_center_distance_numerator=_int(raw["occurrenceCenterDistanceNumerator"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise V7RunStateError(
            "V7_RUN_STATE_CHECKPOINT_INVALID", "V7 selection checkpoint is invalid."
        ) from error


def _summary(value: object) -> V7FrameQualitySummary:
    raw = _mapping(value, "V7 quality summary checkpoint must be an object.")
    try:
        return V7FrameQualitySummary(
            symbol_content_loss=_int(raw["symbolContentLoss"]),
            readability=_int(raw["readability"]),
            visibility=_int(raw["visibility"]),
            blur=_int(raw["blur"]),
            occlusion=_int(raw["occlusion"]),
            decoration=_int(raw["decoration"]),
            warnings=tuple(V7QualityWarning(_string(item)) for item in _items(raw["warnings"])),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise V7RunStateError(
            "V7_RUN_STATE_CHECKPOINT_INVALID", "V7 quality summary checkpoint is invalid."
        ) from error


def _pinned_source(value: object) -> V7PinnedSource:
    raw = _mapping(value, "V7 pinned source checkpoint must be an object.")
    try:
        return V7PinnedSource(
            source_index=_int(raw["sourceIndex"]),
            source_id=_sha256(raw["sourceId"]),
            relative_path=_string(raw["relativePath"]),
            size_bytes=_int(raw["sizeBytes"]),
            checksum_sha256=_sha256(raw["checksumSha256"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise V7RunStateError(
            "V7_RUN_STATE_CHECKPOINT_INVALID", "V7 pinned source checkpoint is invalid."
        ) from error


def _ranges(value: object) -> tuple[SemiAutomaticSelectionRange, ...]:
    result: list[SemiAutomaticSelectionRange] = []
    for item in _items(value):
        if not isinstance(item, list) or len(item) != 2:
            _fail("V7_RUN_STATE_CHECKPOINT_INVALID", "V7 expected range is invalid.")
        result.append(SemiAutomaticSelectionRange(_int(item[0]), _int(item[1])))
    return tuple(result)


def _mapping(value: object, message: str) -> dict[str, object]:
    if not isinstance(value, dict):
        _fail("V7_RUN_STATE_CHECKPOINT_INVALID", message)
    return cast(dict[str, object], value)


def _items(value: object) -> list[object]:
    if not isinstance(value, list):
        _fail("V7_RUN_STATE_CHECKPOINT_INVALID", "V7 checkpoint list is invalid.")
    return value


def _string(value: object) -> str:
    if not isinstance(value, str) or not value:
        _fail("V7_RUN_STATE_CHECKPOINT_INVALID", "V7 checkpoint string is invalid.")
    return value


def _int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail("V7_RUN_STATE_CHECKPOINT_INVALID", "V7 checkpoint integer is invalid.")
    return value


def _sha256(value: object) -> str:
    result = _string(value)
    if len(result) != 64 or any(character not in "0123456789abcdef" for character in result):
        _fail("V7_RUN_STATE_CHECKPOINT_INVALID", "V7 checkpoint SHA-256 is invalid.")
    return result


def _fail(code: str, message: str) -> NoReturn:
    raise V7RunStateError(code, message)


__all__ = [
    "V7PinnedSource",
    "V7PinnedSourceManifest",
    "V7RunFinalization",
    "V7RunStateError",
    "V7RunStatePhase",
    "V7ScanObservation",
    "V7ScanRunState",
]
