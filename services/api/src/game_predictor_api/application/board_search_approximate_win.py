"""Application boundary for the admin "Przybliżona wygrana" range calculator.

Thin glue between the read-only `board_search_approximate_win` domain module
and a repository: load the game's sequence length and its latest published
rules, build a `PreparedPayoutEvaluator` (TASK-0650) once, read the evaluated
range's projection evidence in at most two bounded queries, then hand
everything to `calculate_approximate_win`. A `DomainValidationError` raised
while building or using the evaluator (invalid rules configuration, or a
projected board containing a symbol outside the active rules) is mapped to a
stable `BoardSearchError` here instead of leaking a worker-package exception
type to the API layer.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from game_predictor_worker.domain.contracts import GameConfig
from game_predictor_worker.domain.errors import DomainValidationError
from game_predictor_worker.domain.payout import prepare_payout_evaluator
from game_predictor_worker.domain.signature import MAX_SIGNATURE_CELL_WIDTH
from game_predictor_worker.payouts.contracts import RulesPayoutConfiguration

from game_predictor_api.domain.board_search import BoardSearchAssetMode, BoardSearchError
from game_predictor_api.domain.board_search_approximate_win import (
    ApproximateWinDocument,
    ApproximateWinResult,
    calculate_approximate_win,
    plan_approximate_win_positions,
)

# The board-search projection this calculator reads is fixed to the same
# 3x5 layout as partial board search (`BOARD_SEARCH_CELL_COUNT` in
# `domain/board_search.py`); a rules version published with different
# dimensions cannot back this calculator.
_APPROXIMATE_WIN_BOARD_ROWS = 3
_APPROXIMATE_WIN_BOARD_COLUMNS = 5

APPROXIMATE_WIN_SPIN_COUNT_MAX = 10_000
"""Conservative ceiling on the "Zakres wygranej" input: the calculator does
one synchronous read plus up to `N` in-process payout-v3 evaluations per
request, with no cache. Raise only after measuring real request latency."""

_PAYOUT_ALGORITHM_VERSION = "payout-v3-unknown-prefix-stop"


class BoardSearchApproximateWinRepository(Protocol):
    def game_sequence_length(self, game_id: UUID) -> int: ...

    def latest_published_rules(self, game_id: UUID) -> RulesPayoutConfiguration | None: ...

    def range_documents(
        self,
        *,
        game_id: UUID,
        first_sequence_number: int,
        last_sequence_number: int,
    ) -> tuple[BoardSearchAssetMode, tuple[ApproximateWinDocument, ...]]: ...


@dataclass(frozen=True, slots=True)
class ApproximateWinCalculation:
    """The domain result plus the request/rules context the API response
    needs but that `calculate_approximate_win` itself does not know about."""

    game_id: UUID
    data_source: BoardSearchAssetMode
    start_board_status: str | None
    rules_version_id: UUID
    rules_version: int
    spin_cost: int
    algorithm_version: str
    result: ApproximateWinResult


class BoardSearchApproximateWinService:
    def __init__(self, repository: BoardSearchApproximateWinRepository) -> None:
        self._repository = repository

    def calculate(
        self,
        *,
        game_id: UUID,
        start_sequence_number: int,
        requested_spin_count: int,
    ) -> ApproximateWinCalculation:
        if not 1 <= requested_spin_count <= APPROXIMATE_WIN_SPIN_COUNT_MAX:
            raise BoardSearchError(
                "APPROXIMATE_WIN_SPIN_COUNT_INVALID",
                (
                    "The approximate-win spin count must be between 1 and "
                    f"{APPROXIMATE_WIN_SPIN_COUNT_MAX}."
                ),
            )

        sequence_length = self._repository.game_sequence_length(game_id)
        # Validates start_sequence_number/sequence_length and applies the
        # same full-cycle clamp as calculate_approximate_win itself; cheap
        # to call twice (pure, no I/O) and lets us fail fast before the
        # rules lookup below.
        evaluated_spin_count = len(
            plan_approximate_win_positions(
                start_sequence_number=start_sequence_number,
                requested_spin_count=requested_spin_count,
                sequence_length=sequence_length,
            )
        )

        configuration = self._repository.latest_published_rules(game_id)
        if configuration is None:
            raise BoardSearchError(
                "APPROXIMATE_WIN_RULES_NOT_PUBLISHED",
                "The game has no published rules version to calculate payout against.",
            )
        if (
            configuration.rows != _APPROXIMATE_WIN_BOARD_ROWS
            or configuration.columns != _APPROXIMATE_WIN_BOARD_COLUMNS
        ):
            raise BoardSearchError(
                "APPROXIMATE_WIN_RULES_INVALID",
                (
                    f"Published rules use a {configuration.rows}x{configuration.columns} "
                    "board; approximate win requires "
                    f"{_APPROXIMATE_WIN_BOARD_ROWS}x{_APPROXIMATE_WIN_BOARD_COLUMNS}."
                ),
            )

        # `GameConfig.code`/`.name` are display-only identity fields that
        # `validate_game_config` merely requires to be non-empty; payout
        # evaluation itself never reads them, so a stable placeholder
        # derived from the game id is enough here.
        game = GameConfig(
            id=str(game_id),
            code=f"approximate-win-{game_id}",
            name=f"approximate-win-{game_id}",
            rows=configuration.rows,
            columns=configuration.columns,
            spin_cost=configuration.spin_cost,
            signature_cell_width=MAX_SIGNATURE_CELL_WIDTH,
            symbols=configuration.symbols,
        )
        try:
            evaluator = prepare_payout_evaluator(
                game,
                configuration.paylines,
                configuration.payout_symbols,
                configuration.payout_rules,
            )
        except DomainValidationError as error:
            raise BoardSearchError(
                "APPROXIMATE_WIN_RULES_INVALID",
                f"The published rules configuration is invalid ({error.code}).",
            ) from error

        documents: tuple[ApproximateWinDocument, ...] = ()
        data_source: BoardSearchAssetMode | None = None
        if evaluated_spin_count > 0:
            unwrapped_end = start_sequence_number + evaluated_spin_count
            if unwrapped_end <= sequence_length:
                data_source, documents = self._repository.range_documents(
                    game_id=game_id,
                    first_sequence_number=start_sequence_number + 1,
                    last_sequence_number=unwrapped_end,
                )
            else:
                source_before_wrap, documents_before_wrap = self._repository.range_documents(
                    game_id=game_id,
                    first_sequence_number=start_sequence_number + 1,
                    last_sequence_number=sequence_length,
                )
                source_after_wrap, documents_after_wrap = self._repository.range_documents(
                    game_id=game_id,
                    first_sequence_number=1,
                    last_sequence_number=unwrapped_end - sequence_length,
                )
                data_source = source_before_wrap
                documents = documents_before_wrap + documents_after_wrap

        # The starting board itself is never part of the evaluated range,
        # but its status is shown as a warning when it is not yet approved
        # (D3): a single-position read, reusing the same range reader.
        start_source, start_documents = self._repository.range_documents(
            game_id=game_id,
            first_sequence_number=start_sequence_number,
            last_sequence_number=start_sequence_number,
        )
        if data_source is None:
            data_source = start_source
        start_board_status = start_documents[0].status if start_documents else None

        def evaluate(cells: Sequence[int]) -> int:
            return evaluator.evaluate(cells).total_payout

        try:
            result = calculate_approximate_win(
                start_sequence_number=start_sequence_number,
                requested_spin_count=requested_spin_count,
                sequence_length=sequence_length,
                documents=documents,
                evaluate=evaluate,
                spin_cost=configuration.spin_cost,
            )
        except DomainValidationError as error:
            raise BoardSearchError(
                "APPROXIMATE_WIN_BOARD_SYMBOL_OUTSIDE_RULES",
                (
                    "A projected board contains a symbol outside the active rules "
                    f"configuration ({error.code})."
                ),
            ) from error

        return ApproximateWinCalculation(
            game_id=game_id,
            data_source=data_source,
            start_board_status=start_board_status,
            rules_version_id=configuration.rules_version_id,
            rules_version=configuration.version,
            spin_cost=configuration.spin_cost,
            algorithm_version=_PAYOUT_ALGORITHM_VERSION,
            result=result,
        )


__all__ = [
    "APPROXIMATE_WIN_SPIN_COUNT_MAX",
    "ApproximateWinCalculation",
    "BoardSearchApproximateWinRepository",
    "BoardSearchApproximateWinService",
]
