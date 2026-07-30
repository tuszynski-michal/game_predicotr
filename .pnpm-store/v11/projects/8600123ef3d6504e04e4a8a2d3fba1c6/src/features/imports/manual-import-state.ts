import type {
  JobResponse,
  LayoutImportIntegrityCheckCode,
  LayoutImportIntegrityCheckStatus,
  LayoutImportIntegrityReportResponse,
  LayoutImportValidateJobPayload,
  LayoutImportNormalizedRowResponse,
  ImportJobPayload,
  RulesVersionResponse,
} from '@game-predictor/admin-api-client';

const CHECK_LABELS: Readonly<Record<LayoutImportIntegrityCheckCode, string>> = {
  NORMALIZED_ROW_COUNT_MISMATCH: 'Zgodność liczby wierszy stagingu',
  NO_VALID_IMPORT_ROWS: 'Obecność poprawnych layoutów',
  INVALID_IMPORT_ROW: 'Błędne wiersze importu',
  MISSING_SEQUENCE_NUMBER: 'Luki sequence_number',
  DUPLICATE_SEQUENCE_NUMBER: 'Duplikaty sequence_number',
  DUPLICATE_SIGNATURE: 'Duplikaty treści layoutu',
};

const CHECK_STATUS_LABELS: Readonly<
  Record<LayoutImportIntegrityCheckStatus, string>
> = {
  passed: 'OK',
  warning: 'Ostrzeżenie — publikacja dozwolona',
  blocking: 'Blokada publikacji',
};

export function isLayoutImportValidation(
  job: JobResponse,
): job is JobResponse & {
  readonly inputPayload: LayoutImportValidateJobPayload;
  readonly jobType: 'validate';
} {
  return (
    job.jobType === 'validate' &&
    'validationKind' in job.inputPayload &&
    job.inputPayload.validationKind === 'layout_import'
  );
}

export function isLayoutFileImport(job: JobResponse): job is JobResponse & {
  readonly inputPayload: ImportJobPayload;
  readonly jobType: 'import';
} {
  return (
    job.jobType === 'import' &&
    'importKind' in job.inputPayload &&
    job.inputPayload.importKind === 'layout_file'
  );
}

export function layoutImportValidationIds(
  job: JobResponse,
): { readonly importJobId: string; readonly rulesVersionId: string } | null {
  if (!isLayoutImportValidation(job)) return null;
  return {
    importJobId: job.inputPayload.importJobId,
    rulesVersionId: job.inputPayload.rulesVersionId,
  };
}

export function layoutImportSourcePath(job: JobResponse): string | null {
  if (!isLayoutFileImport(job)) return null;
  return job.inputPayload.sourcePath;
}

export function completedLayoutImportValidations(
  jobs: readonly JobResponse[],
): readonly JobResponse[] {
  return jobs.filter(
    (job) => job.status === 'completed' && isLayoutImportValidation(job),
  );
}

export function completedLayoutFileImports(
  jobs: readonly JobResponse[],
  gameId: string | null,
): readonly JobResponse[] {
  return jobs.filter(
    (job) =>
      job.status === 'completed' &&
      isLayoutFileImport(job) &&
      (gameId === null || job.gameId === gameId),
  );
}

export function publishedRulesForGame(
  versions: readonly RulesVersionResponse[],
): readonly RulesVersionResponse[] {
  return versions.filter((version) => version.status === 'published');
}

export function layoutImportCheckLabel(
  code: LayoutImportIntegrityCheckCode,
): string {
  return CHECK_LABELS[code];
}

export function layoutImportCheckStatusLabel(
  status: LayoutImportIntegrityCheckStatus,
): string {
  return CHECK_STATUS_LABELS[status];
}

export function formatBoundedSample(
  values: readonly number[],
  truncated: boolean,
): string {
  if (values.length === 0) return 'brak';
  return `${values.join(', ')}${truncated ? ' … (próbka obcięta)' : ''}`;
}

export function validateImportSourcePath(
  value: string,
):
  | { readonly error: string; readonly valid: false }
  | { readonly valid: true; readonly value: string } {
  const normalized = value.trim();
  if (normalized.length === 0) {
    return { error: 'Podaj względną ścieżkę pliku importu.', valid: false };
  }
  const segments = normalized.split('/');
  if (
    normalized.includes('\\') ||
    normalized.includes(':') ||
    normalized.startsWith('/') ||
    segments.some(
      (segment) => segment === '' || segment === '.' || segment === '..',
    )
  ) {
    return {
      error: 'Użyj bezpiecznej względnej ścieżki POSIX pod katalogiem imports.',
      valid: false,
    };
  }
  if (!/\.(csv|jsonl)$/i.test(normalized)) {
    return {
      error: 'Plik musi mieć rozszerzenie .csv albo .jsonl.',
      valid: false,
    };
  }
  return { valid: true, value: normalized };
}

export function canConfirmStagingRejection(
  typedImportJobId: string,
  report: LayoutImportIntegrityReportResponse,
): boolean {
  return typedImportJobId.trim() === report.importJobId;
}

export function rowMajorCellLabel(index: number, columns: number): string {
  const row = Math.floor(index / columns) + 1;
  const column = (index % columns) + 1;
  return `Wiersz ${row}, kolumna ${column}`;
}

export function firstPreviewableRow(
  rows: readonly LayoutImportNormalizedRowResponse[],
): LayoutImportNormalizedRowResponse | null {
  return (
    rows.find((row) => row.cells !== null && row.errorCode === null) ?? null
  );
}
