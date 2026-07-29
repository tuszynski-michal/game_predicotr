"""Build bounded and full projective fixed-padding preflight gates."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast

import cv2
import numpy as np
from numpy.typing import NDArray

ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.images.geometry import Point, Quad  # noqa: E402
from game_predictor_worker.images.projective_lattice_crops import (  # noqa: E402
    CROPPER_VERSION,
    FIXED_PADDING_PX,
    ProjectiveLatticeCropResult,
    build_projective_lattice_crops,
)
from game_predictor_worker.images.rectification import (  # noqa: E402
    BOARD_COLUMNS,
    BOARD_ROWS,
    BoardGeometry,
    PageGeometry,
)
from game_predictor_worker.images.safe_context_crops import (  # noqa: E402
    PROJECTIVE_FRAME_PROFILE_SET_VERSION,
    ProjectiveExpandedFrameCalibrator,
)
from game_predictor_worker.images.source_projective_lattice_crops import (  # noqa: E402
    BOUNDING_FALLBACK_CROPPER_VERSION,
    BOUNDING_FALLBACK_GRID_VERSION,
    REVIEWED_SOURCE_QUAD_CROPPER_VERSION,
    REVIEWED_SOURCE_QUAD_GRID_VERSION,
    REVIEWED_SOURCE_QUAD_HOMOGRAPHY_VERSION,
    SourceProjectiveLatticeCropResult,
    build_bounding_fallback_source_projective_lattice_crops,
    build_reviewed_source_quad_crops,
    build_source_projective_lattice_crops,
)
from game_predictor_worker.images.source_projective_lattice_crops import (  # noqa: E402
    CROPPER_VERSION as SOURCE_AWARE_CROPPER_VERSION,
)
from game_predictor_worker.images.source_projective_lattice_crops import (  # noqa: E402
    GRID_VERSION as SOURCE_AWARE_GRID_VERSION,
)
from game_predictor_worker.images.symbol_grid_refinement import (  # noqa: E402
    rectify_board,
)
from game_predictor_worker.images.symbol_lattice_homography import (  # noqa: E402
    GLOBAL_HOMOGRAPHY_VERSION,
    HOMOGRAPHY_VERSION,
)
from game_predictor_worker.images.v14_projective_overrides import (  # noqa: E402
    ReviewedV14ProjectiveOverrides,
    V14ProjectiveOverrideError,
)

DEFAULT_MANIFEST = ROOT / "ai_docs" / "quality" / "m5-corpus-manifest.json"
DEFAULT_DETECTION_REPORT = ROOT / "ai_docs" / "quality" / "m5-page-board-detection-report.json"
DEFAULT_V7_REPORT = (
    ROOT / "ai_docs" / "quality" / "m5-board-cell-crops-v7-reviewed-symbol-aware-report.json"
)
DEFAULT_CONTROLS = ROOT / "ai_docs" / "quality" / "m5-v4-round1-clean-control-sequences.json"
DEFAULT_NORMALIZATION_ROOT = ROOT / "artifacts" / "m5-normalization"
DEFAULT_CROP_ROOT = ROOT / "artifacts" / "m5-board-crops"
DEFAULT_ARTIFACT_ROOT = ROOT / "artifacts" / "m5-projective-fixed-padding-v12-regression"
DEFAULT_REPORT_ROOT = ROOT / "ai_docs" / "quality"
DEFAULT_FULL_V14_REPORT = (
    DEFAULT_REPORT_ROOT / "m5-global-bbox-fallback-v14-full-preflight-report.json"
)
DEFAULT_FULL_V14_ARTIFACT_ROOT = ROOT / "artifacts" / "m5-global-bbox-fallback-v14-full-preflight"
DEFAULT_V14_REVIEW = (
    ROOT / "artifacts" / "m5-v14-projective-fallback-review" / "reviewed-geometry.json"
)
PRIMARY_SEQUENCE = 29
REPORTED_FAILURE_SEQUENCES = (4, 6, 7, 26, 30)
V7_NAMESPACE = "board-cell-crops-v7-reviewed-symbol-aware-affine-v1"
PANEL_WIDTH = 500
PANEL_HEIGHT = 300
HEADER_HEIGHT = 48
Phase = Literal["seq29", "bounded", "full", "failures"]
REVIEWED_MERGE_CROPPER_VERSION = "board-cell-crops-v16-reviewed-v14-merge-v1"
REVIEWED_MERGE_GRID_VERSION = "reviewed-source-quad-plus-immutable-v14-grid-v1"
Candidate = Literal["v12", "v13-source", "v14-bbox", "v16-reviewed"]


class RegressionGateError(ValueError):
    """Stable input or provenance error for the bounded regression gate."""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RegressionGateError(f"{label} must be an object.")
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise RegressionGateError(f"{label} must be an array.")
    return cast(Sequence[object], value)


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise RegressionGateError(f"{label} must be an integer.")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise RegressionGateError(f"{label} must be non-empty text.")
    return value


def _load_json(path: Path) -> Mapping[str, object]:
    try:
        value: Any = json.loads(path.resolve(strict=True).read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise RegressionGateError(f"Cannot load {path}.") from error
    return _mapping(value, path.name)


def _safe_artifact_path(
    root: Path,
    relative_value: object,
    *,
    namespace: str,
    label: str,
) -> Path:
    relative = PurePosixPath(_text(relative_value, label))
    if relative.is_absolute() or not relative.parts or relative.parts[0] != namespace:
        raise RegressionGateError(f"{label} is outside {namespace}.")
    path = (root / Path(*relative.parts)).resolve(strict=True)
    if not path.is_relative_to(root):
        raise RegressionGateError(f"{label} escapes its artifact root.")
    return path


def _decode_rgb(path: Path) -> NDArray[np.uint8]:
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise RegressionGateError(f"Cannot decode {path}.")
    return cast(NDArray[np.uint8], cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def _encode_png(rgb: NDArray[np.uint8]) -> bytes:
    encoded, buffer = cv2.imencode(
        ".png",
        cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
        [cv2.IMWRITE_PNG_COMPRESSION, 6],
    )
    if not encoded:
        raise RegressionGateError("Cannot encode a regression card.")
    return bytes(buffer)


def _point(raw: object, label: str) -> Point:
    value = _mapping(raw, label)
    return Point(
        x=_integer(value.get("x"), f"{label}.x"),
        y=_integer(value.get("y"), f"{label}.y"),
    )


def _quad(raw: object, label: str) -> Quad:
    values = _sequence(raw, label)
    if len(values) != 4:
        raise RegressionGateError(f"{label} must contain four points.")
    return cast(
        Quad,
        tuple(_point(value, f"{label}[{index}]") for index, value in enumerate(values)),
    )


def _bounding_box(raw: object, label: str) -> tuple[int, int, int, int]:
    value = _mapping(raw, label)
    return (
        _integer(value.get("x"), f"{label}.x"),
        _integer(value.get("y"), f"{label}.y"),
        _integer(value.get("width"), f"{label}.width"),
        _integer(value.get("height"), f"{label}.height"),
    )


def _cell_sheet(cells: Sequence[NDArray[np.uint8]]) -> NDArray[np.uint8]:
    if len(cells) != BOARD_ROWS * BOARD_COLUMNS:
        return _placeholder("No 15-cell result")
    bordered: list[NDArray[np.uint8]] = []
    for cell in cells:
        bordered.append(
            cast(
                NDArray[np.uint8],
                cv2.copyMakeBorder(
                    cell,
                    2,
                    2,
                    2,
                    2,
                    cv2.BORDER_CONSTANT,
                    value=(30, 225, 90),
                ),
            )
        )
    rows = [
        np.concatenate(
            bordered[row * BOARD_COLUMNS : (row + 1) * BOARD_COLUMNS],
            axis=1,
        )
        for row in range(BOARD_ROWS)
    ]
    sheet = cast(NDArray[np.uint8], np.concatenate(rows, axis=0))
    return cast(
        NDArray[np.uint8],
        cv2.resize(
            sheet,
            (PANEL_WIDTH, PANEL_HEIGHT),
            interpolation=cv2.INTER_NEAREST,
        ),
    )


def _placeholder(message: str) -> NDArray[np.uint8]:
    panel = np.full((PANEL_HEIGHT, PANEL_WIDTH, 3), (22, 14, 12), dtype=np.uint8)
    cv2.putText(
        panel,
        message[:58],
        (18, PANEL_HEIGHT // 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (245, 95, 70),
        1,
        cv2.LINE_AA,
    )
    return panel


def _card(
    baseline_cells: Sequence[NDArray[np.uint8]],
    result: ProjectiveLatticeCropResult | SourceProjectiveLatticeCropResult,
    *,
    sequence_number: int,
    group: str,
) -> bytes:
    panels = [
        _cell_sheet(baseline_cells),
        result.observed_overlay_rgb,
        (
            result.grid_overlay_rgb
            if result.grid_overlay_rgb is not None
            else _placeholder(result.fallback_reason or "No rectified grid")
        ),
        (
            _cell_sheet([cell.rgb for cell in result.cells])
            if result.status == "cropped"
            else _placeholder(result.fallback_reason or "No fixed-padding cells")
        ),
    ]
    header = np.full(
        (HEADER_HEIGHT, PANEL_WIDTH * len(panels), 3),
        (7, 14, 22),
        dtype=np.uint8,
    )
    labels = (
        f"seq {sequence_number} | {group} | historical v7",
        "expanded projective frame + fitted lattice",
        f"homography rectified | padding {FIXED_PADDING_PX}px",
        (
            "15 fixed-padding crops | 100% source support"
            if result.status == "cropped"
            else f"FAIL-CLOSED | {result.fallback_reason}"
        ),
    )
    for index, label in enumerate(labels):
        cv2.putText(
            header,
            label[:64],
            (index * PANEL_WIDTH + 12, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.50,
            (235, 247, 255),
            1,
            cv2.LINE_AA,
        )
    combined = cast(
        NDArray[np.uint8],
        np.concatenate((header, np.concatenate(panels, axis=1)), axis=0),
    )
    return _encode_png(combined)


def _full_card(
    result: SourceProjectiveLatticeCropResult,
    *,
    sequence_number: int,
) -> bytes:
    panel = (
        _cell_sheet([cell.rgb for cell in result.cells])
        if result.status == "cropped"
        else _placeholder(result.fallback_reason or "No fixed-padding cells")
    )
    header = np.full(
        (HEADER_HEIGHT, PANEL_WIDTH, 3),
        (7, 14, 22),
        dtype=np.uint8,
    )
    frame = (
        "bbox retry"
        if result.analysis_frame_source == "detector-bounding-box-fallback"
        else (
            "manual override"
            if result.analysis_frame_source == "human-reviewed-source-quad"
            else "projective"
        )
    )
    label = (
        f"seq {sequence_number} | {frame} | 15 cells | support 100%"
        if result.status == "cropped"
        else f"seq {sequence_number} | FAIL-CLOSED | {result.fallback_reason}"
    )
    cv2.putText(
        header,
        label[:70],
        (12, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.50,
        (235, 247, 255),
        1,
        cv2.LINE_AA,
    )
    return _encode_png(
        cast(
            NDArray[np.uint8],
            np.concatenate((header, panel), axis=0),
        )
    )


def _full_failure_card(*, sequence_number: int, reason: str) -> bytes:
    panel = _placeholder(reason)
    header = np.full(
        (HEADER_HEIGHT, PANEL_WIDTH, 3),
        (7, 14, 22),
        dtype=np.uint8,
    )
    cv2.putText(
        header,
        f"seq {sequence_number} | FAIL-CLOSED | {reason}"[:70],
        (12, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.50,
        (235, 247, 255),
        1,
        cv2.LINE_AA,
    )
    return _encode_png(
        cast(
            NDArray[np.uint8],
            np.concatenate((header, panel), axis=0),
        )
    )


def _expansion_failure_card(
    baseline_cells: Sequence[NDArray[np.uint8]],
    detector_board_rgb: NDArray[np.uint8],
    *,
    sequence_number: int,
    reason: str,
) -> bytes:
    panels = [
        _cell_sheet(baseline_cells),
        detector_board_rgb,
        _placeholder(reason),
        _placeholder("No v14 cells"),
    ]
    header = np.full(
        (HEADER_HEIGHT, PANEL_WIDTH * len(panels), 3),
        (7, 14, 22),
        dtype=np.uint8,
    )
    labels = (
        f"seq {sequence_number} | full_failure | historical v7",
        "raw detector quad | diagnostic only",
        f"FAIL-CLOSED | {reason}",
        "no v14 fixed-padding result",
    )
    for index, label in enumerate(labels):
        cv2.putText(
            header,
            label[:64],
            (index * PANEL_WIDTH + 12, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.50,
            (235, 247, 255),
            1,
            cv2.LINE_AA,
        )
    return _encode_png(
        cast(
            NDArray[np.uint8],
            np.concatenate((header, np.concatenate(panels, axis=1)), axis=0),
        )
    )


def _write_or_check(path: Path, content: bytes, *, check: bool) -> None:
    if check:
        if path.resolve(strict=True).read_bytes() != content:
            raise RegressionGateError(f"Artifact is not reproducible: {path}")
        return
    if path.exists() and path.read_bytes() == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_immutable_or_check(path: Path, content: bytes, *, check: bool) -> None:
    if path.exists():
        if path.read_bytes() != content:
            raise RegressionGateError(f"Immutable artifact collision: {path}")
        return
    if check:
        raise RegressionGateError(f"Artifact is missing: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _relative_artifact(root: Path, relative_value: object, label: str) -> Path:
    relative = PurePosixPath(_text(relative_value, label))
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise RegressionGateError(f"{label} is not a safe relative path.")
    path = (root / Path(*relative.parts)).resolve()
    if not path.is_relative_to(root):
        raise RegressionGateError(f"{label} escapes its artifact root.")
    return path


def _reuse_v14_entry(
    entry: Mapping[str, object],
    *,
    source_root: Path,
    output_root: Path,
    check: bool,
) -> dict[str, object]:
    reused = cast(dict[str, object], json.loads(json.dumps(entry)))
    assets: list[tuple[object, object, str]] = [
        (
            entry.get("cardRelativePath"),
            entry.get("cardChecksumSha256"),
            "entry.card",
        ),
        (
            entry.get("boardRelativePath"),
            entry.get("boardChecksumSha256"),
            "entry.board",
        ),
        (
            entry.get("overlayRelativePath"),
            entry.get("overlayChecksumSha256"),
            "entry.overlay",
        ),
    ]
    for index, raw in enumerate(_sequence(entry.get("cells"), "entry.cells")):
        cell = _mapping(raw, f"entry.cells[{index}]")
        assets.append(
            (
                cell.get("relativePath"),
                cell.get("checksumSha256"),
                f"entry.cells[{index}]",
            )
        )
    for relative_value, checksum_value, label in assets:
        if relative_value is None and checksum_value is None:
            continue
        expected = _text(checksum_value, f"{label}.checksumSha256")
        source_path = _relative_artifact(source_root, relative_value, f"{label}.relativePath")
        try:
            content = source_path.resolve(strict=True).read_bytes()
        except OSError as error:
            raise RegressionGateError(f"Cannot read immutable v14 asset {source_path}.") from error
        if _sha256(content) != expected:
            raise RegressionGateError(f"Immutable v14 checksum drift for {source_path}.")
        _write_immutable_or_check(
            _relative_artifact(output_root, relative_value, f"{label}.relativePath"),
            content,
            check=check,
        )
    reused["geometryRoute"] = "immutable-v14-reuse"
    return reused


def _html_page(entries: Sequence[Mapping[str, object]], *, phase: Phase) -> bytes:
    if phase == "full":
        groups: list[str] = []
        image_ids = tuple(
            dict.fromkeys(_text(entry.get("sourceImageId"), "sourceImageId") for entry in entries)
        )
        for image_id in image_ids:
            image_entries = [
                entry
                for entry in entries
                if _text(entry.get("sourceImageId"), "sourceImageId") == image_id
            ]
            cards = "".join(
                "<article>"
                f"<h3>Seq {_integer(entry.get('sequenceNumber'), 'sequenceNumber')} — "
                f"{html.escape(_text(entry.get('status'), 'status'))}</h3>"
                f"<p>{html.escape(str(entry.get('primaryFallbackReason') or 'projective'))}</p>"
                f'<a href="{html.escape(_text(entry.get("cardRelativePath"), "cardPath"))}">'
                f'<img src="{html.escape(_text(entry.get("cardRelativePath"), "cardPath"))}" '
                f'alt="Final crops seq {entry.get("sequenceNumber")}"></a>'
                "</article>"
                for entry in image_entries
            )
            groups.append(
                "<section>"
                f"<h2>{html.escape(image_id)}</h2>"
                f"<div class='page-grid'>{cards}</div>"
                "</section>"
            )
        return (
            "<!doctype html><html lang='pl'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>M5 full-corpus crop preflight</title><style>"
            "body{margin:24px;background:#07111b;color:#edf7ff;font-family:system-ui}"
            "p{color:#b9cbd6}.page-grid{display:grid;grid-template-columns:"
            "repeat(3,minmax(0,1fr));gap:12px}section{margin:36px 0;padding:16px;"
            "background:#091722;border:1px solid #1e4055;border-radius:14px}"
            "article{background:#0c1b27;border-radius:10px;overflow:hidden}"
            "h3,p{padding:0 10px}img{width:100%;display:block}"
            "@media(max-width:900px){.page-grid{grid-template-columns:1fr}}</style>"
            "</head><body><h1>M5 — pełny preflight 43 stron</h1>"
            "<p>Każda karta pokazuje finalne 15 wycinków. Kliknij kartę, aby "
            "otworzyć ją w pełnej rozdzielczości. Wynik techniczny nie jest "
            "zgodą na trening.</p>"
            f"{''.join(groups)}</body></html>"
        ).encode()
    phase_description = (
        "Odrzucone sekwencje pełnego preflightu i ich bezpośrednie sąsiednie "
        "kontrole. Wynik służy wyłącznie do diagnostyki."
        if phase == "failures"
        else (
            "Kolejność: seq 29, zgłoszone błędy, niezatwierdzone kontrole. "
            "Wynik techniczny nie jest akceptacją wizualną ani zgodą na trening."
        )
    )
    cards = "".join(
        "<article>"
        f"<h2>Seq {_integer(entry.get('sequenceNumber'), 'sequenceNumber')} — "
        f"{html.escape(_text(entry.get('group'), 'group'))} — "
        f"{html.escape(_text(entry.get('status'), 'status'))}</h2>"
        f"<p>{html.escape(str(entry.get('fallbackReason') or 'technical pass'))}</p>"
        f'<img src="{html.escape(_text(entry.get("cardRelativePath"), "cardPath"))}" '
        f'alt="Regression seq {entry.get("sequenceNumber")}">'
        "</article>"
        for entry in entries
    )
    return (
        "<!doctype html><html lang='pl'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>M5 projective fixed-padding regression</title><style>"
        "body{margin:24px;background:#07111b;color:#edf7ff;font-family:system-ui}"
        "p{color:#b9cbd6}article{margin:24px 0;background:#0c1b27;"
        "border:1px solid #1e4055;border-radius:12px;overflow:hidden}"
        "h2,p{padding:0 16px}img{width:100%;display:block}</style></head><body>"
        f"<h1>Projective fixed-padding regression — {phase}</h1>"
        f"<p>{html.escape(phase_description)}</p>"
        f"{cards}</body></html>"
    ).encode()


def _phase_paths(
    phase: Phase,
    candidate: Candidate,
    output_root: Path | None,
    report_output: Path | None,
) -> tuple[Path, Path]:
    version_label = {
        "v12": "m5-projective-fixed-padding-v12",
        "v13-source": "m5-global-source-aware-v13",
        "v14-bbox": "m5-global-bbox-fallback-v14",
        "v16-reviewed": "m5-reviewed-manual-merge-v16",
    }[candidate]
    resolved_output = (
        output_root.resolve()
        if output_root is not None
        else ROOT
        / "artifacts"
        / (
            f"{version_label}-full-preflight"
            if phase == "full"
            else (
                f"{version_label}-full-failure-diagnostics-v3"
                if phase == "failures"
                else f"{version_label}-regression"
            )
        )
        / (
            ""
            if phase in {"full", "failures"}
            else ("seq29-gate" if phase == "seq29" else "bounded")
        )
    )
    resolved_report = (
        report_output.resolve()
        if report_output is not None
        else DEFAULT_REPORT_ROOT
        / (
            f"{version_label}-full-preflight-report.json"
            if phase == "full"
            else (
                f"{version_label}-full-failure-diagnostics-v3-report.json"
                if phase == "failures"
                else (
                    f"{version_label}-seq29-gate-report.json"
                    if phase == "seq29"
                    else f"{version_label}-bounded-regression-report.json"
                )
            )
        )
    )
    return resolved_output, resolved_report


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase",
        choices=("seq29", "bounded", "full", "failures"),
        default="bounded",
    )
    parser.add_argument(
        "--candidate",
        choices=("v12", "v13-source", "v14-bbox", "v16-reviewed"),
        default="v12",
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--detection-report",
        type=Path,
        default=DEFAULT_DETECTION_REPORT,
    )
    parser.add_argument("--v7-report", type=Path, default=DEFAULT_V7_REPORT)
    parser.add_argument("--controls", type=Path, default=DEFAULT_CONTROLS)
    parser.add_argument(
        "--normalization-root",
        type=Path,
        default=DEFAULT_NORMALIZATION_ROOT,
    )
    parser.add_argument("--crop-root", type=Path, default=DEFAULT_CROP_ROOT)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--report-output", type=Path)
    parser.add_argument(
        "--full-report",
        type=Path,
        default=DEFAULT_FULL_V14_REPORT,
    )
    parser.add_argument(
        "--reviewed-overrides",
        type=Path,
        default=DEFAULT_V14_REVIEW,
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--require-pass", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _args()
    phase = cast(Phase, args.phase)
    candidate = cast(Candidate, args.candidate)
    try:
        manifest_path = args.manifest.resolve(strict=True)
        detection_path = args.detection_report.resolve(strict=True)
        v7_path = args.v7_report.resolve(strict=True)
        controls_path = args.controls.resolve(strict=True)
        normalization_root = args.normalization_root.resolve(strict=True)
        crop_root = args.crop_root.resolve(strict=True)
        full_report_path = (
            args.full_report.resolve(strict=True)
            if phase == "failures" or candidate == "v16-reviewed"
            else None
        )
        output_root, report_output = _phase_paths(
            phase,
            candidate,
            args.output_root,
            args.report_output,
        )
        manifest = _load_json(manifest_path)
        detection = _load_json(detection_path)
        v7 = _load_json(v7_path)
        controls = _load_json(controls_path)
        full_report = (
            _load_json(cast(Path, full_report_path)) if full_report_path is not None else None
        )
        reviewed_overrides = (
            ReviewedV14ProjectiveOverrides.from_files(
                args.reviewed_overrides.resolve(strict=True),
                cast(Path, full_report_path),
            )
            if candidate == "v16-reviewed"
            else None
        )
        manifest_images = tuple(
            _mapping(value, "manifest.image")
            for value in _sequence(manifest.get("images"), "manifest.images")
        )
        control_sequences = tuple(
            _integer(value, "control.sequenceNumber")
            for value in _sequence(
                controls.get("listedSequenceNumbers"),
                "controls.listedSequenceNumbers",
            )
        )
        failure_sequences: tuple[int, ...] = ()
        full_entry_by_sequence: dict[int, Mapping[str, object]] = {}
        if full_report is not None:
            if (
                full_report.get("phase") != "full"
                or full_report.get("candidate") != "v14-bbox"
                or full_report.get("processedCount") != 387
            ):
                raise RegressionGateError(
                    "Failure diagnostics require the complete v14 full report."
                )
            failure_sequences = tuple(
                _integer(entry.get("sequenceNumber"), "entry.sequenceNumber")
                for value in _sequence(full_report.get("entries"), "fullReport.entries")
                for entry in (_mapping(value, "fullReport.entry"),)
                if entry.get("status") != "cropped"
            )
            if not failure_sequences:
                raise RegressionGateError("The full report contains no failed sequences.")
            full_entry_by_sequence = {
                _integer(entry.get("sequenceNumber"), "entry.sequenceNumber"): entry
                for value in _sequence(full_report.get("entries"), "fullReport.entries")
                for entry in (_mapping(value, "fullReport.entry"),)
            }
        sequence_numbers = (
            (PRIMARY_SEQUENCE,)
            if phase == "seq29"
            else (
                tuple(
                    sequence_number
                    for image in manifest_images
                    for sequence_number in range(
                        _integer(
                            image.get("expectedSequenceStart"),
                            "expectedSequenceStart",
                        ),
                        _integer(
                            image.get("expectedSequenceEnd"),
                            "expectedSequenceEnd",
                        )
                        + 1,
                    )
                )
                if phase == "full"
                else (
                    tuple(
                        dict.fromkeys(
                            sequence_number
                            for failed in failure_sequences
                            for sequence_number in (failed, failed - 1, failed + 1)
                            if 1 <= sequence_number <= 387
                        )
                    )
                    if phase == "failures"
                    else (
                        PRIMARY_SEQUENCE,
                        *REPORTED_FAILURE_SEQUENCES,
                        *control_sequences,
                    )
                )
            )
        )
        if len(sequence_numbers) != len(set(sequence_numbers)):
            raise RegressionGateError("Regression sequence list contains duplicates.")
        if phase == "full" and candidate not in {"v14-bbox", "v16-reviewed"}:
            raise RegressionGateError(
                "Full preflight is supported only for v14-bbox and v16-reviewed."
            )
        if phase == "failures" and candidate != "v14-bbox":
            raise RegressionGateError("Failure diagnostics are supported only for v14-bbox.")
        detection_by_source = {
            _text(item.get("sourceChecksumSha256"), "sourceChecksumSha256"): item
            for value in _sequence(
                detection.get("detections"),
                "detection.detections",
            )
            for item in (_mapping(value, "detection"),)
        }
        v7_by_source = {
            _text(item.get("sourceChecksumSha256"), "sourceChecksumSha256"): item
            for value in _sequence(v7.get("images"), "v7.images")
            for item in (_mapping(value, "v7.image"),)
        }
        calibrator = ProjectiveExpandedFrameCalibrator.from_files(
            manifest_path,
            detection_path,
        )
        entries: list[dict[str, object]] = []
        for sequence_number in sequence_numbers:
            manifest_image = next(
                image
                for image in manifest_images
                if _integer(
                    image.get("expectedSequenceStart"),
                    "expectedSequenceStart",
                )
                <= sequence_number
                <= _integer(
                    image.get("expectedSequenceEnd"),
                    "expectedSequenceEnd",
                )
            )
            sequence_start = _integer(
                manifest_image.get("expectedSequenceStart"),
                "expectedSequenceStart",
            )
            position = sequence_number - sequence_start
            source = _text(manifest_image.get("sha256"), "manifest.sha256")
            detection_entry = detection_by_source[source]
            detection_result = _mapping(
                detection_entry.get("result"),
                "detection.result",
            )
            if detection_result.get("status") != "detected":
                raise RegressionGateError(
                    f"Sequence {sequence_number} has no accepted detector result."
                )
            detector_board = next(
                board
                for value in _sequence(
                    detection_result.get("boards"),
                    "detection.boards",
                )
                for board in (_mapping(value, "detection.board"),)
                if _integer(board.get("positionIndex"), "positionIndex") == position
            )
            manual_override = (
                reviewed_overrides.get(source, position) if reviewed_overrides is not None else None
            )
            if candidate == "v16-reviewed" and manual_override is None:
                source_entry = full_entry_by_sequence.get(sequence_number)
                if (
                    source_entry is None
                    or source_entry.get("status") != "cropped"
                    or source_entry.get("sourceChecksumSha256") != source
                    or source_entry.get("positionIndex") != position
                ):
                    raise RegressionGateError(
                        f"Sequence {sequence_number} cannot reuse one immutable v14 result."
                    )
                entries.append(
                    _reuse_v14_entry(
                        source_entry,
                        source_root=DEFAULT_FULL_V14_ARTIFACT_ROOT.resolve(strict=True),
                        output_root=output_root,
                        check=args.check,
                    )
                )
                continue
            normalized_path = _safe_artifact_path(
                normalization_root,
                detection_entry.get("normalizedRelativePath"),
                namespace="image-normalization-v1",
                label="normalizedRelativePath",
            )
            normalized_rgb = _decode_rgb(normalized_path)
            baseline_cells: list[NDArray[np.uint8]] = []
            if phase != "full":
                v7_image = v7_by_source[source]
                v7_board = next(
                    board
                    for value in _sequence(v7_image.get("boards"), "v7.boards")
                    for board in (_mapping(value, "v7.board"),)
                    if _integer(board.get("positionIndex"), "positionIndex") == position
                )
                v7_cells = sorted(
                    (
                        _mapping(value, "v7.cell")
                        for value in _sequence(v7_board.get("cells"), "v7.cells")
                    ),
                    key=lambda cell: (
                        _integer(cell.get("rowIndex"), "rowIndex"),
                        _integer(cell.get("columnIndex"), "columnIndex"),
                    ),
                )
                baseline_cells = [
                    _decode_rgb(
                        _safe_artifact_path(
                            crop_root,
                            cell.get("relativePath"),
                            namespace=V7_NAMESPACE,
                            label="v7.cell.relativePath",
                        )
                    )
                    for cell in v7_cells
                ]
            page_geometry = PageGeometry(
                status="detected",
                image_width=_integer(
                    detection_result.get("imageWidth"),
                    "imageWidth",
                ),
                image_height=_integer(
                    detection_result.get("imageHeight"),
                    "imageHeight",
                ),
                boards=(
                    BoardGeometry(
                        position_index=position,
                        quad=_quad(detector_board.get("quad"), "detector.quad"),
                        bounding_box=_bounding_box(
                            detector_board.get("boundingBox"),
                            "detector.boundingBox",
                        ),
                    ),
                ),
            )
            expanded_quad: Quad
            if manual_override is not None:
                expanded_quad = manual_override.source_quad
                expanded_board, _ = rectify_board(normalized_rgb, expanded_quad)
            else:
                expanded = calibrator.calibrate(source, page_geometry)
                if expanded.status != "detected" or not expanded.boards:
                    if phase in {"full", "failures"}:
                        reason = (
                            expanded.review_reasons[0]
                            if expanded.review_reasons
                            else "PROJECTIVE_FRAME_EXPANSION_INVALID"
                        )
                        card_bytes = (
                            _expansion_failure_card(
                                baseline_cells,
                                rectify_board(
                                    normalized_rgb,
                                    _quad(detector_board.get("quad"), "detector.quad"),
                                )[0],
                                sequence_number=sequence_number,
                                reason=reason,
                            )
                            if phase == "failures"
                            else _full_failure_card(
                                sequence_number=sequence_number,
                                reason=reason,
                            )
                        )
                        card_relative = f"cards/seq-{sequence_number:03d}.png"
                        _write_immutable_or_check(
                            output_root / Path(*PurePosixPath(card_relative).parts),
                            card_bytes,
                            check=args.check,
                        )
                        entries.append(
                            {
                                "analysisFrameSource": "none",
                                "cardChecksumSha256": _sha256(card_bytes),
                                "cardRelativePath": card_relative,
                                "cells": [],
                                "fallbackReason": reason,
                                "group": ("full_failure" if phase == "failures" else "full_corpus"),
                                "homography": None,
                                "minimumSupportFraction": None,
                                "positionIndex": position,
                                "primaryFallbackReason": None,
                                "projectiveExpandedQuad": [],
                                "sequenceNumber": sequence_number,
                                "sourceChecksumSha256": source,
                                "sourceImageId": _text(
                                    manifest_image.get("id"),
                                    "manifest.id",
                                ),
                                "status": "fallback",
                            }
                        )
                        continue
                    raise RegressionGateError(
                        f"Sequence {sequence_number} failed projective expansion: "
                        f"{expanded.review_reasons}"
                    )
                expanded_quad = expanded.boards[0].quad
                expanded_board, _ = rectify_board(
                    normalized_rgb,
                    expanded_quad,
                )
            crop_result: ProjectiveLatticeCropResult | SourceProjectiveLatticeCropResult
            if manual_override is not None:
                crop_result = build_reviewed_source_quad_crops(
                    normalized_rgb,
                    manual_override.source_quad,
                    primary_fallback_reason=manual_override.fallback_reason,
                )
            elif candidate in {"v14-bbox", "v16-reviewed"}:
                crop_result = build_bounding_fallback_source_projective_lattice_crops(
                    normalized_rgb,
                    expanded_quad,
                    _bounding_box(
                        detector_board.get("boundingBox"),
                        "detector.boundingBox",
                    ),
                )
            elif candidate == "v13-source":
                crop_result = build_source_projective_lattice_crops(
                    normalized_rgb,
                    expanded_quad,
                )
            else:
                crop_result = build_projective_lattice_crops(expanded_board)
            group = (
                "full_corpus"
                if phase == "full"
                else (
                    ("full_failure" if sequence_number in failure_sequences else "neighbor_control")
                    if phase == "failures"
                    else (
                        "primary"
                        if sequence_number == PRIMARY_SEQUENCE
                        else (
                            "reported_failure"
                            if sequence_number in REPORTED_FAILURE_SEQUENCES
                            else "control_not_owner_approved"
                        )
                    )
                )
            )
            card_bytes = (
                _full_card(
                    cast(SourceProjectiveLatticeCropResult, crop_result),
                    sequence_number=sequence_number,
                )
                if phase == "full"
                else _card(
                    baseline_cells,
                    crop_result,
                    sequence_number=sequence_number,
                    group=group,
                )
            )
            card_relative = f"cards/seq-{sequence_number:03d}.png"
            write_artifact = (
                _write_immutable_or_check if phase in {"full", "failures"} else _write_or_check
            )
            write_artifact(
                output_root / Path(*PurePosixPath(card_relative).parts),
                card_bytes,
                check=args.check,
            )
            cells: list[dict[str, object]] = []
            for cell in crop_result.cells:
                cell_bytes = _encode_png(cell.rgb)
                cell_value = {
                    **cell.to_dict(),
                    "checksumSha256": _sha256(cell_bytes),
                }
                if phase == "full":
                    cell_relative = (
                        f"cells/seq-{sequence_number:03d}/"
                        f"r{cell.row_index:02d}-c{cell.column_index:02d}.png"
                    )
                    write_artifact(
                        output_root / Path(*PurePosixPath(cell_relative).parts),
                        cell_bytes,
                        check=args.check,
                    )
                    cell_value["relativePath"] = cell_relative
                cells.append(cell_value)
            entry: dict[str, object] = {
                "cardChecksumSha256": _sha256(card_bytes),
                "cardRelativePath": card_relative,
                "cells": cells,
                "fallbackReason": crop_result.fallback_reason,
                "group": group,
                "homography": crop_result.homography.to_dict(),
                "minimumSupportFraction": (crop_result.minimum_support_fraction),
                "normalizedImageSha256": _sha256(normalized_path.read_bytes()),
                "positionIndex": position,
                "projectiveExpandedQuad": [point.to_dict() for point in expanded_quad],
                "sequenceNumber": sequence_number,
                "sourceChecksumSha256": source,
                "sourceImageId": _text(
                    manifest_image.get("id"),
                    "manifest.id",
                ),
                "status": crop_result.status,
            }
            if phase == "full" and isinstance(
                crop_result,
                SourceProjectiveLatticeCropResult,
            ):
                if crop_result.board_rgb is not None:
                    board_relative = f"boards/seq-{sequence_number:03d}/board.png"
                    board_bytes = _encode_png(crop_result.board_rgb)
                    write_artifact(
                        output_root / Path(*PurePosixPath(board_relative).parts),
                        board_bytes,
                        check=args.check,
                    )
                    entry["boardChecksumSha256"] = _sha256(board_bytes)
                    entry["boardRelativePath"] = board_relative
                if crop_result.grid_overlay_rgb is not None:
                    overlay_relative = f"boards/seq-{sequence_number:03d}/grid-overlay.png"
                    overlay_bytes = _encode_png(crop_result.grid_overlay_rgb)
                    write_artifact(
                        output_root / Path(*PurePosixPath(overlay_relative).parts),
                        overlay_bytes,
                        check=args.check,
                    )
                    entry["overlayChecksumSha256"] = _sha256(overlay_bytes)
                    entry["overlayRelativePath"] = overlay_relative
            if isinstance(crop_result, SourceProjectiveLatticeCropResult):
                entry.update(
                    {
                        "analysisFrameSource": crop_result.analysis_frame_source,
                        "primaryFallbackReason": (crop_result.primary_fallback_reason),
                    }
                )
            if manual_override is not None:
                entry["manualOverrideObservationId"] = manual_override.observation_id
            entries.append(entry)
            if (
                phase not in {"full", "failures"}
                and sequence_number == PRIMARY_SEQUENCE
                and crop_result.status != "cropped"
            ):
                break
        fallback_count = sum(entry["status"] != "cropped" for entry in entries)
        cell_count = sum(len(_sequence(entry.get("cells"), "entry.cells")) for entry in entries)
        image_count = len({_text(entry.get("sourceImageId"), "sourceImageId") for entry in entries})
        expected_cell_count = len(sequence_numbers) * BOARD_ROWS * BOARD_COLUMNS
        technical_passed = (
            len(entries) == len(sequence_numbers)
            if phase == "failures"
            else (
                len(entries) == len(sequence_numbers)
                and fallback_count == 0
                and cell_count == expected_cell_count
            )
        )
        page_bytes = _html_page(entries, phase=phase)
        (_write_immutable_or_check if phase in {"full", "failures"} else _write_or_check)(
            output_root / "index.html", page_bytes, check=args.check
        )
        report: dict[str, object] = {
            "controlDefinitionSha256": _sha256(controls_path.read_bytes()),
            "controlOwnerApproved": phase == "full",
            "cropperVersion": CROPPER_VERSION,
            "detectionReportSha256": _sha256(detection_path.read_bytes()),
            "entries": entries,
            "executionOrder": list(sequence_numbers),
            "fallbackCount": fallback_count,
            "fixedPaddingPx": FIXED_PADDING_PX,
            "fullCorpusGenerated": phase == "full" and technical_passed,
            "homographyVersion": HOMOGRAPHY_VERSION,
            "manifestSha256": _sha256(manifest_path.read_bytes()),
            "numpyVersion": np.__version__,
            "opencvVersion": cv2.__version__,
            "ownerReviewRequired": True,
            "phase": phase,
            "processedCount": len(entries),
            "projectiveFrameProfileVersion": (PROJECTIVE_FRAME_PROFILE_SET_VERSION),
            "schemaVersion": "m5-projective-fixed-padding-regression-v1",
            "status": ("waiting_for_owner_review" if technical_passed else "failed"),
            "technicalPassed": technical_passed,
            "trainingAllowed": False,
            "v7ReportSha256": _sha256(v7_path.read_bytes()),
        }
        if phase == "full":
            report.update(
                {
                    "boardCount": len(entries),
                    "cellCount": cell_count,
                    "imageCount": image_count,
                }
            )
        elif phase == "failures":
            report.update(
                {
                    "diagnosticFailureSequenceNumbers": list(failure_sequences),
                    "sourceFullReportSha256": _sha256(cast(Path, full_report_path).read_bytes()),
                }
            )
        if candidate == "v13-source":
            report.update(
                {
                    "candidate": candidate,
                    "cropperVersion": SOURCE_AWARE_CROPPER_VERSION,
                    "gridVersion": SOURCE_AWARE_GRID_VERSION,
                    "homographyVersion": GLOBAL_HOMOGRAPHY_VERSION,
                    "schemaVersion": "m5-projective-fixed-padding-regression-v2",
                }
            )
        elif candidate == "v14-bbox":
            report.update(
                {
                    "candidate": candidate,
                    "cropperVersion": BOUNDING_FALLBACK_CROPPER_VERSION,
                    "gridVersion": BOUNDING_FALLBACK_GRID_VERSION,
                    "homographyVersion": GLOBAL_HOMOGRAPHY_VERSION,
                    "schemaVersion": (
                        "m5-projective-fixed-padding-full-preflight-v1"
                        if phase == "full"
                        else (
                            "m5-projective-fixed-padding-failure-diagnostics-v3"
                            if phase == "failures"
                            else "m5-projective-fixed-padding-regression-v2"
                        )
                    ),
                }
            )
        elif candidate == "v16-reviewed":
            if reviewed_overrides is None:
                raise RegressionGateError("Reviewed v16 overrides are unavailable.")
            manual_override_count = sum(
                entry.get("analysisFrameSource") == "human-reviewed-source-quad"
                for entry in entries
            )
            reused_v14_count = sum(
                entry.get("geometryRoute") == "immutable-v14-reuse" for entry in entries
            )
            if manual_override_count != reviewed_overrides.override_count:
                raise RegressionGateError(
                    "The full run did not consume every reviewed override exactly once."
                )
            if reused_v14_count != 387 - manual_override_count:
                raise RegressionGateError(
                    "The full run did not preserve every accepted v14 result."
                )
            report.update(
                {
                    "candidate": candidate,
                    "cropperVersion": REVIEWED_MERGE_CROPPER_VERSION,
                    "gridVersion": REVIEWED_MERGE_GRID_VERSION,
                    "homographyVersion": (
                        f"{GLOBAL_HOMOGRAPHY_VERSION}+{REVIEWED_SOURCE_QUAD_HOMOGRAPHY_VERSION}"
                    ),
                    "manualOverrideCount": manual_override_count,
                    "manualOverrideCropperVersion": (REVIEWED_SOURCE_QUAD_CROPPER_VERSION),
                    "manualOverrideGridVersion": REVIEWED_SOURCE_QUAD_GRID_VERSION,
                    "reviewedOverrideSetVersion": reviewed_overrides.version,
                    "reviewedOverrideSha256": reviewed_overrides.review_sha256,
                    "reusedV14BoardCount": reused_v14_count,
                    "schemaVersion": "m5-reviewed-manual-merge-v16-full-preflight-v1",
                    "sourceV14FullReportSha256": (reviewed_overrides.source_report_sha256),
                }
            )
        report_bytes = (
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode()
        (_write_immutable_or_check if phase in {"full", "failures"} else _write_or_check)(
            report_output, report_bytes, check=args.check
        )
        print(
            json.dumps(
                {
                    "fallbackCount": fallback_count,
                    "output": str((output_root / "index.html").resolve()),
                    "phase": phase,
                    "processedCount": len(entries),
                    "report": str(report_output.resolve()),
                    "reportSha256": _sha256(report_bytes),
                    "status": report["status"],
                    "technicalPassed": technical_passed,
                },
                sort_keys=True,
            )
        )
        if args.require_pass and not technical_passed:
            return 1
        return 0
    except (
        KeyError,
        OSError,
        RegressionGateError,
        StopIteration,
        V14ProjectiveOverrideError,
        json.JSONDecodeError,
    ) as error:
        print(
            json.dumps(
                {"message": str(error), "status": "failed"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
