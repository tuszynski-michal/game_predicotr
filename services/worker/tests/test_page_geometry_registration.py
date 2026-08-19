from __future__ import annotations

import cv2
import numpy as np
import pytest
from game_predictor_worker.images import page_geometry_registration
from game_predictor_worker.images.geometry import Point
from game_predictor_worker.images.page_geometry_registration import (
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
    # Erase the final red frame while preserving enough texture for ORB to
    # match.  A page with a synthetic/missing board must never reach crops.
    cv2.rectangle(target, (500, 400), (710, 580), (0, 0, 0), -1)
    registrar = VerifiedPageRegistrar(
        _profile(quads),
        load_anchor_rgb=lambda checksum: anchor,
    )

    assert registrar.register(target) is None


def test_registration_caches_anchor_features_between_target_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anchor, quads = _page()
    original = page_geometry_registration._orb_features
    calls = 0

    def observed(image: np.ndarray):
        nonlocal calls
        calls += 1
        return original(image)

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
    assert [anchor["sourceChecksumSha256"] for anchor in profile["anchors"]] == ["a" * 64]
