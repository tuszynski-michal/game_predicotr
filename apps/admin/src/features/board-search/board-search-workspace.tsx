'use client';

import {
  BoardSearchWorkspace as SharedBoardSearchWorkspace,
  type BoardSearchDataSource,
} from '@game-predictor/board-search-ui';
import { useMemo } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';

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
}

/**
 * The Admin's board search: the shared section (D-471) fed by the full
 * Admin API client, so cell correction, the stale-reading refresh and the
 * online share panel stay available here and nowhere else.
 */
export function BoardSearchWorkspace({
  apiBaseUrl,
  client,
  gameId,
}: BoardSearchWorkspaceProps) {
  const api = useMemo<AdminBoardSearchClient>(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const shareClient = useMemo<BoardSearchShareClient | null>(
    () =>
      api.createBoardSearchShareSession !== undefined &&
      api.listBoardSearchShareSessions !== undefined &&
      api.revokeBoardSearchShareSession !== undefined
        ? {
            createBoardSearchShareSession: api.createBoardSearchShareSession,
            listBoardSearchShareSessions: api.listBoardSearchShareSessions,
            revokeBoardSearchShareSession: api.revokeBoardSearchShareSession,
          }
        : null,
    [api],
  );
  return (
    <SharedBoardSearchWorkspace
      client={api}
      gameId={gameId}
      headerActions={
        shareClient === null ? undefined : (
          <BoardSearchSharePanel client={shareClient} gameId={gameId} />
        )
      }
    />
  );
}
