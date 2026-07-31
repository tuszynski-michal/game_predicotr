import type { ForecastPeak, SequencePayout } from '@game-predictor/shared-ts';
import type { ReactElement } from 'react';
import { FlatList, ScrollView, View } from 'react-native';
import { act, create, type ReactTestRenderer } from 'react-test-renderer';

import type { SnapshotDiagnostics } from '@/data/bundled-snapshot';
import type { LocalGameConfig } from '@/data/local-layout-repository';
import {
  GameWorkspaceScreen,
  type MatchingRepository,
} from '@/features/board/game-workspace-screen';
import {
  TargetPeakRow,
  targetPeakKey,
} from '@/features/target/target-peak-row';

const symbols = [
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
] as const;

const diagnostics: SnapshotDiagnostics = {
  algorithmVersion: 'target-v1',
  databaseName: 'snapshot.db',
  datasetVersion: 1,
  fixtureVersion: 'fixture-v1',
  gameCount: 1,
  layoutCount: 8,
  logicalContentSha256: 'b'.repeat(64),
  releaseVersion: 'm1-test',
  rulesVersion: 1,
  schemaVersion: 2,
  snapshotFileSha256: 'a'.repeat(64),
};

function gameWithLayoutCount(layoutCount: number): LocalGameConfig {
  return {
    code: 'game-1',
    columns: 2,
    databaseId: 1,
    datasetVersion: 1,
    id: 'game-1',
    layoutCount,
    name: 'Game 1',
    rows: 1,
    rulesVersion: 1,
    signatureCellWidth: 2,
    spinCost: 10,
    symbols,
  };
}

function repository(
  payouts: readonly SequencePayout[],
  startSequenceNumber = 2,
): MatchingRepository {
  return {
    findByPrefix: jest
      .fn()
      .mockResolvedValue({ candidateCount: 2, suggestion: null }),
    findExact: jest.fn().mockResolvedValue({
      candidate: {
        cells: [1, 2],
        sequenceNumber: startSequenceNumber,
        signature: '0102',
      },
      status: 'unique',
    }),
    readCyclicPayouts: jest.fn().mockResolvedValue(payouts),
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

function visibleRowIds(renderer: ReactTestRenderer): string[] {
  return renderer.root
    .findAll(
      (node) =>
        node.type === View &&
        typeof node.props.testID === 'string' &&
        node.props.testID.startsWith('target-peak-row-'),
    )
    .map((node) => node.props.testID as string);
}

describe('Target results table', () => {
  test('renders all six required values and a complete accessibility label', () => {
    const peak: ForecastPeak = {
      cumulativeCost: 120,
      cumulativePayout: 300,
      netCredits: 180,
      sequenceNumber: 111,
      spinNumber: 12,
      spinPayout: 100,
    };
    const renderer = render(<TargetPeakRow peak={peak} />);
    const row = renderer.root.find(
      (node) =>
        node.type === View && node.props.testID === 'target-peak-row-12',
    );
    const output = JSON.stringify(renderer.toJSON());

    expect(output).toContain('Spin');
    expect(output).toContain('Layout');
    expect(output).toContain('Payout spinu');
    expect(output).toContain('Payout łącznie');
    expect(output).toContain('Koszt łącznie');
    expect(output).toContain('Wynik netto');
    expect(row.props.accessibilityLabel).toContain('spinie 12');
    expect(row.props.accessibilityLabel).toContain('layout 111');
    expect(row.props.accessibilityLabel).toContain('wynik netto 180');
    expect(targetPeakKey(peak)).toBe('12:111');

    act(() => renderer.unmount());
  });

  test('shows the first plateau spin and a later lower local peak in domain order', async () => {
    const game = gameWithLayoutCount(8);
    const payouts: readonly SequencePayout[] = [
      { payoutCredits: 20, sequenceNumber: 3 },
      { payoutCredits: 25, sequenceNumber: 4 },
      { payoutCredits: 10, sequenceNumber: 5 },
      { payoutCredits: 0, sequenceNumber: 6 },
      { payoutCredits: 13, sequenceNumber: 7 },
      { payoutCredits: 10, sequenceNumber: 8 },
      { payoutCredits: 0, sequenceNumber: 1 },
    ];
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={repository(payouts)}
      />,
    );

    await completeBoard(renderer);

    expect(visibleRowIds(renderer)).toEqual([
      'target-peak-row-2',
      'target-peak-row-5',
    ]);
    expect(visibleRowIds(renderer)).not.toContain('target-peak-row-3');
    expect(visibleRowIds(renderer)).not.toContain('target-peak-row-6');
    expect(
      renderer.root.findByProps({ testID: 'target-peak-row-2' }).props
        .accessibilityLabel,
    ).toContain('wynik netto 25');
    expect(
      renderer.root.findByProps({ testID: 'target-peak-row-5' }).props
        .accessibilityLabel,
    ).toContain('wynik netto 18');

    act(() => renderer.unmount());
  });

  test('matches the 999-spin M1 golden with a later lower peak and first plateau item', async () => {
    const game = gameWithLayoutCount(1000);
    const startSequenceNumber = 99;
    const payouts = Array.from({ length: 999 }, (_, payoutIndex) => {
      let payoutCredits = 0;
      if (payoutIndex === 0) {
        payoutCredits = 200;
      } else if (payoutIndex === 11) {
        payoutCredits = 100;
      } else if (payoutIndex === 12) {
        payoutCredits = 10;
      }
      return {
        payoutCredits,
        sequenceNumber:
          ((startSequenceNumber + payoutIndex) % game.layoutCount) + 1,
      };
    });
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={repository(payouts, startSequenceNumber)}
      />,
    );

    await completeBoard(renderer);

    expect(visibleRowIds(renderer)).toEqual([
      'target-peak-row-1',
      'target-peak-row-12',
    ]);
    expect(
      renderer.root.findByProps({ testID: 'target-peak-row-1' }).props
        .accessibilityLabel,
    ).toContain('layout 100');
    expect(
      renderer.root.findByProps({ testID: 'target-peak-row-1' }).props
        .accessibilityLabel,
    ).toContain('wynik netto 190');
    expect(
      renderer.root.findByProps({ testID: 'target-peak-row-12' }).props
        .accessibilityLabel,
    ).toContain('layout 111');
    expect(
      renderer.root.findByProps({ testID: 'target-peak-row-12' }).props
        .accessibilityLabel,
    ).toContain('wynik netto 180');
    expect(
      renderer.root.findByProps({ testID: 'target-final-payout' }).props,
    ).toBeDefined();
    expect(JSON.stringify(renderer.toJSON())).toContain('9990');
    expect(JSON.stringify(renderer.toJSON())).toContain('-9680');

    act(() => renderer.unmount());
  });

  test('shows an explicit empty state when no peak is strictly positive', async () => {
    const game = gameWithLayoutCount(5);
    const payouts: readonly SequencePayout[] = [
      { payoutCredits: 0, sequenceNumber: 3 },
      { payoutCredits: 0, sequenceNumber: 4 },
      { payoutCredits: 0, sequenceNumber: 5 },
      { payoutCredits: 0, sequenceNumber: 1 },
    ];
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={repository(payouts)}
      />,
    );

    await completeBoard(renderer);

    expect(
      renderer.root.findAllByProps({ testID: 'target-results-empty' }).length,
    ).toBeGreaterThan(0);
    expect(visibleRowIds(renderer)).toEqual([]);
    expect(JSON.stringify(renderer.toJSON())).toContain(
      'wyniku netto większego od zera',
    );

    act(() => renderer.unmount());
  });

  test('uses one vertical FlatList and keeps the symbol scroller horizontal', () => {
    const game = gameWithLayoutCount(5);
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={repository([])}
      />,
    );
    const lists = renderer.root.findAllByType(FlatList);
    const scrollViews = renderer.root.findAllByType(ScrollView);
    const resultList = renderer.root.findByProps({
      testID: 'target-results-list',
    });

    expect(lists).toHaveLength(1);
    expect(resultList.props.initialNumToRender).toBe(8);
    expect(resultList.props.maxToRenderPerBatch).toBe(8);
    expect(resultList.props.windowSize).toBe(5);
    expect(resultList.props.removeClippedSubviews).toBe(true);
    expect(
      scrollViews
        .filter(
          (scrollView) => scrollView.props.testID !== 'target-results-list',
        )
        .every((scrollView) => scrollView.props.horizontal === true),
    ).toBe(true);

    act(() => renderer.unmount());
  });

  test('does not mount every row of a long result at once', async () => {
    const game = gameWithLayoutCount(201);
    const payouts = Array.from({ length: 200 }, (_, payoutIndex) => ({
      payoutCredits: payoutIndex % 2 === 0 ? 20 : 0,
      sequenceNumber: ((2 + payoutIndex) % 201) + 1,
    }));
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={repository(payouts)}
      />,
    );

    await completeBoard(renderer);

    const mountedRowCount = visibleRowIds(renderer).length;
    expect(mountedRowCount).toBeGreaterThan(0);
    expect(mountedRowCount).toBeLessThan(100);
    expect(
      renderer.root.findByProps({ testID: 'target-results-list' }).props.data,
    ).toHaveLength(100);

    act(() => renderer.unmount());
  });
});
