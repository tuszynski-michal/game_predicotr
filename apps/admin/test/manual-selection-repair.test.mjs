import assert from 'node:assert/strict';
import test from 'node:test';

import {
  deleteRepairFile,
  inspectRepairDirectory,
  outputBounds,
  readActiveFilledGapsManifest,
  readRepairManifest,
  writeRepairManifest,
  writeRepairFile,
} from '../src/features/manual-image-selection/manual-selection-repair-storage.ts';
import { sha256Hex } from '../src/features/manual-image-selection/manual-image-selection-fsa-adapter.ts';

class MemoryFileHandle {
  kind = 'file';

  constructor(name, file) {
    this.name = name;
    this.file = file;
    this.getFileCalls = 0;
  }

  async getFile() {
    this.getFileCalls += 1;
    return this.file;
  }

  async createWritable() {
    return {
      abort: async () => undefined,
      close: async () => undefined,
      write: async (value) => {
        const body =
          typeof value === 'string' ? value : await new Response(value).text();
        this.file = new File([body], this.name, { type: 'application/json' });
      },
    };
  }
}

class MemoryDirectoryHandle {
  kind = 'directory';

  constructor(name, entries) {
    this.name = name;
    this.files = new Map(
      entries.map((file) => [file.name, new MemoryFileHandle(file.name, file)]),
    );
  }

  async *entries() {
    yield* this.files.entries();
  }

  async getFileHandle(name, options) {
    const existing = this.files.get(name);
    if (existing !== undefined) return existing;
    if (options?.create === true) {
      const created = new MemoryFileHandle(name, new File([], name));
      this.files.set(name, created);
      return created;
    }
    throw new DOMException('missing', 'NotFoundError');
  }

  async removeEntry(name) {
    if (!this.files.delete(name))
      throw new DOMException('missing', 'NotFoundError');
  }
}

test('inspects only top-level seq JPEGs and ignores non-image artifacts', async () => {
  const directory = new MemoryDirectoryHandle('selected', [
    new File(['a'], 'seq_10-18.jpg', { type: 'image/jpeg' }),
    new File(['b'], 'seq_1-9.jpeg', { type: 'image/jpeg' }),
    new File(['{}'], 'notes.json', { type: 'application/json' }),
  ]);
  const snapshot = await inspectRepairDirectory(directory);
  assert.deepEqual(
    snapshot.files.map((file) => file.fileName),
    ['seq_1-9.jpeg', 'seq_10-18.jpg'],
  );
  assert.equal(snapshot.repairManifest.collectionStart, 1);
  assert.equal(snapshot.repairManifest.collectionEnd, 18);
});

test('derives descending output bounds from every persisted item', () => {
  assert.deepEqual(
    outputBounds({
      direction: 'descending',
      firstLayout: 28,
      gameId: 'local',
      items: [
        {
          activeBoardCount: 9,
          imageChecksum: 'a'.repeat(64),
          imagePath: 'source/high.jpg',
          outputName: 'seq_28-36.jpg',
          rangeEnd: 36,
          rangeStart: 28,
        },
        {
          activeBoardCount: 9,
          imageChecksum: 'b'.repeat(64),
          imagePath: 'source/low.jpg',
          outputName: 'seq_1-9.jpg',
          rangeEnd: 9,
          rangeStart: 1,
        },
      ],
      schemaVersion: 2,
      selectionComplete: true,
      sequenceUpperBound: 36,
      sessionKey: 'descending-session',
      sourceDirectoryName: 'source',
      updatedAt: '2026-09-06T00:00:00.000Z',
    }),
    { end: 36, start: 1 },
  );
});

test('inspection persists widened bounds for an existing corrupted repair manifest', async () => {
  const low = new File(['low'], 'seq_1-9.jpg', { type: 'image/jpeg' });
  const high = new File(['high'], 'seq_28-36.jpg', { type: 'image/jpeg' });
  const directory = new MemoryDirectoryHandle('descending', [low, high]);
  const corrupted = {
    activeFiles: [
      {
        checksumSha256: null,
        end: 9,
        fileName: 'seq_1-9.jpg',
        start: 1,
      },
      {
        checksumSha256: null,
        end: 36,
        fileName: 'seq_28-36.jpg',
        start: 28,
      },
    ],
    collectionEnd: 36,
    collectionStart: 28,
    deletedRanges: [{ end: 27, start: 19 }],
    operations: [],
    pendingOperation: null,
    repairKey: 'repair-descending',
    revision: 7,
    schemaVersion: 'manual-image-selection-repair-v1',
    selectedDirectoryName: 'descending',
    updatedAt: '2026-09-06T00:00:00.000Z',
  };
  const handle = await directory.getFileHandle(
    'manual-image-selection-repair-v1.json',
    { create: true },
  );
  const writable = await handle.createWritable();
  await writable.write(JSON.stringify(corrupted));
  await writable.close();
  const outputHandle = await directory.getFileHandle(
    'manual-image-selection-output-v1.json',
    { create: true },
  );
  const outputWritable = await outputHandle.createWritable();
  await outputWritable.write(
    JSON.stringify({
      direction: 'descending',
      firstLayout: 28,
      gameId: 'local',
      items: [
        {
          activeBoardCount: 9,
          imageChecksum: await sha256Hex(low),
          imagePath: 'source/low.jpg',
          outputName: 'seq_1-9.jpg',
          rangeEnd: 9,
          rangeStart: 1,
        },
        {
          activeBoardCount: 9,
          imageChecksum: await sha256Hex(high),
          imagePath: 'source/high.jpg',
          outputName: 'seq_28-36.jpg',
          rangeEnd: 36,
          rangeStart: 28,
        },
      ],
      schemaVersion: 2,
      selectionComplete: true,
      sequenceUpperBound: 36,
      sessionKey: 'descending-session',
      sourceDirectoryName: 'source',
      updatedAt: '2026-09-06T00:00:00.000Z',
    }),
  );
  await outputWritable.close();

  const snapshot = await inspectRepairDirectory(directory);

  assert.equal(snapshot.repairManifest.collectionStart, 1);
  assert.equal(snapshot.repairManifest.collectionEnd, 36);
  assert.equal(snapshot.repairManifest.revision, 8);
  assert.equal((await readRepairManifest(directory)).collectionStart, 1);
  assert.ok(directory.files.has('manual-image-selection-repair-v2.json'));
  assert.equal('operations' in snapshot.repairManifest, false);
  assert.equal(snapshot.outputManifest.selectionComplete, false);
  assert.equal(
    JSON.parse(await (await outputHandle.getFile()).text()).selectionComplete,
    false,
  );
});

test('blocks a malformed top-level JPEG before creating repair state', async () => {
  const directory = new MemoryDirectoryHandle('selected', [
    new File(['a'], 'photo.jpg', { type: 'image/jpeg' }),
  ]);
  await assert.rejects(
    inspectRepairDirectory(directory),
    /INVALID_SEQUENCE_FILE_NAME/,
  );
});

test('writes and reads only the same repair manifest owner', async () => {
  const directory = new MemoryDirectoryHandle('selected', [
    new File(['a'], 'seq_1-9.jpg', { type: 'image/jpeg' }),
  ]);
  const snapshot = await inspectRepairDirectory(directory);
  await writeRepairManifest(directory, snapshot.repairManifest);
  assert.equal(
    (await readRepairManifest(directory)).repairKey,
    snapshot.repairManifest.repairKey,
  );
  await assert.rejects(
    writeRepairManifest(directory, {
      ...snapshot.repairManifest,
      repairKey: 'foreign',
    }),
    /FOREIGN_REPAIR_MANIFEST/,
  );
});

test('checks each persisted seq JPEG once when resuming a verified output', async () => {
  const first = new File(['first'], 'seq_1-9.jpg', { type: 'image/jpeg' });
  const second = new File(['second'], 'seq_10-18.jpg', {
    type: 'image/jpeg',
  });
  const directory = new MemoryDirectoryHandle('selected', [first, second]);
  const output = {
    direction: 'ascending',
    firstLayout: 1,
    gameId: 'local',
    items: [
      {
        activeBoardCount: 9,
        imageChecksum: await sha256Hex(first),
        imagePath: 'source/first.jpg',
        outputName: 'seq_1-9.jpg',
        rangeEnd: 9,
        rangeStart: 1,
      },
      {
        activeBoardCount: 9,
        imageChecksum: await sha256Hex(second),
        imagePath: 'source/second.jpg',
        outputName: 'seq_10-18.jpg',
        rangeEnd: 18,
        rangeStart: 10,
      },
    ],
    schemaVersion: 2,
    selectionComplete: true,
    sequenceUpperBound: 18,
    sessionKey: 'session',
    sourceDirectoryName: 'source',
    updatedAt: '2026-09-02T00:00:00.000Z',
  };
  const outputHandle = await directory.getFileHandle(
    'manual-image-selection-output-v1.json',
    { create: true },
  );
  const outputWritable = await outputHandle.createWritable();
  await outputWritable.write(JSON.stringify(output));
  await outputWritable.close();

  const firstInspection = await inspectRepairDirectory(directory);
  await writeRepairManifest(directory, firstInspection.repairManifest);
  for (const file of directory.files.values()) file.getFileCalls = 0;

  await inspectRepairDirectory(directory);

  assert.equal(directory.files.get('seq_1-9.jpg').getFileCalls, 1);
  assert.equal(directory.files.get('seq_10-18.jpg').getFileCalls, 1);
});

test('rebuilds a stale output manifest after a completed delete before output synchronization', async () => {
  const first = new File(['first'], 'seq_1-9.jpg', { type: 'image/jpeg' });
  const second = new File(['second'], 'seq_10-18.jpg', {
    type: 'image/jpeg',
  });
  const directory = new MemoryDirectoryHandle('selected', [first, second]);
  const outputHandle = await directory.getFileHandle(
    'manual-image-selection-output-v1.json',
    { create: true },
  );
  const outputWritable = await outputHandle.createWritable();
  await outputWritable.write(
    JSON.stringify({
      direction: 'ascending',
      firstLayout: 1,
      gameId: 'local',
      items: [
        {
          activeBoardCount: 9,
          imageChecksum: await sha256Hex(first),
          imagePath: 'source/first.jpg',
          outputName: 'seq_1-9.jpg',
          rangeEnd: 9,
          rangeStart: 1,
        },
        {
          activeBoardCount: 9,
          imageChecksum: await sha256Hex(second),
          imagePath: 'source/second.jpg',
          outputName: 'seq_10-18.jpg',
          rangeEnd: 18,
          rangeStart: 10,
        },
      ],
      schemaVersion: 2,
      selectionComplete: true,
      sequenceUpperBound: 18,
      sessionKey: 'session',
      sourceDirectoryName: 'source',
      updatedAt: '2026-09-15T00:00:00.000Z',
    }),
  );
  await outputWritable.close();
  const snapshot = await inspectRepairDirectory(directory);
  await directory.removeEntry('seq_1-9.jpg');
  await writeRepairManifest(directory, {
    ...snapshot.repairManifest,
    activeFiles: snapshot.repairManifest.activeFiles.filter(
      (file) => file.fileName !== 'seq_1-9.jpg',
    ),
    deletedRanges: [{ end: 9, start: 1 }],
    deletedSources: [
      {
        checksumSha256: await sha256Hex(first),
        end: 9,
        fileName: 'seq_1-9.jpg',
        sourceIndex: 0,
        sourcePath: 'source/first.jpg',
        start: 1,
      },
    ],
    revision: snapshot.repairManifest.revision + 1,
  });

  const recovered = await inspectRepairDirectory(directory);

  assert.deepEqual(
    recovered.outputManifest.items.map((item) => item.outputName),
    ['seq_10-18.jpg'],
  );
  assert.equal(recovered.outputManifest.selectionComplete, false);
});

test('fills exact bytes and safely removes only the checksummed repair file', async () => {
  const directory = new MemoryDirectoryHandle('selected', [
    new File(['left'], 'seq_1-9.jpg', { type: 'image/jpeg' }),
    new File(['right'], 'seq_19-27.jpg', { type: 'image/jpeg' }),
  ]);
  const source = new MemoryFileHandle(
    'source.jpg',
    new File(['chosen-original-bytes'], 'source.jpg', { type: 'image/jpeg' }),
  );
  const snapshot = await inspectRepairDirectory(directory);
  await writeRepairManifest(directory, snapshot.repairManifest);
  const filled = await writeRepairFile({
    directory,
    kind: 'fill',
    manifest: snapshot.repairManifest,
    outputManifest: null,
    source,
    sourceIndex: 4,
    sourcePath: 'base/source.jpg',
    target: { end: 18, start: 10 },
  });
  assert.equal(
    await (
      await directory.getFileHandle('seq_10-18.jpg')
    )
      .getFile()
      .then((file) => file.text()),
    'chosen-original-bytes',
  );
  const handoff = await readActiveFilledGapsManifest(directory);
  assert.deepEqual(
    handoff.entries.map((entry) => ({
      fileName: entry.fileName,
      sourcePath: entry.sourcePath,
    })),
    [{ fileName: 'seq_10-18.jpg', sourcePath: 'base/source.jpg' }],
  );
  assert.ok(directory.files.has('manual-image-selection-filled-gaps-v1.json'));
  const removed = await deleteRepairFile({
    directory,
    fileName: 'seq_10-18.jpg',
    kind: 'undo_fill',
    manifest: filled.manifest,
    outputManifest: null,
    sourceIndex: 4,
    sourcePath: 'base/source.jpg',
  });
  await assert.rejects(directory.getFileHandle('seq_10-18.jpg'), /missing/);
  assert.deepEqual(removed.manifest.deletedRanges, [{ end: 18, start: 10 }]);
  assert.deepEqual((await readActiveFilledGapsManifest(directory)).entries, []);
  assert.deepEqual(removed.manifest.filledGapEntries, []);
});

test('refuses a delete when the staged source checksum no longer matches the local file', async () => {
  const directory = new MemoryDirectoryHandle('selected', [
    new File(['local-bytes'], 'seq_1-9.jpg', { type: 'image/jpeg' }),
  ]);
  const snapshot = await inspectRepairDirectory(directory);
  await writeRepairManifest(directory, snapshot.repairManifest);

  await assert.rejects(
    deleteRepairFile({
      directory,
      expectedChecksumSha256: 'a'.repeat(64),
      fileName: 'seq_1-9.jpg',
      kind: 'delete',
      manifest: snapshot.repairManifest,
      outputManifest: null,
      sourceIndex: 0,
      sourcePath: 'seq_1-9.jpg',
    }),
    /REPAIR_FILE_CHECKSUM_MISMATCH:seq_1-9\.jpg/,
  );
  assert.equal(
    await directory.getFileHandle('seq_1-9.jpg').then((handle) => handle.name),
    'seq_1-9.jpg',
  );
});

test('delete workspace uses fixed step one, immediate snapshot and background persistence', async () => {
  const source = await import('node:fs/promises').then(({ readFile }) =>
    readFile(
      new URL(
        '../src/features/manual-image-selection/manual-selection-repair-workspace.tsx',
        import.meta.url,
      ),
      'utf8',
    ),
  );
  assert.match(source, /navigationStepLabel="skok: 1"/);
  assert.match(source, /Usuń sekwencję F/);
  assert.doesNotMatch(source, /Przywróć ostatnie A \/ Ctrl\+A/);
  assert.doesNotMatch(source, /deleteUndoRef/);
  assert.doesNotMatch(source, /restoreLastSequence/);
  assert.match(source, /setSnapshot\(optimisticSnapshot\)/);
  assert.match(source, /setBackgroundDeletePending\(true\)/);
  assert.match(
    source,
    /operationQueueRef\.current = operationQueueRef\.current/,
  );
  assert.match(source, /Otwórz ponownie ten katalog przed kolejną zmianą/);
  assert.doesNotMatch(source, /inspectRepairDirectory\(snapshot\.directory\)/);
  assert.match(source, /removeSnapshotFile\(/);
});

test('repair viewer keeps Object URLs keyed by path within an explicit repair scope', async () => {
  const source = await import('node:fs/promises').then(({ readFile }) =>
    readFile(
      new URL(
        '../src/features/manual-image-selection/manual-image-viewer.tsx',
        import.meta.url,
      ),
      'utf8',
    ),
  );
  assert.match(source, /cacheScope\?: string/);
  assert.match(source, /Map<string, string>/);
  assert.match(source, /target\.relativePath/);
  assert.match(source, /anonymousSourceChanged/);
});

test('repair workspace supports a non-reversible batch delete by start-number prefix', async () => {
  const source = await import('node:fs/promises').then(({ readFile }) =>
    readFile(
      new URL(
        '../src/features/manual-image-selection/manual-selection-repair-workspace.tsx',
        import.meta.url,
      ),
      'utf8',
    ),
  );
  assert.match(source, />\s*Usuń wybrane\s*</);
  assert.match(source, />\s*Usuń pojedynczo\s*</);
  assert.match(source, /String\(file\.start\)\.startsWith\(prefix\)/);
  assert.match(source, /bulkDeleteCandidates\[0\]/);
  assert.match(source, /Nazwa pliku/);
  assert.match(source, /bez kosza i bez[\s\S]*możliwości cofnięcia/);
  assert.match(source, /for \(const selectedFile of bulkDeleteFiles\)/);
  assert.match(source, /deleteRepairFile\(/);
  assert.match(source, /isCriticalBulkDeleteFailure/);
});

test('admin mounts repair directly below local selection and redirects repaired folders', async () => {
  const workspace = await import('node:fs/promises').then(({ readFile }) =>
    readFile(
      new URL(
        '../src/features/manual-image-selection/manual-image-selection-workspace.tsx',
        import.meta.url,
      ),
      'utf8',
    ),
  );
  assert.match(
    workspace,
    /<LocalManualImageSelectionWorkspace\s*\/>[\s\S]*<ManualSelectionRepairWorkspace\s*\/>/,
  );
  assert.match(workspace, /readRepairManifest\(outputDirectory\)/);
  assert.match(workspace, /Kontynuuj w sekcji „Popraw selekcję”/);
});

test('admin mounts durable filename range verification with five-anchor manual review', async () => {
  const { readFile } = await import('node:fs/promises');
  const workspace = await readFile(
    new URL(
      '../src/features/manual-image-selection/manual-selection-range-verification-workspace.tsx',
      import.meta.url,
    ),
    'utf8',
  );
  const parent = await readFile(
    new URL(
      '../src/features/manual-image-selection/manual-image-selection-workspace.tsx',
      import.meta.url,
    ),
    'utf8',
  );

  assert.match(parent, /ManualSelectionRangeVerificationWorkspace/);
  assert.match(parent, /pickLocalDirectory/);
  assert.match(workspace, /Weryfikacja zakresów/);
  assert.match(workspace, /pickLocalDirectory\(\{ id: 'gp-range-verify'/);
  assert.match(workspace, /filename_verification/);
  assert.match(workspace, /listSemiAutomaticFilenameRangeVerifications/);
  assert.match(
    workspace,
    /listSemiAutomaticImageSelections\(\s*'filename_verification'/,
  );
  assert.match(workspace, /decideSemiAutomaticFilenameRangeVerification/);
  assert.match(workspace, /retryJob/);
  assert.match(workspace, /Wznów analizę/);
  assert.match(workspace, /cleanup_pending/);
  assert.match(workspace, /cleanup_blocked/);
  assert.match(workspace, /Wznów czyszczenie/);
  assert.match(workspace, /dane robocze usunięte/);
  assert.match(workspace, /deleteSemiAutomaticFilenameVerificationHistory/);
  assert.match(workspace, /Usuń trwale/);
  assert.match(workspace, /isDeletableHistory/);
  assert.match(workspace, /remoteAssetHandle/);
  assert.match(workspace, /directoryPermissionIsGranted/);
  assert.match(workspace, /Odrzuć i usuń F/);
  assert.match(workspace, /jobProgressPercent/);
});

test('fill workspace exposes bounded steps, gap targets, shortcuts and visibility gate', async () => {
  const source = await import('node:fs/promises').then(({ readFile }) =>
    readFile(
      new URL(
        '../src/features/manual-image-selection/manual-selection-repair-workspace.tsx',
        import.meta.url,
      ),
      'utf8',
    ),
  );
  assert.match(source, /\[1, 2, 5, 10, 20, 50, 100\]/);
  assert.match(source, /Luka \$\{gapCursor \+ 1\} z \$\{gaps\.length\}/);
  assert.match(source, /key === 'enter' \|\| key === 'f'/);
  assert.match(source, /key === 'a'/);
  assert.match(source, /setViewReady\(true\)/);
  assert.match(source, /writeRepairFile/);
  assert.match(source, /pickLocalDirectory\(\{ id: 'gp-manual-repair'/);
  assert.match(source, /sourceCursor \+ 1/);
});

test('repair workspace shows long-running directory phases and lets manual choice win recovery', async () => {
  const source = await import('node:fs/promises').then(({ readFile }) =>
    readFile(
      new URL(
        '../src/features/manual-image-selection/manual-selection-repair-workspace.tsx',
        import.meta.url,
      ),
      'utf8',
    ),
  );

  assert.match(source, /type RepairWorkspacePhase/);
  assert.match(source, /Przywracam poprzednią sesję/);
  assert.match(source, /Sprawdzam nazwy i checksumy wybranego katalogu/);
  assert.match(source, /Wczytuję listę zdjęć z katalogu bazowego/);
  assert.match(source, /recoveryGenerationRef/);
  assert.match(source, /beginWorkPhase\('selecting_selected'\)/);
  assert.match(source, /beginWorkPhase\('selecting_source'\)/);
  assert.match(source, /selectedDirectory: directory/);
  assert.match(source, /mode: null/);
});
