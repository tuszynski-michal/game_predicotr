export const ADMIN_WORKSPACES = [
  'games',
  'releases',
  'jobs',
  'image-selection',
  'manual-image-selection',
  'semi-automatic-image-selection',
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
] as const;
export type GameSection = (typeof GAME_SECTIONS)[number];

export interface AdminNavigationState {
  readonly workspace: AdminWorkspace;
  readonly gameId: string | null;
  readonly section: GameSection | null;
}

export const DEFAULT_ADMIN_NAVIGATION: AdminNavigationState = {
  workspace: 'games',
  gameId: null,
  section: null,
};

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

  return {
    workspace: includesValue(ADMIN_WORKSPACES, workspaceValue)
      ? workspaceValue
      : DEFAULT_ADMIN_NAVIGATION.workspace,
    gameId,
    section:
      gameId !== null && includesValue(GAME_SECTIONS, sectionValue)
        ? sectionValue
        : null,
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

  const rendered = params.toString();
  return rendered === '' ? '' : `?${rendered}`;
}
