"""Stable validation errors for domain boundaries."""

from __future__ import annotations

from enum import StrEnum


class DomainErrorCode(StrEnum):
    DUPLICATE_PAYLINE = "duplicate_payline"
    DUPLICATE_PAYOUT_RULE = "duplicate_payout_rule"
    DUPLICATE_SYMBOL_CODE = "duplicate_symbol_code"
    DUPLICATE_SYMBOL_MOBILE_CODE = "duplicate_symbol_mobile_code"
    INCOMPLETE_PAYOUT_RULES = "incomplete_payout_rules"
    INVALID_BOARD_LENGTH = "invalid_board_length"
    INVALID_BOARD_SYMBOL = "invalid_board_symbol"
    INVALID_CELL_WIDTH = "invalid_cell_width"
    INVALID_DIMENSIONS = "invalid_dimensions"
    INVALID_GAME = "invalid_game"
    INVALID_MATCH_LENGTH = "invalid_match_length"
    INVALID_PAYLINE_ID = "invalid_payline_id"
    INVALID_PAYOUT = "invalid_payout"
    INVALID_ROW_INDEX = "invalid_row_index"
    INVALID_ROW_PATH_LENGTH = "invalid_row_path_length"
    INVALID_SIGNATURE = "invalid_signature"
    INVALID_SPIN_COST = "invalid_spin_cost"
    INVALID_SYMBOL = "invalid_symbol"
    INVALID_SYMBOL_CODE = "invalid_symbol_code"
    NON_PREFIX_BOARD = "non_prefix_board"
    NON_INCREASING_PAYOUT = "non_increasing_payout"
    SYMBOL_CODE_OUT_OF_RANGE = "symbol_code_out_of_range"
    UNSUPPORTED_PAYOUT_BOARD_WIDTH = "unsupported_payout_board_width"
    WILDCARD_PAYOUT_RULE = "wildcard_payout_rule"


class DomainValidationError(ValueError):
    """A deterministic domain validation failure."""

    def __init__(self, code: DomainErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
