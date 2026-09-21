from __future__ import annotations

import numpy as np
import pytest
from game_predictor_worker.semi_automatic_selection.v7_label_locator import (
    V7GridLabelLocator,
    V7GridLabelLocatorConfig,
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
