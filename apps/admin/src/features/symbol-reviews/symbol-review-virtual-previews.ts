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

export type SymbolReviewPreviewMode = 'current' | 'structured_v0_10';

export interface SymbolReviewPreviewAvailability {
  readonly unavailableCellReviewIds: ReadonlySet<string>;
  readonly rendererVersion: string | null;
  readonly rendererFingerprintSha256: string | null;
}

export type SymbolReviewVirtualPreviewResult =
  | {
      readonly ok: true;
      readonly tilesByCellReviewId: Readonly<
        Record<string, SymbolReviewVirtualPreviewTile>
      >;
      readonly availability: SymbolReviewPreviewAvailability;
    }
  | { readonly ok: false };

/** Loads deterministic page atlases sequentially, prioritizing the visible chunk. */
export async function loadSymbolReviewPreviewAtlases(
  api: SymbolReviewClient,
  gameId: string,
  pageItems: readonly SymbolCellReviewListItemResponse[],
  firstVisibleCellId: string | null,
  previewMode: SymbolReviewPreviewMode,
  onAtlas: (
    tiles: Readonly<Record<string, SymbolReviewVirtualPreviewTile>>,
    availability: SymbolReviewPreviewAvailability,
  ) => void,
): Promise<SymbolReviewVirtualPreviewResult> {
  const chunks = symbolReviewPreviewChunks(pageItems);
  if (chunks.length === 0) {
    return {
      ok: true,
      tilesByCellReviewId: {},
      availability: {
        rendererFingerprintSha256: null,
        rendererVersion: null,
        unavailableCellReviewIds: new Set(),
      },
    };
  }
  const tilesByCellReviewId: Record<string, SymbolReviewVirtualPreviewTile> =
    {};
  const unavailableCellReviewIds = new Set<string>();
  let rendererVersion: string | null = null;
  let rendererFingerprintSha256: string | null = null;
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
        rendererMode: previewMode,
      });
      if (result.data === undefined || result.error !== undefined) {
        return { ok: false };
      }
      rendererVersion = result.data.rendererVersion;
      rendererFingerprintSha256 = result.data.rendererFingerprintSha256;
      for (const cellReviewId of result.data.unavailableCellReviewIds) {
        unavailableCellReviewIds.add(cellReviewId);
      }
      if (typeof result.data.batchKey === 'string') {
        const atlasUrl = api.symbolCellPreviewAtlasUrl(
          gameId,
          result.data.batchKey,
        );
        for (const tile of result.data.tiles) {
          tilesByCellReviewId[tile.cellReviewId] = { atlasUrl, tile };
        }
      }
      onAtlas(
        { ...tilesByCellReviewId },
        {
          rendererFingerprintSha256,
          rendererVersion,
          unavailableCellReviewIds: new Set(unavailableCellReviewIds),
        },
      );
    }
    return {
      ok: true,
      tilesByCellReviewId,
      availability: {
        rendererFingerprintSha256,
        rendererVersion,
        unavailableCellReviewIds,
      },
    };
  } catch {
    return { ok: false };
  }
}
