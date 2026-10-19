import type {
  SuperGameSeriesBoardsResponse,
  SuperGameSeriesResponse,
  SuperGameStateResponse,
} from '@game-predictor/admin-api-client';

import type { BoardLinesClient } from '../board-search-board-lines-modal';
import type { BoardSearchApiResult } from '../board-search-data-source';
import type {
  SeriesFilters,
  SuperSymbolSaveRequest,
} from './super-game-series-state.ts';

/**
 * What the series view needs from its host (TASK-1058): the boards of the
 * opened series, the compare-and-set super symbol update, the search for the
 * next series without a super symbol, and the board reads of the lines
 * window. The Admin maps its generated client onto it; the online share
 * adapter (Reviewer, D-564) implements it over its proxy.
 */
export type SuperGameSeriesViewClient = BoardLinesClient & {
  readonly listSuperGameSeriesBoards: (
    gameId: string,
    seriesId: string,
  ) => BoardSearchApiResult<SuperGameSeriesBoardsResponse>;
  readonly setSuperGameSeriesSuperSymbol: (
    gameId: string,
    seriesId: string,
    request: SuperSymbolSaveRequest,
  ) => BoardSearchApiResult<SuperGameSeriesResponse>;
  /**
   * Up to two series without a super symbol after `afterTrigger` (`null`:
   * from the first series), in trigger order. The host applies the list
   * filters it supports; `pickNextUndefinedSeries` skips the opened series.
   */
  readonly listNextUndefinedSuperGameSeries: (
    gameId: string,
    query: {
      readonly afterTrigger: number | null;
      readonly filters: SeriesFilters;
    },
  ) => BoardSearchApiResult<{
    readonly items: readonly SuperGameSeriesResponse[];
  }>;
};

/** The view client plus the freshness read a host polls while it is stale. */
export type SuperGameSeriesModalClient = SuperGameSeriesViewClient & {
  readonly getSuperGameSeriesState: (
    gameId: string,
  ) => BoardSearchApiResult<SuperGameStateResponse>;
};
