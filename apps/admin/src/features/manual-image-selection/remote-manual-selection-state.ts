import type { RemoteManualSelectionSessionResponse } from '@game-predictor/admin-api-client';

export const REMOTE_SESSION_LIST_POLL_MS = 30_000;
export const REMOTE_SESSION_MONITOR_POLL_MS = 10_000;

export function activeRemoteManualSelectionSessions(
  sessions: readonly RemoteManualSelectionSessionResponse[],
): readonly RemoteManualSelectionSessionResponse[] {
  return sessions.filter((session) => session.status === 'active');
}

export function selectRemoteManualSelectionSessionId(
  sessions: readonly RemoteManualSelectionSessionResponse[],
  current: string,
): string {
  if (sessions.some((session) => session.sessionId === current)) return current;
  return activeRemoteManualSelectionSessions(sessions)[0]?.sessionId ?? '';
}

export function safeRemoteManualSelectionUrl(
  session: RemoteManualSelectionSessionResponse,
): string | null {
  if (!session.ready || session.reviewUrl === null) return null;
  try {
    const url = new URL(session.reviewUrl);
    return url.protocol === 'https:' &&
      url.hostname.endsWith('.trycloudflare.com') &&
      url.username === '' &&
      url.password === '' &&
      url.pathname === '/manual-selection' &&
      url.searchParams.get('session') === session.sessionId
      ? url.toString()
      : null;
  } catch {
    return null;
  }
}

export function remoteSessionStatusLabel(
  status: RemoteManualSelectionSessionResponse['status'],
): string {
  return {
    active: 'aktywna',
    completed: 'zakończona',
    draft: 'szkic',
    expired: 'wygasła',
    revoked: 'zatrzymana',
  }[status];
}
