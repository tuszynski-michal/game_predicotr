import type { AdminApiClient } from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';

export type LocalReviewerStartClient = Pick<
  AdminApiClient,
  'startLocalReviewer'
>;

export type LocalReviewerStartResult =
  { readonly ok: true } | { readonly error: string; readonly ok: false };

const localReviewerCommand = {
  confirmed: true,
  target: 'local-reviewer',
} as const;

const LOCAL_REVIEWER_ORIGIN = 'http://127.0.0.1:3001';

export async function startLocalReviewerProcess(
  api: LocalReviewerStartClient,
): Promise<LocalReviewerStartResult> {
  try {
    const result = await api.startLocalReviewer(localReviewerCommand);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się uruchomić lokalnej aplikacji Reviewer.',
        ),
        ok: false,
      };
    }
    if (
      result.data.state !== 'running' ||
      result.data.reviewerReady !== true ||
      result.data.publicOrigin !== null ||
      !isExactLocalReviewerTarget(result.data.target)
    ) {
      return {
        error: 'Lokalna aplikacja Reviewer nie osiągnęła gotowego stanu.',
        ok: false,
      };
    }
    return { ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

function isExactLocalReviewerTarget(value: string): boolean {
  try {
    const target = new URL(value);
    return (
      target.origin === LOCAL_REVIEWER_ORIGIN &&
      target.pathname === '/' &&
      target.search === '' &&
      target.hash === '' &&
      target.username === '' &&
      target.password === ''
    );
  } catch {
    return false;
  }
}
