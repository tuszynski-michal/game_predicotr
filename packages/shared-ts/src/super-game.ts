import type {
  CountMatch,
  GameConfig,
  PaylineDefinition,
  PayoutMatch,
  PayoutRuleDefinition,
  PayoutSymbolDefinition,
} from './contracts.js';
import { evaluatePayout } from './payout.js';
import { isOrdinaryLineSymbol } from './validation.js';

/**
 * TypeScript mirror of the worker `wild_super_spins` series board evaluation
 * (`services/worker/.../domain/super_games/wild_super_spins.py`, D-537). Both
 * execute the `wildSuperSpinsScenario` section of
 * `packages/domain-fixtures/payout-golden-cases.json` and must agree.
 *
 * 1. `k` = columns of the original board containing the super symbol X; with
 *    `k < minimum(X)` the board is evaluated exactly as in base mode.
 * 2. Otherwise those columns are filled with X (covering Wilds too).
 * 3. Lines on the expanded board, counts on the original board; X's own line
 *    wins are replaced by `payout_line(X, k) × number of paylines`.
 * 4. `exact` only for a fully known board with a defined super symbol in a
 *    fresh series generation, otherwise `provisional`.
 */
export const WILD_SUPER_SPINS_CODE = 'wild_super_spins';

export type SeriesPayoutKind = 'exact' | 'provisional';

export interface SeriesExpansion {
  readonly symbolMobileCode: number;
  readonly columns: readonly number[];
  readonly columnCount: number;
  readonly linePayoutCredits: number;
  readonly paylineCount: number;
  readonly payoutCredits: number;
}

export interface SeriesBoardEvaluation {
  readonly evaluatedCells: readonly number[];
  readonly matches: readonly PayoutMatch[];
  readonly countMatches: readonly CountMatch[];
  readonly expansion: SeriesExpansion | null;
  readonly totalPayout: number;
  readonly payoutKind: SeriesPayoutKind;
  readonly retrigger: boolean;
}

export interface SeriesBoardOptions {
  readonly generationFresh?: boolean;
}

function lineSuperSymbol(
  game: GameConfig,
  payoutRules: readonly PayoutRuleDefinition[],
  superSymbolMobileCode: number | null,
): number | null {
  if (superSymbolMobileCode === null) return null;
  const symbol = game.symbols.find(
    (candidate) => candidate.mobileCode === superSymbolMobileCode,
  );
  if (symbol === undefined || !isOrdinaryLineSymbol(symbol)) return null;
  return payoutRules.some(
    (rule) => rule.symbolMobileCode === superSymbolMobileCode,
  )
    ? superSymbolMobileCode
    : null;
}

function isRetrigger(game: GameConfig, cells: readonly number[]): boolean {
  return game.symbols.some((symbol) => {
    const threshold = symbol.superGameTriggerCount;
    if (threshold === undefined || threshold === null) return false;
    return (
      cells.filter((code) => code === symbol.mobileCode).length >= threshold
    );
  });
}

export function evaluateSeriesBoard(
  game: GameConfig,
  cells: readonly number[],
  paylines: readonly PaylineDefinition[],
  payoutSymbols: readonly PayoutSymbolDefinition[],
  payoutRules: readonly PayoutRuleDefinition[],
  superSymbolMobileCode: number | null,
  options: SeriesBoardOptions = {},
): SeriesBoardEvaluation {
  const original = [...cells];
  const base = evaluatePayout(
    game,
    original,
    paylines,
    payoutSymbols,
    payoutRules,
  );
  const superSymbol = lineSuperSymbol(game, payoutRules, superSymbolMobileCode);
  const provisional =
    superSymbol === null ||
    options.generationFresh === false ||
    original.some((code) => code === 0);

  let evaluatedCells: readonly number[] = original;
  let matches: readonly PayoutMatch[] = base.matches;
  let expansion: SeriesExpansion | null = null;
  if (superSymbol !== null) {
    const payoutByLength = new Map<number, number>();
    for (const rule of payoutRules) {
      if (rule.symbolMobileCode === superSymbol) {
        payoutByLength.set(rule.matchLength, rule.payoutCredits);
      }
    }
    // Validated rules pay every length from the minimum up to the columns.
    const minimumMatchLength = Math.min(...payoutByLength.keys());
    const columns: number[] = [];
    for (let column = 0; column < game.columns; column += 1) {
      for (let row = 0; row < game.rows; row += 1) {
        if (original[row * game.columns + column] === superSymbol) {
          columns.push(column);
          break;
        }
      }
    }
    if (columns.length >= minimumMatchLength) {
      const covered = new Set(columns);
      evaluatedCells = original.map((code, index) =>
        covered.has(index % game.columns) ? superSymbol : code,
      );
      const expanded = evaluatePayout(
        game,
        evaluatedCells,
        paylines,
        payoutSymbols,
        payoutRules,
      );
      matches = expanded.matches.filter(
        (match) => match.symbolMobileCode !== superSymbol,
      );
      let paidLength = minimumMatchLength;
      for (const length of payoutByLength.keys()) {
        if (length <= columns.length && length > paidLength) {
          paidLength = length;
        }
      }
      const linePayoutCredits = payoutByLength.get(paidLength) ?? 0;
      expansion = {
        symbolMobileCode: superSymbol,
        columns,
        columnCount: columns.length,
        linePayoutCredits,
        paylineCount: paylines.length,
        payoutCredits: linePayoutCredits * paylines.length,
      };
    }
  }

  const totalPayout =
    matches.reduce((total, match) => total + match.payoutCredits, 0) +
    base.countMatches.reduce((total, match) => total + match.payoutCredits, 0) +
    (expansion?.payoutCredits ?? 0);
  return {
    evaluatedCells,
    matches,
    countMatches: base.countMatches,
    expansion,
    totalPayout,
    payoutKind: provisional ? 'provisional' : 'exact',
    retrigger: isRetrigger(game, original),
  };
}
