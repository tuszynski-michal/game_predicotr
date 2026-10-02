"""TASK-0803 calibration of the hybrid_v3 gate on the development role (CPU, ONNX).

``python -m game_predictor_worker.vision_lab.hybrid_v3_calibration --bundle <export dir>
--output <new dir>``

Development is the calibration set here; an independent measurement belongs to TASK-0804.
Only the ``development`` role is read, through the ``neural_grid`` role guard; ``gold`` and
the D-456 holdouts are refused before the snapshot is opened.

Reference in the lab = the snapshot labels. For level B photos the label *is* the
production engine output (realistic shadow simulation). For level S the label is a
correction and the original production output is not in the snapshot: S is measured as
"network versus label correction" and reported separately.

Everything below the threshold grid and the selection rule was recorded before the
calibration was run (TASK-0803, ``THRESHOLD_GRID`` and ``SELECTION_RULE``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from collections import Counter
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any, Final

import numpy as np

from .hybrid_v3_gate import (
    BOARD_REASONS,
    GATE_VERSION,
    PHOTO_REASONS,
    Comparison,
    GateThresholds,
    NetworkBoard,
    PhotoDecision,
    ReferenceBoard,
    compare,
    decide,
)
from .neural_grid_data import FloatArray, PhotoSample, load_samples, open_snapshot, prefetch
from .neural_grid_metrics import MAX_NME, MAX_NODE_ERROR, board_errors, evaluate_photo
from .neural_grid_protocol import RoleForbiddenError, require_roles

CALIBRATION_VERSION: Final = "hybrid-v3-calibration-v1"
CALIBRATION_ROLE: Final = "development"
NETWORK_FILE: Final = "network-development.json"
RESULT_FILE: Final = "calibration.json"

# Recorded before the calibration run (TASK-0803). Finite grid, 4 x 7 x 3 = 84 points.
THRESHOLD_GRID: Final[dict[str, tuple[float, ...]]] = {
    "min_quad_iou": (0.80, 0.85, 0.90, 0.95),
    "max_node_error": (0.005, 0.0075, 0.01, 0.015, 0.02, 0.03, 0.04),
    "max_fit_residual": (0.0025, 0.005, 0.01),
}
MAX_CONFIDENT_BOARD_ERROR_RATE: Final = 0.005
PREFERRED_FIT_RESIDUAL: Final = 0.005
SELECTION_RULE: Final[dict[str, Any]] = {
    "version": CALIBRATION_VERSION,
    "role": "development (calibration set, not an independent measurement)",
    "reference": "snapshot labels (level B = production engine output, level S = correction)",
    "board_error": (
        "a confident board is erroneous when its network grid or its output grid is not "
        "D-483 correct against the label (structurally valid, NME <= 0.02 and largest node "
        "error <= 0.05 of the label TL-BR diagonal); the network grid is included because "
        "in the lab the reference is the label, so choosing reference nodes would hide an "
        "error by construction"
    ),
    "constraint": (
        "erroneous confident boards / confident boards <= 0.005, separately for level B, "
        "level S and all photos (no confident board = 0 errors)"
    ),
    "objective": "maximum share of confident photos over all development photos",
    "tie_break": [
        "fewer erroneous confident boards (all photos)",
        "higher min_quad_iou",
        "lower max_node_error",
        "max_fit_residual closest to 0.005 (a priori: the lab cannot rank node sources, "
        "because the reference is the label)",
    ],
    "no_feasible_point": "no thresholds are selected; the report says so",
}
LEVELS: Final = ("B", "S")


class CalibrationError(ValueError):
    pass


# --- network outputs -------------------------------------------------------------------------


def _finite_or_none(value: float | None) -> float | None:
    return None if value is None or not math.isfinite(value) else float(value)


def network_record(boards: list[NetworkBoard]) -> list[dict[str, Any]]:
    return [
        {
            "nodes": None if board.nodes is None else np.asarray(board.nodes).tolist(),
            "fit_residual": _finite_or_none(board.fit_residual),
            "fit_inliers": int(board.fit_inliers),
            "fit_failed": bool(board.fit_failed),
            "score": float(board.score),
            "reasons": list(board.reasons),
        }
        for board in boards
    ]


def network_from_record(records: list[dict[str, Any]]) -> list[NetworkBoard]:
    return [
        NetworkBoard(
            nodes=None if item["nodes"] is None else np.asarray(item["nodes"], np.float32),
            fit_residual=item["fit_residual"],
            fit_inliers=int(item["fit_inliers"]),
            fit_failed=bool(item["fit_failed"]),
            score=float(item["score"]),
            reasons=tuple(item["reasons"]),
        )
        for item in records
    ]


def load_calibration_samples(
    snapshot: Path, roles: tuple[str, ...] = (CALIBRATION_ROLE,)
) -> list[PhotoSample]:
    """Development only; any other role (also ``training``) is refused before reading."""

    require_roles(roles)
    if tuple(roles) != (CALIBRATION_ROLE,):
        raise RoleForbiddenError("HYBRID_V3_CALIBRATION_ROLE_FORBIDDEN")
    return load_samples(snapshot, roles)


def collect_network(
    engine: Any, samples: list[PhotoSample], decode_workers: int = 2
) -> dict[str, dict[str, Any]]:
    """``engine.analyse`` on every photo; a decode failure is recorded, never dropped."""

    from .hybrid_v3_engine import network_boards

    photos: dict[str, dict[str, Any]] = {}
    for sample, rgb in prefetch(samples, decode_workers):
        if isinstance(rgb, Exception):
            photos[sample.image_id] = {"error": str(rgb), "boards": [], "seconds": None}
            continue
        started = time.perf_counter()
        boards = network_boards(engine.analyse(rgb))
        photos[sample.image_id] = {
            "error": None,
            "boards": network_record(boards),
            "seconds": time.perf_counter() - started,
        }
    return photos


# --- sweep -----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PhotoInput:
    image_id: str
    level: str
    labels: tuple[FloatArray, ...]
    comparison: Comparison
    error: str | None


def prepare(samples: list[PhotoSample], network: dict[str, dict[str, Any]]) -> list[PhotoInput]:
    missing = sorted(sample.image_id for sample in samples if sample.image_id not in network)
    if missing:
        raise CalibrationError(f"HYBRID_V3_NETWORK_OUTPUT_MISSING:{missing[:5]}")
    inputs = []
    for sample in samples:
        reference = [ReferenceBoard(i, board.nodes) for i, board in enumerate(sample.boards)]
        record = network[sample.image_id]
        boards = network_from_record(record["boards"])
        inputs.append(
            PhotoInput(
                sample.image_id,
                sample.level,
                tuple(board.nodes for board in sample.boards),
                compare(reference, boards),
                record.get("error"),
            )
        )
    return inputs


def _correct(nodes: FloatArray | None, valid: bool, label: FloatArray) -> bool:
    if nodes is None or not valid:
        return False
    mean_error, max_error = board_errors(nodes, label)
    return mean_error <= MAX_NME and max_error <= MAX_NODE_ERROR


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _empty_block() -> dict[str, Any]:
    return {
        "photos": 0,
        "photos_confident": 0,
        "photos_confident_with_error": 0,
        "label_boards": 0,
        "network_boards": 0,
        "boards_decided": 0,
        "boards_confident": 0,
        "confident_boards_error": 0,
        "confident_boards_output_error": 0,
        "confident_boards_network_nodes": 0,
        "board_reasons": Counter(),
        "photo_reasons": Counter(),
    }


def _finish(block: dict[str, Any]) -> dict[str, Any]:
    result = dict(block)
    result["photo_coverage"] = _rate(block["photos_confident"], block["photos"])
    result["board_coverage"] = _rate(block["boards_confident"], block["label_boards"])
    result["confident_board_error_rate"] = (
        block["confident_boards_error"] / block["boards_confident"]
        if block["boards_confident"]
        else 0.0
    )
    result["confident_board_output_error_rate"] = (
        block["confident_boards_output_error"] / block["boards_confident"]
        if block["boards_confident"]
        else 0.0
    )
    result["board_reasons"] = {r: block["board_reasons"].get(r, 0) for r in BOARD_REASONS}
    result["photo_reasons"] = {r: block["photo_reasons"].get(r, 0) for r in PHOTO_REASONS}
    return result


def _add(block: dict[str, Any], photo: PhotoInput, decision: PhotoDecision) -> None:
    c = photo.comparison
    block["photos"] += 1
    block["label_boards"] += len(photo.labels)
    block["network_boards"] += decision.network_count
    block["boards_decided"] += len(decision.boards)
    photo_error = False
    for board in decision.boards:
        for reason in board.reasons:
            block["board_reasons"][reason] += 1
        if board.state != "confident":
            continue
        i, j = board.network_index, board.reference_index
        assert i is not None and j is not None
        label = photo.labels[j]
        network_ok = _correct(c.network_nodes[i], c.network_valid[i], label)
        output_valid = (
            c.network_valid[i] if board.node_source == "network" else c.reference_valid[j]
        )
        output_ok = _correct(board.nodes, output_valid, label)
        block["boards_confident"] += 1
        block["confident_boards_network_nodes"] += board.node_source == "network"
        block["confident_boards_error"] += not (network_ok and output_ok)
        block["confident_boards_output_error"] += not output_ok
        photo_error |= not (network_ok and output_ok)
    for reason in decision.reasons:
        block["photo_reasons"][reason] += 1
    if decision.state == "confident":
        block["photos_confident"] += 1
        block["photos_confident_with_error"] += photo_error


def evaluate_configuration(
    photos: list[PhotoInput], thresholds: GateThresholds
) -> tuple[dict[str, Any], list[PhotoDecision]]:
    blocks = {"all": _empty_block(), **{level: _empty_block() for level in LEVELS}}
    decisions = []
    for photo in photos:
        decision = decide(photo.comparison, thresholds)
        decisions.append(decision)
        _add(blocks["all"], photo, decision)
        _add(blocks.setdefault(photo.level, _empty_block()), photo, decision)
    summary = {name: _finish(block) for name, block in sorted(blocks.items())}
    feasible = all(
        summary[name]["confident_board_error_rate"] <= MAX_CONFIDENT_BOARD_ERROR_RATE
        for name in summary
    )
    return {"thresholds": thresholds.as_dict(), "feasible": feasible, **summary}, decisions


def grid_points() -> list[GateThresholds]:
    return [
        GateThresholds(iou, nodes, residual)
        for iou, nodes, residual in product(
            THRESHOLD_GRID["min_quad_iou"],
            THRESHOLD_GRID["max_node_error"],
            THRESHOLD_GRID["max_fit_residual"],
        )
    ]


def selection_key(point: dict[str, Any]) -> tuple[float, ...]:
    """Smaller is better (the recorded rule; only feasible points are ranked)."""

    t = point["thresholds"]
    return (
        -float(point["all"]["photo_coverage"] or 0.0),
        float(point["all"]["confident_boards_error"]),
        -t["min_quad_iou"],
        t["max_node_error"],
        abs(t["max_fit_residual"] - PREFERRED_FIT_RESIDUAL),
        t["max_fit_residual"],
    )


def _point_row(point: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {"thresholds": point["thresholds"], "feasible": point["feasible"]}
    for name in ("all", *LEVELS):
        if name not in point:
            continue
        block = point[name]
        row[name] = {
            key: block[key]
            for key in (
                "photos",
                "photos_confident",
                "photo_coverage",
                "boards_confident",
                "board_coverage",
                "confident_boards_error",
                "confident_board_error_rate",
                "confident_boards_output_error",
                "confident_boards_network_nodes",
                "photos_confident_with_error",
            )
        }
    return row


def incorrect_label_routing(
    photos: list[PhotoInput],
    decisions: list[PhotoDecision],
    incorrect: dict[str, set[int]],
) -> dict[str, Any]:
    """Where the gate sends label boards that a metric marked incorrect (per level)."""

    result: dict[str, Any] = {}
    for level in LEVELS:
        routed: Counter[str] = Counter()
        reasons: Counter[str] = Counter()
        items = []
        for photo, decision in zip(photos, decisions, strict=True):
            if photo.level != level:
                continue
            for j in sorted(incorrect.get(photo.image_id, set())):
                board = next((b for b in decision.boards if b.reference_index == j), None)
                state = "missing" if board is None else board.state
                routed[state] += 1
                if board is not None:
                    reasons.update(board.reasons)
                items.append(
                    {
                        "image_id": photo.image_id,
                        "label_index": j,
                        "state": state,
                        "reasons": [] if board is None else list(board.reasons),
                        "node_error_max": None if board is None else board.node_error_max,
                        "quad_iou": None if board is None else board.quad_iou,
                    }
                )
        result[level] = {
            "incorrect_boards": sum(routed.values()),
            "needs_review": routed["needs_review"],
            "confident": routed["confident"],
            "missing": routed["missing"],
            "reasons": dict(sorted(reasons.items())),
            "boards": items,
        }
    return result


def onnx_incorrect_labels(photos: list[PhotoInput]) -> tuple[dict[str, set[int]], dict[str, int]]:
    """D-483 on the network grids of this calibration (ONNX CPU), unchanged metric code."""

    incorrect: dict[str, set[int]] = {}
    counts: Counter[str] = Counter()
    for photo in photos:
        c = photo.comparison
        predictions = [
            (nodes, valid)
            for nodes, valid in zip(c.network_nodes, c.network_valid, strict=True)
            if nodes is not None
        ]
        evaluation = evaluate_photo(photo.image_id, photo.level, list(photo.labels), predictions)
        correct = {m.label for m in evaluation.matches if m.correct}
        missed = {j for j in range(len(photo.labels)) if j not in correct}
        if missed:
            incorrect[photo.image_id] = missed
            counts[photo.level] += len(missed)
    return incorrect, dict(sorted(counts.items()))


def evaluation_incorrect_labels(path: Path) -> tuple[dict[str, set[int]], dict[str, int]]:
    """Incorrect label boards of the run-1 development evaluation (PyTorch, GPU)."""

    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("role") != CALIBRATION_ROLE:
        raise CalibrationError("HYBRID_V3_EVALUATION_ROLE_MISMATCH")
    incorrect: dict[str, set[int]] = {}
    counts: Counter[str] = Counter()
    for photo in document["photos"]:
        correct = {m["label"] for m in photo["matches"] if m["correct"]}
        missed = {j for j in range(int(photo["expected"])) if j not in correct}
        if missed:
            incorrect[photo["image_id"]] = missed
            counts[photo["level"]] += len(missed)
    return incorrect, dict(sorted(counts.items()))


def network_statistics(photos: list[PhotoInput]) -> dict[str, Any]:
    residuals = [
        r
        for p in photos
        for r in p.comparison.network_residual
        if r is not None and math.isfinite(r)
    ]
    max_errors = [pair.node_error_max for p in photos for pair in p.comparison.pairs]
    ious = [pair.quad_iou for p in photos for pair in p.comparison.pairs]

    def quantiles(values: list[float]) -> dict[str, float] | None:
        if not values:
            return None
        return {f"p{q}": float(np.percentile(values, q)) for q in (5, 25, 50, 75, 95, 99)} | {
            "max": float(np.max(values)),
            "min": float(np.min(values)),
        }

    return {
        "network_fit_residual": quantiles(residuals),
        "pair_node_error_max": quantiles(max_errors),
        "pair_quad_iou": quantiles(ious),
        "pairs": len(max_errors),
        "photos_with_decode_error": sum(p.error is not None for p in photos),
    }


def calibrate(
    photos: list[PhotoInput],
    *,
    evaluation_incorrect: dict[str, set[int]] | None = None,
) -> dict[str, Any]:
    """Deterministic sweep over ``THRESHOLD_GRID`` and selection by ``SELECTION_RULE``."""

    points = []
    decisions_by_point = []
    for thresholds in grid_points():
        point, decisions = evaluate_configuration(photos, thresholds)
        points.append(point)
        decisions_by_point.append(decisions)
    feasible = [index for index, point in enumerate(points) if point["feasible"]]
    selected_index = min(feasible, key=lambda i: selection_key(points[i])) if feasible else None
    curve = sorted(
        (_point_row(point) for point in points),
        key=lambda row: (
            -row["all"]["photo_coverage"],
            -row["thresholds"]["min_quad_iou"],
            row["thresholds"]["max_node_error"],
            row["thresholds"]["max_fit_residual"],
        ),
    )
    result: dict[str, Any] = {
        "version": CALIBRATION_VERSION,
        "gate_version": GATE_VERSION,
        "threshold_grid": {k: list(v) for k, v in THRESHOLD_GRID.items()},
        "selection_rule": SELECTION_RULE,
        "max_confident_board_error_rate": MAX_CONFIDENT_BOARD_ERROR_RATE,
        "photos": len(photos),
        "photos_by_level": dict(sorted(Counter(p.level for p in photos).items())),
        "network": network_statistics(photos),
        "feasible_points": len(feasible),
        "curve": curve,
        "selected": None,
    }
    onnx_incorrect, onnx_counts = onnx_incorrect_labels(photos)
    result["onnx_incorrect_label_boards"] = onnx_counts
    if selected_index is None:
        return result
    selected = points[selected_index]
    decisions = decisions_by_point[selected_index]
    result["selected"] = selected
    result["selected_photo_states"] = [
        {
            "image_id": photo.image_id,
            "level": photo.level,
            "state": decision.state,
            "reasons": list(decision.reasons),
            "reference_count": decision.reference_count,
            "network_count": decision.network_count,
            "boards": [
                {
                    "reference_index": b.reference_index,
                    "network_index": b.network_index,
                    "state": b.state,
                    "reasons": list(b.reasons),
                    "node_source": b.node_source,
                    "quad_iou": b.quad_iou,
                    "node_error_max": b.node_error_max,
                    "node_error_mean": b.node_error_mean,
                    "fit_residual": b.fit_residual,
                }
                for b in decision.boards
            ],
        }
        for photo, decision in zip(photos, decisions, strict=True)
    ]
    result["routing_onnx_incorrect"] = incorrect_label_routing(photos, decisions, onnx_incorrect)
    if evaluation_incorrect is not None:
        result["routing_run1_evaluation_incorrect"] = incorrect_label_routing(
            photos, decisions, evaluation_incorrect
        )
    return result


# --- CLI -------------------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(args: argparse.Namespace) -> dict[str, Any]:
    from .neural_grid_inference import onnx_engine

    samples = load_calibration_samples(args.snapshot)
    if args.limit:
        samples = samples[: args.limit]
    snapshot_id = open_snapshot(args.snapshot).snapshot_id
    bundle = json.loads((args.bundle / "bundle.json").read_text(encoding="utf-8"))
    identity = {
        "bundle": str(args.bundle),
        "bundle_json_sha256": _sha256(args.bundle / "bundle.json"),
        "weights_sha256": bundle["weights_sha256"],
        "files": bundle["files"],
        "provenance": bundle.get("provenance"),
        "snapshot_id": snapshot_id,
        "role": CALIBRATION_ROLE,
        "image_ids_sha256": hashlib.sha256(
            "\n".join(s.image_id for s in samples).encode()
        ).hexdigest(),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    network_path = args.output / NETWORK_FILE
    if args.reuse_network and network_path.exists():
        cached = json.loads(network_path.read_text(encoding="utf-8"))
        if cached["identity"] != identity:
            raise CalibrationError("HYBRID_V3_NETWORK_CACHE_IDENTITY_MISMATCH")
        network = cached["photos"]
        inference = cached["inference"]
    else:
        engine = onnx_engine(args.bundle, threads=args.threads)
        started = time.perf_counter()
        network = collect_network(engine, samples)
        seconds = [p["seconds"] for p in network.values() if p["seconds"] is not None]
        inference = {
            "provider": "CPUExecutionProvider",
            "intra_op_threads": args.threads,
            "photos": len(network),
            "wall_seconds": time.perf_counter() - started,
            "analyse_seconds_median": float(np.median(seconds)) if seconds else None,
            "analyse_seconds_p95": float(np.percentile(seconds, 95)) if seconds else None,
        }
        network_path.write_text(
            json.dumps({"identity": identity, "inference": inference, "photos": network}),
            encoding="utf-8",
        )
    photos = prepare(samples, network)
    evaluation = None
    if args.evaluation is not None:
        evaluation, evaluation_counts = evaluation_incorrect_labels(args.evaluation)
    result = calibrate(photos, evaluation_incorrect=evaluation)
    result["identity"] = identity
    result["inference"] = inference
    if args.evaluation is not None:
        result["run1_evaluation"] = {
            "path": str(args.evaluation),
            "sha256": _sha256(args.evaluation),
            "incorrect_label_boards": evaluation_counts,
        }
    (args.output / RESULT_FILE).write_text(
        json.dumps(result, indent=1, sort_keys=True, default=str), encoding="utf-8"
    )
    return result


def parser() -> argparse.ArgumentParser:
    from .neural_grid_runs import DEFAULT_SNAPSHOT

    root = argparse.ArgumentParser(prog="hybrid_v3_calibration")
    root.add_argument("--bundle", type=Path, required=True)
    root.add_argument("--output", type=Path, required=True)
    root.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    root.add_argument("--threads", type=int, default=4)
    root.add_argument("--limit", type=int)
    root.add_argument("--evaluation", type=Path, help="run development evaluation JSON")
    root.add_argument("--reuse-network", action="store_true")
    return root


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    result = run(args)
    selected = result["selected"]
    print(
        json.dumps(
            {
                "output": str(args.output / RESULT_FILE),
                "feasible_points": result["feasible_points"],
                "selected": None if selected is None else _point_row(selected),
                "onnx_incorrect_label_boards": result["onnx_incorrect_label_boards"],
                "inference": result["inference"],
            },
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
