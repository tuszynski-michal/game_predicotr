import {
  createAdminApiClient,
  type AdminApiClient,
} from '@game-predictor/admin-api-client';

import { resolveAdminApiBaseUrl } from '@/config/admin-api';

export function createConfiguredAdminApiClient(
  configuredBaseUrl: string | undefined,
  fetchImplementation?: typeof globalThis.fetch,
): AdminApiClient {
  return createAdminApiClient({
    baseUrl: resolveAdminApiBaseUrl(configuredBaseUrl),
    ...(fetchImplementation === undefined
      ? {}
      : { fetch: fetchImplementation }),
  });
}
