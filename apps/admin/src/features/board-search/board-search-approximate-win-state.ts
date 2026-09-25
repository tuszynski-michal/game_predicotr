import type { ApproximateWinResponse } from '@game-predictor/admin-api-client';

/**
 * "Zakres wygranej": how many future spins S+1..S+N are evaluated. Default
 * and ceiling are independent of "Liczba wyników" (board-search-results-state.ts).
 * The ceiling matches the API's own `APPROXIMATE_WIN_SPIN_COUNT_MAX` —
 * TASK-0652, `application/board_search_approximate_win.py`.
 */
export const APPROXIMATE_WIN_RANGE_DEFAULT = 1000;
export const APPROXIMATE_WIN_RANGE_MAX = 10_000;

/** Client-side pagination only; never changes the calculated summary. */
export const APPROXIMATE_WIN_ROWS_PAGE_SIZE = 100;

export type ParsedApproximateWinRange =
  | { readonly ok: true; readonly value: number }
  | { readonly ok: false; readonly error: string };

export function parseApproximateWinRange(text: string): ParsedApproximateWinRange {
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
 * Once a key has a `ready`/`error` result, reopening with the *same* key
 * reuses it instead of recalculating — there is no server-side cache
 * (TASK-0651/0652), so this in-memory comparison is the only reuse this
 * feature gets.
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
  if (state.kind !== 'ready' || currentKey === null || state.key !== currentKey) {
    return null;
  }
  return state.result;
}

export interface ApproximateWinRowsPage {
  readonly rows: ApproximateWinResponse['rows'];
  readonly page: number;
  readonly pageCount: number;
  readonly totalRowCount: number;
}

/**
 * Client-side pagination over already-calculated rows. Never touches the
 * range's own summary/completeness/balance — those describe the whole
 * evaluated range regardless of how many rows are currently displayed.
 */
export function pageApproximateWinRows(
  rows: ApproximateWinResponse['rows'],
  page: number,
): ApproximateWinRowsPage {
  const pageCount = Math.max(1, Math.ceil(rows.length / APPROXIMATE_WIN_ROWS_PAGE_SIZE));
  const clampedPage = Math.min(Math.max(1, page), pageCount);
  const start = (clampedPage - 1) * APPROXIMATE_WIN_ROWS_PAGE_SIZE;
  return {
    page: clampedPage,
    pageCount,
    rows: rows.slice(start, start + APPROXIMATE_WIN_ROWS_PAGE_SIZE),
    totalRowCount: rows.length,
  };
}

export function formatApproximateWinCredits(value: number): string {
  return value.toLocaleString('pl-PL');
}
