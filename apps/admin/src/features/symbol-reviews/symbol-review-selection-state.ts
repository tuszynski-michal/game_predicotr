import type {
  SymbolCellReviewFilterState,
  SymbolCellReviewListItemResponse,
} from '@game-predictor/admin-api-client';

export const MAX_EXPLICIT_SYMBOL_REVIEW_SELECTION = 10_000;

export interface SymbolReviewExplicitTarget {
  readonly cellReviewId: string;
  readonly expectedCropChecksumSha256: string;
  readonly expectedCropSampleId: string;
  readonly expectedGeometryRevision: number;
  readonly expectedRevision: number;
}

export interface SymbolReviewFilterSelectionSnapshot {
  readonly catalogRevision: number;
  readonly gameId: string;
  readonly matchedCount: number;
  readonly maxConfidence: number | null;
  readonly minConfidence: number | null;
  readonly state: SymbolCellReviewFilterState;
  readonly symbolId: string | 'unknown';
}

export interface SymbolReviewExplicitSelection {
  readonly kind: 'explicit';
  readonly targetsById: Readonly<Record<string, SymbolReviewExplicitTarget>>;
}

export interface SymbolReviewAllMatchingFilterSelection {
  readonly excludedIds: ReadonlySet<string>;
  readonly kind: 'all_matching_filter';
  readonly snapshot: SymbolReviewFilterSelectionSnapshot;
}

export type SymbolReviewSelection =
  SymbolReviewAllMatchingFilterSelection | SymbolReviewExplicitSelection;

export interface SymbolReviewSelectionChange {
  readonly rejectedCount: number;
  readonly selection: SymbolReviewSelection;
}

export function createEmptySymbolReviewSelection(): SymbolReviewExplicitSelection {
  return { kind: 'explicit', targetsById: {} };
}

export function createAllMatchingFilterSymbolReviewSelection(
  snapshot: SymbolReviewFilterSelectionSnapshot,
): SymbolReviewAllMatchingFilterSelection {
  return { excludedIds: new Set(), kind: 'all_matching_filter', snapshot };
}

export function selectedSymbolReviewCount(
  selection: SymbolReviewSelection,
): number {
  if (selection.kind === 'explicit') {
    return Object.keys(selection.targetsById).length;
  }
  return Math.max(
    0,
    selection.snapshot.matchedCount - selection.excludedIds.size,
  );
}

export function isSymbolReviewItemSelected(
  selection: SymbolReviewSelection,
  item: SymbolCellReviewListItemResponse,
): boolean {
  if (selection.kind === 'explicit') {
    return selection.targetsById[item.id] !== undefined;
  }
  return !selection.excludedIds.has(item.id);
}

export function toggleSymbolReviewItem(
  selection: SymbolReviewSelection,
  item: SymbolCellReviewListItemResponse,
): SymbolReviewSelectionChange {
  if (selection.kind === 'all_matching_filter') {
    const excludedIds = new Set(selection.excludedIds);
    if (excludedIds.delete(item.id)) {
      return { rejectedCount: 0, selection: { ...selection, excludedIds } };
    }
    if (excludedIds.size >= MAX_EXPLICIT_SYMBOL_REVIEW_SELECTION) {
      return { rejectedCount: 1, selection };
    }
    excludedIds.add(item.id);
    return { rejectedCount: 0, selection: { ...selection, excludedIds } };
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
  if (selection.kind === 'all_matching_filter') {
    return { rejectedCount: 0, selection };
  }
  const targetsById = { ...selection.targetsById };
  let targetCount = Object.keys(targetsById).length;
  let rejectedCount = 0;
  for (const item of items) {
    if (targetsById[item.id] !== undefined) continue;
    if (targetCount >= MAX_EXPLICIT_SYMBOL_REVIEW_SELECTION) {
      rejectedCount += 1;
      continue;
    }
    targetsById[item.id] = toExplicitTarget(item);
    targetCount += 1;
  }
  return {
    rejectedCount,
    selection: { kind: 'explicit', targetsById },
  };
}

export function symbolReviewSelectionCurrentItemIds(
  selection: SymbolReviewSelection,
  items: readonly SymbolCellReviewListItemResponse[],
): readonly string[] {
  return items
    .filter((item) => isSymbolReviewItemSelected(selection, item))
    .map((item) => item.id);
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
