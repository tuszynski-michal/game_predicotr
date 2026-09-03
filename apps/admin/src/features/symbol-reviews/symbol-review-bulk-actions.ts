import type {
  SymbolCellReviewAction,
  SymbolCellReviewBulkOperationRequest,
  SymbolCellReviewBulkOperationResponse,
  SymbolCellReviewBulkPreviewResponse,
} from '@game-predictor/admin-api-client';

import type { createConfiguredAdminApiClient } from '@/api/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';

import type { SymbolReviewSelection } from './symbol-review-selection-state.ts';

export type SymbolReviewBulkClient = Pick<
  ReturnType<typeof createConfiguredAdminApiClient>,
  | 'getSymbolCellReviewBulkOperation'
  | 'previewSymbolCellReviewBulkOperation'
  | 'startSymbolCellReviewBulkOperation'
>;

export interface SymbolReviewBulkCommand {
  readonly action: SymbolCellReviewAction;
  readonly request: SymbolCellReviewBulkOperationRequest;
}

export type SymbolReviewBulkResult<T> =
  | { readonly ok: true; readonly value: T }
  | { readonly error: string; readonly ok: false };

export function createSymbolReviewBulkCommand(
  action: SymbolCellReviewAction,
  selection: SymbolReviewSelection,
  targetSymbolId: string | null,
): SymbolReviewBulkCommand | null {
  if (action === 'reassign' && targetSymbolId === null) return null;
  return {
    action,
    request: {
      action,
      selection:
        selection.kind === 'explicit'
          ? {
              kind: 'explicit',
              targets: Object.values(selection.targetsById),
            }
          : {
              catalogRevision: selection.snapshot.catalogRevision,
              excludedCellReviewIds: [...selection.excludedIds],
              kind: 'filter',
              maxConfidence: selection.snapshot.maxConfidence,
              minConfidence: selection.snapshot.minConfidence,
              state: selection.snapshot.state,
              symbolId: selection.snapshot.symbolId,
            },
      ...(action === 'reassign' ||
      (action === 'mark_blurry' && targetSymbolId !== null)
        ? { targetSymbolId: targetSymbolId! }
        : {}),
    },
  };
}

export async function previewSymbolReviewBulkOperation(
  api: SymbolReviewBulkClient,
  gameId: string,
  command: SymbolReviewBulkCommand,
): Promise<SymbolReviewBulkResult<SymbolCellReviewBulkPreviewResponse>> {
  try {
    const result = await api.previewSymbolCellReviewBulkOperation(
      gameId,
      command.request,
    );
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się przygotować podglądu operacji.',
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

export async function startSymbolReviewBulkOperation(
  api: SymbolReviewBulkClient,
  gameId: string,
  command: SymbolReviewBulkCommand,
  idempotencyKey: string,
): Promise<SymbolReviewBulkResult<SymbolCellReviewBulkOperationResponse>> {
  try {
    const result = await api.startSymbolCellReviewBulkOperation(gameId, {
      ...command.request,
      idempotencyKey,
    });
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się uruchomić operacji.',
        ),
        ok: false,
      };
    }
    return { ok: true, value: result.data.operation };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function getSymbolReviewBulkOperation(
  api: SymbolReviewBulkClient,
  gameId: string,
  operationId: string,
): Promise<SymbolReviewBulkResult<SymbolCellReviewBulkOperationResponse>> {
  try {
    const result = await api.getSymbolCellReviewBulkOperation(
      gameId,
      operationId,
    );
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się odświeżyć stanu operacji.',
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

export function isSymbolReviewBulkOperationTerminal(
  operation: SymbolCellReviewBulkOperationResponse,
): boolean {
  return ['cancelled', 'completed', 'failed'].includes(operation.status);
}
