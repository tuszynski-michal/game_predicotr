export type DomainErrorCode =
  | 'duplicate_payline'
  | 'duplicate_payout_rule'
  | 'duplicate_symbol_code'
  | 'duplicate_symbol_mobile_code'
  | 'invalid_board_length'
  | 'invalid_board_symbol'
  | 'invalid_cell_width'
  | 'invalid_dimensions'
  | 'invalid_game'
  | 'invalid_match_length'
  | 'invalid_payline_id'
  | 'invalid_payout'
  | 'invalid_row_index'
  | 'invalid_row_path_length'
  | 'invalid_signature'
  | 'invalid_spin_cost'
  | 'invalid_symbol'
  | 'invalid_symbol_code'
  | 'non_prefix_board'
  | 'symbol_code_out_of_range'
  | 'wildcard_payout_rule';

export class DomainValidationError extends Error {
  readonly code: DomainErrorCode;

  constructor(code: DomainErrorCode, message: string) {
    super(message);
    this.name = 'DomainValidationError';
    this.code = code;
  }
}
