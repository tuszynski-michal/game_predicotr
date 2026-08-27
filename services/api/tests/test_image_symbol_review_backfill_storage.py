from __future__ import annotations

from unittest.mock import MagicMock

import game_predictor_api.storage.image_symbol_review_backfill_repository as backfill_storage
import pytest
from game_predictor_api.storage.image_symbol_review_backfill_repository import (
    SqlAlchemySymbolCellReviewBackfillRepository,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    _iter_cell_insert_chunks,
)


def test_backfill_splits_two_hundred_boards_below_postgresql_parameter_limit() -> None:
    values = [{"cell_index": index} for index in range(200 * 15)]

    chunks = tuple(_iter_cell_insert_chunks(values))

    assert [len(chunk) for chunk in chunks] == [1_000, 1_000, 1_000]
    assert [value for chunk in chunks for value in chunk] == values


def test_storage_metrics_keep_database_sizes_when_data_directory_is_inaccessible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock()
    session.bind.dialect.name = "postgresql"
    session.scalar.side_effect = [12_345, 6_789, "/unavailable/postgresql/data"]
    monkeypatch.setattr(
        backfill_storage.shutil,
        "disk_usage",
        MagicMock(side_effect=OSError("directory is owned by another host")),
    )

    metrics = SqlAlchemySymbolCellReviewBackfillRepository(session)._storage_metrics()

    assert metrics == (12_345, 6_789, None)
