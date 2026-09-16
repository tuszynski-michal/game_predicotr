import assert from 'node:assert/strict';
import test from 'node:test';

import {
  LocalDirectoryPickerActiveError,
  isLocalDirectoryPickerActive,
  pickLocalDirectory,
  subscribeLocalDirectoryPickerActive,
} from '../src/lib/local-directory-picker.ts';

test('serializes local directory picker requests without holding a lock for later work', async () => {
  const originalWindow = globalThis.window;
  let releaseFirstPicker;
  const firstHandle = { kind: 'directory', name: 'first' };
  let receivedOptions = null;
  const activeStates = [];
  const unsubscribe = subscribeLocalDirectoryPickerActive(() => {
    activeStates.push(isLocalDirectoryPickerActive());
  });
  globalThis.window = {
    showDirectoryPicker(options) {
      receivedOptions = options;
      assert.equal(this, globalThis.window);
      return new Promise((resolve) => {
        releaseFirstPicker = () => resolve(firstHandle);
      });
    },
  };

  try {
    const first = pickLocalDirectory({
      id: 'gp-test-source',
      mode: 'read',
    });

    assert.equal(isLocalDirectoryPickerActive(), true);
    await assert.rejects(
      pickLocalDirectory({ id: 'gp-test-output', mode: 'readwrite' }),
      LocalDirectoryPickerActiveError,
    );
    assert.deepEqual(receivedOptions, {
      id: 'gp-test-source',
      mode: 'read',
    });
    releaseFirstPicker();
    assert.equal(await first, firstHandle);
    assert.equal(isLocalDirectoryPickerActive(), false);
    assert.deepEqual(activeStates, [true, false]);
  } finally {
    unsubscribe();
    globalThis.window = originalWindow;
  }
});

test('normalizes an untracked native picker conflict and releases the local lock', async () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    showDirectoryPicker() {
      throw new DOMException(
        'File picker already active.',
        'InvalidStateError',
      );
    },
  };

  try {
    await assert.rejects(
      pickLocalDirectory({ id: 'gp-test-conflict', mode: 'readwrite' }),
      LocalDirectoryPickerActiveError,
    );
    assert.equal(isLocalDirectoryPickerActive(), false);
  } finally {
    globalThis.window = originalWindow;
  }
});
