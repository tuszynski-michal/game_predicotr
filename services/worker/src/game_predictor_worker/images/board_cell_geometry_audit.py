"""Deterministic, read-only audit of v19 geometry on registered real pages."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageOps, UnidentifiedImageError

from .board_cell_geometry_contract import canonical_json_bytes
from .board_cell_geometry_estimator import (
    ESTIMATOR_VERSION,
    BoardCellGeometryEstimate,
    estimate_board_cell_geometry,
    estimator_thresholds,
)
from .geometry import Point, Quad

AUDIT_VERSION = "board-cell-geometry-v19-real-page-audit-v1"
AUDIT_SCHEMA_VERSION = 1
SAMPLE_POLICY_VERSION = "sha256-ranked-registered-pages-v1"
DEFAULT_SAMPLE_SEED = "task-0249-v19-pre-editor-audit-v1"
EXPECTED_PAGE_GEOMETRY_VERSIONS = frozenset(
    {"page-geometry-preflight-v1", "page-geometry-preflight-v2-auto-anchor"}
)
_SHA256 = frozenset("0123456789abcdef")
_SEQUENCE_NAME = re.compile(
    r"^seq_(?P<start>[1-9][0-9]*)-(?P<end>[1-9][0-9]*)\.(?:jpg|jpeg)$", re.I
)


class BoardCellGeometryAuditError(RuntimeError):
    """Stable audit failure safe to expose from a local operator script."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class RegisteredPage:
    source_checksum_sha256: str
    source_relative_path: str
    sequence_start: int
    sequence_end: int
    quads: tuple[Quad, ...]


@dataclass(frozen=True, slots=True)
class BoardCellGeometryAudit:
    """Canonical audit document plus source images used only for rendering."""

    document: dict[str, object]
    source_images: tuple[NDArray[np.uint8], ...]

    @property
    def checksum_sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.document)).hexdigest()


Estimator = Callable[[NDArray[np.uint8], Quad], BoardCellGeometryEstimate]


def load_page_geometry_manifest(path: Path) -> tuple[bytes, Mapping[str, object]]:
    """Load a pinned page manifest without accepting a non-object document."""

    try:
        content = path.read_bytes()
        payload: Any = json.loads(content)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _error(
            "BOARD_CELL_GEOMETRY_AUDIT_MANIFEST_UNREADABLE", "Manifest is unreadable."
        ) from error
    if not isinstance(payload, Mapping):
        raise _error("BOARD_CELL_GEOMETRY_AUDIT_MANIFEST_INVALID", "Manifest must be an object.")
    return content, cast(Mapping[str, object], payload)


def registered_pages(payload: Mapping[str, object]) -> tuple[RegisteredPage, ...]:
    """Validate and normalize registered 3 x 3 page geometry entries."""

    if payload.get("version") not in EXPECTED_PAGE_GEOMETRY_VERSIONS:
        raise _error(
            "BOARD_CELL_GEOMETRY_AUDIT_MANIFEST_INVALID", "Unexpected page manifest version."
        )
    entries = payload.get("entries")
    if not isinstance(entries, Mapping):
        raise _error(
            "BOARD_CELL_GEOMETRY_AUDIT_MANIFEST_INVALID", "Manifest entries must be an object."
        )
    pages: list[RegisteredPage] = []
    for raw_checksum, raw_entry in entries.items():
        checksum = _checksum(raw_checksum, "entry checksum")
        if not isinstance(raw_entry, Mapping) or raw_entry.get("status") != "registered":
            continue
        relative_path = _safe_relative_path(raw_entry.get("sourceRelativePath"))
        name_match = _SEQUENCE_NAME.fullmatch(PurePosixPath(relative_path).name)
        if name_match is None:
            raise _error(
                "BOARD_CELL_GEOMETRY_AUDIT_SEQUENCE_NAME_INVALID",
                f"Registered source {relative_path} has no attested seq_* name.",
            )
        sequence_start = int(name_match.group("start"))
        sequence_end = int(name_match.group("end"))
        if sequence_end - sequence_start != 8:
            raise _error(
                "BOARD_CELL_GEOMETRY_AUDIT_SEQUENCE_RANGE_INVALID",
                f"Registered source {relative_path} does not attest exactly nine boards.",
            )
        raw_quads = raw_entry.get("quads")
        if not isinstance(raw_quads, Sequence) or isinstance(raw_quads, str | bytes):
            raise _error(
                "BOARD_CELL_GEOMETRY_AUDIT_MANIFEST_INVALID", "Registered quads must be an array."
            )
        if len(raw_quads) != 9:
            raise _error(
                "BOARD_CELL_GEOMETRY_AUDIT_PAGE_INCOMPLETE",
                f"Registered source {relative_path} must contain nine board quads.",
            )
        pages.append(
            RegisteredPage(
                source_checksum_sha256=checksum,
                source_relative_path=relative_path,
                sequence_start=sequence_start,
                sequence_end=sequence_end,
                quads=tuple(_quad(value, relative_path) for value in raw_quads),
            )
        )
    if not pages:
        raise _error(
            "BOARD_CELL_GEOMETRY_AUDIT_NO_REGISTERED_PAGES", "Manifest has no registered pages."
        )
    return tuple(sorted(pages, key=lambda page: (page.sequence_start, page.source_checksum_sha256)))


def select_audit_pages(
    pages: Sequence[RegisteredPage],
    *,
    sample_size: int,
    sample_seed: str = DEFAULT_SAMPLE_SEED,
) -> tuple[RegisteredPage, ...]:
    """Choose a reproducible sample independent of manifest object order."""

    if sample_size < 1 or sample_size > len(pages):
        raise _error(
            "BOARD_CELL_GEOMETRY_AUDIT_SAMPLE_INVALID",
            "Sample size must be positive and cannot exceed registered pages.",
        )
    if not sample_seed:
        raise _error("BOARD_CELL_GEOMETRY_AUDIT_SAMPLE_INVALID", "Sample seed cannot be empty.")
    unique = {page.source_checksum_sha256 for page in pages}
    if len(unique) != len(pages):
        raise _error("BOARD_CELL_GEOMETRY_AUDIT_MANIFEST_INVALID", "Registered checksums repeat.")
    ranked = sorted(
        pages,
        key=lambda page: (
            hashlib.sha256(f"{sample_seed}:{page.source_checksum_sha256}".encode()).hexdigest(),
            page.source_checksum_sha256,
        ),
    )
    return tuple(ranked[:sample_size])


def run_board_cell_geometry_audit(
    *,
    page_geometry_manifest_path: Path,
    source_root: Path,
    sample_size: int = 100,
    sample_seed: str = DEFAULT_SAMPLE_SEED,
    estimator: Estimator = estimate_board_cell_geometry,
) -> BoardCellGeometryAudit:
    """Audit all nine boards on each sampled page without mutating the pipeline."""

    manifest_content, manifest = load_page_geometry_manifest(page_geometry_manifest_path)
    selected = select_audit_pages(
        registered_pages(manifest), sample_size=sample_size, sample_seed=sample_seed
    )
    root = source_root.resolve(strict=True)
    page_results: list[dict[str, object]] = []
    images: list[NDArray[np.uint8]] = []
    status_counts: Counter[str] = Counter()
    fallback_counts: Counter[str] = Counter()
    for sample_index, page in enumerate(selected):
        image = _load_verified_rgb(root, page)
        images.append(image)
        boards: list[dict[str, object]] = []
        page_estimated_count = 0
        page_needs_review_count = 0
        for position_index, quad in enumerate(page.quads):
            estimate = estimator(image, quad)
            status_counts[estimate.status] += 1
            if estimate.status == "estimated":
                page_estimated_count += 1
            else:
                page_needs_review_count += 1
            if estimate.fallback_reason is not None:
                fallback_counts[estimate.fallback_reason] += 1
            boards.append(
                {
                    "estimate": estimate.to_dict(),
                    "pageQuad": _quad_payload(quad),
                    "positionIndex": position_index,
                    "sequenceNumber": page.sequence_start + position_index,
                }
            )
        page_results.append(
            {
                "boards": boards,
                "estimatedBoardCount": page_estimated_count,
                "needsReviewBoardCount": page_needs_review_count,
                "sampleIndex": sample_index,
                "sequenceEnd": page.sequence_end,
                "sequenceStart": page.sequence_start,
                "sourceImageChecksumSha256": page.source_checksum_sha256,
                "sourceImageRelativePath": page.source_relative_path,
            }
        )
    document: dict[str, object] = {
        "auditPurpose": "pre-editor-real-page-geometry-checkpoint",
        "estimatorThresholds": estimator_thresholds(),
        "estimatorVersion": ESTIMATOR_VERSION,
        "pageGeometryManifestChecksumSha256": hashlib.sha256(manifest_content).hexdigest(),
        "pages": page_results,
        "samplePolicyVersion": SAMPLE_POLICY_VERSION,
        "sampleSeed": sample_seed,
        "schemaVersion": AUDIT_SCHEMA_VERSION,
        "scope": {
            "boardCount": sample_size * 9,
            "pageCount": sample_size,
            "registeredPageCount": len(registered_pages(manifest)),
        },
        "summary": {
            "estimatedBoardCount": status_counts["estimated"],
            "fallbackReasonCounts": dict(sorted(fallback_counts.items())),
            "needsReviewBoardCount": status_counts["needs_review"],
        },
        "version": AUDIT_VERSION,
    }
    return BoardCellGeometryAudit(document=document, source_images=tuple(images))


def write_content_addressed_audit(audit: BoardCellGeometryAudit, output_root: Path) -> Path:
    """Persist only the canonical report under its SHA-256."""

    content = canonical_json_bytes(audit.document)
    checksum = hashlib.sha256(content).hexdigest()
    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / f"{checksum}.json"
    if destination.exists():
        if destination.read_bytes() != content:
            raise _error(
                "BOARD_CELL_GEOMETRY_AUDIT_ARTIFACT_CONFLICT",
                "Audit checksum path conflicts.",
            )
        return destination
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{checksum}.", suffix=".tmp", dir=output_root
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if destination.read_bytes() != content:
                raise _error(
                    "BOARD_CELL_GEOMETRY_AUDIT_ARTIFACT_CONFLICT",
                    "Audit checksum path conflicts.",
                ) from None
        finally:
            temporary.unlink(missing_ok=True)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise _error(
            "BOARD_CELL_GEOMETRY_AUDIT_ARTIFACT_WRITE_FAILED",
            "Audit could not be written atomically.",
        ) from error
    return destination


def render_audit_overlays(audit: BoardCellGeometryAudit, output_root: Path) -> tuple[Path, ...]:
    """Render source-space quads for the required human checkpoint."""

    raw_pages = audit.document.get("pages")
    if not isinstance(raw_pages, Sequence):
        raise _error("BOARD_CELL_GEOMETRY_AUDIT_REPORT_INVALID", "Audit pages are missing.")
    if len(raw_pages) != len(audit.source_images):
        raise _error("BOARD_CELL_GEOMETRY_AUDIT_REPORT_INVALID", "Audit images do not match pages.")
    output_root.mkdir(parents=True, exist_ok=True)
    rendered: list[Path] = []
    for raw_page, image in zip(raw_pages, audit.source_images, strict=True):
        if not isinstance(raw_page, Mapping):
            raise _error("BOARD_CELL_GEOMETRY_AUDIT_REPORT_INVALID", "Audit page is invalid.")
        canvas = _render_page_overlay(raw_page, image)
        index = int(cast(int, raw_page.get("sampleIndex")))
        start = int(cast(int, raw_page.get("sequenceStart")))
        end = int(cast(int, raw_page.get("sequenceEnd")))
        destination = output_root / f"{index + 1:03d}_seq_{start}-{end}.jpg"
        if not cv2.imwrite(str(destination), canvas, [cv2.IMWRITE_JPEG_QUALITY, 95]):
            raise _error("BOARD_CELL_GEOMETRY_AUDIT_OVERLAY_WRITE_FAILED", "Cannot write overlay.")
        rendered.append(destination)
    return tuple(rendered)


def render_audit_contact_sheets(
    audit: BoardCellGeometryAudit,
    output_root: Path,
    *,
    pages_per_sheet: int = 4,
) -> tuple[Path, ...]:
    """Render cropped 2 x 2 sheets so a human can inspect all 100 pages."""

    if pages_per_sheet != 4:
        raise _error(
            "BOARD_CELL_GEOMETRY_AUDIT_RENDER_INVALID", "v1 contact sheets contain four pages."
        )
    raw_pages = audit.document.get("pages")
    if not isinstance(raw_pages, Sequence) or len(raw_pages) != len(audit.source_images):
        raise _error("BOARD_CELL_GEOMETRY_AUDIT_REPORT_INVALID", "Audit pages do not match images.")
    tiles: list[NDArray[np.uint8]] = []
    for raw_page, image in zip(raw_pages, audit.source_images, strict=True):
        if not isinstance(raw_page, Mapping):
            raise _error("BOARD_CELL_GEOMETRY_AUDIT_REPORT_INVALID", "Audit page is invalid.")
        overlay = _render_page_overlay(raw_page, image)
        tiles.append(_page_audit_tile(raw_page, overlay))
    output_root.mkdir(parents=True, exist_ok=True)
    rendered: list[Path] = []
    for offset in range(0, len(tiles), pages_per_sheet):
        sheet_tiles = tiles[offset : offset + pages_per_sheet]
        sheet = np.zeros((1400, 1800, 3), dtype=np.uint8)
        for tile_index, tile in enumerate(sheet_tiles):
            row, column = divmod(tile_index, 2)
            sheet[row * 700 : (row + 1) * 700, column * 900 : (column + 1) * 900] = tile
        destination = output_root / f"sheet_{offset // pages_per_sheet + 1:03d}.jpg"
        if not cv2.imwrite(str(destination), sheet, [cv2.IMWRITE_JPEG_QUALITY, 95]):
            raise _error("BOARD_CELL_GEOMETRY_AUDIT_OVERLAY_WRITE_FAILED", "Cannot write sheet.")
        rendered.append(destination)
    return tuple(rendered)


def _render_page_overlay(
    raw_page: Mapping[str, object], image: NDArray[np.uint8]
) -> NDArray[np.uint8]:
    canvas = cast(NDArray[np.uint8], cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
    boards = raw_page.get("boards")
    if not isinstance(boards, Sequence):
        raise _error("BOARD_CELL_GEOMETRY_AUDIT_REPORT_INVALID", "Audit boards are invalid.")
    for raw_board in boards:
        if not isinstance(raw_board, Mapping):
            continue
        page_quad = _payload_quad(raw_board.get("pageQuad"))
        estimate = raw_board.get("estimate")
        status = estimate.get("status") if isinstance(estimate, Mapping) else None
        colour = (40, 200, 40) if status == "estimated" else (40, 40, 230)
        _draw_quad(canvas, page_quad, colour, 2)
        if isinstance(estimate, Mapping) and status == "estimated":
            cells = estimate.get("cells")
            if isinstance(cells, Sequence):
                for cell in cells:
                    if isinstance(cell, Mapping):
                        _draw_quad(canvas, _payload_quad(cell.get("quad")), colour, 1)
        sequence = raw_board.get("sequenceNumber")
        origin = tuple(int(round(value)) for value in page_quad[0])
        cv2.putText(
            canvas,
            str(sequence),
            (origin[0], max(18, origin[1] - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            colour,
            1,
            cv2.LINE_AA,
        )
    return canvas


def _page_audit_tile(
    raw_page: Mapping[str, object], overlay: NDArray[np.uint8]
) -> NDArray[np.uint8]:
    boards = raw_page.get("boards")
    if not isinstance(boards, Sequence):
        raise _error("BOARD_CELL_GEOMETRY_AUDIT_REPORT_INVALID", "Audit boards are invalid.")
    coordinates = [
        coordinate
        for raw_board in boards
        if isinstance(raw_board, Mapping)
        for point in _payload_quad(raw_board.get("pageQuad"))
        for coordinate in (point,)
    ]
    if not coordinates:
        raise _error("BOARD_CELL_GEOMETRY_AUDIT_REPORT_INVALID", "Audit page has no quads.")
    height, width = overlay.shape[:2]
    padding_x = max(12, int(width * 0.03))
    padding_y = max(12, int(height * 0.03))
    left = max(0, int(min(point[0] for point in coordinates)) - padding_x)
    right = min(width, int(max(point[0] for point in coordinates)) + padding_x)
    top = max(0, int(min(point[1] for point in coordinates)) - padding_y)
    bottom = min(height, int(max(point[1] for point in coordinates)) + padding_y)
    crop = overlay[top:bottom, left:right]
    if crop.size == 0:
        raise _error("BOARD_CELL_GEOMETRY_AUDIT_REPORT_INVALID", "Audit page crop is empty.")
    scale = min(880 / crop.shape[1], 650 / crop.shape[0])
    resized = cast(
        NDArray[np.uint8],
        cv2.resize(
            crop,
            (max(1, round(crop.shape[1] * scale)), max(1, round(crop.shape[0] * scale))),
            interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR,
        ),
    )
    tile = np.zeros((700, 900, 3), dtype=np.uint8)
    y = 40 + (650 - resized.shape[0]) // 2
    x = 10 + (880 - resized.shape[1]) // 2
    tile[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    title = f"seq_{raw_page.get('sequenceStart')}-{raw_page.get('sequenceEnd')}"
    cv2.putText(tile, title, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    return tile


def _load_verified_rgb(root: Path, page: RegisteredPage) -> NDArray[np.uint8]:
    relative = PurePosixPath(page.source_relative_path)
    path = (root / Path(*relative.parts)).resolve(strict=True)
    if not path.is_relative_to(root):
        raise _error("BOARD_CELL_GEOMETRY_AUDIT_PATH_UNSAFE", "Source path escapes root.")
    try:
        content = path.read_bytes()
        with Image.open(path) as image:
            image.load()
            rgb = np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)
    except (OSError, UnidentifiedImageError) as error:
        raise _error(
            "BOARD_CELL_GEOMETRY_AUDIT_SOURCE_UNREADABLE",
            f"Cannot read {page.source_relative_path}.",
        ) from error
    if hashlib.sha256(content).hexdigest() != page.source_checksum_sha256:
        raise _error(
            "BOARD_CELL_GEOMETRY_AUDIT_SOURCE_DRIFT",
            f"Checksum differs for {page.source_relative_path}.",
        )
    return rgb


def _safe_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise _error("BOARD_CELL_GEOMETRY_AUDIT_MANIFEST_INVALID", "Source path must be text.")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise _error("BOARD_CELL_GEOMETRY_AUDIT_PATH_UNSAFE", "Source path is unsafe.")
    return value


def _checksum(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in _SHA256 for char in value):
        raise _error("BOARD_CELL_GEOMETRY_AUDIT_MANIFEST_INVALID", f"{label} is not SHA-256.")
    return value


def _quad(value: object, label: str) -> Quad:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes) or len(value) != 4:
        raise _error("BOARD_CELL_GEOMETRY_AUDIT_MANIFEST_INVALID", f"Quad is invalid for {label}.")
    points: list[Point] = []
    for raw_point in value:
        if not isinstance(raw_point, Mapping):
            raise _error(
                "BOARD_CELL_GEOMETRY_AUDIT_MANIFEST_INVALID", f"Point is invalid for {label}."
            )
        x = raw_point.get("x")
        y = raw_point.get("y")
        if (
            not isinstance(x, int | float)
            or isinstance(x, bool)
            or not isinstance(y, int | float)
            or isinstance(y, bool)
        ):
            raise _error(
                "BOARD_CELL_GEOMETRY_AUDIT_MANIFEST_INVALID", f"Point is invalid for {label}."
            )
        points.append(Point(int(round(float(x))), int(round(float(y)))))
    return cast(Quad, tuple(points))


def _quad_payload(quad: Quad) -> list[dict[str, float]]:
    return [{"x": round(float(point.x), 4), "y": round(float(point.y), 4)} for point in quad]


def _payload_quad(value: object) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes) or len(value) != 4:
        raise _error("BOARD_CELL_GEOMETRY_AUDIT_REPORT_INVALID", "Overlay quad is invalid.")
    points: list[tuple[float, float]] = []
    for point in value:
        if not isinstance(point, Mapping):
            raise _error("BOARD_CELL_GEOMETRY_AUDIT_REPORT_INVALID", "Overlay point is invalid.")
        points.append((float(cast(float, point.get("x"))), float(cast(float, point.get("y")))))
    return tuple(points)


def _draw_quad(
    canvas: NDArray[np.uint8],
    quad: Sequence[tuple[float, float]],
    colour: tuple[int, int, int],
    thickness: int,
) -> None:
    points = np.rint(np.asarray(quad, dtype=np.float64)).astype(np.int32).reshape((-1, 1, 2))
    cv2.polylines(canvas, [points], True, colour, thickness, cv2.LINE_AA)


def _error(code: str, message: str) -> BoardCellGeometryAuditError:
    return BoardCellGeometryAuditError(code, message)


__all__ = [
    "AUDIT_SCHEMA_VERSION",
    "AUDIT_VERSION",
    "DEFAULT_SAMPLE_SEED",
    "EXPECTED_PAGE_GEOMETRY_VERSIONS",
    "SAMPLE_POLICY_VERSION",
    "BoardCellGeometryAudit",
    "BoardCellGeometryAuditError",
    "RegisteredPage",
    "load_page_geometry_manifest",
    "registered_pages",
    "render_audit_contact_sheets",
    "render_audit_overlays",
    "run_board_cell_geometry_audit",
    "select_audit_pages",
    "write_content_addressed_audit",
]
