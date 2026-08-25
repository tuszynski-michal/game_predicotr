import type { JobResponse } from '@game-predictor/admin-api-client';

import type { BoardCellProcessingMode } from './image-folder-import-actions.ts';

export const DEFAULT_BOARD_CELL_PROCESSING_MODE: BoardCellProcessingMode =
  'verified_v19';

export const VERIFIED_V19_ACTIVATION_VERSION =
  'board-cell-processing-v20-verified-v19-v1';

export function boardCellProcessingModeLabel(
  mode: BoardCellProcessingMode,
): string {
  return mode === 'verified_v19'
    ? 'v20 — zweryfikowana geometria v19'
    : 'v18 — tryb historyczny';
}

export function boardCellProcessingJobLabel(job: JobResponse): string {
  const payload = job.inputPayload;
  if (!('importKind' in payload) || payload.importKind !== 'image_directory') {
    return 'brak danych o silniku';
  }
  const snapshot =
    'boardCellProcessing' in payload ? payload.boardCellProcessing : null;
  return snapshot?.activationVersion === VERIFIED_V19_ACTIVATION_VERSION
    ? 'v20 — geometria i cropy v19'
    : 'v18 — tryb historyczny';
}

export function jobMatchesBoardCellProcessingMode(
  job: JobResponse,
  mode: BoardCellProcessingMode,
): boolean {
  const payload = job.inputPayload;
  if (!('importKind' in payload) || payload.importKind !== 'image_directory') {
    return false;
  }
  const snapshot =
    'boardCellProcessing' in payload ? payload.boardCellProcessing : null;
  return mode === 'verified_v19'
    ? snapshot?.activationVersion === VERIFIED_V19_ACTIVATION_VERSION
    : snapshot == null;
}
