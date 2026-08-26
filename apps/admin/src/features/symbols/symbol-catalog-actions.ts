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
  | 'deleteSymbol'
  | 'createSymbol'
  | 'listGames'
  | 'listSymbols'
  | 'symbolImageAssetUrl'
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
            isWildcard: draft.isWildcard,
            name: draft.name,
          } satisfies SymbolCreate)
        : await api.updateSymbol(gameId, intent.symbolId, {
            isWildcard: draft.isWildcard,
            name: draft.name,
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

export type DeleteSymbolResult =
  | { readonly ok: true }
  | {
      readonly blockers: readonly string[];
      readonly error: string;
      readonly ok: false;
    };

export async function deleteSymbol(
  api: SymbolsClient,
  gameId: string,
  symbolId: string,
): Promise<DeleteSymbolResult> {
  try {
    const result = await api.deleteSymbol(gameId, symbolId);
    if (result.error !== undefined) {
      return {
        blockers: symbolDeleteBlockers(result.error.details),
        error: apiErrorMessage(result.error, 'Nie udało się usunąć symbolu.'),
        ok: false,
      };
    }
    return { ok: true };
  } catch {
    return {
      blockers: [],
      error:
        'Połączenie z lokalnym Admin API zostało przerwane. Usunięcie nie zostało potwierdzone.',
      ok: false,
    };
  }
}

const DELETE_BLOCKER_LABELS: Readonly<Record<string, string>> = {
  observationPredictions: 'predykcje obserwacji',
  pendingBoardPredictions: 'oczekujące predykcje plansz',
  resolvedBoardDecisions: 'rozwiązane plansze',
  rules: 'reguły',
  symbolModelActivations: 'aktywacje modelu symboli',
  symbolModelIterations: 'iteracje modelu symboli',
  trainingCohorts: 'kohorty treningowe',
};

function symbolDeleteBlockers(
  details: Readonly<Record<string, unknown>>,
): readonly string[] {
  return Object.entries(DELETE_BLOCKER_LABELS).flatMap(([key, label]) => {
    const count = details[key];
    return typeof count === 'number' && Number.isInteger(count) && count > 0
      ? [`${label}: ${count}`]
      : [];
  });
}
