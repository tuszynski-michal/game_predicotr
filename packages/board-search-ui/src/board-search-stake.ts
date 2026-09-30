/**
 * Stake and currency presentation for "Przybliżona wygrana" (D-470,
 * TASK-0762). The API always answers in credits at the base stake (the
 * published spin cost); everything here is a local, linear re-scaling:
 * `1 zł = 10 kredytów`, and a stake multiplies payouts and spin costs by
 * `stake / base stake`. Arithmetic stays in whole grosze with a single
 * rounding (halves away from zero) on the final value.
 */

export type ApproximateWinAmountUnit = 'credits' | 'pln';

export interface ApproximateWinDisplay {
  /** `null` means the base stake (the published spin cost). */
  readonly stakeGrosze: number | null;
  readonly unit: ApproximateWinAmountUnit;
}

export const APPROXIMATE_WIN_STAKES_GROSZE: readonly number[] = Object.freeze([
  120, 200, 400, 600, 1000, 2000,
]);

export const APPROXIMATE_WIN_DEFAULT_DISPLAY: ApproximateWinDisplay =
  Object.freeze({ stakeGrosze: null, unit: 'credits' });

export const APPROXIMATE_WIN_DISPLAY_STORAGE_KEY =
  'game-predictor-approximate-win-display-v1';

const GROSZE_PER_CREDIT = 10;

export interface ApproximateWinStakeOption {
  readonly grosze: number;
  readonly isBase: boolean;
  readonly label: string;
}

/** Base stake in grosze: the spin cost converted at 10 credits per złoty. */
export function approximateWinBaseStakeGrosze(spinCost: number): number {
  return spinCost * GROSZE_PER_CREDIT;
}

/**
 * The closed stake list; a base stake outside it is offered as an extra
 * first option "bazowa" so the default view always has a matching option.
 */
export function approximateWinStakeOptions(
  spinCost: number,
): readonly ApproximateWinStakeOption[] {
  const base = approximateWinBaseStakeGrosze(spinCost);
  const options = APPROXIMATE_WIN_STAKES_GROSZE.map((grosze) => ({
    grosze,
    isBase: grosze === base,
    label: `${formatZloty(grosze)}${grosze === base ? ' (bazowa)' : ''}`,
  }));
  if (base > 0 && !APPROXIMATE_WIN_STAKES_GROSZE.includes(base)) {
    options.unshift({
      grosze: base,
      isBase: true,
      label: `${formatZloty(base)} (bazowa)`,
    });
  }
  return options;
}

/** The stake actually in effect; unknown or unusable stakes fall back to base. */
export function effectiveApproximateWinStakeGrosze(
  display: ApproximateWinDisplay,
  spinCost: number,
): number {
  const base = approximateWinBaseStakeGrosze(spinCost);
  if (spinCost <= 0 || display.stakeGrosze === null) return base;
  // Membership only: building labelled options here would run per amount.
  return APPROXIMATE_WIN_STAKES_GROSZE.includes(display.stakeGrosze)
    ? display.stakeGrosze
    : base;
}

/**
 * Integer division rounding halves away from zero, built from quotient and
 * remainder so no floating-point division decides the result.
 */
export function roundDivideHalfAwayFromZero(
  numerator: number,
  denominator: number,
): number {
  if (
    !Number.isSafeInteger(numerator) ||
    !Number.isSafeInteger(denominator) ||
    denominator <= 0
  ) {
    throw new RangeError('Stake arithmetic requires safe integers.');
  }
  const remainder = numerator % denominator;
  // `numerator - remainder` is an exact multiple of `denominator`.
  const quotient = (numerator - remainder) / denominator;
  if (2 * Math.abs(remainder) >= denominator) {
    return quotient + Math.sign(numerator);
  }
  return quotient + 0;
}

/**
 * Scale a base-stake credit amount to the chosen stake, in whole grosze.
 * With no spin cost there is no base for a stake, so only the currency
 * conversion (credits / 10 = złote) applies.
 */
export function scaleApproximateWinAmount(
  baseCredits: number,
  display: ApproximateWinDisplay,
  spinCost: number,
): number {
  return scaleApproximateWinAmountAtStake(
    baseCredits,
    effectiveApproximateWinStakeGrosze(display, spinCost),
    spinCost,
  );
}

/**
 * Hot-path variant for callers that resolved the stake once per render
 * (tables and chart series call this for every amount).
 */
export function scaleApproximateWinAmountAtStake(
  baseCredits: number,
  stakeGrosze: number,
  spinCost: number,
): number {
  if (spinCost <= 0) {
    return baseCredits * GROSZE_PER_CREDIT;
  }
  // Throws on unsafe integers: a programming error, not a data state.
  return roundDivideHalfAwayFromZero(baseCredits * stakeGrosze, spinCost);
}

/** Numeric value in the chosen unit, for plotting (not for display text). */
export function approximateWinDisplayValue(
  grosze: number,
  unit: ApproximateWinAmountUnit,
): number {
  return unit === 'pln' ? grosze / 100 : grosze / GROSZE_PER_CREDIT;
}

/**
 * Format an amount already scaled to grosze. Credits stay a bare number
 * (identical to the pre-stake view at the base stake); złote carry "zł".
 */
export function formatApproximateWinAmount(
  grosze: number,
  unit: ApproximateWinAmountUnit,
): string {
  if (unit === 'pln') return formatZloty(grosze);
  return (grosze / GROSZE_PER_CREDIT).toLocaleString('pl-PL', {
    maximumFractionDigits: 1,
  });
}

/** Axis tick text for a value already in the chosen unit. */
export function formatApproximateWinAxisValue(
  value: number,
  unit: ApproximateWinAmountUnit,
): string {
  return value.toLocaleString('pl-PL', {
    maximumFractionDigits: unit === 'pln' ? 2 : 1,
  });
}

/** Human multiplier relative to the base stake, e.g. "0,6". */
export function approximateWinStakeMultiplier(
  display: ApproximateWinDisplay,
  spinCost: number,
): string {
  if (spinCost <= 0) return '1';
  const stake = effectiveApproximateWinStakeGrosze(display, spinCost);
  return (stake / approximateWinBaseStakeGrosze(spinCost)).toLocaleString(
    'pl-PL',
    { maximumFractionDigits: 4 },
  );
}

export function formatZloty(grosze: number): string {
  return `${(grosze / 100).toLocaleString('pl-PL', {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  })} zł`;
}

type StorageLike = Pick<Storage, 'getItem' | 'setItem'>;

function browserStorage(): StorageLike | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** Read the remembered view preference; anything invalid means defaults. */
export function loadApproximateWinDisplay(
  storage: StorageLike | null = browserStorage(),
): ApproximateWinDisplay {
  if (storage === null) return APPROXIMATE_WIN_DEFAULT_DISPLAY;
  try {
    const parsed: unknown = JSON.parse(
      storage.getItem(APPROXIMATE_WIN_DISPLAY_STORAGE_KEY) ?? 'null',
    );
    if (typeof parsed !== 'object' || parsed === null) {
      return APPROXIMATE_WIN_DEFAULT_DISPLAY;
    }
    const record = parsed as Record<string, unknown>;
    const unit =
      record.unit === 'pln' || record.unit === 'credits'
        ? record.unit
        : 'credits';
    const stakeGrosze =
      typeof record.stakeGrosze === 'number' &&
      Number.isSafeInteger(record.stakeGrosze) &&
      record.stakeGrosze > 0
        ? record.stakeGrosze
        : null;
    return { stakeGrosze, unit };
  } catch {
    return APPROXIMATE_WIN_DEFAULT_DISPLAY;
  }
}

export function saveApproximateWinDisplay(
  display: ApproximateWinDisplay,
  storage: StorageLike | null = browserStorage(),
): void {
  if (storage === null) return;
  try {
    storage.setItem(
      APPROXIMATE_WIN_DISPLAY_STORAGE_KEY,
      JSON.stringify(display),
    );
  } catch {
    // A view preference that cannot be stored only resets on the next visit.
  }
}
