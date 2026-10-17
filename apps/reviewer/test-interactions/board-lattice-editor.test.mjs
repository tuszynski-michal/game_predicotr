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
async function pointer(canvas, type, x, y, pointerType = 'mouse') {
  const e = new MouseEvent(type, { bubbles: true, button: 0 });
  Object.defineProperties(e, {
    pointerId: { value: 1 },
    pointerType: { value: pointerType },
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
test('moving an internal node survives 24/4 roundtrip, regularization undo and restart', async () => {
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
  await act(async () => button('Dokładna korekta').click());
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
  await act(async () => button('Dokładna korekta').click());
  await settle();
  assert.deepEqual(previews.at(-1).latticeNodes, edited);
  await act(async () => button('Cztery rogi').click());
  await act(async () => button('Dokładna korekta').click());
  assert.deepEqual(previews.at(-1).latticeNodes, edited, '24/4/24 is lossless');
  await act(async () =>
    button('Wyznacz regularną siatkę z czterech rogów').click(),
  );
  await settle();
  assert.deepEqual(
    previews.at(-1).latticeNodes,
    nodes,
    'explicit regularization has live crop preview',
  );
  await act(async () => button('Cofnij zmianę siatki').click());
  await settle();
  assert.deepEqual(
    previews.at(-1).latticeNodes,
    edited,
    'undo restores every corrected float',
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

test('touch corner transforms all nodes, translation is rigid, invalid quad is rejected and a newer revision blocks the draft', async () => {
  localStorage.clear();
  const corrected = structuredClone(nodes);
  corrected[7].x += 4.25;
  const previews = [],
    saves = [];
  function target(revision = 1) {
    return {
      key: `touch:${revision}`,
      draftKey: 'touch',
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
          sourceUrl: 'http://localhost/touch',
          suggestedCorners: [
            corrected[0],
            corrected[5],
            corrected[23],
            corrected[18],
          ],
          suggestedLatticeNodes: corrected,
          draftBindingKey: `revision${revision}`,
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
        return { ok: false, error: 'lost', isConflict: false };
      },
    };
  }
  const props = { onSaved: async () => {}, onConflict: async () => {} };
  let root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(BoardGeometryCorrectionEditor, {
        ...props,
        target: target(),
      }),
    ),
  );
  await act(async () => images.at(-1).onload());
  await settle();
  assert.equal(
    button('Dokładna korekta').getAttribute('aria-pressed'),
    'false',
  );
  let canvas = document.querySelector('canvas'),
    sx = draws.at(-1)[1],
    sy = draws.at(-1)[2];
  await pointer(
    canvas,
    'pointerdown',
    corrected[0].x - sx,
    corrected[0].y - sy,
    'touch',
  );
  await pointer(
    canvas,
    'pointermove',
    corrected[0].x - sx + 10.125,
    corrected[0].y - sy + 8.375,
    'touch',
  );
  await pointer(
    canvas,
    'pointerup',
    corrected[0].x - sx + 10.125,
    corrected[0].y - sy + 8.375,
    'touch',
  );
  await settle();
  const transformed = structuredClone(previews.at(-1).latticeNodes);
  assert.deepEqual(transformed[0], {
    x: corrected[0].x + 10.125,
    y: corrected[0].y + 8.375,
  });
  assert.deepEqual(transformed[5], corrected[5]);
  assert.notDeepEqual(
    transformed[7],
    corrected[7],
    'internal corrections move with corner homography',
  );
  await act(async () => button('Zapisz geometrię i dalej').click());
  assert.deepEqual(
    saves.at(-1)[4],
    transformed,
    'save consumes the exact previewed lattice',
  );
  sx = draws.at(-1)[1];
  sy = draws.at(-1)[2];
  await pointer(canvas, 'pointerdown', 280 - sx, 170 - sy, 'touch');
  await pointer(canvas, 'pointerup', 283.125 - sx, 174.375 - sy, 'touch');
  await settle();
  const translated = structuredClone(previews.at(-1).latticeNodes);
  translated.forEach((p, i) => {
    assert.equal(p.x, transformed[i].x + 3.125);
    assert.equal(p.y, transformed[i].y + 4.375);
  });
  await act(async () => button('Cofnij zmianę siatki').click());
  await settle();
  assert.deepEqual(previews.at(-1).latticeNodes, transformed);
  sx = draws.at(-1)[1];
  sy = draws.at(-1)[2];
  await pointer(
    canvas,
    'pointerdown',
    transformed[0].x - sx,
    transformed[0].y - sy,
  );
  await pointer(
    canvas,
    'pointerup',
    transformed[23].x - sx - 10,
    transformed[23].y - sy - 10,
  );
  await settle();
  assert.deepEqual(
    previews.at(-1).latticeNodes,
    transformed,
    'crossed corner never changes geometry',
  );
  await act(async () => root.unmount());
  root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(BoardGeometryCorrectionEditor, {
        ...props,
        target: target(2),
      }),
    ),
  );
  await settle();
  assert.match(document.body.textContent, /Nie można odtworzyć szkicu/);
  assert.deepEqual(
    previews.at(-1).latticeNodes,
    corrected,
    'new server view never inherits stale draft',
  );
  assert.equal(button('Zapisz geometrię i dalej').disabled, true);
  await act(async () => button('Przywróć sugestię').click());
  await settle();
  assert.equal(button('Zapisz geometrię i dalej').disabled, false);
  await act(async () => root.unmount());
});

test('empty neural sketch builds regular24 then edits exact internal nodes; legacy has no exact-node controls', async () => {
  localStorage.clear();
  const previews = [],
    saves = [];
  const props = { onSaved: async () => {}, onConflict: async () => {} };
  function target(supportsLatticeEditing) {
    return {
      key: `empty:${supportsLatticeEditing}`,
      load: async () => ({
        ok: true,
        view: {
          initialFlags: {
            partial: false,
            exclude: false,
            includeInPartialGridTraining: false,
            manualUnavailable: [],
          },
          kind: 'deferred',
          metadata: [],
          reportedCellIndices: [],
          saveHint: 'test',
          sourceWidth: 600,
          sourceHeight: 400,
          sourceUrl: 'http://localhost/empty',
          suggestedCorners: [nodes[0], nodes[5], nodes[23], nodes[18]],
          supportsLatticeEditing,
          draftBindingKey: 'neural-pin:revision1',
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
        return { ok: false, error: 'lost', isConflict: false };
      },
    };
  }
  let root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(BoardGeometryCorrectionEditor, {
        ...props,
        target: target(true),
      }),
    ),
  );
  await act(async () => images.at(-1).onload());
  await settle();
  assert.equal(button('Dokładna korekta').disabled, true);
  await act(async () =>
    button('Wyznacz regularną siatkę z czterech rogów').click(),
  );
  await settle();
  assert.deepEqual(previews.at(-1).latticeNodes, nodes);
  await act(async () => button('Dokładna korekta').click());
  const canvas = document.querySelector('canvas'),
    sx = draws.at(-1)[1],
    sy = draws.at(-1)[2];
  await pointer(
    canvas,
    'pointerdown',
    nodes[7].x - sx,
    nodes[7].y - sy,
    'touch',
  );
  await pointer(
    canvas,
    'pointerup',
    nodes[7].x - sx + 1.125,
    nodes[7].y - sy + 2.375,
    'touch',
  );
  await settle();
  assert.equal(previews.at(-1).latticeNodes[7].x, nodes[7].x + 1.125);
  await act(async () => button('Zapisz geometrię i dalej').click());
  assert.deepEqual(saves.at(-1)[4], previews.at(-1).latticeNodes);
  await act(async () => button('Cofnij zmianę siatki').click());
  await settle();
  assert.deepEqual(previews.at(-1).latticeNodes, nodes);
  await act(async () => root.unmount());
  root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(BoardGeometryCorrectionEditor, {
        ...props,
        target: target(false),
      }),
    ),
  );
  await settle();
  assert.equal(button('Dokładna korekta'), undefined);
  assert.equal(button('Wyznacz regularną siatkę z czterech rogów'), undefined);
  await act(async () => root.unmount());
});
