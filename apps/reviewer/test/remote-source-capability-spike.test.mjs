import assert from 'node:assert/strict';
import test from 'node:test';

import {
  REMOTE_SOURCE_CAPABILITY_REPORT_SCHEMA,
  attachCapabilityReportChecksum,
  benchmarkSyntheticManifests,
  buildRemoteSourceManifest,
  compareRelinkManifest,
  createSyntheticJpegMetadata,
  detectRemoteSourceCapabilities,
  naturalSourcePathCompare,
  normalizeRelativeSourcePath,
  queryReadPermission,
  requestReadPermission,
  sourceMetadataFromFile,
  verifyCapabilityReportChecksum,
} from './fixtures/remote-source-capability-spike.mjs';

function jpeg(relativePath, overrides = {}) {
  const name = relativePath.split('/').at(-1);
  return {
    name,
    relativePath,
    size: 350_000,
    lastModified: 1_700_000_000_000,
    type: 'image/jpeg',
    arrayBuffer() {
      throw new Error('The manifest must never read image bytes.');
    },
    ...overrides,
  };
}

test('normalizes only safe relative paths and never accepts an absolute path', () => {
  assert.equal(
    normalizeRelativeSourcePath('partia/zdjęcie_1.jpg'),
    'partia/zdjęcie_1.jpg',
  );
  for (const value of [
    '',
    '/root/image.jpg',
    'C:/images/image.jpg',
    'folder\\image.jpg',
    'folder/../image.jpg',
    'folder//image.jpg',
    'folder/',
  ]) {
    assert.throws(() => normalizeRelativeSourcePath(value));
  }
});

test('uses deterministic natural path ordering', () => {
  const values = [
    'batch/image_10.jpg',
    'batch/image_2.jpg',
    'batch/image_1.jpg',
  ];
  assert.deepEqual(values.toSorted(naturalSourcePathCompare), [
    'batch/image_1.jpg',
    'batch/image_2.jpg',
    'batch/image_10.jpg',
  ]);
});

test('builds the same metadata-only manifest regardless of input order', async () => {
  const files = [jpeg('batch/image_10.jpg'), jpeg('batch/image_2.jpg')];
  const first = await buildRemoteSourceManifest(files);
  const second = await buildRemoteSourceManifest(files.toReversed());

  assert.deepEqual(first, second);
  assert.equal(first.fileCount, 2);
  assert.deepEqual(
    first.entries.map((entry) => entry.relativePath),
    ['batch/image_2.jpg', 'batch/image_10.jpg'],
  );
  assert.equal('bytes' in first.entries[0], false);
  assert.equal('absolutePath' in first.entries[0], false);
});

test('rejects non-JPEG metadata, duplicates and invalid sizes', async () => {
  assert.throws(() => sourceMetadataFromFile(jpeg('batch/image.png')));
  assert.throws(() =>
    sourceMetadataFromFile(jpeg('batch/image.jpg', { size: -1 })),
  );
  await assert.rejects(() =>
    buildRemoteSourceManifest([
      jpeg('batch/image_1.jpg'),
      jpeg('batch/image_1.jpg'),
    ]),
  );
});

test('detects directory-handle, reselect fallback and unsupported modes', () => {
  const inputPrototype = { webkitdirectory: false };
  assert.equal(
    detectRemoteSourceCapabilities({
      isSecureContext: true,
      showDirectoryPicker() {},
      indexedDB: { open() {} },
      navigator: { storage: { getDirectory() {} } },
      HTMLInputElement: { prototype: inputPrototype },
    }).recommendedMode,
    'directory_handle',
  );
  assert.equal(
    detectRemoteSourceCapabilities({
      isSecureContext: false,
      HTMLInputElement: { prototype: inputPrototype },
    }).recommendedMode,
    'webkitdirectory_reselect',
  );
  assert.equal(
    detectRemoteSourceCapabilities({}).recommendedMode,
    'unsupported',
  );
});

test('permission checks always request read-only access', async () => {
  const queryCalls = [];
  const requestCalls = [];
  const handle = {
    async queryPermission(options) {
      queryCalls.push(options);
      return 'prompt';
    },
    async requestPermission(options) {
      requestCalls.push(options);
      return 'granted';
    },
  };

  assert.equal(await queryReadPermission(handle), 'prompt');
  assert.equal(await requestReadPermission(handle), 'granted');
  assert.deepEqual(queryCalls, [{ mode: 'read' }]);
  assert.deepEqual(requestCalls, [{ mode: 'read' }]);
});

test('relink distinguishes identical, changed and incompatible manifests', async () => {
  const expected = await buildRemoteSourceManifest([jpeg('batch/image_1.jpg')]);
  const same = await buildRemoteSourceManifest([jpeg('batch/image_1.jpg')]);
  const changed = await buildRemoteSourceManifest([
    jpeg('batch/image_1.jpg', { size: 350_001 }),
  ]);

  assert.deepEqual(compareRelinkManifest(expected, same), {
    status: 'same',
    changedFileCount: 0,
  });
  assert.deepEqual(compareRelinkManifest(expected, changed), {
    status: 'different',
    changedFileCount: 1,
  });
  assert.deepEqual(compareRelinkManifest(expected, { schemaVersion: 'v2' }), {
    status: 'incompatible',
    changedFileCount: null,
  });
});

test('benchmarks 1, 500 and 1000 metadata entries without decode or byte reads', async () => {
  let clock = 0;
  const benchmark = await benchmarkSyntheticManifests([1, 500, 1000], () => {
    clock += 0.25;
    return clock;
  });

  assert.deepEqual(
    benchmark.map((entry) => entry.fileCount),
    [1, 500, 1000],
  );
  assert.ok(benchmark.every((entry) => entry.decodedFileCount === 0));
  assert.ok(benchmark.every((entry) => entry.byteReadCount === 0));
  assert.equal(createSyntheticJpegMetadata(1000).length, 1000);
});

test('content-addresses and verifies the read-only capability report', async () => {
  const report = await attachCapabilityReportChecksum({
    schemaVersion: REMOTE_SOURCE_CAPABILITY_REPORT_SCHEMA,
    decision: 'go_with_constraints',
    benchmark: [],
  });
  assert.equal(await verifyCapabilityReportChecksum(report), true);
  assert.equal(
    await verifyCapabilityReportChecksum({ ...report, decision: 'no_go' }),
    false,
  );
});
