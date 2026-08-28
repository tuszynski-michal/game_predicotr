"""Measure the warm read path of partial-board search on a ready local projection.

Run from the repository root::

    .venv\\Scripts\\python.exe scripts\\benchmark_board_search.py \\
        --game-id 80f3c7ec-6110-4e20-a263-2675ee5b15d6

The script is deliberately read-only.  It derives a configurable number of
active catalog symbols from one current search document, warms the same service
path used by the API, then measures repeated in-process reads.  It neither
reads image bytes nor changes jobs, review decisions, projection rows, or
artifacts.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from game_predictor_api.application.board_search import BoardSearchService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.board_search import (
    UNKNOWN_SYMBOL_CODE,
    BoardSearchError,
    BoardSearchQueryCell,
    BoardSearchScope,
)
from game_predictor_api.domain.catalog import SymbolStatus
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.database import (
    create_database_engine,
    create_session_factory,
)
from game_predictor_api.storage.models import (
    ImageBoardSearchCandidateModel,
    ImageBoardSearchDocumentModel,
    SymbolModel,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

DEFAULT_RUN_COUNT = 25
DEFAULT_P95_BUDGET_MS = 500.0
DEFAULT_MAX_BUDGET_MS = 2_000.0
DEFAULT_RESULT_LIMIT = 100
DEFAULT_QUERY_SIZE = 3


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", required=True, type=UUID)
    parser.add_argument("--runs", default=DEFAULT_RUN_COUNT, type=int)
    parser.add_argument(
        "--scope",
        choices=tuple(scope.value for scope in BoardSearchScope),
        default=BoardSearchScope.ALL_SEARCHABLE.value,
    )
    parser.add_argument("--limit", default=DEFAULT_RESULT_LIMIT, type=int)
    parser.add_argument(
        "--query-size",
        default=DEFAULT_QUERY_SIZE,
        type=int,
        help="Number of known cells derived from one current board (1..15).",
    )
    parser.add_argument("--p95-budget-ms", default=DEFAULT_P95_BUDGET_MS, type=float)
    parser.add_argument("--max-budget-ms", default=DEFAULT_MAX_BUDGET_MS, type=float)
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON report path. The script writes no other artifact.",
    )
    return parser.parse_args()


def nearest_rank_percentile(values: Sequence[float], percentile: float) -> float:
    """Return a deterministic nearest-rank percentile without NumPy."""

    if not values:
        raise ValueError("Cannot calculate a percentile for an empty sample.")
    if not 0.0 < percentile <= 1.0:
        raise ValueError("percentile must be greater than zero and at most one.")
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def summarize_latencies_ms(latencies_ms: Sequence[float]) -> dict[str, float]:
    """Summarize a concrete warm-query sample for the acceptance report."""

    if not latencies_ms:
        raise ValueError("At least one latency sample is required.")
    return {
        "minMs": round(min(latencies_ms), 4),
        "p50Ms": round(nearest_rank_percentile(latencies_ms, 0.50), 4),
        "p95Ms": round(nearest_rank_percentile(latencies_ms, 0.95), 4),
        "maxMs": round(max(latencies_ms), 4),
    }


def derive_benchmark_query(
    projected_symbols: Iterable[Sequence[str | None]],
    *,
    active_symbol_codes: set[str],
    query_size: int = DEFAULT_QUERY_SIZE,
) -> tuple[BoardSearchQueryCell, ...]:
    """Pick a bounded count of usable cells from one current logical board."""

    if not 1 <= query_size <= 15:
        raise ValueError("query_size must be between 1 and 15.")

    for symbol_codes in projected_symbols:
        query = tuple(
            BoardSearchQueryCell(cell_index=index, symbol_code=symbol_code)
            for index, symbol_code in enumerate(symbol_codes)
            if symbol_code is not None
            and symbol_code != UNKNOWN_SYMBOL_CODE
            and symbol_code in active_symbol_codes
        )[:query_size]
        if len(query) == query_size:
            return query
    raise RuntimeError(
        "The ready projection has no current board with enough active catalog symbols."
    )


def _load_query_cells(
    session: Session,
    game_id: UUID,
    *,
    query_size: int,
) -> tuple[BoardSearchQueryCell, ...]:
    active_codes = set(
        session.scalars(
            select(SymbolModel.code).where(
                SymbolModel.game_id == game_id,
                SymbolModel.status == SymbolStatus.ACTIVE,
            )
        ).all()
    )
    if not active_codes:
        raise RuntimeError("The selected game has no active catalog symbols.")

    candidate = ImageBoardSearchCandidateModel
    document = ImageBoardSearchDocumentModel
    statement = (
        select(candidate.primary_symbol_codes)
        .join(document, document.review_item_id == candidate.review_item_id)
        .where(candidate.game_id == game_id)
        .order_by(candidate.sequence_number.asc(), candidate.review_item_id.asc())
        .execution_options(yield_per=250)
    )
    projected = (
        tuple(code if isinstance(code, str) else None for code in raw)
        for raw in session.scalars(statement)
        if isinstance(raw, list)
    )
    return derive_benchmark_query(
        projected,
        active_symbol_codes=active_codes,
        query_size=query_size,
    )


def run_benchmark(
    session: Session,
    *,
    game_id: UUID,
    scope: BoardSearchScope,
    limit: int,
    run_count: int,
    query_size: int = DEFAULT_QUERY_SIZE,
) -> dict[str, object]:
    """Warm and measure the exact service/repository read path without writes."""

    if run_count < 20:
        raise ValueError("--runs must be at least 20 for a meaningful p95 measurement.")
    if not 1 <= limit <= DEFAULT_RESULT_LIMIT:
        raise ValueError("--limit must be between 1 and 100.")
    query = _load_query_cells(session, game_id, query_size=query_size)
    service = BoardSearchService(SqlAlchemyBoardSearchProjectionRepository(session))

    warmup_results = service.search(
        game_id=game_id,
        cells=query,
        scope=scope,
        limit=limit,
    )
    latencies_ms: list[float] = []
    result_count = len(warmup_results)
    for _ in range(run_count):
        started = time.perf_counter()
        results = service.search(
            game_id=game_id,
            cells=query,
            scope=scope,
            limit=limit,
        )
        latencies_ms.append((time.perf_counter() - started) * 1_000.0)
        if len(results) != result_count:
            raise RuntimeError("Board-search results changed during the benchmark.")

    return {
        "gameId": str(game_id),
        "query": [{"cellIndex": cell.cell_index, "symbolCode": cell.symbol_code} for cell in query],
        "scope": scope.value,
        "limit": limit,
        "warmupResultCount": len(warmup_results),
        "runCount": run_count,
        "measurements": summarize_latencies_ms(latencies_ms),
    }


def _accepted(report: dict[str, object], *, p95_budget_ms: float, max_budget_ms: float) -> bool:
    measurements = cast(dict[str, Any], report["measurements"])
    return (
        float(measurements["p95Ms"]) <= p95_budget_ms
        and float(measurements["maxMs"]) <= max_budget_ms
    )


def main() -> int:
    arguments = _arguments()
    if arguments.p95_budget_ms <= 0 or arguments.max_budget_ms <= 0:
        raise ValueError("Latency budgets must be positive.")
    if not 1 <= arguments.query_size <= 15:
        raise ValueError("--query-size must be between 1 and 15.")
    settings = ApiSettings.from_environment()
    factory = create_session_factory(create_database_engine(settings))
    try:
        with factory() as session:
            report = run_benchmark(
                session,
                game_id=arguments.game_id,
                scope=BoardSearchScope(arguments.scope),
                limit=arguments.limit,
                run_count=arguments.runs,
                query_size=arguments.query_size,
            )
    except (BoardSearchError, RuntimeError, ValueError) as error:
        print(
            json.dumps(
                {"code": "BOARD_SEARCH_BENCHMARK_FAILED", "message": str(error)},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1

    accepted = _accepted(
        report,
        p95_budget_ms=arguments.p95_budget_ms,
        max_budget_ms=arguments.max_budget_ms,
    )
    report["budgets"] = {
        "p95Ms": arguments.p95_budget_ms,
        "maxMs": arguments.max_budget_ms,
    }
    report["accepted"] = accepted
    encoded = json.dumps(report, indent=2, sort_keys=True)
    if arguments.output is not None:
        output = arguments.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if accepted else 2


if __name__ == "__main__":
    raise SystemExit(main())
