"""Deterministic model learned only from explicit manual partial-grid opt-ins."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

PARTIAL_GRID_PROFILE_SCHEMA_VERSION = "partial-grid-training-profile-v1"
PARTIAL_GRID_PROFILE_POLICY_VERSION = "lateral-missing-column-majority-v1"
PARTIAL_GRID_MINIMUM_SOURCE_COUNT = 3
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PartialGridLearningError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PartialGridPattern:
    unavailable_cell_indices: tuple[int, ...]
    sample_count: int
    source_count: int

    def __post_init__(self) -> None:
        if (
            type(self.sample_count) is not int
            or type(self.source_count) is not int
            or self.sample_count < self.source_count
            or self.source_count < 1
            or not _is_lateral_mask(self.unavailable_cell_indices)
        ):
            raise PartialGridLearningError("A partial-grid training pattern is invalid.")

    @property
    def ready(self) -> bool:
        return self.source_count >= PARTIAL_GRID_MINIMUM_SOURCE_COUNT

    def to_payload(self) -> dict[str, object]:
        return {
            "unavailableCellIndices": list(self.unavailable_cell_indices),
            "sampleCount": self.sample_count,
            "sourceCount": self.source_count,
            "ready": self.ready,
        }


@dataclass(frozen=True, slots=True)
class PartialGridTrainingProfile:
    patterns: tuple[PartialGridPattern, ...]
    distinct_source_count: int

    def __post_init__(self) -> None:
        masks = tuple(pattern.unavailable_cell_indices for pattern in self.patterns)
        if (
            masks != tuple(sorted(set(masks)))
            or any(not _is_lateral_mask(mask) for mask in masks)
            or any(
                pattern.sample_count < pattern.source_count or pattern.source_count < 1
                for pattern in self.patterns
            )
            or type(self.distinct_source_count) is not int
            or not max(pattern.source_count for pattern in self.patterns)
            <= self.distinct_source_count
            <= sum(pattern.source_count for pattern in self.patterns)
        ):
            raise PartialGridLearningError("The partial-grid training profile is invalid.")

    @property
    def sample_count(self) -> int:
        return sum(pattern.sample_count for pattern in self.patterns)

    @property
    def source_count(self) -> int:
        return self.distinct_source_count

    @property
    def ready_pattern_count(self) -> int:
        return sum(pattern.ready for pattern in self.patterns)

    def to_payload(self, *, include_checksum: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schemaVersion": PARTIAL_GRID_PROFILE_SCHEMA_VERSION,
            "policyVersion": PARTIAL_GRID_PROFILE_POLICY_VERSION,
            "minimumDistinctSourceCount": PARTIAL_GRID_MINIMUM_SOURCE_COUNT,
            "sampleCount": self.sample_count,
            "sourceCount": self.source_count,
            "readyPatternCount": self.ready_pattern_count,
            "patterns": [pattern.to_payload() for pattern in self.patterns],
        }
        if include_checksum:
            payload["checksumSha256"] = self.checksum_sha256
        return payload

    @property
    def checksum_sha256(self) -> str:
        return hashlib.sha256(_canonical(self.to_payload(include_checksum=False))).hexdigest()

    def select_mask(self, candidates: Sequence[tuple[int, ...]]) -> tuple[int, ...] | None:
        scores = {
            pattern.unavailable_cell_indices: pattern.source_count
            for pattern in self.patterns
            if pattern.ready and pattern.unavailable_cell_indices in candidates
        }
        if not scores:
            return None
        best = max(scores.values())
        winners = [mask for mask, score in scores.items() if score == best]
        return winners[0] if len(winners) == 1 else None

    @classmethod
    def from_payload(cls, value: object) -> PartialGridTrainingProfile:
        if not isinstance(value, Mapping):
            raise PartialGridLearningError("The partial-grid training profile is missing.")
        raw_patterns = value.get("patterns")
        if not isinstance(raw_patterns, Sequence) or isinstance(raw_patterns, str | bytes):
            raise PartialGridLearningError("The partial-grid pattern list is invalid.")
        patterns: list[PartialGridPattern] = []
        for raw in raw_patterns:
            if not isinstance(raw, Mapping):
                raise PartialGridLearningError("A partial-grid pattern is invalid.")
            indices = raw.get("unavailableCellIndices")
            if not isinstance(indices, Sequence) or isinstance(indices, str | bytes):
                raise PartialGridLearningError("A partial-grid mask is invalid.")
            sample_count = raw.get("sampleCount")
            source_count = raw.get("sourceCount")
            if type(sample_count) is not int or type(source_count) is not int:
                raise PartialGridLearningError("A partial-grid pattern count is invalid.")
            patterns.append(
                PartialGridPattern(
                    tuple(indices),
                    sample_count,
                    source_count,
                )
            )
        distinct_source_count = value.get("sourceCount")
        if type(distinct_source_count) is not int:
            raise PartialGridLearningError("The partial-grid source count is invalid.")
        profile = cls(tuple(patterns), distinct_source_count)
        expected = profile.to_payload()
        if set(value) != set(expected) or any(
            type(value[key]) is not type(expected_item) or value[key] != expected_item
            for key, expected_item in expected.items()
        ):
            raise PartialGridLearningError("The partial-grid training profile drifted.")
        return profile


def build_partial_grid_training_profile(
    overrides: Mapping[str, object],
) -> PartialGridTrainingProfile | None:
    """Build from current override snapshot; one source counts once per mask."""

    samples: dict[tuple[int, ...], int] = defaultdict(int)
    sources: dict[tuple[int, ...], set[str]] = defaultdict(set)
    all_sources: set[str] = set()
    for source_checksum, raw_entry in overrides.items():
        if not _SHA256.fullmatch(source_checksum) or not isinstance(raw_entry, Mapping):
            continue
        qualifications = raw_entry.get("slotQualifications")
        if not isinstance(qualifications, Sequence) or isinstance(qualifications, str | bytes):
            continue
        for raw in qualifications:
            if not isinstance(raw, Mapping) or raw.get("version") not in (
                "manual-geometry-qualification-v2",
                "manual-geometry-qualification-v3",
            ):
                continue
            if raw.get("includeInPartialGridTraining") is not True:
                continue
            indices = raw.get("unavailableCellIndices")
            if not isinstance(indices, Sequence) or isinstance(indices, str | bytes):
                continue
            mask = tuple(indices)
            if not _is_lateral_mask(mask):
                continue
            samples[mask] += 1
            sources[mask].add(source_checksum)
            all_sources.add(source_checksum)
    if not samples:
        return None
    return PartialGridTrainingProfile(
        tuple(
            PartialGridPattern(mask, samples[mask], len(sources[mask])) for mask in sorted(samples)
        ),
        len(all_sources),
    )


def _is_lateral_mask(indices: tuple[int, ...]) -> bool:
    if any(type(index) is not int or not 0 <= index < 15 for index in indices):
        return False
    if indices != tuple(sorted(set(indices))):
        return False
    columns = {
        column for column in range(5) if all(row * 5 + column in indices for row in range(3))
    }
    expected = tuple(sorted(row * 5 + column for row in range(3) for column in columns))
    return indices == expected and columns in ({0}, {4}, {0, 1}, {3, 4})


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "ascii"
    )


__all__ = [
    "PARTIAL_GRID_MINIMUM_SOURCE_COUNT",
    "PartialGridLearningError",
    "PartialGridPattern",
    "PartialGridTrainingProfile",
    "build_partial_grid_training_profile",
]
