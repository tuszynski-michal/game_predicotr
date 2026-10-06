import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { after, test } from 'node:test';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';

registerHooks({
  load(url, context, nextLoad) {
    if (url.endsWith('.css'))
      return {
        format: 'module',
        source: 'export default {};',
        shortCircuit: true,
      };
    return nextLoad(url, context);
  },
});

const dom = new JSDOM('<div id="root"></div>', {
  url: 'http://127.0.0.1:3000',
});
for (const key of ['window', 'document', 'HTMLElement', 'Element', 'Event'])
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import('react-dom/client');
const { ReviewerAccessLauncher } =
  await import('../src/features/reviewer-access/reviewer-access-launcher.tsx');
after(() => dom.window.close());

const job = (gameId) => ({
  id: `import-${gameId}`,
  gameId,
  jobType: 'import',
  status: 'waiting_for_review',
  createdAt: '2026-10-07T10:00:00Z',
  inputPayload: { importKind: 'image_directory', sourceDisplayName: gameId },
});
const report = (gameId) => ({
  gameId,
  images: {
    total: 1,
    complete: 0,
    incomplete: 1,
    incompleteMissing: 1,
    incompletePartial: 0,
    incompleteUncertain: 0,
    noSourceGeometry: 0,
    superseded: 0,
    importFailed: 0,
  },
  sourceStatuses: [],
  positions: [],
  gate: null,
});
const page = (gameId) => ({
  images: [
    {
      sourceImageId: `source-${gameId}`,
      importJobId: `import-${gameId}`,
      relativePath: `${gameId}-missing.jpg`,
      imageState: 'incomplete_missing',
      sourceStatus: 'completed',
      sequenceRangeStart: 1,
      sequenceRangeEnd: 9,
      expectedBoardCount: 9,
      orientedWidth: null,
      orientedHeight: null,
      importErrorCode: null,
      positions: [],
      completenessStatus: null,
    },
  ],
  nextCursor: null,
});
const button = (name) =>
  [...document.querySelectorAll('button')].find(
    (element) => element.textContent.trim() === name,
  );
function fixture(overrides = {}) {
  const calls = { reports: [], images: [], jobs: [], grids: [] };
  const api = {
    listGames: async () => ({
      data: [
        { id: 'A', name: 'A', status: 'draft' },
        { id: 'B', name: 'B', status: 'draft' },
      ],
    }),
    listJobs: async (request) => {
      calls.jobs.push(request);
      return { data: [job(request.gameId ?? 'A')] };
    },
    listReadyBrowserImageSelections: async () => ({ data: [] }),
    listImageGridReviews: async (request) => {
      calls.grids.push(request);
      return {
        data: {
          counts: {
            needsValidation: 0,
            needsCorrection: 1,
            approved: 0,
            correction: 1,
          },
        },
      };
    },
    listPendingBoardCellGeometry: async () => ({
      data: { counts: { pending: 1 } },
    }),
    getImageGeometryCompleteness: async (request) => {
      calls.reports.push(request);
      return { data: report(request.gameId) };
    },
    listIncompleteGeometryImages: async (request) => {
      calls.images.push(request);
      return { data: page(request.gameId) };
    },
    getImageGeometryLowQualityBoards: async () => {
      assert.fail('quality scanning must remain an explicit action');
    },
    ...overrides,
  };
  return { api, calls };
}
async function mount(api, gameId = 'A') {
  const root = createRoot(document.getElementById('root'));
  const render = async (nextGameId) => {
    await act(async () =>
      root.render(
        React.createElement(ReviewerAccessLauncher, {
          apiBaseUrl: 'http://fixture',
          client: api,
          ...(nextGameId === null ? {} : { gameId: nextGameId }),
        }),
      ),
    );
  };
  await render(gameId);
  return { root, render };
}

test('correction renders diagnostics and keeps its existing queue available', async () => {
  const { api, calls } = fixture();
  const { root } = await mount(api);
  try {
    assert.match(document.body.textContent, /Diagnostyka siatek zdjęć/);
    assert.match(document.body.textContent, /A-missing.jpg/);
    assert.match(document.body.textContent, /Plansze do korekty cięcia siatki/);
    assert.equal(button('Otwórz lokalnie').disabled, false);
    assert.equal(calls.grids[0].view, 'correction');
    assert.deepEqual(calls.reports, [{ gameId: 'A' }]);
    assert.equal(calls.images[0].completenessStatus, 'geometry_incomplete');
    await act(async () => button('Wybrany import').click());
    assert.deepEqual(calls.reports.at(-1), {
      gameId: 'A',
      importJobId: 'import-A',
    });
  } finally {
    await act(async () => root.unmount());
  }
});

test('refresh reloads queue context and diagnostics without dispatching work', async () => {
  const { api, calls } = fixture();
  const { root } = await mount(api);
  try {
    const reportsBefore = calls.reports.length;
    const gridsBefore = calls.grids.length;
    await act(async () => button('Odśwież kolejkę').click());
    assert.equal(calls.jobs.length, 2);
    assert.ok(calls.grids.length > gridsBefore);
    assert.ok(calls.reports.length > reportsBefore);
    assert.equal(button('Otwórz lokalnie').disabled, false);
  } finally {
    await act(async () => root.unmount());
  }
});

test('report failure exposes retry and then displays the existing grid problems', async () => {
  let failed = true;
  const { api } = fixture({
    getImageGeometryCompleteness: async ({ gameId }) =>
      failed ? { error: {} } : { data: report(gameId) },
  });
  const { root } = await mount(api);
  try {
    assert.match(
      document.querySelector('[role="alert"]').textContent,
      /Nie udało się pobrać/,
    );
    failed = false;
    await act(async () => button('Spróbuj ponownie').click());
    assert.match(document.body.textContent, /A-missing.jpg/);
  } finally {
    await act(async () => root.unmount());
  }
});

test('refresh preserves the game selected in the uncontrolled launcher', async () => {
  const { api } = fixture({
    listJobs: async () => ({ data: [job('A'), job('B')] }),
  });
  const { root } = await mount(api, null);
  try {
    const select = [...document.querySelectorAll('select')].find((element) =>
      element.parentElement.textContent.startsWith('Gra'),
    );
    await act(async () => {
      select.value = 'B';
      select.dispatchEvent(new Event('change', { bubbles: true }));
    });
    assert.match(document.body.textContent, /B-missing.jpg/);
    await act(async () => button('Odśwież kolejkę').click());
    assert.equal(select.value, 'B');
    assert.match(document.body.textContent, /B-missing.jpg/);
    assert.doesNotMatch(document.body.textContent, /A-missing.jpg/);
  } finally {
    await act(async () => root.unmount());
  }
});

test('fresh mount recovers diagnostics from the API', async () => {
  const { api, calls } = fixture();
  let mounted = await mount(api);
  await act(async () => mounted.root.unmount());
  mounted = await mount(api);
  try {
    assert.equal(calls.reports.length, 2);
    assert.match(document.body.textContent, /A-missing.jpg/);
  } finally {
    await act(async () => mounted.root.unmount());
  }
});

test('late response from the previous game cannot populate current diagnostics', async () => {
  let finishA;
  const waiting = new Promise((resolve) => {
    finishA = resolve;
  });
  const { api } = fixture({
    getImageGeometryCompleteness: async ({ gameId }) =>
      gameId === 'A' ? waiting : { data: report(gameId) },
  });
  const { root, render } = await mount(api);
  try {
    assert.match(document.body.textContent, /Ładowanie kompletności siatek/);
    await render('B');
    assert.match(document.body.textContent, /B-missing.jpg/);
    await act(async () => finishA({ data: report('A') }));
    assert.match(document.body.textContent, /B-missing.jpg/);
    assert.doesNotMatch(document.body.textContent, /A-missing.jpg/);
  } finally {
    await act(async () => root.unmount());
  }
});
