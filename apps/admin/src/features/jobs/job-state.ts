import type {
  JobResponse,
  JobStatus,
  JobType,
} from '@game-predictor/admin-api-client';

const JOB_STATUS_LABELS: Readonly<Record<JobStatus, string>> = {
  created: 'Oczekuje',
  processing: 'W toku',
  waiting_for_review: 'Wymaga review',
  completed: 'Ukończone',
  failed: 'Błąd',
  cancelled: 'Anulowane',
};

const JOB_TYPE_LABELS: Readonly<Record<JobType, string>> = {
  import: 'Import',
  validate: 'Walidacja',
  payout: 'Obliczanie payoutów',
  snapshot: 'Snapshot SQLite',
  android_build: 'Build APK',
  symbol_training: 'Trening modelu symboli',
  image_selection: 'Selekcja zdjęć',
  semi_automatic_image_selection: 'Półautomatyczna selekcja zdjęć',
  image_symbol_reinference: 'Przeliczenie oczekujących symboli',
  image_grid_reinference: 'Przeliczenie oczekującej siatki',
  image_symbol_review_bulk: 'Masowa weryfikacja symboli',
  image_symbol_review_backfill: 'Przygotowanie weryfikacji symboli',
  image_geometry_rollout_backfill: 'Walidacja geometrii wirtualnej',
  storage_gc: 'Bezpieczne czyszczenie pamięci',
  storage_inventory: 'Pomiar zajętości pamięci',
  storage_pipeline_compaction: 'Kompakcja danych pipeline’u',
};

export const JOB_STATUS_OPTIONS = Object.keys(
  JOB_STATUS_LABELS,
) as readonly JobStatus[];

export const JOB_TYPE_OPTIONS = Object.keys(
  JOB_TYPE_LABELS,
) as readonly JobType[];

export interface JobFilters {
  readonly status?: JobStatus;
  readonly jobType?: JobType;
}

export function jobStatusLabel(status: JobStatus): string {
  return JOB_STATUS_LABELS[status];
}

export function jobTypeLabel(jobType: JobType): string {
  return JOB_TYPE_LABELS[jobType];
}

export function jobWorkflowLabel(job: JobResponse): string {
  if (isImageImportJob(job)) {
    const stage = job.progress.stage;
    if (stage?.startsWith('image_source:') === true) {
      return 'Ładowanie zdjęć';
    }
    if (
      stage?.endsWith('board_detection') === true ||
      stage?.endsWith('board_cell_geometry') === true ||
      stage?.endsWith('board_crops') === true
    ) {
      return 'Wyznaczanie siatki i cięcie plansz';
    }
    if (stage?.endsWith('symbol_inference') === true) {
      return 'Rozpoznawanie symboli';
    }
    if (stage?.endsWith('sequence_ocr') === true) {
      return 'Przypisywanie numerów plansz';
    }
    if (stage?.endsWith('manual_review') === true) {
      return 'Przygotowanie plansz do zatwierdzenia';
    }
    return 'Tworzenie plansz i symboli';
  }
  if (
    job.jobType === 'validate' &&
    'validationKind' in job.inputPayload &&
    job.inputPayload.validationKind === 'page_geometry_preflight'
  ) {
    return 'Tworzenie geometrii siatek';
  }
  if (job.jobType === 'image_grid_reinference') {
    return 'Ponowne cięcie plansz';
  }
  if (job.jobType === 'image_symbol_reinference') {
    return 'Ponowne rozpoznawanie symboli';
  }
  if (job.jobType === 'image_symbol_review_bulk') {
    return 'Masowe zatwierdzanie i korekta symboli';
  }
  if (job.jobType === 'image_selection') return 'Wybór zdjęć';
  return jobTypeLabel(job.jobType);
}

export function jobContextLabel(job: JobResponse): string {
  if (job.gameId !== null) return `Gra ${job.gameId}`;
  if ('mobileReleaseId' in job.inputPayload) {
    return `Wydanie ${job.inputPayload.mobileReleaseId}`;
  }
  if ('datasetVersionId' in job.inputPayload) {
    return `Dataset ${job.inputPayload.datasetVersionId}`;
  }
  return 'Proces globalny';
}

export function jobSourceRangeLabel(job: JobResponse): string | null {
  const sourceDisplayName =
    'sourceDisplayName' in job.inputPayload &&
    typeof job.inputPayload.sourceDisplayName === 'string'
      ? job.inputPayload.sourceDisplayName
      : 'sourceDirectory' in job.inputPayload &&
          typeof job.inputPayload.sourceDirectory === 'string'
        ? (job.inputPayload.sourceDirectory.split(/[\\/]/).at(-1) ?? null)
        : null;
  if (sourceDisplayName === null) return null;
  const match = /^\s*(\d+)\s*[-–]\s*(\d+)(?:\s|$)/.exec(sourceDisplayName);
  if (match === null) return null;
  const start = Number(match[1]);
  const end = Number(match[2]);
  if (
    !Number.isSafeInteger(start) ||
    !Number.isSafeInteger(end) ||
    start < 1 ||
    end < start
  ) {
    return null;
  }
  return `Zakres ${start}–${end}`;
}

export function jobErrorSummary(job: JobResponse, limit = 140): string | null {
  if (job.error === null) return null;
  const summary = `${job.error.code}: ${job.error.message}`;
  if (summary.length <= limit) return summary;
  return `${summary.slice(0, Math.max(0, limit - 1)).trimEnd()}…`;
}

export function jobStageLabel(
  stage: string | null,
  inputPayload?: JobResponse['inputPayload'],
): string {
  if (stage === null) return 'Etap nie został jeszcze rozpoczęty';
  if (
    stage.endsWith('sequence_ocr') &&
    inputPayload !== undefined &&
    'schemaVersion' in inputPayload &&
    inputPayload.schemaVersion === 5
  ) {
    return 'Przypisanie numerów z nazwy pliku — OCR pominięty';
  }
  return stage.replaceAll('_', ' ');
}

export function isActiveJob(job: JobResponse): boolean {
  return job.status === 'created' || job.status === 'processing';
}

export function canCancelJob(job: JobResponse): boolean {
  return (
    job.cancelRequestedAt === null &&
    (job.status === 'created' ||
      job.status === 'processing' ||
      job.status === 'waiting_for_review')
  );
}

export function canDeleteImageSelectionJob(job: JobResponse): boolean {
  return job.jobType === 'image_selection' && job.status === 'cancelled';
}

export function canRetryJob(job: JobResponse): boolean {
  return job.status === 'failed' || job.status === 'waiting_for_review';
}

export function isImageImportJob(job: JobResponse): boolean {
  return (
    job.jobType === 'import' &&
    'importKind' in job.inputPayload &&
    job.inputPayload.importKind === 'image_directory'
  );
}

export interface ImageImportAutomationTiming {
  readonly completedAt: string;
  readonly durationSeconds: number | null;
}

export function imageImportAutomationTiming(
  job: JobResponse,
): ImageImportAutomationTiming | null {
  if (
    !isImageImportJob(job) ||
    job.progress.stage?.startsWith('image_pipeline:') !== true
  ) {
    return null;
  }
  const completedAt =
    job.status === 'waiting_for_review'
      ? job.updatedAt
      : job.status === 'completed'
        ? job.finishedAt
        : null;
  if (completedAt === null) return null;

  const completed = new Date(completedAt);
  if (Number.isNaN(completed.valueOf())) return null;
  if (job.startedAt === null) {
    return { completedAt, durationSeconds: null };
  }
  const started = new Date(job.startedAt);
  return {
    completedAt,
    durationSeconds: Number.isNaN(started.valueOf())
      ? null
      : Math.max(0, (completed.valueOf() - started.valueOf()) / 1000),
  };
}

export function formatImageThroughput(filesPerMinute: number | null): string {
  if (filesPerMinute === null) return 'Brak pomiaru';
  return `${filesPerMinute.toLocaleString('pl-PL', {
    maximumFractionDigits: 2,
  })} plików/min`;
}

export function formatElapsedSeconds(value: number | null): string {
  if (value === null) return 'Nie rozpoczęto';
  const rounded = Math.max(0, Math.round(value));
  if (rounded < 60) return `${rounded} s`;
  const hours = Math.floor(rounded / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  const seconds = rounded % 60;
  if (hours > 0) return `${hours} godz. ${minutes} min ${seconds} s`;
  return `${minutes} min ${seconds} s`;
}

export function formatStorageBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  const units = ['KB', 'MB', 'GB', 'TB'] as const;
  let amount = value / 1024;
  let unitIndex = 0;
  while (amount >= 1024 && unitIndex < units.length - 1) {
    amount /= 1024;
    unitIndex += 1;
  }
  return `${amount.toLocaleString('pl-PL', {
    maximumFractionDigits: 1,
  })} ${units[unitIndex]}`;
}

export interface JobProgressPresentation {
  readonly current: number;
  readonly total: number | null;
  readonly label: string;
}

export function jobProgressPresentation(
  job: JobResponse,
): JobProgressPresentation {
  const { current, stage, total } = job.progress;
  const isTwoPhaseImageImport =
    isImageImportJob(job) &&
    total !== null &&
    total > 0 &&
    total % 2 === 0 &&
    (stage?.startsWith('image_source:') === true ||
      stage?.startsWith('image_pipeline:') === true);

  if (isTwoPhaseImageImport) {
    const imageTotal = total / 2;
    const pipelinePhase = stage?.startsWith('image_pipeline:') === true;
    const imageCurrent = Math.min(
      imageTotal,
      Math.max(0, pipelinePhase ? current - imageTotal : current),
    );
    const phase = pipelinePhase ? 'Pipeline' : 'Oryginały';
    return {
      current: imageCurrent,
      total: imageTotal,
      label: `${phase}: ${imageCurrent.toLocaleString('pl-PL')} / ${imageTotal.toLocaleString('pl-PL')} zdjęć`,
    };
  }

  return {
    current,
    total,
    label:
      total === null
        ? `${current.toLocaleString('pl-PL')} przetworzonych`
        : `${current.toLocaleString('pl-PL')} / ${total.toLocaleString('pl-PL')}`,
  };
}

export function jobProgressPercent(job: JobResponse): number | null {
  const { current, total } = jobProgressPresentation(job);
  if (total === null || total <= 0) return null;
  return Math.min(100, Math.max(0, (current / total) * 100));
}

export function jobProgressLabel(job: JobResponse): string {
  return jobProgressPresentation(job).label;
}

export function replaceJob(
  jobs: readonly JobResponse[],
  updated: JobResponse,
): readonly JobResponse[] {
  return jobs.map((job) => (job.id === updated.id ? updated : job));
}

export function formatJobTimestamp(value: string | null): string {
  if (value === null) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) return 'Nieprawidłowa data';
  return new Intl.DateTimeFormat('pl-PL', {
    dateStyle: 'short',
    timeStyle: 'medium',
  }).format(parsed);
}
