import type { ReactElement } from 'react';
import { View } from 'react-native';
import { act, create, type ReactTestRenderer } from 'react-test-renderer';

import type { SnapshotDiagnostics } from '@/data/bundled-snapshot';
import type {
  LocalGameConfig,
  PrefixMatchResult,
} from '@/data/local-layout-repository';
import {
  GameWorkspaceScreen,
  type MatchingRepository,
} from '@/features/board/game-workspace-screen';
import type { PrefixMatchRepository } from '@/features/board/use-prefix-matching';

const game: LocalGameConfig = {
  code: 'game-1',
  columns: 3,
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
  gameCount: 1,
  layoutCount: 10,
  logicalContentSha256: 'b'.repeat(64),
  releaseVersion: 'm1-test',
  rulesVersion: 1,
  schemaVersion: 2,
  snapshotFileSha256: 'a'.repeat(64),
};

const uniqueSuggestion = {
  cells: [1, 2, 1],
  kind: 'unique',
  occurrenceCount: 1,
  sequenceNumber: 42,
  signature: '010201',
} as const;

const duplicateSuggestion = {
  cells: [1, 2, 1],
  kind: 'duplicate',
  occurrenceCount: 3,
  sequenceNumber: null,
  signature: '010201',
} as const;

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

function modalCount(renderer: ReactTestRenderer): number {
  return renderer.root.findAll(
    (node) => node.type === View && node.props.testID === 'candidate-modal',
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

function withExact(repository: PrefixMatchRepository): MatchingRepository {
  return {
    ...repository,
    findExact: jest.fn().mockResolvedValue({ status: 'not_found' }),
    readCyclicPayouts: jest.fn().mockResolvedValue([]),
  };
}

describe('prefix matching flow', () => {
  test('skips the empty board and opens an accessible modal for one longer candidate', async () => {
    const repository: PrefixMatchRepository = {
      findByPrefix: jest.fn().mockResolvedValue({
        candidateCount: 1,
        suggestion: uniqueSuggestion,
      }),
    };
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={withExact(repository)}
      />,
    );

    expect(repository.findByPrefix).not.toHaveBeenCalled();
    expect(renderer.root.findByProps({ testID: 'prefix-idle' })).toBeDefined();

    await press(renderer, 'symbol-1');

    expect(repository.findByPrefix).toHaveBeenCalledWith(game, '01');
    expect(modalCount(renderer)).toBe(1);
    expect(JSON.stringify(renderer.toJSON())).toContain('Numer sekwencji: ');
    expect(JSON.stringify(renderer.toJSON())).toContain('42');
    expect(
      renderer.root.findByProps({ testID: 'candidate-accept-button' }).props
        .accessibilityLabel,
    ).toBe('Akceptuj i uzupełnij planszę');
    expect(
      renderer.root.findByProps({ testID: 'candidate-close-button' }).props
        .accessibilityLabel,
    ).toContain('bez zmiany planszy');

    act(() => renderer.unmount());
  });

  test('accepts completion as one Undo operation', async () => {
    const repository: PrefixMatchRepository = {
      findByPrefix: jest.fn().mockResolvedValue({
        candidateCount: 1,
        suggestion: uniqueSuggestion,
      }),
    };
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={withExact(repository)}
      />,
    );
    await press(renderer, 'symbol-1');
    await press(renderer, 'candidate-accept-button');

    expect(
      boardCellLabels(renderer, 0).some((label) => label.includes('Symbol 1')),
    ).toBe(true);
    expect(
      boardCellLabels(renderer, 1).some((label) => label.includes('Symbol 2')),
    ).toBe(true);
    expect(modalCount(renderer)).toBe(0);

    await press(renderer, 'undo-button');

    expect(
      boardCellLabels(renderer, 0).some((label) => label.includes('Symbol 1')),
    ).toBe(true);
    expect(
      boardCellLabels(renderer, 1).some((label) =>
        label.includes('Puste pole'),
      ),
    ).toBe(true);

    act(() => renderer.unmount());
  });

  test('suggests one shared duplicate layout without selecting a sequence or running Target', async () => {
    const readCyclicPayouts = jest.fn().mockResolvedValue([]);
    const repository: MatchingRepository = {
      findByPrefix: jest.fn().mockResolvedValue({
        candidateCount: 3,
        suggestion: duplicateSuggestion,
      }),
      findExact: jest.fn().mockResolvedValue({
        occurrenceCount: 3,
        sequenceNumbers: [4, 7, 9],
        status: 'duplicate',
      }),
      readCyclicPayouts,
    };
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={repository}
      />,
    );

    await press(renderer, 'symbol-1');

    const renderedSuggestion = JSON.stringify(renderer.toJSON());
    expect(renderedSuggestion).toContain('DUPLIKAT LAYOUTU');
    expect(
      renderer.root.findByProps({ testID: 'duplicate-candidate-summary' }).props
        .children,
    ).toEqual(['Identyczny layout występuje ', 3, ' razy.']);
    expect(renderedSuggestion).not.toContain('Numer sekwencji');

    await press(renderer, 'candidate-accept-button');

    expect(JSON.stringify(renderer.toJSON())).toContain('Duplikat layoutu');
    expect(readCyclicPayouts).not.toHaveBeenCalled();

    await press(renderer, 'undo-button');
    expect(
      boardCellLabels(renderer, 1).some((label) =>
        label.includes('Puste pole'),
      ),
    ).toBe(true);

    act(() => renderer.unmount());
  });

  test('closing does not change cells or reopen for the same prefix', async () => {
    const findByPrefix = jest
      .fn<Promise<PrefixMatchResult>, [LocalGameConfig, string]>()
      .mockResolvedValue({
        candidateCount: 1,
        suggestion: uniqueSuggestion,
      });
    const repository: PrefixMatchRepository = { findByPrefix };
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={withExact(repository)}
      />,
    );
    await press(renderer, 'symbol-1');
    await press(renderer, 'candidate-close-button');

    expect(modalCount(renderer)).toBe(0);
    expect(findByPrefix).toHaveBeenCalledTimes(1);
    expect(
      boardCellLabels(renderer, 1).some((label) =>
        label.includes('Puste pole'),
      ),
    ).toBe(true);

    await press(renderer, 'symbol-2');

    expect(findByPrefix).toHaveBeenLastCalledWith(game, '0102');
    expect(modalCount(renderer)).toBe(1);

    act(() => renderer.unmount());
  });

  test('does not open a modal for zero or many candidates', async () => {
    const findByPrefix = jest
      .fn<Promise<PrefixMatchResult>, [LocalGameConfig, string]>()
      .mockResolvedValueOnce({ candidateCount: 0, suggestion: null })
      .mockResolvedValueOnce({ candidateCount: 7, suggestion: null });
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={withExact({ findByPrefix })}
      />,
    );

    await press(renderer, 'symbol-1');
    expect(modalCount(renderer)).toBe(0);
    expect(JSON.stringify(renderer.toJSON())).toContain('0');

    await press(renderer, 'symbol-2');
    expect(modalCount(renderer)).toBe(0);
    expect(JSON.stringify(renderer.toJSON())).toContain('7');

    act(() => renderer.unmount());
  });

  test('reset and game change remove the visible candidate and old prefix state', async () => {
    const findByPrefix = jest
      .fn<Promise<PrefixMatchResult>, [LocalGameConfig, string]>()
      .mockResolvedValue({
        candidateCount: 1,
        suggestion: uniqueSuggestion,
      });
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game, secondGame]}
        repository={withExact({ findByPrefix })}
      />,
    );

    await press(renderer, 'symbol-1');
    expect(modalCount(renderer)).toBe(1);

    await press(renderer, 'reset-button');
    expect(modalCount(renderer)).toBe(0);
    expect(
      renderer.root.findAllByProps({ testID: 'prefix-idle' }).length,
    ).toBeGreaterThan(0);
    expect(findByPrefix).toHaveBeenCalledTimes(1);

    await press(renderer, 'symbol-1');
    expect(modalCount(renderer)).toBe(1);
    await press(renderer, 'game-option-game-2');
    expect(modalCount(renderer)).toBe(0);
    expect(findByPrefix).toHaveBeenCalledTimes(2);

    await press(renderer, 'symbol-1');
    expect(findByPrefix).toHaveBeenLastCalledWith(secondGame, '01');

    act(() => renderer.unmount());
  });

  test('ignores an older response that resolves after a newer prefix', async () => {
    const first = deferred<PrefixMatchResult>();
    const second = deferred<PrefixMatchResult>();
    const findByPrefix = jest
      .fn<Promise<PrefixMatchResult>, [LocalGameConfig, string]>()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={withExact({ findByPrefix })}
      />,
    );

    act(() => {
      renderer.root.findByProps({ testID: 'symbol-1' }).props.onPress();
    });
    act(() => {
      renderer.root.findByProps({ testID: 'symbol-2' }).props.onPress();
    });
    expect(findByPrefix).toHaveBeenNthCalledWith(1, game, '01');
    expect(findByPrefix).toHaveBeenNthCalledWith(2, game, '0102');

    await act(async () => {
      second.resolve({
        candidateCount: 1,
        suggestion: {
          ...uniqueSuggestion,
          sequenceNumber: 22,
        },
      });
      await second.promise;
    });
    expect(JSON.stringify(renderer.toJSON())).toContain('22');

    await act(async () => {
      first.resolve({
        candidateCount: 1,
        suggestion: {
          ...uniqueSuggestion,
          sequenceNumber: 11,
        },
      });
      await first.promise;
    });
    expect(JSON.stringify(renderer.toJSON())).toContain('22');
    expect(JSON.stringify(renderer.toJSON())).not.toContain(
      'Numer sekwencji: 11',
    );

    act(() => renderer.unmount());
  });

  test('shows local_data_error and disables selection on repository failure', async () => {
    const repository: PrefixMatchRepository = {
      findByPrefix: jest
        .fn()
        .mockRejectedValue(new Error('SQLite read failed')),
    };
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={withExact(repository)}
      />,
    );

    await press(renderer, 'symbol-1');

    expect(renderer.root.findByProps({ testID: 'prefix-error' })).toBeDefined();
    expect(JSON.stringify(renderer.toJSON())).toContain('local_data_error');
    expect(
      renderer.root.findByProps({ testID: 'symbol-2' }).props.disabled,
    ).toBe(true);

    act(() => renderer.unmount());
  });
});
