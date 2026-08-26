import type {
  SymbolCellReviewFilterState,
  SymbolCellReviewListItemResponse,
  SymbolCellReviewPageResponse,
} from '@game-predictor/admin-api-client';

import type { SymbolReviewFilters } from './symbol-review-state.ts';

export const MAX_EXPLICIT_SYMBOL_REVIEW_SELECTION = 10_000;

export interface SymbolReviewExplicitTarget {
  readonly cellReviewId: string;
  readonly expectedCropChecksumSha256: string;
  readonly expectedCropSampleId: string;
  readonly expectedGeometryRevision: number;
  readonly expectedRevision: number;
}

export interface SymbolReviewExplicitSelection {
  readonly kind: 'explicit';
  readonly targetsById: Readonly<Record<string, SymbolReviewExplicitTarget>>;
}

export interface SymbolReviewFilterSelection {
  readonly catalogRevision: number;
  readonly excludedCellReviewIds: readonly string[];
  readonly kind: 'filter';
  readonly state: SymbolCellReviewFilterState;
  readonly symbolId: string | 'unknown';
}

export type SymbolReviewSelection =
  SymbolReviewExplicitSelection | SymbolReviewFilterSelection;

export interface SymbolReviewSelectionChange {
  readonly rejectedCount: number;
  readonly selection: SymbolReviewSelection;
}

export function createEmptySymbolReviewSelection(): SymbolReviewExplicitSelection {
  return { kind: 'explicit', targetsById: {} };
}

export function createSymbolReviewFilterSelection(
  filters: SymbolReviewFilters,
  page: SymbolCellReviewPageResponse,
): SymbolReviewFilterSelection | null {
  if (filters.symbolId === null) return null;
  return {
    catalogRevision: page.catalogRevision,
    excludedCellReviewIds: [],
    kind: 'filter',
    state: filters.state,
    symbolId: filters.symbolId,
  };
}

export function selectedSymbolReviewCount(
  selection: SymbolReviewSelection,
  counts: SymbolCellReviewPageResponse['counts'],
): number {
  if (selection.kind === 'explicit') {
    return Object.keys(selection.targetsById).length;
  }
  const total =
    selection.state === 'approved'
      ? counts.approvedCount
      : selection.state === 'pending'
        ? counts.pendingCount
        : counts.allCount;
  return Math.max(0, total - selection.excludedCellReviewIds.length);
}

export function isSymbolReviewItemSelected(
  selection: SymbolReviewSelection,
  item: SymbolCellReviewListItemResponse,
): boolean {
  return selection.kind === 'explicit'
    ? selection.targetsById[item.id] !== undefined
    : !selection.excludedCellReviewIds.includes(item.id);
}

export function toggleSymbolReviewItem(
  selection: SymbolReviewSelection,
  item: SymbolCellReviewListItemResponse,
): SymbolReviewSelectionChange {
  if (selection.kind === 'filter') {
    const excluded = new Set(selection.excludedCellReviewIds);
    if (excluded.has(item.id)) {
      excluded.delete(item.id);
    } else if (excluded.size < MAX_EXPLICIT_SYMBOL_REVIEW_SELECTION) {
      excluded.add(item.id);
    } else {
      return { rejectedCount: 1, selection };
    }
    return {
      rejectedCount: 0,
      selection: {
        ...selection,
        excludedCellReviewIds: [...excluded].sort(),
      },
    };
  }

  const targetsById = { ...selection.targetsById };
  if (targetsById[item.id] !== undefined) {
    delete targetsById[item.id];
    return { rejectedCount: 0, selection: { kind: 'explicit', targetsById } };
  }
  if (Object.keys(targetsById).length >= MAX_EXPLICIT_SYMBOL_REVIEW_SELECTION) {
    return { rejectedCount: 1, selection };
  }
  targetsById[item.id] = toExplicitTarget(item);
  return { rejectedCount: 0, selection: { kind: 'explicit', targetsById } };
}

export function selectVisibleSymbolReviewItems(
  selection: SymbolReviewSelection,
  items: readonly SymbolCellReviewListItemResponse[],
): SymbolReviewSelectionChange {
  if (selection.kind === 'filter') {
    const visibleIds = new Set(items.map((item) => item.id));
    return {
      rejectedCount: 0,
      selection: {
        ...selection,
        excludedCellReviewIds: selection.excludedCellReviewIds.filter(
          (id) => !visibleIds.has(id),
        ),
      },
    };
  }

  const targetsById = { ...selection.targetsById };
  let rejectedCount = 0;
  for (const item of items) {
    if (targetsById[item.id] !== undefined) continue;
    if (
      Object.keys(targetsById).length >= MAX_EXPLICIT_SYMBOL_REVIEW_SELECTION
    ) {
      rejectedCount += 1;
      continue;
    }
    targetsById[item.id] = toExplicitTarget(item);
  }
  return {
    rejectedCount,
    selection: { kind: 'explicit', targetsById },
  };
}

function toExplicitTarget(
  item: SymbolCellReviewListItemResponse,
): SymbolReviewExplicitTarget {
  return {
    cellReviewId: item.id,
    expectedCropChecksumSha256: item.cropChecksumSha256,
    expectedCropSampleId: item.cropSampleId,
    expectedGeometryRevision: item.geometryRevision,
    expectedRevision: item.revision,
  };
}
