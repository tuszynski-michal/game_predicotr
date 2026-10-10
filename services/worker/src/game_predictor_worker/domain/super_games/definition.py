"""Shared description of one code-defined super game kind."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from game_predictor_worker.domain.contracts import CountMatch, PayoutMatch

if TYPE_CHECKING:
    from game_predictor_worker.domain.payout import PreparedPayoutEvaluator


class SeriesPayoutKind(StrEnum):
    """How far the payout of one series board can be trusted (D-537).

    ``exact``: a fully known board with a defined super symbol in a fresh
    generation. ``provisional``: anything else; the payout can still grow or
    shrink (an expansion may add a win or cover one), so it is never a lower
    bound and is summed apart from ``exact`` and ``confirmed_minimum``.
    """

    EXACT = "exact"
    PROVISIONAL = "provisional"


@dataclass(frozen=True, slots=True)
class SeriesExpansion:
    """The super symbol expanded over ``columns`` (0-based) of the board.

    ``payout_credits = line_payout_credits × payline_count``, where
    ``line_payout_credits`` is the line payout of the super symbol for
    ``column_count`` matches and ``payline_count`` the active paylines.
    """

    symbol_mobile_code: int
    columns: tuple[int, ...]
    column_count: int
    line_payout_credits: int
    payline_count: int
    payout_credits: int


@dataclass(frozen=True, slots=True)
class SeriesBoardEvaluation:
    """The payout of one board inside a super game series.

    ``evaluated_cells`` is the board the lines were evaluated on: the expanded
    board when ``expansion`` is set, otherwise the original board. ``matches``
    are line wins on that board (the super symbol's own line wins are replaced
    by ``expansion``), ``count_matches`` are always counted on the original
    board and ``retrigger`` says whether its trigger symbols reach the trigger
    threshold (the series is extended by the derivation, TASK-0933).
    """

    evaluated_cells: tuple[int, ...]
    matches: tuple[PayoutMatch, ...]
    count_matches: tuple[CountMatch, ...]
    expansion: SeriesExpansion | None
    total_payout: int
    payout_kind: SeriesPayoutKind
    retrigger: bool


class SeriesBoardEvaluator(Protocol):
    def __call__(
        self,
        cells: Sequence[int],
        super_symbol_mobile_code: int | None,
        evaluator: PreparedPayoutEvaluator,
        *,
        generation_fresh: bool = True,
    ) -> SeriesBoardEvaluation: ...


@dataclass(frozen=True, slots=True)
class SuperGameKindDefinition:
    """Static parameters of one super game kind.

    ``series_length`` is the number of free spins a trigger opens,
    ``retrigger_extension`` the number of spins added by a retrigger inside a
    running series and ``free_spin_cost`` the credit cost of one series spin.
    The kind ``none`` has no series, so all three values are ``0``.
    ``evaluate_series_board`` evaluates one board inside a series of this kind
    (``None`` for ``none``).
    """

    code: str
    label: str
    series_length: int
    retrigger_extension: int
    free_spin_cost: int
    evaluate_series_board: SeriesBoardEvaluator | None = field(default=None, compare=False)

    @property
    def has_super_game(self) -> bool:
        return self.series_length > 0
