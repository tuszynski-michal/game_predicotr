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

test('v1.2 saves frames derived from one symbol grid and four margins', async () => {
  localStorage.clear();
  const writes = [];
  const frames = quads.map((quad) => [
    { x: quad[0].x - 2, y: quad[0].y - 2 },
    { x: quad[1].x + 2, y: quad[1].y - 2 },
    { x: quad[2].x + 2, y: quad[2].y + 2 },
    { x: quad[3].x - 2, y: quad[3].y + 2 },
  ]);
  const source = {
    ...sources[0],
    existingOverrideRevision: undefined,
    geometryOrigin: 'automatic',
    reviewReason: 'operator_inspection',
    existingBoardFrameQuads: null,
    existingSymbolGridQuads: null,
  };
  const scope = {
    gameId: 'game',
    uploadId: 'upload',
    preflightJobId: 'preflight',
    checksum: source.sourceChecksumSha256,
    revision: 0,
    width: 320,
    height: 320,
    count: 9,
  };
  localStorage.setItem(
    `page-geometry-draft-v1:game:upload:preflight:${source.sourceChecksumSha256}:0`,
    JSON.stringify({
      version: 2,
      scope,
      draft: {
        quads,
        pageCorners: [quads[0][0], quads[2][1], quads[8][2], quads[6][3]],
        flags: Array.from({ length: 9 }, () => ({
          partial: false,
          exclude: false,
          includeInPartialGridTraining: false,
          manualUnavailable: [],
        })),
        cornerPlacement: null,
        boardCornerPlacement: null,
        v12: {
          activeLayer: 'symbolGrid',
          boardFrameQuads: frames,
          frameConfirmed: false,
          symbolGridQuads: quads,
          frameOffsets: Array.from({ length: 9 }, () => ({
            top: (2 / 90) * 100,
            bottom: (2 / 90) * 100,
            left: (2 / 90) * 100,
            right: (2 / 90) * 100,
          })),
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
  assert.equal(button('Zapisz i przejdź dalej').disabled, false);
  await click(button('Zapisz i przejdź dalej'));

  assert.equal(writes.length, 1);
  assert.deepEqual(writes[0].boardFrameQuads, frames);
  assert.deepEqual(writes[0].symbolGridQuads, quads);
  assert.deepEqual(writes[0].finalQuads, quads);
  await act(async () => root.unmount());
});

test('v1.2 offset inputs accept a partial value and show its preview line', async () => {
  localStorage.clear();
  const source = {
    ...sources[0],
    existingOverrideRevision: undefined,
    geometryOrigin: 'automatic',
    reviewReason: 'operator_inspection',
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
    },
    apiBaseUrl: 'http://127.0.0.1:8000',
    gameId: 'game',
    geometryEngineVariant: 'contrast_frame_grid_v1_2',
    uploadId: 'upload',
    preflightJobId: 'preflight',
    onSubmitSaved: async () => {},
  };
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(React.createElement(PageGeometryCorrectionPanel, props)),
  );
  await imageLoaded();
  await selectFirst();
  const input = document.querySelector(
    'input[aria-label="Góra — odstęp od siatki (%)"]',
  );
  assert.ok(input);
  assert.equal(input.disabled, false);
  await act(async () => {
    const setValue = Object.getOwnPropertyDescriptor(
      dom.window.HTMLInputElement.prototype,
      'value',
    ).set;
    setValue.call(input, '10');
    input.dispatchEvent(new dom.window.Event('input', { bubbles: true }));
    input.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
  });
  assert.equal(input.value, '10');
  assert.ok(document.querySelector('polygon.pageGeometryBoardPlacement'));
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

test('v1.2 reload preserves a legacy two-layer draft without altering either quad', async () => {
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
    document.querySelectorAll('input[name="v12-geometry-layer"]').length,
    0,
  );
  await click(button('Zapisz i przejdź dalej'));

  assert.equal(writes.length, 1);
  assert.deepEqual(writes[0].boardFrameQuads, frames);
  assert.deepEqual(writes[0].symbolGridQuads, symbols);
  await act(async () => root.unmount());
});

function selectBoard(index) {
  const polygon = document.querySelectorAll('polygon.pageGeometryBoard')[index];
  assert.ok(polygon, `board ${index} polygon not rendered`);
  return act(async () =>
    polygon.dispatchEvent(
      new dom.window.MouseEvent('pointerdown', { bubbles: true }),
    ),
  );
}
function pointsText(quad) {
  return quad.map((p) => `${Math.round(p.x)},${Math.round(p.y)}`).join(' ');
}
const proposalQuads = quads.map((quad, i) =>
  i === 6 ? quad.map((p) => ({ x: p.x - 15, y: p.y })) : quad,
);
const proposalSource = {
  sourceChecksumSha256: 'e'.repeat(64),
  sourceRelativePath: 'seq_1-9.jpg',
  expectedBoardCount: 9,
  existingFinalQuads: null,
  existingBoardFrameQuads: null,
  existingSymbolGridQuads: null,
  existingOverrideRevision: null,
  existingSlotQualifications: null,
  savedSincePreflight: false,
  geometryOrigin: 'manual_template',
  reviewReason: 'review_required',
  rejectionReasonCode: null,
  registrationDiagnostics: null,
  automaticPageProposal: {
    origin: 'lateral_source_support',
    quads: proposalQuads,
    reviewSlots: [6],
  },
};

test('a manual_template page prefills the editor from the automatic proposal and marks the cropped board partial', async () => {
  localStorage.clear();
  const props = {
    api: {
      listBrowserPageGeometryReviewSources: async () => ({
        data: {
          sources: [proposalSource],
          geometryManifestChecksumSha256: 'f'.repeat(64),
        },
      }),
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
  const polygons = document.querySelectorAll('polygon.pageGeometryBoard');
  assert.equal(polygons.length, 9);
  assert.equal(polygons[0].getAttribute('points'), pointsText(quads[0]));
  assert.equal(
    polygons[6].getAttribute('points'),
    pointsText(proposalQuads[6]),
  );
  assert.match(
    document.body.textContent,
    /Wstępna geometria z automatycznej propozycji/,
  );
  assert.match(document.body.textContent, /Poza kadrem: 7/);
  assert.match(document.body.textContent, /Do sprawdzenia: 7/);
  await selectBoard(6);
  assert.equal(checkbox('Niepełna plansza').checked, true);
  await act(async () => root.unmount());
});

test('saving the unmodified proposal writes its quads and the pending_partial slot', async () => {
  localStorage.clear();
  const writes = [];
  const props = {
    api: {
      listBrowserPageGeometryReviewSources: async () => ({
        data: {
          sources: [proposalSource],
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
  await click(button('Zapisz i przejdź dalej'));
  assert.equal(writes.length, 1);
  assert.deepEqual(writes[0].finalQuads, proposalQuads);
  assert.equal(
    writes[0].slotQualifications[6].completenessStatus,
    'pending_partial',
  );
  assert.equal(
    writes[0].slotQualifications[6].excludeFromGeometryTraining,
    true,
  );
  assert.ok(writes[0].slotQualifications[6].unavailableCellIndices.length > 0);
  assert.equal(writes[0].slotQualifications[0].completenessStatus, 'complete');
  await act(async () => root.unmount());
});

test('an existing localStorage draft wins over the automatic proposal', async () => {
  localStorage.clear();
  const draftQuads = quads.map((quad) =>
    quad.map((p) => ({ x: p.x + 1, y: p.y + 1 })),
  );
  const scope = {
    gameId: 'game',
    uploadId: 'upload',
    preflightJobId: 'preflight',
    checksum: proposalSource.sourceChecksumSha256,
    revision: 0,
    width: 320,
    height: 320,
    count: 9,
  };
  localStorage.setItem(
    `page-geometry-draft-v1:game:upload:preflight:${proposalSource.sourceChecksumSha256}:0`,
    JSON.stringify({
      version: 1,
      scope,
      draft: {
        quads: draftQuads,
        pageCorners: [
          draftQuads[0][0],
          draftQuads[2][1],
          draftQuads[8][2],
          draftQuads[6][3],
        ],
        flags: Array.from({ length: 9 }, () => ({
          partial: false,
          exclude: false,
          includeInPartialGridTraining: false,
          manualUnavailable: [],
        })),
        cornerPlacement: null,
        boardCornerPlacement: null,
      },
    }),
  );
  const props = {
    api: {
      listBrowserPageGeometryReviewSources: async () => ({
        data: {
          sources: [proposalSource],
          geometryManifestChecksumSha256: 'f'.repeat(64),
        },
      }),
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
  const polygons = document.querySelectorAll('polygon.pageGeometryBoard');
  assert.equal(polygons[0].getAttribute('points'), pointsText(draftQuads[0]));
  await selectBoard(6);
  assert.equal(checkbox('Niepełna plansza').checked, false);
  await act(async () => root.unmount());
});

test('an automatic geometryOrigin with saved quads ignores any automaticPageProposal', async () => {
  localStorage.clear();
  const source = {
    ...proposalSource,
    geometryOrigin: 'automatic',
    reviewReason: 'operator_inspection',
    existingFinalQuads: quads,
  };
  const props = {
    api: {
      listBrowserPageGeometryReviewSources: async () => ({
        data: {
          sources: [source],
          geometryManifestChecksumSha256: 'f'.repeat(64),
        },
      }),
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
  const polygons = document.querySelectorAll('polygon.pageGeometryBoard');
  assert.equal(polygons[6].getAttribute('points'), pointsText(quads[6]));
  await selectBoard(6);
  assert.equal(checkbox('Niepełna plansza').checked, false);
  await act(async () => root.unmount());
});

test('Reset restores the automatic proposal geometry and its partial flag, not a blank template', async () => {
  localStorage.clear();
  const props = {
    api: {
      listBrowserPageGeometryReviewSources: async () => ({
        data: {
          sources: [proposalSource],
          geometryManifestChecksumSha256: 'f'.repeat(64),
        },
      }),
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
  await click(button('Reset'));
  const polygons = document.querySelectorAll('polygon.pageGeometryBoard');
  assert.equal(
    polygons[6].getAttribute('points'),
    pointsText(proposalQuads[6]),
  );
  await selectBoard(6);
  assert.equal(checkbox('Niepełna plansza').checked, true);
  await act(async () => root.unmount());
});

function svgOverlay() {
  const svg = document.querySelector(
    'svg[aria-label="Nakładka geometrii strony"]',
  );
  assert.ok(svg);
  return svg;
}
async function pointerDownOnBoard(index, clientX, clientY) {
  const polygon = document.querySelectorAll('polygon.pageGeometryBoard')[index];
  assert.ok(polygon, `board ${index} polygon not rendered`);
  await act(async () =>
    polygon.dispatchEvent(
      new dom.window.MouseEvent('pointerdown', {
        bubbles: true,
        clientX,
        clientY,
      }),
    ),
  );
}
async function pointerMoveOnSvg(clientX, clientY) {
  await act(async () =>
    svgOverlay().dispatchEvent(
      new dom.window.MouseEvent('pointermove', {
        bubbles: true,
        clientX,
        clientY,
      }),
    ),
  );
}
async function pointerUpOnSvg() {
  await act(async () =>
    svgOverlay().dispatchEvent(
      new dom.window.MouseEvent('pointerup', { bubbles: true }),
    ),
  );
}

async function loadFlatPanel() {
  const props = {
    api: {
      listBrowserPageGeometryReviewSources: async () => ({
        data: {
          sources: [sources[0]],
          geometryManifestChecksumSha256: 'f'.repeat(64),
        },
      }),
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
  return root;
}

test('a second pointerdown on an already-selected board drags the whole quad by a fixed vector', async () => {
  localStorage.clear();
  const root = await loadFlatPanel();
  await pointerDownOnBoard(0, 10, 10);
  await pointerDownOnBoard(0, 50, 50);
  await pointerMoveOnSvg(80, 60);
  await pointerUpOnSvg();
  const polygons = document.querySelectorAll('polygon.pageGeometryBoard');
  assert.equal(
    polygons[0].getAttribute('points'),
    pointsText(quads[0].map((p) => ({ x: p.x + 30, y: p.y + 10 }))),
  );
  assert.equal(polygons[1].getAttribute('points'), pointsText(quads[1]));
  await act(async () => root.unmount());
});

test('the first pointerdown on an unselected board only selects it, without moving anything', async () => {
  localStorage.clear();
  const root = await loadFlatPanel();
  await pointerDownOnBoard(3, 50, 50);
  await pointerMoveOnSvg(200, 200);
  await pointerUpOnSvg();
  const polygons = document.querySelectorAll('polygon.pageGeometryBoard');
  assert.equal(polygons[3].getAttribute('points'), pointsText(quads[3]));
  assert.match(polygons[3].getAttribute('class'), /pageGeometryBoardSelected/);
  await act(async () => root.unmount());
});

test('dragging a selected board corner still moves only that corner, not the whole board', async () => {
  localStorage.clear();
  const root = await loadFlatPanel();
  await selectBoard(0);
  const handle = document.querySelector('circle.pageGeometryBoardHandle');
  assert.ok(handle);
  await act(async () =>
    handle.dispatchEvent(
      new dom.window.MouseEvent('pointerdown', {
        bubbles: true,
        clientX: quads[0][0].x,
        clientY: quads[0][0].y,
      }),
    ),
  );
  await pointerMoveOnSvg(quads[0][0].x + 30, quads[0][0].y + 10);
  await pointerUpOnSvg();
  const polygons = document.querySelectorAll('polygon.pageGeometryBoard');
  assert.equal(
    polygons[0].getAttribute('points'),
    pointsText([
      { x: quads[0][0].x + 30, y: quads[0][0].y + 10 },
      quads[0][1],
      quads[0][2],
      quads[0][3],
    ]),
  );
  await act(async () => root.unmount());
});

test('moving a non-partial board without allowed outside-source room stops at the photo edge', async () => {
  localStorage.clear();
  const root = await loadFlatPanel();
  await pointerDownOnBoard(0, 10, 10);
  await pointerDownOnBoard(0, 50, 50);
  await pointerMoveOnSvg(50 - 1000, 50);
  await pointerUpOnSvg();
  const polygons = document.querySelectorAll('polygon.pageGeometryBoard');
  const minX = Math.min(...quads[0].map((p) => p.x));
  assert.equal(
    polygons[0].getAttribute('points'),
    pointsText(quads[0].map((p) => ({ x: p.x - minX, y: p.y }))),
  );
  await act(async () => root.unmount());
});
