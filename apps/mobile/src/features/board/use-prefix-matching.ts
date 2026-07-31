import { encodeSignaturePrefix } from '@game-predictor/shared-ts';
import { useEffect, useMemo, useState } from 'react';

import type {
  LocalGameConfig,
  PrefixLayoutSuggestion,
  PrefixMatchResult,
} from '@/data/local-layout-repository';
import { asLocalDataError, type LocalDataError } from '@/data/local-data-error';

import type { BoardCell } from './board-reducer';

export interface PrefixMatchRepository {
  findByPrefix(
    game: LocalGameConfig,
    signaturePrefix: string,
  ): Promise<PrefixMatchResult>;
}

export type PrefixMatchingState =
  | {
      readonly candidateCount: null;
      readonly error: null;
      readonly signaturePrefix: string;
      readonly status: 'idle' | 'loading';
      readonly suggestion: null;
    }
  | {
      readonly candidateCount: number;
      readonly error: null;
      readonly signaturePrefix: string;
      readonly status: 'ready';
      readonly suggestion: PrefixLayoutSuggestion | null;
    }
  | {
      readonly candidateCount: null;
      readonly error: LocalDataError;
      readonly signaturePrefix: string;
      readonly status: 'error';
      readonly suggestion: null;
    };

type StoredPrefixState = PrefixMatchingState & {
  readonly boardCells: readonly BoardCell[] | null;
  readonly gameId: string | null;
};

function idleState(signaturePrefix = ''): StoredPrefixState {
  return {
    boardCells: null,
    candidateCount: null,
    error: null,
    gameId: null,
    signaturePrefix,
    status: 'idle',
    suggestion: null,
  };
}

function loadingState(signaturePrefix: string): PrefixMatchingState {
  return {
    candidateCount: null,
    error: null,
    signaturePrefix,
    status: 'loading',
    suggestion: null,
  };
}

export function usePrefixMatching(
  repository: PrefixMatchRepository,
  game: LocalGameConfig | null,
  cells: readonly BoardCell[],
  rejectedSuggestionPrefix: string | null,
  enabled = true,
): PrefixMatchingState {
  const signaturePrefix = useMemo(
    () =>
      game === null
        ? ''
        : encodeSignaturePrefix(cells, game.signatureCellWidth),
    [cells, game],
  );
  const [storedState, setStoredState] = useState<StoredPrefixState>(idleState);

  useEffect(() => {
    if (!enabled || game === null || signaturePrefix.length === 0) {
      return;
    }
    if (rejectedSuggestionPrefix === signaturePrefix) {
      return;
    }

    let isCurrentRequest = true;

    void repository
      .findByPrefix(game, signaturePrefix)
      .then((result) => {
        if (!isCurrentRequest) {
          return;
        }
        setStoredState({
          boardCells: cells,
          candidateCount: result.candidateCount,
          error: null,
          gameId: game.id,
          signaturePrefix,
          status: 'ready',
          suggestion: result.suggestion,
        });
      })
      .catch((error: unknown) => {
        if (!isCurrentRequest) {
          return;
        }
        setStoredState({
          boardCells: cells,
          candidateCount: null,
          error: asLocalDataError(error, 'Could not match board prefix'),
          gameId: game.id,
          signaturePrefix,
          status: 'error',
          suggestion: null,
        });
      });

    return () => {
      isCurrentRequest = false;
    };
  }, [
    cells,
    enabled,
    game,
    rejectedSuggestionPrefix,
    repository,
    signaturePrefix,
  ]);

  if (!enabled || game === null || signaturePrefix.length === 0) {
    return idleState(signaturePrefix);
  }
  if (rejectedSuggestionPrefix === signaturePrefix) {
    const candidateCount =
      storedState.status === 'ready' &&
      storedState.gameId === game.id &&
      storedState.boardCells === cells &&
      storedState.signaturePrefix === signaturePrefix
        ? storedState.candidateCount
        : 0;
    return {
      candidateCount,
      error: null,
      signaturePrefix,
      status: 'ready',
      suggestion: null,
    };
  }
  if (
    storedState.gameId !== game.id ||
    storedState.boardCells !== cells ||
    storedState.signaturePrefix !== signaturePrefix
  ) {
    return loadingState(signaturePrefix);
  }
  return storedState;
}
