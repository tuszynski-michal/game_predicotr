"""Bounded SQL ranking of consecutive positions in the existing fast projection."""

from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Numeric, and_, case, func, literal, or_, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql.elements import ColumnElement

from game_predictor_api.domain.board_search import (
    BoardSearchAssetMode,
    BoardSearchError,
    BoardSearchQueryCell,
    BoardSearchResult,
    BoardSearchScope,
    BoardSearchScore,
)
from game_predictor_api.domain.board_search_sequence import (
    BoardSearchSequenceError,
    BoardSearchSequenceResult,
    validate_sequence_length,
)
from game_predictor_api.domain.catalog import SymbolStatus
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.models import (
    GameModel,
    ImageBoardSearchFastDocumentModel,
    SymbolModel,
)

_SCORE_FIELDS = (
    "score",
    "exact_match_count",
    "alternative_match_count",
    "weighted_alternative_score",
    "mismatch_count",
    "unknown_count",
)
_BOARD_FIELDS = (
    "review_item_id",
    "recognized_board_id",
    "import_job_id",
    "sequence_number",
    "status",
    "board_checksum_sha256",
)


def _score(row: Mapping[str, Any], prefix: str, wildcard: bool) -> BoardSearchScore:
    return BoardSearchScore(
        score=float(row[prefix + "score"]),
        exact_match_count=int(row[prefix + "exact_match_count"]),
        alternative_match_count=int(row[prefix + "alternative_match_count"]),
        weighted_alternative_score=float(row[prefix + "weighted_alternative_score"]),
        mismatch_count=int(row[prefix + "mismatch_count"]),
        unknown_count=int(row[prefix + "unknown_count"]),
        unknown_matches_all=wildcard,
    )


def _rank_with_timeout(session: Session, statement: Any) -> list[Mapping[str, Any]]:
    previous = str(session.execute(text("SHOW statement_timeout")).scalar_one())
    previous_ms = int(
        session.execute(
            text("SELECT setting FROM pg_settings WHERE name = 'statement_timeout'")
        ).scalar_one()
    )
    timeout = min(previous_ms, 10000) if previous_ms else 10000
    try:
        with session.begin_nested():
            session.execute(
                text("SELECT set_config('statement_timeout', :value, true)"),
                {"value": str(timeout)},
            )
            rows = session.execute(statement).mappings().all()
            session.execute(
                text("SELECT set_config('statement_timeout', :value, true)"), {"value": previous}
            )
            return [dict(row) for row in rows]
    except DBAPIError as error:
        if getattr(error.orig, "sqlstate", None) == "57014":
            raise BoardSearchSequenceError(
                "BOARD_SEARCH_SEQUENCE_TIMEOUT", "Sequence search took too long. Try again."
            ) from error
        raise


def search_board_sequences(
    session: Session,
    document_source: Callable[
        [UUID], tuple[type[ImageBoardSearchFastDocumentModel], BoardSearchAssetMode]
    ],
    *,
    game_id: UUID,
    patterns: Sequence[Sequence[BoardSearchQueryCell]],
    scope: BoardSearchScope,
    limit: int,
) -> tuple[BoardSearchSequenceResult, ...]:
    # Imported here to keep the existing repository's projection writers independent.
    from game_predictor_api.storage.board_search_projection_repository import (
        _positive_evidence_expression,
        _search_score_expressions,
    )

    game = session.get(GameModel, game_id)
    if game is None:
        raise BoardSearchError("GAME_NOT_FOUND", "The selected game does not exist.")
    GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.READ)
    validate_sequence_length(game.expected_layout_count, len(patterns))
    document, mode = document_source(game_id)
    mobile_codes = {
        code: int(mobile_code)
        for code, mobile_code in session.execute(
            select(SymbolModel.code, SymbolModel.mobile_code).where(
                SymbolModel.game_id == game_id, SymbolModel.status == SymbolStatus.ACTIVE
            )
        ).tuples()
    }
    wildcard = game.code == "777a2"
    aliases = [
        cast(type[ImageBoardSearchFastDocumentModel], aliased(document, name=f"d{i}"))
        for i in range(len(patterns))
    ]
    columns: list[Any] = []
    positive: list[ColumnElement[bool]] = []
    filters: list[ColumnElement[bool]] = [
        aliases[0].game_id == game_id,
        aliases[0].sequence_number.between(1, game.expected_layout_count),
    ]
    score_parts: list[tuple[ColumnElement[Any], ...]] = []
    approved: ColumnElement[int] = literal(0)
    for index, (alias, query) in enumerate(zip(aliases, patterns, strict=True)):
        if any(cell.symbol_code not in mobile_codes for cell in query):
            raise BoardSearchSequenceError(
                "BOARD_SEARCH_SEQUENCE_INVALID",
                "Every symbol must be active in this game.",
                pattern_index=index,
            )
        cell_codes = {
            cell.cell_index: mobile_codes[cell.symbol_code]
            for cell in query
            if cell.symbol_code is not None
        }
        expressions = _search_score_expressions(
            alias, query, mobile_codes_by_cell=cell_codes, unknown_matches_all=wildcard
        )
        score_parts.append(expressions)
        positive.append(
            _positive_evidence_expression(
                alias, query, mobile_codes_by_cell=cell_codes, unknown_matches_all=wildcard
            )
        )
        is_approved = alias.status.in_(("accepted", "corrected"))
        approved = approved + case((is_approved, 1), else_=0)
        if scope is BoardSearchScope.APPROVED_ONLY:
            filters.append(is_approved)
        prefix = f"b{index}_"
        columns.extend(getattr(alias, field).label(prefix + field) for field in _BOARD_FIELDS)
        columns.extend(
            value.label(prefix + field)
            for field, value in zip(_SCORE_FIELDS, expressions, strict=True)
        )
    totals = [sum((part[i] for part in score_parts), literal(0)) for i in range(1, 6)]
    exact, alternative, weighted, mismatch, unknown = totals
    points = exact + weighted + (unknown if wildcard else literal(0))
    total_score = func.round(
        (points * literal(100.0 / sum(map(len, patterns)))).cast(Numeric(10, 6)), 1
    )
    columns.extend(
        value.label("total_" + field)
        for field, value in zip(
            _SCORE_FIELDS,
            (total_score, exact, alternative, weighted, mismatch, unknown),
            strict=True,
        )
    )
    statement = select(*columns).select_from(aliases[0])
    for index, alias in enumerate(aliases[1:], 1):
        position = (aliases[0].sequence_number - 1 + index) % game.expected_layout_count + 1
        statement = statement.join(
            alias, and_(alias.game_id == game_id, alias.sequence_number == position)
        )
    statement = (
        statement.where(*filters, or_(*positive))
        .order_by(
            total_score.desc(),
            exact.desc(),
            weighted.desc(),
            mismatch.asc(),
            approved.desc(),
            aliases[0].sequence_number.asc(),
            aliases[0].review_item_id.asc(),
        )
        .limit(limit)
    )
    rows = _rank_with_timeout(session, statement)
    return tuple(
        BoardSearchSequenceResult(
            boards=tuple(
                BoardSearchResult(
                    asset_mode=mode,
                    review_item_id=row[f"b{i}_review_item_id"],
                    recognized_board_id=row[f"b{i}_recognized_board_id"],
                    import_job_id=row[f"b{i}_import_job_id"],
                    sequence_number=int(row[f"b{i}_sequence_number"]),
                    status=row[f"b{i}_status"],
                    board_checksum_sha256=row[f"b{i}_board_checksum_sha256"],
                    score=_score(row, f"b{i}_", wildcard),
                )
                for i in range(len(patterns))
            ),
            score=_score(row, "total_", wildcard),
        )
        for row in rows
    )
