import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';

const dom = new JSDOM('<!doctype html><div id="root"></div>', {
  pretendToBeVisual: true,
});
for (const key of ['window', 'document', 'HTMLElement', 'Image']) {
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.ResizeObserver = class {
  observe() {}
  disconnect() {}
};
dom.window.HTMLImageElement.prototype.decode = async () => undefined;
const originalCreate = URL.createObjectURL,
  originalRevoke = URL.revokeObjectURL;
const revoked = new Set();
let serial = 0;
URL.createObjectURL = () => `blob:viewer-${serial++}`;
URL.revokeObjectURL = (url) => revoked.add(url);
const { createRoot } = await import('react-dom/client');
const { useManualImageViewer } =
  await import('../src/features/manual-image-selection/manual-image-viewer.tsx');
after(() => {
  URL.createObjectURL = originalCreate;
  URL.revokeObjectURL = originalRevoke;
  dom.window.close();
});

function Viewer({ files, index, scope, warm, onError }) {
  const viewer = useManualImageViewer(
    files,
    index,
    onError,
    undefined,
    undefined,
    scope,
    warm,
  );
  return React.createElement('img', {
    src: viewer.visibleImageUrl ?? undefined,
  });
}
async function fixture(initial) {
  const reads = new Map(),
    errors = [];
  const files = Array.from({ length: 24 }, (_, index) => ({
    relativePath: `${index}.jpg`,
    handle: {
      getFile: async () => {
        reads.set(index, (reads.get(index) ?? 0) + 1);
        return new Blob([String(index)]);
      },
    },
  }));
  const root = createRoot(document.getElementById('root'));
  const onError = (error) => errors.push(error);
  let state = { files, index: 0, scope: 'run-a', onError, ...initial };
  const update = async (values = {}) => {
    state = { ...state, ...values };
    await act(async () => root.render(React.createElement(Viewer, state)));
  };
  await update();
  return {
    reads,
    errors,
    update,
    close: async () => act(async () => root.unmount()),
  };
}

test('default viewer retains the ordinary bounded neighbour window and revokes on exit', async () => {
  const f = await fixture({ index: 12 });
  assert.deepEqual(
    [...f.reads.keys()].sort((a, b) => a - b),
    [9, 10, 11, 12, 13, 14, 15],
  );
  const current = document.querySelector('img').getAttribute('src');
  await f.update({ index: 13 });
  assert.equal(f.reads.get(13), 1);
  assert.ok(!revoked.has(document.querySelector('img').getAttribute('src')));
  assert.deepEqual(f.errors, []);
  await f.close();
  assert.ok(revoked.has(current));
});

test('only two distant valid proposals are warmed; jumping uses the decoded URL without rereading', async () => {
  const f = await fixture({ warm: [-1, 20, 23, 18, NaN] });
  assert.deepEqual(
    [...f.reads.keys()].sort((a, b) => a - b),
    [0, 1, 2, 3, 20, 23],
  );
  await f.update({ index: 20, warm: [23] });
  assert.equal(f.reads.get(20), 1);
  assert.ok(
    document.querySelector('img').getAttribute('src').startsWith('blob:'),
  );
  await f.update({ scope: 'run-b' });
  assert.equal(f.reads.get(20), 2);
  assert.deepEqual(f.errors, []);
  await f.close();
});

test('a departed in-flight proposal cannot fill the new window or show an old source', async () => {
  let finish;
  const file = {
    relativePath: 'late.jpg',
    handle: {
      getFile: () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    },
  };
  const f = await fixture();
  const files = [
    {
      relativePath: 'now.jpg',
      handle: { getFile: async () => new Blob(['now']) },
    },
    file,
  ];
  await f.update({ files, index: 1, scope: 'old-run' });
  await f.update({
    files: [
      {
        relativePath: 'fresh.jpg',
        handle: { getFile: async () => new Blob(['fresh']) },
      },
    ],
    index: 0,
    scope: 'new-run',
    warm: [],
  });
  const freshUrl = document.querySelector('img').getAttribute('src');
  await act(async () => finish(new Blob(['late'])));
  assert.equal(document.querySelector('img').getAttribute('src'), freshUrl);
  assert.ok(!revoked.has(freshUrl));
  assert.deepEqual(f.errors, []);
  await f.close();
});
