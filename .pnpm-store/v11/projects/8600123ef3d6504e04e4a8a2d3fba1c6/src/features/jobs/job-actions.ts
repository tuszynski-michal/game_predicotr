import type {
  AdminApiClient,
  ImageDiagnosticExportCreationResponse,
  ImageDiagnosticExportResponse,
  ImageJobOperationsResponse,
  ImageStorageInventoryResponse,
  JobResponse,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';
import type { JobFilters } from './job-state.ts';

export type JobsClient = Pick<
  AdminApiClient,
  | 'cancelJob'
  | 'createImageDiagnosticExport'
  | 'downloadImageDiagnosticExport'
  | 'getImageJobOperations'
  | 'getImageStorageInventory'
  | 'listImageDiagnosticExports'
  | 'listJobs'
  | 'retryImageJobFile'
  | 'retryJob'
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

export type ImageJobOperationsResult =
  | { readonly operations: ImageJobOperationsResponse; readonly ok: true }
  | { readonly error: string; readonly ok: false };

export async function loadImageJobOperations(
  api: JobsClient,
  jobId: string,
): Promise<ImageJobOperationsResult> {
  try {
    const result = await api.getImageJobOperations(jobId, 100);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać szczegółów importu zdjęć.',
        ),
        ok: false,
      };
    }
    return { ok: true, operations: result.data };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function retryImageJobFile(
  api: JobsClient,
  jobId: string,
  fileExecutionKey: string,
  expectedStage: string,
): Promise<ImageJobOperationsResult> {
  try {
    const result = await api.retryImageJobFile(
      jobId,
      fileExecutionKey,
      { expectedStage },
      100,
    );
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się ponowić pliku obrazu.',
        ),
        ok: false,
      };
    }
    return { ok: true, operations: result.data };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export type ImageStorageResult =
  | { readonly inventory: ImageStorageInventoryResponse; readonly ok: true }
  | { readonly error: string; readonly ok: false };

export async function loadImageStorageInventory(
  api: JobsClient,
): Promise<ImageStorageResult> {
  try {
    const result = await api.getImageStorageInventory();
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać informacji o magazynie obrazów.',
        ),
        ok: false,
      };
    }
    return { inventory: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export type ImageDiagnosticExportsResult =
  | {
      readonly exports: readonly ImageDiagnosticExportResponse[];
      readonly ok: true;
    }
  | { readonly error: string; readonly ok: false };

export async function loadImageDiagnosticExports(
  api: JobsClient,
  jobId: string,
): Promise<ImageDiagnosticExportsResult> {
  try {
    const result = await api.listImageDiagnosticExports(jobId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać eksportów diagnostycznych.',
        ),
        ok: false,
      };
    }
    return { exports: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export type CreateImageDiagnosticExportResult =
  | {
      readonly creation: ImageDiagnosticExportCreationResponse;
      readonly ok: true;
    }
  | { readonly error: string; readonly ok: false };

export async function createImageDiagnosticExport(
  api: JobsClient,
  jobId: string,
): Promise<CreateImageDiagnosticExportResult> {
  try {
    const result = await api.createImageDiagnosticExport(jobId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się utworzyć eksportu diagnostycznego.',
        ),
        ok: false,
      };
    }
    return { creation: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export type DownloadImageDiagnosticExportResult =
  | { readonly artifact: Blob; readonly ok: true }
  | { readonly error: string; readonly ok: false };

export async function downloadImageDiagnosticExport(
  api: JobsClient,
  jobId: string,
  checksumSha256: string,
): Promise<DownloadImageDiagnosticExportResult> {
  try {
    const result = await api.downloadImageDiagnosticExport(
      jobId,
      checksumSha256,
    );
    if (
      result.error !== undefined ||
      result.data === undefined ||
      !(result.data instanceof Blob)
    ) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać zweryfikowanego eksportu diagnostycznego.',
        ),
        ok: false,
      };
    }
    return { artifact: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}
