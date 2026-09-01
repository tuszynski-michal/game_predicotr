import type {
  SymbolCellReviewFilterState,
  SymbolCellReviewPageResponse,
} from '@game-predictor/admin-api-client';

export const DEFAULT_SYMBOL_REVIEW_PAGE_SIZE = 500;
export const MIN_SYMBOL_REVIEW_PAGE_SIZE = 1;
export const MAX_SYMBOL_REVIEW_PAGE_SIZE = 500;
export const MAX_SYMBOL_REVIEW_CACHED_PAGES = 3;

export type SymbolReviewConfidenceFilter = 'all' | 'high' | 'low' | 'medium';

export interface SymbolReviewPageRange {
  readonly end: number;
  readonly start: number;
}

export interface SymbolReviewFilters {
  readonly confidence: SymbolReviewConfidenceFilter;
  readonly gameId: string | null;
  readonly pageSize: number;
  readonly state: SymbolCellReviewFilterState;
  readonly symbolId: string | 'all' | 'unknown' | null;
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
  readonly pages: readonly SymbolReviewCurrentPage[];
}

export type SymbolReviewWorkspaceAction =
  | { readonly type: 'filters_changed'; readonly filters: SymbolReviewFilters }
  | {
      readonly type: 'page_loaded';
      readonly page: SymbolCellReviewPageResponse;
      readonly position: SymbolReviewPagePosition;
    }
  | {
      readonly type: 'page_prefetched';
      readonly page: SymbolCellReviewPageResponse;
      readonly position: SymbolReviewPagePosition;
    }
  | { readonly type: 'clear_page' };

export function createSymbolReviewWorkspaceState(
  filters: SymbolReviewFilters,
): SymbolReviewWorkspaceState {
  return { currentPage: null, filters, pages: [] };
}

export function symbolReviewConfidenceRange(
  confidence: SymbolReviewConfidenceFilter,
): { readonly maxConfidence?: number; readonly minConfidence?: number } {
  switch (confidence) {
    case 'low':
      return { maxConfidence: 0.499_999 };
    case 'medium':
      return { maxConfidence: 0.799_999, minConfidence: 0.5 };
    case 'high':
      return { minConfidence: 0.8 };
    default:
      return {};
  }
}

export function findCachedSymbolReviewPage(
  state: SymbolReviewWorkspaceState,
  pageNumber: number,
): SymbolReviewCurrentPage | null {
  return (
    state.pages.find((page) => page.position.number === pageNumber) ?? null
  );
}

export function symbolReviewPageRange(
  pageNumber: number,
  itemCount: number,
  pageSize: number,
  totalCount: number,
): SymbolReviewPageRange | null {
  if (
    pageNumber < 1 ||
    itemCount < 1 ||
    pageSize < MIN_SYMBOL_REVIEW_PAGE_SIZE ||
    totalCount < 1
  ) {
    return null;
  }
  const start = (pageNumber - 1) * pageSize + 1;
  if (start > totalCount) return null;
  return {
    end: Math.min(start + itemCount - 1, totalCount),
    start,
  };
}

export function symbolReviewWorkspaceReducer(
  state: SymbolReviewWorkspaceState,
  action: SymbolReviewWorkspaceAction,
): SymbolReviewWorkspaceState {
  switch (action.type) {
    case 'filters_changed':
      return createSymbolReviewWorkspaceState(action.filters);
    case 'clear_page':
      return { ...state, currentPage: null, pages: [] };
    case 'page_loaded':
      return {
        ...state,
        currentPage: { page: action.page, position: action.position },
        pages: retainNearbyPages(
          state.pages,
          { page: action.page, position: action.position },
          action.position.number,
        ),
      };
    case 'page_prefetched':
      return {
        ...state,
        pages: retainNearbyPages(
          state.pages,
          { page: action.page, position: action.position },
          state.currentPage?.position.number ?? action.position.number,
        ),
      };
  }
}

function retainNearbyPages(
  existing: readonly SymbolReviewCurrentPage[],
  incoming: SymbolReviewCurrentPage,
  currentPageNumber: number,
): readonly SymbolReviewCurrentPage[] {
  const byPageNumber = new Map<number, SymbolReviewCurrentPage>(
    existing.map((page) => [page.position.number, page]),
  );
  byPageNumber.set(incoming.position.number, incoming);
  return [...byPageNumber.values()]
    .sort(
      (left, right) =>
        Math.abs(left.position.number - currentPageNumber) -
          Math.abs(right.position.number - currentPageNumber) ||
        left.position.number - right.position.number,
    )
    .slice(0, MAX_SYMBOL_REVIEW_CACHED_PAGES)
    .sort((left, right) => left.position.number - right.position.number);
}
