import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import test from 'node:test';

import {
  pendingReplacementMatchesSource,
  replacePageGeometryCutSource,
  verifyPageGeometryCutSource,
} from '../src/features/imports/page-geometry-source-replacement.ts';

test('keeps an empty geometry review render safe before its source loads', () => {
  assert.equal(pendingReplacementMatchesSource(null, null), false);
  assert.equal(pendingReplacementMatchesSource(null, {}), false);
  assert.equal(pendingReplacementMatchesSource(null, {
    sourceChecksum: 'a'.repeat(64),
    sourceRelativePath: 'cut/seq_1-9.jpg',
    replacementUploadId: 'revision',
    replacementChecksum: 'b'.repeat(64),
  }), false);
});

test('recovers only a valid pending replacement for the loaded source', () => {
  const source = {
    sourceChecksumSha256: 'a'.repeat(64),
    sourceRelativePath: 'cut/seq_1-9.jpg',
  };
  const pending = {
    sourceChecksum: source.sourceChecksumSha256,
    sourceRelativePath: source.sourceRelativePath,
    replacementUploadId: 'revision',
    replacementChecksum: 'b'.repeat(64),
  };
  assert.equal(pendingReplacementMatchesSource(source, pending), true);
  assert.equal(pendingReplacementMatchesSource(source, null), false);
  assert.equal(pendingReplacementMatchesSource(source, { ...pending, sourceRelativePath: 'other.jpg' }), false);
});

function checksum(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

function cutFolder(original) {
  let content = Buffer.from(original);
  const file = {
    async getFile() {
      return new Blob([content]);
    },
    async createWritable() {
      return {
        async write(value) {
          content = Buffer.from(await value.arrayBuffer());
        },
        async close() {},
        async abort() {},
      };
    },
  };
  return {
    name: '200575 - 222912 cut',
    async getFileHandle(name) {
      assert.equal(name, 'seq_207064-207072.jpg');
      return file;
    },
    get content() {
      return content;
    },
  };
}

test('replaces only the verified source file in the selected cut folder', async () => {
  const old = Buffer.from('old-jpeg');
  const next = Buffer.from('new-jpeg');
  const folder = cutFolder(old);
  const relativePath = '200575 - 222912 cut/seq_207064-207072.jpg';
  await verifyPageGeometryCutSource(folder, relativePath, checksum(old));
  const actual = await replacePageGeometryCutSource(
    folder,
    relativePath,
    checksum(old),
    new File([next], 'replacement.jpg', { type: 'image/jpeg' }),
  );
  assert.equal(actual, checksum(next));
  assert.deepEqual(folder.content, next);
});

test('refuses a foreign folder or stale original without writing', async () => {
  const old = Buffer.from('old-jpeg');
  const folder = cutFolder(old);
  const replacement = new File(['new-jpeg'], 'replacement.jpg');
  await assert.rejects(
    replacePageGeometryCutSource(
      folder,
      'other-cut/seq_207064-207072.jpg',
      checksum(old),
      replacement,
    ),
    /Wybierz katalog/,
  );
  await assert.rejects(
    replacePageGeometryCutSource(
      folder,
      '200575 - 222912 cut/seq_207064-207072.jpg',
      checksum(Buffer.from('different')),
      replacement,
    ),
    /zmienił się/,
  );
  assert.deepEqual(folder.content, old);
});
