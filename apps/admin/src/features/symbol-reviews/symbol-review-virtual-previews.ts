import type {
  SymbolCellReviewListItemResponse,
  VirtualCellPreviewTileResponse,
} from '@game-predictor/admin-api-client';

import type { SymbolReviewClient } from './symbol-review-actions.ts';
import { boundedVirtualPreviewItems } from './symbol-review-virtual-window.ts';

export interface SymbolReviewVirtualPreviewTile {
  readonly atlasUrl: string;
  readonly tile: VirtualCellPreviewTileResponse;
}

export type SymbolReviewVirtualPreviewResult =
  | {
      readonly ok: true;
      readonly tilesByCellReviewId: Readonly<
        Record<string, SymbolReviewVirtualPreviewTile>
      >;
    }
  | { readonly ok: false };

/** Loads a single atlas only for currently rendered virtual cells. */
export async function loadSymbolReviewVirtualPreviews(
  api: SymbolReviewClient,
  gameId: string,
  visibleItems: readonly SymbolCellReviewListItemResponse[],
): Promise<SymbolReviewVirtualPreviewResult> {
  const targets = boundedVirtualPreviewItems(visibleItems)
    .filter(
      (item) =>
        item.assetMode === 'virtual_source' &&
        item.renderSpecChecksumSha256 !== null,
    )
    .map((item) => ({
      cellReviewId: item.id,
      expectedRenderSpecChecksumSha256: item.renderSpecChecksumSha256!,
      expectedRevision: item.revision,
    }));
  if (targets.length === 0) {
    return { ok: true, tilesByCellReviewId: {} };
  }
  try {
    const result = await api.createVirtualCellPreviewBatch(gameId, {
      cells: targets,
      previewSize: 100,
    });
    if (result.data === undefined || result.error !== undefined) {
      return { ok: false };
    }
    const atlasUrl = api.virtualCellPreviewAtlasUrl(
      gameId,
      result.data.batchKey,
    );
    return {
      ok: true,
      tilesByCellReviewId: Object.fromEntries(
        result.data.tiles.map((tile) => [
          tile.cellReviewId,
          { atlasUrl, tile },
        ]),
      ),
    };
  } catch {
    return { ok: false };
  }
}
