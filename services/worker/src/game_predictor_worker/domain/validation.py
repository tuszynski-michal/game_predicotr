"""Validation at domain boundaries."""

from __future__ import annotations

from collections.abc import Sequence

from game_predictor_worker.domain.contracts import (
    GameConfig,
    PaylineDefinition,
    PayoutRuleDefinition,
    PayoutSymbolDefinition,
    SymbolDefinition,
)
from game_predictor_worker.domain.errors import DomainErrorCode, DomainValidationError
from game_predictor_worker.domain.signature import (
    MAX_SIGNATURE_CELL_WIDTH,
    MAX_SYMBOL_MOBILE_CODE,
)


def _require_non_empty(value: str, code: DomainErrorCode) -> None:
    if not value.strip():
        raise DomainValidationError(code, "Value must not be empty.")


def _require_non_negative_integer(value: int, code: DomainErrorCode, label: str) -> None:
    if isinstance(value, bool) or value < 0:
        raise DomainValidationError(code, f"{label} must be a non-negative integer.")


def validate_board_dimensions(rows: int, columns: int) -> None:
    if isinstance(rows, bool) or isinstance(columns, bool) or rows < 1 or columns < 1:
        raise DomainValidationError(
            DomainErrorCode.INVALID_DIMENSIONS,
            "Board dimensions must be positive integers.",
        )


def _validate_symbols(symbols: Sequence[SymbolDefinition], cell_width: int) -> None:
    if not symbols:
        raise DomainValidationError(
            DomainErrorCode.INVALID_SYMBOL,
            "Game must define at least one symbol.",
        )

    mobile_codes: set[int] = set()
    codes: set[str] = set()
    maximum_code = min(10**cell_width - 1, MAX_SYMBOL_MOBILE_CODE)

    for symbol in symbols:
        _require_non_empty(symbol.code, DomainErrorCode.INVALID_SYMBOL)
        _require_non_empty(symbol.name, DomainErrorCode.INVALID_SYMBOL)
        if (
            isinstance(symbol.mobile_code, bool)
            or symbol.mobile_code < 1
            or symbol.mobile_code > maximum_code
        ):
            raise DomainValidationError(
                DomainErrorCode.INVALID_SYMBOL_CODE,
                f"Symbol mobile code must fit signature width {cell_width}.",
            )
        if isinstance(symbol.display_order, bool) or symbol.display_order < 0:
            raise DomainValidationError(
                DomainErrorCode.INVALID_SYMBOL,
                "Symbol display order must be a non-negative integer.",
            )
        if symbol.mobile_code in mobile_codes:
            raise DomainValidationError(
                DomainErrorCode.DUPLICATE_SYMBOL_MOBILE_CODE,
                f"Duplicate symbol mobile code {symbol.mobile_code}.",
            )
        if symbol.code in codes:
            raise DomainValidationError(
                DomainErrorCode.DUPLICATE_SYMBOL_CODE,
                f"Duplicate symbol code {symbol.code}.",
            )
        mobile_codes.add(symbol.mobile_code)
        codes.add(symbol.code)


def validate_game_config(game: GameConfig) -> None:
    _require_non_empty(game.id, DomainErrorCode.INVALID_GAME)
    _require_non_empty(game.code, DomainErrorCode.INVALID_GAME)
    _require_non_empty(game.name, DomainErrorCode.INVALID_GAME)
    validate_board_dimensions(game.rows, game.columns)
    _require_non_negative_integer(
        game.spin_cost,
        DomainErrorCode.INVALID_SPIN_COST,
        "Spin cost",
    )
    if (
        isinstance(game.signature_cell_width, bool)
        or game.signature_cell_width < 1
        or game.signature_cell_width > MAX_SIGNATURE_CELL_WIDTH
    ):
        raise DomainValidationError(
            DomainErrorCode.INVALID_CELL_WIDTH,
            f"Signature cell width must be between 1 and {MAX_SIGNATURE_CELL_WIDTH}.",
        )
    _validate_symbols(game.symbols, game.signature_cell_width)


def _validate_populated_cell(cell: int, allowed_codes: frozenset[int]) -> None:
    if isinstance(cell, bool) or cell not in allowed_codes:
        raise DomainValidationError(
            DomainErrorCode.INVALID_BOARD_SYMBOL,
            f"Symbol mobile code {cell} does not belong to the game.",
        )


def validate_full_board(cells: Sequence[int], game: GameConfig) -> None:
    validate_game_config(game)
    expected_length = game.rows * game.columns
    if len(cells) != expected_length:
        raise DomainValidationError(
            DomainErrorCode.INVALID_BOARD_LENGTH,
            f"Board contains {len(cells)} cells; expected {expected_length}.",
        )

    allowed_codes = frozenset(symbol.mobile_code for symbol in game.symbols)
    for cell in cells:
        _validate_populated_cell(cell, allowed_codes)


def validate_board_prefix(cells: Sequence[int | None], game: GameConfig) -> None:
    validate_game_config(game)
    expected_length = game.rows * game.columns
    if len(cells) != expected_length:
        raise DomainValidationError(
            DomainErrorCode.INVALID_BOARD_LENGTH,
            f"Board contains {len(cells)} cells; expected {expected_length}.",
        )

    allowed_codes = frozenset(symbol.mobile_code for symbol in game.symbols)
    reached_empty_cell = False
    for cell in cells:
        if cell is None:
            reached_empty_cell = True
            continue
        if reached_empty_cell:
            raise DomainValidationError(
                DomainErrorCode.NON_PREFIX_BOARD,
                "A populated cell cannot occur after an empty prefix cell.",
            )
        _validate_populated_cell(cell, allowed_codes)


def validate_row_path(
    row_path: Sequence[int],
    rows: int,
    columns: int,
) -> None:
    validate_board_dimensions(rows, columns)
    if len(row_path) != columns:
        raise DomainValidationError(
            DomainErrorCode.INVALID_ROW_PATH_LENGTH,
            f"Payline contains {len(row_path)} rows; expected {columns}.",
        )
    if any(
        isinstance(row_index, bool) or row_index < 0 or row_index >= rows for row_index in row_path
    ):
        raise DomainValidationError(
            DomainErrorCode.INVALID_ROW_INDEX,
            f"Every payline row index must be between 0 and {rows - 1}.",
        )


def validate_paylines(
    paylines: Sequence[PaylineDefinition],
    game: GameConfig,
) -> None:
    validate_game_config(game)
    paths: set[tuple[int, ...]] = set()
    ids: set[str] = set()

    for payline in paylines:
        _require_non_empty(payline.id, DomainErrorCode.INVALID_PAYLINE_ID)
        validate_row_path(payline.row_path, game.rows, game.columns)
        if payline.row_path in paths or payline.id in ids:
            raise DomainValidationError(
                DomainErrorCode.DUPLICATE_PAYLINE,
                "Payline id and row path must be unique.",
            )
        paths.add(payline.row_path)
        ids.add(payline.id)


def validate_payout_symbols(
    payout_symbols: Sequence[PayoutSymbolDefinition],
    game: GameConfig,
) -> None:
    validate_game_config(game)
    symbols_by_code = {symbol.mobile_code: symbol for symbol in game.symbols}
    configured_symbols: set[int] = set()

    for payout_symbol in payout_symbols:
        symbol = symbols_by_code.get(payout_symbol.symbol_mobile_code)
        if symbol is None:
            raise DomainValidationError(
                DomainErrorCode.INVALID_BOARD_SYMBOL,
                (f"Payout symbol {payout_symbol.symbol_mobile_code} does not belong to the game."),
            )
        if symbol.is_wildcard:
            raise DomainValidationError(
                DomainErrorCode.WILDCARD_PAYOUT_SYMBOL,
                "Wildcard symbols cannot define payout configuration.",
            )
        if (
            isinstance(payout_symbol.minimum_match_length, bool)
            or payout_symbol.minimum_match_length < 2
            or payout_symbol.minimum_match_length > game.columns
        ):
            raise DomainValidationError(
                DomainErrorCode.INVALID_MINIMUM_MATCH_LENGTH,
                (f"Minimum match length must be between 2 and {game.columns}."),
            )
        if payout_symbol.symbol_mobile_code in configured_symbols:
            raise DomainValidationError(
                DomainErrorCode.DUPLICATE_PAYOUT_SYMBOL,
                (f"Duplicate payout configuration for symbol {payout_symbol.symbol_mobile_code}."),
            )
        configured_symbols.add(payout_symbol.symbol_mobile_code)


def validate_payout_rules(
    rules: Sequence[PayoutRuleDefinition],
    payout_symbols: Sequence[PayoutSymbolDefinition],
    game: GameConfig,
) -> None:
    validate_payout_symbols(payout_symbols, game)
    symbols_by_code = {symbol.mobile_code: symbol for symbol in game.symbols}
    payout_symbols_by_code = {symbol.symbol_mobile_code: symbol for symbol in payout_symbols}
    keys: set[tuple[int, int]] = set()

    for rule in rules:
        symbol = symbols_by_code.get(rule.symbol_mobile_code)
        if symbol is None:
            raise DomainValidationError(
                DomainErrorCode.INVALID_BOARD_SYMBOL,
                f"Payout symbol {rule.symbol_mobile_code} does not belong to the game.",
            )
        if symbol.is_wildcard:
            raise DomainValidationError(
                DomainErrorCode.WILDCARD_PAYOUT_RULE,
                "Wildcard symbols cannot define payout rules.",
            )
        payout_symbol = payout_symbols_by_code.get(rule.symbol_mobile_code)
        if payout_symbol is None:
            raise DomainValidationError(
                DomainErrorCode.INCOMPLETE_PAYOUT_SYMBOLS,
                f"Symbol {rule.symbol_mobile_code} has no payout configuration.",
            )
        if (
            isinstance(rule.match_length, bool)
            or rule.match_length < payout_symbol.minimum_match_length
            or rule.match_length > game.columns
        ):
            raise DomainValidationError(
                DomainErrorCode.INVALID_MATCH_LENGTH,
                (
                    f"Match length for symbol {rule.symbol_mobile_code} must be "
                    f"between {payout_symbol.minimum_match_length} "
                    f"and {game.columns}."
                ),
            )
        _require_non_negative_integer(
            rule.payout_credits,
            DomainErrorCode.INVALID_PAYOUT,
            "Payout credits",
        )
        key = (rule.symbol_mobile_code, rule.match_length)
        if key in keys:
            raise DomainValidationError(
                DomainErrorCode.DUPLICATE_PAYOUT_RULE,
                "Payout rule symbol and match length must be unique.",
            )
        keys.add(key)


def validate_payout_configuration(
    rules: Sequence[PayoutRuleDefinition],
    payout_symbols: Sequence[PayoutSymbolDefinition],
    game: GameConfig,
) -> None:
    """Validate a complete rules matrix ready for payout precomputing."""

    validate_payout_rules(rules, payout_symbols, game)
    payout_symbols_by_code = {
        payout_symbol.symbol_mobile_code: payout_symbol for payout_symbol in payout_symbols
    }
    ordinary_symbols = tuple(symbol for symbol in game.symbols if not symbol.is_wildcard)
    missing_symbols = [
        symbol.mobile_code
        for symbol in ordinary_symbols
        if symbol.mobile_code not in payout_symbols_by_code
    ]
    if missing_symbols or len(payout_symbols) != len(ordinary_symbols):
        raise DomainValidationError(
            DomainErrorCode.INCOMPLETE_PAYOUT_SYMBOLS,
            f"Missing payout configuration for symbols {missing_symbols}.",
        )

    rules_by_symbol: dict[int, dict[int, int]] = {}
    for rule in rules:
        rules_by_symbol.setdefault(rule.symbol_mobile_code, {})[rule.match_length] = (
            rule.payout_credits
        )

    for payout_symbol in payout_symbols:
        expected_lengths = tuple(range(payout_symbol.minimum_match_length, game.columns + 1))
        symbol_rules = rules_by_symbol.get(payout_symbol.symbol_mobile_code, {})
        missing_lengths = [length for length in expected_lengths if length not in symbol_rules]
        if missing_lengths:
            raise DomainValidationError(
                DomainErrorCode.INCOMPLETE_PAYOUT_RULES,
                (
                    f"Symbol {payout_symbol.symbol_mobile_code} is missing payout rules "
                    f"for lengths {missing_lengths}."
                ),
            )

        previous_payout: int | None = None
        for length in expected_lengths:
            payout = symbol_rules[length]
            if previous_payout is not None and payout <= previous_payout:
                raise DomainValidationError(
                    DomainErrorCode.NON_INCREASING_PAYOUT,
                    (
                        f"Payout for symbol {payout_symbol.symbol_mobile_code} "
                        "must increase "
                        f"with match length; length {length} has value {payout}."
                    ),
                )
            previous_payout = payout
