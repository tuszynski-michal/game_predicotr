import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

import {
  adjacentManualNavigationStep,
  createManualSelectionState,
  isMissingManualDirectoryHandleError,
  MANUAL_IMAGE_NAVIGATION_STEPS,
  naturalCompare,
  nextManualSelectionState,
  previousManualSelectionState,
  rangeForStart,
  reconcileManualSelectionStateWithOutputManifest,
  relinkManualSelectionSession,
  writeManualOutputManifest,
} from '../src/features/manual-image-selection/manual-image-selection.ts';
import {
  FileSystemManualSelectionOutputAdapter,
  FileSystemManualSelectionSourceAdapter,
} from '../src/features/manual-image-selection/manual-image-selection-fsa-adapter.ts';
import {
  latestLegacyManualSelectionSession,
  migrateLegacyManualSelectionSession,
} from '../src/features/manual-image-selection/manual-image-selection-store.ts';
import {
  initialManualSelectionCursor,
  manualSelectionDisplayPosition,
  moveManualSelectionCursor,
  resumeManualSelectionCursor,
} from '../src/features/manual-image-selection/manual-image-selection-cursor.ts';

const workspaceSource = await readFile(
  new URL(
    '../src/features/manual-image-selection/manual-image-selection-workspace.tsx',
    import.meta.url,
  ),
  'utf8',
);
const manualSelectionCoreSource = await readFile(
  new URL(
    '../../../packages/manual-image-selection-core/src/index.ts',
    import.meta.url,
  ),
  'utf8',
);
const selectionSource = await readFile(
  new URL(
    '../src/features/manual-image-selection/manual-image-selection-fsa-adapter.ts',
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

test('keeps source traversal natural while descending ranges move independently', () => {
  assert.equal(initialManualSelectionCursor(), 0);
  assert.equal(moveManualSelectionCursor(2_891, 15_000, 5), 2_896);
  assert.equal(manualSelectionDisplayPosition(2_896, 15_000), 2_897);
  assert.equal(moveManualSelectionCursor(2_896, 15_000, -1), 2_895);
});

test('migrates a legacy descending cursor according to its trace order', () => {
  const images = [
    { name: '001.jpg', relativePath: '001.jpg' },
    { name: '002.jpg', relativePath: '002.jpg' },
    { name: '003.jpg', relativePath: '003.jpg' },
    { name: '004.jpg', relativePath: '004.jpg' },
  ];
  const naturallyPresented = resumeManualSelectionCursor({
    currentIndex: 1,
    decisions: [],
    direction: 'descending',
    images,
    traceEvents: [
      {
        decoded: true,
        eventIndex: 0,
        gameId: 'local',
        imagePath: '002.jpg',
        kind: 'accepted',
        rangeEnd: 9,
        rangeStart: 1,
        recordedAt: '2026-08-28T10:00:00.000Z',
        sessionKey: 'session',
        sourceIndex: 1,
        visibleMilliseconds: 300,
      },
    ],
  });
  const reversedPresented = resumeManualSelectionCursor({
    currentIndex: 1,
    decisions: [],
    direction: 'descending',
    images,
    traceEvents: [
      {
        decoded: true,
        eventIndex: 0,
        gameId: 'local',
        imagePath: '003.jpg',
        kind: 'accepted',
        rangeEnd: 9,
        rangeStart: 1,
        recordedAt: '2026-08-28T10:00:00.000Z',
        sessionKey: 'session',
        sourceIndex: 1,
        visibleMilliseconds: 300,
      },
    ],
  });
  const untracedLegacy = resumeManualSelectionCursor({
    currentIndex: 1,
    decisions: [],
    direction: 'descending',
    images,
    traceEvents: [],
  });
  const canonicalSession = resumeManualSelectionCursor({
    cursorSemantics: 'source_ordinal_v1',
    currentIndex: 1,
    decisions: [],
    direction: 'descending',
    images,
    traceEvents: [],
  });

  assert.equal(naturallyPresented.currentIndex, 1);
  assert.equal(reversedPresented.currentIndex, 2);
  assert.equal(untracedLegacy.currentIndex, 2);
  assert.equal(canonicalSession.currentIndex, 1);
  assert.equal(naturallyPresented.migratedLegacyCursor, true);
  assert.equal(canonicalSession.migratedLegacyCursor, true);
  assert.equal(reversedPresented.cursorSemantics, 'source_path_v3');
});

test('does not treat a viewed trace as proof of an old descending cursor order', () => {
  const images = [
    { name: '001.jpg', relativePath: '001.jpg' },
    { name: '002.jpg', relativePath: '002.jpg' },
    { name: '003.jpg', relativePath: '003.jpg' },
    { name: '004.jpg', relativePath: '004.jpg' },
  ];
  const resumed = resumeManualSelectionCursor({
    currentIndex: 1,
    decisions: [],
    direction: 'descending',
    images,
    traceEvents: [
      {
        decoded: true,
        eventIndex: 0,
        gameId: 'local',
        imagePath: '002.jpg',
        kind: 'viewed',
        rangeEnd: 9,
        rangeStart: 1,
        recordedAt: '2026-08-28T10:00:00.000Z',
        sessionKey: 'session',
        sourceIndex: 1,
        visibleMilliseconds: 300,
      },
    ],
  });

  assert.equal(resumed.currentIndex, 2);
});

test('resumes a v3 descending selection by the persisted source path, not an ordinal', () => {
  const images = [
    { name: '001.jpg', relativePath: '001.jpg' },
    { name: '002.jpg', relativePath: '002.jpg' },
    { name: '003.jpg', relativePath: '003.jpg' },
    { name: '004.jpg', relativePath: '004.jpg' },
  ];
  const resumed = resumeManualSelectionCursor({
    cursorSemantics: 'source_path_v3',
    currentImagePath: '002.jpg',
    currentIndex: 3,
    decisions: [],
    direction: 'descending',
    images,
    traceEvents: [],
  });

  assert.equal(resumed.currentIndex, 1);
  assert.equal(resumed.currentImagePath, '002.jpg');
  assert.equal(resumed.migratedLegacyCursor, false);
});

test('repairs a descending v2 source path from the next natural item after the last accepted file', () => {
  const images = [
    { name: '001.jpg', relativePath: '001.jpg' },
    { name: '002.jpg', relativePath: '002.jpg' },
    { name: '003.jpg', relativePath: '003.jpg' },
    { name: '004.jpg', relativePath: '004.jpg' },
  ];
  const resumed = resumeManualSelectionCursor({
    cursorSemantics: 'source_path_v2',
    currentImagePath: '002.jpg',
    currentIndex: 1,
    decisions: [
      {
        action: 'accepted',
        imageChecksum: 'a'.repeat(64),
        imagePath: '003.jpg',
        outputName: 'seq_10-18.jpg',
        rangeEnd: 18,
        rangeStart: 10,
      },
    ],
    direction: 'descending',
    images,
    traceEvents: [],
  });

  assert.equal(resumed.currentIndex, 3);
  assert.equal(resumed.currentImagePath, '004.jpg');
  assert.equal(resumed.cursorSemantics, 'source_path_v3');
  assert.equal(resumed.migratedLegacyCursor, true);
});

test('repairs a previously promoted descending v1 cursor from its last accepted file', () => {
  const images = [
    { name: '001.jpg', relativePath: '001.jpg' },
    { name: '002.jpg', relativePath: '002.jpg' },
    { name: '003.jpg', relativePath: '003.jpg' },
    { name: '004.jpg', relativePath: '004.jpg' },
  ];
  const resumed = resumeManualSelectionCursor({
    cursorSemantics: 'source_ordinal_v1',
    currentIndex: 2,
    decisions: [
      {
        action: 'accepted',
        imageChecksum: 'a'.repeat(64),
        imagePath: '003.jpg',
        outputName: 'seq_1-9.jpg',
        rangeEnd: 9,
        rangeStart: 1,
      },
    ],
    direction: 'descending',
    images,
    traceEvents: [],
  });

  assert.equal(resumed.currentIndex, 3);
  assert.equal(resumed.currentImagePath, '004.jpg');
  assert.equal(resumed.cursorSemantics, 'source_path_v3');
  assert.equal(resumed.migratedLegacyCursor, true);
});

test('fails closed when a persisted cursor image no longer exists in the source', () => {
  assert.throws(
    () =>
      resumeManualSelectionCursor({
        cursorSemantics: 'source_path_v3',
        currentImagePath: 'missing.jpg',
        currentIndex: 0,
        decisions: [],
        direction: 'descending',
        images: [{ name: '001.jpg', relativePath: '001.jpg' }],
        traceEvents: [],
      }),
    /MANUAL_SELECTION_CURSOR_IMAGE_MISSING/,
  );
});

test('adopts the newest legacy game-scoped session for the independent workspace', () => {
  const session = (gameId, key, updatedAt) => ({
    gameId,
    key,
    state: { updatedAt },
  });
  const newest = session('game-new', 'session-new', '2026-08-22T12:00:00Z');
  const selected = latestLegacyManualSelectionSession(
    [
      session(
        'local-independent-manual-image-selection',
        'current',
        '2026-08-23T12:00:00Z',
      ),
      session('game-old', 'session-old', '2026-08-20T12:00:00Z'),
      newest,
    ],
    'local-independent-manual-image-selection',
  );

  assert.equal(selected, newest);
});

test('copies only the adopted session trace without mutating its legacy record', () => {
  const legacy = {
    gameId: 'game-old',
    key: 'session-old',
    state: { updatedAt: '2026-08-22T12:00:00Z' },
  };
  const matching = {
    eventIndex: 0,
    gameId: 'game-old',
    sessionKey: 'session-old',
  };
  const migrated = migrateLegacyManualSelectionSession(
    legacy,
    [
      matching,
      { ...matching, eventIndex: 1, sessionKey: 'other-session' },
      { ...matching, eventIndex: 2, gameId: 'other-game' },
    ],
    'local-independent-manual-image-selection',
  );

  assert.equal(legacy.gameId, 'game-old');
  assert.equal(
    migrated.record.gameId,
    'local-independent-manual-image-selection',
  );
  assert.deepEqual(migrated.traceEvents, [
    {
      ...matching,
      gameId: 'local-independent-manual-image-selection',
    },
  ]);
});

test('recognizes a stale directory handle and relinks it without resetting state', () => {
  assert.equal(
    isMissingManualDirectoryHandleError({ name: 'NotFoundError' }),
    true,
  );
  assert.equal(
    isMissingManualDirectoryHandleError({
      message:
        'A requested file or directory could not be found at the time an operation was processed.',
    }),
    true,
  );
  const state = createManualSelectionState(100, 'ascending');
  const legacy = {
    gameId: 'local-independent-manual-image-selection',
    key: 'session-key',
    outputDirectory: { name: 'old-output' },
    sourceDirectory: { name: 'old-source' },
    sourceDirectoryName: 'old-source',
    state,
  };
  const sourceDirectory = { name: 'relinked-source' };
  const outputDirectory = { name: 'relinked-output' };

  const repaired = relinkManualSelectionSession(
    legacy,
    sourceDirectory,
    outputDirectory,
  );

  assert.equal(repaired.state, state);
  assert.equal(repaired.key, legacy.key);
  assert.equal(repaired.sourceDirectory, sourceDirectory);
  assert.equal(repaired.outputDirectory, outputDirectory);
  assert.equal(repaired.sourceDirectoryName, 'relinked-source');
  assert.equal(legacy.sourceDirectoryName, 'old-source');
  assert.match(workspaceSource, /Wznów z ponownie wybranymi folderami/);
  assert.match(workspaceSource, /Wybierz ponownie folder źródłowy/);
  assert.match(workspaceSource, /Wybierz ponownie folder wynikowy/);
  assert.match(workspaceSource, /resumeRecovery !== null/);
});

test('derives each inclusive nine-layout range from its first number', () => {
  assert.deepEqual(rangeForStart(1), { start: 1, end: 9 });
  assert.deepEqual(rangeForStart(352), { start: 352, end: 360 });
});

test('offers an explicit nine-layout range correction without enabling shortcuts in its editor', () => {
  assert.match(workspaceSource, /manualImageSelectionRangeButton/);
  assert.match(workspaceSource, /openRangeEditor/);
  assert.match(workspaceSource, /rangeEnd !== rangeStart \+ 8/);
  assert.match(workspaceSource, /nextRangeStart: rangeStart/);
  assert.match(workspaceSource, /busyRef\.current \|\| rangeEditorOpen/);
  assert.match(stylesSource, /\.manualImageSelectionRangeEditor\s*\{/);
  assert.match(stylesSource, /\.manualImageSelectionRangeButton\s*\{/);
});

test('resumes only after synchronizing a matching output manifest', () => {
  assert.equal(
    typeof reconcileManualSelectionStateWithOutputManifest,
    'function',
  );
  assert.match(workspaceSource, /readManualOutputManifest/);
  assert.match(
    workspaceSource,
    /reconcileManualSelectionStateWithOutputManifest/,
  );
  assert.match(
    workspaceSource,
    /Numeracja została zsynchronizowana z manifestem/,
  );
  assert.match(selectionSource, /manual-image-selection-output-v1\.json/);
});

test('offers the requested persisted arrow navigation steps', () => {
  const initial = createManualSelectionState(1, 'ascending');
  assert.equal(initial.navigationStep, 1);
  assert.match(workspaceSource, /MANUAL_IMAGE_NAVIGATION_STEPS\.map/);
  assert.deepEqual(
    MANUAL_IMAGE_NAVIGATION_STEPS,
    [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20],
  );
  assert.match(workspaceSource, /delta \* navigationStep/);
  assert.match(workspaceSource, /navigationStep,/);
});

test('up and down arrows move by one configured navigation step', () => {
  assert.equal(adjacentManualNavigationStep(2, 1), 3);
  assert.equal(adjacentManualNavigationStep(5, 1), 6);
  assert.equal(adjacentManualNavigationStep(7, 1), 8);
  assert.equal(adjacentManualNavigationStep(8, 1), 9);
  assert.equal(adjacentManualNavigationStep(9, 1), 10);
  assert.equal(adjacentManualNavigationStep(3, -1), 2);
  assert.equal(adjacentManualNavigationStep(1, -1), 1);
  assert.equal(adjacentManualNavigationStep(20, 1), 20);
  assert.match(manualSelectionCoreSource, /input\.key === 'ArrowDown'/);
  assert.match(workspaceSource, /changeNavigationStepByDirection\(1\)/);
  assert.match(manualSelectionCoreSource, /input\.key === 'ArrowUp'/);
  assert.match(workspaceSource, /changeNavigationStepByDirection\(-1\)/);
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
  assert.match(workspaceSource, /fitManualImageToViewport/);
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
    selectionSource.indexOf('async listImages'),
    selectionSource.indexOf(
      '\n}\n\nexport class FileSystemManualSelectionOutputAdapter',
    ) + 2,
  );
  assert.doesNotMatch(listing, /getFile\(/);
  assert.match(workspaceSource, /manualPreviewWindow\(/);
  assert.match(workspaceSource, /preview\.decode\(\)/);
  assert.match(workspaceSource, /saveQueueRef/);
});

test('keeps source listing read-only and naturally ordered through the source port', async () => {
  let openedFiles = 0;
  const file = (name) => ({
    kind: 'file',
    name,
    getFile: async () => {
      openedFiles += 1;
      return new File(['jpeg'], name, { type: 'image/jpeg' });
    },
  });
  const folder = (name, entries) => ({
    kind: 'directory',
    name,
    entries: async function* () {
      yield* entries;
    },
  });
  const directory = folder('root', [
    ['10.jpg', file('10.jpg')],
    ['nested', folder('nested', [['2.jpeg', file('2.jpeg')]])],
    ['ignore.png', file('ignore.png')],
  ]);

  const images = await new FileSystemManualSelectionSourceAdapter(
    directory,
  ).listImages();

  assert.deepEqual(
    images.map((image) => image.relativePath),
    ['10.jpg', 'nested/2.jpeg'],
  );
  assert.equal(openedFiles, 0);
});

test('output port preserves v1 manifests and never removes a foreign file', async () => {
  const saved = new Map();
  const directory = {
    getFileHandle: async (name, options) => {
      if (options?.create !== true && !saved.has(name)) {
        throw new DOMException('missing', 'NotFoundError');
      }
      return {
        createWritable: async () => ({
          abort: async () => undefined,
          close: async () => undefined,
          write: async (value) => {
            const content =
              typeof value === 'string'
                ? value
                : await new Response(value).text();
            saved.set(name, new File([content], name));
          },
        }),
        getFile: async () => saved.get(name),
      };
    },
    removeEntry: async (name) => saved.delete(name),
  };
  const adapter = new FileSystemManualSelectionOutputAdapter(directory);
  const state = nextManualSelectionState(
    createManualSelectionState(1, 'ascending'),
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
  const record = {
    gameId: 'local-independent-manual-image-selection',
    key: 'session-1',
    sourceDirectoryName: 'source',
    state,
  };

  await adapter.writeOutputManifest(record);
  const manifest = JSON.parse(
    await saved.get('manual-image-selection-output-v1.json').text(),
  );
  assert.equal(manifest.schemaVersion, 1);
  assert.deepEqual(manifest.items, [
    {
      imageChecksum: 'a'.repeat(64),
      imagePath: '001.jpg',
      outputName: 'seq_1-9.jpg',
      rangeEnd: 9,
      rangeStart: 1,
    },
  ]);

  saved.set('seq_1-9.jpg', new File(['foreign'], 'seq_1-9.jpg'));
  await assert.rejects(
    adapter.removeManagedOutput(state.decisions[0]),
    /Nie usuwam obcego pliku/,
  );
  assert.equal(saved.has('seq_1-9.jpg'), true);
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
  assert.match(workspaceSource, /resolveManualSelectionShortcut/);
  assert.match(manualSelectionCoreSource, /key === 'f'/);
  assert.match(manualSelectionCoreSource, /key === 'a'/);
  assert.match(workspaceSource, /void acceptCurrent\(\)/);
  assert.match(workspaceSource, /void undoLast\(\)/);
  assert.match(manualSelectionCoreSource, /tagName === 'INPUT'/);
  assert.match(manualSelectionCoreSource, /tagName === 'SELECT'/);
});
