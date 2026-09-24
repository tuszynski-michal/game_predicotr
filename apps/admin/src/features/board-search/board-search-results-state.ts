import type { BoardSearchResultResponse } from '@game-predictor/admin-api-client';

/** Existing technical limit enforced by the board-search API (`limit=1..100`). */
export const BOARD_SEARCH_LIMIT_MAX = 100;
export const BOARD_SEARCH_LIMIT_DEFAULT = 5;

export interface BoardSearchResultsState {
  readonly activeIndex: number;
  readonly results: readonly BoardSearchResultResponse[];
}

export function createBoardSearchResultsState(
  results: readonly BoardSearchResultResponse[],
): BoardSearchResultsState {
  return Object.freeze({
    activeIndex: 0,
    results: Object.freeze([...results]),
  });
}

/**
 * Stable identity of a board-search result, independent of ranking position.
 * Matches the historical `resultKey` used to remount the carousel.
 */
export function boardSearchResultIdentity(
  result: BoardSearchResultResponse,
): string {
  return `${result.assetMode}:${result.sequenceNumber}:${result.boardChecksumSha256}`;
}

/**
 * Build a fresh results state that keeps the previously active board selected
 * when it is still present in the new results (e.g. after only the result
 * limit changed). Falls back to the first result otherwise, matching the
 * default behaviour of a brand-new search.
 */
export function reconcileBoardSearchResultsState(
  previous: BoardSearchResultsState,
  results: readonly BoardSearchResultResponse[],
): BoardSearchResultsState {
  const previousActive = previous.results[previous.activeIndex];
  const previousIdentity =
    previousActive === undefined
      ? null
      : boardSearchResultIdentity(previousActive);
  const preservedIndex =
    previousIdentity === null
      ? -1
      : results.findIndex(
          (result) => boardSearchResultIdentity(result) === previousIdentity,
        );
  return Object.freeze({
    activeIndex: preservedIndex >= 0 ? preservedIndex : 0,
    results: Object.freeze([...results]),
  });
}

export type ParsedBoardSearchLimit =
  | { readonly ok: true; readonly value: number }
  | { readonly ok: false; readonly error: string };

/**
 * Validate the "Liczba wyników" input: a positive integer within the
 * existing technical limit, matching the API's `limit` query parameter.
 */
export function parseBoardSearchLimit(text: string): ParsedBoardSearchLimit {
  const trimmed = text.trim();
  if (trimmed === '') {
    return { error: 'Podaj liczbę wyników.', ok: false };
  }
  if (!/^\d+$/.test(trimmed)) {
    return { error: 'Liczba wyników musi być liczbą całkowitą.', ok: false };
  }
  const value = Number.parseInt(trimmed, 10);
  if (value < 1 || value > BOARD_SEARCH_LIMIT_MAX) {
    return {
      error: `Liczba wyników musi być z zakresu 1–${BOARD_SEARCH_LIMIT_MAX}.`,
      ok: false,
    };
  }
  return { ok: true, value };
}

export function activeBoardSearchResult(
  state: BoardSearchResultsState,
): BoardSearchResultResponse | null {
  return state.results[state.activeIndex] ?? null;
}

export function moveBoardSearchResult(
  state: BoardSearchResultsState,
  direction: -1 | 1,
): BoardSearchResultsState {
  if (state.results.length === 0) {
    return state;
  }
  const activeIndex = Math.min(
    state.results.length - 1,
    Math.max(0, state.activeIndex + direction),
  );
  if (activeIndex === state.activeIndex) {
    return state;
  }
  return Object.freeze({ ...state, activeIndex });
}

export function boardSearchNeighbourIndexes(
  state: BoardSearchResultsState,
): readonly number[] {
  return [-1, 1]
    .map((offset) => state.activeIndex + offset)
    .filter((index) => index >= 0 && index < state.results.length);
}
