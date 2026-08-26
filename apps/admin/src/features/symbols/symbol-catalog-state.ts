import type {
  GameResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';

export interface SymbolDraft {
  readonly isWildcard: boolean;
  readonly name: string;
}

export type ValidatedSymbolDraft = SymbolDraft;

export type SymbolDraftValidation =
  | { readonly valid: true; readonly value: ValidatedSymbolDraft }
  | { readonly error: string; readonly valid: false };

export const EMPTY_SYMBOL_DRAFT: SymbolDraft = {
  isWildcard: false,
  name: '',
};

export function symbolToDraft(symbol: SymbolResponse): SymbolDraft {
  return {
    isWildcard: symbol.isWildcard,
    name: symbol.name,
  };
}

export function validateSymbolDraft(draft: SymbolDraft): SymbolDraftValidation {
  const name = draft.name.trim();
  if (!name) {
    return { error: 'Nazwa symbolu jest wymagana.', valid: false };
  }
  if (name.length > 200) {
    return {
      error: 'Nazwa symbolu może mieć maksymalnie 200 znaków.',
      valid: false,
    };
  }

  return { valid: true, value: { isWildcard: draft.isWildcard, name } };
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

function compareSymbols(left: SymbolResponse, right: SymbolResponse): number {
  return (
    left.displayOrder - right.displayOrder ||
    left.mobileCode - right.mobileCode ||
    left.id.localeCompare(right.id)
  );
}
