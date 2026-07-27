import type {
  AdminApiClient,
  DatasetVersionResponse,
  MockDatasetCreate,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';

export type DatasetsClient = Pick<
  AdminApiClient,
  | 'generateMockDataset'
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
