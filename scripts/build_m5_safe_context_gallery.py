"""Build full-page and rejected-sequence galleries from final safe-context cells."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, cast

import cv2
import numpy as np
from numpy.typing import NDArray

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "ai_docs" / "quality" / "m5-corpus-manifest.json"
DEFAULT_REPORT = (
    ROOT / "ai_docs" / "quality" / "m5-board-cell-crops-v9-safe-context-shifted-overlap-report.json"
)
DEFAULT_FEEDBACK = ROOT / "ai_docs" / "quality" / "m5-v7-owner-visual-feedback.json"
DEFAULT_CROP_ROOT = ROOT / "artifacts" / "m5-board-crops"
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "m5-safe-context-v9-review"

CROPPER_VERSION = "board-cell-crops-v9-safe-context-shifted-overlap-v1"
BOARD_COLUMNS = 5
BOARD_ROWS = 3
PAGE_COLUMNS = 3
PAGE_ROWS = 3
CELL_BORDER = 2
BOARD_HEADER = 28


class SafeContextGalleryError(ValueError):
    pass


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SafeContextGalleryError(f"{label} must be an object.")
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise SafeContextGalleryError(f"{label} must be an array.")
    return cast(Sequence[object], value)


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise SafeContextGalleryError(f"{label} must be an integer.")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise SafeContextGalleryError(f"{label} must be text.")
    return value


def _load_json(path: Path) -> Mapping[str, object]:
    try:
        value: Any = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise SafeContextGalleryError(f"Cannot read {path}.") from error
    return _mapping(value, path.name)


def _safe_path(root: Path, value: object) -> Path:
    relative = PurePosixPath(_text(value, "relativePath"))
    if relative.is_absolute() or not relative.parts or relative.parts[0] != CROPPER_VERSION:
        raise SafeContextGalleryError("Cell path is outside the safe-context namespace.")
    path = (root / Path(*relative.parts)).resolve(strict=True)
    if not path.is_relative_to(root):
        raise SafeContextGalleryError("Cell path escapes its artifact root.")
    return path


def _decode(path: Path) -> NDArray[np.uint8]:
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise SafeContextGalleryError(f"Cannot decode {path}.")
    return cast(NDArray[np.uint8], cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def _encode(rgb: NDArray[np.uint8]) -> bytes:
    encoded, buffer = cv2.imencode(
        ".png",
        cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
        [cv2.IMWRITE_PNG_COMPRESSION, 6],
    )
    if not encoded:
        raise SafeContextGalleryError("Cannot encode gallery image.")
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


def _cell_with_border(rgb: NDArray[np.uint8]) -> NDArray[np.uint8]:
    return cast(
        NDArray[np.uint8],
        cv2.copyMakeBorder(
            rgb,
            CELL_BORDER,
            CELL_BORDER,
            CELL_BORDER,
            CELL_BORDER,
            cv2.BORDER_CONSTANT,
            value=(20, 220, 95),
        ),
    )


def _board_tile(
    board: Mapping[str, object],
    *,
    crop_root: Path,
    sequence_number: int,
) -> NDArray[np.uint8]:
    cells = sorted(
        (_mapping(raw, "board.cell") for raw in _sequence(board.get("cells"), "board.cells")),
        key=lambda cell: (
            _integer(cell.get("rowIndex"), "rowIndex"),
            _integer(cell.get("columnIndex"), "columnIndex"),
        ),
    )
    if len(cells) != BOARD_ROWS * BOARD_COLUMNS:
        raise SafeContextGalleryError("Every board must contain 15 cells.")
    bordered = [
        _cell_with_border(_decode(_safe_path(crop_root, cell.get("relativePath"))))
        for cell in cells
    ]
    rows = [
        np.concatenate(
            bordered[row * BOARD_COLUMNS : (row + 1) * BOARD_COLUMNS],
            axis=1,
        )
        for row in range(BOARD_ROWS)
    ]
    sheet = cast(NDArray[np.uint8], np.concatenate(rows, axis=0))
    header = np.full((BOARD_HEADER, sheet.shape[1], 3), (7, 14, 22), dtype=np.uint8)
    cv2.putText(
        header,
        f"seq {sequence_number}",
        (8, 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.52,
        (235, 247, 255),
        1,
        cv2.LINE_AA,
    )
    return cast(NDArray[np.uint8], np.concatenate((header, sheet), axis=0))


def _page_sheet(
    image: Mapping[str, object],
    manifest_image: Mapping[str, object],
    crop_root: Path,
) -> bytes:
    start = _integer(manifest_image.get("expectedSequenceStart"), "expectedSequenceStart")
    boards = sorted(
        (_mapping(raw, "image.board") for raw in _sequence(image.get("boards"), "image.boards")),
        key=lambda board: _integer(board.get("positionIndex"), "positionIndex"),
    )
    tiles = [
        _board_tile(
            board,
            crop_root=crop_root,
            sequence_number=start + _integer(board.get("positionIndex"), "positionIndex"),
        )
        for board in boards
    ]
    blank = np.full(tiles[0].shape, (5, 10, 16), dtype=np.uint8)
    while len(tiles) < PAGE_COLUMNS * PAGE_ROWS:
        tiles.append(blank.copy())
    rows = [
        np.concatenate(
            tiles[row * PAGE_COLUMNS : (row + 1) * PAGE_COLUMNS],
            axis=1,
        )
        for row in range(PAGE_ROWS)
    ]
    return _encode(cast(NDArray[np.uint8], np.concatenate(rows, axis=0)))


def _html_page(
    cards: Sequence[Mapping[str, object]],
    *,
    title: str,
    lead: str,
) -> bytes:
    body = "".join(
        f"<article><h2>{html.escape(cast(str, card['title']))}</h2>"
        f'<img src="{html.escape(cast(str, card["relativePath"]))}" '
        f'alt="{html.escape(cast(str, card["title"]))}"></article>'
        for card in cards
    )
    return (
        "<!doctype html><html lang='pl'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)}</title><style>"
        "body{margin:24px;background:#07111b;color:#edf7ff;font-family:system-ui}"
        "p{color:#aac0cf}article{margin:24px 0;background:#0c1b27;"
        "border:1px solid #1e4055;border-radius:12px;overflow:hidden}"
        "h2{padding:0 16px}img{width:100%;display:block}</style></head><body>"
        f"<h1>{html.escape(title)}</h1><p>{html.escape(lead)}</p>{body}</body></html>"
    ).encode()


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--feedback", type=Path, default=DEFAULT_FEEDBACK)
    parser.add_argument("--crop-root", type=Path, default=DEFAULT_CROP_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def main() -> int:
    args = _args()
    try:
        manifest = _load_json(args.manifest)
        report = _load_json(args.report)
        feedback = _load_json(args.feedback)
        if report.get("cropperVersion") != CROPPER_VERSION or report.get("status") != "cropped":
            raise SafeContextGalleryError("A complete safe-context report is required.")
        crop_root = args.crop_root.resolve(strict=True)
        output_root = args.output_root.resolve()
        manifest_by_source = {
            _text(image.get("sha256"), "manifest.sha256"): image
            for raw in _sequence(manifest.get("images"), "manifest.images")
            for image in [_mapping(raw, "manifest.image")]
        }
        report_by_source = {
            _text(image.get("sourceChecksumSha256"), "sourceChecksumSha256"): image
            for raw in _sequence(report.get("images"), "report.images")
            for image in [_mapping(raw, "report.image")]
        }
        page_cards: list[dict[str, object]] = []
        board_by_sequence: dict[int, Mapping[str, object]] = {}
        for source, image in sorted(
            report_by_source.items(),
            key=lambda item: _text(manifest_by_source[item[0]].get("id"), "imageId"),
        ):
            manifest_image = manifest_by_source[source]
            image_id = _text(manifest_image.get("id"), "imageId")
            content = _page_sheet(image, manifest_image, crop_root)
            relative = f"pages/{image_id}.png"
            _write_atomic(output_root / Path(*PurePosixPath(relative).parts), content)
            page_cards.append(
                {
                    "checksumSha256": hashlib.sha256(content).hexdigest(),
                    "relativePath": relative,
                    "title": image_id,
                }
            )
            start = _integer(
                manifest_image.get("expectedSequenceStart"),
                "expectedSequenceStart",
            )
            for raw_board in _sequence(image.get("boards"), "image.boards"):
                board = _mapping(raw_board, "image.board")
                board_by_sequence[start + _integer(board.get("positionIndex"), "positionIndex")] = (
                    board
                )
        rejected_cards: list[dict[str, object]] = []
        for raw_sequence in _sequence(
            feedback.get("listedSequenceNumbers"),
            "feedback.listedSequenceNumbers",
        ):
            sequence_number = _integer(raw_sequence, "sequenceNumber")
            tile = _board_tile(
                board_by_sequence[sequence_number],
                crop_root=crop_root,
                sequence_number=sequence_number,
            )
            content = _encode(tile)
            relative = f"rejected/seq-{sequence_number:03d}.png"
            _write_atomic(output_root / Path(*PurePosixPath(relative).parts), content)
            rejected_cards.append(
                {
                    "checksumSha256": hashlib.sha256(content).hexdigest(),
                    "relativePath": relative,
                    "title": f"Seq {sequence_number}",
                }
            )
        _write_atomic(
            output_root / "index.html",
            _html_page(
                page_cards,
                title="M5 safe-context — 43 strony",
                lead=(
                    "Finalne cropy 90×90. Zielone ramki oddzielają obrazy; nie są częścią danych."
                ),
            ),
        )
        _write_atomic(
            output_root / "rejected.html",
            _html_page(
                rejected_cards,
                title="M5 safe-context — 92 odrzucone sekwencje v7",
                lead="Nowe finalne cropy 90×90 tylko dla wcześniej zgłoszonych sekwencji.",
            ),
        )
        gallery = {
            "cropperVersion": CROPPER_VERSION,
            "fullPageCount": len(page_cards),
            "pageCards": page_cards,
            "rejectedCardCount": len(rejected_cards),
            "rejectedCards": rejected_cards,
            "schemaVersion": 1,
            "status": "waiting_for_owner_review",
        }
        content = (
            json.dumps(gallery, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode()
        _write_atomic(output_root / "gallery.json", content)
        print(
            json.dumps(
                {
                    "fullPageCount": len(page_cards),
                    "output": str((output_root / "index.html").resolve()),
                    "rejectedCardCount": len(rejected_cards),
                    "rejectedOutput": str((output_root / "rejected.html").resolve()),
                    "sha256": hashlib.sha256(content).hexdigest(),
                },
                sort_keys=True,
            )
        )
        return 0
    except (SafeContextGalleryError, KeyError, OSError, json.JSONDecodeError) as error:
        print(
            json.dumps(
                {"message": str(error), "status": "failed"},
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
