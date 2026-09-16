from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from game_predictor_api.domain.image_geometry_v2 import SourcePoint, SourceQuad
from game_predictor_worker.images.structured_geometry.feasibility_spike import (
    SPIKE_CONFIG_VERSION,
    assess_corpus_readiness,
    config_checksum_sha256,
    config_payload,
    load_feasibility_corpus,
    probe_reference_board_signals,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_INPUT = _REPOSITORY_ROOT / "ai_docs" / "quality" / "structured-geometry-feasibility-input-v1.json"


def _quad() -> SourceQuad:
    return SourceQuad(
        corners=(
            SourcePoint(x=0, y=0),
            SourcePoint(x=499, y=0),
            SourcePoint(x=499, y=299),
            SourcePoint(x=0, y=299),
        )
    )


def _visible_board() -> np.ndarray:
    image = np.full((300, 500, 3), 25, dtype=np.uint8)
    cv2.rectangle(image, (3, 3), (496, 296), (235, 22, 18), 8)
    for column in range(1, 5):
        cv2.line(image, (column * 100, 5), (column * 100, 294), (220, 220, 220), 3)
    for row in range(1, 3):
        cv2.line(image, (5, row * 100), (494, row * 100), (220, 220, 220), 3)
    for row in range(3):
        for column in range(5):
            cv2.circle(
                image,
                (column * 100 + 50, row * 100 + 50),
                25,
                (70 + column * 12, 120 + row * 20, 200),
                5,
            )
    return image


def test_pinned_configuration_is_deterministic_and_explicitly_experimental() -> None:
    first = config_payload()
    second = config_payload()

    assert first == second
    assert first["configVersion"] == SPIKE_CONFIG_VERSION
    assert first["thresholdStatus"] == "experimental_measurement_only"
    assert len(config_checksum_sha256()) == 64


def test_existing_real_corpus_is_accepted_for_measurement_but_not_representative() -> None:
    corpus = load_feasibility_corpus(_INPUT)
    readiness = assess_corpus_readiness(corpus)

    assert len(corpus.images) == 43
    assert sum(len(image.boards) for image in corpus.images) == 387
    assert readiness.ready is False
    assert readiness.game_count == 1
    assert readiness.full_page_count == 43
    assert readiness.partial_page_count == 0
    assert readiness.historical_false_success_count == 1
    assert "multiple_games" in readiness.missing_requirements
    assert "partial_pages" in readiness.missing_requirements
    assert "historical_false_successes" in readiness.missing_requirements
    assert "condition:blur" in readiness.missing_requirements


def test_legacy_comparison_is_bound_only_where_reviewed_geometry_exists() -> None:
    corpus = load_feasibility_corpus(_INPUT)
    compared = [
        board
        for image in corpus.images
        for board in image.boards
        if board.legacy_detected_quad is not None
    ]

    assert len(compared) == 27


def test_signal_probe_observes_frame_lines_periodicity_and_centres() -> None:
    result = probe_reference_board_signals(_visible_board(), _quad())

    assert result.outer_border_score > 0.2
    assert result.hough_vertical_count >= 5
    assert result.hough_horizontal_count >= 3
    assert result.hough_coverage_score >= 0.75
    assert result.vertical_gradient_profile_score > 0.45
    assert result.horizontal_gradient_profile_score > 0.45
    assert result.grid_periodicity_score > 0.85
    assert result.symbol_center_support_score > 0.5


def test_signal_probe_is_deterministic() -> None:
    image = _visible_board()

    first = probe_reference_board_signals(image, _quad()).to_payload()
    second = probe_reference_board_signals(image, _quad()).to_payload()

    assert first == second
    assert first["probeCoordinateSource"] == "human_reference_quad"
