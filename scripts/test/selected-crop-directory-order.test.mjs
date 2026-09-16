import assert from 'node:assert/strict';
import test from 'node:test';
import { selectedCropSourceDirectories } from '../lib/selected-crop-directory-order.mjs';

function entry(name, { directory = true, symlink = false } = {}) {
  return {
    name,
    isDirectory: () => directory,
    isSymbolicLink: () => symlink,
  };
}

test('discovers numerically named source directories and excludes cut outputs', () => {
  const result = selectedCropSourceDirectories([
    entry('93853 -117828 cut'),
    entry('117829 - 128268'),
    entry('1-19809'),
    entry('93853 -117828'),
    entry('notes'),
    entry('128269 - 149634', { symlink: true }),
    entry('seq_1-9.jpg', { directory: false }),
  ]);

  assert.deepEqual(
    result.map(({ name }) => name),
    ['1-19809', '93853 -117828', '117829 - 128268'],
  );
});
