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
const sourceImages = [];
dom.window.Image = class {
  naturalWidth = 1200;
  naturalHeight = 900;
  set src(value) {
    this.url = value;
    sourceImages.push(this);
  }
};
dom.window.HTMLCanvasElement.prototype.getContext = function () {
  return new Proxy({}, { get: () => () => {} });
};
dom.window.Element.prototype.getBoundingClientRect = function () {
  return { left: 0, top: 0, width: this.width, height: this.height };
};
const blobUrls = { created: [], revoked: [] };
let blobCounter = 0;
URL.createObjectURL = () => {
  const url = `blob:photo-${++blobCounter}`;
  blobUrls.created.push(url);
  return url;
};
URL.revokeObjectURL = (url) => {
  blobUrls.revoked.push(url);
};
const { createRoot } = await import('react-dom/client');
const { GeometryGapsWorkspace } =
  await import('../src/features/operational-reviews/geometry-gaps-workspace.tsx');
after(() => dom.window.close());

const QUAD = [
  { x: 300, y: 250 },
  { x: 700, y: 250 },
  { x: 700, y: 500 },
  { x: 300, y: 500 },
];

function gapPosition(overrides = {}) {
  return {
    humanApproved: false,
    positionIndex: 0,
    quad: QUAD,
    reasonCode: null,
    recognizedBoardId: null,
    sequenceNumber: 1000,
    state: 'missing',
    ...overrides,
  };
}

function gapImage(id, overrides = {}) {
  return {
    completenessEvaluatedAt: null,
    completenessStatus: 'geometry_incomplete',
    exceptionAt: null,
    exceptionBy: null,
    exceptionReason: null,
    expectedBoardCount: 9,
    gateReasonCode: null,
    imageState: 'incomplete_missing',
    importErrorCode: null,
    importJobId: 'j',
    orientedHeight: 900,
    orientedWidth: 1200,
    positions: [
      gapPosition({ positionIndex: 0, sequenceNumber: 1000 }),
      gapPosition({
        positionIndex: 1,
        quad: null,
        sequenceNumber: 1001,
        state: 'missing',
      }),
    ],
    relativePath: `page-${id}.jpg`,
    sequenceRangeEnd: 1008,
    sequenceRangeStart: 1000,
    sourceImageId: id,
    sourceStatus: 'accepted',
    ...overrides,
  };
}

function report(overrides = {}) {
  return {
    computedAt: '2026-10-10T00:00:00Z',
    expectedBoardCount: 9,
    gameId: 'g',
    gate: {
      geometryException: 0,
      geometryIncomplete: 4,
      notEvaluated: 0,
      withheldBoards: 0,
      withheldReasonCode: 'SOURCE_IMAGE_GEOMETRY_INCOMPLETE',
    },
    images: {
      complete: 5,
      importFailed: 3,
      incomplete: 4,
      incompleteMissing: 1,
      incompletePartial: 0,
      incompleteUncertain: 0,
      noSourceGeometry: 0,
      superseded: 0,
      total: 9,
      ...overrides,
    },
    importJobId: null,
    positions: [],
    sourceStatuses: [],
  };
}

function deferredRow(sourceImageId, positionIndex) {
  return {
    slotId: `p-${sourceImageId}-${positionIndex}`,
    slotKind: 'deferred_geometry',
    reviewItemId: null,
    pendingGeometryId: `p-${sourceImageId}-${positionIndex}`,
    gameId: 'g',
    importJobId: 'j',
    recognizedBoardId: null,
    sourceImageId,
    positionIndex,
    sequenceNumber: 1000 + positionIndex,
    sourceChecksumSha256: 'a'.repeat(64),
    sourceWidth: 1200,
    sourceHeight: 900,
    geometryRevision: 0,
    approvedGeometryRevision: null,
    resolutionRevision: 0,
    gridRows: 3,
    gridColumns: 5,
    geometry: {},
    assetMode: 'virtual_source',
    geometryEngineName: null,
    geometryEngineVersion: null,
    boardConfidence: 0,
    reasonCodes: [],
    state: 'needs_correction',
    reportedCellIndices: [],
  };
}

function partialBoardRow(sourceImageId, positionIndex) {
  return {
    ...deferredRow(sourceImageId, positionIndex),
    slotId: `s-${sourceImageId}-${positionIndex}`,
    slotKind: 'current_review',
    reviewItemId: `r-${sourceImageId}-${positionIndex}`,
    pendingGeometryId: null,
    recognizedBoardId: `b-${sourceImageId}-${positionIndex}`,
    geometryRevision: 2,
    geometry: {
      quad: [
        { x: -100, y: 250 },
        { x: 700, y: 250 },
        { x: 700, y: 500 },
        { x: -100, y: 500 },
      ],
    },
    geometryEngineName: 'manual_v1',
    geometryEngineVersion: 'v1',
    boardConfidence: 1,
    geometryQualification: {
      completenessStatus: 'pending_partial',
      excludeFromGeometryTraining: true,
      exclusionReason: 'missing_pixels',
      includeInPartialGridTraining: false,
      unavailableCellIndices: [0, 5, 10],
      version: 'manual-geometry-qualification-v2',
    },
  };
}

/**
 * A fake client over in-memory pages. `state.pages` maps a cursor (`null`
 * for the first page) to `{ images, nextCursor }` for the `all` filter;
 * `state.byState` holds the pages of a single-state filter.
 */
function fakeApi(state) {
  const calls = {
    assets: [],
    list: [],
    preview: [],
    report: 0,
    resolve: [],
    rows: [],
    save: [],
  };
  const api = {
    getImageGeometryCompleteness: async (options) => {
      calls.report += 1;
      assert.deepEqual(options, { gameId: 'g' });
      return { data: state.report ?? report() };
    },
    listIncompleteGeometryImages: async (options) => {
      calls.list.push(options);
      // `state.gate[imageState]` holds a response until the test releases it.
      const gate = state.gate?.[options.imageState ?? 'all'];
      if (gate !== undefined) await gate;
      // `state.failCursors` fails each listed cursor once ('first' = no cursor).
      const cursorKey = options.afterCursor ?? 'first';
      if (state.failCursors?.has(cursorKey)) {
        state.failCursors.delete(cursorKey);
        if (state.failWithError) {
          return {
            error: {
              code: 'IMAGE_GEOMETRY_LIST_FAILED',
              message: 'Lista padła.',
            },
          };
        }
        throw new Error('lost response');
      }
      const pages =
        options.imageState === undefined
          ? state.pages
          : (state.byState?.[options.imageState] ?? {});
      const page = pages[options.afterCursor ?? 'first'] ?? {
        images: [],
        nextCursor: null,
      };
      return {
        data: {
          completenessStatus: null,
          gameId: 'g',
          gapsOnly: options.gapsOnly === true,
          imageState: options.imageState ?? null,
          images: structuredClone(page.images),
          importJobId: null,
          nextCursor: page.nextCursor,
        },
      };
    },
    getImageGeometryCompletenessSourceAsset: async (gameId, sourceImageId) => {
      calls.assets.push({ gameId, sourceImageId });
      if (state.assetMissing) {
        return { error: { code: 'IMAGE_SOURCE_ASSET_NOT_FOUND' } };
      }
      return { data: new Blob(['jpg'], { type: 'image/jpeg' }) };
    },
    listImageGridReviews: async (options) => {
      calls.rows.push(options);
      if (state.rowsError) {
        return {
          error: {
            code: 'IMAGE_GRID_REVIEW_LIST_FAILED',
            message: 'Wiersze padły.',
          },
        };
      }
      return {
        data: {
          counts: { approved: 0, correction: 0, total: 0 },
          gameId: 'g',
          importJobId: null,
          items: structuredClone(state.rows?.[options.sourceImageId] ?? []),
          nextCursor: null,
          previousCursor: null,
          view: 'all',
        },
      };
    },
    listSymbols: async () => ({ data: [] }),
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
      return { data: { created: true } };
    },
    getImageGridReviewCorrectionSymbols: async () => ({ data: { cells: [] } }),
    getPendingBoardCellGeometryCorrectionContext: async (id) => ({
      data: {
        item: {
          expectedGeometryRevision: 0,
          expectedReviewResolutionRevision: 0,
          gameId: 'g',
          id,
          importJobId: 'j',
          positionIndex: 0,
          processingManifestChecksumSha256: 'b'.repeat(64),
          reasonCode: 'incomplete_lattice',
          sequenceNumber: 1000,
          sourceChecksumSha256: 'c'.repeat(64),
          sourceRelativePath: 'page-img-1.jpg',
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
    previewPendingBoardCellGeometrySymbols: async () => ({
      data: { cells: [] },
    }),
    resolvePendingBoardCellGeometryManually: async (id, scope, command) => {
      calls.resolve.push({ command, id, scope });
      // The slot is materialised: the position has a board now.
      state.pages = state.afterResolve ?? state.pages;
      return {
        data: {
          created: true,
          geometryRevision: 1,
          pending: { id },
          reviewItemId: 'new-review',
        },
      };
    },
    listPendingBoardCellGeometry: async () => assert.fail('not used'),
  };
  return { api, calls };
}

const settle = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 220));
  });

async function render(api, props = {}) {
  blobCounter = 0;
  blobUrls.created.length = 0;
  blobUrls.revoked.length = 0;
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(GeometryGapsWorkspace, {
        api,
        apiBaseUrl: 'http://localhost',
        gameId: 'g',
        ...props,
      }),
    ),
  );
  await settle();
  return root;
}

function button(text) {
  return [...document.querySelectorAll('button')].find(
    (candidate) => candidate.textContent === text,
  );
}

function filterButton(prefix) {
  return [
    ...document.querySelectorAll('[aria-label="Filtr stanu zdjęcia"] button'),
  ].find((candidate) => candidate.textContent.startsWith(prefix));
}

function positionItems() {
  return [...document.querySelectorAll('.geometryGapsPositions li')];
}

async function loadEditorSource() {
  await act(async () => sourceImages.at(-1).onload?.());
  await settle();
}

test('the tab shows one image at a time with its photo loaded without a click, and navigates', async () => {
  const state = {
    pages: {
      first: {
        images: [gapImage('img-1'), gapImage('img-2'), gapImage('img-3')],
        nextCursor: null,
      },
    },
  };
  const { api, calls } = fakeApi(state);
  const root = await render(api);

  assert.equal(calls.report, 1);
  assert.deepEqual(calls.list, [{ gameId: 'g', gapsOnly: true, limit: 25 }]);
  // Counters on the filter buttons, "all" is the default.
  assert.equal(
    filterButton('Wszystkie braki (4)').getAttribute('aria-pressed'),
    'true',
  );
  assert.ok(filterButton('Brakuje plansz (1)'));
  assert.ok(filterButton('Import nieudany (3)'));

  const text = document.body.textContent;
  assert.match(text, /page-img-1\.jpg/);
  assert.match(text, /Brakuje plansz/);
  assert.match(text, /numery 1000–1008 · oczekiwane plansze: 9/);
  assert.match(text, /Zdjęcie 1 z 3/);
  // The photo was fetched for the open image only, without any click.
  assert.deepEqual(calls.assets, [{ gameId: 'g', sourceImageId: 'img-1' }]);
  assert.equal(button('Pokaż zdjęcie pod siatkami'), undefined);
  const svg = document.querySelector('svg.geometryPreview');
  assert.equal(svg.getAttribute('viewBox'), '0 0 1200 900');
  assert.equal(svg.querySelector('image').getAttribute('href'), 'blob:photo-1');
  // One polygon per position with a quad, numbered.
  assert.equal(svg.querySelectorAll('polygon').length, 1);
  assert.equal(svg.querySelector('text').textContent, '1');
  // The positions list with the state labels.
  const items = positionItems();
  assert.equal(items.length, 2);
  assert.match(items[0].textContent, /1\. #1000Brak siatki/);
  assert.match(items[1].textContent, /2\. #1001Brak siatki · bez siatki/);

  await act(async () => button('Następne →').click());
  await settle();
  assert.match(document.body.textContent, /page-img-2\.jpg/);
  assert.match(document.body.textContent, /Zdjęcie 2 z 3/);
  assert.equal(calls.assets.length, 2);
  assert.equal(calls.assets[1].sourceImageId, 'img-2');
  // The previous blob URL is revoked when the image changes.
  assert.deepEqual(blobUrls.revoked, ['blob:photo-1']);
  assert.equal(
    document.querySelector('svg.geometryPreview image').getAttribute('href'),
    'blob:photo-2',
  );

  await act(async () => button('← Poprzednie').click());
  await settle();
  assert.match(document.body.textContent, /Zdjęcie 1 z 3/);
  assert.equal(button('← Poprzednie').disabled, true);
  assert.equal(calls.assets.length, 3);
  assert.deepEqual(blobUrls.revoked, ['blob:photo-1', 'blob:photo-2']);

  await act(async () => root.unmount());
  assert.deepEqual(blobUrls.revoked, [
    'blob:photo-1',
    'blob:photo-2',
    'blob:photo-3',
  ]);
});

test('a filter requests its state only and an empty state is readable', async () => {
  const state = {
    byState: {
      import_failed: { first: { images: [], nextCursor: null } },
    },
    pages: {
      first: { images: [gapImage('img-1')], nextCursor: null },
    },
  };
  const { api, calls } = fakeApi(state);
  const root = await render(api);

  await act(async () => filterButton('Import nieudany').click());
  await settle();
  assert.deepEqual(calls.list.at(-1), {
    gameId: 'g',
    imageState: 'import_failed',
    limit: 25,
  });
  assert.equal(
    filterButton('Import nieudany').getAttribute('aria-pressed'),
    'true',
  );
  assert.match(document.body.textContent, /Brak zdjęć w tym stanie/);
  assert.equal(document.querySelector('svg.geometryPreview'), null);

  await act(async () => filterButton('Wszystkie braki').click());
  await settle();
  assert.deepEqual(calls.list.at(-1), {
    gameId: 'g',
    gapsOnly: true,
    limit: 25,
  });
  assert.match(document.body.textContent, /page-img-1\.jpg/);
  await act(async () => root.unmount());
});

test('a position with a deferred slot opens the editor, one without a row shows the hint, and a save refreshes', async () => {
  const image = gapImage('img-1');
  const state = {
    pages: { first: { images: [image], nextCursor: null } },
    rows: { 'img-1': [deferredRow('img-1', 0)] },
  };
  const { api, calls } = fakeApi(state);
  const root = await render(api);

  // The targets come from the grid-reviews rows of this image, fetched once
  // the image is open (never for the whole page).
  assert.deepEqual(calls.rows, [
    {
      counts: 'correction',
      gameId: 'g',
      limit: 100,
      sourceImageId: 'img-1',
      view: 'all',
    },
  ]);
  const items = positionItems();
  assert.ok(items[0].querySelector('button'));
  assert.equal(
    items[0].querySelector('button').textContent,
    'Popraw siatkę tej planszy',
  );
  assert.equal(items[1].querySelector('button'), null);
  assert.match(
    items[1].textContent,
    /Brak planszy i slotu do ręcznej korekty — przetwórz zdjęcie ponownie w Imporcie plansz/,
  );
  assert.equal(document.querySelector('canvas'), null);

  await act(async () => items[0].querySelector('button').click());
  await settle();
  assert.equal(document.querySelectorAll('canvas').length, 1);
  assert.match(document.body.textContent, /Powód odroczenia/);
  // The deferred target reads the slot source through the local API base URL.
  assert.match(
    sourceImages.at(-1).url,
    /^http:\/\/localhost\/api\/v1\/admin\/games\/g\/image-imports\/j\/board-cell-geometry-pending\/p-img-1-0\/source\?v=c{64}$/,
  );
  await loadEditorSource();
  assert.equal(calls.preview.length, 1);
  assert.equal(calls.preview[0].id, 'p-img-1-0');
  assert.ok(button('Zapisz siatkę pozycji'));

  const listCalls = calls.list.length;
  const reportCalls = calls.report;
  state.afterResolve = {
    first: {
      images: [
        gapImage('img-1', {
          positions: [
            gapPosition({ positionIndex: 0, state: 'ok' }),
            gapPosition({ positionIndex: 1, quad: null, sequenceNumber: 1001 }),
          ],
        }),
      ],
      nextCursor: null,
    },
  };
  await act(async () => button('Zapisz siatkę pozycji').click());
  await settle();

  assert.equal(calls.resolve.length, 1);
  assert.equal(calls.resolve[0].id, 'p-img-1-0');
  assert.deepEqual(calls.resolve[0].scope, { gameId: 'g', importJobId: 'j' });
  assert.match(
    document.body.textContent,
    /Siatka zapisana\. Zdjęcie i liczniki zostały odświeżone\./,
  );
  // The editor closes; the image, the counters and the targets reload.
  assert.equal(document.querySelector('canvas'), null);
  assert.equal(calls.list.length, listCalls + 1);
  assert.equal(calls.report, reportCalls + 1);
  assert.equal(calls.rows.length, 2);
  assert.match(positionItems()[0].textContent, /Poprawna siatka/);
  assert.match(document.body.textContent, /Zdjęcie 1 z 1/);
  await act(async () => root.unmount());
});

test('a partial board opens the reported target as partial; a conflict shows one message without a loop', async () => {
  const image = gapImage('img-7', {
    imageState: 'incomplete_partial',
    positions: [
      gapPosition({
        positionIndex: 2,
        recognizedBoardId: 'b-img-7-2',
        sequenceNumber: 1002,
        state: 'partial',
      }),
    ],
  });
  const state = {
    pages: { first: { images: [image], nextCursor: null } },
    previewResult: {
      error: {
        code: 'IMAGE_GRID_REVIEW_GEOMETRY_REVISION_CONFLICT',
        message: 'Zmieniona geometria.',
      },
    },
    rows: { 'img-7': [partialBoardRow('img-7', 2)] },
  };
  const { api, calls } = fakeApi(state);
  const root = await render(api);

  assert.match(document.body.textContent, /Plansza częściowa/);
  await act(async () => positionItems()[0].querySelector('button').click());
  await settle();
  assert.equal(document.querySelectorAll('canvas').length, 1);
  // A board without reports gets the plain revision hint, not the one about
  // removing "Zła siatka" reports.
  assert.match(document.body.textContent, /Zapis utworzy nową rewizję siatki/);
  assert.doesNotMatch(document.body.textContent, /Zapis usuwa zgłoszenia/);
  assert.match(document.body.textContent, /Zgłoszone pola—/);
  const partialCheckbox = [
    ...document.querySelectorAll(
      '.deferredGeometryEditor input[type="checkbox"]',
    ),
  ][0];
  assert.equal(
    partialCheckbox.checked,
    true,
    'a partial board opens as partial',
  );
  await loadEditorSource();

  assert.equal(calls.preview.length, 1);
  assert.equal(calls.preview[0].id, 'r-img-7-2');
  assert.equal(
    calls.preview[0].command.geometryQualification.completenessStatus,
    'pending_partial',
  );
  // The conflict closes the editor and reloads the image exactly once.
  assert.match(document.body.textContent, /Zmieniona geometria\./);
  assert.match(document.body.textContent, /otwórz pozycję ponownie/);
  assert.equal(document.querySelector('canvas'), null);
  assert.equal(calls.list.length, 2);
  assert.equal(calls.rows.length, 2);
  await settle();
  assert.equal(calls.preview.length, 1, 'no second preview without a click');
  assert.equal(calls.list.length, 2, 'no reload loop');
  await act(async () => root.unmount());
});

test('import_failed shows the error code, the photo and no editor nor row lookup', async () => {
  const state = {
    pages: {
      first: {
        images: [
          gapImage('img-9', {
            expectedBoardCount: null,
            imageState: 'import_failed',
            importErrorCode: 'IMAGE_STAGE_EXECUTION_FAILED',
            orientedHeight: null,
            orientedWidth: null,
            positions: [],
            sequenceRangeEnd: null,
            sequenceRangeStart: null,
            sourceStatus: 'failed',
          }),
        ],
        nextCursor: null,
      },
    },
  };
  const { api, calls } = fakeApi(state);
  const root = await render(api);

  const text = document.body.textContent;
  assert.match(text, /Import nieudany/);
  assert.match(text, /Status zdjęcia: błąd/);
  assert.match(
    text,
    /Błąd importu pliku: etap przetwarzania zakończył się błędem \(IMAGE_STAGE_EXECUTION_FAILED\)/,
  );
  assert.match(text, /przetwórz plik ponownie w Imporcie plansz/);
  // Without dimensions the photo is a plain image, still loaded automatically.
  assert.equal(calls.assets.length, 1);
  assert.equal(
    document.querySelector('img.geometryPreview').getAttribute('src'),
    blobUrls.created.at(-1),
  );
  assert.equal(document.querySelector('svg.geometryPreview'), null);
  assert.equal(button('Popraw siatkę tej planszy'), undefined);
  assert.equal(document.querySelector('canvas'), null);
  assert.equal(calls.rows.length, 0);
  await act(async () => root.unmount());
});

test('a missing source file keeps the positions visible with a message', async () => {
  const state = {
    assetMissing: true,
    pages: { first: { images: [gapImage('img-1')], nextCursor: null } },
  };
  const { api } = fakeApi(state);
  const root = await render(api);
  assert.match(
    document.body.textContent,
    /Zdjęcie źródłowe jest niedostępne\./,
  );
  assert.equal(document.querySelector('svg.geometryPreview image'), null);
  assert.equal(positionItems().length, 2);
  await act(async () => root.unmount());
});

test('images whose partial boards are all human approved are hidden until the toggle shows them (decision 8)', async () => {
  const approved = gapImage('img-a', {
    imageState: 'incomplete_partial',
    positions: [
      gapPosition({ humanApproved: true, positionIndex: 0, state: 'partial' }),
      gapPosition({ humanApproved: true, positionIndex: 1, state: 'partial' }),
    ],
  });
  const pending = gapImage('img-b', {
    imageState: 'incomplete_partial',
    positions: [
      gapPosition({ humanApproved: false, positionIndex: 0, state: 'partial' }),
    ],
  });
  const state = {
    pages: { first: { images: [approved, pending], nextCursor: null } },
  };
  const { api, calls } = fakeApi(state);
  const root = await render(api);

  assert.match(document.body.textContent, /page-img-b\.jpg/);
  assert.doesNotMatch(document.body.textContent, /page-img-a\.jpg/);
  assert.match(
    document.body.textContent,
    /Zdjęcie 1 z 1 · ukryte zatwierdzone ręcznie: 1/,
  );
  assert.equal(button('Następne →').disabled, true);

  const toggle = document.querySelector('.geometryGapsToggle input');
  await act(async () => toggle.click());
  await settle();
  // Client-side only: no new request.
  assert.equal(calls.list.length, 1);
  assert.match(document.body.textContent, /page-img-a\.jpg/);
  assert.match(document.body.textContent, /Zdjęcie 1 z 2/);
  assert.match(document.body.textContent, /zatwierdzona ręcznie/);
  await act(async () => button('Następne →').click());
  await settle();
  assert.match(document.body.textContent, /page-img-b\.jpg/);
  await act(async () => root.unmount());
});

test('the next page is fetched ahead when at most three images remain', async () => {
  const firstPage = ['1', '2', '3', '4', '5'].map((id) =>
    gapImage(`img-${id}`),
  );
  const secondPage = ['6', '7'].map((id) => gapImage(`img-${id}`));
  const state = {
    pages: {
      c1: { images: secondPage, nextCursor: null },
      first: { images: firstPage, nextCursor: 'c1' },
    },
  };
  const { api, calls } = fakeApi(state);
  const root = await render(api);

  assert.equal(calls.list.length, 1);
  assert.match(document.body.textContent, /Zdjęcie 1 z 5\+/);
  await act(async () => button('Następne →').click());
  await settle();
  assert.equal(calls.list.length, 2);
  assert.deepEqual(calls.list[1], {
    afterCursor: 'c1',
    gameId: 'g',
    gapsOnly: true,
    limit: 25,
  });
  assert.match(document.body.textContent, /Zdjęcie 2 z 7/);
  assert.doesNotMatch(document.body.textContent, /z 7\+/);
  // The current image was neither reloaded nor replaced by the append.
  assert.match(document.body.textContent, /page-img-2\.jpg/);
  assert.equal(calls.assets.length, 2);
  await act(async () => root.unmount());
});

function alertText() {
  return [...document.querySelectorAll('[role="alert"]')]
    .map((node) => node.textContent)
    .join(' | ');
}

test('a failed next page keeps the fetched images reachable behind a banner with a retry', async () => {
  const firstPage = ['1', '2', '3', '4'].map((id) => gapImage(`img-${id}`));
  const state = {
    failCursors: new Set(['c1']),
    pages: {
      c1: { images: [gapImage('img-5')], nextCursor: null },
      first: { images: firstPage, nextCursor: 'c1' },
    },
  };
  const { api, calls } = fakeApi(state);
  const root = await render(api);

  // Four images with three remaining: the prefetch ran and failed.
  assert.equal(calls.list.length, 2);
  assert.match(
    alertText(),
    /Połączenie z lokalnym Admin API zostało przerwane\./,
  );
  assert.ok(button('Ponów pobieranie'));
  // The queue is still shown and navigable, not replaced by an error view.
  assert.match(document.body.textContent, /page-img-1\.jpg/);
  assert.match(document.body.textContent, /Zdjęcie 1 z 4\+/);
  assert.doesNotMatch(
    document.body.textContent,
    /Nie udało się wczytać braków zdjęć/,
  );
  await act(async () => button('Następne →').click());
  await settle();
  assert.match(document.body.textContent, /page-img-2\.jpg/);
  // No automatic retry loop: still the two requests.
  assert.equal(calls.list.length, 2);

  await act(async () => button('Ponów pobieranie').click());
  await settle();
  assert.equal(calls.list.length, 3);
  assert.deepEqual(calls.list[2], {
    afterCursor: 'c1',
    gameId: 'g',
    gapsOnly: true,
    limit: 25,
  });
  assert.equal(alertText(), '');
  assert.match(document.body.textContent, /Zdjęcie 2 z 5/);
  await act(async () => root.unmount());
});

test('a failed first page shows the error view and "Spróbuj ponownie" loads the queue', async () => {
  const state = {
    failCursors: new Set(['first']),
    failWithError: true,
    pages: { first: { images: [gapImage('img-1')], nextCursor: null } },
  };
  const { api, calls } = fakeApi(state);
  const root = await render(api);

  assert.match(document.body.textContent, /Nie udało się wczytać braków zdjęć/);
  assert.match(
    document.body.textContent,
    /Lista padła\. \(IMAGE_GEOMETRY_LIST_FAILED\)/,
  );
  assert.equal(document.querySelector('svg.geometryPreview'), null);
  assert.equal(calls.assets.length, 0);

  await act(async () => button('Spróbuj ponownie').click());
  await settle();
  assert.equal(calls.list.length, 2);
  assert.match(document.body.textContent, /page-img-1\.jpg/);
  assert.doesNotMatch(
    document.body.textContent,
    /Nie udało się wczytać braków zdjęć/,
  );
  await act(async () => root.unmount());
});

test('a failed grid-reviews lookup shows an error with a retry and no edit buttons', async () => {
  const state = {
    pages: { first: { images: [gapImage('img-1')], nextCursor: null } },
    rows: { 'img-1': [deferredRow('img-1', 0)] },
    rowsError: true,
  };
  const { api, calls } = fakeApi(state);
  const root = await render(api);

  assert.equal(calls.rows.length, 1);
  assert.match(
    alertText(),
    /Nie udało się sprawdzić celów edycji tego zdjęcia\./,
  );
  assert.equal(button('Popraw siatkę tej planszy'), undefined);
  // The image and its positions are still shown.
  assert.equal(positionItems().length, 2);

  state.rowsError = false;
  await act(async () => button('Spróbuj ponownie').click());
  await settle();
  assert.equal(calls.rows.length, 2);
  assert.equal(alertText(), '');
  assert.ok(button('Popraw siatkę tej planszy'));
  await act(async () => root.unmount());
});

test('a late response of a previous filter never overrides the current filter', async () => {
  let release;
  const state = {
    byState: {
      import_failed: { first: { images: [], nextCursor: null } },
      incomplete_missing: {
        first: { images: [gapImage('img-late')], nextCursor: null },
      },
    },
    gate: {
      incomplete_missing: new Promise((resolve) => {
        release = resolve;
      }),
    },
    pages: { first: { images: [gapImage('img-1')], nextCursor: null } },
  };
  const { api, calls } = fakeApi(state);
  const root = await render(api);

  await act(async () => filterButton('Brakuje plansz').click());
  await settle();
  // The slow filter is still pending; the operator switches again.
  assert.equal(calls.list.length, 2);
  assert.match(document.body.textContent, /Wczytywanie braków/);
  await act(async () => filterButton('Import nieudany').click());
  await settle();
  assert.equal(calls.list.length, 3);
  assert.match(document.body.textContent, /Brak zdjęć w tym stanie/);

  release();
  await settle();
  // The stale "Brakuje plansz" page is discarded.
  assert.match(document.body.textContent, /Brak zdjęć w tym stanie/);
  assert.doesNotMatch(document.body.textContent, /page-img-late\.jpg/);
  assert.equal(
    filterButton('Import nieudany').getAttribute('aria-pressed'),
    'true',
  );
  assert.equal(calls.assets.length, 1, 'only the first image was ever opened');
  await act(async () => root.unmount());
});

test('"↻ Odśwież" keeps the open image (from a later page) and the mounted editor', async () => {
  const firstPage = ['1', '2', '3', '4', '5'].map((id) =>
    gapImage(`img-${id}`),
  );
  const secondPage = ['6', '7'].map((id) => gapImage(`img-${id}`));
  const state = {
    pages: {
      c1: { images: secondPage, nextCursor: null },
      first: { images: firstPage, nextCursor: 'c1' },
    },
    rows: { 'img-6': [deferredRow('img-6', 0)] },
  };
  const { api, calls } = fakeApi(state);
  const root = await render(api);

  for (let step = 0; step < 5; step += 1) {
    await act(async () => button('Następne →').click());
    await settle();
  }
  assert.match(document.body.textContent, /page-img-6\.jpg/);
  assert.match(document.body.textContent, /Zdjęcie 6 z 7/);
  await act(async () => positionItems()[0].querySelector('button').click());
  await settle();
  await loadEditorSource();
  const canvas = document.querySelector('canvas');
  assert.ok(canvas);
  const previews = calls.preview.length;
  const listCalls = calls.list.length;
  const assets = calls.assets.length;
  // One rows lookup per opened image so far (img-1 … img-6).
  const rowsCalls = calls.rows.length;
  assert.equal(rowsCalls, 6);

  await act(async () => button('↻ Odśwież').click());
  await settle();
  // Both pages were re-read in order until the open image came back.
  assert.equal(calls.list.length, listCalls + 2);
  assert.equal(calls.list.at(-2).afterCursor, undefined);
  assert.equal(calls.list.at(-1).afterCursor, 'c1');
  assert.match(document.body.textContent, /page-img-6\.jpg/);
  assert.match(document.body.textContent, /Zdjęcie 6 z 7/);
  // The same DOM node: the editor was neither unmounted nor reloaded, and
  // the photo was not fetched again.
  assert.equal(document.querySelector('canvas'), canvas);
  assert.equal(calls.preview.length, previews);
  assert.equal(calls.assets.length, assets);
  // The targets were re-read once and the edit button is usable again.
  assert.equal(calls.rows.length, rowsCalls + 1);
  assert.equal(calls.rows.at(-1).sourceImageId, 'img-6');
  assert.equal(button('Zamknij edytor').disabled, false);
  assert.doesNotMatch(document.body.textContent, /Wczytywanie braków/);
  await act(async () => root.unmount());
});
