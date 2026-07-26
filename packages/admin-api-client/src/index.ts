import { createClient as createGeneratedClient } from './generated/client';
import { getHealth as getGeneratedHealth } from './generated/sdk.gen';

export type { HealthResponse } from './generated/types.gen';

export interface AdminApiClientOptions {
  readonly baseUrl: string;
  readonly fetch?: typeof globalThis.fetch;
}

export function createAdminApiClient(options: AdminApiClientOptions) {
  const client = createGeneratedClient({
    baseUrl: options.baseUrl,
    ...(options.fetch === undefined ? {} : { fetch: options.fetch }),
  });

  return {
    getHealth: () => getGeneratedHealth({ client }),
  } as const;
}

export type AdminApiClient = ReturnType<typeof createAdminApiClient>;
