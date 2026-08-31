import type {
  SymbolCellReviewListItemResponse,
  VirtualCellPreviewTileResponse,
} from '@game-predictor/admin-api-client';

import type { SymbolReviewClient } from './symbol-review-actions.ts';
import {
  symbolReviewPreviewChunkOrder,
  symbolReviewPreviewChunks,
} from './symbol-review-virtual-window.ts';

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

/** Loads deterministic page atlases sequentially, prioritizing the visible chunk. */
export async function loadSymbolReviewPreviewAtlases(
  api: SymbolReviewClient,
  gameId: string,
  pageItems: readonly SymbolCellReviewListItemResponse[],
  firstVisibleCellId: string | null,
  onAtlas: (
    tiles: Readonly<Record<string, SymbolReviewVirtualPreviewTile>>,
  ) => void,
): Promise<SymbolReviewVirtualPreviewResult> {
  const chunks = symbolReviewPreviewChunks(pageItems);
  if (chunks.length === 0) {
    return { ok: true, tilesByCellReviewId: {} };
  }
  const tilesByCellReviewId: Record<string, SymbolReviewVirtualPreviewTile> =
    {};
  try {
    for (const chunkIndex of symbolReviewPreviewChunkOrder(
      chunks,
      firstVisibleCellId,
    )) {
      const chunk = chunks[chunkIndex]!;
      const result = await api.createSymbolCellPreviewBatch(gameId, {
        cells: chunk.map((item) => ({
          cellReviewId: item.id,
          expectedCropChecksumSha256: item.cropChecksumSha256,
          expectedRevision: item.revision,
          ...(item.renderSpecChecksumSha256 === null
            ? {}
            : {
                expectedRenderSpecChecksumSha256: item.renderSpecChecksumSha256,
              }),
        })),
        previewSize: 100,
      });
      if (result.data === undefined || result.error !== undefined) {
        return { ok: false };
      }
      const atlasUrl = api.symbolCellPreviewAtlasUrl(
        gameId,
        result.data.batchKey,
      );
      for (const tile of result.data.tiles) {
        tilesByCellReviewId[tile.cellReviewId] = { atlasUrl, tile };
      }
      onAtlas({ ...tilesByCellReviewId });
    }
    return {
      ok: true,
      tilesByCellReviewId,
    };
  } catch {
    return { ok: false };
  }
}
