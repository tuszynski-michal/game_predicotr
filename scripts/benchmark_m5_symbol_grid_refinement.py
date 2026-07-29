"""Benchmark guarded symbol-aware grid proposals on reviewed boards."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, cast

import cv2
import numpy as np
from numpy.typing import NDArray

ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.images.geometry import Point, Quad  # noqa: E402
from game_predictor_worker.images.symbol_grid_refinement import (  # noqa: E402
    REFINER_VERSION,
    SymbolCenter,
    rectify_board,
    refine_symbol_grid,
)

REPORT_VERSION = "m5-symbol-grid-refinement-benchmark-v1"
DEFAULT_REVIEW = ROOT / "artifacts" / "m5-local-grid-review" / "reviewed-geometry.json"
DEFAULT_NORMALIZATION_REPORT = ROOT / "ai_docs" / "quality" / "m5-normalization-report.json"
DEFAULT_NORMALIZATION_ROOT = ROOT / "artifacts" / "m5-normalization"
DEFAULT_ARTIFACT_ROOT = ROOT / "artifacts" / "m5-symbol-grid-refinement"
DEFAULT_OUTPUT = ROOT / "ai_docs" / "quality" / "m5-symbol-grid-refinement-report.json"


class BenchmarkError(ValueError):
    """Stable benchmark input or output error."""


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise BenchmarkError(f"{label} must be an object.")
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise BenchmarkError(f"{label} must be an array.")
    return cast(Sequence[object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise BenchmarkError(f"{label} must be non-empty text.")
    return value


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise BenchmarkError(f"{label} must be an integer.")
    return value


def _number_or_zero(value: object) -> float:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return 0.0


def _load_json(path: Path, label: str) -> tuple[bytes, Mapping[str, object]]:
    try:
        content = path.read_bytes()
        value: Any = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise BenchmarkError(f"{label} cannot be read.") from error
    return content, _mapping(value, label)


def _quad(value: object, label: str) -> Quad:
    raw_points = _sequence(value, label)
    if len(raw_points) != 4:
        raise BenchmarkError(f"{label} must contain four points.")
    points: list[Point] = []
    for index, raw in enumerate(raw_points):
        point = _mapping(raw, f"{label}[{index}]")
        x = point.get("x")
        y = point.get("y")
        if not isinstance(x, int | float) or not isinstance(y, int | float):
            raise BenchmarkError(f"{label}[{index}] coordinates are invalid.")
        points.append(Point(int(round(float(x))), int(round(float(y)))))
    return cast(Quad, tuple(points))


def _safe_artifact(
    root: Path,
    relative_path: object,
    *,
    namespace: str,
) -> Path:
    text = _text(relative_path, "normalizedRelativePath")
    relative = PurePosixPath(text)
    if (
        relative.is_absolute()
        or not relative.parts
        or relative.parts[0] != namespace
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise BenchmarkError("Normalized path leaves its namespace.")
    path = (root / Path(*relative.parts)).resolve(strict=True)
    if not path.is_relative_to(root.resolve(strict=True)):
        raise BenchmarkError("Normalized path leaves its root.")
    return path


def _decode_rgb(path: Path) -> NDArray[np.uint8]:
    content = path.read_bytes()
    bgr = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        raise BenchmarkError(f"Cannot decode normalized image: {path}")
    return cast(NDArray[np.uint8], cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def _draw_grid(
    board_rgb: NDArray[np.uint8],
    centers: tuple[SymbolCenter, ...],
    *,
    colour: tuple[int, int, int],
) -> NDArray[np.uint8]:
    canvas = board_rgb.copy()
    for column in range(1, 5):
        cv2.line(canvas, (column * 100, 0), (column * 100, 299), colour, 2)
    for row in range(1, 3):
        cv2.line(canvas, (0, row * 100), (499, row * 100), colour, 2)
    for center in centers:
        center_colour = (0, 255, 0) if center.confidence >= 0.34 else (255, 80, 80)
        cv2.circle(
            canvas,
            (int(round(center.x)), int(round(center.y))),
            5,
            center_colour,
            2,
            lineType=cv2.LINE_AA,
        )
    return canvas


def _encode_png(rgb: NDArray[np.uint8]) -> bytes:
    encoded, buffer = cv2.imencode(
        ".png",
        cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
        [cv2.IMWRITE_PNG_COMPRESSION, 6],
    )
    if not encoded:
        raise BenchmarkError("Cannot encode benchmark overlay.")
    return bytes(buffer)


def _write_if_changed(path: Path, content: bytes) -> None:
    if path.exists() and path.read_bytes() == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def _overlay(
    rgb: NDArray[np.uint8],
    initial_quad: Quad,
    *,
    result_quad: Quad,
    initial_centers: tuple[SymbolCenter, ...],
    status: str,
    sequence_number: int,
) -> NDArray[np.uint8]:
    before, _ = rectify_board(rgb, initial_quad)
    after, _ = rectify_board(rgb, result_quad)
    from game_predictor_worker.images.symbol_grid_refinement import (  # noqa: PLC0415
        locate_symbol_centers,
    )

    after_centers = locate_symbol_centers(after)
    left = _draw_grid(
        before,
        initial_centers,
        colour=(255, 210, 0),
    )
    right = _draw_grid(
        after,
        after_centers,
        colour=(0, 255, 120),
    )
    separator = np.full((300, 8, 3), 235, dtype=np.uint8)
    boards = cast(
        NDArray[np.uint8],
        np.concatenate((left, separator, right), axis=1),
    )
    header = np.full((32, boards.shape[1], 3), (8, 15, 24), dtype=np.uint8)
    for text, x in (
        (f"frame baseline | seq {sequence_number}", 10),
        (f"symbol-aware | {status}", 518),
    ):
        cv2.putText(
            header,
            text,
            (x, 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
    return cast(NDArray[np.uint8], np.concatenate((header, boards), axis=0))


def _summary(entries: Sequence[Mapping[str, object]]) -> dict[str, object]:
    status_counts = Counter(_text(entry.get("status"), "entry.status") for entry in entries)
    baseline = [
        float(value)
        for entry in entries
        if isinstance(value := entry.get("baselineMedianResidualPx"), int | float)
    ]
    refined = [
        float(value)
        for entry in entries
        if isinstance(value := entry.get("refinedMedianResidualPx"), int | float)
    ]
    return {
        "baselineMedianResidualPx": (
            None if not baseline else round(float(np.median(baseline)), 4)
        ),
        "fallbackCount": status_counts["fallback"],
        "refinedCount": status_counts["refined"],
        "refinedMedianResidualPx": (None if not refined else round(float(np.median(refined)), 4)),
        "total": len(entries),
    }


def _gallery_html(entries: Sequence[Mapping[str, object]]) -> bytes:
    cards: list[str] = []
    ordered = sorted(
        entries,
        key=lambda entry: (
            -_number_or_zero(entry.get("baselineMedianResidualPx")),
            _integer(entry.get("sequenceNumber"), "sequenceNumber"),
        ),
    )
    for entry in ordered:
        overlay = entry.get("overlayRelativePath")
        if not isinstance(overlay, str):
            continue
        sequence_number = _integer(entry.get("sequenceNumber"), "sequenceNumber")
        board_position = _integer(entry.get("boardPosition"), "boardPosition")
        cut_count = _integer(entry.get("reportedCutCellCount"), "reportedCutCellCount")
        baseline = entry.get("baselineMedianResidualPx")
        refined = entry.get("refinedMedianResidualPx")
        purpose = html.escape(_text(entry.get("purpose"), "purpose"))
        status = html.escape(_text(entry.get("status"), "status"))
        cards.append(
            f"""
            <article>
              <header>
                <h2>Sekwencja {sequence_number} · pozycja {board_position}</h2>
                <p>{purpose} · {status} · zgłoszone komórki: {cut_count}</p>
                <p>mediana: {baseline} px → {refined} px</p>
              </header>
              <img src="{html.escape(overlay)}"
                   alt="Porównanie geometrii dla sekwencji {sequence_number}" />
            </article>
            """
        )
    document = f"""<!doctype html>
<html lang="pl">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>M5 — symbol-aware grid spike</title>
    <style>
      :root {{
        color-scheme: dark;
        font-family: Inter, system-ui, sans-serif;
        background: #07111b;
        color: #edf7ff;
      }}
      body {{ margin: 0; padding: 32px; }}
      main {{ max-width: 1180px; margin: 0 auto; }}
      h1 {{ margin-bottom: 8px; }}
      .lead {{ color: #a9bfd0; margin-bottom: 28px; }}
      article {{
        background: #0d1d2a;
        border: 1px solid #1d3b4f;
        border-radius: 14px;
        margin: 0 0 24px;
        overflow: hidden;
      }}
      article header {{ padding: 16px 20px 10px; }}
      article h2 {{ margin: 0 0 6px; font-size: 18px; }}
      article p {{ display: inline-block; margin: 0 24px 6px 0; color: #a9bfd0; }}
      img {{ display: block; width: 100%; height: auto; background: #020609; }}
      .yellow {{ color: #ffd200; }}
      .green {{ color: #00ef85; }}
    </style>
  </head>
  <body>
    <main>
      <h1>Porównanie siatki względem symboli</h1>
      <p class="lead">
        <span class="yellow">Żółty: rama planszy.</span>
        <span class="green">Zielony: dopasowanie do 15 środków symboli.</span>
        To jest benchmark — żadna geometria nie została automatycznie
        opublikowana.
      </p>
      {"".join(cards)}
    </main>
  </body>
</html>
"""
    return document.encode()


def build_report(
    *,
    review_path: Path,
    normalization_report_path: Path,
    normalization_root: Path,
    artifact_root: Path,
) -> dict[str, object]:
    review_bytes, review = _load_json(review_path, "review")
    normalization_bytes, normalization = _load_json(
        normalization_report_path,
        "normalizationReport",
    )
    normalized_by_source = {
        _text(item.get("sourceChecksumSha256"), "sourceChecksumSha256"): item
        for raw in _sequence(normalization.get("images"), "normalizationReport.images")
        for item in [_mapping(raw, "normalizationReport.image")]
    }
    entries: list[dict[str, object]] = []
    artifact_base = artifact_root.resolve()
    for index, raw in enumerate(_sequence(review.get("entries"), "review.entries")):
        item = _mapping(raw, f"review.entries[{index}]")
        if item.get("reviewStatus") != "accepted":
            raise BenchmarkError("All corrective review entries must be accepted.")
        source_checksum = _text(
            item.get("sourceImageChecksumSha256"),
            "sourceImageChecksumSha256",
        )
        normalized = normalized_by_source.get(source_checksum)
        if normalized is None:
            raise BenchmarkError("Reviewed source is missing from normalization report.")
        normalized_path = _safe_artifact(
            normalization_root,
            normalized.get("normalizedRelativePath"),
            namespace="image-normalization-v1",
        )
        normalized_content = normalized_path.read_bytes()
        if hashlib.sha256(normalized_content).hexdigest() != normalized.get(
            "normalizedChecksumSha256"
        ):
            raise BenchmarkError("Normalized image checksum drift.")
        rgb = _decode_rgb(normalized_path)
        initial_quad = _quad(item.get("sourceQuad"), "entry.sourceQuad")
        result = refine_symbol_grid(rgb, initial_quad)
        sequence_number = _integer(item.get("sequenceNumber"), "entry.sequenceNumber")
        board_position = _integer(item.get("boardPosition"), "entry.boardPosition")
        cut_cells = [
            _integer(value, "v1CutCellIndexes[]")
            for value in _sequence(
                item.get("v1CutCellIndexes"),
                "entry.v1CutCellIndexes",
            )
        ]
        overlay_relative = (
            PurePosixPath(REFINER_VERSION) / f"seq-{sequence_number:04d}-pos-{board_position}.png"
        ).as_posix()
        overlay = _overlay(
            rgb,
            initial_quad,
            result_quad=result.source_quad,
            initial_centers=result.centers,
            status=result.status,
            sequence_number=sequence_number,
        )
        overlay_content = _encode_png(overlay)
        _write_if_changed(
            artifact_base / Path(*PurePosixPath(overlay_relative).parts),
            overlay_content,
        )
        overlay_sha = hashlib.sha256(overlay_content).hexdigest()
        entry = result.to_dict()
        entry.update(
            {
                "boardPosition": board_position,
                "imageId": _text(item.get("imageId"), "entry.imageId"),
                "observationId": _text(
                    item.get("observationId"),
                    "entry.observationId",
                ),
                "overlayChecksumSha256": overlay_sha,
                "overlayRelativePath": overlay_relative,
                "purpose": _text(item.get("purpose"), "entry.purpose"),
                "reportedCutCellCount": len(cut_cells),
                "reportedCutCellIndexes": cut_cells,
                "sequenceNumber": sequence_number,
                "sourceImageChecksumSha256": source_checksum,
            }
        )
        entries.append(entry)
    missing = [entry for entry in entries if entry["purpose"] == "missing_anchor"]
    heldout = [entry for entry in entries if entry["purpose"] == "heldout"]
    cut_entries = [entry for entry in entries if entry["reportedCutCellCount"] != 0]
    _write_if_changed(artifact_base / "index.html", _gallery_html(entries))
    return {
        "entries": entries,
        "normalizationReportSha256": hashlib.sha256(normalization_bytes).hexdigest(),
        "refinerVersion": REFINER_VERSION,
        "reportVersion": REPORT_VERSION,
        "reviewSha256": hashlib.sha256(review_bytes).hexdigest(),
        "status": "spike_review_required",
        "summary": {
            "all": _summary(entries),
            "heldout": _summary(heldout),
            "missingAnchor": _summary(missing),
            "reportedCutBoards": len(cut_entries),
            "reportedCutCells": sum(
                _integer(
                    entry["reportedCutCellCount"],
                    "entry.reportedCutCellCount",
                )
                for entry in entries
            ),
        },
        "trainingAllowed": False,
    }


def _json_bytes(value: Mapping[str, object]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument(
        "--normalization-report",
        type=Path,
        default=DEFAULT_NORMALIZATION_REPORT,
    )
    parser.add_argument(
        "--normalization-root",
        type=Path,
        default=DEFAULT_NORMALIZATION_ROOT,
    )
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        report = build_report(
            review_path=args.review,
            normalization_report_path=args.normalization_report,
            normalization_root=args.normalization_root,
            artifact_root=args.artifact_root,
        )
        content = _json_bytes(report)
        if args.check:
            if not args.output.exists() or args.output.read_bytes() != content:
                raise BenchmarkError("Benchmark report is missing or stale.")
        else:
            _write_if_changed(args.output.resolve(), content)
        print(
            json.dumps(
                {
                    "output": str(args.output.resolve()),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "summary": report["summary"],
                },
                sort_keys=True,
            )
        )
        return 0
    except (BenchmarkError, OSError, json.JSONDecodeError) as error:
        print(
            json.dumps(
                {"code": "SYMBOL_GRID_BENCHMARK_FAILED", "message": str(error)},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
