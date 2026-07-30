import type {
  DatasetValidationCheckCode,
  DatasetValidationCheckStatus,
  DatasetVersionResponse,
  RulesVersionResponse,
} from '@game-predictor/admin-api-client';

export const DEFAULT_DATASET_SEED = '71401';

const VALIDATION_CHECK_LABELS: Readonly<
  Record<DatasetValidationCheckCode, string>
> = {
  LAYOUT_COUNT_MISMATCH: 'Deklarowana i rzeczywista liczba layoutów',
  MISSING_SEQUENCE_NUMBER: 'Brakujące numery sekwencji',
  OUT_OF_RANGE_SEQUENCE_NUMBER: 'Numery poza zakresem',
  DUPLICATE_SEQUENCE_NUMBER: 'Zduplikowane numery sekwencji',
  INVALID_CELL_COUNT: 'Liczba komórek layoutu',
  FOREIGN_SYMBOL: 'Przynależność symboli do gry',
  SIGNATURE_MISMATCH: 'Zgodność sygnatur z komórkami',
  DUPLICATE_SIGNATURE: 'Duplikaty sygnatur layoutu',
};

const VALIDATION_STATUS_LABELS: Readonly<
  Record<DatasetValidationCheckStatus, string>
> = {
  passed: 'OK',
  warning: 'Ostrzeżenie',
  blocking: 'Blokada',
};

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

export function datasetValidationCheckLabel(
  code: DatasetValidationCheckCode,
): string {
  return VALIDATION_CHECK_LABELS[code];
}

export function datasetValidationStatusLabel(
  status: DatasetValidationCheckStatus,
): string {
  return VALIDATION_STATUS_LABELS[status];
}

export function formatDiagnosticNumbers(values: readonly number[]): string {
  return values.join(', ');
}
