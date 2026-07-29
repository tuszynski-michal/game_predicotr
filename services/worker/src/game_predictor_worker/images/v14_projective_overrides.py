"""Accepted exact-observation source quads for v14 full-preflight fallbacks."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .geometry import Point, Quad
from .v14_projective_fallback_review import (
    CANDIDATE_VERSION,
    REPORT_VERSION,
    REVIEW_VERSION,
)

OVERRIDE_SET_VERSION = "reviewed-v14-projective-overrides-v1"


class V14ProjectiveOverrideError(ValueError):
    """Stable failure for reviewed v14 override contracts."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise V14ProjectiveOverrideError(
            "V14_PROJECTIVE_OVERRIDE_CONTRACT_INVALID",
            f"{label} must be an object.",
        )
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise V14ProjectiveOverrideError(
            "V14_PROJECTIVE_OVERRIDE_CONTRACT_INVALID",
            f"{label} must be an array.",
        )
    return cast(Sequence[object], value)


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise V14ProjectiveOverrideError(
            "V14_PROJECTIVE_OVERRIDE_CONTRACT_INVALID",
            f"{label} must be a non-negative integer.",
        )
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise V14ProjectiveOverrideError(
            "V14_PROJECTIVE_OVERRIDE_CONTRACT_INVALID",
            f"{label} must be non-empty text.",
        )
    return value


def _sha256(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise V14ProjectiveOverrideError(
            "V14_PROJECTIVE_OVERRIDE_CONTRACT_INVALID",
            f"{label} must be a lowercase SHA-256.",
        )
    return text


def _quad(value: object, label: str) -> Quad:
    raw_points = _sequence(value, label)
    if len(raw_points) != 4:
        raise V14ProjectiveOverrideError(
            "V14_PROJECTIVE_OVERRIDE_CONTRACT_INVALID",
            f"{label} must contain four points.",
        )
    points: list[Point] = []
    for index, raw in enumerate(raw_points):
        point = _mapping(raw, f"{label}[{index}]")
        x = point.get("x")
        y = point.get("y")
        if (
            not isinstance(x, int | float)
            or isinstance(x, bool)
            or not isinstance(y, int | float)
            or isinstance(y, bool)
        ):
            raise V14ProjectiveOverrideError(
                "V14_PROJECTIVE_OVERRIDE_CONTRACT_INVALID",
                f"{label}[{index}] coordinates must be numbers.",
            )
        points.append(Point(round(x), round(y)))
    return cast(Quad, tuple(points))


def _load_json(path: Path, label: str) -> tuple[bytes, Mapping[str, object]]:
    try:
        content = path.read_bytes()
        value: Any = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise V14ProjectiveOverrideError(
            "V14_PROJECTIVE_OVERRIDE_SOURCE_INVALID",
            f"{label} cannot be read.",
        ) from error
    return content, _mapping(value, label)


@dataclass(frozen=True, slots=True)
class ReviewedV14ProjectiveOverride:
    source_checksum_sha256: str
    board_position: int
    sequence_number: int
    observation_id: str
    source_quad: Quad
    fallback_reason: str


class ReviewedV14ProjectiveOverrides:
    """Expose all and only accepted v14 full-preflight fallback overrides."""

    def __init__(
        self,
        *,
        review_sha256: str,
        source_report_sha256: str,
        overrides: Mapping[tuple[str, int], ReviewedV14ProjectiveOverride],
    ) -> None:
        self.version = OVERRIDE_SET_VERSION
        self.review_sha256 = review_sha256
        self.source_report_sha256 = source_report_sha256
        self._overrides = dict(overrides)

    @classmethod
    def from_files(
        cls,
        review_path: Path,
        preflight_report_path: Path,
    ) -> ReviewedV14ProjectiveOverrides:
        review_bytes, review = _load_json(review_path.resolve(strict=True), "fallbackReview")
        report_bytes, report = _load_json(
            preflight_report_path.resolve(strict=True),
            "preflightReport",
        )
        report_sha256 = hashlib.sha256(report_bytes).hexdigest()
        if (
            review.get("goldenVersion") != REVIEW_VERSION
            or review.get("status") != "accepted"
            or review.get("preflightReportSha256") != report_sha256
            or report.get("schemaVersion") != REPORT_VERSION
            or report.get("phase") != "full"
            or report.get("candidate") != CANDIDATE_VERSION
            or report.get("trainingAllowed") is not False
        ):
            raise V14ProjectiveOverrideError(
                "V14_PROJECTIVE_OVERRIDE_SOURCE_DRIFT",
                "Review and v14 report do not form an accepted source chain.",
            )
        fallback_by_key: dict[tuple[str, int], Mapping[str, object]] = {}
        for index, raw in enumerate(_sequence(report.get("entries"), "preflightReport.entries")):
            entry = _mapping(raw, f"preflightReport.entries[{index}]")
            if entry.get("status") != "fallback":
                continue
            key = (
                _sha256(
                    entry.get("sourceChecksumSha256"),
                    f"preflightReport.entries[{index}].sourceChecksumSha256",
                ),
                _integer(
                    entry.get("positionIndex"),
                    f"preflightReport.entries[{index}].positionIndex",
                ),
            )
            if key in fallback_by_key:
                raise V14ProjectiveOverrideError(
                    "V14_PROJECTIVE_OVERRIDE_SELECTION_DRIFT",
                    "The v14 report duplicates a fallback board.",
                )
            fallback_by_key[key] = entry
        overrides: dict[tuple[str, int], ReviewedV14ProjectiveOverride] = {}
        for index, raw in enumerate(_sequence(review.get("entries"), "fallbackReview.entries")):
            entry = _mapping(raw, f"fallbackReview.entries[{index}]")
            if (
                entry.get("reviewStatus") != "accepted"
                or not entry.get("reviewedBy")
                or entry.get("v1ImpactReviewed") is not True
            ):
                raise V14ProjectiveOverrideError(
                    "V14_PROJECTIVE_OVERRIDE_REVIEW_INCOMPLETE",
                    "Every fallback board and its 15 cells must be explicitly accepted.",
                )
            source = _sha256(
                entry.get("sourceImageChecksumSha256"),
                f"fallbackReview.entries[{index}].sourceImageChecksumSha256",
            )
            position = _integer(
                entry.get("boardPosition"),
                f"fallbackReview.entries[{index}].boardPosition",
            )
            key = (source, position)
            fallback = fallback_by_key.get(key)
            if fallback is None or key in overrides:
                raise V14ProjectiveOverrideError(
                    "V14_PROJECTIVE_OVERRIDE_SELECTION_DRIFT",
                    "Accepted override does not match exactly one v14 fallback.",
                )
            sequence_number = _integer(
                entry.get("sequenceNumber"),
                f"fallbackReview.entries[{index}].sequenceNumber",
            )
            if sequence_number != _integer(
                fallback.get("sequenceNumber"),
                "fallback.sequenceNumber",
            ):
                raise V14ProjectiveOverrideError(
                    "V14_PROJECTIVE_OVERRIDE_SEQUENCE_DRIFT",
                    "Accepted override changed the domain sequence number.",
                )
            overrides[key] = ReviewedV14ProjectiveOverride(
                source_checksum_sha256=source,
                board_position=position,
                sequence_number=sequence_number,
                observation_id=_sha256(
                    entry.get("observationId"),
                    f"fallbackReview.entries[{index}].observationId",
                ),
                source_quad=_quad(
                    entry.get("sourceQuad"),
                    f"fallbackReview.entries[{index}].sourceQuad",
                ),
                fallback_reason=_text(
                    fallback.get("fallbackReason"),
                    "fallback.fallbackReason",
                ),
            )
        if set(overrides) != set(fallback_by_key) or len(overrides) != 14:
            raise V14ProjectiveOverrideError(
                "V14_PROJECTIVE_OVERRIDE_REVIEW_INCOMPLETE",
                "Accepted overrides must cover all 14 v14 fallbacks exactly once.",
            )
        return cls(
            review_sha256=hashlib.sha256(review_bytes).hexdigest(),
            source_report_sha256=report_sha256,
            overrides=overrides,
        )

    @property
    def override_count(self) -> int:
        return len(self._overrides)

    @property
    def overrides(self) -> tuple[ReviewedV14ProjectiveOverride, ...]:
        return tuple(
            sorted(
                self._overrides.values(),
                key=lambda item: (
                    item.sequence_number,
                    item.board_position,
                    item.observation_id,
                ),
            )
        )

    def get(
        self,
        source_checksum_sha256: str,
        board_position: int,
    ) -> ReviewedV14ProjectiveOverride | None:
        return self._overrides.get((source_checksum_sha256, board_position))


__all__ = [
    "OVERRIDE_SET_VERSION",
    "ReviewedV14ProjectiveOverride",
    "ReviewedV14ProjectiveOverrides",
    "V14ProjectiveOverrideError",
]
