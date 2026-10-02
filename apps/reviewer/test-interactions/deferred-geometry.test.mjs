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
]) {
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
}
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
const draws = [];
dom.window.HTMLCanvasElement.prototype.getContext = function () {
  return new Proxy(
    {
      drawImage: (...args) => draws.push({ canvas: this, args }),
    },
    { get: (object, key) => (key in object ? object[key] : () => {}) },
  );
};
dom.window.Element.prototype.getBoundingClientRect = function () {
  return { left: 0, top: 0, width: this.width, height: this.height };
};
dom.window.Element.prototype.setPointerCapture = () => {};
dom.window.Element.prototype.hasPointerCapture = () => false;
const { createRoot } = await import('react-dom/client');
const { DeferredBoardCellGeometryEditor } =
  await import('../src/features/operational-reviews/deferred-board-cell-geometry-editor.tsx');
const corners = [
  { x: 300, y: 250 },
  { x: 700, y: 250 },
  { x: 700, y: 500 },
  { x: 300, y: 500 },
];
const context = {
  sourceWidth: 1200,
  sourceHeight: 900,
  suggestedCorners: corners,
  item: {
    id: 'a',
    gameId: 'g',
    importJobId: 'j',
    sequenceNumber: 1,
    positionIndex: 0,
    reasonCode: 'incomplete_lattice',
    sourceRelativePath: 'a.jpg',
    sourceChecksumSha256: 'a'.repeat(64),
    expectedGeometryRevision: 0,
    expectedReviewResolutionRevision: 0,
    processingManifestChecksumSha256: 'b'.repeat(64),
  },
};
const requests = [];
const conflicts = [];
const props = {
  api: {
    getPendingBoardCellGeometryCorrectionContext: async (id) => ({
      data: { ...context, item: { ...context.item, id } },
    }),
    previewPendingBoardCellGeometryCorrection: (id, scope, command) =>
      new Promise((resolve) => requests.push({ id, command, resolve })),
    resolvePendingBoardCellGeometryManually: () =>
      assert.fail('No automatic persistence'),
  },
  apiBaseUrl: 'http://localhost',
  itemId: 'a',
  scope: { gameId: 'g', importJobId: 'j' },
  onConflict: async (message) => {
    conflicts.push(message);
  },
  onMaterialized: async () => {},
};
const settle = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 180));
  });
async function pointer(canvas, type, x, y, pointerId = 1) {
  const event = new dom.window.MouseEvent(type, {
    bubbles: true,
    clientX: x,
    clientY: y,
    button: 0,
  });
  Object.defineProperty(event, 'pointerId', { value: pointerId });
  await act(async () => canvas.dispatchEvent(event));
}
after(() => dom.window.close());

test('deferred editor freezes source through hold, fits and previews final geometry on release; stale responses and next image are isolated', async () => {
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(React.createElement(DeferredBoardCellGeometryEditor, props)),
  );
  assert.equal(draws.length, 0);
  await act(async () => images.at(-1).onload());
  assert.ok(draws.length > 0, 'source paints without a click');
  await settle();
  assert.equal(requests.length, 1);
  const canvas = document.querySelector('canvas');
  const before = draws.at(-1).args.slice(1);
  const sourceX = before[0],
    sourceY = before[1];
  await pointer(canvas, 'pointerdown', 300 - sourceX, 250 - sourceY);
  await pointer(canvas, 'pointermove', 240 - sourceX, 200 - sourceY);
  await settle();
  assert.deepEqual(
    draws.at(-1).args.slice(1),
    before,
    'source crop/scale must stay fixed during hold',
  );
  assert.equal(requests.length, 1, 'no preview while held');
  await pointer(canvas, 'pointerup', 180 - sourceX, 180 - sourceY, 2);
  assert.deepEqual(
    draws.at(-1).args.slice(1),
    before,
    'another pointer cannot finish',
  );
  await pointer(canvas, 'pointerup', 230 - sourceX, 190 - sourceY);
  assert.notDeepEqual(
    draws.at(-1).args.slice(1),
    before,
    'fit only on release',
  );
  await settle();
  assert.equal(requests.length, 2);
  assert.deepEqual(
    requests[1].command.corners[0],
    { x: 230, y: 190 },
    'preview uses final pointerup position',
  );
  await act(async () => requests[1].resolve({ data: new Blob(['new']) }));
  const previewTile = () =>
    document.querySelector('[aria-label="Podgląd 15 cropów planszy"] > div')
      .style.backgroundImage;
  const preview = previewTile();
  await act(async () =>
    requests[0].resolve({
      error: {
        code: 'IMAGE_BOARD_CELL_PENDING_REVISION_CONFLICT',
        message: 'stale',
      },
    }),
  );
  assert.equal(previewTile(), preview);
  assert.deepEqual(conflicts, []);
  assert.ok(!document.body.textContent.includes('Aktywne przesuwanie'));

  const previousImage = images.at(-1);
  await act(async () =>
    root.render(
      React.createElement(DeferredBoardCellGeometryEditor, {
        ...props,
        itemId: 'b',
      }),
    ),
  );
  assert.notEqual(images.at(-1), previousImage);
  await act(async () => images.at(-1).onload());
  assert.equal(
    draws.at(-1).args[0],
    images.at(-1),
    'next image draws immediately',
  );
  await settle();
  assert.equal(requests.at(-1).id, 'b');
  const bCanvas = document.querySelector('canvas');
  const bDraw = draws.at(-1).args;
  await pointer(bCanvas, 'pointerdown', 500 - bDraw[1], 375 - bDraw[2]);
  await pointer(bCanvas, 'pointermove', 540 - bDraw[1], 385 - bDraw[2]);
  await pointer(bCanvas, 'pointercancel', 0, 0);
  await settle();
  assert.deepEqual(
    requests.at(-1).command.corners,
    corners.map((p) => ({ x: p.x + 40, y: p.y + 10 })),
  );
  await pointer(bCanvas, 'pointermove', 0, 0);
  const count = requests.length;
  await settle();
  assert.equal(requests.length, count, 'cancel clears whole-grid drag');
  await act(async () => root.unmount());
  await act(async () => requests.at(-1).resolve({ data: new Blob(['late']) }));

  const restarted = createRoot(document.getElementById('root'));
  await act(async () =>
    restarted.render(
      React.createElement(DeferredBoardCellGeometryEditor, props),
    ),
  );
  await act(async () => images.at(-1).onload());
  assert.equal(
    draws.at(-1).canvas,
    document.querySelector('canvas'),
    'remount repaints current canvas',
  );
  await act(async () => restarted.unmount());
});
