"""PostgreSQL statistics maintenance for the symbol-review read model."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

SYMBOL_REVIEW_QUERY_TABLES = (
    "image_symbol_review_cells",
    "image_board_search_fast_documents",
    "recognized_boards",
    "cell_observations",
    "image_symbol_prediction_revisions",
)

_ANALYZE_SYMBOL_REVIEW_QUERY_TABLES = text("ANALYZE " + ", ".join(SYMBOL_REVIEW_QUERY_TABLES))


class SymbolReviewStatisticsRefreshError(RuntimeError):
    """Raised when a complete projection cannot publish usable query statistics."""

    code = "SYMBOL_CELL_REVIEW_STATISTICS_REFRESH_FAILED"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def refresh_symbol_review_query_statistics(session: Session) -> tuple[str, ...]:
    """Refresh planner statistics once after a complete projection build.

    Test databases use another dialect and intentionally remain a no-op. Table
    names are a closed constant rather than input so the maintenance statement
    cannot expand beyond this read model.
    """

    if session.get_bind().dialect.name != "postgresql":
        return ()
    try:
        session.execute(_ANALYZE_SYMBOL_REVIEW_QUERY_TABLES)
    except SQLAlchemyError as error:
        raise SymbolReviewStatisticsRefreshError(
            "PostgreSQL could not refresh symbol-review query statistics."
        ) from error
    return SYMBOL_REVIEW_QUERY_TABLES


__all__ = [
    "SYMBOL_REVIEW_QUERY_TABLES",
    "SymbolReviewStatisticsRefreshError",
    "refresh_symbol_review_query_statistics",
]
