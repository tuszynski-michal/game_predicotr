/** A capability identity never changes when another tab replaces its cookie. */
export const MANAGEMENT_SESSION_ID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
export const managementStorageNamespace = (sessionId: string) =>
  `public:${sessionId}`;

const MESSAGES: Record<string, string> = {
  MANAGEMENT_CODE_INVALID: 'Nieprawidłowy kod dostępu.',
  MANAGEMENT_CODE_LOCKED:
    'Link zablokowany po pięciu błędnych kodach. Poproś o nowy link.',
  MANAGEMENT_SHARE_DISABLED:
    'Udostępnianie panelu zostało wyłączone. Poproś o nowy dostęp.',
  MANAGEMENT_SESSION_NOT_FOUND: 'Ten link nie istnieje albo wygasł.',
  MANAGEMENT_TOKEN_INVALID:
    'Dostęp został zakończony lub przeglądarka używa innego linku.',
  MANAGEMENT_SESSION_ID_MISMATCH:
    'Przeglądarka używa innego linku. Otwórz ponownie swój link i podaj kod.',
};
export function managementAccessMessage(error: unknown): string {
  if (
    error &&
    typeof error === 'object' &&
    'code' in error &&
    typeof error.code === 'string'
  )
    return (
      MESSAGES[error.code] ??
      'Nie udało się otworzyć panelu. Sprawdź kod i dostępność aplikacji.'
    );
  return 'Nie udało się połączyć z aplikacją. Spróbuj ponownie.';
}
