"""Exact-source local-frame calibration for board rectification."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from .cell_grid_golden import CellGridGolden
from .grid_calibration import (
    FloatQuad,
    LocalOffsets,
    apply_local_corner_offsets,
    local_corner_offsets,
)
from .rectification import BoardGeometry, PageGeometry

PROFILE_SET_VERSION = "local-grid-calibration-profiles-v2"
COMPLETE_PROFILE_SET_VERSION = "local-grid-calibration-profiles-v3-complete"
PROFILE_VERSION = 2
BASIS_VERSION = "detector-bounding-box-v1"
SOURCE_QUAD_SOURCE = "local-image-calibration-profile"
MISSING_PROFILE_REASON = "LOCAL_GRID_CALIBRATION_PROFILE_MISSING"


class LocalGridCalibrationError(ValueError):
    """Stable failure for exact-source calibration."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise LocalGridCalibrationError(
            "LOCAL_GRID_CALIBRATION_CONTRACT_INVALID",
            f"{label} must be an object.",
        )
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise LocalGridCalibrationError(
            "LOCAL_GRID_CALIBRATION_CONTRACT_INVALID",
            f"{label} must be an array.",
        )
    return cast(Sequence[object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise LocalGridCalibrationError(
            "LOCAL_GRID_CALIBRATION_CONTRACT_INVALID",
            f"{label} must be a non-empty string.",
        )
    return value


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise LocalGridCalibrationError(
            "LOCAL_GRID_CALIBRATION_CONTRACT_INVALID",
            f"{label} must be an integer greater than or equal to {minimum}.",
        )
    return value


def _sha256(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise LocalGridCalibrationError(
            "LOCAL_GRID_CALIBRATION_CONTRACT_INVALID",
            f"{label} must be a lowercase SHA-256.",
        )
    return text


def _float_quad(value: object, label: str) -> FloatQuad:
    points = _sequence(value, label)
    if len(points) != 4:
        raise LocalGridCalibrationError(
            "LOCAL_GRID_CALIBRATION_CONTRACT_INVALID",
            f"{label} must contain four points.",
        )
    parsed: list[tuple[float, float]] = []
    for index, raw in enumerate(points):
        point = _mapping(raw, f"{label}[{index}]")
        x = point.get("x")
        y = point.get("y")
        if (
            not isinstance(x, int | float)
            or isinstance(x, bool)
            or not isinstance(y, int | float)
            or isinstance(y, bool)
        ):
            raise LocalGridCalibrationError(
                "LOCAL_GRID_CALIBRATION_CONTRACT_INVALID",
                f"{label}[{index}] must contain numeric x and y.",
            )
        parsed.append((float(x), float(y)))
    return cast(FloatQuad, tuple(parsed))


def _offsets(value: object, label: str) -> LocalOffsets:
    items = _sequence(value, label)
    if len(items) != 4:
        raise LocalGridCalibrationError(
            "LOCAL_GRID_CALIBRATION_CONTRACT_INVALID",
            f"{label} must contain four offsets.",
        )
    parsed: list[tuple[float, float]] = []
    for index, raw in enumerate(items):
        item = _mapping(raw, f"{label}[{index}]")
        u = item.get("u")
        v = item.get("v")
        if (
            not isinstance(u, int | float)
            or isinstance(u, bool)
            or not isinstance(v, int | float)
            or isinstance(v, bool)
            or max(abs(float(u)), abs(float(v))) > 1.0
        ):
            raise LocalGridCalibrationError(
                "LOCAL_GRID_CALIBRATION_OFFSET_INVALID",
                f"{label}[{index}] is outside the supported local basis.",
            )
        parsed.append((float(u), float(v)))
    return cast(LocalOffsets, tuple(parsed))


def local_bounding_frame(bounding_box: tuple[int, int, int, int]) -> FloatQuad:
    """Create the deterministic per-board basis from the detector bounding frame."""

    x, y, width, height = bounding_box
    if x < 0 or y < 0 or width < 2 or height < 2:
        raise LocalGridCalibrationError(
            "LOCAL_GRID_CALIBRATION_BOUNDING_BOX_INVALID",
            "A non-degenerate detector bounding box is required.",
        )
    return (
        (float(x), float(y)),
        (float(x + width - 1), float(y)),
        (float(x + width - 1), float(y + height - 1)),
        (float(x), float(y + height - 1)),
    )


def _quad_dict(quad: FloatQuad) -> list[dict[str, float]]:
    return [{"x": point[0], "y": point[1]} for point in quad]


def _offsets_dict(offsets: LocalOffsets) -> list[dict[str, float]]:
    return [{"u": offset[0], "v": offset[1]} for offset in offsets]


def _profile_id(source_checksum: str, profile_set_version: str) -> str:
    return hashlib.sha256(f"{profile_set_version}\0{source_checksum}".encode()).hexdigest()


def _detection_by_source(
    detection_report: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    if detection_report.get("detectorVersion") != "page-board-detector-v2":
        raise LocalGridCalibrationError(
            "LOCAL_GRID_CALIBRATION_DETECTION_UNSUPPORTED",
            "A page-board-detector-v2 report is required.",
        )
    detections: dict[str, Mapping[str, object]] = {}
    for index, raw in enumerate(
        _sequence(detection_report.get("detections"), "detectionReport.detections")
    ):
        item = _mapping(raw, f"detectionReport.detections[{index}]")
        source = _sha256(
            item.get("sourceChecksumSha256"),
            f"detectionReport.detections[{index}].sourceChecksumSha256",
        )
        if source in detections:
            raise LocalGridCalibrationError(
                "LOCAL_GRID_CALIBRATION_DETECTION_DUPLICATE",
                "A source image occurs more than once in the detection report.",
            )
        detections[source] = item
    return detections


def _bounding_box(
    board: Mapping[str, object],
    label: str,
) -> tuple[int, int, int, int]:
    value = _mapping(board.get("boundingBox"), f"{label}.boundingBox")
    return (
        _integer(value.get("x"), f"{label}.boundingBox.x"),
        _integer(value.get("y"), f"{label}.boundingBox.y"),
        _integer(value.get("width"), f"{label}.boundingBox.width", minimum=2),
        _integer(value.get("height"), f"{label}.boundingBox.height", minimum=2),
    )


def build_local_profile_document(
    golden: CellGridGolden,
    *,
    golden_sha256: str,
    detector_report_sha256: str,
    detection_report: Mapping[str, object],
    corpus_manifest: Mapping[str, object],
    profile_set_version: str = PROFILE_SET_VERSION,
) -> dict[str, object]:
    """Build exact-source profiles and list source images still needing one anchor."""

    if any(entry.review_status != "accepted" for entry in golden.entries):
        raise LocalGridCalibrationError(
            "LOCAL_GRID_CALIBRATION_GOLDEN_INCOMPLETE",
            "Every selected source anchor must be accepted.",
        )
    detections = _detection_by_source(detection_report)
    manifest_sources: dict[str, Mapping[str, object]] = {}
    for index, raw in enumerate(_sequence(corpus_manifest.get("images"), "corpusManifest.images")):
        item = _mapping(raw, f"corpusManifest.images[{index}]")
        source = _sha256(item.get("sha256"), f"corpusManifest.images[{index}].sha256")
        manifest_sources[source] = item
    if set(detections) != set(manifest_sources):
        raise LocalGridCalibrationError(
            "LOCAL_GRID_CALIBRATION_SOURCE_DRIFT",
            "Detection and corpus sources differ.",
        )

    profiles: list[dict[str, object]] = []
    covered: set[str] = set()
    reviewers: set[str] = set()
    for entry in golden.entries:
        candidate = entry.candidate
        source = candidate.source_image_checksum_sha256
        if source in covered:
            raise LocalGridCalibrationError(
                "LOCAL_GRID_CALIBRATION_ANCHOR_DUPLICATE",
                "A source image may have exactly one local calibration anchor.",
            )
        detection = detections.get(source)
        if detection is None or entry.reviewed_by is None:
            raise LocalGridCalibrationError(
                "LOCAL_GRID_CALIBRATION_ANCHOR_INVALID",
                "The accepted anchor is missing detection or reviewer provenance.",
            )
        result = _mapping(detection.get("result"), "detection.result")
        matching = [
            _mapping(raw, "detection board")
            for raw in _sequence(result.get("boards"), "detection.result.boards")
            if _mapping(raw, "detection board").get("positionIndex") == candidate.board_position
        ]
        if len(matching) != 1:
            raise LocalGridCalibrationError(
                "LOCAL_GRID_CALIBRATION_ANCHOR_INVALID",
                "The anchor board position is missing or duplicated.",
            )
        bounding_box = _bounding_box(matching[0], "anchor board")
        local_base = local_bounding_frame(bounding_box)
        offsets = local_corner_offsets(local_base, candidate_quad(entry.source_quad))
        profiles.append(
            {
                "anchor": {
                    "acceptedSourceQuad": _quad_dict(candidate_quad(entry.source_quad)),
                    "boardPosition": candidate.board_position,
                    "localBaseQuad": _quad_dict(local_base),
                    "localCornerOffsets": _offsets_dict(offsets),
                    "observationId": candidate.observation_id,
                    "sequenceNumber": candidate.sequence_number,
                },
                "basisVersion": BASIS_VERSION,
                "profileId": _profile_id(source, profile_set_version),
                "profileVersion": PROFILE_VERSION,
                "sourceGroup": candidate.source_group,
                "sourceImageChecksumSha256": source,
                "status": "published",
            }
        )
        covered.add(source)
        reviewers.add(entry.reviewed_by)
    profiles.sort(key=lambda profile: cast(str, profile["sourceImageChecksumSha256"]))
    missing = sorted(set(manifest_sources) - covered)
    return {
        "basisVersion": BASIS_VERSION,
        "corpusId": golden.corpus_id,
        "corpusManifestSha256": golden.corpus_manifest_sha256,
        "coveredSourceImageCount": len(covered),
        "detectorReportSha256": detector_report_sha256,
        "goldenSha256": golden_sha256,
        "goldenVersion": golden.to_dict()["goldenVersion"],
        "missingSourceImageChecksums": missing,
        "profileCount": len(profiles),
        "profileSetVersion": profile_set_version,
        "profiles": profiles,
        "publishedBy": sorted(reviewers),
        "schemaVersion": 1,
        "sourceImageCount": len(manifest_sources),
        "status": "ready_for_heldout" if not missing else "partial_review_required",
        "trainingAllowed": False,
    }


def candidate_quad(value: FloatQuad) -> FloatQuad:
    """Keep an explicit typed boundary between golden and profile coordinates."""

    return value


@dataclass(frozen=True, slots=True)
class LocalImageProfile:
    profile_id: str
    source_checksum_sha256: str
    source_group: str
    anchor_sequence_number: int
    anchor_board_position: int
    offsets: LocalOffsets


@dataclass(frozen=True, slots=True)
class _SourceContext:
    source_group: str
    expected_board_count: int


class LocalImageGridCalibrationProfiles:
    """Apply one local-frame correction only within its exact source image."""

    def __init__(
        self,
        *,
        profile_set_version: str,
        profile_set_sha256: str,
        corpus_manifest_sha256: str,
        detector_report_sha256: str,
        profiles: Mapping[str, LocalImageProfile],
        source_contexts: Mapping[str, _SourceContext],
    ) -> None:
        self.profile_set_version = profile_set_version
        self.profile_set_sha256 = profile_set_sha256
        self.corpus_manifest_sha256 = corpus_manifest_sha256
        self.detection_report_sha256 = detector_report_sha256
        self._profiles = dict(profiles)
        self._source_contexts = dict(source_contexts)

    @classmethod
    def from_files(
        cls,
        profile_path: Path,
        corpus_manifest_path: Path,
    ) -> LocalImageGridCalibrationProfiles:
        try:
            profile_bytes = profile_path.read_bytes()
            document = _mapping(json.loads(profile_bytes), "localProfiles")
            manifest_bytes = corpus_manifest_path.read_bytes()
            manifest = _mapping(json.loads(manifest_bytes), "corpusManifest")
        except (OSError, json.JSONDecodeError) as error:
            raise LocalGridCalibrationError(
                "LOCAL_GRID_CALIBRATION_FILE_UNREADABLE",
                "Local profiles or corpus manifest cannot be read.",
            ) from error
        manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
        profile_set_version = document.get("profileSetVersion")
        if (
            document.get("schemaVersion") != 1
            or profile_set_version not in {PROFILE_SET_VERSION, COMPLETE_PROFILE_SET_VERSION}
            or document.get("basisVersion") != BASIS_VERSION
            or document.get("corpusManifestSha256") != manifest_sha
            or document.get("status") not in {"partial_review_required", "ready_for_heldout"}
            or document.get("trainingAllowed") is not False
        ):
            raise LocalGridCalibrationError(
                "LOCAL_GRID_CALIBRATION_PROFILE_SET_INVALID",
                "A matching non-training local profile set is required.",
            )
        contexts: dict[str, _SourceContext] = {}
        for index, raw in enumerate(_sequence(manifest.get("images"), "manifest.images")):
            item = _mapping(raw, f"manifest.images[{index}]")
            source = _sha256(item.get("sha256"), f"manifest.images[{index}].sha256")
            contexts[source] = _SourceContext(
                source_group=_text(
                    item.get("sourceGroup"),
                    f"manifest.images[{index}].sourceGroup",
                ),
                expected_board_count=_integer(
                    item.get("expectedBoardCount"),
                    f"manifest.images[{index}].expectedBoardCount",
                    minimum=1,
                ),
            )
        profiles: dict[str, LocalImageProfile] = {}
        for index, raw in enumerate(_sequence(document.get("profiles"), "profiles")):
            item = _mapping(raw, f"profiles[{index}]")
            source = _sha256(
                item.get("sourceImageChecksumSha256"),
                f"profiles[{index}].sourceImageChecksumSha256",
            )
            anchor = _mapping(item.get("anchor"), f"profiles[{index}].anchor")
            offsets = _offsets(
                anchor.get("localCornerOffsets"),
                f"profiles[{index}].anchor.localCornerOffsets",
            )
            local_base = _float_quad(
                anchor.get("localBaseQuad"),
                f"profiles[{index}].anchor.localBaseQuad",
            )
            accepted = _float_quad(
                anchor.get("acceptedSourceQuad"),
                f"profiles[{index}].anchor.acceptedSourceQuad",
            )
            if (
                source in profiles
                or source not in contexts
                or item.get("basisVersion") != BASIS_VERSION
                or item.get("profileVersion") != PROFILE_VERSION
                or item.get("profileId")
                != _profile_id(
                    source,
                    cast(str, profile_set_version),
                )
                or item.get("status") != "published"
                or item.get("sourceGroup") != contexts[source].source_group
                or local_corner_offsets(local_base, accepted) != offsets
            ):
                raise LocalGridCalibrationError(
                    "LOCAL_GRID_CALIBRATION_PROFILE_INVALID",
                    "A local source profile has invalid identity or geometry.",
                )
            profiles[source] = LocalImageProfile(
                profile_id=cast(str, item["profileId"]),
                source_checksum_sha256=source,
                source_group=contexts[source].source_group,
                anchor_sequence_number=_integer(
                    anchor.get("sequenceNumber"),
                    f"profiles[{index}].anchor.sequenceNumber",
                    minimum=1,
                ),
                anchor_board_position=_integer(
                    anchor.get("boardPosition"),
                    f"profiles[{index}].anchor.boardPosition",
                ),
                offsets=offsets,
            )
        if (
            document.get("profileCount") != len(profiles)
            or document.get("coveredSourceImageCount") != len(profiles)
            or document.get("sourceImageCount") != len(contexts)
            or sorted(set(contexts) - set(profiles))
            != list(
                _sequence(
                    document.get("missingSourceImageChecksums"),
                    "localProfiles.missingSourceImageChecksums",
                )
            )
        ):
            raise LocalGridCalibrationError(
                "LOCAL_GRID_CALIBRATION_PROFILE_SET_INVALID",
                "Local profile counters or missing-source list differ.",
            )
        return cls(
            profile_set_version=cast(str, profile_set_version),
            profile_set_sha256=hashlib.sha256(profile_bytes).hexdigest(),
            corpus_manifest_sha256=manifest_sha,
            detector_report_sha256=_sha256(
                document.get("detectorReportSha256"),
                "localProfiles.detectorReportSha256",
            ),
            profiles=profiles,
            source_contexts=contexts,
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
            raise LocalGridCalibrationError(
                "LOCAL_GRID_CALIBRATION_SOURCE_UNKNOWN",
                "The source image is absent from the corpus manifest.",
            )
        profile = self._profiles.get(source_checksum_sha256)
        if profile is None:
            return PageGeometry(
                status="needs_review",
                image_width=geometry.image_width,
                image_height=geometry.image_height,
                boards=(),
                review_reasons=(MISSING_PROFILE_REASON,),
            )
        if len(geometry.boards) != context.expected_board_count:
            raise LocalGridCalibrationError(
                "LOCAL_GRID_CALIBRATION_BOARD_COUNT_DRIFT",
                "Detected board count differs from the source-image contract.",
            )
        calibrated: list[BoardGeometry] = []
        for board in geometry.boards:
            if board.bounding_box is None:
                raise LocalGridCalibrationError(
                    "LOCAL_GRID_CALIBRATION_BOUNDING_BOX_MISSING",
                    "Every board requires its detector bounding frame.",
                )
            base = local_bounding_frame(board.bounding_box)
            calibrated.append(
                BoardGeometry(
                    position_index=board.position_index,
                    quad=apply_local_corner_offsets(base, profile.offsets),
                    bounding_box=board.bounding_box,
                    source_quad_source=SOURCE_QUAD_SOURCE,
                    calibration_profile_id=profile.profile_id,
                    calibration_profile_version=PROFILE_VERSION,
                    calibration_anchor_sequence_numbers=(profile.anchor_sequence_number,),
                    calibration_interpolation_weight=0.0,
                )
            )
        return PageGeometry(
            status="detected",
            image_width=geometry.image_width,
            image_height=geometry.image_height,
            boards=tuple(calibrated),
            review_reasons=(),
        )


def local_profile_document_bytes(document: Mapping[str, object]) -> bytes:
    return _json_bytes(document)


__all__ = [
    "BASIS_VERSION",
    "COMPLETE_PROFILE_SET_VERSION",
    "MISSING_PROFILE_REASON",
    "PROFILE_SET_VERSION",
    "PROFILE_VERSION",
    "SOURCE_QUAD_SOURCE",
    "LocalGridCalibrationError",
    "LocalImageGridCalibrationProfiles",
    "build_local_profile_document",
    "local_bounding_frame",
    "local_profile_document_bytes",
]
