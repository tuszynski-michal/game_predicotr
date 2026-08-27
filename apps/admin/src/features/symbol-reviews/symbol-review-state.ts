import type {
  SymbolCellReviewFilterState,
  SymbolCellReviewPageResponse,
} from '@game-predictor/admin-api-client';

export const SYMBOL_REVIEW_PAGE_SIZE = 500;

export interface SymbolReviewFilters {
  readonly gameId: string | null;
  readonly state: SymbolCellReviewFilterState;
  readonly symbolId: string | 'unknown' | null;
}

export interface SymbolReviewPagePosition {
  readonly afterCursor?: string;
  readonly beforeCursor?: string;
  readonly number: number;
}

export interface SymbolReviewCurrentPage {
  readonly page: SymbolCellReviewPageResponse;
  readonly position: SymbolReviewPagePosition;
}

export interface SymbolReviewWorkspaceState {
  readonly currentPage: SymbolReviewCurrentPage | null;
  readonly filters: SymbolReviewFilters;
}

export type SymbolReviewWorkspaceAction =
  | { readonly type: 'filters_changed'; readonly filters: SymbolReviewFilters }
  | {
      readonly type: 'page_loaded';
      readonly page: SymbolCellReviewPageResponse;
      readonly position: SymbolReviewPagePosition;
    }
  | { readonly type: 'clear_page' };

export function createSymbolReviewWorkspaceState(
  filters: SymbolReviewFilters,
): SymbolReviewWorkspaceState {
  return { currentPage: null, filters };
}

export function symbolReviewWorkspaceReducer(
  state: SymbolReviewWorkspaceState,
  action: SymbolReviewWorkspaceAction,
): SymbolReviewWorkspaceState {
  switch (action.type) {
    case 'filters_changed':
      return createSymbolReviewWorkspaceState(action.filters);
    case 'clear_page':
      return { ...state, currentPage: null };
    case 'page_loaded':
      return {
        ...state,
        currentPage: { page: action.page, position: action.position },
      };
  }
}
