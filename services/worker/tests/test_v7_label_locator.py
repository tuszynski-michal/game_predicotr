from __future__ import annotations

import cv2
import numpy as np
import pytest
from game_predictor_worker.semi_automatic_selection.v7_label_locator import (
    V7DynamicGridLabelLocator,
    V7DynamicGridLabelLocatorConfig,
    V7GridLabelLocator,
    V7GridLabelLocatorConfig,
    _find_complete_lattice,
    _TextBox,
    recognize_grid_labels,
)


class _Recognition:
    def __init__(self, raw_text: str, confidence: float) -> None:
        self.raw_text = raw_text
        self.confidence = confidence


class _Recognizer:
    def __init__(self, values: tuple[_Recognition, ...]) -> None:
        self.values = values

    def recognize_many(self, crops: list[np.ndarray]) -> tuple[_Recognition, ...]:
        assert len(crops) == len(self.values)
        return self.values


def test_locator_returns_nine_source_local_crops_for_landscape_page() -> None:
    source = np.zeros((100, 140, 3), dtype=np.uint8)

    crops = V7GridLabelLocator().locate(source)

    assert len(crops) == 9
    assert tuple(crop.position_index for crop in crops) == tuple(range(9))
    assert all(crop.complete for crop in crops)


def test_recognizer_keeps_only_positive_decimal_own_labels() -> None:
    source = np.zeros((100, 140, 3), dtype=np.uint8)
    values = tuple(
        _Recognition(value, 0.98)
        for value in ("1", "002", "not-a-number", "0", "5", "6", "7", "8", "9")
    )

    evidence = recognize_grid_labels(source, _Recognizer(values))

    assert [(item.position_index, item.sequence_number) for item in evidence] == [
        (0, 1),
        (1, 2),
        (4, 5),
        (5, 6),
        (6, 7),
        (7, 8),
        (8, 9),
    ]
    assert all(item.position_confidence == 0.0 for item in evidence)


def test_recognizer_requires_a_calibrated_locator_before_positions_can_be_reliable() -> None:
    source = np.zeros((100, 140, 3), dtype=np.uint8)
    recognizer = _Recognizer(tuple(_Recognition(str(position + 1), 0.98) for position in range(9)))
    locator = V7GridLabelLocator(V7GridLabelLocatorConfig(position_confidence=0.96))

    evidence = recognize_grid_labels(source, recognizer, locator=locator)

    assert all(item.position_confidence == 0.96 for item in evidence)


def test_locator_rejects_invalid_viewport_and_contract_errors() -> None:
    assert V7GridLabelLocator().locate(np.zeros((100, 30, 3), dtype=np.uint8)) == ()
    with pytest.raises(ValueError, match="configuration"):
        V7GridLabelLocatorConfig(width_ratios=(0.14,) * 8)
    with pytest.raises(ValueError, match="configuration"):
        V7GridLabelLocatorConfig(position_confidence=1.01)
    with pytest.raises(ValueError, match="invalid v7 label contract"):
        recognize_grid_labels(
            np.zeros((100, 140, 3), dtype=np.uint8),
            _Recognizer(tuple(_Recognition("1", True) for _ in range(9))),
        )


def _dynamic_grid_source(*, inverted: bool = False, duplicate: bool = False) -> np.ndarray:
    source = np.full((360, 560, 3), 235 if inverted else 18, dtype=np.uint8)
    foreground = (12, 12, 12) if inverted else (248, 248, 248)
    destination = np.asarray([[110, 104], [432, 86], [461, 272], [86, 294]], dtype=np.float32)
    transform = cv2.getPerspectiveTransform(
        np.asarray([[0, 0], [2, 0], [2, 2], [0, 2]], dtype=np.float32), destination
    )
    points = cv2.perspectiveTransform(
        np.asarray([[(column, row) for row in range(3) for column in range(3)]], dtype=np.float32),
        transform,
    )[0]
    for position, (x, y) in enumerate(points):
        cv2.putText(
            source,
            f"{position + 101:06d}",
            (round(x - 42), round(y + 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            foreground,
            2,
            cv2.LINE_AA,
        )
    if duplicate:
        for position, (x, y) in enumerate(points):
            cv2.putText(
                source,
                f"{position + 201:06d}",
                (round(x - 35), round(y + 58)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                foreground,
                2,
                cv2.LINE_AA,
            )
    return source


@pytest.mark.parametrize("inverted", [False, True])
def test_dynamic_locator_normalizes_a_translated_perspective_grid_without_colour_rules(
    inverted: bool,
) -> None:
    crops = V7DynamicGridLabelLocator(
        V7DynamicGridLabelLocatorConfig(position_confidence=0.95)
    ).locate(_dynamic_grid_source(inverted=inverted))

    assert tuple(crop.position_index for crop in crops) == tuple(range(9))
    assert all(crop.complete and crop.rgb.size > 0 for crop in crops)


def test_dynamic_locator_fails_closed_for_no_or_ambiguous_lattice() -> None:
    locator = V7DynamicGridLabelLocator()

    assert locator.locate(np.zeros((360, 560, 3), dtype=np.uint8)) == ()
    assert locator.locate(_dynamic_grid_source(duplicate=True)) == ()


def _boxes_for_centers(points: list[tuple[int, int]]) -> tuple[_TextBox, ...]:
    return tuple(_TextBox(x - 5, y - 5, x + 5, y + 5) for x, y in points)


def test_dynamic_lattice_rejects_a_distinct_competitor_hidden_by_duplicate_hypotheses() -> None:
    first = [(100 + 160 * column, 100 + 90 * row) for row in range(3) for column in range(3)]
    second = [(120 + 160 * column, 135 + 90 * row) for row in range(3) for column in range(3)]
    candidates = _boxes_for_centers(first + second + [(260, 100)])

    assert _find_complete_lattice(candidates, (400, 600), 0.08, 0.10) is None


def test_dynamic_lattice_rejects_the_only_bad_reprojection() -> None:
    candidates = _boxes_for_centers(
        [
            (100, 100),
            (260, 100),
            (420, 100),
            (100, 190),
            (290, 210),
            (420, 190),
            (100, 280),
            (260, 280),
            (450, 310),
        ]
    )

    assert _find_complete_lattice(candidates, (400, 600), 0.08, 0.10) is None
