import type {
  AdminApiClient,
  RulesVersionCreate,
  RulesVersionResponse,
  RulesVersionUpdate,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';
import type { ValidatedRulesVersionDraft } from './rules-version-state.ts';

export type RulesVersionsClient = Pick<
  AdminApiClient,
  | 'createRulesVersion'
  | 'archivePayline'
  | 'createPayline'
  | 'listGames'
  | 'listPaylines'
  | 'listRulesVersions'
  | 'updatePayline'
  | 'updateRulesVersion'
>;

export type SaveRulesVersionIntent =
  | { readonly mode: 'create'; readonly gameId: string }
  | { readonly mode: 'edit'; readonly rulesVersionId: string };

export type SaveRulesVersionResult =
  | { readonly ok: true; readonly rulesVersion: RulesVersionResponse }
  | { readonly error: string; readonly ok: false };

export async function saveRulesVersion(
  api: RulesVersionsClient,
  intent: SaveRulesVersionIntent,
  draft: ValidatedRulesVersionDraft,
): Promise<SaveRulesVersionResult> {
  try {
    const body = {
      columns: draft.columns,
      rows: draft.rows,
      spinCost: draft.spinCost,
    };
    const result =
      intent.mode === 'create'
        ? await api.createRulesVersion(
            intent.gameId,
            body satisfies RulesVersionCreate,
          )
        : await api.updateRulesVersion(
            intent.rulesVersionId,
            body satisfies RulesVersionUpdate,
          );

    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się zapisać wersji reguł.',
        ),
        ok: false,
      };
    }
    return { ok: true, rulesVersion: result.data };
  } catch {
    return {
      error:
        'Połączenie z lokalnym Admin API zostało przerwane. Spróbuj ponownie.',
      ok: false,
    };
  }
}
