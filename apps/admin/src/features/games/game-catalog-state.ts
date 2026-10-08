import type {
  GameShapeGeometryConfiguration,
  GameResponse,
  GameStatus,
  GridEngineModelStatus,
  GridEngineProfileResponse,
  ShapeGeometryReadinessStatus,
  SuperGameKindResponse,
} from '@game-predictor/admin-api-client';

export interface GameDraft {
  readonly code: string;
  readonly name: string;
  readonly status: GameStatus;
  readonly expectedLayoutCount: string;
  readonly shapeGeometryConfiguration: GameShapeGeometryConfiguration;
  /** Code from GET /api/v1/admin/super-game-kinds; 'none' = no super game (D-535). */
  readonly superGameKind: string;
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
  superGameKind: 'none',
};

// Shown until the API registry loads, or when it cannot be loaded; the API
// owns the list of kinds, so the Admin never keeps its own copy of the others.
export const FALLBACK_SUPER_GAME_KINDS: readonly SuperGameKindResponse[] = [
  { code: 'none', label: 'Brak' },
];

/**
 * Options for the „Supergra” select: the API registry, plus the current value
 * when it is missing from the list (an unloaded registry must never silently
 * change a saved kind on the next save).
 */
export function superGameKindOptions(
  kinds: readonly SuperGameKindResponse[],
  currentKind: string,
): readonly SuperGameKindResponse[] {
  const available = kinds.length > 0 ? kinds : FALLBACK_SUPER_GAME_KINDS;
  return available.some((kind) => kind.code === currentKind)
    ? available
    : [...available, { code: currentKind, label: currentKind }];
}

export function superGameKindLabel(
  kinds: readonly SuperGameKindResponse[],
  code: string,
): string {
  return (
    kinds.find((kind) => kind.code === code)?.label ??
    FALLBACK_SUPER_GAME_KINDS.find((kind) => kind.code === code)?.label ??
    code
  );
}

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
  grid_profile_777_v2: '777 v2',
  grid_profile_mumie_v1: 'Mumie',
};

// TASK-0830: page formats that also select a grid engine profile (a frozen
// neural_grid model). The API owns the model registry; these texts only
// describe the choice when the profile list is unavailable.
export const GRID_ENGINE_PROFILE_FALLBACK_DESCRIPTIONS: Partial<
  Record<GameShapeGeometryConfiguration, string>
> = {
  grid_profile_777_v2:
    'Model neural_grid trenowany na 777. Profil służy także kolejnym wersjom gry 777 (np. 777 v3).',
  grid_profile_mumie_v1: 'Model neural_grid doszkolony na Mumiach.',
};

export const GRID_ENGINE_MODEL_STATUS_LABELS: Record<
  GridEngineModelStatus,
  string
> = {
  available: 'Model dostępny',
  checksum_mismatch: 'Model niezgodny z rejestrem (SHA-256)',
  missing: 'Brak plików modelu',
};

export function isGridEngineProfileConfiguration(
  configuration: GameShapeGeometryConfiguration | null | undefined,
): boolean {
  return (
    configuration !== null &&
    configuration !== undefined &&
    configuration in GRID_ENGINE_PROFILE_FALLBACK_DESCRIPTIONS
  );
}

export function findGridEngineProfile(
  profiles: readonly GridEngineProfileResponse[],
  configuration: GameShapeGeometryConfiguration | null | undefined,
): GridEngineProfileResponse | undefined {
  return profiles.find((profile) => profile.configuration === configuration);
}

export function shapeGeometryConfigurationLabel(
  configuration: GameShapeGeometryConfiguration | null | undefined,
): string {
  return configuration
    ? SHAPE_GEOMETRY_CONFIGURATION_LABELS[configuration]
    : 'Nie ustalono (rekord historyczny)';
}

export function gridEngineModelSummary(
  profile: GridEngineProfileResponse,
): string {
  return `${GRID_ENGINE_MODEL_STATUS_LABELS[profile.status]} · ${profile.modelKind} ${profile.version} (run ${profile.runId.slice(0, 8)}, preset ${profile.preset})`;
}

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
      superGameKind: draft.superGameKind,
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
