import { encodeSignaturePrefix } from '@game-predictor/shared-ts';
import { useEffect, useMemo, useState } from 'react';

import type {
  LayoutCandidate,
  LocalGameConfig,
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
      readonly candidate: null;
      readonly candidateCount: null;
      readonly error: null;
      readonly signaturePrefix: string;
      readonly status: 'idle' | 'loading';
    }
  | {
      readonly candidate: LayoutCandidate | null;
      readonly candidateCount: number;
      readonly error: null;
      readonly signaturePrefix: string;
      readonly status: 'ready';
    }
  | {
      readonly candidate: null;
      readonly candidateCount: null;
      readonly error: LocalDataError;
      readonly signaturePrefix: string;
      readonly status: 'error';
    };

type StoredPrefixState = PrefixMatchingState & {
  readonly boardCells: readonly BoardCell[] | null;
  readonly gameId: string | null;
};

function idleState(signaturePrefix = ''): StoredPrefixState {
  return {
    boardCells: null,
    candidate: null,
    candidateCount: null,
    error: null,
    gameId: null,
    signaturePrefix,
    status: 'idle',
  };
}

function loadingState(signaturePrefix: string): PrefixMatchingState {
  return {
    candidate: null,
    candidateCount: null,
    error: null,
    signaturePrefix,
    status: 'loading',
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
          candidate: result.candidate,
          candidateCount: result.candidateCount,
          error: null,
          gameId: game.id,
          signaturePrefix,
          status: 'ready',
        });
      })
      .catch((error: unknown) => {
        if (!isCurrentRequest) {
          return;
        }
        setStoredState({
          boardCells: cells,
          candidate: null,
          candidateCount: null,
          error: asLocalDataError(error, 'Could not match board prefix'),
          gameId: game.id,
          signaturePrefix,
          status: 'error',
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
    return {
      candidate: null,
      candidateCount: 1,
      error: null,
      signaturePrefix,
      status: 'ready',
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
