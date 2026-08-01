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
  'archiveGame' | 'createGame' | 'getGame' | 'listGames' | 'updateGame'
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
  const fallbackError = 'Nie udało się zapisać gry.';
  try {
    const result =
      intent.mode === 'create'
        ? await api.createGame({
            code: draft.code,
            name: draft.name,
            status: draft.status,
            expectedLayoutCount: Number(draft.expectedLayoutCount),
          } satisfies GameCreate)
        : await api.updateGame(intent.gameId, {
            name: draft.name,
            status: draft.status,
            expectedLayoutCount: Number(draft.expectedLayoutCount),
          } satisfies GameUpdate);

    const mutationError = result.error;
    if (mutationError === undefined && result.data !== undefined) {
      return { game: result.data, ok: true };
    }

    const reconciled = await reconcileEditedGame(api, intent, draft);
    if (reconciled !== null) {
      return reconciled;
    }

    return {
      error: apiErrorMessage(mutationError, fallbackError),
      ok: false,
    };
  } catch {
    const reconciled = await reconcileEditedGame(api, intent, draft);
    if (reconciled !== null) {
      return reconciled;
    }
    return {
      error:
        'Połączenie z lokalnym Admin API zostało przerwane. Spróbuj ponownie.',
      ok: false,
    };
  }
}

async function reconcileEditedGame(
  api: GamesClient,
  intent: SaveGameIntent,
  draft: GameDraft,
): Promise<SaveGameResult | null> {
  if (intent.mode !== 'edit') {
    return null;
  }

  try {
    const verification = await api.getGame(intent.gameId);
    const game = verification.data;
    if (
      verification.error === undefined &&
      game !== undefined &&
      game.name === draft.name &&
      game.status === draft.status &&
      game.expectedLayoutCount === Number(draft.expectedLayoutCount)
    ) {
      return { game, ok: true };
    }
  } catch {
    // Preserve the original mutation error when read-back is unavailable.
  }
  return null;
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

export async function restoreGameIdentity(
  api: GamesClient,
  game: GameResponse,
): Promise<SaveGameResult> {
  try {
    const result = await api.updateGame(game.id, {
      name: game.name,
      status: 'draft',
      expectedLayoutCount: game.expectedLayoutCount,
    } satisfies GameUpdate);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się przywrócić gry jako szkicu.',
        ),
        ok: false,
      };
    }
    return { game: result.data, ok: true };
  } catch {
    return {
      error:
        'Połączenie z lokalnym Admin API zostało przerwane. Przywrócenie nie zostało potwierdzone.',
      ok: false,
    };
  }
}
