import type { ReactElement } from 'react';
import { View } from 'react-native';
import { act, create, type ReactTestRenderer } from 'react-test-renderer';

import type { SnapshotDiagnostics } from '@/data/bundled-snapshot';
import type {
  ExactMatchResult,
  LocalGameConfig,
} from '@/data/local-layout-repository';
import {
  GameWorkspaceScreen,
  type MatchingRepository,
} from '@/features/board/game-workspace-screen';

const game: LocalGameConfig = {
  code: 'game-1',
  columns: 2,
  databaseId: 1,
  datasetVersion: 1,
  id: 'game-1',
  layoutCount: 10,
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

const secondGame: LocalGameConfig = {
  ...game,
  code: 'game-2',
  databaseId: 2,
  id: 'game-2',
  name: 'Game 2',
};

const diagnostics: SnapshotDiagnostics = {
  algorithmVersion: 'payout-v2',
  databaseName: 'snapshot.db',
  datasetVersion: 1,
  fixtureVersion: 'fixture-v1',
  gameCount: 2,
  layoutCount: 20,
  logicalContentSha256: 'b'.repeat(64),
  releaseVersion: 'm1-test',
  rulesVersion: 1,
  schemaVersion: 3,
  snapshotFileSha256: 'a'.repeat(64),
};

const uniqueResult = (sequenceNumber: number): ExactMatchResult => ({
  candidate: {
    cells: [1, 2],
    sequenceNumber,
    signature: '0102',
  },
  status: 'unique',
});

function matchingRepository(
  findExact: MatchingRepository['findExact'],
): MatchingRepository {
  return {
    findByPrefix: jest
      .fn()
      .mockResolvedValue({ candidateCount: 2, suggestion: null }),
    findExact,
    readCyclicPayouts: jest.fn(
      (selectedGame: LocalGameConfig, startSequenceNumber: number) =>
        Promise.resolve(
          Array.from(
            { length: selectedGame.layoutCount - 1 },
            (_, payoutIndex) => ({
              payoutCredits: 0,
              sequenceNumber:
                ((startSequenceNumber + payoutIndex) %
                  selectedGame.layoutCount) +
                1,
            }),
          ),
        ),
    ),
    readLayoutBySequence: jest
      .fn()
      .mockRejectedValue(
        new Error('Next navigation is not used in this test.'),
      ),
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

describe('exact matching flow', () => {
  test('uses prefix matching only for a partial board and exact matching for a full board', async () => {
    const exact = deferred<ExactMatchResult>();
    const repository = matchingRepository(jest.fn(() => exact.promise));
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={repository}
      />,
    );

    await press(renderer, 'symbol-1');
    expect(repository.findByPrefix).toHaveBeenCalledWith(game, '01');
    expect(repository.findExact).not.toHaveBeenCalled();
    expect(
      renderer.root.findByProps({ testID: 'next-button' }).props.disabled,
    ).toBe(true);

    await press(renderer, 'symbol-2');
    expect(repository.findByPrefix).toHaveBeenCalledTimes(1);
    expect(repository.findExact).toHaveBeenCalledWith(game, '0102');
    expect(visibleTestIdCount(renderer, 'result-summary')).toBe(1);
    expect(JSON.stringify(renderer.toJSON())).toContain('Wyszukiwanie układu');

    await act(async () => {
      exact.resolve(uniqueResult(7));
      await exact.promise;
    });
    act(() => renderer.unmount());
  });

  test('shows the deterministic sequence number and starts Target for a unique match', async () => {
    const repository = matchingRepository(
      jest.fn().mockResolvedValue(uniqueResult(7)),
    );
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={repository}
      />,
    );

    await press(renderer, 'symbol-1');
    await press(renderer, 'symbol-2');

    expect(visibleTestIdCount(renderer, 'result-summary')).toBe(1);
    const output = JSON.stringify(renderer.toJSON());
    expect(output).toContain('Układ znaleziony i obliczony');
    expect(output).not.toContain('Target obliczony');
    expect(output).not.toContain('Jednoznaczny układ uruchamia');
    expect(output).toContain('Układ: ');
    expect(output).toContain('7');
    expect(repository.readCyclicPayouts).toHaveBeenCalledWith(game, 7, 10_000);

    act(() => renderer.unmount());
  });

  test('shows duplicate diagnostics, never selects a sequence, and Reset clears the result', async () => {
    const repository = matchingRepository(
      jest.fn().mockResolvedValue({
        occurrenceCount: 2,
        sequenceNumbers: [2, 8],
        status: 'duplicate',
      }),
    );
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={repository}
      />,
    );

    await press(renderer, 'symbol-1');
    await press(renderer, 'symbol-2');

    expect(visibleTestIdCount(renderer, 'result-summary')).toBe(1);
    const duplicateOutput = JSON.stringify(renderer.toJSON());
    expect(duplicateOutput).toContain('Duplikat layoutu');
    expect(duplicateOutput).toContain('Liczba wystąpień: ');
    expect(duplicateOutput).toContain('Pozycje: ');
    expect(duplicateOutput).toContain('2, 8');
    expect(duplicateOutput).not.toContain('Układ: ');
    expect(
      renderer.root.findByProps({ testID: 'next-button' }).props.disabled,
    ).toBe(true);

    await press(renderer, 'reset-button');
    expect(visibleTestIdCount(renderer, 'result-summary')).toBe(0);
    expect(visibleTestIdCount(renderer, 'prefix-idle')).toBeGreaterThan(0);
    expect(repository.findExact).toHaveBeenCalledTimes(1);

    act(() => renderer.unmount());
  });

  test('explains when duplicate sequence diagnostics exceed their limit', async () => {
    const repository = matchingRepository(
      jest.fn().mockResolvedValue({
        occurrenceCount: 25,
        sequenceNumbers: null,
        status: 'duplicate',
      }),
    );
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={repository}
      />,
    );

    await press(renderer, 'symbol-1');
    await press(renderer, 'symbol-2');

    expect(JSON.stringify(renderer.toJSON())).toContain(
      'Lista pozycji przekracza limit diagnostyczny',
    );
    act(() => renderer.unmount());
  });

  test('keeps a not-found board visible and allows Undo', async () => {
    const repository = matchingRepository(
      jest.fn().mockResolvedValue({ status: 'not_found' }),
    );
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={repository}
      />,
    );

    await press(renderer, 'symbol-1');
    await press(renderer, 'symbol-2');

    expect(visibleTestIdCount(renderer, 'result-summary')).toBe(1);
    expect(JSON.stringify(renderer.toJSON())).toContain(
      'Nie znaleziono layoutu',
    );
    expect(
      boardCellLabels(renderer, 1).some((label) => label.includes('Symbol 2')),
    ).toBe(true);
    expect(
      renderer.root.findByProps({ testID: 'undo-button' }).props.disabled,
    ).toBe(false);
    expect(
      renderer.root.findByProps({ testID: 'next-button' }).props.disabled,
    ).toBe(true);

    await press(renderer, 'undo-button');
    expect(visibleTestIdCount(renderer, 'result-summary')).toBe(0);
    expect(
      boardCellLabels(renderer, 1).some((label) =>
        label.includes('Puste pole'),
      ),
    ).toBe(true);

    act(() => renderer.unmount());
  });

  test('shows local_data_error without clearing a full board', async () => {
    const repository = matchingRepository(
      jest.fn().mockRejectedValue(new Error('SQLite read failed')),
    );
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={repository}
      />,
    );

    await press(renderer, 'symbol-1');
    await press(renderer, 'symbol-2');

    expect(visibleTestIdCount(renderer, 'result-summary')).toBe(1);
    expect(JSON.stringify(renderer.toJSON())).toContain(
      'Błąd danych lokalnych',
    );
    expect(JSON.stringify(renderer.toJSON())).toContain('local_data_error');
    expect(
      boardCellLabels(renderer, 1).some((label) => label.includes('Symbol 2')),
    ).toBe(true);
    expect(
      renderer.root.findByProps({ testID: 'next-button' }).props.disabled,
    ).toBe(true);

    act(() => renderer.unmount());
  });

  test('ignores an old exact response after Undo and a different complete board', async () => {
    const first = deferred<ExactMatchResult>();
    const second = deferred<ExactMatchResult>();
    const findExact = jest
      .fn<Promise<ExactMatchResult>, [LocalGameConfig, string]>()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const repository = matchingRepository(findExact);
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={repository}
      />,
    );

    await press(renderer, 'symbol-1');
    await press(renderer, 'symbol-2');
    await press(renderer, 'undo-button');
    await press(renderer, 'symbol-1');
    expect(findExact).toHaveBeenNthCalledWith(2, game, '0101');

    await act(async () => {
      second.resolve({
        candidate: {
          cells: [1, 1],
          sequenceNumber: 2,
          signature: '0101',
        },
        status: 'unique',
      });
      await second.promise;
    });
    expect(JSON.stringify(renderer.toJSON())).toContain('2');

    await act(async () => {
      first.resolve(uniqueResult(3));
      await first.promise;
    });
    expect(JSON.stringify(renderer.toJSON())).toContain('2');
    expect(JSON.stringify(renderer.toJSON())).not.toContain('Układ: 3');

    act(() => renderer.unmount());
  });

  test('changing the game clears a visible exact result and starts with an empty board', async () => {
    const repository = matchingRepository(
      jest.fn().mockResolvedValue(uniqueResult(4)),
    );
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game, secondGame]}
        repository={repository}
      />,
    );

    await press(renderer, 'symbol-1');
    await press(renderer, 'symbol-2');
    expect(visibleTestIdCount(renderer, 'result-summary')).toBe(1);

    await press(renderer, 'game-option-game-2');
    expect(visibleTestIdCount(renderer, 'result-summary')).toBe(0);
    expect(visibleTestIdCount(renderer, 'prefix-idle')).toBeGreaterThan(0);
    expect(
      boardCellLabels(renderer, 0).some((label) =>
        label.includes('Puste pole'),
      ),
    ).toBe(true);

    act(() => renderer.unmount());
  });
});
