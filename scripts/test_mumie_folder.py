"""Bounded, resumable offline comparison of exported grids on operator photos.

No training, database access, annotation writes or model activation. Filename
ranges are diagnostic metadata; they never supply final sequence assignments.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from game_predictor_worker.vision_lab.annotations import exclusive_bounded
from game_predictor_worker.vision_lab.assisted_annotation import (
    photo_complete,
    read_store_state,
    source_rows,
    workflow_game,
)
from game_predictor_worker.vision_lab.catalog import MAX_SOURCE_BYTES, Catalog
from game_predictor_worker.vision_lab.contracts import Board, Point, Topology
from game_predictor_worker.vision_lab.geometry import cell_quads, crop_cell
from game_predictor_worker.vision_lab.neural_grid_inference import (
    onnx_engine,
    structurally_valid,
)
from game_predictor_worker.vision_lab.neural_grid_metrics import (
    BoardMatch,
    PhotoEvaluation,
    evaluate_photo,
    summarize,
)
from game_predictor_worker.vision_lab.snapshot import canonical
from PIL import Image, ImageDraw, ImageOps

FORMAT = "mumie-folder-comparison-v1"
RANGE = re.compile(r"^seq_(\d+)-(\d+)(?: — kopia)?\.(?:jpg|jpeg|png|webp)$", re.IGNORECASE)


def sha(path: Path) -> str:
    if path.is_symlink():
        raise ValueError("SOURCE_LINK_FORBIDDEN")
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def range_key(path: Path) -> tuple[int, int, str]:
    match = RANGE.fullmatch(path.name)
    if match is None or int(match[2]) < int(match[1]):
        raise ValueError("SOURCE_RANGE_INVALID: " + path.name)
    # Prefer the original filename when an exact byte duplicate carries the
    # Windows Polish copy suffix. A distinct image is never deduplicated by name.
    return int(match[1]), int(match[2]), ("1" if " — kopia" in path.stem else "0") + path.name


def select_rows(
    rows: list[dict[str, Any]], known: set[str], limit: int
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if limit < 1:
        raise ValueError("SAMPLE_LIMIT_INVALID")
    available: list[dict[str, Any]] = []
    seen: set[str] = set()
    duplicate, excluded = 0, 0
    for row in sorted(rows, key=lambda r: range_key(Path(r["path"]))):
        if row["sha256"] in seen:
            duplicate += 1
            continue
        seen.add(row["sha256"])
        if row["sha256"] in known:
            excluded += 1
            continue
        available.append(row)
    count = min(limit, len(available))
    indices = [0] if count == 1 else [i * (len(available) - 1) // (count - 1) for i in range(count)]
    return [available[i] for i in indices], {
        "files": len(rows),
        "duplicates": duplicate,
        "known_sha_excluded": excluded,
        "eligible": len(available),
        "selected": count,
    }


def write_new(path: Path, value: dict[str, Any]) -> None:
    envelope = {"payload": value, "sha256": hashlib.sha256(canonical(value)).hexdigest()}
    content = canonical(envelope)
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError("ARTIFACT_ALREADY_EXISTS_DIFFERENT")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".pending-" + uuid.uuid4().hex)
    with temporary.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.rename(path)


def read_bound(path: Path) -> dict[str, Any]:
    envelope = json.loads(path.read_bytes())
    value: dict[str, Any] = envelope["payload"]
    if envelope["sha256"] != hashlib.sha256(canonical(value)).hexdigest():
        raise ValueError("ARTIFACT_CHECKSUM_MISMATCH")
    return value


def load_image(row: dict[str, Any]) -> Image.Image:
    path = Path(row["path"])
    if path.is_symlink():
        raise ValueError("SOURCE_LINK_FORBIDDEN")
    with path.open("rb") as handle:
        content = handle.read(MAX_SOURCE_BYTES + 1)
    if len(content) > MAX_SOURCE_BYTES:
        raise ValueError("SOURCE_TOO_LARGE")
    if hashlib.sha256(content).hexdigest() != row["sha256"]:
        raise ValueError("SOURCE_CHECKSUM_CHANGED")
    with Image.open(io.BytesIO(content)) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def prepare(args: argparse.Namespace) -> None:
    folder = args.folder.resolve()
    if args.folder.is_symlink() or not folder.is_dir():
        raise ValueError("SOURCE_FOLDER_INVALID")
    catalog = Catalog(args.catalog)
    state = read_store_state(args.annotations, catalog)
    ledger = read_bound(args.ledger)
    complete = {
        key
        for key in state.assisted_photos
        if workflow_game(catalog.sources[key]) == "mumie"
        and photo_complete(state, catalog.sources[key])
    }
    previously_used = set(ledger["holdout"])
    known = {catalog.sources[key].sha256 for key in complete | previously_used}
    folder_rows = []
    for path in sorted(folder.iterdir(), key=lambda p: p.name):
        if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        start, end, _ = range_key(path)
        folder_rows.append(
            {
                "id": "folder-" + path.stem,
                "path": str(path),
                "sha256": sha(path),
                "kind": "folder",
                "range_start": start,
                "range_end": end,
                "expected_from_filename": end - start + 1,
                "labels": None,
            }
        )
        if len(folder_rows) % 500 == 0:
            print(f"Inventoried {len(folder_rows)} photos", flush=True)
    selected, inventory = select_rows(folder_rows, known, args.limit)
    if not selected:
        raise ValueError("NO_ELIGIBLE_FOLDER_PHOTOS")
    fresh = []
    for key in sorted(complete - previously_used):
        source = catalog.sources[key]
        path = catalog.paths[source.asset_id]
        if sha(path) != source.sha256:
            raise ValueError("APPROVED_SOURCE_CHANGED")
        fresh.append(
            {
                "id": "approved-" + key,
                "source_id": key,
                "path": str(path),
                "filename": source.filename,
                "sha256": source.sha256,
                "kind": "new_approved",
                "expected_from_filename": None,
                "labels": [
                    {
                        "board_index": annotation.board_index,
                        "revision": annotation.revision,
                        "nodes": [[p.x, p.y] for p in annotation.nodes],
                    }
                    for _, annotation in sorted(source_rows(state, key).items())
                    if annotation.presence == "present"
                ],
            }
        )
    models = {}
    for iteration in ("2", "3"):
        path = Path(ledger["iterations"][iteration]["bundle"])
        bundle = json.loads((path / "bundle.json").read_bytes())
        for name in ("screen.onnx", "board.onnx"):
            if sha(path / name) != bundle["files"][name]:
                raise ValueError("MODEL_FILE_CHANGED")
        models["iteration" + iteration] = {
            "path": str(path),
            "bundle_sha256": sha(path / "bundle.json"),
            "files": bundle["files"],
        }
    plan = {
        "format": FORMAT,
        "folder": str(folder),
        "inventory": inventory,
        "folder_inventory_sha256": hashlib.sha256(canonical(folder_rows)).hexdigest(),
        "annotation_revision": state.revision,
        "annotations_path": str(args.annotations.resolve()),
        "annotations_sha256": sha(args.annotations / "state.json"),
        "complete_photos": len(complete),
        "known_source_sha256": sorted(known),
        "new_approved_photos": len(fresh),
        "models": models,
        "rows": selected + fresh,
        "warning": "Same recording possible; board count is not geometry accuracy.",
    }
    write_new(args.output / "manifest.json", plan)
    print(json.dumps({"inventory": inventory, "new_approved": len(fresh)}), flush=True)


def validate_result(directory: Path, path: Path, binding: str) -> dict[str, Any]:
    row = read_bound(path)
    if row["binding"] != binding:
        raise ValueError("RESULT_FOREIGN_MANIFEST")
    root = directory.resolve()
    for relative, checksum in row["files"].items():
        asset = directory / relative
        if not asset.resolve().is_relative_to(root) or sha(asset) != checksum:
            raise ValueError("RESULT_FILE_CHANGED")
    return row


def render(
    image: Image.Image, boards: list[dict[str, Any]], directory: Path, colour: str
) -> dict[str, str]:
    directory.mkdir(parents=True, exist_ok=True)
    overlay = image.copy()
    draw = ImageDraw.Draw(overlay)
    rgb = np.asarray(image, dtype=np.uint8)
    sheet = Image.new("RGB", (1000, max(1, (len(boards) + 2) // 3) * 228), "#171a21")
    sheet_draw = ImageDraw.Draw(sheet)
    for index, row in enumerate(boards):
        nodes = row["nodes"]
        if nodes is None:
            continue
        tint = colour if row["valid"] else "#ef4444"
        for y in range(4):
            draw.line([tuple(p) for p in nodes[y * 6 : y * 6 + 6]], fill=tint, width=2)
        for x in range(6):
            draw.line([tuple(nodes[y * 6 + x]) for y in range(4)], fill=tint, width=2)
        draw.text(
            tuple(nodes[0]), str(index + 1), fill="white", stroke_width=1, stroke_fill="black"
        )
        left, top = (index % 3) * 333, (index // 3) * 228
        sheet_draw.text((left + 4, top + 4), f"Board {index + 1} / proposal", fill="white")
        if row["valid"]:
            board = Board(
                position_index=index,
                status="needs_review",
                nodes=[Point(x=p[0], y=p[1], provenance="model") for p in nodes],
            )
            for cell, quad in enumerate(cell_quads(board, Topology())):
                pixels = crop_cell(rgb, quad)
                if pixels is not None:
                    sheet.paste(
                        Image.fromarray(pixels).resize((64, 64)),
                        (left + cell % 5 * 64, top + 25 + cell // 5 * 64),
                    )
                else:
                    row["outside_cells"] += 1
    overlay.thumbnail((1600, 1600))
    files = {}
    for name, value in (("overlay.jpg", overlay), ("cells.jpg", sheet)):
        path = directory / name
        # Results are published only after complete assets; a partial attempt is
        # retained under its unique directory and never reused as a finished row.
        with path.open("xb") as handle:
            value.save(handle, format="JPEG", quality=92)
        files[name] = sha(path)
    return files


def run(args: argparse.Namespace) -> None:
    manifest = read_bound(args.output / "manifest.json")
    binding = hashlib.sha256(canonical(manifest)).hexdigest()
    model = manifest["models"][args.model]
    if sha(Path(model["path"]) / "bundle.json") != model["bundle_sha256"]:
        raise ValueError("MODEL_BUNDLE_CHANGED")
    for name in ("screen.onnx", "board.onnx"):
        if sha(Path(model["path"]) / name) != model["files"][name]:
            raise ValueError("MODEL_FILE_CHANGED")
    if sha(Path(manifest["annotations_path"]) / "state.json") != manifest["annotations_sha256"]:
        raise ValueError("ANNOTATIONS_CHANGED_REPREPARE_REQUIRED")
    remaining = []
    for row in manifest["rows"]:
        path = args.output / "results" / args.model / (row["id"] + ".json")
        if path.exists():
            validate_result(args.output, path, binding)
            if sha(Path(row["path"])) != row["sha256"]:
                raise ValueError("SOURCE_CHECKSUM_CHANGED")
        else:
            remaining.append(row)
    if not remaining:
        print(json.dumps({"model": args.model, "pending": 0, "recovered": len(manifest["rows"])}))
        return
    engine = onnx_engine(Path(model["path"]), args.threads)
    processed = 0
    for row in remaining[: args.max_photos]:
        print(f"{args.model}: {row['id']}", flush=True)
        image = load_image(row)
        started = time.perf_counter()
        detections = engine.analyse(np.asarray(image, dtype=np.uint8))
        seconds = time.perf_counter() - started
        boards = [
            {
                "nodes": d.nodes.tolist() if d.nodes is not None else None,
                "valid": d.nodes is not None and structurally_valid(d.nodes),
                "score": d.score,
                "reasons": d.reasons,
                "fit_inliers": d.fit_inliers,
                "outside_cells": 0,
            }
            for d in detections
        ]
        assets = args.output / "assets" / args.model / (row["id"] + "-" + uuid.uuid4().hex[:8])
        file_digests = render(
            image, boards, assets, "#22d3ee" if args.model == "iteration2" else "#fbbf24"
        )
        labels = row["labels"]
        evaluation = (
            evaluate_photo(
                row["id"],
                "operator_approved",
                [np.asarray(label["nodes"], dtype=np.float32) for label in labels],
                [
                    (np.asarray(b["nodes"], dtype=np.float32), bool(b["valid"]))
                    for b in boards
                    if b["nodes"] is not None
                ],
            ).as_dict()
            if labels is not None
            else None
        )
        result = {
            "binding": binding,
            "id": row["id"],
            "kind": row["kind"],
            "filename": row.get("filename", Path(row["path"]).name),
            "sha256": row["sha256"],
            "model": args.model,
            "model_version": engine.model_version,
            "detected": len(boards),
            "expected_from_filename": row["expected_from_filename"],
            "boards": boards,
            "evaluation": evaluation,
            "inference_seconds": seconds,
            "files": {
                (assets / name).relative_to(args.output).as_posix(): value
                for name, value in file_digests.items()
            },
        }
        write_new(args.output / "results" / args.model / (row["id"] + ".json"), result)
        processed += 1
        print(f"  {len(boards)} boards, {seconds:.2f} s", flush=True)
    print(
        json.dumps(
            {"model": args.model, "processed": processed, "pending": len(remaining) - processed}
        )
    )


def evaluation_object(row: dict[str, Any]) -> PhotoEvaluation:
    data = row["evaluation"]
    return PhotoEvaluation(
        data["image_id"],
        data["level"],
        data["expected"],
        data["predicted"],
        matches=[BoardMatch(**match) for match in data["matches"]],
        false_boards=data["false_boards"],
        duplicates=data["duplicates"],
        macro_cost=data["macro_cost"],
    )


def collect(directory: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    manifest = read_bound(directory / "manifest.json")
    binding = hashlib.sha256(canonical(manifest)).hexdigest()
    results = {}
    for model in manifest["models"]:
        results[model] = [
            validate_result(directory, directory / "results" / model / (r["id"] + ".json"), binding)
            for r in manifest["rows"]
        ]
    return manifest, results


def finish(args: argparse.Namespace) -> None:
    manifest, results = collect(args.output)
    summary = {"inventory": manifest["inventory"], "models": {}}
    for model, rows in results.items():
        folder = [r for r in rows if r["kind"] == "folder"]
        approved = [evaluation_object(r) for r in rows if r["evaluation"] is not None]
        summary["models"][model] = {
            "folder_photos": len(folder),
            "count_matches_filename": sum(
                r["detected"] == r["expected_from_filename"] for r in folder
            ),
            "detected_count_distribution": dict(Counter(str(r["detected"]) for r in folder)),
            "structurally_invalid_boards": sum(not b["valid"] for r in folder for b in r["boards"]),
            "outside_cells": sum(b["outside_cells"] for r in folder for b in r["boards"]),
            "supervised_new_photos": summarize(approved),
        }
    write_new(args.output / "summary.json", summary)
    write_gallery(args.output, results, summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


def write_gallery(
    directory: Path, results: dict[str, list[dict[str, Any]]], summary: dict[str, Any]
) -> None:
    pairs = []
    for older, current in zip(results["iteration2"], results["iteration3"], strict=True):
        if older["id"] != current["id"]:
            raise ValueError("PAIRED_SOURCE_MISMATCH")
        pairs.append(
            {
                "id": older["id"],
                "filename": older["filename"],
                "kind": older["kind"],
                "models": [
                    {
                        "count": row["detected"],
                        "overlay": next(p for p in row["files"] if p.endswith("overlay.jpg")),
                        "cells": next(p for p in row["files"] if p.endswith("cells.jpg")),
                    }
                    for row in (older, current)
                ],
                "anomaly": any(
                    row["detected"] != row["expected_from_filename"]
                    or any(not b["valid"] or b["outside_cells"] for b in row["boards"])
                    for row in (older, current)
                )
                if older["kind"] == "folder"
                else not all(row["evaluation"]["complete_correct"] for row in (older, current)),
            }
        )
    payload = json.dumps({"pairs": pairs, "summary": summary}, ensure_ascii=False).replace(
        "<", "\\u003c"
    )
    template = Path(__file__).with_name("mumie_folder_gallery.html").read_text(encoding="utf-8")
    path = directory / "index.html"
    content = template.replace("__DATA__", payload).encode("utf-8")
    if path.exists() and path.read_bytes() != content:
        raise ValueError("GALLERY_ALREADY_EXISTS_DIFFERENT")
    if not path.exists():
        with path.open("xb") as handle:
            handle.write(content)


def reference_audit(args: argparse.Namespace) -> None:
    """Keep approval provenance visible; self-origin targets are not a blind test."""
    manifest, _ = collect(args.output)
    state_path = Path(manifest["annotations_path"]) / "state.json"
    if sha(state_path) != manifest["annotations_sha256"]:
        raise ValueError("ANNOTATIONS_CHANGED_REPREPARE_REQUIRED")
    state = read_bound(state_path)["state"]
    ledger = read_bound(args.ledger)
    proposal_models = {
        Path(row["proposals"]).name: "iteration" + key
        for key, row in ledger["iterations"].items()
        if row.get("proposals")
    }
    origins: Counter[str] = Counter()
    sets: Counter[str] = Counter()
    models: Counter[str] = Counter()
    rows = []
    for row in manifest["rows"]:
        if row["kind"] != "new_approved":
            continue
        owners = state["assisted_photos"][row["source_id"]]["boards"]
        for label in row["labels"]:
            owner = owners[str(label["board_index"])]
            if owner["annotation_revision"] != label["revision"]:
                raise ValueError("REFERENCE_REVISION_CHANGED")
            origin = owner["origin"]
            proposal_set = owner.get("proposal_set_id") or "none"
            model = proposal_models.get(proposal_set, "unknown")
            origins[origin] += 1
            sets[proposal_set] += 1
            models[model] += 1
            rows.append(
                {
                    "source_id": row["source_id"],
                    "board_index": label["board_index"],
                    "revision": label["revision"],
                    "actor": owner["actor"],
                    "origin": origin,
                    "proposal_set": proposal_set,
                    "proposal_model": model,
                }
            )
    audit = {
        "manifest_binding": hashlib.sha256(canonical(manifest)).hexdigest(),
        "origins": dict(origins),
        "proposal_sets": dict(sets),
        "proposal_models": dict(models),
        "rows": rows,
        "warning": (
            "Operator approvals are valid, but unchanged model proposals "
            "are not independent reference grids."
        ),
    }
    write_new(args.output / "reference-provenance.json", audit)
    content = (args.output / "index.html").read_text(encoding="utf-8")
    note = (
        '<p class="note" style="border:1px solid #fbbf24;padding:16px;border-radius:10px">'
        "Ważne: referencje nowych 11 zdjęć to zatwierdzone przez Ciebie siatki. "
        f"{origins.get('proposal_unchanged', 0)} plansz przyjęto bez zmian z propozycji modelu. "
        "Wynik mierzy zgodność z zatwierdzeniami, a nie niezależną dokładność. "
        "Nie oznacza to, że zatwierdzenia są błędne. Sprawdź także zdjęcia z folderu.</p>"
    )
    content = content.replace('<div id="stats"', note + '<div id="stats"')
    content = content.replace(
        "Poprawne całe zdjęcia z nowych 11.", "Zgodne z Twoimi siatkami z nowych 11."
    )
    content = content.replace(
        "function render(){",
        "function render(){document.querySelector('.pair').style.display=rows.length?'':'none';",
    ).replace(
        "if(!rows.length)return;",
        "if(!rows.length){document.getElementById('name').textContent="
        "'Brak zdjęć w tym filtrze.';return;}",
    )
    target = args.output / "review.html"
    if target.exists() and target.read_text(encoding="utf-8") != content:
        raise ValueError("QUALIFIED_GALLERY_ALREADY_EXISTS_DIFFERENT")
    if not target.exists():
        with target.open("xb") as handle:
            handle.write(content.encode("utf-8"))
    print(json.dumps({key: audit[key] for key in ("origins", "proposal_models")}), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=("prepare", "run", "finish", "verify", "audit"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--folder", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--annotations", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--model", choices=("iteration2", "iteration3"))
    parser.add_argument("--max-photos", type=int, default=12)
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    with exclusive_bounded(args.output, 3):
        if args.step == "prepare":
            if any(
                getattr(args, key) is None for key in ("folder", "catalog", "annotations", "ledger")
            ):
                parser.error("prepare requires folder, catalog, annotations and ledger")
            prepare(args)
        elif args.step == "run":
            if args.model is None or not 1 <= args.max_photos <= 40 or not 1 <= args.threads <= 8:
                parser.error("run requires model, max-photos 1..40 and threads 1..8")
            run(args)
        elif args.step == "finish":
            finish(args)
        elif args.step == "audit":
            if args.ledger is None:
                parser.error("audit requires the existing ledger")
            reference_audit(args)
        else:
            manifest, results = collect(args.output)
            for model in manifest["models"].values():
                if sha(Path(model["path"]) / "bundle.json") != model["bundle_sha256"]:
                    raise ValueError("MODEL_BUNDLE_CHANGED")
                for name in ("screen.onnx", "board.onnx"):
                    if sha(Path(model["path"]) / name) != model["files"][name]:
                        raise ValueError("MODEL_FILE_CHANGED")
            for row in manifest["rows"]:
                if sha(Path(row["path"])) != row["sha256"]:
                    raise ValueError("SOURCE_CHECKSUM_CHANGED")
            print(json.dumps({"verified": {key: len(rows) for key, rows in results.items()}}))


if __name__ == "__main__":
    main()
