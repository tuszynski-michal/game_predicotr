import type {
  AdminApiClient,
  PaylineCreate,
  PaylineResponse,
  PaylineUpdate,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';
import {
  nextPaylineDisplayOrder,
  type ValidatedPaylineDraft,
} from './payline-editor-state.ts';

export type PaylinesClient = Pick<
  AdminApiClient,
  'archivePayline' | 'createPayline' | 'listPaylines' | 'updatePayline'
>;

export type SavePaylineIntent =
  | { readonly mode: 'create' }
  | { readonly mode: 'edit'; readonly paylineId: string };

export type SavePaylineResult =
  | { readonly ok: true; readonly payline: PaylineResponse }
  | { readonly error: string; readonly ok: false };

export async function savePayline(
  api: PaylinesClient,
  rulesVersionId: string,
  intent: SavePaylineIntent,
  draft: ValidatedPaylineDraft,
  existingPaylines: readonly PaylineResponse[],
): Promise<SavePaylineResult> {
  try {
    if (intent.mode === 'create') {
      const displayOrder = nextPaylineDisplayOrder(existingPaylines);
      if (displayOrder === null) {
        return {
          error:
            'Nie można nadać automatycznej kolejności: osiągnięto maksymalną liczbę wzorców.',
          ok: false,
        };
      }
      const result = await api.createPayline(rulesVersionId, {
        code: draft.code,
        displayOrder,
        isActive: draft.isActive,
        name: draft.code,
        rowPath: [...draft.rowPath],
      } satisfies PaylineCreate);
      return mapSaveResponse(result);
    }
    const result = await api.updatePayline(rulesVersionId, intent.paylineId, {
      isActive: draft.isActive,
      rowPath: [...draft.rowPath],
    } satisfies PaylineUpdate);
    return mapSaveResponse(result);
  } catch {
    return {
      error:
        'Połączenie z lokalnym Admin API zostało przerwane. Spróbuj ponownie.',
      ok: false,
    };
  }
}

function mapSaveResponse(result: {
  readonly data?: PaylineResponse;
  readonly error?: unknown;
}): SavePaylineResult {
  if (result.error !== undefined || result.data === undefined) {
    return {
      error: apiErrorMessage(result.error, 'Nie udało się zapisać wzorca.'),
      ok: false,
    };
  }
  return { ok: true, payline: result.data };
}

export type ArchivePaylineResult =
  { readonly ok: true } | { readonly error: string; readonly ok: false };

export async function archivePayline(
  api: PaylinesClient,
  rulesVersionId: string,
  paylineId: string,
): Promise<ArchivePaylineResult> {
  try {
    const result = await api.archivePayline(rulesVersionId, paylineId);
    if (result.error !== undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się zarchiwizować wzorca.',
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
