import type {
  AdminApiClient,
  RulesPublicationReadinessResponse,
  RulesVersionCreate,
  RulesVersionResponse,
  RulesVersionUpdate,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';
import type { ValidatedRulesVersionDraft } from './rules-version-state.ts';

export type RulesVersionsClient = Pick<
  AdminApiClient,
  | 'createRulesVersion'
  | 'archiveRulesVersion'
  | 'archivePayline'
  | 'createPayline'
  | 'createPayoutRule'
  | 'listGames'
  | 'listPaylines'
  | 'listPayoutRules'
  | 'listRulesVersions'
  | 'listRulesVersionSymbols'
  | 'listSymbols'
  | 'getRulesPublicationReadiness'
  | 'publishRulesVersion'
  | 'updatePayline'
  | 'updatePayoutRule'
  | 'updateRulesVersion'
  | 'updateRulesVersionSymbol'
>;

export type SaveRulesVersionIntent =
  | { readonly mode: 'create'; readonly gameId: string }
  | { readonly mode: 'edit'; readonly rulesVersionId: string };

export type SaveRulesVersionResult =
  | { readonly ok: true; readonly rulesVersion: RulesVersionResponse }
  | { readonly error: string; readonly ok: false };

export type PublicationReadinessResult =
  | {
      readonly ok: true;
      readonly readiness: RulesPublicationReadinessResponse;
    }
  | { readonly error: string; readonly ok: false };

export type RulesVersionTransitionResult =
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

export async function loadPublicationReadiness(
  api: RulesVersionsClient,
  rulesVersionId: string,
): Promise<PublicationReadinessResult> {
  try {
    const result = await api.getRulesPublicationReadiness(rulesVersionId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się sprawdzić gotowości wersji.',
        ),
        ok: false,
      };
    }
    return { ok: true, readiness: result.data };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function publishRulesVersion(
  api: RulesVersionsClient,
  rulesVersionId: string,
): Promise<RulesVersionTransitionResult> {
  try {
    const result = await api.publishRulesVersion(rulesVersionId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się opublikować wersji reguł.',
        ),
        ok: false,
      };
    }
    return { ok: true, rulesVersion: result.data };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function archiveRulesVersion(
  api: RulesVersionsClient,
  rulesVersion: RulesVersionResponse,
): Promise<RulesVersionTransitionResult> {
  try {
    const result = await api.archiveRulesVersion(rulesVersion.id);
    if (result.error !== undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się zarchiwizować wersji reguł.',
        ),
        ok: false,
      };
    }
    return {
      ok: true,
      rulesVersion: { ...rulesVersion, status: 'archived' },
    };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}
