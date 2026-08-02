import type { SequencePayout } from '@game-predictor/shared-ts';
import type { SQLiteBindParams } from 'expo-sqlite';

import type { SnapshotDiagnostics } from '@/data/bundled-snapshot';
import type {
  ExactMatchResult,
  LocalGameConfig,
  LocalSnapshotDatabase,
  PrefixMatchResult,
} from '@/data/local-layout-repository';
import {
  runM35MobileBenchmark,
  summarizeBenchmarkTimings,
} from '@/benchmarks/m35-performance';

const GAME: LocalGameConfig = {
  code: 'benchmark',
  columns: 2,
  databaseId: 1,
  datasetVersion: 1,
  id: 'benchmark',
  layoutCount: 4,
  name: 'Benchmark',
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

const DIAGNOSTICS: SnapshotDiagnostics = {
  algorithmVersion: 'payout-v2',
  databaseName: 'benchmark.db',
  datasetVersion: null,
  fixtureVersion: null,
  gameCount: 1,
  layoutCount: 4,
  logicalContentSha256: 'a'.repeat(64),
  releaseVersion: 'm35-benchmark.1',
  rulesVersion: null,
  schemaVersion: 3,
  snapshotFileSha256: 'b'.repeat(64),
};

class FakeDatabase implements LocalSnapshotDatabase {
  async getAllAsync<T>(): Promise<T[]> {
    return [];
  }

  async getFirstAsync<T>(
    source: string,
    params?: SQLiteBindParams,
  ): Promise<T | null> {
    if (source.includes('NOT EXISTS')) {
      return { sequence_number: 1, signature: '0101' } as T;
    }
    if (source.includes('GROUP BY signature')) {
      return { sequence_number: 2, signature: '0201' } as T;
    }
    if (source.includes('candidate_count')) {
      const signature = Array.isArray(params) ? params[1] : undefined;
      return { candidate_count: signature === '0101' ? 1 : 0 } as T;
    }
    return null;
  }
}

class FakeRepository {
  async findExact(
    _game: LocalGameConfig,
    signature: string,
  ): Promise<ExactMatchResult> {
    if (signature === '0101') {
      return {
        candidate: { cells: [1, 1], sequenceNumber: 1, signature },
        status: 'unique',
      };
    }
    if (signature === '0201') {
      return {
        occurrenceCount: 2,
        sequenceNumbers: [2, 4],
        status: 'duplicate',
      };
    }
    return { status: 'not_found' };
  }

  async findByPrefix(): Promise<PrefixMatchResult> {
    return { candidateCount: 3, suggestion: null };
  }

  async readCyclicPayouts(): Promise<readonly SequencePayout[]> {
    return [
      { payoutCredits: 20, sequenceNumber: 2 },
      { payoutCredits: 0, sequenceNumber: 3 },
      { payoutCredits: 0, sequenceNumber: 4 },
    ];
  }
}

describe('M3.5 mobile performance benchmark', () => {
  it('uses nearest-rank p50 and p95', () => {
    expect(summarizeBenchmarkTimings([5, 1, 4, 2, 3])).toEqual({
      firstMs: 5,
      iterations: 5,
      maxMs: 5,
      minMs: 1,
      p50Ms: 3,
      p95Ms: 5,
    });
  });

  it('measures exact, prefix and full Target through production ports', async () => {
    const report = await runM35MobileBenchmark(
      new FakeDatabase(),
      new FakeRepository(),
      GAME,
      DIAGNOSTICS,
      12.5,
      {
        cycleIterations: 2,
        exactIterations: 2,
        prefixIterations: 2,
      },
    );

    expect(report.databaseInitializationMs).toBe(12.5);
    expect(report.measurements.exactUnique.iterations).toBe(2);
    expect(report.measurements.prefixFiveCells.candidateCount).toBe(3);
    expect(report.measurements.cyclicRead.iterations).toBe(2);
    expect(report.measurements.targetCalculation.iterations).toBe(2);
    expect(report.budgetResults.targetEndToEnd).toBe(true);
  });
});
