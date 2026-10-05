'use client';

import {
  BoardSearchWorkspace as SharedBoardSearchWorkspace,
  type BoardSearchDataSource,
} from '@game-predictor/board-search-ui';
import { useMemo } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';

import type { BoardSearchReplayPlan } from './board-search-replay-state';
import { boardSearchReplayHref } from './board-search-replay-state';
import {
  type BoardSearchShareClient,
  BoardSearchSharePanel,
} from './board-search-share-panel';

type AdminBoardSearchClient = BoardSearchDataSource &
  Partial<BoardSearchShareClient>;

interface BoardSearchWorkspaceProps {
  readonly apiBaseUrl: string;
  readonly client?: AdminBoardSearchClient;
  readonly gameId: string;
  /** A share-link query to reproduce (D-472), resolved by the catalog. */
  readonly replay?: BoardSearchReplayPlan | null;
  /** Why a requested replay cannot run (e.g. no earlier search). */
  readonly replayMessage?: string | null;
  readonly onReplayApplied?: (id: string) => void;
}

/** Opens a query log entry through the Admin URL (`?boardSearchReplay=`). */
function openReplay(eventId: string): void {
  window.history.pushState(
    null,
    '',
    boardSearchReplayHref(window.location.href, eventId),
  );
  window.dispatchEvent(new PopStateEvent('popstate'));
}

/**
 * The Admin's board search: the shared section (D-471) fed by the full
 * Admin API client, so cell correction, the stale-reading refresh, the
 * online share panel and query replays stay available here and nowhere else.
 */
export function BoardSearchWorkspace({
  apiBaseUrl,
  client,
  gameId,
  onReplayApplied,
  replay = null,
  replayMessage = null,
}: BoardSearchWorkspaceProps) {
  const api = useMemo<AdminBoardSearchClient>(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const shareClient = useMemo<BoardSearchShareClient | null>(
    () =>
      api.createBoardSearchShareSession !== undefined &&
      api.deleteBoardSearchShareQuery !== undefined &&
      api.listBoardSearchShareQueries !== undefined &&
      api.listBoardSearchShareSessions !== undefined &&
      api.revokeBoardSearchShareSession !== undefined
        ? {
            createBoardSearchShareSession: api.createBoardSearchShareSession,
            deleteBoardSearchShareQuery: api.deleteBoardSearchShareQuery,
            getBoardSearchApproximateWin: api.getBoardSearchApproximateWin,
            listBoardSearchShareQueries: api.listBoardSearchShareQueries,
            listBoardSearchShareSessions: api.listBoardSearchShareSessions,
            listSymbols: api.listSymbols,
            revokeBoardSearchShareSession: api.revokeBoardSearchShareSession,
            symbolImageAssetUrl: api.symbolImageAssetUrl,
            listBoardSearchShareCorrections:
              api.listBoardSearchShareCorrections,
            getBoardSearchShareCorrection: api.getBoardSearchShareCorrection,
            reviewBoardSearchShareCorrection:
              api.reviewBoardSearchShareCorrection,
            getBoardSearchBoardDetail: api.getBoardSearchBoardDetail,
            boardSearchBoardViewUrl: api.boardSearchBoardViewUrl,
            applySymbolCellReviewDecision: api.applySymbolCellReviewDecision,
            refreshBoardSearchBoardDocument:
              api.refreshBoardSearchBoardDocument,
          }
        : null,
    [api],
  );
  return (
    <>
      {replayMessage !== null ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {replayMessage}
        </p>
      ) : null}
      <SharedBoardSearchWorkspace
        client={api}
        gameId={gameId}
        headerActions={
          shareClient === null ? undefined : (
            <BoardSearchSharePanel
              client={shareClient}
              gameId={gameId}
              onReplay={openReplay}
            />
          )
        }
        onReplayApplied={onReplayApplied}
        replay={replay}
      />
    </>
  );
}
