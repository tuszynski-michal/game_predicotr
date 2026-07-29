"""Build the bounded sequence-29 diagnostic for projective lattice step 2."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import cast

import cv2
import numpy as np
from game_predictor_worker.images.geometry import Point
from game_predictor_worker.images.rectification import (
    BOARD_HEIGHT,
    BOARD_WIDTH,
    BoardGeometry,
    PageGeometry,
)
from game_predictor_worker.images.safe_context_crops import (
    PROJECTIVE_FRAME_PROFILE_SET_VERSION,
    ProjectiveExpandedFrameCalibrator,
)
from game_predictor_worker.images.symbol_grid_refinement import (
    MIN_CENTER_CONFIDENCE,
    rectify_board,
)
from game_predictor_worker.images.symbol_lattice_homography import (
    SymbolLatticeHomography,
    estimate_symbol_lattice_homography,
    project_points,
)
from numpy.typing import NDArray

SOURCE_RELATIVE_PATH = "5983122166590934320.jpg"
SEQUENCE_NUMBER = 29
DETECTOR_QUAD = (
    Point(402, 336),
    Point(652, 328),
    Point(645, 448),
    Point(410, 430),
)
DETECTOR_BOUNDING_BOX = (390, 310, 267, 145)
EXPECTED_EXPANDED_QUAD = (
    Point(386, 329),
    Point(679, 317),
    Point(669, 459),
    Point(396, 436),
)
DISPLAY_PADDING_PX = 28
PANEL_GAP_PX = 18
HEADER_HEIGHT_PX = 62


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _quad_to_dict(quad: tuple[Point, Point, Point, Point]) -> list[dict[str, int]]:
    return [point.to_dict() for point in quad]


def _draw_fixed_grid(board_rgb: NDArray[np.uint8]) -> NDArray[np.uint8]:
    panel = cv2.copyMakeBorder(
        board_rgb,
        DISPLAY_PADDING_PX,
        DISPLAY_PADDING_PX,
        DISPLAY_PADDING_PX,
        DISPLAY_PADDING_PX,
        cv2.BORDER_CONSTANT,
        value=(18, 13, 10),
    )
    for column in range(6):
        x = DISPLAY_PADDING_PX + column * 100
        cv2.line(
            panel,
            (x, DISPLAY_PADDING_PX),
            (x, DISPLAY_PADDING_PX + BOARD_HEIGHT),
            (45, 240, 95),
            2,
            cv2.LINE_AA,
        )
    for row in range(4):
        y = DISPLAY_PADDING_PX + row * 100
        cv2.line(
            panel,
            (DISPLAY_PADDING_PX, y),
            (DISPLAY_PADDING_PX + BOARD_WIDTH, y),
            (45, 240, 95),
            2,
            cv2.LINE_AA,
        )
    return cast(NDArray[np.uint8], panel)


def _draw_fitted_grid(
    board_rgb: NDArray[np.uint8],
    result: SymbolLatticeHomography,
) -> NDArray[np.uint8]:
    if result.ideal_to_observed_matrix is None:
        raise ValueError("Fitted homography matrix is required for the overlay.")
    panel = cv2.copyMakeBorder(
        board_rgb,
        DISPLAY_PADDING_PX,
        DISPLAY_PADDING_PX,
        DISPLAY_PADDING_PX,
        DISPLAY_PADDING_PX,
        cv2.BORDER_CONSTANT,
        value=(18, 13, 10),
    )
    for column in range(6):
        projected = project_points(
            np.asarray(
                (
                    (column * 100.0, 0.0),
                    (column * 100.0, float(BOARD_HEIGHT)),
                ),
                dtype=np.float64,
            ),
            result.ideal_to_observed_matrix,
        )
        start = tuple(int(round(value + DISPLAY_PADDING_PX)) for value in projected[0])
        end = tuple(int(round(value + DISPLAY_PADDING_PX)) for value in projected[1])
        cv2.line(panel, start, end, (40, 230, 245), 2, cv2.LINE_AA)
    for row in range(4):
        projected = project_points(
            np.asarray(
                (
                    (0.0, row * 100.0),
                    (float(BOARD_WIDTH), row * 100.0),
                ),
                dtype=np.float64,
            ),
            result.ideal_to_observed_matrix,
        )
        start = tuple(int(round(value + DISPLAY_PADDING_PX)) for value in projected[0])
        end = tuple(int(round(value + DISPLAY_PADDING_PX)) for value in projected[1])
        cv2.line(panel, start, end, (40, 230, 245), 2, cv2.LINE_AA)

    inlier_slots = set(result.inlier_slots)
    for center in result.centers:
        slot = (center.row_index, center.column_index)
        if slot in inlier_slots:
            colour = (45, 245, 80)
        elif center.confidence >= MIN_CENTER_CONFIDENCE:
            colour = (245, 65, 45)
        else:
            colour = (245, 190, 35)
        point = (
            int(round(center.x + DISPLAY_PADDING_PX)),
            int(round(center.y + DISPLAY_PADDING_PX)),
        )
        cv2.circle(panel, point, 6, colour, 2, cv2.LINE_AA)
    return cast(NDArray[np.uint8], panel)


def _diagnostic_card(
    board_rgb: NDArray[np.uint8],
    result: SymbolLatticeHomography,
) -> NDArray[np.uint8]:
    fixed = _draw_fixed_grid(board_rgb)
    fitted = _draw_fitted_grid(board_rgb, result)
    width = fixed.shape[1] + PANEL_GAP_PX + fitted.shape[1]
    height = HEADER_HEIGHT_PX + fixed.shape[0]
    card = np.full((height, width, 3), (18, 13, 10), dtype=np.uint8)
    card[HEADER_HEIGHT_PX:, : fixed.shape[1]] = fixed
    card[
        HEADER_HEIGHT_PX:,
        fixed.shape[1] + PANEL_GAP_PX :,
    ] = fitted
    cv2.putText(
        card,
        "seq 29 | provisional fixed grid",
        (18, 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        (235, 235, 235),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        card,
        "seq 29 | whole-lattice homography",
        (fixed.shape[1] + PANEL_GAP_PX + 18, 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.52,
        (235, 235, 235),
        1,
        cv2.LINE_AA,
    )
    metrics = (
        f"green=inlier red=outlier amber=low | {result.reliable_center_count}/15 "
        f"| inliers {result.inlier_count} | p95 "
        f"{result.inlier_p95_residual_px:.4f}px"
    )
    cv2.putText(
        card,
        metrics,
        (fixed.shape[1] + PANEL_GAP_PX + 18, 49),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.34,
        (80, 220, 250),
        1,
        cv2.LINE_AA,
    )
    return card


def _build(root: Path) -> tuple[bytes, dict[str, object]]:
    source_path = root / "examples" / "imgs" / SOURCE_RELATIVE_PATH
    source_bytes = source_path.resolve(strict=True).read_bytes()
    source_bgr = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
    if source_bgr is None:
        raise ValueError(f"Cannot read source image: {source_path}")
    source_rgb = cast(
        NDArray[np.uint8],
        cv2.cvtColor(source_bgr, cv2.COLOR_BGR2RGB),
    )
    geometry = PageGeometry(
        status="detected",
        image_width=int(source_rgb.shape[1]),
        image_height=int(source_rgb.shape[0]),
        boards=(
            BoardGeometry(
                position_index=0,
                quad=DETECTOR_QUAD,
                bounding_box=DETECTOR_BOUNDING_BOX,
            ),
        ),
    )
    calibrator = ProjectiveExpandedFrameCalibrator.from_files(
        root / "ai_docs" / "quality" / "m5-corpus-manifest.json",
        root / "ai_docs" / "quality" / "m5-page-board-detection-report.json",
    )
    expanded = calibrator.calibrate(_sha256(source_bytes), geometry)
    if expanded.status != "detected" or not expanded.boards:
        raise ValueError(f"Projective expansion failed: {expanded.review_reasons}")
    expanded_quad = expanded.boards[0].quad
    if expanded_quad != EXPECTED_EXPANDED_QUAD:
        raise ValueError(f"Sequence-29 expanded quad drifted: {expanded_quad}")
    board_rgb, _ = rectify_board(source_rgb, expanded_quad)
    result = estimate_symbol_lattice_homography(board_rgb)
    if result.status != "fitted":
        raise ValueError(f"Sequence-29 homography failed: {result.fallback_reason}")
    card = _diagnostic_card(board_rgb, result)
    encoded, png = cv2.imencode(
        ".png",
        cv2.cvtColor(card, cv2.COLOR_RGB2BGR),
    )
    if not encoded:
        raise ValueError("Cannot encode sequence-29 diagnostic PNG.")
    png_bytes = png.tobytes()
    report: dict[str, object] = {
        "artifact": {
            "relativePath": ("artifacts/m5-symbol-lattice-homography-v12-step2/seq-029.png"),
            "sha256": _sha256(png_bytes),
        },
        "detectorBoundingBox": {
            "height": DETECTOR_BOUNDING_BOX[3],
            "width": DETECTOR_BOUNDING_BOX[2],
            "x": DETECTOR_BOUNDING_BOX[0],
            "y": DETECTOR_BOUNDING_BOX[1],
        },
        "detectorQuad": _quad_to_dict(DETECTOR_QUAD),
        "fullCorpusGenerated": False,
        "homography": result.to_dict(),
        "numpyVersion": np.__version__,
        "opencvVersion": cv2.__version__,
        "productionCellsGenerated": False,
        "projectiveExpandedQuad": _quad_to_dict(expanded_quad),
        "projectiveFrameProfileVersion": PROJECTIVE_FRAME_PROFILE_SET_VERSION,
        "schemaVersion": "m5-symbol-lattice-homography-step2-report-v1",
        "sequenceNumber": SEQUENCE_NUMBER,
        "sourceImageRelativePath": SOURCE_RELATIVE_PATH,
        "sourceImageSha256": _sha256(source_bytes),
        "status": "passed",
        "trainingAllowed": False,
    }
    return png_bytes, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify that committed diagnostic bytes are reproducible.",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    artifact_path = root / "artifacts" / "m5-symbol-lattice-homography-v12-step2" / "seq-029.png"
    report_path = (
        root / "ai_docs" / "quality" / "m5-symbol-lattice-homography-v12-step2-report.json"
    )
    png_bytes, report = _build(root)
    report_bytes = (
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode()
    if args.check:
        if artifact_path.read_bytes() != png_bytes:
            raise ValueError("Sequence-29 diagnostic PNG is not reproducible.")
        if report_path.read_bytes() != report_bytes:
            raise ValueError("Sequence-29 homography report is not reproducible.")
        print("Sequence-29 step-2 diagnostic is reproducible.")
        return 0
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(png_bytes)
    report_path.write_bytes(report_bytes)
    print(f"Wrote {artifact_path}")
    print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
