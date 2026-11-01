import type { AdminApiClient } from '@game-predictor/admin-api-client';
import type { SuperGameSeriesModalClient } from '@game-predictor/board-search-ui';
import { nextUndefinedSeriesQuery } from './super-game-series-state';

/** Existing Admin routes used by the shared series view and its modal. */
export type AdminSuperGameSeriesClientSource = Pick<
  AdminApiClient,
  | 'applySymbolCellReviewDecision'
  | 'boardSearchBoardViewUrl'
  | 'getBoardSearchBoardDetail'
  | 'getSuperGameSeriesState'
  | 'listSuperGameSeries'
  | 'listSuperGameSeriesBoards'
  | 'refreshBoardSearchBoardDocument'
  | 'setSuperGameSeriesSuperSymbol'
  | 'symbolImageAssetUrl'
>;

/** Injected read-only clients keep their existing capabilities. */
export function supportsAdminSuperGameSeriesModal(
  api: Partial<AdminSuperGameSeriesClientSource>,
): api is AdminSuperGameSeriesClientSource {
  return [
    api.applySymbolCellReviewDecision,
    api.boardSearchBoardViewUrl,
    api.getBoardSearchBoardDetail,
    api.getSuperGameSeriesState,
    api.listSuperGameSeries,
    api.listSuperGameSeriesBoards,
    api.refreshBoardSearchBoardDocument,
    api.setSuperGameSeriesSuperSymbol,
    api.symbolImageAssetUrl,
  ].every((method) => typeof method === 'function');
}

export function createAdminSuperGameSeriesClient(
  api: AdminSuperGameSeriesClientSource,
): SuperGameSeriesModalClient {
  return {
    applySymbolCellReviewDecision: (...args) =>
      api.applySymbolCellReviewDecision(...args),
    boardSearchBoardViewUrl: (...args) => api.boardSearchBoardViewUrl(...args),
    getBoardSearchBoardDetail: (...args) =>
      api.getBoardSearchBoardDetail(...args),
    getSuperGameSeriesState: (...args) => api.getSuperGameSeriesState(...args),
    listNextUndefinedSuperGameSeries: (gameId, query) =>
      api.listSuperGameSeries(
        gameId,
        nextUndefinedSeriesQuery(query.filters, query.afterTrigger),
      ),
    listSuperGameSeriesBoards: (...args) =>
      api.listSuperGameSeriesBoards(...args),
    refreshBoardSearchBoardDocument: (...args) =>
      api.refreshBoardSearchBoardDocument(...args),
    setSuperGameSeriesSuperSymbol: (...args) =>
      api.setSuperGameSeriesSuperSymbol(...args),
    symbolImageAssetUrl: (...args) => api.symbolImageAssetUrl(...args),
  };
}
