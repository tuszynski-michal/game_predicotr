"""Application boundary for the admin "Przybliżona wygrana" range calculator.

Thin glue between the read-only `board_search_approximate_win` domain module
and a repository: load the game's sequence length and its latest published
rules (or, in the Admin only, an explicitly selected draft or published rules
version of the same game, TASK-0932), build a `PreparedPayoutEvaluator`
(TASK-0650) once, read the evaluated
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

from game_predictor_worker.domain.contracts import GameConfig, PayoutEvaluation
from game_predictor_worker.domain.errors import DomainValidationError
from game_predictor_worker.domain.payout import PreparedPayoutEvaluator, prepare_payout_evaluator
from game_predictor_worker.domain.signature import MAX_SIGNATURE_CELL_WIDTH
from game_predictor_worker.payouts.contracts import RulesPayoutConfiguration

from game_predictor_api.application.super_game_markers import SuperGameMarkerSource
from game_predictor_api.domain.board_search import BoardSearchAssetMode, BoardSearchError
from game_predictor_api.domain.board_search_approximate_win import (
    ApproximateWinDocument,
    ApproximateWinResult,
    ApproximateWinSpinEvaluation,
    calculate_approximate_win,
    plan_approximate_win_positions,
)
from game_predictor_api.domain.board_search_board_detail import BoardCountMatch
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.domain.super_game_markers import SuperGameMarkers

# The board-search projection this calculator reads is fixed to the same
# 3x5 layout as partial board search (`BOARD_SEARCH_CELL_COUNT` in
# `domain/board_search.py`); a rules version published with different
# dimensions cannot back this calculator.
_APPROXIMATE_WIN_BOARD_ROWS = 3
_APPROXIMATE_WIN_BOARD_COLUMNS = 5

APPROXIMATE_WIN_SPIN_COUNT_MAX = 100_000
"""Operator-approved ceiling for current-version testing; the calculator does
one synchronous read plus up to `N` in-process payout-v3 evaluations per
request, with no cache."""

SELECTABLE_RULES_STATUSES = frozenset({RulesVersionStatus.DRAFT, RulesVersionStatus.PUBLISHED})
"""Rules versions the Admin may preview explicitly (D-535 draft preview)."""


class RulesConfigurationSource(Protocol):
    def latest_published_rules(self, game_id: UUID) -> RulesPayoutConfiguration | None: ...

    def rules_configuration(
        self, *, game_id: UUID, rules_version_id: UUID
    ) -> RulesPayoutConfiguration | None: ...


class BoardSearchApproximateWinRepository(Protocol):
    def game_sequence_length(self, game_id: UUID) -> int: ...

    def latest_published_rules(self, game_id: UUID) -> RulesPayoutConfiguration | None: ...

    def rules_configuration(
        self, *, game_id: UUID, rules_version_id: UUID
    ) -> RulesPayoutConfiguration | None: ...

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
    super_game: SuperGameMarkers | None = None
    """Markers of the winning rows' positions and the freshness of their
    generation (TASK-0935); `None` when no marker source was wired (frozen
    management results never carry markers)."""


class BoardSearchApproximateWinService:
    def __init__(
        self,
        repository: BoardSearchApproximateWinRepository,
        super_game_markers: SuperGameMarkerSource | None = None,
    ) -> None:
        self._repository = repository
        self._super_game_markers = super_game_markers

    def calculate(
        self,
        *,
        game_id: UUID,
        start_sequence_number: int,
        requested_spin_count: int,
        rules_version_id: UUID | None = None,
    ) -> ApproximateWinCalculation:
        """`rules_version_id` selects a draft or published rules version of
        the game (Admin draft preview); `None` uses the latest published one."""
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

        configuration = resolve_rules_configuration(self._repository, game_id, rules_version_id)
        evaluator = prepare_approximate_win_evaluator(game_id, configuration)

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

        def evaluate(cells: Sequence[int]) -> ApproximateWinSpinEvaluation:
            evaluation = evaluator.evaluate(cells)
            return ApproximateWinSpinEvaluation(
                payout_credits=evaluation.total_payout,
                count_matches=board_count_matches(evaluation, configuration),
            )

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

        super_game = (
            None
            if self._super_game_markers is None
            else self._super_game_markers.markers(
                game_id, {row.sequence_number for row in result.rows}
            )
        )
        return ApproximateWinCalculation(
            game_id=game_id,
            data_source=data_source,
            start_board_status=start_board_status,
            rules_version_id=configuration.rules_version_id,
            rules_version=configuration.version,
            spin_cost=configuration.spin_cost,
            algorithm_version=evaluator.algorithm_version,
            result=result,
            super_game=super_game,
        )


def resolve_rules_configuration(
    repository: RulesConfigurationSource,
    game_id: UUID,
    rules_version_id: UUID | None,
) -> RulesPayoutConfiguration:
    """The latest published rules, or the explicitly selected draft or
    published rules version of the same game (Admin-only draft preview)."""

    if rules_version_id is None:
        configuration = repository.latest_published_rules(game_id)
        if configuration is None:
            raise BoardSearchError(
                "APPROXIMATE_WIN_RULES_NOT_PUBLISHED",
                "The game has no published rules version to calculate payout against.",
            )
        return configuration
    selected = repository.rules_configuration(game_id=game_id, rules_version_id=rules_version_id)
    if (
        selected is None
        or selected.rules_game_id != game_id
        or selected.status not in SELECTABLE_RULES_STATUSES
    ):
        raise BoardSearchError(
            "APPROXIMATE_WIN_RULES_VERSION_NOT_FOUND",
            "The selected rules version is not a draft or published version of this game.",
        )
    return selected


def board_count_matches(
    evaluation: PayoutEvaluation,
    configuration: RulesPayoutConfiguration,
) -> tuple[BoardCountMatch, ...]:
    """Count payouts of super game trigger symbols with their catalog codes."""

    codes = {symbol.mobile_code: symbol.code for symbol in configuration.symbols}
    return tuple(
        BoardCountMatch(
            symbol_code=codes[match.symbol_mobile_code],
            count=match.count,
            cells=tuple(match.matched_cells),
            payout_credits=match.payout_credits,
        )
        for match in evaluation.count_matches
    )


def prepare_approximate_win_evaluator(
    game_id: UUID,
    configuration: RulesPayoutConfiguration,
) -> PreparedPayoutEvaluator:
    """Validate the rules once and build the evaluator (payout-v3, or
    payout-v4-wild-count with a trigger symbol) shared by the range
    calculator and the single-board detail (D-470)."""

    if (
        configuration.rows != _APPROXIMATE_WIN_BOARD_ROWS
        or configuration.columns != _APPROXIMATE_WIN_BOARD_COLUMNS
    ):
        raise BoardSearchError(
            "APPROXIMATE_WIN_RULES_INVALID",
            (
                f"The rules use a {configuration.rows}x{configuration.columns} "
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
        return prepare_payout_evaluator(
            game,
            configuration.paylines,
            configuration.payout_symbols,
            configuration.payout_rules,
        )
    except DomainValidationError as error:
        raise BoardSearchError(
            "APPROXIMATE_WIN_RULES_INVALID",
            f"The selected rules configuration is invalid ({error.code}).",
        ) from error


__all__ = [
    "APPROXIMATE_WIN_SPIN_COUNT_MAX",
    "ApproximateWinCalculation",
    "BoardSearchApproximateWinRepository",
    "BoardSearchApproximateWinService",
    "RulesConfigurationSource",
    "SELECTABLE_RULES_STATUSES",
    "board_count_matches",
    "prepare_approximate_win_evaluator",
    "resolve_rules_configuration",
]
