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

export function jobErrorSummary(job: JobResponse, limit = 140): string | null {
  if (job.error === null) return null;
  const summary = `${job.error.code}: ${job.error.message}`;
  if (summary.length <= limit) return summary;
  return `${summary.slice(0, Math.max(0, limit - 1)).trimEnd()}…`;
}

export function jobStageLabel(stage: string | null): string {
  if (stage === null) return 'Etap nie został jeszcze rozpoczęty';
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

export function formatImageThroughput(filesPerMinute: number | null): string {
  if (filesPerMinute === null) return 'Brak pomiaru';
  return `${filesPerMinute.toLocaleString('pl-PL', {
    maximumFractionDigits: 2,
  })} plików/min`;
}

export function formatElapsedSeconds(value: number | null): string {
  if (value === null) return 'Nie rozpoczęto';
  if (value < 60) return `${Math.round(value)} s`;
  const minutes = Math.floor(value / 60);
  const seconds = Math.round(value % 60);
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

export function jobProgressPercent(job: JobResponse): number | null {
  const { current, total } = job.progress;
  if (total === null || total <= 0) return null;
  return Math.min(100, Math.max(0, (current / total) * 100));
}

export function jobProgressLabel(job: JobResponse): string {
  const { current, total } = job.progress;
  return total === null
    ? `${current.toLocaleString('pl-PL')} przetworzonych`
    : `${current.toLocaleString('pl-PL')} / ${total.toLocaleString('pl-PL')}`;
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
