import {
  buildLocalDatabaseName,
  LocalDataError,
  validateSnapshotMetadata,
  type SnapshotManifest,
} from '@/data/bundled-snapshot';

const manifest: SnapshotManifest = {
  algorithmVersion: 'payout-v2',
  createdAt: '2026-07-24T00:00:00Z',
  datasetVersion: 2,
  fixtureFingerprint: 'c'.repeat(64),
  fixtureVersion: 'm1-fixture-v2',
  gameCount: 3,
  games: [],
  layoutCount: 3_000,
  logicalContentSha256: 'b'.repeat(64),
  releaseVersion: 'm1-fixture.2',
  rulesVersion: 2,
  schemaVersion: 2,
  snapshotFile: 'm1-snapshot.db',
  snapshotFileSha256: 'a'.repeat(64),
  targetGoldenCases: [],
};

const metadata = {
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

describe('bundled snapshot contract', () => {
  test('derives a stable local database name from the snapshot checksum', () => {
    expect(buildLocalDatabaseName(manifest)).toBe(
      'snapshot-v2-aaaaaaaaaaaaaaaa.db',
    );
  });

  test('changes the local database name when snapshot checksum changes', () => {
    const changedManifest = {
      ...manifest,
      snapshotFileSha256: `c${manifest.snapshotFileSha256.slice(1)}`,
    };

    expect(buildLocalDatabaseName(changedManifest)).not.toBe(
      buildLocalDatabaseName(manifest),
    );
  });

  test('accepts metadata and counts matching the final manifest', () => {
    expect(() =>
      validateSnapshotMetadata(metadata, manifest, 3, 3_000),
    ).not.toThrow();
  });

  test('rejects an unsupported schema with local_data_error', () => {
    const unsupportedManifest = { ...manifest, schemaVersion: 1 };

    expect(() =>
      validateSnapshotMetadata(metadata, unsupportedManifest, 3, 3_000),
    ).toThrow(LocalDataError);

    try {
      validateSnapshotMetadata(metadata, unsupportedManifest, 3, 3_000);
    } catch (error: unknown) {
      expect(error).toMatchObject({ code: 'local_data_error' });
    }
  });

  test('rejects layout count mismatch with local_data_error', () => {
    expect(() =>
      validateSnapshotMetadata(metadata, manifest, 3, 2_999),
    ).toThrow(LocalDataError);
  });
});
