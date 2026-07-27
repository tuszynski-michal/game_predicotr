import type {
  AdminApiClient,
  DatasetLayoutPageResponse,
  DatasetValidationReportResponse,
  DatasetVersionResponse,
  MockDatasetCreate,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';

export type DatasetsClient = Pick<
  AdminApiClient,
  | 'generateMockDataset'
  | 'archiveDatasetVersion'
  | 'getDatasetValidationReport'
  | 'listDatasetLayouts'
  | 'listDatasetVersions'
  | 'listGames'
  | 'listRulesVersions'
  | 'listSymbols'
  | 'publishDatasetVersion'
>;

export type GenerateMockDatasetResult =
  | { readonly dataset: DatasetVersionResponse; readonly ok: true }
  | { readonly error: string; readonly ok: false };

export async function generateMockDataset(
  api: DatasetsClient,
  gameId: string,
  rulesVersionId: string,
  seed: number,
): Promise<GenerateMockDatasetResult> {
  try {
    const result = await api.generateMockDataset(gameId, {
      rulesVersionId,
      seed,
    } satisfies MockDatasetCreate);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się wygenerować mock datasetu.',
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

export type GetDatasetValidationReportResult =
  | { readonly ok: true; readonly report: DatasetValidationReportResponse }
  | { readonly error: string; readonly ok: false };

export async function getDatasetValidationReport(
  api: DatasetsClient,
  datasetVersionId: string,
): Promise<GetDatasetValidationReportResult> {
  try {
    const result = await api.getDatasetValidationReport(datasetVersionId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się sprawdzić integralności datasetu.',
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

export type ListDatasetLayoutsResult =
  | { readonly ok: true; readonly page: DatasetLayoutPageResponse }
  | { readonly error: string; readonly ok: false };

export async function listDatasetLayouts(
  api: DatasetsClient,
  datasetVersionId: string,
  afterSequenceNumber: number,
  limit: number,
): Promise<ListDatasetLayoutsResult> {
  try {
    const result = await api.listDatasetLayouts(
      datasetVersionId,
      afterSequenceNumber,
      limit,
    );
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać podglądu layoutów.',
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

export type DatasetTransitionResult =
  | { readonly dataset: DatasetVersionResponse; readonly ok: true }
  | { readonly error: string; readonly ok: false };

export async function publishDataset(
  api: DatasetsClient,
  datasetVersionId: string,
): Promise<DatasetTransitionResult> {
  try {
    const result = await api.publishDatasetVersion(datasetVersionId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się opublikować datasetu.',
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

export async function archiveDataset(
  api: DatasetsClient,
  dataset: DatasetVersionResponse,
): Promise<DatasetTransitionResult> {
  try {
    const result = await api.archiveDatasetVersion(dataset.id);
    if (result.error !== undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się zarchiwizować datasetu.',
        ),
        ok: false,
      };
    }
    return {
      dataset: { ...dataset, status: 'archived' },
      ok: true,
    };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}
