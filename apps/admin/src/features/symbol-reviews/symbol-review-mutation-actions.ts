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
  'applySymbolCellReviewDecision' | 'selectSymbolReferenceFromCellReview'
>;

export type SymbolImageFromReviewResult =
  | {
      readonly decision: SymbolCellReviewMutationResponse;
      readonly ok: true;
      readonly symbolName: string;
    }
  | {
      readonly decision: SymbolCellReviewMutationResponse | null;
      readonly error: string;
      readonly ok: false;
    };

/**
 * Approve one crop (optionally as a newly chosen symbol) and use it as that
 * symbol's image. The image is shown in "Symbole", "Wyszukaj plansze" and is
 * the source of the symbol image for later mobile releases.
 */
export async function setSymbolImageFromReviewCell(
  api: SymbolReviewMutationClient,
  gameId: string,
  target: SymbolReviewExplicitTarget,
  targetSymbolId: string | null,
): Promise<SymbolImageFromReviewResult> {
  const decision = await applySingleSymbolReviewDecision(
    api,
    gameId,
    targetSymbolId === null ? 'approve' : 'reassign',
    target,
    targetSymbolId,
  );
  if (!decision.ok) {
    return { decision: null, error: decision.error, ok: false };
  }
  try {
    const result = await api.selectSymbolReferenceFromCellReview(
      gameId,
      target.cellReviewId,
      {
        expectedChecksumSha256: target.expectedCropChecksumSha256,
        selectedBy: 'admin-local',
      },
    );
    if (result.error !== undefined || result.data === undefined) {
      return {
        decision: decision.value,
        error: `Crop zatwierdzono, ale nie ustawiono grafiki symbolu: ${apiErrorMessage(
          result.error,
          'nieznany błąd.',
        )}`,
        ok: false,
      };
    }
    return {
      decision: decision.value,
      ok: true,
      symbolName: result.data.name,
    };
  } catch {
    return {
      decision: decision.value,
      error:
        'Crop zatwierdzono, ale połączenie z lokalnym Admin API zostało przerwane przed ustawieniem grafiki.',
      ok: false,
    };
  }
}

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
    ...(action === 'reassign' ||
    (action === 'mark_blurry' && targetSymbolId !== null)
      ? { targetSymbolId: targetSymbolId! }
      : {}),
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
