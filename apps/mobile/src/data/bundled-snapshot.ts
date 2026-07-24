import type { SQLiteDatabase } from 'expo-sqlite';

import manifestJson from '../../assets/snapshot/manifest.json';
import { LocalDataError } from './local-data-error';

export {
  asLocalDataError,
  LOCAL_DATA_ERROR_CODE,
  LocalDataError,
} from './local-data-error';

type SnapshotManifestGame = {
  code: string;
  datasetVersion: number;
  duplicateFixtures: readonly {
    sequenceNumbers: readonly number[];
    signature: string;
  }[];
  id: number;
  layoutCount: number;
  rulesVersion: number;
  seed: number;
  symbolCount: number;
  uniquePrefixFixture: {
    cellCount: number;
    sequenceNumber: number;
    signaturePrefix: string;
  };
};

export type SnapshotManifest = {
  algorithmVersion: string;
  createdAt: string;
  datasetVersion: number;
  fixtureFingerprint: string;
  fixtureVersion: string;
  gameCount: number;
  games: readonly SnapshotManifestGame[];
  layoutCount: number;
  logicalContentSha256: string;
  releaseVersion: string;
  rulesVersion: number;
  schemaVersion: number;
  snapshotFile: string;
  snapshotFileSha256: string;
  targetGoldenCases: readonly unknown[];
};

export type SnapshotDiagnostics = {
  algorithmVersion: string;
  databaseName: string;
  datasetVersion: number;
  fixtureVersion: string;
  gameCount: number;
  layoutCount: number;
  logicalContentSha256: string;
  releaseVersion: string;
  rulesVersion: number;
  schemaVersion: number;
  snapshotFileSha256: string;
};

type MetadataRow = {
  key: string;
  value: string;
};

type CountRow = {
  game_count: number;
  layout_count: number;
};

const EXPECTED_SCHEMA_VERSION = 2;
const SHA256_PATTERN = /^[a-f0-9]{64}$/;

export const snapshotManifest = manifestJson satisfies SnapshotManifest;

// Static require is required by Metro so the database is bundled in the APK.
export const snapshotAssetId =
  require('../../assets/snapshot/m1-snapshot.db') as number;

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
  actualGameCount: number,
  actualLayoutCount: number,
): void {
  if (manifest.schemaVersion !== EXPECTED_SCHEMA_VERSION) {
    throw new LocalDataError(
      `Unsupported manifest schema version: ${manifest.schemaVersion}.`,
    );
  }

  const expectedMetadata: Readonly<Record<string, string>> = {
    algorithm_version: manifest.algorithmVersion,
    content_checksum: manifest.logicalContentSha256,
    created_at: manifest.createdAt,
    dataset_version: String(manifest.datasetVersion),
    fixture_fingerprint: manifest.fixtureFingerprint,
    fixture_version: manifest.fixtureVersion,
    game_count: String(manifest.gameCount),
    layout_count: String(manifest.layoutCount),
    release_version: manifest.releaseVersion,
    rules_version: String(manifest.rulesVersion),
    snapshot_schema_version: String(manifest.schemaVersion),
  };

  for (const [key, expectedValue] of Object.entries(expectedMetadata)) {
    if (metadata[key] !== expectedValue) {
      throw new LocalDataError(`Snapshot metadata mismatch for "${key}".`);
    }
  }

  if (actualGameCount !== manifest.gameCount) {
    throw new LocalDataError(
      `Snapshot game count mismatch: expected ${manifest.gameCount}, got ${actualGameCount}.`,
    );
  }
  if (actualLayoutCount !== manifest.layoutCount) {
    throw new LocalDataError(
      `Snapshot layout count mismatch: expected ${manifest.layoutCount}, got ${actualLayoutCount}.`,
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
      `
        SELECT
          (SELECT COUNT(*) FROM games) AS game_count,
          (SELECT COUNT(*) FROM layouts) AS layout_count
      `,
    );

    if (countRow === null) {
      throw new LocalDataError(
        'Snapshot did not return game and layout counts.',
      );
    }

    const metadata = Object.fromEntries(
      metadataRows.map(({ key, value }) => [key, value]),
    );

    validateSnapshotMetadata(
      metadata,
      snapshotManifest,
      countRow.game_count,
      countRow.layout_count,
    );

    return {
      algorithmVersion: snapshotManifest.algorithmVersion,
      databaseName: buildLocalDatabaseName(snapshotManifest),
      datasetVersion: snapshotManifest.datasetVersion,
      fixtureVersion: snapshotManifest.fixtureVersion,
      gameCount: countRow.game_count,
      layoutCount: countRow.layout_count,
      logicalContentSha256: snapshotManifest.logicalContentSha256,
      releaseVersion: snapshotManifest.releaseVersion,
      rulesVersion: snapshotManifest.rulesVersion,
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
