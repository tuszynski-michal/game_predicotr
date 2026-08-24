import type { RemoteManualSelectionSessionResponse } from '@game-predictor/admin-api-client';

export const REMOTE_SESSION_LIST_POLL_MS = 30_000;
export const REMOTE_SESSION_MONITOR_POLL_MS = 10_000;
export const REMOTE_SESSION_LIST_LIMIT = 10;
export const REMOTE_SESSION_FETCH_LIMIT = 100;

export type RemoteManualSelectionSessionFilter = 'active' | 'completed';

export function newestRemoteManualSelectionSessions(
  sessions: readonly RemoteManualSelectionSessionResponse[],
  limit = REMOTE_SESSION_LIST_LIMIT,
): readonly RemoteManualSelectionSessionResponse[] {
  return [...sessions]
    .sort((left, right) => {
      const byCreatedAt = right.createdAt.localeCompare(left.createdAt);
      return byCreatedAt !== 0
        ? byCreatedAt
        : right.sessionId.localeCompare(left.sessionId);
    })
    .slice(0, Math.max(0, limit));
}

export function activeRemoteManualSelectionSessions(
  sessions: readonly RemoteManualSelectionSessionResponse[],
): readonly RemoteManualSelectionSessionResponse[] {
  return sessions.filter((session) => session.status === 'active');
}

export function filteredRemoteManualSelectionSessions(
  sessions: readonly RemoteManualSelectionSessionResponse[],
  filter: RemoteManualSelectionSessionFilter,
  limit = REMOTE_SESSION_LIST_LIMIT,
): readonly RemoteManualSelectionSessionResponse[] {
  const matching = sessions.filter((session) =>
    filter === 'active'
      ? session.status === 'active' || session.status === 'draft'
      : session.status === 'completed' ||
        session.status === 'expired' ||
        session.status === 'revoked',
  );
  return newestRemoteManualSelectionSessions(matching, limit);
}

export function selectVisibleRemoteManualSelectionSessionId(
  sessions: readonly RemoteManualSelectionSessionResponse[],
  current: string,
): string {
  return sessions.some((session) => session.sessionId === current)
    ? current
    : (sessions[0]?.sessionId ?? '');
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
