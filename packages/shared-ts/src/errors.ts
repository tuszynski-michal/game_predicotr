export type DomainErrorCode =
  | 'duplicate_payline'
  | 'duplicate_payout_rule'
  | 'duplicate_payout_symbol'
  | 'duplicate_symbol_code'
  | 'duplicate_symbol_mobile_code'
  | 'incomplete_payout_rules'
  | 'incomplete_payout_symbols'
  | 'invalid_board_length'
  | 'invalid_board_symbol'
  | 'invalid_cell_width'
  | 'invalid_dimensions'
  | 'invalid_forecast_length'
  | 'invalid_forecast_metadata'
  | 'invalid_game'
  | 'invalid_layout_count'
  | 'invalid_match_length'
  | 'invalid_minimum_match_length'
  | 'invalid_payline_id'
  | 'invalid_payout'
  | 'invalid_row_index'
  | 'invalid_row_path_length'
  | 'invalid_sequence_number'
  | 'invalid_signature'
  | 'invalid_spin_cost'
  | 'invalid_target_scan_limit'
  | 'invalid_symbol'
  | 'invalid_symbol_code'
  | 'forecast_numeric_overflow'
  | 'non_prefix_board'
  | 'non_increasing_payout'
  | 'sequence_integrity_error'
  | 'symbol_code_out_of_range'
  | 'wildcard_payout_symbol'
  | 'wildcard_payout_rule';

export class DomainValidationError extends Error {
  readonly code: DomainErrorCode;

  constructor(code: DomainErrorCode, message: string) {
    super(message);
    this.name = 'DomainValidationError';
    this.code = code;
  }
}
