"""V4.1 grouping over source-local exact middle-row proofs.

Unknown observations can bridge two exact proofs for the same range, but they
never extend the evidence span and can never become output candidates.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import NoReturn, cast

from .contracts import (
    RangeEvidenceResult,
    RangeEvidenceStatus,
    SemiAutomaticSelectionError,
    SemiAutomaticSelectionRange,
)
from .engine import RangeGroup, RangeGroupSelection

MIDDLE_ROW_GROUPING_VERSION = "middle-row-exact-span-grouping-v1"
MIDDLE_ROW_EVIDENCE_SELECTOR_VERSION = "middle-row-evidence-span-midpoint-v1"
MIDDLE_ROW_GROUPING_CHECKPOINT_VERSION = 1
MIDDLE_ROW_MAXIMUM_UNKNOWN_GAP = 160
MIDDLE_ROW_GROUPING_CALIBRATION_MANIFEST_SHA256 = (
    "3ad20befe90d214c46cd671fecbd29105fd9eb60b91c93524057ce57ce42b0ff"
)


def middle_row_grouping_policy_fingerprint() -> str:
    return _canonical_sha256(
        {
            "algorithmVersion": MIDDLE_ROW_GROUPING_VERSION,
            "calibrationManifestSha256": (MIDDLE_ROW_GROUPING_CALIBRATION_MANIFEST_SHA256),
            "maximumConsecutiveUnknownSources": MIDDLE_ROW_MAXIMUM_UNKNOWN_GAP,
            "selectorVersion": MIDDLE_ROW_EVIDENCE_SELECTOR_VERSION,
        }
    )


@dataclass(slots=True)
class _OpenExactSpan:
    expected_index: int
    sequence_range: SemiAutomaticSelectionRange
    first_exact_source_index: int
    last_exact_source_index: int
    exact_observation_count: int = 1
    unknown_after_last_exact: int = 0
    exact_candidates: list[RangeEvidenceResult] = field(default_factory=list)

    @classmethod
    def from_exact(cls, evidence: RangeEvidenceResult) -> _OpenExactSpan:
        if (
            evidence.status is not RangeEvidenceStatus.EXACT_RANGE
            or evidence.expected_index is None
            or evidence.observed_range is None
        ):
            _fail(
                "SEMI_AUTOMATIC_SELECTION_RANGE_PROOF_INSUFFICIENT",
                "Only an exact middle-row proof can open a v4.1 group.",
            )
        return cls(
            expected_index=evidence.expected_index,
            sequence_range=evidence.observed_range,
            first_exact_source_index=evidence.source.source_index,
            last_exact_source_index=evidence.source.source_index,
            exact_candidates=[evidence],
        )

    def append_exact(self, evidence: RangeEvidenceResult) -> None:
        self.last_exact_source_index = evidence.source.source_index
        self.exact_observation_count += 1
        self.unknown_after_last_exact = 0
        self.exact_candidates.append(evidence)

    def to_checkpoint(self) -> dict[str, object]:
        return {
            "exactCandidates": [_candidate_to_dict(item) for item in self.exact_candidates],
            "exactObservationCount": self.exact_observation_count,
            "expectedIndex": self.expected_index,
            "firstExactSourceIndex": self.first_exact_source_index,
            "lastExactSourceIndex": self.last_exact_source_index,
            "rangeEnd": self.sequence_range.end,
            "rangeStart": self.sequence_range.start,
            "unknownAfterLastExact": self.unknown_after_last_exact,
        }

    @classmethod
    def from_checkpoint(cls, value: object) -> _OpenExactSpan | None:
        if value is None:
            return None
        if not isinstance(value, Mapping):
            _fail(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "The v4.1 active group checkpoint must be an object.",
            )
        raw = cast(Mapping[str, object], value)
        try:
            candidates_raw = raw.get("exactCandidates", [])
            if not isinstance(candidates_raw, list):
                raise TypeError("candidate list")
            result = cls(
                expected_index=_as_int(raw["expectedIndex"]),
                sequence_range=SemiAutomaticSelectionRange(
                    start=_as_int(raw["rangeStart"]),
                    end=_as_int(raw["rangeEnd"]),
                ),
                first_exact_source_index=_as_int(raw["firstExactSourceIndex"]),
                last_exact_source_index=_as_int(raw["lastExactSourceIndex"]),
                exact_observation_count=_as_int(raw["exactObservationCount"]),
                unknown_after_last_exact=_as_int(raw["unknownAfterLastExact"]),
                exact_candidates=[
                    _candidate_from_dict(cast(Mapping[str, object], item))
                    for item in candidates_raw
                ],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "The v4.1 active group checkpoint is invalid.",
            ) from error
        if (
            result.expected_index < 0
            or result.first_exact_source_index < 0
            or result.last_exact_source_index < result.first_exact_source_index
            or result.exact_observation_count < 1
            or result.unknown_after_last_exact < 0
            or len(result.exact_candidates) != result.exact_observation_count
            or any(
                candidate.expected_index != result.expected_index
                or candidate.observed_range != result.sequence_range
                for candidate in result.exact_candidates
            )
        ):
            _fail(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "The v4.1 active group checkpoint is inconsistent.",
            )
        return result


@dataclass(frozen=True, slots=True)
class FinalizedMiddleRowGroup:
    group: RangeGroup
    selection: RangeGroupSelection


class MiddleRowGroupingAccumulator:
    """Bounded grouping whose interval is exactly its own-proof evidence span."""

    def __init__(
        self,
        *,
        maximum_consecutive_unknown_sources: int = MIDDLE_ROW_MAXIMUM_UNKNOWN_GAP,
        checkpoint: Mapping[str, object] | None = None,
    ) -> None:
        if maximum_consecutive_unknown_sources < 0:
            raise ValueError("Maximum unknown gap cannot be negative.")
        self._maximum_gap = maximum_consecutive_unknown_sources
        self._next_source_index = 0
        self._next_group_order = 0
        self._active: _OpenExactSpan | None = None
        if checkpoint is not None:
            self._restore(checkpoint)

    @property
    def next_source_index(self) -> int:
        return self._next_source_index

    @property
    def next_group_order(self) -> int:
        return self._next_group_order

    def consume(self, evidence: RangeEvidenceResult) -> tuple[FinalizedMiddleRowGroup, ...]:
        if evidence.source.source_index != self._next_source_index:
            _fail(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "V4.1 observations must be consumed once in contiguous order.",
            )
        self._next_source_index += 1
        if evidence.status is RangeEvidenceStatus.EXACT_RANGE:
            return self._consume_exact(evidence)
        return self._consume_unknown()

    def finish(self) -> tuple[FinalizedMiddleRowGroup, ...]:
        if self._active is None:
            return ()
        value = self._finalize(self._active)
        self._active = None
        return (value,)

    def checkpoint(self) -> dict[str, object]:
        return {
            "activeGroup": None if self._active is None else self._active.to_checkpoint(),
            "algorithmVersion": MIDDLE_ROW_GROUPING_VERSION,
            "maximumConsecutiveUnknownSources": self._maximum_gap,
            "nextGroupOrder": self._next_group_order,
            "nextSourceIndex": self._next_source_index,
            "schemaVersion": MIDDLE_ROW_GROUPING_CHECKPOINT_VERSION,
        }

    def _consume_unknown(self) -> tuple[FinalizedMiddleRowGroup, ...]:
        if self._active is None:
            return ()
        self._active.unknown_after_last_exact += 1
        if self._active.unknown_after_last_exact <= self._maximum_gap:
            return ()
        result = self._finalize(self._active)
        self._active = None
        return (result,)

    def _consume_exact(
        self,
        evidence: RangeEvidenceResult,
    ) -> tuple[FinalizedMiddleRowGroup, ...]:
        if self._active is None:
            self._active = _OpenExactSpan.from_exact(evidence)
            return ()
        if (
            evidence.expected_index == self._active.expected_index
            and evidence.observed_range == self._active.sequence_range
            and self._active.unknown_after_last_exact <= self._maximum_gap
        ):
            self._active.append_exact(evidence)
            return ()
        previous = self._finalize(self._active)
        self._active = _OpenExactSpan.from_exact(evidence)
        return (previous,)

    def _finalize(self, value: _OpenExactSpan) -> FinalizedMiddleRowGroup:
        group = RangeGroup(
            group_order=self._next_group_order,
            expected_index=value.expected_index,
            sequence_range=value.sequence_range,
            first_source_index=value.first_exact_source_index,
            last_source_index=value.last_exact_source_index,
            exact_observation_count=value.exact_observation_count,
            reason_codes=("MIDDLE_ROW_EXACT_EVIDENCE_SPAN",),
        )
        self._next_group_order += 1
        return FinalizedMiddleRowGroup(
            group=group,
            selection=select_middle_row_exact_observation(group, value.exact_candidates),
        )

    def _restore(self, checkpoint: Mapping[str, object]) -> None:
        try:
            if (
                checkpoint.get("schemaVersion") != MIDDLE_ROW_GROUPING_CHECKPOINT_VERSION
                or checkpoint.get("algorithmVersion") != MIDDLE_ROW_GROUPING_VERSION
                or _as_int(checkpoint["maximumConsecutiveUnknownSources"]) != self._maximum_gap
            ):
                raise ValueError("contract mismatch")
            self._next_source_index = _as_int(checkpoint["nextSourceIndex"])
            self._next_group_order = _as_int(checkpoint["nextGroupOrder"])
            self._active = _OpenExactSpan.from_checkpoint(checkpoint.get("activeGroup"))
        except (KeyError, TypeError, ValueError) as error:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "The v4.1 grouping checkpoint does not match its policy.",
            ) from error
        if self._next_source_index < 0 or self._next_group_order < 0:
            _fail(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "The v4.1 grouping checkpoint contains negative progress.",
            )


def select_middle_row_exact_observation(
    group: RangeGroup,
    evidence: Iterable[RangeEvidenceResult],
) -> RangeGroupSelection:
    """Select own-proof evidence closest to the exact evidence-span midpoint."""

    candidates = tuple(
        item
        for item in evidence
        if item.status is RangeEvidenceStatus.EXACT_RANGE
        and item.expected_index == group.expected_index
        and item.observed_range == group.sequence_range
        and group.first_source_index <= item.source.source_index <= group.last_source_index
    )
    if not candidates:
        _fail(
            "SEMI_AUTOMATIC_SELECTION_RANGE_PROOF_INSUFFICIENT",
            "The v4.1 group contains no source-local exact proof.",
        )
    midpoint = (group.first_source_index + group.last_source_index) / 2

    def key(item: RangeEvidenceResult) -> tuple[float, float, float, int, str]:
        readability = item.local_readability_score or 0.0
        minimum_confidence = (
            item.minimum_ocr_confidence
            if item.minimum_ocr_confidence is not None
            else (item.confidence or 0.0)
        )
        return (
            abs(item.source.source_index - midpoint),
            -readability,
            -minimum_confidence,
            item.source.source_index,
            item.source.relative_path,
        )

    selected = min(candidates, key=key)
    return RangeGroupSelection(
        group=group,
        evidence=selected,
        selection_method=MIDDLE_ROW_EVIDENCE_SELECTOR_VERSION,
    )


def _candidate_to_dict(value: RangeEvidenceResult) -> dict[str, object]:
    if value.observed_range is None or value.expected_index is None:
        raise ValueError("Only exact candidates are checkpointed.")
    return {
        "confidence": value.confidence,
        "expectedIndex": value.expected_index,
        "localReadabilityScore": value.local_readability_score,
        "minimumOcrConfidence": value.minimum_ocr_confidence,
        "observationKey": value.observation_key,
        "rangeEnd": value.observed_range.end,
        "rangeStart": value.observed_range.start,
        "source": value.source.as_dict(),
    }


def _candidate_from_dict(value: Mapping[str, object]) -> RangeEvidenceResult:
    from .contracts import SemiAutomaticSelectionSource

    source_raw = cast(Mapping[str, object], value["source"])
    confidence = value.get("confidence")
    readability = value.get("localReadabilityScore")
    minimum_confidence = value.get("minimumOcrConfidence")
    observation_key = value.get("observationKey")
    return RangeEvidenceResult(
        source=SemiAutomaticSelectionSource(
            source_index=_as_int(source_raw["sourceIndex"]),
            relative_path=str(source_raw["relativePath"]),
            size_bytes=_as_int(source_raw["sizeBytes"]),
            checksum_sha256=str(source_raw["checksumSha256"]),
        ),
        status=RangeEvidenceStatus.EXACT_RANGE,
        observed_range=SemiAutomaticSelectionRange(
            start=_as_int(value["rangeStart"]),
            end=_as_int(value["rangeEnd"]),
        ),
        expected_index=_as_int(value["expectedIndex"]),
        confidence=None if confidence is None else float(cast(float | int | str, confidence)),
        reason_codes=("MIDDLE_ROW_TRIPLE_EXACT",),
        local_readability_score=(
            None if readability is None else float(cast(float | int | str, readability))
        ),
        minimum_ocr_confidence=(
            None
            if minimum_confidence is None
            else float(cast(float | int | str, minimum_confidence))
        ),
        observation_key=None if observation_key is None else str(observation_key),
    )


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise TypeError("value is not an integer")
    return int(value)


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _fail(code: str, message: str) -> NoReturn:
    raise SemiAutomaticSelectionError(code, message)


__all__ = [
    "MIDDLE_ROW_EVIDENCE_SELECTOR_VERSION",
    "MIDDLE_ROW_GROUPING_CHECKPOINT_VERSION",
    "MIDDLE_ROW_GROUPING_VERSION",
    "MIDDLE_ROW_MAXIMUM_UNKNOWN_GAP",
    "FinalizedMiddleRowGroup",
    "MiddleRowGroupingAccumulator",
    "middle_row_grouping_policy_fingerprint",
    "select_middle_row_exact_observation",
]
