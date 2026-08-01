import type {
  AdminApiClient,
  DatasetVersionResponse,
  JobResponse,
  PayoutJobCreate,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';
import { PAYOUT_ALGORITHM_VERSION } from './payout-computation-state.ts';

export type PayoutComputationClient = Pick<
  AdminApiClient,
  'createJob' | 'getJob' | 'listDatasetVersions' | 'listJobs' | 'retryJob'
>;

export type LoadPayoutWorkspaceResult =
  | {
      readonly datasets: readonly DatasetVersionResponse[];
      readonly jobs: readonly JobResponse[];
      readonly ok: true;
    }
  | { readonly error: string; readonly ok: false };

export async function loadPayoutWorkspace(
  api: PayoutComputationClient,
  gameId: string,
): Promise<LoadPayoutWorkspaceResult> {
  try {
    const [datasets, jobs] = await Promise.all([
      api.listDatasetVersions(gameId),
      api.listJobs({ gameId, jobType: 'payout', limit: 200 }),
    ]);
    if (
      datasets.error !== undefined ||
      datasets.data === undefined ||
      jobs.error !== undefined ||
      jobs.data === undefined
    ) {
      return {
        error: apiErrorMessage(
          datasets.error ?? jobs.error,
          'Nie udało się sprawdzić gotowości przeliczania.',
        ),
        ok: false,
      };
    }
    return { datasets: datasets.data, jobs: jobs.data, ok: true };
  } catch {
    return {
      error: 'Brak połączenia z lokalnym Admin API.',
      ok: false,
    };
  }
}

export type PayoutJobMutationResult =
  | { readonly job: JobResponse; readonly ok: true }
  | { readonly error: string; readonly ok: false };

export async function startPayoutComputation(
  api: PayoutComputationClient,
  gameId: string,
  datasetVersionId: string,
  rulesVersionId: string,
): Promise<PayoutJobMutationResult> {
  try {
    const body = {
      gameId,
      inputPayload: {
        algorithmVersion: PAYOUT_ALGORITHM_VERSION,
        datasetVersionId,
        rulesVersionId,
        schemaVersion: 1,
      },
      jobType: 'payout',
    } satisfies PayoutJobCreate;
    const result = await api.createJob(body);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się uruchomić przeliczania payoutów.',
        ),
        ok: false,
      };
    }
    return { job: result.data, ok: true };
  } catch {
    return { error: 'Brak połączenia z lokalnym Admin API.', ok: false };
  }
}

export async function refreshPayoutJob(
  api: PayoutComputationClient,
  jobId: string,
): Promise<PayoutJobMutationResult> {
  try {
    const result = await api.getJob(jobId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się odświeżyć postępu przeliczania.',
        ),
        ok: false,
      };
    }
    return { job: result.data, ok: true };
  } catch {
    return { error: 'Brak połączenia z lokalnym Admin API.', ok: false };
  }
}

export async function retryPayoutComputation(
  api: PayoutComputationClient,
  jobId: string,
): Promise<PayoutJobMutationResult> {
  try {
    const result = await api.retryJob(jobId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się wznowić przeliczania payoutów.',
        ),
        ok: false,
      };
    }
    return { job: result.data, ok: true };
  } catch {
    return { error: 'Brak połączenia z lokalnym Admin API.', ok: false };
  }
}
