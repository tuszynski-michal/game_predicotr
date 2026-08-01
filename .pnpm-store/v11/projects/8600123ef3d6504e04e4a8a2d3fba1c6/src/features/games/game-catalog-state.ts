import type {
  GameResponse,
  GameStatus,
} from '@game-predictor/admin-api-client';

export interface GameDraft {
  readonly code: string;
  readonly name: string;
  readonly status: GameStatus;
  readonly expectedLayoutCount: string;
}

export type ValidatedGameDraft =
  | {
      readonly valid: true;
      readonly value: GameDraft;
    }
  | {
      readonly error: string;
      readonly valid: false;
    };

export const EMPTY_GAME_DRAFT: GameDraft = {
  code: '',
  name: '',
  status: 'draft',
  expectedLayoutCount: '500000',
};

export const GAME_STATUS_LABELS: Record<GameStatus, string> = {
  draft: 'Szkic',
  active: 'Aktywna',
  archived: 'Zarchiwizowana',
};

export const GAME_STATUS_FILTERS = ['active', 'draft', 'archived'] as const;

export const GAME_STATUS_FILTER_LABELS: Record<GameStatus, string> = {
  active: 'Aktywne',
  draft: 'Szkice',
  archived: 'Zarchiwizowane',
};

export type GameStatusCounts = Readonly<Record<GameStatus, number>>;

export function countGamesByStatus(
  games: readonly GameResponse[],
): GameStatusCounts {
  return games.reduce<GameStatusCounts>(
    (counts, game) => ({
      ...counts,
      [game.status]: counts[game.status] + 1,
    }),
    { active: 0, archived: 0, draft: 0 },
  );
}

export function filterGamesByStatus(
  games: readonly GameResponse[],
  status: GameStatus,
): readonly GameResponse[] {
  return games.filter((game) => game.status === status);
}

export function validateGameDraft(draft: GameDraft): ValidatedGameDraft {
  const code = draft.code.trim();
  const name = draft.name.trim();
  const expectedLayoutCount = Number(draft.expectedLayoutCount);
  if (!code || !name) {
    return {
      error: 'Kod i nazwa gry są wymagane.',
      valid: false,
    };
  }
  if (
    !Number.isSafeInteger(expectedLayoutCount) ||
    expectedLayoutCount < 1 ||
    expectedLayoutCount > 10_000_000
  ) {
    return {
      error: 'Oczekiwana liczba layoutów musi być liczbą od 1 do 10 000 000.',
      valid: false,
    };
  }
  return {
    valid: true,
    value: {
      code,
      name,
      status: draft.status,
      expectedLayoutCount: String(expectedLayoutCount),
    },
  };
}

export function upsertGame(
  games: readonly GameResponse[],
  savedGame: GameResponse,
): readonly GameResponse[] {
  return games.some((game) => game.id === savedGame.id)
    ? games.map((game) => (game.id === savedGame.id ? savedGame : game))
    : [...games, savedGame];
}

export function markGameArchived(
  games: readonly GameResponse[],
  gameId: string,
): readonly GameResponse[] {
  return games.map((game) =>
    game.id === gameId ? { ...game, status: 'archived' } : game,
  );
}
