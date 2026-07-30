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
  readonly isActive: boolean;
  readonly minimumMatchLength: number | null;
  readonly payouts: readonly {
    readonly matchLength: number;
    readonly payoutCredits: number;
  }[];
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
  const minimum = symbol.isWildcard
    ? null
    : (configuration?.minimumMatchLength ?? defaultMinimum(columns));
  return {
    credits: Object.fromEntries(
      payoutRules
        .filter((item) => item.symbolId === symbol.id)
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
): PayoutConfigurationValidation {
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

function parseInteger(value: string): number | null {
  const normalized = value.trim();
  if (!/^\d+$/.test(normalized)) return null;
  const parsed = Number(normalized);
  return Number.isSafeInteger(parsed) ? parsed : null;
}
