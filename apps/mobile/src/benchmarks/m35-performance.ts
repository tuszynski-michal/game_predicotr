import type { SequencePayout } from '@game-predictor/shared-ts';

import type { SnapshotDiagnostics } from '@/data/bundled-snapshot';
import type {
  ExactMatchResult,
  LocalGameConfig,
  LocalSnapshotDatabase,
  PrefixMatchResult,
} from '@/data/local-layout-repository';
import { calculateSnapshotTargetForecast } from '@/features/target/use-target-forecast';

export const M35_BENCHMARK_RELEASE_VERSION = 'm35-benchmark.1';
export const M35_BENCHMARK_LOG_PREFIX = 'M35_BENCHMARK_RESULT';
export const M35_BENCHMARK_SNAPSHOT_SIZE_BYTES = 41_025_536;

interface LayoutReferenceRow {
  sequence_number: number;
  signature: string;
}

export interface M35BenchmarkRepository {
  findByPrefix(
    game: LocalGameConfig,
    signaturePrefix: string,
  ): Promise<PrefixMatchResult>;
  findExact(
    game: LocalGameConfig,
    signature: string,
  ): Promise<ExactMatchResult>;
  readCyclicPayouts(
    game: LocalGameConfig,
    startSequenceNumber: number,
    targetScanLimit: number,
  ): Promise<readonly SequencePayout[]>;
}

export interface BenchmarkTimingSummary {
  readonly firstMs: number;
  readonly iterations: number;
  readonly maxMs: number;
  readonly minMs: number;
  readonly p50Ms: number;
  readonly p95Ms: number;
}

export interface M35MobileBenchmarkReport {
  readonly budgetResults: {
    readonly cyclicRead: boolean;
    readonly exact: boolean;
    readonly prefix: boolean;
    readonly targetEndToEnd: boolean;
  };
  readonly databaseInitializationMs: number;
  readonly dataset: {
    readonly layoutCount: number;
    readonly logicalContentSha256: string;
    readonly releaseVersion: string;
    readonly snapshotFileSha256: string;
    readonly snapshotSizeBytes: number;
  };
  readonly measurements: {
    readonly cyclicRead: BenchmarkTimingSummary;
    readonly exactDuplicate: BenchmarkTimingSummary;
    readonly exactNotFound: BenchmarkTimingSummary;
    readonly exactUnique: BenchmarkTimingSummary;
    readonly prefixFiveCells: BenchmarkTimingSummary & {
      readonly candidateCount: number;
    };
    readonly targetCalculation: BenchmarkTimingSummary;
    readonly targetEndToEnd: BenchmarkTimingSummary;
  };
  readonly references: {
    readonly cycleStartSequenceNumber: number;
    readonly duplicateSequenceNumber: number;
    readonly uniqueSequenceNumber: number;
  };
}

type BenchmarkOptions = {
  readonly cycleIterations?: number;
  readonly exactIterations?: number;
  readonly prefixIterations?: number;
};

function roundMilliseconds(value: number): number {
  return Math.round(value * 10_000) / 10_000;
}

function percentile(
  values: readonly number[],
  percentileValue: number,
): number {
  if (values.length === 0) {
    throw new Error('At least one benchmark measurement is required.');
  }
  const ordered = [...values].sort((left, right) => left - right);
  const index = Math.max(0, Math.ceil(percentileValue * ordered.length) - 1);
  const value = ordered[index];
  if (value === undefined) {
    throw new Error('Benchmark percentile index is invalid.');
  }
  return value;
}

export function summarizeBenchmarkTimings(
  values: readonly number[],
): BenchmarkTimingSummary {
  const first = values[0];
  if (first === undefined) {
    throw new Error('At least one benchmark measurement is required.');
  }
  return Object.freeze({
    firstMs: roundMilliseconds(first),
    iterations: values.length,
    maxMs: roundMilliseconds(Math.max(...values)),
    minMs: roundMilliseconds(Math.min(...values)),
    p50Ms: roundMilliseconds(percentile(values, 0.5)),
    p95Ms: roundMilliseconds(percentile(values, 0.95)),
  });
}

async function measureAsync<T>(
  operation: () => Promise<T>,
  iterations: number,
  warmups: number,
): Promise<{
  readonly lastResult: T;
  readonly timing: BenchmarkTimingSummary;
}> {
  for (let index = 0; index < warmups; index += 1) {
    await operation();
  }

  const values: number[] = [];
  let lastResult: T | undefined;
  for (let index = 0; index < iterations; index += 1) {
    const startedAt = performance.now();
    lastResult = await operation();
    values.push(performance.now() - startedAt);
  }
  if (lastResult === undefined) {
    throw new Error('Benchmark operation did not return a result.');
  }
  return {
    lastResult,
    timing: summarizeBenchmarkTimings(values),
  };
}

async function loadReferences(
  database: LocalSnapshotDatabase,
  game: LocalGameConfig,
): Promise<{
  readonly duplicate: LayoutReferenceRow;
  readonly notFoundSignature: string;
  readonly unique: LayoutReferenceRow;
}> {
  const unique = await database.getFirstAsync<LayoutReferenceRow>(
    `
      SELECT sequence_number, signature
      FROM layouts AS candidate
      WHERE game_id = ?
        AND NOT EXISTS (
          SELECT 1
          FROM layouts AS duplicate
          WHERE duplicate.game_id = candidate.game_id
            AND duplicate.signature = candidate.signature
            AND duplicate.sequence_number <> candidate.sequence_number
        )
      ORDER BY sequence_number
      LIMIT 1
    `,
    [game.databaseId],
  );
  const duplicate = await database.getFirstAsync<LayoutReferenceRow>(
    `
      SELECT MIN(sequence_number) AS sequence_number, signature
      FROM layouts
      WHERE game_id = ?
      GROUP BY signature
      HAVING COUNT(*) > 1
      ORDER BY MIN(sequence_number)
      LIMIT 1
    `,
    [game.databaseId],
  );
  if (unique === null || duplicate === null) {
    throw new Error('Benchmark unique or duplicate reference is missing.');
  }

  for (const symbol of game.symbols) {
    const signature = String(symbol.mobileCode)
      .padStart(game.signatureCellWidth, '0')
      .repeat(game.rows * game.columns);
    const result = await database.getFirstAsync<{ candidate_count: number }>(
      `
        SELECT COUNT(*) AS candidate_count
        FROM layouts INDEXED BY idx_layouts_game_signature
        WHERE game_id = ? AND signature = ?
      `,
      [game.databaseId, signature],
    );
    if (result?.candidate_count === 0) {
      return { duplicate, notFoundSignature: signature, unique };
    }
  }
  throw new Error('Benchmark not-found signature could not be selected.');
}

export async function runM35MobileBenchmark(
  database: LocalSnapshotDatabase,
  repository: M35BenchmarkRepository,
  game: LocalGameConfig,
  diagnostics: SnapshotDiagnostics,
  databaseInitializationMs: number,
  options: BenchmarkOptions = {},
): Promise<M35MobileBenchmarkReport> {
  const exactIterations = options.exactIterations ?? 100;
  const prefixIterations = options.prefixIterations ?? 100;
  const cycleIterations = options.cycleIterations ?? 5;
  const references = await loadReferences(database, game);

  const exactUnique = await measureAsync(
    () => repository.findExact(game, references.unique.signature),
    exactIterations,
    10,
  );
  const exactDuplicate = await measureAsync(
    () => repository.findExact(game, references.duplicate.signature),
    exactIterations,
    10,
  );
  const exactNotFound = await measureAsync(
    () => repository.findExact(game, references.notFoundSignature),
    exactIterations,
    10,
  );
  if (
    exactUnique.lastResult.status !== 'unique' ||
    exactDuplicate.lastResult.status !== 'duplicate' ||
    exactNotFound.lastResult.status !== 'not_found'
  ) {
    throw new Error('Benchmark exact references returned unexpected states.');
  }

  const prefix = references.unique.signature.slice(
    0,
    game.signatureCellWidth * 5,
  );
  const prefixMeasurement = await measureAsync(
    () => repository.findByPrefix(game, prefix),
    prefixIterations,
    10,
  );

  const cyclicReadValues: number[] = [];
  const targetValues: number[] = [];
  const endToEndValues: number[] = [];
  for (let index = 0; index < cycleIterations; index += 1) {
    const endToEndStartedAt = performance.now();
    const readStartedAt = performance.now();
    const payouts = await repository.readCyclicPayouts(
      game,
      references.unique.sequence_number,
      500_000,
    );
    cyclicReadValues.push(performance.now() - readStartedAt);

    const targetStartedAt = performance.now();
    const forecast = calculateSnapshotTargetForecast(
      game,
      references.unique.sequence_number,
      500_000,
      diagnostics,
      payouts,
    );
    targetValues.push(performance.now() - targetStartedAt);
    endToEndValues.push(performance.now() - endToEndStartedAt);
    if (forecast.evaluatedSpinCount !== game.layoutCount - 1) {
      throw new Error('Benchmark Target did not evaluate N - 1 spins.');
    }
  }

  const cyclicRead = summarizeBenchmarkTimings(cyclicReadValues);
  const targetCalculation = summarizeBenchmarkTimings(targetValues);
  const targetEndToEnd = summarizeBenchmarkTimings(endToEndValues);
  const exactTiming = exactUnique.timing;
  const prefixTiming = prefixMeasurement.timing;

  return Object.freeze({
    budgetResults: Object.freeze({
      cyclicRead: cyclicRead.p95Ms < 5_000,
      exact: exactTiming.p95Ms < 200,
      prefix: prefixTiming.p95Ms < 300,
      targetEndToEnd: targetEndToEnd.p95Ms < 10_000,
    }),
    databaseInitializationMs: roundMilliseconds(databaseInitializationMs),
    dataset: Object.freeze({
      layoutCount: diagnostics.layoutCount,
      logicalContentSha256: diagnostics.logicalContentSha256,
      releaseVersion: diagnostics.releaseVersion,
      snapshotFileSha256: diagnostics.snapshotFileSha256,
      snapshotSizeBytes: M35_BENCHMARK_SNAPSHOT_SIZE_BYTES,
    }),
    measurements: Object.freeze({
      cyclicRead,
      exactDuplicate: exactDuplicate.timing,
      exactNotFound: exactNotFound.timing,
      exactUnique: exactTiming,
      prefixFiveCells: Object.freeze({
        ...prefixTiming,
        candidateCount: prefixMeasurement.lastResult.candidateCount,
      }),
      targetCalculation,
      targetEndToEnd,
    }),
    references: Object.freeze({
      cycleStartSequenceNumber: references.unique.sequence_number,
      duplicateSequenceNumber: references.duplicate.sequence_number,
      uniqueSequenceNumber: references.unique.sequence_number,
    }),
  });
}
