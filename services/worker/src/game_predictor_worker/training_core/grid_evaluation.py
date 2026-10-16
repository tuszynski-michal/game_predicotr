"""Base-versus-candidate measurement of one control role (TASK-0997, D-559).

Engine independent and database free. Both engines analyse the very same decoded
frame of every photo, from the original image (no label corners), and each photo is
scored by the frozen ``neural-grid-metrics-v1`` D-483 metrics: a missing board lowers
the matched and correct counts and costs 1 in image-macro; an extra detection is a false
board, or a duplicate when it overlaps an already matched board. Nothing here chooses a
checkpoint; it only measures exported models.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from ..geometry_core.lattice import structurally_valid
from ..geometry_core.metrics import PhotoEvaluation, evaluate_photo, summarize
from ..geometry_core.settings import METRIC_DEFINITION

METRICS_VERSION = str(METRIC_DEFINITION["version"])


class Engine(Protocol):
    def analyse(self, rgb: Any) -> list[Any]: ...


@dataclass(frozen=True, slots=True)
class ControlPhoto:
    """One used control photo: identity, recording group and label nodes per board."""

    source_id: str
    group_id: str
    original_sha256: str
    labels: tuple[np.ndarray, ...]
    load: Callable[[], np.ndarray]


def predictions(detections: Iterable[Any]) -> list[tuple[np.ndarray, bool]]:
    """Every decoded board with nodes; structural validity decides usability."""
    result = []
    for detection in detections:
        if detection.nodes is None:
            continue
        nodes = np.asarray(detection.nodes, dtype=np.float32)
        result.append((nodes, bool(np.isfinite(nodes).all() and structurally_valid(nodes))))
    return result


def measure(photos: Sequence[PhotoEvaluation]) -> dict[str, Any]:
    """Closed metric block of the v2 report (counts are exact, rates derive from them)."""
    summary = summarize(list(photos))
    expected = int(summary["boards_expected"])
    return {
        "photos": int(summary["photos"]),
        "photo_complete_correct": int(summary["photo_complete_correct"]),
        "photo_complete_correct_rate": summary["photo_complete_correct_rate"],
        "boards_expected": expected,
        "boards_correct": int(summary["boards_correct"]),
        "board_correct_rate": summary["boards_correct"] / expected if expected else None,
        "boards_matched": int(summary["boards_matched"]),
        "detection_recall": summary["detection_recall"],
        "false_boards": int(summary["false_boards"]),
        "duplicate_predictions": int(summary["duplicate_predictions"]),
        "image_macro": summary["image_macro"],
        "nme_p95": summary["nme_p95"],
        "max_node_error_p95": summary["max_node_error_p95"],
    }


def input_sha256(photos: Sequence[ControlPhoto]) -> str:
    """Identity of the exact inputs both models received."""
    identity = [[photo.source_id, photo.original_sha256] for photo in photos]
    return hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()


def measure_role(
    photos: Sequence[ControlPhoto],
    base: Engine,
    candidate: Engine,
    *,
    before_photo: Callable[[int], None] = lambda _index: None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Role summary for both models and the per-photo detail rows, in input order."""
    evaluated: dict[str, list[PhotoEvaluation]] = {"base": [], "candidate": []}
    groups: dict[str, dict[str, list[PhotoEvaluation]]] = defaultdict(
        lambda: {"base": [], "candidate": []}
    )
    details = []
    for index, photo in enumerate(photos):
        before_photo(index)
        rgb = photo.load()
        labels = list(photo.labels)
        row: dict[str, Any] = {"sourceId": photo.source_id, "groupId": photo.group_id}
        for name, engine in (("base", base), ("candidate", candidate)):
            result = evaluate_photo(
                photo.source_id, photo.group_id, labels, predictions(engine.analyse(rgb))
            )
            evaluated[name].append(result)
            groups[photo.group_id][name].append(result)
            row[name] = result.as_dict()
        details.append(row)
    summary = {
        "photos": len(photos),
        "inputSha256": input_sha256(photos),
        "base": measure(evaluated["base"]),
        "candidate": measure(evaluated["candidate"]),
        "recordings": [
            {
                "groupId": group,
                "base": measure(groups[group]["base"]),
                "candidate": measure(groups[group]["candidate"]),
            }
            for group in sorted(groups)
        ],
    }
    return summary, details
