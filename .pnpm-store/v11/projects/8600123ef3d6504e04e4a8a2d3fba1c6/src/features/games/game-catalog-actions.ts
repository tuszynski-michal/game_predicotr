import type {
  AdminApiClient,
  GameCreate,
  GameResponse,
  GameUpdate,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';
import type { GameDraft } from './game-catalog-state.ts';

export type GamesClient = Pick<
  AdminApiClient,
  'archiveGame' | 'createGame' | 'listGames' | 'updateGame'
>;

export type SaveGameIntent =
  | { readonly mode: 'create' }
  | { readonly gameId: string; readonly mode: 'edit' };

export type SaveGameResult =
  | { readonly game: GameResponse; readonly ok: true }
  | { readonly error: string; readonly ok: false };

export async function saveGameIdentity(
  api: GamesClient,
  intent: SaveGameIntent,
  draft: GameDraft,
): Promise<SaveGameResult> {
  try {
    const result =
      intent.mode === 'create'
        ? await api.createGame({
            code: draft.code,
            name: draft.name,
            status: draft.status,
          } satisfies GameCreate)
        : await api.updateGame(intent.gameId, {
            name: draft.name,
            status: draft.status,
          } satisfies GameUpdate);

    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(result.error, 'Nie udało się zapisać gry.'),
        ok: false,
      };
    }
    return { game: result.data, ok: true };
  } catch {
    return {
      error:
        'Połączenie z lokalnym Admin API zostało przerwane. Spróbuj ponownie.',
      ok: false,
    };
  }
}

export type ArchiveGameResult =
  { readonly ok: true } | { readonly error: string; readonly ok: false };

export async function archiveGameIdentity(
  api: GamesClient,
  gameId: string,
): Promise<ArchiveGameResult> {
  try {
    const result = await api.archiveGame(gameId);
    if (result.error !== undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się zarchiwizować gry.',
        ),
        ok: false,
      };
    }
    return { ok: true };
  } catch {
    return {
      error:
        'Połączenie z lokalnym Admin API zostało przerwane. Archiwizacja nie została potwierdzona.',
      ok: false,
    };
  }
}
