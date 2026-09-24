"""Pure build-time payout evaluation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from game_predictor_worker.domain.contracts import (
    GameConfig,
    JokerInterpretation,
    PaylineDefinition,
    PayoutEvaluation,
    PayoutMatch,
    PayoutRuleDefinition,
    PayoutSymbolDefinition,
    SymbolDefinition,
)
from game_predictor_worker.domain.validation import (
    validate_full_board,
    validate_layout_board,
    validate_paylines,
    validate_payout_configuration,
)


def _compatible_prefix_length(
    line_codes: Sequence[int],
    symbol_code: int,
    wildcard_codes: frozenset[int],
) -> int:
    prefix_length = 0
    for cell_code in line_codes:
        if cell_code == 0:
            break
        if cell_code != symbol_code and cell_code not in wildcard_codes:
            break
        prefix_length += 1
    return prefix_length


def _evaluate_symbol_on_payline(
    *,
    symbol: SymbolDefinition,
    payline: PaylineDefinition,
    line_codes: Sequence[int],
    line_cell_indices: Sequence[int],
    wildcard_codes: frozenset[int],
    payout_by_length: Mapping[int, int],
) -> PayoutMatch | None:
    prefix_length = _compatible_prefix_length(
        line_codes,
        symbol.mobile_code,
        wildcard_codes,
    )
    matched_length = next(
        (length for length in sorted(payout_by_length, reverse=True) if length <= prefix_length),
        None,
    )
    if matched_length is None:
        return None

    matched_line_codes = line_codes[:matched_length]
    if symbol.mobile_code not in matched_line_codes:
        return None

    matched_cells = tuple(line_cell_indices[:matched_length])
    joker_cells = tuple(
        cell_index
        for cell_index, cell_code in zip(
            matched_cells,
            matched_line_codes,
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
    return PayoutMatch(
        symbol_mobile_code=symbol.mobile_code,
        payline_id=payline.id,
        start_column=0,
        matched_length=matched_length,
        matched_cells=matched_cells,
        joker_cells=joker_cells,
        payout_credits=payout_by_length[matched_length],
        interpretation=interpretation,
    )


def _line_cell_indices(payline: PaylineDefinition, columns: int) -> tuple[int, ...]:
    return tuple(payline.row_path[column] * columns + column for column in range(columns))


def _ordinary_symbols_by_display_order(
    symbols: Sequence[SymbolDefinition],
) -> tuple[SymbolDefinition, ...]:
    return tuple(
        sorted(
            (symbol for symbol in symbols if not symbol.is_wildcard),
            key=lambda symbol: (symbol.display_order, symbol.mobile_code),
        )
    )


def _rules_by_symbol(
    payout_rules: Sequence[PayoutRuleDefinition],
) -> dict[int, dict[int, int]]:
    rules_by_symbol: dict[int, dict[int, int]] = {}
    for rule in payout_rules:
        rules_by_symbol.setdefault(rule.symbol_mobile_code, {})[rule.match_length] = (
            rule.payout_credits
        )
    return rules_by_symbol


def _evaluate_matches(
    *,
    cells: Sequence[int],
    paylines: Sequence[PaylineDefinition],
    line_cell_indices_by_payline: Sequence[tuple[int, ...]],
    ordinary_symbols: Sequence[SymbolDefinition],
    wildcard_codes: frozenset[int],
    rules_by_symbol: Mapping[int, Mapping[int, int]],
) -> PayoutEvaluation:
    """Match every active `(payline, ordinary symbol)` pair against `cells`.

    Shared by every entry point in this module: the one-shot
    `evaluate_payout`/`evaluate_payout_v2` functions and the precomputed
    `PreparedPayoutEvaluator`. Callers are responsible for validating both
    the rules configuration and the board before calling this.
    """

    matches: list[PayoutMatch] = []
    for payline, line_cell_indices in zip(paylines, line_cell_indices_by_payline, strict=True):
        line_codes = tuple(cells[cell_index] for cell_index in line_cell_indices)
        for symbol in ordinary_symbols:
            match = _evaluate_symbol_on_payline(
                symbol=symbol,
                payline=payline,
                line_codes=line_codes,
                line_cell_indices=line_cell_indices,
                wildcard_codes=wildcard_codes,
                payout_by_length=rules_by_symbol[symbol.mobile_code],
            )
            if match is not None:
                matches.append(match)

    return PayoutEvaluation(
        total_payout=sum(match.payout_credits for match in matches),
        matches=tuple(matches),
    )


@dataclass(frozen=True, slots=True)
class PreparedPayoutEvaluator:
    """A payout-v3 evaluator with its paylines and payout configuration
    validated and precomputed once.

    Building one costs the same validation as a single `evaluate_payout`
    call. Each subsequent `evaluate` only re-validates the board layout and
    reuses the precomputed wildcard set, symbol order and payout-by-length
    lookup, instead of re-validating the whole rules matrix. Intended for
    callers that evaluate many boards against one fixed, already-published
    rules version (e.g. an admin payout-range calculator), where repeating
    full payout-configuration validation per board would be wasted, and
    otherwise identical, work.
    """

    game: GameConfig
    paylines: tuple[PaylineDefinition, ...]
    wildcard_codes: frozenset[int]
    ordinary_symbols: tuple[SymbolDefinition, ...]
    rules_by_symbol: Mapping[int, Mapping[int, int]]
    line_cell_indices_by_payline: tuple[tuple[int, ...], ...]

    def evaluate(self, cells: Sequence[int]) -> PayoutEvaluation:
        """Evaluate payout-v3, stopping each line at the first unknown cell."""

        validate_layout_board(cells, self.game)
        return _evaluate_matches(
            cells=cells,
            paylines=self.paylines,
            line_cell_indices_by_payline=self.line_cell_indices_by_payline,
            ordinary_symbols=self.ordinary_symbols,
            wildcard_codes=self.wildcard_codes,
            rules_by_symbol=self.rules_by_symbol,
        )


def prepare_payout_evaluator(
    game: GameConfig,
    paylines: Sequence[PaylineDefinition],
    payout_symbols: Sequence[PayoutSymbolDefinition],
    payout_rules: Sequence[PayoutRuleDefinition],
) -> PreparedPayoutEvaluator:
    """Validate paylines and the payout configuration once and precompute
    the lookups payout-v3 evaluation needs, for reuse across many boards.

    Raises the same `DomainValidationError` as `evaluate_payout` would for
    an invalid configuration; no board is validated at this point.
    """

    validate_paylines(paylines, game)
    validate_payout_configuration(payout_rules, payout_symbols, game)

    frozen_paylines = tuple(paylines)
    return PreparedPayoutEvaluator(
        game=game,
        paylines=frozen_paylines,
        wildcard_codes=frozenset(
            symbol.mobile_code for symbol in game.symbols if symbol.is_wildcard
        ),
        ordinary_symbols=_ordinary_symbols_by_display_order(game.symbols),
        rules_by_symbol=_rules_by_symbol(payout_rules),
        line_cell_indices_by_payline=tuple(
            _line_cell_indices(payline, game.columns) for payline in frozen_paylines
        ),
    )


def _evaluate_payout_validated(
    game: GameConfig,
    cells: Sequence[int],
    paylines: Sequence[PaylineDefinition],
    payout_symbols: Sequence[PayoutSymbolDefinition],
    payout_rules: Sequence[PayoutRuleDefinition],
) -> PayoutEvaluation:
    validate_paylines(paylines, game)
    validate_payout_configuration(payout_rules, payout_symbols, game)

    line_cell_indices_by_payline = tuple(
        _line_cell_indices(payline, game.columns) for payline in paylines
    )
    return _evaluate_matches(
        cells=cells,
        paylines=paylines,
        line_cell_indices_by_payline=line_cell_indices_by_payline,
        ordinary_symbols=_ordinary_symbols_by_display_order(game.symbols),
        wildcard_codes=frozenset(
            symbol.mobile_code for symbol in game.symbols if symbol.is_wildcard
        ),
        rules_by_symbol=_rules_by_symbol(payout_rules),
    )


def evaluate_payout(
    game: GameConfig,
    cells: Sequence[int],
    paylines: Sequence[PaylineDefinition],
    payout_symbols: Sequence[PayoutSymbolDefinition],
    payout_rules: Sequence[PayoutRuleDefinition],
) -> PayoutEvaluation:
    """Evaluate payout-v3, stopping each line at the first unknown cell."""

    validate_layout_board(cells, game)
    return _evaluate_payout_validated(game, cells, paylines, payout_symbols, payout_rules)


def evaluate_payout_v2(
    game: GameConfig,
    cells: Sequence[int],
    paylines: Sequence[PaylineDefinition],
    payout_symbols: Sequence[PayoutSymbolDefinition],
    payout_rules: Sequence[PayoutRuleDefinition],
) -> PayoutEvaluation:
    """Reproduce historical payout-v2, which rejects unknown cells."""

    validate_full_board(cells, game)
    return _evaluate_payout_validated(game, cells, paylines, payout_symbols, payout_rules)
