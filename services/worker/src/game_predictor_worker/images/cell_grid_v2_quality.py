"""Independent quality evaluation for detector-driven board-cell-crops-v2."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, cast

import numpy as np
from PIL import Image, UnidentifiedImageError

from .cell_grid_golden import CellGridGoldenReview
from .grid_calibration import (
    PROFILE_SET_VERSION,
    SOURCE_QUAD_SOURCE,
    GridCalibrationProfiles,
)
from .grid_quality import metric_summary, project_points, quad_to_canonical_matrix
from .rectification import (
    BOARD_COLUMNS,
    BOARD_HEIGHT,
    BOARD_ROWS,
    BOARD_WIDTH,
    CALIBRATED_CROPPER_VERSION,
    CELL_HEIGHT,
    CELL_WIDTH,
    V2_CROPPER_VERSION,
    V2_GRID_CONTRACT,
)

QUALITY_REPORT_VERSION = "board-cell-crops-v2-quality-v1"
CALIBRATED_QUALITY_REPORT_VERSION = "board-cell-crops-v2-calibrated-quality-v1"
LINE_ERROR_BUDGET_P95_PX = 5.0
EXPECTED_INTERNAL_VERTICAL_LINES = (100.0, 200.0, 300.0, 400.0)
EXPECTED_INTERNAL_HORIZONTAL_LINES = (100.0, 200.0)
Point = tuple[float, float]
Quad = tuple[Point, Point, Point, Point]


class CellGridV2QualityError(ValueError):
    """Stable quality-report failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CellGridV2QualityError(
            "CELL_GRID_V2_REPORT_INVALID",
            f"{label} must be an object.",
        )
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise CellGridV2QualityError(
            "CELL_GRID_V2_REPORT_INVALID",
            f"{label} must be an array.",
        )
    return cast(Sequence[object], value)


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise CellGridV2QualityError(
            "CELL_GRID_V2_REPORT_INVALID",
            f"{label} must be an integer.",
        )
    return value


def _sha256(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise CellGridV2QualityError(
            "CELL_GRID_V2_REPORT_INVALID",
            f"{label} must be a lowercase SHA-256.",
        )
    return value


def _quad(value: object, label: str) -> Quad:
    points = _sequence(value, label)
    if len(points) != 4:
        raise CellGridV2QualityError(
            "CELL_GRID_V2_REPORT_INVALID",
            f"{label} must contain four points.",
        )
    parsed: list[Point] = []
    for index, raw in enumerate(points):
        point = _mapping(raw, f"{label}[{index}]")
        x = point.get("x")
        y = point.get("y")
        if (
            not isinstance(x, int | float)
            or isinstance(x, bool)
            or not isinstance(y, int | float)
            or isinstance(y, bool)
            or not math.isfinite(float(x))
            or not math.isfinite(float(y))
        ):
            raise CellGridV2QualityError(
                "CELL_GRID_V2_REPORT_INVALID",
                f"{label}[{index}] must contain finite coordinates.",
            )
        parsed.append((float(x), float(y)))
    return cast(Quad, tuple(parsed))


def _load_json(path: Path, label: str) -> tuple[bytes, Mapping[str, object]]:
    try:
        content = path.read_bytes()
        value: Any = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise CellGridV2QualityError(
            "CELL_GRID_V2_REPORT_UNREADABLE",
            f"{label} cannot be read.",
        ) from error
    return content, _mapping(value, label)


def _artifact_path(
    root: Path,
    value: object,
    label: str,
    *,
    namespace: str,
) -> Path:
    if not isinstance(value, str):
        raise CellGridV2QualityError(
            "CELL_GRID_V2_REPORT_INVALID",
            f"{label} must be a relative path.",
        )
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or relative.parts[0] != namespace
    ):
        raise CellGridV2QualityError(
            "CELL_GRID_V2_ARTIFACT_PATH_INVALID",
            f"{label} must stay in the expected artifact namespace.",
        )
    try:
        path = (root / Path(*relative.parts)).resolve(strict=True)
    except OSError as error:
        raise CellGridV2QualityError(
            "CELL_GRID_V2_ARTIFACT_MISSING",
            f"{label} cannot be resolved.",
        ) from error
    if not path.is_relative_to(root):
        raise CellGridV2QualityError(
            "CELL_GRID_V2_ARTIFACT_PATH_INVALID",
            f"{label} escapes the artifact root.",
        )
    return path


def _verify_png(
    root: Path,
    artifact: Mapping[str, object],
    *,
    path_field: str,
    checksum_field: str,
    width: int,
    height: int,
    label: str,
    namespace: str,
) -> None:
    path = _artifact_path(
        root,
        artifact.get(path_field),
        f"{label}.{path_field}",
        namespace=namespace,
    )
    expected_checksum = _sha256(
        artifact.get(checksum_field),
        f"{label}.{checksum_field}",
    )
    try:
        content = path.read_bytes()
        with Image.open(path) as image:
            image.load()
            valid = image.format == "PNG" and image.mode == "RGB" and image.size == (width, height)
    except (OSError, UnidentifiedImageError) as error:
        raise CellGridV2QualityError(
            "CELL_GRID_V2_ARTIFACT_INVALID",
            f"{label} is not a readable RGB PNG.",
        ) from error
    if hashlib.sha256(content).hexdigest() != expected_checksum or not valid:
        raise CellGridV2QualityError(
            "CELL_GRID_V2_ARTIFACT_DRIFT",
            f"{label} differs from its report.",
        )


def _json_bytes(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()


def _build_quality_report(
    review: CellGridGoldenReview,
    *,
    crop_report_path: Path,
    crop_root: Path,
    expected_cropper_version: str,
    expected_source_quad_source: str,
    quality_report_version: str,
    profiles: GridCalibrationProfiles | None,
    passed_next_task: str | None,
) -> dict[str, object]:
    """Measure one v2 rectification variant against accepted source quads."""

    golden = review.golden
    if any(entry.review_status != "accepted" for entry in golden.entries):
        raise CellGridV2QualityError(
            "CELL_GRID_V2_GOLDEN_INCOMPLETE",
            "Every golden entry must be accepted before v2 evaluation.",
        )
    crop_bytes, crop_report = _load_json(crop_report_path, "cropReport")
    if (
        crop_report.get("schemaVersion") != 1
        or crop_report.get("cropperVersion") != expected_cropper_version
        or crop_report.get("status") != "cropped"
        or crop_report.get("needsReviewCount") != 0
    ):
        raise CellGridV2QualityError(
            "CELL_GRID_V2_CROP_REPORT_NOT_READY",
            "A complete board-cell-crops-v2 report is required.",
        )
    if profiles is not None and (
        crop_report.get("calibrationProfileSetVersion") != PROFILE_SET_VERSION
        or crop_report.get("calibrationProfileSetSha256")
        != profiles.profile_set_sha256
        or crop_report.get("corpusManifestSha256")
        != profiles.corpus_manifest_sha256
        or crop_report.get("detectionReportSha256")
        != profiles.detection_report_sha256
    ):
        raise CellGridV2QualityError(
            "CELL_GRID_V2_CALIBRATION_PROFILE_DRIFT",
            "The calibrated crop report does not match its published profile set.",
        )
    try:
        artifact_root = crop_root.resolve(strict=True)
    except OSError as error:
        raise CellGridV2QualityError(
            "CELL_GRID_V2_ARTIFACT_ROOT_MISSING",
            "The v2 artifact root does not exist.",
        ) from error
    if not artifact_root.is_dir():
        raise CellGridV2QualityError(
            "CELL_GRID_V2_ARTIFACT_ROOT_INVALID",
            "The v2 artifact root must be a directory.",
        )

    images_by_source: dict[str, Mapping[str, object]] = {}
    actual_board_count = 0
    actual_cell_count = 0
    for image_index, value in enumerate(_sequence(crop_report.get("images"), "cropReport.images")):
        image = _mapping(value, f"cropReport.images[{image_index}]")
        source_checksum = _sha256(
            image.get("sourceChecksumSha256"),
            f"cropReport.images[{image_index}].sourceChecksumSha256",
        )
        if source_checksum in images_by_source or image.get("status") != "cropped":
            raise CellGridV2QualityError(
                "CELL_GRID_V2_CROP_REPORT_INVALID",
                "Every source must occur once with status cropped.",
            )
        boards = _sequence(image.get("boards"), f"cropReport.images[{image_index}].boards")
        actual_board_count += len(boards)
        for board_index, board_value in enumerate(boards):
            board = _mapping(
                board_value,
                f"cropReport.images[{image_index}].boards[{board_index}]",
            )
            actual_cell_count += len(_sequence(board.get("cells"), "board.cells"))
        images_by_source[source_checksum] = image
    if (
        _integer(crop_report.get("imageCount"), "cropReport.imageCount") != len(images_by_source)
        or _integer(crop_report.get("boardCount"), "cropReport.boardCount") != actual_board_count
        or _integer(crop_report.get("cellCount"), "cropReport.cellCount") != actual_cell_count
    ):
        raise CellGridV2QualityError(
            "CELL_GRID_V2_CROP_REPORT_INVALID",
            "Declared corpus counters differ from report contents.",
        )

    line_errors: list[dict[str, object]] = []
    quad_errors: list[dict[str, object]] = []
    all_line_values: list[float] = []
    all_corner_values: list[float] = []
    by_axis: dict[str, list[float]] = {"horizontal": [], "vertical": []}
    by_position: dict[int, list[float]] = {position: [] for position in range(9)}
    by_source: dict[str, list[float]] = {source_group: [] for source_group in golden.source_groups}
    verified_cells = 0
    for entry in golden.entries:
        candidate = entry.candidate
        golden_image = images_by_source.get(candidate.source_image_checksum_sha256)
        if golden_image is None:
            raise CellGridV2QualityError(
                "CELL_GRID_V2_GOLDEN_BOARD_MISSING",
                "A golden source is missing from the v2 crop report.",
            )
        boards = _sequence(golden_image.get("boards"), "crop image boards")
        matching = [
            _mapping(board, "crop board")
            for board in boards
            if _mapping(board, "crop board").get("positionIndex") == candidate.board_position
        ]
        if len(matching) != 1:
            raise CellGridV2QualityError(
                "CELL_GRID_V2_GOLDEN_BOARD_MISSING",
                "A golden board position is missing or duplicated.",
            )
        board = matching[0]
        if board.get("sourceQuadSource") != expected_source_quad_source:
            raise CellGridV2QualityError(
                "CELL_GRID_V2_EVALUATION_CIRCULAR",
                "The evaluated corpus uses an unexpected source-quad provenance.",
            )
        actual_quad = _quad(board.get("sourceQuad"), "crop board sourceQuad")
        if profiles is None:
            if actual_quad != candidate.detected_source_quad:
                raise CellGridV2QualityError(
                    "CELL_GRID_V2_SOURCE_QUAD_DRIFT",
                    "The v2 board quad differs from the detector suggestion.",
                )
        else:
            application = profiles.apply(
                source_group=candidate.source_group,
                board_position=candidate.board_position,
                sequence_number=candidate.sequence_number,
                detected_quad=candidate.detected_source_quad,
            )
            expected_quad = cast(
                Quad,
                tuple(
                    (float(point.x), float(point.y))
                    for point in application.calibrated_quad
                ),
            )
            if actual_quad != expected_quad:
                raise CellGridV2QualityError(
                    "CELL_GRID_V2_CALIBRATED_QUAD_DRIFT",
                    "The board quad differs from the published calibration profile.",
                )
            calibration = _mapping(
                board.get("calibrationProfile"),
                "crop board calibrationProfile",
            )
            if calibration != {
                "anchorSequenceNumbers": list(application.anchor_sequence_numbers),
                "interpolationWeight": application.interpolation_weight,
                "profileId": application.profile_id,
                "profileVersion": 1,
            }:
                raise CellGridV2QualityError(
                    "CELL_GRID_V2_CALIBRATION_PROVENANCE_DRIFT",
                    "Board calibration provenance differs from the published profile.",
                )
        if board.get("grid") != V2_GRID_CONTRACT.to_dict():
            raise CellGridV2QualityError(
                "CELL_GRID_V2_GRID_CONTRACT_INVALID",
                "The v2 board does not use the accepted logical-slot contract.",
            )
        _verify_png(
            artifact_root,
            board,
            path_field="boardRelativePath",
            checksum_field="boardChecksumSha256",
            width=BOARD_WIDTH,
            height=BOARD_HEIGHT,
            label="board",
            namespace=expected_cropper_version,
        )
        _verify_png(
            artifact_root,
            board,
            path_field="overlayRelativePath",
            checksum_field="overlayChecksumSha256",
            width=BOARD_WIDTH,
            height=BOARD_HEIGHT,
            label="overlay",
            namespace=expected_cropper_version,
        )
        cells = _sequence(board.get("cells"), "board.cells")
        expected_locations = [
            (row, column) for row in range(BOARD_ROWS) for column in range(BOARD_COLUMNS)
        ]
        locations = [
            (
                _integer(_mapping(cell, "cell").get("rowIndex"), "cell.rowIndex"),
                _integer(
                    _mapping(cell, "cell").get("columnIndex"),
                    "cell.columnIndex",
                ),
            )
            for cell in cells
        ]
        if locations != expected_locations:
            raise CellGridV2QualityError(
                "CELL_GRID_V2_CELL_ORDER_INVALID",
                "The v2 cells must contain exactly one row-major 3 × 5 grid.",
            )
        for cell_index, value in enumerate(cells):
            cell = _mapping(value, f"board.cells[{cell_index}]")
            if cell.get("width") != CELL_WIDTH or cell.get("height") != CELL_HEIGHT:
                raise CellGridV2QualityError(
                    "CELL_GRID_V2_CELL_DIMENSIONS_INVALID",
                    "Every v2 cell must be RGB 90 × 90.",
                )
            _verify_png(
                artifact_root,
                cell,
                path_field="relativePath",
                checksum_field="checksumSha256",
                width=CELL_WIDTH,
                height=CELL_HEIGHT,
                label=f"cell[{cell_index}]",
                namespace=expected_cropper_version,
            )
            verified_cells += 1

        actual_matrix = quad_to_canonical_matrix(
            actual_quad,
            board_width=BOARD_WIDTH,
            board_height=BOARD_HEIGHT,
        )
        golden_matrix = quad_to_canonical_matrix(
            entry.source_quad,
            board_width=BOARD_WIDTH,
            board_height=BOARD_HEIGHT,
        )
        correction = golden_matrix @ np.linalg.inv(actual_matrix)
        for corner_index, (actual, expected) in enumerate(
            zip(actual_quad, entry.source_quad, strict=True)
        ):
            corner_error = round(math.dist(actual, expected), 4)
            all_corner_values.append(corner_error)
            quad_error: dict[str, object] = {
                "absoluteErrorPx": corner_error,
                "boardPosition": candidate.board_position,
                "cornerIndex": corner_index,
                "expectedPoint": {"x": expected[0], "y": expected[1]},
                "observationId": candidate.observation_id,
                "sequenceNumber": candidate.sequence_number,
                "sourceGroup": candidate.source_group,
            }
            quad_error[
                "detectedPoint" if profiles is None else "calibratedPoint"
            ] = {"x": actual[0], "y": actual[1]}
            quad_errors.append(quad_error)
        for axis, coordinates in (
            ("vertical", EXPECTED_INTERNAL_VERTICAL_LINES),
            ("horizontal", EXPECTED_INTERNAL_HORIZONTAL_LINES),
        ):
            for line_index, coordinate in enumerate(coordinates):
                endpoints: tuple[Point, Point] = (
                    (
                        (coordinate, 0.0),
                        (coordinate, float(BOARD_HEIGHT - 1)),
                    )
                    if axis == "vertical"
                    else (
                        (0.0, coordinate),
                        (float(BOARD_WIDTH - 1), coordinate),
                    )
                )
                projected = project_points(endpoints, correction)
                coordinate_index = 0 if axis == "vertical" else 1
                endpoint_errors = tuple(
                    round(abs(point[coordinate_index] - coordinate), 4) for point in projected
                )
                line_error = round(sum(endpoint_errors) / 2, 4)
                all_line_values.append(line_error)
                by_axis[axis].append(line_error)
                by_position[candidate.board_position].append(line_error)
                by_source[candidate.source_group].append(line_error)
                line_errors.append(
                    {
                        "absoluteErrorPx": line_error,
                        "axis": axis,
                        "boardPosition": candidate.board_position,
                        "endpointAbsoluteErrorsPx": list(endpoint_errors),
                        "expectedCoordinate": coordinate,
                        "lineIndex": line_index,
                        "observationId": candidate.observation_id,
                        "projectedEndpoints": [
                            {"x": point[0], "y": point[1]} for point in projected
                        ],
                        "sequenceNumber": candidate.sequence_number,
                        "sourceGroup": candidate.source_group,
                        "v2Coordinate": coordinate,
                    }
                )

    overall = metric_summary(all_line_values)
    p95 = cast(float, overall["p95AbsoluteErrorPx"])
    training_allowed = p95 <= LINE_ERROR_BUDGET_P95_PX
    golden_bytes = golden.to_json_bytes()
    result: dict[str, object] = {
        "artifactVerification": {
            "verifiedBoardCount": len(golden.entries),
            "verifiedCellCount": verified_cells,
        },
        "cropReportSha256": hashlib.sha256(crop_bytes).hexdigest(),
        "cropperVersion": expected_cropper_version,
        "fullCorpus": {
            "boardCount": actual_board_count,
            "cellCount": actual_cell_count,
            "imageCount": len(images_by_source),
        },
        "goldenAcceptedEntryCount": len(golden.entries),
        "goldenSha256": hashlib.sha256(golden_bytes).hexdigest(),
        "goldenVersion": golden.to_dict()["goldenVersion"],
        "lineErrorBudgetP95Px": LINE_ERROR_BUDGET_P95_PX,
        "lineErrors": line_errors,
        "nextTask": passed_next_task if training_allowed else "TASK-0096",
        "percentileMethod": "linear-r7",
        "qualityReportVersion": quality_report_version,
        "quadErrors": quad_errors,
        "schemaVersion": 1,
        "status": "passed" if training_allowed else "quarantined_calibration_required",
        "summary": {
            "byAxis": [
                {"axis": axis, **metric_summary(values)} for axis, values in sorted(by_axis.items())
            ],
            "byBoardPosition": [
                {
                    "boardPosition": position,
                    **metric_summary(by_position[position]),
                }
                for position in range(9)
            ],
            "bySourceGroup": [
                {
                    "sourceGroup": source_group,
                    **metric_summary(by_source[source_group]),
                }
                for source_group in golden.source_groups
            ],
            "overall": overall,
            "quadCornersOverall": metric_summary(all_corner_values),
        },
        "trainingAllowed": training_allowed,
    }
    if profiles is not None:
        result["calibrationProfileSetSha256"] = profiles.profile_set_sha256
        result["calibrationProfileSetVersion"] = profiles.profile_set_version
    return result


def build_v2_quality_report(
    review: CellGridGoldenReview,
    *,
    crop_report_path: Path,
    crop_root: Path,
) -> dict[str, object]:
    """Measure detector-driven v2 against accepted source quads."""

    return _build_quality_report(
        review,
        crop_report_path=crop_report_path,
        crop_root=crop_root,
        expected_cropper_version=V2_CROPPER_VERSION,
        expected_source_quad_source="detector",
        quality_report_version=QUALITY_REPORT_VERSION,
        profiles=None,
        passed_next_task=None,
    )


def build_calibrated_quality_report(
    review: CellGridGoldenReview,
    *,
    crop_report_path: Path,
    crop_root: Path,
    profiles: GridCalibrationProfiles,
) -> dict[str, object]:
    """Measure profile-calibrated v2 artifacts against accepted source quads."""

    return _build_quality_report(
        review,
        crop_report_path=crop_report_path,
        crop_root=crop_root,
        expected_cropper_version=CALIBRATED_CROPPER_VERSION,
        expected_source_quad_source=SOURCE_QUAD_SOURCE,
        quality_report_version=CALIBRATED_QUALITY_REPORT_VERSION,
        profiles=profiles,
        passed_next_task="TASK-0097",
    )


def v2_quality_report_bytes(
    review: CellGridGoldenReview,
    *,
    crop_report_path: Path,
    crop_root: Path,
) -> bytes:
    return _json_bytes(
        build_v2_quality_report(
            review,
            crop_report_path=crop_report_path,
            crop_root=crop_root,
        )
    )


def calibrated_quality_report_bytes(
    review: CellGridGoldenReview,
    *,
    crop_report_path: Path,
    crop_root: Path,
    profiles: GridCalibrationProfiles,
) -> bytes:
    return _json_bytes(
        build_calibrated_quality_report(
            review,
            crop_report_path=crop_report_path,
            crop_root=crop_root,
            profiles=profiles,
        )
    )


__all__ = [
    "LINE_ERROR_BUDGET_P95_PX",
    "QUALITY_REPORT_VERSION",
    "CALIBRATED_QUALITY_REPORT_VERSION",
    "CellGridV2QualityError",
    "build_calibrated_quality_report",
    "build_v2_quality_report",
    "calibrated_quality_report_bytes",
    "v2_quality_report_bytes",
]
