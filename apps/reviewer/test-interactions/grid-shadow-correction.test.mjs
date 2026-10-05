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
  'Event',
  'MouseEvent',
])
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const images = [];
dom.window.Image = class {
  naturalWidth = 1200;
  naturalHeight = 900;
  set src(value) {
    this.url = value;
    images.push(this);
  }
};
dom.window.HTMLCanvasElement.prototype.getContext = () =>
  new Proxy(
    {},
    {
      get: (target, key) => target[key] ?? (() => {}),
      set: (target, key, value) => {
        target[key] = value;
        return true;
      },
    },
  );
dom.window.Element.prototype.getBoundingClientRect = function () {
  return { left: 0, top: 0, width: this.width, height: this.height };
};
URL.createObjectURL = () => 'blob:preview';
URL.revokeObjectURL = () => {};
const { createRoot } = await import('react-dom/client');
const { GridShadowCorrectionWorkspace } =
  await import('../src/features/operational-reviews/grid-shadow-correction-workspace.tsx');
after(() => dom.window.close());
const settle = () =>
  act(async () => new Promise((resolve) => setTimeout(resolve, 220)));
const nodes = Array.from({ length: 24 }, (_, i) => ({
  x: 300 + (i % 6) * 80,
  y: 250 + Math.floor(i / 6) * 80,
}));
const item = {
  gameId: 'g',
  importJobId: 'j',
  sourceImageId: 's',
  positionIndex: 2,
  sequenceNumber: 1002,
  sourceWidth: 1200,
  sourceHeight: 900,
  sourceChecksumSha256: 'a'.repeat(64),
  slotId: 'slot',
  slotKind: 'current_review',
  reviewItemId: 'review',
  pendingGeometryId: null,
  geometryRevision: 1,
  resolutionRevision: 0,
  gridColumns: 5,
  gridRows: 3,
  geometry: { quad: [nodes[0], nodes[5], nodes[23], nodes[18]] },
};
function fixture() {
  const calls = { reads: 0, previews: [], saves: [] };
  let stale = false;
  const result = () => ({
    id: 'r',
    gameId: 'g',
    sourceWidth: 1200,
    sourceHeight: 900,
    modelProfile: 'mumie',
    modelVersion: 'v1',
    reasons: [],
    stale,
    output: {
      slots: [
        {
          positionIndex: 2,
          sequenceNumber: 1002,
          state: 'needs_review',
          neuralNodes24: nodes,
          reasonCodes: [],
          reviewItem: stale ? null : item,
        },
      ],
    },
  });
  const api = {
    getGridShadowResult: async () => {
      calls.reads++;
      return { data: result() };
    },
    listSymbols: async () => ({
      data: [
        {
          id: 'cherry',
          name: 'Wiśnia',
          namePl: 'Wiśnia',
          displayOrder: 0,
          status: 'active',
        },
      ],
    }),
    imageGridReviewSourceAssetUrl: () => '/source',
    getImageGridReviewCorrectionSymbols: async () => ({ data: { cells: [] } }),
    previewImageGridReviewGeometry: async (id, scope, command) => {
      calls.previews.push({ id, scope, command });
      return { data: new Blob(['png'], { type: 'image/png' }) };
    },
    createImageGridReviewGeometryRevision: async (id, scope, command) => {
      calls.saves.push({ id, scope, command });
      stale = true;
      return { data: { created: true } };
    },
  };
  return {
    api,
    calls,
    markStale: () => {
      stale = true;
    },
  };
}
async function render(api) {
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(GridShadowCorrectionWorkspace, {
        api,
        apiBaseUrl: '',
        gameId: 'g',
        resultId: 'r',
        positionIndex: 2,
      }),
    ),
  );
  await settle();
  return root;
}
async function key(key) {
  await act(async () =>
    window.dispatchEvent(
      new dom.window.KeyboardEvent('keydown', {
        key,
        bubbles: true,
        cancelable: true,
      }),
    ),
  );
}
const button = (text) =>
  [...document.querySelectorAll('button')].find((node) =>
    node.textContent.includes(text),
  );
const click = async (node) => {
  assert.ok(node);
  await act(async () =>
    node.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })),
  );
  await settle();
};

test('shadow opens immediate crop selection with symbol shortcuts and saves through existing bound command', async () => {
  const { api, calls } = fixture();
  const root = await render(api);
  try {
    assert.match(document.body.textContent, /nie zachowuje pełnych 24 węzłów/);
    assert.equal(calls.previews.length, 1);
    const crop = document.querySelector('button[aria-label^="Crop 1"]');
    assert.equal(crop.getAttribute('aria-pressed'), 'true');
    await key('1');
    assert.match(crop.getAttribute('aria-label'), /Wiśnia/);
    await key('9');
    assert.match(crop.getAttribute('aria-label'), /wybrany symbol: \?/);
    await key('1');
    await act(async () => images.at(-1).onload?.());
    await settle();
    await click(button('Zapisz siatkę'));
    assert.equal(calls.saves.length, 1);
    assert.equal(calls.saves[0].id, 'review');
    assert.equal(calls.saves[0].command.expectedGeometryRevision, 1);
    assert.deepEqual(calls.saves[0].command.cellSymbols, [
      { cellIndex: 0, symbolId: 'cherry' },
    ]);
    assert.match(document.body.textContent, /propozycja jest już nieaktualna/);
    assert.equal(button('Zapisz siatkę'), undefined);
  } finally {
    await act(async () => root.unmount());
  }
});

test('drift before save stops an old proposal without a production write', async () => {
  const { api, calls, markStale } = fixture();
  const root = await render(api);
  try {
    await act(async () => images.at(-1).onload?.());
    await settle();
    markStale();
    await click(button('Zapisz siatkę'));
    assert.equal(calls.saves.length, 0);
    assert.match(document.body.textContent, /nieaktualna/);
  } finally {
    await act(async () => root.unmount());
  }
});
