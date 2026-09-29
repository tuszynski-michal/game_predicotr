"""Pure nearest-reference symbol proposals from operator-verified cells.

A proposal is advisory evidence only. It never represents an operator decision
and callers must not persist it as one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

REFERENCE_LIBRARY_VERSION = "symbol-reference-library-v1"
NEIGHBOUR_COUNT = 7
CROP_SIZE = 64
_HOG_GRID = 4
_HOG_BINS = 8
_LUMA_GRID = 12
_HUE_BINS = 12
_HUE_MARGIN = 8

FloatArray = NDArray[np.float32]
RgbArray = NDArray[np.uint8]


class ReferenceLibraryError(ValueError):
    """Stable input-contract failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class Vote:
    """Outcome of one descriptor's nearest-reference vote."""

    class_index: int | None
    neighbour_count: int
    agreeing_count: int
    best_similarity: float
    # Per-class vote weights; excluded from equality because batching may change last digits.
    class_weights: tuple[float, ...] = field(default=(), compare=False)

    @property
    def unanimous(self) -> bool:
        return (
            self.class_index is not None
            and self.neighbour_count == NEIGHBOUR_COUNT
            and self.agreeing_count == NEIGHBOUR_COUNT
        )


@dataclass(frozen=True, slots=True)
class Proposal:
    """Combined result; ``class_index`` is None when the cell needs manual review."""

    class_index: int | None
    reason: str
    shape_vote: Vote
    combined_vote: Vote


def _require_crop(rgb: RgbArray) -> None:
    if (
        not isinstance(rgb, np.ndarray)
        or rgb.dtype != np.uint8
        or rgb.shape != (CROP_SIZE, CROP_SIZE, 3)
    ):
        raise ReferenceLibraryError(
            "SYMBOL_REFERENCE_CROP_INVALID",
            "A reference descriptor requires one 64 x 64 RGB uint8 crop.",
        )


def normalize_rows(values: FloatArray) -> FloatArray:
    """L2-normalize each row; an all-zero row stays zero."""

    matrix = np.asarray(values, dtype=np.float32)
    if matrix.ndim != 2 or not bool(np.isfinite(matrix).all()):
        raise ReferenceLibraryError(
            "SYMBOL_REFERENCE_DESCRIPTOR_INVALID",
            "Descriptors must form a finite two-dimensional matrix.",
        )
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return cast(FloatArray, (matrix / np.maximum(norms, 1e-9)).astype(np.float32))


def gray_world(rgb: RgbArray) -> RgbArray:
    """Equalize channel means so a colour cast does not dominate learned features."""

    _require_crop(rgb)
    pixels = rgb.astype(np.float32)
    channel_means = pixels.reshape(-1, 3).mean(axis=0)
    target = float(channel_means.mean())
    gains = target / np.maximum(channel_means, 1.0)
    return cast(RgbArray, np.clip(pixels * gains, 0.0, 255.0).astype(np.uint8))


def shape_descriptor(rgb: RgbArray) -> FloatArray:
    """Colour-free descriptor: edge-orientation histograms plus standardized luma."""

    _require_crop(rgb)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    gradient_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0)
    gradient_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1)
    magnitude = np.hypot(gradient_x, gradient_y)
    orientation = (np.arctan2(gradient_y, gradient_x) % np.pi) / np.pi * _HOG_BINS
    bins = np.clip(orientation.astype(np.int64), 0, _HOG_BINS - 1)
    block = CROP_SIZE // _HOG_GRID
    histograms: list[FloatArray] = []
    for row in range(_HOG_GRID):
        for column in range(_HOG_GRID):
            window = (
                slice(row * block, (row + 1) * block),
                slice(column * block, (column + 1) * block),
            )
            counts = np.bincount(
                bins[window].ravel(),
                weights=magnitude[window].ravel(),
                minlength=_HOG_BINS,
            )
            histograms.append(np.asarray(counts, dtype=np.float32))
    edges = np.concatenate(histograms).astype(np.float32)
    edges /= float(np.linalg.norm(edges)) + 1e-6
    luma = cv2.resize(gray, (_LUMA_GRID, _LUMA_GRID), interpolation=cv2.INTER_AREA)
    luma = (luma - float(luma.mean())) / (float(luma.std()) + 1e-6)
    luma = luma.ravel() / float(_LUMA_GRID)
    luma /= float(np.linalg.norm(luma)) + 1e-6
    return cast(FloatArray, np.concatenate([edges, luma]).astype(np.float32))


def hue_descriptor(rgb: RgbArray) -> FloatArray:
    """Saturation- and value-weighted hue histogram of the crop centre."""

    _require_crop(rgb)
    centre = np.ascontiguousarray(rgb[_HUE_MARGIN:-_HUE_MARGIN, _HUE_MARGIN:-_HUE_MARGIN])
    hsv = cv2.cvtColor(centre, cv2.COLOR_RGB2HSV)
    hue = np.clip(hsv[..., 0].astype(np.int64) // 15, 0, _HUE_BINS - 1)
    weights = hsv[..., 1].astype(np.float32) * hsv[..., 2].astype(np.float32) / 255.0
    counts = np.bincount(hue.ravel(), weights=weights.ravel(), minlength=_HUE_BINS)
    histogram = np.asarray(counts, dtype=np.float32)
    return cast(FloatArray, histogram / (float(histogram.sum()) + 1e-6))


def combined_descriptor(
    shape: FloatArray,
    feature_map: FloatArray,
    hue: FloatArray,
    *,
    hue_weight: float = 0.7,
) -> FloatArray:
    """Concatenate row-normalized parts into the second, colour-aware descriptor."""

    parts = (normalize_rows(feature_map), normalize_rows(shape), normalize_rows(hue))
    if len({part.shape[0] for part in parts}) != 1:
        raise ReferenceLibraryError(
            "SYMBOL_REFERENCE_DESCRIPTOR_INVALID",
            "Descriptor parts must describe the same cells.",
        )
    return cast(
        FloatArray,
        np.hstack([parts[0], parts[1], hue_weight * parts[2]]).astype(np.float32),
    )


def vote(
    query: FloatArray,
    references: FloatArray,
    labels: NDArray[np.int64],
    *,
    class_count: int,
    excluded: NDArray[np.bool_] | None = None,
) -> Vote:
    """Vote among the nearest references by cosine similarity.

    ``query`` and ``references`` must already be row-normalized. ``excluded``
    removes references that must not inform this query, for example the
    query's own import during evaluation.
    """

    if (
        query.ndim != 1
        or references.ndim != 2
        or references.shape[1] != query.shape[0]
        or labels.shape != (references.shape[0],)
        or class_count < 2
        or (labels.size and (int(labels.min()) < 0 or int(labels.max()) >= class_count))
        or (excluded is not None and excluded.shape != labels.shape)
    ):
        raise ReferenceLibraryError(
            "SYMBOL_REFERENCE_VOTE_INPUT_INVALID",
            "Vote inputs have inconsistent shapes or labels.",
        )
    allowed = np.arange(labels.shape[0]) if excluded is None else np.flatnonzero(~excluded)
    if allowed.size < NEIGHBOUR_COUNT:
        return Vote(None, int(allowed.size), 0, 0.0)
    similarity = references[allowed] @ query
    # Stable order makes ties deterministic: higher similarity, then lower row.
    order = np.lexsort((allowed, -similarity))[:NEIGHBOUR_COUNT]
    return _vote_from_neighbours(similarity[order], labels[allowed[order]], class_count)


def vote_batch(
    queries: FloatArray,
    references: FloatArray,
    labels: NDArray[np.int64],
    *,
    class_count: int,
) -> list[Vote]:
    """Vote for every query row in one matrix product, without exclusions.

    Neighbour choice and tie order follow ``vote``; similarities may differ from
    it in the last float32 digit because the product is computed in a batch.
    """

    if (
        queries.ndim != 2
        or references.ndim != 2
        or queries.shape[1] != references.shape[1]
        or labels.shape != (references.shape[0],)
        or class_count < 2
        or (labels.size and (int(labels.min()) < 0 or int(labels.max()) >= class_count))
    ):
        raise ReferenceLibraryError(
            "SYMBOL_REFERENCE_VOTE_INPUT_INVALID",
            "Vote inputs have inconsistent shapes or labels.",
        )
    if references.shape[0] < NEIGHBOUR_COUNT:
        return [vote(query, references, labels, class_count=class_count) for query in queries]
    similarity = queries @ references.T
    kth = np.partition(-similarity, NEIGHBOUR_COUNT - 1, axis=1)[:, NEIGHBOUR_COUNT - 1]
    results: list[Vote] = []
    for row, threshold in zip(similarity, kth, strict=True):
        # Keep every tie at the boundary so the stable order matches ``vote`` exactly.
        candidates = np.flatnonzero(-row <= threshold)
        order = candidates[np.lexsort((candidates, -row[candidates]))][:NEIGHBOUR_COUNT]
        results.append(_vote_from_neighbours(row[order], labels[order], class_count))
    return results


def _vote_from_neighbours(
    similarity: NDArray[np.float32], neighbour_labels: NDArray[np.int64], class_count: int
) -> Vote:
    weights = np.bincount(
        neighbour_labels,
        weights=np.maximum(similarity, 0.0) + 1e-6,
        minlength=class_count,
    )
    winner = int(np.argmax(weights))
    return Vote(
        class_index=winner,
        neighbour_count=NEIGHBOUR_COUNT,
        agreeing_count=int(np.count_nonzero(neighbour_labels == winner)),
        best_similarity=float(similarity[0]),
        class_weights=tuple(float(value) for value in weights),
    )


def hint_candidates(proposal: Proposal, count: int = 2) -> tuple[int, ...]:
    """Classes with the largest summed weight of both descriptors' votes.

    A hint for manual review only; it never replaces the unanimous-proposal rule.
    """

    shape, combined = proposal.shape_vote.class_weights, proposal.combined_vote.class_weights
    if not shape or not combined or len(shape) != len(combined) or count < 1:
        return ()
    fused = np.asarray(shape, dtype=np.float64) + np.asarray(combined, dtype=np.float64)
    # Stable order: larger weight first, then the lower class index.
    order = np.lexsort((np.arange(fused.size), -fused))
    return tuple(int(index) for index in order[:count] if fused[index] > 0)


def decide(shape_vote: Vote, combined_vote: Vote) -> Proposal:
    """Propose a symbol only when both descriptors agree unanimously."""

    if shape_vote.class_index is None or combined_vote.class_index is None:
        reason = "insufficient_references"
    elif shape_vote.class_index != combined_vote.class_index:
        reason = "descriptors_disagree"
    elif not (shape_vote.unanimous and combined_vote.unanimous):
        reason = "not_unanimous"
    else:
        return Proposal(shape_vote.class_index, "unanimous", shape_vote, combined_vote)
    return Proposal(None, reason, shape_vote, combined_vote)


def descriptor_matrix(crops: Sequence[RgbArray]) -> tuple[FloatArray, FloatArray]:
    """Return row-normalized shape descriptors and raw hue descriptors."""

    if not crops:
        raise ReferenceLibraryError(
            "SYMBOL_REFERENCE_CROP_INVALID",
            "At least one crop is required.",
        )
    shape = np.stack([shape_descriptor(crop) for crop in crops])
    hue = np.stack([hue_descriptor(crop) for crop in crops])
    return normalize_rows(shape), cast(FloatArray, hue.astype(np.float32))
