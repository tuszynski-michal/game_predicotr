import type {
  GameResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';

export type SuperGameTriggerCount = 3 | 4 | 5;

export interface SymbolDraft {
  readonly isWildcard: boolean;
  readonly name: string;
  /** Checkbox „Uruchamia supergrę” (D-535). */
  readonly triggersSuperGame: boolean;
  /** Selected threshold; kept while the checkbox is off to restore the choice. */
  readonly superGameTriggerCount: SuperGameTriggerCount;
}

export interface ValidatedSymbolDraft {
  readonly isWildcard: boolean;
  readonly name: string;
  readonly superGameTriggerCount: SuperGameTriggerCount | null;
}

export const SUPER_GAME_TRIGGER_COUNT_OPTIONS: readonly {
  readonly label: string;
  readonly value: SuperGameTriggerCount;
}[] = [
  { label: 'Trzy symbole', value: 3 },
  { label: 'Cztery symbole', value: 4 },
  { label: 'Pięć symboli', value: 5 },
];

export const NO_SUPER_GAME_KIND = 'none';

export function superGameTriggerCountLabel(count: number): string {
  return (
    SUPER_GAME_TRIGGER_COUNT_OPTIONS.find((option) => option.value === count)
      ?.label ?? `${count} symbole`
  );
}

export function parseSuperGameTriggerCount(
  value: string,
): SuperGameTriggerCount {
  const parsed = Number(value);
  return parsed === 4 || parsed === 5 ? parsed : 3;
}

/**
 * The trigger role needs a game with a super game kind; the API rejects it
 * otherwise (SUPER_GAME_KIND_REQUIRED). An already saved role stays editable
 * so the operator can always remove it.
 */
export function canEditSuperGameTrigger(
  game: Pick<GameResponse, 'superGameKind'> | null,
  draft: Pick<SymbolDraft, 'triggersSuperGame'>,
): boolean {
  return (
    draft.triggersSuperGame ||
    (game !== null && game.superGameKind !== NO_SUPER_GAME_KIND)
  );
}

export type SymbolDraftValidation =
  | { readonly valid: true; readonly value: ValidatedSymbolDraft }
  | { readonly error: string; readonly valid: false };

export const EMPTY_SYMBOL_DRAFT: SymbolDraft = {
  isWildcard: false,
  name: '',
  superGameTriggerCount: 3,
  triggersSuperGame: false,
};

export function symbolToDraft(symbol: SymbolResponse): SymbolDraft {
  const count = symbol.superGameTriggerCount;
  return {
    isWildcard: symbol.isWildcard,
    name: symbol.name,
    superGameTriggerCount:
      count === null ? 3 : parseSuperGameTriggerCount(String(count)),
    triggersSuperGame: count !== null,
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

  return {
    valid: true,
    value: {
      isWildcard: draft.isWildcard,
      name,
      superGameTriggerCount: draft.triggersSuperGame
        ? draft.superGameTriggerCount
        : null,
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

function compareSymbols(left: SymbolResponse, right: SymbolResponse): number {
  return (
    left.displayOrder - right.displayOrder ||
    left.mobileCode - right.mobileCode ||
    left.id.localeCompare(right.id)
  );
}

export type SymbolMoveDirection = 'down' | 'up';

export interface SymbolDisplayOrderChange {
  readonly displayOrder: number;
  readonly symbolId: string;
}

/**
 * Moves one symbol a single position in the catalog order and renumbers the
 * whole list to 0..n-1, which also removes existing ties and gaps. Returns only
 * the symbols whose displayOrder changes; an edge move or an unknown symbol
 * returns no changes.
 */
export function planSymbolReorder(
  symbols: readonly SymbolResponse[],
  symbolId: string,
  direction: SymbolMoveDirection,
): readonly SymbolDisplayOrderChange[] {
  const ordered = [...symbols].sort(compareSymbols);
  const index = ordered.findIndex((symbol) => symbol.id === symbolId);
  const targetIndex = direction === 'up' ? index - 1 : index + 1;
  if (index < 0 || targetIndex < 0 || targetIndex >= ordered.length) {
    return [];
  }
  const moved = ordered[index];
  const neighbour = ordered[targetIndex];
  if (moved === undefined || neighbour === undefined) return [];
  ordered[index] = neighbour;
  ordered[targetIndex] = moved;
  return ordered.flatMap((symbol, displayOrder) =>
    symbol.displayOrder === displayOrder
      ? []
      : [{ displayOrder, symbolId: symbol.id }],
  );
}

export function applySymbolDisplayOrderChanges(
  symbols: readonly SymbolResponse[],
  changes: readonly SymbolDisplayOrderChange[],
): readonly SymbolResponse[] {
  const orderById = new Map(
    changes.map((change) => [change.symbolId, change.displayOrder]),
  );
  return symbols
    .map((symbol) => {
      const displayOrder = orderById.get(symbol.id);
      return displayOrder === undefined ? symbol : { ...symbol, displayOrder };
    })
    .sort(compareSymbols);
}
