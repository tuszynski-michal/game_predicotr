import type { ImageGridReviewItemResponse } from '@game-predictor/admin-api-client';
import type { GridGeometrySourceDrafts } from './grid-review-state.ts';
import {
  completeManualGridFlags,
  validManualGridFlags,
  type ManualGridFlags,
} from '@game-predictor/manual-image-selection-core/manual-grid-qualification';

export class GridDraftRevisionConflict extends Error {}

export function gridDraftKey(
  items: readonly ImageGridReviewItemResponse[],
): string {
  const item = items[0];
  return `grid-source-draft-v1:${item?.gameId}:${item?.importJobId}:${item?.sourceImageId}`;
}

export function gridDraftRevisionKey(
  items: readonly ImageGridReviewItemResponse[],
): string {
  return JSON.stringify(
    items.map((item) => [
      item.slotId,
      item.sourceChecksumSha256,
      item.sourceWidth,
      item.sourceHeight,
      item.geometryRevision,
      item.resolutionRevision,
    ]),
  );
}

export function serializeGridDraft(
  items: readonly ImageGridReviewItemResponse[],
  drafts: GridGeometrySourceDrafts,
  flags?: ReadonlyMap<string, ManualGridFlags>,
): string {
  return JSON.stringify({
    version: flags ? 2 : 1,
    revision: gridDraftRevisionKey(items),
    drafts: [...drafts],
    ...(flags ? { flags: [...flags] } : {}),
  });
}

export function restoreGridDraft(
  items: readonly ImageGridReviewItemResponse[],
  text: string | null,
): GridGeometrySourceDrafts | null {
  if (!text) return null;
  try {
    const value = JSON.parse(text);
    if (
      (value.version === 1 || value.version === 2) &&
      value.revision !== gridDraftRevisionKey(items)
    ) {
      throw new GridDraftRevisionConflict(
        'Lokalny szkic dotyczy wcześniejszej rewizji. Resetuj szkic do zapisanej geometrii, aby kontynuować.',
      );
    }
    if (
      (value.version !== 1 && value.version !== 2) ||
      value.revision !== gridDraftRevisionKey(items) ||
      !Array.isArray(value.drafts) ||
      value.drafts.length !== items.length
    )
      return null;
    const flags = restoreGridFlags(items, text);
    const result = new Map();
    for (const pair of value.drafts) {
      if (!Array.isArray(pair) || pair.length !== 2) return null;
      const [id, points] = pair;
      const item = items.find((item) => item.slotId === id);
      if (
        !item ||
        result.has(id) ||
        !Array.isArray(points) ||
        points.length > 4
      )
        return null;
      if (
        !points.every(
          (p) =>
            p &&
            Number.isFinite(p.x) &&
            Number.isFinite(p.y) &&
            p.x >= (flags.get(id)?.partial ? -item.sourceWidth : 0) &&
            p.y >= (flags.get(id)?.partial ? -item.sourceHeight : 0) &&
            p.x <= item.sourceWidth * (flags.get(id)?.partial ? 2 : 1) &&
            p.y <= item.sourceHeight * (flags.get(id)?.partial ? 2 : 1),
        )
      )
        return null;
      result.set(
        id,
        points.map((p) => ({ x: p.x, y: p.y })),
      );
    }
    return result;
  } catch (error) {
    if (error instanceof GridDraftRevisionConflict) throw error;
    return null;
  }
}

export function restoreGridFlags(
  items: readonly ImageGridReviewItemResponse[],
  text: string | null,
): ReadonlyMap<string, ManualGridFlags> {
  if (!text) return new Map();
  const value = JSON.parse(text);
  if (value.version !== 2) return new Map();
  if (value.revision !== gridDraftRevisionKey(items))
    throw new GridDraftRevisionConflict('Konflikt rewizji szkicu.');
  if (!Array.isArray(value.flags) || value.flags.length !== items.length)
    throw new Error('Nieprawidłowe oznaczenia szkicu.');
  const result = new Map<string, ManualGridFlags>();
  for (const pair of value.flags) {
    if (
      !Array.isArray(pair) ||
      pair.length !== 2 ||
      !items.some((item) => item.slotId === pair[0]) ||
      result.has(pair[0]) ||
      !validManualGridFlags(pair[1])
    )
      throw new Error('Nieprawidłowe oznaczenia szkicu.');
    result.set(pair[0], { ...completeManualGridFlags, ...pair[1] });
  }
  return result;
}
