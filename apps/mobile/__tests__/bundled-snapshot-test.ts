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
  schemaVersion: 3,
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
      'snapshot-v3-aaaaaaaaaaaaaaaa.db',
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

  test('accepts the production M3 manifest without fixture-only metadata', () => {
    const productionManifest: SnapshotManifest = {
      algorithmVersion: 'payout-v2',
      createdAt: '2026-07-27T00:00:00Z',
      gameCount: 1,
      games: [
        {
          columns: 5,
          datasetVersion: 7,
          datasetVersionId: '00000000-0000-0000-0000-000000000001',
          gameCode: 'game-1',
          gameId: '00000000-0000-0000-0000-000000000002',
          layoutCount: 500_000,
          mobileGameId: 1,
          rows: 3,
          rulesVersion: 4,
          rulesVersionId: '00000000-0000-0000-0000-000000000003',
          signatureCellWidth: 2,
          symbolCount: 10,
        },
      ],
      layoutCount: 500_000,
      logicalContentSha256: 'd'.repeat(64),
      manifestVersion: 1,
      releaseVersion: 'release-1',
      snapshotFile: 'snapshot.db',
      snapshotFileSha256: 'e'.repeat(64),
      snapshotSchemaVersion: 3,
      symbolCount: 10,
    };
    const productionMetadata = {
      algorithm_version: productionManifest.algorithmVersion,
      content_checksum: productionManifest.logicalContentSha256,
      created_at: productionManifest.createdAt,
      game_count: '1',
      layout_count: '500000',
      release_version: productionManifest.releaseVersion,
      snapshot_schema_version: '3',
    };

    expect(() =>
      validateSnapshotMetadata(
        productionMetadata,
        productionManifest,
        1,
        500_000,
      ),
    ).not.toThrow();
    expect(buildLocalDatabaseName(productionManifest)).toBe(
      'snapshot-v3-eeeeeeeeeeeeeeee.db',
    );
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
