"""Bounded SQL ranking of consecutive positions in the existing fast projection."""

from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Numeric, and_, case, func, literal, literal_column, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql.selectable import Select

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
_SEQUENCE_RANK_TIMEOUT_MS = 60_000


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
    previous_jit = str(session.execute(text("SHOW jit")).scalar_one())
    previous_ms = int(
        session.execute(
            text("SELECT setting FROM pg_settings WHERE name = 'statement_timeout'")
        ).scalar_one()
    )
    timeout = (
        min(previous_ms, _SEQUENCE_RANK_TIMEOUT_MS) if previous_ms else _SEQUENCE_RANK_TIMEOUT_MS
    )
    try:
        with session.begin_nested():
            session.execute(
                text("SELECT set_config('statement_timeout', :value, true)"),
                {"value": str(timeout)},
            )
            # These bounded interactive requests must not pay LLVM compilation
            # startup for hundreds of per-cell CASE expressions on every search.
            session.execute(text("SELECT set_config('jit', 'off', true)"))
            rows = session.execute(statement).mappings().all()
            session.execute(text("SELECT set_config('jit', :value, true)"), {"value": previous_jit})
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


def _sequence_statement(
    document: type[ImageBoardSearchFastDocumentModel],
    *,
    game_id: UUID,
    patterns: Sequence[Sequence[BoardSearchQueryCell]],
    mobile_codes: Mapping[str, int],
    wildcard: bool,
    sequence_length: int,
    scope: BoardSearchScope,
    limit: int,
) -> Select[Any]:
    # Imported here to keep the existing repository's projection writers independent.
    from game_predictor_api.storage.board_search_projection_repository import (
        _search_score_expressions,
    )

    evidence = []
    for index, query in enumerate(patterns):
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
        alias = cast(type[ImageBoardSearchFastDocumentModel], aliased(document, name=f"d{index}"))
        expressions = _search_score_expressions(
            alias, query, mobile_codes_by_cell=cell_codes, unknown_matches_all=wildcard
        )
        is_approved = alias.status.in_(("accepted", "corrected"))
        filters = [alias.game_id == game_id, alias.sequence_number.between(1, sequence_length)]
        if scope is BoardSearchScope.APPROVED_ONLY:
            filters.append(is_approved)
        # An optimization fence: PostgreSQL must not inline these CASE trees into
        # every total, filter and sort expression. Keep wide metadata out of it.
        evidence.append(
            select(
                alias.sequence_number,
                alias.review_item_id,
                case((is_approved, 1), else_=0).label("approved"),
                *(
                    value.label(field)
                    for field, value in zip(_SCORE_FIELDS[1:], expressions[1:], strict=True)
                ),
            )
            .where(*filters)
            .cte(f"evidence_{index}")
            .prefix_with("MATERIALIZED")
        )
    totals = [sum((part.c[field] for part in evidence), literal(0)) for field in _SCORE_FIELDS[1:]]
    exact, alternative, weighted, mismatch, unknown = totals
    points = exact + weighted + (unknown if wildcard else literal(0))
    total_score = func.round(
        (points * literal(100.0 / sum(map(len, patterns)))).cast(Numeric(10, 6)), 1
    )
    columns = [
        part.c[field].label(f"b{index}_" + field)
        for index, part in enumerate(evidence)
        for field in ("sequence_number", *_SCORE_FIELDS[1:])
    ]
    columns.extend(
        value.label("total_" + field)
        for field, value in zip(
            _SCORE_FIELDS,
            (total_score, exact, alternative, weighted, mismatch, unknown),
            strict=True,
        )
    )
    approved = sum((part.c.approved for part in evidence), literal(0))
    columns.extend((approved.label("approved"), evidence[0].c.review_item_id.label("root_id")))
    ranked = select(*columns).select_from(evidence[0])
    for index, part in enumerate(evidence[1:], 1):
        position = (evidence[0].c.sequence_number - 1 + index) % sequence_length + 1
        ranked = ranked.join(part, part.c.sequence_number == position)
    ranking = (
        ("total_score", True),
        ("total_exact_match_count", True),
        ("total_weighted_alternative_score", True),
        ("total_mismatch_count", False),
        ("approved", True),
        ("b0_sequence_number", False),
        ("root_id", False),
    )
    limited = (
        ranked.where(exact + alternative + (unknown if wildcard else literal(0)) > 0)
        .order_by(
            *(
                literal_column(name).desc() if descending else literal_column(name).asc()
                for name, descending in ranking
            )
        )
        .limit(limit)
        .cte("limited_sequences")
        .prefix_with("MATERIALIZED")
    )
    output = [limited.c["total_" + field] for field in _SCORE_FIELDS]
    statement = select().select_from(limited)
    for index, query in enumerate(patterns):
        prefix = f"b{index}_"
        alias = aliased(document, name=f"result_{index}")
        statement = statement.join(
            alias,
            and_(
                alias.game_id == game_id,
                alias.sequence_number == limited.c[prefix + "sequence_number"],
            ),
        )
        output.extend(getattr(alias, field).label(prefix + field) for field in _BOARD_FIELDS)
        points = (
            limited.c[prefix + "exact_match_count"]
            + limited.c[prefix + "weighted_alternative_score"]
        )
        if wildcard:
            points = points + limited.c[prefix + "unknown_count"]
        output.append(
            func.round((points * literal(100.0 / len(query))).cast(Numeric(10, 6)), 1).label(
                prefix + "score"
            )
        )
        output.extend(limited.c[prefix + field] for field in _SCORE_FIELDS[1:])
    return statement.with_only_columns(*output).order_by(
        *(
            limited.c[name].desc() if descending else limited.c[name].asc()
            for name, descending in ranking
        )
    )


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
    statement = _sequence_statement(
        document,
        game_id=game_id,
        patterns=patterns,
        mobile_codes=mobile_codes,
        wildcard=wildcard,
        sequence_length=game.expected_layout_count,
        scope=scope,
        limit=limit,
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
