import type {
  BrowserReadySelectionResponse,
  GameResponse,
  JobResponse,
} from '@game-predictor/admin-api-client';

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
