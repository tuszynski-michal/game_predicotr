from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import cv2
import numpy as np
import pytest
from game_predictor_api.domain.global_geometry_library import (
    FRAME_APPEARANCE_SCHEMA_VERSION,
    NORMALIZED_TEMPLATE_SCHEMA_VERSION,
    SUPPORTED_GEOMETRY_FAMILY,
    GlobalGeometryProfileStatus,
    GlobalGeometryProfileVersion,
    GlobalGeometryTopology,
)
from game_predictor_worker.images.shape_geometry_v2.preflight import (
    ShapeGeometryV2PreflightError,
    build_shape_geometry_v2_preflight_profile,
    parse_shape_geometry_v2_preflight_profile,
    verify_shape_geometry_v2_profile,
)


def _profile(*, maximum_aspect_ratio: float = 2.0) -> GlobalGeometryProfileVersion:
    topology = GlobalGeometryTopology(3, 3, 3, 5)
    return GlobalGeometryProfileVersion(
        id=uuid4(),
        profile_number=7,
        status=GlobalGeometryProfileStatus.ACTIVE,
        geometry_family=SUPPORTED_GEOMETRY_FAMILY,
        topology=topology,
        normalized_template={
            "schemaVersion": NORMALIZED_TEMPLATE_SCHEMA_VERSION,
            "topology": topology.to_dict(),
            "frameQuad": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
            "aspectRatioRange": {"minimum": 0.5, "maximum": maximum_aspect_ratio},
        },
        frame_appearance={
            "schemaVersion": FRAME_APPEARANCE_SCHEMA_VERSION,
            "sides": {
                "top": {
                    "clusters": [{"lab": [44.0, 12.0, -8.0], "hsv": [23.0, 0.5, 0.7]}],
                    "contrast": {"minimum": 0.2, "median": 0.4, "maximum": 0.8},
                    "continuity": 0.9,
                }
            },
        },
        evidence_summary={
            "schemaVersion": "shape-geometry-evidence-summary-v1",
            "fullSourceCount": 1,
            "partialSourceCount": 0,
            "sourceGameRefs": ["mummies"],
            "extractorVersion": "shape-frame-geometry-v2-core-v1",
            "qualityMetrics": {"candidateCount": 1},
        },
        profile_checksum_sha256="a" * 64,
        created_at=datetime.now(UTC),
    )


def _framed_page(*, frame_color: tuple[int, int, int], with_grid: bool = True) -> np.ndarray:
    page = np.full((600, 900, 3), (18, 21, 25), dtype=np.uint8)
    cv2.rectangle(page, (3, 3), (896, 596), frame_color, thickness=12, lineType=cv2.LINE_AA)
    if with_grid:
        for x in range(60, 900, 60):
            cv2.line(page, (x, 5), (x, 594), frame_color, thickness=4, lineType=cv2.LINE_AA)
        for y in range(67, 600, 67):
            cv2.line(page, (5, y), (894, y), frame_color, thickness=4, lineType=cv2.LINE_AA)
    image = np.zeros((800, 1100, 3), dtype=np.uint8)
    transform = cv2.getPerspectiveTransform(
        np.float32(((0, 0), (899, 0), (899, 599), (0, 599))),
        np.float32(((100, 108), (936, 132), (900, 682), (124, 650))),
    )
    return cv2.warpPerspective(page, transform, (1100, 800), dst=image)


@pytest.mark.parametrize("frame_color", [(235, 25, 20), (230, 180, 20)])
def test_local_verifier_accepts_structure_across_frame_colours(
    frame_color: tuple[int, int, int],
) -> None:
    profile = parse_shape_geometry_v2_preflight_profile(
        build_shape_geometry_v2_preflight_profile(_profile())
    )

    result = verify_shape_geometry_v2_profile(_framed_page(frame_color=frame_color), profile)

    assert result.verdict == "proposal_requires_manual_confirmation"
    assert result.reason_code == "SHAPE_GEOMETRY_V2_MANUAL_CONFIRMATION_REQUIRED"
    assert result.core_result["status"] == "proposal"
    assert result.observed_aspect_ratio is not None


def test_local_verifier_keeps_missing_grid_in_manual_review() -> None:
    profile = parse_shape_geometry_v2_preflight_profile(
        build_shape_geometry_v2_preflight_profile(_profile())
    )

    result = verify_shape_geometry_v2_profile(
        _framed_page(frame_color=(235, 25, 20), with_grid=False), profile
    )

    assert result.verdict == "needs_manual_review"
    assert result.reason_code == "SHAPE_GEOMETRY_V2_CORE_REVIEW_REQUIRED"
    assert result.core_result["status"] == "needs_manual_review"


def test_local_verifier_rejects_a_proposal_outside_profile_aspect_range() -> None:
    profile = parse_shape_geometry_v2_preflight_profile(
        build_shape_geometry_v2_preflight_profile(_profile(maximum_aspect_ratio=1.1))
    )

    result = verify_shape_geometry_v2_profile(_framed_page(frame_color=(235, 25, 20)), profile)

    assert result.verdict == "needs_manual_review"
    assert result.reason_code == "SHAPE_GEOMETRY_V2_ASPECT_RATIO_MISMATCH"


def test_profile_snapshot_is_closed_and_refuses_game_data() -> None:
    payload = build_shape_geometry_v2_preflight_profile(_profile())
    payload["gameId"] = str(uuid4())

    with pytest.raises(ShapeGeometryV2PreflightError) as error:
        parse_shape_geometry_v2_preflight_profile(payload)

    assert error.value.code == "SHAPE_GEOMETRY_V2_PREFLIGHT_PROFILE_INVALID"


def test_profile_snapshot_refuses_descriptors_that_do_not_match_its_checksum() -> None:
    payload = build_shape_geometry_v2_preflight_profile(_profile())
    template = payload["normalizedTemplate"]
    assert isinstance(template, dict)
    template["aspectRatioRange"] = {"minimum": 0.5, "maximum": 1.1}

    with pytest.raises(ShapeGeometryV2PreflightError) as error:
        parse_shape_geometry_v2_preflight_profile(payload)

    assert error.value.code == "SHAPE_GEOMETRY_V2_PREFLIGHT_PROFILE_INTEGRITY_INVALID"
