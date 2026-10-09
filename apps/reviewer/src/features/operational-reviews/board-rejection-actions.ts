import type {
  AdminApiClient,
  BoardCellGeometryRejectionResponse,
  OperationalImageReviewResolutionResponse,
} from '@game-predictor/admin-api-client';

import {
  boardRejectionCommand,
  slotRejectionCommand,
  type BoardRejectionRequest,
} from './board-rejection-state.ts';
import { runMutation, type MutationOutcome } from './mutation-outcome.ts';

export type BoardRejectionClient = Pick<
  AdminApiClient,
  'rejectPendingBoardCellGeometry' | 'resolveOperationalImageReviewItem'
>;

export interface BoardRejectionScope {
  readonly gameId: string;
  readonly importJobId: string;
}

/** Rejects an open deferred slot (`POST …/board-cell-geometry-pending/{id}/rejection`). */
export function rejectDeferredSlot(
  api: Pick<BoardRejectionClient, 'rejectPendingBoardCellGeometry'>,
  scope: BoardRejectionScope,
  slot: {
    readonly expectedGeometryRevision: number;
    readonly pendingGeometryId: string;
  },
  request: BoardRejectionRequest,
): Promise<MutationOutcome<BoardCellGeometryRejectionResponse>> {
  return runMutation<BoardCellGeometryRejectionResponse>(
    () =>
      api.rejectPendingBoardCellGeometry(
        slot.pendingGeometryId,
        scope,
        slotRejectionCommand(request, slot.expectedGeometryRevision),
      ),
    'Nie udało się odrzucić slotu.',
  );
}

/**
 * Rejects an existing board through the resolution route (`action = rejected`).
 * The canonical owner of a sequence is refused with `BOARD_REJECT_CANONICAL`.
 */
export function rejectReviewItem(
  api: Pick<BoardRejectionClient, 'resolveOperationalImageReviewItem'>,
  scope: BoardRejectionScope,
  board: {
    readonly geometryRevision: number;
    readonly resolutionRevision: number;
    readonly reviewItemId: string;
  },
  request: BoardRejectionRequest,
): Promise<MutationOutcome<OperationalImageReviewResolutionResponse>> {
  return runMutation<OperationalImageReviewResolutionResponse>(
    () =>
      api.resolveOperationalImageReviewItem(
        board.reviewItemId,
        scope,
        boardRejectionCommand(request, board),
      ),
    'Nie udało się odrzucić planszy.',
  );
}
