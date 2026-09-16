"""Deterministic range-only grouping for semi-automatic image selection.

The engine consumes already classified OCR evidence.  It intentionally has no
image, geometry, crop-quality, or symbol-classification inputs.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import NoReturn, cast

from .contracts import (
    RangeEvidenceResult,
    RangeEvidenceStatus,
    SemiAutomaticSelectionError,
    SemiAutomaticSelectionRange,
)

RANGE_GROUPING_ALGORITHM_VERSION = "semi-automatic-range-grouping-v1"
MIDDLE_EXACT_SELECTOR_VERSION = "middle-exact-range-proof-v1"
RANGE_GROUPING_CHECKPOINT_SCHEMA_VERSION = 1
RANGE_GROUPING_MAXIMUM_UNPROVEN_SOURCES = 160
RANGE_GROUPING_CALIBRATION_MANIFEST_SHA256 = (
    "3ad20befe90d214c46cd671fecbd29105fd9eb60b91c93524057ce57ce42b0ff"
)

_NATURAL_PART = re.compile(r"(\d+)")


def grouping_policy_fingerprint() -> str:
    """Fingerprint every parameter that can change grouping or selection."""

    return _canonical_sha256(
        {
            "algorithmVersion": RANGE_GROUPING_ALGORITHM_VERSION,
            "calibrationManifestSha256": RANGE_GROUPING_CALIBRATION_MANIFEST_SHA256,
            "maximumConsecutiveUnprovenSources": RANGE_GROUPING_MAXIMUM_UNPROVEN_SOURCES,
            "selectorVersion": MIDDLE_EXACT_SELECTOR_VERSION,
        }
    )


@dataclass(frozen=True, slots=True)
class RangeGroup:
    """One finalized source interval supported by at least one exact proof."""

    group_order: int
    expected_index: int
    sequence_range: SemiAutomaticSelectionRange
    first_source_index: int
    last_source_index: int
    exact_observation_count: int
    isolated_source_indexes: tuple[int, ...] = ()
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            self.group_order < 0
            or self.expected_index < 0
            or self.first_source_index < 0
            or self.last_source_index < self.first_source_index
            or self.exact_observation_count < 1
        ):
            _fail("SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID", "A range group is invalid.")

    @property
    def midpoint(self) -> float:
        return (self.first_source_index + self.last_source_index) / 2

    def to_dict(self) -> dict[str, object]:
        return {
            "exactObservationCount": self.exact_observation_count,
            "expectedIndex": self.expected_index,
            "firstSourceIndex": self.first_source_index,
            "groupOrder": self.group_order,
            "isolatedSourceIndexes": list(self.isolated_source_indexes),
            "lastSourceIndex": self.last_source_index,
            "rangeEnd": self.sequence_range.end,
            "rangeStart": self.sequence_range.start,
            "reasonCodes": list(self.reason_codes),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> RangeGroup:
        try:
            return cls(
                group_order=_as_int(value["groupOrder"]),
                expected_index=_as_int(value["expectedIndex"]),
                sequence_range=SemiAutomaticSelectionRange(
                    start=_as_int(value["rangeStart"]),
                    end=_as_int(value["rangeEnd"]),
                ),
                first_source_index=_as_int(value["firstSourceIndex"]),
                last_source_index=_as_int(value["lastSourceIndex"]),
                exact_observation_count=_as_int(value["exactObservationCount"]),
                isolated_source_indexes=tuple(
                    _as_int(item)
                    for item in cast(list[object], value.get("isolatedSourceIndexes", []))
                ),
                reason_codes=tuple(
                    str(item) for item in cast(list[object], value.get("reasonCodes", []))
                ),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "A persisted range group is invalid.",
            ) from error


@dataclass(frozen=True, slots=True)
class RangeGroupSelection:
    """The exact-proof source nearest to the source interval midpoint."""

    group: RangeGroup
    evidence: RangeEvidenceResult
    selection_method: str = MIDDLE_EXACT_SELECTOR_VERSION

    def __post_init__(self) -> None:
        if (
            not self.evidence.is_exact_range
            or self.evidence.expected_index != self.group.expected_index
            or self.evidence.observed_range != self.group.sequence_range
            or not (
                self.group.first_source_index
                <= self.evidence.source.source_index
                <= self.group.last_source_index
            )
        ):
            _fail(
                "SEMI_AUTOMATIC_SELECTION_RANGE_PROOF_INSUFFICIENT",
                "A selected source must carry exact local proof for its group.",
            )

    def to_dict(self) -> dict[str, object]:
        return {
            **self.group.to_dict(),
            "selectedConfidence": self.evidence.confidence,
            "selectedSourceChecksumSha256": self.evidence.source.checksum_sha256,
            "selectedSourceIndex": self.evidence.source.source_index,
            "selectedSourceRelativePath": self.evidence.source.relative_path,
            "selectionMethod": self.selection_method,
        }


@dataclass(slots=True)
class _OpenGroup:
    expected_index: int
    sequence_range: SemiAutomaticSelectionRange
    first_source_index: int
    last_source_index: int
    exact_observation_count: int = 1
    unproven_after_last_exact: int = 0
    isolated_source_indexes: list[int] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)

    @classmethod
    def exact(cls, evidence: RangeEvidenceResult) -> _OpenGroup:
        if (
            not evidence.is_exact_range
            or evidence.expected_index is None
            or evidence.observed_range is None
        ):
            _fail(
                "SEMI_AUTOMATIC_SELECTION_RANGE_PROOF_INSUFFICIENT",
                "Only exact local range proof can open a group.",
            )
        return cls(
            expected_index=evidence.expected_index,
            sequence_range=evidence.observed_range,
            first_source_index=evidence.source.source_index,
            last_source_index=evidence.source.source_index,
        )

    def append_exact(self, source_index: int) -> None:
        self.last_source_index = source_index
        self.exact_observation_count += 1
        self.unproven_after_last_exact = 0

    def append_unproven(self, source_index: int) -> None:
        self.last_source_index = source_index
        self.unproven_after_last_exact += 1

    def as_checkpoint(self) -> dict[str, object]:
        return {
            "exactObservationCount": self.exact_observation_count,
            "expectedIndex": self.expected_index,
            "firstSourceIndex": self.first_source_index,
            "isolatedSourceIndexes": list(self.isolated_source_indexes),
            "lastSourceIndex": self.last_source_index,
            "rangeEnd": self.sequence_range.end,
            "rangeStart": self.sequence_range.start,
            "reasonCodes": list(self.reason_codes),
            "unprovenAfterLastExact": self.unproven_after_last_exact,
        }

    @classmethod
    def from_checkpoint(cls, value: object) -> _OpenGroup | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            _fail(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "An open range-group checkpoint must be an object.",
            )
        raw = cast(dict[str, object], value)
        try:
            group = cls(
                expected_index=_as_int(raw["expectedIndex"]),
                sequence_range=SemiAutomaticSelectionRange(
                    start=_as_int(raw["rangeStart"]),
                    end=_as_int(raw["rangeEnd"]),
                ),
                first_source_index=_as_int(raw["firstSourceIndex"]),
                last_source_index=_as_int(raw["lastSourceIndex"]),
                exact_observation_count=_as_int(raw["exactObservationCount"]),
                unproven_after_last_exact=_as_int(raw["unprovenAfterLastExact"]),
                isolated_source_indexes=[
                    _as_int(item)
                    for item in cast(list[object], raw.get("isolatedSourceIndexes", []))
                ],
                reason_codes=[str(item) for item in cast(list[object], raw.get("reasonCodes", []))],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "An open range-group checkpoint is invalid.",
            ) from error
        if (
            group.expected_index < 0
            or group.first_source_index < 0
            or group.last_source_index < group.first_source_index
            or group.exact_observation_count < 1
            or group.unproven_after_last_exact < 0
        ):
            _fail(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "An open range-group checkpoint has invalid counters.",
            )
        return group


class RangeGroupingAccumulator:
    """Bounded-memory accumulator with one confirmed and one pending group."""

    def __init__(
        self,
        *,
        maximum_consecutive_unproven_sources: int = (RANGE_GROUPING_MAXIMUM_UNPROVEN_SOURCES),
        checkpoint: dict[str, object] | None = None,
    ) -> None:
        if maximum_consecutive_unproven_sources < 0:
            raise ValueError("The unproven-source gap must be non-negative.")
        self._maximum_gap = maximum_consecutive_unproven_sources
        self._next_source_index = 0
        self._next_group_order = 0
        self._current: _OpenGroup | None = None
        self._pending: _OpenGroup | None = None
        if checkpoint:
            self._restore(checkpoint)

    @property
    def next_source_index(self) -> int:
        return self._next_source_index

    def consume(self, evidence: RangeEvidenceResult) -> tuple[RangeGroup, ...]:
        source_index = evidence.source.source_index
        if source_index != self._next_source_index:
            _fail(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "Range observations must be consumed once in contiguous source order.",
            )
        self._next_source_index += 1
        if evidence.status is not RangeEvidenceStatus.EXACT_RANGE:
            return self._consume_unproven(source_index)
        return self._consume_exact(evidence)

    def finish(self) -> tuple[RangeGroup, ...]:
        finalized: list[RangeGroup] = []
        if self._pending is not None:
            if self._current is not None:
                finalized.append(
                    self._finalize(
                        self._current,
                        last_source_index=self._pending.first_source_index - 1,
                    )
                )
            finalized.append(self._finalize(self._pending))
        elif self._current is not None:
            finalized.append(self._finalize(self._current))
        self._current = None
        self._pending = None
        return tuple(finalized)

    def checkpoint(self) -> dict[str, object]:
        return {
            "algorithmVersion": RANGE_GROUPING_ALGORITHM_VERSION,
            "currentGroup": None if self._current is None else self._current.as_checkpoint(),
            "maximumConsecutiveUnprovenSources": self._maximum_gap,
            "nextGroupOrder": self._next_group_order,
            "nextSourceIndex": self._next_source_index,
            "pendingGroup": None if self._pending is None else self._pending.as_checkpoint(),
            "schemaVersion": RANGE_GROUPING_CHECKPOINT_SCHEMA_VERSION,
        }

    def _consume_unproven(self, source_index: int) -> tuple[RangeGroup, ...]:
        active = self._pending or self._current
        if active is None:
            return ()
        active.append_unproven(source_index)
        if active.unproven_after_last_exact <= self._maximum_gap:
            return ()
        last_in_group = source_index - 1
        finalized: list[RangeGroup] = []
        if self._pending is not None:
            if self._current is not None:
                finalized.append(
                    self._finalize(
                        self._current,
                        last_source_index=self._pending.first_source_index - 1,
                    )
                )
            finalized.append(self._finalize(self._pending, last_source_index=last_in_group))
        elif self._current is not None:
            finalized.append(self._finalize(self._current, last_source_index=last_in_group))
        self._current = None
        self._pending = None
        return tuple(finalized)

    def _consume_exact(self, evidence: RangeEvidenceResult) -> tuple[RangeGroup, ...]:
        if self._current is None:
            self._current = _OpenGroup.exact(evidence)
            return ()
        source_index = evidence.source.source_index
        if self._same_range(self._current, evidence):
            if self._pending is not None:
                self._current.isolated_source_indexes.extend(
                    range(
                        self._pending.first_source_index,
                        self._pending.last_source_index + 1,
                    )
                )
                _append_unique(
                    self._current.reason_codes,
                    "ISOLATED_RANGE_OBSERVATION_IGNORED",
                )
                self._pending = None
            self._current.append_exact(source_index)
            return ()

        if self._pending is None:
            self._pending = _OpenGroup.exact(evidence)
            return ()

        if self._same_range(self._pending, evidence):
            previous = self._finalize(
                self._current,
                last_source_index=self._pending.first_source_index - 1,
            )
            self._pending.append_exact(source_index)
            self._current = self._pending
            self._pending = None
            return (previous,)

        previous = self._finalize(
            self._current,
            last_source_index=self._pending.first_source_index - 1,
        )
        singleton = self._finalize(self._pending, last_source_index=source_index - 1)
        self._current = _OpenGroup.exact(evidence)
        self._pending = None
        return (previous, singleton)

    def _finalize(
        self,
        value: _OpenGroup,
        *,
        last_source_index: int | None = None,
    ) -> RangeGroup:
        end = value.last_source_index if last_source_index is None else last_source_index
        if end < value.first_source_index:
            end = value.first_source_index
        group = RangeGroup(
            group_order=self._next_group_order,
            expected_index=value.expected_index,
            sequence_range=value.sequence_range,
            first_source_index=value.first_source_index,
            last_source_index=end,
            exact_observation_count=value.exact_observation_count,
            isolated_source_indexes=tuple(value.isolated_source_indexes),
            reason_codes=tuple(value.reason_codes),
        )
        self._next_group_order += 1
        return group

    @staticmethod
    def _same_range(value: _OpenGroup, evidence: RangeEvidenceResult) -> bool:
        return (
            evidence.expected_index == value.expected_index
            and evidence.observed_range == value.sequence_range
        )

    def _restore(self, checkpoint: dict[str, object]) -> None:
        try:
            if (
                checkpoint.get("schemaVersion") != RANGE_GROUPING_CHECKPOINT_SCHEMA_VERSION
                or checkpoint.get("algorithmVersion") != RANGE_GROUPING_ALGORITHM_VERSION
                or _as_int(checkpoint["maximumConsecutiveUnprovenSources"]) != self._maximum_gap
            ):
                raise ValueError("contract mismatch")
            self._next_source_index = _as_int(checkpoint["nextSourceIndex"])
            self._next_group_order = _as_int(checkpoint["nextGroupOrder"])
            self._current = _OpenGroup.from_checkpoint(checkpoint.get("currentGroup"))
            self._pending = _OpenGroup.from_checkpoint(checkpoint.get("pendingGroup"))
        except (KeyError, TypeError, ValueError) as error:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "The range-grouping checkpoint does not match the active policy.",
            ) from error
        if self._next_source_index < 0 or self._next_group_order < 0:
            _fail(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "The range-grouping checkpoint has negative progress.",
            )


def select_middle_exact_observation(
    group: RangeGroup,
    evidence: Iterable[RangeEvidenceResult],
) -> RangeGroupSelection:
    """Select the exact proof nearest to midpoint with stable tie-breaks."""

    selected: RangeEvidenceResult | None = None
    selected_key: tuple[object, ...] | None = None
    for item in evidence:
        if not (
            item.is_exact_range
            and item.expected_index == group.expected_index
            and item.observed_range == group.sequence_range
            and group.first_source_index <= item.source.source_index <= group.last_source_index
        ):
            continue
        key: tuple[object, ...] = (
            abs(item.source.source_index - group.midpoint),
            -(item.confidence if item.confidence is not None else -1.0),
            item.source.source_index,
            _natural_path_key(item.source.relative_path),
            item.source.relative_path,
        )
        if selected_key is None or key < selected_key:
            selected = item
            selected_key = key
    if selected is None:
        _fail(
            "SEMI_AUTOMATIC_SELECTION_RANGE_PROOF_INSUFFICIENT",
            "The finalized group has no exact local range proof.",
        )
    return RangeGroupSelection(group=group, evidence=selected)


def _natural_path_key(value: str) -> tuple[tuple[int, int | str], ...]:
    return tuple(
        (1, int(part)) if part.isdigit() else (0, part.casefold())
        for part in _NATURAL_PART.split(value)
    )


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _canonical_sha256(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise TypeError("value is not an integer")
    return int(value)


def _fail(code: str, message: str) -> NoReturn:
    raise SemiAutomaticSelectionError(code, message)


__all__ = [
    "MIDDLE_EXACT_SELECTOR_VERSION",
    "RANGE_GROUPING_ALGORITHM_VERSION",
    "RANGE_GROUPING_CALIBRATION_MANIFEST_SHA256",
    "RANGE_GROUPING_CHECKPOINT_SCHEMA_VERSION",
    "RANGE_GROUPING_MAXIMUM_UNPROVEN_SOURCES",
    "RangeGroup",
    "RangeGroupSelection",
    "RangeGroupingAccumulator",
    "grouping_policy_fingerprint",
    "select_middle_exact_observation",
]
