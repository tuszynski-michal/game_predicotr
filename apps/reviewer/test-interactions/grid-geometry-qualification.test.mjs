import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
const dom = new JSDOM('<!doctype html><div id="root"></div>', {
  url: 'http://localhost',
});
for (const key of [
  'window',
  'document',
  'HTMLElement',
  'Element',
  'localStorage',
  'Event',
  'MouseEvent',
])
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
dom.window.Image = class {
  naturalWidth = 320;
  naturalHeight = 320;
  set src(_) {
    queueMicrotask(() => this.onload?.());
  }
};
dom.window.Element.prototype.getBoundingClientRect = () => ({
  left: 0,
  top: 0,
  width: 320,
  height: 320,
});
dom.window.Element.prototype.setPointerCapture = () => {};
dom.window.Element.prototype.hasPointerCapture = () => false;
dom.window.HTMLCanvasElement.prototype.getContext = function () {
  return new Proxy(
    { canvas: this },
    { get: (object, key) => (key in object ? object[key] : () => {}) },
  );
};
const { createRoot } = await import('react-dom/client');
const { GridReviewEditor } =
  await import('../src/features/grid-reviews/grid-review-editor.tsx');
after(() => dom.window.close());
const items = Array.from({ length: 9 }, (_, i) => {
  const x = (i % 3) * 100 + 5,
    y = Math.floor(i / 3) * 100 + 5;
  return {
    slotId: `s${i}`,
    reviewItemId: `r${i}`,
    gameId: 'g',
    importJobId: 'j',
    sourceImageId: 'source',
    sourceChecksumSha256: 'a'.repeat(64),
    sourceWidth: 320,
    sourceHeight: 320,
    positionIndex: i,
    sequenceNumber: i + 1,
    gridRows: 3,
    gridColumns: 5,
    geometryRevision: 1,
    resolutionRevision: 1,
    assetMode: 'virtual_source',
    state: 'needs_validation',
    warnings: [],
    reasonCodes: [],
    geometry: {
      sourceQuad: [
        { x, y },
        { x: x + 90, y },
        { x: x + 90, y: y + 90 },
        { x, y: y + 90 },
      ],
    },
  };
});
async function dispatch(node, type, options = {}) {
  assert.ok(node);
  await act(async () =>
    node.dispatchEvent(
      new dom.window.MouseEvent(type, { bubbles: true, ...options }),
    ),
  );
}
test('qualification remains dirty when dragged corner returns to baseline; one explicit source save includes nine slots', async () => {
  localStorage.clear();
  const writes = [];
  const ref = React.createRef();
  const root = createRoot(document.getElementById('root'));
  const props = {
    api: {
      imageGridReviewSourceAssetUrl: () => '/source',
      createImageGridReviewSourceGeometryRevision: async (...args) => {
        writes.push(args[2]);
        return { data: {} };
      },
    },
    items,
    onEditingChange: () => {},
    onSaved: () => {},
    onSelect: () => {},
    selectedReviewItemId: 's0',
    ref,
  };
  await act(async () =>
    root.render(React.createElement(GridReviewEditor, props)),
  );
  await dispatch(document.querySelectorAll('input[type=checkbox]')[1], 'click');
  const canvas = document.querySelector('canvas');
  await dispatch(canvas, 'pointerdown', { clientX: 5, clientY: 5 });
  await dispatch(canvas, 'pointermove', { clientX: 15, clientY: 5 });
  await dispatch(canvas, 'pointerup', { clientX: 5, clientY: 5 });
  assert.equal(writes.length, 0);
  const draftKey = 'grid-source-draft-v1:g:j:source';
  const otherTabText = localStorage.getItem(draftKey) + ' ';
  localStorage.setItem(draftKey, otherTabText);
  let result;
  await act(async () => {
    result = await ref.current.submitEdits();
  });
  assert.equal(result, 'saved');
  assert.equal(localStorage.getItem(draftKey), otherTabText);
  assert.equal(writes.length, 1);
  assert.equal(writes[0].targets.length, 9);
  assert.deepEqual(writes[0].targets[0].corners, items[0].geometry.sourceQuad);
  assert.equal(
    writes[0].targets[0].geometryQualification.excludeFromGeometryTraining,
    true,
  );
  await act(async () => root.unmount());
});
test('external revision change blocks stale drafts before persistence or API write', async () => {
  localStorage.clear();
  const writes = [],
    ref = React.createRef(),
    root = createRoot(document.getElementById('root'));
  const props = {
    ref,
    items,
    api: {
      imageGridReviewSourceAssetUrl: () => '/source',
      createImageGridReviewSourceGeometryRevision: async (...args) => {
        writes.push(args[2]);
        return { data: {} };
      },
    },
    onEditingChange: () => {},
    onSaved: () => {},
    onSelect: () => {},
    selectedReviewItemId: 's0',
  };
  await act(async () =>
    root.render(React.createElement(GridReviewEditor, props)),
  );
  await dispatch(document.querySelectorAll('input[type=checkbox]')[1], 'click');
  const stored = localStorage.getItem('grid-source-draft-v1:g:j:source');
  assert.ok(stored);
  await act(async () =>
    root.render(
      React.createElement(GridReviewEditor, {
        ...props,
        items: items.map((item) => ({ ...item, geometryRevision: 2 })),
      }),
    ),
  );
  let result;
  await act(async () => {
    result = await ref.current.submitEdits();
  });
  assert.equal(result, 'invalid');
  assert.equal(writes.length, 0);
  assert.equal(localStorage.getItem('grid-source-draft-v1:g:j:source'), stored);
  assert.match(document.body.textContent, /innym oknie|konfliktowy szkic/);
  await act(async () => root.unmount());
});

test('legacy reset remains an individual workflow and does not invoke a source batch', async () => {
  localStorage.clear();
  const ref = React.createRef(),
    root = createRoot(document.getElementById('root'));
  const writes = [];
  await act(async () =>
    root.render(
      React.createElement(GridReviewEditor, {
        ref,
        items: [{ ...items[0], assetMode: 'legacy_file' }],
        api: {
          imageGridReviewSourceAssetUrl: () => '/source',
          createImageGridReviewSourceGeometryRevision: async () =>
            writes.push(1),
        },
        onEditingChange: () => {},
        onSaved: () => {},
        onSelect: () => {},
        selectedReviewItemId: 's0',
      }),
    ),
  );
  await dispatch(document.querySelector('canvas'), 'pointerdown', {
    clientX: 5,
    clientY: 5,
  });
  const reset = [...document.querySelectorAll('button')].find((node) =>
    node.textContent.includes('Resetuj do automatu'),
  );
  await dispatch(reset, 'click');
  let result;
  await act(async () => {
    result = await ref.current.submitEdits();
  });
  assert.equal(result, 'unchanged');
  assert.equal(writes.length, 0);
  assert.equal(document.querySelectorAll('input[type=checkbox]').length, 0);
  await act(async () => root.unmount());
});
