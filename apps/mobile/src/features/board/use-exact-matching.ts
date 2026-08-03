import { encodeSignature } from '@game-predictor/shared-ts';
import { useEffect, useMemo, useState } from 'react';

import { asLocalDataError, LocalDataError } from '@/data/local-data-error';
import type {
  ExactMatchResult,
  LocalGameConfig,
} from '@/data/local-layout-repository';

import type { BoardCell } from './board-reducer';

export interface ExactMatchRepository {
  findExact(
    game: LocalGameConfig,
    signature: string,
  ): Promise<ExactMatchResult>;
}

export type ExactMatchingState =
  | {
      readonly error: null;
      readonly result: null;
      readonly signature: string;
      readonly status: 'idle' | 'loading';
    }
  | {
      readonly error: null;
      readonly result: ExactMatchResult;
      readonly signature: string;
      readonly status: 'ready';
    }
  | {
      readonly error: LocalDataError;
      readonly result: null;
      readonly signature: string;
      readonly status: 'error';
    };

type StoredExactState = ExactMatchingState & {
  readonly boardCells: readonly BoardCell[] | null;
  readonly gameId: string | null;
};

function idleState(signature = ''): StoredExactState {
  return {
    boardCells: null,
    error: null,
    gameId: null,
    result: null,
    signature,
    status: 'idle',
  };
}

function loadingState(signature: string): ExactMatchingState {
  return {
    error: null,
    result: null,
    signature,
    status: 'loading',
  };
}

function isCompleteBoard(
  game: LocalGameConfig | null,
  cells: readonly BoardCell[],
): cells is readonly number[] {
  return (
    game !== null &&
    cells.length === game.rows * game.columns &&
    cells.every((cell) => cell !== null)
  );
}

export function useExactMatching(
  repository: ExactMatchRepository,
  game: LocalGameConfig | null,
  cells: readonly BoardCell[],
  anchorSequenceNumber: number | null = null,
): ExactMatchingState {
  const signature = useMemo(() => {
    if (game === null || !isCompleteBoard(game, cells)) {
      return '';
    }
    return encodeSignature(cells, game.signatureCellWidth);
  }, [cells, game]);
  const [storedState, setStoredState] = useState<StoredExactState>(idleState);

  useEffect(() => {
    if (
      game === null ||
      signature.length === 0 ||
      anchorSequenceNumber !== null
    ) {
      return;
    }

    let isCurrentRequest = true;

    void repository
      .findExact(game, signature)
      .then((result) => {
        if (!isCurrentRequest) {
          return;
        }
        setStoredState({
          boardCells: cells,
          error: null,
          gameId: game.id,
          result,
          signature,
          status: 'ready',
        });
      })
      .catch((error: unknown) => {
        if (!isCurrentRequest) {
          return;
        }
        setStoredState({
          boardCells: cells,
          error: asLocalDataError(error, 'Could not match exact board'),
          gameId: game.id,
          result: null,
          signature,
          status: 'error',
        });
      });

    return () => {
      isCurrentRequest = false;
    };
  }, [anchorSequenceNumber, cells, game, repository, signature]);

  if (game === null || signature.length === 0) {
    return idleState(signature);
  }
  if (anchorSequenceNumber !== null) {
    if (
      !Number.isSafeInteger(anchorSequenceNumber) ||
      anchorSequenceNumber < 1 ||
      anchorSequenceNumber > game.layoutCount ||
      !isCompleteBoard(game, cells)
    ) {
      return {
        error: new LocalDataError('Known sequence anchor is invalid.'),
        result: null,
        signature,
        status: 'error',
      };
    }
    return {
      error: null,
      result: {
        candidate: {
          cells,
          sequenceNumber: anchorSequenceNumber,
          signature,
        },
        status: 'unique',
      },
      signature,
      status: 'ready',
    };
  }
  if (
    storedState.gameId !== game.id ||
    storedState.boardCells !== cells ||
    storedState.signature !== signature
  ) {
    return loadingState(signature);
  }
  return storedState;
}
