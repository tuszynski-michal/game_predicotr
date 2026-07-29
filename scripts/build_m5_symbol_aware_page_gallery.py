"""Build a deterministic page-level gallery for the final geometry gate."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, cast

import cv2
import numpy as np
from numpy.typing import NDArray

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = (
    ROOT / "ai_docs" / "quality" / "m5-board-cell-crops-v5-symbol-aware-affine-report.json"
)
DEFAULT_MANIFEST = ROOT / "ai_docs" / "quality" / "m5-corpus-manifest.json"
DEFAULT_CROP_ROOT = ROOT / "artifacts" / "m5-board-crops"
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "m5-symbol-aware-page-review"
GALLERY_VERSION = "m5-symbol-aware-page-gallery-v1"
TILE_WIDTH = 300
TILE_HEIGHT = 180
TILE_HEADER = 28
GRID_COLUMNS = 3
GRID_ROWS = 3


class GalleryError(ValueError):
    """Stable gallery generation error."""


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise GalleryError(f"{label} must be an object.")
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise GalleryError(f"{label} must be an array.")
    return cast(Sequence[object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise GalleryError(f"{label} must be non-empty text.")
    return value


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise GalleryError(f"{label} must be an integer.")
    return value


def _load_json(path: Path, label: str) -> tuple[bytes, Mapping[str, object]]:
    try:
        content = path.read_bytes()
        value: Any = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise GalleryError(f"{label} cannot be read.") from error
    return content, _mapping(value, label)


def _safe_crop_path(root: Path, value: object, namespace: str) -> Path:
    relative = PurePosixPath(_text(value, "overlayRelativePath"))
    if (
        relative.is_absolute()
        or not relative.parts
        or relative.parts[0] != namespace
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise GalleryError("Overlay path leaves the expected namespace.")
    root = root.resolve(strict=True)
    path = (root / Path(*relative.parts)).resolve(strict=True)
    if not path.is_relative_to(root):
        raise GalleryError("Overlay path leaves the crop root.")
    return path


def _decode_rgb(path: Path) -> NDArray[np.uint8]:
    content = path.read_bytes()
    bgr = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        raise GalleryError("Overlay cannot be decoded.")
    return cast(NDArray[np.uint8], cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def _encode_png(rgb: NDArray[np.uint8]) -> bytes:
    encoded, buffer = cv2.imencode(
        ".png",
        cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
        [cv2.IMWRITE_PNG_COMPRESSION, 6],
    )
    if not encoded:
        raise GalleryError("Contact sheet cannot be encoded.")
    return bytes(buffer)


def _write_atomic(path: Path, content: bytes) -> None:
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


def _tile(
    overlay: NDArray[np.uint8],
    *,
    sequence_number: int,
    position: int,
    residual: float,
) -> NDArray[np.uint8]:
    resized = cv2.resize(
        overlay,
        (TILE_WIDTH, TILE_HEIGHT),
        interpolation=cv2.INTER_AREA,
    )
    header = np.full((TILE_HEADER, TILE_WIDTH, 3), (8, 15, 24), dtype=np.uint8)
    cv2.putText(
        header,
        f"seq {sequence_number} | pos {position} | p95 {residual:.2f}px",
        (8, 19),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (235, 247, 255),
        1,
        cv2.LINE_AA,
    )
    return cast(NDArray[np.uint8], np.concatenate((header, resized), axis=0))


def _contact_sheet(
    image: Mapping[str, object],
    manifest: Mapping[str, object],
    crop_root: Path,
    namespace: str,
) -> tuple[bytes, float]:
    start = _integer(manifest.get("expectedSequenceStart"), "expectedSequenceStart")
    tiles: list[NDArray[np.uint8]] = []
    max_residual = 0.0
    for raw in _sequence(image.get("boards"), "image.boards"):
        board = _mapping(raw, "image.board")
        position = _integer(board.get("positionIndex"), "positionIndex")
        refinement = _mapping(board.get("symbolRefinement"), "symbolRefinement")
        residual_value = refinement.get("refinedP95ResidualPx")
        if not isinstance(residual_value, int | float) or isinstance(residual_value, bool):
            raise GalleryError("Board residual is invalid.")
        residual = float(residual_value)
        max_residual = max(max_residual, residual)
        tiles.append(
            _tile(
                _decode_rgb(
                    _safe_crop_path(
                        crop_root,
                        board.get("overlayRelativePath"),
                        namespace,
                    )
                ),
                sequence_number=start + position,
                position=position,
                residual=residual,
            )
        )
    blank = np.full(
        (TILE_HEADER + TILE_HEIGHT, TILE_WIDTH, 3),
        (5, 10, 16),
        dtype=np.uint8,
    )
    while len(tiles) < GRID_COLUMNS * GRID_ROWS:
        tiles.append(blank.copy())
    rows = [
        np.concatenate(
            tiles[row * GRID_COLUMNS : (row + 1) * GRID_COLUMNS],
            axis=1,
        )
        for row in range(GRID_ROWS)
    ]
    return _encode_png(cast(NDArray[np.uint8], np.concatenate(rows, axis=0))), max_residual


def _gallery_html(
    cards: Sequence[Mapping[str, object]],
    *,
    total_image_count: int,
    board_count: int,
    cropper_version: str,
) -> bytes:
    content = []
    for card in sorted(
        cards,
        key=lambda item: (
            -float(cast(float, item["maxResidualPx"])),
            cast(str, item["imageId"]),
        ),
    ):
        content.append(
            f"""
            <article>
              <header>
                <h2>{html.escape(cast(str, card["imageId"]))}</h2>
                <p>{html.escape(cast(str, card["sourceGroup"]))}</p>
                <p>{html.escape(cast(str, card["relativePath"]))}</p>
                <p>maks. P95: {card["maxResidualPx"]} px</p>
              </header>
              <img src="{html.escape(cast(str, card["contactSheetRelativePath"]))}"
                   alt="Plansze dla {html.escape(cast(str, card["imageId"]))}" />
            </article>
            """
        )
    return f"""<!doctype html>
<html lang="pl">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>M5 — pełna bramka geometrii symbol-aware</title>
    <style>
      :root {{ color-scheme: dark; font-family: Inter, system-ui, sans-serif; }}
      body {{ margin: 0; padding: 28px; background: #07111b; color: #edf7ff; }}
      main {{ max-width: 1120px; margin: auto; }}
      .lead {{ color: #aac0cf; line-height: 1.55; }}
      article {{
        margin: 24px 0; overflow: hidden; border: 1px solid #1e4055;
        border-radius: 14px; background: #0c1b27;
      }}
      article header {{ padding: 14px 18px 8px; }}
      h2 {{ margin: 0 18px 5px 0; display: inline-block; }}
      article p {{ margin: 0 20px 6px 0; display: inline-block; color: #aac0cf; }}
      img {{ display: block; width: 100%; height: auto; background: #020609; }}
    </style>
  </head>
  <body>
    <main>
      <h1>Pełna bramka geometrii symbol-aware</h1>
      <p class="lead">
        Automatycznie ukończone strony: {len(cards)}/{total_image_count};
        zapisane plansze: {board_count}. Każdy kafel pokazuje końcową planszę
        5 × 3 z zieloną siatką. Strony są posortowane od najwyższego residualu.
        Sprawdź, czy żaden symbol nie jest przecięty lub utracony.
        Wersja: {html.escape(cropper_version)}.
      </p>
      {"".join(content)}
    </main>
  </body>
</html>
""".encode()


def build_gallery(
    *,
    report_path: Path,
    manifest_path: Path,
    crop_root: Path,
    output_root: Path,
) -> dict[str, object]:
    report_bytes, report = _load_json(report_path, "cropReport")
    manifest_bytes, manifest = _load_json(manifest_path, "corpusManifest")
    cropper_version = _text(report.get("cropperVersion"), "cropperVersion")
    if cropper_version not in {
        "board-cell-crops-v5-symbol-aware-affine-v1",
        "board-cell-crops-v6-detector-symbol-aware-affine-v1",
    } or report.get("status") not in {"cropped", "needs_review"}:
        raise GalleryError("A supported symbol-aware crop report is required.")
    manifest_by_source = {
        _text(item.get("sha256"), "manifest.sha256"): item
        for raw in _sequence(manifest.get("images"), "manifest.images")
        for item in [_mapping(raw, "manifest.image")]
    }
    cards: list[dict[str, object]] = []
    for raw in _sequence(report.get("images"), "cropReport.images"):
        image = _mapping(raw, "cropReport.image")
        if image.get("status") != "cropped":
            continue
        source = _text(image.get("sourceChecksumSha256"), "sourceChecksumSha256")
        manifest_image = manifest_by_source.get(source)
        if manifest_image is None:
            raise GalleryError("Crop source is missing from the manifest.")
        image_id = _text(manifest_image.get("id"), "manifest.id")
        content, max_residual = _contact_sheet(
            image,
            manifest_image,
            crop_root,
            cropper_version,
        )
        relative = (PurePosixPath("pages") / f"{image_id}.png").as_posix()
        _write_atomic(output_root / Path(*PurePosixPath(relative).parts), content)
        cards.append(
            {
                "contactSheetChecksumSha256": hashlib.sha256(content).hexdigest(),
                "contactSheetRelativePath": relative,
                "imageId": image_id,
                "maxResidualPx": round(max_residual, 4),
                "relativePath": _text(
                    manifest_image.get("relativePath"),
                    "manifest.relativePath",
                ),
                "sourceGroup": _text(
                    manifest_image.get("sourceGroup"),
                    "manifest.sourceGroup",
                ),
            }
        )
    total_image_count = _integer(report.get("imageCount"), "imageCount")
    board_count = _integer(report.get("boardCount"), "boardCount")
    _write_atomic(
        output_root / "index.html",
        _gallery_html(
            cards,
            total_image_count=total_image_count,
            board_count=board_count,
            cropper_version=cropper_version,
        ),
    )
    document = {
        "cards": cards,
        "cropReportSha256": hashlib.sha256(report_bytes).hexdigest(),
        "galleryVersion": GALLERY_VERSION,
        "imageCount": len(cards),
        "totalImageCount": total_image_count,
        "boardCount": board_count,
        "cropperVersion": cropper_version,
        "manifestSha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "status": "waiting_for_owner_review",
        "trainingAllowed": False,
    }
    _write_atomic(
        output_root / "gallery.json",
        (json.dumps(document, indent=2, sort_keys=True) + "\n").encode(),
    )
    return document


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--crop-root", type=Path, default=DEFAULT_CROP_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _args()
    try:
        before = (
            (args.output_root / "gallery.json").read_bytes()
            if args.check and (args.output_root / "gallery.json").exists()
            else None
        )
        gallery = build_gallery(
            report_path=args.report,
            manifest_path=args.manifest,
            crop_root=args.crop_root,
            output_root=args.output_root,
        )
        current = (args.output_root / "gallery.json").read_bytes()
        if args.check and before != current:
            raise GalleryError("Page gallery was stale.")
        print(
            json.dumps(
                {
                    "imageCount": gallery["imageCount"],
                    "output": str((args.output_root / "index.html").resolve()),
                    "sha256": hashlib.sha256(current).hexdigest(),
                    "status": gallery["status"],
                },
                sort_keys=True,
            )
        )
        return 0
    except (GalleryError, OSError, json.JSONDecodeError) as error:
        print(
            json.dumps({"code": "SYMBOL_AWARE_GALLERY_FAILED", "message": str(error)}),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
