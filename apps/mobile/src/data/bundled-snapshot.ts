import type { SQLiteDatabase } from 'expo-sqlite';

import manifestJson from '../../assets/snapshot/manifest.json';
import { LocalDataError } from './local-data-error';

export {
  asLocalDataError,
  LOCAL_DATA_ERROR_CODE,
  LocalDataError,
} from './local-data-error';

type FixtureSnapshotManifestGame = {
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

type ProductionSnapshotManifestGame = {
  columns: number;
  datasetVersion: number;
  datasetVersionId: string;
  gameCode: string;
  gameId: string;
  layoutCount: number;
  mobileGameId: number;
  rows: number;
  rulesVersion: number;
  rulesVersionId: string;
  signatureCellWidth: number;
  symbolCount: number;
};

type SnapshotManifestCommon = {
  algorithmVersion: string;
  createdAt: string;
  gameCount: number;
  layoutCount: number;
  logicalContentSha256: string;
  releaseVersion: string;
  snapshotFile: string;
  snapshotFileSha256: string;
};

type FixtureSnapshotManifest = SnapshotManifestCommon & {
  datasetVersion: number;
  fixtureFingerprint: string;
  fixtureVersion: string;
  games: readonly FixtureSnapshotManifestGame[];
  rulesVersion: number;
  schemaVersion: number;
  targetGoldenCases: readonly unknown[];
};

type ProductionSnapshotManifest = SnapshotManifestCommon & {
  games: readonly ProductionSnapshotManifestGame[];
  manifestVersion: number;
  snapshotSchemaVersion: number;
  symbolCount: number;
};

export type SnapshotManifest =
  FixtureSnapshotManifest | ProductionSnapshotManifest;

export type SnapshotDiagnostics = {
  algorithmVersion: string;
  databaseName: string;
  datasetVersion: number | null;
  fixtureVersion: string | null;
  gameCount: number;
  layoutCount: number;
  logicalContentSha256: string;
  releaseVersion: string;
  rulesVersion: number | null;
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

  return `snapshot-v${schemaVersion(manifest)}-${manifest.snapshotFileSha256.slice(0, 16)}.db`;
}

export function validateSnapshotMetadata(
  metadata: Readonly<Record<string, string>>,
  manifest: SnapshotManifest,
  actualGameCount: number,
  actualLayoutCount: number,
): void {
  if ('manifestVersion' in manifest && manifest.manifestVersion !== 1) {
    throw new LocalDataError(
      `Unsupported snapshot manifest version: ${manifest.manifestVersion}.`,
    );
  }
  const manifestSchemaVersion = schemaVersion(manifest);
  if (manifestSchemaVersion !== EXPECTED_SCHEMA_VERSION) {
    throw new LocalDataError(
      `Unsupported manifest schema version: ${manifestSchemaVersion}.`,
    );
  }

  const expectedMetadata: Readonly<Record<string, string>> = {
    algorithm_version: manifest.algorithmVersion,
    content_checksum: manifest.logicalContentSha256,
    created_at: manifest.createdAt,
    game_count: String(manifest.gameCount),
    layout_count: String(manifest.layoutCount),
    release_version: manifest.releaseVersion,
    snapshot_schema_version: String(manifestSchemaVersion),
    ...('fixtureVersion' in manifest
      ? {
          dataset_version: String(manifest.datasetVersion),
          fixture_fingerprint: manifest.fixtureFingerprint,
          fixture_version: manifest.fixtureVersion,
          rules_version: String(manifest.rulesVersion),
        }
      : {}),
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
      datasetVersion:
        'datasetVersion' in snapshotManifest
          ? snapshotManifest.datasetVersion
          : null,
      fixtureVersion:
        'fixtureVersion' in snapshotManifest
          ? snapshotManifest.fixtureVersion
          : null,
      gameCount: countRow.game_count,
      layoutCount: countRow.layout_count,
      logicalContentSha256: snapshotManifest.logicalContentSha256,
      releaseVersion: snapshotManifest.releaseVersion,
      rulesVersion:
        'rulesVersion' in snapshotManifest
          ? snapshotManifest.rulesVersion
          : null,
      schemaVersion: schemaVersion(snapshotManifest),
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

function schemaVersion(manifest: SnapshotManifest): number {
  return 'schemaVersion' in manifest
    ? manifest.schemaVersion
    : manifest.snapshotSchemaVersion;
}
