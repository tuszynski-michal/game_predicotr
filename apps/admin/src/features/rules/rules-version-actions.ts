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
  | 'createRulesDraftFromPublished'
  | 'createJob'
  | 'archiveRulesVersion'
  | 'archivePayline'
  | 'createPayline'
  | 'createPayoutRule'
  | 'listGames'
  | 'listDatasetVersions'
  | 'listJobs'
  | 'listPaylines'
  | 'listPayoutRules'
  | 'listRulesVersions'
  | 'listRulesVersionSymbols'
  | 'listSymbols'
  | 'getJob'
  | 'getRulesPublicationReadiness'
  | 'publishRulesVersion'
  | 'retryJob'
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

export type LoadRulesVersionsResult =
  | {
      readonly ok: true;
      readonly rulesVersions: readonly RulesVersionResponse[];
    }
  | { readonly error: string; readonly ok: false };

export interface RulesRequestPolicy {
  readonly timeoutMs?: number;
}

export type PublicationReadinessResult =
  | {
      readonly ok: true;
      readonly readiness: RulesPublicationReadinessResponse;
    }
  | { readonly error: string; readonly ok: false };

export type RulesVersionTransitionResult =
  | { readonly ok: true; readonly rulesVersion: RulesVersionResponse }
  | { readonly error: string; readonly ok: false };

const DEFAULT_RULES_REQUEST_TIMEOUT_MS = 15_000;

class RulesRequestTimeoutError extends Error {
  constructor() {
    super('Rules request timed out.');
    this.name = 'RulesRequestTimeoutError';
  }
}

async function withRulesRequestTimeout<T>(
  request: Promise<T>,
  timeoutMs: number,
): Promise<T> {
  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timeoutId = setTimeout(
      () => reject(new RulesRequestTimeoutError()),
      timeoutMs,
    );
  });
  try {
    return await Promise.race([request, timeout]);
  } finally {
    if (timeoutId !== undefined) clearTimeout(timeoutId);
  }
}

function requestTimeout(policy?: RulesRequestPolicy): number {
  return policy?.timeoutMs ?? DEFAULT_RULES_REQUEST_TIMEOUT_MS;
}

export async function loadRulesVersionsForGame(
  api: RulesVersionsClient,
  gameId: string,
  policy?: RulesRequestPolicy,
): Promise<LoadRulesVersionsResult> {
  try {
    const result = await withRulesRequestTimeout(
      api.listRulesVersions(gameId),
      requestTimeout(policy),
    );
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać wersji reguł.',
        ),
        ok: false,
      };
    }
    return { ok: true, rulesVersions: result.data };
  } catch {
    return {
      error: 'Lokalne Admin API nie zakończyło pobierania wersji reguł.',
      ok: false,
    };
  }
}

export async function createEditableRulesDraft(
  api: RulesVersionsClient,
  publishedRulesVersionId: string,
): Promise<RulesVersionTransitionResult> {
  try {
    const result = await api.createRulesDraftFromPublished(
      publishedRulesVersionId,
    );
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się przygotować reguł do edycji.',
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

export async function saveRulesVersion(
  api: RulesVersionsClient,
  intent: SaveRulesVersionIntent,
  draft: ValidatedRulesVersionDraft,
  policy?: RulesRequestPolicy,
): Promise<SaveRulesVersionResult> {
  const timeoutMs = requestTimeout(policy);
  try {
    const body = {
      columns: draft.columns,
      rows: draft.rows,
      spinCost: draft.spinCost,
    };
    const result =
      intent.mode === 'create'
        ? await withRulesRequestTimeout(
            api.createRulesVersion(
              intent.gameId,
              body satisfies RulesVersionCreate,
            ),
            timeoutMs,
          )
        : await withRulesRequestTimeout(
            api.updateRulesVersion(
              intent.rulesVersionId,
              body satisfies RulesVersionUpdate,
            ),
            timeoutMs,
          );

    if (result.error !== undefined || result.data === undefined) {
      if (result.error === undefined && intent.mode === 'create') {
        const reconciled = await reconcileCreatedRulesVersion(
          api,
          intent.gameId,
          draft,
          timeoutMs,
        );
        if (reconciled !== null) {
          return { ok: true, rulesVersion: reconciled };
        }
      }
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
    if (intent.mode === 'create') {
      const reconciled = await reconcileCreatedRulesVersion(
        api,
        intent.gameId,
        draft,
        timeoutMs,
      );
      if (reconciled !== null) {
        return { ok: true, rulesVersion: reconciled };
      }
    }
    return {
      error:
        'Nie udało się potwierdzić zapisu reguł w lokalnym Admin API. Odśwież sekcję przed ponowieniem.',
      ok: false,
    };
  }
}

async function reconcileCreatedRulesVersion(
  api: RulesVersionsClient,
  gameId: string,
  draft: ValidatedRulesVersionDraft,
  timeoutMs: number,
): Promise<RulesVersionResponse | null> {
  try {
    const result = await withRulesRequestTimeout(
      api.listRulesVersions(gameId),
      timeoutMs,
    );
    if (result.error !== undefined || result.data === undefined) return null;
    return (
      result.data.find(
        (rulesVersion) =>
          rulesVersion.gameId === gameId &&
          rulesVersion.status === 'draft' &&
          rulesVersion.rows === draft.rows &&
          rulesVersion.columns === draft.columns &&
          rulesVersion.spinCost === draft.spinCost,
      ) ?? null
    );
  } catch {
    return null;
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
