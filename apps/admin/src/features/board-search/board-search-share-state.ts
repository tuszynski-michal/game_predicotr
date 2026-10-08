import type { BoardSearchShareSessionResponse } from '@game-predictor/admin-api-client';

/** Pure state of the Admin share panel (D-471, TASK-0769). */

export const BOARD_SEARCH_SHARE_LIFETIMES = [
  { label: '1 h', minutes: 60 },
  { label: '4 h', minutes: 240 },
  { label: '8 h', minutes: 480 },
  { label: '24 h', minutes: 1440 },
  { label: '48 h', minutes: 2880 },
  { label: '72 h', minutes: 4320 },
] as const;
export const BOARD_SEARCH_SHARE_DEFAULT_LIFETIME_MINUTES = 480;

export type BoardSearchShareGroups = {
  readonly active: readonly BoardSearchShareSessionResponse[];
  readonly ended: readonly BoardSearchShareSessionResponse[];
};

/** Active links first (newest first), then everything that no longer works. */
export function groupBoardSearchShareSessions(
  sessions: readonly BoardSearchShareSessionResponse[],
): BoardSearchShareGroups {
  const byNewest = [...sessions].sort(
    (left, right) =>
      Date.parse(right.createdAt) - Date.parse(left.createdAt) ||
      right.sessionId.localeCompare(left.sessionId),
  );
  return {
    active: byNewest.filter((session) => session.status === 'active'),
    ended: byNewest.filter((session) => session.status !== 'active'),
  };
}

export function boardSearchShareStatusLabel(
  status: BoardSearchShareSessionResponse['status'],
): string {
  switch (status) {
    case 'active':
      return 'Aktywny';
    case 'locked':
      return 'Zablokowany (błędne kody)';
    case 'expired':
      return 'Wygasł';
    case 'revoked':
      return 'Zatrzymany';
  }
}

const SHARE_ERRORS: Readonly<Record<string, string>> = {
  BOARD_SEARCH_SHARE_ACTIVE_LIMIT:
    'Aktywnych może być najwyżej 5 linków. Zatrzymaj jeden z nich.',
  BOARD_SEARCH_SHARE_DISABLED:
    'Udostępnianie online jest wyłączone na tym komputerze (GAME_PREDICTOR_BOARD_SEARCH_SHARE_ENABLED).',
  BOARD_SEARCH_PROJECTION_INCOMPLETE:
    'Wyszukiwarka tej gry nie jest jeszcze gotowa, więc nie ma czego udostępnić.',
  APPROXIMATE_WIN_RULES_NOT_PUBLISHED:
    'Gra nie ma opublikowanych reguł, więc przybliżona wygrana nie zadziała online.',
  REVIEWER_INGRESS_NOT_READY:
    'Nie udało się uruchomić publicznego adresu Reviewera. Sprawdź, czy Reviewer działa, i spróbuj ponownie.',
  REVIEWER_INGRESS_COMMAND_FAILED:
    'Nie udało się uruchomić publicznego adresu Reviewera. Sprawdź, czy Reviewer działa, i spróbuj ponownie.',
  REVIEWER_INGRESS_CONTROLLER_MISSING:
    'Nie udało się uruchomić publicznego adresu Reviewera. Sprawdź, czy Reviewer działa, i spróbuj ponownie.',
  REVIEWER_INGRESS_INVALID_RESPONSE:
    'Nie udało się uruchomić publicznego adresu Reviewera. Sprawdź, czy Reviewer działa, i spróbuj ponownie.',
};

export function boardSearchShareErrorMessage(
  error: unknown,
  fallback: string,
): string {
  if (typeof error === 'object' && error !== null && 'code' in error) {
    const code = (error as { readonly code: unknown }).code;
    const message = (error as { readonly message?: unknown }).message;
    if (typeof code === 'string') {
      const known = SHARE_ERRORS[code];
      if (known !== undefined) return known;
      if (typeof message === 'string') return `${message} (${code})`;
    }
  }
  return fallback;
}

export function formatBoardSearchShareDate(value: string | null): string {
  if (value === null) return '—';
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return '—';
  return date.toLocaleString('pl-PL', {
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    month: '2-digit',
  });
}
