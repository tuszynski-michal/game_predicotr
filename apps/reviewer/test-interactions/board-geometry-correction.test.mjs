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
  'localStorage',
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
const { LocalReviewerWorkspace } =
  await import('../src/features/access/local-reviewer-workspace.tsx');
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
    rejectBoard: [],
    rejectSlot: [],
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
    // TASK-0970: the rejection of a deferred slot and of a reported board.
    rejectPendingBoardCellGeometry: async (id, scope, command) => {
      calls.rejectSlot.push({ command, id, scope });
      const scripted = state.rejectResults?.shift();
      if (scripted === 'throw') throw new Error('lost response');
      if (scripted !== undefined) return scripted;
      state.queue = state.queue.filter((item) => item.pendingGeometryId !== id);
      return { data: { counts: {}, created: true, item: { id } } };
    },
    resolveOperationalImageReviewItem: async (id, scope, command) => {
      calls.rejectBoard.push({ command, id, scope });
      const scripted = state.rejectResults?.shift();
      if (scripted === 'throw') throw new Error('lost response');
      if (scripted !== undefined) return scripted;
      state.queue = state.queue.filter((item) => item.reviewItemId !== id);
      return { data: { created: true, item: { id, status: 'rejected' } } };
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
    // TASK-0963: the "Braki zdjęć" tab of `LocalReviewerWorkspace`; empty
    // here, its behaviour is covered by geometry-gaps-workspace.test.mjs.
    getImageGeometryCompleteness: async () => ({
      data: {
        computedAt: '2026-10-10T00:00:00Z',
        expectedBoardCount: 9,
        gameId: 'g',
        gate: {
          geometryException: 0,
          geometryIncomplete: 0,
          notEvaluated: 0,
          withheldBoards: 0,
          withheldReasonCode: 'SOURCE_IMAGE_GEOMETRY_INCOMPLETE',
        },
        images: {
          complete: 0,
          importFailed: 0,
          incomplete: 0,
          incompleteMissing: 0,
          incompletePartial: 0,
          incompleteUncertain: 0,
          noSourceGeometry: 0,
          superseded: 0,
          total: 0,
        },
        importJobId: null,
        positions: [],
        sourceStatuses: [],
      },
    }),
    listIncompleteGeometryImages: async () => ({
      data: {
        completenessStatus: null,
        gameId: 'g',
        gapsOnly: true,
        imageState: null,
        images: [],
        importJobId: null,
        nextCursor: null,
      },
    }),
    getImageGeometryCompletenessSourceAsset: async () =>
      assert.fail('no image to show'),
  };
  return { api, calls };
}

const settle = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 220));
  });

async function render(
  api,
  props = { importJobId: 'j' },
  component = BoardGeometryCorrectionWorkspace,
) {
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(component, {
        api,
        apiBaseUrl: 'http://localhost',
        gameId: 'g',
        ...props,
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
    counts: 'correction',
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

function typeInto(element, value) {
  const prototype =
    element instanceof dom.window.HTMLTextAreaElement
      ? dom.window.HTMLTextAreaElement.prototype
      : dom.window.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(prototype, 'value').set.call(element, value);
  element.dispatchEvent(new dom.window.Event('input', { bubbles: true }));
}

const radio = (reason) =>
  document.querySelector(
    `input[name="board-rejection-reason"][value="${reason}"]`,
  );
const confirmRejection = () => button('Potwierdź odrzucenie');

test('rejecting a deferred slot asks for a reason, sends one request and refreshes the queue and the list', async () => {
  const state = { corrections: [], queue: [deferredSlot()] };
  const { api, calls } = fakeApi(state);
  const root = await render(api);
  const queueLoads = calls.list.length;
  const listLoads = calls.corrections.length;

  await act(async () => button('Odrzuć planszę').click());
  const dialog = document.querySelector('[role="dialog"]');
  assert.ok(dialog);
  assert.match(dialog.textContent, /Plansza przycięta/);
  assert.match(dialog.textContent, /Rozmyta/);
  assert.match(dialog.textContent, /Inny/);
  assert.match(dialog.textContent, /czeka na zdjęcie zastępcze/);
  // No reason yet: nothing can be confirmed.
  assert.equal(confirmRejection().disabled, true);

  await act(async () => radio('cropped').click());
  assert.equal(confirmRejection().disabled, false);
  // A double click still sends exactly one request.
  await act(async () => {
    confirmRejection().click();
    confirmRejection().click();
  });
  await settle();

  assert.equal(calls.rejectSlot.length, 1);
  const [request] = calls.rejectSlot;
  assert.equal(request.id, 'p1');
  assert.deepEqual(request.scope, { gameId: 'g', importJobId: 'j' });
  assert.equal(request.command.reason, 'cropped');
  assert.equal(request.command.note, null);
  assert.equal(request.command.expectedGeometryRevision, 2);
  assert.match(request.command.idempotencyKey, /^[0-9a-f-]{36}$/);
  assert.equal(calls.rejectBoard.length, 0);
  assert.equal(document.querySelector('[role="dialog"]'), null);
  assert.equal(calls.list.length, queueLoads + 1);
  assert.equal(calls.corrections.length, listLoads + 1);
  assert.match(document.body.textContent, /Plansza została odrzucona/);
  assert.match(document.body.textContent, /Brak plansz do korekty/);
  await act(async () => root.unmount());
});

test('rejecting a reported board uses the resolution route with the reason "Inny" and its note', async () => {
  const state = { corrections: [], queue: [reportedBoard()] };
  const { api, calls } = fakeApi(state);
  const root = await render(api);

  await act(async () => button('Odrzuć planszę').click());
  assert.match(
    document.querySelector('[role="dialog"]').textContent,
    /zostają w historii/,
  );
  await act(async () => radio('other').click());
  // The reason "Inny" needs a description.
  assert.equal(confirmRejection().disabled, true);
  await act(async () =>
    typeInto(document.querySelector('textarea'), '  Ucięty górny rząd  '),
  );
  assert.equal(confirmRejection().disabled, false);
  await act(async () => confirmRejection().click());
  await settle();

  assert.equal(calls.rejectSlot.length, 0);
  assert.equal(calls.rejectBoard.length, 1);
  const [request] = calls.rejectBoard;
  assert.equal(request.id, 'r1');
  assert.deepEqual(request.scope, { gameId: 'g', importJobId: 'j' });
  assert.equal(request.command.action, 'rejected');
  assert.equal(request.command.rejectionReason, 'other: Ucięty górny rząd');
  assert.equal(request.command.expectedRevision, 0);
  assert.equal(request.command.geometryRevision, 2);
  assert.deepEqual(request.command.cells, []);
  assert.equal(request.command.sequenceNumber, null);
  assert.match(document.body.textContent, /Brak plansz do korekty/);
  await act(async () => root.unmount());
});

test('a lost rejection response keeps the dialog, the key and the draft for an identical retry', async () => {
  const state = {
    corrections: [],
    queue: [deferredSlot()],
    rejectResults: ['throw'],
  };
  const { api, calls } = fakeApi(state);
  const root = await render(api);

  await act(async () => button('Odrzuć planszę').click());
  await act(async () => radio('blurred').click());
  await act(async () => confirmRejection().click());
  await settle();

  assert.ok(document.querySelector('[role="dialog"]'));
  assert.match(document.body.textContent, /Wynik operacji jest nieznany/);
  // The draft is frozen, so the retry cannot differ from the first request.
  assert.equal(radio('cropped').matches(':disabled'), true);
  await act(async () => button('Spróbuj ponownie').click());
  await settle();

  assert.equal(calls.rejectSlot.length, 2);
  assert.deepEqual(calls.rejectSlot[1], calls.rejectSlot[0]);
  assert.equal(calls.rejectSlot[0].command.reason, 'blurred');
  assert.equal(document.querySelector('[role="dialog"]'), null);
  await act(async () => root.unmount());
});

test('a refusal such as the canonical owner closes the dialog, shows the reason and reloads the queue', async () => {
  const state = {
    corrections: [],
    queue: [reportedBoard()],
    rejectResults: [
      {
        error: {
          code: 'BOARD_REJECT_CANONICAL',
          message: 'Ta plansza jest kanonicznym właścicielem swojej sekwencji.',
        },
        response: { status: 409 },
      },
    ],
  };
  const { api, calls } = fakeApi(state);
  const root = await render(api);
  const queueLoads = calls.list.length;

  await act(async () => button('Odrzuć planszę').click());
  await act(async () => radio('cropped').click());
  await act(async () => confirmRejection().click());
  await settle();

  assert.equal(calls.rejectBoard.length, 1);
  assert.equal(document.querySelector('[role="dialog"]'), null);
  assert.match(document.body.textContent, /kanonicznym właścicielem/);
  assert.match(document.body.textContent, /BOARD_REJECT_CANONICAL/);
  assert.equal(calls.list.length, queueLoads + 1);
  // The board is still in the queue: nothing was rejected.
  assert.match(document.body.textContent, /Do korekty: 1/);
  await act(async () => root.unmount());
});

test('without an import the queue spans the game and asks only for the correction counter (TASK-0962)', async () => {
  const state = { queue: [reportedBoard()] };
  const { api, calls } = fakeApi(state);
  const root = await render(api, {});

  assert.deepEqual(calls.list[0], {
    counts: 'correction',
    gameId: 'g',
    limit: 1,
    view: 'correction',
  });
  assert.equal('importJobId' in calls.list[0], false);
  assert.doesNotMatch(document.body.textContent, /import/i);
  assert.match(document.body.textContent, /Do korekty: 1/);
  await act(async () => root.unmount());
});

test('without an import the recent corrections follow the import of the board on screen', async () => {
  const state = { corrections: [correctionRow()], queue: [reportedBoard()] };
  const { api, calls } = fakeApi(state);
  const root = await render(api, {});

  assert.equal(calls.corrections.length, 1);
  assert.deepEqual(calls.corrections[0], { gameId: 'g', importJobId: 'j' });
  assert.ok(button('Cofnij'));

  // The saved board leaves the queue; the last import keeps its history.
  state.queue = [];
  await act(async () => button('Zapisz geometrię i dalej').click());
  await settle();
  assert.match(document.body.textContent, /Brak plansz do korekty/);
  assert.equal(calls.corrections.length, 2);
  assert.deepEqual(calls.corrections[1], { gameId: 'g', importJobId: 'j' });
  assert.match(document.body.textContent, /Ostatnie korekty/);
  await act(async () => root.unmount());
});

test('Escape closes the rejection dialog without sending anything', async () => {
  const state = { corrections: [], queue: [deferredSlot()] };
  const { api, calls } = fakeApi(state);
  const root = await render(api);

  await act(async () => button('Odrzuć planszę').click());
  const dialog = document.querySelector('.operationalReviewConfirmDialog');
  await act(async () =>
    dialog.dispatchEvent(
      new dom.window.KeyboardEvent('keydown', { bubbles: true, key: 'Escape' }),
    ),
  );

  assert.equal(document.querySelector('[role="dialog"]'), null);
  assert.equal(calls.rejectSlot.length + calls.rejectBoard.length, 0);
  await act(async () => root.unmount());
});

test('the local Reviewer tabs keep the editor of "Do korekty" mounted (TASK-0962)', async () => {
  const state = { queue: [reportedBoard()] };
  const { api, calls } = fakeApi(state);
  const root = await render(api, {}, LocalReviewerWorkspace);

  const tab = (name) =>
    [...document.querySelectorAll('[role="tab"]')].find(
      (candidate) => candidate.textContent === name,
    );
  const panel = (id) => document.getElementById(id);
  assert.equal(tab('Do korekty').getAttribute('aria-selected'), 'true');
  assert.equal(panel('reviewer-tab-correction').hidden, false);
  assert.equal(panel('reviewer-tab-gaps').hidden, true);
  assert.match(document.body.textContent, /Numer planszy1234/);

  const canvas = document.querySelector('canvas');
  const listCalls = calls.list.length;
  const previewCalls = calls.preview.length;
  await act(async () => tab('Braki zdjęć').click());
  assert.equal(panel('reviewer-tab-correction').hidden, true);
  assert.equal(panel('reviewer-tab-gaps').hidden, false);
  // TASK-0963: the tab is the image-level gaps screen, empty for this game.
  assert.match(panel('reviewer-tab-gaps').textContent, /Braki zdjęć/);
  assert.match(
    panel('reviewer-tab-gaps').textContent,
    /Brak zdjęć w tym stanie/,
  );

  await act(async () => tab('Do korekty').click());
  await settle();
  assert.equal(panel('reviewer-tab-correction').hidden, false);
  // The same DOM node: the editor was neither unmounted nor reloaded.
  assert.equal(document.querySelector('canvas'), canvas);
  assert.equal(calls.list.length, listCalls);
  assert.equal(calls.preview.length, previewCalls);
  assert.match(document.body.textContent, /Numer planszy1234/);
  await act(async () => root.unmount());
});

test('symbol keys are inert while the "Braki zdjęć" tab is shown (TASK-0962)', async () => {
  const state = {
    queue: [deferredSlot()],
    suggestions: [{ cellIndex: 0, origin: 'predicted', symbolId: 'sym-seven' }],
    symbols: SYMBOLS,
  };
  const { api } = fakeApi(state);
  const root = await render(api, {}, LocalReviewerWorkspace);
  const tab = (name) =>
    [...document.querySelectorAll('[role="tab"]')].find(
      (candidate) => candidate.textContent === name,
    );

  await act(async () => cropButton('Crop 1 — podpowiedź: Siódemka').click());
  await act(async () => tab('Braki zdjęć').click());
  await pressKey('2');
  await act(async () => tab('Do korekty').click());
  assert.ok(cropButton('Crop 1 — podpowiedź: Siódemka'));
  await pressKey('2');
  assert.ok(cropButton('Crop 1 — wybrany symbol: Star'));
  await act(async () => root.unmount());
});

test('framing changes only the viewport, preserves preview and saved geometry, and keeps full mode when centered', async () => {
  const { api, calls } = fakeApi({ queue: [reportedBoard()] });
  const root = await render(api);
  try {
    const canvas = document.querySelector('canvas');
    const contextWidth = canvas.width;
    const preview = structuredClone(calls.preview.at(-1).command);
    const imageCount = images.length;
    const previewCount = calls.preview.length;
    await act(async () => button('Całe zdjęcie').click());
    assert.ok(canvas.width >= 1200 && canvas.height >= 900);
    assert.equal(button('Całe zdjęcie').getAttribute('aria-pressed'), 'true');
    await act(async () => button('Wycentruj widok na siatce').click());
    assert.ok(canvas.width >= 1200 && canvas.height >= 900);
    assert.equal(
      images.length,
      imageCount,
      'no geometry/source reload on framing',
    );
    assert.equal(
      calls.preview.length,
      previewCount,
      'no new preview or mutation',
    );
    await act(async () => button('Szerszy kadr').click());
    assert.equal(canvas.width, contextWidth);
    await act(async () => button('Zapisz geometrię i dalej').click());
    assert.deepEqual(calls.save[0].command.corners, preview.corners);
    assert.deepEqual(calls.save[0].command.latticeNodes, preview.latticeNodes);
  } finally {
    await act(async () => root.unmount());
  }
});

test('legacy editor consumers retain the 35 percent viewport without new controls', async () => {
  const { BoardGeometryCorrectionEditor } =
    await import('../src/features/operational-reviews/deferred-board-cell-geometry-editor.tsx');
  const { reportedBoardGeometryTarget } =
    await import('../src/features/operational-reviews/board-geometry-correction-target.ts');
  const { api } = fakeApi({ queue: [reportedBoard()] });
  const target = reportedBoardGeometryTarget({ api, item: reportedBoard() });
  const root = await render(api, {}, () =>
    React.createElement(BoardGeometryCorrectionEditor, {
      target,
      onSaved: async () => {},
      onConflict: async () => {},
    }),
  );
  try {
    assert.equal(button('Całe zdjęcie'), undefined);
    assert.equal(document.querySelector('canvas').width, 680);
    assert.equal(document.querySelector('canvas').height, 426);
  } finally {
    await act(async () => root.unmount());
  }
});

test('the main correction queue discovers proposals read-only and advances only after explicit human acceptance', async () => {
  const board = reportedBoard();
  const state = { queue: [board] };
  const { api, calls } = fakeApi(state);
  const proposalCalls = [];
  const nodes = Array.from({ length: 24 }, (_, index) => ({
    x: 300 + (index % 6) * 80,
    y: 250 + Math.floor(index / 6) * 80,
  }));
  const candidate = {
    originalGeometry: { corners: QUAD, latticeNodes: nodes },
    expectedGeometryRevision: 2,
    expectedResolutionRevision: 0,
    originalCandidateSha256: 'b'.repeat(64),
    modelSnapshot: { model: { version: 'new-model' } },
  };
  const proposal = {
    id: 'proposal',
    revision: 1,
    state: 'pending',
    applicable: true,
    reasons: [],
    candidate,
  };
  Object.assign(api, {
    getOperationalImageReviewItem: async () => ({
      data: { ...board, id: board.reviewItemId },
    }),
    listOperationalGridGeometryProposals: async () => {
      proposalCalls.push('read');
      return { data: { candidates: [], proposals: [proposal] } };
    },
    createOperationalGridGeometryProposal: async () =>
      assert.fail('no creation on mount'),
    previewOperationalImageReviewGeometry: async () =>
      assert.fail('no proposal edit on mount'),
    createOperationalImageReviewGeometryRevision: async () =>
      assert.fail('proposal uses its acceptance endpoint'),
    rejectOperationalGridGeometryProposal: async () =>
      assert.fail('not requested'),
    acceptOperationalGridGeometryProposal: async (
      id,
      proposalId,
      scope,
      body,
    ) => {
      proposalCalls.push(['accept', id, proposalId, scope, body]);
      state.queue = [];
      return {
        data: {
          current: { ...proposal, state: 'accepted', applicable: false },
        },
      };
    },
  });
  const root = await render(api);
  try {
    assert.deepEqual(proposalCalls, ['read']);
    assert.ok(button('Przyjmij propozycję'));
    assert.equal(state.queue.length, 1);
    assert.equal(calls.save.length, 0);
    await act(async () => button('Przyjmij propozycję').click());
    await settle();
    assert.equal(proposalCalls[1][1], 'r1');
    assert.equal(proposalCalls[1][4].mode, 'model');
    assert.match(document.body.textContent, /Brak plansz do korekty/);
    assert.match(document.body.textContent, /Przyjęto propozycję siatki/);
    assert.equal(calls.save.length, 0);
  } finally {
    await act(async () => root.unmount());
  }
});

test('full-photo mode survives corner drag release and qualification changes', async () => {
  const { api, calls } = fakeApi({ queue: [reportedBoard()] });
  dom.window.Element.prototype.setPointerCapture = () => {};
  dom.window.Element.prototype.hasPointerCapture = () => false;
  const root = await render(api);
  try {
    await act(async () => button('Całe zdjęcie').click());
    const canvas = document.querySelector('canvas');
    for (const [type, x] of [
      ['pointerdown', 300],
      ['pointermove', 330],
      ['pointerup', 340],
    ]) {
      const event = new dom.window.MouseEvent(type, {
        bubbles: true,
        clientX: x,
        clientY: 250,
        button: 0,
      });
      Object.defineProperty(event, 'pointerId', { value: 1 });
      await act(async () => canvas.dispatchEvent(event));
    }
    await settle();
    assert.equal(calls.preview.at(-1).command.corners[0].x, 340);
    assert.ok(canvas.width >= 1200 && canvas.height >= 900);
    const partial = document.querySelector('input[type="checkbox"]');
    assert.ok(partial);
    await act(async () => partial.click());
    assert.ok(canvas.width >= 1200 && canvas.height >= 900);
    assert.equal(button('Całe zdjęcie').getAttribute('aria-pressed'), 'true');
  } finally {
    await act(async () => root.unmount());
  }
});

function proposalQueueApi(state, api) {
  const rejected = new Set();
  const nodes = Array.from({ length: 24 }, (_, i) => ({
    x: 300 + (i % 6) * 80,
    y: 250 + Math.floor(i / 6) * 80,
  }));
  const proposal = (id) => ({
    id: `proposal-${id}`,
    revision: 1,
    state: rejected.has(id) ? 'rejected' : 'pending',
    applicable: !rejected.has(id),
    reasons: [],
    candidate: {
      originalGeometry: { corners: QUAD, latticeNodes: nodes },
      originalCandidateSha256: 'b'.repeat(64),
      expectedGeometryRevision: 2,
      expectedResolutionRevision: 0,
      modelSnapshot: { model: { version: 'test' } },
    },
  });
  const calls = [];
  Object.assign(api, {
    getOperationalImageReviewItem: async (id) => ({
      data: { ...state.queue.find((board) => board.reviewItemId === id), id },
    }),
    listOperationalGridGeometryProposals: async (id) => ({
      data: { candidates: [], proposals: [proposal(id)] },
    }),
    createOperationalGridGeometryProposal: async () =>
      assert.fail('not on discovery'),
    acceptOperationalGridGeometryProposal: async () =>
      assert.fail('not on rejection/read'),
    previewOperationalImageReviewGeometry: async () =>
      assert.fail('not editing'),
    createOperationalImageReviewGeometryRevision: async () =>
      assert.fail('not a geometry write'),
    rejectOperationalGridGeometryProposal: async (id) => {
      calls.push(id);
      rejected.add(id);
      return { data: { current: proposal(id) } };
    },
  });
  return calls;
}

test('rejecting a proposal after skipping keeps the current board, navigation history and confirmation', async () => {
  const state = {
    queue: [
      reportedBoard(),
      reportedBoard({ slotId: 's2', reviewItemId: 'r2', sequenceNumber: 1235 }),
    ],
  };
  const { api, calls } = fakeApi(state);
  const rejections = proposalQueueApi(state, api);
  const root = await render(api);
  try {
    await act(async () => button('Pomiń na razie →').click());
    await loadImageAndPreview();
    assert.equal(images.at(-1).url, 'http://localhost/source/r2');
    await act(async () => button('Odrzuć propozycję').click());
    await settle();
    assert.deepEqual(rejections, ['r2']);
    assert.equal(state.queue.length, 2);
    assert.equal(calls.list.at(-1).afterCursor, '1');
    assert.equal(button('← Poprzednia').disabled, false);
    assert.equal(images.at(-1).url, 'http://localhost/source/r2');
    assert.match(
      document.body.textContent,
      /Zgłoszenie siatki pozostaje otwarte/,
    );
    assert.equal(calls.save.length, 0);
  } finally {
    await act(async () => root.unmount());
  }
});

test('stale proposal identity offers a working read-only queue refresh even on its first board', async () => {
  const state = { queue: [reportedBoard()] };
  const { api, calls } = fakeApi(state);
  proposalQueueApi(state, api);
  api.getOperationalImageReviewItem = async (id) => {
    state.queue = [{ ...state.queue[0], geometryRevision: 3 }];
    return { data: { ...state.queue[0], id } };
  };
  const root = await render(api);
  try {
    assert.match(document.body.textContent, /aktualnej wersji planszy/);
    assert.ok(button('Odśwież kolejkę'));
    await act(async () => button('Odśwież kolejkę').click());
    await loadImageAndPreview();
    assert.doesNotMatch(document.body.textContent, /aktualnej wersji planszy/);
    assert.ok(button('Przyjmij propozycję'));
    assert.equal(calls.preview.at(-1).command.expectedGeometryRevision, 3);
    assert.equal(calls.save.length, 0);
  } finally {
    await act(async () => root.unmount());
  }
});

test('ordinary good geometry uses the same editor, GET-only all view and photo filter', async () => {
  const { api, calls } = fakeApi({
    queue: [
      reportedBoard({
        reportedCellIndices: [],
        state: 'needs_validation',
        approvedGeometryRevision: 3,
        geometryRevision: 3,
      }),
    ],
  });
  const root = await render(api, { importJobId: 'j', reviewAll: true });
  assert.equal(calls.list[0].view, 'all');
  assert.equal(calls.save.length, 0);
  assert.equal(calls.rejectBoard.length, 0);
  assert.match(document.body.textContent, /Geometria zdjęć/);
  assert.match(
    document.body.textContent,
    /Zapisana geometria nie potwierdza ludzkiej weryfikacji/,
  );
  assert.match(document.body.textContent, /zapisz ją ręcznie/);
  assert.doesNotMatch(document.body.textContent, /ma zapisane zatwierdzenie/);
  assert.match(document.body.textContent, /Symbole|symbole/);
  await act(async () =>
    button('Sprawdź wszystkie plansze tego zdjęcia').click(),
  );
  await settle();
  assert.equal(calls.list.at(-1).sourceImageId, 'src');
  assert.equal(calls.list.at(-1).view, 'all');
  assert.equal(calls.save.length, 0);
  await act(async () => root.unmount());
});

test('all-view save advances although the approved board remains in the collection', async () => {
  const first = reportedBoard();
  const second = reportedBoard({
    slotId: 's2',
    reviewItemId: 'r2',
    recognizedBoardId: 'b2',
    positionIndex: 4,
    sequenceNumber: 1235,
  });
  const state = { queue: [first, second] };
  const { api, calls } = fakeApi(state);
  api.createImageGridReviewGeometryRevision = async (id, scope, command) => {
    calls.save.push({ id, scope, command });
    state.queue[0] = {
      ...first,
      geometryRevision: 3,
      approvedGeometryRevision: 3,
      state: 'approved',
    };
    return { data: { created: true } };
  };
  const root = await render(api, { importJobId: 'j', reviewAll: true });
  try {
    await act(async () => button('Zapisz geometrię i dalej').click());
    await loadImageAndPreview();
    assert.equal(calls.list.at(-1).afterCursor, '1');
    assert.equal(calls.preview.at(-1).id, 'r2');
    assert.ok(calls.list.every((x) => x.view === 'all' && x.counts === 'none'));
    assert.equal(calls.save.length, 1);
  } finally {
    await act(async () => root.unmount());
  }
});

test('all-view last save ends the range and only an explicit restart returns to the first board', async () => {
  const state = { queue: [reportedBoard()] };
  const { api, calls } = fakeApi(state);
  api.createImageGridReviewGeometryRevision = async (id, scope, command) => {
    calls.save.push({ id, scope, command });
    return { data: { created: true } };
  };
  const root = await render(api, { importJobId: 'j', reviewAll: true });
  try {
    await act(async () => button('Zapisz geometrię i dalej').click());
    await settle();
    assert.match(document.body.textContent, /Koniec zakresu/);
    assert.equal(calls.list.length, 1);
    await act(async () => button('Od początku').click());
    await loadImageAndPreview();
    assert.equal(calls.list.length, 2);
    assert.equal(calls.list.at(-1).afterCursor, undefined);
    assert.equal(calls.preview.at(-1).id, 'r1');
  } finally {
    await act(async () => root.unmount());
  }
});

test('all-view materialized UUID is skipped but another source with the same sequence remains reviewable', async () => {
  const first = deferredSlot();
  const materialized = reportedBoard({
    slotId: 'materialized',
    reviewItemId: 'new-review',
  });
  const alternative = reportedBoard({
    slotId: 'alternative',
    reviewItemId: 'r2',
    sourceImageId: 'other-source',
    recognizedBoardId: 'b2',
  });
  const state = { queue: [first] };
  const { api, calls } = fakeApi(state);
  api.listImageGridReviews = async (options) => {
    calls.list.push(options);
    const [item, nextCursor] =
      options.afterCursor === 'after-pending'
        ? [materialized, 'after-materialized']
        : options.afterCursor === 'after-materialized'
          ? [alternative, null]
          : [first, 'after-pending'];
    return {
      data: {
        counts: counts(1),
        items: [structuredClone(item)],
        nextCursor,
        previousCursor: null,
        gameId: 'g',
        view: 'all',
      },
    };
  };
  api.resolvePendingBoardCellGeometryManually = async (id, scope, command) => {
    calls.resolve.push({ id, scope, command });
    state.queue = [materialized, alternative];
    return {
      data: {
        created: true,
        geometryRevision: 1,
        pending: { id },
        reviewItemId: 'new-review',
      },
    };
  };
  const root = await render(api, { importJobId: 'j', reviewAll: true });
  try {
    await act(async () => button('Zapisz geometrię i dalej').click());
    await loadImageAndPreview();
    assert.deepEqual(
      calls.list.slice(1).map((x) => x.afterCursor),
      ['after-pending', 'after-materialized'],
    );
    assert.equal(calls.preview.at(-1).id, 'r2');
    assert.equal(calls.resolve.length, 1);
    assert.ok(!calls.preview.some((x) => x.id === 'new-review'));
  } finally {
    await act(async () => root.unmount());
  }
});

test('all-view lost save response stays on the board until its idempotent retry succeeds', async () => {
  const state = {
    queue: [
      reportedBoard(),
      reportedBoard({
        slotId: 's2',
        reviewItemId: 'r2',
        recognizedBoardId: 'b2',
        positionIndex: 4,
        sequenceNumber: 1235,
      }),
    ],
  };
  const { api, calls } = fakeApi(state);
  api.createImageGridReviewGeometryRevision = async (id, scope, command) => {
    calls.save.push({ id, scope, command });
    if (calls.save.length === 1) {
      state.queue[0] = {
        ...state.queue[0],
        geometryRevision: 3,
        state: 'approved',
      };
      throw new Error('lost after commit');
    }
    return { data: { created: false } };
  };
  const root = await render(api, { importJobId: 'j', reviewAll: true });
  try {
    await act(async () => button('Zapisz geometrię i dalej').click());
    await settle();
    assert.equal(calls.list.length, 1);
    assert.ok(button('Zapisz geometrię i dalej'));
    await act(async () => button('Zapisz geometrię i dalej').click());
    await loadImageAndPreview();
    assert.match(calls.save[0].command.idempotencyKey, /^[0-9a-f-]{36}$/);
    assert.equal(
      calls.save[0].command.idempotencyKey,
      calls.save[1].command.idempotencyKey,
    );
    assert.equal(calls.preview.at(-1).id, 'r2');
  } finally {
    await act(async () => root.unmount());
  }
});

test('a successful save from an old import cannot reset or advance the new import', async () => {
  const state = { queue: [reportedBoard()] };
  const { api, calls } = fakeApi(state);
  let finishSave;
  api.createImageGridReviewGeometryRevision = (id, scope, command) => {
    calls.save.push({ id, scope, command });
    return new Promise((resolve) => {
      finishSave = resolve;
    });
  };
  const root = await render(api, { importJobId: 'j', reviewAll: true });
  try {
    await act(async () => button('Zapisz geometrię i dalej').click());
    assert.equal(calls.save.length, 1);
    state.queue = [
      reportedBoard({ importJobId: 'j2', reviewItemId: 'r2', slotId: 's2' }),
    ];
    await act(async () =>
      root.render(
        React.createElement(BoardGeometryCorrectionWorkspace, {
          api,
          apiBaseUrl: 'http://localhost',
          gameId: 'g',
          importJobId: 'j2',
          reviewAll: true,
        }),
      ),
    );
    await settle();
    await loadImageAndPreview();
    const readsBeforeOldSave = calls.list.length;
    await act(async () => finishSave({ data: { created: true } }));
    await settle();
    assert.equal(calls.list.length, readsBeforeOldSave);
    assert.equal(calls.list.at(-1).importJobId, 'j2');
    assert.equal(calls.preview.at(-1).id, 'r2');
    assert.doesNotMatch(document.body.textContent, /Koniec zakresu/);
  } finally {
    await act(async () => root.unmount());
  }
});

test('all-view saving in a photo filter advances within the same photo', async () => {
  const state = {
    queue: [
      reportedBoard(),
      reportedBoard({ reviewItemId: 'r2', slotId: 's2', positionIndex: 4 }),
    ],
  };
  const { api, calls } = fakeApi(state);
  api.createImageGridReviewGeometryRevision = async (id, scope, command) => {
    calls.save.push({ id, scope, command });
    return { data: { created: true } };
  };
  const root = await render(api, { importJobId: 'j', reviewAll: true });
  try {
    await act(async () =>
      button('Sprawdź wszystkie plansze tego zdjęcia').click(),
    );
    await settle();
    await loadImageAndPreview();
    await act(async () => button('Zapisz geometrię i dalej').click());
    await loadImageAndPreview();
    assert.equal(calls.list.at(-1).sourceImageId, 'src');
    assert.equal(calls.list.at(-1).importJobId, 'j');
    assert.equal(calls.list.at(-1).afterCursor, '1');
    assert.equal(calls.preview.at(-1).id, 'r2');
  } finally {
    await act(async () => root.unmount());
  }
});

test('all-view previous reloads the saved revision and restart works on the last board', async () => {
  const state = {
    queue: [
      reportedBoard(),
      reportedBoard({ slotId: 's2', reviewItemId: 'r2', positionIndex: 4 }),
    ],
  };
  const { api, calls } = fakeApi(state);
  api.createImageGridReviewGeometryRevision = async (id, scope, command) => {
    calls.save.push({ id, scope, command });
    state.queue = state.queue.map((board) =>
      board.reviewItemId === id
        ? { ...board, geometryRevision: 3, approvedGeometryRevision: 3 }
        : board,
    );
    return { data: { created: true } };
  };
  const root = await render(api, { importJobId: 'j', reviewAll: true });
  try {
    await act(async () => button('Zapisz geometrię i dalej').click());
    await loadImageAndPreview();
    assert.equal(button('← Poprzednia').disabled, false);
    assert.equal(button('Od początku').disabled, false);
    await act(async () => button('← Poprzednia').click());
    await loadImageAndPreview();
    assert.equal(calls.preview.at(-1).id, 'r1');
    assert.equal(calls.preview.at(-1).command.expectedGeometryRevision, 3);
    assert.equal(calls.list.at(-1).afterCursor, undefined);
    await act(async () => button('Pomiń na razie →').click());
    await loadImageAndPreview();
    await act(async () => button('Zapisz geometrię i dalej').click());
    await settle();
    assert.match(document.body.textContent, /Koniec zakresu/);
    await act(async () => button('← Poprzednia').click());
    await loadImageAndPreview();
    assert.equal(calls.preview.at(-1).id, 'r2');
    assert.equal(calls.preview.at(-1).command.expectedGeometryRevision, 3);
    await act(async () => button('Od początku').click());
    await loadImageAndPreview();
    assert.equal(calls.preview.at(-1).id, 'r1');
  } finally {
    await act(async () => root.unmount());
  }
});

test('all-view retry after a successful save repeats the failed forward read, not the first page', async () => {
  const first = deferredSlot();
  const materialized = reportedBoard({
    slotId: 'new-review',
    reviewItemId: 'new-review',
  });
  const next = reportedBoard({
    slotId: 's2',
    reviewItemId: 'r2',
    positionIndex: 4,
  });
  const state = { queue: [first] };
  const { api, calls } = fakeApi(state);
  let failed = false;
  api.listImageGridReviews = async (options) => {
    calls.list.push(options);
    if (options.afterCursor === 'after-materialized' && !failed) {
      failed = true;
      throw new Error('next page response lost');
    }
    const [board, nextCursor] =
      options.afterCursor === undefined
        ? [first, 'after-pending']
        : options.afterCursor === 'after-pending'
          ? [materialized, 'after-materialized']
          : [next, null];
    return {
      data: {
        counts: counts(2),
        gameId: 'g',
        items: [structuredClone(board)],
        nextCursor,
        previousCursor: null,
        view: 'all',
      },
    };
  };
  api.resolvePendingBoardCellGeometryManually = async (id, scope, command) => {
    calls.resolve.push({ id, scope, command });
    return {
      data: {
        created: true,
        geometryRevision: 1,
        reviewItemId: 'new-review',
        pending: { id },
      },
    };
  };
  const root = await render(api, { importJobId: 'j', reviewAll: true });
  try {
    await act(async () => button('Zapisz geometrię i dalej').click());
    await settle();
    assert.ok(button('Spróbuj ponownie'));
    await act(async () => button('Spróbuj ponownie').click());
    await loadImageAndPreview();
    assert.deepEqual(
      calls.list.map((x) => x.afterCursor),
      [
        undefined,
        'after-pending',
        'after-materialized',
        'after-pending',
        'after-materialized',
      ],
    );
    assert.equal(calls.preview.at(-1).id, 'r2');
    assert.equal(calls.resolve.length, 1);
    assert.equal(button('← Poprzednia').disabled, false);
  } finally {
    await act(async () => root.unmount());
  }
});

test('rejecting and refreshing proposals after saving keeps the current all-view cursor', async () => {
  const state = {
    queue: [
      reportedBoard(),
      reportedBoard({ slotId: 's2', reviewItemId: 'r2', positionIndex: 4 }),
    ],
  };
  const { api, calls } = fakeApi(state);
  proposalQueueApi(state, api);
  api.createImageGridReviewGeometryRevision = async () => ({
    data: { created: true },
  });
  const root = await render(api, { importJobId: 'j', reviewAll: true });
  try {
    await act(async () => button('Zapisz geometrię i dalej').click());
    await loadImageAndPreview();
    await act(async () => button('Odrzuć propozycję').click());
    await loadImageAndPreview();
    assert.equal(calls.list.at(-1).afterCursor, '1');
    assert.equal(calls.preview.at(-1).id, 'r2');
    state.queue[1] = { ...state.queue[1], geometryRevision: 3 };
    // The stale identity offers the proposal panel's read-only refresh.
    await act(async () => button('Odśwież propozycje').click());
    await settle();
    assert.ok(button('Odśwież kolejkę'));
    await act(async () => button('Odśwież kolejkę').click());
    await loadImageAndPreview();
    assert.equal(calls.list.at(-1).afterCursor, '1');
    assert.equal(calls.preview.at(-1).command.expectedGeometryRevision, 3);
  } finally {
    await act(async () => root.unmount());
  }
});

test('accepting a proposal in all-view advances although the saved board remains listed', async () => {
  const state = {
    queue: [
      reportedBoard(),
      reportedBoard({ slotId: 's2', reviewItemId: 'r2', positionIndex: 4 }),
    ],
  };
  const { api, calls } = fakeApi(state);
  proposalQueueApi(state, api);
  let accepted = 0;
  api.acceptOperationalGridGeometryProposal = async () => {
    accepted += 1;
    return { data: { current: { state: 'accepted', applicable: false } } };
  };
  const root = await render(api, { importJobId: 'j', reviewAll: true });
  try {
    await act(async () => button('Przyjmij propozycję').click());
    await loadImageAndPreview();
    assert.equal(accepted, 1);
    assert.equal(calls.list.at(-1).afterCursor, '1');
    assert.equal(calls.preview.at(-1).id, 'r2');
    assert.match(document.body.textContent, /Przyjęto propozycję siatki/);
  } finally {
    await act(async () => root.unmount());
  }
});

test('the end of a photo range offers a direct return to all photos', async () => {
  const state = { queue: [reportedBoard()] };
  const { api, calls } = fakeApi(state);
  api.createImageGridReviewGeometryRevision = async () => ({
    data: { created: true },
  });
  const root = await render(api, { importJobId: 'j', reviewAll: true });
  try {
    await act(async () =>
      button('Sprawdź wszystkie plansze tego zdjęcia').click(),
    );
    await settle();
    await loadImageAndPreview();
    await act(async () => button('Zapisz geometrię i dalej').click());
    await settle();
    assert.match(document.body.textContent, /Koniec zakresu/);
    await act(async () => button('Wszystkie zdjęcia').click());
    await settle();
    await loadImageAndPreview();
    assert.equal(calls.list.at(-1).sourceImageId, undefined);
    assert.equal(calls.preview.at(-1).id, 'r1');
  } finally {
    await act(async () => root.unmount());
  }
});
