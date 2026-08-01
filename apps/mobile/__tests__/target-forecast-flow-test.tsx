import type { SequencePayout } from '@game-predictor/shared-ts';
import type { ReactElement } from 'react';
import { Text, TextInput, View } from 'react-native';
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
import { calculateSnapshotTargetForecast } from '@/features/target/use-target-forecast';
import { parseTargetScanLimit } from '@/features/target/target-scan-limit-input';

const game: LocalGameConfig = {
  code: 'game-1',
  columns: 2,
  databaseId: 1,
  datasetVersion: 3,
  id: 'game-1',
  layoutCount: 5,
  name: 'Game 1',
  rows: 1,
  rulesVersion: 4,
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
  algorithmVersion: 'target-v1',
  databaseName: 'snapshot.db',
  datasetVersion: 3,
  fixtureVersion: 'fixture-v1',
  gameCount: 1,
  layoutCount: 5,
  logicalContentSha256: 'b'.repeat(64),
  releaseVersion: 'm1-test',
  rulesVersion: 4,
  schemaVersion: 3,
  snapshotFileSha256: 'a'.repeat(64),
};

const secondGame: LocalGameConfig = {
  ...game,
  code: 'game-2',
  databaseId: 2,
  id: 'game-2',
  name: 'Game 2',
};

const payoutsFromTwo: readonly SequencePayout[] = [
  { payoutCredits: 20, sequenceNumber: 3 },
  { payoutCredits: 20, sequenceNumber: 4 },
  { payoutCredits: 0, sequenceNumber: 5 },
  { payoutCredits: 0, sequenceNumber: 1 },
];

function uniqueResult(
  sequenceNumber: number,
  cells: readonly number[] = [1, 2],
  signature = '0102',
): ExactMatchResult {
  return {
    candidate: { cells, sequenceNumber, signature },
    status: 'unique',
  };
}

function repository(
  findExact: MatchingRepository['findExact'],
  readCyclicPayouts: MatchingRepository['readCyclicPayouts'],
): MatchingRepository {
  return {
    findByPrefix: jest
      .fn()
      .mockResolvedValue({ candidateCount: 2, suggestion: null }),
    findExact,
    readCyclicPayouts,
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

async function changeText(
  renderer: ReactTestRenderer,
  testID: string,
  value: string,
): Promise<void> {
  await act(async () => {
    renderer.root.findByProps({ testID }).props.onChangeText(value);
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

function testIdCount(renderer: ReactTestRenderer, testID: string): number {
  return renderer.root.findAll((node) => node.props.testID === testID).length;
}

function summaryValue(renderer: ReactTestRenderer, testID: string): string {
  const item = renderer.root.find(
    (node) => node.type === View && node.props.testID === testID,
  );
  return item
    .findAllByType(Text)
    .flatMap((node) => node.props.children)
    .join(' ');
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

describe('Target forecast integration', () => {
  test('accepts exact production limits and rejects incomplete drafts', () => {
    expect(parseTargetScanLimit('1000')).toBe(1_000);
    expect(parseTargetScanLimit('12345')).toBe(12_345);
    expect(parseTargetScanLimit('500000')).toBe(500_000);
    for (const value of ['', '999', '500001', '1.5', 'abc']) {
      expect(parseTargetScanLimit(value)).toBeNull();
    }
  });

  test('passes verified release and game metadata to the shared full-cycle engine', () => {
    const result = calculateSnapshotTargetForecast(
      game,
      2,
      500_000,
      diagnostics,
      payoutsFromTwo,
    );

    expect(result).toEqual(
      expect.objectContaining({
        algorithmVersion: 'target-v1',
        datasetVersion: 3,
        evaluatedSpinCount: 4,
        finalCumulativeCost: 40,
        finalCumulativePayout: 40,
        finalNetCredits: 0,
        mobileReleaseVersion: 'm1-test',
        rulesVersion: 4,
        snapshotChecksum: 'b'.repeat(64),
        spinCost: 10,
        startSequenceNumber: 2,
      }),
    );
    expect(result.positiveLocalPeaks).toEqual([
      {
        cumulativeCost: 20,
        cumulativePayout: 40,
        netCredits: 20,
        sequenceNumber: 4,
        spinNumber: 2,
        spinPayout: 20,
      },
    ]);
  });

  test('calculates only the requested bounded window', () => {
    const result = calculateSnapshotTargetForecast(
      game,
      2,
      2,
      diagnostics,
      payoutsFromTwo.slice(0, 2),
    );

    expect(result).toEqual(
      expect.objectContaining({
        evaluatedSpinCount: 2,
        finalCumulativeCost: 20,
        finalCumulativePayout: 40,
        finalNetCredits: 20,
        targetScanLimit: 2,
      }),
    );
  });

  test('evaluates the M1 fixture shape as exactly 999 spins without revisiting spin 0', () => {
    const fixtureGame = {
      ...game,
      datasetVersion: 1,
      layoutCount: 1000,
      rulesVersion: 1,
    };
    const startSequenceNumber = 200;
    const sequencePayouts = Array.from({ length: 999 }, (_, payoutIndex) => ({
      payoutCredits: 0,
      sequenceNumber:
        ((startSequenceNumber + payoutIndex) % fixtureGame.layoutCount) + 1,
    }));

    const result = calculateSnapshotTargetForecast(
      fixtureGame,
      startSequenceNumber,
      500_000,
      diagnostics,
      sequencePayouts,
    );

    expect(sequencePayouts[0]?.sequenceNumber).toBe(201);
    expect(sequencePayouts.at(-1)?.sequenceNumber).toBe(199);
    expect(sequencePayouts).not.toContainEqual(
      expect.objectContaining({ sequenceNumber: startSequenceNumber }),
    );
    expect(result.evaluatedSpinCount).toBe(999);
    expect(result.finalCumulativeCost).toBe(9990);
    expect(result.finalCumulativePayout).toBe(0);
    expect(result.finalNetCredits).toBe(-9990);
    expect(result.positiveLocalPeaks).toEqual([]);
  });

  test('shows loading and a full-cycle summary after a unique exact match', async () => {
    const payoutRequest = deferred<readonly SequencePayout[]>();
    const readCyclicPayouts = jest.fn(() => payoutRequest.promise);
    const matching = repository(
      jest.fn().mockResolvedValue(uniqueResult(2)),
      readCyclicPayouts,
    );
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={matching}
      />,
    );

    await completeBoard(renderer);

    expect(readCyclicPayouts).toHaveBeenCalledTimes(1);
    expect(readCyclicPayouts).toHaveBeenCalledWith(game, 2, 10_000);
    expect(testIdCount(renderer, 'result-status-loading')).toBeGreaterThan(0);

    await act(async () => {
      payoutRequest.resolve(payoutsFromTwo);
      await payoutRequest.promise;
    });

    expect(testIdCount(renderer, 'result-status-success')).toBeGreaterThan(0);
    expect(visibleTestIdCount(renderer, 'result-summary')).toBe(1);
    expect(visibleTestIdCount(renderer, 'result-details')).toBe(0);
    const collapsedOutput = JSON.stringify(renderer.toJSON());
    expect(collapsedOutput).toContain('Układ znaleziony i obliczony');
    expect(collapsedOutput).not.toContain('Target obliczony');
    expect(collapsedOutput).not.toContain('Ocenione spiny');
    expect(collapsedOutput).not.toContain('Łączny payout');
    expect(collapsedOutput).not.toContain('Dodatnie szczyty');
    expect(collapsedOutput).not.toContain(
      'Szczegółowe dodatnie lokalne maksima znajdują się w tabeli poniżej',
    );
    expect(
      renderer.root.findByProps({ testID: 'result-details-toggle' }).props
        .accessibilityState,
    ).toEqual({ expanded: false });

    await press(renderer, 'result-details-toggle');

    expect(
      renderer.root.findByProps({ testID: 'result-details-toggle' }).props
        .accessibilityState,
    ).toEqual({ expanded: true });
    expect(summaryValue(renderer, 'target-spin-cost')).toContain('10');
    expect(summaryValue(renderer, 'target-final-cost')).toContain('40');
    expect(summaryValue(renderer, 'target-final-net')).toContain('0');
    const expandedOutput = JSON.stringify(renderer.toJSON());
    expect(expandedOutput).toContain('Koszt spinu');
    expect(expandedOutput).toContain('Koszt');
    expect(expandedOutput).toContain('Suma końcowa');
    expect(expandedOutput).not.toContain('Ocenione spiny');
    expect(expandedOutput).not.toContain('Łączny payout');
    expect(expandedOutput).not.toContain('Dodatnie szczyty');
    expect(expandedOutput).not.toContain('Wynik końcowy');
    expect(
      visibleTestIdCount(renderer, 'target-results-header'),
    ).toBeGreaterThan(0);
    expect(visibleTestIdCount(renderer, 'target-peak-row-2')).toBeGreaterThan(
      0,
    );

    act(() => renderer.unmount());
  }, 15_000);

  test('validates the production input and recalculates with a new exact limit', async () => {
    const readCyclicPayouts = jest.fn().mockResolvedValue(payoutsFromTwo);
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={repository(
          jest.fn().mockResolvedValue(uniqueResult(2)),
          readCyclicPayouts,
        )}
      />,
    );

    expect(renderer.root.findByType(TextInput).props.value).toBe('10000');
    await changeText(renderer, 'target-scan-limit-input', '999');
    expect(
      renderer.root.findAll(
        (node) =>
          node.type === Text && node.props.testID === 'target-scan-limit-error',
      ),
    ).toHaveLength(1);

    await completeBoard(renderer);
    expect(readCyclicPayouts).not.toHaveBeenCalled();
    expect(testIdCount(renderer, 'result-status-success')).toBe(0);
    expect(testIdCount(renderer, 'result-status-pending')).toBeGreaterThan(0);

    await changeText(renderer, 'target-scan-limit-input', '1000');
    expect(readCyclicPayouts).toHaveBeenCalledWith(game, 2, 1_000);
    expect(testIdCount(renderer, 'result-status-success')).toBeGreaterThan(0);

    act(() => renderer.unmount());
  });

  test('ignores the previous response after the scan limit changes', async () => {
    const first = deferred<readonly SequencePayout[]>();
    const second = deferred<readonly SequencePayout[]>();
    const readCyclicPayouts = jest
      .fn()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={repository(
          jest.fn().mockResolvedValue(uniqueResult(2)),
          readCyclicPayouts,
        )}
      />,
    );

    await completeBoard(renderer);
    await changeText(renderer, 'target-scan-limit-input', '1000');
    expect(readCyclicPayouts).toHaveBeenNthCalledWith(1, game, 2, 10_000);
    expect(readCyclicPayouts).toHaveBeenNthCalledWith(2, game, 2, 1_000);

    await act(async () => {
      first.resolve(payoutsFromTwo);
      await first.promise;
    });
    expect(testIdCount(renderer, 'result-status-success')).toBe(0);

    await act(async () => {
      second.resolve(payoutsFromTwo);
      await second.promise;
    });
    expect(testIdCount(renderer, 'result-status-success')).toBeGreaterThan(0);

    act(() => renderer.unmount());
  });

  test.each([
    [{ status: 'not_found' } as const, 'not_found'],
    [
      {
        occurrenceCount: 2,
        sequenceNumbers: [2, 5],
        status: 'duplicate',
      } as const,
      'duplicate',
    ],
  ])(
    'does not start Target for %s exact result',
    async (exactResult, _label) => {
      const readCyclicPayouts = jest.fn().mockResolvedValue(payoutsFromTwo);
      const renderer = render(
        <GameWorkspaceScreen
          diagnostics={diagnostics}
          games={[game]}
          repository={repository(
            jest.fn().mockResolvedValue(exactResult),
            readCyclicPayouts,
          )}
        />,
      );

      await completeBoard(renderer);

      expect(readCyclicPayouts).not.toHaveBeenCalled();
      expect(testIdCount(renderer, 'result-status-loading')).toBe(0);
      expect(testIdCount(renderer, 'result-status-success')).toBe(0);
      act(() => renderer.unmount());
    },
  );

  test('maps repository failure to local_data_error and retries without changing the board', async () => {
    const readCyclicPayouts = jest
      .fn()
      .mockRejectedValueOnce(new Error('SQLite read failed'))
      .mockResolvedValueOnce(payoutsFromTwo);
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={repository(
          jest.fn().mockResolvedValue(uniqueResult(2)),
          readCyclicPayouts,
        )}
      />,
    );

    await completeBoard(renderer);

    expect(testIdCount(renderer, 'result-status-error')).toBeGreaterThan(0);
    expect(JSON.stringify(renderer.toJSON())).toContain('local_data_error');

    await press(renderer, 'target-retry-button');

    expect(readCyclicPayouts).toHaveBeenCalledTimes(2);
    expect(testIdCount(renderer, 'result-status-success')).toBeGreaterThan(0);
    await press(renderer, 'result-details-toggle');
    expect(summaryValue(renderer, 'target-final-cost')).toContain('40');
    act(() => renderer.unmount());
  });

  test('reports engine sequence-integrity failures as a controlled local error', async () => {
    const invalidPayouts = payoutsFromTwo.map((payout, index) =>
      index === 1 ? { ...payout, sequenceNumber: 5 } : payout,
    );
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={repository(
          jest.fn().mockResolvedValue(uniqueResult(2)),
          jest.fn().mockResolvedValue(invalidPayouts),
        )}
      />,
    );

    await completeBoard(renderer);

    expect(testIdCount(renderer, 'result-status-error')).toBeGreaterThan(0);
    expect(JSON.stringify(renderer.toJSON())).toContain('local_data_error');
    expect(JSON.stringify(renderer.toJSON())).toContain(
      'Spin 2 must use sequence 4',
    );
    act(() => renderer.unmount());
  });

  test('Reset removes a completed Target result and does not start another scan', async () => {
    const readCyclicPayouts = jest.fn().mockResolvedValue(payoutsFromTwo);
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={repository(
          jest.fn().mockResolvedValue(uniqueResult(2)),
          readCyclicPayouts,
        )}
      />,
    );

    await completeBoard(renderer);
    expect(testIdCount(renderer, 'result-status-success')).toBeGreaterThan(0);
    expect(visibleTestIdCount(renderer, 'target-peak-row-2')).toBeGreaterThan(
      0,
    );

    await press(renderer, 'reset-button');

    expect(testIdCount(renderer, 'result-status-success')).toBe(0);
    expect(visibleTestIdCount(renderer, 'target-peak-row-2')).toBe(0);
    expect(readCyclicPayouts).toHaveBeenCalledTimes(1);
    act(() => renderer.unmount());
  });

  test('changing the game removes the completed Target context', async () => {
    const readCyclicPayouts = jest.fn().mockResolvedValue(payoutsFromTwo);
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game, secondGame]}
        repository={repository(
          jest.fn().mockResolvedValue(uniqueResult(2)),
          readCyclicPayouts,
        )}
      />,
    );

    await completeBoard(renderer);
    expect(testIdCount(renderer, 'result-status-success')).toBeGreaterThan(0);

    await press(renderer, 'game-option-game-2');

    expect(testIdCount(renderer, 'result-status-success')).toBe(0);
    expect(visibleTestIdCount(renderer, 'prefix-idle')).toBeGreaterThan(0);
    expect(readCyclicPayouts).toHaveBeenCalledTimes(1);
    act(() => renderer.unmount());
  });

  test('ignores an older Target response after Undo and a new complete board', async () => {
    const first = deferred<readonly SequencePayout[]>();
    const second = deferred<readonly SequencePayout[]>();
    const readCyclicPayouts = jest
      .fn()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const findExact = jest.fn(
      (_selectedGame: LocalGameConfig, signature: string) =>
        Promise.resolve(
          signature === '0102'
            ? uniqueResult(2)
            : uniqueResult(3, [1, 1], '0101'),
        ),
    );
    const renderer = render(
      <GameWorkspaceScreen
        diagnostics={diagnostics}
        games={[game]}
        repository={repository(findExact, readCyclicPayouts)}
      />,
    );

    await completeBoard(renderer);
    await press(renderer, 'undo-button');
    await press(renderer, 'symbol-1');

    expect(readCyclicPayouts).toHaveBeenNthCalledWith(2, game, 3, 10_000);

    const payoutsFromThree: readonly SequencePayout[] = [
      { payoutCredits: 0, sequenceNumber: 4 },
      { payoutCredits: 0, sequenceNumber: 5 },
      { payoutCredits: 0, sequenceNumber: 1 },
      { payoutCredits: 0, sequenceNumber: 2 },
    ];
    await act(async () => {
      second.resolve(payoutsFromThree);
      await second.promise;
    });
    expect(testIdCount(renderer, 'result-status-success')).toBeGreaterThan(0);
    await press(renderer, 'result-details-toggle');
    expect(summaryValue(renderer, 'target-final-net')).toContain('-40');

    await act(async () => {
      first.resolve(payoutsFromTwo);
      await first.promise;
    });
    expect(summaryValue(renderer, 'target-final-net')).toContain('-40');

    act(() => renderer.unmount());
  });
});
