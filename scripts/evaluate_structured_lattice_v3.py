"""Evaluate structured lattice v3 against current manual 3 x 5 corrections."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, cast
from uuid import UUID

import numpy as np
from game_predictor_api.config import get_settings
from game_predictor_api.domain.image_geometry_v2 import (
    SourcePoint,
    SourceQuad,
    canonical_json_bytes,
)
from game_predictor_api.storage.database import create_database_engine, create_session_factory
from game_predictor_api.storage.models import (
    ImageBoardGeometryRevisionModel,
    ImageSourceGeometryRevisionModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from game_predictor_worker.images.board_cell_geometry_contract import (
    LEGACY_BOARD_CELL_TOPOLOGY,
)
from game_predictor_worker.images.board_cell_geometry_estimator import (
    estimate_board_cell_geometry,
)
from game_predictor_worker.images.geometry import Point
from game_predictor_worker.images.structured_geometry.lattice_refinement_v3 import (
    STRUCTURED_LATTICE_REFINEMENT_V3_VERSION,
    refine_structured_symbol_lattice_v3,
    structured_lattice_candidate_config_payload,
)
from PIL import Image, ImageOps
from sqlalchemy import select

REPORT_VERSION = "structured-lattice-v3-real-manual-acceptance-v1"
EXPECTED_GAMES = {
    UUID("9ed937db-ec86-46ca-a8f3-dcfb78edf8c0"): 162,
    UUID("b73c7a42-dfce-498c-be26-0df015721990"): 288,
}
EXPECTED_BOARD_COUNT = 450
EXPECTED_SOURCE_COUNT = 50
MANUAL_CROPPER_VERSION = "virtual-cell-renderer-source-direct-v1"
MANUAL_ACTOR = "local-admin"
DEFAULT_OUTPUT = Path("ai_docs/quality/STRUCTURED_LATTICE_V3_ACCEPTANCE.json")
EXTERNAL_GOLDEN_SOURCE_CHECKSUM = "4b81d5a822fca8f85df07d8e909a071c98688e578024f681594628eda060964a"
EXTERNAL_GOLDEN_MANIFEST_CHECKSUM = (
    "23857fcfd92790fb0851175e44202fa8817676241054d64a952f8c660831ea0d"
)
EXTERNAL_GOLDEN_RELATIVE_PATH = "777 - new 30/seq_20026-20034.jpg"


def _quad(value: object) -> SourceQuad:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes) or len(value) != 4:
        raise ValueError("A geometry quad must contain exactly four points.")
    points: list[SourcePoint] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("A geometry point must be an object.")
        x, y = item.get("x"), item.get("y")
        if (
            not isinstance(x, int | float)
            or isinstance(x, bool)
            or not isinstance(y, int | float)
            or isinstance(y, bool)
        ):
            raise ValueError("A geometry point must contain finite numeric coordinates.")
        points.append(SourcePoint(float(x), float(y)))
    return SourceQuad(corners=tuple(points))  # type: ignore[arg-type]


def _initial_quad(payload: Sequence[Mapping[str, object]], position_index: int) -> SourceQuad:
    matches = [item for item in payload if item.get("positionIndex") == position_index]
    if len(matches) != 1:
        raise ValueError("The source revision does not contain one matching board slot.")
    return _quad(matches[0].get("initialQuad"))


def _load_source(
    artifact_root: Path,
    source: SourceImageModel,
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
    if rgb.shape[:2] != (source.height, source.width):
        raise ValueError("A managed source dimension changed.")
    return rgb


def _corner_errors(actual: SourceQuad, expected: SourceQuad) -> tuple[float, ...]:
    return tuple(
        math.dist((left.x, left.y), (right.x, right.y))
        for left, right in zip(actual.corners, expected.corners, strict=True)
    )


def _percentile(values: Sequence[float], value: float) -> float | None:
    if not values:
        return None
    return round(float(np.percentile(np.asarray(values, dtype=np.float64), value)), 4)


def _source_support(quad: SourceQuad, *, width: int, height: int) -> bool:
    return all(0 <= point.x < width and 0 <= point.y < height for point in quad.corners)


def _row_major_valid(cells: Sequence[object]) -> bool:
    return all(
        getattr(cell, "row_index", None) == index // 5
        and getattr(cell, "column_index", None) == index % 5
        for index, cell in enumerate(cells)
    )


def _external_golden(settings: Any) -> dict[str, object]:
    artifact_root = settings.artifact_root
    image_path = (
        artifact_root
        / "data"
        / "originals"
        / EXTERNAL_GOLDEN_SOURCE_CHECKSUM[:2]
        / f"{EXTERNAL_GOLDEN_SOURCE_CHECKSUM}.jpg"
    )
    content = image_path.read_bytes()
    if hashlib.sha256(content).hexdigest() != EXTERNAL_GOLDEN_SOURCE_CHECKSUM:
        raise RuntimeError("The 20026-20034 golden source drifted.")
    with Image.open(image_path) as image:
        image.load()
        rgb = np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)
    manifest_path = (
        artifact_root
        / "data"
        / "page-geometry-manifests"
        / f"{EXTERNAL_GOLDEN_MANIFEST_CHECKSUM}.json"
    )
    manifest_content = manifest_path.read_bytes()
    if hashlib.sha256(manifest_content).hexdigest() != EXTERNAL_GOLDEN_MANIFEST_CHECKSUM:
        raise RuntimeError("The 20026-20034 golden page manifest drifted.")
    manifest = json.loads(manifest_content)
    entries = manifest.get("entries") if isinstance(manifest, Mapping) else None
    if not isinstance(entries, Mapping):
        raise RuntimeError("The 20026-20034 golden page manifest is invalid.")
    matches = [
        item
        for item in entries.values()
        if isinstance(item, Mapping)
        and item.get("sourceRelativePath") == EXTERNAL_GOLDEN_RELATIVE_PATH
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("quads"), Sequence):
        raise RuntimeError("The 20026-20034 golden page is missing.")
    results = []
    for offset, raw_quad in enumerate(matches[0]["quads"]):
        analysis_quad = _quad(raw_quad)
        refined = refine_structured_symbol_lattice_v3(
            rgb,
            analysis_quad=analysis_quad,
            board_frame_quad=analysis_quad,
            topology=LEGACY_BOARD_CELL_TOPOLOGY,
        )
        results.append(
            {
                "analysisQuad": analysis_quad.to_dict(),
                "reasonCode": refined.reason_code,
                "sequenceNumber": 20026 + offset,
                "status": refined.status,
                "symbolGridQuad": (
                    None if refined.symbol_grid_quad is None else refined.symbol_grid_quad.to_dict()
                ),
            }
        )
    return {
        "manifestChecksumSha256": EXTERNAL_GOLDEN_MANIFEST_CHECKSUM,
        "results": results,
        "sourceChecksumSha256": EXTERNAL_GOLDEN_SOURCE_CHECKSUM,
    }


def build_report() -> dict[str, object]:
    settings = get_settings()
    engine = create_database_engine(settings)
    session = create_session_factory(engine)()
    started = time.perf_counter()
    try:
        rows = session.execute(
            select(
                ImageBoardGeometryRevisionModel,
                RecognizedBoardModel,
                SourceImageModel,
                ImageSourceGeometryRevisionModel,
                JobModel,
            )
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageBoardGeometryRevisionModel.recognized_board_id,
            )
            .join(
                SourceImageModel,
                SourceImageModel.id == RecognizedBoardModel.source_image_id,
            )
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .join(
                ImageSourceGeometryRevisionModel,
                ImageSourceGeometryRevisionModel.id
                == ImageBoardGeometryRevisionModel.source_geometry_revision_id,
            )
            .where(
                JobModel.game_id.in_(tuple(EXPECTED_GAMES)),
                ImageBoardGeometryRevisionModel.corrected_by == MANUAL_ACTOR,
                ImageBoardGeometryRevisionModel.cropper_version == MANUAL_CROPPER_VERSION,
                ImageBoardGeometryRevisionModel.revision == RecognizedBoardModel.geometry_revision,
            )
            .order_by(
                JobModel.game_id,
                SourceImageModel.checksum_sha256,
                RecognizedBoardModel.position_index,
            )
        ).all()
    finally:
        session.close()
        engine.dispose()

    source_cache: dict[str, np.ndarray[Any, np.dtype[np.uint8]]] = {}
    board_results: list[dict[str, object]] = []
    corner_errors: list[float] = []
    board_mean_corner_errors: list[float] = []
    baseline_corner_errors: list[float] = []
    reason_counts: Counter[str] = Counter()
    baseline_success = 0
    game_counts: Counter[str] = Counter()
    invariant_violations: Counter[str] = Counter()
    for revision, board, source, source_revision, job in rows:
        game_counts[str(job.game_id)] += 1
        rgb = source_cache.get(source.checksum_sha256)
        if rgb is None:
            rgb = _load_source(settings.artifact_root, source)
            source_cache[source.checksum_sha256] = rgb
        analysis_quad = _initial_quad(source_revision.board_geometries, board.position_index)
        manual_quad = _quad(revision.corners)
        detector_quad = tuple(
            Point(cast(int, point.x), cast(int, point.y)) for point in analysis_quad.corners
        )
        baseline = estimate_board_cell_geometry(rgb, detector_quad)  # type: ignore[arg-type]
        if baseline.status == "estimated":
            baseline_success += 1
            if baseline.lattice_bounds_quad is not None:
                baseline_quad = SourceQuad(
                    corners=tuple(
                        SourcePoint(float(x), float(y)) for x, y in baseline.lattice_bounds_quad
                    )  # type: ignore[arg-type]
                )
                baseline_corner_errors.extend(_corner_errors(baseline_quad, manual_quad))
        refined = refine_structured_symbol_lattice_v3(
            rgb,
            analysis_quad=analysis_quad,
            board_frame_quad=analysis_quad,
            topology=LEGACY_BOARD_CELL_TOPOLOGY,
        )
        errors: tuple[float, ...] = ()
        if refined.status == "estimated" and refined.symbol_grid_quad is not None:
            errors = _corner_errors(refined.symbol_grid_quad, manual_quad)
            corner_errors.extend(errors)
            board_mean_corner_errors.append(sum(errors) / len(errors))
            if refined.content_safety.status != "passed":
                invariant_violations["content_safety"] += 1
            if len(refined.estimate.cells) != 15 or not _row_major_valid(refined.estimate.cells):
                invariant_violations["row_major"] += 1
            if not _source_support(
                refined.symbol_grid_quad,
                width=source.width,
                height=source.height,
            ):
                invariant_violations["source_support"] += 1
        else:
            reason_counts[refined.reason_code or "unknown"] += 1
        board_results.append(
            {
                "boardId": str(board.id),
                "cornerErrorsPx": [round(value, 4) for value in errors],
                "contentSafety": refined.content_safety.to_payload(),
                "estimatorDiagnostics": {
                    "assignedCandidateCount": refined.estimate.assigned_candidate_count,
                    "candidateCenterCount": refined.estimate.candidate_center_count,
                    "inlierCount": refined.estimate.inlier_count,
                    "inlierP95ResidualPx": refined.estimate.inlier_p95_residual_px,
                    "reliableCenterCount": refined.estimate.reliable_center_count,
                },
                "gameId": str(job.game_id),
                "positionIndex": board.position_index,
                "reasonCode": refined.reason_code,
                "sequenceNumber": board.sequence_number,
                "sourceChecksumSha256": source.checksum_sha256,
                "status": refined.status,
            }
        )

    if len(rows) != EXPECTED_BOARD_COUNT or len(source_cache) != EXPECTED_SOURCE_COUNT:
        raise RuntimeError(
            f"Acceptance cohort drifted: {len(rows)} boards/{len(source_cache)} sources."
        )
    if game_counts != Counter({str(key): value for key, value in EXPECTED_GAMES.items()}):
        raise RuntimeError(f"Acceptance game counts drifted: {dict(game_counts)}")

    estimated_count = sum(item["status"] == "estimated" for item in board_results)
    coverage = estimated_count / len(board_results)
    baseline_coverage = baseline_success / len(board_results)
    median_error = _percentile(corner_errors, 50)
    p90_error = _percentile(corner_errors, 90)
    board_mean_p90_error = _percentile(board_mean_corner_errors, 90)
    external_golden = _external_golden(settings)
    internal_golden = [
        item
        for item in board_results
        if isinstance(item["sequenceNumber"], int) and 19999 <= item["sequenceNumber"] <= 20007
    ]
    internal_golden_passed = (
        len(internal_golden) == 9
        and all(item["status"] == "estimated" for item in internal_golden[:-1])
        and internal_golden[-1]["reasonCode"] == "content_boundary_conflict"
    )
    external_results = cast(list[dict[str, object]], external_golden["results"])
    external_golden_passed = all(item["status"] == "estimated" for item in external_results)
    gates = {
        "coverageAtLeast98Percent": coverage >= 0.98,
        "coverageRegressionAtMostHalfPoint": baseline_coverage - coverage <= 0.005,
        "medianCornerErrorAtMost3Px": median_error is not None and median_error <= 3.0,
        "p90BoardMeanCornerErrorAtMost4_5Px": (
            board_mean_p90_error is not None and board_mean_p90_error <= 4.5
        ),
        "zeroInvariantViolations": not invariant_violations,
    }
    immutable = {
        "adapterVersion": STRUCTURED_LATTICE_REFINEMENT_V3_VERSION,
        "boards": board_results,
        "candidateConfig": structured_lattice_candidate_config_payload(),
        "cohort": {
            "boardCount": len(board_results),
            "gameCounts": dict(sorted(game_counts.items())),
            "manualActor": MANUAL_ACTOR,
            "manualCropperVersion": MANUAL_CROPPER_VERSION,
            "sourceCount": len(source_cache),
            "sourceChecksumsSha256": sorted(source_cache),
            "tuningSourcesUsed": 0,
        },
        "gates": gates,
        "goldenRegressions": {
            "19999-20007": {
                "passed": internal_golden_passed,
                "results": internal_golden,
            },
            "20026-20034": {
                **external_golden,
                "passed": external_golden_passed,
            },
        },
        "metrics": {
            "baselineCoverage": round(baseline_coverage, 6),
            "baselineEstimatedCount": baseline_success,
            "baselineMedianCornerErrorPx": _percentile(baseline_corner_errors, 50),
            "baselineP90CornerErrorPx": _percentile(baseline_corner_errors, 90),
            "coverage": round(coverage, 6),
            "estimatedCount": estimated_count,
            "medianCornerErrorPx": median_error,
            "p90CornerErrorPx": p90_error,
            "p90BoardMeanCornerErrorPx": board_mean_p90_error,
            "reasonCounts": dict(sorted(reason_counts.items())),
            "invariantViolations": dict(sorted(invariant_violations.items())),
        },
        "reportVersion": REPORT_VERSION,
    }
    checksum = hashlib.sha256(canonical_json_bytes(immutable)).hexdigest()
    return {
        **immutable,
        "acceptancePassed": all(gates.values())
        and internal_golden_passed
        and external_golden_passed,
        "evaluationMilliseconds": round((time.perf_counter() - started) * 1000, 3),
        "reportChecksumSha256": checksum,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = build_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes((json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    print(
        json.dumps({key: report[key] for key in ("acceptancePassed", "metrics", "gates")}, indent=2)
    )
    return 0 if report["acceptancePassed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
