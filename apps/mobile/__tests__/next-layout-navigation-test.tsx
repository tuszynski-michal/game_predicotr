import type { SequencePayout } from '@game-predictor/shared-ts';
import type { ReactElement } from 'react';
import { Text, View } from 'react-native';
import { act, create, type ReactTestRenderer } from 'react-test-renderer';

import type { SnapshotDiagnostics } from '@/data/bundled-snapshot';
import type {
  ExactMatchResult,
  LayoutCandidate,
  LocalGameConfig,
} from '@/data/local-layout-repository';
import {
  GameWorkspaceScreen,
  type MatchingRepository,
} from '@/features/board/game-workspace-screen';
import { nextSequenceNumber } from '@/features/board/use-next-layout-navigation';

const game: LocalGameConfig = {
  code: 'game-1',
  columns: 2,
  databaseId: 1,
  datasetVersion: 1,
  id: 'game-1',
  layoutCount: 3,
  name: 'Game 1',
  rows: 1,
  rulesVersion: 1,
  signatureCellWidth: 2,
  spinCost: 10,
  symbols: [
    {
      code: 'S1',
      displayOrder: 0,
      isWildcard: false,
      mobileCode: 1,
      name: 'Symbol 1',
    },
    {
      code: 'S2',
      displayOrder: 1,
      isWildcard: false,
      mobileCode: 2,
      name: 'Symbol 2',
    },
  ],
};

const diagnostics: SnapshotDiagnostics = {
  algorithmVersion: 'payout-v2',
  databaseName: 'snapshot.db',
  datasetVersion: 1,
  fixtureVersion: 'fixture-v1',
  gameCount: 1,
  layoutCount: 3,
  logicalContentSha256: 'b'.repeat(64),
  releaseVersion: '0.3-test',
  rulesVersion: 1,
  schemaVersion: 3,
  snapshotFileSha256: 'a'.repeat(64),
};

function unique(sequenceNumber: number): ExactMatchResult {
  return {
    candidate: {
      cells: [1, 2],
      sequenceNumber,
      signature: '0102',
    },
    status: 'unique',
  };
}

function payouts(
  selectedGame: LocalGameConfig,
  startSequenceNumber: number,
): readonly SequencePayout[] {
  return Array.from(
    { length: selectedGame.layoutCount - 1 },
    (_, payoutIndex) => ({
      payoutCredits: 0,
      sequenceNumber:
        ((startSequenceNumber + payoutIndex) % selectedGame.layoutCount) + 1,
    }),
  );
}

function repository(
  findExact: MatchingRepository['findExact'],
  readLayoutBySequence: MatchingRepository['readLayoutBySequence'],
): MatchingRepository {
  return {
    findByPrefix: jest
      .fn()
      .mockResolvedValue({ candidateCount: 2, suggestion: null }),
    findExact,
    readCyclicPayouts: jest.fn(
      (
        selectedGame: LocalGameConfig,
        startSequenceNumber: number,
        _targetScanLimit: number,
      ) => Promise.resolve(payouts(selectedGame, startSequenceNumber)),
    ),
    readLayoutBySequence,
  };
}

function render(element: ReactElement): ReactTestRenderer {
  let renderer!: ReactTestRenderer;
  act(() => {
    renderer = create(element);
  });
  return renderer;
}

async function press(
  renderer: ReactTestRenderer,
  testID: string,
): Promise<void> {
  await act(async () => {
    renderer.root.findByProps({ testID }).props.onPress();
    await Promise.resolve();
  });
}

async function completeBoard(renderer: ReactTestRenderer): Promise<void> {
  await press(renderer, 'symbol-1');
  await press(renderer, 'symbol-2');
}

function visibleTestIdCount(
  renderer: ReactTestRenderer,
  testID: string,
): number {
  return renderer.root.findAll(
    (node) => node.type === View && node.props.testID === testID,
  ).length;
}

function boardCellLabels(
  renderer: ReactTestRenderer,
  cellIndex: number,
): string[] {
  return renderer.root
    .findAll(
      (node) =>
        node.type === View && node.props.testID === `board-cell-${cellIndex}`,
    )
    .map((node) => node.props.accessibilityLabel as string);
}

function resultSummaryText(renderer: ReactTestRenderer): string {
  return renderer.root
    .findByProps({ testID: 'result-summary' })
    .findAllByType(Text)
    .flatMap((node) => node.props.children)
    .join('');
}

type Deferred<T> = {
  promise: Promise<T>;
  resolve: (value: T) => void;
};

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((complete) => {
    resolve = complete;
  });
  return { promise, resolve };
}

describe('anchored Next navigation', () => {
  test('loads the exact next position, preserves duplicate content as anchored and undoes atomically', async () => {
    const findExact = jest.fn().mockResolvedValue(unique(1));
    const nextCandidate: LayoutCandidate = {
      cells: [2, 1],
      sequenceNumber: 2,
      signature: '0201',
    };
    const matchingRepository = repository(
      findExact,
      jest.fn().mockResolvedValue(nextCandidate),
    );
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={matchingRepository}
      />,
    );

    await completeBoard(renderer);
    expect(
      renderer.root.findByProps({ testID: 'next-button' }).props.disabled,
    ).toBe(false);

    await press(renderer, 'next-button');

    expect(matchingRepository.readLayoutBySequence).toHaveBeenCalledWith(
      game,
      2,
    );
    expect(findExact).toHaveBeenCalledTimes(1);
    expect(boardCellLabels(renderer, 0).join(' ')).toContain('Symbol 2');
    expect(boardCellLabels(renderer, 1).join(' ')).toContain('Symbol 1');
    expect(resultSummaryText(renderer)).toContain('Układ: 2');
    expect(matchingRepository.readCyclicPayouts).toHaveBeenCalledWith(
      game,
      2,
      10_000,
    );

    await press(renderer, 'undo-button');
    expect(boardCellLabels(renderer, 0).join(' ')).toContain('Symbol 1');
    expect(boardCellLabels(renderer, 1).join(' ')).toContain('Symbol 2');
    expect(resultSummaryText(renderer)).toContain('Układ: 1');

    act(() => renderer.unmount());
  });

  test('wraps the last sequence position to the first', async () => {
    const readLayoutBySequence = jest.fn().mockResolvedValue({
      cells: [2, 2],
      sequenceNumber: 1,
      signature: '0202',
    });
    const matchingRepository = repository(
      jest.fn().mockResolvedValue(unique(3)),
      readLayoutBySequence,
    );
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={matchingRepository}
      />,
    );

    await completeBoard(renderer);
    await press(renderer, 'next-button');

    expect(nextSequenceNumber(3, 3)).toBe(1);
    expect(readLayoutBySequence).toHaveBeenCalledWith(game, 1);
    expect(resultSummaryText(renderer)).toContain('Układ: 1');
    act(() => renderer.unmount());
  });

  test('keeps Next disabled without a unique sequence anchor', async () => {
    const readLayoutBySequence = jest.fn();
    const matchingRepository = repository(
      jest.fn().mockResolvedValue({
        occurrenceCount: 2,
        sequenceNumbers: [1, 3],
        status: 'duplicate',
      }),
      readLayoutBySequence,
    );
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={matchingRepository}
      />,
    );

    await completeBoard(renderer);

    expect(
      renderer.root.findByProps({ testID: 'next-button' }).props.disabled,
    ).toBe(true);
    expect(readLayoutBySequence).not.toHaveBeenCalled();
    act(() => renderer.unmount());
  });

  test('keeps the current board after a read error and ignores a response after Reset', async () => {
    const failedRepository = repository(
      jest.fn().mockResolvedValue(unique(1)),
      jest.fn().mockRejectedValue(new Error('SQLite read failed')),
    );
    const failedRenderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={failedRepository}
      />,
    );
    await completeBoard(failedRenderer);
    await press(failedRenderer, 'next-button');

    expect(visibleTestIdCount(failedRenderer, 'next-error')).toBeGreaterThan(0);
    expect(boardCellLabels(failedRenderer, 0).join(' ')).toContain('Symbol 1');
    act(() => failedRenderer.unmount());

    const pending = deferred<LayoutCandidate>();
    const pendingRepository = repository(
      jest.fn().mockResolvedValue(unique(1)),
      jest.fn(() => pending.promise),
    );
    const pendingRenderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={pendingRepository}
      />,
    );
    await completeBoard(pendingRenderer);
    await press(pendingRenderer, 'next-button');
    await press(pendingRenderer, 'reset-button');
    await act(async () => {
      pending.resolve({
        cells: [2, 1],
        sequenceNumber: 2,
        signature: '0201',
      });
      await pending.promise;
    });

    expect(boardCellLabels(pendingRenderer, 0).join(' ')).toContain(
      'Puste pole',
    );
    expect(visibleTestIdCount(pendingRenderer, 'prefix-idle')).toBeGreaterThan(
      0,
    );
    act(() => pendingRenderer.unmount());
  });
});
