"""TASK-0804 comparison of the 5 x 3 grid engines on frozen sets (V3-C).

``python -m game_predictor_worker.vision_lab.grid_v3_comparison <command>``

development  one engine on the 600 development photos of snapshot v2 (ONNX CPU or the
             production original output); results under ``<output>/development``
hybrid       ``hybrid_v3`` on development from the stored run-1 network output and the
             production original output (run-1 thresholds, no recalibration)
timing       ONNX Runtime CPU seconds per photo for every frozen model (development photos)

Engines: the production engine measured on its *original* output (the last automatic
``structured_opencv_v1`` revision before any manual revision, exported read-only by
``scripts/vision_lab_geometry_export.py --production-originals-for``), ``neural_grid``
runs 1 and 2 and the Mumie fine-tune iteration 3 (frozen ONNX bundles), and ``hybrid_v3``
(reference = production original, network = run 1, ``RUN1_DEVELOPMENT_THRESHOLDS``).

The D-483 metric code is reused unchanged (``evaluate_photo``). This module adds *target*
evaluation for sets whose labels do not cover every board: on ``gold`` every board of a
photo is known (G targets plus U/S boards without an evaluation label), so a prediction on a
U board is neither scored nor a false board; on the partial lab holdouts (Reels, Treasure)
only labelled boards exist, so false boards and complete photos are not measurable and are
reported as ``None``. Nothing here reads a sealed role: gold and the lab holdouts are read
only by ``grid_v3_sealed`` behind its single-use ledger.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import numpy as np

from .hybrid_v3_calibration import network_from_record, network_record
from .hybrid_v3_engine import RUN1_DEVELOPMENT_THRESHOLDS, network_boards
from .hybrid_v3_gate import GATE_VERSION, GateThresholds, PhotoDecision, ReferenceBoard, gate_photo
from .neural_grid_data import ByteImage, FloatArray, PhotoSample, load_samples, read_rgb
from .neural_grid_inference import structurally_valid
from .neural_grid_metrics import evaluate_photo
from .neural_grid_protocol import METRIC_DEFINITION

COMPARISON_VERSION: Final = "grid-v3-comparison-v1"
DATA_ROOT: Final = Path(
    os.environ.get(
        "VISION_LAB_DATA_ROOT", str(Path.home() / "Documents" / "game_predictor_vision_data")
    )
)
RUNS: Final = DATA_ROOT / "neural-grid-runs"
SNAPSHOT_V2: Final = (
    DATA_ROOT
    / "production-geometry-snapshots"
    / "286f2e370aa84437c63fcffe202f01260d6ca13aee317eb8c11cac2ad0f2df59"
)
ORIGINALS: Final = DATA_ROOT / "production-geometry" / "production-originals-777-20261004"
OUTPUT: Final = DATA_ROOT / "grid-v3-comparison"
# Frozen models of TASK-0804 (no selection after a holdout read).
BUNDLES: Final[Mapping[str, Path]] = {
    "run1": RUNS / "43933ac8d7d443c8b9079630a83de2e6" / "exports" / "2cd19738367121e6-round3",
    "run2": RUNS / "ff03b1d7c489448483f23e73dd03f31d" / "exports" / "d623eebfc876c7f3-round9",
    "iter3": RUNS / "5bc981568c3f42bd96f6f9238e57aedc" / "exports" / "iteration03-f896da7196431be2",
}
NETWORK_MODELS: Final = ("run1", "run2", "iter3")
PRODUCTION: Final = "production"
HYBRID: Final = "hybrid"
ENGINES: Final = (PRODUCTION, *NETWORK_MODELS, HYBRID)
HYBRID_NETWORK: Final = "run1"
HYBRID_THRESHOLDS: Final[GateThresholds] = RUN1_DEVELOPMENT_THRESHOLDS
BOOTSTRAP_SAMPLES: Final = 2000
BOOTSTRAP_SEED: Final = 804
WILSON_Z: Final = 1.959963984540054


# --- photos ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvalPhoto:
    """One photo of an evaluation set with every known board and which ones are scored.

    ``labels`` are all boards known for the photo (they decide matching); ``targets`` are
    the indices that are scored. ``labels_complete`` says every board of the photo is in
    ``labels`` (false boards are measurable); ``photo_metric`` says the D-483 photo metric
    applies (every board is a target and the labels are complete).
    """

    image_id: str
    group: str
    load: Callable[[], ByteImage]
    labels: tuple[FloatArray, ...]
    targets: tuple[int, ...]
    labels_complete: bool
    photo_metric: bool
    meta: Mapping[str, Any] = field(default_factory=dict)


def development_photos(snapshot: Path = SNAPSHOT_V2) -> list[EvalPhoto]:
    """The development role of snapshot v2 through the ``neural_grid`` role guard."""

    return [photo_from_sample(sample) for sample in load_samples(snapshot, ("development",))]


def photo_from_sample(sample: PhotoSample, group: str | None = None) -> EvalPhoto:
    labels = tuple(board.nodes for board in sample.boards)
    return EvalPhoto(
        image_id=sample.image_id,
        group=group or sample.level,
        load=lambda: read_rgb(sample),
        labels=labels,
        targets=tuple(range(len(labels))),
        labels_complete=True,
        photo_metric=True,
        meta={"level": sample.level, "family": sample.family_id, "sha256": sample.sha256},
    )


# --- engine outputs -------------------------------------------------------------------------

Prediction = tuple[FloatArray, bool]


def load_originals(directory: Path = ORIGINALS) -> dict[str, dict[str, Any]]:
    """``production-originals.jsonl`` checked against its export manifest (SHA-256)."""

    manifest = json.loads((directory / "export_manifest.json").read_text(encoding="utf-8"))
    path = directory / "production-originals.jsonl"
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != manifest["files"]["production-originals.jsonl"]["sha256"]:
        raise ValueError("GRID_V3_ORIGINALS_CHECKSUM_MISMATCH")
    rows: dict[str, dict[str, Any]] = {}
    with path.open("rb") as stream:
        for line in stream:
            if line.strip():
                row = json.loads(line)
                rows[str(row["sourceImageId"])] = row
    return rows


def original_reference(row: Mapping[str, Any] | None) -> list[ReferenceBoard]:
    """Every board of the original production output (``None`` nodes = no grid)."""

    if row is None or row["status"] != "present":
        return []
    return [
        ReferenceBoard(
            int(board["positionIndex"]),
            None if board["nodes"] is None else np.asarray(board["nodes"], np.float32),
        )
        for board in row["boards"]
    ]


def predictions_of_reference(reference: Iterable[ReferenceBoard]) -> list[Prediction]:
    return [
        (board.nodes, structurally_valid(board.nodes))
        for board in reference
        if board.nodes is not None
    ]


def predictions_of_network(record: Sequence[Mapping[str, Any]]) -> list[Prediction]:
    result = []
    for board in network_from_record([dict(item) for item in record]):
        if board.nodes is not None:
            result.append((board.nodes, structurally_valid(board.nodes)))
    return result


def hybrid_decision(
    original: Mapping[str, Any] | None,
    network: Sequence[Mapping[str, Any]],
    thresholds: GateThresholds = HYBRID_THRESHOLDS,
) -> PhotoDecision:
    boards = network_from_record([dict(item) for item in network])
    return gate_photo(original_reference(original), boards, thresholds)


def predictions_of_decision(decision: PhotoDecision) -> tuple[list[Prediction], list[str]]:
    predictions: list[Prediction] = []
    states: list[str] = []
    for board in decision.boards:
        if board.nodes is not None:
            predictions.append((board.nodes, structurally_valid(board.nodes)))
            states.append(board.state)
    return predictions, states


def run_network(engine: Any, rgb: ByteImage) -> dict[str, Any]:
    started = time.perf_counter()
    boards = network_record(network_boards(engine.analyse(rgb)))
    return {"boards": boards, "seconds": time.perf_counter() - started, "error": None}


# --- target evaluation ----------------------------------------------------------------------


def evaluate_targets(
    photo: EvalPhoto, predictions: Sequence[Prediction], states: Sequence[str] | None = None
) -> dict[str, Any]:
    """D-483 on the scored boards of one photo (``evaluate_photo`` unchanged underneath).

    Every prediction is matched against every known board; only target boards are scored.
    A prediction matching a known non-target board is ignored; one matching no known board
    is a false board only when the labels are complete. ``states`` (hybrid) carries the gate
    state of each prediction.
    """

    evaluation = evaluate_photo(photo.image_id, photo.group, list(photo.labels), list(predictions))
    by_label = {match.label: match for match in evaluation.matches}
    targets: list[dict[str, Any]] = []
    costs: list[float] = []
    for index in photo.targets:
        match = by_label.get(index)
        state = None
        if match is not None and states is not None:
            state = states[match.prediction]
        targets.append(
            {
                "label": index,
                "matched": match is not None,
                "iou": None if match is None else match.iou,
                "valid": None if match is None else match.valid,
                "nme": None if match is None else match.nme,
                "max_error": None if match is None else match.max_error,
                "correct": bool(match is not None and match.correct),
                "state": state,
            }
        )
        if match is not None and match.valid and match.nme is not None:
            costs.append(min(1.0, float(match.nme)))
        else:
            costs.append(1.0)
    false_boards = evaluation.false_boards if photo.labels_complete else None
    correct = sum(bool(t["correct"]) for t in targets)
    complete = None
    if photo.photo_metric:
        complete = correct == len(photo.targets) and evaluation.false_boards == 0
    result: dict[str, Any] = {
        "image_id": photo.image_id,
        "group": photo.group,
        "meta": dict(photo.meta),
        "predicted": len(predictions),
        "targets": targets,
        "false_boards": false_boards,
        "false_predictions": [
            i
            for i in range(len(predictions))
            if i not in {m.prediction for m in evaluation.matches}
        ]
        if photo.labels_complete
        else None,
        "macro_cost": float(np.mean(costs)) if costs else None,
        "complete_correct": complete,
    }
    if states is not None:
        confident_false = 0
        if photo.labels_complete:
            matched_predictions = {m.prediction for m in evaluation.matches}
            confident_false = sum(
                1
                for i, state in enumerate(states)
                if state == "confident" and i not in matched_predictions
            )
        result["confident_false_boards"] = confident_false
    return result


# --- summaries ------------------------------------------------------------------------------


def wilson(successes: int, total: int, z: float = WILSON_Z) -> list[float] | None:
    """Wilson 95% interval of a proportion (``None`` without trials)."""

    if total <= 0:
        return None
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [max(0.0, centre - half), min(1.0, centre + half)]


def bootstrap(
    groups: Sequence[Sequence[float]],
    statistic: Callable[[list[float]], float],
    samples: int = BOOTSTRAP_SAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> list[float] | None:
    """Percentile 95% interval of ``statistic`` resampling photos (their values together)."""

    if not groups or not any(groups):
        return None
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(samples):
        picked = rng.integers(0, len(groups), len(groups))
        pooled = [value for index in picked for value in groups[int(index)]]
        if pooled:
            values.append(statistic(pooled))
    if not values:
        return None
    return [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))]


def _percentile(values: Sequence[float], q: float) -> float | None:
    return float(np.percentile(values, q)) if values else None


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def summarize_results(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Photo, board and node metrics of one engine on one set, with 95% intervals."""

    targets = [t for r in results for t in r["targets"]]
    expected = len(targets)
    correct = sum(t["correct"] for t in targets)
    matched = sum(t["matched"] for t in targets)
    photo_rows = [r for r in results if r["complete_correct"] is not None]
    complete = sum(bool(r["complete_correct"]) for r in photo_rows)
    per_photo_nme = [
        [
            float(t["nme"])
            for t in r["targets"]
            if t["matched"] and t["valid"] and t["nme"] is not None
        ]
        for r in results
    ]
    nme = [value for values in per_photo_nme for value in values]
    max_errors = [
        float(t["max_error"])
        for t in targets
        if t["matched"] and t["valid"] and t["max_error"] is not None
    ]
    macro = [float(r["macro_cost"]) for r in results if r["macro_cost"] is not None]
    false_rows = [r for r in results if r["false_boards"] is not None]
    summary: dict[str, Any] = {
        "photos": len(results),
        "photo_metric_photos": len(photo_rows),
        "photo_complete_correct": complete if photo_rows else None,
        "photo_complete_correct_rate": _rate(complete, len(photo_rows)),
        "photo_complete_correct_ci95": wilson(complete, len(photo_rows)),
        "image_macro": float(np.mean(macro)) if macro else None,
        "image_macro_ci95": bootstrap([[m] for m in macro], lambda v: float(np.mean(v))),
        "boards_expected": expected,
        "boards_matched": matched,
        "boards_correct": correct,
        "board_recovery_rate": _rate(correct, expected),
        "board_recovery_ci95": wilson(correct, expected),
        "detection_recall": _rate(matched, expected),
        "boards_invalid": sum(1 for t in targets if t["matched"] and not t["valid"]),
        "nme_median": _percentile(nme, 50),
        "nme_median_ci95": bootstrap(per_photo_nme, lambda v: float(np.median(v))),
        "nme_p95": _percentile(nme, 95),
        "nme_p95_ci95": bootstrap(per_photo_nme, lambda v: float(np.percentile(v, 95))),
        "max_node_error_median": _percentile(max_errors, 50),
        "max_node_error_p95": _percentile(max_errors, 95),
        "false_boards": sum(int(r["false_boards"]) for r in false_rows) if false_rows else None,
        "photos_with_false_boards": sum(int(r["false_boards"]) > 0 for r in false_rows)
        if false_rows
        else None,
        "boards_predicted": sum(int(r["predicted"]) for r in results),
    }
    if results and "confident_false_boards" in results[0]:
        summary["hybrid"] = summarize_hybrid(results)
    return summary


def summarize_hybrid(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Coverage and errors of what the gate would accept without review."""

    confident_photos = [r for r in results if r.get("photo_state") == "confident"]
    photo_rows = [r for r in confident_photos if r["complete_correct"] is not None]
    wrong_photos = sum(not r["complete_correct"] for r in photo_rows)
    confident_targets = [
        t for r in results for t in r["targets"] if t["matched"] and t["state"] == "confident"
    ]
    wrong_boards = sum(not t["correct"] for t in confident_targets) + sum(
        int(r.get("confident_false_boards") or 0) for r in results
    )
    confident_boards = len(confident_targets) + sum(
        int(r.get("confident_false_boards") or 0) for r in results
    )
    any_wrong_target = sum(
        any(t["state"] == "confident" and not t["correct"] for t in r["targets"])
        or int(r.get("confident_false_boards") or 0) > 0
        for r in confident_photos
    )
    reasons: Counter[str] = Counter()
    for r in results:
        reasons.update(r.get("photo_reasons") or [])
    return {
        "photos_confident": len(confident_photos),
        "photo_coverage": _rate(len(confident_photos), len(results)),
        "photo_coverage_ci95": wilson(len(confident_photos), len(results)),
        "confident_photos_with_photo_metric": len(photo_rows),
        "confident_photos_not_complete_correct": wrong_photos if photo_rows else None,
        "confident_photos_with_wrong_scored_board": any_wrong_target,
        "confident_photo_error_rate_ci95": wilson(any_wrong_target, len(confident_photos)),
        "target_boards_confident": len(confident_targets),
        "confident_boards_scored_or_false": confident_boards,
        "confident_boards_wrong": wrong_boards,
        "confident_board_error_rate": _rate(wrong_boards, confident_boards),
        "confident_board_error_ci95": wilson(wrong_boards, confident_boards),
        "photo_reasons": dict(sorted(reasons.items())),
    }


def grouped_summary(
    results: Sequence[Mapping[str, Any]], key: Callable[[Mapping[str, Any]], str]
) -> dict[str, Any]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for result in results:
        groups.setdefault(key(result), []).append(result)
    return {name: summarize_results(items) for name, items in sorted(groups.items())}


def production_acceptance(
    results: Sequence[Mapping[str, Any]], originals: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    """The production engine's own gate: photos its original revision ``accepted``."""

    accepted = [
        r
        for r in results
        if (originals.get(r["image_id"]) or {}).get("original")
        and originals[r["image_id"]]["original"]["status"] == "accepted"
    ]
    rows = [r for r in accepted if r["complete_correct"] is not None]
    wrong = sum(
        any(not t["correct"] for t in r["targets"]) or bool(r["false_boards"]) for r in accepted
    )
    return {
        "photos": len(results),
        "photos_accepted": len(accepted),
        "photo_coverage": _rate(len(accepted), len(results)),
        "photo_coverage_ci95": wilson(len(accepted), len(results)),
        "accepted_photos_with_photo_metric": len(rows),
        "accepted_photos_with_wrong_scored_board_or_false_board": wrong,
        "accepted_photo_error_ci95": wilson(wrong, len(accepted)),
    }


# --- engine runs on one set -----------------------------------------------------------------


def evaluate_engine_set(
    photos: Sequence[EvalPhoto],
    engine: str,
    *,
    originals: Mapping[str, Mapping[str, Any]],
    networks: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    """Results of ``engine`` from stored outputs (``networks[model][image_id]``)."""

    results = []
    for photo in photos:
        original = originals.get(photo.image_id)
        if engine == PRODUCTION:
            if original is None or original["status"] != "present":
                continue
            result = evaluate_targets(photo, predictions_of_reference(original_reference(original)))
            result["production_status"] = original["original"]["status"]
        elif engine == HYBRID:
            if original is None or original["status"] != "present":
                continue
            decision = hybrid_decision(original, networks[HYBRID_NETWORK][photo.image_id]["boards"])
            predictions, states = predictions_of_decision(decision)
            result = evaluate_targets(photo, predictions, states)
            result["photo_state"] = decision.state
            result["photo_reasons"] = list(decision.reasons)
            result["board_reasons"] = [list(b.reasons) for b in decision.boards]
        else:
            record = networks[engine][photo.image_id]
            result = evaluate_targets(photo, predictions_of_network(record["boards"]))
            result["seconds"] = record.get("seconds")
        results.append(result)
    return results


def missing_originals(
    photos: Sequence[EvalPhoto], originals: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Photos measured without a production original, each with its reason."""

    missing = []
    for photo in photos:
        row = originals.get(photo.image_id)
        if row is None:
            missing.append({"image_id": photo.image_id, "reason": "NOT_IN_ORIGINALS_EXPORT"})
        elif row["status"] != "present":
            missing.append(
                {
                    "image_id": photo.image_id,
                    "reason": row["missingReason"],
                    "lineage": row["lineage"],
                }
            )
    return missing


def collect_networks(
    photos: Sequence[EvalPhoto], models: Sequence[str], threads: int = 4
) -> dict[str, dict[str, dict[str, Any]]]:
    """Every model on every photo (each photo decoded once); a decode error is recorded."""

    from .neural_grid_inference import onnx_engine

    engines = {model: onnx_engine(BUNDLES[model], threads=threads) for model in models}
    outputs: dict[str, dict[str, dict[str, Any]]] = {model: {} for model in models}
    for photo in photos:
        try:
            rgb = photo.load()
        except (ValueError, OSError) as error:
            for model in models:
                outputs[model][photo.image_id] = {
                    "boards": [],
                    "seconds": None,
                    "error": str(error),
                }
            continue
        for model, engine in engines.items():
            outputs[model][photo.image_id] = run_network(engine, rgb)
    return outputs


def bundle_identity(model: str) -> dict[str, Any]:
    bundle = json.loads((BUNDLES[model] / "bundle.json").read_text(encoding="utf-8"))
    return {
        "model": model,
        "bundle": str(BUNDLES[model]),
        "weights_sha256": bundle["weights_sha256"],
        "files": bundle["files"],
        "provenance": bundle.get("provenance"),
    }


def frozen_identity() -> dict[str, Any]:
    """Models, gate thresholds and metric bound to every comparison output."""

    return {
        "version": COMPARISON_VERSION,
        "models": {model: bundle_identity(model) for model in NETWORK_MODELS},
        "hybrid": {
            "gate_version": GATE_VERSION,
            "network": HYBRID_NETWORK,
            "reference": "production original output",
            "thresholds": HYBRID_THRESHOLDS.as_dict(),
            "thresholds_source": "TASK-0803 run-1 development calibration (no recalibration)",
        },
        "metric": METRIC_DEFINITION,
        "originals": str(ORIGINALS),
    }


def write_json(path: Path, value: Any) -> str:
    """Create-only JSON file; returns its SHA-256."""

    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, indent=1, sort_keys=True, default=_jsonable).encode("utf-8")
    with path.open("xb") as stream:
        stream.write(data)
    return hashlib.sha256(data).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def set_report(
    photos: Sequence[EvalPhoto],
    *,
    originals: Mapping[str, Mapping[str, Any]],
    networks: Mapping[str, Mapping[str, Mapping[str, Any]]],
    engines: Sequence[str],
    group_key: Callable[[Mapping[str, Any]], str] | None = None,
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    """Summary per engine (and per group) and the per-photo results."""

    per_engine = {
        engine: evaluate_engine_set(photos, engine, originals=originals, networks=networks)
        for engine in engines
    }
    summary: dict[str, Any] = {
        "photos": len(photos),
        "target_boards": sum(len(p.targets) for p in photos),
        "photo_metric_photos": sum(p.photo_metric for p in photos),
        "missing_production_original": missing_originals(photos, originals),
        "engines": {},
    }
    for engine, results in per_engine.items():
        block = {"all": summarize_results(results)}
        if group_key is not None:
            block["groups"] = grouped_summary(results, group_key)
        if engine == PRODUCTION:
            block["production_acceptance"] = production_acceptance(results, originals)
        summary["engines"][engine] = block
    # Same photos for every engine: the production subset (photos with an original).
    with_original = {
        p.image_id for p in photos if (originals.get(p.image_id) or {}).get("status") == "present"
    }
    summary["engines_on_photos_with_original"] = {
        engine: summarize_results([r for r in results if r["image_id"] in with_original])
        for engine, results in per_engine.items()
    }
    return summary, per_engine


# --- CLI ------------------------------------------------------------------------------------


def _network_path(output: Path, dataset: str, model: str) -> Path:
    return output / dataset / f"network-{model}.json"


def command_development(args: argparse.Namespace) -> None:
    photos = development_photos(args.snapshot)
    if args.limit:
        photos = photos[: args.limit]
    path = _network_path(args.output, "development", args.model)
    started = time.perf_counter()
    outputs = collect_networks(photos, (args.model,), threads=args.threads)[args.model]
    seconds = [o["seconds"] for o in outputs.values() if o["seconds"] is not None]
    digest = write_json(
        path,
        {
            "identity": bundle_identity(args.model),
            "role": "development",
            "photos": outputs,
            "inference": {
                "wall_seconds": time.perf_counter() - started,
                "threads": args.threads,
                "analyse_seconds_median": _percentile(seconds, 50),
                "analyse_seconds_p95": _percentile(seconds, 95),
            },
        },
    )
    print(json.dumps({"output": str(path), "sha256": digest, "photos": len(outputs)}))


def command_report(args: argparse.Namespace) -> None:
    """Development summary of every engine from the stored network outputs."""

    photos = development_photos(args.snapshot)
    originals = load_originals(args.originals)
    networks = {}
    for model in NETWORK_MODELS:
        document = json.loads(
            _network_path(args.output, "development", model).read_text(encoding="utf-8")
        )
        if document["identity"]["weights_sha256"] != bundle_identity(model)["weights_sha256"]:
            raise ValueError("GRID_V3_NETWORK_OUTPUT_IDENTITY_MISMATCH")
        networks[model] = document["photos"]
    summary, per_engine = set_report(
        photos,
        originals=originals,
        networks=networks,
        engines=ENGINES,
        group_key=lambda r: str(r["group"]),
    )
    summary["identity"] = frozen_identity()
    summary["note"] = (
        "development = model selection set of runs 1-3 and calibration set of the hybrid_v3 "
        "gate; not an independent measurement"
    )
    digest = write_json(args.output / "development" / "summary.json", summary)
    write_json(args.output / "development" / "photos.json", per_engine)
    print(json.dumps({"summary_sha256": digest}))


def command_timing(args: argparse.Namespace) -> None:
    from .neural_grid_onnx import cpu_timing

    samples = load_samples(args.snapshot, ("development",))[: args.images + 1]
    result: dict[str, Any] = {"photos": args.images, "threads": args.threads, "models": {}}
    for model in NETWORK_MODELS:
        result["models"][model] = {
            "identity": bundle_identity(model),
            "timing": cpu_timing(BUNDLES[model], samples, args.threads),
        }
    # hybrid_v3 = run-1 network + the pure-Python gate on the production original.
    originals = load_originals(args.originals)
    document = json.loads(
        _network_path(args.output, "development", HYBRID_NETWORK).read_text(encoding="utf-8")
    )
    gate_seconds = []
    for sample in samples[1:]:
        original = originals.get(sample.image_id)
        started = time.perf_counter()
        hybrid_decision(original, document["photos"][sample.image_id]["boards"])
        gate_seconds.append(time.perf_counter() - started)
    result["hybrid_gate_seconds_per_photo"] = {
        "median": _percentile(gate_seconds, 50),
        "p95": _percentile(gate_seconds, 95),
    }
    processing = [
        int(originals[s.image_id]["original"]["processingTimeMs"])
        for s in samples[1:]
        if (originals.get(s.image_id) or {}).get("original")
        and originals[s.image_id]["original"].get("processingTimeMs") is not None
    ]
    result["production_engine_recorded_processing_ms"] = {
        "photos": len(processing),
        "median": _percentile(processing, 50),
        "p95": _percentile(processing, 95),
        "note": "processing_time_ms recorded by the import pipeline (other process and "
        "load), not measured here",
    }
    digest = write_json(args.output / "timing" / f"cpu-timing-{args.images}.json", result)
    print(json.dumps({"sha256": digest, **result}, default=str))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="grid_v3_comparison")
    commands = root.add_subparsers(dest="command", required=True)

    def add(name: str) -> argparse.ArgumentParser:
        item = commands.add_parser(name)
        item.add_argument("--output", type=Path, default=OUTPUT)
        item.add_argument("--snapshot", type=Path, default=SNAPSHOT_V2)
        item.add_argument("--originals", type=Path, default=ORIGINALS)
        item.add_argument("--threads", type=int, default=4)
        return item

    development = add("development")
    development.add_argument("--model", choices=NETWORK_MODELS, required=True)
    development.add_argument("--limit", type=int)
    add("report")
    timing = add("timing")
    timing.add_argument("--images", type=int, default=30)
    return root


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    {
        "development": command_development,
        "report": command_report,
        "timing": command_timing,
    }[args.command](args)


if __name__ == "__main__":
    main()
