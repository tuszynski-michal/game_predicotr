import type { ReactElement } from 'react';
import { View } from 'react-native';
import {
  act,
  create,
  type ReactTestInstance,
  type ReactTestRenderer,
} from 'react-test-renderer';

import type { SnapshotDiagnostics } from '@/data/bundled-snapshot';
import type { LocalGameConfig } from '@/data/local-layout-repository';
import { BoardGrid } from '@/features/board/board-grid';
import {
  GameWorkspaceScreen,
  type MatchingRepository,
} from '@/features/board/game-workspace-screen';
import { GameHeader } from '@/features/board/game-header';
import { SymbolSelection } from '@/features/board/symbol-selection';

const symbols = [
  {
    code: 'S1',
    displayOrder: 0,
    isWildcard: false,
    mobileCode: 1,
    name: 'Symbol 1',
  },
  {
    code: 'W',
    displayOrder: 1,
    isWildcard: true,
    mobileCode: 2,
    name: 'Wild',
  },
] as const;

const games: readonly LocalGameConfig[] = [
  {
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
    symbols,
  },
  {
    code: 'game-2',
    columns: 3,
    databaseId: 2,
    datasetVersion: 1,
    id: 'game-2',
    layoutCount: 10,
    name: 'Game 2',
    rows: 1,
    rulesVersion: 1,
    signatureCellWidth: 2,
    spinCost: 10,
    symbols,
  },
];

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
  schemaVersion: 2,
  snapshotFileSha256: 'a'.repeat(64),
};

const pendingMatchingRepository: MatchingRepository = {
  findExact: jest.fn(
    () =>
      new Promise(() => {
        // TASK-0009 component tests do not exercise matching.
      }),
  ),
  findByPrefix: jest.fn(
    () =>
      new Promise(() => {
        // TASK-0009 component tests do not exercise matching.
      }),
  ),
  readCyclicPayouts: jest.fn(
    () =>
      new Promise(() => {
        // TASK-0009 component tests do not exercise Target.
      }),
  ),
};

function render(element: ReactElement): ReactTestRenderer {
  let renderer!: ReactTestRenderer;
  act(() => {
    renderer = create(element);
  });
  return renderer;
}

function boardCells(root: ReactTestInstance): ReactTestInstance[] {
  return root.findAll(
    (node) =>
      node.type === View &&
      typeof node.props.testID === 'string' &&
      node.props.testID.startsWith('board-cell-'),
  );
}

describe('board components', () => {
  test('renders cells in stable row-major order with accessible labels', () => {
    const renderer = render(
      <BoardGrid
        cells={[1, null, 2, null]}
        columns={2}
        rows={2}
        symbols={symbols}
      />,
    );

    const cells = boardCells(renderer.root);
    expect(cells.map((cell) => cell.props.testID)).toEqual([
      'board-cell-0',
      'board-cell-1',
      'board-cell-2',
      'board-cell-3',
    ]);
    expect(cells[0]?.props.accessibilityLabel).toContain(
      'Symbol 1, wiersz 1, kolumna 1',
    );
    expect(cells[1]?.props.accessibilityLabel).toContain(
      'Puste pole, wiersz 1, kolumna 2',
    );
    expect(cells[2]?.props.accessibilityLabel).toContain(
      'Wild, wiersz 2, kolumna 1',
    );

    act(() => renderer.unmount());
  });

  test('exposes selected game and disabled Undo state without using color alone', () => {
    const renderer = render(
      <GameHeader
        canUndo={false}
        games={games}
        onReset={jest.fn()}
        onSelectGame={jest.fn()}
        onUndo={jest.fn()}
        releaseVersion="m1-test"
        selectedGameId="game-1"
      />,
    );

    expect(renderer.root.findByProps({ testID: 'undo-button' }).props).toEqual(
      expect.objectContaining({
        accessibilityLabel: 'Cofnij ostatnią operację',
        accessibilityState: { disabled: true },
        disabled: true,
      }),
    );
    expect(
      renderer.root.findByProps({ testID: 'game-option-game-1' }).props
        .accessibilityState,
    ).toEqual({ selected: true });

    act(() => renderer.unmount());
  });

  test('marks every symbol disabled on a full board and labels joker in text', () => {
    const renderer = render(
      <SymbolSelection disabled onSelectSymbol={jest.fn()} symbols={symbols} />,
    );

    expect(
      renderer.root.findByProps({ testID: 'symbol-1' }).props
        .accessibilityState,
    ).toEqual({ disabled: true });
    expect(
      renderer.root.findByProps({ testID: 'symbol-2' }).props
        .accessibilityLabel,
    ).toBe('Wild, joker');
    expect(JSON.stringify(renderer.toJSON())).toContain('JOKER');

    act(() => renderer.unmount());
  });

  test('connects symbol input, Undo, Reset and game change in one session', () => {
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={games}
        repository={pendingMatchingRepository}
      />,
    );

    expect(boardCells(renderer.root)).toHaveLength(2);
    expect(
      renderer.root.findByProps({ testID: 'undo-button' }).props.disabled,
    ).toBe(true);

    act(() => {
      renderer.root.findByProps({ testID: 'symbol-1' }).props.onPress();
    });
    expect(
      renderer.root.findByProps({ testID: 'board-cell-0' }).props
        .accessibilityLabel,
    ).toContain('Symbol 1');
    expect(
      renderer.root.findByProps({ testID: 'undo-button' }).props.disabled,
    ).toBe(false);

    act(() => {
      renderer.root.findByProps({ testID: 'undo-button' }).props.onPress();
    });
    expect(
      renderer.root.findByProps({ testID: 'board-cell-0' }).props
        .accessibilityLabel,
    ).toContain('Puste pole');

    act(() => {
      renderer.root.findByProps({ testID: 'symbol-2' }).props.onPress();
    });
    act(() => {
      renderer.root.findByProps({ testID: 'reset-button' }).props.onPress();
    });
    expect(
      renderer.root.findByProps({ testID: 'board-cell-0' }).props
        .accessibilityLabel,
    ).toContain('Puste pole');
    expect(
      renderer.root.findByProps({ testID: 'undo-button' }).props.disabled,
    ).toBe(true);

    act(() => {
      renderer.root
        .findByProps({ testID: 'game-option-game-2' })
        .props.onPress();
    });
    expect(boardCells(renderer.root)).toHaveLength(3);
    expect(
      renderer.root.findByProps({ testID: 'game-option-game-2' }).props
        .accessibilityState,
    ).toEqual({ selected: true });

    act(() => renderer.unmount());
  });
});
