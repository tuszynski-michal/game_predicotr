"""Pure build-time payout evaluation."""

from __future__ import annotations

from collections.abc import Sequence

from game_predictor_worker.domain.contracts import (
    GameConfig,
    JokerInterpretation,
    PaylineDefinition,
    PayoutEvaluation,
    PayoutMatch,
    PayoutRuleDefinition,
    SymbolDefinition,
)
from game_predictor_worker.domain.errors import DomainErrorCode, DomainValidationError
from game_predictor_worker.domain.validation import (
    validate_full_board,
    validate_paylines,
    validate_payout_configuration,
)

MAX_PAYOUT_COLUMNS = 5


def _compatible_runs(
    line_codes: Sequence[int],
    symbol_code: int,
    wildcard_codes: frozenset[int],
) -> tuple[tuple[int, int], ...]:
    runs: list[tuple[int, int]] = []
    run_start: int | None = None

    for column, cell_code in enumerate(line_codes):
        compatible = cell_code == symbol_code or cell_code in wildcard_codes
        if compatible and run_start is None:
            run_start = column
        elif not compatible and run_start is not None:
            runs.append((run_start, column))
            run_start = None

    if run_start is not None:
        runs.append((run_start, len(line_codes)))

    return tuple(runs)


def _winning_segment(
    line_codes: Sequence[int],
    run_start: int,
    run_end: int,
    symbol_code: int,
    payout_by_length: dict[int, int],
) -> tuple[int, int, int] | None:
    run_length = run_end - run_start
    for match_length in sorted(payout_by_length, reverse=True):
        if match_length > run_length:
            continue
        last_start = run_end - match_length
        for segment_start in range(run_start, last_start + 1):
            segment_end = segment_start + match_length
            if symbol_code in line_codes[segment_start:segment_end]:
                return segment_start, match_length, payout_by_length[match_length]
    return None


def _evaluate_symbol_on_payline(
    *,
    symbol: SymbolDefinition,
    payline: PaylineDefinition,
    line_codes: Sequence[int],
    line_cell_indices: Sequence[int],
    wildcard_codes: frozenset[int],
    payout_by_length: dict[int, int],
) -> tuple[PayoutMatch, ...]:
    matches: list[PayoutMatch] = []
    for run_start, run_end in _compatible_runs(
        line_codes,
        symbol.mobile_code,
        wildcard_codes,
    ):
        winning_segment = _winning_segment(
            line_codes,
            run_start,
            run_end,
            symbol.mobile_code,
            payout_by_length,
        )
        if winning_segment is None:
            continue

        start_column, matched_length, payout_credits = winning_segment
        end_column = start_column + matched_length
        matched_cells = tuple(line_cell_indices[start_column:end_column])
        joker_cells = tuple(
            cell_index
            for cell_index, cell_code in zip(
                matched_cells,
                line_codes[start_column:end_column],
                strict=True,
            )
            if cell_code in wildcard_codes
        )
        interpretation = tuple(
            JokerInterpretation(
                cell_index=cell_index,
                as_symbol_mobile_code=symbol.mobile_code,
            )
            for cell_index in joker_cells
        )
        matches.append(
            PayoutMatch(
                symbol_mobile_code=symbol.mobile_code,
                payline_id=payline.id,
                start_column=start_column,
                matched_length=matched_length,
                matched_cells=matched_cells,
                joker_cells=joker_cells,
                payout_credits=payout_credits,
                interpretation=interpretation,
            )
        )

    return tuple(matches)


def evaluate_payout(
    game: GameConfig,
    cells: Sequence[int],
    paylines: Sequence[PaylineDefinition],
    payout_rules: Sequence[PayoutRuleDefinition],
) -> PayoutEvaluation:
    """Evaluate all payline/symbol pairs for one complete row-major layout."""

    validate_full_board(cells, game)
    if game.columns > MAX_PAYOUT_COLUMNS:
        raise DomainValidationError(
            DomainErrorCode.UNSUPPORTED_PAYOUT_BOARD_WIDTH,
            (
                f"Payout evaluation supports at most {MAX_PAYOUT_COLUMNS} "
                "columns until multi-run semantics are defined."
            ),
        )
    validate_paylines(paylines, game)
    validate_payout_configuration(payout_rules, game)

    wildcard_codes = frozenset(
        symbol.mobile_code for symbol in game.symbols if symbol.is_wildcard
    )
    ordinary_symbols = sorted(
        (symbol for symbol in game.symbols if not symbol.is_wildcard),
        key=lambda symbol: (symbol.display_order, symbol.mobile_code),
    )
    rules_by_symbol: dict[int, dict[int, int]] = {}
    for rule in payout_rules:
        rules_by_symbol.setdefault(rule.symbol_mobile_code, {})[
            rule.match_length
        ] = rule.payout_credits

    matches: list[PayoutMatch] = []
    for payline in paylines:
        line_cell_indices = tuple(
            payline.row_path[column] * game.columns + column
            for column in range(game.columns)
        )
        line_codes = tuple(cells[cell_index] for cell_index in line_cell_indices)
        for symbol in ordinary_symbols:
            matches.extend(
                _evaluate_symbol_on_payline(
                    symbol=symbol,
                    payline=payline,
                    line_codes=line_codes,
                    line_cell_indices=line_cell_indices,
                    wildcard_codes=wildcard_codes,
                    payout_by_length=rules_by_symbol[symbol.mobile_code],
                )
            )

    return PayoutEvaluation(
        total_payout=sum(match.payout_credits for match in matches),
        matches=tuple(matches),
    )
