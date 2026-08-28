import type {
  SymbolCellReviewAction,
  SymbolCellReviewMutationRequest,
  SymbolCellReviewMutationResponse,
} from '@game-predictor/admin-api-client';

import type { createConfiguredAdminApiClient } from '@/api/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';

import type { SymbolReviewExplicitTarget } from './symbol-review-selection-state.ts';

export type SymbolReviewMutationClient = Pick<
  ReturnType<typeof createConfiguredAdminApiClient>,
  'applySymbolCellReviewDecision'
>;

export type SymbolReviewMutationResult =
  | { readonly ok: true; readonly value: SymbolCellReviewMutationResponse }
  | { readonly error: string; readonly ok: false };

export async function applySingleSymbolReviewDecision(
  api: SymbolReviewMutationClient,
  gameId: string,
  action: SymbolCellReviewAction,
  target: SymbolReviewExplicitTarget,
  targetSymbolId: string | null,
): Promise<SymbolReviewMutationResult> {
  if (action === 'reassign' && targetSymbolId === null) {
    return { error: 'Wybierz docelowy aktywny symbol.', ok: false };
  }
  const request: SymbolCellReviewMutationRequest = {
    action,
    expectedCropChecksumSha256: target.expectedCropChecksumSha256,
    expectedCropSampleId: target.expectedCropSampleId,
    expectedGeometryRevision: target.expectedGeometryRevision,
    expectedRevision: target.expectedRevision,
    ...(action === 'reassign' ? { targetSymbolId: targetSymbolId! } : {}),
  };
  try {
    const result = await api.applySymbolCellReviewDecision(
      gameId,
      target.cellReviewId,
      request,
    );
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się zapisać zmiany symbolu.',
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
