import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

import {
  createManualSelectionOutputManifest,
  createManualSelectionState,
  manualPreviewWindow,
  naturalCompare,
  nextManualSelectionState,
  previousManualSelectionState,
  rangeForStart,
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
