"""Compare standard and board-area page registration on current manual overrides.

The evaluator is read-only.  Each evaluated source checksum is removed from the
anchor profile before registration, so an image can never validate itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from statistics import median
from typing import cast
from uuid import UUID

import numpy as np
from game_predictor_api.storage.page_geometry_override_repository import (
    SqlAlchemyPageGeometryOverrideRepository,
)
from game_predictor_worker.images.geometry import Point, Quad
from game_predictor_worker.images.page_geometry_registration import (
    PAGE_REGISTRATION_ANCHOR_MASK_PADDING_RATIO,
    PAGE_REGISTRATION_ANCHOR_MASK_VERSION,
    PAGE_REGISTRATION_BOARD_AREA_MASK_VERSION,
    PAGE_REGISTRATION_FEATURES_VERSION,
    PAGE_REGISTRATION_THRESHOLDS_VERSION,
    PAGE_REGISTRATION_VERSION,
    PageRegistrationEvaluation,
    VerifiedPageRegistrar,
)
from numpy.typing import NDArray
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", action="append", required=True, type=UUID)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--artifact-root", default="artifacts", type=Path)
    parser.add_argument("--diagnostic-source-checksum")
    parser.add_argument("--diagnostic-source-path", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def _rgb(path: Path) -> NDArray[np.uint8]:
    try:
        with Image.open(path) as image:
            image.load()
            return cast(
                NDArray[np.uint8],
                np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8),
            )
    except (OSError, UnidentifiedImageError) as error:
        raise RuntimeError(f"Cannot read managed source {path}.") from error


def _profile_variant(profile: Mapping[str, object], *, masked: bool) -> dict[str, object]:
    result = {
        key: value
        for key, value in profile.items()
        if key not in {"anchorMaskVersion", "anchorMaskPaddingRatio"}
    }
    result["policy"] = (
        PAGE_REGISTRATION_BOARD_AREA_MASK_VERSION if masked else PAGE_REGISTRATION_VERSION
    )
    if masked:
        result["anchorMaskVersion"] = PAGE_REGISTRATION_ANCHOR_MASK_VERSION
        result["anchorMaskPaddingRatio"] = PAGE_REGISTRATION_ANCHOR_MASK_PADDING_RATIO
    return result


def _without_source_anchor(
    profile: Mapping[str, object], source_checksum_sha256: str
) -> dict[str, object]:
    result = dict(profile)
    raw_anchors = profile.get("anchors")
    anchors = (
        [
            dict(anchor)
            for anchor in raw_anchors
            if isinstance(anchor, Mapping)
            and anchor.get("sourceChecksumSha256") != source_checksum_sha256
        ]
        if isinstance(raw_anchors, Sequence) and not isinstance(raw_anchors, str | bytes)
        else []
    )
    result["anchors"] = anchors
    return result


def _reference_quads(raw: Sequence[Sequence[Mapping[str, object]]]) -> tuple[Quad, ...]:
    return tuple(
        cast(
            Quad,
            tuple(
                Point(
                    float(cast(int | float, point["x"])),
                    float(cast(int | float, point["y"])),
                )
                for point in raw_quad
            ),
        )
        for raw_quad in raw
    )


def _geometry_error(
    result_quads: Sequence[Quad], reference_quads: Sequence[Quad]
) -> dict[str, float] | None:
    if len(result_quads) != len(reference_quads):
        return None
    corner_errors = np.asarray(
        [
            np.hypot(actual.x - expected.x, actual.y - expected.y)
            for actual, expected in zip(
                (point for quad in result_quads for point in quad),
                (point for quad in reference_quads for point in quad),
                strict=True,
            )
        ],
        dtype=np.float64,
    )
    board_means = corner_errors.reshape((-1, 4)).mean(axis=1)
    return {
        "medianCornerErrorPx": round(float(np.median(corner_errors)), 6),
        "p95CornerErrorPx": round(float(np.percentile(corner_errors, 95)), 6),
        "maximumBoardMeanCornerErrorPx": round(float(board_means.max()), 6),
    }


def _evaluate(
    rgb: np.ndarray,
    reference: Sequence[Quad] | None,
    profile: Mapping[str, object],
    *,
    load_anchor_rgb: Callable[[str], np.ndarray],
) -> dict[str, object]:
    started = time.perf_counter()
    registrar = VerifiedPageRegistrar(
        profile,
        load_anchor_rgb=load_anchor_rgb,
    )
    initialization_seconds = time.perf_counter() - started
    started = time.perf_counter()
    evaluation: PageRegistrationEvaluation = registrar.evaluate(rgb)
    registration_seconds = time.perf_counter() - started
    result = evaluation.result
    payload: dict[str, object] = {
        "attemptCount": len(evaluation.attempts),
        "initializationSeconds": round(initialization_seconds, 6),
        "registered": result is not None,
        "registrationSeconds": round(registration_seconds, 6),
        "totalSeconds": round(initialization_seconds + registration_seconds, 6),
    }
    if result is None:
        failure = evaluation.failure_payload()
        payload["failureReasonCode"] = failure["reasonCode"]
    if result is not None:
        payload["anchorSourceChecksumSha256"] = result.anchor_source_checksum_sha256
        payload["inlierCount"] = result.inlier_count
        payload["p95ReprojectionError"] = round(result.p95_reprojection_error, 6)
        if reference is not None:
            payload["geometryError"] = _geometry_error(result.quads, reference)
    return payload


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    return None if not values else round(float(np.percentile(values, percentile)), 6)


def _summary(results: Sequence[Mapping[str, object]], variant: str) -> dict[str, object]:
    observations = [
        cast(Mapping[str, object], result[variant])
        for result in results
        if isinstance(result.get(variant), Mapping)
    ]
    registered = [item for item in observations if item.get("registered") is True]
    corner_errors = [
        float(error["medianCornerErrorPx"])
        for item in registered
        if isinstance((error := item.get("geometryError")), Mapping)
        and isinstance(error.get("medianCornerErrorPx"), int | float)
    ]
    durations = [float(cast(int | float, item["totalSeconds"])) for item in observations]
    return {
        "evaluatedSourceCount": len(observations),
        "registeredSourceCount": len(registered),
        "registrationRate": round(len(registered) / len(observations), 6) if observations else None,
        "medianCornerErrorPx": round(median(corner_errors), 6) if corner_errors else None,
        "medianSecondsPerSource": round(median(durations), 6) if durations else None,
        "p95SecondsPerSource": _percentile(durations, 95),
        "totalSeconds": round(sum(durations), 6),
    }


def build_report(
    *,
    artifact_root: Path,
    database_url: str,
    game_ids: Sequence[UUID],
    limit: int,
    diagnostic_source_checksum: str | None,
    diagnostic_source_path: Path | None,
) -> dict[str, object]:
    if not 1 <= limit <= 50:
        raise RuntimeError("--limit must be between 1 and 50.")
    root = artifact_root.resolve()
    engine = create_engine(database_url)
    results: list[dict[str, object]] = []
    skipped: list[dict[str, str]] = []
    diagnostics: list[dict[str, object]] = []
    rgb_cache: dict[str, np.ndarray] = {}

    def load_checksum(checksum: str) -> np.ndarray:
        cached = rgb_cache.get(checksum)
        if cached is None:
            cached = _rgb(root / "data" / "originals" / checksum[:2] / f"{checksum}.jpg")
            rgb_cache[checksum] = cached
        return cached

    with Session(engine) as session:
        for game_id in game_ids:
            overrides = SqlAlchemyPageGeometryOverrideRepository(session).list_current(
                game_id=game_id
            )
            raw_profile: dict[str, object] = {
                "schemaVersion": 1,
                "policy": PAGE_REGISTRATION_VERSION,
                "featuresVersion": PAGE_REGISTRATION_FEATURES_VERSION,
                "thresholdsVersion": PAGE_REGISTRATION_THRESHOLDS_VERSION,
                "cornerCountPerAnchor": 36,
                "anchors": [
                    {
                        "sourceChecksumSha256": override.source_checksum_sha256,
                        "imageWidth": override.image_width,
                        "imageHeight": override.image_height,
                        "quads": [list(quad) for quad in override.final_quads],
                        "provenance": "manual-page-geometry-override-v1",
                    }
                    for override in overrides
                    if (
                        root
                        / "data"
                        / "originals"
                        / override.source_checksum_sha256[:2]
                        / f"{override.source_checksum_sha256}.jpg"
                    ).is_file()
                ],
            }
            for override in overrides:
                if len(results) >= limit:
                    break
                checksum = override.source_checksum_sha256
                source_path = root / "data" / "originals" / checksum[:2] / f"{checksum}.jpg"
                if not source_path.is_file():
                    skipped.append(
                        {
                            "gameId": str(game_id),
                            "sourceChecksumSha256": checksum,
                            "reason": "asset_missing",
                        }
                    )
                    continue
                source_disjoint = _without_source_anchor(raw_profile, checksum)
                anchors = source_disjoint.get("anchors")
                if not isinstance(anchors, list) or not anchors:
                    skipped.append(
                        {
                            "gameId": str(game_id),
                            "sourceChecksumSha256": checksum,
                            "reason": "no_disjoint_anchor",
                        }
                    )
                    continue
                rgb = load_checksum(checksum)
                reference = _reference_quads(override.final_quads)
                standard = _evaluate(
                    rgb,
                    reference,
                    _profile_variant(source_disjoint, masked=False),
                    load_anchor_rgb=load_checksum,
                )
                masked = _evaluate(
                    rgb,
                    reference,
                    _profile_variant(source_disjoint, masked=True),
                    load_anchor_rgb=load_checksum,
                )
                results.append(
                    {
                        "gameId": str(game_id),
                        "sourceChecksumSha256": checksum,
                        "standard": standard,
                        "boardAreaMasked": masked,
                    }
                )
            if diagnostic_source_checksum is not None:
                diagnostic_path = (
                    root
                    / "data"
                    / "originals"
                    / diagnostic_source_checksum[:2]
                    / f"{diagnostic_source_checksum}.jpg"
                )
                if not diagnostic_path.is_file() and diagnostic_source_path is not None:
                    diagnostic_path = diagnostic_source_path.resolve()
                if diagnostic_path.is_file():
                    if (
                        hashlib.sha256(diagnostic_path.read_bytes()).hexdigest()
                        != diagnostic_source_checksum
                    ):
                        skipped.append(
                            {
                                "gameId": str(game_id),
                                "sourceChecksumSha256": diagnostic_source_checksum,
                                "reason": "diagnostic_checksum_mismatch",
                            }
                        )
                        continue
                    source_disjoint = _without_source_anchor(
                        raw_profile, diagnostic_source_checksum
                    )
                    diagnostic_rgb = _rgb(diagnostic_path)
                    diagnostics.append(
                        {
                            "gameId": str(game_id),
                            "sourceChecksumSha256": diagnostic_source_checksum,
                            "hasManualReference": False,
                            "standard": _evaluate(
                                diagnostic_rgb,
                                None,
                                _profile_variant(source_disjoint, masked=False),
                                load_anchor_rgb=load_checksum,
                            ),
                            "boardAreaMasked": _evaluate(
                                diagnostic_rgb,
                                None,
                                _profile_variant(source_disjoint, masked=True),
                                load_anchor_rgb=load_checksum,
                            ),
                        }
                    )
    engine.dispose()
    standard_summary = _summary(results, "standard")
    masked_summary = _summary(results, "boardAreaMasked")
    masked_only = [
        result["sourceChecksumSha256"]
        for result in results
        if cast(Mapping[str, object], result["standard"]).get("registered") is False
        and cast(Mapping[str, object], result["boardAreaMasked"]).get("registered") is True
    ]
    return {
        "schemaVersion": 1,
        "policy": "board-area-registration-bounded-acceptance-v1",
        "sourceDisjointByChecksum": True,
        "requestedLimit": limit,
        "evaluatedSourceCount": len(results),
        "standard": standard_summary,
        "boardAreaMasked": masked_summary,
        "maskedOnlyAcceptanceChecksums": masked_only,
        "activationEligible": False,
        "activationStatus": "requires_operator_quality_review",
        "results": results,
        "diagnosticsWithoutReference": diagnostics,
        "skipped": skipped,
    }


def main() -> int:
    arguments = _arguments()
    database_url = os.environ.get(
        "GAME_PREDICTOR_DATABASE_URL",
        "postgresql+psycopg://game_predictor:game_predictor_local@127.0.0.1:5432/game_predictor",
    )
    report = build_report(
        artifact_root=arguments.artifact_root,
        database_url=database_url,
        game_ids=arguments.game_id,
        limit=arguments.limit,
        diagnostic_source_checksum=arguments.diagnostic_source_checksum,
        diagnostic_source_path=arguments.diagnostic_source_path,
    )
    content = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.write_text(content, encoding="utf-8")
    print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
