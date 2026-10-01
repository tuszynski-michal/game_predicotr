"""D-484 geometry completeness of one source image (pure classification).

The unit of geometry is the source image. The expected boards of an image are
the ``active_board_slots`` of its current source geometry revision; each
expected position is classified from a handful of plain facts, and the image
is classified from its positions. No SQLAlchemy, no I/O.

The SQL in ``storage.image_geometry_completeness_repository`` counts the same
states in aggregate; the PostgreSQL tests of that module assert that both
agree on every state, so changing a rule here means changing it there too.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final
from uuid import UUID

from game_predictor_api.domain.image_reviews import ImageReviewError

MAX_GEOMETRY_COMPLETENESS_PAGE_SIZE: Final = 100
DEFAULT_LOW_QUALITY_MAX_CONFIDENCE: Final = 0.80
DEFAULT_LOW_QUALITY_MIN_CELLS: Final = 5
MAX_LOW_QUALITY_MIN_CELLS: Final = 15
MAX_LOW_QUALITY_BOARDS: Final = 100

_COMPLETE_STATUS: Final = "complete"
_PARTIAL_STATUS: Final = "pending_partial"


class GeometryPositionState(StrEnum):
    """State of one expected board position of a source image."""

    OK = "ok"
    UNCERTAIN = "uncertain"
    PARTIAL = "partial"
    MISSING = "missing"
    DEFERRED = "deferred"


class GeometryImageState(StrEnum):
    """State of a source image as a whole."""

    COMPLETE = "complete"
    INCOMPLETE_MISSING = "incomplete_missing"
    INCOMPLETE_PARTIAL = "incomplete_partial"
    INCOMPLETE_UNCERTAIN = "incomplete_uncertain"
    NO_SOURCE_GEOMETRY = "no_source_geometry"


@dataclass(frozen=True, slots=True)
class GeometryPositionFacts:
    """Facts about one expected position, read from the current storage.

    ``geometry_approved`` is ``approved_geometry_revision == geometry_revision``
    of the recognized board (a human approved the board's current geometry).
    ``source_revision_accepted`` is ``status == 'accepted'`` of the source
    geometry revision the board points to (not of the image's newest one).
    ``deferred_reason_code`` is the reason of an open
    ``image_board_geometry_pending`` row for the position, if any.
    """

    position_index: int
    board_exists: bool
    completeness_status: str | None = None
    geometry_approved: bool = False
    source_revision_accepted: bool = False
    deferred_reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class GeometryPositionClassification:
    state: GeometryPositionState
    reason_code: str | None = None


def classify_position(facts: GeometryPositionFacts) -> GeometryPositionClassification:
    """Classify one expected position; the first matching rule wins (D-484)."""

    if not facts.board_exists:
        if facts.deferred_reason_code is not None:
            return GeometryPositionClassification(
                GeometryPositionState.DEFERRED, facts.deferred_reason_code
            )
        return GeometryPositionClassification(GeometryPositionState.MISSING)
    if facts.completeness_status == _PARTIAL_STATUS:
        return GeometryPositionClassification(GeometryPositionState.PARTIAL)
    if facts.completeness_status == _COMPLETE_STATUS and (
        facts.geometry_approved or facts.source_revision_accepted
    ):
        return GeometryPositionClassification(GeometryPositionState.OK)
    # A complete board whose geometry is neither human-approved nor accepted
    # without reservations by the engine; an unknown completeness value is not
    # evidence of a correct grid either.
    return GeometryPositionClassification(GeometryPositionState.UNCERTAIN)


def classify_image(
    position_states: Iterable[GeometryPositionState],
    *,
    has_source_geometry: bool,
) -> GeometryImageState:
    """Classify an image from the states of all its expected positions."""

    if not has_source_geometry:
        return GeometryImageState.NO_SOURCE_GEOMETRY
    states = set(position_states)
    if GeometryPositionState.MISSING in states or GeometryPositionState.DEFERRED in states:
        return GeometryImageState.INCOMPLETE_MISSING
    if GeometryPositionState.PARTIAL in states:
        return GeometryImageState.INCOMPLETE_PARTIAL
    if GeometryPositionState.UNCERTAIN in states:
        return GeometryImageState.INCOMPLETE_UNCERTAIN
    return GeometryImageState.COMPLETE


def expected_sequence_number(sequence_range_start: int, position_index: int) -> int:
    """Sequence number of position ``p`` in a source revision (D-484)."""

    return sequence_range_start + position_index


Point = tuple[float, float]
Quad = tuple[Point, Point, Point, Point]


def extract_position_quad(entry: Mapping[str, object] | None) -> Quad | None:
    """Quad of one ``board_geometries`` entry in source pixels, if it has one.

    Reads ``symbolGridQuad`` (the symbol lattice the cells are cut from) and
    falls back to ``finalQuad``; returns ``None`` instead of inventing a grid.
    """

    if entry is None:
        return None
    for key in ("symbolGridQuad", "finalQuad"):
        value = entry.get(key)
        if not isinstance(value, Sequence) or isinstance(value, str | bytes) or len(value) != 4:
            continue
        points: list[Point] = []
        for point in value:
            if not isinstance(point, Mapping):
                break
            x = point.get("x")
            y = point.get("y")
            if (
                isinstance(x, bool)
                or isinstance(y, bool)
                or not isinstance(x, int | float)
                or not isinstance(y, int | float)
                or not math.isfinite(x)
                or not math.isfinite(y)
            ):
                break
            points.append((float(x), float(y)))
        else:
            return (points[0], points[1], points[2], points[3])
    return None


@dataclass(frozen=True, slots=True)
class GeometryImageCursor:
    relative_path: str
    source_image_id: UUID


def encode_geometry_image_cursor(cursor: GeometryImageCursor) -> str:
    payload = json.dumps(
        {"p": cursor.relative_path, "i": str(cursor.source_image_id)},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def decode_geometry_image_cursor(value: str) -> GeometryImageCursor:
    try:
        payload = json.loads(base64.urlsafe_b64decode(value.encode("ascii")))
        relative_path = payload["p"]
        source_image_id = UUID(payload["i"])
        if not isinstance(relative_path, str):
            raise TypeError("relative path must be a string")
    except (
        binascii.Error,
        KeyError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as error:
        raise ImageReviewError(
            "IMAGE_GEOMETRY_COMPLETENESS_CURSOR_INVALID",
            "The geometry completeness cursor is invalid.",
        ) from error
    return GeometryImageCursor(relative_path=relative_path, source_image_id=source_image_id)


@dataclass(frozen=True, slots=True)
class LowQualityThresholds:
    """Explicit thresholds of the low-quality symbol signal (TASK-0806)."""

    max_confidence: float = DEFAULT_LOW_QUALITY_MAX_CONFIDENCE
    min_cells: int = DEFAULT_LOW_QUALITY_MIN_CELLS

    def __post_init__(self) -> None:
        if not math.isfinite(self.max_confidence) or not 0 <= self.max_confidence <= 1:
            raise ImageReviewError(
                "IMAGE_GEOMETRY_LOW_QUALITY_THRESHOLD_INVALID",
                "maxConfidence must be between 0 and 1.",
            )
        if isinstance(self.min_cells, bool) or not 1 <= self.min_cells <= MAX_LOW_QUALITY_MIN_CELLS:
            raise ImageReviewError(
                "IMAGE_GEOMETRY_LOW_QUALITY_THRESHOLD_INVALID",
                f"minCells must be between 1 and {MAX_LOW_QUALITY_MIN_CELLS}.",
            )


__all__ = [
    "DEFAULT_LOW_QUALITY_MAX_CONFIDENCE",
    "DEFAULT_LOW_QUALITY_MIN_CELLS",
    "MAX_GEOMETRY_COMPLETENESS_PAGE_SIZE",
    "MAX_LOW_QUALITY_BOARDS",
    "MAX_LOW_QUALITY_MIN_CELLS",
    "GeometryImageCursor",
    "GeometryImageState",
    "GeometryPositionClassification",
    "GeometryPositionFacts",
    "GeometryPositionState",
    "LowQualityThresholds",
    "Point",
    "Quad",
    "classify_image",
    "classify_position",
    "decode_geometry_image_cursor",
    "encode_geometry_image_cursor",
    "expected_sequence_number",
    "extract_position_quad",
]
