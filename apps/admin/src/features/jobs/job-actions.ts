import type {
  AdminApiClient,
  JobResponse,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';
import type { JobFilters } from './job-state.ts';

export type JobsClient = Pick<
  AdminApiClient,
  'cancelJob' | 'listJobs' | 'retryJob'
>;

export type LoadJobsResult =
  | { readonly jobs: readonly JobResponse[]; readonly ok: true }
  | { readonly error: string; readonly ok: false };

export async function loadJobs(
  api: JobsClient,
  filters: JobFilters,
): Promise<LoadJobsResult> {
  try {
    const result = await api.listJobs({
      ...filters,
      limit: 50,
    });
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać listy zadań.',
        ),
        ok: false,
      };
    }
    return { jobs: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export type JobMutationResult =
  | { readonly job: JobResponse; readonly ok: true }
  | { readonly error: string; readonly ok: false };

export async function cancelJob(
  api: JobsClient,
  jobId: string,
): Promise<JobMutationResult> {
  try {
    const result = await api.cancelJob(jobId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(result.error, 'Nie udało się anulować zadania.'),
        ok: false,
      };
    }
    return { job: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function retryJob(
  api: JobsClient,
  jobId: string,
): Promise<JobMutationResult> {
  try {
    const result = await api.retryJob(jobId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(result.error, 'Nie udało się ponowić zadania.'),
        ok: false,
      };
    }
    return { job: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}
