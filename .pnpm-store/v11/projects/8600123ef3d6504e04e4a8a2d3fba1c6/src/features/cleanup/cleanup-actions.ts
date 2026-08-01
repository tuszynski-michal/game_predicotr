import type {
  AdminApiClient,
  CleanupPreviewResponse,
  CleanupResultResponse,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';

export type CleanupClient = Pick<
  AdminApiClient,
  | 'deleteMobileRelease'
  | 'previewGameLayoutDataReset'
  | 'previewMobileReleaseDeletion'
  | 'resetGameLayoutData'
>;

export type CleanupTarget =
  | { readonly id: string; readonly kind: 'game-layout-data' }
  | { readonly id: string; readonly kind: 'mobile-release' };

export type CleanupActionResult<T> =
  | { readonly data: T; readonly ok: true }
  | { readonly error: string; readonly ok: false };

export async function loadCleanupPreview(
  api: CleanupClient,
  target: CleanupTarget,
): Promise<CleanupActionResult<CleanupPreviewResponse>> {
  try {
    const response =
      target.kind === 'mobile-release'
        ? await api.previewMobileReleaseDeletion(target.id)
        : await api.previewGameLayoutDataReset(target.id);
    if (response.error !== undefined || response.data === undefined) {
      return {
        error: apiErrorMessage(
          response.error,
          'Nie udało się przygotować aktualnego zakresu operacji.',
        ),
        ok: false,
      };
    }
    return { data: response.data, ok: true };
  } catch {
    return {
      error: 'API jest niedostępne. Spróbuj ponownie po sprawdzeniu serwera.',
      ok: false,
    };
  }
}

export async function executeCleanup(
  api: CleanupClient,
  target: CleanupTarget,
  preview: CleanupPreviewResponse,
): Promise<CleanupActionResult<CleanupResultResponse>> {
  const body = {
    confirmationTarget: preview.confirmationTarget,
    confirmed: true,
    previewToken: preview.previewToken,
  };
  try {
    const response =
      target.kind === 'mobile-release'
        ? await api.deleteMobileRelease(target.id, body)
        : await api.resetGameLayoutData(target.id, body);
    if (response.error !== undefined || response.data === undefined) {
      return {
        error: apiErrorMessage(
          response.error,
          'Operacja nie została wykonana. Odśwież zakres i spróbuj ponownie.',
        ),
        ok: false,
      };
    }
    return { data: response.data, ok: true };
  } catch {
    return {
      error:
        'API jest niedostępne. Dane nie zostały świadomie oznaczone jako usunięte.',
      ok: false,
    };
  }
}
