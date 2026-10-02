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
  naturalWidth = 620;
  naturalHeight = 420;
  set src(value) {
    this.url = value;
    images.push(this);
  }
};
dom.window.HTMLCanvasElement.prototype.getContext = function () {
  return new Proxy({}, { get: () => () => {} });
};
dom.window.Element.prototype.getBoundingClientRect = function () {
  return { left: 0, top: 0, width: this.width, height: this.height };
};
const dialogPrototype = dom.window.HTMLDialogElement.prototype;
dialogPrototype.showModal ??= function () {
  this.open = true;
};
dialogPrototype.close ??= function () {
  this.open = false;
};
URL.createObjectURL = () => 'blob:preview';
URL.revokeObjectURL = () => {};
const { createRoot } = await import('react-dom/client');
const { OperationalReviewGeometryEditor } =
  await import('../src/features/operational-reviews/operational-review-geometry-editor.tsx');
after(() => dom.window.close());

const LATTICE = [
  { x: 100, y: 80 },
  { x: 500, y: 80 },
  { x: 500, y: 320 },
  { x: 100, y: 320 },
];

function item(overrides = {}) {
  return {
    boardChecksumSha256: 'b'.repeat(64),
    cells: [],
    createdAt: '2026-10-01T00:00:00Z',
    gameId: 'g',
    geometry: { latticeBoundsQuad: LATTICE },
    geometryQualification: null,
    geometryRevision: 1,
    id: 'r1',
    importJobId: 'j',
    pipelineFingerprint: 'c'.repeat(64),
    positionIndex: 0,
    recognizedBoardId: 'b1',
    resolutionRevision: 0,
    resolvedAt: null,
    resolvedBy: null,
    resolvedValue: null,
    sequenceNumber: null,
    sourceChecksumSha256: 'a'.repeat(64),
    sourceHeight: 420,
    sourceOrderIndex: 0,
    sourceWidth: 620,
    status: 'pending',
    suggestedSequenceNumber: 100,
    ...overrides,
  };
}

function fakeApi() {
  const calls = { preview: [], save: [] };
  const api = {
    createOperationalImageReviewGeometryRevision: async (id, scope, body) => {
      calls.save.push({ body, id, scope });
      return {
        data: {
          created: true,
          geometryRevision: { revision: 2 },
          item: item({ geometryRevision: 2 }),
        },
      };
    },
    previewOperationalImageReviewGeometry: async (id, scope, body) => {
      calls.preview.push({ body, id, scope });
      return { data: new Blob(['png'], { type: 'image/png' }) };
    },
  };
  return { api, calls };
}

const settle = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 220));
  });

function button(text) {
  return [...document.querySelectorAll('button')].find(
    (candidate) => candidate.textContent === text,
  );
}

function checkbox(label) {
  return [...document.querySelectorAll('input[type="checkbox"]')].find(
    (candidate) =>
      candidate.getAttribute('aria-label') === label ||
      candidate.parentElement?.textContent.trim() === label,
  );
}

async function openEditor(api, saved) {
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(OperationalReviewGeometryEditor, {
        api,
        apiBaseUrl: 'http://localhost/api/review',
        importJobId: 'j',
        item: item(),
        onSaved: (geometry) => saved.push(geometry),
      }),
    ),
  );
  await act(async () => button('Edytuj siatkę').click());
  await settle();
  await act(async () => images.at(-1).onload?.());
  await settle();
  return root;
}

test('the operational editor saves a partial board with its qualification (TASK-0798)', async () => {
  const { api, calls } = fakeApi();
  const saved = [];
  const root = await openEditor(api, saved);

  assert.equal(document.querySelector('dialog').open, true);
  assert.match(document.body.textContent, /Numer planszy100/);
  assert.equal(calls.preview.length, 1);
  assert.equal(calls.preview[0].body.geometryQualification, null);

  await act(async () => checkbox('Niepełna plansza').click());
  await act(async () => checkbox('Pole 1 poza zdjęciem').click());
  await settle();

  const previewed = calls.preview.at(-1).body.geometryQualification;
  assert.equal(previewed.completenessStatus, 'pending_partial');
  assert.deepEqual(previewed.unavailableCellIndices, [0]);
  const missingTiles = [...document.querySelectorAll('[role="img"]')]
    .map((tile) => tile.getAttribute('aria-label'))
    .filter((label) => label.includes('poza zdjęciem'));
  assert.deepEqual(missingTiles, ['Crop 1 — poza zdjęciem']);

  await act(async () => button('Zapisz nową rewizję').click());
  await settle();

  assert.equal(calls.save.length, 1);
  assert.equal(calls.save[0].id, 'r1');
  assert.deepEqual(calls.save[0].scope, { gameId: 'g', importJobId: 'j' });
  assert.deepEqual(calls.save[0].body.geometryQualification, previewed);
  assert.equal(calls.save[0].body.expectedGeometryRevision, 1);
  assert.equal(saved.length, 1);
  assert.equal(saved[0].geometryRevision.revision, 2);
  assert.equal(document.querySelector('dialog').open, false);
  await act(async () => root.unmount());
});

test('a revision conflict keeps the editor open with a reload hint', async () => {
  const { api } = fakeApi();
  api.previewOperationalImageReviewGeometry = async () => ({
    error: {
      code: 'IMAGE_GRID_REVIEW_REVISION_CONFLICT',
      message: 'Zmieniona geometria.',
    },
  });
  const saved = [];
  const root = await openEditor(api, saved);

  assert.equal(document.querySelector('dialog').open, true);
  assert.match(
    document.body.textContent,
    /Zmieniona geometria.*Zamknij edytor i przeładuj planszę/,
  );
  assert.equal(saved.length, 0);
  await act(async () => root.unmount());
});
