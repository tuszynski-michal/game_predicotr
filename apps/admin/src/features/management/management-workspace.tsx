'use client';

import { useMemo } from 'react';
import {
  ManagementWorkspace as SharedManagementWorkspace,
  type ManagementClient,
} from '@game-predictor/board-search-ui/management';
import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { ManagementSharePanel } from './management-share-panel';

export type { ManagementClient } from '@game-predictor/board-search-ui/management';

/** Local transport and link administration stay outside the shared panel. */
export function ManagementWorkspace({
  apiBaseUrl,
  client,
  ...props
}: {
  apiBaseUrl: string;
  client?: ManagementClient;
  storageNamespace?: string;
  accessAllowed?: boolean;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  return (
    <SharedManagementWorkspace
      {...props}
      client={api}
      headerActions={
        client === undefined ? (
          <ManagementSharePanel apiBaseUrl={apiBaseUrl} />
        ) : undefined
      }
    />
  );
}
