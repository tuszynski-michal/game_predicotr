import type {
  AdminApiClient,
  ApproximateWinResponse,
  BoardSearchBoardDetailResponse,
  BoardSearchBoardCellResponse,
  BoardSearchSharePublicBoardDetailResponse,
  BoardSearchSharePublicCellResponse,
  BoardSearchShareCellCorrectionRequest,
  BoardSearchShareCellCorrectionResponse,
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

export type BoardSearchModalDetail =
  BoardSearchBoardDetailResponse | BoardSearchSharePublicBoardDetailResponse;
export type BoardSearchEditableCell =
  BoardSearchBoardCellResponse | BoardSearchSharePublicCellResponse;
export type BoardSearchCorrectionContext = {
  readonly startSequenceNumber: number;
  readonly spinCount?: number;
  readonly stakeGrosze?: number;
};

/**
 * Board search reads and optional writes. The Admin passes its generated
 * client directly; the online share adapter (Reviewer, D-492) implements the
 * same members over its proxy.
 *
 * Correction has separate optional ports for local identity and public position.
 * Without mutations the section hides correction; stale-reading refresh is local.
 * Without the full-photo
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
  ) => BoardSearchApiResult<BoardSearchModalDetail>;
  readonly correctBoardSearchCell?: (
    gameId: string,
    sequenceNumber: number,
    cellIndex: number,
    request: Omit<
      BoardSearchShareCellCorrectionRequest,
      'operationId' | 'searchContextId'
    >,
  ) => BoardSearchApiResult<BoardSearchShareCellCorrectionResponse>;
  readonly hasPendingBoardSearchCell?: (
    gameId: string,
    sequenceNumber: number,
  ) => boolean;
  readonly retryBoardSearchCell?: (
    gameId: string,
    sequenceNumber: number,
  ) => BoardSearchApiResult<BoardSearchShareCellCorrectionResponse>;
  readonly listSymbols: (
    gameId: string,
  ) => BoardSearchApiResult<SymbolResponse[]>;
  readonly searchGameBoards: (
    gameId: string,
    options: SearchGameBoardsOptions,
  ) => BoardSearchApiResult<BoardSearchResponse>;
  readonly symbolImageAssetUrl: (gameId: string, symbolId: string) => string;
  /**
   * Online share only (D-487): tells the link's owner which stake the
   * recipient views a calculated range at; `null` is the base stake.
   */
  readonly recordBoardSearchApproximateWinStake?: (
    gameId: string,
    options: {
      readonly spinCount: number;
      readonly startSequenceNumber: number;
      readonly stakeGrosze: number | null;
    },
  ) => BoardSearchApiResult<undefined>;
} & Partial<
  Pick<
    AdminApiClient,
    | 'applySymbolCellReviewDecision'
    | 'getOperationalImageReviewItem'
    | 'operationalImageReviewBoardAssetUrl'
    | 'refreshBoardSearchBoardDocument'
  >
>;
