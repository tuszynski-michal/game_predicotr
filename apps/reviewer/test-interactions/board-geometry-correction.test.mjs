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
dom.window.HTMLCanvasElement.prototype.getContext = function () {
  return new Proxy({}, { get: () => () => {} });
};
dom.window.Element.prototype.getBoundingClientRect = function () {
  return { left: 0, top: 0, width: this.width, height: this.height };
};
URL.createObjectURL = () => 'blob:preview';
URL.revokeObjectURL = () => {};
const { createRoot } = await import('react-dom/client');
const { BoardGeometryCorrectionWorkspace } =
  await import('../src/features/operational-reviews/board-geometry-correction-workspace.tsx');
after(() => dom.window.close());

const QUAD = [
  { x: 300, y: 250 },
  { x: 700, y: 250 },
  { x: 700, y: 500 },
  { x: 300, y: 500 },
];

function reportedBoard(overrides = {}) {
  return {
    slotId: 's1',
    slotKind: 'current_review',
    reviewItemId: 'r1',
    pendingGeometryId: null,
    gameId: 'g',
    importJobId: 'j',
    recognizedBoardId: 'b1',
    sourceImageId: 'src',
    positionIndex: 3,
    sequenceNumber: 1234,
    sourceChecksumSha256: 'a'.repeat(64),
    sourceWidth: 1200,
    sourceHeight: 900,
    geometryRevision: 2,
    approvedGeometryRevision: null,
    resolutionRevision: 0,
    gridRows: 3,
    gridColumns: 5,
    geometry: { quad: QUAD },
    assetMode: 'virtual_source',
    geometryEngineName: 'manual_v1',
    geometryEngineVersion: 'v1',
    boardConfidence: 1,
    reasonCodes: [],
    state: 'needs_correction',
    reportedCellIndices: [4, 1],
    ...overrides,
  };
}

function deferredSlot() {
  return {
    ...reportedBoard(),
    slotId: 'p1',
    slotKind: 'deferred_geometry',
    reviewItemId: null,
    pendingGeometryId: 'p1',
    recognizedBoardId: null,
    reportedCellIndices: [],
  };
}

const counts = (correction) => ({
  approved: 0,
  correction,
  needsCorrection: correction,
  needsValidation: 0,
  total: correction,
});

/** A fake client over an in-memory queue; `queue` is consulted per request. */
function fakeApi(state) {
  const calls = {
    list: [],
    preview: [],
    corrections: [],
    previewRevert: [],
    resolve: [],
    revert: [],
    save: [],
    symbols: [],
  };
  const api = {
    listImageGridReviews: async (options) => {
      calls.list.push(options);
      const start =
        options.afterCursor === undefined ? 0 : Number(options.afterCursor);
      const item = state.queue[start];
      return {
        data: {
          counts: counts(state.queue.length),
          gameId: 'g',
          importJobId: 'j',
          // Every response is a fresh object, as after JSON parsing.
          items: item === undefined ? [] : [structuredClone(item)],
          nextCursor: start + 1 < state.queue.length ? String(start + 1) : null,
          previousCursor: null,
          view: 'correction',
        },
      };
    },
    imageGridReviewSourceAssetUrl: (id) => `http://localhost/source/${id}`,
    previewImageGridReviewGeometry: async (id, scope, command) => {
      calls.preview.push({ command, id, scope });
      return (
        state.previewResult ?? {
          data: new Blob(['png'], { type: 'image/png' }),
        }
      );
    },
    createImageGridReviewGeometryRevision: async (id, scope, command) => {
      calls.save.push({ command, id, scope });
      if (state.failSaveOnce) {
        state.failSaveOnce = false;
        throw new Error('lost response');
      }
      state.queue = state.queue.filter((item) => item.reviewItemId !== id);
      return { data: { created: true } };
    },
    getPendingBoardCellGeometryCorrectionContext: async (id) => ({
      data: {
        item: {
          expectedGeometryRevision: 0,
          expectedReviewResolutionRevision: 0,
          gameId: 'g',
          id,
          importJobId: 'j',
          positionIndex: 5,
          processingManifestChecksumSha256: 'b'.repeat(64),
          reasonCode: 'incomplete_lattice',
          sequenceNumber: 77,
          sourceChecksumSha256: 'c'.repeat(64),
          sourceRelativePath: 'page-77.jpg',
        },
        sourceHeight: 900,
        sourceWidth: 1200,
        suggestedCorners: QUAD,
      },
    }),
    previewPendingBoardCellGeometryCorrection: async (id, scope, command) => {
      calls.preview.push({ command, id, scope });
      return { data: new Blob(['png'], { type: 'image/png' }) };
    },
    resolvePendingBoardCellGeometryManually: async (id, scope, command) => {
      calls.resolve.push({ command, id, scope });
      state.queue = state.queue.filter((item) => item.pendingGeometryId !== id);
      return {
        data: {
          created: true,
          geometryRevision: 1,
          pending: { id },
          reviewItemId: 'new-review',
        },
      };
    },
    listGeometryCorrections: async (options) => {
      calls.corrections.push(options);
      return { data: { items: structuredClone(state.corrections ?? []) } };
    },
    previewGeometryCorrectionRevert: async (id, scope) => {
      calls.previewRevert.push({ id, scope });
      return {
        data: {
          expectedGeometryRevision: 3,
          expectedResolutionRevision: 5,
          removedCellCount: 15,
          removesBoard: true,
          repointedBoardCount: 0,
          restoredCellDecisionCount: 0,
          restoredSourceEngineKind: null,
          restoredSourceStatus: null,
        },
      };
    },
    revertGeometryCorrection: async (id, scope, body) => {
      calls.revert.push({ body, id, scope });
      state.onRevert?.();
      return { data: { created: true } };
    },
    listPendingBoardCellGeometry: async () => assert.fail('not used'),
    // D-488: the catalogue and the read-only suggestions of the symbol picker.
    listSymbols: async () => ({ data: state.symbols ?? [] }),
    getImageGridReviewCorrectionSymbols: async (id, gameId) => {
      calls.symbols.push({ gameId, id });
      return { data: { cells: state.suggestions ?? [] } };
    },
    previewPendingBoardCellGeometrySymbols: async (id, scope, command) => {
      calls.symbols.push({ command, id, scope });
      return { data: { cells: state.suggestions ?? [] } };
    },
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
      React.createElement(BoardGeometryCorrectionWorkspace, {
        api,
        apiBaseUrl: 'http://localhost',
        gameId: 'g',
        importJobId: 'j',
      }),
    ),
  );
  await settle();
  if (images.length > 0) {
    await act(async () => images.at(-1).onload?.());
    await settle();
  }
  return root;
}

function button(text) {
  return [...document.querySelectorAll('button')].find(
    (candidate) => candidate.textContent === text,
  );
}

async function loadImageAndPreview() {
  await act(async () => images.at(-1).onload?.());
  await settle();
}

test('the 3001 screen corrects one reported board at a time and moves on after saving', async () => {
  const state = { queue: [reportedBoard()] };
  const { api, calls } = fakeApi(state);
  const root = await render(api);

  // D-462: one queue, one board, no validation of finished grids.
  assert.deepEqual(calls.list[0], {
    gameId: 'g',
    importJobId: 'j',
    limit: 1,
    view: 'correction',
  });
  const text = document.body.textContent;
  assert.match(text, /Korekta cięcia siatki/);
  assert.match(text, /Zgłoszone pola2, 5/);
  assert.match(text, /Do korekty: 1/);
  assert.doesNotMatch(text, /Do walidacji|Walidacja gotowych siatek|Zatwierdź/);
  assert.equal(document.querySelectorAll('canvas').length, 1);
  assert.equal(images.at(-1).url, 'http://localhost/source/r1');
  const reportedCrops = [...document.querySelectorAll('[role="img"]')]
    .map((crop) => crop.getAttribute('aria-label'))
    .filter((label) => label.includes('zgłoszona'));
  assert.deepEqual(reportedCrops, [
    'Crop 2 — zgłoszona zła siatka',
    'Crop 5 — zgłoszona zła siatka',
  ]);

  await act(async () => button('Zapisz geometrię i dalej').click());
  await settle();

  assert.equal(calls.save.length, 1);
  assert.equal(calls.save[0].id, 'r1');
  assert.deepEqual(calls.save[0].scope, { gameId: 'g', importJobId: 'j' });
  assert.equal(calls.save[0].command.expectedGeometryRevision, 2);
  assert.match(document.body.textContent, /Brak plansz do korekty/);
  assert.match(document.body.textContent, /Pola ze zmienionym wycinkiem/);
  await act(async () => root.unmount());
});

test('a deferred slot saves through its manual resolution and reuses the key after a lost response', async () => {
  const state = { queue: [deferredSlot()] };
  const { api, calls } = fakeApi(state);
  const root = await render(api);

  const text = document.body.textContent;
  assert.match(text, /Powód odroczenia/);
  assert.match(text, /Plikpage-77\.jpg/);
  assert.match(text, /Zapis utworzy zwykłą planszę/);
  assert.equal(calls.preview.length, 1);
  assert.equal(calls.preview[0].id, 'p1');

  const originalResolve = api.resolvePendingBoardCellGeometryManually;
  let lost = true;
  api.resolvePendingBoardCellGeometryManually = async (id, scope, command) => {
    if (lost) {
      lost = false;
      calls.resolve.push({ command, id, scope });
      throw new Error('lost response');
    }
    return originalResolve(id, scope, command);
  };
  await act(async () => button('Zapisz geometrię i dalej').click());
  await settle();
  assert.match(document.body.textContent, /Połączenie z lokalnym Admin API/);
  await act(async () => button('Zapisz geometrię i dalej').click());
  await settle();

  assert.equal(calls.resolve.length, 2);
  const [first, second] = calls.resolve.map((call) => call.command);
  assert.equal(first.idempotencyKey, second.idempotencyKey);
  assert.equal(first.expectedManifestChecksumSha256, 'b'.repeat(64));
  assert.equal(first.correctedBy, 'reviewer-operator');
  assert.match(document.body.textContent, /Nowa plansza trafiła/);
  assert.match(document.body.textContent, /Brak plansz do korekty/);
  await act(async () => root.unmount());
});

test('commands keep a qualified board qualified and leave a plain board unqualified', async () => {
  const cases = [
    {
      board: reportedBoard(),
      expected: null,
    },
    {
      board: reportedBoard({
        geometryQualification: {
          completenessStatus: 'complete',
          excludeFromGeometryTraining: false,
          exclusionReason: null,
          includeInPartialGridTraining: false,
          unavailableCellIndices: [],
          version: 'manual-geometry-qualification-v2',
        },
      }),
      expected: 'complete',
    },
    {
      board: reportedBoard({
        geometry: {
          quad: [
            { x: -100, y: 250 },
            { x: 700, y: 250 },
            { x: 700, y: 500 },
            { x: -100, y: 500 },
          ],
        },
        geometryQualification: {
          completenessStatus: 'pending_partial',
          excludeFromGeometryTraining: true,
          exclusionReason: 'missing_pixels',
          includeInPartialGridTraining: false,
          unavailableCellIndices: [0, 5, 10],
          version: 'manual-geometry-qualification-v2',
        },
      }),
      expected: 'pending_partial',
    },
  ];
  for (const { board, expected } of cases) {
    const { api, calls } = fakeApi({ queue: [board] });
    const root = await render(api);
    const checkbox = [
      ...document.querySelectorAll('input[type="checkbox"]'),
    ][0];
    assert.equal(
      calls.preview.length,
      1,
      `one preview for ${board.assetMode}/${expected}`,
    );
    const qualification = calls.preview[0].command.geometryQualification;
    assert.equal(qualification?.completenessStatus ?? null, expected);
    if (expected === 'pending_partial') {
      assert.equal(checkbox.checked, true, 'a partial board opens as partial');
    }
    await act(async () => root.unmount());
  }
});

test('navigation skips and returns, and a permanent failure never reloads the queue', async () => {
  const state = {
    queue: [
      reportedBoard(),
      reportedBoard({ reviewItemId: 'r2', sequenceNumber: 2000, slotId: 's2' }),
    ],
    previewResult: {
      error: { code: 'IMAGE_REVIEW_ASSET_NOT_FOUND', message: 'Brak pliku.' },
    },
  };
  const { api, calls } = fakeApi(state);
  const root = await render(api);

  // A missing asset stays on screen instead of reloading the first board.
  assert.equal(calls.list.length, 1);
  assert.match(document.body.textContent, /Brak pliku/);

  await act(async () => button('Pomiń na razie →').click());
  await settle();
  assert.equal(calls.list.at(-1).afterCursor, '1');
  assert.match(document.body.textContent, /Numer planszy2000/);
  await act(async () => button('← Poprzednia').click());
  await settle();
  assert.match(document.body.textContent, /Numer planszy1234/);
  await act(async () => root.unmount());
});

test('a queue conflict reloads once and never loops on the same board', async () => {
  const state = {
    queue: [reportedBoard()],
    previewResult: {
      error: {
        code: 'IMAGE_GRID_REVIEW_GEOMETRY_REVISION_CONFLICT',
        message: 'Zmieniona geometria.',
      },
    },
  };
  const { api, calls } = fakeApi(state);
  const root = await render(api);
  await loadImageAndPreview();
  await loadImageAndPreview();

  assert.equal(calls.list.length, 2, 'one reload for the conflict');
  assert.equal(calls.preview.length, 2, 'the reloaded board is previewed once');
  // The only board in the queue: there is nothing to skip to.
  assert.match(
    document.body.textContent,
    /nadal wskazuje tę planszę — wróć do niej później/,
  );
  await act(async () => root.unmount());
});

const SYMBOLS = [
  {
    code: 'star',
    displayOrder: 1,
    id: 'sym-star',
    mobileCode: 2,
    name: 'Star',
    namePl: null,
    status: 'active',
  },
  {
    code: 'seven',
    displayOrder: 0,
    id: 'sym-seven',
    mobileCode: 1,
    name: 'Seven',
    namePl: 'Siódemka',
    status: 'active',
  },
  {
    code: 'old',
    displayOrder: 2,
    id: 'sym-old',
    mobileCode: 3,
    name: 'Old',
    namePl: null,
    status: 'archived',
  },
];

/** A palette button; a labelled tile shows the same text as its symbol. */
function paletteButton(text) {
  return [
    ...document.querySelectorAll('[aria-label="Symbol wybranego pola"] button'),
  ].find(
    (candidate) =>
      (candidate.querySelector('span')?.textContent ??
        candidate.textContent) === text,
  );
}

/** A key press as the browser reports it to the page. */
async function pressKey(key, init = {}) {
  await act(async () => {
    document.body.dispatchEvent(
      new dom.window.KeyboardEvent('keydown', {
        bubbles: true,
        cancelable: true,
        key,
        ...init,
      }),
    );
  });
}

function cropButton(label) {
  return [...document.querySelectorAll('button')].find(
    (candidate) => candidate.getAttribute('aria-label') === label,
  );
}

test('the operator labels previewed cells and the save sends only those symbols (D-488)', async () => {
  const state = {
    queue: [deferredSlot()],
    suggestions: [
      { cellIndex: 0, origin: 'predicted', symbolId: 'sym-seven' },
      { cellIndex: 1, origin: 'predicted', symbolId: null },
    ],
    symbols: SYMBOLS,
  };
  const { api, calls } = fakeApi(state);
  const root = await render(api);

  // The suggestion is the model's prediction for exactly the previewed cut.
  assert.equal(calls.symbols.length, 1);
  assert.deepEqual(calls.symbols[0].command, calls.preview[0].command);
  assert.ok(cropButton('Crop 1 — podpowiedź: Siódemka'));
  // Active symbols only, in catalogue order, each with its key; nothing is
  // assignable yet.
  const picker = document.querySelector('[aria-label="Symbol wybranego pola"]');
  assert.deepEqual(
    [...picker.querySelectorAll('button')].map((entry) => entry.textContent),
    ['1Siódemka', '2Star', '? Nie wiem', 'Usuń wybór'],
  );
  assert.equal(paletteButton('Star').disabled, true);

  await act(async () => cropButton('Crop 3').click());
  await act(async () => paletteButton('Star').click());
  assert.ok(cropButton('Crop 3 — wybrany symbol: Star'));
  // A choice replaces the suggestion on its tile and can be withdrawn.
  await act(async () => cropButton('Crop 1 — podpowiedź: Siódemka').click());
  await act(async () => paletteButton('Star').click());
  assert.ok(cropButton('Crop 1 — wybrany symbol: Star'));
  await act(async () => paletteButton('Usuń wybór').click());
  assert.ok(cropButton('Crop 1 — podpowiedź: Siódemka'));

  await act(async () => button('Zapisz geometrię i dalej').click());
  await settle();

  assert.equal(calls.resolve.length, 1);
  assert.deepEqual(calls.resolve[0].command.cellSymbols, [
    { cellIndex: 2, symbolId: 'sym-star' },
  ]);
  await act(async () => root.unmount());
});

test('the symbol keys of the app pick the symbol of the selected cell', async () => {
  const state = {
    queue: [deferredSlot()],
    suggestions: [{ cellIndex: 0, origin: 'predicted', symbolId: 'sym-seven' }],
    symbols: SYMBOLS,
  };
  const { api, calls } = fakeApi(state);
  const root = await render(api);

  // No selected cell: the key changes nothing.
  await pressKey('2');
  assert.ok(cropButton('Crop 1 — podpowiedź: Siódemka'));

  await act(async () => cropButton('Crop 1 — podpowiedź: Siódemka').click());
  await pressKey('2');
  assert.ok(cropButton('Crop 1 — wybrany symbol: Star'));
  // The same keys as on the symbol verification screen: 1 is the first symbol.
  await pressKey('1');
  assert.ok(cropButton('Crop 1 — wybrany symbol: Siódemka'));
  // Modifier combinations and unassigned keys keep their meaning.
  await pressKey('2', { ctrlKey: true });
  await pressKey('x');
  assert.ok(cropButton('Crop 1 — wybrany symbol: Siódemka'));

  await act(async () => cropButton('Crop 3').click());
  await pressKey('2');
  await act(async () => button('Zapisz geometrię i dalej').click());
  await settle();

  assert.deepEqual(calls.resolve[0].command.cellSymbols, [
    { cellIndex: 0, symbolId: 'sym-seven' },
    { cellIndex: 2, symbolId: 'sym-star' },
  ]);
  await act(async () => root.unmount());
});

test('"Nie wiem" saves a covered cell as unknown instead of a guessed symbol', async () => {
  const state = {
    queue: [deferredSlot()],
    suggestions: [{ cellIndex: 0, origin: 'predicted', symbolId: 'sym-seven' }],
    symbols: SYMBOLS,
  };
  const { api, calls } = fakeApi(state);
  const root = await render(api);

  await act(async () => cropButton('Crop 1 — podpowiedź: Siódemka').click());
  await act(async () => paletteButton('? Nie wiem').click());
  // The unknown choice replaces the model hint on the tile.
  assert.ok(cropButton('Crop 1 — wybrany symbol: ?'));
  await act(async () => cropButton('Crop 3').click());
  await act(async () => paletteButton('Star').click());

  await act(async () => button('Zapisz geometrię i dalej').click());
  await settle();

  assert.deepEqual(calls.resolve[0].command.cellSymbols, [
    { cellIndex: 0, symbolId: null },
    { cellIndex: 2, symbolId: 'sym-star' },
  ]);
  await act(async () => root.unmount());
});

test('a save without a chosen symbol sends no symbols and stored ones are only hints', async () => {
  const state = {
    queue: [reportedBoard()],
    suggestions: [{ cellIndex: 4, origin: 'assigned', symbolId: 'sym-star' }],
    symbols: SYMBOLS,
  };
  const { api, calls } = fakeApi(state);
  const root = await render(api);

  assert.deepEqual(calls.symbols, [{ gameId: 'g', id: 'r1' }]);
  assert.ok(cropButton('Crop 5 — zgłoszona zła siatka — podpowiedź: Star'));

  await act(async () => button('Zapisz geometrię i dalej').click());
  await settle();

  assert.equal(calls.save.length, 1);
  assert.equal('cellSymbols' in calls.save[0].command, false);
  await act(async () => root.unmount());
});

const correctionRow = () => ({
  actor: 'reviewer-session:1',
  blockingReasonCode: null,
  blockingReasonMessage: null,
  boardGeometryRevisionId: 'rev1',
  createdAt: '2026-10-09T10:00:00Z',
  geometryRevision: 3,
  kind: 'pending_slot',
  pendingGeometryId: 'p1',
  positionIndex: 5,
  recognizedBoardId: 'b1',
  resolutionRevision: 5,
  revertable: true,
  reviewItemId: 'r1',
  sequenceNumber: 77,
  sourceImageId: 'src',
});

test('a saved correction re-fetches the recent corrections list', async () => {
  const state = { corrections: [correctionRow()], queue: [reportedBoard()] };
  const { api, calls } = fakeApi(state);
  const root = await render(api);
  assert.equal(calls.corrections.length, 1);
  assert.deepEqual(calls.corrections[0], { gameId: 'g', importJobId: 'j' });

  await act(async () => button('Zapisz geometrię i dalej').click());
  await settle();

  assert.equal(calls.save.length, 1);
  assert.equal(calls.corrections.length, 2);
  await act(async () => root.unmount());
});

test('a revert re-fetches the history and the queue and the restored slot appears', async () => {
  const state = { corrections: [correctionRow()], queue: [] };
  state.onRevert = () => {
    state.queue = [deferredSlot()];
    state.corrections = [];
  };
  const { api, calls } = fakeApi(state);
  const root = await render(api);
  assert.match(document.body.textContent, /Brak plansz do korekty/);
  const queueLoads = calls.list.length;

  await act(async () => button('Cofnij').click());
  await settle();
  // The editor shortcuts stay silent while the modal is open.
  await act(async () => button('Potwierdź cofnięcie').click());
  await settle();

  assert.equal(calls.previewRevert.length, 1);
  assert.equal(calls.revert.length, 1);
  assert.equal(calls.revert[0].id, 'rev1');
  assert.equal(calls.revert[0].body.expectedGeometryRevision, 3);
  assert.equal(calls.revert[0].body.expectedResolutionRevision, 5);
  assert.equal(calls.corrections.length, 2);
  assert.equal(calls.list.length, queueLoads + 1);
  assert.match(document.body.textContent, /Do korekty: 1/);
  assert.doesNotMatch(document.body.textContent, /Brak plansz do korekty/);
  await act(async () => root.unmount());
});
