import type { JobResponse } from '@game-predictor/admin-api-client';

import type { BoardCellProcessingMode } from './image-folder-import-actions.ts';

/**
 * Activation of the removed v20 / verified v19 file-crop engine (D-467,
 * TASK-0790). It is kept only to label historical import jobs.
 */
export const VERIFIED_V19_ACTIVATION_VERSION =
  'board-cell-processing-v20-verified-v19-v1';

/** Selectable engines are virtual only; legacy and shadow were removed. */
export function boardCellProcessingModeLabel(
  mode: BoardCellProcessingMode,
): string {
  if (mode === 'structured_default')
    return 'v0.10 v2 — stabilny silnik strukturalny';
  return 'v0.10 v3 — precyzyjna siatka symboli';
}

export function boardCellProcessingJobLabel(job: JobResponse): string {
  const payload = job.inputPayload;
  if (!('importKind' in payload) || payload.importKind !== 'image_directory') {
    return 'brak danych o silniku';
  }
  const rollout =
    'imageGeometryRollout' in payload ? payload.imageGeometryRollout : null;
  if (rollout?.geometryMode === 'structured_shadow') {
    return '0.10 — nowy silnik w cieniu · primary v20/v19 (usunięty)';
  }
  if (rollout?.geometryMode === 'structured_default') {
    return 'v0.10 v2 — stabilny silnik strukturalny · wirtualne cropy';
  }
  if (rollout?.geometryMode === 'structured_lattice_v3') {
    return 'v0.10 v3 — precyzyjna siatka symboli · wirtualne cropy';
  }
  const snapshot =
    'boardCellProcessing' in payload ? payload.boardCellProcessing : null;
  if (snapshot?.activationVersion === VERIFIED_V19_ACTIVATION_VERSION) {
    return 'v20 — geometria i cropy v19 (usunięty)';
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
  return rollout?.geometryMode === mode;
}
