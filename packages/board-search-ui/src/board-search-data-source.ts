import type { AdminApiClient } from '@game-predictor/admin-api-client';

/**
 * Everything the board search section reads, shaped like the generated Admin
 * API client so the Admin passes its client directly and the online share
 * adapter returns the same `{ data, error }` results.
 *
 * The optional members are Admin-only. Without the mutations the section
 * hides cell correction and the stale-reading refresh; without the full-photo
 * members the carousel has no fallback when the cropped view is unavailable.
 */
export type BoardSearchDataSource = Pick<
  AdminApiClient,
  | 'boardSearchBoardViewUrl'
  | 'getBoardSearchApproximateWin'
  | 'getBoardSearchBoardDetail'
  | 'listSymbols'
  | 'searchGameBoards'
  | 'symbolImageAssetUrl'
> &
  Partial<
    Pick<
      AdminApiClient,
      | 'applySymbolCellReviewDecision'
      | 'archivedBoardSearchAssetUrl'
      | 'getOperationalImageReviewItem'
      | 'operationalImageReviewBoardAssetUrl'
      | 'refreshBoardSearchBoardDocument'
    >
  >;
