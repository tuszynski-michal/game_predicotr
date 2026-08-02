import type {
  AdminApiClient,
  SymbolCreate,
  SymbolResponse,
  SymbolUpdate,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';
import type { ValidatedSymbolDraft } from './symbol-catalog-state.ts';

export type SymbolsClient = Pick<
  AdminApiClient,
  | 'archiveSymbol'
  | 'createSymbol'
  | 'getLatestSymbolBootstrap'
  | 'listGames'
  | 'listSymbols'
  | 'resolveSymbolBootstrap'
  | 'listSymbolImageCandidates'
  | 'selectSymbolImageCandidate'
  | 'startSymbolBootstrap'
  | 'symbolImageAssetUrl'
  | 'symbolImageCandidateAssetUrl'
  | 'updateSymbol'
>;

export type SaveSymbolIntent =
  | { readonly mode: 'create' }
  | { readonly mode: 'edit'; readonly symbolId: string };

export type SaveSymbolResult =
  | { readonly ok: true; readonly symbol: SymbolResponse }
  | { readonly error: string; readonly ok: false };

export async function saveSymbol(
  api: SymbolsClient,
  gameId: string,
  intent: SaveSymbolIntent,
  draft: ValidatedSymbolDraft,
): Promise<SaveSymbolResult> {
  try {
    const result =
      intent.mode === 'create'
        ? await api.createSymbol(gameId, {
            code: draft.code,
            displayOrder: draft.displayOrder,
            imagePath: draft.imagePath,
            isWildcard: draft.isWildcard,
            mobileCode: draft.mobileCode,
            name: draft.name,
            nameEn: draft.nameEn,
            namePl: draft.namePl,
            status: draft.status,
          } satisfies SymbolCreate)
        : await api.updateSymbol(gameId, intent.symbolId, {
            displayOrder: draft.displayOrder,
            imagePath: draft.imagePath,
            isWildcard: draft.isWildcard,
            name: draft.name,
            nameEn: draft.nameEn,
            namePl: draft.namePl,
            status: draft.status,
          } satisfies SymbolUpdate);

    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(result.error, 'Nie udało się zapisać symbolu.'),
        ok: false,
      };
    }
    return { ok: true, symbol: result.data };
  } catch {
    return {
      error:
        'Połączenie z lokalnym Admin API zostało przerwane. Spróbuj ponownie.',
      ok: false,
    };
  }
}

export type ArchiveSymbolResult =
  { readonly ok: true } | { readonly error: string; readonly ok: false };

export async function archiveSymbol(
  api: SymbolsClient,
  gameId: string,
  symbolId: string,
): Promise<ArchiveSymbolResult> {
  try {
    const result = await api.archiveSymbol(gameId, symbolId);
    if (result.error !== undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się zarchiwizować symbolu.',
        ),
        ok: false,
      };
    }
    return { ok: true };
  } catch {
    return {
      error:
        'Połączenie z lokalnym Admin API zostało przerwane. Archiwizacja nie została potwierdzona.',
      ok: false,
    };
  }
}
