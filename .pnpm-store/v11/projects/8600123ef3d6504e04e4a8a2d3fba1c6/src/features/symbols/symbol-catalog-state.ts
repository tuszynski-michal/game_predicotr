import type {
  GameResponse,
  SymbolResponse,
  SymbolStatus,
} from '@game-predictor/admin-api-client';

const STABLE_CODE_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/;
const MAX_DISPLAY_ORDER = 2_147_483_647;

export interface SymbolDraft {
  readonly code: string;
  readonly displayOrder: string;
  readonly imagePath: string;
  readonly isWildcard: boolean;
  readonly mobileCode: string;
  readonly name: string;
  readonly status: SymbolStatus;
}

export interface ValidatedSymbolDraft {
  readonly code: string;
  readonly displayOrder: number;
  readonly imagePath: string | null;
  readonly isWildcard: boolean;
  readonly mobileCode: number;
  readonly name: string;
  readonly status: SymbolStatus;
}

export type SymbolDraftValidation =
  | { readonly valid: true; readonly value: ValidatedSymbolDraft }
  | { readonly error: string; readonly valid: false };

export const EMPTY_SYMBOL_DRAFT: SymbolDraft = {
  code: '',
  displayOrder: '0',
  imagePath: '',
  isWildcard: false,
  mobileCode: '',
  name: '',
  status: 'active',
};

export const SYMBOL_STATUS_LABELS: Record<SymbolStatus, string> = {
  active: 'Aktywny',
  archived: 'Zarchiwizowany',
};

export function symbolToDraft(symbol: SymbolResponse): SymbolDraft {
  return {
    code: symbol.code,
    displayOrder: String(symbol.displayOrder),
    imagePath: symbol.imagePath ?? '',
    isWildcard: symbol.isWildcard,
    mobileCode: String(symbol.mobileCode),
    name: symbol.name,
    status: symbol.status,
  };
}

export function validateSymbolDraft(draft: SymbolDraft): SymbolDraftValidation {
  const code = draft.code.trim();
  const name = draft.name.trim();
  const imagePath = draft.imagePath.trim();

  if (!code || !name || !draft.mobileCode.trim()) {
    return {
      error: 'Kod mobilny, kod stabilny i nazwa symbolu są wymagane.',
      valid: false,
    };
  }
  if (!STABLE_CODE_PATTERN.test(code)) {
    return {
      error:
        'Kod stabilny musi mieć 1–64 znaki: litery, cyfry, myślnik lub podkreślenie.',
      valid: false,
    };
  }

  const mobileCode = parseInteger(draft.mobileCode);
  if (mobileCode === null || mobileCode < 1 || mobileCode > 32767) {
    return {
      error: 'Kod mobilny musi być liczbą całkowitą od 1 do 32767.',
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
      error: 'Kolejność musi być nieujemną liczbą całkowitą.',
      valid: false,
    };
  }

  if (imagePath && !isValidRelativeImagePath(imagePath)) {
    return {
      error:
        'Ścieżka obrazu musi być względną ścieżką POSIX bez dysku, „..” i ukośników wstecznych.',
      valid: false,
    };
  }

  return {
    valid: true,
    value: {
      code,
      displayOrder,
      imagePath: imagePath || null,
      isWildcard: draft.isWildcard,
      mobileCode,
      name,
      status: draft.status,
    },
  };
}

export function selectGameId(
  games: readonly GameResponse[],
  currentGameId: string | null,
): string | null {
  if (currentGameId && games.some((game) => game.id === currentGameId)) {
    return currentGameId;
  }
  return (
    games.find((game) => game.status !== 'archived')?.id ?? games[0]?.id ?? null
  );
}

export function upsertSymbol(
  symbols: readonly SymbolResponse[],
  savedSymbol: SymbolResponse,
): readonly SymbolResponse[] {
  const updated = symbols.some((symbol) => symbol.id === savedSymbol.id)
    ? symbols.map((symbol) =>
        symbol.id === savedSymbol.id ? savedSymbol : symbol,
      )
    : [...symbols, savedSymbol];
  return [...updated].sort(compareSymbols);
}

export function markSymbolArchived(
  symbols: readonly SymbolResponse[],
  symbolId: string,
): readonly SymbolResponse[] {
  return symbols.map((symbol) =>
    symbol.id === symbolId ? { ...symbol, status: 'archived' } : symbol,
  );
}

function parseInteger(value: string): number | null {
  const normalized = value.trim();
  if (!/^\d+$/.test(normalized)) {
    return null;
  }
  const parsed = Number(normalized);
  return Number.isSafeInteger(parsed) ? parsed : null;
}

function isValidRelativeImagePath(value: string): boolean {
  if (
    value.length > 500 ||
    value.startsWith('/') ||
    value.includes('\\') ||
    value.includes(':')
  ) {
    return false;
  }
  return !value.split('/').some((part) => part === '..');
}

function compareSymbols(left: SymbolResponse, right: SymbolResponse): number {
  return (
    left.displayOrder - right.displayOrder ||
    left.mobileCode - right.mobileCode ||
    left.id.localeCompare(right.id)
  );
}
