"""Pure build-time payout evaluation.

One evaluator serves two algorithm versions, chosen per game
(`payout_algorithm_version`):

- `payout-v3-unknown-prefix-stop` for a game without a super game trigger
  symbol: every `(payline, ordinary symbol)` pair pays its longest prefix from
  the first column, Wild substitutes per line and the unknown code `0` stops
  the prefix.
- `payout-v4-wild-count` for a game with at least one trigger symbol (D-535):
  the same line rules, except that trigger symbols are no longer ordinary
  line symbols, plus one count match per trigger symbol: its cells anywhere
  on the board, paid by the largest configured count not above that number.

For a game without a trigger symbol both descriptions are the same
computation, so 777 results and audits stay byte-identical to v3.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from game_predictor_worker.domain.contracts import (
    CountMatch,
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
    is_ordinary_line_symbol,
    is_super_game_trigger,
    validate_full_board,
    validate_layout_board,
    validate_paylines,
    validate_payout_configuration,
)

PAYOUT_V3_ALGORITHM_VERSION = "payout-v3-unknown-prefix-stop"
PAYOUT_V4_ALGORITHM_VERSION = "payout-v4-wild-count"


def payout_algorithm_version(game: GameConfig) -> str:
    """The payout algorithm version a game is evaluated and reported with.

    Only a game with a super game trigger symbol uses `payout-v4-wild-count`;
    every other game keeps reporting `payout-v3-unknown-prefix-stop`.
    """

    if any(is_super_game_trigger(symbol) for symbol in game.symbols):
        return PAYOUT_V4_ALGORITHM_VERSION
    return PAYOUT_V3_ALGORITHM_VERSION


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
    """Symbols evaluated on paylines: neither Wild nor a super game trigger."""

    return tuple(
        sorted(
            (symbol for symbol in symbols if is_ordinary_line_symbol(symbol)),
            key=lambda symbol: (symbol.display_order, symbol.mobile_code),
        )
    )


def _count_symbols_by_display_order(
    symbols: Sequence[SymbolDefinition],
) -> tuple[SymbolDefinition, ...]:
    """Super game trigger symbols, paid per count of their cells on the board."""

    return tuple(
        sorted(
            (symbol for symbol in symbols if is_super_game_trigger(symbol)),
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


def _evaluate_count_matches(
    *,
    cells: Sequence[int],
    count_symbols: Sequence[SymbolDefinition],
    rules_by_symbol: Mapping[int, Mapping[int, int]],
) -> tuple[CountMatch, ...]:
    """Pay every trigger symbol by the number of its cells on the board.

    Position and order do not matter. An unknown cell (`0`) is never counted,
    so on a partial board the count, and its payout, is a lower bound. The
    largest configured count not above the board count pays; a symbol
    without such a rule (or without any count rule) pays nothing.
    """

    matches: list[CountMatch] = []
    for symbol in count_symbols:
        payout_by_count = rules_by_symbol.get(symbol.mobile_code, {})
        matched_cells = tuple(
            cell_index for cell_index, code in enumerate(cells) if code == symbol.mobile_code
        )
        paid_count = next(
            (
                count
                for count in sorted(payout_by_count, reverse=True)
                if count <= len(matched_cells)
            ),
            None,
        )
        if paid_count is None:
            continue
        matches.append(
            CountMatch(
                symbol_mobile_code=symbol.mobile_code,
                count=len(matched_cells),
                matched_cells=matched_cells,
                payout_credits=payout_by_count[paid_count],
            )
        )
    return tuple(matches)


def _evaluate_matches(
    *,
    cells: Sequence[int],
    paylines: Sequence[PaylineDefinition],
    line_cell_indices_by_payline: Sequence[tuple[int, ...]],
    ordinary_symbols: Sequence[SymbolDefinition],
    count_symbols: Sequence[SymbolDefinition],
    wildcard_codes: frozenset[int],
    rules_by_symbol: Mapping[int, Mapping[int, int]],
) -> PayoutEvaluation:
    """Match every active `(payline, ordinary symbol)` pair against `cells`,
    then pay every super game trigger symbol by its count on the board.

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

    count_matches = _evaluate_count_matches(
        cells=cells,
        count_symbols=count_symbols,
        rules_by_symbol=rules_by_symbol,
    )
    return PayoutEvaluation(
        total_payout=sum(match.payout_credits for match in matches)
        + sum(match.payout_credits for match in count_matches),
        matches=tuple(matches),
        count_matches=count_matches,
    )


@dataclass(frozen=True, slots=True)
class PreparedPayoutEvaluator:
    """A payout evaluator (v3, or v4 for a game with a trigger symbol) with
    its paylines and payout configuration validated and precomputed once.

    Building one costs the same validation as a single `evaluate_payout`
    call. Each subsequent `evaluate` only re-validates the board layout and
    reuses the precomputed wildcard set, symbol order and payout-by-length
    lookup, instead of re-validating the whole rules matrix. Intended for
    callers that evaluate many boards against one fixed rules version (e.g.
    an admin payout-range calculator), where repeating full
    payout-configuration validation per board would be wasted, and
    otherwise identical, work.
    """

    game: GameConfig
    paylines: tuple[PaylineDefinition, ...]
    wildcard_codes: frozenset[int]
    ordinary_symbols: tuple[SymbolDefinition, ...]
    rules_by_symbol: Mapping[int, Mapping[int, int]]
    line_cell_indices_by_payline: tuple[tuple[int, ...], ...]
    count_symbols: tuple[SymbolDefinition, ...] = ()

    @property
    def algorithm_version(self) -> str:
        """`payout-v4-wild-count` with a trigger symbol, otherwise v3."""

        return payout_algorithm_version(self.game)

    def evaluate(self, cells: Sequence[int]) -> PayoutEvaluation:
        """Evaluate one board, stopping each line at the first unknown cell."""

        validate_layout_board(cells, self.game)
        return _evaluate_matches(
            cells=cells,
            paylines=self.paylines,
            line_cell_indices_by_payline=self.line_cell_indices_by_payline,
            ordinary_symbols=self.ordinary_symbols,
            count_symbols=self.count_symbols,
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
    the lookups payout evaluation needs, for reuse across many boards.

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
        count_symbols=_count_symbols_by_display_order(game.symbols),
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
        count_symbols=_count_symbols_by_display_order(game.symbols),
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
    """Evaluate one board with the game's algorithm version
    (`payout_algorithm_version`), stopping each line at the first unknown cell.
    """

    validate_layout_board(cells, game)
    return _evaluate_payout_validated(game, cells, paylines, payout_symbols, payout_rules)


def evaluate_payout_v2(
    game: GameConfig,
    cells: Sequence[int],
    paylines: Sequence[PaylineDefinition],
    payout_symbols: Sequence[PayoutSymbolDefinition],
    payout_rules: Sequence[PayoutRuleDefinition],
) -> PayoutEvaluation:
    """Reproduce historical payout-v2, which rejects unknown cells.

    Historical v2 data has no super game trigger symbols; the payout job
    rejects a v2 or v3 job for a game that has one.
    """

    validate_full_board(cells, game)
    return _evaluate_payout_validated(game, cells, paylines, payout_symbols, payout_rules)
