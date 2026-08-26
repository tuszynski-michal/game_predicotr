import assert from 'node:assert/strict';
import test from 'node:test';

import {
  inspectOperatorLocalOutputDirectory,
  removeOperatorLocalSelection,
  resetOperatorLocalOutputDirectory,
  resumeOperatorLocalBatch,
  verifyOperatorLocalOutputDirectory,
  writeOperatorLocalManifest,
  writeOperatorLocalSelection,
} from '../src/features/manual-selection/operator-local-selection-output.ts';

class MemoryFileHandle {
  constructor(name, value = null) {
    this.name = name;
    this.value = value;
    this.kind = 'file';
  }

  async getFile() {
    if (this.value === null) throw new DOMException('missing', 'NotFoundError');
    return new File([this.value], this.name, { type: 'image/jpeg' });
  }

  async createWritable() {
    let pending = this.value;
    return {
      write: async (value) => {
        pending = new Uint8Array(await new Blob([value]).arrayBuffer());
      },
      close: async () => {
        this.value = pending;
      },
      abort: async () => undefined,
    };
  }
}

class MemoryDirectoryHandle {
  constructor(name = 'source wybrane') {
    this.name = name;
    this.kind = 'directory';
    this.files = new Map();
  }

  async getFileHandle(name, options = {}) {
    let handle = this.files.get(name);
    if (handle === undefined && options.create === true) {
      handle = new MemoryFileHandle(name);
      this.files.set(name, handle);
    }
    if (handle === undefined)
      throw new DOMException('missing', 'NotFoundError');
    return handle;
  }

  async removeEntry(name) {
    if (!this.files.delete(name))
      throw new DOMException('missing', 'NotFoundError');
  }

  async *entries() {
    yield* this.files.entries();
  }
}

class MemoryParentDirectoryHandle {
  constructor() {
    this.name = 'parent';
    this.kind = 'directory';
    this.directories = new Map();
  }

  async getDirectoryHandle(name, options = {}) {
    let handle = this.directories.get(name);
    if (handle === undefined && options.create === true) {
      handle = new MemoryDirectoryHandle(name);
      this.directories.set(name, handle);
    }
    if (handle === undefined)
      throw new DOMException('missing', 'NotFoundError');
    return handle;
  }

  async removeEntry(name) {
    if (!this.directories.delete(name))
      throw new DOMException('missing', 'NotFoundError');
  }
}

const SOURCE_CHECKSUM = 'a'.repeat(64);

function manifestInput(overrides = {}) {
  return {
    batchId: 'batch-1',
    currentIndex: 4,
    decisions: [],
    direction: 'ascending',
    fileCount: 10,
    firstLayout: 1,
    nextRangeStart: 1,
    sessionId: 'session-1',
    sourceDirectoryName: '1 - 19',
    sourceManifestChecksumSha256: SOURCE_CHECKSUM,
    ...overrides,
  };
}

test('writes original JPEG bytes idempotently into the operator output folder', async () => {
  const directory = new MemoryDirectoryHandle();
  const source = new File(['jpeg-original'], 'photo.jpg', {
    type: 'image/jpeg',
  });

  const first = await writeOperatorLocalSelection(directory, source, 1);
  const second = await writeOperatorLocalSelection(directory, source, 1);

  assert.equal(first.name, 'seq_1-9.jpg');
  assert.equal(first.created, true);
  assert.equal(second.created, false);
  assert.equal(
    await (
      await directory.getFileHandle(first.name)
    )
      .getFile()
      .then((file) => file.text()),
    'jpeg-original',
  );
});

test('writes an explicitly edited nine-layout range and rejects invalid ranges', async () => {
  const directory = new MemoryDirectoryHandle();
  const source = new File(['jpeg-original'], 'photo.jpg', {
    type: 'image/jpeg',
  });

  const output = await writeOperatorLocalSelection(
    directory,
    source,
    222913,
    222921,
  );

  assert.equal(output.name, 'seq_222913-222921.jpg');
  await assert.rejects(
    writeOperatorLocalSelection(directory, source, 222913, 222920),
    /musi obejmować 9 plansz/,
  );
});

test('never overwrites or removes a foreign operator file', async () => {
  const directory = new MemoryDirectoryHandle();
  const foreign = new MemoryFileHandle(
    'seq_1-9.jpg',
    new TextEncoder().encode('foreign'),
  );
  directory.files.set(foreign.name, foreign);

  await assert.rejects(
    writeOperatorLocalSelection(
      directory,
      new File(['selected'], 'photo.jpg', { type: 'image/jpeg' }),
      1,
    ),
    /inną zawartość/,
  );
  await assert.rejects(
    removeOperatorLocalSelection(directory, {
      action: 'accepted',
      fileId: 'file-1',
      imageChecksumSha256: '0'.repeat(64),
      imagePath: 'photo.jpg',
      operationId: 'decision-1',
      outputName: 'seq_1-9.jpg',
      rangeEnd: 9,
      rangeStart: 1,
      selectionGeneration: 1,
      sourceIndex: 0,
    }),
    /Nie usuwam obcego pliku/,
  );
  assert.equal(await (await foreign.getFile()).text(), 'foreign');
});

test('restart recreates only a verified output directory and removes its progress', async () => {
  const parent = new MemoryParentDirectoryHandle();
  const directory = await parent.getDirectoryHandle('1 - 19 wybrane', {
    create: true,
  });
  const source = new File(['selected'], 'photo.jpg', { type: 'image/jpeg' });
  const output = await writeOperatorLocalSelection(directory, source, 1);
  await writeOperatorLocalManifest(
    directory,
    manifestInput({
      currentIndex: 1,
      decisions: [
        {
          action: 'accepted',
          fileId: 'file-1',
          imageChecksumSha256: output.checksumSha256,
          imagePath: 'photo.jpg',
          operationId: 'decision-1',
          outputName: output.name,
          rangeEnd: 9,
          rangeStart: 1,
          selectionGeneration: 1,
          sourceIndex: 0,
        },
      ],
      nextRangeStart: 10,
    }),
  );

  const restarted = await resetOperatorLocalOutputDirectory(
    parent,
    '1 - 19 wybrane',
    {
      fileCount: 10,
      sourceDirectoryName: '1 - 19',
      sourceManifestChecksumSha256: SOURCE_CHECKSUM,
    },
  );

  assert.notEqual(restarted, directory);
  assert.deepEqual(await inspectOperatorLocalOutputDirectory(restarted), {
    kind: 'empty',
  });
});

test('restart creates a deleted output directory but refuses foreign contents', async () => {
  const parent = new MemoryParentDirectoryHandle();
  const created = await resetOperatorLocalOutputDirectory(
    parent,
    '1 - 19 wybrane',
    {
      fileCount: 10,
      sourceDirectoryName: '1 - 19',
      sourceManifestChecksumSha256: SOURCE_CHECKSUM,
    },
  );
  assert.equal(created.name, '1 - 19 wybrane');

  created.files.set(
    'notes.txt',
    new MemoryFileHandle('notes.txt', new TextEncoder().encode('foreign')),
  );
  await assert.rejects(
    resetOperatorLocalOutputDirectory(parent, '1 - 19 wybrane', {
      fileCount: 10,
      sourceDirectoryName: '1 - 19',
      sourceManifestChecksumSha256: SOURCE_CHECKSUM,
    }),
    /obce dane|nie zawiera danych/,
  );
  assert.equal(parent.directories.get('1 - 19 wybrane'), created);
});

test('materializes a local progress manifest without a host transfer', async () => {
  const directory = new MemoryDirectoryHandle();
  await writeOperatorLocalManifest(
    directory,
    manifestInput({ nextRangeStart: 10, firstLayout: 10 }),
  );

  const manifest = JSON.parse(
    await (
      await directory.getFileHandle('manual-image-selection-output-v1.json')
    )
      .getFile()
      .then((file) => file.text()),
  );
  assert.equal(manifest.storageMode, 'operator_local');
  assert.equal(manifest.nextRangeStart, 10);
  assert.equal(manifest.sourceDirectoryName, '1 - 19');
});

test('never overwrites a manifest owned by another operator session', async () => {
  const directory = new MemoryDirectoryHandle();
  const foreign = new MemoryFileHandle(
    'manual-image-selection-output-v1.json',
    new TextEncoder().encode(
      JSON.stringify({
        batchId: 'batch-foreign',
        currentIndex: 4,
        decisions: [],
        nextRangeStart: 1,
        schemaVersion: 1,
        sessionId: 'session-foreign',
        sourceDirectoryName: '1 - 19',
        storageMode: 'operator_local',
        updatedAt: '2026-08-24T00:00:00.000Z',
      }),
    ),
  );
  directory.files.set(foreign.name, foreign);

  await assert.rejects(
    writeOperatorLocalManifest(directory, manifestInput()),
    /innej sesji/,
  );
  assert.equal(
    JSON.parse(await (await foreign.getFile()).text()).sessionId,
    'session-foreign',
  );
});

test('accepts only an empty folder or a complete resumable output', async () => {
  const empty = new MemoryDirectoryHandle();
  assert.deepEqual(await inspectOperatorLocalOutputDirectory(empty), {
    kind: 'empty',
  });

  const foreign = new MemoryDirectoryHandle();
  foreign.files.set(
    'notes.txt',
    new MemoryFileHandle('notes.txt', new TextEncoder().encode('foreign')),
  );
  await assert.rejects(
    inspectOperatorLocalOutputDirectory(foreign),
    /nie jest pusty/,
  );

  const resumable = new MemoryDirectoryHandle();
  const source = new File(['selected'], 'photo.jpg', { type: 'image/jpeg' });
  const output = await writeOperatorLocalSelection(resumable, source, 1);
  const decision = {
    action: 'accepted',
    fileId: 'old-file-id',
    imageChecksumSha256: output.checksumSha256,
    imagePath: 'photo.jpg',
    operationId: 'decision-1',
    outputName: output.name,
    rangeEnd: 9,
    rangeStart: 1,
    selectionGeneration: 1,
    sourceIndex: 0,
  };
  await writeOperatorLocalManifest(
    resumable,
    manifestInput({
      currentIndex: 1,
      decisions: [decision],
      nextRangeStart: 10,
    }),
  );
  const state = await inspectOperatorLocalOutputDirectory(resumable);
  assert.equal(state.kind, 'resumable');
  assert.equal(state.manifest.nextRangeStart, 10);
});

test('rejects a resumable output whose managed JPEG no longer matches its manifest checksum', async () => {
  const directory = new MemoryDirectoryHandle();
  const output = await writeOperatorLocalSelection(
    directory,
    new File(['selected'], 'photo.jpg', { type: 'image/jpeg' }),
    1,
  );
  await writeOperatorLocalManifest(
    directory,
    manifestInput({
      currentIndex: 1,
      decisions: [
        {
          action: 'accepted',
          fileId: 'old-file-id',
          imageChecksumSha256: output.checksumSha256,
          imagePath: 'photo.jpg',
          operationId: 'decision-1',
          outputName: output.name,
          rangeEnd: 9,
          rangeStart: 1,
          selectionGeneration: 1,
          sourceIndex: 0,
        },
      ],
      nextRangeStart: 10,
    }),
  );
  directory.files.get(output.name).value = new TextEncoder().encode('changed');

  await assert.rejects(
    verifyOperatorLocalOutputDirectory(directory),
    /Nie usuwam obcego pliku/,
  );
});

test('resumes on the saved source photo and next range across access sessions', async () => {
  const directory = new MemoryDirectoryHandle();
  const source = new File(['selected'], 'photo.jpg', { type: 'image/jpeg' });
  const output = await writeOperatorLocalSelection(directory, source, 1);
  await writeOperatorLocalManifest(
    directory,
    manifestInput({
      currentIndex: 3,
      decisions: [
        {
          action: 'accepted',
          fileId: 'old-file-id',
          imageChecksumSha256: output.checksumSha256,
          imagePath: 'photo.jpg',
          operationId: 'decision-1',
          outputName: output.name,
          rangeEnd: 9,
          rangeStart: 1,
          selectionGeneration: 1,
          sourceIndex: 0,
        },
      ],
      nextRangeStart: 10,
    }),
  );
  const state = await inspectOperatorLocalOutputDirectory(directory);
  assert.equal(state.kind, 'resumable');
  const resumed = await resumeOperatorLocalBatch(
    state.manifest,
    {
      batchId: 'new-batch',
      cursorIndex: 0,
      decisions: [],
      direction: 'ascending',
      fileCount: 10,
      firstLayout: 1,
      navigationStep: 1,
      nextRangeStart: 1,
      schemaVersion: 1,
      sessionId: 'new-session',
      sourceDirectoryName: '1 - 19',
      sourceKind: 'directory_handle',
      sourceManifestChecksumSha256: SOURCE_CHECKSUM,
      totalBytes: 100,
      updatedAt: '2026-08-24T00:00:00.000Z',
    },
    async (ordinal) =>
      ordinal === 0
        ? {
            batchId: 'new-batch',
            fileId: 'new-file-id',
            lastModifiedMs: 1,
            mimeType: 'image/jpeg',
            name: 'photo.jpg',
            ordinal: 0,
            relativePath: 'photo.jpg',
            schemaVersion: 1,
            sessionId: 'new-session',
            sizeBytes: 8,
          }
        : null,
  );
  assert.equal(resumed.cursorIndex, 3);
  assert.equal(resumed.nextRangeStart, 10);
  assert.equal(resumed.decisions[0].fileId, 'new-file-id');
  assert.equal(resumed.hostRegistered, true);
});

test('blocks a resumable folder from a different indexed source', async () => {
  const directory = new MemoryDirectoryHandle();
  await writeOperatorLocalManifest(directory, manifestInput());
  const state = await inspectOperatorLocalOutputDirectory(directory);
  assert.equal(state.kind, 'resumable');
  await assert.rejects(
    resumeOperatorLocalBatch(
      state.manifest,
      {
        batchId: 'new-batch',
        cursorIndex: 0,
        direction: 'ascending',
        fileCount: 10,
        firstLayout: 1,
        schemaVersion: 1,
        sessionId: 'new-session',
        sourceDirectoryName: '1 - 19',
        sourceKind: 'directory_handle',
        sourceManifestChecksumSha256: 'b'.repeat(64),
        totalBytes: 100,
        updatedAt: '2026-08-24T00:00:00.000Z',
      },
      async () => null,
    ),
    /zmienił się/,
  );
});
