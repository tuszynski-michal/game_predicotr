import type {
  AdminApiClient,
  DatasetValidationReportResponse,
  DatasetVersionResponse,
  MockDatasetCreate,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';

export type DatasetsClient = Pick<
  AdminApiClient,
  | 'generateMockDataset'
  | 'getDatasetValidationReport'
  | 'listDatasetVersions'
  | 'listGames'
  | 'listRulesVersions'
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
