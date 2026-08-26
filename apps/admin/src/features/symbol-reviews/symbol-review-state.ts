import type {
  SymbolCellReviewFilterState,
  SymbolCellReviewPageResponse,
} from '@game-predictor/admin-api-client';

export const SYMBOL_REVIEW_PAGE_SIZE = 60;

export interface SymbolReviewFilters {
  readonly gameId: string | null;
  readonly state: SymbolCellReviewFilterState;
  readonly symbolId: string | 'unknown' | null;
}

export interface SymbolReviewPageBuffer {
  readonly current: SymbolCellReviewPageResponse | null;
  readonly next: SymbolCellReviewPageResponse | null;
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
        pages: { current: action.page, next: null, previous: null },
      };
    case 'next_page_prefetched':
      return state.pages.current === null
        ? state
        : { ...state, pages: { ...state.pages, next: action.page } };
    case 'next_page_loaded':
      return state.pages.current === null
        ? {
            ...state,
            pages: { current: action.page, next: null, previous: null },
          }
        : {
            ...state,
            pages: {
              current: action.page,
              next: null,
              previous: state.pages.current,
            },
          };
    case 'previous_page_loaded':
      return state.pages.current === null
        ? {
            ...state,
            pages: { current: action.page, next: null, previous: null },
          }
        : {
            ...state,
            pages: {
              current: action.page,
              next: state.pages.current,
              previous: null,
            },
          };
  }
}

export function symbolReviewBufferedPageCount(
  state: SymbolReviewWorkspaceState,
): number {
  return [state.pages.previous, state.pages.current, state.pages.next].filter(
    (page) => page !== null,
  ).length;
}

function emptySymbolReviewPageBuffer(): SymbolReviewPageBuffer {
  return { current: null, next: null, previous: null };
}
