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
    : '0.10 — geometria strukturalna w cieniu';
}

export function boardCellProcessingJobLabel(job: JobResponse): string {
  const payload = job.inputPayload;
  if (!('importKind' in payload) || payload.importKind !== 'image_directory') {
    return 'brak danych o silniku';
  }
  const snapshot =
    'boardCellProcessing' in payload ? payload.boardCellProcessing : null;
  if (snapshot?.activationVersion === VERIFIED_V19_ACTIVATION_VERSION) {
    return 'v20 — geometria i cropy v19';
  }
  const rollout = 'imageGeometryRollout' in payload ? payload.imageGeometryRollout : null;
  return rollout?.geometryMode === 'structured_shadow'
    ? '0.10 — geometria strukturalna w cieniu'
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
  if (mode === 'verified_v19') {
    return snapshot?.activationVersion === VERIFIED_V19_ACTIVATION_VERSION;
  }
  const rollout = 'imageGeometryRollout' in payload ? payload.imageGeometryRollout : null;
  return rollout?.geometryMode === 'structured_shadow';
}
