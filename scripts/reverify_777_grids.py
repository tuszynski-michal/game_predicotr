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
    arguments = parser.parse_args(argv)
    if arguments.game_id != GAME_777_ID:
        parser.error("This one-off tool only supports game 777.")
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
