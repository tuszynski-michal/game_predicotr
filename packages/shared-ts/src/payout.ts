import type {
  CountMatch,
  GameConfig,
  PaylineDefinition,
  PayoutEvaluation,
  PayoutMatch,
  PayoutRuleDefinition,
  PayoutSymbolDefinition,
  SymbolDefinition,
} from './contracts.js';
import {
  isOrdinaryLineSymbol,
  isSuperGameTrigger,
  validateLayoutBoard,
  validatePaylines,
  validatePayoutConfiguration,
} from './validation.js';

/**
 * TypeScript mirror of the worker payout evaluator
 * (`services/worker/.../domain/payout.py`). Both execute
 * `packages/domain-fixtures/payout-golden-cases.json` and must agree on
 * every case.
 *
 * - `payout-v3-unknown-prefix-stop` for a game without a super game trigger
 *   symbol: every `(payline, ordinary symbol)` pair pays its longest prefix
 *   from the first column, Wild substitutes per line and the unknown code `0`
 *   stops the prefix.
 * - `payout-v4-wild-count` for a game with a trigger symbol (D-535): trigger
 *   symbols are not line symbols; each one is paid by the largest configured
 *   count not above the number of its cells on the board (unknown cells never
 *   count).
 */
export const PAYOUT_V3_ALGORITHM_VERSION = 'payout-v3-unknown-prefix-stop';
export const PAYOUT_V4_ALGORITHM_VERSION = 'payout-v4-wild-count';

export function payoutAlgorithmVersion(game: GameConfig): string {
  return game.symbols.some(isSuperGameTrigger)
    ? PAYOUT_V4_ALGORITHM_VERSION
    : PAYOUT_V3_ALGORITHM_VERSION;
}

function byDisplayOrder(a: SymbolDefinition, b: SymbolDefinition): number {
  return a.displayOrder - b.displayOrder || a.mobileCode - b.mobileCode;
}

function largestRuleNotAbove(
  payoutByLength: ReadonlyMap<number, number>,
  limit: number,
): number | undefined {
  let best: number | undefined;
  for (const length of payoutByLength.keys()) {
    if (length <= limit && (best === undefined || length > best)) {
      best = length;
    }
  }
  return best;
}

function compatiblePrefixLength(
  lineCodes: readonly number[],
  symbolCode: number,
  wildcardCodes: ReadonlySet<number>,
): number {
  let length = 0;
  for (const code of lineCodes) {
    if (code === 0) break;
    if (code !== symbolCode && !wildcardCodes.has(code)) break;
    length += 1;
  }
  return length;
}

export function evaluatePayout(
  game: GameConfig,
  cells: readonly number[],
  paylines: readonly PaylineDefinition[],
  payoutSymbols: readonly PayoutSymbolDefinition[],
  payoutRules: readonly PayoutRuleDefinition[],
): PayoutEvaluation {
  validateLayoutBoard(cells, game);
  validatePaylines(paylines, game);
  validatePayoutConfiguration(payoutRules, payoutSymbols, game);

  const wildcardCodes = new Set(
    game.symbols
      .filter((symbol) => symbol.isWildcard)
      .map((symbol) => symbol.mobileCode),
  );
  const ordinarySymbols = game.symbols
    .filter(isOrdinaryLineSymbol)
    .sort(byDisplayOrder);
  const countSymbols = game.symbols
    .filter(isSuperGameTrigger)
    .sort(byDisplayOrder);
  const rulesBySymbol = new Map<number, Map<number, number>>();
  for (const rule of payoutRules) {
    let symbolRules = rulesBySymbol.get(rule.symbolMobileCode);
    if (symbolRules === undefined) {
      symbolRules = new Map<number, number>();
      rulesBySymbol.set(rule.symbolMobileCode, symbolRules);
    }
    symbolRules.set(rule.matchLength, rule.payoutCredits);
  }

  const matches: PayoutMatch[] = [];
  for (const payline of paylines) {
    const lineCells = payline.rowPath.map(
      (row, column) => row * game.columns + column,
    );
    const lineCodes = lineCells.map((cellIndex) => cells[cellIndex] ?? 0);
    for (const symbol of ordinarySymbols) {
      const payoutByLength =
        rulesBySymbol.get(symbol.mobileCode) ?? new Map<number, number>();
      const prefixLength = compatiblePrefixLength(
        lineCodes,
        symbol.mobileCode,
        wildcardCodes,
      );
      const matchedLength = largestRuleNotAbove(payoutByLength, prefixLength);
      if (matchedLength === undefined) continue;
      const matchedCodes = lineCodes.slice(0, matchedLength);
      // A prefix made only of Wild cells never wins as a line.
      if (!matchedCodes.includes(symbol.mobileCode)) continue;
      const matchedCells = lineCells.slice(0, matchedLength);
      const jokerCells = matchedCells.filter((_cellIndex, position) =>
        wildcardCodes.has(matchedCodes[position] ?? 0),
      );
      matches.push({
        symbolMobileCode: symbol.mobileCode,
        paylineId: payline.id,
        startColumn: 0,
        matchedLength,
        matchedCells,
        jokerCells,
        payoutCredits: payoutByLength.get(matchedLength) ?? 0,
        interpretation: jokerCells.map((cellIndex) => ({
          cellIndex,
          asSymbolMobileCode: symbol.mobileCode,
        })),
      });
    }
  }

  const countMatches: CountMatch[] = [];
  for (const symbol of countSymbols) {
    const payoutByCount =
      rulesBySymbol.get(symbol.mobileCode) ?? new Map<number, number>();
    // The unknown code 0 never equals a symbol code, so it is never counted.
    const matchedCells = cells.flatMap((code, cellIndex) =>
      code === symbol.mobileCode ? [cellIndex] : [],
    );
    const paidCount = largestRuleNotAbove(payoutByCount, matchedCells.length);
    if (paidCount === undefined) continue;
    countMatches.push({
      symbolMobileCode: symbol.mobileCode,
      count: matchedCells.length,
      matchedCells,
      payoutCredits: payoutByCount.get(paidCount) ?? 0,
    });
  }

  return {
    totalPayout:
      matches.reduce((total, match) => total + match.payoutCredits, 0) +
      countMatches.reduce((total, match) => total + match.payoutCredits, 0),
    matches,
    countMatches,
  };
}
