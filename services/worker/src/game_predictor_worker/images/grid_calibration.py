"""Versioned source-quad calibration profiles for the M5 image corpus."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray

from .cell_grid_golden import CellGridGolden
from .geometry import Point, Quad
from .rectification import BoardGeometry, PageGeometry

PROFILE_SET_VERSION = "grid-calibration-profiles-v1"
PROFILE_VERSION = 1
INTERPOLATION_VERSION = "sequence-linear-clamped-v1"
SOURCE_QUAD_SOURCE = "calibration-profile"
EXPECTED_BOARD_POSITIONS = tuple(range(9))

FloatPoint = tuple[float, float]
FloatQuad = tuple[FloatPoint, FloatPoint, FloatPoint, FloatPoint]
LocalOffset = tuple[float, float]
LocalOffsets = tuple[LocalOffset, LocalOffset, LocalOffset, LocalOffset]


class GridCalibrationError(ValueError):
    """Stable failure for profile generation, loading or application."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _profile_id(source_group: str, board_position: int) -> str:
    identity = f"{PROFILE_SET_VERSION}\0{source_group}\0{board_position}".encode()
    return hashlib.sha256(identity).hexdigest()


def _float_quad_array(quad: FloatQuad) -> NDArray[np.float64]:
    return np.asarray(quad, dtype=np.float64)


def _local_basis(quad: FloatQuad) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    points = _float_quad_array(quad)
    horizontal = ((points[1] - points[0]) + (points[2] - points[3])) / 2.0
    vertical = ((points[3] - points[0]) + (points[2] - points[1])) / 2.0
    basis = np.column_stack((horizontal, vertical))
    determinant = float(np.linalg.det(basis))
    if not math.isfinite(determinant) or abs(determinant) < 1e-6:
        raise GridCalibrationError(
            "GRID_CALIBRATION_QUAD_DEGENERATE",
            "The detector quad cannot define a stable local calibration basis.",
        )
    return points, basis


def local_corner_offsets(detected: FloatQuad, accepted: FloatQuad) -> LocalOffsets:
    """Represent accepted corners in the detector quad's local basis."""

    detected_points, basis = _local_basis(detected)
    accepted_points = _float_quad_array(accepted)
    offsets = tuple(
        (
            round(float(value[0]), 10),
            round(float(value[1]), 10),
        )
        for value in (
            np.linalg.solve(basis, accepted_points[index] - detected_points[index])
            for index in range(4)
        )
    )
    return cast(LocalOffsets, offsets)


def apply_local_corner_offsets(detected: FloatQuad, offsets: LocalOffsets) -> Quad:
    """Apply local offsets and round to detector-compatible source pixels."""

    detected_points, basis = _local_basis(detected)
    calibrated = detected_points + np.asarray(
        [basis @ np.asarray(offset, dtype=np.float64) for offset in offsets],
        dtype=np.float64,
    )
    if not np.isfinite(calibrated).all():
        raise GridCalibrationError(
            "GRID_CALIBRATION_RESULT_INVALID",
            "The calibrated source quad contains non-finite coordinates.",
        )
    return cast(
        Quad,
        tuple(Point(x=int(round(point[0])), y=int(round(point[1]))) for point in calibrated),
    )


def _quad_dict(quad: FloatQuad) -> list[dict[str, float]]:
    return [{"x": point[0], "y": point[1]} for point in quad]


def _offsets_dict(offsets: LocalOffsets) -> list[dict[str, float]]:
    return [{"u": offset[0], "v": offset[1]} for offset in offsets]


def build_profile_document(
    golden: CellGridGolden,
    *,
    golden_sha256: str,
    detector_report_sha256: str,
) -> dict[str, object]:
    """Create immutable group-position profiles from accepted golden anchors."""

    if any(entry.review_status != "accepted" for entry in golden.entries):
        raise GridCalibrationError(
            "GRID_CALIBRATION_GOLDEN_INCOMPLETE",
            "Every cell-grid golden entry must be accepted before profile publication.",
        )
    grouped: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    reviewers: set[str] = set()
    for entry in golden.entries:
        candidate = entry.candidate
        if entry.reviewed_by is None:
            raise GridCalibrationError(
                "GRID_CALIBRATION_GOLDEN_INCOMPLETE",
                "Every calibration anchor must carry a reviewer identity.",
            )
        reviewers.add(entry.reviewed_by)
        grouped[(candidate.source_group, candidate.board_position)].append(
            {
                "acceptedSourceQuad": _quad_dict(entry.source_quad),
                "detectedSourceQuad": _quad_dict(candidate.detected_source_quad),
                "localCornerOffsets": _offsets_dict(
                    local_corner_offsets(
                        candidate.detected_source_quad,
                        entry.source_quad,
                    )
                ),
                "observationId": candidate.observation_id,
                "sequenceNumber": candidate.sequence_number,
                "sourceImageChecksumSha256": candidate.source_image_checksum_sha256,
            }
        )

    expected_scopes = {
        (source_group, position)
        for source_group in golden.source_groups
        for position in EXPECTED_BOARD_POSITIONS
    }
    if set(grouped) != expected_scopes:
        raise GridCalibrationError(
            "GRID_CALIBRATION_SCOPE_INCOMPLETE",
            "Accepted golden anchors do not cover every source-group/position scope.",
        )

    profiles: list[dict[str, object]] = []
    for source_group, position in sorted(grouped):
        anchors = sorted(
            grouped[(source_group, position)],
            key=lambda anchor: cast(int, anchor["sequenceNumber"]),
        )
        sequences = [cast(int, anchor["sequenceNumber"]) for anchor in anchors]
        if len(set(sequences)) != len(sequences):
            raise GridCalibrationError(
                "GRID_CALIBRATION_ANCHOR_DUPLICATE",
                "A calibration profile cannot contain duplicate sequence anchors.",
            )
        profiles.append(
            {
                "anchors": anchors,
                "boardPosition": position,
                "interpolation": INTERPOLATION_VERSION,
                "profileId": _profile_id(source_group, position),
                "profileVersion": PROFILE_VERSION,
                "sourceGroup": source_group,
                "status": "published",
            }
        )
    return {
        "anchorCount": len(golden.entries),
        "coordinateSystem": "detector-quad-local-basis",
        "corpusId": golden.corpus_id,
        "corpusManifestSha256": golden.corpus_manifest_sha256,
        "detectorReportSha256": detector_report_sha256,
        "goldenSha256": golden_sha256,
        "goldenVersion": golden.to_dict()["goldenVersion"],
        "interpolation": INTERPOLATION_VERSION,
        "profileCount": len(profiles),
        "profileSetVersion": PROFILE_SET_VERSION,
        "profiles": profiles,
        "publishedBy": sorted(reviewers),
        "schemaVersion": 1,
        "sourceGroups": list(golden.source_groups),
        "status": "published",
    }


@dataclass(frozen=True, slots=True)
class CalibrationAnchor:
    observation_id: str
    sequence_number: int
    source_image_checksum_sha256: str
    detected_source_quad: FloatQuad
    accepted_source_quad: FloatQuad
    local_corner_offsets: LocalOffsets


@dataclass(frozen=True, slots=True)
class CalibrationProfile:
    profile_id: str
    source_group: str
    board_position: int
    anchors: tuple[CalibrationAnchor, ...]


@dataclass(frozen=True, slots=True)
class CalibrationApplication:
    calibrated_quad: Quad
    profile_id: str
    anchor_sequence_numbers: tuple[int, ...]
    interpolation_weight: float


@dataclass(frozen=True, slots=True)
class _SourceContext:
    source_group: str
    expected_sequence_start: int
    expected_board_count: int


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise GridCalibrationError(
            "GRID_CALIBRATION_CONTRACT_INVALID",
            f"{label} must be an object.",
        )
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise GridCalibrationError(
            "GRID_CALIBRATION_CONTRACT_INVALID",
            f"{label} must be an array.",
        )
    return cast(Sequence[object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise GridCalibrationError(
            "GRID_CALIBRATION_CONTRACT_INVALID",
            f"{label} must be a non-empty string.",
        )
    return value


def _sha256(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise GridCalibrationError(
            "GRID_CALIBRATION_CONTRACT_INVALID",
            f"{label} must be a lowercase SHA-256.",
        )
    return text


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise GridCalibrationError(
            "GRID_CALIBRATION_CONTRACT_INVALID",
            f"{label} must be an integer greater than or equal to {minimum}.",
        )
    return value


def _finite(value: object, label: str) -> float:
    if (
        not isinstance(value, int | float)
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        raise GridCalibrationError(
            "GRID_CALIBRATION_CONTRACT_INVALID",
            f"{label} must be a finite number.",
        )
    return float(value)


def _float_quad(value: object, label: str) -> FloatQuad:
    raw_points = _sequence(value, label)
    if len(raw_points) != 4:
        raise GridCalibrationError(
            "GRID_CALIBRATION_CONTRACT_INVALID",
            f"{label} must contain four points.",
        )
    points = tuple(
        (
            _finite(_mapping(raw, f"{label}[{index}]").get("x"), f"{label}[{index}].x"),
            _finite(_mapping(raw, f"{label}[{index}]").get("y"), f"{label}[{index}].y"),
        )
        for index, raw in enumerate(raw_points)
    )
    return cast(FloatQuad, points)


def _local_offsets(value: object, label: str) -> LocalOffsets:
    raw_offsets = _sequence(value, label)
    if len(raw_offsets) != 4:
        raise GridCalibrationError(
            "GRID_CALIBRATION_CONTRACT_INVALID",
            f"{label} must contain four offsets.",
        )
    offsets: list[LocalOffset] = []
    for index, raw in enumerate(raw_offsets):
        item = _mapping(raw, f"{label}[{index}]")
        offset = (
            _finite(item.get("u"), f"{label}[{index}].u"),
            _finite(item.get("v"), f"{label}[{index}].v"),
        )
        if max(abs(offset[0]), abs(offset[1])) > 1.0:
            raise GridCalibrationError(
                "GRID_CALIBRATION_OFFSET_OUT_OF_RANGE",
                "Local corner offsets must remain within one detector-quad basis unit.",
            )
        offsets.append(offset)
    return cast(LocalOffsets, tuple(offsets))


def _load_json(path: Path, label: str) -> tuple[bytes, Mapping[str, object]]:
    try:
        content = path.read_bytes()
        value: Any = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise GridCalibrationError(
            "GRID_CALIBRATION_FILE_UNREADABLE",
            f"{label} cannot be read.",
        ) from error
    return content, _mapping(value, label)


class GridCalibrationProfiles:
    """Validated published profile set and full-corpus geometry calibrator."""

    profile_set_version = PROFILE_SET_VERSION

    def __init__(
        self,
        *,
        profile_set_sha256: str,
        corpus_manifest_sha256: str,
        detector_report_sha256: str,
        profiles: tuple[CalibrationProfile, ...],
        source_contexts: Mapping[str, _SourceContext],
    ) -> None:
        self.profile_set_sha256 = profile_set_sha256
        self.corpus_manifest_sha256 = corpus_manifest_sha256
        self.detection_report_sha256 = detector_report_sha256
        self._profiles = {
            (profile.source_group, profile.board_position): profile for profile in profiles
        }
        self._source_contexts = dict(source_contexts)

    @classmethod
    def from_files(
        cls,
        profile_path: Path,
        corpus_manifest_path: Path,
    ) -> GridCalibrationProfiles:
        profile_bytes, document = _load_json(profile_path, "calibrationProfiles")
        manifest_bytes, manifest = _load_json(corpus_manifest_path, "corpusManifest")
        manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
        if (
            document.get("schemaVersion") != 1
            or document.get("profileSetVersion") != PROFILE_SET_VERSION
            or document.get("interpolation") != INTERPOLATION_VERSION
            or document.get("status") != "published"
            or document.get("corpusManifestSha256") != manifest_sha
        ):
            raise GridCalibrationError(
                "GRID_CALIBRATION_PROFILE_SET_INVALID",
                "A published profile set matching the corpus manifest is required.",
            )
        detector_sha = _sha256(
            document.get("detectorReportSha256"),
            "calibrationProfiles.detectorReportSha256",
        )
        source_groups = tuple(
            _text(value, f"calibrationProfiles.sourceGroups[{index}]")
            for index, value in enumerate(
                _sequence(document.get("sourceGroups"), "calibrationProfiles.sourceGroups")
            )
        )
        if tuple(sorted(set(source_groups))) != source_groups or len(source_groups) < 1:
            raise GridCalibrationError(
                "GRID_CALIBRATION_PROFILE_SET_INVALID",
                "Profile source groups must be unique and sorted.",
            )

        parsed_profiles: list[CalibrationProfile] = []
        for profile_index, raw_profile in enumerate(
            _sequence(document.get("profiles"), "calibrationProfiles.profiles")
        ):
            item = _mapping(raw_profile, f"calibrationProfiles.profiles[{profile_index}]")
            source_group = _text(item.get("sourceGroup"), "profile.sourceGroup")
            position = _integer(item.get("boardPosition"), "profile.boardPosition")
            if (
                source_group not in source_groups
                or position not in EXPECTED_BOARD_POSITIONS
                or item.get("profileVersion") != PROFILE_VERSION
                or item.get("interpolation") != INTERPOLATION_VERSION
                or item.get("status") != "published"
                or item.get("profileId") != _profile_id(source_group, position)
            ):
                raise GridCalibrationError(
                    "GRID_CALIBRATION_PROFILE_INVALID",
                    "Calibration profile identity or scope is invalid.",
                )
            anchors: list[CalibrationAnchor] = []
            for anchor_index, raw_anchor in enumerate(
                _sequence(item.get("anchors"), "profile.anchors")
            ):
                anchor = _mapping(raw_anchor, f"profile.anchors[{anchor_index}]")
                detected = _float_quad(
                    anchor.get("detectedSourceQuad"),
                    "anchor.detectedSourceQuad",
                )
                accepted = _float_quad(
                    anchor.get("acceptedSourceQuad"),
                    "anchor.acceptedSourceQuad",
                )
                offsets = _local_offsets(
                    anchor.get("localCornerOffsets"),
                    "anchor.localCornerOffsets",
                )
                expected_offsets = local_corner_offsets(detected, accepted)
                if any(
                    abs(actual_axis - expected_axis) > 1e-8
                    for actual, expected in zip(offsets, expected_offsets, strict=True)
                    for actual_axis, expected_axis in zip(actual, expected, strict=True)
                ):
                    raise GridCalibrationError(
                        "GRID_CALIBRATION_ANCHOR_DRIFT",
                        "Stored local offsets differ from the anchor source quads.",
                    )
                anchors.append(
                    CalibrationAnchor(
                        observation_id=_sha256(
                            anchor.get("observationId"),
                            "anchor.observationId",
                        ),
                        sequence_number=_integer(
                            anchor.get("sequenceNumber"),
                            "anchor.sequenceNumber",
                            minimum=1,
                        ),
                        source_image_checksum_sha256=_sha256(
                            anchor.get("sourceImageChecksumSha256"),
                            "anchor.sourceImageChecksumSha256",
                        ),
                        detected_source_quad=detected,
                        accepted_source_quad=accepted,
                        local_corner_offsets=offsets,
                    )
                )
            if not anchors or [anchor.sequence_number for anchor in anchors] != sorted(
                {anchor.sequence_number for anchor in anchors}
            ):
                raise GridCalibrationError(
                    "GRID_CALIBRATION_ANCHOR_ORDER_INVALID",
                    "Profile anchors must have unique ascending sequence numbers.",
                )
            parsed_profiles.append(
                CalibrationProfile(
                    profile_id=_profile_id(source_group, position),
                    source_group=source_group,
                    board_position=position,
                    anchors=tuple(anchors),
                )
            )

        expected_scopes = {
            (source_group, position)
            for source_group in source_groups
            for position in EXPECTED_BOARD_POSITIONS
        }
        actual_scopes = {
            (profile.source_group, profile.board_position) for profile in parsed_profiles
        }
        anchor_count = sum(len(profile.anchors) for profile in parsed_profiles)
        if (
            actual_scopes != expected_scopes
            or len(actual_scopes) != len(parsed_profiles)
            or document.get("profileCount") != len(parsed_profiles)
            or document.get("anchorCount") != anchor_count
        ):
            raise GridCalibrationError(
                "GRID_CALIBRATION_SCOPE_INCOMPLETE",
                "Published profiles must cover every unique source-group/position scope.",
            )

        if (
            manifest.get("schemaVersion") != 1
            or manifest.get("status") != "accepted"
            or manifest.get("corpusId") != document.get("corpusId")
        ):
            raise GridCalibrationError(
                "GRID_CALIBRATION_MANIFEST_INVALID",
                "An accepted matching corpus manifest is required.",
            )
        source_contexts: dict[str, _SourceContext] = {}
        for image_index, raw_image in enumerate(
            _sequence(manifest.get("images"), "corpusManifest.images")
        ):
            image = _mapping(raw_image, f"corpusManifest.images[{image_index}]")
            source_checksum = _sha256(image.get("sha256"), "manifest image sha256")
            source_group = _text(image.get("sourceGroup"), "manifest image sourceGroup")
            if source_checksum in source_contexts or source_group not in source_groups:
                raise GridCalibrationError(
                    "GRID_CALIBRATION_MANIFEST_INVALID",
                    "Manifest sources must be unique and use a profiled source group.",
                )
            source_contexts[source_checksum] = _SourceContext(
                source_group=source_group,
                expected_sequence_start=_integer(
                    image.get("expectedSequenceStart"),
                    "manifest image expectedSequenceStart",
                    minimum=1,
                ),
                expected_board_count=_integer(
                    image.get("expectedBoardCount"),
                    "manifest image expectedBoardCount",
                    minimum=1,
                ),
            )
        if document.get("profileCount") != len(expected_scopes):
            raise GridCalibrationError(
                "GRID_CALIBRATION_PROFILE_SET_INVALID",
                "Declared profile count differs from the required scope count.",
            )
        return cls(
            profile_set_sha256=hashlib.sha256(profile_bytes).hexdigest(),
            corpus_manifest_sha256=manifest_sha,
            detector_report_sha256=detector_sha,
            profiles=tuple(parsed_profiles),
            source_contexts=source_contexts,
        )

    def apply(
        self,
        *,
        source_group: str,
        board_position: int,
        sequence_number: int,
        detected_quad: FloatQuad,
    ) -> CalibrationApplication:
        profile = self._profiles.get((source_group, board_position))
        if profile is None:
            raise GridCalibrationError(
                "GRID_CALIBRATION_SCOPE_MISSING",
                "No published calibration profile matches this source group and position.",
            )
        anchors = profile.anchors
        selected: tuple[CalibrationAnchor, ...]
        if sequence_number <= anchors[0].sequence_number:
            selected = (anchors[0],)
            weight = 0.0
            offsets = anchors[0].local_corner_offsets
        elif sequence_number >= anchors[-1].sequence_number:
            selected = (anchors[-1],)
            weight = 0.0
            offsets = anchors[-1].local_corner_offsets
        else:
            left, right = next(
                (left, right)
                for left, right in zip(anchors, anchors[1:], strict=False)
                if left.sequence_number <= sequence_number <= right.sequence_number
            )
            if sequence_number == left.sequence_number:
                selected = (left,)
                weight = 0.0
                offsets = left.local_corner_offsets
            elif sequence_number == right.sequence_number:
                selected = (right,)
                weight = 0.0
                offsets = right.local_corner_offsets
            else:
                selected = (left, right)
                weight = (sequence_number - left.sequence_number) / (
                    right.sequence_number - left.sequence_number
                )
                offsets = cast(
                    LocalOffsets,
                    tuple(
                        (
                            left_offset[0] + weight * (right_offset[0] - left_offset[0]),
                            left_offset[1] + weight * (right_offset[1] - left_offset[1]),
                        )
                        for left_offset, right_offset in zip(
                            left.local_corner_offsets,
                            right.local_corner_offsets,
                            strict=True,
                        )
                    ),
                )
        return CalibrationApplication(
            calibrated_quad=apply_local_corner_offsets(detected_quad, offsets),
            profile_id=profile.profile_id,
            anchor_sequence_numbers=tuple(anchor.sequence_number for anchor in selected),
            interpolation_weight=round(weight, 10),
        )

    def calibrate(
        self,
        source_checksum_sha256: str,
        geometry: PageGeometry,
    ) -> PageGeometry:
        if geometry.status != "detected":
            return geometry
        context = self._source_contexts.get(source_checksum_sha256)
        if context is None:
            raise GridCalibrationError(
                "GRID_CALIBRATION_SOURCE_UNKNOWN",
                "The detected source is absent from the calibration corpus manifest.",
            )
        if len(geometry.boards) != context.expected_board_count:
            raise GridCalibrationError(
                "GRID_CALIBRATION_BOARD_COUNT_DRIFT",
                "Detected board count differs from the calibration source contract.",
            )
        calibrated: list[BoardGeometry] = []
        for board in geometry.boards:
            sequence_number = context.expected_sequence_start + board.position_index
            detected_quad = cast(
                FloatQuad,
                tuple((float(point.x), float(point.y)) for point in board.quad),
            )
            application = self.apply(
                source_group=context.source_group,
                board_position=board.position_index,
                sequence_number=sequence_number,
                detected_quad=detected_quad,
            )
            calibrated.append(
                BoardGeometry(
                    position_index=board.position_index,
                    quad=application.calibrated_quad,
                    bounding_box=board.bounding_box,
                    source_quad_source=SOURCE_QUAD_SOURCE,
                    calibration_profile_id=application.profile_id,
                    calibration_profile_version=PROFILE_VERSION,
                    calibration_anchor_sequence_numbers=application.anchor_sequence_numbers,
                    calibration_interpolation_weight=application.interpolation_weight,
                )
            )
        return PageGeometry(
            status=geometry.status,
            image_width=geometry.image_width,
            image_height=geometry.image_height,
            boards=tuple(calibrated),
            review_reasons=geometry.review_reasons,
        )


def profile_document_bytes(document: Mapping[str, object]) -> bytes:
    return _json_bytes(document)


__all__ = [
    "INTERPOLATION_VERSION",
    "PROFILE_SET_VERSION",
    "PROFILE_VERSION",
    "SOURCE_QUAD_SOURCE",
    "CalibrationApplication",
    "GridCalibrationError",
    "GridCalibrationProfiles",
    "apply_local_corner_offsets",
    "build_profile_document",
    "local_corner_offsets",
    "profile_document_bytes",
]
