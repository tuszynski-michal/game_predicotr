import type {
  SymbolCellReviewFilterState,
  SymbolCellReviewPageResponse,
} from '@game-predictor/admin-api-client';

export const SYMBOL_REVIEW_PAGE_SIZE = 60;
export const SYMBOL_REVIEW_READ_AHEAD_PAGE_COUNT = 4;

export interface SymbolReviewFilters {
  readonly gameId: string | null;
  readonly state: SymbolCellReviewFilterState;
  readonly symbolId: string | 'unknown' | null;
}

export interface SymbolReviewPageBuffer {
  readonly current: SymbolCellReviewPageResponse | null;
  readonly next: readonly SymbolCellReviewPageResponse[];
  readonly previous: SymbolCellReviewPageResponse | null;
}

export interface SymbolReviewWorkspaceState {
  readonly filters: SymbolReviewFilters;
  readonly pages: SymbolReviewPageBuffer;
}

export type SymbolReviewWorkspaceAction =
  | { readonly type: 'filters_changed'; readonly filters: SymbolReviewFilters }
  | {
      readonly type: 'initial_page_loaded';
      readonly page: SymbolCellReviewPageResponse;
    }
  | {
      readonly type: 'next_page_loaded';
      readonly page: SymbolCellReviewPageResponse;
    }
  | {
      readonly type: 'previous_page_loaded';
      readonly page: SymbolCellReviewPageResponse;
    }
  | {
      readonly type: 'next_page_prefetched';
      readonly page: SymbolCellReviewPageResponse;
    }
  | { readonly type: 'clear_pages' };

export function createSymbolReviewWorkspaceState(
  filters: SymbolReviewFilters,
): SymbolReviewWorkspaceState {
  return { filters, pages: emptySymbolReviewPageBuffer() };
}

export function symbolReviewWorkspaceReducer(
  state: SymbolReviewWorkspaceState,
  action: SymbolReviewWorkspaceAction,
): SymbolReviewWorkspaceState {
  switch (action.type) {
    case 'filters_changed':
      return createSymbolReviewWorkspaceState(action.filters);
    case 'clear_pages':
      return { ...state, pages: emptySymbolReviewPageBuffer() };
    case 'initial_page_loaded':
      return {
        ...state,
        pages: { current: action.page, next: [], previous: null },
      };
    case 'next_page_prefetched':
      if (
        state.pages.current === null ||
        state.pages.next.length >= SYMBOL_REVIEW_READ_AHEAD_PAGE_COUNT ||
        state.pages.next.some((page) => sameSymbolReviewPage(page, action.page))
      ) {
        return state;
      }
      return {
        ...state,
        pages: {
          ...state.pages,
          next: [...state.pages.next, action.page],
        },
      };
    case 'next_page_loaded':
      return state.pages.current === null
        ? {
            ...state,
            pages: { current: action.page, next: [], previous: null },
          }
        : {
            ...state,
            pages: {
              current: action.page,
              next: state.pages.next.filter(
                (page) => !sameSymbolReviewPage(page, action.page),
              ),
              previous: state.pages.current,
            },
          };
    case 'previous_page_loaded':
      return state.pages.current === null
        ? {
            ...state,
            pages: { current: action.page, next: [], previous: null },
          }
        : {
            ...state,
            pages: {
              current: action.page,
              next: [state.pages.current, ...state.pages.next].slice(
                0,
                SYMBOL_REVIEW_READ_AHEAD_PAGE_COUNT,
              ),
              previous: null,
            },
          };
  }
}

export function symbolReviewBufferedPageCount(
  state: SymbolReviewWorkspaceState,
): number {
  return [
    state.pages.previous,
    state.pages.current,
    state.pages.next[0] ?? null,
  ].filter((page) => page !== null).length;
}

export function symbolReviewBufferedPages(
  state: SymbolReviewWorkspaceState,
): readonly SymbolCellReviewPageResponse[] {
  return [
    state.pages.previous,
    state.pages.current,
    state.pages.next[0] ?? null,
  ].filter((page): page is SymbolCellReviewPageResponse => page !== null);
}

export function symbolReviewBufferedItemCount(
  state: SymbolReviewWorkspaceState,
): number {
  return new Set(
    symbolReviewCachedPages(state).flatMap((page) =>
      page.items.map((item) => item.id),
    ),
  ).size;
}

function emptySymbolReviewPageBuffer(): SymbolReviewPageBuffer {
  return { current: null, next: [], previous: null };
}

export function symbolReviewCachedPages(
  state: SymbolReviewWorkspaceState,
): readonly SymbolCellReviewPageResponse[] {
  return [
    state.pages.previous,
    state.pages.current,
    ...state.pages.next,
  ].filter((page): page is SymbolCellReviewPageResponse => page !== null);
}

function sameSymbolReviewPage(
  left: SymbolCellReviewPageResponse,
  right: SymbolCellReviewPageResponse,
): boolean {
  return (
    left.items[0]?.id === right.items[0]?.id &&
    left.items.length === right.items.length
  );
}
