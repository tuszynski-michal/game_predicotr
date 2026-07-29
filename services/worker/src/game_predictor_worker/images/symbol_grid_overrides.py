"""Accepted exact-observation geometry overrides for strict refiner fallbacks."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .geometry import Point, Quad
from .rectification import (
    BoardGeometry,
    PageGeometry,
    SymbolRefinementMetadata,
)
from .symbol_grid_fallback_review import REVIEW_VERSION
from .symbol_grid_refinement import MANUAL_SOURCE_QUAD_SOURCE

OVERRIDE_SET_VERSION = "reviewed-symbol-grid-overrides-v1"
OVERRIDE_PROFILE_VERSION = 1


class SymbolGridOverrideError(ValueError):
    """Stable failure for reviewed fallback override contracts."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SymbolGridOverrideError(
            "SYMBOL_GRID_OVERRIDE_CONTRACT_INVALID",
            f"{label} must be an object.",
        )
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise SymbolGridOverrideError(
            "SYMBOL_GRID_OVERRIDE_CONTRACT_INVALID",
            f"{label} must be an array.",
        )
    return cast(Sequence[object], value)


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SymbolGridOverrideError(
            "SYMBOL_GRID_OVERRIDE_CONTRACT_INVALID",
            f"{label} must be a non-negative integer.",
        )
    return value


def _optional_number(value: object, label: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise SymbolGridOverrideError(
            "SYMBOL_GRID_OVERRIDE_CONTRACT_INVALID",
            f"{label} must be a number or null.",
        )
    return float(value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise SymbolGridOverrideError(
            "SYMBOL_GRID_OVERRIDE_CONTRACT_INVALID",
            f"{label} must be a non-empty string.",
        )
    return value


def _sha256(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise SymbolGridOverrideError(
            "SYMBOL_GRID_OVERRIDE_CONTRACT_INVALID",
            f"{label} must be a lowercase SHA-256.",
        )
    return text


def _quad(value: object, label: str) -> Quad:
    raw_points = _sequence(value, label)
    if len(raw_points) != 4:
        raise SymbolGridOverrideError(
            "SYMBOL_GRID_OVERRIDE_CONTRACT_INVALID",
            f"{label} must contain four points.",
        )
    points: list[Point] = []
    for index, raw in enumerate(raw_points):
        point = _mapping(raw, f"{label}[{index}]")
        x = _optional_number(point.get("x"), f"{label}[{index}].x")
        y = _optional_number(point.get("y"), f"{label}[{index}].y")
        if x is None or y is None:
            raise SymbolGridOverrideError(
                "SYMBOL_GRID_OVERRIDE_CONTRACT_INVALID",
                f"{label}[{index}] coordinates cannot be null.",
            )
        points.append(Point(round(x), round(y)))
    return cast(Quad, tuple(points))


def _load_json(path: Path, label: str) -> tuple[bytes, Mapping[str, object]]:
    try:
        content = path.read_bytes()
        value: Any = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise SymbolGridOverrideError(
            "SYMBOL_GRID_OVERRIDE_SOURCE_INVALID",
            f"{label} cannot be read.",
        ) from error
    return content, _mapping(value, label)


@dataclass(frozen=True, slots=True)
class ReviewedOverride:
    source_checksum_sha256: str
    board_position: int
    sequence_number: int
    observation_id: str
    source_quad: Quad
    metadata: SymbolRefinementMetadata


class ReviewedSymbolGridOverrides:
    """Apply six accepted quads and leave every other detector board untouched."""

    def __init__(
        self,
        *,
        profile_set_sha256: str,
        corpus_manifest_sha256: str,
        detection_report_sha256: str,
        overrides: Mapping[tuple[str, int], ReviewedOverride],
    ) -> None:
        self.profile_set_version = OVERRIDE_SET_VERSION
        self.profile_set_sha256 = profile_set_sha256
        self.corpus_manifest_sha256 = corpus_manifest_sha256
        self.detection_report_sha256 = detection_report_sha256
        self._overrides = dict(overrides)

    @classmethod
    def from_files(
        cls,
        review_path: Path,
        refinement_report_path: Path,
    ) -> ReviewedSymbolGridOverrides:
        review_bytes, review = _load_json(review_path.resolve(strict=True), "fallbackReview")
        report_bytes, report = _load_json(
            refinement_report_path.resolve(strict=True),
            "refinementReport",
        )
        report_sha = hashlib.sha256(report_bytes).hexdigest()
        if (
            review.get("goldenVersion") != REVIEW_VERSION
            or review.get("status") != "accepted"
            or review.get("refinementReportSha256") != report_sha
            or report.get("geometrySource") != "detector"
            or report.get("trainingAllowed") is not False
        ):
            raise SymbolGridOverrideError(
                "SYMBOL_GRID_OVERRIDE_SOURCE_DRIFT",
                "Review and strict refinement report do not form an accepted source chain.",
            )
        fallback_by_key: dict[tuple[str, int], Mapping[str, object]] = {}
        for index, raw in enumerate(_sequence(report.get("entries"), "refinementReport.entries")):
            entry = _mapping(raw, f"refinementReport.entries[{index}]")
            if entry.get("status") != "fallback":
                continue
            key = (
                _sha256(
                    entry.get("sourceImageChecksumSha256"),
                    f"refinementReport.entries[{index}].sourceImageChecksumSha256",
                ),
                _integer(
                    entry.get("boardPosition"),
                    f"refinementReport.entries[{index}].boardPosition",
                ),
            )
            fallback_by_key[key] = entry
        overrides: dict[tuple[str, int], ReviewedOverride] = {}
        for index, raw in enumerate(_sequence(review.get("entries"), "fallbackReview.entries")):
            entry = _mapping(raw, f"fallbackReview.entries[{index}]")
            if entry.get("reviewStatus") != "accepted" or not entry.get("reviewedBy"):
                raise SymbolGridOverrideError(
                    "SYMBOL_GRID_OVERRIDE_REVIEW_INCOMPLETE",
                    "Every fallback board must be explicitly accepted.",
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
                raise SymbolGridOverrideError(
                    "SYMBOL_GRID_OVERRIDE_SELECTION_DRIFT",
                    "Accepted override does not match exactly one strict fallback.",
                )
            overrides[key] = ReviewedOverride(
                source_checksum_sha256=source,
                board_position=position,
                sequence_number=_integer(
                    entry.get("sequenceNumber"),
                    f"fallbackReview.entries[{index}].sequenceNumber",
                ),
                observation_id=_sha256(
                    entry.get("observationId"),
                    f"fallbackReview.entries[{index}].observationId",
                ),
                source_quad=_quad(
                    entry.get("sourceQuad"),
                    f"fallbackReview.entries[{index}].sourceQuad",
                ),
                metadata=SymbolRefinementMetadata(
                    refiner_version=_text(
                        fallback.get("refinerVersion"),
                        "fallback.refinerVersion",
                    ),
                    reliable_center_count=_integer(
                        fallback.get("reliableCenterCount"),
                        "fallback.reliableCenterCount",
                    ),
                    inlier_count=_integer(
                        fallback.get("inlierCount"),
                        "fallback.inlierCount",
                    ),
                    baseline_median_residual_px=_optional_number(
                        fallback.get("baselineMedianResidualPx"),
                        "fallback.baselineMedianResidualPx",
                    ),
                    refined_median_residual_px=_optional_number(
                        fallback.get("refinedMedianResidualPx"),
                        "fallback.refinedMedianResidualPx",
                    ),
                    refined_p95_residual_px=_optional_number(
                        fallback.get("refinedP95ResidualPx"),
                        "fallback.refinedP95ResidualPx",
                    ),
                    status="manual_override",
                    fallback_reason=_text(
                        fallback.get("fallbackReason"),
                        "fallback.fallbackReason",
                    ),
                ),
            )
        if set(overrides) != set(fallback_by_key):
            raise SymbolGridOverrideError(
                "SYMBOL_GRID_OVERRIDE_REVIEW_INCOMPLETE",
                "Accepted overrides must cover every strict fallback exactly once.",
            )
        return cls(
            profile_set_sha256=hashlib.sha256(review_bytes).hexdigest(),
            corpus_manifest_sha256=_sha256(
                review.get("corpusManifestSha256"),
                "fallbackReview.corpusManifestSha256",
            ),
            detection_report_sha256=_sha256(
                report.get("detectionReportSha256"),
                "refinementReport.detectionReportSha256",
            ),
            overrides=overrides,
        )

    @property
    def override_count(self) -> int:
        return len(self._overrides)

    def calibrate(
        self,
        source_checksum_sha256: str,
        geometry: PageGeometry,
    ) -> PageGeometry:
        if geometry.status != "detected":
            return geometry
        boards: list[BoardGeometry] = []
        for board in geometry.boards:
            override = self._overrides.get((source_checksum_sha256, board.position_index))
            if override is None:
                boards.append(board)
                continue
            boards.append(
                BoardGeometry(
                    position_index=board.position_index,
                    quad=override.source_quad,
                    bounding_box=board.bounding_box,
                    source_quad_source=MANUAL_SOURCE_QUAD_SOURCE,
                    calibration_profile_id=override.observation_id,
                    calibration_profile_version=OVERRIDE_PROFILE_VERSION,
                    calibration_anchor_sequence_numbers=(override.sequence_number,),
                    calibration_interpolation_weight=0.0,
                    symbol_refinement=override.metadata,
                )
            )
        return PageGeometry(
            status="detected",
            image_width=geometry.image_width,
            image_height=geometry.image_height,
            boards=tuple(boards),
            review_reasons=geometry.review_reasons,
        )


__all__ = [
    "OVERRIDE_PROFILE_VERSION",
    "OVERRIDE_SET_VERSION",
    "ReviewedOverride",
    "ReviewedSymbolGridOverrides",
    "SymbolGridOverrideError",
]
