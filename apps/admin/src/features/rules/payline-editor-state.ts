import type { PaylineResponse } from '@game-predictor/admin-api-client';

const STABLE_CODE_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/;
const MAX_DISPLAY_ORDER = 2_147_483_647;

export interface PaylineDraft {
  readonly code: string;
  readonly displayOrder: string;
  readonly isActive: boolean;
  readonly name: string;
  readonly rowPath: readonly (number | null)[];
}

export interface ValidatedPaylineDraft {
  readonly code: string;
  readonly displayOrder: number;
  readonly isActive: boolean;
  readonly name: string;
  readonly rowPath: readonly number[];
}

export type PaylineDraftValidation =
  | { readonly valid: true; readonly value: ValidatedPaylineDraft }
  | { readonly error: string; readonly valid: false };

export function emptyPaylineDraft(columns: number): PaylineDraft {
  return {
    code: '',
    displayOrder: '0',
    isActive: true,
    name: '',
    rowPath: Array.from({ length: columns }, () => null),
  };
}

export function paylineToDraft(payline: PaylineResponse): PaylineDraft {
  return {
    code: payline.code,
    displayOrder: String(payline.displayOrder),
    isActive: payline.isActive,
    name: payline.name,
    rowPath: payline.rowPath,
  };
}

export function selectPaylineCell(
  rowPath: readonly (number | null)[],
  column: number,
  row: number,
): readonly (number | null)[] {
  return rowPath.map((current, index) => (index === column ? row : current));
}

export function isPaylineComplete(
  rowPath: readonly (number | null)[],
  columns: number,
): boolean {
  return rowPath.length === columns && rowPath.every((row) => row !== null);
}

export function validatePaylineDraft(
  draft: PaylineDraft,
  dimensions: {
    readonly rows: number;
    readonly columns: number;
  },
): PaylineDraftValidation {
  const { rows, columns } = dimensions;
  const code = draft.code.trim();
  const name = draft.name.trim();
  if (!STABLE_CODE_PATTERN.test(code)) {
    return {
      error:
        'Kod musi mieć 1–64 znaki: litery, cyfry, myślnik lub podkreślenie.',
      valid: false,
    };
  }
  if (!name || name.length > 200) {
    return {
      error: 'Nazwa musi zawierać od 1 do 200 znaków.',
      valid: false,
    };
  }
  const displayOrder = parseInteger(draft.displayOrder);
  if (
    displayOrder === null ||
    displayOrder < 0 ||
    displayOrder > MAX_DISPLAY_ORDER
  ) {
    return {
      error: 'Kolejność musi być liczbą całkowitą od 0 do 2147483647.',
      valid: false,
    };
  }
  if (!isPaylineComplete(draft.rowPath, columns)) {
    return {
      error: 'Wybierz dokładnie jedną komórkę w każdej kolumnie.',
      valid: false,
    };
  }
  const rowPath = draft.rowPath as readonly number[];
  if (rowPath.some((row) => row < 0 || row >= rows)) {
    return {
      error: 'Wybrany wzór wskazuje wiersz spoza siatki.',
      valid: false,
    };
  }
  return {
    valid: true,
    value: {
      code,
      displayOrder,
      isActive: draft.isActive,
      name,
      rowPath,
    },
  };
}

export function upsertPayline(
  paylines: readonly PaylineResponse[],
  saved: PaylineResponse,
): readonly PaylineResponse[] {
  const updated = paylines.some((item) => item.id === saved.id)
    ? paylines.map((item) => (item.id === saved.id ? saved : item))
    : [...paylines, saved];
  return [...updated].sort(
    (left, right) =>
      left.displayOrder - right.displayOrder ||
      left.code.localeCompare(right.code) ||
      left.id.localeCompare(right.id),
  );
}

export function markPaylineArchived(
  paylines: readonly PaylineResponse[],
  paylineId: string,
): readonly PaylineResponse[] {
  return paylines.map((item) =>
    item.id === paylineId ? { ...item, isActive: false } : item,
  );
}

export function formatRowPath1Based(rowPath: readonly number[]): string {
  return `[${rowPath.map((row) => row + 1).join(', ')}]`;
}

function parseInteger(value: string): number | null {
  const normalized = value.trim();
  if (!/^\d+$/.test(normalized)) {
    return null;
  }
  const parsed = Number(normalized);
  return Number.isSafeInteger(parsed) ? parsed : null;
}
