from __future__ import annotations

from uuid import uuid4

from game_predictor_api.domain.image_reviews import ImageReviewCell
from game_predictor_api.storage.image_symbol_review_repository import (
    _incompatible_prediction_codes,
)


def _cell(symbol_code: str) -> ImageReviewCell:
    return ImageReviewCell(
        observation_id=uuid4(),
        cell_index=0,
        row_index=0,
        column_index=0,
        crop_sample_id="crop",
        crop_relative_path="crops/cell.jpg",
        crop_checksum_sha256="a" * 64,
        predicted_symbol_code=symbol_code,
        confidence=0.9,
        alternatives=(),
        current_symbol_code=symbol_code,
    )


def test_trained_prediction_rejects_codes_outside_active_game_catalog() -> None:
    active_symbol_id = uuid4()

    incompatible = _incompatible_prediction_codes(
        cells=(_cell("WISNIA"), _cell("cherries")),
        active_symbol_ids={"WISNIA": active_symbol_id},
        model_iteration_id=uuid4(),
    )

    assert incompatible == ("cherries",)


def test_historical_bootstrap_prediction_remains_readable_as_unknown() -> None:
    incompatible = _incompatible_prediction_codes(
        cells=(_cell("cherries"),),
        active_symbol_ids={"WISNIA": uuid4()},
        model_iteration_id=None,
    )

    assert incompatible == ()
