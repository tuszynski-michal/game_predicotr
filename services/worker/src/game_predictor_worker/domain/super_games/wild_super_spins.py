"""The ``wild_super_spins`` super game kind (D-535, D-537, plan MUMIE_SUPER_GAME).

A trigger opens a series of 10 free spins (cost 0) on the following positions
of the same sequence; a retrigger inside the series extends it by 10 without a
new super symbol.

A board inside the series is evaluated in four steps (TASK-0936):

1. ``k`` = the number of columns of the *original* board that contain the
   super symbol ``X`` (columns need not be adjacent). With
   ``k < minimum_match_length(X)`` the board is not transformed: lines and
   counts are evaluated exactly as in base mode.
2. Otherwise every one of those ``k`` columns is filled with ``X`` (covering
   whatever was underneath, Wilds included): the expanded board.
3. Lines are evaluated on the expanded board (Wild still substitutes), counts
   of trigger symbols on the original board. ``X``'s own line wins on the
   expanded board are *replaced* by the expansion payout
   ``payout_line(X, k) × number of active paylines``; line wins of other
   symbols on the expanded board stay.
4. The spin costs nothing; a board with at least ``N`` trigger symbols pays
   its count payout and extends the series (derived by TASK-0933).

The result is ``exact`` only for a fully known board with a defined super
symbol in a fresh series generation; any unknown cell, an undefined super
symbol or a stale generation makes it ``provisional`` (an unknown cell outside
the ``X`` columns can add a column, cross the threshold and cover an earlier
win; one inside a covered column can still change the count payout and the
retrigger).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from game_predictor_worker.domain.contracts import PayoutEvaluation
from game_predictor_worker.domain.payout import PreparedPayoutEvaluator
from game_predictor_worker.domain.super_games.definition import (
    SeriesBoardEvaluation,
    SeriesExpansion,
    SeriesPayoutKind,
    SuperGameKindDefinition,
)
from game_predictor_worker.domain.validation import is_super_game_trigger

WILD_SUPER_SPINS_CODE: Final = "wild_super_spins"
WILD_SUPER_SPINS_SERIES_LENGTH: Final = 10
WILD_SUPER_SPINS_RETRIGGER_EXTENSION: Final = 10
WILD_SUPER_SPINS_FREE_SPIN_COST: Final = 0

_UNKNOWN_MOBILE_CODE: Final = 0


def super_symbol_columns(
    cells: Sequence[int], super_symbol_mobile_code: int, *, rows: int, columns: int
) -> tuple[int, ...]:
    """0-based columns of the board that contain the super symbol at least once."""

    return tuple(
        column
        for column in range(columns)
        if any(cells[row * columns + column] == super_symbol_mobile_code for row in range(rows))
    )


def expanded_board(
    cells: Sequence[int],
    expanded_columns: Sequence[int],
    super_symbol_mobile_code: int,
    *,
    columns: int,
) -> tuple[int, ...]:
    """``cells`` with every cell of ``expanded_columns`` replaced by the super symbol."""

    covered = frozenset(expanded_columns)
    return tuple(
        super_symbol_mobile_code if index % columns in covered else code
        for index, code in enumerate(cells)
    )


def _is_retrigger(evaluator: PreparedPayoutEvaluator, cells: Sequence[int]) -> bool:
    for symbol in evaluator.game.symbols:
        if not is_super_game_trigger(symbol) or symbol.super_game_trigger_count is None:
            continue
        count = sum(1 for code in cells if code == symbol.mobile_code)
        if count >= symbol.super_game_trigger_count:
            return True
    return False


def _line_super_symbol(
    evaluator: PreparedPayoutEvaluator, super_symbol_mobile_code: int | None
) -> int | None:
    """The super symbol when it is an ordinary line symbol of these rules.

    A super symbol is validated as an ordinary symbol when the operator saves
    it (TASK-0933); a later role change in the evaluated rules version leaves
    it without a line payout, so it is treated as undefined (provisional).
    """

    if super_symbol_mobile_code is None:
        return None
    if any(
        symbol.mobile_code == super_symbol_mobile_code for symbol in evaluator.ordinary_symbols
    ) and evaluator.rules_by_symbol.get(super_symbol_mobile_code):
        return super_symbol_mobile_code
    return None


def evaluate_series_board(
    cells: Sequence[int],
    super_symbol_mobile_code: int | None,
    evaluator: PreparedPayoutEvaluator,
    *,
    generation_fresh: bool = True,
) -> SeriesBoardEvaluation:
    """Evaluate one board inside a ``wild_super_spins`` series (steps 1–4).

    ``cells`` is the original row-major board (``0`` = unknown cell) and
    ``evaluator`` the prepared rules of the game; the board is validated by the
    evaluator exactly like in base mode.
    """

    original_cells = tuple(cells)
    base: PayoutEvaluation = evaluator.evaluate(original_cells)
    super_symbol = _line_super_symbol(evaluator, super_symbol_mobile_code)
    provisional = (
        super_symbol is None
        or not generation_fresh
        or any(code == _UNKNOWN_MOBILE_CODE for code in original_cells)
    )
    payout_kind = SeriesPayoutKind.PROVISIONAL if provisional else SeriesPayoutKind.EXACT
    retrigger = _is_retrigger(evaluator, original_cells)

    expansion: SeriesExpansion | None = None
    evaluated_cells = original_cells
    matches = base.matches
    if super_symbol is not None:
        game = evaluator.game
        payout_by_length = evaluator.rules_by_symbol[super_symbol]
        # A validated rules version pays every length from the symbol's
        # minimum match length up to the column count, so the smallest rule
        # length is that minimum.
        minimum_match_length = min(payout_by_length)
        columns = super_symbol_columns(
            original_cells, super_symbol, rows=game.rows, columns=game.columns
        )
        if len(columns) >= minimum_match_length:
            evaluated_cells = expanded_board(
                original_cells, columns, super_symbol, columns=game.columns
            )
            expanded = evaluator.evaluate(evaluated_cells)
            matches = tuple(
                match for match in expanded.matches if match.symbol_mobile_code != super_symbol
            )
            paid_length = max(length for length in payout_by_length if length <= len(columns))
            line_payout = payout_by_length[paid_length]
            payline_count = len(evaluator.paylines)
            expansion = SeriesExpansion(
                symbol_mobile_code=super_symbol,
                columns=columns,
                column_count=len(columns),
                line_payout_credits=line_payout,
                payline_count=payline_count,
                payout_credits=line_payout * payline_count,
            )

    total = (
        sum(match.payout_credits for match in matches)
        + sum(match.payout_credits for match in base.count_matches)
        + (0 if expansion is None else expansion.payout_credits)
    )
    return SeriesBoardEvaluation(
        evaluated_cells=evaluated_cells,
        matches=matches,
        count_matches=base.count_matches,
        expansion=expansion,
        total_payout=total,
        payout_kind=payout_kind,
        retrigger=retrigger,
    )


WILD_SUPER_SPINS: Final = SuperGameKindDefinition(
    code=WILD_SUPER_SPINS_CODE,
    label="Wild super spins",
    series_length=WILD_SUPER_SPINS_SERIES_LENGTH,
    retrigger_extension=WILD_SUPER_SPINS_RETRIGGER_EXTENSION,
    free_spin_cost=WILD_SUPER_SPINS_FREE_SPIN_COST,
    evaluate_series_board=evaluate_series_board,
)
