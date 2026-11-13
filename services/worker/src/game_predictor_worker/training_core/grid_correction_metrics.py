"""Photo-macro correction metrics; legacy matching and correctness stay frozen."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

import numpy as np

from ..geometry_core.metrics import PhotoEvaluation
from ..geometry_core.metrics import evaluate_photo as match_photo
from .grid_evaluation import ControlPhoto, Engine, input_sha256, predictions

METRICS_VERSION = "grid-correction-metrics-v1"
# D-609: a matched board stays within its cells when no lattice node of any of the 15
# cells moves more than this fraction of the label cell's width or height.
CELL_CUT_VERSION = "grid-cell-cut-v1"
CELL_CUT_TOLERANCE = 0.10
CHECKPOINT_RULE = "validation-board-correct-photo-macro-error-earliest-v1"
PHOTO_CHECKPOINT_RULE = "validation-photo-board-correct-photo-macro-error-earliest-v1"


@dataclass(frozen=True, slots=True)
class CorrectionControlPhoto(ControlPhoto):
    full_geometry: bool
    load_with_support: Callable[[], tuple[np.ndarray, tuple[int, int, int, int]]] | None = None
    available_source_box: tuple[int, int, int, int] | None = None


@dataclass(frozen=True, slots=True)
class CorrectionPhotoEvaluation:
    matching: PhotoEvaluation
    full_geometry: bool
    normalized_error: float
    boards_within_cells: int = 0

    def as_dict(self) -> dict[str, Any]:
        result = self.matching.as_dict()
        # Unlabelled predictions cannot support any whole-photo quality claim.
        for key in ("false_boards", "duplicates", "complete_correct", "complete_correct_strict"):
            if not self.full_geometry:
                result[key] = None
        result["full_geometry"] = self.full_geometry
        result["normalized_error"] = self.normalized_error
        return result


def evaluate_photo(
    image_id: str,
    group_id: str,
    labels: list[np.ndarray[Any, Any]],
    predicted: list[tuple[np.ndarray[Any, Any], bool]],
    *,
    full_geometry: bool,
) -> CorrectionPhotoEvaluation:
    """Match once; average 24-node errors over targets, missing/invalid costs one."""
    if not labels:
        raise ValueError("Correction photos require at least one labelled board.")
    if len(labels) > 9 or (full_geometry and len(labels) != 9):
        raise ValueError("Full geometry requires exactly nine labelled boards.")
    for label in labels:
        if np.asarray(label).shape != (24, 2) or not np.isfinite(label).all():
            raise ValueError("Each target requires 24 finite nodes.")
        if float(np.linalg.norm(np.ptp(label, axis=0))) <= 0:
            raise ValueError("Target bounding-box diagonal must be positive.")
    matching = match_photo(image_id, group_id, labels, predicted)
    errors = [1.0] * len(labels)
    within = 0
    for match in matching.matches:
        nodes = np.asarray(predicted[match.prediction][0], dtype=np.float64)
        if not match.valid or not np.isfinite(nodes).all():
            continue
        label = np.asarray(labels[match.label], dtype=np.float64)
        diagonal = float(np.linalg.norm(np.ptp(label, axis=0)))
        errors[match.label] = min(
            1.0, float(np.linalg.norm(nodes - label, axis=1).mean()) / diagonal
        )
        if cell_cut_fraction(nodes, label) <= CELL_CUT_TOLERANCE:
            within += 1
    return CorrectionPhotoEvaluation(matching, full_geometry, float(np.mean(errors)), within)


def cell_cut_fraction(predicted: np.ndarray[Any, Any], label: np.ndarray[Any, Any]) -> float:
    """Largest node shift of any cell, as a fraction of that label cell's size (D-609).

    Nodes are 4 rows x 6 columns. Each shift is projected on the label cell's own
    column (top edge) and row (left edge) directions and divided by the cell's mean
    width and height, so a quarter-cell shift is 0.25 whatever the board size.
    """
    predicted = np.asarray(predicted, dtype=np.float64).reshape(4, 6, 2)
    label = np.asarray(label, dtype=np.float64).reshape(4, 6, 2)
    worst = 0.0
    for row in range(3):
        for column in range(5):
            corners = [(row, column), (row, column + 1), (row + 1, column + 1), (row + 1, column)]
            top = label[row, column + 1] - label[row, column]
            bottom = label[row + 1, column + 1] - label[row + 1, column]
            left = label[row + 1, column] - label[row, column]
            right = label[row + 1, column + 1] - label[row, column + 1]
            width = float(np.linalg.norm(top) + np.linalg.norm(bottom)) / 2
            height = float(np.linalg.norm(left) + np.linalg.norm(right)) / 2
            if width <= 0 or height <= 0:
                return float("inf")
            across = (top + bottom) / (2 * width)
            down = (left + right) / (2 * height)
            for r, c in corners:
                shift = predicted[r, c] - label[r, c]
                worst = max(
                    worst,
                    abs(float(shift @ across)) / width,
                    abs(float(shift @ down)) / height,
                )
    return worst


def measure(photos: Sequence[CorrectionPhotoEvaluation]) -> dict[str, Any]:
    """Counts plus equal-photo means; full-only evidence is explicitly nullable."""
    full = [photo.matching for photo in photos if photo.full_geometry]
    expected = sum(photo.matching.expected for photo in photos)
    matched = sum(photo.matching.matched for photo in photos)
    return {
        "photos": len(photos),
        "full_photos": len(full),
        "partial_photos": len(photos) - len(full),
        "boards_expected": expected,
        "boards_matched": matched,
        "boards_correct": sum(photo.matching.correct for photo in photos),
        "board_correct_rate": (
            float(np.mean([photo.matching.correct / photo.matching.expected for photo in photos]))
            if photos
            else None
        ),
        "detection_recall": matched / expected if expected else None,
        "normalized_error": float(np.mean([p.normalized_error for p in photos]))
        if photos
        else None,
        "photo_complete_correct": sum(photo.complete_correct_strict for photo in full)
        if full
        else None,
        "photo_complete_correct_rate": (
            sum(photo.complete_correct_strict for photo in full) / len(full) if full else None
        ),
        "false_boards": sum(photo.false_boards for photo in full) if full else None,
        "duplicate_predictions": sum(photo.duplicates for photo in full) if full else None,
    }


def checkpoint_metrics(
    photos: Sequence[CorrectionPhotoEvaluation], *, photo_first: bool = False
) -> dict[str, float]:
    measured = measure(photos)
    if not photos:
        raise ValueError("Checkpoint selection requires VALIDATION photos.")
    if photo_first and any(not photo.full_geometry for photo in photos):
        raise ValueError("Screen checkpoint selection requires every photo to be full.")
    return {
        **(
            {"photoCorrectRate": float(measured["photo_complete_correct_rate"])}
            if photo_first
            else {}
        ),
        "boardCorrectRate": float(measured["board_correct_rate"]),
        "normalizedError": float(measured["normalized_error"]),
    }


def aggregate_checkpoint_metrics(
    per_game: Sequence[Mapping[str, float]], *, photo_first: bool = False
) -> dict[str, float]:
    """Equal game weights after equal-photo aggregation within each game."""
    if not per_game:
        raise ValueError("Checkpoint selection requires at least one game.")
    for metrics in per_game:
        photo_selection_key(metrics, 0) if photo_first else selection_key(metrics, 0)
    return {
        key: float(np.mean([game[key] for game in per_game]))
        for key in (
            ("photoCorrectRate", "boardCorrectRate", "normalizedError")
            if photo_first
            else ("boardCorrectRate", "normalizedError")
        )
    }


def photo_selection_key(metrics: Mapping[str, float], step: int) -> tuple[float, float, float, int]:
    if set(metrics) != {"photoCorrectRate", "boardCorrectRate", "normalizedError"}:
        raise ValueError("Screen checkpoint requires exact photo/board/error metrics.")
    photo = metrics["photoCorrectRate"]
    if isinstance(photo, bool) or not np.isfinite(photo) or not 0 <= photo <= 1:
        raise ValueError("Photo correctness must be a finite unit rate.")
    return (
        photo,
        *selection_key(
            {key: value for key, value in metrics.items() if key != "photoCorrectRate"}, step
        ),
    )


def selection_key(metrics: Mapping[str, float], step: int) -> tuple[float, float, int]:
    """Larger is better; REGRESSION must never be passed by the training caller."""
    if set(metrics) != {"boardCorrectRate", "normalizedError"} or any(
        isinstance(value, bool) or not np.isfinite(value) or not 0 <= value <= 1
        for value in metrics.values()
    ):
        raise ValueError("Checkpoint metrics must be finite unit rates.")
    if type(step) is not int or step < 0:
        raise ValueError("Checkpoint step must be a non-negative integer.")
    return metrics["boardCorrectRate"], -metrics["normalizedError"], -step


def measure_role(
    photos: Sequence[CorrectionControlPhoto],
    base: Engine,
    candidate: Engine,
    *,
    before_photo: Callable[[int], None] = lambda _index: None,
    observation: Callable[[CorrectionControlPhoto, Any, Mapping[str, Any]], list[dict[str, Any]]]
    | None = None,
    content_observation: Callable[[CorrectionControlPhoto, Any, Mapping[str, Any]], dict[str, Any]]
    | None = None,
    cell_cut: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Role summary; ``cell_cut`` adds the gate v5 boards-within-cells counts (D-609)."""
    evaluated: dict[str, list[CorrectionPhotoEvaluation]] = {"base": [], "candidate": []}
    groups: dict[str, dict[str, list[CorrectionPhotoEvaluation]]] = defaultdict(
        lambda: {"base": [], "candidate": []}
    )
    details = []
    if len({photo.source_id for photo in photos}) != len(photos):
        raise ValueError("A control photo can only be measured once per role.")
    for index, photo in enumerate(photos):
        before_photo(index)
        if photo.load_with_support is None:
            rgb = photo.load()
        else:
            rgb, box = photo.load_with_support()
            photo = replace(photo, available_source_box=box)
        row: dict[str, Any] = {"sourceId": photo.source_id, "groupId": photo.group_id}
        observed = {}
        for name, engine in (("base", base), ("candidate", candidate)):
            found = engine.analyse(rgb)
            result = evaluate_photo(
                photo.source_id,
                photo.group_id,
                list(photo.labels),
                predictions(found),
                full_geometry=photo.full_geometry,
            )
            evaluated[name].append(result)
            groups[photo.group_id][name].append(result)
            row[name] = result.as_dict()
            if observation is not None or content_observation is not None:
                observed[name] = (found, result, engine)
        if content_observation is not None:
            row["contentEvaluation"] = content_observation(photo, rgb, observed)
            if observation is not None and hasattr(observation, "production_observation"):
                observation.production_observation = row["contentEvaluation"]
        if observation is not None:
            row["calibrationTargets"] = observation(photo, rgb, observed)
            proofs = getattr(observation, "input_proofs", None)
            if proofs:
                row["inputContentEvidence"] = proofs
        details.append(row)
    summary: dict[str, Any] = {
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
    if cell_cut:
        summary["cellCut"] = cell_cut_summary(evaluated["base"], evaluated["candidate"])
    return summary, details


def cell_cut_summary(
    base: Sequence[CorrectionPhotoEvaluation], candidate: Sequence[CorrectionPhotoEvaluation]
) -> dict[str, Any]:
    return {
        "version": CELL_CUT_VERSION,
        "tolerance": CELL_CUT_TOLERANCE,
        "base": sum(photo.boards_within_cells for photo in base),
        "candidate": sum(photo.boards_within_cells for photo in candidate),
    }
