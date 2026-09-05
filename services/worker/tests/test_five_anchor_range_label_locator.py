from __future__ import annotations

import ast
import hashlib
import inspect
import json
from pathlib import Path

import cv2
import numpy as np
from game_predictor_worker.semi_automatic_selection import (
    five_anchor_range_label_locator as locator_module,
)
from game_predictor_worker.semi_automatic_selection.five_anchor_range_label_locator import (
    FIVE_ANCHOR_RANGE_LABEL_COORDINATE_SPACE,
    FiveAnchorLocatorMode,
    FiveAnchorLocatorUnknownReason,
    FiveAnchorPosition,
    FiveAnchorRangeLabelLocator,
)
from PIL import Image

_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "range_ocr_real_v6"


def _portrait_with_anchor_labels() -> np.ndarray:
    image = np.zeros((1_000, 600, 3), dtype=np.uint8)
    locator = FiveAnchorRangeLabelLocator()
    for _position, x_ratio, y_ratio in locator.config.anchor_centers:
        center_x = round(image.shape[1] * x_ratio)
        center_y = round(image.shape[0] * y_ratio)
        cv2.putText(
            image,
            "12345",
            (center_x - 48, center_y + 12),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (245, 245, 245),
            2,
            cv2.LINE_AA,
        )
    return image


def _real_corpus_cases() -> list[dict[str, object]]:
    raw = json.loads((_FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    cases = raw["cases"]
    assert isinstance(cases, list)
    return [case for case in cases if isinstance(case, dict)]


def test_locator_returns_source_direct_crops_for_five_stable_positions() -> None:
    image = _portrait_with_anchor_labels()
    locator = FiveAnchorRangeLabelLocator()

    result = locator.locate(image)

    assert result.reason_code is None
    assert result.location is not None
    assert result.location.fingerprint == locator.fingerprint
    assert tuple(crop.position for crop in result.location.crops) == (
        FiveAnchorPosition.TOP_LEFT,
        FiveAnchorPosition.TOP_RIGHT,
        FiveAnchorPosition.CENTER,
        FiveAnchorPosition.BOTTOM_LEFT,
        FiveAnchorPosition.BOTTOM_RIGHT,
    )
    assert all(crop.complete for crop in result.location.crops)
    assert all(
        crop.mode is FiveAnchorLocatorMode.COMPONENT_REFINED for crop in result.location.crops
    )
    for crop in result.location.crops:
        assert np.array_equal(
            crop.rgb,
            image[crop.box.top : crop.box.bottom, crop.box.left : crop.box.right],
        )
        assert crop.box.left >= 0
        assert crop.box.top >= 0
        assert crop.box.right <= image.shape[1]
        assert crop.box.bottom <= image.shape[0]
    assert result.diagnostics["coordinateSpace"] == FIVE_ANCHOR_RANGE_LABEL_COORDINATE_SPACE


def test_locator_uses_complete_viewport_fallback_without_turning_it_into_a_proof() -> None:
    image = np.zeros((1_000, 600, 3), dtype=np.uint8)
    result = FiveAnchorRangeLabelLocator().locate(image)

    assert result.reason_code is None
    assert result.location is not None
    assert all(
        crop.mode is FiveAnchorLocatorMode.VIEWPORT_FALLBACK for crop in result.location.crops
    )
    assert result.diagnostics["anchorCount"] == 5
    assert "range" not in result.diagnostics
    assert "text" not in result.diagnostics


def test_locator_returns_reason_coded_unknown_for_invalid_or_unsupported_input() -> None:
    locator = FiveAnchorRangeLabelLocator()

    invalid = locator.locate(np.zeros((30, 30), dtype=np.uint8))
    landscape = locator.locate(np.zeros((600, 1_000, 3), dtype=np.uint8))

    assert invalid.location is None
    assert invalid.reason_code is FiveAnchorLocatorUnknownReason.INVALID_RGB
    assert landscape.location is None
    assert landscape.reason_code is FiveAnchorLocatorUnknownReason.UNSUPPORTED_VIEWPORT


def test_locator_keeps_all_five_crops_bounded_after_projective_perturbation() -> None:
    image = _portrait_with_anchor_labels()
    transform = cv2.getPerspectiveTransform(
        np.float32([[0, 0], [599, 0], [599, 999], [0, 999]]),
        np.float32([[12, 10], [582, 0], [599, 999], [0, 987]]),
    )
    perturbed = cv2.warpPerspective(image, transform, (600, 1_000))

    result = FiveAnchorRangeLabelLocator().locate(perturbed)

    assert result.location is not None
    assert result.reason_code is None
    assert len(result.location.crops) == 5
    assert all(crop.complete for crop in result.location.crops)


def test_real_corpus_is_only_checksumming_input_to_the_localizer() -> None:
    locator = FiveAnchorRangeLabelLocator()
    for case in _real_corpus_cases():
        relative_path = case["relativePath"]
        checksum = case["sha256"]
        assert isinstance(relative_path, str)
        assert isinstance(checksum, str)
        path = _FIXTURE_ROOT / relative_path
        assert hashlib.sha256(path.read_bytes()).hexdigest() == checksum
        with Image.open(path) as source:
            rgb = np.asarray(source.convert("RGB"), dtype=np.uint8)

        result = locator.locate(rgb)

        assert result.reason_code is None
        assert result.location is not None
        assert len(result.location.crops) == 5
        for crop in result.location.crops:
            assert np.array_equal(
                crop.rgb,
                rgb[crop.box.top : crop.box.bottom, crop.box.left : crop.box.right],
            )


def test_localizer_has_no_heavy_pipeline_or_filename_dependency() -> None:
    tree = ast.parse(inspect.getsource(locator_module))
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_from_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert imported_modules == {"cv2", "hashlib", "json", "numpy"}
    assert imported_from_modules == {
        "__future__",
        "dataclasses",
        "enum",
        "numpy.typing",
        "typing",
    }
    source = inspect.getsource(locator_module)
    assert "expected_range" not in source
    assert "source_index" not in source
    assert "open(" not in source
    assert "imwrite" not in source
