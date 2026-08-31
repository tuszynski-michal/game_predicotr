import type {
  GameResponse,
  SymbolCellReviewCountSnapshotResponse,
  SymbolCellReviewFilterState,
  SymbolCellReviewPageResponse,
  SymbolCellReviewProjectionStartResponse,
  SymbolCellReviewProjectionStatusResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';

import type { createConfiguredAdminApiClient } from '@/api/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';

export type SymbolReviewClient = Pick<
  ReturnType<typeof createConfiguredAdminApiClient>,
  | 'listGames'
  | 'listSymbols'
  | 'listSymbolCellReviews'
  | 'getSymbolCellReviewCounts'
  | 'getSymbolCellReviewProjectionStatus'
  | 'startSymbolCellReviewProjectionBackfill'
  | 'symbolCellReviewAssetUrl'
  | 'createVirtualCellPreviewBatch'
  | 'virtualCellPreviewAtlasUrl'
>;

export type SymbolReviewProjectionResult =
  | {
      readonly ok: true;
      readonly status: SymbolCellReviewProjectionStatusResponse;
    }
  | { readonly error: string; readonly ok: false };

export async function loadSymbolReviewProjection(
  api: SymbolReviewClient,
  gameId: string,
): Promise<SymbolReviewProjectionResult> {
  try {
    const result = await api.getSymbolCellReviewProjectionStatus(gameId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać stanu przygotowania weryfikacji symboli.',
        ),
        ok: false,
      };
    }
    return { ok: true, status: result.data };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function startSymbolReviewProjection(
  api: SymbolReviewClient,
  gameId: string,
): Promise<
  | {
      readonly ok: true;
      readonly value: SymbolCellReviewProjectionStartResponse;
    }
  | { readonly error: string; readonly ok: false }
> {
  try {
    const result = await api.startSymbolCellReviewProjectionBackfill(gameId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się rozpocząć przygotowania weryfikacji symboli.',
        ),
        ok: false,
      };
    }
    return { ok: true, value: result.data };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export interface LoadSymbolReviewPageOptions {
  readonly afterCursor?: string;
  readonly beforeCursor?: string;
  readonly gameId: string;
  readonly limit: number;
  readonly maxConfidence?: number;
  readonly minConfidence?: number;
  readonly state: SymbolCellReviewFilterState;
  readonly symbolId: string | 'unknown';
}

export interface LoadSymbolReviewCountsOptions {
  readonly catalogRevision: number;
  readonly gameId: string;
  readonly maxConfidence?: number;
  readonly minConfidence?: number;
  readonly state: SymbolCellReviewFilterState;
  readonly symbolId: string | 'unknown';
}

export type SymbolReviewCountsResult =
  | {
      readonly ok: true;
      readonly snapshot: SymbolCellReviewCountSnapshotResponse;
    }
  | { readonly error: string; readonly ok: false };

export type SymbolReviewPageResult =
  | { readonly ok: true; readonly page: SymbolCellReviewPageResponse }
  | {
      readonly error: string;
      readonly isProjectionRebuilding: boolean;
      readonly ok: false;
    };

export async function loadSymbolReviewGames(
  api: SymbolReviewClient,
): Promise<
  | { readonly games: readonly GameResponse[]; readonly ok: true }
  | { readonly error: string; readonly ok: false }
> {
  try {
    const result = await api.listGames();
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(result.error, 'Nie udało się pobrać gier.'),
        ok: false,
      };
    }
    return {
      games: result.data
        .filter((game) => game.status !== 'archived')
        .sort(
          (left, right) =>
            left.name.localeCompare(right.name, 'pl-PL') ||
            left.code.localeCompare(right.code),
        ),
      ok: true,
    };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function loadSymbolReviewSymbols(
  api: SymbolReviewClient,
  gameId: string,
): Promise<
  | { readonly ok: true; readonly symbols: readonly SymbolResponse[] }
  | { readonly error: string; readonly ok: false }
> {
  try {
    const result = await api.listSymbols(gameId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać katalogu symboli.',
        ),
        ok: false,
      };
    }
    return {
      ok: true,
      symbols: result.data
        .filter((symbol) => symbol.status === 'active')
        .sort(
          (left, right) =>
            left.displayOrder - right.displayOrder ||
            left.code.localeCompare(right.code),
        ),
    };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function loadSymbolReviewPage(
  api: SymbolReviewClient,
  options: LoadSymbolReviewPageOptions,
): Promise<SymbolReviewPageResult> {
  try {
    const result = await api.listSymbolCellReviews({
      ...options,
    });
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać cropów do weryfikacji.',
        ),
        isProjectionRebuilding: isApiErrorCode(
          result.error,
          'SYMBOL_CELL_REVIEW_PROJECTION_INCOMPLETE',
        ),
        ok: false,
      };
    }
    return { ok: true, page: result.data };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      isProjectionRebuilding: false,
      ok: false,
    };
  }
}

export async function loadSymbolReviewCounts(
  api: SymbolReviewClient,
  options: LoadSymbolReviewCountsOptions,
): Promise<SymbolReviewCountsResult> {
  try {
    const result = await api.getSymbolCellReviewCounts(options);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać liczników weryfikacji.',
        ),
        ok: false,
      };
    }
    return { ok: true, snapshot: result.data };
  } catch {
    return {
      error: 'Nie udało się pobrać liczników weryfikacji.',
      ok: false,
    };
  }
}

function isApiErrorCode(error: unknown, code: string): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    error.code === code
  );
}
