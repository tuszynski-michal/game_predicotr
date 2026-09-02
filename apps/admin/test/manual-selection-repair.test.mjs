import assert from 'node:assert/strict';
import test from 'node:test';

import {
  deleteRepairFile,
  inspectRepairDirectory,
  readRepairManifest,
  writeRepairManifest,
  writeRepairFile,
} from '../src/features/manual-image-selection/manual-selection-repair-storage.ts';

class MemoryFileHandle {
  kind = 'file';

  constructor(name, file) {
    this.name = name;
    this.file = file;
  }

  async getFile() {
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

test('fills exact bytes and safely undoes only the checksummed repair file', async () => {
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
  const removed = await deleteRepairFile({
    directory,
    fileName: 'seq_10-18.jpg',
    kind: 'undo_fill',
    manifest: filled.manifest,
    outputManifest: null,
    sourceIndex: 4,
    sourcePath: 'base/source.jpg',
  });
  assert.equal(removed.file.size, 'chosen-original-bytes'.length);
  await assert.rejects(directory.getFileHandle('seq_10-18.jpg'), /missing/);
  assert.deepEqual(removed.manifest.deletedRanges, [{ end: 18, start: 10 }]);
  const restored = await writeRepairFile({
    directory,
    kind: 'restore',
    manifest: removed.manifest,
    outputManifest: null,
    source: new MemoryFileHandle('seq_10-18.jpg', removed.file),
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
  assert.deepEqual(restored.manifest.deletedRanges, []);
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

test('delete workspace uses fixed step one and keeps only one in-memory restore buffer', async () => {
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
  assert.match(source, /Przywróć ostatnie A \/ Ctrl\+A/);
  assert.match(source, /deleteUndoRef\.current = \{/);
  assert.match(source, /deleteUndoRef\.current = null/);
  assert.doesNotMatch(source, /localStorage.*deleteUndo/s);
  assert.doesNotMatch(source, /inspectRepairDirectory\(snapshot\.directory\)/);
  assert.match(source, /removeSnapshotFile\(/);
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
