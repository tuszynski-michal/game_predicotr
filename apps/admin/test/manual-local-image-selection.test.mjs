import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

import {
  createManualSelectionState,
  naturalCompare,
  nextManualSelectionState,
  previousManualSelectionState,
  rangeForStart,
  writeManualOutputManifest,
} from '../src/features/manual-image-selection/manual-image-selection.ts';

const workspaceSource = await readFile(
  new URL(
    '../src/features/manual-image-selection/manual-image-selection-workspace.tsx',
    import.meta.url,
  ),
  'utf8',
);
const selectionSource = await readFile(
  new URL(
    '../src/features/manual-image-selection/manual-image-selection.ts',
    import.meta.url,
  ),
  'utf8',
);

test('sorts image names in the same numeric order as Explorer', () => {
  const names = ['1_10.jpg', '1_2.jpg', '1_1.jpg', '1_20.jpg'];
  assert.deepEqual(names.sort(naturalCompare), [
    '1_1.jpg',
    '1_2.jpg',
    '1_10.jpg',
    '1_20.jpg',
  ]);
});

test('derives each inclusive nine-layout range from its first number', () => {
  assert.deepEqual(rangeForStart(1), { start: 1, end: 9 });
  assert.deepEqual(rangeForStart(352), { start: 352, end: 360 });
});

test('offers the requested persisted arrow navigation steps', () => {
  const initial = createManualSelectionState(1, 'ascending');
  assert.equal(initial.navigationStep, 1);
  assert.match(
    workspaceSource,
    /NAVIGATION_STEPS = \[1, 2, 5, 7, 10, 15, 20\]/,
  );
  assert.match(workspaceSource, /delta \* navigationStep/);
  assert.match(workspaceSource, /navigationStep,/);
});

test('enter advances the range and tab can keep the same photo', () => {
  const initial = createManualSelectionState(1, 'ascending');
  const next = nextManualSelectionState(
    initial,
    {
      action: 'accepted',
      imageChecksum: 'a'.repeat(64),
      imagePath: '1_000001.jpg',
      outputName: 'seq_1-9.jpg',
      rangeEnd: 9,
      rangeStart: 1,
    },
    1,
  );
  const skipped = nextManualSelectionState(
    next,
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
  assert.equal(next.nextRangeStart, 10);
  assert.equal(next.currentIndex, 1);
  assert.equal(skipped.nextRangeStart, 19);
  assert.equal(skipped.currentIndex, 1);
});

test('undo restores the previous range and removes the last decision', () => {
  const initial = createManualSelectionState(1, 'ascending');
  const selected = nextManualSelectionState(
    initial,
    {
      action: 'skipped',
      imageChecksum: null,
      imagePath: null,
      outputName: null,
      rangeEnd: 9,
      rangeStart: 1,
    },
    0,
  );
  const restored = previousManualSelectionState(selected);
  assert.ok(restored);
  assert.equal(restored.decisions.length, 0);
  assert.equal(restored.nextRangeStart, 1);
});

test('offers fullscreen and bounded zoom controls without changing the source file', () => {
  assert.match(workspaceSource, /toggleFullscreen/);
  assert.match(workspaceSource, /requestFullscreen/);
  assert.match(workspaceSource, /Powiększ zdjęcie/);
  assert.match(workspaceSource, /Math\.min\(2/);
  assert.match(workspaceSource, /manualImageSelectionFullscreenInfo/);
  assert.match(workspaceSource, /Zakres \{range\.start\}–\{range\.end\}/);
});

test('indexes handles without opening every JPEG and preloads a bounded neighbour window', () => {
  const listing = selectionSource.slice(
    selectionSource.indexOf('export async function listManualImages'),
    selectionSource.indexOf('export function naturalCompare'),
  );
  assert.doesNotMatch(listing, /getFile\(/);
  assert.match(workspaceSource, /currentImageIndex \+ 3/);
  assert.match(workspaceSource, /currentImageIndex - 3/);
  assert.match(workspaceSource, /preview\.decode\(\)/);
  assert.match(workspaceSource, /saveQueueRef/);
});

test('defines durable output and training trace manifests', () => {
  assert.match(selectionSource, /manual-image-selection-output-v1\.json/);
  assert.match(selectionSource, /manual-image-selection-trace-v1\.json/);
  assert.match(workspaceSource, /Eksportuj ślad uczenia/);
  assert.match(workspaceSource, /appendTraceEvent/);
  assert.match(workspaceSource, /visibleMilliseconds/);
  assert.equal(typeof writeManualOutputManifest, 'function');
});
