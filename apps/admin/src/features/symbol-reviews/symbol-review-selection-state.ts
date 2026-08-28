import type { SymbolCellReviewListItemResponse } from '@game-predictor/admin-api-client';

export const MAX_EXPLICIT_SYMBOL_REVIEW_SELECTION = 500;

export interface SymbolReviewExplicitTarget {
  readonly cellReviewId: string;
  readonly expectedCropChecksumSha256: string;
  readonly expectedCropSampleId: string;
  readonly expectedGeometryRevision: number;
  readonly expectedRevision: number;
}

export interface SymbolReviewSelection {
  readonly kind: 'explicit';
  readonly targetsById: Readonly<Record<string, SymbolReviewExplicitTarget>>;
}

export interface SymbolReviewSelectionChange {
  readonly rejectedCount: number;
  readonly selection: SymbolReviewSelection;
}

export function createEmptySymbolReviewSelection(): SymbolReviewSelection {
  return { kind: 'explicit', targetsById: {} };
}

export function selectedSymbolReviewCount(
  selection: SymbolReviewSelection,
): number {
  return Object.keys(selection.targetsById).length;
}

export function isSymbolReviewItemSelected(
  selection: SymbolReviewSelection,
  item: SymbolCellReviewListItemResponse,
): boolean {
  return selection.targetsById[item.id] !== undefined;
}

export function toggleSymbolReviewItem(
  selection: SymbolReviewSelection,
  item: SymbolCellReviewListItemResponse,
): SymbolReviewSelectionChange {
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
