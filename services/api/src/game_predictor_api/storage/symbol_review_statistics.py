"""PostgreSQL statistics maintenance for the symbol-review read model."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

SYMBOL_REVIEW_QUERY_TABLES = (
    "image_symbol_review_cells",
    "image_board_search_fast_documents",
    "recognized_boards",
    "board_render_manifests",
    "image_symbol_prediction_revisions",
)

_SCHEMA = "game_data_v2"
# Qualified names: the owner session that runs ANALYZE (TASK-0795) does not
# carry the data-plane search_path of a bound game session.
_QUALIFIED_TABLES = tuple(f"{_SCHEMA}.{table}" for table in SYMBOL_REVIEW_QUERY_TABLES)
_ANALYZE_SYMBOL_REVIEW_QUERY_TABLES = text("ANALYZE " + ", ".join(_QUALIFIED_TABLES))
# PostgreSQL silently skips (WARNING only) tables the current role may not
# analyze; count them first so a non-owner refresh fails instead of
# reporting statistics that were never refreshed.
_TABLES_NOT_ANALYZABLE = text(
    """SELECT count(*) FROM unnest(CAST(:tables AS text[])) AS requested(name)
    LEFT JOIN pg_class c ON c.oid = to_regclass(requested.name)
    WHERE c.oid IS NULL OR NOT (
        (SELECT rolsuper FROM pg_roles WHERE rolname = current_user)
        OR pg_has_role(current_user, c.relowner, 'USAGE'))"""
)


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
    cannot expand beyond this read model. ``session`` must belong to the
    schema owner (TASK-0795); the application role is refused explicitly.
    """

    if session.get_bind().dialect.name != "postgresql":
        return ()
    try:
        not_analyzable = int(
            session.execute(
                _TABLES_NOT_ANALYZABLE, {"tables": list(_QUALIFIED_TABLES)}
            ).scalar_one()
        )
        if not_analyzable:
            raise SymbolReviewStatisticsRefreshError(
                "Refreshing symbol-review statistics requires the schema owner role."
            )
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
