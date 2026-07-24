import type { SQLiteDatabase } from 'expo-sqlite';

import manifestJson from '../../assets/snapshot/manifest.json';

export const LOCAL_DATA_ERROR_CODE = 'local_data_error';

export type SnapshotManifest = {
  algorithmVersion: string;
  logicalContentSha256: string;
  recordCount: number;
  releaseVersion: string;
  schemaVersion: number;
  snapshotFile: string;
  snapshotFileSha256: string;
};

export type SnapshotDiagnostics = {
  algorithmVersion: string;
  databaseName: string;
  logicalContentSha256: string;
  recordCount: number;
  releaseVersion: string;
  schemaVersion: number;
  snapshotFileSha256: string;
};

type MetadataRow = {
  key: string;
  value: string;
};

type CountRow = {
  record_count: number;
};

const EXPECTED_SCHEMA_VERSION = 1;
const SHA256_PATTERN = /^[a-f0-9]{64}$/;

export const snapshotManifest = manifestJson satisfies SnapshotManifest;

// Static require is required by Metro so the database is bundled in the APK.
export const snapshotAssetId =
  require('../../assets/snapshot/m1-spike.db') as number;

export class LocalDataError extends Error {
  readonly code = LOCAL_DATA_ERROR_CODE;

  constructor(message: string) {
    super(message);
    this.name = 'LocalDataError';
  }
}

export function buildLocalDatabaseName(manifest: SnapshotManifest): string {
  if (!SHA256_PATTERN.test(manifest.snapshotFileSha256)) {
    throw new LocalDataError(
      'Snapshot manifest contains an invalid SHA-256 checksum.',
    );
  }

  return `snapshot-v${manifest.schemaVersion}-${manifest.snapshotFileSha256.slice(0, 16)}.db`;
}

export function validateSnapshotMetadata(
  metadata: Readonly<Record<string, string>>,
  manifest: SnapshotManifest,
  actualRecordCount: number,
): void {
  if (manifest.schemaVersion !== EXPECTED_SCHEMA_VERSION) {
    throw new LocalDataError(
      `Unsupported manifest schema version: ${manifest.schemaVersion}.`,
    );
  }

  const expectedMetadata: Readonly<Record<string, string>> = {
    algorithm_version: manifest.algorithmVersion,
    logical_content_sha256: manifest.logicalContentSha256,
    release_version: manifest.releaseVersion,
    schema_version: String(manifest.schemaVersion),
  };

  for (const [key, expectedValue] of Object.entries(expectedMetadata)) {
    if (metadata[key] !== expectedValue) {
      throw new LocalDataError(`Snapshot metadata mismatch for "${key}".`);
    }
  }

  if (actualRecordCount !== manifest.recordCount) {
    throw new LocalDataError(
      `Snapshot record count mismatch: expected ${manifest.recordCount}, got ${actualRecordCount}.`,
    );
  }
}

export async function readSnapshotDiagnostics(
  database: SQLiteDatabase,
): Promise<SnapshotDiagnostics> {
  try {
    const metadataRows = await database.getAllAsync<MetadataRow>(
      'SELECT key, value FROM metadata',
    );
    const countRow = await database.getFirstAsync<CountRow>(
      'SELECT COUNT(*) AS record_count FROM diagnostic_record',
    );

    if (countRow === null) {
      throw new LocalDataError(
        'Snapshot did not return a diagnostic record count.',
      );
    }

    const metadata = Object.fromEntries(
      metadataRows.map(({ key, value }) => [key, value]),
    );

    validateSnapshotMetadata(metadata, snapshotManifest, countRow.record_count);

    return {
      algorithmVersion: snapshotManifest.algorithmVersion,
      databaseName: buildLocalDatabaseName(snapshotManifest),
      logicalContentSha256: snapshotManifest.logicalContentSha256,
      recordCount: countRow.record_count,
      releaseVersion: snapshotManifest.releaseVersion,
      schemaVersion: snapshotManifest.schemaVersion,
      snapshotFileSha256: snapshotManifest.snapshotFileSha256,
    };
  } catch (error: unknown) {
    if (error instanceof LocalDataError) {
      throw error;
    }

    const detail =
      error instanceof Error ? error.message : 'Unknown SQLite error.';
    throw new LocalDataError(`Could not validate bundled snapshot: ${detail}`);
  }
}

export function asLocalDataError(error: unknown): LocalDataError {
  if (error instanceof LocalDataError) {
    return error;
  }

  const detail =
    error instanceof Error ? error.message : 'Unknown local data error.';
  return new LocalDataError(detail);
}
