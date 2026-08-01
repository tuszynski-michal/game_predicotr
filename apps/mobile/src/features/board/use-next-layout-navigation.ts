import { useCallback, useLayoutEffect, useRef, useState } from 'react';

import { asLocalDataError, type LocalDataError } from '@/data/local-data-error';
import type {
  LayoutCandidate,
  LocalGameConfig,
} from '@/data/local-layout-repository';

export interface NextLayoutRepository {
  readLayoutBySequence(
    game: LocalGameConfig,
    sequenceNumber: number,
  ): Promise<LayoutCandidate>;
}

export type NextLayoutNavigationState =
  | {
      readonly error: null;
      readonly status: 'idle' | 'loading';
    }
  | {
      readonly error: LocalDataError;
      readonly status: 'error';
    };

type StoredState = NextLayoutNavigationState & {
  readonly contextKey: string;
};

type Result = {
  readonly navigate: () => void;
  readonly state: NextLayoutNavigationState;
};

function idleState(): NextLayoutNavigationState {
  return { error: null, status: 'idle' };
}

export function nextSequenceNumber(
  currentSequenceNumber: number,
  layoutCount: number,
): number {
  if (
    !Number.isSafeInteger(currentSequenceNumber) ||
    !Number.isSafeInteger(layoutCount) ||
    layoutCount < 1 ||
    currentSequenceNumber < 1 ||
    currentSequenceNumber > layoutCount
  ) {
    throw new RangeError('Sequence anchor must belong to the selected game.');
  }
  return currentSequenceNumber === layoutCount ? 1 : currentSequenceNumber + 1;
}

export function useNextLayoutNavigation(
  repository: NextLayoutRepository,
  game: LocalGameConfig | null,
  anchorSequenceNumber: number | null,
  anchorSignature: string,
  onLoad: (candidate: LayoutCandidate) => void,
): Result {
  const contextKey = `${game?.id ?? 'none'}:${anchorSequenceNumber ?? 'none'}:${anchorSignature}`;
  const contextKeyRef = useRef(contextKey);
  const requestNumberRef = useRef(0);
  const requestInFlightContextRef = useRef<string | null>(null);
  const [storedState, setStoredState] = useState<StoredState>({
    contextKey,
    error: null,
    status: 'idle',
  });

  useLayoutEffect(() => {
    contextKeyRef.current = contextKey;
    requestNumberRef.current += 1;
    requestInFlightContextRef.current = null;
  }, [contextKey]);

  const navigate = useCallback(() => {
    if (
      game === null ||
      anchorSequenceNumber === null ||
      requestInFlightContextRef.current === contextKey
    ) {
      return;
    }

    const requestContextKey = contextKey;
    const requestNumber = requestNumberRef.current + 1;
    requestNumberRef.current = requestNumber;
    requestInFlightContextRef.current = requestContextKey;
    setStoredState({
      contextKey: requestContextKey,
      error: null,
      status: 'loading',
    });

    const requestedSequenceNumber = nextSequenceNumber(
      anchorSequenceNumber,
      game.layoutCount,
    );
    void repository
      .readLayoutBySequence(game, requestedSequenceNumber)
      .then((candidate) => {
        if (
          requestNumberRef.current !== requestNumber ||
          contextKeyRef.current !== requestContextKey
        ) {
          return;
        }
        if (candidate.sequenceNumber !== requestedSequenceNumber) {
          throw new RangeError(
            'Next layout repository returned a different sequence position.',
          );
        }
        onLoad(candidate);
      })
      .catch((error: unknown) => {
        if (
          requestNumberRef.current !== requestNumber ||
          contextKeyRef.current !== requestContextKey
        ) {
          return;
        }
        setStoredState({
          contextKey: requestContextKey,
          error: asLocalDataError(error, 'Could not load next layout'),
          status: 'error',
        });
      })
      .finally(() => {
        if (requestNumberRef.current === requestNumber) {
          requestInFlightContextRef.current = null;
        }
      });
  }, [anchorSequenceNumber, contextKey, game, onLoad, repository]);

  return {
    navigate,
    state: storedState.contextKey === contextKey ? storedState : idleState(),
  };
}
