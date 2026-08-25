import assert from 'node:assert/strict';
import test from 'node:test';

import {
  DirectoryHandleRemoteSourceAdapter,
  REMOTE_SOURCE_DIRECTORY_PICKER_ID,
  RemoteSourceAdapterError,
  WebkitDirectoryRemoteSourceAdapter,
  createRemoteSourceItemRecords,
  detectRemoteSourceMode,
  pagedRemoteSourceDescriptors,
  validateRemoteSourceRelink,
} from '../src/features/manual-selection/remote-source-adapter.ts';

test('uses a stable File System Access picker id accepted by Chromium', () => {
  assert.equal(REMOTE_SOURCE_DIRECTORY_PICKER_ID, 'gp-remote-source-v1');
  assert.ok(REMOTE_SOURCE_DIRECTORY_PICKER_ID.length <= 32);
  assert.match(REMOTE_SOURCE_DIRECTORY_PICKER_ID, /^[A-Za-z0-9_-]+$/);
});

function jpeg(name, size = 100, lastModified = 1_700_000_000_000) {
  const file = new File([new Uint8Array(size)], name, {
    lastModified,
    type: 'image/jpeg',
  });
  Object.defineProperty(file, 'webkitRelativePath', {
    configurable: true,
    value: `batch/${name}`,
  });
  return file;
}

function fileHandle(file, byteReadCounter) {
  return {
    kind: 'file',
    name: file.name,
    async getFile() {
      const original = file.arrayBuffer.bind(file);
      Object.defineProperty(file, 'arrayBuffer', {
        configurable: true,
        value: async () => {
          byteReadCounter.count += 1;
          return original();
        },
      });
      return file;
    },
  };
}

function directoryHandle(name, entries, permission = 'granted') {
  const calls = [];
  return {
    calls,
    kind: 'directory',
    name,
    async *entries() {
      yield* entries;
    },
    async queryPermission(options) {
      calls.push(['query', options]);
      return permission;
    },
    async requestPermission(options) {
      calls.push(['request', options]);
      return 'granted';
    },
    async getDirectoryHandle(segment) {
      const match = entries.find(
        ([entryName, handle]) =>
          entryName === segment && handle.kind === 'directory',
      );
      if (!match) throw new DOMException('Missing', 'NotFoundError');
      return match[1];
    },
    async getFileHandle(segment) {
      const match = entries.find(
        ([entryName, handle]) =>
          entryName === segment && handle.kind === 'file',
      );
      if (!match) throw new DOMException('Missing', 'NotFoundError');
      return match[1];
    },
  };
}

test('indexes only JPEG metadata in natural order and asks only for read access', async () => {
  const byteReads = { count: 0 };
  const nested = directoryHandle('nested', [
    ['10.jpg', fileHandle(jpeg('10.jpg', 10), byteReads)],
    ['2.JPG', fileHandle(jpeg('2.JPG', 2), byteReads)],
    ['ignored.png', fileHandle(new File(['x'], 'ignored.png'), byteReads)],
  ]);
  const root = directoryHandle('batch', [
    ['nested', nested],
    ['1.jpeg', fileHandle(jpeg('1.jpeg', 1), byteReads)],
  ]);
  const adapter = new DirectoryHandleRemoteSourceAdapter(root);

  assert.equal(await adapter.requestPermission(), 'granted');
  const indexed = await adapter.index();

  assert.deepEqual(root.calls, [
    ['query', { mode: 'read' }],
    ['query', { mode: 'read' }],
  ]);
  assert.deepEqual(
    indexed.manifest.entries.map((entry) => entry.relativePath),
    ['1.jpeg', 'nested/2.JPG', 'nested/10.jpg'],
  );
  assert.equal(indexed.manifest.fileCount, 3);
  assert.equal(byteReads.count, 0);
  assert.equal('absolutePath' in indexed.manifest.entries[0], false);
  assert.equal('bytes' in indexed.manifest.entries[0], false);
});

test('pages a 1000-item source index without eager image reads', async () => {
  const files = Array.from({ length: 1000 }, (_, index) =>
    jpeg(`${index + 1}.jpg`, 1),
  );
  const indexed = await new WebkitDirectoryRemoteSourceAdapter(files).index();
  const pages = [];
  for await (const page of pagedRemoteSourceDescriptors(
    indexed.descriptors,
    250,
  )) {
    pages.push(page);
  }

  assert.deepEqual(
    pages.map((page) => page.length),
    [250, 250, 250, 250],
  );
  assert.equal(indexed.manifest.fileCount, 1000);
});

test('fallback is session-only and relink validation fails closed', async () => {
  const files = [jpeg('1.jpg'), jpeg('2.jpg')];
  const expected = await new WebkitDirectoryRemoteSourceAdapter(files).index();
  const same = await new WebkitDirectoryRemoteSourceAdapter(
    files.toReversed(),
  ).index();
  const changed = await new WebkitDirectoryRemoteSourceAdapter([
    jpeg('1.jpg', 101),
    jpeg('2.jpg'),
  ]).index();

  assert.equal(expected.sourceHandle, null);
  assert.doesNotThrow(() =>
    validateRemoteSourceRelink(expected.manifest, same.manifest),
  );
  assert.throws(
    () => validateRemoteSourceRelink(expected.manifest, changed.manifest),
    (error) =>
      error instanceof RemoteSourceAdapterError &&
      error.code === 'REMOTE_SELECTION_SOURCE_CHANGED',
  );
});

test('detects capability fallback and creates metadata-only source records', async () => {
  assert.equal(
    detectRemoteSourceMode({
      HTMLInputElement: { prototype: { webkitdirectory: false } },
      isSecureContext: true,
      showDirectoryPicker() {},
    }),
    'directory_handle',
  );
  assert.equal(
    detectRemoteSourceMode({
      HTMLInputElement: { prototype: { webkitdirectory: false } },
      isSecureContext: false,
    }),
    'webkitdirectory_reselect',
  );
  assert.equal(
    detectRemoteSourceMode({ isSecureContext: false }),
    'unsupported',
  );

  const indexed = await new WebkitDirectoryRemoteSourceAdapter([
    jpeg('1.jpg'),
  ]).index();
  const records = createRemoteSourceItemRecords(
    'session',
    'batch',
    indexed.manifest,
    () => 'file-id',
  );
  assert.equal(records[0].fileId, 'file-id');
  assert.equal(
    Object.values(records[0]).some((value) => value instanceof Blob),
    false,
  );
});

test('fails with stable errors when an indexed file disappears or changes', async () => {
  const byteReads = { count: 0 };
  const original = jpeg('1.jpg', 10, 100);
  const root = directoryHandle('batch', [
    ['1.jpg', fileHandle(original, byteReads)],
  ]);
  const adapter = new DirectoryHandleRemoteSourceAdapter(root);
  const indexed = await adapter.index();
  root.getFileHandle = async () => {
    throw new DOMException('Missing', 'NotFoundError');
  };
  await assert.rejects(
    adapter.fileForEntry(indexed.manifest.entries[0]),
    (error) =>
      error instanceof RemoteSourceAdapterError &&
      error.code === 'REMOTE_SELECTION_SOURCE_FILE_MISSING',
  );

  const changedRoot = directoryHandle('batch', [
    ['1.jpg', fileHandle(jpeg('1.jpg', 11, 100), byteReads)],
  ]);
  await assert.rejects(
    new DirectoryHandleRemoteSourceAdapter(changedRoot).fileForEntry(
      indexed.manifest.entries[0],
    ),
    (error) =>
      error instanceof RemoteSourceAdapterError &&
      error.code === 'REMOTE_SELECTION_SOURCE_CHANGED',
  );
});
