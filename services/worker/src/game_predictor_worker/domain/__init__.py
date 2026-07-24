"""Framework-independent Game Predictor domain contracts."""

from game_predictor_worker.domain.contracts import (
    ForecastPeak,
    ForecastResult,
    GameConfig,
    PaylineDefinition,
    PayoutEvaluation,
    PayoutMatch,
    PayoutRuleDefinition,
    SequencePayout,
    SymbolDefinition,
)
from game_predictor_worker.domain.errors import DomainErrorCode, DomainValidationError
from game_predictor_worker.domain.signature import (
    MAX_SIGNATURE_CELL_WIDTH,
    MAX_SYMBOL_MOBILE_CODE,
    decode_signature,
    encode_signature,
    encode_signature_prefix,
)
from game_predictor_worker.domain.validation import (
    validate_board_dimensions,
    validate_board_prefix,
    validate_full_board,
    validate_game_config,
    validate_paylines,
    validate_payout_rules,
    validate_row_path,
)

__all__ = [
    "DomainErrorCode",
    "DomainValidationError",
    "ForecastPeak",
    "ForecastResult",
    "GameConfig",
    "MAX_SIGNATURE_CELL_WIDTH",
    "MAX_SYMBOL_MOBILE_CODE",
    "PaylineDefinition",
    "PayoutEvaluation",
    "PayoutMatch",
    "PayoutRuleDefinition",
    "SequencePayout",
    "SymbolDefinition",
    "decode_signature",
    "encode_signature",
    "encode_signature_prefix",
    "validate_board_dimensions",
    "validate_board_prefix",
    "validate_full_board",
    "validate_game_config",
    "validate_paylines",
    "validate_payout_rules",
    "validate_row_path",
]
