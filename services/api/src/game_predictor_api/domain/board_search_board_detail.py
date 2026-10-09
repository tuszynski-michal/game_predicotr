"""Pure domain logic for one board's payline detail and cropped view (D-470).

The admin "Przybliżona wygrana" table lists winning spins; this module turns
one of those boards into the evidence a modal needs to draw the winning
paylines: which lines paid, over which cells, and where those cells sit on a
cropped view of the source photo. Payouts come from the same evaluator as
the range calculator, so a line counts only from the left edge and stops at
the first unknown cell (`payout-v3-unknown-prefix-stop`); a game with a super
game trigger symbol (`payout-v4-wild-count`, D-535) additionally pays that
symbol per count of its known cells on the whole board.

No I/O here: geometry arrives as the board's stored JSON and images are
rendered by the application layer.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from game_predictor_api.domain.board_search import BoardSearchAssetMode

BOARD_ROWS = 3
BOARD_COLUMNS = 5
BOARD_CELL_COUNT = BOARD_ROWS * BOARD_COLUMNS
BOARD_VIEW_PADDING_FACTOR = 0.2
BOARD_VIEW_MAX_SIDE = 1280
BOARD_VIEW_RENDERER_VERSION = "board-search-view-v1"
BOARD_VIEW_MAX_CROP_PIXELS = 60_000_000

BoardPayoutKind = Literal["exact", "confirmed_minimum", "provisional", "none"]

Point = tuple[float, float]
Quad = tuple[Point, Point, Point, Point]


@dataclass(frozen=True, slots=True)
class BoardSearchBoardDocument:
    """One logical board as read by board search, with its internal source
    identity. The identity never leaves the application layer."""

    sequence_number: int
    status: str
    board_checksum_sha256: str
    mobile_codes: tuple[int | None, ...]
    asset_mode: BoardSearchAssetMode
    review_item_id: UUID | None


@dataclass(frozen=True, slots=True)
class BoardSearchBoardViewSource:
    """Where the pixels of one board come from, checked against the search
    document before any view is derived from it."""

    image_relative_path: str
    image_checksum_sha256: str
    geometry: Mapping[str, object] | None
    current_board_checksum_sha256: str


@dataclass(frozen=True, slots=True)
class BoardSearchBoardCell:
    """Current human-review record of one cell, with exactly what the
    existing checksum-bound cell decision needs (D-473)."""

    cell_index: int
    cell_review_id: UUID
    revision: int
    geometry_revision: int
    crop_sample_id: str | None
    crop_checksum_sha256: str | None
    review_state: str
    quality_issue: str | None
    assigned_symbol_code: str | None


@dataclass(frozen=True, slots=True)
class PaylineLabel:
    payline_id: str
    code: str
    name: str
    display_order: int
    row_path: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class BoardSearchLineMatch:
    payline_id: str
    payline_code: str
    payline_name: str
    payline_display_order: int
    row_path: tuple[int, ...]
    symbol_code: str
    matched_length: int
    matched_cells: tuple[int, ...]
    joker_cells: tuple[int, ...]
    payout_credits: int


@dataclass(frozen=True, slots=True)
class BoardCountMatch:
    """A super game trigger symbol paid per count of its cells on the board
    (`payout-v4-wild-count`); unknown cells are never counted."""

    symbol_code: str
    count: int
    cells: tuple[int, ...]
    payout_credits: int


@dataclass(frozen=True, slots=True)
class BoardExpansion:
    """The super symbol expanded over whole columns of a series board
    (`wild_super_spins`, D-537): `payout_credits = line_payout_credits ×
    payline_count`, replacing the super symbol's own line wins."""

    symbol_code: str
    columns: tuple[int, ...]
    column_count: int
    line_payout_credits: int
    payline_count: int
    payout_credits: int


@dataclass(frozen=True, slots=True)
class BoardViewCrop:
    """Integer crop box in source pixels and the rendered output size."""

    left: int
    top: int
    right: int
    bottom: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class BoardSearchBoardView:
    """Rendered view size, its cache revision and, when the board has a
    saved grid, cell polygons in 0–1 view coordinates."""

    width: int
    height: int
    revision: str
    cell_polygons: tuple[tuple[Point, ...], ...] | None


def board_payout_kind(payout_credits: int, mobile_codes: Sequence[int | None]) -> BoardPayoutKind:
    """`none` without payout; `exact` for a complete board; otherwise the
    visible left prefix guarantees a `confirmed_minimum`.

    `payout_credits` includes count matches: an unknown cell is never counted
    as a trigger symbol, so on a partial board the count, like every line
    prefix, is a lower bound and the board stays `confirmed_minimum`.
    """

    if payout_credits <= 0:
        return "none"
    return "exact" if all(code is not None for code in mobile_codes) else "confirmed_minimum"


def _point(raw: object) -> Point | None:
    if isinstance(raw, Mapping):
        x, y = raw.get("x"), raw.get("y")
    elif isinstance(raw, Sequence) and not isinstance(raw, str | bytes) and len(raw) == 2:
        x, y = raw[0], raw[1]
    else:
        return None
    if (
        isinstance(x, bool)
        or isinstance(y, bool)
        or not isinstance(x, int | float)
        or not isinstance(y, int | float)
        or not math.isfinite(x)
        or not math.isfinite(y)
    ):
        return None
    return (float(x), float(y))


def _quad(raw: object) -> Quad | None:
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes) or len(raw) != 4:
        return None
    points = [_point(value) for value in raw]
    if any(point is None for point in points):
        return None
    a, b, c, d = (point for point in points if point is not None)
    return (a, b, c, d)


def derive_grid_cell_quads(quad: Quad) -> tuple[Quad, ...] | None:
    """Split a TL, TR, BR, BL board quad into 15 row-major cells through the
    projective map of the unit square (same construction as the shared TS
    `manualGridCellPolygons`)."""

    (ax, ay), (bx, by), (cx, cy), (dx, dy) = quad
    dx1, dx2 = bx - cx, dx - cx
    dy1, dy2 = by - cy, dy - cy
    dx3, dy3 = ax - bx + cx - dx, ay - by + cy - dy
    determinant = dx1 * dy2 - dx2 * dy1
    if abs(determinant) < 1e-12:
        return None
    g = (dx3 * dy2 - dx2 * dy3) / determinant
    h = (dx1 * dy3 - dx3 * dy1) / determinant

    def at(u: float, v: float) -> Point:
        scale = g * u + h * v + 1
        return (
            ((bx - ax + g * bx) * u + (dx - ax + h * dx) * v + ax) / scale,
            ((by - ay + g * by) * u + (dy - ay + h * dy) * v + ay) / scale,
        )

    cells: list[Quad] = []
    for index in range(BOARD_CELL_COUNT):
        u = (index % BOARD_COLUMNS) / BOARD_COLUMNS
        v = (index // BOARD_COLUMNS) / BOARD_ROWS
        cells.append(
            (
                at(u, v),
                at(u + 1 / BOARD_COLUMNS, v),
                at(u + 1 / BOARD_COLUMNS, v + 1 / BOARD_ROWS),
                at(u, v + 1 / BOARD_ROWS),
            )
        )
    return tuple(cells)


def board_cell_quads(geometry: Mapping[str, object]) -> tuple[Quad, ...] | None:
    """The 15 saved cell footprints in source pixels, or `None`.

    Explicit `cells[].sourceQuad` wins per cell; missing cells are derived
    from the saved lattice quad. Never invents a grid: any malformed or
    incomplete geometry returns `None`.
    """

    footprints: dict[int, Quad] = {}
    raw_cells = geometry.get("cells")
    if isinstance(raw_cells, Sequence) and not isinstance(raw_cells, str | bytes):
        for cell in raw_cells:
            if not isinstance(cell, Mapping):
                return None
            row, column = cell.get("rowIndex"), cell.get("columnIndex")
            if (
                type(row) is not int
                or type(column) is not int
                or not 0 <= row < BOARD_ROWS
                or not 0 <= column < BOARD_COLUMNS
            ):
                return None
            index = row * BOARD_COLUMNS + column
            quad = _quad(cell.get("sourceQuad"))
            if quad is None or index in footprints:
                return None
            footprints[index] = quad
    derived: tuple[Quad, ...] | None = None
    if len(footprints) < BOARD_CELL_COUNT:
        # Like the TS `a ?? b ?? …`: the first key present decides, even when
        # its value is malformed (then no grid is derived at all).
        present = next(
            (
                geometry.get(key)
                for key in ("latticeBoundsQuad", "symbolGridQuad", "sourceQuad", "quad", "corners")
                if geometry.get(key) is not None
            ),
            None,
        )
        lattice = _quad(present)
        if lattice is not None:
            derived = derive_grid_cell_quads(lattice)
        if derived is None:
            return None
    cells: list[Quad] = []
    for index in range(BOARD_CELL_COUNT):
        if index in footprints:
            cells.append(footprints[index])
        elif derived is not None:
            cells.append(derived[index])
        else:
            return None
    return tuple(cells)


def board_view_crop(
    cell_quads: Sequence[Quad],
    *,
    padding_factor: float = BOARD_VIEW_PADDING_FACTOR,
    max_side: int = BOARD_VIEW_MAX_SIDE,
) -> BoardViewCrop | None:
    """Board bounding box plus padding, independent of the image size.

    The renderer fills pixels outside the photo, so the box (and therefore
    the normalized polygons) never depends on image dimensions.
    """

    xs = [point[0] for quad in cell_quads for point in quad]
    ys = [point[1] for quad in cell_quads for point in quad]
    if not xs or not all(math.isfinite(value) for value in (*xs, *ys)):
        return None
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    width, height = max_x - min_x, max_y - min_y
    if not math.isfinite(width) or not math.isfinite(height) or width <= 0 or height <= 0:
        return None
    try:
        left = math.floor(min_x - width * padding_factor)
        top = math.floor(min_y - height * padding_factor)
        right = math.ceil(max_x + width * padding_factor)
        bottom = math.ceil(max_y + height * padding_factor)
    except (OverflowError, ValueError):
        return None
    box_width, box_height = right - left, bottom - top
    if box_width * box_height > BOARD_VIEW_MAX_CROP_PIXELS:
        # Absurd geometry: refuse the view instead of rendering a huge canvas.
        return None
    scale = min(1.0, max_side / max(box_width, box_height))
    return BoardViewCrop(
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        width=max(1, round(box_width * scale)),
        height=max(1, round(box_height * scale)),
    )


def board_view_revision(image_checksum_sha256: str, crop: BoardViewCrop | None) -> str:
    """Identity of one rendered view: renderer, source pixels and crop.

    It is both the server cache key and the `viewRevision` the client puts
    in the image URL, so a changed grid always yields a new URL.
    """

    payload = {
        "crop": None
        if crop is None
        else [crop.left, crop.top, crop.right, crop.bottom, crop.width, crop.height],
        "imageChecksumSha256": image_checksum_sha256,
        "maxSide": BOARD_VIEW_MAX_SIDE,
        "renderer": BOARD_VIEW_RENDERER_VERSION,
    }
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def resized_view_size(
    width: int, height: int, max_side: int = BOARD_VIEW_MAX_SIDE
) -> tuple[int, int]:
    scale = min(1.0, max_side / max(width, height))
    return max(1, round(width * scale)), max(1, round(height * scale))


def board_view(
    cell_quads: Sequence[Quad], crop: BoardViewCrop, *, revision: str
) -> BoardSearchBoardView:
    """Cell polygons in 0–1 coordinates of the cropped view (points of a
    board cut off by the photo edge may fall outside 0–1)."""

    box_width = crop.right - crop.left
    box_height = crop.bottom - crop.top
    return BoardSearchBoardView(
        width=crop.width,
        height=crop.height,
        revision=revision,
        cell_polygons=tuple(
            tuple(
                (
                    round((x - crop.left) / box_width, 6),
                    round((y - crop.top) / box_height, 6),
                )
                for x, y in quad
            )
            for quad in cell_quads
        ),
    )


__all__ = [
    "BOARD_VIEW_MAX_CROP_PIXELS",
    "BOARD_VIEW_MAX_SIDE",
    "BOARD_VIEW_PADDING_FACTOR",
    "BOARD_VIEW_RENDERER_VERSION",
    "BoardCountMatch",
    "BoardExpansion",
    "BoardPayoutKind",
    "BoardSearchBoardCell",
    "BoardSearchBoardDocument",
    "BoardSearchBoardView",
    "BoardSearchBoardViewSource",
    "BoardSearchLineMatch",
    "BoardViewCrop",
    "PaylineLabel",
    "board_cell_quads",
    "board_payout_kind",
    "board_view",
    "board_view_crop",
    "board_view_revision",
    "resized_view_size",
    "derive_grid_cell_quads",
]
