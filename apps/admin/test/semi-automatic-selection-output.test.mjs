import assert from 'node:assert/strict';
import test from 'node:test';

import {
  assertSemiAutomaticManifestMatchesRun,
  beginSemiAutomaticOutputOperation,
  createSemiAutomaticSelectionOutputManifest,
  parseSemiAutomaticSelectionOutputManifest,
  serializeSemiAutomaticSelectionOutputManifest,
} from '../src/features/semi-automatic-image-selection/semi-automatic-selection-output.ts';
import {
  readLocalOutputFile,
  readSemiAutomaticSelectionOutputManifest,
  sha256Hex,
  validateLocalSessionRecord,
  writeOriginalOutputBytes,
  writeSemiAutomaticSelectionOutputManifest,
} from '../src/features/semi-automatic-image-selection/semi-automatic-selection-output-storage.ts';
import { synchronizeSemiAutomaticSelectionOutput } from '../src/features/semi-automatic-image-selection/semi-automatic-selection-output-sync.ts';

const SHA_A = 'a'.repeat(64);
const SHA_B = 'b'.repeat(64);
const SHA_C = 'c'.repeat(64);

test('serializes a run-bound manifest deterministically and rejects a foreign run', () => {
  const run = runIdentity();
  const manifest = createSemiAutomaticSelectionOutputManifest({
    now: '2026-08-31T10:00:00.000Z',
    outputDirectoryName: 'selected',
    run,
  });
  const serialized = serializeSemiAutomaticSelectionOutputManifest(manifest);

  assert.deepEqual(
    parseSemiAutomaticSelectionOutputManifest(serialized),
    manifest,
  );
  assert.equal(
    serializeSemiAutomaticSelectionOutputManifest(manifest),
    serialized,
  );
  assert.throws(
    () =>
      assertSemiAutomaticManifestMatchesRun(
        manifest,
        { ...run, id: 'different-run' },
        'selected',
      ),
    /SEMI_AUTOMATIC_SELECTION_OUTPUT_MANIFEST_FOREIGN/,
  );
});

test('writes original bytes idempotently and never overwrites different content', async () => {
  const directory = new MemoryDirectory('selected');
  const source = new Blob(['original-jpeg'], { type: 'image/jpeg' });
  const checksum = await sha256Hex(source);

  assert.deepEqual(
    await writeOriginalOutputBytes({
      directory,
      expectedChecksumSha256: checksum,
      expectedSizeBytes: source.size,
      outputName: 'seq_1-9.jpg',
      source,
    }),
    { checksumSha256: checksum, created: true },
  );
  assert.deepEqual(
    await writeOriginalOutputBytes({
      directory,
      expectedChecksumSha256: checksum,
      expectedSizeBytes: source.size,
      outputName: 'seq_1-9.jpg',
      source,
    }),
    { checksumSha256: checksum, created: false },
  );

  directory.put('seq_10-18.jpg', new Blob(['foreign']));
  await assert.rejects(
    writeOriginalOutputBytes({
      directory,
      expectedChecksumSha256: checksum,
      expectedSizeBytes: source.size,
      outputName: 'seq_10-18.jpg',
      source,
    }),
    /SEMI_AUTOMATIC_SELECTION_TARGET_CONFLICT/,
  );
  assert.equal(await directory.text('seq_10-18.jpg'), 'foreign');
});

test('recovers a pending operation created before the file write and acknowledges only verified bytes', async () => {
  const directory = new MemoryDirectory('selected');
  const source = new Blob(['selected-source'], { type: 'image/jpeg' });
  const checksum = await sha256Hex(source);
  const run = runResponse();
  const range = rangeResponse({ checksum, size: source.size });
  let manifest = createSemiAutomaticSelectionOutputManifest({
    now: '2026-08-31T10:00:00.000Z',
    outputDirectoryName: directory.name,
    run: runIdentity(),
  });
  manifest = beginSemiAutomaticOutputOperation(
    manifest,
    pendingOperation({ checksum, size: source.size }),
    '2026-08-31T10:00:01.000Z',
  );
  await writeSemiAutomaticSelectionOutputManifest(directory, manifest);
  directory.put('seq_1-9.jpg', new Blob([]));

  let acknowledgementSawVerifiedFile = false;
  const result = await synchronizeSemiAutomaticSelectionOutput({
    client: {
      acknowledgeSemiAutomaticImageSelectionOutput: async (
        _runId,
        _index,
        body,
      ) => {
        const local = await readLocalOutputFile(directory, 'seq_1-9.jpg');
        acknowledgementSawVerifiedFile =
          local?.checksumSha256 === body.outputChecksumSha256;
        return { data: { ...range, revision: 2, status: 'output_synced' } };
      },
      getSemiAutomaticImageSelectionSourceAsset: async () => ({ data: source }),
    },
    directory,
    now: incrementingClock(),
    operationId: () => 'retry-operation',
    ranges: [range],
    run,
  });

  assert.equal(acknowledgementSawVerifiedFile, true);
  assert.equal(result.writtenCount, 1);
  assert.equal(result.acknowledgedCount, 1);
  assert.equal(result.manifest.pendingOperation, null);
  assert.equal(result.manifest.selections[0]?.acknowledged, true);
  assert.equal(await directory.text('seq_1-9.jpg'), 'selected-source');
});

test('recovers a pending operation after the file write without downloading it again', async () => {
  const directory = new MemoryDirectory('selected');
  const source = new Blob(['already-written'], { type: 'image/jpeg' });
  const checksum = await sha256Hex(source);
  const run = runResponse();
  const range = rangeResponse({ checksum, size: source.size });
  let manifest = createSemiAutomaticSelectionOutputManifest({
    now: '2026-08-31T10:00:00.000Z',
    outputDirectoryName: directory.name,
    run: runIdentity(),
  });
  manifest = beginSemiAutomaticOutputOperation(
    manifest,
    pendingOperation({ checksum, size: source.size }),
    '2026-08-31T10:00:01.000Z',
  );
  await writeSemiAutomaticSelectionOutputManifest(directory, manifest);
  directory.put('seq_1-9.jpg', source);
  let downloadCount = 0;

  const result = await synchronizeSemiAutomaticSelectionOutput({
    client: {
      acknowledgeSemiAutomaticImageSelectionOutput: async () => ({
        data: { ...range, revision: 2, status: 'output_synced' },
      }),
      getSemiAutomaticImageSelectionSourceAsset: async () => {
        downloadCount += 1;
        return { data: source };
      },
    },
    directory,
    now: incrementingClock(),
    ranges: [range],
    run,
  });

  assert.equal(downloadCount, 0);
  assert.equal(result.writtenCount, 0);
  assert.equal(result.manifest.selections[0]?.status, 'AUTO_SELECTED');
  assert.equal(result.manifest.selections[0]?.acknowledged, true);
});

test('reconciles a lost acknowledgement response without rewriting local output', async () => {
  const directory = new MemoryDirectory('selected');
  const source = new Blob(['acknowledgement-retry'], { type: 'image/jpeg' });
  const checksum = await sha256Hex(source);
  const range = rangeResponse({ checksum, size: source.size });

  await assert.rejects(
    synchronizeSemiAutomaticSelectionOutput({
      client: {
        acknowledgeSemiAutomaticImageSelectionOutput: async () => ({
          error: { code: 'NETWORK_RESPONSE_LOST' },
        }),
        getSemiAutomaticImageSelectionSourceAsset: async () => ({
          data: source,
        }),
      },
      directory,
      now: incrementingClock(),
      ranges: [range],
      run: runResponse(),
    }),
    /SEMI_AUTOMATIC_SELECTION_OUTPUT_ACKNOWLEDGEMENT_FAILED/,
  );
  const interrupted = await readSemiAutomaticSelectionOutputManifest(directory);
  assert.equal(interrupted?.selections[0]?.acknowledged, false);
  let networkCalls = 0;

  const result = await synchronizeSemiAutomaticSelectionOutput({
    client: {
      acknowledgeSemiAutomaticImageSelectionOutput: async () => {
        networkCalls += 1;
        return { data: range };
      },
      getSemiAutomaticImageSelectionSourceAsset: async () => {
        networkCalls += 1;
        return { data: source };
      },
    },
    directory,
    now: incrementingClock(),
    ranges: [
      {
        ...range,
        outputChecksumSha256: checksum,
        revision: 2,
        status: 'output_synced',
      },
    ],
    run: runResponse(),
  });

  assert.equal(networkCalls, 0);
  assert.equal(result.writtenCount, 0);
  assert.equal(result.manifest.selections[0]?.acknowledged, true);
  assert.equal(result.manifest.selections[0]?.serverRangeRevision, 2);
});

test('records a target conflict without replacing or acknowledging the file', async () => {
  const directory = new MemoryDirectory('selected');
  const source = new Blob(['expected'], { type: 'image/jpeg' });
  const checksum = await sha256Hex(source);
  const range = rangeResponse({ checksum, size: source.size });
  directory.put('seq_1-9.jpg', new Blob(['operator-file']));
  let acknowledgements = 0;

  const result = await synchronizeSemiAutomaticSelectionOutput({
    client: {
      acknowledgeSemiAutomaticImageSelectionOutput: async () => {
        acknowledgements += 1;
        return { data: range };
      },
      getSemiAutomaticImageSelectionSourceAsset: async () => ({ data: source }),
    },
    directory,
    now: incrementingClock(),
    ranges: [range],
    run: runResponse(),
  });

  assert.equal(acknowledgements, 0);
  assert.equal(result.conflictCount, 1);
  assert.equal(result.gapCount, 1);
  assert.equal(await directory.text('seq_1-9.jpg'), 'operator-file');
});

test('keeps only directory handles and small UI state in the local record', () => {
  const directory = new MemoryDirectory('selected');
  const record = validateLocalSessionRecord({
    outputDirectory: directory,
    outputManifestChecksumSha256: null,
    runId: 'run-1',
    sourceDirectory: { name: 'source' },
    ui: {
      activeExpectedIndex: 0,
      mode: 'syncing_output',
      scrollLeft: 12,
      scrollTop: 24,
      zoomPercent: 100,
    },
    updatedAt: '2026-08-31T10:00:00.000Z',
  });
  assert.equal(record?.runId, 'run-1');
  assert.equal('blob' in record, false);
  assert.throws(
    () =>
      validateLocalSessionRecord({
        ...record,
        jpegBytes: new Blob(['must-not-be-persisted']),
      }),
    /SEMI_AUTOMATIC_SELECTION_LOCAL_SESSION_INVALID/,
  );
  assert.throws(
    () =>
      validateLocalSessionRecord({
        ...record,
        outputDirectory: new Blob(['not-a-handle']),
      }),
    /SEMI_AUTOMATIC_SELECTION_LOCAL_SESSION_INVALID/,
  );
});

function runIdentity() {
  return {
    diagnosticsChecksumSha256: null,
    direction: 'ascending',
    expectedRangesFingerprint: SHA_B,
    firstSequenceNumber: 1,
    fullRangeSize: 9,
    groupingPolicyFingerprint: SHA_C,
    id: 'run-1',
    lastSequenceNumber: 9,
    rangeConvention: 'seq-inclusive-v1',
    recognizerFingerprint: SHA_A,
    source: {
      displayName: 'source',
      manifestChecksumSha256: SHA_B,
      sourceFingerprint: SHA_C,
    },
  };
}

function runResponse() {
  return {
    ...runIdentity(),
    checkpoint: {},
    counters: {},
    createdAt: '2026-08-31T10:00:00.000Z',
    job: {},
    revision: 1,
    source: {
      ...runIdentity().source,
      sourceCount: 1,
      sourceTotalBytes: 100,
      uploadId: 'upload-1',
    },
    status: 'analysis_complete',
    updatedAt: '2026-08-31T10:00:00.000Z',
  };
}

function rangeResponse({ checksum, size }) {
  return {
    createdAt: '2026-08-31T10:00:00.000Z',
    expectedIndex: 0,
    fileName: 'seq_1-9.jpg',
    id: 'range-1',
    outputChecksumSha256: null,
    rangeEnd: 9,
    rangeStart: 1,
    revision: 1,
    runId: 'run-1',
    selectionMethod: 'middle-of-group-v1',
    sourceChecksumSha256: checksum,
    sourceIndex: 5,
    sourceRelativePath: 'folder/photo-5.jpg',
    sourceSizeBytes: size,
    status: 'auto_selected',
    updatedAt: '2026-08-31T10:00:00.000Z',
  };
}

function pendingOperation({ checksum, size }) {
  return {
    expectedIndex: 0,
    expectedRangeRevision: 1,
    operationId: 'pending-operation',
    outputName: 'seq_1-9.jpg',
    rangeEnd: 9,
    rangeStart: 1,
    selectionStatus: 'AUTO_SELECTED',
    source: {
      checksumSha256: checksum,
      relativePath: 'folder/photo-5.jpg',
      sizeBytes: size,
      sourceIndex: 5,
    },
    startedAt: '2026-08-31T10:00:01.000Z',
  };
}

function incrementingClock() {
  let seconds = 10;
  return () => {
    seconds += 1;
    return `2026-08-31T10:00:${String(seconds).padStart(2, '0')}.000Z`;
  };
}

class MemoryDirectory {
  #files = new Map();

  constructor(name) {
    this.name = name;
  }

  async getFileHandle(name, options = {}) {
    if (!this.#files.has(name) && options.create !== true) {
      throw new DOMException('missing', 'NotFoundError');
    }
    if (!this.#files.has(name)) this.#files.set(name, new Blob([]));
    return {
      createWritable: async () => {
        let next = this.#files.get(name);
        return {
          abort: async () => undefined,
          close: async () => {
            this.#files.set(name, next);
          },
          write: async (value) => {
            next = value instanceof Blob ? value : new Blob([value]);
          },
        };
      },
      getFile: async () => this.#files.get(name),
    };
  }

  put(name, value) {
    this.#files.set(name, value);
  }

  async text(name) {
    return this.#files.get(name)?.text();
  }
}
