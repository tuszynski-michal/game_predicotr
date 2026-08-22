import type {
  BrowserReadySelectionResponse,
  GameResponse,
  JobResponse,
} from '@game-predictor/admin-api-client';

const REVIEW_READY_STATUSES = new Set<JobResponse['status']>([
  'waiting_for_review',
  'completed',
]);

export function reviewableGames(
  games: readonly GameResponse[],
): readonly GameResponse[] {
  return games.filter((game) => game.status !== 'archived');
}

export function isImageImport(job: JobResponse): boolean {
  return (
    job.jobType === 'import' &&
    'importKind' in job.inputPayload &&
    job.inputPayload.importKind === 'image_directory'
  );
}

export function reviewReadyImports(
  jobs: readonly JobResponse[],
  gameId: string,
): readonly JobResponse[] {
  return jobs
    .filter(
      (job) =>
        job.gameId === gameId &&
        isImageImport(job) &&
        REVIEW_READY_STATUSES.has(job.status),
    )
    .sort(
      (left, right) =>
        Date.parse(right.createdAt) - Date.parse(left.createdAt) ||
        left.id.localeCompare(right.id),
    );
}

export function selectReviewImportId(
  jobs: readonly JobResponse[],
  gameId: string,
  currentId: string,
): string {
  const available = reviewReadyImports(jobs, gameId);
  return available.some((job) => job.id === currentId)
    ? currentId
    : (available[0]?.id ?? '');
}

export function hasImageImport(
  jobs: readonly JobResponse[],
  gameId: string,
): boolean {
  return jobs.some((job) => job.gameId === gameId && isImageImport(job));
}

export function readyBoardImportStaging(
  selections: readonly BrowserReadySelectionResponse[],
  gameId: string,
): readonly BrowserReadySelectionResponse[] {
  return selections
    .filter(
      (selection) =>
        selection.purpose === 'layout_import' &&
        (selection.gameId === null || selection.gameId === gameId),
    )
    .sort(
      (left, right) =>
        Date.parse(right.createdAt) - Date.parse(left.createdAt) ||
        left.uploadId.localeCompare(right.uploadId),
    );
}

export function reviewJobLabel(job: JobResponse): string {
  const timestamp = new Intl.DateTimeFormat('pl-PL', {
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    month: '2-digit',
    year: '2-digit',
  }).format(new Date(job.createdAt));
  const status = job.status === 'completed' ? 'gotowy' : 'do zatw.';
  const displayName =
    'sourceDisplayName' in job.inputPayload &&
    typeof job.inputPayload.sourceDisplayName === 'string' &&
    job.inputPayload.sourceDisplayName.trim() !== ''
      ? job.inputPayload.sourceDisplayName.trim()
      : 'Import bez nazwy katalogu';
  return `${timestamp} · ${displayName} · ${status}`;
}
