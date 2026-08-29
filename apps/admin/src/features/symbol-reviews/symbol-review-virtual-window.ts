import type { SymbolCellReviewListItemResponse } from '@game-predictor/admin-api-client';

export const MAX_SYMBOL_REVIEW_ATLAS_CELLS = 100;
export const SYMBOL_REVIEW_CARD_SIZE = 100;
export const SYMBOL_REVIEW_GRID_GAP = 8;
export const SYMBOL_REVIEW_ROW_HEIGHT =
  SYMBOL_REVIEW_CARD_SIZE + SYMBOL_REVIEW_GRID_GAP;
export const SYMBOL_REVIEW_VIRTUAL_OVERSCAN_ROWS = 2;

export interface SymbolReviewVirtualWindow {
  readonly endIndexExclusive: number;
  readonly startIndex: number;
}

/**
 * The DOM window is derived from virtual rows, never from the page size. Keeping
 * this pure makes the 500-item page contract testable without mounting React.
 */
export function symbolReviewVirtualWindow(
  itemCount: number,
  columnCount: number,
  firstVisibleRow: number,
  visibleRowCount: number,
  overscanRows = SYMBOL_REVIEW_VIRTUAL_OVERSCAN_ROWS,
): SymbolReviewVirtualWindow {
  if (itemCount <= 0 || columnCount <= 0 || visibleRowCount <= 0) {
    return { endIndexExclusive: 0, startIndex: 0 };
  }
  const startRow = Math.max(0, firstVisibleRow - overscanRows);
  const endRowExclusive = Math.ceil(itemCount / columnCount);
  const renderedRows = Math.min(
    endRowExclusive - startRow,
    visibleRowCount + overscanRows * 2,
  );
  return {
    endIndexExclusive: Math.min(
      itemCount,
      (startRow + renderedRows) * columnCount,
    ),
    startIndex: startRow * columnCount,
  };
}

export function boundedVirtualPreviewItems(
  items: readonly SymbolCellReviewListItemResponse[],
): readonly SymbolCellReviewListItemResponse[] {
  return items.slice(0, MAX_SYMBOL_REVIEW_ATLAS_CELLS);
}

export function shouldApplyVirtualPreviewResult(
  requestId: number,
  currentRequestId: number,
): boolean {
  return requestId === currentRequestId;
}
