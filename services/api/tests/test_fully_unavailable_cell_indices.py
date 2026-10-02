from types import SimpleNamespace

from game_predictor_api.storage.image_symbol_review_repository import (
    _fully_unavailable_cell_indices,
)


def _board(unavailable: list[int], qualification: dict[str, object] | None) -> SimpleNamespace:
    return SimpleNamespace(
        grid_rows=3,
        grid_columns=5,
        unavailable_cell_indices=unavailable,
        geometry_qualification=qualification,
        asset_mode="virtual_source",
    )


def test_partially_visible_cells_keep_their_current_crop() -> None:
    board = _board(
        [3, 4],
        {
            "version": "manual-geometry-qualification-v3",
            "exclusionReason": "missing_pixels",
            "completenessStatus": "pending_partial",
            "unavailableCellIndices": [3, 4],
            "fullyUnavailableCellIndices": [4],
            "excludeFromGeometryTraining": True,
            "includeInPartialGridTraining": False,
        },
    )

    assert _fully_unavailable_cell_indices(board) == (4,)  # type: ignore[arg-type]


def test_unqualified_board_uses_the_declared_mask() -> None:
    assert _fully_unavailable_cell_indices(_board([3, 4], None)) == (3, 4)  # type: ignore[arg-type]
