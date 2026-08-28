import type { BoardSearchResultResponse } from '@game-predictor/admin-api-client';

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
