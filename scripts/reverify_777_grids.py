"""One-off grid re-verification for game 777 (plan: GAME_777_GRID_REVERIFICATION).

``calibrate`` is strictly read-only: every database connection is opened with
``read_only = True`` and all reads run inside ``game_storage_scope``.  It
measures an independent symbol-lattice verifier against the golden set that
humans produced in the Reviewer and sweeps acceptance thresholds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast
from uuid import UUID

import numpy as np
from game_predictor_api.config import get_settings
from game_predictor_api.storage.database import create_database_engine, create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.models import (
    ImageBoardGeometryPendingModel,
    ImageBoardGeometryRevisionModel,
    ImageSourceGeometryRevisionModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from game_predictor_worker.images.board_cell_geometry_estimator import (
    BoardCellGeometryEstimate,
    estimate_board_cell_geometry,
)
from game_predictor_worker.images.geometry import Point
from PIL import Image, ImageOps
from sqlalchemy import event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

REPORT_VERSION = "grid-reverify-777-calibration-v1"
GAME_777_ID = UUID("bfc4f949-5c14-4850-b02a-db99610bcfa5")
AUTO_ENGINE_KIND = "structured_opencv_v1"
MANUAL_ACTOR = "local-admin"
DEFAULT_OUTPUT_DIR = Path("artifacts/grid-reverify-777")
HINT_SCALES: tuple[float, ...] = (1.0, 1.06, 1.12)
TAU_GRID: tuple[float, ...] = (1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0)
RESIDUAL_GRID: tuple[float | None, ...] = (1.0, 1.5, 2.0, 3.0, 4.0, None)
INLIER_GRID: tuple[int, ...] = (15, 14, 13, 12)
HUMAN_ERROR_GRID: tuple[float, ...] = (2.0, 3.0, 5.0)

FloatQuad = tuple[
    tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]
]
GoldenKind = Literal["approved_unchanged", "human_revised", "pending_resolved"]


# --------------------------------------------------------------------------- geometry


def parse_quad(value: object) -> FloatQuad | None:
    """Return a TL, TR, BR, BL quad from a ``[{x, y}, ...]`` payload, or ``None``."""

    if not isinstance(value, Sequence) or isinstance(value, str | bytes) or len(value) != 4:
        return None
    points: list[tuple[float, float]] = []
    for item in value:
        if not isinstance(item, Mapping):
            return None
        x, y = item.get("x"), item.get("y")
        if (
            isinstance(x, bool)
            or isinstance(y, bool)
            or not isinstance(x, int | float)
            or not isinstance(y, int | float)
            or not math.isfinite(float(x))
            or not math.isfinite(float(y))
        ):
            return None
        points.append((float(x), float(y)))
    return cast(FloatQuad, tuple(points))


def max_corner_distance(first: FloatQuad, second: FloatQuad) -> float:
    return max(math.dist(left, right) for left, right in zip(first, second, strict=True))


def scale_quad(quad: FloatQuad, scale: float) -> FloatQuad:
    cx = sum(point[0] for point in quad) / 4.0
    cy = sum(point[1] for point in quad) / 4.0
    return cast(
        FloatQuad,
        tuple((cx + (x - cx) * scale, cy + (y - cy) * scale) for x, y in quad),
    )


def quad_inside(quad: FloatQuad, *, width: int, height: int) -> bool:
    return all(0.0 <= x <= width - 1 and 0.0 <= y <= height - 1 for x, y in quad)


def _detector_quad(
    quad: FloatQuad, *, width: int, height: int
) -> tuple[Point, Point, Point, Point]:
    points = tuple(
        Point(
            min(max(int(round(x)), 0), width - 1),
            min(max(int(round(y)), 0), height - 1),
        )
        for x, y in quad
    )
    return cast(tuple[Point, Point, Point, Point], points)


# --------------------------------------------------------------------------- verifier


@dataclass(frozen=True, slots=True)
class VerifierObservation:
    """One verifier run for one board and one hint scale."""

    hint_scale: float
    status: str
    quad: FloatQuad | None
    inlier_count: int
    p95_residual_px: float | None
    fallback_reason: str | None
    elapsed_ms: float


def run_verifier(
    rgb: np.ndarray[Any, np.dtype[np.uint8]],
    hint: FloatQuad,
    *,
    hint_scale: float,
) -> VerifierObservation:
    height, width = int(rgb.shape[0]), int(rgb.shape[1])
    started = time.perf_counter()
    try:
        estimate: BoardCellGeometryEstimate = estimate_board_cell_geometry(
            rgb,
            _detector_quad(scale_quad(hint, hint_scale), width=width, height=height),
        )
    except ValueError as error:
        return VerifierObservation(
            hint_scale=hint_scale,
            status="verifier_failed",
            quad=None,
            inlier_count=0,
            p95_residual_px=None,
            fallback_reason=f"{type(error).__name__}: {error}",
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    quad = (
        None
        if estimate.lattice_bounds_quad is None
        else cast(
            FloatQuad,
            tuple((float(x), float(y)) for x, y in estimate.lattice_bounds_quad),
        )
    )
    return VerifierObservation(
        hint_scale=hint_scale,
        status=estimate.status,
        quad=quad,
        inlier_count=estimate.inlier_count,
        p95_residual_px=estimate.inlier_p95_residual_px,
        fallback_reason=estimate.fallback_reason,
        elapsed_ms=elapsed_ms,
    )


@dataclass(frozen=True, slots=True)
class Thresholds:
    tau_px: float
    max_residual_px: float | None
    min_inliers: int

    def to_payload(self) -> dict[str, object]:
        return {
            "maxResidualPx": self.max_residual_px,
            "minInliers": self.min_inliers,
            "tauPx": self.tau_px,
        }


def verifier_is_confident(
    observation: VerifierObservation,
    thresholds: Thresholds,
    *,
    width: int,
    height: int,
) -> bool:
    """Gate shared by both populations: a complete, low-residual, in-image lattice."""

    if observation.status != "estimated" or observation.quad is None:
        return False
    if observation.inlier_count < thresholds.min_inliers:
        return False
    if thresholds.max_residual_px is not None and (
        observation.p95_residual_px is None
        or observation.p95_residual_px > thresholds.max_residual_px
    ):
        return False
    return quad_inside(observation.quad, width=width, height=height)


def validation_board_accepted(
    observation: VerifierObservation,
    engine_quad: FloatQuad,
    thresholds: Thresholds,
    *,
    width: int,
    height: int,
) -> bool:
    """A "Do walidacji" board is approved only when the verifier agrees with the engine."""

    if not verifier_is_confident(observation, thresholds, width=width, height=height):
        return False
    assert observation.quad is not None
    return max_corner_distance(observation.quad, engine_quad) <= thresholds.tau_px


# --------------------------------------------------------------------------- golden set


@dataclass(slots=True)
class GoldenBoard:
    kind: GoldenKind
    recognized_board_id: UUID
    source_image_id: UUID
    position_index: int
    sequence_number: int
    width: int
    height: int
    hint: FloatQuad
    engine_quad: FloatQuad | None
    human_quad: FloatQuad
    observations: list[VerifierObservation] = field(default_factory=list)

    @property
    def engine_error_px(self) -> float | None:
        if self.engine_quad is None:
            return None
        return max_corner_distance(self.engine_quad, self.human_quad)


@dataclass(slots=True)
class SampleBoard:
    kind: Literal["validation_sample", "pending_sample"]
    width: int
    height: int
    engine_quad: FloatQuad | None
    observations: list[VerifierObservation] = field(default_factory=list)
    position_index: int = -1
    sequence_number: int | None = None


def _slot_geometry(board_geometries: object, position_index: int) -> Mapping[str, object] | None:
    if not isinstance(board_geometries, Sequence) or isinstance(board_geometries, str | bytes):
        return None
    matches = [
        item
        for item in board_geometries
        if isinstance(item, Mapping) and item.get("positionIndex") == position_index
    ]
    if len(matches) == 1:
        return cast(Mapping[str, object], matches[0])
    if 0 <= position_index < len(board_geometries) and isinstance(
        board_geometries[position_index], Mapping
    ):
        return cast(Mapping[str, object], board_geometries[position_index])
    return None


def hint_quad(slot: Mapping[str, object]) -> FloatQuad | None:
    for key in ("boardFrameQuad", "analysisQuad", "initialQuad"):
        quad = parse_quad(slot.get(key))
        if quad is not None:
            return quad
    return None


def engine_quad(slot: Mapping[str, object]) -> FloatQuad | None:
    if slot.get("disposition") != "automatic":
        return None
    return parse_quad(slot.get("symbolGridQuad"))


def _source_dimensions(source: SourceImageModel) -> tuple[int, int]:
    return int(source.oriented_width or source.width), int(source.oriented_height or source.height)


def _auto_revisions(
    session: Session, source_ids: Iterable[UUID]
) -> dict[UUID, ImageSourceGeometryRevisionModel]:
    ids = tuple(source_ids)
    if not ids:
        return {}
    rows = session.scalars(
        select(ImageSourceGeometryRevisionModel)
        .where(
            ImageSourceGeometryRevisionModel.source_image_id.in_(ids),
            ImageSourceGeometryRevisionModel.engine_kind == AUTO_ENGINE_KIND,
        )
        .order_by(
            ImageSourceGeometryRevisionModel.source_image_id,
            ImageSourceGeometryRevisionModel.revision,
        )
    ).all()
    result: dict[UUID, ImageSourceGeometryRevisionModel] = {}
    for row in rows:
        result.setdefault(row.source_image_id, row)  # earliest automatic revision
    return result


def load_golden(
    session: Session,
) -> tuple[list[GoldenBoard], dict[UUID, SourceImageModel], dict[str, int]]:
    skipped: dict[str, int] = {}
    approved_rows = session.execute(
        select(RecognizedBoardModel, SourceImageModel)
        .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
        .where(
            RecognizedBoardModel.asset_mode == "virtual_source",
            RecognizedBoardModel.approved_geometry_revision.is_not(None),
        )
    ).all()
    revised_rows = {
        revision.recognized_board_id: revision
        for revision in session.scalars(
            select(ImageBoardGeometryRevisionModel)
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageBoardGeometryRevisionModel.recognized_board_id,
            )
            .where(
                ImageBoardGeometryRevisionModel.corrected_by == MANUAL_ACTOR,
                ImageBoardGeometryRevisionModel.revision == RecognizedBoardModel.geometry_revision,
            )
        ).all()
    }
    pending_board_ids = set(
        session.scalars(
            select(ImageBoardGeometryPendingModel.recognized_board_id).where(
                ImageBoardGeometryPendingModel.status == "resolved",
                ImageBoardGeometryPendingModel.recognized_board_id.is_not(None),
            )
        ).all()
    )
    sources = {source.id: source for _board, source in approved_rows}
    autos = _auto_revisions(session, sources)
    golden: list[GoldenBoard] = []
    for board, source in approved_rows:
        auto = autos.get(source.id)
        slot = None if auto is None else _slot_geometry(auto.board_geometries, board.position_index)
        if slot is None:
            skipped["missing_automatic_slot"] = skipped.get("missing_automatic_slot", 0) + 1
            continue
        hint = hint_quad(slot)
        if hint is None:
            skipped["missing_hint"] = skipped.get("missing_hint", 0) + 1
            continue
        width, height = _source_dimensions(source)
        auto_quad = engine_quad(slot)
        revision = revised_rows.get(board.id)
        kind: GoldenKind
        if revision is None:
            if board.geometry_revision != 0 or auto_quad is None:
                skipped["approved_without_manual_revision"] = (
                    skipped.get("approved_without_manual_revision", 0) + 1
                )
                continue
            kind, human = "approved_unchanged", auto_quad
        else:
            parsed = parse_quad(revision.corners)
            if parsed is None:
                skipped["invalid_manual_corners"] = skipped.get("invalid_manual_corners", 0) + 1
                continue
            human = parsed
            kind = (
                "pending_resolved"
                if board.id in pending_board_ids or auto_quad is None
                else "human_revised"
            )
        golden.append(
            GoldenBoard(
                kind=kind,
                recognized_board_id=board.id,
                source_image_id=source.id,
                position_index=int(board.position_index),
                sequence_number=int(board.sequence_number),
                width=width,
                height=height,
                hint=hint,
                engine_quad=None if kind == "pending_resolved" else auto_quad,
                human_quad=human,
            )
        )
    return golden, sources, skipped


def load_samples(
    session: Session, *, sample_sources: int, seed: int
) -> tuple[list[tuple[SourceImageModel, list[SampleBoard], list[FloatQuad]]], int]:
    """Deterministic sample of sources for coverage: needs-validation and pending slots."""

    validation_source_ids = list(
        session.scalars(
            select(RecognizedBoardModel.source_image_id)
            .where(
                RecognizedBoardModel.asset_mode == "virtual_source",
                RecognizedBoardModel.approved_geometry_revision.is_(None),
                RecognizedBoardModel.geometry_revision == 0,
            )
            .distinct()
        ).all()
    )
    pending_source_ids = list(
        session.scalars(
            select(ImageBoardGeometryPendingModel.source_image_id)
            .where(ImageBoardGeometryPendingModel.status == "pending")
            .distinct()
        ).all()
    )
    rng = random.Random(seed)
    validation_source_ids.sort(key=str)
    pending_source_ids.sort(key=str)
    chosen = set(rng.sample(validation_source_ids, min(sample_sources, len(validation_source_ids))))
    chosen |= set(rng.sample(pending_source_ids, min(sample_sources, len(pending_source_ids))))
    sources = {
        source.id: source
        for source in session.scalars(
            select(SourceImageModel).where(SourceImageModel.id.in_(tuple(chosen)))
        ).all()
    }
    autos = _auto_revisions(session, sources)
    pending_positions: dict[UUID, set[int]] = {}
    for source_id, position in session.execute(
        select(
            ImageBoardGeometryPendingModel.source_image_id,
            ImageBoardGeometryPendingModel.position_index,
        ).where(
            ImageBoardGeometryPendingModel.status == "pending",
            ImageBoardGeometryPendingModel.source_image_id.in_(tuple(sources)),
        )
    ).all():
        pending_positions.setdefault(source_id, set()).add(int(position))
    unapproved_positions: dict[UUID, set[int]] = {}
    for source_id, position in session.execute(
        select(RecognizedBoardModel.source_image_id, RecognizedBoardModel.position_index).where(
            RecognizedBoardModel.source_image_id.in_(tuple(sources)),
            RecognizedBoardModel.approved_geometry_revision.is_(None),
            RecognizedBoardModel.geometry_revision == 0,
        )
    ).all():
        unapproved_positions.setdefault(source_id, set()).add(int(position))
    result: list[tuple[SourceImageModel, list[SampleBoard], list[FloatQuad]]] = []
    for source_id in sorted(sources, key=str):
        source = sources[source_id]
        auto = autos.get(source_id)
        if auto is None:
            continue
        width, height = _source_dimensions(source)
        boards: list[SampleBoard] = []
        hints: list[FloatQuad] = []
        for position in sorted(
            unapproved_positions.get(source_id, set()) | pending_positions.get(source_id, set())
        ):
            slot = _slot_geometry(auto.board_geometries, position)
            hint = None if slot is None else hint_quad(slot)
            if slot is None or hint is None:
                continue
            is_pending = position in pending_positions.get(source_id, set())
            boards.append(
                SampleBoard(
                    kind="pending_sample" if is_pending else "validation_sample",
                    width=width,
                    height=height,
                    engine_quad=None if is_pending else engine_quad(slot),
                    position_index=position,
                    sequence_number=(
                        int(cast(int, slot["sequenceNumber"]))
                        if isinstance(slot.get("sequenceNumber"), int)
                        else None
                    ),
                )
            )
            hints.append(hint)
        result.append((source, boards, hints))
    return result, len(chosen)


# --------------------------------------------------------------------------- sources


def load_source_rgb(
    artifact_root: Path, source: SourceImageModel
) -> np.ndarray[Any, np.dtype[np.uint8]]:
    relative = PurePosixPath(source.relative_path)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError("A managed source path is unsafe.")
    root = (artifact_root / "data").resolve()
    path = root.joinpath(*relative.parts).resolve(strict=True)
    if not path.is_relative_to(root):
        raise ValueError("A managed source path escapes artifact storage.")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != source.checksum_sha256:
        raise ValueError("A managed source checksum changed.")
    with Image.open(path) as image:
        image.load()
        rgb = np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)
    width, height = _source_dimensions(source)
    if rgb.shape[:2] != (height, width):
        raise ValueError("A managed source dimension changed.")
    return rgb


# --------------------------------------------------------------------------- sweep


def _percentiles(values: Sequence[float]) -> dict[str, float | None]:
    if not values:
        return {"p50": None, "p90": None, "p99": None, "max": None}
    array = np.asarray(values, dtype=np.float64)
    return {
        "p50": round(float(np.percentile(array, 50)), 3),
        "p90": round(float(np.percentile(array, 90)), 3),
        "p99": round(float(np.percentile(array, 99)), 3),
        "max": round(float(array.max()), 3),
    }


def _observation(board: GoldenBoard | SampleBoard, scale: float) -> VerifierObservation:
    return next(item for item in board.observations if item.hint_scale == scale)


def sweep(
    golden: Sequence[GoldenBoard],
    samples: Sequence[SampleBoard],
) -> list[dict[str, object]]:
    """Every threshold combination with its golden false accepts and sample coverage."""

    rows: list[dict[str, object]] = []
    for scale in HINT_SCALES:
        for tau in TAU_GRID:
            for residual in RESIDUAL_GRID:
                for inliers in INLIER_GRID:
                    thresholds = Thresholds(tau, residual, inliers)
                    rows.append(
                        {
                            "hintScale": scale,
                            **thresholds.to_payload(),
                            **_evaluate(golden, samples, scale, thresholds),
                        }
                    )
    return rows


def _evaluate(
    golden: Sequence[GoldenBoard],
    samples: Sequence[SampleBoard],
    scale: float,
    thresholds: Thresholds,
) -> dict[str, object]:
    validation_false: dict[str, int] = {str(value): 0 for value in HUMAN_ERROR_GRID}
    pending_false: dict[str, int] = {str(value): 0 for value in HUMAN_ERROR_GRID}
    validation_true = 0
    validation_total = 0
    pending_accepted = 0
    pending_total = 0
    for golden_board in golden:
        observation = _observation(golden_board, scale)
        if golden_board.kind == "pending_resolved":
            pending_total += 1
            if verifier_is_confident(
                observation, thresholds, width=golden_board.width, height=golden_board.height
            ):
                pending_accepted += 1
                assert observation.quad is not None
                error = max_corner_distance(observation.quad, golden_board.human_quad)
                for limit in HUMAN_ERROR_GRID:
                    if error > limit:
                        pending_false[str(limit)] += 1
            continue
        assert golden_board.engine_quad is not None
        validation_total += 1
        accepted = validation_board_accepted(
            observation,
            golden_board.engine_quad,
            thresholds,
            width=golden_board.width,
            height=golden_board.height,
        )
        engine_error = golden_board.engine_error_px or 0.0
        if accepted:
            validation_true += 1
            for limit in HUMAN_ERROR_GRID:
                if engine_error > limit:
                    validation_false[str(limit)] += 1
    sample_validation = [item for item in samples if item.kind == "validation_sample"]
    sample_pending = [item for item in samples if item.kind == "pending_sample"]
    sample_validation_accepted = sum(
        1
        for item in sample_validation
        if item.engine_quad is not None
        and validation_board_accepted(
            _observation(item, scale),
            item.engine_quad,
            thresholds,
            width=item.width,
            height=item.height,
        )
    )
    sample_pending_accepted = sum(
        1
        for item in sample_pending
        if verifier_is_confident(
            _observation(item, scale), thresholds, width=item.width, height=item.height
        )
    )
    return {
        "goldenValidationAccepted": validation_true,
        "goldenValidationTotal": validation_total,
        "goldenValidationFalseAcceptsByHumanErrorPx": validation_false,
        "goldenPendingAccepted": pending_accepted,
        "goldenPendingTotal": pending_total,
        "goldenPendingFalseAcceptsByHumanErrorPx": pending_false,
        "sampleValidationCoverage": _ratio(sample_validation_accepted, len(sample_validation)),
        "samplePendingCoverage": _ratio(sample_pending_accepted, len(sample_pending)),
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else round(numerator / denominator, 4)


# --------------------------------------------------------------------------- CLI


def _read_only_engine(engine: Engine) -> Engine:
    @event.listens_for(engine, "connect")
    def _set_read_only(dbapi_connection: Any, _record: object) -> None:
        dbapi_connection.read_only = True

    return engine


def _observation_payload(observation: VerifierObservation) -> dict[str, object]:
    return {
        "elapsedMs": round(observation.elapsed_ms, 2),
        "fallbackReason": observation.fallback_reason,
        "hintScale": observation.hint_scale,
        "inlierCount": observation.inlier_count,
        "p95ResidualPx": observation.p95_residual_px,
        "quad": None if observation.quad is None else [list(point) for point in observation.quad],
        "status": observation.status,
    }


def calibrate(*, game_id: UUID, sample_sources: int, seed: int, output_dir: Path) -> Path:
    settings = get_settings()
    engine = _read_only_engine(create_database_engine(settings))
    session_factory = create_session_factory(engine)
    started = time.perf_counter()
    try:
        with game_storage_scope(game_id), session_factory() as session:
            golden, golden_sources, skipped = load_golden(session)
            sampled, sampled_source_count = load_samples(
                session, sample_sources=sample_sources, seed=seed
            )
            # Keep the loaded rows usable after the read-only session closes.
            session.expunge_all()
    finally:
        engine.dispose()

    source_errors: dict[str, int] = {}
    by_source: dict[UUID, list[GoldenBoard]] = {}
    for board in golden:
        by_source.setdefault(board.source_image_id, []).append(board)
    for source_id, boards in by_source.items():
        try:
            rgb = load_source_rgb(settings.artifact_root, golden_sources[source_id])
        except (OSError, ValueError) as error:
            source_errors[type(error).__name__] = source_errors.get(type(error).__name__, 0) + 1
            for board in boards:
                board.observations = [
                    VerifierObservation(scale, "source_unavailable", None, 0, None, str(error), 0.0)
                    for scale in HINT_SCALES
                ]
            continue
        for board in boards:
            board.observations = [
                run_verifier(rgb, board.hint, hint_scale=scale) for scale in HINT_SCALES
            ]

    samples: list[SampleBoard] = []
    for source, sample_boards, hints in sampled:
        try:
            rgb = load_source_rgb(settings.artifact_root, source)
        except (OSError, ValueError) as error:
            source_errors[type(error).__name__] = source_errors.get(type(error).__name__, 0) + 1
            continue
        for sample_board, hint in zip(sample_boards, hints, strict=True):
            sample_board.observations = [
                run_verifier(rgb, hint, hint_scale=scale) for scale in HINT_SCALES
            ]
            samples.append(sample_board)

    elapsed = [
        observation.elapsed_ms
        for observations in (
            *(item.observations for item in golden),
            *(item.observations for item in samples),
        )
        for observation in observations
        if observation.status != "source_unavailable"
    ]
    counts: dict[str, int] = {}
    for board in golden:
        counts[board.kind] = counts.get(board.kind, 0) + 1
    report: dict[str, object] = {
        "reportVersion": REPORT_VERSION,
        "generatedAt": datetime.now(UTC).isoformat(),
        "gameId": str(game_id),
        "verifier": "board_cell_geometry_estimator.estimate_board_cell_geometry",
        "hintScales": list(HINT_SCALES),
        "golden": {
            "counts": counts,
            "skipped": skipped,
            "engineErrorPxHumanRevised": _percentiles(
                [
                    board.engine_error_px
                    for board in golden
                    if board.kind == "human_revised" and board.engine_error_px is not None
                ]
            ),
            "boards": [
                {
                    "kind": board.kind,
                    "recognizedBoardId": str(board.recognized_board_id),
                    "sourceImageId": str(board.source_image_id),
                    "sequenceNumber": board.sequence_number,
                    "positionIndex": board.position_index,
                    "engineErrorPx": (
                        None if board.engine_error_px is None else round(board.engine_error_px, 3)
                    ),
                    "observations": [
                        {
                            **_observation_payload(observation),
                            "verifierVsEnginePx": (
                                None
                                if observation.quad is None or board.engine_quad is None
                                else round(
                                    max_corner_distance(observation.quad, board.engine_quad), 3
                                )
                            ),
                            "verifierVsHumanPx": (
                                None
                                if observation.quad is None
                                else round(
                                    max_corner_distance(observation.quad, board.human_quad), 3
                                )
                            ),
                        }
                        for observation in board.observations
                    ],
                }
                for board in golden
            ],
        },
        "sample": {
            "seed": seed,
            "sampledSources": sampled_source_count,
            "validationBoards": sum(1 for item in samples if item.kind == "validation_sample"),
            "pendingSlots": sum(1 for item in samples if item.kind == "pending_sample"),
        },
        "sourceErrors": source_errors,
        "verifierElapsedMs": _percentiles(elapsed),
        "sweep": sweep(golden, samples),
        "wallClockSeconds": round(time.perf_counter() - started, 1),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"calibration-{stamp}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _lattice_point(quad: FloatQuad, u: float, v: float) -> tuple[float, float]:
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = quad
    top = (x0 + (x1 - x0) * u, y0 + (y1 - y0) * u)
    bottom = (x3 + (x2 - x3) * u, y3 + (y2 - y3) * u)
    return top[0] + (bottom[0] - top[0]) * v, top[1] + (bottom[1] - top[1]) * v


def _board_tile(
    rgb: np.ndarray[Any, np.dtype[np.uint8]], quad: FloatQuad, *, tile_width: int = 420
) -> Image.Image:
    """Crop around the engine quad and draw its 5 x 3 symbol lattice."""

    from PIL import ImageDraw

    xs = [point[0] for point in quad]
    ys = [point[1] for point in quad]
    pad_x = (max(xs) - min(xs)) * 0.18
    pad_y = (max(ys) - min(ys)) * 0.25
    left = max(int(min(xs) - pad_x), 0)
    top = max(int(min(ys) - pad_y), 0)
    right = min(int(max(xs) + pad_x), rgb.shape[1] - 1)
    bottom = min(int(max(ys) + pad_y), rgb.shape[0] - 1)
    crop = Image.fromarray(rgb[top : bottom + 1, left : right + 1])
    scale = tile_width / max(crop.width, 1)
    crop = crop.resize((tile_width, max(int(crop.height * scale), 1)), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(crop)

    def point(u: float, v: float) -> tuple[float, float]:
        x, y = _lattice_point(quad, u, v)
        return (x - left) * scale, (y - top) * scale

    for column in range(6):
        u = column / 5
        draw.line([point(u, 0.0), point(u, 1.0)], fill=(0, 255, 80), width=2)
    for row in range(4):
        v = row / 3
        draw.line([point(0.0, v), point(1.0, v)], fill=(0, 255, 80), width=2)
    return crop


def _instability(board: SampleBoard) -> float:
    """Worst engine disagreement of the perturbed-hint verifier runs (inf when it fails)."""

    assert board.engine_quad is not None
    worst = 0.0
    for observation in board.observations:
        if observation.hint_scale == 1.0:
            continue
        if observation.status != "estimated" or observation.quad is None:
            return math.inf
        worst = max(worst, max_corner_distance(observation.quad, board.engine_quad))
    return worst


def review_sheet(
    *,
    game_id: UUID,
    sample_sources: int,
    seed: int,
    unstable_count: int,
    stable_count: int,
    unstable_px: float,
    stable_px: float,
    output_dir: Path,
) -> Path:
    """Blind visual sheet of engine grids: unstable and stable boards, shuffled."""

    import base64
    import html
    import io

    settings = get_settings()
    engine = _read_only_engine(create_database_engine(settings))
    session_factory = create_session_factory(engine)
    try:
        with game_storage_scope(game_id), session_factory() as session:
            sampled, _count = load_samples(session, sample_sources=sample_sources, seed=seed)
            session.expunge_all()
    finally:
        engine.dispose()

    candidates: list[tuple[SourceImageModel, SampleBoard, float]] = []
    for source, sample_boards, hints in sampled:
        try:
            rgb = load_source_rgb(settings.artifact_root, source)
        except (OSError, ValueError):
            continue
        for sample_board, hint in zip(sample_boards, hints, strict=True):
            if sample_board.kind != "validation_sample" or sample_board.engine_quad is None:
                continue
            sample_board.observations = [
                run_verifier(rgb, hint, hint_scale=scale) for scale in HINT_SCALES
            ]
            candidates.append((source, sample_board, _instability(sample_board)))

    rng = random.Random(seed)
    unstable = [item for item in candidates if item[2] > unstable_px]
    stable = [item for item in candidates if item[2] <= stable_px]
    # Half verifier failures, half the largest finite disagreements: both are
    # "unstable", but they fail for different reasons and must both be seen.
    failed = [item for item in unstable if math.isinf(item[2])]
    diverging = sorted(
        (item for item in unstable if not math.isinf(item[2])), key=lambda item: -item[2]
    )
    failed_share = min(len(failed), unstable_count // 2)
    picked = rng.sample(failed, failed_share)
    picked += diverging[: unstable_count - failed_share]
    chosen = [(*item, "unstable") for item in picked]
    chosen += [(*item, "stable") for item in rng.sample(stable, min(stable_count, len(stable)))]
    rng.shuffle(chosen)

    tiles: list[str] = []
    key: list[dict[str, object]] = []
    for number, (source, sample_board, instability, group) in enumerate(chosen, start=1):
        assert sample_board.engine_quad is not None
        rgb = load_source_rgb(settings.artifact_root, source)
        buffer = io.BytesIO()
        _board_tile(rgb, sample_board.engine_quad).save(buffer, format="JPEG", quality=88)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        label = (
            f"#{number} · sekwencja {sample_board.sequence_number} · "
            f"plansza {sample_board.position_index + 1}"
        )
        tiles.append(
            f'<figure><img src="data:image/jpeg;base64,{encoded}" alt="{html.escape(label)}">'
            f"<figcaption>{html.escape(label)}</figcaption></figure>"
        )
        key.append(
            {
                "number": number,
                "group": group,
                "instabilityPx": None if math.isinf(instability) else round(instability, 3),
                "verifierFailed": math.isinf(instability),
                "sourceImageId": str(source.id),
                "importJobId": str(source.import_job_id),
                "sequenceNumber": sample_board.sequence_number,
                "positionIndex": sample_board.position_index,
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    page = output_dir / f"review-sheet-{stamp}.html"
    page.write_text(
        "<!doctype html><html lang='pl'><head><meta charset='utf-8'>"
        "<title>Siatki 777 – ocena</title><style>"
        "body{font-family:system-ui,sans-serif;margin:16px;background:#111;color:#eee}"
        "main{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:16px}"
        "figure{margin:0}img{width:100%;display:block}"
        "figcaption{padding:4px 0;font-size:14px}</style></head><body>"
        f"<h1>Siatki silnika 777 — {len(tiles)} plansz</h1>"
        "<p>Zielona siatka 5 × 3 to geometria, która zostałaby zatwierdzona. "
        "Zapisz numery (#) plansz, na których siatka NIE pokrywa poprawnie symboli.</p>"
        f"<main>{''.join(tiles)}</main></body></html>",
        encoding="utf-8",
    )
    key_path = output_dir / f"review-sheet-{stamp}.key.json"
    key_path.write_text(
        json.dumps(
            {
                "candidates": len(candidates),
                "unstableAvailable": len(unstable),
                "stableAvailable": len(stable),
                "unstablePx": unstable_px,
                "stablePx": stable_px,
                "tiles": key,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return page


def _sample_source_ids(session: Session, *, per_category: int, seed: int) -> dict[str, list[UUID]]:
    """Deterministic source sample: sources with pending slots vs. validation-only sources."""

    pending = set(
        session.scalars(
            select(ImageBoardGeometryPendingModel.source_image_id)
            .where(ImageBoardGeometryPendingModel.status == "pending")
            .distinct()
        ).all()
    )
    validation = set(
        session.scalars(
            select(RecognizedBoardModel.source_image_id)
            .where(
                RecognizedBoardModel.asset_mode == "virtual_source",
                RecognizedBoardModel.approved_geometry_revision.is_(None),
                RecognizedBoardModel.geometry_revision == 0,
            )
            .distinct()
        ).all()
    )
    rng = random.Random(seed)
    only_validation = sorted(validation - pending, key=str)
    with_pending = sorted(pending, key=str)
    return {
        "do_poprawy": rng.sample(with_pending, min(per_category, len(with_pending))),
        "do_walidacji": rng.sample(only_validation, min(per_category, len(only_validation))),
    }


def v3_sample(*, game_id: UUID, per_category: int, seed: int, output_dir: Path) -> Path:
    """Read-only: run the proposed v3 engine on sampled 777 sources and draw both grids."""

    import html

    import cv2
    from game_predictor_worker.images.screen_layout_v3 import BoardStatus, detect_screen_layout_v3

    settings = get_settings()
    engine = _read_only_engine(create_database_engine(settings))
    session_factory = create_session_factory(engine)
    try:
        with game_storage_scope(game_id), session_factory() as session:
            categories = _sample_source_ids(session, per_category=per_category, seed=seed)
            all_ids = [sid for ids in categories.values() for sid in ids]
            sources = {
                s.id: s
                for s in session.scalars(
                    select(SourceImageModel).where(SourceImageModel.id.in_(all_ids))
                ).all()
            }
            autos = _auto_revisions(session, all_ids)
            pending_positions: dict[UUID, set[int]] = {}
            for source_id, position in session.execute(
                select(
                    ImageBoardGeometryPendingModel.source_image_id,
                    ImageBoardGeometryPendingModel.position_index,
                ).where(
                    ImageBoardGeometryPendingModel.status == "pending",
                    ImageBoardGeometryPendingModel.source_image_id.in_(all_ids),
                )
            ).all():
                pending_positions.setdefault(source_id, set()).add(int(position))
            session.expunge_all()
    finally:
        engine.dispose()

    colours = {
        BoardStatus.COMPLETE: (0, 220, 0),
        BoardStatus.PARTIAL: (0, 220, 255),
        BoardStatus.NEEDS_REVIEW: (0, 0, 255),
    }
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = output_dir / f"v3-sample-{stamp}"
    target.mkdir(parents=True, exist_ok=True)
    report: list[dict[str, object]] = []
    sections: list[str] = []
    labels = {"do_poprawy": "Do poprawy", "do_walidacji": "Do walidacji"}
    number = 0
    for category, ids in categories.items():
        figures: list[str] = []
        for source_id in ids:
            number += 1
            source = sources[source_id]
            auto = autos.get(source_id)
            try:
                rgb = load_source_rgb(settings.artifact_root, source)
            except (OSError, ValueError) as error:
                report.append({"sourceImageId": str(source_id), "error": str(error)})
                continue
            result = detect_screen_layout_v3(rgb)
            canvas = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            thickness = max(2, rgb.shape[1] // 700)
            pending = pending_positions.get(source_id, set())
            boards_payload: list[dict[str, object]] = []
            for position in range(9):
                slot = None if auto is None else _slot_geometry(auto.board_geometries, position)
                old = None if slot is None else engine_quad(slot)
                if old is not None:
                    pts = np.array(old, dtype=np.int32)
                    cv2.polylines(canvas, [pts], True, (255, 160, 0), thickness)  # old engine: blue
            for board in result.boards:
                colour = colours[board.status]
                points = board.points
                for row in range(points.shape[0]):
                    cv2.polylines(canvas, [points[row].astype(np.int32)], False, colour, thickness)
                for col in range(points.shape[1]):
                    cv2.polylines(
                        canvas, [points[:, col].astype(np.int32)], False, colour, thickness
                    )
                slot = (
                    None
                    if auto is None
                    else _slot_geometry(auto.board_geometries, board.position_index)
                )
                old = None if slot is None else engine_quad(slot)
                v3_quad = cast(FloatQuad, tuple((float(x), float(y)) for x, y in board.quad))
                diff = None if old is None else round(max_corner_distance(old, v3_quad), 1)
                tag = f"{board.position_index + 1}{' P' if board.position_index in pending else ''}"
                at = board.quad[0].astype(int)
                cv2.putText(
                    canvas,
                    tag,
                    (int(at[0]) + 4, int(at[1]) - 6),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.9,
                    colour,
                    thickness,
                )
                boards_payload.append(
                    {
                        "positionIndex": board.position_index,
                        "pendingSlot": board.position_index in pending,
                        "v3Status": board.status.value,
                        "v3Reasons": list(board.reason_codes),
                        "v3VsEngineMaxCornerPx": diff,
                    }
                )
            if canvas.shape[1] > 1400:
                scale = 1400 / canvas.shape[1]
                canvas = cv2.resize(canvas, (1400, int(canvas.shape[0] * scale)))
            name = f"{number:03d}.jpg"
            cv2.imwrite(str(target / name), canvas, [cv2.IMWRITE_JPEG_QUALITY, 88])
            counts = {s: sum(1 for b in result.boards if b.status is s) for s in BoardStatus}
            caption = html.escape(
                f"#{number} · {source.relative_path.rsplit('/', 1)[-1]} · sloty bez siatki: "
                f"{', '.join(str(p + 1) for p in sorted(pending)) or '—'} · v3: pełne "
                f"{counts[BoardStatus.COMPLETE]}, częściowe {counts[BoardStatus.PARTIAL]}, "
                f"do poprawy {counts[BoardStatus.NEEDS_REVIEW]}"
            )
            figures.append(
                f'<figure><img src="{name}" alt=""><figcaption>{caption}</figcaption></figure>'
            )
            report.append(
                {
                    "number": number,
                    "category": category,
                    "sourceImageId": str(source_id),
                    "importJobId": str(source.import_job_id),
                    "relativePath": source.relative_path,
                    "v3Status": result.status.value,
                    "v3Reason": result.reason_code,
                    "boards": boards_payload,
                }
            )
            print(caption.replace("·", "|"), flush=True)
        sections.append(
            f"<h2>{labels[category]} ({len(figures)})</h2><main>{''.join(figures)}</main>"
        )
    (target / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    page = target / "index.html"
    page.write_text(
        "<!doctype html><html lang='pl'><head><meta charset='utf-8'><title>777 — silnik v3</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:16px;background:#111;color:#eee}"
        "main{display:grid;grid-template-columns:repeat(auto-fill,minmax(640px,1fr));gap:18px}"
        "figure{margin:0}img{width:100%;display:block}"
        "figcaption{font-size:14px;padding:4px 0}</style></head><body>"
        "<h1>Gra 777 — silnik v3 na próbce kolejek (podgląd, bez zapisu)</h1>"
        "<p>Niebieska ramka: obecna siatka silnika 777 (brak ramki = slot bez siatki). "
        "Siatka v3: zielona = pewna, czerwona = do poprawy, żółta = częściowa. "
        "Etykieta „P” = slot, który dziś jest w „Do poprawy”.</p>"
        f"{''.join(sections)}</body></html>",
        encoding="utf-8",
    )
    return page


# --------------------------------------------------------------------------- hybrid

HYBRID_ASPECT = 0.55  # fixed gauge: the homography absorbs the vertical scale
HYBRID_MIN_NEIGHBOURS = 5
HYBRID_TILE = 240
HYBRID_MARGIN = 0.15


def _hybrid_canonical(params: np.ndarray[Any, np.dtype[np.float64]], cell: tuple[int, int]) -> Any:
    column, row = cell
    u = np.array([0.0, 1.0, 1.0, 0.0])
    v = np.array([0.0, 0.0, 1.0, 1.0])
    return np.column_stack([column * params[8] + u, (row * params[9] + v) * HYBRID_ASPECT])


def fit_board_layout(
    boards: Mapping[int, FloatQuad], shape: tuple[int, int], *, radial: bool = True
) -> tuple[np.ndarray[Any, np.dtype[np.float64]], np.ndarray[Any, np.dtype[np.float64]], float]:
    """Screen model (homography + pitches [+ radial term]) fitted to known symbol-grid quads.

    Without the radial term the model extrapolates linearly, which is safer for a
    board outside the columns (or rows) covered by the known boards.
    """

    from game_predictor_worker.images.screen_layout_v3.layout import levenberg_marquardt, project

    height, width = shape
    center = np.array([width / 2, height / 2], dtype=np.float64)
    scale = float(np.hypot(width, height)) / 2
    cells = {p: (p % 3, p // 3) for p in boards}
    observed = np.array([boards[p] for p in boards], dtype=np.float64).reshape(-1, 2)

    def canonical(params: np.ndarray[Any, np.dtype[np.float64]]) -> Any:
        return np.vstack([_hybrid_canonical(params, cells[p]) for p in boards])

    start = np.zeros(12)
    start[8:11] = [1.3, 1.6, HYBRID_ASPECT]
    homography, _ = cv2_find_homography(canonical(start), observed)
    start[:8] = (homography / homography[2, 2]).ravel()[:8]

    def residual(p11: np.ndarray[Any, np.dtype[np.float64]]) -> Any:
        k1 = p11[10:11] if radial else np.zeros(1)
        params = np.concatenate([p11[:10], [HYBRID_ASPECT], k1])
        return (project(params, canonical(params), center, scale) - observed).ravel()

    p11 = levenberg_marquardt(residual, np.concatenate([start[:10], start[11:12]]), 80)
    k1 = p11[10:11] if radial else np.zeros(1)
    return np.concatenate([p11[:10], [HYBRID_ASPECT], k1]), center, scale


def cv2_find_homography(source: Any, target: Any) -> tuple[Any, Any]:
    import cv2

    homography, mask = cv2.findHomography(source.astype(np.float32), target.astype(np.float32))
    if homography is None:
        homography = np.eye(3)
    return homography, mask


def is_extrapolated(boards: Mapping[int, FloatQuad], position: int) -> bool:
    """True when no known board shares the target's column or none shares its row."""

    column, row = position % 3, position // 3
    return not any(p % 3 == column for p in boards) or not any(p // 3 == row for p in boards)


def predict_board(
    boards: Mapping[int, FloatQuad],
    position: int,
    shape: tuple[int, int],
    *,
    radial: bool | None = None,
) -> FloatQuad:
    from game_predictor_worker.images.screen_layout_v3.layout import project

    use_radial = True if radial is None else radial
    params, center, scale = fit_board_layout(boards, shape, radial=use_radial)
    quad = project(params, _hybrid_canonical(params, (position % 3, position // 3)), center, scale)
    return cast(FloatQuad, tuple((float(x), float(y)) for x, y in quad))


def _unit_homography(quad: FloatQuad) -> Any:
    import cv2

    tile = HYBRID_TILE
    th = int(round(tile * HYBRID_ASPECT))
    m = HYBRID_MARGIN
    unit = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)
    pixel = unit * np.array([tile, th], np.float32) + np.array([m * tile, m * th], np.float32)
    return (
        cv2.getPerspectiveTransform(pixel, np.array(quad, dtype=np.float32)),
        (
            int(tile * (1 + 2 * m)),
            int(th * (1 + 2 * m)),
        ),
        pixel,
    )


def _rectify_board(gray: Any, quad: FloatQuad) -> Any:
    import cv2

    matrix, size, _ = _unit_homography(quad)
    return cv2.warpPerspective(
        gray, matrix, size, flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderValue=0
    )


ARROW_BAND = 0.22  # fraction of the board width covered by the "<" / ">" arrow
ARROW_SIDE = {3: "left", 5: "right"}  # middle-row edge boards of the 3 x 3 screen
ARROW_TAU_CELL = 0.1  # the arrow can drag one corner of the engine grid
REPAIR_MIN_ECC = 0.8


def _draw_lattice(canvas: Any, quad: FloatQuad, colour: tuple[int, int, int], thick: int) -> None:
    import cv2

    for k in range(6):
        a = _lattice_point(quad, k / 5, 0.0)
        b = _lattice_point(quad, k / 5, 1.0)
        cv2.line(canvas, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), colour, thick)
    for k in range(4):
        a = _lattice_point(quad, 0.0, k / 3)
        b = _lattice_point(quad, 1.0, k / 3)
        cv2.line(canvas, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), colour, thick)


def _refine_mask(shape: tuple[int, ...], position: int | None) -> Any:
    """ECC input mask; the arrow band of boards 4 and 6 is excluded."""

    height, width = shape[:2]
    mask = np.full((height, width), 255, np.uint8)
    side = ARROW_SIDE.get(position) if position is not None else None
    if side is None:
        return mask
    m = HYBRID_MARGIN
    board_w = width / (1 + 2 * m)
    x_left = width * m / (1 + 2 * m)
    band = int(board_w * ARROW_BAND + x_left)
    if side == "left":
        mask[:, :band] = 0
    else:
        mask[:, width - band :] = 0
    return mask


SEARCH_MARGIN = 0.5  # search window around the predicted board, in board sizes
SEARCH_SCALES = (0.95, 1.0, 1.05)
AMBIGUITY_MARGIN = 0.05  # a second peak this close in score, >= 0.5 cell away -> ambiguous


def _rectify_with_margin(gray: Any, quad: FloatQuad, margin: float) -> tuple[Any, Any]:
    import cv2

    tile = HYBRID_TILE
    th = int(round(tile * HYBRID_ASPECT))
    unit = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)
    pixel = unit * np.array([tile, th], np.float32) + np.array(
        [margin * tile, margin * th], np.float32
    )
    matrix = cv2.getPerspectiveTransform(pixel, np.array(quad, dtype=np.float32))
    size = (int(tile * (1 + 2 * margin)), int(th * (1 + 2 * margin)))
    image = cv2.warpPerspective(
        gray, matrix, size, flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderValue=0
    )
    return image.astype(np.float32), matrix


MAX_ROTATION_DEG = 3.0
MAX_ASPECT_CHANGE = 0.08


def _edge_angles_and_aspect(quad: FloatQuad) -> tuple[float, float, float]:
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = quad
    top = math.degrees(math.atan2(y1 - y0, x1 - x0))
    left = math.degrees(math.atan2(x0 - x3, y3 - y0))
    width = (math.dist(quad[0], quad[1]) + math.dist(quad[3], quad[2])) / 2
    height = (math.dist(quad[0], quad[3]) + math.dist(quad[1], quad[2])) / 2
    return top, left, width / max(height, 1e-9)


def shape_consistent(quad: FloatQuad, model_quad: FloatQuad) -> bool:
    """The grid keeps the neighbours' angles and proportions (rotation, skew, aspect)."""

    top, left, aspect = _edge_angles_and_aspect(quad)
    m_top, m_left, m_aspect = _edge_angles_and_aspect(model_quad)
    return (
        abs(top - m_top) <= MAX_ROTATION_DEG
        and abs(left - m_left) <= MAX_ROTATION_DEG
        and abs(aspect / m_aspect - 1) <= MAX_ASPECT_CHANGE
    )


def place_board(
    gray: Any, neighbours: Sequence[FloatQuad], predicted: FloatQuad
) -> tuple[FloatQuad, float, bool]:
    """Shape from the screen model; search only translation and +-5% scale.

    Returns the placed quad, the best normalized correlation and whether a
    clearly different placement (>= 0.5 cell away) scores almost as well.
    """

    import cv2

    tile = HYBRID_TILE
    th = int(round(tile * HYBRID_ASPECT))
    m = HYBRID_MARGIN
    template = np.median(
        np.stack([_rectify_with_margin(gray, q, m)[0] for q in neighbours]), axis=0
    ).astype(np.float32)
    template = cv2.GaussianBlur(template, (0, 0), 1.5)
    search, matrix = _rectify_with_margin(gray, predicted, SEARCH_MARGIN)
    search = cv2.GaussianBlur(search, (0, 0), 1.5)
    peaks: list[tuple[float, float, float, float]] = []  # score, x_board, y_board, scale
    for scale in SEARCH_SCALES:
        scaled = cv2.resize(template, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        response = cv2.matchTemplate(search, scaled, cv2.TM_CCOEFF_NORMED)
        for _ in range(4):
            _, value, _, (x, y) = cv2.minMaxLoc(response)
            peaks.append((float(value), x + m * tile * scale, y + m * th * scale, scale))
            rx, ry = int(tile * scale / 10), int(th * scale / 6)
            response[max(y - ry, 0) : y + ry + 1, max(x - rx, 0) : x + rx + 1] = -1
    peaks.sort(reverse=True)
    best = peaks[0]
    cell_w, cell_h = tile / 5, th / 3
    ambiguous = any(
        other[0] >= best[0] - AMBIGUITY_MARGIN
        and max(abs(other[1] - best[1]) / cell_w, abs(other[2] - best[2]) / cell_h) >= 0.5
        for other in peaks[1:]
    )
    _, bx, by, scale = best
    unit = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float64)
    in_search = unit * np.array([tile * scale, th * scale]) + np.array([bx, by])
    corners = cv2.perspectiveTransform(in_search.reshape(-1, 1, 2), matrix).reshape(-1, 2)
    return cast(FloatQuad, tuple((float(x), float(y)) for x, y in corners)), best[0], ambiguous


REFINE_SCALES = (0.97, 1.0, 1.03)
HALF_MAX_OFFSET_CELL = 0.35  # a half-board offset beyond this means a row jump on one side


def _neighbour_template(gray: Any, neighbours: Sequence[FloatQuad]) -> Any:
    import cv2

    template = np.median(
        np.stack([_rectify_board(gray, q).astype(np.float32) for q in neighbours]), axis=0
    ).astype(np.float32)
    return cv2.GaussianBlur(template, (0, 0), 1.5)


def refine_board(
    gray: Any,
    neighbours: Sequence[FloatQuad],
    predicted: FloatQuad,
    position: int | None = None,
) -> tuple[FloatQuad, float]:
    """Align the predicted board to the median of its neighbours.

    Shape (proportions, skew, perspective) comes from the screen model of the
    neighbours; the correction is only translation, a small rotation and one
    common scale. Without shear or per-axis scale one side of the grid cannot
    jump a row relative to the other.
    """

    import cv2

    template = _neighbour_template(gray, neighbours)
    best: tuple[float, FloatQuad] | None = None
    for scale in REFINE_SCALES:
        start = scale_quad(predicted, scale)
        tile = cv2.GaussianBlur(_rectify_board(gray, start).astype(np.float32), (0, 0), 1.5)
        warp = np.eye(2, 3, dtype=np.float32)
        try:
            correlation, found = cv2.findTransformECC(
                template,
                tile,
                warp,
                cv2.MOTION_EUCLIDEAN,
                (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-6),
                _refine_mask(tile.shape, position),
                3,
            )
        except cv2.error:
            continue
        affine = np.vstack([np.asarray(found, np.float64), [0.0, 0.0, 1.0]])
        matrix, _size, pixel = _unit_homography(start)
        corners_in_tile = cv2.perspectiveTransform(pixel.reshape(-1, 1, 2), affine)
        corners = cv2.perspectiveTransform(corners_in_tile, matrix).reshape(-1, 2)
        quad = cast(FloatQuad, tuple((float(x), float(y)) for x, y in corners))
        if best is None or float(correlation) > best[0]:
            best = (float(correlation), quad)
    if best is None:
        return predicted, 0.0
    return best[1], best[0]


def refine_board_affine(
    gray: Any,
    neighbours: Sequence[FloatQuad],
    predicted: FloatQuad,
    position: int | None = None,
) -> tuple[FloatQuad, float]:
    """Precise affine alignment used only to *check* an existing engine grid.

    It follows local detail better than the rigid refinement (median 0.07 cell on
    known boards) but may shear on occluded boards, so its result is never
    written; new grids come from ``refine_board``.
    """

    import cv2

    template = _neighbour_template(gray, neighbours)
    tile = cv2.GaussianBlur(_rectify_board(gray, predicted).astype(np.float32), (0, 0), 1.5)
    warp = np.eye(2, 3, dtype=np.float32)
    try:
        correlation, found = cv2.findTransformECC(
            template,
            tile,
            warp,
            cv2.MOTION_AFFINE,
            (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-6),
            _refine_mask(tile.shape, position),
            3,
        )
    except cv2.error:
        return predicted, 0.0
    matrix3 = np.vstack([np.asarray(found, np.float64), [0.0, 0.0, 1.0]])
    matrix, _size, pixel = _unit_homography(predicted)
    corners_in_tile = cv2.perspectiveTransform(pixel.reshape(-1, 1, 2), matrix3)
    corners = cv2.perspectiveTransform(corners_in_tile, matrix).reshape(-1, 2)
    return cast(FloatQuad, tuple((float(x), float(y)) for x, y in corners)), float(correlation)


def halves_consistent(
    gray: Any, neighbours: Sequence[FloatQuad], quad: FloatQuad, position: int | None = None
) -> tuple[bool, float, float]:
    """Align the left and right half separately (translation only).

    A grid whose one side sits a row off shows a vertical offset on that half.
    Returns (consistent, left dy, right dy) with offsets in cell heights.
    """

    import cv2

    template = _neighbour_template(gray, neighbours)
    tile = cv2.GaussianBlur(_rectify_board(gray, quad).astype(np.float32), (0, 0), 1.5)
    height, width = tile.shape[:2]
    m = HYBRID_MARGIN
    x0 = width * m / (1 + 2 * m)
    board_w = width / (1 + 2 * m)
    cell_h = height / (1 + 2 * m) / 3
    base = _refine_mask(tile.shape, position)
    offsets: list[float] = []
    for left, right in ((0.0, x0 + board_w / 2), (x0 + board_w / 2, float(width))):
        mask = base.copy()
        mask[:, : int(left)] = 0
        mask[:, int(right) :] = 0
        warp = np.eye(2, 3, dtype=np.float32)
        try:
            _c, found = cv2.findTransformECC(
                template,
                tile,
                warp,
                cv2.MOTION_TRANSLATION,
                (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-5),
                mask,
                3,
            )
        except cv2.error:
            return False, math.nan, math.nan
        offsets.append(float(np.asarray(found)[1, 2]) / cell_h)
    dy_left, dy_right = offsets
    consistent = (
        abs(dy_left) <= HALF_MAX_OFFSET_CELL
        and abs(dy_right) <= HALF_MAX_OFFSET_CELL
        and abs(dy_left - dy_right) <= HALF_MAX_OFFSET_CELL
    )
    return consistent, dy_left, dy_right


def _cell_width(quad: FloatQuad) -> float:
    return (math.dist(quad[0], quad[1]) + math.dist(quad[3], quad[2])) / 2 / 5


DECISION_STYLE: dict[str, tuple[tuple[int, int, int], str]] = {
    "pewna": ((0, 200, 0), "OK"),
    "niezgodna": ((0, 0, 255), "BLOK"),
    "poprawiona": ((0, 165, 255), "POPR."),
    "uzupelniona_pewna": ((255, 0, 255), "NOWA"),
    "uzupelniona_niepewna": ((0, 0, 255), "NOWA?"),
    "za_malo_sasiadow": ((255, 160, 0), "?"),
}


def _draw_decisions(
    canvas: Any,
    decisions: Mapping[int, Mapping[str, object]],
    *,
    include_confirmed: bool,
    skip_positions: set[int] | None = None,
) -> None:
    """Full 5 x 3 lattice with thin lines for every drawn board, labelled pl.N TAG."""

    import cv2

    thin = max(1, canvas.shape[1] // 1400)
    for position, decision in sorted(decisions.items()):
        if skip_positions and position in skip_positions:
            continue
        verdict = str(decision.get("decision"))
        if verdict == "pewna" and not include_confirmed:
            continue
        raw = decision.get("quad")
        if raw is None or verdict not in DECISION_STYLE:
            continue
        colour, tag = DECISION_STYLE[verdict]
        quad = cast(FloatQuad, tuple(tuple(point) for point in cast(list[Any], raw)))
        _draw_lattice(canvas, quad, colour, thin)
        cv2.putText(
            canvas,
            f"pl.{position + 1} {tag}",
            (int(quad[0][0]), int(quad[0][1]) - 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6 + 0.2 * thin,
            colour,
            thin + 1,
        )


def _encode_preview(canvas: Any, width: int = 1100) -> str:
    import base64

    import cv2

    if canvas.shape[1] > width:
        canvas = cv2.resize(
            canvas,
            (width, int(canvas.shape[0] * width / canvas.shape[1])),
            interpolation=cv2.INTER_AREA,
        )
    _ok, buffer = cv2.imencode(".jpg", canvas, [cv2.IMWRITE_JPEG_QUALITY, 82])
    return base64.b64encode(buffer.tobytes()).decode("ascii")


def hybrid_sample(
    *,
    game_id: UUID,
    per_category: int,
    seed: int,
    output_dir: Path,
    tau_cell: float,
    min_ecc: float,
    only_pending: bool = False,
) -> Path:
    """Read-only 777 hybrid: engine grids + leave-one-out screen consensus + slot fill."""

    import html

    import cv2

    settings = get_settings()
    engine = _read_only_engine(create_database_engine(settings))
    session_factory = create_session_factory(engine)
    try:
        with game_storage_scope(game_id), session_factory() as session:
            categories = _sample_source_ids(session, per_category=per_category, seed=seed)
            if only_pending:
                categories = {"do_poprawy": categories["do_poprawy"]}
            all_ids = [sid for ids in categories.values() for sid in ids]
            sources = {
                s.id: s
                for s in session.scalars(
                    select(SourceImageModel).where(SourceImageModel.id.in_(all_ids))
                ).all()
            }
            autos = _auto_revisions(session, all_ids)
            pending_positions: dict[UUID, set[int]] = {}
            for source_id, position in session.execute(
                select(
                    ImageBoardGeometryPendingModel.source_image_id,
                    ImageBoardGeometryPendingModel.position_index,
                ).where(
                    ImageBoardGeometryPendingModel.status == "pending",
                    ImageBoardGeometryPendingModel.source_image_id.in_(all_ids),
                )
            ).all():
                pending_positions.setdefault(source_id, set()).add(int(position))
            session.expunge_all()
    finally:
        engine.dispose()

    report: list[dict[str, object]] = []
    sections: list[str] = []
    labels = {"do_poprawy": "Do poprawy", "do_walidacji": "Do walidacji"}
    loo_errors: list[float] = []
    fill_errors: list[float] = []
    number = 0
    for category, ids in categories.items():
        figures: list[str] = []
        for source_id in ids:
            number += 1
            source = sources[source_id]
            auto = autos.get(source_id)
            pending = pending_positions.get(source_id, set())
            rgb = load_source_rgb(settings.artifact_root, source)
            height, width = rgb.shape[:2]
            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            known: dict[int, FloatQuad] = {}
            for position in range(9):
                slot = None if auto is None else _slot_geometry(auto.board_geometries, position)
                quad = None if slot is None else engine_quad(slot)
                if quad is not None and position not in pending:
                    known[position] = quad
            decisions = _evaluate_source(
                gray, (height, width), known, pending, tau_cell=tau_cell, min_ecc=min_ecc
            )
            boards_payload: list[dict[str, object]] = []
            for position in range(9):
                entry: dict[str, object] = {
                    "positionIndex": position,
                    "pendingSlot": position in pending,
                    **decisions[position],
                }
                if "deviationCell" in entry:
                    loo_errors.append(float(cast(float, entry["deviationCell"])))
                boards_payload.append(entry)
            canvas = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            _draw_decisions(canvas, decisions, include_confirmed=True)
            # Accuracy estimate of the slot-fill path on boards with a known engine grid.
            for position in list(known)[:3]:
                others = {p: q for p, q in known.items() if p != position}
                if len(others) >= HYBRID_MIN_NEIGHBOURS:
                    refined, _c = refine_board(
                        gray,
                        list(others.values()),
                        predict_board(others, position, (height, width)),
                        position,
                    )
                    fill_errors.append(
                        max_corner_distance(refined, known[position]) / _cell_width(known[position])
                    )
            data = _encode_preview(canvas)
            verdicts = [str(b.get("decision")) for b in boards_payload]
            slots = ", ".join(str(p + 1) for p in sorted(pending)) or "—"
            caption = html.escape(
                f"#{number} · sloty bez siatki: {slots}"
                f" · pewne {verdicts.count('pewna')}, poprawione {verdicts.count('poprawiona')},"
                f" niezgodne {verdicts.count('niezgodna')},"
                f" uzupełnione pewne {verdicts.count('uzupelniona_pewna')},"
                f" uzupełnione niepewne {verdicts.count('uzupelniona_niepewna')}"
            )
            figures.append(
                f'<figure><img src="data:image/jpeg;base64,{data}" alt="">'
                f"<figcaption>{caption}</figcaption></figure>"
            )
            report.append(
                {
                    "number": number,
                    "category": category,
                    "sourceImageId": str(source_id),
                    "boards": boards_payload,
                }
            )
            print(caption.replace("·", "|"), flush=True)
        sections.append(
            f"<h2>{labels[category]} ({len(figures)})</h2><main>{''.join(figures)}</main>"
        )

    def pct(values: list[float]) -> str:
        if not values:
            return "—"
        a = np.asarray(values)
        return (
            ", ".join(f"p{q}={np.percentile(a, q):.2f}" for q in (50, 90, 99))
            + f", max={a.max():.2f}"
        )

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = output_dir / f"hybrid-sample-{stamp}"
    target.mkdir(parents=True, exist_ok=True)
    (target / "report.json").write_text(
        json.dumps(
            {
                "tauCell": tau_cell,
                "minEcc": min_ecc,
                "looDeviationCell": loo_errors,
                "fillErrorCell": fill_errors,
                "sources": report,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    page = target / "podglad.html"
    page.write_text(
        "<!doctype html><html lang='pl'><head><meta charset='utf-8'><title>777 — hybryda</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:16px;background:#111;color:#eee}"
        "main{display:grid;grid-template-columns:repeat(auto-fill,minmax(640px,1fr));gap:18px}"
        "figure{margin:0}img{width:100%;display:block}"
        "figcaption{font-size:14px;padding:4px 0}</style></head><body>"
        "<h1>Gra 777 — obecny silnik + model ekranu (podgląd, bez zapisu)</h1>"
        "<p>Ramka zielona: siatka obecnego silnika zgodna z modelem z pozostałych plansz (pewna). "
        "Siatka 5 × 3 zielona bez „P” na niebieskiej ramce: siatka obecnego silnika odrzucona "
        "i zastąpiona siatką z sąsiadów (poprawiona). "
        "Ramka czerwona: niezgodna. Siatka 5 × 3 z „P”: slot dziś bez siatki, "
        "dorysowany z sąsiadów "
        "(zielona = pewna, czerwona = niepewna). Niebieska ramka: za mało sąsiadów do oceny.</p>"
        f"<p>Odchylenie planszy od modelu sąsiadów (w szerokościach komórki): {pct(loo_errors)}. "
        f"Próg pewności: {tau_cell}. Błąd dorysowania sprawdzony na planszach o znanej siatce: "
        f"{pct(fill_errors)}.</p>"
        f"{''.join(sections)}</body></html>",
        encoding="utf-8",
    )
    return page


# --------------------------------------------------------------------------- dry run

DRY_RUN_VERSION = "grid-reverify-777-hybrid-dry-run-v1"


def _evaluate_source(
    gray: Any,
    shape: tuple[int, int],
    known: Mapping[int, FloatQuad],
    pending: set[int],
    *,
    tau_cell: float,
    min_ecc: float,
) -> dict[int, dict[str, object]]:
    """Hybrid decision for every board slot of one photo.

    Every grid the tool would write itself (a filled slot or a repair) passes the
    same checks: alignment strength, bounded correction, inside the photo, the
    neighbours' shape, agreement with a shape-locked placement search, no almost
    equally good placement a cell away, and consistent left/right halves.
    """

    height, width = shape
    out: dict[int, dict[str, object]] = {}
    for position in range(9):
        others = {p: q for p, q in known.items() if p != position}
        if len(others) < HYBRID_MIN_NEIGHBOURS or (
            position not in known and position not in pending
        ):
            entry: dict[str, object] = {"decision": "za_malo_sasiadow"}
            if position in known:
                entry["quad"] = [list(p) for p in known[position]]
            out[position] = entry
            continue
        neighbours = list(others.values())
        predicted = predict_board(others, position, (height, width))
        refined, correlation = refine_board(gray, neighbours, predicted, position)
        shift = max_corner_distance(refined, predicted) / _cell_width(predicted)

        def own_grid_checks(
            neighbours: list[FloatQuad] = neighbours,
            predicted: FloatQuad = predicted,
            refined: FloatQuad = refined,
            correlation: float = correlation,
            shift: float = shift,
            position: int = position,
        ) -> dict[str, object]:
            placed, placed_score, ambiguous = place_board(gray, neighbours, predicted)
            halves_ok, dy_left, dy_right = halves_consistent(gray, neighbours, refined, position)
            inside = quad_inside(refined, width=width, height=height)
            shape_ok = shape_consistent(refined, predicted)
            agree = max_corner_distance(refined, placed) / _cell_width(predicted) <= 0.3
            return {
                "ecc": round(correlation, 3),
                "refineShiftCell": round(shift, 3),
                "inside": inside,
                "shapeOk": shape_ok,
                "placementAgrees": agree,
                "ambiguous": ambiguous,
                "halvesOk": halves_ok,
                "halfOffsetsCell": [round(dy_left, 3), round(dy_right, 3)],
                "placedQuad": [list(point) for point in placed],
                "placedScore": round(placed_score, 3),
                "passed": bool(
                    correlation >= min_ecc
                    and shift <= 0.5
                    and inside
                    and shape_ok
                    and agree
                    and not ambiguous
                    and halves_ok
                ),
            }

        if position in known:
            own = known[position]
            checked, _check_ecc = refine_board_affine(gray, neighbours, predicted, position)
            deviation = max_corner_distance(own, checked) / _cell_width(own)
            limit = ARROW_TAU_CELL if position in ARROW_SIDE else tau_cell
            if deviation <= limit:
                out[position] = {
                    "decision": "pewna",
                    "deviationCell": round(deviation, 3),
                    "quad": [list(p) for p in own],
                }
                continue
            checks = own_grid_checks()
            repair = bool(checks["passed"]) and correlation >= REPAIR_MIN_ECC
            out[position] = {
                "decision": "poprawiona" if repair else "niezgodna",
                "deviationCell": round(deviation, 3),
                **checks,
                "quad": [list(p) for p in (refined if repair else own)],
                "proposedQuad": [list(p) for p in refined],
            }
        else:
            checks = own_grid_checks()
            # A diverged refinement (rotated, skewed or moved too far) is never drawn:
            # the shape-locked placement keeps the neighbours' shape and cannot twist.
            sane = bool(checks["shapeOk"]) and shift <= 0.5
            drawn = (
                refined
                if sane
                else cast(FloatQuad, tuple(map(tuple, cast(list[Any], checks["placedQuad"]))))
            )
            out[position] = {
                "decision": "uzupelniona_pewna" if checks["passed"] else "uzupelniona_niepewna",
                **checks,
                "drawnFrom": "refine" if sane else "placement",
                "quad": [list(p) for p in drawn],
            }
    return out


PAGE_SIZE = 100


def _block_reasons(board_payload: Sequence[Mapping[str, object]]) -> list[str]:
    blocked: list[str] = []
    for item in board_payload:
        number = int(cast(int, item["positionIndex"])) + 1
        if item["kind"] == "missing":
            blocked.append(f"pl.{number} brak")
        elif item["kind"] == "pending_slot" and item["decision"] != "uzupelniona_pewna":
            blocked.append(f"pl.{number} NOWA?")
        elif (
            item["kind"] == "board"
            and not item.get("alreadyApproved")
            and item["decision"] not in ("pewna", "poprawiona")
        ):
            blocked.append(f"pl.{number} BLOK")
    return blocked


def dry_run(
    *,
    game_id: UUID,
    import_job_id: UUID,
    output_dir: Path,
    tau_cell: float,
    min_ecc: float,
) -> Path:
    """Read-only: decide every photo of one import that has slots without a grid.

    Writes ``decisions.json`` (the manifest a later execute step reads, with the
    database identities observed now) and paged previews ordered by sequence
    number. Only grids the tool would write or that block a photo are drawn,
    always as a full thin 5 x 3 lattice. A finished import is skipped on rerun.
    """

    import html

    import cv2
    from game_predictor_api.storage.models import ImageReviewItemModel

    target = output_dir / f"dry-run-{import_job_id}"
    if (target / "decisions.json").exists():
        return target / "index.html"
    settings = get_settings()
    engine = _read_only_engine(create_database_engine(settings))
    session_factory = create_session_factory(engine)
    try:
        with game_storage_scope(game_id), session_factory() as session:
            pending_rows = session.scalars(
                select(ImageBoardGeometryPendingModel).where(
                    ImageBoardGeometryPendingModel.status == "pending",
                    ImageBoardGeometryPendingModel.import_job_id == import_job_id,
                )
            ).all()
            source_ids = sorted({row.source_image_id for row in pending_rows}, key=str)
            sources = {
                s.id: s
                for s in session.scalars(
                    select(SourceImageModel).where(SourceImageModel.id.in_(source_ids))
                ).all()
            }
            autos = _auto_revisions(session, source_ids)
            board_rows = session.execute(
                select(RecognizedBoardModel, ImageReviewItemModel)
                .join(
                    ImageReviewItemModel,
                    ImageReviewItemModel.recognized_board_id == RecognizedBoardModel.id,
                )
                .where(RecognizedBoardModel.source_image_id.in_(source_ids))
            ).all()
            session.expunge_all()
    finally:
        engine.dispose()

    pending_by_source: dict[UUID, dict[int, ImageBoardGeometryPendingModel]] = {}
    for row in pending_rows:
        pending_by_source.setdefault(row.source_image_id, {})[int(row.position_index)] = row
    boards_by_source: dict[UUID, dict[int, tuple[RecognizedBoardModel, Any]]] = {}
    for board, review_row in board_rows:
        boards_by_source.setdefault(board.source_image_id, {})[int(board.position_index)] = (
            board,
            review_row,
        )

    def sequence_start(source_id: UUID) -> int:
        auto = autos.get(source_id)
        return int(auto.sequence_range_start) if auto is not None else 0

    ordered = sorted(source_ids, key=lambda sid: (sequence_start(sid), str(sid)))
    work = target.with_name(target.name + ".partial")
    work.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []
    figures: list[str] = []
    started = time.perf_counter()
    for number, source_id in enumerate(ordered, start=1):
        source = sources[source_id]
        auto = autos.get(source_id)
        pending = pending_by_source.get(source_id, {})
        boards = boards_by_source.get(source_id, {})
        entry: dict[str, object] = {
            "previewNumber": number,
            "sourceImageId": str(source_id),
            "importJobId": str(source.import_job_id),
            "relativePath": source.relative_path,
            "sourceChecksumSha256": source.checksum_sha256,
            "sourceWidth": int(source.oriented_width or source.width),
            "sourceHeight": int(source.oriented_height or source.height),
            "sequenceRange": (
                None
                if auto is None
                else [int(auto.sequence_range_start), int(auto.sequence_range_end)]
            ),
        }
        blocked: list[str] = []
        if auto is None:
            blocked.append("brak automatycznej geometrii")
        if any(int(b.geometry_revision) != 0 for b, _i in boards.values()):
            blocked.append("plansza z ręczną rewizją")
        try:
            rgb = load_source_rgb(settings.artifact_root, source)
        except (OSError, ValueError) as error:
            blocked.append(f"zdjęcie niedostępne: {error}")
            rgb = None
        if rgb is None or auto is None:
            entry.update({"resolvable": False, "blocked": blocked, "boards": []})
            manifest.append(entry)
            continue
        height, width = rgb.shape[:2]
        known: dict[int, FloatQuad] = {}
        for position in boards:
            slot = _slot_geometry(auto.board_geometries, position)
            quad = None if slot is None else engine_quad(slot)
            if quad is not None:
                known[position] = quad
        decisions = _evaluate_source(
            cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY),
            (height, width),
            known,
            set(pending),
            tau_cell=tau_cell,
            min_ecc=min_ecc,
        )
        board_payload: list[dict[str, object]] = []
        for position in range(9):
            item: dict[str, object] = {"positionIndex": position, **decisions[position]}
            if position in pending:
                row = pending[position]
                item.update(
                    {
                        "kind": "pending_slot",
                        "pendingGeometryId": str(row.id),
                        "expectedGeometryRevision": int(row.expected_geometry_revision),
                        "expectedResolutionRevision": int(row.expected_review_resolution_revision),
                    }
                )
            elif position in boards:
                board, review_item = boards[position]
                item.update(
                    {
                        "kind": "board",
                        "reviewItemId": str(review_item.id),
                        "expectedGeometryRevision": int(board.geometry_revision),
                        "expectedResolutionRevision": int(review_item.resolution_revision),
                        "alreadyApproved": board.approved_geometry_revision
                        == board.geometry_revision,
                    }
                )
            else:
                item["kind"] = "missing"
            board_payload.append(item)
        blocked.extend(_block_reasons(board_payload))
        resolvable = not blocked
        entry.update({"resolvable": resolvable, "blocked": blocked, "boards": board_payload})
        manifest.append(entry)

        canvas = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        approved = {
            int(cast(int, b["positionIndex"])) for b in board_payload if b.get("alreadyApproved")
        }
        _draw_decisions(canvas, decisions, include_confirmed=False, skip_positions=approved)
        sequence = cast(list[int] | None, entry["sequenceRange"])
        seq_text = "?" if sequence is None else f"{sequence[0]}–{sequence[1]}"
        status = "GOTOWE" if resolvable else "ZABLOKOWANE: " + ", ".join(blocked)
        caption = html.escape(f"#{number} · sekwencje {seq_text} · {status}")
        figures.append(
            f'<figure id="n{number}"><img src="data:image/jpeg;base64,'
            f'{_encode_preview(canvas)}" alt=""><figcaption>{caption}</figcaption></figure>'
        )
        if number % 50 == 0:
            print(
                f"{import_job_id}: {number}/{len(ordered)} zdjęć, "
                f"{time.perf_counter() - started:.0f} s",
                flush=True,
            )

    resolvable_sources = [m for m in manifest if m["resolvable"]]

    def count(predicate: Any) -> int:
        return sum(
            1
            for m in resolvable_sources
            for b in cast(list[dict[str, object]], m["boards"])
            if predicate(b)
        )

    summary = {
        "version": DRY_RUN_VERSION,
        "gameId": str(game_id),
        "importJobId": str(import_job_id),
        "generatedAt": datetime.now(UTC).isoformat(),
        "tauCell": tau_cell,
        "minEcc": min_ecc,
        "sourcesWithSlots": len(ordered),
        "pendingSlots": len(pending_rows),
        "resolvableSources": len(resolvable_sources),
        "filledSlots": count(lambda b: b["kind"] == "pending_slot"),
        "repairedBoards": count(lambda b: b["decision"] == "poprawiona"),
        "confidentFills": sum(
            1
            for m in manifest
            for b in cast(list[dict[str, object]], m["boards"])
            if b.get("decision") == "uzupelniona_pewna"
        ),
        "sequenceRange": [
            min(
                (cast(list[int], m["sequenceRange"])[0] for m in manifest if m["sequenceRange"]),
                default=0,
            ),
            max(
                (cast(list[int], m["sequenceRange"])[1] for m in manifest if m["sequenceRange"]),
                default=0,
            ),
        ],
        "accepted": [],
        "rejected": [],
    }
    legend = (
        "<p>Rysuję tylko siatki wyznaczone przez silnik lub blokujące zapis, zawsze pełną "
        "siatką 5 × 3: <span style='color:#f0f'>NOWA</span> = brakujący slot dorysowany "
        "pewnie, <span style='color:#f33'>NOWA?</span> = dorysowany niepewnie, "
        "<span style='color:#fa0'>POPR.</span> = siatka obecnego silnika zastąpiona, "
        "<span style='color:#f33'>BLOK</span> = istniejąca siatka niepotwierdzona. "
        "Plansze potwierdzone i już zatwierdzone nie są rysowane. „GOTOWE” = zdjęcie "
        "do zapisu w całości.</p>"
    )
    pages: list[tuple[str, int, int]] = []
    for start in range(0, len(figures), PAGE_SIZE):
        chunk = figures[start : start + PAGE_SIZE]
        first, last = start + 1, start + len(chunk)
        name = f"strona_{first:05d}-{last:05d}.html"
        pages.append((name, first, last))
        (work / name).write_text(
            "<!doctype html><html lang='pl'><head><meta charset='utf-8'>"
            f"<title>777 dry-run #{first}–{last}</title>"
            "<style>body{font-family:system-ui,sans-serif;margin:16px;background:#111;"
            "color:#eee}main{display:grid;grid-template-columns:repeat(auto-fill,"
            "minmax(640px,1fr));gap:18px}figure{margin:0}img{width:100%;display:block}"
            "figcaption{font-size:14px;padding:4px 0}a{color:#8cf}</style></head><body>"
            f"<p><a href='index.html'>← spis</a></p><h1>Import {html.escape(str(import_job_id))}"
            f" — zdjęcia #{first}–{last}</h1>{legend}<main>{''.join(chunk)}</main></body></html>",
            encoding="utf-8",
        )
    links = "".join(f"<li><a href='{name}'>#{first}–{last}</a></li>" for name, first, last in pages)
    (work / "index.html").write_text(
        "<!doctype html><html lang='pl'><head><meta charset='utf-8'><title>777 dry-run</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:16px;background:#111;color:#eee}"
        "a{color:#8cf}</style></head><body>"
        f"<h1>Import {html.escape(str(import_job_id))}</h1>"
        f"<p>Zdjęcia ze slotami bez siatki: {len(ordered)} ({len(pending_rows)} slotów). "
        f"Gotowe do zapisu w całości: {summary['resolvableSources']} zdjęć, "
        f"{summary['filledSlots']} nowych siatek, {summary['repairedBoards']} poprawionych. "
        f"Wszystkie pewnie dorysowane sloty: {summary['confidentFills']}.</p>"
        f"{legend}<ul>{links}</ul></body></html>",
        encoding="utf-8",
    )
    (work / "decisions.json").write_text(
        json.dumps({"summary": summary, "sources": manifest}, indent=2), encoding="utf-8"
    )
    work.rename(target)
    return target / "index.html"


def _range_text(row: Mapping[str, object]) -> str:
    first, last = cast(list[int], row["sequenceRange"])
    return f"{first}–{last}"


def dry_run_all(*, game_id: UUID, output_dir: Path, tau_cell: float, min_ecc: float) -> Path:
    """Dry-run every import with slots without a grid; finished imports are skipped."""

    import html

    settings = get_settings()
    engine = _read_only_engine(create_database_engine(settings))
    session_factory = create_session_factory(engine)
    try:
        with game_storage_scope(game_id), session_factory() as session:
            import_ids = sorted(
                set(
                    session.scalars(
                        select(ImageBoardGeometryPendingModel.import_job_id).where(
                            ImageBoardGeometryPendingModel.status == "pending"
                        )
                    ).all()
                ),
                key=str,
            )
    finally:
        engine.dispose()
    rows: list[dict[str, object]] = []
    for import_id in import_ids:
        dry_run(
            game_id=game_id,
            import_job_id=import_id,
            output_dir=output_dir,
            tau_cell=tau_cell,
            min_ecc=min_ecc,
        )
        data = json.loads(
            (output_dir / f"dry-run-{import_id}" / "decisions.json").read_text(encoding="utf-8")
        )
        rows.append(cast(dict[str, object], data["summary"]))
        print(f"gotowe: {import_id}", flush=True)
    rows.sort(key=lambda r: cast(list[int], r["sequenceRange"])[0])
    table = "".join(
        "<tr>"
        f"<td><a href='dry-run-{r['importJobId']}/index.html'>{r['importJobId']}</a></td>"
        f"<td>{_range_text(r)}</td>"
        f"<td>{r['sourcesWithSlots']}</td><td>{r['pendingSlots']}</td>"
        f"<td>{r['resolvableSources']}</td><td>{r['filledSlots']}</td>"
        f"<td>{r['repairedBoards']}</td><td>{r['confidentFills']}</td></tr>"
        for r in rows
    )
    totals = {
        key: sum(int(cast(int, r[key])) for r in rows)
        for key in (
            "sourcesWithSlots",
            "pendingSlots",
            "resolvableSources",
            "filledSlots",
            "repairedBoards",
            "confidentFills",
        )
    }
    index = output_dir / "dry-run-index.html"
    index.write_text(
        "<!doctype html><html lang='pl'><head><meta charset='utf-8'><title>777 dry-run</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:16px;background:#111;color:#eee}"
        "a{color:#8cf}td,th{padding:4px 10px;border-bottom:1px solid #333}</style></head><body>"
        "<h1>Gra 777 — dry-run wszystkich importów (bez zapisu)</h1>"
        f"<p>{html.escape(json.dumps(totals))}</p><table><tr><th>import</th><th>sekwencje</th>"
        "<th>zdjęcia</th><th>sloty</th><th>gotowe zdjęcia</th><th>nowe siatki</th>"
        f"<th>poprawione</th><th>pewne sloty</th></tr>{table}</table></body></html>",
        encoding="utf-8",
    )
    (output_dir / "dry-run-totals.json").write_text(
        json.dumps({"totals": totals, "imports": rows}, indent=2), encoding="utf-8"
    )
    return index


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    calibrate_parser = commands.add_parser("calibrate", help="read-only golden-set calibration")
    calibrate_parser.add_argument("--game-id", type=UUID, default=GAME_777_ID)
    calibrate_parser.add_argument("--sample-sources", type=int, default=150)
    calibrate_parser.add_argument("--seed", type=int, default=777)
    calibrate_parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    sheet_parser = commands.add_parser("review-sheet", help="read-only blind visual sheet")
    sheet_parser.add_argument("--game-id", type=UUID, default=GAME_777_ID)
    sheet_parser.add_argument("--sample-sources", type=int, default=150)
    sheet_parser.add_argument("--seed", type=int, default=777)
    sheet_parser.add_argument("--unstable-count", type=int, default=50)
    sheet_parser.add_argument("--stable-count", type=int, default=20)
    sheet_parser.add_argument("--unstable-px", type=float, default=2.0)
    sheet_parser.add_argument("--stable-px", type=float, default=1.5)
    sheet_parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    v3_parser = commands.add_parser("v3-sample", help="read-only v3 engine preview on queue sample")
    v3_parser.add_argument("--game-id", type=UUID, default=GAME_777_ID)
    v3_parser.add_argument("--per-category", type=int, default=15)
    v3_parser.add_argument("--seed", type=int, default=777)
    v3_parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    hybrid_parser = commands.add_parser("hybrid-sample", help="read-only engine + screen consensus")
    hybrid_parser.add_argument("--game-id", type=UUID, default=GAME_777_ID)
    hybrid_parser.add_argument("--per-category", type=int, default=15)
    hybrid_parser.add_argument("--seed", type=int, default=777)
    hybrid_parser.add_argument("--tau-cell", type=float, default=0.2)
    hybrid_parser.add_argument("--min-ecc", type=float, default=0.7)
    hybrid_parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    hybrid_parser.add_argument("--only-pending", action="store_true")
    dry_parser = commands.add_parser("dry-run", help="read-only decisions for one import")
    dry_parser.add_argument("--game-id", type=UUID, default=GAME_777_ID)
    dry_parser.add_argument("--import-job-id", type=UUID)
    dry_parser.add_argument("--all-imports", action="store_true")
    dry_parser.add_argument("--tau-cell", type=float, default=0.2)
    dry_parser.add_argument("--min-ecc", type=float, default=0.7)
    dry_parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    arguments = parser.parse_args(argv)
    if arguments.game_id != GAME_777_ID:
        parser.error("This one-off tool only supports game 777.")
    if arguments.command == "dry-run" and arguments.all_imports:
        print(
            dry_run_all(
                game_id=arguments.game_id,
                output_dir=arguments.output_dir,
                tau_cell=arguments.tau_cell,
                min_ecc=arguments.min_ecc,
            ).as_posix()
        )
    elif arguments.command == "dry-run":
        if arguments.import_job_id is None:
            parser.error("dry-run needs --import-job-id or --all-imports")
        print(
            dry_run(
                game_id=arguments.game_id,
                import_job_id=arguments.import_job_id,
                output_dir=arguments.output_dir,
                tau_cell=arguments.tau_cell,
                min_ecc=arguments.min_ecc,
            ).as_posix()
        )
    if arguments.command == "hybrid-sample":
        print(
            hybrid_sample(
                game_id=arguments.game_id,
                per_category=arguments.per_category,
                seed=arguments.seed,
                output_dir=arguments.output_dir,
                tau_cell=arguments.tau_cell,
                min_ecc=arguments.min_ecc,
                only_pending=arguments.only_pending,
            ).as_posix()
        )
    if arguments.command == "v3-sample":
        print(
            v3_sample(
                game_id=arguments.game_id,
                per_category=arguments.per_category,
                seed=arguments.seed,
                output_dir=arguments.output_dir,
            ).as_posix()
        )
    if arguments.command == "review-sheet":
        page = review_sheet(
            game_id=arguments.game_id,
            sample_sources=arguments.sample_sources,
            seed=arguments.seed,
            unstable_count=arguments.unstable_count,
            stable_count=arguments.stable_count,
            unstable_px=arguments.unstable_px,
            stable_px=arguments.stable_px,
            output_dir=arguments.output_dir,
        )
        print(page.as_posix())
    if arguments.command == "calibrate":
        path = calibrate(
            game_id=arguments.game_id,
            sample_sources=arguments.sample_sources,
            seed=arguments.seed,
            output_dir=arguments.output_dir,
        )
        print(path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
