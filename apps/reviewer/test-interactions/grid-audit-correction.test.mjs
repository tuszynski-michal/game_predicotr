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
const strokes = [];
dom.window.HTMLCanvasElement.prototype.getContext = function () {
  const context = {};
  return new Proxy(context, {
    get: (_target, name) =>
      name === 'stroke'
        ? () => strokes.push(context.strokeStyle)
        : name in context
          ? context[name]
          : () => {},
    set: (_target, name, value) => {
      context[name] = value;
      return true;
    },
  });
};
dom.window.Element.prototype.getBoundingClientRect = function () {
  return { left: 0, top: 0, width: this.width, height: this.height };
};
URL.createObjectURL = () => 'blob:preview';
URL.revokeObjectURL = () => {};
const { createRoot } = await import('react-dom/client');
const { GridAuditCorrectionWorkspace } =
  await import('../src/features/operational-reviews/grid-audit-correction-workspace.tsx');
after(() => dom.window.close());

const CURRENT = [
  { x: 300, y: 250 },
  { x: 700, y: 250 },
  { x: 700, y: 500 },
  { x: 300, y: 500 },
];
const shifted = (dx) =>
  CURRENT.map((point) => ({ x: point.x + dx, y: point.y }));

/** One audited board: its review item, audited revision and network grid. */
function board(ordinal, overrides = {}) {
  return {
    itemId: `p0000${ordinal}`,
    ordinal,
    reviewItemId: `r${ordinal}`,
    revision: 1,
    auditRevision: 1,
    network: shifted(80),
    humanDecidedCells: ordinal === 0 ? 2 : 0,
    ...overrides,
  };
}

function reviewItem(entry) {
  return {
    approvedGeometryRevision: null,
    assetMode: 'virtual_source',
    boardConfidence: 1,
    gameId: 'g',
    geometry: { quad: CURRENT },
    geometryEngineName: 'manual_v1',
    geometryEngineVersion: 'v1',
    geometryRevision: entry.revision,
    gridColumns: 5,
    gridRows: 3,
    importJobId: `job-${entry.ordinal}`,
    pendingGeometryId: null,
    positionIndex: 2,
    reasonCodes: [],
    recognizedBoardId: `b${entry.ordinal}`,
    reportedCellIndices: [],
    resolutionRevision: 0,
    reviewItemId: entry.reviewItemId,
    sequenceNumber: 1000 + entry.ordinal,
    slotId: entry.reviewItemId,
    slotKind: 'current_review',
    sourceChecksumSha256: 'a'.repeat(64),
    sourceHeight: 900,
    sourceImageId: `src${entry.ordinal}`,
    sourceWidth: 1200,
    state: 'needs_validation',
  };
}

function queueItem(entry) {
  return {
    auditClass: 'column_shift',
    auditGeometryRevision: entry.auditRevision,
    currentGeometryRevision: entry.revision,
    humanDecidedCells: entry.humanDecidedCells,
    importJobId: `job-${entry.ordinal}`,
    importStatus: 'proposal',
    itemId: entry.itemId,
    level: 'S',
    ordinal: entry.ordinal,
    positionIndex: 2,
    recognizedBoardId: `b${entry.ordinal}`,
    sequenceNumber: 1000 + entry.ordinal,
    sourceImageId: `src${entry.ordinal}`,
    status: entry.revision === entry.auditRevision ? 'open' : 'corrected',
    verdictSource: 'operator',
  };
}

/**
 * A fake API whose queue is derived on every read from the boards' current
 * revisions — exactly like the backend (no stored queue state).
 */
function fakeApi(boards) {
  const calls = { list: [], proposal: [], preview: [], save: [] };
  const open = () =>
    boards.filter((entry) => entry.revision === entry.auditRevision);
  const api = {
    listGridAuditProposals: async (options) => {
      calls.list.push(options);
      const following = open().filter(
        (entry) =>
          options.afterOrdinal === undefined ||
          entry.ordinal > options.afterOrdinal,
      );
      const page = following.slice(0, options.limit ?? 1);
      return {
        data: {
          artifactSha256: 'c'.repeat(64),
          auditId: 'silent-grid-777-20261004',
          counts: {
            corrected: boards.length - open().length,
            noProposal: 0,
            open: open().length,
            openWithSymbolDecisions: open().filter(
              (entry) => entry.humanDecidedCells > 0,
            ).length,
            removed: 0,
            stale: 0,
            total: boards.length,
          },
          createdAt: '2026-10-04T09:00:00+00:00',
          gameId: 'g',
          items: page.map(queueItem),
          nextAfterOrdinal:
            following.length > page.length ? page.at(-1).ordinal : null,
        },
      };
    },
    getGridAuditProposal: async (gameId, itemId) => {
      calls.proposal.push({ gameId, itemId });
      const entry = boards.find((candidate) => candidate.itemId === itemId);
      const current = entry.revision === entry.auditRevision;
      return {
        data: {
          auditId: 'silent-grid-777-20261004',
          gameId,
          item: queueItem(entry),
          proposal: current
            ? {
                coordinateSpace: 'exif-normalized-rgb-pixels-v1',
                corners: entry.network,
                nodes: [],
                provenance: 'audit-network-proposal',
              }
            : null,
          reviewItem: current ? reviewItem(entry) : null,
        },
      };
    },
    imageGridReviewSourceAssetUrl: (id) => `http://127.0.0.1:8000/source/${id}`,
    previewImageGridReviewGeometry: async (id, scope, command) => {
      calls.preview.push({ command, id, scope });
      return { data: new Blob(['png'], { type: 'image/png' }) };
    },
    createImageGridReviewGeometryRevision: async (id, scope, command) => {
      calls.save.push({ command, id, scope });
      // The existing save path gives the board a newer revision.
      const entry = boards.find((candidate) => candidate.reviewItemId === id);
      entry.revision += 1;
      return { data: { created: true } };
    },
    getImageGridReviewCorrectionSymbols: async () => ({ data: { cells: [] } }),
    listSymbols: async () => ({ data: [] }),
  };
  return { api, calls };
}

const settle = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 220));
  });

async function render(api) {
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(GridAuditCorrectionWorkspace, { api, gameId: 'g' }),
    ),
  );
  await settle();
  await loadImage();
  return root;
}

async function loadImage() {
  if (images.length > 0) {
    await act(async () => images.at(-1).onload?.());
    await settle();
  }
}

function button(text) {
  return [...document.querySelectorAll('button')].find(
    (candidate) => candidate.textContent === text,
  );
}

test('the audit list opens each board with the network grid and saves through the existing path', async () => {
  const boards = [board(0), board(1), board(2, { network: shifted(-60) })];
  const { api, calls } = fakeApi(boards);
  const root = await render(api);

  assert.deepEqual(calls.list[0], { gameId: 'g', limit: 1 });
  assert.deepEqual(calls.proposal[0], { gameId: 'g', itemId: 'p00000' });
  let text = document.body.textContent;
  assert.match(text, /Poprawki z audytu siatek/);
  assert.match(
    text,
    /Do poprawy: 3 · poprawione: 0 z 3 · z decyzjami symboli: 1/,
  );
  assert.match(text, /Audyt siatekprzesunięcie o kolumnę · p00000/);
  assert.match(text, /Decyzje symboli2 pól/);
  assert.match(text, /Żółta siatka to propozycja sieci/);
  // The source is the board's checksum-bound source of the existing route.
  assert.equal(images.at(-1).url, 'http://127.0.0.1:8000/source/r0');
  // The first preview is the network proposal, not the saved grid.
  assert.deepEqual(calls.preview[0].command.corners, shifted(80));
  assert.equal(calls.preview[0].command.expectedGeometryRevision, 1);
  // The current grid is drawn as a thin red outline under the proposal.
  assert.ok(strokes.includes('#e5484d'));
  assert.ok(strokes.includes('#f4d35e'));

  await act(async () => button('Zapisz geometrię i dalej').click());
  await settle();
  assert.equal(calls.save.length, 1);
  assert.equal(calls.save[0].id, 'r0');
  assert.deepEqual(calls.save[0].scope, { gameId: 'g', importJobId: 'job-0' });
  assert.deepEqual(calls.save[0].command.corners, shifted(80));
  await loadImage();

  // The saved board left the derived queue; the next one opens.
  text = document.body.textContent;
  assert.match(text, /Siatka zapisana\. Plansza zniknęła z listy/);
  assert.match(text, /Do poprawy: 2 · poprawione: 1 z 3/);
  assert.equal(calls.proposal.at(-1).itemId, 'p00001');

  // Skip moves on in this session; the last board ends the list.
  await act(async () => button('Pomiń na razie →').click());
  await settle();
  await loadImage();
  assert.equal(calls.list.at(-1).afterOrdinal, 1);
  assert.equal(calls.proposal.at(-1).itemId, 'p00002');
  assert.deepEqual(calls.preview.at(-1).command.corners, shifted(-60));
  await act(async () => button('← Poprzednia').click());
  await settle();
  await loadImage();
  assert.equal(calls.proposal.at(-1).itemId, 'p00001');
  await act(async () => root.unmount());

  // A restart (new mount) derives the same queue: the saved board stays gone.
  const restarted = await render(api);
  assert.equal(calls.proposal.at(-1).itemId, 'p00001');
  assert.match(document.body.textContent, /Pozycja 2 z 3/);
  await act(async () => restarted.unmount());
});

test('a board corrected elsewhere is not offered and an empty list says so', async () => {
  const boards = [board(0, { revision: 2 })];
  const { api, calls } = fakeApi(boards);
  const root = await render(api);
  assert.equal(calls.proposal.length, 0);
  assert.equal(calls.preview.length, 0);
  assert.match(document.body.textContent, /Lista poprawek jest pusta/);
  assert.match(document.body.textContent, /poprawione: 1 z 1/);
  await act(async () => root.unmount());
});

test('a board that changed between the list and the proposal read shows no stale grid', async () => {
  const boards = [board(0)];
  const { api, calls } = fakeApi(boards);
  const original = api.getGridAuditProposal;
  api.getGridAuditProposal = async (gameId, itemId) => {
    boards[0].revision = 2;
    return original(gameId, itemId);
  };
  const root = await render(api);
  assert.equal(calls.preview.length, 0);
  assert.match(document.body.textContent, /zmieniła się po audycie/);
  await act(async () => root.unmount());
});
