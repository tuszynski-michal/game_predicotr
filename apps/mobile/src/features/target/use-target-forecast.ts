import {
  calculateTargetForecast,
  type ForecastResult,
  type SequencePayout,
} from '@game-predictor/shared-ts';
import { useCallback, useEffect, useState } from 'react';

import type { SnapshotDiagnostics } from '@/data/bundled-snapshot';
import { asLocalDataError, type LocalDataError } from '@/data/local-data-error';
import type { LocalGameConfig } from '@/data/local-layout-repository';

export interface TargetForecastRepository {
  readCyclicPayouts(
    game: LocalGameConfig,
    startSequenceNumber: number,
  ): Promise<readonly SequencePayout[]>;
}

export type TargetForecastState =
  | {
      readonly error: null;
      readonly result: null;
      readonly status: 'idle' | 'loading';
    }
  | {
      readonly error: null;
      readonly result: ForecastResult;
      readonly status: 'ready';
    }
  | {
      readonly error: LocalDataError;
      readonly result: null;
      readonly status: 'error';
    };

type StoredTargetState = TargetForecastState & {
  readonly attempt: number;
  readonly gameId: string | null;
  readonly startSequenceNumber: number | null;
};

type UseTargetForecastResult = {
  readonly retry: () => void;
  readonly state: TargetForecastState;
};

export function calculateSnapshotTargetForecast(
  game: LocalGameConfig,
  startSequenceNumber: number,
  diagnostics: SnapshotDiagnostics,
  sequencePayouts: readonly SequencePayout[],
): ForecastResult {
  return calculateTargetForecast({
    algorithmVersion: diagnostics.algorithmVersion,
    datasetVersion: game.datasetVersion,
    layoutCount: game.layoutCount,
    mobileReleaseVersion: diagnostics.releaseVersion,
    rulesVersion: game.rulesVersion,
    sequencePayouts,
    snapshotChecksum: diagnostics.logicalContentSha256,
    spinCost: game.spinCost,
    startSequenceNumber,
  });
}

function idleState(): StoredTargetState {
  return {
    attempt: 0,
    error: null,
    gameId: null,
    result: null,
    startSequenceNumber: null,
    status: 'idle',
  };
}

function loadingState(): TargetForecastState {
  return {
    error: null,
    result: null,
    status: 'loading',
  };
}

export function useTargetForecast(
  repository: TargetForecastRepository,
  game: LocalGameConfig | null,
  startSequenceNumber: number | null,
  diagnostics: SnapshotDiagnostics,
): UseTargetForecastResult {
  const [attempt, setAttempt] = useState(0);
  const [storedState, setStoredState] = useState<StoredTargetState>(idleState);

  useEffect(() => {
    if (game === null || startSequenceNumber === null) {
      return;
    }

    let isCurrentRequest = true;

    void repository
      .readCyclicPayouts(game, startSequenceNumber)
      .then((sequencePayouts) =>
        calculateSnapshotTargetForecast(
          game,
          startSequenceNumber,
          diagnostics,
          sequencePayouts,
        ),
      )
      .then((result) => {
        if (!isCurrentRequest) {
          return;
        }
        setStoredState({
          attempt,
          error: null,
          gameId: game.id,
          result,
          startSequenceNumber,
          status: 'ready',
        });
      })
      .catch((error: unknown) => {
        if (!isCurrentRequest) {
          return;
        }
        setStoredState({
          attempt,
          error: asLocalDataError(error, 'Could not calculate Target'),
          gameId: game.id,
          result: null,
          startSequenceNumber,
          status: 'error',
        });
      });

    return () => {
      isCurrentRequest = false;
    };
  }, [attempt, diagnostics, game, repository, startSequenceNumber]);

  const retry = useCallback(() => {
    if (game !== null && startSequenceNumber !== null) {
      setAttempt((currentAttempt) => currentAttempt + 1);
    }
  }, [game, startSequenceNumber]);

  if (game === null || startSequenceNumber === null) {
    return { retry, state: idleState() };
  }
  if (
    storedState.attempt !== attempt ||
    storedState.gameId !== game.id ||
    storedState.startSequenceNumber !== startSequenceNumber
  ) {
    return { retry, state: loadingState() };
  }
  return { retry, state: storedState };
}
