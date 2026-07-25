"""Framework-independent Game Predictor domain contracts."""

from game_predictor_worker.domain.contracts import (
    ForecastInput,
    ForecastPeak,
    ForecastResult,
    GameConfig,
    JokerInterpretation,
    PaylineDefinition,
    PayoutEvaluation,
    PayoutMatch,
    PayoutRuleDefinition,
    PayoutSymbolDefinition,
    SequencePayout,
    SymbolDefinition,
)
from game_predictor_worker.domain.errors import DomainErrorCode, DomainValidationError
from game_predictor_worker.domain.payout import evaluate_payout
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
    validate_payout_configuration,
    validate_payout_rules,
    validate_payout_symbols,
    validate_row_path,
)

__all__ = [
    "DomainErrorCode",
    "DomainValidationError",
    "ForecastInput",
    "ForecastPeak",
    "ForecastResult",
    "GameConfig",
    "JokerInterpretation",
    "MAX_SIGNATURE_CELL_WIDTH",
    "MAX_SYMBOL_MOBILE_CODE",
    "PaylineDefinition",
    "PayoutEvaluation",
    "PayoutMatch",
    "PayoutRuleDefinition",
    "PayoutSymbolDefinition",
    "SequencePayout",
    "SymbolDefinition",
    "decode_signature",
    "encode_signature",
    "encode_signature_prefix",
    "evaluate_payout",
    "validate_board_dimensions",
    "validate_board_prefix",
    "validate_full_board",
    "validate_game_config",
    "validate_paylines",
    "validate_payout_configuration",
    "validate_payout_rules",
    "validate_payout_symbols",
    "validate_row_path",
]
