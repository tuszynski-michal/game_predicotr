import type { ImageGridReviewItemResponse } from '@game-predictor/admin-api-client';
import type { GridGeometrySourceDrafts } from './grid-review-state.ts';

export function gridDraftKey(
  items: readonly ImageGridReviewItemResponse[],
): string {
  const item = items[0];
  return `grid-source-draft-v1:${item?.gameId}:${item?.importJobId}:${item?.sourceImageId}`;
}

function revisionKey(items: readonly ImageGridReviewItemResponse[]): string {
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
): string {
  return JSON.stringify({
    version: 1,
    revision: revisionKey(items),
    drafts: [...drafts],
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
      value.version !== 1 ||
      value.revision !== revisionKey(items) ||
      !Array.isArray(value.drafts) ||
      value.drafts.length !== items.length
    )
      return null;
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
            p.x >= 0 &&
            p.y >= 0 &&
            p.x <= item.sourceWidth &&
            p.y <= item.sourceHeight,
        )
      )
        return null;
      result.set(
        id,
        points.map((p) => ({ x: p.x, y: p.y })),
      );
    }
    return result;
  } catch {
    return null;
  }
}
