/** Pure helpers of the shared board search gate (D-471). */

export function formatShareTimeLeft(expiresAt: string, nowMs: number): string {
  const leftMs = new Date(expiresAt).getTime() - nowMs;
  if (!Number.isFinite(leftMs) || leftMs <= 0) return '0 min';
  const minutes = Math.ceil(leftMs / 60_000);
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${rest} min`;
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`;
}

const MESSAGES: Readonly<Record<string, string>> = {
  BOARD_SEARCH_SHARE_CODE_INVALID: 'Nieprawidłowy kod dostępu.',
  BOARD_SEARCH_SHARE_LOCKED:
    'Link został zablokowany po zbyt wielu błędnych kodach. Poproś o nowy link.',
  BOARD_SEARCH_SHARE_NOT_FOUND: 'Ten link nie istnieje albo wygasł.',
  BOARD_SEARCH_SHARE_REVOKED: 'Ten link został zatrzymany.',
  BOARD_SEARCH_SHARE_DISABLED: 'Udostępnianie jest teraz wyłączone.',
  BOARD_SEARCH_SHARE_ROUTE_DISABLED: 'Udostępnianie jest teraz wyłączone.',
  BOARD_SEARCH_SHARE_RATE_LIMITED:
    'Zbyt wiele prób. Odczekaj chwilę i spróbuj ponownie.',
};

export function shareErrorMessage(body: unknown): string {
  if (typeof body === 'object' && body !== null && 'code' in body) {
    const code = (body as { readonly code: unknown }).code;
    if (typeof code === 'string' && MESSAGES[code] !== undefined)
      return MESSAGES[code];
  }
  return 'Nie udało się otworzyć wyszukiwarki. Spróbuj ponownie.';
}
