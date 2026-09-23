from __future__ import annotations

import cv2
import numpy as np
import pytest
from game_predictor_worker.images import page_geometry_registration
from game_predictor_worker.images.geometry import Point
from game_predictor_worker.images.page_geometry_registration import (
    PAGE_REGISTRATION_ANCHOR_MASK_PADDING_RATIO,
    PAGE_REGISTRATION_ANCHOR_MASK_VERSION,
    PAGE_REGISTRATION_BOARD_AREA_MASK_VERSION,
    PAGE_REGISTRATION_FEATURES_VERSION,
    PAGE_REGISTRATION_RED_MASK_VERSION,
    PAGE_REGISTRATION_VERSION,
    VerifiedPageRegistrar,
    build_verified_page_registration_profile,
)


def _page() -> tuple[np.ndarray, tuple[tuple[Point, Point, Point, Point], ...]]:
    rng = np.random.default_rng(20260819)
    image = rng.integers(0, 60, size=(620, 760, 3), dtype=np.uint8)
    quads = []
    for row in range(3):
        for column in range(3):
            left = 85 + column * 210
            top = 70 + row * 165
            right, bottom = left + 155, top + 100
            cv2.rectangle(image, (left, top), (right, bottom), (235, 25, 20), 7)
            cv2.putText(
                image,
                f"{row * 3 + column + 1}",
                (left + 65, top + 58),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (255, 255, 255),
                2,
            )
            quads.append(
                (
                    Point(left, top),
                    Point(right, top),
                    Point(right, bottom),
                    Point(left, bottom),
                )
            )
    return image, tuple(quads)


def _profile(quads: tuple[tuple[Point, Point, Point, Point], ...]) -> dict[str, object]:
    return {
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


def _hsv_to_rgb(hue: int, saturation: int, value: int) -> tuple[int, int, int]:
    pixel = np.uint8([[[hue, saturation, value]]])
    rgb = cv2.cvtColor(pixel, cv2.COLOR_HSV2RGB)[0, 0]
    return int(rgb[0]), int(rgb[1]), int(rgb[2])


def test_red_mask_accepts_dark_red_frame_pixels() -> None:
    # D-430: new staging photos have a dark red top-row frame (V approx 40-45).
    # At the previous V>=50 floor every "dark_red_*" sample below would be 0.
    samples: dict[str, tuple[tuple[int, int, int], int]] = {
        "dark_red_low_hue": (_hsv_to_rgb(5, 190, 40), 255),
        "dark_red_high_hue": (_hsv_to_rgb(172, 150, 30), 255),
        "below_value_floor": (_hsv_to_rgb(5, 190, 29), 0),
        "below_saturation_floor": (_hsv_to_rgb(5, 50, 200), 0),
        "blue": (_hsv_to_rgb(110, 200, 200), 0),
    }
    names = list(samples.keys())
    image = np.zeros((1, len(names), 3), dtype=np.uint8)
    for index, name in enumerate(names):
        image[0, index] = samples[name][0]

    mask = page_geometry_registration._red_mask(image)

    for index, name in enumerate(names):
        expected = samples[name][1]
        assert int(mask[0, index]) == expected, name


def test_registration_accepts_dark_top_row_frames_with_baseline_gate() -> None:
    # D-430 regression: a photo whose top-row board frame is a dark red
    # (HSV (3, 200, 40), V=40) rather than the bright anchor red (V=235),
    # matching the reported new-staging photos.  The background here is
    # deliberately achromatic (R=G=B), unlike the shared ``_page()`` fixture's
    # 0-59 RGB noise: that noise occasionally lands inside the red hue/
    # saturation band by chance and inflates coverage regardless of the V
    # floor, which would make this regression test pass even against the old,
    # buggy threshold. With a zero-saturation background only real frame
    # evidence can move coverage.  At the previous V>=50 mask floor the dark
    # frame pixels fall out of the mask and every top-row board's coverage
    # drops under the 0.45 minimum, which was confirmed locally by
    # temporarily restoring the V>=50 floor.
    rng = np.random.default_rng(20260923)
    gray = rng.integers(0, 60, size=(620, 760), dtype=np.uint8)
    anchor = np.repeat(gray[:, :, np.newaxis], 3, axis=2).copy()
    quads = []
    for row in range(3):
        for column in range(3):
            left = 85 + column * 210
            top = 70 + row * 165
            right, bottom = left + 155, top + 100
            cv2.rectangle(anchor, (left, top), (right, bottom), (235, 25, 20), 7)
            cv2.putText(
                anchor,
                f"{row * 3 + column + 1}",
                (left + 65, top + 58),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (255, 255, 255),
                2,
            )
            quads.append(
                (
                    Point(left, top),
                    Point(right, top),
                    Point(right, bottom),
                    Point(left, bottom),
                )
            )
    quads = tuple(quads)

    target = anchor.copy()
    dark_red = _hsv_to_rgb(3, 200, 40)
    for column in range(3):
        left = 85 + column * 210
        top = 70
        right, bottom = left + 155, top + 100
        cv2.rectangle(target, (left, top), (right, bottom), dark_red, 7)
    registrar = VerifiedPageRegistrar(
        _profile(quads),
        load_anchor_rgb=lambda checksum: anchor,
    )

    result = registrar.register(target)

    assert result is not None
    assert result.slot_qualifications is None
    assert all(value >= 0.45 for value in result.board_red_edge_coverages)


def test_registration_payload_pins_red_mask_version() -> None:
    anchor, quads = _page()
    registrar = VerifiedPageRegistrar(
        _profile(quads),
        load_anchor_rgb=lambda checksum: anchor,
    )

    result = registrar.register(anchor.copy())

    assert result is not None
    assert result.to_payload()["redMaskVersion"] == PAGE_REGISTRATION_RED_MASK_VERSION


def test_registration_transforms_all_nine_quads_to_target_specific_geometry() -> None:
    anchor, quads = _page()
    transform = cv2.getPerspectiveTransform(
        np.float32([[0, 0], [759, 0], [759, 619], [0, 619]]),
        np.float32([[17, 11], [747, 22], [754, 608], [6, 600]]),
    )
    target = cv2.warpPerspective(anchor, transform, (760, 620))
    registrar = VerifiedPageRegistrar(
        _profile(quads),
        load_anchor_rgb=lambda checksum: anchor,
    )

    result = registrar.register(target)

    assert result is not None
    assert len(result.quads) == 9
    assert result.inlier_count >= 35
    assert result.mean_red_edge_coverage >= 0.70
    # The same reviewed page was used, but coordinates were transformed to the
    # target's angle rather than copied from the anchor.
    assert result.quads[0] != quads[0]
    assert all(value >= 0.45 for value in result.board_red_edge_coverages)


def test_registration_rejects_a_page_when_one_board_has_no_border_evidence() -> None:
    anchor, quads = _page()
    target = anchor.copy()
    # Erase a large area around the final board while preserving enough texture
    # for ORB to match.  The relaxed red-edge gate accepts a weak board only
    # when it still has some border evidence; a completely missing board must
    # never reach crops.
    cv2.rectangle(target, (480, 380), (730, 600), (0, 0, 0), -1)
    registrar = VerifiedPageRegistrar(
        _profile(quads),
        load_anchor_rgb=lambda checksum: anchor,
    )

    assert registrar.register(target) is None


def test_registration_accepts_a_page_with_one_weak_board_using_relaxed_thresholds() -> None:
    anchor, quads = _page()
    target = anchor.copy()
    # Erase just the final board's interior.  The surrounding red frame remains,
    # so the board clears the relaxed gate but not the strict one.
    cv2.rectangle(target, (500, 400), (710, 580), (0, 0, 0), -1)
    registrar = VerifiedPageRegistrar(
        _profile(quads),
        load_anchor_rgb=lambda checksum: anchor,
    )

    result = registrar.register(target)

    assert result is not None
    assert result.mean_red_edge_coverage >= 0.68
    assert result.slot_qualifications is not None
    assert len(result.slot_qualifications) == 9
    assert all(
        not qualification.exclude_from_geometry_training
        for qualification in result.slot_qualifications[:8]
    )
    assert result.slot_qualifications[8].exclude_from_geometry_training is True


def test_registration_uses_homography_projection_for_the_relaxed_weak_board() -> None:
    # T2/DA-2: the one board that only clears the relaxed D-420 gate keeps
    # the untouched homography projection instead of the snapped quad, since
    # its red-border evidence is too unreliable to trust the bounded snap.
    anchor, quads = _page()
    target = anchor.copy()
    cv2.rectangle(target, (500, 400), (710, 580), (0, 0, 0), -1)
    registrar = VerifiedPageRegistrar(
        _profile(quads),
        load_anchor_rgb=lambda checksum: anchor,
    )

    result = registrar.register(target)

    assert result is not None
    assert result.weak_board_quad_source == "homography_projection"
    assert result.to_payload()["weakBoardQuadSource"] == "homography_projection"
    # This scenario keeps the target pixel-identical to the anchor apart from
    # the erased interior, so the estimated homography is near-identity and
    # every quad (snapped or projected) lands back on the anchor's own quad.
    assert result.quads == quads


def test_registration_fails_closed_when_weak_board_projection_breaks_the_grid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anchor, quads = _page()
    target = anchor.copy()
    cv2.rectangle(target, (500, 400), (710, 580), (0, 0, 0), -1)
    registrar = VerifiedPageRegistrar(
        _profile(quads),
        load_anchor_rgb=lambda checksum: anchor,
    )

    real_is_complete_ordered_grid = page_geometry_registration.is_complete_ordered_grid
    call_count = {"n": 0}

    def flaky_is_complete_ordered_grid(
        quads_arg: object, width: int, height: int
    ) -> bool:
        call_count["n"] += 1
        # Each retry (1000/1500/3000 ORB features) makes exactly two calls:
        # the first validates the snapped grid (must stay real so the page
        # reaches the relaxed-acceptance branch at all) and the second guards
        # the projected weak-board grid, which every retry forces to fail.
        if call_count["n"] % 2 == 0:
            return False
        return bool(real_is_complete_ordered_grid(quads_arg, width, height))  # type: ignore[arg-type]

    monkeypatch.setattr(
        page_geometry_registration,
        "is_complete_ordered_grid",
        flaky_is_complete_ordered_grid,
    )

    evaluation = registrar.evaluate(target)

    assert evaluation.result is None
    assert call_count["n"] >= 2
    reason_codes = {attempt.reason_code for attempt in evaluation.attempts}
    assert "PAGE_GEOMETRY_QUADS_INVALID" in reason_codes


def test_registration_omits_weak_board_quad_source_for_baseline_pages() -> None:
    anchor, quads = _page()
    registrar = VerifiedPageRegistrar(
        _profile(quads),
        load_anchor_rgb=lambda checksum: anchor,
    )

    result = registrar.register(anchor.copy())

    assert result is not None
    assert result.weak_board_quad_source is None
    assert "weakBoardQuadSource" not in result.to_payload()


def test_registration_reports_red_edge_rejection_without_repeating_orb(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anchor, quads = _page()
    target = anchor.copy()
    # Erase enough of the final board that even the relaxed gate cannot accept it.
    cv2.rectangle(target, (480, 380), (730, 600), (0, 0, 0), -1)
    original = page_geometry_registration._orb_features
    calls = 0

    def observed(image: np.ndarray, *, feature_count: int):
        nonlocal calls
        calls += 1
        return original(image, feature_count=feature_count)

    monkeypatch.setattr(page_geometry_registration, "_orb_features", observed)
    registrar = VerifiedPageRegistrar(_profile(quads), load_anchor_rgb=lambda _checksum: anchor)

    evaluation = registrar.evaluate(target)

    assert evaluation.result is None
    payload = evaluation.failure_payload()
    assert payload["reasonCode"] == "PAGE_GEOMETRY_RED_EDGE_COVERAGE_INSUFFICIENT"
    diagnostics = payload["registrationDiagnostics"]
    assert isinstance(diagnostics, dict)
    assert diagnostics["bestAttempt"]["minimumBoardRedEdgeCoverage"] < 0.20
    # One anchor + one target extraction at each configured feature budget.
    assert calls == 6


def test_registration_reports_missing_target_features_without_fake_zero_measurements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anchor, quads = _page()
    original = page_geometry_registration._orb_features
    calls = 0

    def no_target_features(image: np.ndarray, *, feature_count: int):
        nonlocal calls
        calls += 1
        if calls % 2 == 0:
            return (), None
        return original(image, feature_count=feature_count)

    monkeypatch.setattr(page_geometry_registration, "_orb_features", no_target_features)
    registrar = VerifiedPageRegistrar(_profile(quads), load_anchor_rgb=lambda _checksum: anchor)

    payload = registrar.evaluate(anchor).failure_payload()

    assert payload["reasonCode"] == "PAGE_GEOMETRY_TARGET_FEATURES_INSUFFICIENT"
    diagnostics = payload["registrationDiagnostics"]
    assert isinstance(diagnostics, dict)
    assert len(diagnostics["attempts"]) == 3
    assert "inlierCount" not in diagnostics["bestAttempt"]


@pytest.mark.parametrize(
    ("homography", "mask", "expected_reason"),
    [
        (None, None, "PAGE_GEOMETRY_HOMOGRAPHY_INVALID"),
        (
            np.eye(3),
            np.array([[1] * 10 + [0] * 30], dtype=np.uint8).T,
            "PAGE_GEOMETRY_INLIER_EVIDENCE_INSUFFICIENT",
        ),
        (
            np.eye(3),
            np.ones((40, 1), dtype=np.uint8),
            "PAGE_GEOMETRY_REPROJECTION_ERROR_EXCESSIVE",
        ),
    ],
)
def test_anchor_match_reports_the_exact_failed_gate(
    monkeypatch: pytest.MonkeyPatch,
    homography: np.ndarray | None,
    mask: np.ndarray | None,
    expected_reason: str,
) -> None:
    anchor_points = tuple(cv2.KeyPoint(float(index), float(index), 1) for index in range(40))
    target_points = tuple(cv2.KeyPoint(float(index + 10), float(index), 1) for index in range(40))
    matches = [cv2.DMatch(index, index, 0.0) for index in range(40)]
    anchor = page_geometry_registration._Anchor(
        source_checksum_sha256="a" * 64,
        feature_descriptors=np.zeros((40, 32), dtype=np.uint8),
        feature_points=anchor_points,
        quads=(),
    )
    monkeypatch.setattr(page_geometry_registration, "_ratio_matches", lambda *_args: matches)
    monkeypatch.setattr(cv2, "findHomography", lambda *_args: (homography, mask))

    result, diagnostic = page_geometry_registration._evaluate_anchor_match(
        anchor,
        target_points=target_points,
        target_descriptors=np.zeros((40, 32), dtype=np.uint8),
        thresholds=page_geometry_registration.DEFAULT_PAGE_REGISTRATION_THRESHOLDS,
        feature_count=1000,
    )

    assert result is None
    assert diagnostic is not None
    assert diagnostic.reason_code == expected_reason


def test_anchor_match_reports_insufficient_ratio_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keypoints = tuple(cv2.KeyPoint(float(index), float(index), 1) for index in range(40))
    anchor = page_geometry_registration._Anchor(
        source_checksum_sha256="a" * 64,
        feature_descriptors=np.zeros((40, 32), dtype=np.uint8),
        feature_points=keypoints,
        quads=(),
    )
    monkeypatch.setattr(page_geometry_registration, "_ratio_matches", lambda *_args: [])

    result, diagnostic = page_geometry_registration._evaluate_anchor_match(
        anchor,
        target_points=keypoints,
        target_descriptors=np.zeros((40, 32), dtype=np.uint8),
        thresholds=page_geometry_registration.DEFAULT_PAGE_REGISTRATION_THRESHOLDS,
        feature_count=1000,
    )

    assert result is None
    assert diagnostic is not None
    assert diagnostic.reason_code == "PAGE_GEOMETRY_MATCHES_INSUFFICIENT"


def test_final_registration_reports_invalid_projected_grid() -> None:
    _image, quads = _page()
    anchor = page_geometry_registration._Anchor(
        source_checksum_sha256="a" * 64,
        feature_descriptors=np.empty((0, 32), dtype=np.uint8),
        feature_points=(),
        quads=quads,
    )
    match = page_geometry_registration._MatchedAnchor(
        anchor=anchor,
        inlier_count=40,
        inlier_ratio=0.5,
        native_homography=np.array([[1.0, 0.0, 2000.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
        p95_reprojection_error=1.0,
    )
    target = np.zeros((620, 760, 3), dtype=np.uint8)

    result, diagnostic = page_geometry_registration._evaluate_final_registration(
        match,
        target_rgb=target,
        red_mask=np.zeros((620, 760), dtype=np.uint8),
        thresholds=page_geometry_registration.DEFAULT_PAGE_REGISTRATION_THRESHOLDS,
        feature_count=1000,
    )

    assert result is None
    assert diagnostic is not None
    assert diagnostic.reason_code == "PAGE_GEOMETRY_QUADS_INVALID"


def test_registration_caches_anchor_features_between_target_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anchor, quads = _page()
    original = page_geometry_registration._orb_features
    calls = 0

    def observed(image: np.ndarray, *, feature_count: int):
        nonlocal calls
        calls += 1
        return original(image, feature_count=feature_count)

    monkeypatch.setattr(page_geometry_registration, "_orb_features", observed)
    registrar = VerifiedPageRegistrar(
        _profile(quads),
        load_anchor_rgb=lambda _checksum: anchor,
    )

    assert registrar.register(anchor) is not None
    assert registrar.register(anchor) is not None
    # One ORB extraction happens when the reviewed anchor is pinned; each
    # target page then computes only its own half-resolution descriptors.
    assert calls == 3


def test_registration_uses_larger_orb_budget_only_after_primary_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anchor, quads = _page()
    original = page_geometry_registration._orb_features
    requested_counts: list[int] = []

    def primary_without_features(image: np.ndarray, *, feature_count: int):
        requested_counts.append(feature_count)
        # The first primary-budget call builds the reviewed anchor.  Only the
        # target's first 1,000-feature attempt is made deliberately
        # insufficient, so the registrar has a valid profile and must take the
        # bounded fallback path.
        if feature_count == 1000 and len(requested_counts) > 1:
            return (), None
        return original(image, feature_count=feature_count)

    monkeypatch.setattr(page_geometry_registration, "_orb_features", primary_without_features)
    registrar = VerifiedPageRegistrar(
        _profile(quads),
        load_anchor_rgb=lambda _checksum: anchor,
    )

    result = registrar.register(anchor)

    assert result is not None
    assert result.feature_count == 1500
    assert result.to_payload()["featuresVersion"] == PAGE_REGISTRATION_FEATURES_VERSION
    assert requested_counts == [1000, 1000, 1500, 1500]


def test_profile_keeps_only_complete_reviewed_pages() -> None:
    def sample(source: str, position: int) -> dict[str, object]:
        left = 10 + (position % 3) * 100
        top = 20 + (position // 3) * 80
        return {
            "sourceChecksumSha256": source,
            "positionIndex": position,
            "imageWidth": 400,
            "imageHeight": 300,
            "finalQuad": [
                {"x": left, "y": top},
                {"x": left + 70, "y": top},
                {"x": left + 70, "y": top + 50},
                {"x": left, "y": top + 50},
            ],
        }

    profile = build_verified_page_registration_profile(
        {"samples": [*(sample("a" * 64, index) for index in range(9)), sample("b" * 64, 0)]}
    )

    assert profile["policy"] == PAGE_REGISTRATION_VERSION
    assert profile["featuresVersion"] == PAGE_REGISTRATION_FEATURES_VERSION
    assert [anchor["sourceChecksumSha256"] for anchor in profile["anchors"]] == ["a" * 64]


def test_v2_profile_pins_the_selected_36_corner_anchor_order() -> None:
    def samples(source: str) -> list[dict[str, object]]:
        output: list[dict[str, object]] = []
        for position in range(9):
            left = 10 + (position % 3) * 100
            top = 20 + (position // 3) * 80
            output.append(
                {
                    "sourceChecksumSha256": source,
                    "positionIndex": position,
                    "imageWidth": 400,
                    "imageHeight": 300,
                    "finalQuad": [
                        {"x": left, "y": top},
                        {"x": left + 70, "y": top + 2},
                        {"x": left + 68, "y": top + 50},
                        {"x": left + 1, "y": top + 48},
                    ],
                }
            )
        return output

    profile = build_verified_page_registration_profile(
        {"samples": samples("a" * 64) + samples("b" * 64) + samples("c" * 64)},
        anchor_source_checksums=("c" * 64, "a" * 64),
    )

    assert profile["schemaVersion"] == 2
    assert profile["cornerCountPerAnchor"] == 36
    assert profile["anchorSelectionPolicy"] == "geometry-medoid-farthest-point-16-v1"
    assert [anchor["sourceChecksumSha256"] for anchor in profile["anchors"]] == [
        "c" * 64,
        "a" * 64,
    ]


def test_board_area_registration_masks_only_anchor_features(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anchor, quads = _page()
    original = page_geometry_registration._orb_features
    masks: list[np.ndarray | None] = []

    def observed(
        image: np.ndarray,
        *,
        feature_count: int,
        mask: np.ndarray | None = None,
    ):
        masks.append(mask)
        return original(image, feature_count=feature_count, mask=mask)

    monkeypatch.setattr(page_geometry_registration, "_orb_features", observed)
    registrar = VerifiedPageRegistrar(
        {
            **_profile(quads),
            "policy": PAGE_REGISTRATION_BOARD_AREA_MASK_VERSION,
            "anchorMaskVersion": PAGE_REGISTRATION_ANCHOR_MASK_VERSION,
            "anchorMaskPaddingRatio": PAGE_REGISTRATION_ANCHOR_MASK_PADDING_RATIO,
        },
        load_anchor_rgb=lambda _checksum: anchor,
    )

    result = registrar.register(anchor)

    assert result is not None
    assert masks[0] is not None
    assert masks[1] is None
    assert result.registration_version == PAGE_REGISTRATION_BOARD_AREA_MASK_VERSION
    assert result.to_payload()["anchorMaskVersion"] == PAGE_REGISTRATION_ANCHOR_MASK_VERSION


def test_board_area_mask_covers_all_boards_and_excludes_remote_background() -> None:
    _image, quads = _page()

    mask = page_geometry_registration._board_area_anchor_mask((310, 380), quads)

    assert mask.shape == (310, 380)
    assert mask[5, 5] == 0
    for quad in quads:
        center_x = round(sum(point.x for point in quad) / 8)
        center_y = round(sum(point.y for point in quad) / 8)
        assert mask[center_y, center_x] == 255


def test_masked_profile_pins_mask_policy_without_changing_v1_profile() -> None:
    _image, quads = _page()

    def samples(source: str) -> list[dict[str, object]]:
        return [
            {
                "sourceChecksumSha256": source,
                "positionIndex": position,
                "imageWidth": 760,
                "imageHeight": 620,
                "finalQuad": [point.to_dict() for point in quad],
            }
            for position, quad in enumerate(quads)
        ]

    manifest = {"samples": samples("a" * 64)}
    legacy = build_verified_page_registration_profile(manifest)
    masked = build_verified_page_registration_profile(
        manifest,
        registration_version=PAGE_REGISTRATION_BOARD_AREA_MASK_VERSION,
    )

    assert legacy["policy"] == PAGE_REGISTRATION_VERSION
    assert "anchorMaskVersion" not in legacy
    assert masked["policy"] == PAGE_REGISTRATION_BOARD_AREA_MASK_VERSION
    assert masked["anchorMaskVersion"] == PAGE_REGISTRATION_ANCHOR_MASK_VERSION
    assert masked["anchorMaskPaddingRatio"] == PAGE_REGISTRATION_ANCHOR_MASK_PADDING_RATIO
