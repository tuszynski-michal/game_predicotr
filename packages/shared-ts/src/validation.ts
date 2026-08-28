import type {
  GameConfig,
  PaylineDefinition,
  PayoutRuleDefinition,
  PayoutSymbolDefinition,
  SymbolDefinition,
} from './contracts.js';
import { DomainValidationError } from './errors.js';
import {
  MAX_SIGNATURE_CELL_WIDTH,
  MAX_SYMBOL_MOBILE_CODE,
} from './signature.js';

function requireNonEmpty(
  value: string,
  code: 'invalid_game' | 'invalid_payline_id' | 'invalid_symbol',
): void {
  if (value.trim().length === 0) {
    throw new DomainValidationError(code, 'Value must not be empty.');
  }
}

function requireNonNegativeInteger(
  value: number,
  code: 'invalid_payout' | 'invalid_spin_cost',
  label: string,
): void {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new DomainValidationError(
      code,
      `${label} must be a non-negative safe integer.`,
    );
  }
}

export function validateBoardDimensions(rows: number, columns: number): void {
  if (
    !Number.isSafeInteger(rows) ||
    !Number.isSafeInteger(columns) ||
    rows < 1 ||
    columns < 1
  ) {
    throw new DomainValidationError(
      'invalid_dimensions',
      'Board dimensions must be positive safe integers.',
    );
  }
}

function validateSymbols(
  symbols: readonly SymbolDefinition[],
  cellWidth: number,
): void {
  if (symbols.length === 0) {
    throw new DomainValidationError(
      'invalid_symbol',
      'Game must define at least one symbol.',
    );
  }

  const mobileCodes = new Set<number>();
  const codes = new Set<string>();
  const maximumCode = Math.min(10 ** cellWidth - 1, MAX_SYMBOL_MOBILE_CODE);

  for (const symbol of symbols) {
    requireNonEmpty(symbol.code, 'invalid_symbol');
    requireNonEmpty(symbol.name, 'invalid_symbol');

    if (
      !Number.isSafeInteger(symbol.mobileCode) ||
      symbol.mobileCode < 1 ||
      symbol.mobileCode > maximumCode
    ) {
      throw new DomainValidationError(
        'invalid_symbol_code',
        `Symbol mobile code must fit signature width ${cellWidth}.`,
      );
    }
    if (!Number.isSafeInteger(symbol.displayOrder) || symbol.displayOrder < 0) {
      throw new DomainValidationError(
        'invalid_symbol',
        'Symbol display order must be a non-negative integer.',
      );
    }
    if (mobileCodes.has(symbol.mobileCode)) {
      throw new DomainValidationError(
        'duplicate_symbol_mobile_code',
        `Duplicate symbol mobile code ${symbol.mobileCode}.`,
      );
    }
    if (codes.has(symbol.code)) {
      throw new DomainValidationError(
        'duplicate_symbol_code',
        `Duplicate symbol code ${symbol.code}.`,
      );
    }
    mobileCodes.add(symbol.mobileCode);
    codes.add(symbol.code);
  }
}

export function validateGameConfig(game: GameConfig): void {
  requireNonEmpty(game.id, 'invalid_game');
  requireNonEmpty(game.code, 'invalid_game');
  requireNonEmpty(game.name, 'invalid_game');
  validateBoardDimensions(game.rows, game.columns);
  requireNonNegativeInteger(game.spinCost, 'invalid_spin_cost', 'Spin cost');

  if (
    !Number.isSafeInteger(game.signatureCellWidth) ||
    game.signatureCellWidth < 1 ||
    game.signatureCellWidth > MAX_SIGNATURE_CELL_WIDTH
  ) {
    throw new DomainValidationError(
      'invalid_cell_width',
      `Signature cell width must be between 1 and ${MAX_SIGNATURE_CELL_WIDTH}.`,
    );
  }

  validateSymbols(game.symbols, game.signatureCellWidth);
}

function allowedSymbolCodes(game: GameConfig): ReadonlySet<number> {
  return new Set(game.symbols.map((symbol) => symbol.mobileCode));
}

function validatePopulatedCell(
  cell: number,
  allowedCodes: ReadonlySet<number>,
): void {
  if (!Number.isSafeInteger(cell) || !allowedCodes.has(cell)) {
    throw new DomainValidationError(
      'invalid_board_symbol',
      `Symbol mobile code ${cell} does not belong to the game.`,
    );
  }
}

export function validateFullBoard(
  cells: readonly number[],
  game: GameConfig,
): void {
  validateGameConfig(game);
  const expectedLength = game.rows * game.columns;
  if (cells.length !== expectedLength) {
    throw new DomainValidationError(
      'invalid_board_length',
      `Board contains ${cells.length} cells; expected ${expectedLength}.`,
    );
  }

  const allowedCodes = allowedSymbolCodes(game);
  cells.forEach((cell) => validatePopulatedCell(cell, allowedCodes));
}

export function validateLayoutBoard(
  cells: readonly number[],
  game: GameConfig,
): void {
  validateGameConfig(game);
  const expectedLength = game.rows * game.columns;
  if (cells.length !== expectedLength) {
    throw new DomainValidationError(
      'invalid_board_length',
      `Board contains ${cells.length} cells; expected ${expectedLength}.`,
    );
  }
  const allowedCodes = new Set([0, ...allowedSymbolCodes(game)]);
  cells.forEach((cell) => validatePopulatedCell(cell, allowedCodes));
}

export function validateBoardPrefix(
  cells: readonly (number | null)[],
  game: GameConfig,
): void {
  validateGameConfig(game);
  const expectedLength = game.rows * game.columns;
  if (cells.length !== expectedLength) {
    throw new DomainValidationError(
      'invalid_board_length',
      `Board contains ${cells.length} cells; expected ${expectedLength}.`,
    );
  }

  const allowedCodes = allowedSymbolCodes(game);
  let reachedEmptyCell = false;
  for (const cell of cells) {
    if (cell === null) {
      reachedEmptyCell = true;
      continue;
    }
    if (reachedEmptyCell) {
      throw new DomainValidationError(
        'non_prefix_board',
        'A populated cell cannot occur after an empty prefix cell.',
      );
    }
    validatePopulatedCell(cell, allowedCodes);
  }
}

export function validateRowPath(
  rowPath: readonly number[],
  rows: number,
  columns: number,
): void {
  validateBoardDimensions(rows, columns);
  if (rowPath.length !== columns) {
    throw new DomainValidationError(
      'invalid_row_path_length',
      `Payline contains ${rowPath.length} rows; expected ${columns}.`,
    );
  }
  if (
    rowPath.some(
      (rowIndex) =>
        !Number.isSafeInteger(rowIndex) || rowIndex < 0 || rowIndex >= rows,
    )
  ) {
    throw new DomainValidationError(
      'invalid_row_index',
      `Every payline row index must be between 0 and ${rows - 1}.`,
    );
  }
}

export function validatePaylines(
  paylines: readonly PaylineDefinition[],
  game: GameConfig,
): void {
  validateGameConfig(game);
  const paths = new Set<string>();
  const ids = new Set<string>();

  for (const payline of paylines) {
    requireNonEmpty(payline.id, 'invalid_payline_id');
    validateRowPath(payline.rowPath, game.rows, game.columns);
    const pathKey = payline.rowPath.join(',');
    if (paths.has(pathKey) || ids.has(payline.id)) {
      throw new DomainValidationError(
        'duplicate_payline',
        'Payline id and row path must be unique.',
      );
    }
    paths.add(pathKey);
    ids.add(payline.id);
  }
}

export function validatePayoutSymbols(
  payoutSymbols: readonly PayoutSymbolDefinition[],
  game: GameConfig,
): void {
  validateGameConfig(game);
  const symbolsByCode = new Map(
    game.symbols.map((symbol) => [symbol.mobileCode, symbol]),
  );
  const configuredSymbols = new Set<number>();

  for (const payoutSymbol of payoutSymbols) {
    const symbol = symbolsByCode.get(payoutSymbol.symbolMobileCode);
    if (symbol === undefined) {
      throw new DomainValidationError(
        'invalid_board_symbol',
        `Payout symbol ${payoutSymbol.symbolMobileCode} does not belong to the game.`,
      );
    }
    if (symbol.isWildcard) {
      throw new DomainValidationError(
        'wildcard_payout_symbol',
        'Wildcard symbols cannot define payout configuration.',
      );
    }
    if (
      !Number.isSafeInteger(payoutSymbol.minimumMatchLength) ||
      payoutSymbol.minimumMatchLength < 2 ||
      payoutSymbol.minimumMatchLength > game.columns
    ) {
      throw new DomainValidationError(
        'invalid_minimum_match_length',
        `Minimum match length must be between 2 and ${game.columns}.`,
      );
    }
    if (configuredSymbols.has(payoutSymbol.symbolMobileCode)) {
      throw new DomainValidationError(
        'duplicate_payout_symbol',
        `Duplicate payout configuration for symbol ${payoutSymbol.symbolMobileCode}.`,
      );
    }
    configuredSymbols.add(payoutSymbol.symbolMobileCode);
  }
}

export function validatePayoutRules(
  rules: readonly PayoutRuleDefinition[],
  payoutSymbols: readonly PayoutSymbolDefinition[],
  game: GameConfig,
): void {
  validatePayoutSymbols(payoutSymbols, game);
  const symbolsByCode = new Map(
    game.symbols.map((symbol) => [symbol.mobileCode, symbol]),
  );
  const payoutSymbolsByCode = new Map(
    payoutSymbols.map((symbol) => [symbol.symbolMobileCode, symbol]),
  );
  const keys = new Set<string>();

  for (const rule of rules) {
    const symbol = symbolsByCode.get(rule.symbolMobileCode);
    if (symbol === undefined) {
      throw new DomainValidationError(
        'invalid_board_symbol',
        `Payout symbol ${rule.symbolMobileCode} does not belong to the game.`,
      );
    }
    if (symbol.isWildcard) {
      throw new DomainValidationError(
        'wildcard_payout_rule',
        'Wildcard symbols cannot define payout rules.',
      );
    }
    const payoutSymbol = payoutSymbolsByCode.get(rule.symbolMobileCode);
    if (payoutSymbol === undefined) {
      throw new DomainValidationError(
        'incomplete_payout_symbols',
        `Symbol ${rule.symbolMobileCode} has no payout configuration.`,
      );
    }
    if (
      !Number.isSafeInteger(rule.matchLength) ||
      rule.matchLength < payoutSymbol.minimumMatchLength ||
      rule.matchLength > game.columns
    ) {
      throw new DomainValidationError(
        'invalid_match_length',
        `Match length for symbol ${rule.symbolMobileCode} must be between ${payoutSymbol.minimumMatchLength} and ${game.columns}.`,
      );
    }
    requireNonNegativeInteger(
      rule.payoutCredits,
      'invalid_payout',
      'Payout credits',
    );
    const key = `${rule.symbolMobileCode}:${rule.matchLength}`;
    if (keys.has(key)) {
      throw new DomainValidationError(
        'duplicate_payout_rule',
        'Payout rule symbol and match length must be unique.',
      );
    }
    keys.add(key);
  }
}

export function validatePayoutConfiguration(
  rules: readonly PayoutRuleDefinition[],
  payoutSymbols: readonly PayoutSymbolDefinition[],
  game: GameConfig,
): void {
  validatePayoutRules(rules, payoutSymbols, game);
  const payoutSymbolsByCode = new Map(
    payoutSymbols.map((symbol) => [symbol.symbolMobileCode, symbol]),
  );
  const ordinarySymbols = game.symbols.filter((symbol) => !symbol.isWildcard);

  const missingSymbols = ordinarySymbols
    .filter((symbol) => !payoutSymbolsByCode.has(symbol.mobileCode))
    .map((symbol) => symbol.mobileCode);
  if (
    missingSymbols.length > 0 ||
    payoutSymbols.length !== ordinarySymbols.length
  ) {
    throw new DomainValidationError(
      'incomplete_payout_symbols',
      `Missing payout configuration for symbols ${missingSymbols.join(', ')}.`,
    );
  }

  const rulesBySymbol = new Map<number, Map<number, number>>();
  for (const rule of rules) {
    let symbolRules = rulesBySymbol.get(rule.symbolMobileCode);
    if (symbolRules === undefined) {
      symbolRules = new Map<number, number>();
      rulesBySymbol.set(rule.symbolMobileCode, symbolRules);
    }
    symbolRules.set(rule.matchLength, rule.payoutCredits);
  }

  for (const payoutSymbol of payoutSymbols) {
    const symbolRules =
      rulesBySymbol.get(payoutSymbol.symbolMobileCode) ??
      new Map<number, number>();
    let previousPayout: number | undefined;

    for (
      let length = payoutSymbol.minimumMatchLength;
      length <= game.columns;
      length += 1
    ) {
      const payout = symbolRules.get(length);
      if (payout === undefined) {
        throw new DomainValidationError(
          'incomplete_payout_rules',
          `Symbol ${payoutSymbol.symbolMobileCode} is missing payout rule for length ${length}.`,
        );
      }
      if (previousPayout !== undefined && payout <= previousPayout) {
        throw new DomainValidationError(
          'non_increasing_payout',
          `Payout for symbol ${payoutSymbol.symbolMobileCode} must increase with match length.`,
        );
      }
      previousPayout = payout;
    }
  }
}
