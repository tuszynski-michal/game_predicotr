from __future__ import annotations

from dataclasses import replace
from io import BytesIO

import cv2
import numpy as np
import pytest
from game_predictor_worker.semi_automatic_selection.middle_row_locator import (
    MIDDLE_ROW_COORDINATE_SPACE,
    CanonicalSourceImage,
    CropCompletenessPolicy,
    ImageDimensions,
    LocalReadabilityPolicy,
    MiddleRowComponentPolicy,
    MiddleRowLatticePrior,
    MiddleRowLocatorConfig,
    MiddleRowLocatorMode,
    MiddleRowTripleLocator,
    canonicalize_source_image,
)
from game_predictor_worker.semi_automatic_selection.middle_row_range import (
    MiddleRowUnknownReason,
)
from PIL import Image


def _jpeg_with_orientation(orientation: int) -> bytes:
    image = Image.new("RGB", (80, 40), (30, 80, 140))
    image.putpixel((2, 3), (255, 255, 255))
    exif = Image.Exif()
    exif[274] = orientation
    output = BytesIO()
    image.save(output, format="JPEG", exif=exif, quality=95)
    return output.getvalue()


@pytest.mark.parametrize("orientation", range(1, 9))
def test_exif_is_applied_once_for_all_orientation_values(orientation: int) -> None:
    source = canonicalize_source_image(_jpeg_with_orientation(orientation))

    expected = (40, 80) if orientation in {5, 6, 7, 8} else (80, 40)
    assert (source.oriented_dimensions.width, source.oriented_dimensions.height) == expected
    assert source.raw_dimensions == ImageDimensions(width=80, height=40)
    assert source.exif_orientation == orientation
    assert source.coordinate_space == MIDDLE_ROW_COORDINATE_SPACE


def _synthetic_grid(
    *,
    missing: set[int] | None = None,
    blur: int = 0,
    perspective_shift: int = 0,
    vertical_offset: int = 0,
    row_slant: int = 0,
    text_overrides: dict[int, str] | None = None,
) -> CanonicalSourceImage:
    width, height = 1_440, 1_920
    rgb = np.full((height, width, 3), (15, 20, 35), dtype=np.uint8)
    x_values = (510, 760, 1_010)
    y_values = (590, 705, 820)
    missing = missing or set()
    text_overrides = text_overrides or {}
    for position in range(9):
        if position in missing:
            continue
        row, column = divmod(position, 3)
        x = x_values[column] + row * perspective_shift
        y = y_values[row] + vertical_offset + column * row_slant
        cv2.putText(
            rgb,
            text_overrides.get(position, str(21_169 + position)),
            (x - 58, y + 12),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.72,
            (245, 245, 245),
            2,
            cv2.LINE_AA,
        )
    if blur > 0:
        kernel = blur | 1
        rgb = cv2.GaussianBlur(rgb, (kernel, kernel), 0)
    dimensions = ImageDimensions(width=width, height=height)
    return CanonicalSourceImage(
        rgb=rgb,
        raw_dimensions=dimensions,
        oriented_dimensions=dimensions,
        exif_orientation=1,
    )


def _locked_prior() -> MiddleRowLatticePrior:
    return MiddleRowLatticePrior(
        column_axes=(510 / 1_440, 760 / 1_440, 1_010 / 1_440),
        row_axes=(590 / 1_920, 705 / 1_920, 820 / 1_920),
        local_scale=0.06,
        local_slant=0,
    )


def test_full_lattice_returns_exactly_three_source_resolution_crops() -> None:
    source = _synthetic_grid()
    result = MiddleRowTripleLocator().locate(source)

    assert result.reason_code is None
    assert result.location is not None
    assert result.location.locator_mode is MiddleRowLocatorMode.FULL_LATTICE
    assert len(result.location.crops) == 3
    assert all(crop.rgb.shape[0] > 20 and crop.rgb.shape[1] > 60 for crop in result.location.crops)
    assert all(crop.complete and crop.readable for crop in result.location.crops)
    assert result.location.crop_boxes[0].right < result.location.crop_boxes[1].left
    assert result.location.crop_boxes[1].right < result.location.crop_boxes[2].left


def test_digit_components_are_grouped_into_nine_complete_labels() -> None:
    locator = MiddleRowTripleLocator()
    thumbnail, _, _ = locator._thumbnail(_synthetic_grid().rgb)

    candidates = locator._candidate_boxes(thumbnail)

    assert len(candidates) == 9
    assert all(candidate.box.width > candidate.box.height * 3 for candidate in candidates)


def test_moderate_perspective_shift_preserves_row_major_middle_row() -> None:
    result = MiddleRowTripleLocator().locate(_synthetic_grid(perspective_shift=12, row_slant=8))

    assert result.location is not None
    assert len(result.location.middle_row_centers) == 3
    assert tuple(sorted(center[0] for center in result.location.middle_row_centers)) == tuple(
        center[0] for center in result.location.middle_row_centers
    )
    assert result.location.middle_row_centers[0][1] < result.location.middle_row_centers[2][1]


def test_bounded_roi_expansion_finds_lattice_near_initial_boundary() -> None:
    result = MiddleRowTripleLocator().locate(_synthetic_grid(vertical_offset=235))

    assert result.location is not None
    assert result.reason_code is None
    assert result.diagnostics["expandedRoi"] is True


@pytest.mark.parametrize("clipped_text", ["1173", "2117"])
def test_inconsistent_label_width_is_rejected_as_possibly_clipped(
    clipped_text: str,
) -> None:
    result = MiddleRowTripleLocator().locate(_synthetic_grid(text_overrides={4: clipped_text}))

    assert result.location is None
    assert result.reason_code is MiddleRowUnknownReason.CROP_POSSIBLY_CLIPPED


def test_insufficient_crop_margin_is_rejected_before_ocr() -> None:
    policy = MiddleRowComponentPolicy(
        completeness=replace(
            CropCompletenessPolicy(),
            minimum_text_margin_ratio=0.45,
        )
    )

    result = MiddleRowTripleLocator(policy).locate(_synthetic_grid())

    assert result.location is None
    assert result.reason_code is MiddleRowUnknownReason.CROP_POSSIBLY_CLIPPED


def test_prior_crop_crossing_source_boundary_is_rejected() -> None:
    width, height = 1_440, 1_920
    rgb = np.full((height, width, 3), (15, 20, 35), dtype=np.uint8)
    x_values = (22, 272, 522)
    for column, x in enumerate(x_values):
        cv2.putText(
            rgb,
            str(21_172 + column),
            (x - 58, 717),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.72,
            (245, 245, 245),
            2,
            cv2.LINE_AA,
        )
    dimensions = ImageDimensions(width=width, height=height)
    source = CanonicalSourceImage(
        rgb=rgb,
        raw_dimensions=dimensions,
        oriented_dimensions=dimensions,
        exif_orientation=1,
    )
    policy = MiddleRowComponentPolicy(
        locator=replace(
            MiddleRowLocatorConfig(),
            minimum_x_ratio=0,
            maximum_x_ratio=0.55,
            minimum_y_ratio=0.30,
            maximum_y_ratio=0.42,
            expanded_maximum_y_ratio=0.42,
        )
    )
    prior = MiddleRowLatticePrior(
        column_axes=tuple(value / width for value in x_values),
        row_axes=(590 / height, 705 / height, 820 / height),
        local_scale=0.06,
        local_slant=0,
    )

    result = MiddleRowTripleLocator(policy).locate(source, prior=prior)

    assert result.location is None
    assert result.reason_code is MiddleRowUnknownReason.CROP_OUT_OF_BOUNDS


def test_two_competing_lattices_are_rejected_as_ambiguous() -> None:
    width, height = 1_440, 1_920
    rgb = np.full((height, width, 3), (15, 20, 35), dtype=np.uint8)
    for base_x, base_y, first_value in ((420, 520, 21_169), (470, 560, 31_169)):
        for position in range(9):
            row, column = divmod(position, 3)
            cv2.putText(
                rgb,
                str(first_value + position),
                (base_x + column * 250 - 58, base_y + row * 115 + 12),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.72,
                (245, 245, 245),
                2,
                cv2.LINE_AA,
            )
    dimensions = ImageDimensions(width=width, height=height)
    source = CanonicalSourceImage(rgb, dimensions, dimensions, 1)

    result = MiddleRowTripleLocator().locate(source)

    assert result.location is None
    assert result.reason_code is MiddleRowUnknownReason.AMBIGUOUS_LATTICE


def test_middle_row_prior_fallback_requires_locked_prior() -> None:
    source = _synthetic_grid(missing={0, 1, 2, 6, 7, 8})
    without_prior = MiddleRowTripleLocator().locate(source)
    with_prior = MiddleRowTripleLocator().locate(source, prior=_locked_prior())

    assert without_prior.location is None
    assert without_prior.reason_code is MiddleRowUnknownReason.UNKNOWN_LATTICE
    assert with_prior.location is not None
    assert with_prior.location.locator_mode is MiddleRowLocatorMode.MIDDLE_ROW_WITH_LOCKED_PRIOR


@pytest.mark.parametrize("missing", [{3}, {4}, {5}])
def test_missing_any_middle_label_is_unknown(missing: set[int]) -> None:
    result = MiddleRowTripleLocator().locate(_synthetic_grid(missing=missing))

    assert result.location is None
    assert result.reason_code in {
        MiddleRowUnknownReason.INCOMPLETE_MIDDLE_ROW,
        MiddleRowUnknownReason.UNKNOWN_LATTICE,
    }


def test_obviously_blurred_middle_row_is_rejected_before_ocr() -> None:
    policy = MiddleRowComponentPolicy(
        readability=replace(LocalReadabilityPolicy(), minimum_tenengrad=20.0)
    )
    result = MiddleRowTripleLocator(policy).locate(_synthetic_grid(blur=31))

    assert result.location is None
    assert result.reason_code in {
        MiddleRowUnknownReason.LOCAL_BLUR,
        MiddleRowUnknownReason.LOW_LOCAL_CONTRAST,
        MiddleRowUnknownReason.UNKNOWN_LATTICE,
    }


def test_locator_fingerprint_is_deterministic_and_configuration_bound() -> None:
    default = MiddleRowTripleLocator()
    changed = MiddleRowTripleLocator(
        MiddleRowComponentPolicy(locator=replace(default.policy.locator, maximum_x_ratio=0.80))
    )

    assert default.fingerprint == MiddleRowTripleLocator().fingerprint
    assert default.fingerprint != changed.fingerprint


def test_locator_module_has_no_paddle_or_board_pipeline_dependency() -> None:
    import game_predictor_worker.semi_automatic_selection.middle_row_locator as module

    names = set(module.__dict__)
    assert not any("paddle" in name.lower() for name in names)
    assert not any("board" in name.lower() for name in names)
    assert not any("symbol" in name.lower() for name in names)
    assert "Path" not in names
