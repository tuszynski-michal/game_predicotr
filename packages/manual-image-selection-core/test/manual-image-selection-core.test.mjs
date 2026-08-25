import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

import {
  buildRemoteSourceManifestV1,
  adjacentManualNavigationStep,
  compareRemoteSourceManifestV1,
  canonicalRemoteChecksumSha256,
  createManualSelectionOutputManifest,
  createManualSelectionState,
  fitManualImageToViewport,
  manualPreviewWindow,
  naturalCompare,
  nextManualSelectionState,
  previousManualSelectionState,
  rangeForStart,
  reconcileManualSelectionStateWithOutputManifest,
  resolveManualSelectionShortcut,
  RemoteManualSelectionContractError,
  stableRemoteStringify,
  transitionRemoteBatchStatus,
  transitionRemoteCollectionStatus,
  transitionRemoteFileStatus,
  transitionRemoteHostActionStatus,
  transitionRemoteOperationStatus,
  transitionRemoteSessionStatus,
  transitionRemoteTransferStatus,
} from '../src/index.ts';

const coreSource = await readFile(
  new URL('../src/index.ts', import.meta.url),
  'utf8',
);

test('keeps the deterministic nine-layout range and undo state machine', () => {
  const initial = createManualSelectionState(1, 'ascending');
  const selected = nextManualSelectionState(
    initial,
    {
      action: 'accepted',
      imageChecksum: 'a'.repeat(64),
      imagePath: '001.jpg',
      outputName: 'seq_1-9.jpg',
      rangeEnd: 9,
      rangeStart: 1,
    },
    1,
  );

  assert.deepEqual(rangeForStart(initial.nextRangeStart), {
    start: 1,
    end: 9,
  });
  assert.equal(selected.nextRangeStart, 10);
  assert.equal(selected.currentIndex, 1);
  assert.equal(previousManualSelectionState(selected)?.nextRangeStart, 1);
});

test('reconciles a corrected output manifest before resuming a local session', () => {
  const state = {
    ...createManualSelectionState(229913, 'ascending'),
    currentIndex: 2,
    decisions: [
      {
        action: 'accepted',
        imageChecksum: 'a'.repeat(64),
        imagePath: '229904_000006.jpg',
        outputName: 'seq_229913-229921.jpg',
        rangeEnd: 229921,
        rangeStart: 229913,
      },
      {
        action: 'skipped',
        imageChecksum: null,
        imagePath: null,
        outputName: null,
        rangeEnd: 229930,
        rangeStart: 229922,
      },
      {
        action: 'accepted',
        imageChecksum: 'b'.repeat(64),
        imagePath: '229904_000026.jpg',
        outputName: 'seq_229931-229939.jpg',
        rangeEnd: 229939,
        rangeStart: 229931,
      },
    ],
    nextRangeStart: 229940,
  };
  const reconciled = reconcileManualSelectionStateWithOutputManifest(state, {
    schemaVersion: 1,
    gameId: 'local-independent-manual-image-selection',
    sessionKey: 'session-1',
    sourceDirectoryName: '229913 - 248184',
    direction: 'ascending',
    firstLayout: 222913,
    updatedAt: '2026-08-25T10:35:01.000Z',
    items: [
      {
        imageChecksum: 'a'.repeat(64),
        imagePath: '229904_000006.jpg',
        outputName: 'seq_222913-222921.jpg',
        rangeEnd: 222921,
        rangeStart: 222913,
      },
      {
        imageChecksum: 'b'.repeat(64),
        imagePath: '229904_000026.jpg',
        outputName: 'seq_222931-222939.jpg',
        rangeEnd: 222939,
        rangeStart: 222931,
      },
    ],
  });

  assert.equal(reconciled.firstLayout, 222913);
  assert.equal(reconciled.nextRangeStart, 222940);
  assert.equal(reconciled.decisions[1]?.rangeStart, 222922);
  assert.equal(reconciled.decisions[2]?.outputName, 'seq_222931-222939.jpg');
});

test('rejects a corrected manifest whose selected files do not match the session', () => {
  const state = {
    ...createManualSelectionState(229913, 'ascending'),
    decisions: [
      {
        action: 'accepted',
        imageChecksum: 'a'.repeat(64),
        imagePath: '229904_000006.jpg',
        outputName: 'seq_229913-229921.jpg',
        rangeEnd: 229921,
        rangeStart: 229913,
      },
    ],
    nextRangeStart: 229922,
  };

  assert.throws(
    () =>
      reconcileManualSelectionStateWithOutputManifest(state, {
        schemaVersion: 1,
        gameId: 'local-independent-manual-image-selection',
        sessionKey: 'session-1',
        sourceDirectoryName: '229913 - 248184',
        direction: 'ascending',
        firstLayout: 222913,
        updatedAt: '2026-08-25T10:35:01.000Z',
        items: [
          {
            imageChecksum: 'b'.repeat(64),
            imagePath: '229904_000006.jpg',
            outputName: 'seq_222913-222921.jpg',
            rangeEnd: 222921,
            rangeStart: 222913,
          },
        ],
      }),
    /Manifest nie odpowiada zapisanym plikom tej sesji/,
  );
});

test('preserves natural ordering and a bounded three-image preview policy', () => {
  assert.deepEqual(['1_10.jpg', '1_2.jpg', '1_1.jpg'].sort(naturalCompare), [
    '1_1.jpg',
    '1_2.jpg',
    '1_10.jpg',
  ]);
  assert.deepEqual(manualPreviewWindow(4, 10), [1, 2, 3, 4, 5, 6, 7]);
  assert.deepEqual(manualPreviewWindow(0, 2), [0, 1]);
  assert.deepEqual(manualPreviewWindow(3, 3), []);
});

test('shares exact keyboard semantics without stealing editable controls', () => {
  assert.equal(resolveManualSelectionShortcut({ key: 'Enter' }), 'accept');
  assert.equal(resolveManualSelectionShortcut({ key: 'f' }), 'accept');
  assert.equal(resolveManualSelectionShortcut({ key: 'Tab' }), 'skip');
  assert.equal(resolveManualSelectionShortcut({ key: 'a' }), 'undo');
  assert.equal(
    resolveManualSelectionShortcut({ ctrlKey: true, key: 'z' }),
    'undo',
  );
  assert.equal(
    resolveManualSelectionShortcut({ key: 'ArrowRight' }),
    'next_image',
  );
  assert.equal(
    resolveManualSelectionShortcut({ key: 'ArrowDown' }),
    'next_step',
  );
  assert.equal(
    resolveManualSelectionShortcut({ key: 'f', repeat: true }),
    null,
  );
  assert.equal(
    resolveManualSelectionShortcut({
      key: 'Enter',
      target: { tagName: 'input' },
    }),
    null,
  );
  assert.equal(
    resolveManualSelectionShortcut({
      key: 'ArrowDown',
      target: { tagName: 'select' },
    }),
    null,
  );
});

test('offers contiguous one-to-ten image navigation steps', () => {
  assert.equal(adjacentManualNavigationStep(7, 1), 8);
  assert.equal(adjacentManualNavigationStep(8, 1), 9);
  assert.equal(adjacentManualNavigationStep(9, 1), 10);
  assert.equal(adjacentManualNavigationStep(8, -1), 7);
  assert.equal(adjacentManualNavigationStep(1, -1), 1);
  assert.equal(adjacentManualNavigationStep(20, 1), 20);
});

test('shares viewport fitting without resampling or changing the image aspect ratio', () => {
  assert.deepEqual(
    fitManualImageToViewport(
      { width: 4000, height: 3000 },
      { width: 1000, height: 500 },
      1,
    ),
    { width: 667, height: 500 },
  );
  assert.deepEqual(
    fitManualImageToViewport(
      { width: 4000, height: 3000 },
      { width: 1000, height: 500 },
      3,
    ),
    { width: 2000, height: 1500 },
  );
  assert.equal(fitManualImageToViewport(null, null, 1), null);
});

test('materializes the existing v1 output schema without skipped decisions', () => {
  const state = nextManualSelectionState(
    createManualSelectionState(1, 'ascending'),
    {
      action: 'accepted',
      imageChecksum: 'b'.repeat(64),
      imagePath: 'source/001.jpg',
      outputName: 'seq_1-9.jpg',
      rangeEnd: 9,
      rangeStart: 1,
    },
    1,
  );
  const skipped = nextManualSelectionState(
    state,
    {
      action: 'skipped',
      imageChecksum: null,
      imagePath: null,
      outputName: null,
      rangeEnd: 18,
      rangeStart: 10,
    },
    1,
  );
  const manifest = createManualSelectionOutputManifest(
    {
      gameId: 'local-independent-manual-image-selection',
      key: 'session-1',
      sourceDirectoryName: 'source',
      state: skipped,
    },
    '2026-08-23T00:00:00.000Z',
  );

  assert.deepEqual(manifest, {
    schemaVersion: 1,
    gameId: 'local-independent-manual-image-selection',
    sessionKey: 'session-1',
    sourceDirectoryName: 'source',
    direction: 'ascending',
    firstLayout: 1,
    updatedAt: '2026-08-23T00:00:00.000Z',
    items: [
      {
        outputName: 'seq_1-9.jpg',
        imagePath: 'source/001.jpg',
        imageChecksum: 'b'.repeat(64),
        rangeStart: 1,
        rangeEnd: 9,
      },
    ],
  });
});

test('keeps browser-specific dependencies out of the shared core', () => {
  assert.doesNotMatch(coreSource, /from ['\"]react['\"]/i);
  assert.doesNotMatch(coreSource, /indexedDB|IDB[A-Z]/);
  assert.doesNotMatch(coreSource, /FileSystem(?:File|Directory)Handle/);
});

test('builds a canonical remote source manifest in natural order', async () => {
  const entries = [
    ['10.jpg', 10],
    ['2.jpg', 2],
    ['1.jpg', 1],
  ].map(([name, sizeBytes]) => ({
    relativePath: name,
    name,
    sizeBytes,
    lastModifiedMs: 1_700_000_000_000,
    mimeType: 'image/jpeg',
  }));
  const manifest = await buildRemoteSourceManifestV1(
    entries,
    'directory_handle',
  );
  const replay = await buildRemoteSourceManifestV1(
    entries.toReversed(),
    'directory_handle',
  );

  assert.deepEqual(
    manifest.entries.map((entry) => entry.relativePath),
    ['1.jpg', '2.jpg', '10.jpg'],
  );
  assert.equal(manifest.manifestChecksumSha256, replay.manifestChecksumSha256);
  assert.match(manifest.manifestChecksumSha256, /^[0-9a-f]{64}$/);
});

test('compares remote source manifests without exposing paths', async () => {
  const metadata = [
    {
      relativePath: 'batch/1.jpg',
      name: '1.jpg',
      sizeBytes: 10,
      lastModifiedMs: 100,
      mimeType: 'image/jpeg',
    },
    {
      relativePath: 'batch/2.jpg',
      name: '2.jpg',
      sizeBytes: 20,
      lastModifiedMs: 200,
      mimeType: 'image/jpeg',
    },
  ];
  const expected = await buildRemoteSourceManifestV1(
    metadata,
    'directory_handle',
  );
  const reordered = await buildRemoteSourceManifestV1(
    metadata.toReversed(),
    'directory_handle',
  );
  const changed = await buildRemoteSourceManifestV1(
    [{ ...metadata[0], sizeBytes: 11 }, metadata[1]],
    'directory_handle',
  );
  const fallback = await buildRemoteSourceManifestV1(
    metadata,
    'webkitdirectory_reselect',
  );

  assert.deepEqual(compareRemoteSourceManifestV1(expected, reordered), {
    changedFileCount: 0,
    status: 'same',
  });
  assert.deepEqual(compareRemoteSourceManifestV1(expected, changed), {
    changedFileCount: 1,
    status: 'different',
  });
  assert.deepEqual(compareRemoteSourceManifestV1(expected, fallback), {
    changedFileCount: null,
    status: 'incompatible',
  });
});

test('rejects unsafe or duplicate remote source paths with a stable code', async () => {
  const entry = {
    relativePath: '../outside.jpg',
    name: 'outside.jpg',
    sizeBytes: 1,
    lastModifiedMs: 1,
    mimeType: 'image/jpeg',
  };
  await assert.rejects(
    buildRemoteSourceManifestV1([entry], 'directory_handle'),
    (error) =>
      error instanceof RemoteManualSelectionContractError &&
      error.code === 'REMOTE_SELECTION_SOURCE_MANIFEST_INVALID',
  );
  const duplicate = { ...entry, relativePath: '1.jpg', name: '1.jpg' };
  await assert.rejects(
    buildRemoteSourceManifestV1([duplicate, duplicate], 'directory_handle'),
    (error) =>
      error instanceof RemoteManualSelectionContractError &&
      error.code === 'REMOTE_SELECTION_SOURCE_MANIFEST_INVALID',
  );
});

test('uses deterministic canonical JSON and checksum semantics', async () => {
  assert.equal(
    stableRemoteStringify({ z: 1, a: { b: 2, a: 1 } }),
    '{"a":{"a":1,"b":2},"z":1}',
  );
  const checksum = await canonicalRemoteChecksumSha256({ a: 1, b: 2 });
  assert.equal(checksum, await canonicalRemoteChecksumSha256({ b: 2, a: 1 }));
  assert.equal(
    checksum,
    '43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777',
  );
});

test('exposes fail-closed state transitions for every remote state machine', () => {
  const cases = [
    [transitionRemoteSessionStatus, 'draft', 'active', 'draft', 'completed'],
    [
      transitionRemoteCollectionStatus,
      'active',
      'completed',
      'completed',
      'active',
    ],
    [transitionRemoteBatchStatus, 'active', 'finalizing', 'active', 'draft'],
    [
      transitionRemoteFileStatus,
      'verified',
      'materialized',
      'verified',
      'discovered',
    ],
    [
      transitionRemoteOperationStatus,
      'sending',
      'applied',
      'sending',
      'queued',
    ],
    [
      transitionRemoteTransferStatus,
      'stored_temp',
      'verified',
      'stored_temp',
      'queued',
    ],
    [
      transitionRemoteHostActionStatus,
      'processing',
      'completed',
      'processing',
      'queued',
    ],
  ];
  for (const [
    transition,
    current,
    allowed,
    forbiddenCurrent,
    forbiddenTarget,
  ] of cases) {
    assert.equal(transition(current, allowed), allowed);
    assert.equal(transition(current, current), current);
    assert.throws(
      () => transition(forbiddenCurrent, forbiddenTarget),
      (error) =>
        error instanceof RemoteManualSelectionContractError &&
        error.code === 'REMOTE_SELECTION_INVALID_TRANSITION',
    );
  }
});
