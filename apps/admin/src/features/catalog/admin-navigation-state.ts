export const ADMIN_WORKSPACES = [
  'games',
  'management',
  'releases',
  'jobs',
  'image-selection',
  'manual-image-selection',
  'semi-automatic-image-selection',
  'v7-label-geometry',
  'symbol-verification',
  'storage',
] as const;
export type AdminWorkspace = (typeof ADMIN_WORKSPACES)[number];

export const GAME_SECTIONS = [
  'imports',
  'board-source-cleanup',
  'symbols',
  'board-search',
  'rules',
  'reviews',
  'unreadable-symbols',
  'model-quality',
  'super-games',
] as const;
export type GameSection = (typeof GAME_SECTIONS)[number];

export interface AdminNavigationState {
  readonly workspace: AdminWorkspace;
  readonly gameId: string | null;
  readonly section: GameSection | null;
  /**
   * The opened super game series (TASK-0934). Meaningful, parsed and
   * serialised only for the `super-games` section of a selected game.
   */
  readonly seriesId: string | null;
}

export const DEFAULT_ADMIN_NAVIGATION: AdminNavigationState = {
  workspace: 'games',
  gameId: null,
  section: null,
  seriesId: null,
};

/** Name of the query parameter that carries the opened series. */
export const SUPER_GAME_SERIES_PARAMETER = 'series';

/**
 * The „Supergry” section exists only for games with a super game kind other
 * than `none` (D-535); every other section is always available.
 */
export function isGameSectionAvailable(
  section: GameSection,
  game: { readonly superGameKind: string } | null,
): boolean {
  if (section !== 'super-games') return true;
  return game !== null && game.superGameKind !== 'none';
}

/**
 * Drops state that does not belong to the current section: an opened series
 * is kept only inside the „Supergry” section of a selected game.
 */
export function normalizeAdminNavigation(
  state: AdminNavigationState,
): AdminNavigationState {
  const seriesId = state.seriesId ?? null;
  const keepSeries =
    seriesId !== null &&
    state.gameId !== null &&
    state.section === 'super-games';
  if (keepSeries) return state;
  return state.seriesId === null ? state : { ...state, seriesId: null };
}

function includesValue<T extends string>(
  values: readonly T[],
  candidate: string | null,
): candidate is T {
  return candidate !== null && values.includes(candidate as T);
}

export function parseAdminNavigation(
  search: string | URLSearchParams,
): AdminNavigationState {
  const params =
    typeof search === 'string'
      ? new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
      : search;
  const workspaceValue = params.get('workspace');
  const gameId = params.get('game')?.trim() || null;
  const sectionValue = params.get('section');
  const section =
    gameId !== null && includesValue(GAME_SECTIONS, sectionValue)
      ? sectionValue
      : null;
  const seriesId =
    section === 'super-games'
      ? params.get(SUPER_GAME_SERIES_PARAMETER)?.trim() || null
      : null;

  return {
    workspace: includesValue(ADMIN_WORKSPACES, workspaceValue)
      ? workspaceValue
      : DEFAULT_ADMIN_NAVIGATION.workspace,
    gameId,
    section,
    seriesId,
  };
}

export function serializeAdminNavigation(
  currentSearch: string | URLSearchParams,
  state: AdminNavigationState,
): string {
  const params =
    typeof currentSearch === 'string'
      ? new URLSearchParams(
          currentSearch.startsWith('?')
            ? currentSearch.slice(1)
            : currentSearch,
        )
      : new URLSearchParams(currentSearch);

  if (state.workspace === DEFAULT_ADMIN_NAVIGATION.workspace) {
    params.delete('workspace');
  } else {
    params.set('workspace', state.workspace);
  }

  if (state.gameId === null) {
    params.delete('game');
    params.delete('section');
  } else {
    params.set('game', state.gameId);
    if (state.section === null) {
      params.delete('section');
    } else {
      params.set('section', state.section);
    }
  }

  const normalized = normalizeAdminNavigation(state);
  if (normalized.seriesId === null) {
    params.delete(SUPER_GAME_SERIES_PARAMETER);
  } else {
    params.set(SUPER_GAME_SERIES_PARAMETER, normalized.seriesId);
  }

  const rendered = params.toString();
  return rendered === '' ? '' : `?${rendered}`;
}
