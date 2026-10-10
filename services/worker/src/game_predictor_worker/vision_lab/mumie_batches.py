"""Create-only review batches and unlabelled symbol crops from complete Mumie photos.

Reads existing lab state; never writes annotations or connects to the database.
Proposal overlays remain proposals. Crop metadata never claims symbol approval.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from .assisted_annotation import (
    open_proposals,
    photo_view,
    read_store_state,
    store_snapshot_id,
    workflow_game,
)
from .catalog import Catalog
from .contracts import Board, Point, Topology
from .geometry import cell_quads, crop_cell
from .snapshot import canonical

FORMAT = "mumie-review-batches-v1"
SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp"})


def checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def chunks(items: Sequence[Any], size: int) -> list[list[Any]]:
    if not 1 <= size <= 50:
        raise ValueError("BATCH_SIZE_OUT_OF_RANGE")
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


def match_folder(folder: Path, catalog: Catalog) -> dict[str, Any]:
    """Every input file must match an existing Mumie source by bytes, not name."""
    sources: dict[str, list[str]] = {}
    for source in catalog.sources.values():
        try:
            if workflow_game(source) == "mumie":
                sources.setdefault(source.sha256, []).append(source.id)
        except ValueError:
            continue
    rows = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUFFIXES:
            continue
        if path.is_symlink():
            raise ValueError("SOURCE_LINK_FORBIDDEN")
        sha = checksum(path)
        rows.append(
            {
                "file": path.relative_to(folder).as_posix(),
                "sha256": sha,
                "source_ids": sorted(sources.get(sha, [])),
            }
        )
    if not rows:
        raise ValueError("SOURCE_FOLDER_EMPTY")
    return {
        "files": rows,
        "missing": [r["file"] for r in rows if not r["source_ids"]],
        "unique": len({r["sha256"] for r in rows}),
    }


def eligible_boards(view: dict[str, Any]) -> list[dict[str, Any]]:
    """Incomplete photos contribute zero crops, even if individual boards are approved."""
    if not view["complete"]:
        return []
    boards = sorted(
        (b for b in view["boards"] if b["presence"] == "present"), key=lambda b: b["board_index"]
    )
    if not boards or any(
        b["presence"] != "present" or not b["full_approved"] or len(b["nodes"]) != 24
        for b in boards
    ):
        raise ValueError("COMPLETE_PHOTO_INVALID")
    return boards


def verify(directory: Path) -> dict[str, Any]:
    """Verify all bytes in a published artifact in a fresh process, without rewriting it."""
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    payload: dict[str, Any] = manifest["payload"]
    if manifest["sha256"] != hashlib.sha256(canonical(payload)).hexdigest():
        raise ValueError("MANIFEST_CHECKSUM_MISMATCH")
    if payload["format"] != FORMAT or payload["artifact_id"] != directory.name:
        raise ValueError("MANIFEST_ID_MISMATCH")
    root = directory.resolve()
    for relative, expected in payload["files"].items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or path.is_symlink() or checksum(path) != expected:
            raise ValueError("ARTIFACT_CHECKSUM_MISMATCH")
    return payload


def _json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _overlay(image: Image.Image, view: dict[str, Any]) -> Image.Image:
    out = image.copy()
    draw = ImageDraw.Draw(out)
    for board in view["boards"]:
        if len(board["nodes"]) != 24:
            continue
        _grid(draw, board["nodes"], "#26eb72" if board["full_approved"] else "#ee9c35")
    for proposal in view["proposals"]:
        if (
            proposal["dismissed"]
            or proposal["used_by"] is not None
            or proposal["covered_by"] is not None
        ):
            continue
        _grid(draw, proposal["nodes"], "#ff593e")
    out.thumbnail((1400, 1400))
    return out


def _grid(draw: ImageDraw.ImageDraw, nodes: list[list[float]], colour: str) -> None:
    for row in range(4):
        draw.line([tuple(p) for p in nodes[row * 6 : row * 6 + 6]], fill=colour, width=3)
    for column in range(6):
        draw.line([tuple(nodes[row * 6 + column]) for row in range(4)], fill=colour, width=3)


def prepare(
    catalog_path: Path,
    annotations: Path,
    proposals: Path,
    folder: Path,
    output: Path,
    batch_size: int = 50,
) -> Path:
    catalog = Catalog(catalog_path)
    matched = match_folder(folder, catalog)
    if matched["missing"]:
        raise ValueError("SOURCE_IMPORT_INCOMPLETE: " + ", ".join(matched["missing"]))
    state = read_store_state(annotations, catalog)
    book = open_proposals(proposals, catalog, ("mumie",))
    plan = {
        "format": FORMAT,
        "snapshot_id": store_snapshot_id(catalog),
        "annotation_revision": state.revision,
        "proposal_sets": list(book.sets),
        "batch_size": batch_size,
        "folder": matched,
        "source_ids": [item["source_id"] for item in book.items],
    }
    artifact_id = hashlib.sha256(canonical(plan)).hexdigest()
    output.mkdir(parents=True, exist_ok=True)
    destination = output / artifact_id
    if destination.exists():
        verify(destination)
        return destination
    temporary = output / (".pending-" + uuid.uuid4().hex)
    temporary.mkdir()
    photos = []
    crops = []
    for item in book.items:
        if item["queue_index"] % 10 == 0:
            print(f"Preparing photo {item['queue_index'] + 1}/{len(book.items)}", flush=True)
        source_id = item["source_id"]
        source = catalog.sources[source_id]
        view = photo_view(state, catalog, book, source_id)
        image = catalog.image(source).convert("RGB")
        photo_dir = temporary / "photos" / source_id
        photo_dir.mkdir(parents=True)
        _overlay(image, view).save(photo_dir / "overlay.jpg", quality=90)
        photo = {
            "source_id": source_id,
            "source_sha256": source.sha256,
            "filename": source.filename,
            "queue_index": item["queue_index"],
            "complete": view["complete"],
            "board_revisions": view["board_revisions"],
            "proposal_set_id": view["proposal_set_id"],
            "overlay": f"photos/{source_id}/overlay.jpg",
            "boards": view["boards"],
            "proposals": view["proposals"],
        }
        approved = eligible_boards(view)
        rgb = np.asarray(image)
        sheet = Image.new("RGB", (3 * 500, max(1, (len(approved) + 2) // 3) * 326), "#171a21")
        sheet_draw = ImageDraw.Draw(sheet)
        for board_number, annotation in enumerate(approved):
            board = Board(
                position_index=annotation["board_index"],
                status="complete",
                nodes=[Point(x=p[0], y=p[1], provenance="human") for p in annotation["nodes"]],
            )
            left, top = (board_number % 3) * 500, (board_number // 3) * 326
            sheet_draw.text(
                (left + 4, top + 4),
                f"Board {annotation['board_index'] + 1} / unlabelled",
                fill="white",
            )
            for cell_index, quad in enumerate(cell_quads(board, Topology())):
                pixels = crop_cell(rgb, quad)
                if pixels is None:
                    raise ValueError("APPROVED_CROP_OUTSIDE_SOURCE")
                name = f"b{board.position_index + 1:02d}-c{cell_index + 1:02d}.png"
                Image.fromarray(pixels).save(photo_dir / name)
                sheet.paste(
                    Image.fromarray(pixels),
                    (left + (cell_index % 5) * 96, top + 26 + (cell_index // 5) * 96),
                )
                crops.append(
                    {
                        "source_id": source_id,
                        "source_sha256": source.sha256,
                        "board_index": board.position_index,
                        "cell_index": cell_index,
                        "geometry_revision": annotation["revision"],
                        "geometry_actor": annotation["actor"],
                        "quad": quad.tolist(),
                        "path": f"photos/{source_id}/{name}",
                        "symbol": None,
                        "gold_frame": None,
                        "symbol_training_eligible": False,
                    }
                )
        if approved:
            sheet.save(photo_dir / "symbols.jpg", quality=93)
            photo["symbol_sheet"] = f"photos/{source_id}/symbols.jpg"
        photos.append(photo)
    batches = chunks(photos, batch_size)
    for number, batch in enumerate(batches, start=1):
        _json(temporary / f"batch-{number:02d}.json", batch)
    _json(temporary / "photos.json", photos)
    _json(temporary / "crops.json", crops)
    summary = {
        "photos": len(photos),
        "complete_photos": sum(p["complete"] for p in photos),
        "pending_photos": sum(not p["complete"] for p in photos),
        "crops": len(crops),
        "batches": [len(batch) for batch in batches],
        "folder_files": len(matched["files"]),
        "folder_unique": matched["unique"],
        "missing_folder_files": matched["missing"],
    }
    _json(temporary / "summary.json", summary)
    payload = {
        **plan,
        "artifact_id": artifact_id,
        "summary": summary,
        "files": {
            p.relative_to(temporary).as_posix(): checksum(p)
            for p in sorted(temporary.rglob("*"))
            if p.is_file()
        },
    }
    _json(
        temporary / "manifest.json",
        {"payload": payload, "sha256": hashlib.sha256(canonical(payload)).hexdigest()},
    )
    temporary.rename(destination)
    verify(destination)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--annotations", type=Path)
    parser.add_argument("--proposals", type=Path)
    parser.add_argument("--folder", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()
    if args.verify:
        print(json.dumps(verify(args.verify)["summary"], ensure_ascii=False))
        return
    if any(
        getattr(args, key) is None
        for key in ("catalog", "annotations", "proposals", "folder", "output")
    ):
        parser.error("all preparation paths are required")
    result = prepare(
        args.catalog, args.annotations, args.proposals, args.folder, args.output, args.batch_size
    )
    print(json.dumps({"directory": str(result), **verify(result)["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
