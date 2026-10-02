"""D-483 metrics frozen before training (``METRIC_DEFINITION``), engine independent.

Predictions and labels are matched per photo by a Hungarian assignment maximising quad
IoU over pairs with IoU >= 0.5. A board is correct when its NME (mean node error over
the label TL-BR diagonal, the T05 normalization) is <= 0.02 and its largest node error is
<= 0.05 of the same diagonal. A photo is complete and correct when every label board is
matched and correct and no prediction is a false board (IoU < 0.5 with every label).
The image-macro score is T05's: per label min(1, NME), missing or invalid = 1, mean per
photo, then mean over photos. Nothing here assumes a number of boards per photo.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

from .neural_grid_protocol import METRIC_DEFINITION

MIN_IOU: float = METRIC_DEFINITION["match_min_iou"]
MAX_NME: float = METRIC_DEFINITION["board_correct_max_nme"]
MAX_NODE_ERROR: float = METRIC_DEFINITION["board_correct_max_node_error"]
_CORNERS = [0, 5, 23, 18]
_UNMATCHABLE = 1e9


def quad_iou(left: NDArray[Any], right: NDArray[Any]) -> float:
    a = cv2.convexHull(np.asarray(left, dtype=np.float32).reshape(-1, 1, 2))
    b = cv2.convexHull(np.asarray(right, dtype=np.float32).reshape(-1, 1, 2))
    area_a, area_b = float(cv2.contourArea(a)), float(cv2.contourArea(b))
    if area_a <= 0 or area_b <= 0:
        return 0.0
    intersection, _ = cv2.intersectConvexConvex(a, b)
    union = area_a + area_b - float(intersection)
    return max(0.0, float(intersection) / union) if union > 0 else 0.0


def hungarian(cost: NDArray[np.float64]) -> list[tuple[int, int]]:
    """Minimum-cost assignment for a rectangular matrix (Kuhn-Munkres with potentials)."""

    matrix = np.asarray(cost, dtype=np.float64)
    if matrix.size == 0:
        return []
    transposed = matrix.shape[0] > matrix.shape[1]
    if transposed:
        matrix = matrix.T
    n, m = matrix.shape
    u, v = np.zeros(n + 1), np.zeros(m + 1)
    p = np.zeros(m + 1, dtype=int)
    way = np.zeros(m + 1, dtype=int)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = np.full(m + 1, np.inf)
        used = np.zeros(m + 1, dtype=bool)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], np.inf, 0
            for j in range(1, m + 1):
                if not used[j]:
                    current = matrix[i0 - 1, j - 1] - u[i0] - v[j]
                    if current < minv[j]:
                        minv[j], way[j] = current, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    pairs = [(int(p[j]) - 1, j - 1) for j in range(1, m + 1) if p[j] != 0]
    if transposed:
        pairs = [(b, a) for a, b in pairs]
    return sorted(pairs)


@dataclass(slots=True)
class BoardMatch:
    prediction: int
    label: int
    iou: float
    valid: bool
    nme: float | None
    max_error: float | None
    correct: bool


@dataclass(slots=True)
class PhotoEvaluation:
    image_id: str
    level: str
    expected: int
    predicted: int
    matches: list[BoardMatch] = field(default_factory=list)
    false_boards: int = 0
    duplicates: int = 0
    macro_cost: float = 1.0

    @property
    def matched(self) -> int:
        return len(self.matches)

    @property
    def correct(self) -> int:
        return sum(match.correct for match in self.matches)

    @property
    def complete_correct(self) -> bool:
        return self.correct == self.expected and self.false_boards == 0

    @property
    def complete_correct_strict(self) -> bool:
        return self.complete_correct and self.duplicates == 0

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value.update(
            matched=self.matched,
            correct=self.correct,
            complete_correct=self.complete_correct,
            complete_correct_strict=self.complete_correct_strict,
        )
        return value


def board_errors(predicted: NDArray[Any], label: NDArray[Any]) -> tuple[float, float]:
    predicted = np.asarray(predicted, dtype=np.float64).reshape(24, 2)
    label = np.asarray(label, dtype=np.float64).reshape(24, 2)
    diagonal = max(float(np.linalg.norm(label[23] - label[0])), 1e-6)
    errors = np.linalg.norm(predicted - label, axis=1)
    return float(errors.mean() / diagonal), float(errors.max() / diagonal)


def evaluate_photo(
    image_id: str,
    level: str,
    labels: list[NDArray[Any]],
    predictions: list[tuple[NDArray[Any], bool]],
) -> PhotoEvaluation:
    """``predictions`` are (24 nodes, structurally valid) pairs in source pixels."""

    result = PhotoEvaluation(image_id, level, len(labels), len(predictions))
    ious = np.zeros((len(predictions), len(labels)))
    for i, (nodes, _) in enumerate(predictions):
        for j, label in enumerate(labels):
            ious[i, j] = quad_iou(np.asarray(nodes)[_CORNERS], np.asarray(label)[_CORNERS])
    cost = np.where(ious >= MIN_IOU, 1.0 - ious, _UNMATCHABLE)
    assigned = [(i, j) for i, j in hungarian(cost) if ious[i, j] >= MIN_IOU]
    costs = [1.0] * len(labels)
    for i, j in assigned:
        nodes, valid = predictions[i]
        nme, max_error = (
            board_errors(nodes, labels[j]) if np.isfinite(nodes).all() else (None, None)
        )
        usable = valid and nme is not None
        correct = bool(
            usable
            and nme is not None
            and max_error is not None
            and nme <= MAX_NME
            and max_error <= MAX_NODE_ERROR
        )
        result.matches.append(
            BoardMatch(i, j, float(ious[i, j]), bool(valid), nme, max_error, correct)
        )
        if usable and nme is not None:
            costs[j] = min(1.0, nme)
    taken = {i for i, _ in assigned}
    for i in range(len(predictions)):
        if i in taken:
            continue
        if len(labels) and ious[i].max() >= MIN_IOU:
            result.duplicates += 1
        else:
            result.false_boards += 1
    result.macro_cost = float(np.mean(costs)) if labels else (1.0 if predictions else 0.0)
    return result


def _percentile(values: list[float], q: float) -> float | None:
    return float(np.percentile(values, q)) if values else None


def summarize(photos: list[PhotoEvaluation]) -> dict[str, Any]:
    def block(items: list[PhotoEvaluation]) -> dict[str, Any]:
        nme = [m.nme for p in items for m in p.matches if m.valid and m.nme is not None]
        max_error = [
            m.max_error for p in items for m in p.matches if m.valid and m.max_error is not None
        ]
        expected = sum(p.expected for p in items)
        complete = sum(p.complete_correct for p in items)
        return {
            "photos": len(items),
            "photo_complete_correct": complete,
            "photo_complete_correct_rate": complete / len(items) if items else None,
            "photo_complete_correct_strict": sum(p.complete_correct_strict for p in items),
            "image_macro": float(np.mean([p.macro_cost for p in items])) if items else None,
            "boards_expected": expected,
            "boards_predicted": sum(p.predicted for p in items),
            "boards_matched": sum(p.matched for p in items),
            "boards_correct": sum(p.correct for p in items),
            "board_recovery_rate": sum(p.correct for p in items) / expected if expected else None,
            "detection_recall": sum(p.matched for p in items) / expected if expected else None,
            "boards_invalid": sum(not m.valid for p in items for m in p.matches),
            "false_boards": sum(p.false_boards for p in items),
            "photos_with_false_boards": sum(p.false_boards > 0 for p in items),
            "duplicate_predictions": sum(p.duplicates for p in items),
            "nme_median": _percentile(nme, 50),
            "nme_p95": _percentile(nme, 95),
            "max_node_error_median": _percentile(max_error, 50),
            "max_node_error_p95": _percentile(max_error, 95),
        }

    by_level: dict[str, list[PhotoEvaluation]] = defaultdict(list)
    for photo in photos:
        by_level[photo.level].append(photo)
    return {
        "definition": METRIC_DEFINITION,
        **block(photos),
        "by_level": {level: block(items) for level, items in sorted(by_level.items())},
    }


def selection_key(summary: dict[str, Any], round_index: int) -> tuple[float, float, int]:
    """Larger is better: complete-correct rate, then lower image-macro, then earlier round."""

    return (
        float(summary["photo_complete_correct_rate"] or 0.0),
        -float(summary["image_macro"] if summary["image_macro"] is not None else 1.0),
        -round_index,
    )
