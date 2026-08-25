import type {
  AdminApiClient,
  BoardCellGeometryCorrectionContextResponse,
  BoardCellGeometryManualPreviewCommand,
  BoardCellGeometryManualResolutionCommand,
  BoardCellGeometryManualResolutionResponse,
  BoardCellGeometryPendingPageResponse,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';

export type DeferredBoardCellGeometryClient = Pick<
  AdminApiClient,
  | 'getPendingBoardCellGeometryCorrectionContext'
  | 'listPendingBoardCellGeometry'
  | 'previewPendingBoardCellGeometryCorrection'
  | 'resolvePendingBoardCellGeometryManually'
>;

export interface DeferredBoardCellGeometryScope {
  readonly gameId: string;
  readonly importJobId: string;
}

export type DeferredBoardCellGeometryFailure = {
  readonly error: string;
  readonly isConflict: boolean;
  readonly ok: false;
};

export async function loadDeferredBoardCellGeometryPage(
  api: DeferredBoardCellGeometryClient,
  scope: DeferredBoardCellGeometryScope,
  cursor?: string,
): Promise<
  | { readonly ok: true; readonly page: BoardCellGeometryPendingPageResponse }
  | DeferredBoardCellGeometryFailure
> {
  try {
    const result = await api.listPendingBoardCellGeometry({
      ...scope,
      ...(cursor === undefined ? {} : { cursor }),
      limit: 1,
      status: 'pending',
    });
    if (result.error !== undefined || result.data === undefined) {
      return failure(
        result.error,
        'Nie udało się pobrać kolejki korekty geometrii.',
      );
    }
    return { ok: true, page: result.data };
  } catch {
    return connectionFailure();
  }
}

export async function loadDeferredBoardCellGeometryContext(
  api: DeferredBoardCellGeometryClient,
  scope: DeferredBoardCellGeometryScope,
  pendingId: string,
): Promise<
  | {
      readonly context: BoardCellGeometryCorrectionContextResponse;
      readonly ok: true;
    }
  | DeferredBoardCellGeometryFailure
> {
  try {
    const result = await api.getPendingBoardCellGeometryCorrectionContext(
      pendingId,
      scope,
    );
    if (result.error !== undefined || result.data === undefined) {
      return failure(
        result.error,
        'Nie udało się pobrać kontekstu odroczonej planszy.',
      );
    }
    return { context: result.data, ok: true };
  } catch {
    return connectionFailure();
  }
}

export async function previewDeferredBoardCellGeometry(
  api: DeferredBoardCellGeometryClient,
  scope: DeferredBoardCellGeometryScope,
  pendingId: string,
  command: BoardCellGeometryManualPreviewCommand,
): Promise<
  { readonly blob: Blob; readonly ok: true } | DeferredBoardCellGeometryFailure
> {
  try {
    const result = await api.previewPendingBoardCellGeometryCorrection(
      pendingId,
      scope,
      command,
    );
    if (result.error !== undefined || !(result.data instanceof Blob)) {
      return failure(
        result.error,
        'Nie udało się wygenerować podglądu 15 cropów.',
      );
    }
    return { blob: result.data, ok: true };
  } catch {
    return connectionFailure();
  }
}

export async function resolveDeferredBoardCellGeometry(
  api: DeferredBoardCellGeometryClient,
  scope: DeferredBoardCellGeometryScope,
  pendingId: string,
  command: BoardCellGeometryManualResolutionCommand,
): Promise<
  | {
      readonly ok: true;
      readonly resolution: BoardCellGeometryManualResolutionResponse;
    }
  | DeferredBoardCellGeometryFailure
> {
  try {
    const result = await api.resolvePendingBoardCellGeometryManually(
      pendingId,
      scope,
      command,
    );
    if (result.error !== undefined || result.data === undefined) {
      return failure(
        result.error,
        'Nie udało się zapisać ręcznej geometrii planszy.',
      );
    }
    return { ok: true, resolution: result.data };
  } catch {
    return connectionFailure();
  }
}

function failure(
  error: unknown,
  fallback: string,
): DeferredBoardCellGeometryFailure {
  return {
    error: apiErrorMessage(error, fallback),
    isConflict: isDeferredGeometryConflict(error),
    ok: false,
  };
}

function connectionFailure(): DeferredBoardCellGeometryFailure {
  return {
    error: 'Połączenie z lokalnym Admin API zostało przerwane.',
    isConflict: false,
    ok: false,
  };
}

function isDeferredGeometryConflict(error: unknown): boolean {
  if (typeof error !== 'object' || error === null || !('code' in error)) {
    return false;
  }
  const code = (error as { readonly code?: unknown }).code;
  return (
    typeof code === 'string' &&
    (code === 'IMAGE_BOARD_CELL_PENDING_MANIFEST_CONFLICT' ||
      code === 'IMAGE_BOARD_CELL_PENDING_REVISION_CONFLICT' ||
      code === 'IMAGE_BOARD_CELL_PENDING_RESOLUTION_CONFLICT' ||
      code === 'IMAGE_BOARD_CELL_PENDING_NOT_EDITABLE' ||
      code === 'IMAGE_BOARD_CELL_PENDING_NOT_FOUND')
  );
}
