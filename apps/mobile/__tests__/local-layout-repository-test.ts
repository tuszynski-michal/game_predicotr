import type { SymbolDefinition } from '@game-predictor/shared-ts';
import type { SQLiteBindParams } from 'expo-sqlite';

import {
  LocalLayoutRepository,
  type LocalGameConfig,
  type LocalSnapshotDatabase,
} from '@/data/local-layout-repository';

type RecordedQuery = {
  params: SQLiteBindParams | undefined;
  source: string;
};

class FakeDatabase implements LocalSnapshotDatabase {
  readonly allQueries: RecordedQuery[] = [];
  readonly firstQueries: RecordedQuery[] = [];

  constructor(
    private readonly allResults: unknown[][] = [],
    private readonly firstResults: unknown[] = [],
  ) {}

  async getAllAsync<T>(
    source: string,
    params?: SQLiteBindParams,
  ): Promise<T[]> {
    this.allQueries.push({ params, source });
    const result = this.allResults.shift();
    if (result === undefined) {
      throw new Error('Missing queued getAllAsync result.');
    }
    return result as T[];
  }

  async getFirstAsync<T>(
    source: string,
    params?: SQLiteBindParams,
  ): Promise<T | null> {
    this.firstQueries.push({ params, source });
    const result = this.firstResults.shift();
    if (result === undefined) {
      throw new Error('Missing queued getFirstAsync result.');
    }
    return result as T | null;
  }
}

const symbols: readonly SymbolDefinition[] = [
  {
    code: 'symbol-1',
    displayOrder: 0,
    isWildcard: false,
    mobileCode: 1,
    name: 'Symbol 1',
    nameEn: 'Lemon',
    namePl: 'Cytryna',
  },
  {
    code: 'symbol-2',
    displayOrder: 1,
    isWildcard: true,
    mobileCode: 2,
    name: 'Symbol 2',
  },
];

const game: LocalGameConfig = {
  code: 'game-1',
  columns: 2,
  databaseId: 7,
  datasetVersion: 1,
  id: 'game-1',
  layoutCount: 4,
  name: 'Game 1',
  rows: 2,
  rulesVersion: 1,
  signatureCellWidth: 2,
  spinCost: 10,
  symbols,
};

const signature = '01020102';

function count(candidateCount: number): { candidate_count: number } {
  return { candidate_count: candidateCount };
}

describe('LocalLayoutRepository game catalog', () => {
  test('maps games, symbols and version metadata from one open database', async () => {
    const database = new FakeDatabase([
      [
        {
          code: 'game-1',
          columns: 2,
          dataset_version: 3,
          id: 7,
          layout_count: 4,
          name: 'Game 1',
          rows: 2,
          rules_version: 5,
          signature_cell_width: 2,
          spin_cost: 10,
        },
      ],
      [
        {
          code: 'symbol-1',
          display_order: 0,
          game_id: 7,
          is_wildcard: 0,
          mobile_code: 1,
          name: 'Symbol 1',
          name_en: 'Lemon',
          name_pl: 'Cytryna',
        },
        {
          code: 'symbol-2',
          display_order: 1,
          game_id: 7,
          is_wildcard: 1,
          mobile_code: 2,
          name: 'Symbol 2',
          name_en: null,
          name_pl: null,
        },
      ],
    ]);

    const games = await new LocalLayoutRepository(database).listGames();

    expect(games).toEqual([
      {
        ...game,
        datasetVersion: 3,
        rulesVersion: 5,
      },
    ]);
    expect(database.allQueries).toHaveLength(2);
  });

  test('maps malformed catalog data to local_data_error', async () => {
    const database = new FakeDatabase([
      [
        {
          code: 'game-1',
          columns: 2,
          dataset_version: 1,
          id: 7,
          layout_count: 4,
          name: 'Game 1',
          rows: 2,
          rules_version: 1,
          signature_cell_width: 2,
          spin_cost: 10,
        },
      ],
      [],
    ]);

    await expect(
      new LocalLayoutRepository(database).listGames(),
    ).rejects.toMatchObject({ code: 'local_data_error' });
  });
});

describe('LocalLayoutRepository prefix matching', () => {
  test('returns zero candidates without a second query', async () => {
    const database = new FakeDatabase([], [count(0)]);

    await expect(
      new LocalLayoutRepository(database).findByPrefix(game, '02'),
    ).resolves.toEqual({
      candidateCount: 0,
      suggestion: null,
    });
    expect(database.firstQueries).toHaveLength(1);
    expect(database.allQueries).toHaveLength(0);
    expect(database.firstQueries[0]?.params).toEqual([7, '02', '02:']);
    expect(database.firstQueries[0]?.source).toContain(
      'idx_layouts_game_signature',
    );
  });

  test('returns the full layout only for one prefix candidate', async () => {
    const database = new FakeDatabase(
      [],
      [count(1), { sequence_number: 3, signature }],
    );

    await expect(
      new LocalLayoutRepository(database).findByPrefix(game, '0102'),
    ).resolves.toEqual({
      candidateCount: 1,
      suggestion: {
        cells: [1, 2, 1, 2],
        kind: 'unique',
        occurrenceCount: 1,
        sequenceNumber: 3,
        signature,
      },
    });
    expect(database.firstQueries).toHaveLength(2);
  });

  test('suggests shared content when all matching records have one signature', async () => {
    const database = new FakeDatabase([[{ signature }]], [count(3)]);

    await expect(
      new LocalLayoutRepository(database).findByPrefix(game, '01'),
    ).resolves.toEqual({
      candidateCount: 3,
      suggestion: {
        cells: [1, 2, 1, 2],
        kind: 'duplicate',
        occurrenceCount: 3,
        sequenceNumber: null,
        signature,
      },
    });
    expect(database.firstQueries).toHaveLength(1);
    expect(database.allQueries).toHaveLength(1);
    expect(database.allQueries[0]?.source).toContain('GROUP BY signature');
    expect(database.allQueries[0]?.source).toContain('LIMIT 2');
  });

  test('does not suggest when a prefix has multiple distinct signatures', async () => {
    const database = new FakeDatabase(
      [[{ signature }, { signature: '01020201' }]],
      [count(4)],
    );

    await expect(
      new LocalLayoutRepository(database).findByPrefix(game, '01'),
    ).resolves.toEqual({
      candidateCount: 4,
      suggestion: null,
    });
  });

  test('rejects a prefix containing a symbol outside the game', async () => {
    const database = new FakeDatabase();

    await expect(
      new LocalLayoutRepository(database).findByPrefix(game, '03'),
    ).rejects.toMatchObject({ code: 'local_data_error' });
    expect(database.firstQueries).toHaveLength(0);
  });
});

describe('LocalLayoutRepository exact matching', () => {
  test('returns not_found without reading an arbitrary layout', async () => {
    const database = new FakeDatabase([], [count(0)]);

    await expect(
      new LocalLayoutRepository(database).findExact(game, signature),
    ).resolves.toEqual({ status: 'not_found' });
    expect(database.firstQueries).toHaveLength(1);
  });

  test('returns the only exact layout', async () => {
    const database = new FakeDatabase(
      [],
      [count(1), { sequence_number: 3, signature }],
    );

    await expect(
      new LocalLayoutRepository(database).findExact(game, signature),
    ).resolves.toEqual({
      candidate: {
        cells: [1, 2, 1, 2],
        sequenceNumber: 3,
        signature,
      },
      status: 'unique',
    });
  });

  test('reports duplicate occurrences without selecting a unique result', async () => {
    const database = new FakeDatabase(
      [[{ sequence_number: 2 }, { sequence_number: 4 }]],
      [count(2)],
    );

    await expect(
      new LocalLayoutRepository(database).findExact(game, signature),
    ).resolves.toEqual({
      occurrenceCount: 2,
      sequenceNumbers: [2, 4],
      status: 'duplicate',
    });
    expect(database.firstQueries).toHaveLength(1);
    expect(database.allQueries).toHaveLength(1);
  });

  test('keeps the exact occurrence count when diagnostics exceed the limit', async () => {
    const database = new FakeDatabase(
      [[{ sequence_number: 1 }, { sequence_number: 2 }]],
      [count(3)],
    );

    await expect(
      new LocalLayoutRepository(database, 2).findExact(game, signature),
    ).resolves.toEqual({
      occurrenceCount: 3,
      sequenceNumbers: null,
      status: 'duplicate',
    });
  });
});

describe('LocalLayoutRepository cyclic payouts', () => {
  test('reads N-1 payouts in one query and wraps from layout 4 to 1', async () => {
    const database = new FakeDatabase([
      [
        { cycle_segment: 0, payout: 20, sequence_number: 4 },
        { cycle_segment: 1, payout: 0, sequence_number: 1 },
        { cycle_segment: 1, payout: 50, sequence_number: 2 },
      ],
    ]);

    await expect(
      new LocalLayoutRepository(database).readCyclicPayouts(game, 3),
    ).resolves.toEqual([
      { payoutCredits: 20, sequenceNumber: 4 },
      { payoutCredits: 0, sequenceNumber: 1 },
      { payoutCredits: 50, sequenceNumber: 2 },
    ]);
    expect(database.allQueries).toHaveLength(1);
    expect(database.allQueries[0]?.source).toContain('UNION ALL');
    expect(database.allQueries[0]?.params).toEqual([7, 3, 7, 3]);
  });

  test('rejects an incomplete or incorrectly ordered payout stream', async () => {
    const database = new FakeDatabase([
      [
        { cycle_segment: 0, payout: 20, sequence_number: 4 },
        { cycle_segment: 1, payout: 0, sequence_number: 2 },
        { cycle_segment: 1, payout: 50, sequence_number: 1 },
      ],
    ]);

    await expect(
      new LocalLayoutRepository(database).readCyclicPayouts(game, 3),
    ).rejects.toMatchObject({ code: 'local_data_error' });
  });
});
