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
  'SVGElement',
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
globalThis.ResizeObserver = class {
  observe() {}
  disconnect() {}
};
dom.window.Element.prototype.getBoundingClientRect = () => ({
  x: 0,
  y: 0,
  left: 0,
  top: 0,
  right: 320,
  bottom: 320,
  width: 320,
  height: 320,
});
dom.window.Element.prototype.setPointerCapture = () => {};
const { createRoot } = await import('react-dom/client');
const { PageGeometryCorrectionPanel } =
  await import('../src/features/imports/page-geometry-correction-panel.tsx');
after(() => dom.window.close());

const quads = Array.from({ length: 9 }, (_, i) => {
  const x = (i % 3) * 100 + 5,
    y = Math.floor(i / 3) * 100 + 5;
  return [
    { x, y },
    { x: x + 90, y },
    { x: x + 90, y: y + 90 },
    { x, y: y + 90 },
  ];
});
const sources = Array.from({ length: 2 }, (_, i) => ({
  sourceChecksumSha256: String(i + 1).repeat(64),
  sourceRelativePath: `seq_${i * 9 + 1}-${i * 9 + 9}.jpg`,
  expectedBoardCount: 9,
  existingFinalQuads: quads,
  existingOverrideRevision: 1,
  existingSlotQualifications: null,
  savedSincePreflight: false,
  geometryOrigin: 'manual_override',
  reviewReason: 'manual_override',
}));
function button(text) {
  return [...document.querySelectorAll('button')].find((node) =>
    node.textContent.includes(text),
  );
}
function checkbox(text) {
  const label = [...document.querySelectorAll('label')].find((node) =>
    node.textContent.includes(text),
  );
  return label?.querySelector('input[type=checkbox]');
}
async function click(node) {
  assert.ok(node);
  await act(async () =>
    node.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })),
  );
}
async function imageLoaded() {
  const img = document.querySelector('img');
  Object.defineProperties(img, {
    naturalWidth: { configurable: true, value: 320 },
    naturalHeight: { configurable: true, value: 320 },
  });
  await act(async () =>
    img.dispatchEvent(new dom.window.Event('load', { bubbles: true })),
  );
}
async function selectFirst() {
  const polygon = document.querySelector('polygon.pageGeometryBoard');
  assert.ok(polygon);
  await act(async () =>
    polygon.dispatchEvent(
      new dom.window.MouseEvent('pointerdown', { bubbles: true }),
    ),
  );
}

test('navigation never writes; flags survive remount; reset before next image load cannot copy prior geometry', async () => {
  localStorage.clear();
  const writes = [],
    preflights = [];
  const api = {
    listBrowserPageGeometryReviewSources: async () => ({
      data: { sources, geometryManifestChecksumSha256: 'f'.repeat(64) },
    }),
    createBrowserPageGeometryOverride: async (_id, body) => {
      writes.push(body);
      return { data: { revision: 2 } };
    },
    excludeBrowserPageGeometrySource: async () => {
      throw Error('unexpected exclusion');
    },
  };
  const props = {
    api,
    apiBaseUrl: 'http://127.0.0.1:8000',
    gameId: 'game',
    uploadId: 'upload',
    preflightJobId: 'preflight',
    onSubmitSaved: async () => preflights.push(1),
  };
  let root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(React.createElement(PageGeometryCorrectionPanel, props)),
  );
  await imageLoaded();
  await selectFirst();
  let checks = document.querySelectorAll('input[type=checkbox]');
  assert.equal(checks.length, 3);
  assert.equal(
    checkbox('Użyj w oddzielnym uczeniu niepełnych siatek').checked,
    false,
  );
  assert.equal(
    checkbox('Użyj w oddzielnym uczeniu niepełnych siatek').disabled,
    true,
  );
  await click(checkbox('Nie używaj do uczenia geometrii'));
  assert.equal(checkbox('Nie używaj do uczenia geometrii').checked, true);
  await click(button('Następna'));
  await click(button('Reset'));
  await click(button('Zapisz i przejdź dalej'));
  assert.equal(writes.length, 0);
  assert.equal(preflights.length, 0);
  await imageLoaded();
  await click(button('Poprzednia'));
  await imageLoaded();
  await selectFirst();
  assert.equal(checkbox('Nie używaj do uczenia geometrii').checked, true);
  await act(async () => root.unmount());
  root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(React.createElement(PageGeometryCorrectionPanel, props)),
  );
  await imageLoaded();
  await selectFirst();
  assert.equal(checkbox('Nie używaj do uczenia geometrii').checked, true);
  const draftKey = `page-geometry-draft-v1:game:upload:preflight:${sources[0].sourceChecksumSha256}:1`;
  const otherTabText = localStorage.getItem(draftKey) + ' ';
  localStorage.setItem(draftKey, otherTabText);
  await click(button('Zapisz i przejdź dalej'));
  assert.equal(localStorage.getItem(draftKey), otherTabText);
  assert.equal(writes.length, 1);
  assert.equal(preflights.length, 0);
  assert.equal(writes[0].expectedOverrideRevision, 1);
  assert.equal(
    writes[0].slotQualifications[0].excludeFromGeometryTraining,
    true,
  );
  assert.equal(writes[0].slotQualifications.length, 9);
  assert.deepEqual(writes[0].finalQuads, quads);
  await act(async () => root.unmount());
});

test('partial training checkbox saves one complete lateral missing column', async () => {
  localStorage.clear();
  const writes = [];
  const props = {
    api: {
      listBrowserPageGeometryReviewSources: async () => ({
        data: {
          sources: [sources[0]],
          geometryManifestChecksumSha256: 'f'.repeat(64),
        },
      }),
      createBrowserPageGeometryOverride: async (_id, body) => {
        writes.push(body);
        return { data: { revision: 2 } };
      },
    },
    apiBaseUrl: 'http://127.0.0.1:8000',
    gameId: 'game',
    uploadId: 'upload',
    preflightJobId: 'preflight',
    onSubmitSaved: async () => {
      throw Error('unexpected preflight');
    },
  };
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(React.createElement(PageGeometryCorrectionPanel, props)),
  );
  await imageLoaded();
  await selectFirst();
  await click(checkbox('Niepełna plansza'));
  assert.equal(checkbox('Nie używaj do uczenia geometrii').disabled, true);
  assert.equal(
    checkbox('Użyj w oddzielnym uczeniu niepełnych siatek').disabled,
    false,
  );
  await click(checkbox('Użyj w oddzielnym uczeniu niepełnych siatek'));
  await click(
    document.querySelector('input[aria-label="Pole 1 poza zdjęciem"]'),
  );
  await click(
    document.querySelector('input[aria-label="Pole 6 poza zdjęciem"]'),
  );
  await click(
    document.querySelector('input[aria-label="Pole 11 poza zdjęciem"]'),
  );
  await click(button('Zapisz i przejdź dalej'));
  assert.equal(writes.length, 1);
  assert.equal(
    writes[0].slotQualifications[0].completenessStatus,
    'pending_partial',
  );
  assert.equal(
    writes[0].slotQualifications[0].includeInPartialGridTraining,
    true,
  );
  assert.equal(
    writes[0].slotQualifications[0].excludeFromGeometryTraining,
    true,
  );
  assert.deepEqual(
    writes[0].slotQualifications[0].unavailableCellIndices,
    [0, 5, 10],
  );
  await act(async () => root.unmount());
});

test('v1.2 saves independently confirmed frame and symbol-grid layers', async () => {
  localStorage.clear();
  const writes = [];
  const frames = quads.map((quad) =>
    quad.map((point) => ({ x: point.x - 2, y: point.y - 2 })),
  );
  const props = {
    api: {
      listBrowserPageGeometryReviewSources: async () => ({
        data: {
          sources: [
            {
              ...sources[0],
              existingOverrideRevision: undefined,
              geometryOrigin: 'automatic',
              reviewReason: 'operator_inspection',
              existingBoardFrameQuads: frames,
              existingSymbolGridQuads: quads,
            },
          ],
          geometryManifestChecksumSha256: 'f'.repeat(64),
        },
      }),
      createBrowserPageGeometryOverride: async (_id, body) => {
        writes.push(body);
        return { data: { revision: 2 } };
      },
    },
    apiBaseUrl: 'http://127.0.0.1:8000',
    gameId: 'game',
    geometryEngineVariant: 'contrast_frame_grid_v1_2',
    uploadId: 'upload',
    preflightJobId: 'preflight',
    onSubmitSaved: async () => {
      throw Error('unexpected preflight');
    },
  };
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(React.createElement(PageGeometryCorrectionPanel, props)),
  );
  await imageLoaded();
  await selectFirst();
  assert.equal(button('Zapisz i przejdź dalej').disabled, true);
  await click(checkbox('Potwierdzam obrys ramki planszy'));
  await click(button('Zapisz i przejdź dalej'));

  assert.equal(writes.length, 1);
  assert.deepEqual(writes[0].boardFrameQuads, frames);
  assert.deepEqual(writes[0].symbolGridQuads, quads);
  assert.deepEqual(writes[0].finalQuads, quads);
  await act(async () => root.unmount());
});

test('v1.2 does not treat a legacy override as confirmation of a proposed frame', async () => {
  localStorage.clear();
  const source = {
    ...sources[0],
    existingOverrideRevision: 4,
    geometryOrigin: 'manual_override',
    reviewReason: 'manual_override',
    existingBoardFrameQuads: null,
    existingSymbolGridQuads: null,
  };
  const props = {
    api: {
      listBrowserPageGeometryReviewSources: async () => ({
        data: {
          sources: [source],
          geometryManifestChecksumSha256: 'f'.repeat(64),
        },
      }),
      createBrowserPageGeometryOverride: async () => {
        throw Error('must require frame confirmation');
      },
    },
    apiBaseUrl: 'http://127.0.0.1:8000',
    gameId: 'game',
    geometryEngineVariant: 'contrast_frame_grid_v1_2',
    uploadId: 'upload',
    preflightJobId: 'preflight',
    onSubmitSaved: async () => {
      throw Error('unexpected preflight');
    },
  };
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(React.createElement(PageGeometryCorrectionPanel, props)),
  );
  await imageLoaded();
  await selectFirst();

  assert.equal(button('Zapisz i przejdź dalej').disabled, true);
  await act(async () => root.unmount());
});

test('v1.2 reload restores both draft layers and its active frame layer', async () => {
  localStorage.clear();
  const writes = [];
  const frames = quads.map((quad) =>
    quad.map((point) => ({ x: point.x - 4, y: point.y - 3 })),
  );
  const symbols = quads.map((quad) =>
    quad.map((point) => ({ x: point.x + 3, y: point.y + 2 })),
  );
  const source = {
    ...sources[0],
    existingOverrideRevision: undefined,
    geometryOrigin: 'automatic',
    reviewReason: 'operator_inspection',
    existingBoardFrameQuads: quads,
    existingSymbolGridQuads: quads,
  };
  const draftScope = {
    gameId: 'game',
    uploadId: 'upload',
    preflightJobId: 'preflight',
    checksum: source.sourceChecksumSha256,
    revision: 0,
    width: 320,
    height: 320,
    count: 9,
  };
  const key = `page-geometry-draft-v1:game:upload:preflight:${source.sourceChecksumSha256}:0`;
  localStorage.setItem(
    key,
    JSON.stringify({
      version: 2,
      scope: draftScope,
      draft: {
        quads: frames,
        pageCorners: [frames[0][0], frames[2][1], frames[8][2], frames[6][3]],
        flags: Array.from({ length: 9 }, () => ({
          partial: false,
          exclude: false,
          includeInPartialGridTraining: false,
          manualUnavailable: [],
        })),
        cornerPlacement: null,
        boardCornerPlacement: null,
        v12: {
          activeLayer: 'boardFrame',
          boardFrameQuads: frames,
          frameConfirmed: true,
          symbolGridQuads: symbols,
        },
      },
    }),
  );
  const props = {
    api: {
      listBrowserPageGeometryReviewSources: async () => ({
        data: {
          sources: [source],
          geometryManifestChecksumSha256: 'f'.repeat(64),
        },
      }),
      createBrowserPageGeometryOverride: async (_id, body) => {
        writes.push(body);
        return { data: { revision: 1 } };
      },
    },
    apiBaseUrl: 'http://127.0.0.1:8000',
    gameId: 'game',
    geometryEngineVariant: 'contrast_frame_grid_v1_2',
    uploadId: 'upload',
    preflightJobId: 'preflight',
    onSubmitSaved: async () => {
      throw Error('unexpected preflight');
    },
  };
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(React.createElement(PageGeometryCorrectionPanel, props)),
  );
  await imageLoaded();
  await selectFirst();
  assert.equal(
    [...document.querySelectorAll('input[name="v12-geometry-layer"]')][0]
      .checked,
    true,
  );
  await click(button('Zapisz i przejdź dalej'));

  assert.equal(writes.length, 1);
  assert.deepEqual(writes[0].boardFrameQuads, frames);
  assert.deepEqual(writes[0].symbolGridQuads, symbols);
  await act(async () => root.unmount());
});
