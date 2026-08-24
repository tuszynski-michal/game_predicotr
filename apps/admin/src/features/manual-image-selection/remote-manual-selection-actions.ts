import type {
  AdminApiClient,
  RemoteManualSelectionBaseCapabilityResponse,
  RemoteManualSelectionSessionCreatedResponse,
  RemoteManualSelectionSessionListResponse,
  RemoteManualSelectionSessionMonitorResponse,
  RemoteManualSelectionSessionResponse,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';

export type RemoteManualSelectionHostClient = Pick<
  AdminApiClient,
  | 'createRemoteManualSelectionSession'
  | 'getRemoteManualSelectionSession'
  | 'listRemoteManualSelectionSessions'
  | 'revokeRemoteManualSelectionSession'
  | 'selectRemoteManualSelectionHostBase'
>;

type ActionResult<T> =
  | { readonly data: T; readonly ok: true }
  | { readonly error: string; readonly ok: false };

export async function selectRemoteManualSelectionBase(
  client: RemoteManualSelectionHostClient,
): Promise<ActionResult<RemoteManualSelectionBaseCapabilityResponse>> {
  return call(
    () => client.selectRemoteManualSelectionHostBase(),
    'Nie udało się wybrać folderu bazowego zdalnej selekcji.',
  );
}

export async function createRemoteManualSelectionAccess(
  client: RemoteManualSelectionHostClient,
  input: {
    readonly baseCapability: string;
    readonly label: string;
    readonly lifetimeMinutes: number;
  },
): Promise<ActionResult<RemoteManualSelectionSessionCreatedResponse>> {
  return call(
    () =>
      client.createRemoteManualSelectionSession({
        baseCapability: input.baseCapability,
        label: input.label.trim(),
        lifetimeMinutes: input.lifetimeMinutes,
      }),
    'Nie udało się utworzyć zdalnej sesji.',
  );
}

export async function loadRemoteManualSelectionSessions(
  client: RemoteManualSelectionHostClient,
): Promise<ActionResult<RemoteManualSelectionSessionListResponse>> {
  return call(
    () => client.listRemoteManualSelectionSessions(100),
    'Nie udało się odczytać zdalnych sesji.',
  );
}

export async function loadRemoteManualSelectionMonitor(
  client: RemoteManualSelectionHostClient,
  sessionId: string,
): Promise<ActionResult<RemoteManualSelectionSessionMonitorResponse>> {
  return call(
    () => client.getRemoteManualSelectionSession(sessionId, 100),
    'Nie udało się odświeżyć stanu zdalnej sesji.',
  );
}

export async function revokeRemoteManualSelectionAccess(
  client: RemoteManualSelectionHostClient,
  sessionId: string,
): Promise<ActionResult<RemoteManualSelectionSessionResponse>> {
  return call(
    () => client.revokeRemoteManualSelectionSession(sessionId),
    'Nie udało się zatrzymać wybranej sesji.',
  );
}

async function call<T>(
  request: () => Promise<{
    readonly data?: T;
    readonly error?: unknown;
  }>,
  fallback: string,
): Promise<ActionResult<T>> {
  try {
    const result = await request();
    if (result.error !== undefined || result.data === undefined) {
      return { error: apiErrorMessage(result.error, fallback), ok: false };
    }
    return { data: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}
