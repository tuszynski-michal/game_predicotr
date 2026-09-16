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
dom.window.Element.prototype.getBoundingClientRect = () => ({
  left: 0,
  top: 0,
  width: 320,
  height: 320,
});
dom.window.Element.prototype.setPointerCapture = () => {};
const { createRoot } = await import('react-dom/client');
const { GeometryGuardResolutionPanel } =
  await import('../src/features/imports/geometry-guard-resolution-panel.tsx');
after(() => dom.window.close());
const boards = Array.from({ length: 18 }, (_, i) => {
  const index = i % 9,
    x = (index % 3) * 100 + 5,
    y = Math.floor(index / 3) * 100 + 5;
  const quad = [
    { x, y },
    { x: x + 90, y },
    { x: x + 90, y: y + 90 },
    { x, y: y + 90 },
  ];
  return {
    sourceChecksumSha256: i < 9 ? 'a'.repeat(64) : 'b'.repeat(64),
    sourceRelativePath: i < 9 ? 'seq_1-9.jpg' : 'seq_10-18.jpg',
    positionIndex: index,
    sequenceNumber: i + 1,
    requiresDecision: index === 0,
    reasonCodes: [],
    symbolGridQuad: quad,
    pageGeometry: quad,
    analysisQuad: quad,
  };
});
async function click(node) {
  assert.ok(node);
  await act(async () =>
    node.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })),
  );
}
function button(text) {
  return [...document.querySelectorAll('button')].find((node) =>
    node.textContent.includes(text),
  );
}
async function settle() {
  await act(async () => new Promise((resolve) => setTimeout(resolve, 10)));
  await act(async () => new Promise((resolve) => setTimeout(resolve, 10)));
}
async function imageLoaded() {
  const img = document.querySelector('img');
  assert.ok(img);
  Object.defineProperties(img, {
    naturalWidth: { configurable: true, value: 320 },
    naturalHeight: { configurable: true, value: 320 },
  });
  await act(async () =>
    img.dispatchEvent(new dom.window.Event('load', { bubbles: true })),
  );
}
test('guard navigation preserves two board decisions and masks across remount; explicit save clears only saved drafts', async () => {
  localStorage.clear();
  let decisions = [];
  const writes = [];
  const props = {
    api: {
      listImageGeometryGuardBoards: async () => ({
        data: {
          boards,
          targets: [boards[0], boards[9]],
          decisions,
          guardReportChecksumSha256: 'f'.repeat(64),
          unresolvedCount:
            2 - decisions.filter((d) => d.positionIndex === 0).length,
        },
      }),
      createImageGeometryGuardDecisions: async (_u, _g, payload) => {
        writes.push(payload);
        decisions = payload.decisions.map((d) => ({ ...d, revision: 1 }));
        return { data: { decisions } };
      },
    },
    apiBaseUrl: 'http://127.0.0.1:8000',
    gameId: 'g',
    guardJobId: 'j',
    uploadId: 'u',
    onManifestInvalidated: () => {},
    onPersistedContextLoaded: () => {},
    onManifestSealed: () => {},
  };
  let root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(React.createElement(GeometryGuardResolutionPanel, props)),
  );
  await settle();
  await imageLoaded();
  await click(document.querySelectorAll('input[type=radio]')[1]);
  await click(document.querySelector('.geometryGuardCellButtons button'));
  await click(document.querySelectorAll('polygon.geometryGuardBoard')[1]);
  await click(document.querySelector('input[type=checkbox]'));
  await act(async () =>
    root.render(
      React.createElement(GeometryGuardResolutionPanel, {
        ...props,
        guardJobId: 'other-job',
      }),
    ),
  );
  await settle();
  await imageLoaded();
  assert.equal(document.querySelectorAll('input[type=radio]')[0].checked, true);
  assert.equal(document.querySelector('input[type=checkbox]').checked, false);
  await act(async () =>
    root.render(React.createElement(GeometryGuardResolutionPanel, props)),
  );
  await settle();
  await imageLoaded();
  assert.equal(document.querySelectorAll('input[type=radio]')[1].checked, true);
  await click(button('Następne zdjęcie'));
  await settle();
  await click(button('Zapisz decyzję'));
  assert.equal(writes.length, 0);
  await act(async () => root.unmount());
  root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(React.createElement(GeometryGuardResolutionPanel, props)),
  );
  await settle();
  await imageLoaded();
  assert.equal(document.querySelectorAll('input[type=radio]')[1].checked, true);
  await click(button('Zapisz decyzję'));
  await settle();
  assert.equal(writes.length, 1);
  assert.equal(writes[0].decisions.length, 2);
  assert.deepEqual(writes[0].decisions[0].unavailableCellIndices, [0]);
  assert.equal(
    writes[0].decisions[0].geometryQualification.exclusionReason,
    'missing_pixels',
  );
  assert.equal(
    writes[0].decisions[1].geometryQualification.exclusionReason,
    'manual_exclusion',
  );
  assert.equal(writes[0].decisions[0].expectedDecisionRevision, 0);
  assert.equal(localStorage.length, 0);
  await click(document.querySelectorAll('input[type=radio]')[0]);
  assert.ok(button('Resetuj szkice'));
  await click(button('Resetuj szkice'));
  assert.equal(document.querySelectorAll('input[type=radio]')[1].checked, true);
  assert.equal(writes.length, 1);
  assert.equal(localStorage.length, 0);
  await act(async () => root.unmount());
});
