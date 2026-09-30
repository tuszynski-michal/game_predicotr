import type { ApproximateWinResponse } from '@game-predictor/admin-api-client';

/**
 * "Zakres wygranej": how many future spins S+1..S+N are evaluated. Default
 * and ceiling are independent of "Liczba wyników" (board-search-results-state.ts).
 * The ceiling matches the API's own `APPROXIMATE_WIN_SPIN_COUNT_MAX` —
 * TASK-0652, `application/board_search_approximate_win.py`.
 */
export const APPROXIMATE_WIN_RANGE_DEFAULT = 2500;
export const APPROXIMATE_WIN_RANGE_MAX = 100_000;

export interface ApproximateWinChartPoint {
  readonly cumulativeBalanceCredits: number;
  /**
   * `before_payout` is the balance after the spin cost and before its payout:
   * between payouts the balance only falls by the spin cost, so the series is
   * a saw and never hides the drawdowns.
   */
  readonly kind: 'before_payout' | 'end' | 'payout' | 'start';
  readonly spinNumber: number;
}

export type ParsedApproximateWinRange =
  | { readonly ok: true; readonly value: number }
  | { readonly ok: false; readonly error: string };

export function parseApproximateWinRange(
  text: string,
): ParsedApproximateWinRange {
  const trimmed = text.trim();
  if (trimmed === '') {
    return { error: 'Podaj zakres wygranej.', ok: false };
  }
  if (!/^\d+$/.test(trimmed)) {
    return { error: 'Zakres wygranej musi być liczbą całkowitą.', ok: false };
  }
  const value = Number.parseInt(trimmed, 10);
  if (value < 1 || value > APPROXIMATE_WIN_RANGE_MAX) {
    return {
      error: `Zakres wygranej musi być z zakresu 1–${APPROXIMATE_WIN_RANGE_MAX.toLocaleString('pl-PL')}.`,
      ok: false,
    };
  }
  return { ok: true, value };
}

/**
 * Identifies exactly what one calculation was for: the selected board (by
 * its stable identity, not ranking position) and the committed range. A
 * result is only ever shown when its key matches the current selection and
 * range — this is what makes a stale response, or a result left over from a
 * board/range that no longer applies, impossible to display by accident.
 */
export function approximateWinRequestKey(params: {
  readonly gameId: string;
  readonly resultIdentity: string;
  readonly spinCount: number;
}): string {
  return `${params.gameId}|${params.resultIdentity}|${params.spinCount}`;
}

export type ApproximateWinState =
  | { readonly kind: 'idle' }
  | { readonly kind: 'loading'; readonly key: string }
  | {
      readonly kind: 'ready';
      readonly key: string;
      readonly result: ApproximateWinResponse;
    }
  | { readonly kind: 'error'; readonly key: string; readonly message: string };

export const APPROXIMATE_WIN_IDLE_STATE: ApproximateWinState = Object.freeze({
  kind: 'idle',
});

/**
 * Decide whether the current (open, selected board, committed range)
 * combination needs a new request. `requestKey` is `null` whenever the
 * section is closed or nothing is selected — collapsing never triggers a
 * calculation, and neither does switching candidates while collapsed
 * (the caller only calls this once the section is open, keyed off the
 * current selection/range, so a null key naturally short-circuits both).
 * While the section stays open, a key with a `ready`/`error` result is not
 * requested again. Collapsing resets the component state to `idle` (D-462),
 * so reopening always recalculates from the current verified symbols; there
 * is no server-side cache (TASK-0651/0652).
 */
export function shouldRequestApproximateWin(params: {
  readonly isOpen: boolean;
  readonly requestKey: string | null;
  readonly state: ApproximateWinState;
}): boolean {
  if (!params.isOpen || params.requestKey === null) {
    return false;
  }
  if (params.state.kind === 'idle') {
    return true;
  }
  return params.state.key !== params.requestKey;
}

/**
 * The result to render for the current selection/range, or `null` when
 * there isn't one yet (or the last `ready` result belongs to a superseded
 * key and must not be shown as if it were current).
 */
export function visibleApproximateWinResult(
  state: ApproximateWinState,
  currentKey: string | null,
): ApproximateWinResponse | null {
  if (
    state.kind !== 'ready' ||
    currentKey === null ||
    state.key !== currentKey
  ) {
    return null;
  }
  return state.result;
}

/**
 * Builds a cumulative-balance chart series from the rows returned by the API.
 * The origin is explicit so the graph never implies a balance before the first
 * spin. Rows already contain cumulative values for all evaluated spins,
 * including the losing and missing ones absent from `rows`; the balance just
 * before a payout is its cumulative balance minus that payout. The series ends
 * at the last evaluated spin with the summary balance.
 */
export function approximateWinChartPoints(
  rows: ApproximateWinResponse['rows'],
  end?: { readonly balanceCredits: number; readonly spinNumber: number },
): readonly ApproximateWinChartPoint[] {
  const points: ApproximateWinChartPoint[] = [
    { cumulativeBalanceCredits: 0, kind: 'start', spinNumber: 0 },
  ];
  for (const row of rows) {
    points.push(
      {
        cumulativeBalanceCredits:
          row.cumulativeBalanceCredits - row.payoutCredits,
        kind: 'before_payout',
        spinNumber: row.spinNumber,
      },
      {
        cumulativeBalanceCredits: row.cumulativeBalanceCredits,
        kind: 'payout',
        spinNumber: row.spinNumber,
      },
    );
  }
  const last = points.at(-1);
  if (
    end !== undefined &&
    last !== undefined &&
    end.spinNumber > last.spinNumber
  ) {
    points.push({
      cumulativeBalanceCredits: end.balanceCredits,
      kind: 'end',
      spinNumber: end.spinNumber,
    });
  }
  return points;
}

/** Minimum and maximum without spreading large arrays into arguments. */
export function approximateWinExtremes(values: readonly number[]): {
  readonly maximum: number;
  readonly minimum: number;
} {
  let minimum = Number.POSITIVE_INFINITY;
  let maximum = Number.NEGATIVE_INFINITY;
  for (const value of values) {
    if (value < minimum) minimum = value;
    if (value > maximum) maximum = value;
  }
  return values.length === 0
    ? { maximum: 0, minimum: 0 }
    : { maximum, minimum };
}

/**
 * "Round" axis ticks (step 1, 2 or 5 × 10ⁿ) whose first and last values
 * enclose `[minimum, maximum]`. The chart widens its domain to the outer
 * ticks, so every tick is drawable and labels never collide with separate
 * min/max labels (TASK-0761). A degenerate range is widened symmetrically.
 */
export function approximateWinAxisTicks(
  minimum: number,
  maximum: number,
  targetCount = 5,
  options: { readonly integerStep?: boolean } = {},
): readonly number[] {
  if (!Number.isFinite(minimum) || !Number.isFinite(maximum)) return [];
  let low = Math.min(minimum, maximum);
  let high = Math.max(minimum, maximum);
  if (low === high) {
    const padding = Math.abs(low) || 1;
    low -= padding;
    high += padding;
  }
  const rawStep = (high - low) / Math.max(1, targetCount);
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const normalized = rawStep / magnitude;
  const factor =
    normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  // Spin counts are whole numbers, so their axis never uses a fractional step.
  const step = options.integerStep
    ? Math.max(1, factor * magnitude)
    : factor * magnitude;
  const decimals = Math.min(20, Math.max(0, -Math.floor(Math.log10(step))));
  const first = Math.floor(low / step);
  const last = Math.ceil(high / step);
  if (
    !Number.isSafeInteger(first) ||
    !Number.isSafeInteger(last) ||
    last - first > 1000
  ) {
    return [low, high];
  }
  const ticks: number[] = [];
  for (let index = first; index <= last; index += 1) {
    // Rounding through toFixed removes binary noise such as 0.30000000000000004.
    ticks.push(Number((index * step).toFixed(decimals)) + 0);
  }
  return ticks;
}

export const APPROXIMATE_WIN_PIN_LIMIT = 8;

/** Stable identity of a chart point: a payout and its preceding drop share a spin. */
export function approximateWinPointKey(
  point: ApproximateWinChartPoint,
): string {
  return `${point.kind}:${point.spinNumber}`;
}

/**
 * Pin or unpin one point. A new pin beyond `limit` is refused with
 * `limitReached` instead of silently dropping an older pin.
 */
export function toggleApproximateWinPinnedPoint(
  pins: readonly ApproximateWinChartPoint[],
  point: ApproximateWinChartPoint,
  limit = APPROXIMATE_WIN_PIN_LIMIT,
): {
  readonly limitReached: boolean;
  readonly pins: readonly ApproximateWinChartPoint[];
} {
  const key = approximateWinPointKey(point);
  if (pins.some((pin) => approximateWinPointKey(pin) === key)) {
    return {
      limitReached: false,
      pins: pins.filter((pin) => approximateWinPointKey(pin) !== key),
    };
  }
  if (pins.length >= limit) {
    return { limitReached: true, pins };
  }
  return {
    limitReached: false,
    pins: [...pins, point].sort(
      (left, right) =>
        left.spinNumber - right.spinNumber ||
        approximateWinPointKey(left).localeCompare(
          approximateWinPointKey(right),
        ),
    ),
  };
}

/**
 * Keyboard navigation over the labelled points: ArrowLeft/ArrowRight move one
 * point and stop at the ends; the first press starts at the matching end.
 * `before_payout` points are never targets (they only draw the drop).
 */
export function moveApproximateWinHighlight(
  points: readonly ApproximateWinChartPoint[],
  currentKey: string | null,
  step: -1 | 1,
): ApproximateWinChartPoint | null {
  const targets = points.filter((point) => point.kind !== 'before_payout');
  if (targets.length === 0) return null;
  const index =
    currentKey === null
      ? -1
      : targets.findIndex(
          (point) => approximateWinPointKey(point) === currentKey,
        );
  if (index < 0) {
    return (step > 0 ? targets[0] : targets.at(-1)) ?? null;
  }
  return (
    targets[Math.min(targets.length - 1, Math.max(0, index + step))] ?? null
  );
}

export interface ApproximateWinLabelRequest {
  readonly key: string;
  /** Horizontal position of the point the label describes. */
  readonly x: number;
}

export interface ApproximateWinLabelPlacement {
  readonly key: string;
  /** Row of the label band, 0 = nearest to the plot. */
  readonly row: number;
  /** Centre of the label; differs from `pointX` when the label was shifted. */
  readonly x: number;
  readonly pointX: number;
}

/**
 * Place labels in the band above the plot without overlap. Each label takes
 * the first row that is free at its point; when no row is free there, it is
 * shifted sideways to the nearest free slot in the row needing the smallest
 * shift, and the caller draws a bent leader line. Only when no slot exists
 * at all does a label overlap (row 0 at its point).
 */
export function layoutApproximateWinPinLabels(
  labels: readonly ApproximateWinLabelRequest[],
  options: {
    readonly gap?: number;
    readonly labelWidth: number;
    readonly maxX: number;
    readonly minX: number;
    /** Labels already placed (e.g. pins) that the new labels must avoid. */
    readonly reserved?: readonly ApproximateWinLabelPlacement[];
    readonly rows: number;
  },
): readonly ApproximateWinLabelPlacement[] {
  const gap = options.gap ?? 4;
  const half = options.labelWidth / 2;
  const lowest = options.minX + half;
  const highest = options.maxX - half;
  const occupied: { left: number; right: number }[][] = Array.from(
    { length: options.rows },
    () => [],
  );
  for (const placement of options.reserved ?? []) {
    occupied[placement.row]?.push({
      left: placement.x - half,
      right: placement.x + half,
    });
  }
  // Side candidates are computed from the neighbouring slot, so the
  // comparison needs a tolerance or float noise rejects an exact fit.
  const tolerance = 1e-6;
  const isFree = (row: number, centre: number) =>
    centre >= lowest - tolerance &&
    centre <= highest + tolerance &&
    occupied[row].every(
      (slot) =>
        centre + half + gap <= slot.left + tolerance ||
        centre - half - gap >= slot.right - tolerance,
    );
  const ordered = [...labels].sort(
    (left, right) => left.x - right.x || left.key.localeCompare(right.key),
  );
  const placements: ApproximateWinLabelPlacement[] = [];
  for (const label of ordered) {
    const desired = Math.min(highest, Math.max(lowest, label.x));
    let best: { row: number; x: number } | null = null;
    for (let row = 0; row < options.rows; row += 1) {
      if (isFree(row, desired)) {
        best = { row, x: desired };
        break;
      }
    }
    if (best === null) {
      for (let row = 0; row < options.rows; row += 1) {
        const candidates = occupied[row].flatMap((slot) => [
          slot.left - gap - half,
          slot.right + gap + half,
        ]);
        for (const candidate of candidates) {
          if (!isFree(row, candidate)) continue;
          if (
            best === null ||
            Math.abs(candidate - desired) < Math.abs(best.x - desired)
          ) {
            best = { row, x: candidate };
          }
        }
      }
    }
    const placed = best ?? { row: 0, x: desired };
    occupied[placed.row].push({
      left: placed.x - half,
      right: placed.x + half,
    });
    placements.push({
      key: label.key,
      pointX: label.x,
      row: placed.row,
      x: placed.x,
    });
  }
  return placements;
}

/** Filters only the client-rendered payout table; the API result stays intact. */
export function filterApproximateWinRows(
  rows: ApproximateWinResponse['rows'],
  minimumPayoutCredits: number,
): ApproximateWinResponse['rows'] {
  return rows.filter((row) => row.payoutCredits >= minimumPayoutCredits);
}

export function formatApproximateWinCredits(value: number): string {
  return value.toLocaleString('pl-PL');
}
