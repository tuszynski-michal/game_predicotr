export function panelErrorMessage(error: unknown, fallback: string): string {
  if (typeof error !== 'object' || error === null || !('code' in error))
    return fallback;
  const code = error.code;
  if (code === 'BOARD_SEARCH_SHARE_ACTIVE_LIMIT')
    return 'Aktywnych może być najwyżej 5 linków wyszukiwarki. Zatrzymaj jeden z nich.';
  if (code === 'BOARD_SEARCH_PANEL_GAME_UNAVAILABLE')
    return 'Wybrana gra nie jest już dostępna. Odśwież listę gier.';
  if (code === 'BOARD_SEARCH_PANEL_GAMES_INVALID')
    return 'Wybierz co najmniej jedną grę, bez powtórzeń.';
  if (code === 'BOARD_SEARCH_SHARE_DISABLED')
    return 'Udostępnianie jest teraz wyłączone.';
  if (
    code === 'BOARD_SEARCH_PANEL_GAME_NOT_READY' &&
    'details' in error &&
    typeof error.details === 'object' &&
    error.details !== null
  ) {
    const details = error.details as Record<string, unknown>;
    const name =
      typeof details.gameName === 'string' ? details.gameName : 'Wybrana gra';
    const reason =
      details.reasonCode === 'APPROXIMATE_WIN_RULES_NOT_PUBLISHED'
        ? 'nie ma opublikowanych reguł'
        : 'nie ma jeszcze gotowych danych wyszukiwarki';
    return `${name}: ${reason}. Przygotuj grę albo odznacz ją przed utworzeniem linku.`;
  }
  return fallback;
}
