"""Read-only, bounded feasibility diagnostics for Structured OpenCV geometry.

The spike consumes immutable JPEGs and human annotations, writes only to an
explicit diagnostics directory, and deliberately has no storage/API imports.
Its provisional correctness threshold is a measurement aid, not a production
acceptance policy.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, Literal, cast
from uuid import UUID

import cv2
import numpy as np
from game_predictor_api.domain.board_topology import LEGACY_IMAGE_BOARD_TOPOLOGY
from game_predictor_api.domain.image_geometry_v2 import (
    AttestedSequenceRange,
    SourcePoint,
    SourceQuad,
    canonical_json_bytes,
)
from numpy.typing import NDArray

from ..image_file import sha256_file
from ..normalization import CanonicalSourceLoader
from .geometry_engine import SourceGeometryResult, StructuredOpenCvGeometryEngine
from .global_initialization import StructuredGeometryInitializationRequest
from .line_refinement import BoardLineRefiner

SPIKE_SCHEMA_VERSION: Final = "structured-geometry-feasibility-report-v1"
SPIKE_INPUT_VERSION: Final = "structured-geometry-feasibility-input-v1"
SPIKE_CONFIG_VERSION: Final = "structured-geometry-feasibility-config-v1"
_TOPOLOGY_RULES_VERSION_ID = UUID("00000000-0000-0000-0000-000000000323")
_MIN_IMAGES = 30
_MAX_IMAGES = 50
_MIN_GAMES = 2
_MIN_FALSE_SUCCESSES = 3
_MAX_CORNER_ERROR_DIAGONAL_FRACTION = 0.025
_REQUIRED_CONDITIONS = frozenset({"angle", "brightness", "blur", "glare", "occlusion"})


class GeometryFeasibilitySpikeError(ValueError):
    """Stable invalid-input or artifact error for the read-only spike."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class FeasibilityBoardAnnotation:
    position_index: int
    sequence_number: int
    reference_quad: SourceQuad
    legacy_detected_quad: SourceQuad | None


@dataclass(frozen=True, slots=True)
class FeasibilityImage:
    image_id: str
    game_id: str
    source_path: Path
    source_relative_path: str
    source_checksum_sha256: str
    split: str
    condition_tags: tuple[str, ...]
    normalized_conditions: tuple[str, ...]
    historical_false_success: bool
    boards: tuple[FeasibilityBoardAnnotation, ...]

    @property
    def page_kind(self) -> Literal["full", "partial"]:
        return "full" if len(self.boards) == 9 else "partial"


@dataclass(frozen=True, slots=True)
class FeasibilityCorpus:
    corpus_id: str
    images: tuple[FeasibilityImage, ...]
    anchor_image_ids: tuple[tuple[str, str], ...]
    input_checksum_sha256: str


@dataclass(frozen=True, slots=True)
class CorpusReadiness:
    ready: bool
    image_count: int
    game_count: int
    full_page_count: int
    partial_page_count: int
    historical_false_success_count: int
    observed_conditions: tuple[str, ...]
    missing_requirements: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "fullPageCount": self.full_page_count,
            "gameCount": self.game_count,
            "historicalFalseSuccessCount": self.historical_false_success_count,
            "imageCount": self.image_count,
            "missingRequirements": list(self.missing_requirements),
            "observedConditions": list(self.observed_conditions),
            "partialPageCount": self.partial_page_count,
            "ready": self.ready,
        }


@dataclass(frozen=True, slots=True)
class CandidateAccuracy:
    available: bool
    maximum_corner_error_px: float | None
    maximum_corner_error_diagonal_fraction: float | None
    intersection_over_union: float | None
    provisionally_correct: bool | None

    def to_payload(self) -> dict[str, object]:
        return {
            "available": self.available,
            "intersectionOverUnion": _rounded(self.intersection_over_union),
            "maximumCornerErrorDiagonalFraction": _rounded(
                self.maximum_corner_error_diagonal_fraction
            ),
            "maximumCornerErrorPx": _rounded(self.maximum_corner_error_px),
            "provisionallyCorrect": self.provisionally_correct,
        }


@dataclass(frozen=True, slots=True)
class SupplementalSignalProbe:
    outer_border_score: float
    hough_vertical_count: int
    hough_horizontal_count: int
    hough_coverage_score: float
    vertical_gradient_profile_score: float
    horizontal_gradient_profile_score: float
    grid_periodicity_score: float
    symbol_center_support_score: float
    probe_coordinate_source: str = "human_reference_quad"

    def to_payload(self) -> dict[str, object]:
        return {
            "gridPeriodicityScore": round(self.grid_periodicity_score, 8),
            "horizontalGradientProfileScore": round(self.horizontal_gradient_profile_score, 8),
            "houghCoverageScore": round(self.hough_coverage_score, 8),
            "houghHorizontalCount": self.hough_horizontal_count,
            "houghVerticalCount": self.hough_vertical_count,
            "outerBorderScore": round(self.outer_border_score, 8),
            "probeCoordinateSource": self.probe_coordinate_source,
            "symbolCenterSupportScore": round(self.symbol_center_support_score, 8),
            "verticalGradientProfileScore": round(self.vertical_gradient_profile_score, 8),
        }


def config_payload() -> dict[str, object]:
    """Return the pinned experimental configuration included in every report."""

    return {
        "configVersion": SPIKE_CONFIG_VERSION,
        "corpusBounds": {"maximumImages": _MAX_IMAGES, "minimumImages": _MIN_IMAGES},
        "provisionalMaximumCornerErrorDiagonalFraction": (_MAX_CORNER_ERROR_DIAGONAL_FRACTION),
        "requiredConditionClasses": sorted(_REQUIRED_CONDITIONS),
        "requiredFalseSuccessCount": _MIN_FALSE_SUCCESSES,
        "requiredGameCount": _MIN_GAMES,
        "thresholdStatus": "experimental_measurement_only",
    }


def config_checksum_sha256() -> str:
    return hashlib.sha256(canonical_json_bytes(config_payload())).hexdigest()


def load_feasibility_corpus(manifest_path: Path) -> FeasibilityCorpus:
    """Load one or more immutable annotated corpora without touching a database."""

    raw = _read_json(manifest_path, "spike input")
    if raw.get("schemaVersion") != SPIKE_INPUT_VERSION:
        raise GeometryFeasibilitySpikeError(
            "GEOMETRY_FEASIBILITY_INPUT_VERSION_UNSUPPORTED",
            "The geometry feasibility input schema is unsupported.",
        )
    sources = _sequence(raw.get("sources"), "sources")
    images: list[FeasibilityImage] = []
    anchor_image_ids: list[tuple[str, str]] = []
    seen_ids: set[str] = set()
    for source_index, source_value in enumerate(sources):
        source = _mapping(source_value, f"sources[{source_index}]")
        game_id = _text(source.get("gameId"), f"sources[{source_index}].gameId")
        corpus_path = _safe_input_path(
            manifest_path.parent,
            source.get("corpusManifest"),
            f"sources[{source_index}].corpusManifest",
        )
        annotations_path = _safe_input_path(
            manifest_path.parent,
            source.get("annotations"),
            f"sources[{source_index}].annotations",
        )
        source_root = _declared_input_directory(
            manifest_path.parent,
            source.get("sourceRoot"),
            f"sources[{source_index}].sourceRoot",
        )
        condition_aliases = _condition_aliases(source.get("conditionAliases"))
        false_successes = frozenset(
            _text(value, f"sources[{source_index}].historicalFalseSuccessImageIds")
            for value in _sequence(
                source.get("historicalFalseSuccessImageIds", []),
                f"sources[{source_index}].historicalFalseSuccessImageIds",
            )
        )
        anchor_image_ids.append(
            (
                game_id,
                _text(source.get("anchorImageId"), f"sources[{source_index}].anchorImageId"),
            )
        )
        corpus = _read_json(corpus_path, "source corpus manifest")
        annotations = _read_json(annotations_path, "source golden annotations")
        legacy_by_key = _legacy_geometry_annotations(manifest_path.parent, source)
        annotation_by_id = {
            _text(item.get("imageId"), "annotations.images.imageId"): item
            for value in _sequence(annotations.get("images"), "annotations.images")
            for item in [_mapping(value, "annotations.images[]")]
        }
        for image_value in _sequence(corpus.get("images"), "corpus.images"):
            image = _mapping(image_value, "corpus.images[]")
            image_id = _text(image.get("id"), "corpus.images.id")
            if image_id in seen_ids:
                raise GeometryFeasibilitySpikeError(
                    "GEOMETRY_FEASIBILITY_IMAGE_DUPLICATE",
                    "Every feasibility image ID must be globally unique.",
                )
            seen_ids.add(image_id)
            annotation = annotation_by_id.get(image_id)
            if annotation is None:
                raise GeometryFeasibilitySpikeError(
                    "GEOMETRY_FEASIBILITY_ANNOTATION_MISSING",
                    f"Image {image_id} has no golden annotation.",
                )
            relative = _safe_relative_path(image.get("relativePath"), "corpus.images.relativePath")
            image_path = _resolve_beneath(source_root, relative)
            expected_checksum = _sha256_text(image.get("sha256"), "corpus.images.sha256")
            if sha256_file(image_path) != expected_checksum:
                raise GeometryFeasibilitySpikeError(
                    "GEOMETRY_FEASIBILITY_SOURCE_CHECKSUM_MISMATCH",
                    f"Image {image_id} differs from its immutable manifest.",
                )
            condition_tags = tuple(
                sorted(
                    _text(value, "corpus.images.conditionTags")
                    for value in _sequence(
                        image.get("conditionTags", []), "corpus.images.conditionTags"
                    )
                )
            )
            normalized = tuple(
                sorted(
                    {
                        normalized_tag
                        for tag in condition_tags
                        for normalized_tag in condition_aliases.get(tag, ())
                    }
                )
            )
            boards = _board_annotations(
                annotation,
                source_relative_path=relative.as_posix(),
                legacy_by_key=legacy_by_key,
            )
            if not 1 <= len(boards) <= 9:
                raise GeometryFeasibilitySpikeError(
                    "GEOMETRY_FEASIBILITY_BOARD_COUNT_INVALID",
                    f"Image {image_id} must contain one through nine active boards.",
                )
            images.append(
                FeasibilityImage(
                    image_id=image_id,
                    game_id=game_id,
                    source_path=image_path,
                    source_relative_path=relative.as_posix(),
                    source_checksum_sha256=expected_checksum,
                    split=_text(image.get("split"), "corpus.images.split"),
                    condition_tags=condition_tags,
                    normalized_conditions=normalized,
                    historical_false_success=image_id in false_successes,
                    boards=boards,
                )
            )
    if not _MIN_IMAGES <= len(images) <= _MAX_IMAGES:
        raise GeometryFeasibilitySpikeError(
            "GEOMETRY_FEASIBILITY_CORPUS_SIZE_INVALID",
            f"The spike requires {_MIN_IMAGES} through {_MAX_IMAGES} real images.",
        )
    payload_checksum = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    image_ids = {image.image_id for image in images}
    if any(image_id not in image_ids for _, image_id in anchor_image_ids):
        raise GeometryFeasibilitySpikeError(
            "GEOMETRY_FEASIBILITY_ANCHOR_MISSING",
            "Every game must declare an anchor image from the bounded corpus.",
        )
    return FeasibilityCorpus(
        corpus_id=_text(raw.get("corpusId"), "corpusId"),
        images=tuple(images),
        anchor_image_ids=tuple(anchor_image_ids),
        input_checksum_sha256=payload_checksum,
    )


def assess_corpus_readiness(corpus: FeasibilityCorpus) -> CorpusReadiness:
    conditions = tuple(
        sorted({condition for image in corpus.images for condition in image.normalized_conditions})
    )
    game_count = len({image.game_id for image in corpus.images})
    full = sum(image.page_kind == "full" for image in corpus.images)
    partial = sum(image.page_kind == "partial" for image in corpus.images)
    false_successes = sum(image.historical_false_success for image in corpus.images)
    missing: list[str] = []
    if game_count < _MIN_GAMES:
        missing.append("multiple_games")
    if not full:
        missing.append("full_pages")
    if not partial:
        missing.append("partial_pages")
    if false_successes < _MIN_FALSE_SUCCESSES:
        missing.append("historical_false_successes")
    for condition in sorted(_REQUIRED_CONDITIONS.difference(conditions)):
        missing.append(f"condition:{condition}")
    return CorpusReadiness(
        ready=not missing,
        image_count=len(corpus.images),
        game_count=game_count,
        full_page_count=full,
        partial_page_count=partial,
        historical_false_success_count=false_successes,
        observed_conditions=conditions,
        missing_requirements=tuple(missing),
    )


def probe_reference_board_signals(
    rgb: NDArray[np.uint8],
    reference_quad: SourceQuad,
) -> SupplementalSignalProbe:
    """Measure visibility signals inside a human reference ROI without deciding geometry."""

    patch = _rectify(rgb, reference_quad, width=500, height=300)
    gray = cast(NDArray[np.uint8], cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY))
    hsv = cv2.cvtColor(patch, cv2.COLOR_RGB2HSV)
    low_red = cv2.inRange(hsv, np.array([0, 70, 45]), np.array([12, 255, 255]))
    high_red = cv2.inRange(hsv, np.array([165, 70, 45]), np.array([179, 255, 255]))
    red = cv2.bitwise_or(low_red, high_red)
    border = np.zeros(red.shape, dtype=np.uint8)
    border[:12, :] = 255
    border[-12:, :] = 255
    border[:, :12] = 255
    border[:, -12:] = 255
    border_pixels = int(np.count_nonzero(border))
    outer_border_score = float(
        np.count_nonzero(cv2.bitwise_and(red, border)) / max(1, border_pixels)
    )

    enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(6, 6)).apply(gray)
    edges = cv2.Canny(enhanced, 45, 135)
    hough = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=34,
        minLineLength=42,
        maxLineGap=14,
    )
    vertical_coordinates: list[float] = []
    horizontal_coordinates: list[float] = []
    if hough is not None:
        for x1, y1, x2, y2 in hough[:, 0]:
            dx, dy = float(x2 - x1), float(y2 - y1)
            angle = abs(math.degrees(math.atan2(dy, dx)))
            if 70 <= angle <= 110:
                vertical_coordinates.append((float(x1) + float(x2)) / 2)
            elif angle <= 20 or angle >= 160:
                horizontal_coordinates.append((float(y1) + float(y2)) / 2)
    hough_vertical = _expected_support_count(vertical_coordinates, 500, 5)
    hough_horizontal = _expected_support_count(horizontal_coordinates, 300, 3)
    hough_score = (hough_vertical / 6 + hough_horizontal / 4) / 2

    vertical_gradient = np.mean(np.abs(cv2.Sobel(enhanced, cv2.CV_32F, 1, 0, ksize=3)), axis=0)
    horizontal_gradient = np.mean(np.abs(cv2.Sobel(enhanced, cv2.CV_32F, 0, 1, ksize=3)), axis=1)
    vertical_profile, vertical_peaks = _profile_score(vertical_gradient, 5)
    horizontal_profile, horizontal_peaks = _profile_score(horizontal_gradient, 3)
    periodicity = (
        _spacing_score(vertical_peaks, expected_count=6)
        + _spacing_score(horizontal_peaks, expected_count=4)
    ) / 2
    center_support = _symbol_center_support(gray)
    return SupplementalSignalProbe(
        outer_border_score=_unit(outer_border_score),
        hough_vertical_count=hough_vertical,
        hough_horizontal_count=hough_horizontal,
        hough_coverage_score=_unit(hough_score),
        vertical_gradient_profile_score=vertical_profile,
        horizontal_gradient_profile_score=horizontal_profile,
        grid_periodicity_score=_unit(periodicity),
        symbol_center_support_score=center_support,
    )


def run_feasibility_spike(
    *,
    manifest_path: Path,
    output_root: Path,
) -> dict[str, object]:
    """Run the bounded spike and write only checksum-bound diagnostic artifacts."""

    corpus = load_feasibility_corpus(manifest_path)
    readiness = assess_corpus_readiness(corpus)
    output = output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink():
        raise GeometryFeasibilitySpikeError(
            "GEOMETRY_FEASIBILITY_OUTPUT_PATH_UNSAFE",
            "The diagnostics output root cannot be a symlink.",
        )
    loader = CanonicalSourceLoader()
    images_by_id = {image.image_id: image for image in corpus.images}
    anchor_rgb: dict[str, NDArray[np.uint8]] = {}
    profiles: dict[str, Mapping[str, object]] = {}
    for game_id, anchor_image_id in corpus.anchor_image_ids:
        anchor = images_by_id[anchor_image_id]
        frame = loader.load(
            anchor.source_path,
            expected_source_checksum_sha256=anchor.source_checksum_sha256,
        )
        anchor_rgb[anchor.source_checksum_sha256] = np.array(frame.rgb, copy=True)
        profiles[game_id] = _geometry_profile(
            anchor, width=frame.source.width, height=frame.source.height
        )
        loader.clear()
    generic_engine = StructuredOpenCvGeometryEngine(load_anchor_rgb=_unexpected_anchor_load)
    engine = StructuredOpenCvGeometryEngine(load_anchor_rgb=lambda checksum: anchor_rgb[checksum])
    oracle_refiner = BoardLineRefiner()
    summaries: list[dict[str, object]] = []
    disposition_counts: Counter[str] = Counter()
    candidate_counts: dict[str, Counter[str]] = {
        "legacyCorpusDetector": Counter(),
        "genericGlobalProjection": Counter(),
        "knownLayoutProjection": Counter(),
        "oracleInitializedLocalRefinement": Counter(),
        "structuredHybrid": Counter(),
    }
    reason_counts: Counter[str] = Counter()
    signal_totals: dict[str, float] = {}
    signal_board_count = 0
    for image in corpus.images:
        frame = loader.load(
            image.source_path,
            expected_source_checksum_sha256=image.source_checksum_sha256,
        )
        generic_request = StructuredGeometryInitializationRequest.for_frame(
            frame,
            topology=LEGACY_IMAGE_BOARD_TOPOLOGY,
            topology_rules_version_id=_TOPOLOGY_RULES_VERSION_ID,
            attested_range=AttestedSequenceRange(
                start=image.boards[0].sequence_number,
                end=image.boards[-1].sequence_number,
            ),
            geometry_profile=None,
        )
        generic_initialization = generic_engine.initialize(frame, generic_request)
        request = StructuredGeometryInitializationRequest.for_frame(
            frame,
            topology=LEGACY_IMAGE_BOARD_TOPOLOGY,
            topology_rules_version_id=_TOPOLOGY_RULES_VERSION_ID,
            attested_range=generic_request.attested_range,
            geometry_profile=profiles[image.game_id],
        )
        structured_error: str | None = None
        try:
            result = engine.detect(frame, request)
        except (ValueError, cv2.error) as error:
            result = None
            structured_error = type(error).__name__
            reason_counts[f"structured_engine_exception:{structured_error}"] += len(image.boards)
        boards_payload: list[dict[str, object]] = []
        initial_by_position = {
            slot.slot.position_index: slot.initial_quad
            for slot in (() if result is None else result.global_initialization.slots)
        }
        generic_by_position = {
            slot.slot.position_index: slot.initial_quad for slot in generic_initialization.slots
        }
        structured_by_position = {
            board.slot.position_index: board for board in (() if result is None else result.boards)
        }
        oracle_by_position: dict[int, tuple[str, SourceQuad | None]] = {}
        for annotation in image.boards:
            board_result = structured_by_position.get(annotation.position_index)
            signal = probe_reference_board_signals(frame.rgb, annotation.reference_quad)
            signal_board_count += 1
            for key, value in signal.to_payload().items():
                if isinstance(value, int | float) and not isinstance(value, bool):
                    signal_totals[key] = signal_totals.get(key, 0.0) + float(value)
            legacy_accuracy = _candidate_accuracy(
                annotation.legacy_detected_quad,
                annotation.reference_quad,
                width=frame.source.width,
                height=frame.source.height,
            )
            initial_accuracy = _candidate_accuracy(
                initial_by_position.get(annotation.position_index),
                annotation.reference_quad,
                width=frame.source.width,
                height=frame.source.height,
            )
            generic_accuracy = _candidate_accuracy(
                generic_by_position.get(annotation.position_index),
                annotation.reference_quad,
                width=frame.source.width,
                height=frame.source.height,
            )
            oracle_refinement = oracle_refiner.refine(
                frame.rgb,
                initial_quad=annotation.reference_quad,
                topology=LEGACY_IMAGE_BOARD_TOPOLOGY,
                global_registration_score=1.0,
            )
            oracle_by_position[annotation.position_index] = (
                "oracle_local_refinement",
                oracle_refinement.final_quad,
            )
            oracle_accuracy = _candidate_accuracy(
                oracle_refinement.final_quad,
                annotation.reference_quad,
                width=frame.source.width,
                height=frame.source.height,
            )
            final_accuracy = _candidate_accuracy(
                None if board_result is None else board_result.final_quad,
                annotation.reference_quad,
                width=frame.source.width,
                height=frame.source.height,
            )
            _count_candidate(candidate_counts["legacyCorpusDetector"], legacy_accuracy)
            _count_candidate(candidate_counts["genericGlobalProjection"], generic_accuracy)
            _count_candidate(candidate_counts["knownLayoutProjection"], initial_accuracy)
            _count_candidate(candidate_counts["oracleInitializedLocalRefinement"], oracle_accuracy)
            _count_candidate(candidate_counts["structuredHybrid"], final_accuracy)
            disposition = (
                "needs_manual_correction"
                if board_result is None
                else board_result.disposition.value
            )
            reasons = (
                [f"structured_engine_exception:{structured_error}"]
                if board_result is None
                else [reason.value for reason in board_result.reason_codes]
            )
            disposition_counts[disposition] += 1
            if board_result is not None:
                reason_counts.update(reasons)
            boards_payload.append(
                {
                    "confidenceComponents": (
                        None
                        if board_result is None
                        else board_result.confidence_components.to_payload()
                    ),
                    "disposition": disposition,
                    "evidence": (
                        None if board_result is None else board_result.evidence.to_payload()
                    ),
                    "finalQuad": (
                        None
                        if board_result is None or board_result.final_quad is None
                        else board_result.final_quad.to_dict()
                    ),
                    "genericGlobalProjection": generic_accuracy.to_payload(),
                    "knownLayoutProjection": initial_accuracy.to_payload(),
                    "legacyCorpusDetector": legacy_accuracy.to_payload(),
                    "lines": (
                        []
                        if board_result is None
                        else [line.to_payload() for line in board_result.lines]
                    ),
                    "positionIndex": annotation.position_index,
                    "oracleInitializedLocalRefinement": {
                        "accuracy": oracle_accuracy.to_payload(),
                        "confidenceComponents": (
                            oracle_refinement.confidence_components.to_payload()
                        ),
                        "diagnostics": dict(oracle_refinement.diagnostics),
                        "evidence": oracle_refinement.evidence.to_payload(),
                        "intrinsicReasonCodes": [
                            value.value for value in oracle_refinement.intrinsic_reason_codes
                        ],
                    },
                    "reasonCodes": reasons,
                    "referenceQuad": annotation.reference_quad.to_dict(),
                    "sequenceNumber": annotation.sequence_number,
                    "structuredHybrid": final_accuracy.to_payload(),
                    "supplementalSignals": signal.to_payload(),
                }
            )
        image_dir = output / image.image_id
        image_dir.mkdir(parents=True, exist_ok=True)
        overlay_path = image_dir / "source-overlay.jpg"
        cells_path = image_dir / "structured-cells.jpg"
        _write_jpeg_atomic(overlay_path, _source_overlay(frame.rgb, image, result))
        contact_boards = tuple(
            (
                position,
                structured_by_position[position].disposition.value,
                structured_by_position[position].final_quad,
            )
            if position in structured_by_position
            else (position, *oracle_by_position[position])
            for position in range(len(image.boards))
        )
        _write_jpeg_atomic(cells_path, _cell_contact_sheet(frame.rgb, contact_boards))
        image_payload = {
            "activeBoardSlots": [board.position_index for board in image.boards],
            "boards": boards_payload,
            "conditionTags": list(image.condition_tags),
            "gameId": image.game_id,
            "historicalFalseSuccess": image.historical_false_success,
            "imageId": image.image_id,
            "pageKind": image.page_kind,
            "source": {
                "height": frame.source.height,
                "relativePath": image.source_relative_path,
                "sha256": image.source_checksum_sha256,
                "width": frame.source.width,
            },
            "sourceGeometry": (
                {"errorType": structured_error, "status": "engine_exception"}
                if result is None
                else result.to_payload()
            ),
            "genericGlobalInitialization": generic_initialization.to_payload(),
            "split": image.split,
        }
        diagnostic_path = image_dir / "diagnostic.json"
        _write_json_atomic(diagnostic_path, image_payload)
        summaries.append(
            {
                "artifactChecksums": {
                    "cellsJpegSha256": sha256_file(cells_path),
                    "diagnosticJsonSha256": sha256_file(diagnostic_path),
                    "sourceOverlayJpegSha256": sha256_file(overlay_path),
                },
                "artifactDirectory": image.image_id,
                "automaticBoardCount": sum(
                    board.disposition.value == "automatic"
                    for board in (() if result is None else result.boards)
                ),
                "historicalFalseSuccess": image.historical_false_success,
                "imageId": image.image_id,
                "sourceStatus": "engine_exception" if result is None else result.status.value,
            }
        )
        loader.clear()
    candidate_summary = {
        name: _candidate_summary(values) for name, values in candidate_counts.items()
    }
    signal_summary = {
        key: round(value / signal_board_count, 8) for key, value in sorted(signal_totals.items())
    }
    report = {
        "candidateSummary": candidate_summary,
        "config": config_payload(),
        "configChecksumSha256": config_checksum_sha256(),
        "corpusId": corpus.corpus_id,
        "corpusInputChecksumSha256": corpus.input_checksum_sha256,
        "corpusReadiness": readiness.to_payload(),
        "decision": {
            "status": "measurement_complete" if readiness.ready else "insufficient_corpus",
            "rolloutAuthorized": False,
            "threshold95Or98Assessed": False,
        },
        "dispositionCounts": dict(sorted(disposition_counts.items())),
        "engine": {
            "configChecksumSha256": engine.config_checksum_sha256,
            "engineId": engine.engine_id,
            "engineVersion": engine.version,
        },
        "images": summaries,
        "provenanceNotes": [
            (
                "legacyCorpusDetector uses reviewed M5 comparison quads and is not a "
                "production v20 replay."
            ),
            (
                "Supplemental Hough, gradient, periodicity and center probes use the human "
                "reference quad and are visibility diagnostics only."
            ),
            (
                "oracleInitializedLocalRefinement starts from the human reference quad and "
                "measures local-line feasibility; it is not a deployable candidate."
            ),
            "No candidate threshold in this report authorizes the 95/98 production cutover gate.",
        ],
        "reasonCodeCounts": dict(sorted(reason_counts.items())),
        "schemaVersion": SPIKE_SCHEMA_VERSION,
        "signalSummary": signal_summary,
        "technicalAssessment": _technical_assessment(
            candidate_summary=candidate_summary,
            reason_counts=reason_counts,
            readiness=readiness,
            signal_summary=signal_summary,
        ),
    }
    report["reportChecksumSha256"] = hashlib.sha256(canonical_json_bytes(report)).hexdigest()
    _write_json_atomic(output / "report.json", report)
    return report


def _board_annotations(
    annotation: Mapping[str, object],
    *,
    source_relative_path: str,
    legacy_by_key: Mapping[tuple[str, int], tuple[SourceQuad, SourceQuad]],
) -> tuple[FeasibilityBoardAnnotation, ...]:
    boards = tuple(
        FeasibilityBoardAnnotation(
            position_index=_integer(item.get("positionIndex"), "annotations.positionIndex"),
            sequence_number=_integer(item.get("sequenceNumber"), "annotations.sequenceNumber"),
            reference_quad=(
                legacy_by_key.get(
                    (
                        source_relative_path,
                        _integer(item.get("positionIndex"), "annotations.positionIndex"),
                    )
                )
                or (_source_quad(item.get("boardQuad"), "annotations.boardQuad"), None)
            )[0],
            legacy_detected_quad=(
                legacy_by_key.get(
                    (
                        source_relative_path,
                        _integer(item.get("positionIndex"), "annotations.positionIndex"),
                    )
                )
                or (_source_quad(item.get("boardQuad"), "annotations.boardQuad"), None)
            )[1],
        )
        for value in _sequence(annotation.get("boards"), "annotations.boards")
        for item in [_mapping(value, "annotations.boards[]")]
    )
    if tuple(board.position_index for board in boards) != tuple(range(len(boards))):
        raise GeometryFeasibilitySpikeError(
            "GEOMETRY_FEASIBILITY_SLOT_ORDER_INVALID",
            "Annotated boards must form an active row-major prefix.",
        )
    if tuple(board.sequence_number for board in boards) != tuple(
        range(boards[0].sequence_number, boards[0].sequence_number + len(boards))
    ):
        raise GeometryFeasibilitySpikeError(
            "GEOMETRY_FEASIBILITY_SEQUENCE_INVALID",
            "Annotated sequence numbers must be contiguous and row-major.",
        )
    return boards


def _geometry_profile(
    anchor: FeasibilityImage,
    *,
    width: int,
    height: int,
) -> Mapping[str, object]:
    return {
        "anchors": [
            {
                "imageHeight": height,
                "imageWidth": width,
                "quads": [board.reference_quad.to_dict() for board in anchor.boards],
                "sourceChecksumSha256": anchor.source_checksum_sha256,
            }
        ],
        "policy": "verified-page-registration-v1",
        "schemaVersion": 1,
    }


def _legacy_geometry_annotations(
    manifest_root: Path,
    source: Mapping[str, object],
) -> dict[tuple[str, int], tuple[SourceQuad, SourceQuad]]:
    value = source.get("legacyGeometryAnnotations")
    if value is None:
        return {}
    path = _safe_input_path(manifest_root, value, "legacyGeometryAnnotations")
    payload = _read_json(path, "legacy geometry annotations")
    result: dict[tuple[str, int], tuple[SourceQuad, SourceQuad]] = {}
    for raw in _sequence(payload.get("entries"), "legacyGeometry.entries"):
        entry = _mapping(raw, "legacyGeometry.entries[]")
        key = (
            _text(entry.get("sourceImageRelativePath"), "legacyGeometry.sourceImageRelativePath"),
            _integer(entry.get("boardPosition"), "legacyGeometry.boardPosition"),
        )
        if key in result:
            raise GeometryFeasibilitySpikeError(
                "GEOMETRY_FEASIBILITY_LEGACY_DUPLICATE",
                "Legacy comparison geometry must be unique per source and position.",
            )
        result[key] = (
            _source_quad(entry.get("sourceQuad"), "legacyGeometry.sourceQuad"),
            _source_quad(entry.get("detectedSourceQuad"), "legacyGeometry.detectedSourceQuad"),
        )
    return result


def _candidate_accuracy(
    candidate: SourceQuad | None,
    reference: SourceQuad,
    *,
    width: int,
    height: int,
) -> CandidateAccuracy:
    if candidate is None:
        return CandidateAccuracy(False, None, None, None, None)
    actual = _quad_array(candidate)
    expected = _quad_array(reference)
    maximum_error = float(np.max(np.linalg.norm(actual - expected, axis=1)))
    diagonal = math.hypot(width, height)
    normalized = maximum_error / diagonal
    try:
        intersection, _ = cv2.intersectConvexConvex(actual, expected)
    except cv2.error:
        intersection = 0.0
    first_area = abs(float(cv2.contourArea(actual)))
    second_area = abs(float(cv2.contourArea(expected)))
    union = first_area + second_area - float(intersection)
    iou = 0.0 if union <= 0 else float(intersection) / union
    return CandidateAccuracy(
        True,
        maximum_error,
        normalized,
        iou,
        normalized <= _MAX_CORNER_ERROR_DIAGONAL_FRACTION,
    )


def _count_candidate(counter: Counter[str], accuracy: CandidateAccuracy) -> None:
    if not accuracy.available:
        counter["unavailable"] += 1
    elif accuracy.provisionally_correct:
        counter["provisionallyCorrect"] += 1
    else:
        counter["provisionallyIncorrect"] += 1


def _candidate_summary(counter: Counter[str]) -> dict[str, object]:
    correct = counter["provisionallyCorrect"]
    incorrect = counter["provisionallyIncorrect"]
    available = correct + incorrect
    total = available + counter["unavailable"]
    return {
        "available": available,
        "provisionalCorrectnessAmongAvailable": (
            None if not available else round(correct / available, 8)
        ),
        "provisionallyCorrect": correct,
        "provisionallyIncorrect": incorrect,
        "total": total,
        "unavailable": counter["unavailable"],
    }


def _technical_assessment(
    *,
    candidate_summary: Mapping[str, Mapping[str, object]],
    reason_counts: Counter[str],
    readiness: CorpusReadiness,
    signal_summary: Mapping[str, float],
) -> dict[str, object]:
    generic = candidate_summary["genericGlobalProjection"]
    known = candidate_summary["knownLayoutProjection"]
    oracle = candidate_summary["oracleInitializedLocalRefinement"]
    generic_available = cast(int, generic["available"])
    known_available = cast(int, known["available"])
    known_correctness = cast(float | None, known["provisionalCorrectnessAmongAvailable"])
    oracle_available = cast(int, oracle["available"])
    oracle_correctness = cast(float | None, oracle["provisionalCorrectnessAmongAvailable"])
    horizontal_failures = reason_counts["horizontal_line_coverage_insufficient"]
    intersection_failures = reason_counts["intersection_coverage_insufficient"]
    return {
        "corpusScope": "representative" if readiness.ready else "single-corpus-limited",
        "globalInitializationWithoutProfileSufficient": generic_available > 0,
        "internalLinesConsistentlyVisible": (
            horizontal_failures == 0 and intersection_failures == 0
        ),
        "knownLayoutProjectionObservedAsUseful": (
            known_available > 0 and (known_correctness or 0.0) >= 0.95
        ),
        "localRefinementObservedAsFeasibleWithOracleRoi": (
            oracle_available > 0 and (oracle_correctness or 0.0) >= 0.95
        ),
        "outerFrameAndKnownLayoutMayCompensateForWeakLines": (
            known_available > horizontal_failures * 0.5
            and signal_summary.get("outerBorderScore", 0.0) >= 0.5
        ),
        "regularitySignalObservedAsUseful": (
            signal_summary.get("gridPeriodicityScore", 0.0) >= 0.75
        ),
        "structuredOpenCvRecommendation": (
            "conditional_go_for_broader_read_only_corpus"
            if known_available > 0 and oracle_available > 0
            else "no_go_without_initializer_changes"
        ),
        "productionRolloutAuthorized": False,
    }


def _source_overlay(
    rgb: NDArray[np.uint8],
    image: FeasibilityImage,
    result: SourceGeometryResult | None,
) -> NDArray[np.uint8]:
    output = np.array(rgb, copy=True)
    boards = {} if result is None else {board.slot.position_index: board for board in result.boards}
    for annotation in image.boards:
        board = boards.get(annotation.position_index)
        _draw_quad(output, annotation.reference_quad, (255, 255, 255), 2)
        if annotation.legacy_detected_quad is not None:
            _draw_quad(output, annotation.legacy_detected_quad, (255, 220, 0), 1)
        if board is not None and board.initial_quad is not None:
            _draw_quad(output, board.initial_quad, (40, 140, 255), 1)
        if board is not None and board.final_quad is not None:
            _draw_quad(output, board.final_quad, (30, 235, 90), 2)
        for line in () if board is None else board.lines:
            cv2.line(
                output,
                _point_tuple(line.source_start),
                _point_tuple(line.source_end),
                (210, 60, 240) if line.inferred else (40, 220, 220),
                1,
                cv2.LINE_AA,
            )
        anchor = annotation.reference_quad.corners[0]
        cv2.putText(
            output,
            (
                f"{annotation.position_index}:engine_exception"
                if board is None
                else f"{annotation.position_index}:{board.disposition.value}"
            ),
            (round(anchor.x), max(16, round(anchor.y) - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.36,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
    return output


def _cell_contact_sheet(
    rgb: NDArray[np.uint8],
    boards: Sequence[tuple[int, str, SourceQuad | None]],
) -> NDArray[np.uint8]:
    cell = 48
    board_header = 18
    board_width = 5 * cell
    board_height = board_header + 3 * cell
    sheet: NDArray[np.uint8] = np.full((3 * board_height, 3 * board_width, 3), 24, dtype=np.uint8)
    for board_index, (position_index, disposition, final_quad) in enumerate(boards):
        top = (board_index // 3) * board_height
        left = (board_index % 3) * board_width
        cv2.putText(
            sheet,
            f"slot {position_index} {disposition}",
            (left + 3, top + 13),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.34,
            (235, 235, 235),
            1,
            cv2.LINE_AA,
        )
        if final_quad is None:
            cv2.putText(
                sheet,
                "NO FINAL GEOMETRY",
                (left + 28, top + board_header + 72),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (230, 80, 80),
                1,
                cv2.LINE_AA,
            )
            continue
        rectified = _rectify(rgb, final_quad, width=500, height=300)
        for row in range(3):
            for column in range(5):
                crop = rectified[row * 100 : (row + 1) * 100, column * 100 : (column + 1) * 100]
                resized = cv2.resize(crop, (cell, cell), interpolation=cv2.INTER_AREA)
                y = top + board_header + row * cell
                x = left + column * cell
                sheet[y : y + cell, x : x + cell] = resized
                cv2.rectangle(sheet, (x, y), (x + cell - 1, y + cell - 1), (85, 85, 85), 1)
    return sheet


def _rectify(
    rgb: NDArray[np.uint8],
    quad: SourceQuad,
    *,
    width: int,
    height: int,
) -> NDArray[np.uint8]:
    destination = np.asarray(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(_quad_array(quad), destination)
    return cast(
        NDArray[np.uint8],
        cv2.warpPerspective(rgb, transform, (width, height), flags=cv2.INTER_LINEAR),
    )


def _profile_score(profile: NDArray[np.floating], cells: int) -> tuple[float, tuple[float, ...]]:
    length = profile.shape[0]
    radius = max(2, round(length / cells * 0.08))
    baseline = float(np.median(profile)) + 1e-6
    peaks: list[float] = []
    strengths: list[float] = []
    for index in range(cells + 1):
        expected = round(index * (length - 1) / cells)
        start, end = max(0, expected - radius), min(length, expected + radius + 1)
        local = profile[start:end]
        local_index = start + int(np.argmax(local))
        peaks.append(float(local_index))
        strengths.append(float(profile[local_index]) / baseline)
    score = float(np.mean([min(1.0, max(0.0, (value - 1.0) / 2.0)) for value in strengths]))
    return _unit(score), tuple(peaks)


def _spacing_score(peaks: Sequence[float], *, expected_count: int) -> float:
    if len(peaks) != expected_count or expected_count < 2:
        return 0.0
    spacing = np.diff(np.asarray(peaks, dtype=np.float64))
    mean = float(np.mean(spacing))
    if mean <= 0:
        return 0.0
    return _unit(1.0 - float(np.std(spacing)) / mean)


def _symbol_center_support(gray: NDArray[np.uint8]) -> float:
    scores: list[float] = []
    for row in range(3):
        for column in range(5):
            cell = gray[row * 100 : (row + 1) * 100, column * 100 : (column + 1) * 100]
            center = cell[22:78, 22:78]
            center_std = float(np.std(center))
            cell_std = float(np.std(cell)) + 1e-6
            scores.append(min(1.0, center_std / cell_std))
    return _unit(float(np.mean(scores)))


def _expected_support_count(coordinates: Sequence[float], length: int, cells: int) -> int:
    tolerance = length / cells * 0.14
    return sum(
        any(abs(value - index * (length - 1) / cells) <= tolerance for value in coordinates)
        for index in range(cells + 1)
    )


def _draw_quad(
    image: NDArray[np.uint8],
    quad: SourceQuad,
    color: tuple[int, int, int],
    thickness: int,
) -> None:
    points = np.rint(_quad_array(quad)).astype(np.int32).reshape((-1, 1, 2))
    cv2.polylines(image, [points], True, color, thickness, cv2.LINE_AA)


def _point_tuple(point: SourcePoint) -> tuple[int, int]:
    return round(point.x), round(point.y)


def _quad_array(quad: SourceQuad) -> NDArray[np.float32]:
    return np.asarray([[point.x, point.y] for point in quad.corners], dtype=np.float32)


def _source_quad(value: object, label: str) -> SourceQuad:
    points = tuple(
        SourcePoint(
            x=_number(item.get("x"), f"{label}.x"),
            y=_number(item.get("y"), f"{label}.y"),
        )
        for raw in _sequence(value, label)
        for item in [_mapping(raw, f"{label}[]")]
    )
    if len(points) != 4:
        raise GeometryFeasibilitySpikeError(
            "GEOMETRY_FEASIBILITY_QUAD_INVALID",
            f"{label} must contain four source points.",
        )
    return SourceQuad(corners=points)


def _condition_aliases(value: object) -> dict[str, tuple[str, ...]]:
    aliases = _mapping(value or {}, "conditionAliases")
    return {
        _text(key, "conditionAliases.key"): tuple(
            sorted(_text(item, f"conditionAliases.{key}") for item in _sequence(raw, str(key)))
        )
        for key, raw in aliases.items()
    }


def _read_json(path: Path, label: str) -> Mapping[str, object]:
    try:
        return _mapping(json.loads(path.read_bytes()), label)
    except (OSError, json.JSONDecodeError) as error:
        raise GeometryFeasibilitySpikeError(
            "GEOMETRY_FEASIBILITY_INPUT_UNREADABLE",
            f"The {label} cannot be read.",
        ) from error


def _safe_input_path(root: Path, value: object, label: str) -> Path:
    relative = _safe_relative_path(value, label)
    return _resolve_beneath(root.resolve(strict=True), relative)


def _safe_input_directory(root: Path, value: object, label: str) -> Path:
    path = _safe_input_path(root, value, label)
    if not path.is_dir():
        raise GeometryFeasibilitySpikeError(
            "GEOMETRY_FEASIBILITY_INPUT_PATH_UNSAFE", f"{label} must be a directory."
        )
    return path


def _declared_input_directory(root: Path, value: object, label: str) -> Path:
    """Resolve an explicitly declared source root, including an ancestor path.

    Unlike individual files inside that root, the root declaration may contain
    ``..`` because versioned manifests live below ``ai_docs/quality``.  All
    image paths are still resolved beneath the resulting directory.
    """

    text = _text(value, label)
    try:
        path = (root.resolve(strict=True) / Path(text)).resolve(strict=True)
    except OSError as error:
        raise GeometryFeasibilitySpikeError(
            "GEOMETRY_FEASIBILITY_INPUT_UNREADABLE", f"{label} does not exist."
        ) from error
    if not path.is_dir() or path.is_symlink():
        raise GeometryFeasibilitySpikeError(
            "GEOMETRY_FEASIBILITY_INPUT_PATH_UNSAFE", f"{label} must be a real directory."
        )
    return path


def _safe_relative_path(value: object, label: str) -> PurePosixPath:
    relative = PurePosixPath(_text(value, label))
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise GeometryFeasibilitySpikeError(
            "GEOMETRY_FEASIBILITY_INPUT_PATH_UNSAFE", f"{label} must be a safe relative path."
        )
    return relative


def _resolve_beneath(root: Path, relative: PurePosixPath) -> Path:
    try:
        resolved_root = root.resolve(strict=True)
        path = (resolved_root / Path(*relative.parts)).resolve(strict=True)
    except OSError as error:
        raise GeometryFeasibilitySpikeError(
            "GEOMETRY_FEASIBILITY_INPUT_UNREADABLE", "A feasibility input path is missing."
        ) from error
    if path.is_symlink() or not path.is_relative_to(resolved_root):
        raise GeometryFeasibilitySpikeError(
            "GEOMETRY_FEASIBILITY_INPUT_PATH_UNSAFE",
            "A feasibility input path escapes its declared root.",
        )
    return path


def _write_json_atomic(path: Path, value: object) -> None:
    content = (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
    )
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def _write_jpeg_atomic(path: Path, rgb: NDArray[np.uint8]) -> None:
    success, encoded = cv2.imencode(
        ".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 88]
    )
    if not success:
        raise GeometryFeasibilitySpikeError(
            "GEOMETRY_FEASIBILITY_ARTIFACT_WRITE_FAILED", "A diagnostic JPEG could not be encoded."
        )
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(encoded.tobytes())
    temporary.replace(path)


def _unexpected_anchor_load(_checksum: str) -> NDArray[np.uint8]:
    raise GeometryFeasibilitySpikeError(
        "GEOMETRY_FEASIBILITY_UNDECLARED_ANCHOR",
        "The read-only spike input did not declare a verified profile anchor.",
    )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise GeometryFeasibilitySpikeError(
            "GEOMETRY_FEASIBILITY_INPUT_INVALID", f"{label} must be an object."
        )
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise GeometryFeasibilitySpikeError(
            "GEOMETRY_FEASIBILITY_INPUT_INVALID", f"{label} must be an array."
        )
    return cast(Sequence[object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GeometryFeasibilitySpikeError(
            "GEOMETRY_FEASIBILITY_INPUT_INVALID", f"{label} must be non-empty text."
        )
    return value


def _sha256_text(value: object, label: str) -> str:
    result = _text(value, label)
    if len(result) != 64 or any(character not in "0123456789abcdef" for character in result):
        raise GeometryFeasibilitySpikeError(
            "GEOMETRY_FEASIBILITY_INPUT_INVALID", f"{label} must be a lowercase SHA-256."
        )
    return result


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise GeometryFeasibilitySpikeError(
            "GEOMETRY_FEASIBILITY_INPUT_INVALID", f"{label} must be an integer."
        )
    return value


def _number(value: object, label: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise GeometryFeasibilitySpikeError(
            "GEOMETRY_FEASIBILITY_INPUT_INVALID", f"{label} must be numeric."
        )
    result = float(value)
    if not math.isfinite(result):
        raise GeometryFeasibilitySpikeError(
            "GEOMETRY_FEASIBILITY_INPUT_INVALID", f"{label} must be finite."
        )
    return result


def _unit(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 8)


__all__ = [
    "SPIKE_CONFIG_VERSION",
    "SPIKE_INPUT_VERSION",
    "SPIKE_SCHEMA_VERSION",
    "CorpusReadiness",
    "FeasibilityCorpus",
    "FeasibilityImage",
    "GeometryFeasibilitySpikeError",
    "SupplementalSignalProbe",
    "assess_corpus_readiness",
    "config_checksum_sha256",
    "config_payload",
    "load_feasibility_corpus",
    "probe_reference_board_signals",
    "run_feasibility_spike",
]
