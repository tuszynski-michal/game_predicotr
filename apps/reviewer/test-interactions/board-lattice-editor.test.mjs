import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost' });
for (const key of [
  'window',
  'document',
  'HTMLElement',
  'Element',
  'Event',
  'MouseEvent',
  'localStorage',
])
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const images = [],
  draws = [];
dom.window.Image = class {
  naturalWidth = 600;
  naturalHeight = 400;
  set src(value) {
    this.url = value;
    images.push(this);
  }
};
dom.window.HTMLCanvasElement.prototype.getContext = function () {
  return new Proxy(
    { drawImage: (...args) => draws.push(args) },
    { get: (obj, key) => (key in obj ? obj[key] : () => {}) },
  );
};
dom.window.Element.prototype.getBoundingClientRect = function () {
  return { left: 0, top: 0, width: this.width, height: this.height };
};
dom.window.Element.prototype.setPointerCapture = () => {};
dom.window.Element.prototype.hasPointerCapture = () => false;
URL.createObjectURL = () => 'blob:preview';
URL.revokeObjectURL = () => {};
const { createRoot } = await import('react-dom/client');
const { BoardGeometryCorrectionEditor } =
  await import('../src/features/operational-reviews/deferred-board-cell-geometry-editor.tsx');
after(() => dom.window.close());
const nodes = Array.from({ length: 24 }, (_, i) => ({
  x: 50.125 + (i % 6) * 90,
  y: 50.375 + Math.floor(i / 6) * 80,
}));
const settle = () =>
  act(async () => {
    await new Promise((r) => setTimeout(r, 190));
  });
const button = (text) =>
  [...document.querySelectorAll('button')].find((b) => b.textContent === text);
async function pointer(canvas, type, x, y) {
  const e = new MouseEvent(type, { bubbles: true, button: 0 });
  Object.defineProperties(e, {
    pointerId: { value: 1 },
    clientX: { value: x },
    clientY: { value: y },
  });
  await act(async () => canvas.dispatchEvent(e));
}
test('full-node editor previews on open, changes symbol without redrawing grid and retries exact command after restart', async () => {
  localStorage.clear();
  const calls = { previews: [], saves: [] };
  let lost = true;
  const target = {
    key: 'full24',
    load: async () => ({
      ok: true,
      view: {
        initialFlags: {
          partial: false,
          exclude: false,
          includeInPartialGridTraining: false,
          manualUnavailable: [],
        },
        kind: 'reported',
        metadata: [],
        reportedCellIndices: [],
        saveHint: 'test',
        sourceWidth: 600,
        sourceHeight: 400,
        sourceUrl: 'http://localhost/source?sha=a',
        suggestedCorners: [nodes[0], nodes[5], nodes[23], nodes[18]],
        suggestedLatticeNodes: nodes,
        draftBindingKey: 'revision1:proposalA',
        supportsPartial: true,
      },
    }),
    commandKey: (corners, flags, latticeNodes) =>
      JSON.stringify({ corners, flags, latticeNodes }),
    preview: async (corners, flags, latticeNodes) => {
      calls.previews.push(structuredClone({ corners, flags, latticeNodes }));
      return { ok: true, blob: new Blob(['png']) };
    },
    symbols: async () => ({ ok: true, cells: [] }),
    save: async (...args) => {
      calls.saves.push(structuredClone(args));
      return lost
        ? ((lost = false), { ok: false, error: 'lost', isConflict: false })
        : { ok: true, reviewItemId: 'done' };
    },
  };
  const props = {
    target,
    symbols: [{ id: 'cherry', label: 'Wiśnia', shortcut: '1' }],
    unknownSymbolShortcut: '9',
    onSaved: async () => {},
    onConflict: async () => {},
  };
  let root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(React.createElement(BoardGeometryCorrectionEditor, props)),
  );
  await settle();
  assert.equal(calls.previews.length, 1, 'no source-click needed');
  assert.deepEqual(calls.previews[0].latticeNodes, nodes);
  await act(async () =>
    window.dispatchEvent(
      new dom.window.KeyboardEvent('keydown', { key: '1', bubbles: true }),
    ),
  );
  await settle();
  assert.equal(
    calls.previews.length,
    1,
    'symbol picker leaves crop geometry unchanged',
  );
  await act(async () => button('Zapisz geometrię i dalej').click());
  assert.equal(calls.saves[0][3][0].symbolId, 'cherry');
  await act(async () => root.unmount());
  root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(React.createElement(BoardGeometryCorrectionEditor, props)),
  );
  await settle();
  await act(async () => button('Zapisz geometrię i dalej').click());
  assert.deepEqual(
    calls.saves[1],
    calls.saves[0],
    'exact float geometry, symbol and idempotency after remount',
  );
  await act(async () => root.unmount());
});
test('moving one internal node keeps the other23 float nodes; corner conversion is explicit and integer-compatible', async () => {
  localStorage.clear();
  const previews = [];
  const saves = [];
  const target = {
    key: 'drag24',
    load: async () => ({
      ok: true,
      view: {
        initialFlags: {
          partial: false,
          exclude: false,
          includeInPartialGridTraining: false,
          manualUnavailable: [],
        },
        kind: 'reported',
        metadata: [],
        reportedCellIndices: [],
        saveHint: 'test',
        sourceWidth: 600,
        sourceHeight: 400,
        sourceUrl: 'http://localhost/drag',
        suggestedCorners: [nodes[0], nodes[5], nodes[23], nodes[18]],
        suggestedLatticeNodes: nodes,
        draftBindingKey: 'revision1',
        supportsPartial: true,
      },
    }),
    commandKey: (corners, flags, latticeNodes) =>
      JSON.stringify({ corners, flags, latticeNodes }),
    preview: async (corners, flags, latticeNodes) => {
      previews.push(structuredClone({ corners, latticeNodes }));
      return { ok: true, blob: new Blob(['png']) };
    },
    save: async (...args) => {
      saves.push(structuredClone(args));
      return { ok: false, error: 'lost response', isConflict: false };
    },
  };
  let root = createRoot(document.getElementById('root'));
  const props = { target, onSaved: async () => {}, onConflict: async () => {} };
  await act(async () =>
    root.render(
      React.createElement(BoardGeometryCorrectionEditor, {
        target,
        onSaved: async () => {},
        onConflict: async () => {},
      }),
    ),
  );
  await act(async () => images.at(-1).onload());
  await settle();
  const canvas = document.querySelector('canvas'),
    sx = draws.at(-1)[1],
    sy = draws.at(-1)[2],
    p = nodes[7];
  await pointer(canvas, 'pointerdown', p.x - sx, p.y - sy);
  await pointer(canvas, 'pointermove', p.x - sx + 1.125, p.y - sy + 2.375);
  await pointer(canvas, 'pointerup', p.x - sx + 1.125, p.y - sy + 2.375);
  await settle();
  assert.equal(previews.at(-1).latticeNodes[7].x, p.x + 1.125);
  assert.equal(previews.at(-1).latticeNodes[7].y, p.y + 2.375);
  assert.deepEqual(
    previews.at(-1).latticeNodes.filter((_, i) => i !== 7),
    nodes.filter((_, i) => i !== 7),
  );
  const edited = structuredClone(previews.at(-1).latticeNodes);
  await act(async () => button('Zapisz geometrię i dalej').click());
  assert.equal(saves.length, 1, 'dragged draft remains writable');
  assert.deepEqual(saves[0][4], edited);
  await act(async () => root.unmount());
  root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(React.createElement(BoardGeometryCorrectionEditor, props)),
  );
  await settle();
  assert.deepEqual(
    previews.at(-1).latticeNodes,
    edited,
    'dragged draft survives restart',
  );
  await act(async () => button('Zapisz geometrię i dalej').click());
  assert.deepEqual(
    saves[1],
    saves[0],
    'retry of dragged draft is exact after restart',
  );
  await act(async () => images.at(-1).onload());
  await act(async () =>
    button('Zamień na szkic z czterech narożników').click(),
  );
  await settle();
  assert.equal(previews.at(-1).latticeNodes, undefined);
  assert.ok(
    previews
      .at(-1)
      .corners.every((p) => Number.isInteger(p.x) && Number.isInteger(p.y)),
  );
  await act(async () => button('Przywróć sugestię').click());
  await settle();
  await act(async () => button('Zapisz geometrię i dalej').click());
  assert.deepEqual(
    saves.at(-1)[4],
    nodes,
    'restore suggestion remains writable',
  );
  await act(async () => root.unmount());
});

test('all24 legal nodes remain visible outside the corner padding; viewport never rewrites geometry', async () => {
  localStorage.clear();
  const extended = structuredClone(nodes);
  extended[1].y = -150.125;
  const saves = [];
  const target = {
    key: 'outside-boundary',
    load: async () => ({
      ok: true,
      view: {
        initialFlags: {
          partial: true,
          exclude: false,
          includeInPartialGridTraining: false,
          manualUnavailable: [],
        },
        kind: 'reported',
        metadata: [],
        reportedCellIndices: [],
        saveHint: 'test',
        sourceWidth: 600,
        sourceHeight: 400,
        sourceUrl: 'http://localhost/extended',
        suggestedCorners: [nodes[0], nodes[5], nodes[23], nodes[18]],
        suggestedLatticeNodes: extended,
        draftBindingKey: 'revision1',
        supportsPartial: true,
      },
    }),
    commandKey: (corners, flags, latticeNodes) =>
      JSON.stringify({ corners, flags, latticeNodes }),
    preview: async () => ({ ok: true, blob: new Blob(['png']) }),
    save: async (...args) => {
      saves.push(structuredClone(args));
      return { ok: false, error: 'mock receipt', isConflict: false };
    },
  };
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(BoardGeometryCorrectionEditor, {
        target,
        onSaved: async () => {},
        onConflict: async () => {},
      }),
    ),
  );
  await act(async () => images.at(-1).onload());
  await settle();
  const canvas = document.querySelector('canvas'),
    draw = draws.at(-1);
  const sx = draw[1] - draw[5],
    sy = draw[2] - draw[6];
  assert.ok(
    extended.every(
      (p) =>
        p.x >= sx &&
        p.x <= sx + canvas.width &&
        p.y >= sy &&
        p.y <= sy + canvas.height,
    ),
    'every handle fits the rendered viewport',
  );
  await act(async () => button('Zapisz geometrię i dalej').click());
  assert.equal(saves.length, 1);
  assert.deepEqual(saves[0][4], extended);
  assert.deepEqual(
    saves[0][0],
    [nodes[0], nodes[5], nodes[23], nodes[18]],
    'fit rectangle is not saved as geometry',
  );
  await act(async () => root.unmount());
});
