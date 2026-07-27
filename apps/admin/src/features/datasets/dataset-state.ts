import type {
  DatasetVersionResponse,
  RulesVersionResponse,
} from '@game-predictor/admin-api-client';

export const DEFAULT_DATASET_SEED = '71401';

export function publishedRulesVersions(
  versions: readonly RulesVersionResponse[],
): readonly RulesVersionResponse[] {
  return versions.filter((version) => version.status === 'published');
}

export function validateDatasetSeed(
  value: string,
):
  | { readonly error: string; readonly valid: false }
  | { readonly valid: true; readonly value: number } {
  if (!/^\d+$/.test(value)) {
    return { error: 'Seed musi być liczbą całkowitą.', valid: false };
  }
  const seed = Number(value);
  if (!Number.isSafeInteger(seed) || seed < 0 || seed > 2_147_483_647) {
    return {
      error: 'Seed musi mieścić się w zakresie 0–2147483647.',
      valid: false,
    };
  }
  return { valid: true, value: seed };
}

export function upsertDatasetVersion(
  current: readonly DatasetVersionResponse[],
  dataset: DatasetVersionResponse,
): readonly DatasetVersionResponse[] {
  return [...current.filter((item) => item.id !== dataset.id), dataset].sort(
    (left, right) =>
      right.version - left.version || left.id.localeCompare(right.id),
  );
}
