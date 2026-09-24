"""Local, read-only preview of the proposed grid engine v3 on screen photos.

Runs ``detect_screen_layout_v3`` on a few photos per directory and writes an
HTML page with grid overlays plus a JSON report.  Nothing is written to the
database or to managed storage; photos stay where they are.

Colours: green = complete board, yellow = partial (lateral crop, red cells are
unavailable), red = needs review.
"""

from __future__ import annotations

import argparse
import html
import json
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
from game_predictor_worker.images.screen_layout_v3 import (
    BoardStatus,
    ScreenLayoutResult,
    detect_screen_layout_v3,
)
from numpy.typing import NDArray
from PIL import Image, ImageOps

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
DEFAULT_OUTPUT_DIR = Path("artifacts/screen-layout-v3")
STATUS_COLOURS = {
    BoardStatus.COMPLETE: (0, 220, 0),
    BoardStatus.PARTIAL: (0, 220, 255),
    BoardStatus.NEEDS_REVIEW: (0, 0, 255),
}


def select_photos(inputs: Sequence[Path], per_dir: int) -> list[Path]:
    """Evenly spaced photos per directory (recursively); files are taken as given."""

    selected: list[Path] = []
    for item in inputs:
        if not item.exists():
            raise FileNotFoundError(f"Input does not exist: {item}")
        if item.is_file():
            selected.append(item)
            continue
        for directory in sorted({item, *(p for p in item.rglob("*") if p.is_dir())}):
            photos = sorted(
                p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
            )
            if not photos:
                continue
            if per_dir <= 0 or len(photos) <= per_dir:
                selected.extend(photos)
                continue
            indices = [int((k + 0.5) * len(photos) / per_dir) for k in range(per_dir)]
            selected.extend(photos[i] for i in indices)
    return selected


def load_rgb(path: Path) -> NDArray[np.uint8]:
    with Image.open(path) as image:
        return np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)


def draw(rgb: NDArray[np.uint8], result: ScreenLayoutResult) -> NDArray[np.uint8]:
    canvas = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    thickness = max(2, rgb.shape[1] // 700)
    for board in result.boards:
        colour = STATUS_COLOURS[board.status]
        for index in board.unavailable_cell_indices:
            quad = board.cell_quad(index).astype(np.int32)
            cv2.line(canvas, tuple(quad[0]), tuple(quad[2]), (0, 0, 255), thickness)
            cv2.line(canvas, tuple(quad[1]), tuple(quad[3]), (0, 0, 255), thickness)
        points = board.points
        for row in range(points.shape[0]):
            cv2.polylines(canvas, [points[row].astype(np.int32)], False, colour, thickness)
        for column in range(points.shape[1]):
            cv2.polylines(canvas, [points[:, column].astype(np.int32)], False, colour, thickness)
        label_at = board.quad[0].astype(np.int32) + np.array([4, -6])
        cv2.putText(
            canvas,
            str(board.position_index + 1),
            (int(label_at[0]), int(label_at[1])),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8 * thickness / 2,
            colour,
            thickness,
        )
    return np.asarray(canvas, dtype=np.uint8)


def result_payload(path: Path, result: ScreenLayoutResult) -> dict[str, object]:
    return {
        "photo": str(path),
        "status": result.status.value,
        "reasonCode": result.reason_code,
        "version": result.version,
        "metrics": {k: round(v, 4) for k, v in result.metrics.items()},
        "boards": [
            {
                "positionIndex": board.position_index,
                "status": board.status.value,
                "reasonCodes": list(board.reason_codes),
                "unavailableCellIndices": list(board.unavailable_cell_indices),
                "residualPx": None if board.residual_px is None else round(board.residual_px, 2),
                "alignment": round(board.alignment, 3),
                "gridQuad": [[round(float(x), 1), round(float(y), 1)] for x, y in board.quad],
            }
            for board in result.boards
        ],
    }


def run(inputs: Sequence[Path], per_dir: int, output_dir: Path, max_width: int) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = output_dir / stamp
    target.mkdir(parents=True, exist_ok=True)
    photos = select_photos(inputs, per_dir)
    report: list[dict[str, object]] = []
    rows: list[str] = []
    for number, photo in enumerate(photos, start=1):
        started = time.perf_counter()
        rgb = load_rgb(photo)
        result = detect_screen_layout_v3(rgb)
        overlay = draw(rgb, result)
        if overlay.shape[1] > max_width:
            scale = max_width / overlay.shape[1]
            overlay = np.asarray(
                cv2.resize(overlay, (max_width, int(overlay.shape[0] * scale))), dtype=np.uint8
            )
        name = f"{number:03d}.jpg"
        cv2.imwrite(str(target / name), overlay, [cv2.IMWRITE_JPEG_QUALITY, 88])
        payload = result_payload(photo, result)
        report.append(payload)
        counts = {status: 0 for status in BoardStatus}
        for board in result.boards:
            counts[board.status] += 1
        summary = (
            f"#{number} · {html.escape(photo.parent.name)}/{html.escape(photo.name)} · "
            f"{result.status.value}"
            + (f" ({html.escape(result.reason_code)})" if result.reason_code else "")
            + f" · pełne {counts[BoardStatus.COMPLETE]}, częściowe {counts[BoardStatus.PARTIAL]},"
            f" do poprawy {counts[BoardStatus.NEEDS_REVIEW]}"
            f" · {time.perf_counter() - started:.1f} s"
        )
        rows.append(
            f'<figure><img src="{name}" alt="{summary}"><figcaption>{summary}</figcaption></figure>'
        )
        print(summary.replace("·", "|"), flush=True)
    (target / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    page = target / "index.html"
    page.write_text(
        "<!doctype html><html lang='pl'><head><meta charset='utf-8'><title>Silnik siatek v3</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:16px;background:#111;color:#eee}"
        "main{display:grid;grid-template-columns:repeat(auto-fill,minmax(640px,1fr));gap:18px}"
        "figure{margin:0}img{width:100%;display:block}"
        "figcaption{font-size:14px;padding:4px 0}</style>"
        "</head><body><h1>Silnik siatek v3 — podgląd</h1>"
        "<p>Zielona siatka: plansza pełna. Żółta: częściowa (czerwone X = komórka niedostępna)."
        " Czerwona: do poprawy. Numer = pozycja planszy 1–9.</p>"
        f"<main>{''.join(rows)}</main></body></html>",
        encoding="utf-8",
    )
    return page


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="photo files or directories")
    parser.add_argument("--per-dir", type=int, default=3, help="photos per directory (0 = all)")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-width", type=int, default=1400)
    arguments = parser.parse_args(argv)
    page = run(arguments.inputs, arguments.per_dir, arguments.output_dir, arguments.max_width)
    print(page.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
