"""The symbol-deletion gate counts predictions on the V2 cell projection (D-467, S2)."""

from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

from game_predictor_api.storage.catalog_repository import SqlAlchemyCatalogRepository
from game_predictor_api.storage.models import SymbolModel
from sqlalchemy.dialects import postgresql


class _Session:
    """Returns the symbol, then records every statement the summary executes."""

    def __init__(self, symbol: SymbolModel) -> None:
        self.symbol = symbol
        self.statements: list[str] = []

    def scalar(self, _statement: Any) -> SymbolModel:
        return self.symbol

    def execute(self, statement: Any) -> Any:
        dialect: Any = cast(Any, postgresql).dialect()
        self.statements.append(str(statement.compile(dialect=dialect)))

        class _Result:
            @staticmethod
            def scalar_one() -> int:
                return 0

        return _Result()


def test_prediction_counts_read_only_the_cell_projection() -> None:
    game_id, symbol_id = uuid4(), uuid4()
    symbol = SymbolModel(id=symbol_id, game_id=game_id, code="SIEDEM")
    session = _Session(symbol)

    summary = SqlAlchemyCatalogRepository(cast(Any, session)).symbol_usage_summary(
        game_id=game_id, symbol_id=symbol_id
    )

    assert summary is not None
    assert not any("cell_observations" in sql for sql in session.statements)
    prediction_statements = [sql for sql in session.statements if "prediction_symbol_code" in sql]
    assert len(prediction_statements) == 2
    pending = next(sql for sql in prediction_statements if "image_review_items" in sql)
    everything = next(sql for sql in prediction_statements if "image_review_items" not in sql)
    for sql in (pending, everything):
        assert "image_symbol_review_cells.game_id = " in sql
        assert "image_symbol_review_cells.prediction_symbol_code = " in sql
    assert "image_review_items.game_id = image_symbol_review_cells.game_id" in pending
    assert "image_review_items.id = image_symbol_review_cells.review_item_id" in pending
    assert "image_review_items.status = " in pending
