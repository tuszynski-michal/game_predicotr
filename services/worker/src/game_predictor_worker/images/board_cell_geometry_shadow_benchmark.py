"""Read-only cross-staging shadow benchmark for automatic v19 cell geometry."""

from __future__ import annotations

import hashlib
import math
import os
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from statistics import fmean
from typing import Literal, cast

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageOps, UnidentifiedImageError

from .board_cell_geometry_audit import (
    BoardCellGeometryAudit,
    RegisteredPage,
    load_page_geometry_manifest,
    registered_pages,
    render_audit_contact_sheets,
    render_audit_overlays,
    select_audit_pages,
)
from .board_cell_geometry_contract import (
    BOARD_CELL_GEOMETRY_VERSION,
    BoardCellGeometryEntry,
    BoardCellQuad,
    canonical_json_bytes,
)
from .board_cell_geometry_crops import (
    CROPPER_VERSION,
    BoardCellGeometrySourceDirectCropper,
)
from .board_cell_geometry_estimator import (
    ESTIMATOR_VERSION,
    BoardCellGeometryEstimate,
    estimate_board_cell_geometry,
    estimator_thresholds,
)
from .geometry import Quad
from .grid_symbol_diagnosis import CellPrediction

SHADOW_MANIFEST_VERSION = "board-cell-geometry-shadow-manifest-v1"
SHADOW_MANIFEST_SCHEMA_VERSION = 1
SHADOW_RUN_REPORT_VERSION = "board-cell-geometry-shadow-run-report-v1"
SHADOW_GALLERY_VERSION = "board-cell-geometry-shadow-gallery-v1"
SAMPLE_POLICY_VERSION = "sha256-ranked-balanced-six-staging-pages-v1"
DEFAULT_SAMPLE_SEED = "task-2-v19-cross-staging-shadow-v1"
EXPECTED_STAGING_COUNT = 6
EXPECTED_PAGES_PER_STAGING = 50
EXPECTED_PAGE_COUNT = 300
EXPECTED_BOARD_COUNT = 2700
_SHA256 = frozenset("0123456789abcdef")


class BoardCellGeometryShadowError(RuntimeError):
    """Stable failure which prevents an untrustworthy shadow result."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ShadowStagingSpec:
    label: str
    manifest_path: Path
    manifest_checksum_sha256: str


@dataclass(frozen=True, slots=True)
class SelectedShadowPage:
    staging_label: str
    staging_index: int
    page_manifest_checksum_sha256: str
    page: RegisteredPage


@dataclass(frozen=True, slots=True)
class ShadowChallengeBoard:
    board_id: str
    staging_label: str
    sequence_number: int
    position_index: int
    source_checksum_sha256: str
    source_relative_path: str
    page_quad: tuple[tuple[float, float], ...]
    manual_cells: tuple[BoardCellQuad, ...]
    automatic_cells: tuple[BoardCellQuad, ...]
    expected_symbols: tuple[str, ...]
    predictions: tuple[CellPrediction, ...]
    status: Literal["automatic_success", "deferred"]
    fallback_reason: str | None
    inlier_p95_residual_px: float | None
    mean_cell_corner_error_px: float | None
    max_cell_corner_error_px: float | None
    catastrophic_slot_shift: bool

    def __post_init__(self) -> None:
        if len(self.manual_cells) != 15 or len(self.expected_symbols) != 15:
            raise _error(
                "BOARD_CELL_SHADOW_CHALLENGE_INVALID",
                "A challenge board requires fifteen manual cells and labels.",
            )
        if self.status == "automatic_success":
            if len(self.automatic_cells) != 15 or len(self.predictions) != 15:
                raise _error(
                    "BOARD_CELL_SHADOW_CHALLENGE_INVALID",
                    "An automatic challenge success requires fifteen cells and predictions.",
                )
            if self.fallback_reason is not None:
                raise _error(
                    "BOARD_CELL_SHADOW_CHALLENGE_INVALID",
                    "An automatic challenge success cannot carry a fallback reason.",
                )
        elif self.automatic_cells or self.predictions or not self.fallback_reason:
            raise _error(
                "BOARD_CELL_SHADOW_CHALLENGE_INVALID",
                "A deferred challenge board cannot contain partial automatic output.",
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "automaticCells": [_stable_cell_payload(cell) for cell in self.automatic_cells],
            "boardId": self.board_id,
            "catastrophicSlotShift": self.catastrophic_slot_shift,
            "expectedSymbols": list(self.expected_symbols),
            "fallbackReason": self.fallback_reason,
            "inlierP95ResidualPx": _rounded(self.inlier_p95_residual_px),
            "manualCells": [cell.to_dict() for cell in self.manual_cells],
            "maxCellCornerErrorPx": _rounded(self.max_cell_corner_error_px),
            "meanCellCornerErrorPx": _rounded(self.mean_cell_corner_error_px),
            "pageQuad": _float_quad_payload(self.page_quad),
            "positionIndex": self.position_index,
            "predictions": [prediction.to_dict() for prediction in self.predictions],
            "sequenceNumber": self.sequence_number,
            "sourceImageChecksumSha256": self.source_checksum_sha256,
            "sourceImageRelativePath": self.source_relative_path,
            "stagingLabel": self.staging_label,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class BoardCellGeometryShadowBenchmark:
    document: dict[str, object]
    source_images: tuple[NDArray[np.uint8], ...]
    timing_report: dict[str, object]
    challenge_source_images: tuple[NDArray[np.uint8], ...] = ()

    @property
    def checksum_sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.document)).hexdigest()


Estimator = Callable[[NDArray[np.uint8], Quad], BoardCellGeometryEstimate]


def select_cross_staging_pages(
    staging_pages: Sequence[tuple[str, str, Sequence[RegisteredPage]]],
    *,
    pages_per_staging: int = EXPECTED_PAGES_PER_STAGING,
    sample_seed: str = DEFAULT_SAMPLE_SEED,
    expected_staging_count: int = EXPECTED_STAGING_COUNT,
) -> tuple[SelectedShadowPage, ...]:
    """Freeze an equal deterministic sample from every staging."""

    if len(staging_pages) != expected_staging_count or not sample_seed:
        raise _error(
            "BOARD_CELL_SHADOW_SAMPLE_INVALID",
            f"The shadow sample requires exactly {expected_staging_count} staging inputs.",
        )
    if pages_per_staging < 1:
        raise _error("BOARD_CELL_SHADOW_SAMPLE_INVALID", "The staging quota must be positive.")
    labels = [label for label, _checksum, _pages in staging_pages]
    if any(not label.strip() for label in labels) or len(set(labels)) != len(labels):
        raise _error(
            "BOARD_CELL_SHADOW_SAMPLE_INVALID", "Staging labels must be non-empty and unique."
        )
    selected: list[SelectedShadowPage] = []
    seen_checksums: set[str] = set()
    for staging_index, (label, manifest_checksum, pages) in enumerate(staging_pages):
        _require_sha256(manifest_checksum, "page manifest")
        chosen = select_audit_pages(
            pages,
            sample_size=pages_per_staging,
            sample_seed=f"{sample_seed}:{label}",
        )
        for page in chosen:
            if page.source_checksum_sha256 in seen_checksums:
                raise _error(
                    "BOARD_CELL_SHADOW_SOURCE_DUPLICATE",
                    "A source page occurs in more than one staging sample.",
                )
            seen_checksums.add(page.source_checksum_sha256)
            selected.append(
                SelectedShadowPage(
                    staging_label=label,
                    staging_index=staging_index,
                    page_manifest_checksum_sha256=manifest_checksum,
                    page=page,
                )
            )
    return tuple(selected)


def run_board_cell_geometry_shadow_benchmark(
    *,
    staging_specs: Sequence[ShadowStagingSpec],
    source_root: Path,
    challenge_boards: Sequence[ShadowChallengeBoard] = (),
    challenge_source_images: Sequence[NDArray[np.uint8]] = (),
    pages_per_staging: int = EXPECTED_PAGES_PER_STAGING,
    sample_seed: str = DEFAULT_SAMPLE_SEED,
    expected_staging_count: int = EXPECTED_STAGING_COUNT,
    cell_output_size: int = 64,
    estimator: Estimator = estimate_board_cell_geometry,
) -> BoardCellGeometryShadowBenchmark:
    """Run v19 without persistence and emit a deterministic result manifest."""

    root = source_root.resolve(strict=True)
    loaded: list[tuple[str, str, tuple[RegisteredPage, ...]]] = []
    staging_scope: list[dict[str, object]] = []
    for spec in staging_specs:
        expected_checksum = _require_sha256(spec.manifest_checksum_sha256, "page manifest")
        content, payload = load_page_geometry_manifest(spec.manifest_path)
        actual_checksum = hashlib.sha256(content).hexdigest()
        if actual_checksum != expected_checksum:
            raise _error(
                "BOARD_CELL_SHADOW_MANIFEST_DRIFT",
                f"The pinned page manifest differs for staging {spec.label}.",
            )
        pages = registered_pages(payload)
        for page in pages:
            first_part = PurePosixPath(page.source_relative_path).parts[0]
            if first_part != spec.label:
                raise _error(
                    "BOARD_CELL_SHADOW_STAGING_PATH_MISMATCH",
                    f"Source {page.source_relative_path} does not belong to {spec.label}.",
                )
        loaded.append((spec.label, actual_checksum, pages))
        staging_scope.append(
            {
                "label": spec.label,
                "pageGeometryManifestChecksumSha256": actual_checksum,
                "registeredPageCount": len(pages),
                "samplePageCount": pages_per_staging,
            }
        )
    selected = select_cross_staging_pages(
        loaded,
        pages_per_staging=pages_per_staging,
        sample_seed=sample_seed,
        expected_staging_count=expected_staging_count,
    )
    cropper = BoardCellGeometrySourceDirectCropper(cell_output_size=cell_output_size)
    pages_payload: list[dict[str, object]] = []
    images: list[NDArray[np.uint8]] = []
    estimator_durations: list[float] = []
    cropper_durations: list[float] = []
    staging_durations: dict[str, float] = {}
    started = time.perf_counter()
    for sample_index, selected_page in enumerate(selected):
        page_started = time.perf_counter()
        image = _load_verified_rgb(root, selected_page.page)
        images.append(image)
        boards: list[dict[str, object]] = []
        for position_index, quad in enumerate(selected_page.page.quads):
            estimate_started = time.perf_counter()
            estimate = estimator(image, quad)
            estimator_durations.append(time.perf_counter() - estimate_started)
            crop_payload, shadow_status = _shadow_crop_payload(
                estimate,
                cropper=cropper,
                image=image,
                selected_page=selected_page,
                sample_index=sample_index,
                position_index=position_index,
                cropper_durations=cropper_durations,
            )
            boards.append(
                {
                    "crop": crop_payload,
                    "estimate": _stable_estimate_payload(estimate),
                    "pageQuad": _quad_payload(quad),
                    "positionIndex": position_index,
                    "sequenceNumber": selected_page.page.sequence_start + position_index,
                    "shadowStatus": shadow_status,
                }
            )
        staging_durations[selected_page.staging_label] = staging_durations.get(
            selected_page.staging_label, 0.0
        ) + (time.perf_counter() - page_started)
        pages_payload.append(
            {
                "boards": boards,
                "pageGeometryManifestChecksumSha256": (selected_page.page_manifest_checksum_sha256),
                "sampleIndex": sample_index,
                "sequenceEnd": selected_page.page.sequence_end,
                "sequenceStart": selected_page.page.sequence_start,
                "sourceImageChecksumSha256": selected_page.page.source_checksum_sha256,
                "sourceImageRelativePath": selected_page.page.source_relative_path,
                "stagingIndex": selected_page.staging_index,
                "stagingLabel": selected_page.staging_label,
            }
        )
    challenge = build_shadow_challenge_document(challenge_boards)
    summary = _shadow_summary(pages_payload, challenge=challenge)
    document: dict[str, object] = {
        "challengeSubset": challenge,
        "cropper": {
            "cellOutputSize": cell_output_size,
            "fingerprintSha256": cropper.fingerprint_sha256,
            "version": CROPPER_VERSION,
        },
        "estimatorThresholds": estimator_thresholds(),
        "estimatorVersion": ESTIMATOR_VERSION,
        "geometryVersion": BOARD_CELL_GEOMETRY_VERSION,
        "pages": pages_payload,
        "samplePolicyVersion": SAMPLE_POLICY_VERSION,
        "sampleSeed": sample_seed,
        "schemaVersion": SHADOW_MANIFEST_SCHEMA_VERSION,
        "scope": {
            "boardCount": len(selected) * 9,
            "pageCount": len(selected),
            "pagesPerStaging": pages_per_staging,
            "stagingCount": len(staging_specs),
            "stagings": staging_scope,
        },
        "summary": summary,
        "version": SHADOW_MANIFEST_VERSION,
    }
    elapsed = time.perf_counter() - started
    timing_report = {
        "cropper": _timing_summary(cropper_durations),
        "elapsedSeconds": round(elapsed, 6),
        "estimator": _timing_summary(estimator_durations),
        "stagingElapsedSeconds": {
            key: round(value, 6) for key, value in sorted(staging_durations.items())
        },
        "version": SHADOW_RUN_REPORT_VERSION,
    }
    if len(challenge_boards) != len(challenge_source_images):
        raise _error(
            "BOARD_CELL_SHADOW_CHALLENGE_INVALID",
            "Challenge source images must align with challenge boards.",
        )
    return BoardCellGeometryShadowBenchmark(
        document=document,
        source_images=tuple(images),
        timing_report=timing_report,
        challenge_source_images=tuple(challenge_source_images),
    )


def build_shadow_challenge_document(
    boards: Sequence[ShadowChallengeBoard],
) -> dict[str, object]:
    """Summarize all current manual overrides without hiding controlled defers."""

    ordered = tuple(sorted(boards, key=lambda item: (item.sequence_number, item.board_id)))
    if len({item.board_id for item in ordered}) != len(ordered):
        raise _error("BOARD_CELL_SHADOW_CHALLENGE_INVALID", "Challenge board IDs repeat.")
    successes = tuple(item for item in ordered if item.status == "automatic_success")
    expected = [symbol for item in successes for symbol in item.expected_symbols]
    predicted = [prediction for item in successes for prediction in item.predictions]
    correct = sum(
        left == right.symbol_code for left, right in zip(expected, predicted, strict=True)
    )
    complete = sum(
        all(
            expected_symbol == prediction.symbol_code
            for expected_symbol, prediction in zip(
                item.expected_symbols, item.predictions, strict=True
            )
        )
        for item in successes
    )
    fallback_counts = Counter(
        item.fallback_reason for item in ordered if item.fallback_reason is not None
    )
    result: dict[str, object] = {
        "boards": [item.to_dict() for item in ordered],
        "summary": {
            "automaticCoverage": _ratio(len(successes), len(ordered)),
            "automaticSuccessBoardCount": len(successes),
            "boardCount": len(ordered),
            "catastrophicSlotShiftCount": sum(item.catastrophic_slot_shift for item in successes),
            "deferredBoardCount": len(ordered) - len(successes),
            "fallbackReasonCounts": dict(sorted(fallback_counts.items())),
            "maxCellCornerErrorPx": _maximum(item.max_cell_corner_error_px for item in successes),
            "meanCellCornerErrorPx": _mean(item.mean_cell_corner_error_px for item in successes),
            "modelSymbolAccuracy": _ratio(correct, len(expected)),
            "modelWholeBoardAccuracy": _ratio(complete, len(successes)),
        },
    }
    return result


def cell_geometry_error(
    automatic: Sequence[BoardCellQuad],
    manual: Sequence[BoardCellQuad],
) -> tuple[float, float, bool]:
    """Return corner error and detect whole-row/column slot displacement."""

    if len(automatic) != 15 or len(manual) != 15:
        raise _error(
            "BOARD_CELL_SHADOW_CHALLENGE_INVALID", "Geometry comparison requires 15 cells."
        )
    expected_order = [(row, column) for row in range(3) for column in range(5)]
    if [(cell.row_index, cell.column_index) for cell in automatic] != expected_order or [
        (cell.row_index, cell.column_index) for cell in manual
    ] != expected_order:
        raise _error("BOARD_CELL_SHADOW_CHALLENGE_INVALID", "Geometry cells must be row-major.")
    distances: list[float] = []
    manual_centers = [_cell_center(cell) for cell in manual]
    catastrophic = False
    for index, (automatic_cell, manual_cell) in enumerate(zip(automatic, manual, strict=True)):
        distances.extend(
            math.dist(left, right)
            for left, right in zip(automatic_cell.quad, manual_cell.quad, strict=True)
        )
        automatic_center = _cell_center(automatic_cell)
        nearest = min(
            range(len(manual_centers)),
            key=lambda candidate: math.dist(automatic_center, manual_centers[candidate]),
        )
        catastrophic = catastrophic or nearest != index
    return round(fmean(distances), 8), round(max(distances), 8), catastrophic


def write_content_addressed_shadow_manifest(
    benchmark: BoardCellGeometryShadowBenchmark,
    output_root: Path,
) -> Path:
    return _write_content_addressed(
        output_root / "manifests", canonical_json_bytes(benchmark.document), suffix=".json"
    )


def write_content_addressed_run_report(
    benchmark: BoardCellGeometryShadowBenchmark,
    output_root: Path,
) -> Path:
    payload = {
        **benchmark.timing_report,
        "shadowManifestChecksumSha256": benchmark.checksum_sha256,
    }
    return _write_content_addressed(
        output_root / "run-reports", canonical_json_bytes(payload), suffix=".json"
    )


def render_content_addressed_shadow_gallery(
    benchmark: BoardCellGeometryShadowBenchmark,
    output_root: Path,
) -> Path:
    """Render every sampled page and challenge board under immutable checksums."""

    checksum = benchmark.checksum_sha256
    # Avoid repeating the 64-character manifest checksum in every raster path.
    # Each file retains its full content checksum and the immutable index binds
    # the complete gallery to this shadow manifest.
    gallery_root = output_root / "galleries"
    gallery_root.mkdir(parents=True, exist_ok=True)
    audit = BoardCellGeometryAudit(
        document={"pages": benchmark.document["pages"]},
        source_images=benchmark.source_images,
    )
    with tempfile.TemporaryDirectory(prefix="shadow-gallery-") as temporary_name:
        temporary = Path(temporary_name)
        overlays = render_audit_overlays(audit, temporary / "overlays")
        sheets = render_audit_contact_sheets(audit, temporary / "sheets")
        overlay_entries = _materialize_gallery_files(
            overlays, gallery_root / "page-overlays", kind="page-overlay"
        )
        sheet_entries = _materialize_gallery_files(
            sheets, gallery_root / "page-sheets", kind="page-sheet"
        )
    challenge_entries = _render_challenge_gallery(benchmark, gallery_root)
    gallery_document = {
        "challengeBoards": challenge_entries,
        "pageOverlays": overlay_entries,
        "pageSheets": sheet_entries,
        "shadowManifestChecksumSha256": checksum,
        "version": SHADOW_GALLERY_VERSION,
    }
    return _write_content_addressed(
        gallery_root / "indexes", canonical_json_bytes(gallery_document), suffix=".json"
    )


def _shadow_crop_payload(
    estimate: BoardCellGeometryEstimate,
    *,
    cropper: BoardCellGeometrySourceDirectCropper,
    image: NDArray[np.uint8],
    selected_page: SelectedShadowPage,
    sample_index: int,
    position_index: int,
    cropper_durations: list[float],
) -> tuple[dict[str, object], str]:
    if (
        estimate.status != "estimated"
        or estimate.lattice_bounds_quad is None
        or estimate.evidence is None
        or len(estimate.cells) != 15
    ):
        return (
            {
                "cellCount": 0,
                "reviewReasons": [
                    estimate.fallback_reason
                    or "BOARD_CELL_GEOMETRY_AUTOMATIC_EVIDENCE_INSUFFICIENT"
                ],
                "status": "needs_review",
            },
            "deferred",
        )
    entry = BoardCellGeometryEntry(
        source_order_index=sample_index,
        image_id=selected_page.page.source_checksum_sha256,
        source_image_checksum_sha256=selected_page.page.source_checksum_sha256,
        source_image_relative_path=selected_page.page.source_relative_path,
        source_image_width=int(image.shape[1]),
        source_image_height=int(image.shape[0]),
        source_group=selected_page.staging_label,
        condition_tags=("cross-staging-shadow",),
        sequence_number=selected_page.page.sequence_start + position_index,
        position_index=position_index,
        lattice_bounds_quad=estimate.lattice_bounds_quad,
        cells=estimate.cells,
        evidence=estimate.evidence,
    )
    crop_started = time.perf_counter()
    cropped = cropper.crop(image, entry)
    cropper_durations.append(time.perf_counter() - crop_started)
    if cropped.status == "needs_review" and cropped.cells:
        raise _error(
            "BOARD_CELL_SHADOW_PARTIAL_CROP",
            "A failed shadow crop emitted partial cell images.",
        )
    payload = {
        "cellCount": len(cropped.cells),
        "cropperFingerprintSha256": cropped.cropper_fingerprint_sha256,
        "reviewReasons": list(cropped.review_reasons),
        "status": cropped.status,
    }
    return payload, "automatic_success" if cropped.status == "cropped" else "deferred"


def _shadow_summary(
    pages: Sequence[Mapping[str, object]],
    *,
    challenge: Mapping[str, object],
) -> dict[str, object]:
    boards = [
        cast(Mapping[str, object], board)
        for page in pages
        for board in cast(Sequence[object], page["boards"])
    ]
    successes = [board for board in boards if board["shadowStatus"] == "automatic_success"]
    fallback_counts: Counter[str] = Counter()
    residuals: list[float] = []
    by_staging: dict[str, dict[str, object]] = {}
    by_position: dict[str, dict[str, object]] = {}
    for page in pages:
        label = cast(str, page["stagingLabel"])
        stage_boards = cast(Sequence[Mapping[str, object]], page["boards"])
        stage = by_staging.setdefault(label, {"automaticSuccess": 0, "boardCount": 0})
        for board in stage_boards:
            stage["boardCount"] = cast(int, stage["boardCount"]) + 1
            position = str(board["positionIndex"])
            position_summary = by_position.setdefault(
                position, {"automaticSuccess": 0, "boardCount": 0}
            )
            position_summary["boardCount"] = cast(int, position_summary["boardCount"]) + 1
            if board["shadowStatus"] == "automatic_success":
                stage["automaticSuccess"] = cast(int, stage["automaticSuccess"]) + 1
                position_summary["automaticSuccess"] = (
                    cast(int, position_summary["automaticSuccess"]) + 1
                )
            estimate = cast(Mapping[str, object], board["estimate"])
            residual = estimate.get("inlierP95ResidualPx")
            if isinstance(residual, int | float) and not isinstance(residual, bool):
                residuals.append(float(residual))
            crop = cast(Mapping[str, object], board["crop"])
            reasons = crop.get("reviewReasons")
            if isinstance(reasons, Sequence) and not isinstance(reasons, str | bytes):
                fallback_counts.update(str(reason) for reason in reasons)
    for groups in (by_staging, by_position):
        for value in groups.values():
            value["automaticCoverage"] = _ratio(
                cast(int, value["automaticSuccess"]), cast(int, value["boardCount"])
            )
    challenge_summary = cast(Mapping[str, object], challenge.get("summary", {}))
    return {
        "automaticCoverage": _ratio(len(successes), len(boards)),
        "automaticSuccessBoardCount": len(successes),
        "boardCount": len(boards),
        "challenge": dict(challenge_summary),
        "deferredBoardCount": len(boards) - len(successes),
        "fallbackReasonCounts": dict(sorted(fallback_counts.items())),
        "inlierP95ResidualPx": {
            "max": _maximum(residuals),
            "mean": _mean(residuals),
            "p95": _percentile(residuals, 95),
        },
        "perPosition": dict(sorted(by_position.items(), key=lambda item: int(item[0]))),
        "perStaging": dict(sorted(by_staging.items())),
    }


def _load_verified_rgb(root: Path, page: RegisteredPage) -> NDArray[np.uint8]:
    relative = PurePosixPath(page.source_relative_path)
    path = root.joinpath(*relative.parts).resolve(strict=True)
    if not path.is_relative_to(root):
        raise _error("BOARD_CELL_SHADOW_PATH_UNSAFE", "Source path escapes the source root.")
    try:
        content = path.read_bytes()
        with Image.open(path) as image:
            image.load()
            rgb = np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)
    except (OSError, UnidentifiedImageError) as error:
        raise _error(
            "BOARD_CELL_SHADOW_SOURCE_UNAVAILABLE", f"Cannot read {page.source_relative_path}."
        ) from error
    if hashlib.sha256(content).hexdigest() != page.source_checksum_sha256:
        raise _error(
            "BOARD_CELL_SHADOW_SOURCE_DRIFT", f"Checksum differs for {page.source_relative_path}."
        )
    return rgb


def _render_challenge_gallery(
    benchmark: BoardCellGeometryShadowBenchmark,
    gallery_root: Path,
) -> list[dict[str, object]]:
    challenge = cast(Mapping[str, object], benchmark.document["challengeSubset"])
    raw_boards = cast(Sequence[Mapping[str, object]], challenge.get("boards", ()))
    if len(raw_boards) != len(benchmark.challenge_source_images):
        raise _error(
            "BOARD_CELL_SHADOW_CHALLENGE_INVALID", "Challenge gallery inputs do not align."
        )
    entries: list[dict[str, object]] = []
    destination_root = gallery_root / "challenge-overlays"
    for raw, rgb in zip(raw_boards, benchmark.challenge_source_images, strict=True):
        overlay = _challenge_overlay(raw, rgb)
        success, encoded = cv2.imencode(".jpg", overlay, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not success:
            raise _error(
                "BOARD_CELL_SHADOW_GALLERY_FAILED", "A challenge overlay could not be encoded."
            )
        content = bytes(encoded)
        destination = _write_content_addressed(destination_root, content, suffix=".jpg")
        entries.append(
            {
                "boardId": raw["boardId"],
                "checksumSha256": destination.stem,
                "relativePath": destination.relative_to(gallery_root).as_posix(),
                "sequenceNumber": raw["sequenceNumber"],
                "status": raw["status"],
            }
        )
    return entries


def _challenge_overlay(raw: Mapping[str, object], rgb: NDArray[np.uint8]) -> NDArray[np.uint8]:
    canvas = cast(NDArray[np.uint8], cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    manual = cast(Sequence[Mapping[str, object]], raw["manualCells"])
    automatic = cast(Sequence[Mapping[str, object]], raw["automaticCells"])
    for cell in manual:
        _draw_float_quad(canvas, cast(Sequence[Mapping[str, object]], cell["quad"]), (255, 220, 0))
    for cell in automatic:
        _draw_float_quad(canvas, cast(Sequence[Mapping[str, object]], cell["quad"]), (40, 220, 40))
    page_quad = cast(Sequence[Mapping[str, object]], raw["pageQuad"])
    points = [
        (
            float(cast(int | float, point["x"])),
            float(cast(int | float, point["y"])),
        )
        for point in page_quad
    ]
    height, width = canvas.shape[:2]
    padding_x = max(16, round((max(x for x, _y in points) - min(x for x, _y in points)) * 0.12))
    padding_y = max(16, round((max(y for _x, y in points) - min(y for _x, y in points)) * 0.18))
    left = max(0, math.floor(min(x for x, _y in points) - padding_x))
    right = min(width, math.ceil(max(x for x, _y in points) + padding_x))
    top = max(0, math.floor(min(y for _x, y in points) - padding_y))
    bottom = min(height, math.ceil(max(y for _x, y in points) + padding_y))
    crop = canvas[top:bottom, left:right]
    if crop.size == 0:
        raise _error("BOARD_CELL_SHADOW_GALLERY_FAILED", "Challenge crop is empty.")
    scale = min(1400 / crop.shape[1], 900 / crop.shape[0])
    resized = cv2.resize(
        crop,
        (max(1, round(crop.shape[1] * scale)), max(1, round(crop.shape[0] * scale))),
        interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR,
    )
    sheet: NDArray[np.uint8] = np.zeros((980, 1440, 3), dtype=np.uint8)
    x = (1440 - resized.shape[1]) // 2
    y = 64 + (900 - resized.shape[0]) // 2
    sheet[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    title = f"seq {raw['sequenceNumber']} | {raw['stagingLabel']} | {raw['status']}"
    cv2.putText(sheet, title, (16, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (255, 255, 255), 2)
    return sheet


def _draw_float_quad(
    canvas: NDArray[np.uint8],
    raw_quad: Sequence[Mapping[str, object]],
    colour: tuple[int, int, int],
) -> None:
    points = np.rint(
        np.asarray(
            [
                (
                    float(cast(int | float, point["x"])),
                    float(cast(int | float, point["y"])),
                )
                for point in raw_quad
            ]
        )
    ).astype(np.int32)
    cv2.polylines(canvas, [points.reshape((-1, 1, 2))], True, colour, 2, cv2.LINE_AA)


def _materialize_gallery_files(
    paths: Sequence[Path], destination_root: Path, *, kind: str
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for index, source in enumerate(paths):
        destination = _write_content_addressed(
            destination_root, source.read_bytes(), suffix=source.suffix.lower()
        )
        entries.append(
            {
                "checksumSha256": destination.stem,
                "index": index,
                "kind": kind,
                "relativePath": destination.relative_to(destination_root.parent).as_posix(),
            }
        )
    return entries


def _write_content_addressed(root: Path, content: bytes, *, suffix: str) -> Path:
    checksum = hashlib.sha256(content).hexdigest()
    root.mkdir(parents=True, exist_ok=True)
    destination = root / f"{checksum}{suffix}"
    if destination.exists():
        if destination.read_bytes() != content:
            raise _error(
                "BOARD_CELL_SHADOW_ARTIFACT_CONFLICT",
                "A content-addressed shadow artifact contains different bytes.",
            )
        return destination
    # Keep the temporary basename short because the content-addressed gallery
    # already creates deep paths and Windows still enforces legacy path limits
    # in some Python/runtime combinations.
    descriptor, temporary_name = tempfile.mkstemp(prefix=".tmp-", suffix=".part", dir=root)
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
                    "BOARD_CELL_SHADOW_ARTIFACT_CONFLICT",
                    "A content-addressed shadow artifact contains different bytes.",
                ) from None
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _timing_summary(values: Sequence[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "maxMilliseconds": _milliseconds(_maximum(values)),
        "meanMilliseconds": _milliseconds(_mean(values)),
        "p95Milliseconds": _milliseconds(_percentile(values, 95)),
    }


def _milliseconds(value: float | None) -> float | None:
    return None if value is None else round(value * 1000, 4)


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else round(numerator / denominator, 8)


def _mean(values: Iterable[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return None if not present else round(fmean(present), 8)


def _maximum(values: Iterable[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return None if not present else round(max(present), 8)


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    return round(float(np.percentile(np.asarray(values, dtype=np.float64), percentile)), 8)


def _rounded(value: float | None) -> float | None:
    # Board-level OpenCV residuals can differ below 1e-4 px between otherwise
    # identical Windows processes. Four decimals preserve materially more
    # precision than the acceptance thresholds while keeping the immutable
    # shadow manifest reproducible.
    return None if value is None else round(value, 4)


def _cell_center(cell: BoardCellQuad) -> tuple[float, float]:
    return (
        fmean(point[0] for point in cell.quad),
        fmean(point[1] for point in cell.quad),
    )


def _quad_payload(quad: Quad) -> list[dict[str, float]]:
    return [{"x": float(point.x), "y": float(point.y)} for point in quad]


def _float_quad_payload(
    quad: Sequence[tuple[float, float]],
) -> list[dict[str, float]]:
    return [{"x": round(point[0], 4), "y": round(point[1], 4)} for point in quad]


def _stable_cell_payload(cell: BoardCellQuad) -> dict[str, object]:
    return {
        "columnIndex": cell.column_index,
        "quad": [
            {"x": round(float(point[0]), 3), "y": round(float(point[1]), 3)} for point in cell.quad
        ],
        "rowIndex": cell.row_index,
    }


def _stable_estimate_payload(estimate: BoardCellGeometryEstimate) -> dict[str, object]:
    payload = cast(dict[str, object], estimate.to_dict())
    raw_cells = payload.get("cells")
    if isinstance(raw_cells, list):
        payload["cells"] = [_stable_cell_payload(cell) for cell in estimate.cells]
    raw_bounds = payload.get("latticeBoundsQuad")
    if raw_bounds is not None and estimate.lattice_bounds_quad is not None:
        payload["latticeBoundsQuad"] = [
            {"x": round(float(point[0]), 3), "y": round(float(point[1]), 3)}
            for point in estimate.lattice_bounds_quad
        ]
    return payload


def _require_sha256(value: str, label: str) -> str:
    if len(value) != 64 or any(character not in _SHA256 for character in value):
        raise _error("BOARD_CELL_SHADOW_CHECKSUM_INVALID", f"The {label} is not SHA-256.")
    return value


def _error(code: str, message: str) -> BoardCellGeometryShadowError:
    return BoardCellGeometryShadowError(code, message)


__all__ = [
    "DEFAULT_SAMPLE_SEED",
    "EXPECTED_BOARD_COUNT",
    "EXPECTED_PAGE_COUNT",
    "EXPECTED_PAGES_PER_STAGING",
    "EXPECTED_STAGING_COUNT",
    "SAMPLE_POLICY_VERSION",
    "SHADOW_GALLERY_VERSION",
    "SHADOW_MANIFEST_SCHEMA_VERSION",
    "SHADOW_MANIFEST_VERSION",
    "SHADOW_RUN_REPORT_VERSION",
    "BoardCellGeometryShadowBenchmark",
    "BoardCellGeometryShadowError",
    "SelectedShadowPage",
    "ShadowChallengeBoard",
    "ShadowStagingSpec",
    "build_shadow_challenge_document",
    "cell_geometry_error",
    "render_content_addressed_shadow_gallery",
    "run_board_cell_geometry_shadow_benchmark",
    "select_cross_staging_pages",
    "write_content_addressed_run_report",
    "write_content_addressed_shadow_manifest",
]
