import type {
  AdminApiClient,
  ApproximateWinResponse,
  BoardSearchBoardDetailResponse,
  BoardSearchResponse,
  GetBoardSearchApproximateWinOptions,
  SearchGameBoardsOptions,
  SymbolResponse,
} from '@game-predictor/admin-api-client';

/**
 * A request result as the section reads it: data on success, an error body
 * (`{ code, message }` when the API answered) otherwise. The generated
 * Admin API client returns a superset of this shape.
 */
export type BoardSearchApiResult<T> = Promise<{
  readonly data?: T;
  readonly error?: unknown;
}>;

/**
 * Everything the board search section reads. The Admin passes its generated
 * client directly; the online share adapter (Reviewer, D-471) implements the
 * same members over its proxy.
 *
 * The optional members are Admin-only. Without the mutations the section
 * hides cell correction and the stale-reading refresh; without the full-photo
 * members the carousel has no fallback when the cropped view is unavailable.
 */
export type BoardSearchDataSource = {
  readonly boardSearchBoardViewUrl: (
    gameId: string,
    sequenceNumber: number,
    expectedBoardChecksumSha256: string,
    viewRevision?: string,
  ) => string;
  readonly getBoardSearchApproximateWin: (
    gameId: string,
    options: GetBoardSearchApproximateWinOptions,
  ) => BoardSearchApiResult<ApproximateWinResponse>;
  readonly getBoardSearchBoardDetail: (
    gameId: string,
    sequenceNumber: number,
  ) => BoardSearchApiResult<BoardSearchBoardDetailResponse>;
  readonly listSymbols: (
    gameId: string,
  ) => BoardSearchApiResult<SymbolResponse[]>;
  readonly searchGameBoards: (
    gameId: string,
    options: SearchGameBoardsOptions,
  ) => BoardSearchApiResult<BoardSearchResponse>;
  readonly symbolImageAssetUrl: (gameId: string, symbolId: string) => string;
} & Partial<
  Pick<
    AdminApiClient,
    | 'applySymbolCellReviewDecision'
    | 'archivedBoardSearchAssetUrl'
    | 'getOperationalImageReviewItem'
    | 'operationalImageReviewBoardAssetUrl'
    | 'refreshBoardSearchBoardDocument'
  >
>;
