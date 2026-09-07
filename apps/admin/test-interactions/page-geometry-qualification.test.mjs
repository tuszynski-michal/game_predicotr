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
  assert.equal(checks.length, 2);
  await click(checks[1]);
  assert.equal(
    document.querySelectorAll('input[type=checkbox]')[1].checked,
    true,
  );
  await click(button('Następna'));
  await click(button('Reset'));
  await click(button('Zapisz i przejdź dalej'));
  assert.equal(writes.length, 0);
  assert.equal(preflights.length, 0);
  await imageLoaded();
  await click(button('Poprzednia'));
  await imageLoaded();
  await selectFirst();
  assert.equal(
    document.querySelectorAll('input[type=checkbox]')[1].checked,
    true,
  );
  await act(async () => root.unmount());
  root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(React.createElement(PageGeometryCorrectionPanel, props)),
  );
  await imageLoaded();
  await selectFirst();
  assert.equal(
    document.querySelectorAll('input[type=checkbox]')[1].checked,
    true,
  );
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

test('partial checkbox allows signed corners and automatically protects cells; reset keeps server untouched', async () => {
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
  await click(document.querySelector('input[type=checkbox]'));
  assert.equal(
    document.querySelectorAll('input[type=checkbox]')[1].disabled,
    true,
  );
  const svg = document.querySelector('svg[aria-label]');
  const corner = svg.querySelector('circle');
  await act(async () =>
    corner.dispatchEvent(
      new dom.window.MouseEvent('pointerdown', { bubbles: true }),
    ),
  );
  await act(async () =>
    svg.dispatchEvent(
      new dom.window.MouseEvent('pointermove', {
        bubbles: true,
        clientX: 100,
        clientY: 108,
      }),
    ),
  );
  await act(async () =>
    svg.dispatchEvent(
      new dom.window.MouseEvent('pointerup', { bubbles: true }),
    ),
  );
  const autoFields = [...document.querySelectorAll('input[aria-label]')].filter(
    (node) => node.disabled && node.checked,
  );
  assert.ok(autoFields.length > 0);
  await click(button('Zapisz i przejdź dalej'));
  assert.equal(writes.length, 1);
  assert.equal(
    writes[0].slotQualifications[0].completenessStatus,
    'pending_partial',
  );
  assert.ok(writes[0].finalQuads[0][0].x < 0);
  await act(async () => root.unmount());
});
