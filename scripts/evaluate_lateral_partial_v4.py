"""Build and verify the bounded real-image acceptance corpus for v0.10.4.

The default evaluation reads only the immutable manifest and checksum-addressed
managed originals. ``--freeze-from-reviewed`` is an explicit metadata export:
it reads current manual page overrides and writes only the requested repository
manifest. Neither mode writes the database or the operator's image folders.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from statistics import median
from typing import Any, cast
from uuid import UUID

import cv2
import numpy as np
from game_predictor_api.config import get_settings
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.image_geometry_v2 import (
    ActiveBoardSlot,
    DirectCellRenderConfiguration,
    GeometryEngineKind,
    NormalizedSourceImage,
    SourceImageBounds,
    SourceOccurrence,
    SourcePoint,
    SourceQuad,
    VirtualBoardGeometry,
    canonical_json_bytes,
    derive_virtual_cells,
    unavailable_source_cell_indices,
)
from game_predictor_api.storage.database import create_database_engine, create_session_factory
from game_predictor_api.storage.models import ImagePageGeometryOverrideModel
from game_predictor_worker.images.board_cell_geometry_contract import LEGACY_BOARD_CELL_TOPOLOGY
from game_predictor_worker.images.geometry import Point
from game_predictor_worker.images.lateral_partial_contract import (
    LATERAL_PARTIAL_POLICY_VERSION,
    LateralPartialGeometrySnapshot,
)
from game_predictor_worker.images.normalization import (
    CanonicalSourceFrame,
    rgb_pixel_checksum_sha256,
)
from game_predictor_worker.images.page_geometry_registration import (
    PAGE_REGISTRATION_FEATURES_VERSION,
    PAGE_REGISTRATION_THRESHOLDS_VERSION,
    PAGE_REGISTRATION_VERSION,
    LateralPageRegistrationCandidate,
    PageRegistrationInitialization,
    VerifiedPageRegistrar,
)
from game_predictor_worker.images.structured_geometry.lattice_refinement_v3 import (
    refine_structured_symbol_lattice_v3,
)
from game_predictor_worker.images.structured_geometry.lattice_refinement_v4 import (
    LateralLatticeProposal,
    StructuredLatticeRefinementV4,
    refine_structured_symbol_lattice_v4,
)
from game_predictor_worker.images.virtual_cell_extraction import (
    VIRTUAL_CELL_INTERPOLATION_VERSION,
    VIRTUAL_CELL_RENDERER_VERSION,
    VirtualCellRenderer,
)
from PIL import Image, ImageOps
from sqlalchemy import select

CORPUS_VERSION = "lateral-partial-v4-real-corpus-v1"
REPORT_VERSION = "lateral-partial-v4-real-acceptance-v1"
DEFAULT_CORPUS = Path("ai_docs/quality/lateral-partial-v4-real-corpus-v1.json")
DEFAULT_REPORT = Path("ai_docs/quality/lateral-partial-v4-real-acceptance-v1.json")
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
M5_GOLDEN = REPOSITORY_ROOT / "ai_docs" / "quality" / "m5-cell-grid-golden.json"
POLICY = LateralPartialGeometrySnapshot()
DOMAIN_TOPOLOGY = BoardTopology(rows=3, columns=5)
EXPECTED_SOURCE_CHECKSUMS = (
    "34f09a4763e064a909b2616a94daddbd18ba245725f36c585d1e7dd715d88afa",
    "567ccc8bfc43356624c6b9559f37642f97410bf61c28a695a0eca43f0abebde6",
    "cf3482ff4a49c8df7a0bcd8cdb7b1f8c3baad6d39ed590998554d39b6ee622e6",
    "cff6aec06739bc0cd4951657791d10f727931a581301022054012cadd339010c",
    "ead3e4efc618d7c7e9574266f64558bb4e3d7a8a5a42fdf1383dff1c3a5e91f1",
)
EXPECTED_GAME_ID = UUID("03d64bfe-4d29-47dd-9153-76bd99b3b5d9")
LEFT_MASK = (0, 5, 10)
RIGHT_MASK = (4, 9, 14)


def _quad(value: object) -> SourceQuad:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes) or len(value) != 4:
        raise RuntimeError("Each reviewed quad must contain four points.")
    points = []
    for item in value:
        if not isinstance(item, Mapping):
            raise RuntimeError("Each reviewed point must be an object.")
        x, y = item.get("x"), item.get("y")
        if (
            not isinstance(x, int | float)
            or isinstance(x, bool)
            or not isinstance(y, int | float)
            or isinstance(y, bool)
            or not math.isfinite(float(x))
            or not math.isfinite(float(y))
        ):
            raise RuntimeError("Reviewed points must contain finite coordinates.")
        points.append(SourcePoint(float(x), float(y)))
    return SourceQuad(
        cast(tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint], tuple(points))
    )


def _managed_path(artifact_root: Path, checksum: str) -> Path:
    return artifact_root / "data" / "originals" / checksum[:2] / f"{checksum}.jpg"


def _load_rgb(path: Path, checksum: str, width: int, height: int) -> np.ndarray[Any, Any]:
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != checksum:
        raise RuntimeError(f"Managed original checksum drifted: {checksum}.")
    with Image.open(path) as image:
        image.load()
        rgb = np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)
    if rgb.shape != (height, width, 3):
        raise RuntimeError(f"Managed original dimensions drifted: {checksum}.")
    return rgb


def freeze_corpus(output: Path) -> dict[str, object]:
    settings = get_settings()
    engine = create_database_engine(settings)
    session = create_session_factory(engine)()
    try:
        rows = session.scalars(
            select(ImagePageGeometryOverrideModel)
            .where(
                ImagePageGeometryOverrideModel.game_id == EXPECTED_GAME_ID,
                ImagePageGeometryOverrideModel.source_checksum_sha256.in_(
                    EXPECTED_SOURCE_CHECKSUMS
                ),
            )
            .order_by(
                ImagePageGeometryOverrideModel.source_checksum_sha256,
                ImagePageGeometryOverrideModel.revision.desc(),
            )
        ).all()
    finally:
        session.close()
        engine.dispose()
    current: dict[str, ImagePageGeometryOverrideModel] = {}
    for row in rows:
        current.setdefault(row.source_checksum_sha256, row)
    if tuple(current) != EXPECTED_SOURCE_CHECKSUMS:
        raise RuntimeError("The reviewed source set is incomplete or changed.")
    sources = []
    for checksum, row in current.items():
        path = _managed_path(settings.artifact_root, checksum)
        _load_rgb(path, checksum, row.image_width, row.image_height)
        if len(row.final_quads) != 9:
            raise RuntimeError("The acceptance source must have nine reviewed board quads.")
        sources.append(
            {
                "actor": row.actor,
                "decisionChecksumSha256": row.decision_checksum_sha256,
                "gameId": str(row.game_id),
                "height": row.image_height,
                "quads": row.final_quads,
                "reviewRevision": row.revision,
                "sourceChecksumSha256": checksum,
                "sourceFamily": checksum,
                "width": row.image_width,
            }
        )
    golden = json.loads(M5_GOLDEN.read_text(encoding="utf-8"))
    raw_entries = golden.get("entries") if isinstance(golden, Mapping) else None
    if not isinstance(raw_entries, list) or len(raw_entries) != 27:
        raise RuntimeError("The reviewed M5 board fixture set is incomplete.")
    board_sources = []
    seen_board_checksums: set[str] = set()
    for entry in raw_entries:
        if not isinstance(entry, Mapping) or entry.get("reviewStatus") != "accepted":
            raise RuntimeError("Every M5 board fixture must be manually accepted.")
        checksum = cast(str, entry["sourceImageChecksumSha256"])
        if checksum in seen_board_checksums or checksum in current:
            raise RuntimeError("Acceptance sources must be checksum-disjoint.")
        seen_board_checksums.add(checksum)
        relative_path = cast(str, entry["sourceImageRelativePath"])
        image_path = REPOSITORY_ROOT / "examples" / "imgs" / relative_path
        _load_rgb(
            image_path,
            checksum,
            cast(int, entry["sourceImageWidth"]),
            cast(int, entry["sourceImageHeight"]),
        )
        board_sources.append(
            {
                "actor": entry["reviewedBy"],
                "boardPosition": entry["boardPosition"],
                "height": entry["sourceImageHeight"],
                "quad": entry["sourceQuad"],
                "relativePath": relative_path,
                "sequenceNumber": entry["sequenceNumber"],
                "sourceChecksumSha256": checksum,
                "sourceFamily": entry["sourceGroup"],
                "width": entry["sourceImageWidth"],
            }
        )
    immutable = {
        "corpusVersion": CORPUS_VERSION,
        "manualReference": "current-local-owner-page-geometry-override",
        "scenarioPolicy": {
            "ambiguous": "real-middle-three-columns-with-half-cell-search-offset",
            "full": "all-nine-reviewed-boards",
            "lateral": "one-complete-logical-column-removed-left-and-right",
            "missing": "reviewed-board-completely-outside-horizontal-source-support",
            "vertical": "one-complete-logical-row-removed-from-top",
        },
        "sourceDisjointByChecksum": True,
        "boardSources": board_sources,
        "sources": sources,
        "tuningSourceChecksumsSha256": [],
    }
    payload = {
        **immutable,
        "corpusChecksumSha256": hashlib.sha256(canonical_json_bytes(immutable)).hexdigest(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _profile(sources: Sequence[Mapping[str, object]], excluded: str) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "policy": PAGE_REGISTRATION_VERSION,
        "featuresVersion": PAGE_REGISTRATION_FEATURES_VERSION,
        "thresholdsVersion": PAGE_REGISTRATION_THRESHOLDS_VERSION,
        "cornerCountPerAnchor": 36,
        "anchors": [
            {
                "sourceChecksumSha256": item["sourceChecksumSha256"],
                "imageWidth": item["width"],
                "imageHeight": item["height"],
                "quads": item["quads"],
                "provenance": "manual-page-geometry-override-v1",
            }
            for item in sources
            if item["sourceChecksumSha256"] != excluded
        ],
    }


def _shift_x(quad: SourceQuad, amount: int) -> SourceQuad:
    return _source_quad(SourcePoint(point.x - amount, point.y) for point in quad.corners)


def _shift_y(quad: SourceQuad, amount: int) -> SourceQuad:
    return _source_quad(SourcePoint(point.x, point.y - amount) for point in quad.corners)


def _mask(quad: SourceQuad, width: int, height: int) -> tuple[int, ...]:
    return unavailable_source_cell_indices(
        quad,
        source=SourceImageBounds(width, height),
        topology=DOMAIN_TOPOLOGY,
    )


def _negative_is_rejected(status: object) -> bool:
    """Return whether a negative case stayed on a fail-closed review path."""

    return status in {"needs_review", "source_preparation_error"}


def _find_board_cut(quad: SourceQuad, width: int, height: int, side: str) -> int:
    expected_mask = LEFT_MASK if side == "left" else RIGHT_MASK
    matches = []
    for cut in range(1, width):
        cropped_width = width - cut if side == "left" else cut
        value = _mask(_shift_x(quad, cut) if side == "left" else quad, cropped_width, height)
        if value == expected_mask:
            matches.append(cut)
    if matches:
        # Remove the clipped symbol centre as well as the proper cell footprint.
        # On the right the first matching bound is the symmetric choice.
        return matches[-1] if side == "left" else matches[0]
    raise RuntimeError(f"No exact one-column {side} crop exists for reviewed source.")


def _detector_quad(quad: SourceQuad) -> tuple[Point, Point, Point, Point]:
    return cast(
        tuple[Point, Point, Point, Point],
        tuple(Point(cast(int, point.x), cast(int, point.y)) for point in quad.corners),
    )


def _source_quad(points: Iterable[SourcePoint]) -> SourceQuad:
    return SourceQuad(
        cast(tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint], tuple(points))
    )


def _fixture_candidate(quad: SourceQuad) -> LateralPageRegistrationCandidate:
    """Create explicit search evidence for a real-pixel, manual-quad fixture.

    These fixtures validate the local v4 lattice/mask only. End-to-end
    source-disjoint ORB registration is evaluated separately by page sources.
    """

    return LateralPageRegistrationCandidate(
        initialization=PageRegistrationInitialization(
            anchor_source_checksum_sha256=hashlib.sha256(b"manual-fixture-anchor").hexdigest(),
            active_board_slots=(0,),
            initialization_quads=(_detector_quad(quad),),
            native_homography=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            inlier_count=100,
            inlier_ratio=1.0,
            p95_reprojection_error=0.0,
            feature_count=1000,
        ),
        policy_checksum_sha256=POLICY.checksum_sha256,
        board_red_edge_coverages=(1.0,),
    )


def _refine(
    rgb: np.ndarray[Any, Any],
    quad: SourceQuad,
    position: int,
    checksum: str,
    candidate: LateralPageRegistrationCandidate | None,
) -> StructuredLatticeRefinementV4:
    return refine_structured_symbol_lattice_v4(
        rgb,
        analysis_quad=quad,
        board_frame_quad=quad,
        topology=LEGACY_BOARD_CELL_TOPOLOGY,
        source_checksum_sha256=checksum,
        position_index=position,
        lateral_candidate=candidate,
        policy=POLICY,
    )


def _render_proof(
    rgb: np.ndarray[Any, Any],
    *,
    source_checksum_sha256: str,
    position_index: int,
    proposal: LateralLatticeProposal,
) -> dict[str, object]:
    height, width = rgb.shape[:2]
    frame = CanonicalSourceFrame(
        source=NormalizedSourceImage(
            source_checksum_sha256=source_checksum_sha256,
            normalized_pixel_checksum_sha256=rgb_pixel_checksum_sha256(rgb),
            width=width,
            height=height,
            exif_orientation=1,
            normalization_adapter_version="lateral-partial-v4-acceptance-v1",
        ),
        raw_width=width,
        raw_height=height,
        source_mode="RGB",
        orientation_action="identity",
        rgb=rgb,
    )
    geometry = VirtualBoardGeometry(
        source=frame.source,
        source_occurrence=SourceOccurrence(
            UUID(int=515),
            hashlib.sha256(
                f"{source_checksum_sha256}:{position_index}".encode("ascii")
            ).hexdigest(),
        ),
        slot=ActiveBoardSlot(1, 9, position_index, position_index + 1),
        topology=DOMAIN_TOPOLOGY,
        topology_rules_version_id=UUID(int=515),
        geometry_revision=1,
        geometry_version=LATERAL_PARTIAL_POLICY_VERSION,
        engine_kind=GeometryEngineKind.MANUAL_V1,
        symbol_grid_quad=proposal.symbol_grid_quad,
        geometry_qualification=proposal.qualification,
    )
    cells = derive_virtual_cells(
        geometry=geometry,
        configuration=DirectCellRenderConfiguration(
            extractor_version=VIRTUAL_CELL_RENDERER_VERSION,
            preprocessing_version="rgb-v1",
            interpolation=VIRTUAL_CELL_INTERPOLATION_VERSION,
            output_width=32,
            output_height=32,
            padding_fraction=0.08,
        ),
    )
    renders = VirtualCellRenderer().render(frame, cells)
    independent_mask = _mask(proposal.symbol_grid_quad, width, height)
    rendered_indices = tuple(render.cell_index for render in renders)
    expected_rendered = tuple(index for index in range(15) if index not in independent_mask)
    return {
        "independentUnavailableCellIndices": list(independent_mask),
        "renderedCellIndices": list(rendered_indices),
        "renderProofPassed": (
            independent_mask == proposal.qualification.unavailable_cell_indices
            and rendered_indices == expected_rendered
            and len(renders) == len(expected_rendered)
        ),
    }


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    return None if not values else round(float(np.percentile(values, percentile)), 6)


def _load_corpus(
    path: Path,
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("corpusVersion") != CORPUS_VERSION:
        raise RuntimeError("The lateral acceptance corpus version is invalid.")
    checksum = payload.pop("corpusChecksumSha256", None)
    actual = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    payload["corpusChecksumSha256"] = checksum
    if checksum != actual:
        raise RuntimeError("The lateral acceptance corpus checksum drifted.")
    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list) or len(raw_sources) < 2:
        raise RuntimeError("At least two reviewed sources are required.")
    sources = [cast(dict[str, object], item) for item in raw_sources]
    raw_board_sources = payload.get("boardSources")
    if not isinstance(raw_board_sources, list) or len(raw_board_sources) != 27:
        raise RuntimeError("The reviewed board fixture set is incomplete.")
    board_sources = [cast(dict[str, object], item) for item in raw_board_sources]
    checksums = [item.get("sourceChecksumSha256") for item in (*sources, *board_sources)]
    if len(set(checksums)) != len(checksums) or payload.get("tuningSourceChecksumsSha256"):
        raise RuntimeError("Acceptance sources must be unique and disjoint from tuning.")
    return payload, sources, board_sources


def build_report(corpus_path: Path, artifact_root: Path, timing_repeats: int) -> dict[str, object]:
    previous_thread_count = cv2.getNumThreads()
    try:
        cv2.setNumThreads(1)
        return _build_report_single_thread(corpus_path, artifact_root, timing_repeats)
    finally:
        cv2.setNumThreads(previous_thread_count)


def _build_report_single_thread(
    corpus_path: Path, artifact_root: Path, timing_repeats: int
) -> dict[str, object]:
    if not 3 <= timing_repeats <= 9:
        raise RuntimeError("Timing repeats must be between 3 and 9.")
    corpus, sources, board_sources = _load_corpus(corpus_path)
    rgb_cache: dict[str, np.ndarray[Any, Any]] = {}
    source_paths = {
        cast(str, source["sourceChecksumSha256"]): _managed_path(
            artifact_root, cast(str, source["sourceChecksumSha256"])
        )
        for source in sources
    }
    source_paths.update(
        {
            cast(str, source["sourceChecksumSha256"]): REPOSITORY_ROOT
            / "examples"
            / "imgs"
            / cast(str, source["relativePath"])
            for source in board_sources
        }
    )

    def load_checksum(checksum: str) -> np.ndarray[Any, Any]:
        source = next(item for item in sources if item["sourceChecksumSha256"] == checksum)
        cached = rgb_cache.get(checksum)
        if cached is None:
            cached = _load_rgb(
                _managed_path(artifact_root, checksum),
                checksum,
                cast(int, source["width"]),
                cast(int, source["height"]),
            )
            rgb_cache[checksum] = cached
        return cached

    results: list[dict[str, object]] = []
    full_v3_times: list[float] = []
    full_v4_times: list[float] = []
    registration_counts: Counter[str] = Counter()
    for source in sources:
        checksum = cast(str, source["sourceChecksumSha256"])
        width, height = cast(int, source["width"]), cast(int, source["height"])
        rgb = load_checksum(checksum)
        quads = [_quad(value) for value in cast(list[object], source["quads"])]
        registrar = VerifiedPageRegistrar(
            _profile(sources, checksum), load_anchor_rgb=load_checksum
        )
        for position, quad in enumerate(quads):
            cv2.setRNGSeed(515)
            expected = refine_structured_symbol_lattice_v3(
                rgb,
                analysis_quad=quad,
                board_frame_quad=quad,
                topology=LEGACY_BOARD_CELL_TOPOLOGY,
            )
            cv2.setRNGSeed(515)
            actual = _refine(rgb, quad, position, checksum, None)
            results.append(
                {
                    "scenarioId": f"{checksum}:full:{position}",
                    "kind": "full",
                    "sourceChecksumSha256": checksum,
                    "positionIndex": position,
                    "v3Status": expected.status,
                    "v4Status": actual.status,
                    "coverageEqual": (expected.status == "estimated") == (actual.status == "full"),
                    "acceptedPayloadEqual": expected.status != "estimated"
                    or expected.to_payload() == actual.to_payload(),
                }
            )
            for repeat in range(timing_repeats):
                order = ("v3", "v4") if repeat % 2 == 0 else ("v4", "v3")
                for variant in order:
                    cv2.setRNGSeed(1000 + repeat)
                    started = time.perf_counter()
                    if variant == "v3":
                        refine_structured_symbol_lattice_v3(
                            rgb,
                            analysis_quad=quad,
                            board_frame_quad=quad,
                            topology=LEGACY_BOARD_CELL_TOPOLOGY,
                        )
                        full_v3_times.append(time.perf_counter() - started)
                    else:
                        _refine(rgb, quad, position, checksum, None)
                        full_v4_times.append(time.perf_counter() - started)

        for side in ("left", "right"):
            positions = (0, 3, 6) if side == "left" else (2, 5, 8)
            for position in positions:
                cut = _find_board_cut(quads[position], width, height, side)
                cropped = rgb[:, cut:].copy() if side == "left" else rgb[:, :cut].copy()
                reference_quad = (
                    _shift_x(quads[position], cut) if side == "left" else quads[position]
                )
                registration = registrar.evaluate(
                    cropped,
                    lateral_partial_policy=POLICY,
                )
                candidate = registration.lateral_candidate
                registration_counts[f"{side}:{'candidate' if candidate else 'manual'}"] += 1
                analysis_quad = (
                    reference_quad
                    if candidate is None
                    else _source_quad(
                        SourcePoint(point.x, point.y)
                        for point in candidate.initialization.initialization_quads[position]
                    )
                )
                outcome = _refine(cropped, analysis_quad, position, checksum, candidate)
                replay = _refine(cropped.copy(), analysis_quad, position, checksum, candidate)
                proposal = outcome.proposal
                expected_mask = _mask(reference_quad, cropped.shape[1], cropped.shape[0])
                actual_mask = (
                    () if proposal is None else proposal.qualification.unavailable_cell_indices
                )
                render_proof = (
                    {}
                    if proposal is None
                    else _render_proof(
                        cropped,
                        source_checksum_sha256=checksum,
                        position_index=position,
                        proposal=proposal,
                    )
                )
                corner_errors = (
                    []
                    if proposal is None
                    else [
                        math.dist((actual.x, actual.y), (expected.x, expected.y))
                        for actual, expected in zip(
                            proposal.symbol_grid_quad.corners,
                            reference_quad.corners,
                            strict=True,
                        )
                    ]
                )
                cell_width = (
                    math.dist(
                        (reference_quad.corners[0].x, reference_quad.corners[0].y),
                        (reference_quad.corners[1].x, reference_quad.corners[1].y),
                    )
                    + math.dist(
                        (reference_quad.corners[3].x, reference_quad.corners[3].y),
                        (reference_quad.corners[2].x, reference_quad.corners[2].y),
                    )
                ) / 10
                results.append(
                    {
                        "scenarioId": f"{checksum}:{side}:{position}",
                        "kind": side,
                        "sourceChecksumSha256": checksum,
                        "positionIndex": position,
                        "status": outcome.status,
                        "reasonCode": outcome.reason_code,
                        "replayEqual": outcome.to_payload() == replay.to_payload(),
                        "expectedUnavailableCellIndices": list(expected_mask),
                        "actualUnavailableCellIndices": list(actual_mask),
                        "referenceMaskEqual": expected_mask == actual_mask,
                        "expectedColumnOffset": 1 if side == "left" else 0,
                        "actualColumnOffset": None if proposal is None else proposal.column_offset,
                        "maximumCornerErrorPx": None if not corner_errors else max(corner_errors),
                        "halfCellWidthPx": cell_width / 2,
                        "columnShiftDetected": bool(corner_errors)
                        and max(corner_errors) >= cell_width / 2,
                        "candidateAvailable": candidate is not None,
                        "supportedCropIndices": [
                            index for index in range(15) if index not in actual_mask
                        ],
                        **render_proof,
                    }
                )

        # Negatives use reviewed pixels and geometry but do not enter registration/profile tuning.
        position = 4
        quad = quads[position]
        top_cut = min(
            height - 1,
            max(
                1,
                int(
                    round(
                        min(point.y for point in quad.corners)
                        + 0.36
                        * (
                            max(point.y for point in quad.corners)
                            - min(point.y for point in quad.corners)
                        )
                    )
                ),
            ),
        )
        vertical_rgb = rgb[top_cut:].copy()
        vertical_quad = _shift_y(quad, top_cut)
        vertical_candidate = registrar.evaluate(
            vertical_rgb,
            lateral_partial_policy=POLICY,
        ).lateral_candidate
        vertical_analysis = (
            vertical_quad
            if vertical_candidate is None
            else _source_quad(
                SourcePoint(point.x, point.y)
                for point in vertical_candidate.initialization.initialization_quads[position]
            )
        )
        vertical = _refine(vertical_rgb, vertical_analysis, position, checksum, vertical_candidate)
        vertical_replay = _refine(
            vertical_rgb.copy(), vertical_analysis, position, checksum, vertical_candidate
        )
        results.append(
            {
                "scenarioId": f"{checksum}:vertical:{position}",
                "kind": "vertical",
                "sourceChecksumSha256": checksum,
                "positionIndex": position,
                "status": vertical.status,
                "reasonCode": vertical.reason_code,
                "replayEqual": vertical.to_payload() == vertical_replay.to_payload(),
            }
        )

        # Completely missing board: retain real pixels to the right of the reviewed board.
        missing_cut = min(width - 1, max(1, int(math.ceil(max(p.x for p in quad.corners))) + 2))
        missing_rgb = rgb[:, missing_cut:].copy()
        missing_quad = _shift_x(quad, missing_cut)
        missing_candidate = registrar.evaluate(
            missing_rgb,
            lateral_partial_policy=POLICY,
        ).lateral_candidate
        missing_analysis = (
            missing_quad
            if missing_candidate is None
            else _source_quad(
                SourcePoint(point.x, point.y)
                for point in missing_candidate.initialization.initialization_quads[position]
            )
        )
        missing = _refine(missing_rgb, missing_analysis, position, checksum, missing_candidate)
        missing_replay = _refine(
            missing_rgb.copy(), missing_analysis, position, checksum, missing_candidate
        )
        results.append(
            {
                "scenarioId": f"{checksum}:missing:{position}",
                "kind": "missing",
                "sourceChecksumSha256": checksum,
                "positionIndex": position,
                "status": missing.status,
                "reasonCode": missing.reason_code,
                "replayEqual": missing.to_payload() == missing_replay.to_payload(),
            }
        )

        # Ambiguous search evidence: the real crop retains middle columns while the
        # attested search area is shifted half a logical cell and must fail closed.
        left_cut = _find_board_cut(quad, width, height, "left")
        right_cut = _find_board_cut(quad, width, height, "right")
        ambiguous_rgb = rgb[:, left_cut:right_cut].copy()
        ambiguous_quad = _shift_x(quad, left_cut)
        ambiguous_candidate = registrar.evaluate(
            ambiguous_rgb,
            lateral_partial_policy=POLICY,
        ).lateral_candidate
        ambiguous_search = (
            ambiguous_quad
            if ambiguous_candidate is None
            else _source_quad(
                SourcePoint(point.x, point.y)
                for point in ambiguous_candidate.initialization.initialization_quads[position]
            )
        )
        ambiguous = _refine(
            ambiguous_rgb, ambiguous_search, position, checksum, ambiguous_candidate
        )
        ambiguous_replay = _refine(
            ambiguous_rgb.copy(), ambiguous_search, position, checksum, ambiguous_candidate
        )
        results.append(
            {
                "scenarioId": f"{checksum}:ambiguous:{position}",
                "kind": "ambiguous",
                "sourceChecksumSha256": checksum,
                "positionIndex": position,
                "status": ambiguous.status,
                "reasonCode": ambiguous.reason_code,
                "replayEqual": ambiguous.to_payload() == ambiguous_replay.to_payload(),
                "manualReferenceQuad": ambiguous_quad.to_dict(),
            }
        )
        print(f"evaluated page source {checksum[:12]}", flush=True)

    for source in board_sources:
        checksum = cast(str, source["sourceChecksumSha256"])
        width, height = cast(int, source["width"]), cast(int, source["height"])
        relative_path = cast(str, source["relativePath"])
        rgb = _load_rgb(
            REPOSITORY_ROOT / "examples" / "imgs" / relative_path,
            checksum,
            width,
            height,
        )
        quad = _quad(source["quad"])
        original_position = cast(int, source["boardPosition"])
        cv2.setRNGSeed(515)
        expected = refine_structured_symbol_lattice_v3(
            rgb,
            analysis_quad=quad,
            board_frame_quad=quad,
            topology=LEGACY_BOARD_CELL_TOPOLOGY,
        )
        cv2.setRNGSeed(515)
        actual = _refine(rgb, quad, 0, checksum, None)
        results.append(
            {
                "scenarioId": f"{checksum}:full:{original_position}",
                "kind": "full",
                "sourceChecksumSha256": checksum,
                "positionIndex": original_position,
                "v3Status": expected.status,
                "v4Status": actual.status,
                "coverageEqual": (expected.status == "estimated") == (actual.status == "full"),
                "acceptedPayloadEqual": actual.status != "full"
                or expected.to_payload() == actual.to_payload(),
                "evidenceScope": "manual_real_board_fixture",
            }
        )
        for repeat in range(timing_repeats):
            order = ("v3", "v4") if repeat % 2 == 0 else ("v4", "v3")
            for variant in order:
                cv2.setRNGSeed(2000 + repeat)
                started = time.perf_counter()
                if variant == "v3":
                    refine_structured_symbol_lattice_v3(
                        rgb,
                        analysis_quad=quad,
                        board_frame_quad=quad,
                        topology=LEGACY_BOARD_CELL_TOPOLOGY,
                    )
                    full_v3_times.append(time.perf_counter() - started)
                else:
                    _refine(rgb, quad, 0, checksum, None)
                    full_v4_times.append(time.perf_counter() - started)

        for side in ("left", "right"):
            cut = _find_board_cut(quad, width, height, side)
            cropped = rgb[:, cut:].copy() if side == "left" else rgb[:, :cut].copy()
            reference_quad = _shift_x(quad, cut) if side == "left" else quad
            candidate = _fixture_candidate(reference_quad)
            outcome = _refine(cropped, reference_quad, 0, checksum, candidate)
            replay = _refine(cropped.copy(), reference_quad, 0, checksum, candidate)
            proposal = outcome.proposal
            expected_mask = _mask(reference_quad, cropped.shape[1], cropped.shape[0])
            actual_mask = (
                () if proposal is None else proposal.qualification.unavailable_cell_indices
            )
            render_proof = (
                {}
                if proposal is None
                else _render_proof(
                    cropped,
                    source_checksum_sha256=checksum,
                    position_index=0,
                    proposal=proposal,
                )
            )
            corner_errors = (
                []
                if proposal is None
                else [
                    math.dist((left.x, left.y), (right.x, right.y))
                    for left, right in zip(
                        proposal.symbol_grid_quad.corners,
                        reference_quad.corners,
                        strict=True,
                    )
                ]
            )
            cell_width = (
                math.dist(
                    (reference_quad.corners[0].x, reference_quad.corners[0].y),
                    (reference_quad.corners[1].x, reference_quad.corners[1].y),
                )
                + math.dist(
                    (reference_quad.corners[3].x, reference_quad.corners[3].y),
                    (reference_quad.corners[2].x, reference_quad.corners[2].y),
                )
            ) / 10
            results.append(
                {
                    "scenarioId": f"{checksum}:{side}:{original_position}",
                    "kind": side,
                    "sourceChecksumSha256": checksum,
                    "positionIndex": original_position,
                    "status": outcome.status,
                    "reasonCode": outcome.reason_code,
                    "replayEqual": outcome.to_payload() == replay.to_payload(),
                    "expectedUnavailableCellIndices": list(expected_mask),
                    "actualUnavailableCellIndices": list(actual_mask),
                    "referenceMaskEqual": expected_mask == actual_mask,
                    "expectedColumnOffset": 1 if side == "left" else 0,
                    "actualColumnOffset": None if proposal is None else proposal.column_offset,
                    "maximumCornerErrorPx": None if not corner_errors else max(corner_errors),
                    "halfCellWidthPx": cell_width / 2,
                    "columnShiftDetected": bool(corner_errors)
                    and max(corner_errors) >= cell_width / 2,
                    "candidateAvailable": True,
                    "supportedCropIndices": [
                        index for index in range(15) if index not in actual_mask
                    ],
                    "evidenceScope": "manual_real_board_fixture",
                    **render_proof,
                }
            )

        top_cut = min(
            height - 1,
            max(
                1,
                int(
                    round(
                        min(point.y for point in quad.corners)
                        + 0.36
                        * (
                            max(point.y for point in quad.corners)
                            - min(point.y for point in quad.corners)
                        )
                    )
                ),
            ),
        )
        vertical_quad = _shift_y(quad, top_cut)
        vertical_rgb = rgb[top_cut:].copy()
        vertical_candidate = _fixture_candidate(vertical_quad)
        vertical = _refine(vertical_rgb, vertical_quad, 0, checksum, vertical_candidate)
        vertical_replay = _refine(
            vertical_rgb.copy(), vertical_quad, 0, checksum, vertical_candidate
        )
        results.append(
            {
                "scenarioId": f"{checksum}:vertical:{original_position}",
                "kind": "vertical",
                "sourceChecksumSha256": checksum,
                "positionIndex": original_position,
                "status": vertical.status,
                "reasonCode": vertical.reason_code,
                "replayEqual": vertical.to_payload() == vertical_replay.to_payload(),
                "evidenceScope": "manual_real_board_fixture",
            }
        )

        missing_cut = min(width - 1, max(1, int(math.ceil(max(p.x for p in quad.corners))) + 2))
        missing_quad = _shift_x(quad, missing_cut)
        missing_rgb = rgb[:, missing_cut:].copy()
        missing_candidate = _fixture_candidate(missing_quad)
        missing = _refine(missing_rgb, missing_quad, 0, checksum, missing_candidate)
        missing_replay = _refine(missing_rgb.copy(), missing_quad, 0, checksum, missing_candidate)
        results.append(
            {
                "scenarioId": f"{checksum}:missing:{original_position}",
                "kind": "missing",
                "sourceChecksumSha256": checksum,
                "positionIndex": original_position,
                "status": missing.status,
                "reasonCode": missing.reason_code,
                "replayEqual": missing.to_payload() == missing_replay.to_payload(),
                "evidenceScope": "manual_real_board_fixture",
            }
        )

        left_cut = _find_board_cut(quad, width, height, "left")
        right_cut = _find_board_cut(quad, width, height, "right")
        ambiguous_rgb = rgb[:, left_cut:right_cut].copy()
        ambiguous_quad = _shift_x(quad, left_cut)
        cell_dx = (
            max(point.x for point in ambiguous_quad.corners)
            - min(point.x for point in ambiguous_quad.corners)
        ) / 5
        ambiguous_search = _source_quad(
            SourcePoint(point.x + cell_dx * 0.5, point.y) for point in ambiguous_quad.corners
        )
        ambiguous_candidate = _fixture_candidate(ambiguous_search)
        ambiguous = _refine(ambiguous_rgb, ambiguous_search, 0, checksum, ambiguous_candidate)
        ambiguous_replay = _refine(
            ambiguous_rgb.copy(), ambiguous_search, 0, checksum, ambiguous_candidate
        )
        results.append(
            {
                "scenarioId": f"{checksum}:ambiguous:{original_position}",
                "kind": "ambiguous",
                "sourceChecksumSha256": checksum,
                "positionIndex": original_position,
                "status": ambiguous.status,
                "reasonCode": ambiguous.reason_code,
                "replayEqual": ambiguous.to_payload() == ambiguous_replay.to_payload(),
                "manualReferenceQuad": ambiguous_quad.to_dict(),
                "evidenceScope": "manual_real_board_fixture",
            }
        )
        print(f"evaluated board source {checksum[:12]}", flush=True)

    ids = [cast(str, item["scenarioId"]) for item in results]
    full = [item for item in results if item["kind"] == "full"]
    lateral = [item for item in results if item["kind"] in {"left", "right"}]
    negatives = [item for item in results if item["kind"] in {"vertical", "ambiguous", "missing"}]
    proposals = [item for item in lateral if item["status"] == "pending_partial"]
    v3_total, v4_total = sum(full_v3_times), sum(full_v4_times)
    overhead = (v4_total / v3_total - 1.0) if v3_total else float("inf")
    reason_index = Counter(
        cast(str, item.get("reasonCode") or item.get("status") or item.get("v4Status"))
        for item in results
    )
    manual_index = [
        {
            "scenarioId": item["scenarioId"],
            "reasonCode": item.get("reasonCode"),
        }
        for item in lateral
        if item["status"] != "pending_partial"
    ]
    error_index = []
    for item in proposals:
        expected_mask_set = set(cast(list[int], item["expectedUnavailableCellIndices"]))
        actual_mask_set = set(cast(list[int], item["actualUnavailableCellIndices"]))
        if item["columnShiftDetected"]:
            error_index.append({"scenarioId": item["scenarioId"], "code": "COLUMN_SHIFT"})
        if item["actualColumnOffset"] != item["expectedColumnOffset"]:
            error_index.append({"scenarioId": item["scenarioId"], "code": "COLUMN_OFFSET_MISMATCH"})
        if expected_mask_set != actual_mask_set or item.get("renderProofPassed") is not True:
            error_index.append({"scenarioId": item["scenarioId"], "code": "MISSING_PIXEL_CROP"})
    for item in negatives:
        if not _negative_is_rejected(item["status"]):
            error_index.append({"scenarioId": item["scenarioId"], "code": "NEGATIVE_ACCEPTED"})
    for item in (*lateral, *negatives):
        if item.get("replayEqual") is not True:
            error_index.append({"scenarioId": item["scenarioId"], "code": "REPLAY_DRIFT"})
    gates = {
        "zeroFullBoardRegressions": all(
            item["coverageEqual"] and item["acceptedPayloadEqual"] for item in full
        ),
        "zeroColumnShifts": all(
            not item["columnShiftDetected"]
            and item["actualColumnOffset"] == item["expectedColumnOffset"]
            for item in proposals
        ),
        "zeroMissingPixelCrops": all(
            item["referenceMaskEqual"] is True
            and item.get("renderProofPassed") is True
            and len(cast(list[int], item["supportedCropIndices"]))
            + len(cast(list[int], item["actualUnavailableCellIndices"]))
            == 15
            for item in proposals
        ),
        "zeroVerticalAcceptedAsLateral": all(
            _negative_is_rejected(item["status"])
            for item in negatives
            if item["kind"] == "vertical"
        ),
        "zeroAmbiguousOrMissingAccepted": all(
            _negative_is_rejected(item["status"])
            for item in negatives
            if item["kind"] != "vertical"
        ),
        "realLeftAndRightRecovery": all(
            any(item["kind"] == side and item["status"] == "pending_partial" for item in lateral)
            for side in ("left", "right")
        ),
        "noDecisionLossOrDuplicates": len(ids)
        == len(set(ids))
        == len(sources) * 18 + len(board_sources) * 6,
        "deterministicReplay": all(
            item.get("replayEqual") is True for item in (*lateral, *negatives)
        ),
        "sourceChecksumsPreserved": all(
            hashlib.sha256(path.read_bytes()).hexdigest() == checksum
            for checksum, path in source_paths.items()
        ),
        "fullImageOverheadAtMost10Percent": overhead <= 0.10,
    }
    immutable = {
        "reportVersion": REPORT_VERSION,
        "corpusChecksumSha256": corpus["corpusChecksumSha256"],
        "policyChecksumSha256": POLICY.checksum_sha256,
        "sourceDisjointByChecksum": True,
        "tuningSourcesUsed": 0,
        "coverage": {
            "fullBoardCount": len(full),
            "fullV3AcceptedCount": sum(item["v3Status"] == "estimated" for item in full),
            "fullV4AcceptedCount": sum(item["v4Status"] == "full" for item in full),
            "lateralScenarioCount": len(lateral),
            "lateralProposalCount": len(proposals),
            "leftProposalCount": sum(item["kind"] == "left" for item in proposals),
            "rightProposalCount": sum(item["kind"] == "right" for item in proposals),
            "manualLateralCount": len(lateral) - len(proposals),
            "negativeScenarioCount": len(negatives),
        },
        "reasonIndex": dict(sorted(reason_index.items())),
        "manualIndex": manual_index,
        "errorIndex": error_index,
        "registrationIndex": dict(sorted(registration_counts.items())),
        "performance": {
            "timingRepeats": timing_repeats,
            "v3MedianMilliseconds": round(median(full_v3_times) * 1000, 6),
            "v3P95Milliseconds": round(cast(float, _percentile(full_v3_times, 95)) * 1000, 6),
            "v4MedianMilliseconds": round(median(full_v4_times) * 1000, 6),
            "v4P95Milliseconds": round(cast(float, _percentile(full_v4_times, 95)) * 1000, 6),
            "pairedTotalOverheadRatio": round(overhead, 6),
        },
        "gates": gates,
        "results": results,
    }
    complete = {
        **immutable,
        "acceptancePassed": all(gates.values()),
    }
    return {
        **complete,
        "reportChecksumSha256": hashlib.sha256(canonical_json_bytes(complete)).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--artifact-root", type=Path, default=get_settings().artifact_root)
    parser.add_argument("--timing-repeats", type=int, default=3)
    parser.add_argument("--freeze-from-reviewed", action="store_true")
    args = parser.parse_args()
    if args.freeze_from_reviewed:
        payload = freeze_corpus(args.corpus)
        print(json.dumps({"corpusChecksumSha256": payload["corpusChecksumSha256"]}))
        return 0
    report = build_report(args.corpus, args.artifact_root.resolve(), args.timing_repeats)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "acceptancePassed": report["acceptancePassed"],
                "gates": report["gates"],
                "coverage": report["coverage"],
                "performance": report["performance"],
            },
            indent=2,
        )
    )
    return 0 if report["acceptancePassed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
