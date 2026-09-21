import type {
  GameShapeGeometryConfiguration,
  GameResponse,
  GameStatus,
  ShapeGeometryReadinessStatus,
} from '@game-predictor/admin-api-client';

export interface GameDraft {
  readonly code: string;
  readonly name: string;
  readonly status: GameStatus;
  readonly expectedLayoutCount: string;
  readonly shapeGeometryConfiguration: GameShapeGeometryConfiguration;
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
  shapeGeometryConfiguration: 'requires_clarification',
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

export const SHAPE_GEOMETRY_CONFIGURATION_LABELS: Record<
  GameShapeGeometryConfiguration,
  string
> = {
  framed_full_page_v2: 'Pełna strona z ramką',
  requires_clarification: 'Format wymaga doprecyzowania',
};

export const SHAPE_GEOMETRY_READINESS_LABELS: Record<
  ShapeGeometryReadinessStatus,
  string
> = {
  manual_review_required: 'Pierwszy import wymaga ręcznej korekty',
  ready_for_shared_preflight: 'Wspólna geometria gotowa do preflightu',
  requires_clarification: 'Trzeba doprecyzować format strony',
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
      error: 'Oczekiwana liczba plansz musi być liczbą od 1 do 10 000 000.',
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
      shapeGeometryConfiguration: draft.shapeGeometryConfiguration,
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
