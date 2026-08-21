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
const stylesSource = await readFile(
  new URL('../src/app/globals.css', import.meta.url),
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
    /NAVIGATION_STEPS = \[1, 2, 3, 4, 5, 6, 7, 10, 15, 20\]/,
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
  assert.match(workspaceSource, /Math\.min\(30/);
  assert.match(workspaceSource, /zoom >= 30/);
  assert.match(workspaceSource, /manualImageSelectionFullscreenInfo/);
  assert.match(workspaceSource, /Zakres \{range\.start\}–\{range\.end\}/);
});

test('uses scrollable layout dimensions for zoomed images instead of a visual transform', () => {
  assert.match(workspaceSource, /fitImageToViewport/);
  assert.match(workspaceSource, /manualImageSelectionImageViewport/);
  assert.match(workspaceSource, /manualImageSelectionImageCanvas/);
  assert.match(workspaceSource, /imageViewportRef\.current\?\.scrollTo/);
  assert.doesNotMatch(workspaceSource, /transform:\s*`scale/);
  assert.match(
    stylesSource,
    /\.manualImageSelectionImageViewport\s*\{[\s\S]*overflow-x:\s*hidden;[\s\S]*overflow-y:\s*auto;/,
  );
  assert.match(
    stylesSource,
    /\.manualImageSelectionImageViewport\s*\{[\s\S]*justify-content:\s*center;/,
  );
  assert.match(
    stylesSource,
    /\.manualImageSelectionViewer:fullscreen\s*\{[\s\S]*grid-template-rows:\s*auto minmax\(0, 1fr\);/,
  );
});

test('keeps the vertical image position while navigating between photos', () => {
  assert.match(workspaceSource, /imageScrollTopRef/);
  assert.match(workspaceSource, /pendingImageScrollRestoreRef/);
  assert.match(
    workspaceSource,
    /viewport\.scrollTop = imageScrollTopRef\.current/,
  );
  assert.match(workspaceSource, /onScroll=/);
  assert.doesNotMatch(workspaceSource, /scrollTo\(\{ top: 0 \}\)/);
});

test('renders the navigation step selector with a readable dark popup', () => {
  assert.match(
    stylesSource,
    /\.manualImageSelectionStep select\s*\{[\s\S]*background:\s*#0b1524;[\s\S]*color-scheme:\s*dark;/,
  );
  assert.match(
    stylesSource,
    /\.manualImageSelectionStep select option\s*\{[\s\S]*background:\s*#0b1524;[\s\S]*color:\s*#f8fafc;/,
  );
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

test('supports single-key accept and undo shortcuts without hijacking form fields', () => {
  assert.match(workspaceSource, /key === 'f'/);
  assert.match(workspaceSource, /key === 'a'/);
  assert.match(workspaceSource, /void acceptCurrent\(\)/);
  assert.match(workspaceSource, /void undoLast\(\)/);
  assert.match(workspaceSource, /target\?\.tagName === 'INPUT'/);
  assert.match(workspaceSource, /target\?\.tagName === 'SELECT'/);
});
