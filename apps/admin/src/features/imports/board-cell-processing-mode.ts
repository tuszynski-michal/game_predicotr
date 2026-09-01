import type { JobResponse } from '@game-predictor/admin-api-client';

import type { BoardCellProcessingMode } from './image-folder-import-actions.ts';

export const DEFAULT_BOARD_CELL_PROCESSING_MODE: BoardCellProcessingMode =
  'verified_v19';

export const VERIFIED_V19_ACTIVATION_VERSION =
  'board-cell-processing-v20-verified-v19-v1';

export function boardCellProcessingModeLabel(
  mode: BoardCellProcessingMode,
): string {
  if (mode === 'verified_v19') return 'v20 — zweryfikowana geometria v19';
  if (mode === 'structured_default')
    return 'v0.10 — główny silnik strukturalny';
  return 'v0.10 — historyczny tryb pomiarowy';
}

export function boardCellProcessingJobLabel(job: JobResponse): string {
  const payload = job.inputPayload;
  if (!('importKind' in payload) || payload.importKind !== 'image_directory') {
    return 'brak danych o silniku';
  }
  const rollout =
    'imageGeometryRollout' in payload ? payload.imageGeometryRollout : null;
  if (rollout?.geometryMode === 'structured_shadow') {
    return '0.10 — nowy silnik w cieniu · primary v20/v19';
  }
  if (rollout?.geometryMode === 'structured_default') {
    return 'v0.10 — główny silnik strukturalny · wirtualne cropy';
  }
  const snapshot =
    'boardCellProcessing' in payload ? payload.boardCellProcessing : null;
  if (snapshot?.activationVersion === VERIFIED_V19_ACTIVATION_VERSION) {
    return 'v20 — geometria i cropy v19';
  }
  return 'v18 — tryb historyczny';
}

export function jobMatchesBoardCellProcessingMode(
  job: JobResponse,
  mode: BoardCellProcessingMode,
): boolean {
  const payload = job.inputPayload;
  if (!('importKind' in payload) || payload.importKind !== 'image_directory') {
    return false;
  }
  const rollout =
    'imageGeometryRollout' in payload ? payload.imageGeometryRollout : null;
  if (rollout?.geometryMode === 'structured_shadow') {
    return mode === 'structured_shadow';
  }
  if (rollout?.geometryMode === 'structured_default') {
    return mode === 'structured_default';
  }
  const snapshot =
    'boardCellProcessing' in payload ? payload.boardCellProcessing : null;
  if (mode === 'verified_v19') {
    return snapshot?.activationVersion === VERIFIED_V19_ACTIVATION_VERSION;
  }
  return false;
}
