from __future__ import annotations

from dataclasses import replace

import cv2
import numpy as np
import pytest
from game_predictor_worker.images import page_geometry_registration as registration
from game_predictor_worker.images.geometry import Point
from game_predictor_worker.images.lateral_partial_contract import LateralPartialGeometrySnapshot
from game_predictor_worker.images.structured_geometry import StructuredOpenCvGeometryEngine
from test_page_geometry_registration import _page, _profile
from test_structured_geometry_global_initialization import _frame, _request


@pytest.mark.parametrize("side", ["left", "right"])
def test_lateral_registration_retains_search_evidence_without_more_orb_or_ransac(
    monkeypatch: pytest.MonkeyPatch, side: str
) -> None:
    anchor, quads = _page()
    target = anchor[:, 110:] if side == "left" else anchor[:, :635]
    original_orb = registration._orb_features
    original_homography = cv2.findHomography
    calls = {"orb": 0, "ransac": 0}

    def observed_orb(*args, **kwargs):
        calls["orb"] += 1
        return original_orb(*args, **kwargs)

    def observed_homography(*args, **kwargs):
        calls["ransac"] += 1
        return original_homography(*args, **kwargs)

    monkeypatch.setattr(registration, "_orb_features", observed_orb)
    monkeypatch.setattr(cv2, "findHomography", observed_homography)
    baseline = registration.VerifiedPageRegistrar(_profile(quads), load_anchor_rgb=lambda _: anchor)
    legacy = baseline.evaluate(target)
    baseline_calls = calls.copy()
    calls.update(orb=0, ransac=0)
    variant = registration.VerifiedPageRegistrar(_profile(quads), load_anchor_rgb=lambda _: anchor)
    policy = LateralPartialGeometrySnapshot(frame_support_review=True)
    result = variant.evaluate(target, lateral_partial_policy=policy)

    assert result.result is legacy.result is None
    assert calls == baseline_calls == {"orb": 6, "ransac": 3}
    assert result.attempts == legacy.attempts
    candidate = result.lateral_candidate
    assert candidate is not None
    assert candidate.initialization.active_board_slots == tuple(range(9))
    assert len(candidate.initialization.initialization_quads) == 9
    assert candidate.policy_checksum_sha256 == policy.checksum_sha256
    payload = candidate.to_payload()
    assert len(payload["analysisQuads"]) == 9
    assert "finalQuad" not in payload and "quads" not in payload
    assert payload["origin"] == "automatic_search_proposal"
    assert payload["requiresLocalRefinement"] is True
    assert result.failure_payload()["lateralRegistrationCandidate"] == payload
    assert "lateralRegistrationCandidate" not in legacy.failure_payload()
    # Original projected coordinates remain outside the source, not clamped.
    xs = [p.x for quad in candidate.initialization.initialization_quads for p in quad]
    assert min(xs) < 0 if side == "left" else max(xs) >= target.shape[1]


def test_full_registration_is_unchanged_and_does_not_return_partial_candidate() -> None:
    anchor, quads = _page()
    baseline = registration.VerifiedPageRegistrar(_profile(quads), load_anchor_rgb=lambda _: anchor)
    candidate = registration.VerifiedPageRegistrar(
        _profile(quads), load_anchor_rgb=lambda _: anchor
    )
    expected = baseline.evaluate(anchor)
    actual = candidate.evaluate(
        anchor,
        lateral_partial_policy=LateralPartialGeometrySnapshot(frame_support_review=True),
    )
    assert actual.result is not None
    assert actual == expected
    assert actual.result.to_payload() == expected.result.to_payload()
    assert actual.lateral_candidate is None


@pytest.mark.parametrize(
    "coverages,weak_slots",
    [
        ((0.3525, 0.9745, 0.8742, 0.8980, 0.9458, 1.0, 1.0, 1.0, 0.9326), (0,)),
        ((0.6250, 0.9193, 0.8616, 0.9139, 0.9281, 0.8922, 0.9935, 1.0, 1.0), (0,)),
        ((0.4245, 0.9688, 0.9136, 0.9592, 0.8503, 0.9118, 1.0, 1.0, 0.9663), (0,)),
    ],
)
def test_visible_grid_with_weak_frame_is_retained_for_review(
    coverages: tuple[float, ...], weak_slots: tuple[int, ...]
) -> None:
    anchor, quads = _page()
    registrar = registration.VerifiedPageRegistrar(
        _profile(quads), load_anchor_rgb=lambda _: anchor
    )
    match = registrar._matched_candidates(registration._half_gray(anchor), feature_count=1000)[0]
    candidate = registration._frame_support_search_candidate(
        match,
        quads=quads,
        coverages=coverages,
        thresholds=registration.DEFAULT_PAGE_REGISTRATION_THRESHOLDS,
        feature_count=1000,
        policy=LateralPartialGeometrySnapshot(frame_support_review=True),
        active_board_slots=tuple(range(9)),
        target_width=anchor.shape[1],
        target_height=anchor.shape[0],
        registration_version=registration.PAGE_REGISTRATION_VERSION,
        anchor_mask_version=None,
        anchor_mask_padding_ratio=None,
    )
    assert candidate is not None
    assert candidate.recovery_kind == "frame_support_review"
    assert candidate.review_required_slots == weak_slots
    assert candidate.initialization.initialization_quads == quads


@pytest.mark.parametrize(
    "coverages",
    [
        (0.29, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0),
        (0.60, 0.60, 0.60, 0.60, 1.0, 1.0, 1.0, 1.0, 1.0),
        (0.31, 0.31, 0.31, 0.65, 0.65, 0.65, 0.65, 0.65, 0.65),
    ],
)
def test_weak_frame_recovery_keeps_global_support_gates(
    coverages: tuple[float, ...]
) -> None:
    anchor, quads = _page()
    registrar = registration.VerifiedPageRegistrar(
        _profile(quads), load_anchor_rgb=lambda _: anchor
    )
    match = registrar._matched_candidates(registration._half_gray(anchor), feature_count=1000)[0]
    assert registration._frame_support_search_candidate(
        match,
        quads=quads,
        coverages=coverages,
        thresholds=registration.DEFAULT_PAGE_REGISTRATION_THRESHOLDS,
        feature_count=1000,
        policy=LateralPartialGeometrySnapshot(frame_support_review=True),
        active_board_slots=tuple(range(9)),
        target_width=anchor.shape[1],
        target_height=anchor.shape[0],
        registration_version=registration.PAGE_REGISTRATION_VERSION,
        anchor_mask_version=None,
        anchor_mask_padding_ratio=None,
    ) is None


@pytest.mark.parametrize("case", ["top", "bottom", "missing_board", "missing_frame"])
def test_incomplete_evidence_does_not_create_lateral_proposal(case: str) -> None:
    anchor, quads = _page()
    target = anchor[:, 110:].copy()
    if case == "top":
        target = target[80:]
    elif case == "bottom":
        target = target[:490]
    elif case == "missing_board":
        target = anchor[:, 250:]
    else:
        cv2.rectangle(target, (390, 400), (600, 580), (0, 0, 0), -1)
    registrar = registration.VerifiedPageRegistrar(
        _profile(quads), load_anchor_rgb=lambda _: anchor
    )
    result = registrar.evaluate(target, lateral_partial_policy=LateralPartialGeometrySnapshot())
    assert result.result is None
    assert result.lateral_candidate is None


def test_terminal_prefix_contains_only_filename_attested_slots() -> None:
    anchor, quads = _page()
    registrar = registration.VerifiedPageRegistrar(
        _profile(quads), load_anchor_rgb=lambda _: anchor
    )
    result = registrar.evaluate(
        anchor[:, 110:],
        lateral_partial_policy=LateralPartialGeometrySnapshot(),
        active_board_slots=range(5),
    )
    assert result.result is None
    assert result.lateral_candidate is not None
    assert result.lateral_candidate.initialization.active_board_slots == (0, 1, 2, 3, 4)
    assert len(result.lateral_candidate.initialization.initialization_quads) == 5


@pytest.mark.parametrize("slots", [(), (1, 2), (0, 2), tuple(range(10)), (False,)])
def test_unknown_or_incomplete_slot_numbering_is_rejected(slots) -> None:
    anchor, quads = _page()
    registrar = registration.VerifiedPageRegistrar(
        _profile(quads), load_anchor_rgb=lambda _: anchor
    )
    with pytest.raises(ValueError, match="attested row-major prefix"):
        registrar.evaluate(
            anchor,
            lateral_partial_policy=LateralPartialGeometrySnapshot(),
            active_board_slots=slots,
        )


@pytest.mark.parametrize("case", ["order", "overlap", "vertical", "whole_missing", "excessive"])
def test_lateral_grid_does_not_relax_other_geometry_gates(case: str) -> None:
    _, quads = _page()
    shifted = [tuple(Point(p.x - 110, p.y) for p in quad) for quad in quads]
    if case == "order":
        shifted[0], shifted[1] = shifted[1], shifted[0]
    elif case == "overlap":
        shifted[1] = tuple(Point(p.x + 40, p.y) for p in shifted[0])
    elif case == "vertical":
        shifted[0] = tuple(Point(p.x, p.y - 80) for p in shifted[0])
    elif case == "whole_missing":
        shifted[0] = tuple(Point(p.x - 160, p.y) for p in shifted[0])
    else:
        shifted[0] = (Point(-700, 70), *shifted[0][1:])
    assert not registration._is_lateral_ordered_grid(tuple(shifted), tuple(range(9)), 650, 620)


@pytest.mark.parametrize("case", ["singular", "horizon", "nan", "inliers", "ratio", "residual"])
def test_lateral_capture_requires_valid_matching_and_projective_support(case: str) -> None:
    anchor, quads = _page()
    registrar = registration.VerifiedPageRegistrar(
        _profile(quads), load_anchor_rgb=lambda _: anchor
    )
    target = anchor[:, 110:]
    match = registrar._matched_candidates(registration._half_gray(target), feature_count=1000)[0]
    projected = tuple(registration._transform_quad(q, match.native_homography) for q in quads)
    if case == "singular":
        match = replace(match, native_homography=np.zeros((3, 3), dtype=np.float64))
    elif case == "horizon":
        value = match.native_homography.copy()
        value[2] = [1.0, 0.0, -300.0]
        match = replace(match, native_homography=value)
    elif case == "nan":
        match = replace(match, native_homography=np.full((3, 3), np.nan))
    elif case == "inliers":
        match = replace(match, inlier_count=34)
    elif case == "ratio":
        match = replace(match, inlier_ratio=0.22)
    else:
        match = replace(match, p95_reprojection_error=2.51)
    assert (
        registration._lateral_search_candidate(
            match,
            projected_quads=projected,
            quads=projected,
            red_neighbourhood=registration._red_mask(target),
            thresholds=registration.DEFAULT_PAGE_REGISTRATION_THRESHOLDS,
            feature_count=1000,
            policy=LateralPartialGeometrySnapshot(),
            active_board_slots=tuple(range(9)),
            registration_version=registration.PAGE_REGISTRATION_VERSION,
            anchor_mask_version=None,
            anchor_mask_padding_ratio=None,
        )
        is None
    )


def test_no_anchor_preserves_empty_evidence_instead_of_synthesizing_missing_slots() -> None:
    anchor, _ = _page()
    registrar = registration.VerifiedPageRegistrar(None, load_anchor_rgb=lambda _: anchor)
    actual = registrar.evaluate(anchor, lateral_partial_policy=LateralPartialGeometrySnapshot())
    assert actual == registrar.evaluate(anchor)
    assert actual.result is None and actual.lateral_candidate is None


@pytest.mark.parametrize("count", [5, 9])
def test_missing_initialization_keeps_every_attested_slot_for_manual_correction(count: int) -> None:
    image = np.zeros((620, 760, 3), dtype=np.uint8)
    frame = _frame(image)
    request = _request(frame, active_count=count, profile=None)
    engine = StructuredOpenCvGeometryEngine(load_anchor_rgb=lambda _: image)
    result = engine.detect(frame, request)
    assert len(result.boards) == count
    assert [board.slot.sequence_number for board in result.boards] == list(range(100, 100 + count))
    assert all(board.final_quad is None for board in result.boards)
