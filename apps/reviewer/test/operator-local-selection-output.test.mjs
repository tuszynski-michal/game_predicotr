import assert from 'node:assert/strict';
import test from 'node:test';

import {
  removeOperatorLocalSelection,
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

test('materializes a local progress manifest without a host transfer', async () => {
  const directory = new MemoryDirectoryHandle();
  await writeOperatorLocalManifest(directory, {
    batchId: 'batch-1',
    currentIndex: 4,
    decisions: [],
    nextRangeStart: 10,
    sessionId: 'session-1',
    sourceDirectoryName: '1 - 19',
  });

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
        sessionId: 'session-foreign',
        storageMode: 'operator_local',
      }),
    ),
  );
  directory.files.set(foreign.name, foreign);

  await assert.rejects(
    writeOperatorLocalManifest(directory, {
      batchId: 'batch-1',
      currentIndex: 4,
      decisions: [],
      nextRangeStart: 10,
      sessionId: 'session-1',
      sourceDirectoryName: '1 - 19',
    }),
    /innej sesji/,
  );
  assert.equal(
    JSON.parse(await (await foreign.getFile()).text()).sessionId,
    'session-foreign',
  );
});
