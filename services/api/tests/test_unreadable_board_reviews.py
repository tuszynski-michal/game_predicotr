from __future__ import annotations

from uuid import uuid4

import pytest
from game_predictor_api.application.unreadable_board_reviews import (
    UnreadableBoardReviewView,
    decode_unreadable_board_cursor,
    encode_unreadable_board_cursor,
)
from game_predictor_api.domain.image_symbol_reviews import SymbolCellReviewError


def test_unreadable_board_cursor_is_scoped_to_game_and_view() -> None:
    game_id = uuid4()
    review_item_id = uuid4()
    cursor = encode_unreadable_board_cursor(
        game_id=game_id,
        view=UnreadableBoardReviewView.PENDING,
        key=(41, str(review_item_id)),
    )

    assert decode_unreadable_board_cursor(
        cursor,
        game_id=game_id,
        view=UnreadableBoardReviewView.PENDING,
    ) == (41, str(review_item_id))

    with pytest.raises(SymbolCellReviewError) as wrong_game:
        decode_unreadable_board_cursor(
            cursor,
            game_id=uuid4(),
            view=UnreadableBoardReviewView.PENDING,
        )
    assert wrong_game.value.code == "UNREADABLE_BOARD_REVIEW_CURSOR_INVALID"

    with pytest.raises(SymbolCellReviewError) as wrong_view:
        decode_unreadable_board_cursor(
            cursor,
            game_id=game_id,
            view=UnreadableBoardReviewView.ALL,
        )
    assert wrong_view.value.code == "UNREADABLE_BOARD_REVIEW_CURSOR_INVALID"


@pytest.mark.parametrize("cursor", ["not-base64", "e30", ""])
def test_unreadable_board_cursor_rejects_invalid_payload(cursor: str) -> None:
    with pytest.raises(SymbolCellReviewError) as invalid:
        decode_unreadable_board_cursor(
            cursor,
            game_id=uuid4(),
            view=UnreadableBoardReviewView.PENDING,
        )
    assert invalid.value.code == "UNREADABLE_BOARD_REVIEW_CURSOR_INVALID"
