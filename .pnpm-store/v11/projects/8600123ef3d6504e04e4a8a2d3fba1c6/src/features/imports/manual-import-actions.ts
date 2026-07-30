import type {
  AdminApiClient,
  DatasetVersionResponse,
  JobCreate,
  JobResponse,
  LayoutImportIntegrityReportResponse,
  LayoutImportNormalizedRowPageResponse,
  LayoutImportRowStatus,
  LayoutImportStagingRejectionResponse,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';

export type ManualImportsClient = Pick<
  AdminApiClient,
  | 'createJob'
  | 'getLayoutImportIntegrityReport'
  | 'listGames'
  | 'listJobs'
  | 'listLayoutImportNormalizedRows'
  | 'listRulesVersions'
  | 'listSymbols'
  | 'publishLayoutImportDataset'
  | 'rejectLayoutImportStaging'
>;

type ActionFailure = { readonly error: string; readonly ok: false };

export async function createLayoutImportJob(
  api: ManualImportsClient,
  gameId: string,
  sourcePath: string,
): Promise<{ readonly job: JobResponse; readonly ok: true } | ActionFailure> {
  const body = {
    gameId,
    inputPayload: {
      contractVersion: 1,
      schemaVersion: 1,
      sourcePath,
    },
    jobType: 'import',
  } satisfies JobCreate;
  try {
    const result = await api.createJob(body);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się utworzyć zadania importu.',
        ),
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

export async function createLayoutImportValidation(
  api: ManualImportsClient,
  gameId: string,
  importJobId: string,
  rulesVersionId: string,
): Promise<{ readonly job: JobResponse; readonly ok: true } | ActionFailure> {
  const body = {
    gameId,
    inputPayload: {
      importJobId,
      rulesVersionId,
      schemaVersion: 1,
      validationKind: 'layout_import',
    },
    jobType: 'validate',
  } satisfies JobCreate;
  try {
    const result = await api.createJob(body);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się utworzyć walidacji importu.',
        ),
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

export async function loadLayoutImportReport(
  api: ManualImportsClient,
  validationJobId: string,
): Promise<
  | { readonly ok: true; readonly report: LayoutImportIntegrityReportResponse }
  | ActionFailure
> {
  try {
    const result = await api.getLayoutImportIntegrityReport(validationJobId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać raportu integralności.',
        ),
        ok: false,
      };
    }
    return { ok: true, report: result.data };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function loadLayoutImportRows(
  api: ManualImportsClient,
  validationJobId: string,
  options: {
    readonly afterLineNumber: number;
    readonly errorCode?: string;
    readonly limit: number;
    readonly status: LayoutImportRowStatus;
  },
): Promise<
  | { readonly ok: true; readonly page: LayoutImportNormalizedRowPageResponse }
  | ActionFailure
> {
  try {
    const result = await api.listLayoutImportNormalizedRows(
      validationJobId,
      options,
    );
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać wierszy stagingu.',
        ),
        ok: false,
      };
    }
    return { ok: true, page: result.data };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function rejectLayoutImportStaging(
  api: ManualImportsClient,
  validationJobId: string,
): Promise<
  | {
      readonly ok: true;
      readonly rejection: LayoutImportStagingRejectionResponse;
    }
  | ActionFailure
> {
  try {
    const result = await api.rejectLayoutImportStaging(validationJobId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się odrzucić stagingu importu.',
        ),
        ok: false,
      };
    }
    return { ok: true, rejection: result.data };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function publishLayoutImportDataset(
  api: ManualImportsClient,
  validationJobId: string,
): Promise<
  | {
      readonly dataset: DatasetVersionResponse;
      readonly ok: true;
    }
  | ActionFailure
> {
  try {
    const result = await api.publishLayoutImportDataset(validationJobId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się opublikować datasetu z importu.',
        ),
        ok: false,
      };
    }
    return { dataset: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}
