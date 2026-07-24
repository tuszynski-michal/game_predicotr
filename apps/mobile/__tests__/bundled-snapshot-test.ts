import {
  buildLocalDatabaseName,
  LocalDataError,
  validateSnapshotMetadata,
  type SnapshotManifest,
} from '@/data/bundled-snapshot';

const manifest: SnapshotManifest = {
  algorithmVersion: 'm1-spike.1',
  logicalContentSha256: 'b'.repeat(64),
  recordCount: 3,
  releaseVersion: 'm1-spike.1',
  schemaVersion: 1,
  snapshotFile: 'm1-spike.db',
  snapshotFileSha256: 'a'.repeat(64),
};

const metadata = {
  algorithm_version: manifest.algorithmVersion,
  logical_content_sha256: manifest.logicalContentSha256,
  release_version: manifest.releaseVersion,
  schema_version: String(manifest.schemaVersion),
};

describe('bundled snapshot contract', () => {
  test('derives a stable local database name from the snapshot checksum', () => {
    expect(buildLocalDatabaseName(manifest)).toBe(
      'snapshot-v1-aaaaaaaaaaaaaaaa.db',
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

  test('accepts metadata matching the manifest', () => {
    expect(() => validateSnapshotMetadata(metadata, manifest, 3)).not.toThrow();
  });

  test('rejects an unsupported schema with local_data_error', () => {
    const unsupportedManifest = { ...manifest, schemaVersion: 2 };

    expect(() =>
      validateSnapshotMetadata(metadata, unsupportedManifest, 3),
    ).toThrow(LocalDataError);

    try {
      validateSnapshotMetadata(metadata, unsupportedManifest, 3);
    } catch (error: unknown) {
      expect(error).toMatchObject({ code: 'local_data_error' });
    }
  });
});
