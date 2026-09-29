'use client';

import type { AdminApiClient } from '@game-predictor/admin-api-client';

import { BoardGeometryCorrectionWorkspace } from '@/features/operational-reviews/board-geometry-correction-workspace';

/**
 * The local Reviewer (port 3001) is the single grid-correction screen of
 * D-462: one queue, one board at a time, no validation of finished grids.
 */
export function LocalReviewerWorkspace({
  api,
  apiBaseUrl,
  gameId,
  importJobId,
}: {
  readonly api: AdminApiClient;
  readonly apiBaseUrl: string;
  readonly gameId: string;
  readonly importJobId: string;
}) {
  return (
    <BoardGeometryCorrectionWorkspace
      api={api}
      apiBaseUrl={apiBaseUrl}
      gameId={gameId}
      importJobId={importJobId}
    />
  );
}
