import type {
  PayoutRuleResponse,
  RulesVersionSymbolResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';

const MAX_CREDITS = 2_147_483_647;

export interface PayoutConfigurationDraft {
  readonly credits: Readonly<Record<number, string>>;
  readonly isActive: boolean;
  readonly minimumMatchLength: string;
}

export interface ValidatedPayoutConfiguration {
  /**
   * Count payouts of a super game trigger symbol (D-535): every active payout
   * of the symbol that is not listed in `payouts` is archived on save.
   */
  readonly archiveUnlistedPayouts?: boolean;
  readonly isActive: boolean;
  readonly minimumMatchLength: number | null;
  readonly payouts: readonly {
    readonly matchLength: number;
    readonly payoutCredits: number;
  }[];
}

const MINIMUM_COUNT_PAYOUT_LENGTH = 2;

/** A symbol with the „Uruchamia supergrę” role is paid per count on the board. */
export function isSuperGameTriggerSymbol(
  symbol: Pick<SymbolResponse, 'superGameTriggerCount'>,
): boolean {
  return symbol.superGameTriggerCount !== null;
}

/** Counts a trigger symbol can be paid for: 2..rows*columns cells. */
export function countPayoutLengths(
  rows: number,
  columns: number,
): readonly number[] {
  const maximum = rows * columns;
  return maximum < MINIMUM_COUNT_PAYOUT_LENGTH
    ? []
    : requiredMatchLengths(MINIMUM_COUNT_PAYOUT_LENGTH, maximum);
}

export function payoutLengthLabel(
  symbol: Pick<SymbolResponse, 'superGameTriggerCount'>,
  matchLength: number,
): string {
  return isSuperGameTriggerSymbol(symbol)
    ? `${matchLength} sztuk na planszy`
    : `${matchLength} kolejnych symboli`;
}

export type PayoutConfigurationValidation =
  | { readonly valid: true; readonly value: ValidatedPayoutConfiguration }
  | { readonly error: string; readonly valid: false };

export function defaultMinimum(columns: number): number | null {
  if (columns < 2) return null;
  return Math.min(3, columns);
}

export function payoutConfigurationToDraft(
  symbol: SymbolResponse,
  configuration: RulesVersionSymbolResponse | undefined,
  payoutRules: readonly PayoutRuleResponse[],
  columns: number,
): PayoutConfigurationDraft {
  const minimum =
    symbol.isWildcard || isSuperGameTriggerSymbol(symbol)
      ? null
      : (configuration?.minimumMatchLength ?? defaultMinimum(columns));
  return {
    credits: Object.fromEntries(
      payoutRules
        .filter(
          (item) =>
            item.symbolId === symbol.id &&
            // An archived count payout must not reappear as a live value.
            (item.isActive || !isSuperGameTriggerSymbol(symbol)),
        )
        .map((item) => [item.matchLength, String(item.payoutCredits)]),
    ),
    isActive: configuration?.isActive ?? true,
    minimumMatchLength: minimum === null ? '' : String(minimum),
  };
}

export function changePayoutMinimum(
  draft: PayoutConfigurationDraft,
  minimumMatchLength: string,
): PayoutConfigurationDraft {
  return { ...draft, minimumMatchLength };
}

export function changePayoutCredits(
  draft: PayoutConfigurationDraft,
  matchLength: number,
  value: string,
): PayoutConfigurationDraft {
  return {
    ...draft,
    credits: { ...draft.credits, [matchLength]: value },
  };
}

export function requiredMatchLengths(
  minimumMatchLength: number,
  columns: number,
): readonly number[] {
  return Array.from(
    { length: columns - minimumMatchLength + 1 },
    (_, index) => minimumMatchLength + index,
  );
}

export function validatePayoutConfiguration(
  symbol: SymbolResponse,
  draft: PayoutConfigurationDraft,
  columns: number,
  rows = 1,
): PayoutConfigurationValidation {
  if (isSuperGameTriggerSymbol(symbol)) {
    return validateCountPayouts(draft, rows, columns);
  }
  if (symbol.isWildcard) {
    return {
      valid: true,
      value: {
        isActive: draft.isActive,
        minimumMatchLength: null,
        payouts: [],
      },
    };
  }
  const minimum = parseInteger(draft.minimumMatchLength);
  if (minimum === null || minimum < 2 || minimum > columns) {
    return {
      error: `Minimum musi być liczbą całkowitą od 2 do ${columns}.`,
      valid: false,
    };
  }
  const payouts: { matchLength: number; payoutCredits: number }[] = [];
  for (const matchLength of requiredMatchLengths(minimum, columns)) {
    const credits = parseInteger(draft.credits[matchLength] ?? '');
    if (credits === null || credits < 0 || credits > MAX_CREDITS) {
      return {
        error: `Podaj całkowitą wartość kredytów 0–${MAX_CREDITS} dla długości ${matchLength}.`,
        valid: false,
      };
    }
    payouts.push({ matchLength, payoutCredits: credits });
  }
  if (
    payouts.some(
      (item, index) =>
        index > 0 && item.payoutCredits <= payouts[index - 1]!.payoutCredits,
    )
  ) {
    return {
      error: 'Wartość wypłaty musi ściśle rosnąć wraz z długością ciągu.',
      valid: false,
    };
  }
  return {
    valid: true,
    value: {
      isActive: draft.isActive,
      minimumMatchLength: minimum,
      payouts,
    },
  };
}

export function upsertRulesSymbol(
  configurations: readonly RulesVersionSymbolResponse[],
  saved: RulesVersionSymbolResponse,
): readonly RulesVersionSymbolResponse[] {
  return configurations.some((item) => item.symbolId === saved.symbolId)
    ? configurations.map((item) =>
        item.symbolId === saved.symbolId ? saved : item,
      )
    : [...configurations, saved];
}

export function upsertPayoutRules(
  payoutRules: readonly PayoutRuleResponse[],
  saved: readonly PayoutRuleResponse[],
): readonly PayoutRuleResponse[] {
  const replacements = new Map(saved.map((item) => [item.id, item]));
  const updated = payoutRules.map((item) => replacements.get(item.id) ?? item);
  for (const item of saved) {
    if (!payoutRules.some((existing) => existing.id === item.id)) {
      updated.push(item);
    }
  }
  return updated.sort(
    (left, right) =>
      left.symbolId.localeCompare(right.symbolId) ||
      left.matchLength - right.matchLength ||
      left.id.localeCompare(right.id),
  );
}

/**
 * Trigger symbol payouts (D-535): `matchLength` is a count of cells anywhere on
 * the board. Any subset of counts may be paid; empty fields mean no payout and
 * the filled values must strictly increase with the count. No minimum.
 */
function validateCountPayouts(
  draft: PayoutConfigurationDraft,
  rows: number,
  columns: number,
): PayoutConfigurationValidation {
  const payouts: { matchLength: number; payoutCredits: number }[] = [];
  for (const matchLength of countPayoutLengths(rows, columns)) {
    const raw = (draft.credits[matchLength] ?? '').trim();
    if (raw === '') continue;
    const credits = parseInteger(raw);
    if (credits === null || credits < 0 || credits > MAX_CREDITS) {
      return {
        error: `Podaj całkowitą wartość kredytów 0–${MAX_CREDITS} dla ${matchLength} sztuk na planszy albo zostaw pole puste.`,
        valid: false,
      };
    }
    payouts.push({ matchLength, payoutCredits: credits });
  }
  if (
    payouts.some(
      (item, index) =>
        index > 0 && item.payoutCredits <= payouts[index - 1]!.payoutCredits,
    )
  ) {
    return {
      error:
        'Wartość wypłaty musi ściśle rosnąć wraz z liczbą sztuk na planszy.',
      valid: false,
    };
  }
  return {
    valid: true,
    value: {
      archiveUnlistedPayouts: true,
      isActive: draft.isActive,
      minimumMatchLength: null,
      payouts,
    },
  };
}

function parseInteger(value: string): number | null {
  const normalized = value.trim();
  if (!/^\d+$/.test(normalized)) return null;
  const parsed = Number(normalized);
  return Number.isSafeInteger(parsed) ? parsed : null;
}
