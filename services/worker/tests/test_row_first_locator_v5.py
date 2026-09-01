from __future__ import annotations

from dataclasses import replace

import cv2
import numpy as np
from game_predictor_worker.semi_automatic_selection.middle_row_locator import (
    BoundingBox,
    CanonicalSourceImage,
    ImageDimensions,
)
from game_predictor_worker.semi_automatic_selection.range_proof_v5 import RangeRowOffset
from game_predictor_worker.semi_automatic_selection.row_first_locator_v5 import (
    RowFirstLocatorConfig,
    RowFirstLocatorUnknownReason,
    RowFirstPositionPrior,
    RowFirstTripleLocator,
)


def _source(
    *,
    hidden_rows: set[int] | None = None,
    row_slant: int = 0,
    perspective_shift: int = 0,
    extra_rows: tuple[tuple[int, int], ...] = (),
) -> CanonicalSourceImage:
    width, height = 1_440, 1_920
    rgb = np.full((height, width, 3), (15, 20, 35), dtype=np.uint8)
    x_values = (510, 760, 1_010)
    y_values = (590, 705, 820)
    for row, y in enumerate(y_values):
        if row in (hidden_rows or set()):
            continue
        for column, x in enumerate(x_values):
            cv2.putText(
                rgb,
                str(21_169 + row * 3 + column),
                (x + row * perspective_shift - 54, y + column * row_slant + 12),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.72,
                (245, 245, 245),
                2,
                cv2.LINE_AA,
            )
    for y, first in extra_rows:
        for column, x in enumerate((85, 265, 445)):
            cv2.putText(
                rgb,
                str(first + column),
                (x - 36, y + 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.54,
                (245, 245, 245),
                2,
                cv2.LINE_AA,
            )
    dimensions = ImageDimensions(width=width, height=height)
    return CanonicalSourceImage(
        rgb=rgb,
        raw_dimensions=dimensions,
        oriented_dimensions=dimensions,
        exif_orientation=1,
    )


def test_two_visible_rows_are_independent_without_a_full_lattice() -> None:
    result = RowFirstTripleLocator().locate(
        _source(hidden_rows={0}),
        prior=RowFirstPositionPrior(row_axes=(0.31, 0.37, 0.43)),
    )

    assert result.reason_code is None
    assert result.location is not None
    assert tuple(row.row for row in result.location.rows) == (
        RangeRowOffset.MIDDLE,
        RangeRowOffset.BOTTOM,
    )
    assert all(len(row.crops) == 3 for row in result.location.rows)
    assert all(crop.complete for row in result.location.rows for crop in row.crops)


def test_perspective_and_uneven_row_gaps_keep_three_row_hypotheses() -> None:
    result = RowFirstTripleLocator().locate(_source(row_slant=11, perspective_shift=13))

    assert result.reason_code is None
    assert result.location is not None
    assert tuple(row.row for row in result.location.rows) == tuple(RangeRowOffset)
    assert all(abs(row.baseline_slope) > 0 for row in result.location.rows)


def test_wide_number_control_component_is_split_at_a_defensible_valley() -> None:
    locator = RowFirstTripleLocator()
    mask = np.zeros((70, 280), dtype=np.uint8)
    mask[20:46, 40:150] = 255
    mask[20:46, 178:234] = 255
    box = locator._split_wide_component(  # noqa: SLF001 - focused morphology contract
        # The initial component mimics a number joined to a side control after
        # horizontal morphology; the empty valley is the only safe split point.
        BoundingBox(40, 20, 234, 46),
        mask,
        area=int(np.count_nonzero(mask)),
    )

    assert len(box) == 2
    assert box[0].box.right <= box[1].box.left
    assert box[0].box.width >= 90


def test_hand_obscuring_one_row_leaves_other_two_available() -> None:
    result = RowFirstTripleLocator().locate(_source(hidden_rows={1}))

    assert result.reason_code is None
    assert result.location is not None
    assert tuple(row.row for row in result.location.rows) == (
        RangeRowOffset.TOP,
        RangeRowOffset.BOTTOM,
    )


def test_triplets_outside_the_panel_roi_do_not_make_rows() -> None:
    result = RowFirstTripleLocator().locate(
        _source(hidden_rows={0, 1, 2}, extra_rows=((1_600, 31_000),))
    )

    assert result.location is None
    assert result.reason_code is RowFirstLocatorUnknownReason.UNKNOWN_ROWS


def test_locked_position_prior_only_maps_geometry_and_can_reject_mismatch() -> None:
    matching = RowFirstPositionPrior(row_axes=(0.31, 0.37, 0.43))
    mismatched = RowFirstPositionPrior(row_axes=(0.05, 0.10, 0.15))

    resolved = RowFirstTripleLocator().locate(_source(hidden_rows={0}), prior=matching)
    rejected = RowFirstTripleLocator().locate(_source(hidden_rows={0}), prior=mismatched)

    assert resolved.location is not None
    assert rejected.location is None
    assert rejected.reason_code is RowFirstLocatorUnknownReason.POSITION_PRIOR_MISMATCH


def test_configuration_fingerprint_is_deterministic_and_bound_to_roi_policy() -> None:
    default = RowFirstTripleLocator()
    changed = RowFirstTripleLocator(replace(RowFirstLocatorConfig(), minimum_x_ratio=0.18))

    assert default.fingerprint == RowFirstTripleLocator().fingerprint
    assert default.fingerprint != changed.fingerprint


def test_locator_has_no_ocr_or_pipeline_dependency() -> None:
    import game_predictor_worker.semi_automatic_selection.row_first_locator_v5 as module

    names = set(module.__dict__)
    assert not any("paddle" in name.lower() for name in names)
    assert not any("symbol" in name.lower() for name in names)
    assert "Path" not in names
