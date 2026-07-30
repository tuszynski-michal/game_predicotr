import type {
  AdminApiClient,
  GameResponse,
  ImageReviewView,
  JobResponse,
  OperationalImageReviewPageResponse,
  OperationalImageReviewGeometryCommand,
  OperationalImageReviewGeometryPreviewCommand,
  OperationalImageReviewGeometryResponse,
  OperationalImageReviewResolutionCommand,
  OperationalImageReviewResolutionResponse,
  SymbolResponse,
  VerifiedCohortExportResponse,
  VerifiedCohortFreezeResponse,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';
import {
  isImageImportJob,
  orderOperationalReviewGames,
  orderOperationalReviewJobs,
  orderOperationalReviewSymbols,
} from './operational-review-state.ts';

export type OperationalReviewsClient = Pick<
  AdminApiClient,
  | 'listGames'
  | 'listJobs'
  | 'listOperationalImageReviewItems'
  | 'listSymbols'
  | 'previewOperationalImageReviewGeometry'
  | 'createOperationalImageReviewGeometryRevision'
  | 'resolveOperationalImageReviewItem'
  | 'freezeVerifiedImageReviewCohort'
  | 'listVerifiedImageReviewCohorts'
>;

export interface OperationalReviewGeometryOptions {
  readonly gameId: string;
  readonly importJobId: string;
  readonly reviewItemId: string;
}

export async function previewOperationalReviewGeometry(
  api: OperationalReviewsClient,
  options: OperationalReviewGeometryOptions & {
    readonly command: OperationalImageReviewGeometryPreviewCommand;
  },
): Promise<
  | { readonly blob: Blob; readonly ok: true }
  | {
      readonly error: string;
      readonly isRevisionConflict: boolean;
      readonly ok: false;
    }
> {
  try {
    const result = await api.previewOperationalImageReviewGeometry(
      options.reviewItemId,
      { gameId: options.gameId, importJobId: options.importJobId },
      options.command,
    );
    if (result.error !== undefined || !(result.data instanceof Blob)) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się wygenerować podglądu poprawionej siatki.',
        ),
        isRevisionConflict:
          isApiErrorCode(result.error, 'IMAGE_REVIEW_REVISION_CONFLICT') ||
          isApiErrorCode(
            result.error,
            'IMAGE_REVIEW_GEOMETRY_REVISION_CONFLICT',
          ),
        ok: false,
      };
    }
    return { blob: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      isRevisionConflict: false,
      ok: false,
    };
  }
}

export async function saveOperationalReviewGeometry(
  api: OperationalReviewsClient,
  options: OperationalReviewGeometryOptions & {
    readonly command: OperationalImageReviewGeometryCommand;
  },
): Promise<
  | {
      readonly geometry: OperationalImageReviewGeometryResponse;
      readonly ok: true;
    }
  | {
      readonly error: string;
      readonly isRevisionConflict: boolean;
      readonly ok: false;
    }
> {
  try {
    const result = await api.createOperationalImageReviewGeometryRevision(
      options.reviewItemId,
      { gameId: options.gameId, importJobId: options.importJobId },
      options.command,
    );
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się zapisać poprawionej geometrii.',
        ),
        isRevisionConflict:
          isApiErrorCode(result.error, 'IMAGE_REVIEW_REVISION_CONFLICT') ||
          isApiErrorCode(
            result.error,
            'IMAGE_REVIEW_GEOMETRY_REVISION_CONFLICT',
          ),
        ok: false,
      };
    }
    return { geometry: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      isRevisionConflict: false,
      ok: false,
    };
  }
}

export type OperationalReviewGamesResult =
  | { readonly games: readonly GameResponse[]; readonly ok: true }
  | { readonly error: string; readonly ok: false };

export async function loadOperationalReviewGames(
  api: OperationalReviewsClient,
): Promise<OperationalReviewGamesResult> {
  try {
    const result = await api.listGames();
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać gier do weryfikacji.',
        ),
        ok: false,
      };
    }
    return {
      games: orderOperationalReviewGames(
        result.data.filter((game) => game.status === 'active'),
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

export type OperationalReviewJobsResult =
  | { readonly jobs: readonly JobResponse[]; readonly ok: true }
  | { readonly error: string; readonly ok: false };

export async function loadOperationalReviewJobs(
  api: OperationalReviewsClient,
  gameId: string,
): Promise<OperationalReviewJobsResult> {
  try {
    const result = await api.listJobs({
      gameId,
      jobType: 'import',
      limit: 50,
    });
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać importów zdjęć.',
        ),
        ok: false,
      };
    }
    return {
      jobs: orderOperationalReviewJobs(result.data.filter(isImageImportJob)),
      ok: true,
    };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export type OperationalReviewSymbolsResult =
  | { readonly ok: true; readonly symbols: readonly SymbolResponse[] }
  | { readonly error: string; readonly ok: false };

export async function loadOperationalReviewSymbols(
  api: OperationalReviewsClient,
  gameId: string,
): Promise<OperationalReviewSymbolsResult> {
  try {
    const result = await api.listSymbols(gameId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać symboli do korekty planszy.',
        ),
        ok: false,
      };
    }
    return {
      ok: true,
      symbols: orderOperationalReviewSymbols(result.data),
    };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export interface LoadOperationalReviewPageOptions {
  readonly gameId: string;
  readonly importJobId: string;
  readonly view: ImageReviewView;
  readonly afterCursor?: string;
  readonly beforeCursor?: string;
  readonly sequenceNumber?: number;
}

export type OperationalReviewPageResult =
  | {
      readonly ok: true;
      readonly page: OperationalImageReviewPageResponse;
    }
  | {
      readonly error: string;
      readonly isCursorConflict: boolean;
      readonly ok: false;
    };

export async function loadOperationalReviewPage(
  api: OperationalReviewsClient,
  options: LoadOperationalReviewPageOptions,
): Promise<OperationalReviewPageResult> {
  try {
    const result = await api.listOperationalImageReviewItems({
      ...options,
      limit: 1,
    });
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać planszy do weryfikacji.',
        ),
        isCursorConflict:
          isApiErrorCode(result.error, 'IMAGE_REVIEW_CURSOR_STALE') ||
          isApiErrorCode(result.error, 'IMAGE_REVIEW_CURSOR_SCOPE_INVALID'),
        ok: false,
      };
    }
    return { ok: true, page: result.data };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      isCursorConflict: false,
      ok: false,
    };
  }
}

export interface ResolveOperationalReviewOptions {
  readonly command: OperationalImageReviewResolutionCommand;
  readonly gameId: string;
  readonly importJobId: string;
  readonly reviewItemId: string;
}

export type ResolveOperationalReviewResult =
  | {
      readonly ok: true;
      readonly resolution: OperationalImageReviewResolutionResponse;
    }
  | {
      readonly error: string;
      readonly isRevisionConflict: boolean;
      readonly ok: false;
    };

export async function resolveOperationalReview(
  api: OperationalReviewsClient,
  options: ResolveOperationalReviewOptions,
): Promise<ResolveOperationalReviewResult> {
  try {
    const result = await api.resolveOperationalImageReviewItem(
      options.reviewItemId,
      {
        gameId: options.gameId,
        importJobId: options.importJobId,
      },
      options.command,
    );
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się zapisać decyzji dla planszy.',
        ),
        isRevisionConflict:
          isApiErrorCode(result.error, 'IMAGE_REVIEW_REVISION_CONFLICT') ||
          isApiErrorCode(
            result.error,
            'IMAGE_REVIEW_GEOMETRY_REVISION_CONFLICT',
          ),
        ok: false,
      };
    }
    return { ok: true, resolution: result.data };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      isRevisionConflict: false,
      ok: false,
    };
  }
}

export type VerifiedCohortHistoryResult =
  | {
      readonly exports: readonly VerifiedCohortExportResponse[];
      readonly ok: true;
    }
  | { readonly error: string; readonly ok: false };

export async function loadVerifiedCohortHistory(
  api: OperationalReviewsClient,
  gameId: string,
  importJobId: string,
): Promise<VerifiedCohortHistoryResult> {
  try {
    const result = await api.listVerifiedImageReviewCohorts({
      gameId,
      importJobId,
      limit: 20,
    });
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać historii zamrożonych kohort.',
        ),
        ok: false,
      };
    }
    return { exports: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export type FreezeVerifiedCohortResult =
  | {
      readonly freeze: VerifiedCohortFreezeResponse;
      readonly ok: true;
    }
  | { readonly error: string; readonly ok: false };

export async function freezeVerifiedCohort(
  api: OperationalReviewsClient,
  gameId: string,
  importJobId: string,
): Promise<FreezeVerifiedCohortResult> {
  try {
    const result = await api.freezeVerifiedImageReviewCohort(
      { gameId, importJobId },
      { createdBy: 'local-admin' },
    );
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się zamrozić zweryfikowanej kohorty.',
        ),
        ok: false,
      };
    }
    return { freeze: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
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
