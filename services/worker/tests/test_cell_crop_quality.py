from __future__ import annotations

import cv2
import numpy as np
import pytest
from game_predictor_worker.images.cell_crop_quality import assess_cell_crop


def _crop() -> np.ndarray:
    return np.full((90, 90, 3), (25, 18, 30), dtype=np.uint8)


def test_centered_isolated_symbol_is_eligible() -> None:
    crop = _crop()
    cv2.circle(crop, (45, 45), 23, (250, 190, 25), -1, cv2.LINE_AA)

    quality = assess_cell_crop(
        crop,
        expected_center_x=45,
        expected_center_y=45,
        center_confidence=0.8,
        edge_column=False,
    )

    assert quality.status == "eligible"
    assert quality.training_eligible is True


def test_centered_edge_symbol_is_quarantined_during_bootstrap() -> None:
    crop = _crop()
    cv2.circle(crop, (45, 45), 23, (250, 190, 25), -1, cv2.LINE_AA)

    quality = assess_cell_crop(
        crop,
        expected_center_x=45,
        expected_center_y=45,
        center_confidence=0.8,
        edge_column=True,
    )

    assert quality.status == "uncertain"
    assert quality.reasons == ("CELL_EDGE_COLUMN_BOOTSTRAP_QUARANTINE",)
    assert quality.training_eligible is False


def test_symbol_touching_crop_border_is_clipped() -> None:
    crop = _crop()
    cv2.circle(crop, (10, 45), 24, (250, 190, 25), -1, cv2.LINE_AA)

    quality = assess_cell_crop(
        crop,
        expected_center_x=12,
        expected_center_y=45,
        center_confidence=0.8,
        edge_column=True,
    )

    assert quality.status == "clipped"
    assert "CELL_PRIMARY_TOUCHES_BORDER" in quality.reasons


def test_small_visible_fragment_is_occluded() -> None:
    crop = _crop()
    cv2.circle(crop, (45, 45), 5, (250, 190, 25), -1, cv2.LINE_AA)

    quality = assess_cell_crop(
        crop,
        expected_center_x=45,
        expected_center_y=45,
        center_confidence=0.8,
        edge_column=False,
    )

    assert quality.status == "occluded"


def test_edge_control_next_to_symbol_is_interface_contamination() -> None:
    crop = _crop()
    cv2.circle(crop, (42, 45), 18, (250, 190, 25), -1, cv2.LINE_AA)
    cv2.rectangle(crop, (70, 18), (89, 72), (235, 235, 235), -1)

    quality = assess_cell_crop(
        crop,
        expected_center_x=42,
        expected_center_y=45,
        center_confidence=0.8,
        edge_column=True,
    )

    assert quality.status == "interface_contaminated"


def test_low_center_confidence_is_uncertain() -> None:
    crop = _crop()
    cv2.circle(crop, (45, 45), 23, (250, 190, 25), -1, cv2.LINE_AA)

    quality = assess_cell_crop(
        crop,
        expected_center_x=45,
        expected_center_y=45,
        center_confidence=0.2,
        edge_column=False,
    )

    assert quality.status == "uncertain"


def test_invalid_center_is_rejected() -> None:
    with pytest.raises(ValueError, match="Expected center"):
        assess_cell_crop(
            _crop(),
            expected_center_x=-1,
            expected_center_y=45,
            center_confidence=0.8,
            edge_column=False,
        )
