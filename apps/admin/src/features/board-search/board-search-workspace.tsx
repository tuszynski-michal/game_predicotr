'use client';

import {
  BoardSearchWorkspace as SharedBoardSearchWorkspace,
  type BoardSearchDataSource,
} from '@game-predictor/board-search-ui';
import { useMemo } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';

interface BoardSearchWorkspaceProps {
  readonly apiBaseUrl: string;
  readonly client?: BoardSearchDataSource;
  readonly gameId: string;
}

/**
 * The Admin's board search: the shared section (D-471) fed by the full
 * Admin API client, so cell correction and the stale-reading refresh stay
 * available here and nowhere else.
 */
export function BoardSearchWorkspace({
  apiBaseUrl,
  client,
  gameId,
}: BoardSearchWorkspaceProps) {
  const api = useMemo<BoardSearchDataSource>(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  return <SharedBoardSearchWorkspace client={api} gameId={gameId} />;
}
