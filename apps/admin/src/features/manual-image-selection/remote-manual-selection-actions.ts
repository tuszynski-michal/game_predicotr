import type {
  AdminApiClient,
  RemoteManualSelectionSessionCreatedResponse,
  RemoteManualSelectionSessionListResponse,
  RemoteManualSelectionSessionMonitorResponse,
  RemoteManualSelectionSessionResponse,
  RemoteSelectionRecoveryStatusResponse,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';
import { REMOTE_SESSION_FETCH_LIMIT } from './remote-manual-selection-state.ts';

export type RemoteManualSelectionHostClient = Pick<
  AdminApiClient,
  | 'createRemoteManualSelectionSession'
  | 'getRemoteManualSelectionSession'
  | 'getRemoteManualSelectionRecoveryStatus'
  | 'listRemoteManualSelectionSessions'
  | 'revokeRemoteManualSelectionSession'
  | 'reopenRemoteManualSelectionBatch'
>;

type ActionResult<T> =
  | { readonly data: T; readonly ok: true }
  | { readonly error: string; readonly ok: false };

export async function createRemoteManualSelectionAccess(
  client: RemoteManualSelectionHostClient,
  input: {
    readonly label: string;
    readonly lifetimeMinutes: number;
  },
): Promise<ActionResult<RemoteManualSelectionSessionCreatedResponse>> {
  return call(
    () =>
      client.createRemoteManualSelectionSession({
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
    () => client.listRemoteManualSelectionSessions(REMOTE_SESSION_FETCH_LIMIT),
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

export async function loadRemoteManualSelectionRecoveryStatus(
  client: RemoteManualSelectionHostClient,
  sessionId: string,
  batchId: string,
): Promise<ActionResult<RemoteSelectionRecoveryStatusResponse>> {
  return call(
    () => client.getRemoteManualSelectionRecoveryStatus(sessionId, batchId),
    'Nie udało się odczytać diagnostyki odzyskiwania.',
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

export async function reopenRemoteManualSelectionBatch(
  client: RemoteManualSelectionHostClient,
  input: {
    readonly sessionId: string;
    readonly batchId: string;
    readonly expectedServerRevision: number;
    readonly expectedFinalManifestChecksumSha256: string;
  },
) {
  return call(
    () =>
      client.reopenRemoteManualSelectionBatch(input.sessionId, {
        batchId: input.batchId,
        expectedFinalManifestChecksumSha256:
          input.expectedFinalManifestChecksumSha256,
        expectedServerRevision: input.expectedServerRevision,
      }),
    'Nie udało się ponownie otworzyć zakończonej partii.',
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
