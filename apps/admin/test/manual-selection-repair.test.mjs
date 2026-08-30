import assert from 'node:assert/strict';
import test from 'node:test';

import {
  inspectRepairDirectory,
  readRepairManifest,
  writeRepairManifest,
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
