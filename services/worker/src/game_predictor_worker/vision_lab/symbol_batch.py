"""Bounded, read-only inference of frozen symbol models on operator photo folders."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from game_predictor_worker.geometry_core.inference import (
    BoardDetection,
    onnx_engine,
    reading_order,
)
from game_predictor_worker.geometry_core.lattice import lattice_cell_quads, structurally_valid

from .annotations import digest, exclusive_bounded, read_checked
from .catalog import MAX_SOURCE_BYTES, Catalog
from .geometry import crop_cell
from .run_contracts import RunState
from .run_files import verify_artifact
from .snapshot import canonical, reject_links, safe_file, sha
from .symbol_models import compare, model_pair, probabilities, require_robust_qualification
from .symbol_store import publish_file
from .symbol_training_manifest import SymbolTrainingAdapter

FORMAT = "mumie-symbol-batch-v1"
RANGE = re.compile(r"^seq_(\d+)-(\d+)(?: — kopia)?\.(jpg|jpeg|png|webp)$", re.IGNORECASE)
FOLDER_RANGE = re.compile(r"^(\d+)\s*-\s*(\d+)(?:\s+cut)?$", re.IGNORECASE)


def checked_publish(path: Path, payload: dict[str, Any]) -> None:
    publish_file(path, canonical({"payload": payload, "sha256": digest(payload)}))


def sequence_range(path: Path) -> tuple[int, int]:
    match = RANGE.fullmatch(path.name)
    if match is None:
        raise ValueError("SYMBOL_BATCH_FILENAME_RANGE_INVALID")
    start, end = int(match[1]), int(match[2])
    if start < 1 or not 1 <= end - start + 1 <= 9:
        raise ValueError("SYMBOL_BATCH_FILENAME_RANGE_INVALID")
    return start, end


def expected_count(row: dict[str, Any], folder: Path) -> tuple[int, list[str]]:
    """Operator-supplied folder extent limits the final filename range as well."""
    start, end = row["start"], row["end"]
    match = FOLDER_RANGE.fullmatch(folder.name)
    reasons = []
    if match:
        lower, upper = int(match[1]), int(match[2])
        if not lower <= start <= upper or lower > upper:
            raise ValueError("SYMBOL_BATCH_SOURCE_OUTSIDE_FOLDER_RANGE")
        if end > upper:
            end = upper
            reasons.append("FILENAME_FOLDER_RANGE_CLIPPED")
    return end - start + 1, reasons


def excluded_sources(payload: dict[str, Any]) -> set[str]:
    """Close both training parts and protected sources over the full merged graph."""
    excluded = set(payload["assignments"]) | set(payload["protected_source_ids"])
    for members in payload["graph"].values():
        if excluded.intersection(members):
            excluded.update(members)
    return excluded


def choose_rows(
    rows: list[dict[str, Any]], excluded_sha: set[str], limit: int
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if not 1 <= limit <= 4096:
        raise ValueError("SYMBOL_BATCH_LIMIT_INVALID")
    seen: set[str] = set()
    eligible, duplicates, excluded = [], 0, 0
    for row in sorted(rows, key=lambda r: (r["start"], r["end"], r["filename"])):
        if row["sha256"] in seen:
            duplicates += 1
            continue
        seen.add(row["sha256"])
        if row["sha256"] in excluded_sha:
            excluded += 1
            continue
        eligible.append(row)
    count = min(limit, len(eligible))
    if not count:
        raise ValueError("SYMBOL_BATCH_NO_ELIGIBLE_PHOTOS")
    positions = (
        [0] if count == 1 else [i * (len(eligible) - 1) // (count - 1) for i in range(count)]
    )
    return [eligible[i] for i in positions], {
        "files": len(rows),
        "duplicates": duplicates,
        "excluded": excluded,
        "eligible": len(eligible),
        "selected": count,
    }


def bound_boards(
    boards: list[BoardDetection], expected: int
) -> tuple[list[BoardDetection], list[str], list[dict[str, Any]]]:
    if not 1 <= expected <= 9:
        raise ValueError("SYMBOL_BATCH_BOARD_COUNT_INVALID")
    reasons = []
    selected = sorted(enumerate(boards), key=lambda item: (-item[1].score, item[0]))
    dropped = [
        {"score": board.score, "screen_quad": board.screen_quad.tolist()}
        for _, board in selected[expected:]
    ]
    if len(boards) != expected:
        reasons.append("BOARD_COUNT_EXCESS" if len(boards) > expected else "BOARD_COUNT_MISSING")
    # Reading order remains the domain's existing row grouping. No final sequence assignment.
    return reading_order([board for _, board in selected[:expected]]), reasons, dropped


def preprocess(crops: list[np.ndarray], gray: bool = False) -> np.ndarray:
    """Exact unaugmented training transform, retaining torchvision antialiasing."""
    import torch
    from torchvision.transforms import functional  # type: ignore[import-untyped]

    if not crops or any(c.shape != (96, 96, 3) or c.dtype != np.uint8 for c in crops):
        raise ValueError("SYMBOL_BATCH_CROP_INVALID")
    tensor = torch.from_numpy(np.stack(crops).transpose(0, 3, 1, 2).copy()).float()
    tensor = functional.resize(tensor, [64, 64], antialias=True)
    tensor = tensor.div(255.0).sub(0.5).div(0.5)
    if gray:
        tensor = functional.rgb_to_grayscale(tensor, num_output_channels=3)
    return np.asarray(tensor.numpy(), dtype=np.float32)


def classify_logits(
    rgb: np.ndarray, gray: np.ndarray, classes: list[str], calibration: dict[str, float]
) -> list[dict[str, Any]]:
    if (
        rgb.ndim != 2
        or rgb.shape != gray.shape
        or rgb.shape[1] != len(classes)
        or not np.isfinite(rgb).all()
        or not np.isfinite(gray).all()
    ):
        raise ValueError("SYMBOL_BATCH_LOGITS_INVALID")
    rp = probabilities(rgb, calibration["rgb_temperature"])
    gp = probabilities(gray, calibration["gray_temperature"])
    fused = calibration["rgb_weight"] * rp + (1 - calibration["rgb_weight"]) * gp
    rows = []
    for i, values in enumerate(fused):
        r, g, f = int(rp[i].argmax()), int(gp[i].argmax()), int(values.argmax())
        reasons = []
        if r != g:
            reasons.append("SYMBOL_MODEL_DISAGREEMENT")
        if values[f] < calibration["threshold"]:
            reasons.append("SYMBOL_LOW_CONFIDENCE")
        rows.append(
            {
                "predicted": classes[f],
                "confidence": float(values[f]),
                "rgb": classes[r],
                "gray": classes[g],
                "probabilities": values.tolist(),
                "symbol_reasons": reasons,
            }
        )
    return rows


def freeze(
    root: Path,
    folder: Path,
    training: Path,
    runs: Path,
    comparison: Path,
    geometry: Path,
    catalog_path: Path,
    limit: int,
    generation: int = 1,
    geometry_reference: Path | None = None,
) -> dict[str, Any]:
    pair = model_pair(generation)
    if generation == 2 and geometry_reference is None:
        raise ValueError("SYMBOL_BATCH_GEOMETRY_REFERENCE_REQUIRED")
    paths = (root, folder, training, runs, comparison, geometry, catalog_path)
    if not all(p.is_absolute() for p in paths):
        raise ValueError("SYMBOL_BATCH_ABSOLUTE_PATH_REQUIRED")
    for path in paths:
        reject_links(path)
    inputs = SymbolTrainingAdapter(training).validate()
    if str(catalog_path / "manifest.json") not in inputs.payload["live_bindings"]:
        raise ValueError("SYMBOL_BATCH_EXCLUSION_CATALOG_MISMATCH")
    catalog = Catalog(catalog_path)
    excluded = excluded_sources(inputs.payload)
    if not excluded.issubset(catalog.sources):
        raise ValueError("SYMBOL_BATCH_EXCLUSION_CATALOG_MISMATCH")
    live = dict(inputs.payload["live_bindings"])
    sources = [folder, runs, inputs.bundle, geometry, catalog_path]
    for protected in [*sources, *[Path(name).parent for name in live]]:
        if root.resolve().is_relative_to(protected.resolve()) or protected.resolve().is_relative_to(
            root.resolve()
        ):
            raise ValueError("SYMBOL_BATCH_DIRECTORY_OVERLAP")
    state_path = runs / "state.json"
    exported: dict[str, dict[str, str]] = {}
    reports = {}
    for raw in read_checked(state_path)["runs"].values():
        run = RunState.model_validate(raw)
        if run.request.manifest_id != inputs.manifest_id or run.request.model_version not in pair:
            continue
        if run.status != "succeeded" or run.report is None or run.request.model_version in exported:
            raise ValueError("SYMBOL_BATCH_RUN_INVALID")
        onnx = verify_artifact(runs, run.artifacts["onnx"])
        report = verify_artifact(runs, run.report)
        measured = json.loads(report.read_bytes())["metrics"]
        if generation == 2:
            require_robust_qualification(measured)
        reports[run.request.model_version] = measured["predictions"]
        exported[run.request.model_version] = {
            "path": str(onnx),
            "sha256": sha(onnx),
            "run": run.id,
        }
        live[str(report)] = sha(report)
        live[str(onnx)] = sha(onnx)
    if set(exported) != set(pair):
        raise ValueError("SYMBOL_BATCH_EXPORTS_MISSING")
    recorded = json.loads(comparison.read_bytes())
    if recorded != compare(reports[pair[0]], reports[pair[1]]):
        raise ValueError("SYMBOL_BATCH_CALIBRATION_MISMATCH")
    live.update({str(path): sha(path) for path in (training, state_path, comparison)})
    geometry_payload = json.loads((geometry / "bundle.json").read_bytes())
    for name in ("bundle.json", "screen.onnx", "board.onnx"):
        path = safe_file(geometry, name)
        value = sha(path)
        if name != "bundle.json" and value != geometry_payload["files"][name]:
            raise ValueError("SYMBOL_BATCH_GEOMETRY_CHECKSUM_MISMATCH")
        live[str(path)] = value
    excluded_sha = {catalog.sources[sid].sha256 for sid in excluded}
    rows = []
    for path in folder.iterdir():
        if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        reject_links(path)
        start, end = sequence_range(path)
        if path.stat().st_size > MAX_SOURCE_BYTES:
            raise ValueError("SYMBOL_BATCH_SOURCE_TOO_LARGE")
        rows.append(
            {
                "path": str(path),
                "filename": path.name,
                "sha256": sha(path),
                "start": start,
                "end": end,
            }
        )
    selected, inventory = choose_rows(rows, excluded_sha, limit)
    for row in selected:
        live[row["path"]] = row["sha256"]
    payload = {
        "format": FORMAT,
        "purpose": "unlabelled_inference_only",
        "training_manifest": str(training),
        "training_manifest_id": inputs.manifest_id,
        "folder": str(folder),
        "classes": reports[pair[0]]["classes"],
        "models": exported,
        "geometry": str(geometry),
        "calibration": {
            "rgb_temperature": recorded["rgb"]["temperature"],
            "gray_temperature": recorded["gray"]["temperature"],
            "rgb_weight": recorded["selected_fusion"]["rgb_weight"],
            "threshold": 0.9,
        },
        "excluded_source_ids": sorted(excluded),
        "excluded_sha256": sorted(excluded_sha),
        "training_photo_pixel_groups": sorted(inputs.payload["photo_pixel_groups"]),
        "inventory": inventory,
        "rows": selected,
        "live_bindings": live,
        "human_labels_written": 0,
        "accuracy": None,
    }
    if generation == 2:
        payload["generation"] = 2
    if geometry_reference is not None:
        if not geometry_reference.is_absolute():
            raise ValueError("SYMBOL_BATCH_ABSOLUTE_PATH_REQUIRED")
        if root.resolve().is_relative_to(
            geometry_reference.resolve()
        ) or geometry_reference.resolve().is_relative_to(root.resolve()):
            raise ValueError("SYMBOL_BATCH_DIRECTORY_OVERLAP")
        baseline = validate_batch(geometry_reference)
        if (
            baseline["rows"] != selected
            or baseline["training_manifest_id"] != inputs.manifest_id
            or baseline["geometry"] != str(geometry)
        ):
            raise ValueError("SYMBOL_BATCH_GEOMETRY_REFERENCE_MISMATCH")
        payload["geometry_reference"] = str(geometry_reference)
        live[str(geometry_reference / "manifest.json")] = sha(geometry_reference / "manifest.json")
        for index in range(len(selected)):
            previous = validate_result(geometry_reference, baseline, index)
            path = result_path(geometry_reference, index)
            live[str(path)] = sha(path)
            for name, value in previous["assets"].items():
                live[str(path.parent / name)] = value
    with exclusive_bounded(root):
        checked_publish(root / "manifest.json", payload)
    return payload


def validate_batch(root: Path) -> dict[str, Any]:
    if not root.is_absolute():
        raise ValueError("SYMBOL_BATCH_ABSOLUTE_PATH_REQUIRED")
    reject_links(root)
    payload = read_checked(root / "manifest.json")
    if payload["format"] != FORMAT:
        raise ValueError("SYMBOL_BATCH_FORMAT_INVALID")
    for name, expected in payload["live_bindings"].items():
        path = Path(name)
        reject_links(path)
        if sha(path) != expected:
            raise ValueError("SYMBOL_BATCH_INPUT_DRIFT: " + name)
    return payload


def load_photo(row: dict[str, Any], forbidden_pixels: list[str]) -> Image.Image:
    path = Path(row["path"])
    reject_links(path)
    with path.open("rb") as stream:
        data = stream.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES or hashlib.sha256(data).hexdigest() != row["sha256"]:
        raise ValueError("SYMBOL_BATCH_SOURCE_DRIFT")
    with Image.open(io.BytesIO(data)) as image:
        rgb = ImageOps.exif_transpose(image).convert("RGB")
    pixels = digest([rgb.size, hashlib.sha256(rgb.tobytes()).hexdigest()])
    if pixels in forbidden_pixels:
        raise ValueError("SYMBOL_BATCH_TRAINING_PIXEL_DUPLICATE")
    return rgb


def image_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=93, subsampling=0)
    return buffer.getvalue()


def reclassify_photo(
    image: Image.Image, baseline: dict[str, Any], classifier: Any
) -> dict[str, Any]:
    """Change only symbol proposals, proving exact same crop pixels as the baseline."""
    result: dict[str, Any] = json.loads(canonical(baseline))
    rgb = np.asarray(image)
    crops, indices = [], []
    for index, cell in enumerate(result["cells"]):
        if cell["crop_pixel_sha256"] is None:
            continue
        crop = crop_cell(rgb, np.asarray(cell["quad"], dtype=np.float32))
        if crop is None or hashlib.sha256(crop.tobytes()).hexdigest() != cell["crop_pixel_sha256"]:
            raise ValueError("SYMBOL_BATCH_REFERENCE_CROP_MISMATCH")
        crops.append(crop)
        indices.append(index)
    predictions = classifier(crops) if crops else []
    if len(predictions) != len(crops):
        raise ValueError("SYMBOL_BATCH_PREDICTION_COUNT_INVALID")
    for index, prediction in zip(indices, predictions, strict=True):
        cell = result["cells"][index]
        geometry_reasons = [r for r in cell["reasons"] if not r.startswith("SYMBOL_")]
        cell.update(prediction)
        cell["reasons"] = sorted(set(geometry_reasons + prediction["symbol_reasons"]))
        cell["requires_review"] = bool(cell["reasons"])
    return result


def analyse_photo(
    image: Image.Image, boards: list[BoardDetection], expected: int, classifier: Any
) -> tuple[dict[str, Any], dict[str, bytes]]:
    selected, photo_reasons, dropped = bound_boards(boards, expected)
    overlay = image.copy()
    draw = ImageDraw.Draw(overlay)
    rgb = np.asarray(image)
    atlas = Image.new("RGB", (480, max(1, len(selected)) * 288), "#222222")
    atlas_draw = ImageDraw.Draw(atlas)
    board_rows: list[dict[str, Any]] = []
    cells: list[dict[str, Any]] = []
    crops, crop_indices = [], []
    for bi, board in enumerate(selected):
        reasons = [r for r in board.reasons if r != "NEURAL_GRID_GATE_UNCALIBRATED"]
        if board.nodes is None or not structurally_valid(board.nodes):
            reasons.append("GRID_STRUCTURE_INVALID")
            quads = []
        else:
            quads = lattice_cell_quads(board.nodes)
            grid = board.nodes.reshape(4, 6, 2)
            for line in [*grid, *grid.transpose(1, 0, 2)]:
                draw.line([tuple(map(float, point)) for point in line], fill="#00eeee", width=2)
            corner = board.nodes[0]
            draw.text((float(corner[0]), float(corner[1])), str(bi + 1), fill="red", stroke_width=1)
        board_rows.append(
            {
                "board_index": bi,
                "score": board.score,
                "nodes": board.nodes.tolist() if board.nodes is not None else None,
                "reasons": sorted(set(reasons)),
                "sequence_number": None,
            }
        )
        for ci in range(15):
            quad = quads[ci] if quads else None
            crop = crop_cell(rgb, quad) if quad is not None else None
            cell_reasons = list(photo_reasons) + reasons
            if crop is None:
                cell_reasons.append(
                    "CELL_OUTSIDE_IMAGE" if quad is not None else "GRID_UNAVAILABLE"
                )
            x, y = ci % 5 * 96, (bi * 3 + ci // 5) * 96
            if crop is not None:
                atlas.paste(Image.fromarray(crop), (x, y))
                crop_indices.append(len(cells))
                crops.append(crop)
            else:
                atlas_draw.text((x + 8, y + 8), "brak obrazu", fill="white")
            cells.append(
                {
                    "board_index": bi,
                    "cell_index": ci,
                    "atlas": [x, y, 96, 96],
                    "quad": quad.tolist() if quad is not None else None,
                    "crop_pixel_sha256": hashlib.sha256(crop.tobytes()).hexdigest()
                    if crop is not None
                    else None,
                    "predicted": None,
                    "confidence": None,
                    "reasons": sorted(set(cell_reasons)),
                    "human_approved": False,
                }
            )
    if crops:
        predictions = classifier(crops)
        if len(predictions) != len(crops):
            raise ValueError("SYMBOL_BATCH_PREDICTION_COUNT_INVALID")
        for index, prediction in zip(crop_indices, predictions, strict=True):
            cells[index].update(prediction)
            cells[index]["reasons"] = sorted(
                set(cells[index]["reasons"] + prediction["symbol_reasons"])
            )
    for cell in cells:
        cell["requires_review"] = bool(cell["reasons"])
    return {
        "detected": len(boards),
        "expected": expected,
        "selected": len(selected),
        "photo_reasons": photo_reasons,
        "dropped_candidates": dropped,
        "boards": board_rows,
        "cells": cells,
    }, {"overlay.jpg": image_bytes(overlay), "atlas.jpg": image_bytes(atlas)}


def result_path(root: Path, index: int) -> Path:
    return root / "photos" / f"{index:04d}" / "result.json"


def validate_result(root: Path, payload: dict[str, Any], index: int) -> dict[str, Any]:
    result = read_checked(result_path(root, index))
    if result["batch_id"] != digest(payload) or result["row"] != payload["rows"][index]:
        raise ValueError("SYMBOL_BATCH_RESULT_BINDING_INVALID")
    for name, expected in result["assets"].items():
        if sha(safe_file(result_path(root, index).parent, name)) != expected:
            raise ValueError("SYMBOL_BATCH_RESULT_ASSET_DRIFT")
    return result


def run(root: Path, max_photos: int = 25) -> dict[str, int]:
    if not 1 <= max_photos <= 25:
        raise ValueError("SYMBOL_BATCH_PORTION_INVALID")
    import cv2
    import onnxruntime as ort  # type: ignore[import-untyped]
    import torch

    torch.set_num_threads(2)
    with exclusive_bounded(root):
        payload = validate_batch(root)
        done = set()
        for index in range(len(payload["rows"])):
            if result_path(root, index).exists():
                validate_result(root, payload, index)
                done.add(index)
        pending = [i for i in range(len(payload["rows"])) if i not in done][:max_photos]
        if not pending:
            return {"complete": len(done), "processed": 0, "total": len(payload["rows"])}
        geometry = Path(payload["geometry"])
        reference = Path(payload["geometry_reference"]) if "geometry_reference" in payload else None
        engine = (
            None
            if reference is not None
            else onnx_engine(
                geometry,
                threads=2,
                expected_bundle_sha256=payload["live_bindings"][str(geometry / "bundle.json")],
            )
        )
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        sessions = []
        for model in model_pair(payload.get("generation", 1)):
            descriptor = payload["models"][model]
            content = Path(descriptor["path"]).read_bytes()
            if hashlib.sha256(content).hexdigest() != descriptor["sha256"]:
                raise ValueError("SYMBOL_BATCH_MODEL_LOAD_DRIFT")
            sessions.append(
                ort.InferenceSession(content, options, providers=["CPUExecutionProvider"])
            )

        def classifier(crops: list[np.ndarray]) -> list[dict[str, Any]]:
            logits = [
                session.run(["logits"], {"images": preprocess(crops, gray=bool(i))})[0]
                for i, session in enumerate(sessions)
            ]
            return classify_logits(logits[0], logits[1], payload["classes"], payload["calibration"])

        started, processed = time.monotonic(), 0
        for index in pending:
            row = payload["rows"][index]
            image = load_photo(row, payload["training_photo_pixel_groups"])
            cv2.setRNGSeed(int(row["sha256"][:8], 16) % 2147483647)
            if reference is not None:
                baseline = read_checked(result_path(reference, index))
                result = reclassify_photo(image, baseline, classifier)
                assets = {
                    name: (result_path(reference, index).parent / name).read_bytes()
                    for name in baseline["assets"]
                }
            else:
                assert engine is not None
                detections = engine.analyse(np.asarray(image))
                expected, range_reasons = expected_count(row, Path(payload["folder"]))
                result, assets = analyse_photo(image, detections, expected, classifier)
                result["photo_reasons"] += range_reasons
                for cell in result["cells"]:
                    cell["reasons"] = sorted(set(cell["reasons"] + range_reasons))
                    cell["requires_review"] = bool(cell["reasons"])
            result.update({"batch_id": digest(payload), "row": row, "assets": {}})
            directory = result_path(root, index).parent
            for name, content in assets.items():
                publish_file(directory / name, content)
                result["assets"][name] = hashlib.sha256(content).hexdigest()
            # Result is the commit marker. Recheck source before publishing a completed photo.
            if sha(Path(row["path"])) != row["sha256"]:
                raise ValueError("SYMBOL_BATCH_SOURCE_DRIFT")
            checked_publish(result_path(root, index), result)
            processed += 1
            print(
                f"Photo {index + 1}/{len(payload['rows'])}: {len(result['cells'])} cells",
                flush=True,
            )
            if time.monotonic() - started >= 70:
                break
        validate_batch(root)
        return {
            "complete": len(done) + processed,
            "processed": processed,
            "total": len(payload["rows"]),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["freeze", "run", "review", "verify"])
    parser.add_argument("--root", type=Path, required=True)
    for name in ("folder", "training", "runs", "comparison", "geometry", "catalog"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--limit", type=int, default=600)
    parser.add_argument("--max-photos", type=int, default=25)
    parser.add_argument("--generation", type=int, choices=(1, 2), default=1)
    parser.add_argument("--geometry-reference", type=Path)
    args = parser.parse_args()
    if args.action == "freeze":
        required = (
            args.folder,
            args.training,
            args.runs,
            args.comparison,
            args.geometry,
            args.catalog,
        )
        if any(value is None for value in required):
            parser.error("freeze requires folder/training/runs/comparison/geometry/catalog")
        print(
            json.dumps(
                freeze(
                    args.root,
                    *required,
                    args.limit,
                    generation=args.generation,
                    geometry_reference=args.geometry_reference,
                )["inventory"]
            )
        )
    elif args.action == "run":
        print(json.dumps(run(args.root, args.max_photos)))
    else:
        from .symbol_batch_review import finish

        print(json.dumps(finish(args.root, render=args.action == "review")))


if __name__ == "__main__":
    main()
