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
