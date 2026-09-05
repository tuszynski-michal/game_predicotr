from __future__ import annotations

from uuid import UUID

import cv2
import numpy as np
import pytest
from game_predictor_api.domain.board_topology import LEGACY_IMAGE_BOARD_TOPOLOGY
from game_predictor_api.domain.image_geometry_v2 import (
    AttestedSequenceRange,
    NormalizedSourceImage,
    SourcePoint,
    SourceQuad,
)
from game_predictor_worker.images.geometry import Point
from game_predictor_worker.images.normalization import (
    CanonicalSourceFrame,
    rgb_pixel_checksum_sha256,
)
from game_predictor_worker.images.page_geometry_registration import PAGE_REGISTRATION_VERSION
from game_predictor_worker.images.structured_geometry import (
    STRUCTURED_OPENCV_PINNED_PREFLIGHT_VERSION,
    BoardGeometryDisposition,
    BoardGeometryReasonCode,
    GlobalInitializationMethod,
    GlobalInitializationStatus,
    SourceGeometryStatus,
    StructuredGeometryInitializationError,
    StructuredGeometryInitializationRequest,
    StructuredOpenCvGeometryEngine,
)

_TOPOLOGY_RULES_VERSION_ID = UUID("00000000-0000-0000-0000-000000000310")


def _page(
    *,
    active_count: int,
) -> tuple[np.ndarray, tuple[tuple[Point, Point, Point, Point], ...]]:
    rng = np.random.default_rng(310)
    image = rng.integers(0, 55, size=(620, 760, 3), dtype=np.uint8)
    quads: list[tuple[Point, Point, Point, Point]] = []
    for position in range(9):
        row, column = divmod(position, 3)
        left = 85 + column * 210
        top = 70 + row * 165
        right, bottom = left + 155, top + 100
        quad = (
            Point(left, top),
            Point(right, top),
            Point(right, bottom),
            Point(left, bottom),
        )
        quads.append(quad)
        if position >= active_count:
            continue
        cv2.rectangle(image, (left, top), (right, bottom), (235, 25, 20), 7)
        for column_index in range(1, 5):
            x = left + round(column_index * (right - left) / 5)
            cv2.line(image, (x, top + 5), (x, bottom - 5), (210, 210, 210), 1)
        for row_index in range(1, 3):
            y = top + round(row_index * (bottom - top) / 3)
            cv2.line(image, (left + 5, y), (right - 5, y), (210, 210, 210), 1)
        cv2.putText(
            image,
            str(position + 1),
            (left + 63, top + 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (255, 255, 255),
            2,
        )
    return image, tuple(quads)


def _warp(
    image: np.ndarray,
    quads: tuple[tuple[Point, Point, Point, Point], ...],
    *,
    corners: tuple[tuple[float, float], ...],
) -> tuple[np.ndarray, tuple[np.ndarray, ...]]:
    homography = cv2.getPerspectiveTransform(
        np.float32([[0, 0], [759, 0], [759, 619], [0, 619]]),
        np.float32(corners),
    )
    target = cv2.warpPerspective(image, homography, (760, 620))
    transformed = tuple(
        cv2.perspectiveTransform(
            np.asarray([[[point.x, point.y] for point in quad]], dtype=np.float32),
            homography,
        )[0]
        for quad in quads
    )
    return target, transformed


def _frame(image: np.ndarray, *, source_checksum: str = "b" * 64) -> CanonicalSourceFrame:
    height, width = image.shape[:2]
    return CanonicalSourceFrame(
        source=NormalizedSourceImage(
            source_checksum_sha256=source_checksum,
            normalized_pixel_checksum_sha256=rgb_pixel_checksum_sha256(image),
            width=width,
            height=height,
            exif_orientation=1,
            normalization_adapter_version="test-canonical-source-v1",
        ),
        raw_width=width,
        raw_height=height,
        source_mode="RGB",
        orientation_action="identity",
        rgb=image,
    )


def _profile(quads: tuple[tuple[Point, Point, Point, Point], ...]) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "policy": PAGE_REGISTRATION_VERSION,
        "anchors": [
            {
                "sourceChecksumSha256": "a" * 64,
                "imageWidth": 760,
                "imageHeight": 620,
                "quads": [[point.to_dict() for point in quad] for quad in quads],
            }
        ],
    }


def _request(
    frame: CanonicalSourceFrame,
    *,
    active_count: int,
    profile: dict[str, object] | None,
) -> StructuredGeometryInitializationRequest:
    return StructuredGeometryInitializationRequest.for_frame(
        frame,
        topology=LEGACY_IMAGE_BOARD_TOPOLOGY,
        topology_rules_version_id=_TOPOLOGY_RULES_VERSION_ID,
        attested_range=AttestedSequenceRange(start=100, end=99 + active_count),
        geometry_profile=profile,
    )


def _maximum_corner_error(result, expected: tuple[np.ndarray, ...]) -> float:
    errors = []
    for slot, target in zip(result.slots, expected, strict=True):
        actual = np.asarray(
            [[point.x, point.y] for point in slot.initial_quad.corners],
            dtype=np.float32,
        )
        errors.append(float(np.max(np.linalg.norm(actual - target, axis=1))))
    return max(errors)


def _source_quads(
    quads: tuple[tuple[Point, Point, Point, Point], ...],
    *,
    active_count: int,
) -> tuple[SourceQuad, ...]:
    return tuple(
        SourceQuad(
            corners=tuple(SourcePoint(float(point.x), float(point.y)) for point in quad)  # type: ignore[arg-type]
        )
        for quad in quads[:active_count]
    )


def test_v2_uses_exact_checksum_bound_preflight_quads_as_initialization() -> None:
    image, quads = _page(active_count=9)
    frame = _frame(image)
    request = StructuredGeometryInitializationRequest.for_frame(
        frame,
        topology=LEGACY_IMAGE_BOARD_TOPOLOGY,
        topology_rules_version_id=_TOPOLOGY_RULES_VERSION_ID,
        attested_range=AttestedSequenceRange(start=100, end=108),
        pinned_initial_quads=_source_quads(quads, active_count=9),
        pinned_geometry_checksum_sha256="9" * 64,
    )
    engine = StructuredOpenCvGeometryEngine(
        load_anchor_rgb=lambda _checksum: image,
        engine_version=STRUCTURED_OPENCV_PINNED_PREFLIGHT_VERSION,
    )

    result = engine.initialize(frame, request)

    assert result.status is GlobalInitializationStatus.INITIALIZED
    assert result.method is GlobalInitializationMethod.PINNED_PAGE_PREFLIGHT
    assert tuple(slot.initial_quad for slot in result.slots) == request.pinned_initial_quads
    assert result.profile_checksum_sha256 == "9" * 64
    assert result.homography is None

    detected = engine.detect(frame, request)
    assert detected.status is SourceGeometryStatus.READY
    assert all(board.disposition is BoardGeometryDisposition.AUTOMATIC for board in detected.boards)
    assert all(board.final_quad == board.initial_quad for board in detected.boards)
    assert all(board.lines == () for board in detected.boards)
    assert all(board.evidence.pinned_preflight_certified for board in detected.boards)
    assert all(
        board.confidence_components.pinned_preflight_score == 1.0
        for board in detected.boards
    )


def test_v1_refuses_the_new_pinned_preflight_contract() -> None:
    image, quads = _page(active_count=5)
    frame = _frame(image)
    request = StructuredGeometryInitializationRequest.for_frame(
        frame,
        topology=LEGACY_IMAGE_BOARD_TOPOLOGY,
        topology_rules_version_id=_TOPOLOGY_RULES_VERSION_ID,
        attested_range=AttestedSequenceRange(start=100, end=104),
        pinned_initial_quads=_source_quads(quads, active_count=5),
        pinned_geometry_checksum_sha256="8" * 64,
    )
    engine = StructuredOpenCvGeometryEngine(load_anchor_rgb=lambda _checksum: image)

    with pytest.raises(StructuredGeometryInitializationError) as raised:
        engine.initialize(frame, request)

    assert raised.value.code == "IMAGE_STRUCTURED_GEOMETRY_PINNED_PREFLIGHT_VERSION_UNSUPPORTED"


def test_v2_pinned_preflight_still_requires_padded_cell_source_support() -> None:
    image, _quads = _page(active_count=1)
    frame = _frame(image)
    edge_quad = SourceQuad(
        corners=(
            SourcePoint(0.0, 0.0),
            SourcePoint(155.0, 0.0),
            SourcePoint(155.0, 100.0),
            SourcePoint(0.0, 100.0),
        )
    )
    request = StructuredGeometryInitializationRequest.for_frame(
        frame,
        topology=LEGACY_IMAGE_BOARD_TOPOLOGY,
        topology_rules_version_id=_TOPOLOGY_RULES_VERSION_ID,
        attested_range=AttestedSequenceRange(start=100, end=100),
        pinned_initial_quads=(edge_quad,),
        pinned_geometry_checksum_sha256="7" * 64,
    )
    engine = StructuredOpenCvGeometryEngine(
        load_anchor_rgb=lambda _checksum: image,
        engine_version=STRUCTURED_OPENCV_PINNED_PREFLIGHT_VERSION,
    )

    result = engine.detect(frame, request)

    assert result.status is SourceGeometryStatus.NEEDS_MANUAL_CORRECTION
    assert result.boards[0].reason_codes == (BoardGeometryReasonCode.SOURCE_SUPPORT_INCOMPLETE,)


def test_verified_profile_initializes_full_page_at_target_angle() -> None:
    anchor, quads = _page(active_count=9)
    target, expected = _warp(
        anchor,
        quads,
        corners=((18, 13), (742, 28), (756, 607), (7, 594)),
    )
    frame = _frame(target)
    engine = StructuredOpenCvGeometryEngine(load_anchor_rgb=lambda _checksum: anchor)

    result = engine.initialize(frame, _request(frame, active_count=9, profile=_profile(quads)))

    assert result.status is GlobalInitializationStatus.INITIALIZED
    assert result.method is GlobalInitializationMethod.VERIFIED_PROFILE_ORB_RANSAC
    assert result.active_board_slots == tuple(range(9))
    assert len(result.slots) == 9
    assert _maximum_corner_error(result, expected) <= 5.0
    assert result.anchor_source_checksum_sha256 == "a" * 64
    assert result.to_payload()["resultChecksumSha256"] == result.result_checksum_sha256
    assert all("finalQuad" not in slot for slot in result.to_payload()["slots"])


def test_verified_profile_initializes_only_partial_attested_prefix() -> None:
    anchor, quads = _page(active_count=9)
    partial, _ = _page(active_count=5)
    target, expected = _warp(
        partial,
        quads,
        corners=((44, 8), (750, 51), (724, 614), (13, 568)),
    )
    frame = _frame(target, source_checksum="c" * 64)
    engine = StructuredOpenCvGeometryEngine(load_anchor_rgb=lambda _checksum: anchor)

    result = engine.initialize(frame, _request(frame, active_count=5, profile=_profile(quads)))

    assert result.status is GlobalInitializationStatus.INITIALIZED
    assert [slot.slot.position_index for slot in result.slots] == list(range(5))
    assert [slot.slot.sequence_number for slot in result.slots] == list(range(100, 105))
    assert _maximum_corner_error(result, expected[:5]) <= 7.0


def test_verified_profile_breaks_equal_anchor_metrics_by_checksum() -> None:
    anchor, quads = _page(active_count=9)
    frame = _frame(anchor)
    profile = _profile(quads)
    anchors = profile["anchors"]
    assert isinstance(anchors, list)
    anchors.append({**anchors[0], "sourceChecksumSha256": "f" * 64})
    engine = StructuredOpenCvGeometryEngine(load_anchor_rgb=lambda _checksum: anchor)

    result = engine.initialize(frame, _request(frame, active_count=9, profile=profile))

    assert result.status is GlobalInitializationStatus.INITIALIZED
    assert result.anchor_source_checksum_sha256 == "a" * 64


@pytest.mark.parametrize(
    ("active_count", "corners"),
    [
        (9, ((10, 24), (749, 7), (730, 608), (28, 598))),
        (5, ((37, 5), (754, 45), (716, 615), (9, 570))),
    ],
)
def test_generic_frame_line_initialization_without_profile(
    active_count: int,
    corners: tuple[tuple[float, float], ...],
) -> None:
    page, quads = _page(active_count=active_count)
    target, expected = _warp(page, quads, corners=corners)
    frame = _frame(target, source_checksum="d" * 64)
    engine = StructuredOpenCvGeometryEngine(load_anchor_rgb=lambda _checksum: page)

    result = engine.initialize(frame, _request(frame, active_count=active_count, profile=None))

    assert result.status is GlobalInitializationStatus.INITIALIZED
    assert result.method is GlobalInitializationMethod.GENERIC_FRAME_LINES
    assert len(result.slots) == active_count
    assert _maximum_corner_error(result, expected[:active_count]) <= 14.0
    assert result.profile_checksum_sha256 is None


def test_global_initialization_is_deterministic() -> None:
    page, _ = _page(active_count=5)
    target, _ = _warp(
        page,
        _page(active_count=9)[1],
        corners=((21, 19), (742, 30), (749, 602), (12, 591)),
    )
    frame = _frame(target, source_checksum="e" * 64)
    request = _request(frame, active_count=5, profile=None)
    engine = StructuredOpenCvGeometryEngine(load_anchor_rgb=lambda _checksum: page)

    first = engine.initialize(frame, request)
    second = engine.initialize(frame, request)

    assert first.status is GlobalInitializationStatus.INITIALIZED
    assert first.to_payload() == second.to_payload()
    assert first.result_checksum_sha256 == second.result_checksum_sha256


def test_full_engine_returns_one_independent_row_major_quad_per_active_slot() -> None:
    anchor, quads = _page(active_count=9)
    target, _ = _warp(
        anchor,
        quads,
        corners=((18, 13), (742, 28), (756, 607), (7, 594)),
    )
    frame = _frame(target, source_checksum="1" * 64)
    engine = StructuredOpenCvGeometryEngine(load_anchor_rgb=lambda _checksum: anchor)

    result = engine.detect(frame, _request(frame, active_count=9, profile=_profile(quads)))

    assert result.status in {
        SourceGeometryStatus.READY,
        SourceGeometryStatus.NEEDS_MANUAL_REVIEW,
    }
    assert len(result.boards) == 9
    assert all(board.final_quad is not None for board in result.boards)
    assert all(
        BoardGeometryReasonCode.SLOT_ORDER_INVALID not in board.reason_codes
        and BoardGeometryReasonCode.BOARD_OVERLAP_DETECTED not in board.reason_codes
        for board in result.boards
    )
    centres = [
        np.mean(
            np.asarray(
                [[point.x, point.y] for point in board.final_quad.corners],
                dtype=np.float64,
            ),
            axis=0,
        )
        for board in result.boards
        if board.final_quad is not None
    ]
    assert all(centres[index][0] < centres[index + 1][0] for index in (0, 1, 3, 4, 6, 7))
    assert all(centres[index][1] < centres[index + 3][1] for index in range(6))


def test_insufficient_generic_evidence_requires_manual_review() -> None:
    image = np.zeros((620, 760, 3), dtype=np.uint8)
    frame = _frame(image, source_checksum="f" * 64)
    engine = StructuredOpenCvGeometryEngine(load_anchor_rgb=lambda _checksum: image)

    result = engine.initialize(frame, _request(frame, active_count=3, profile=None))

    assert result.status is GlobalInitializationStatus.NEEDS_MANUAL_REVIEW
    assert result.slots == ()
    assert result.homography is None
    assert result.reason_codes == ("generic_frame_line_evidence_insufficient",)
