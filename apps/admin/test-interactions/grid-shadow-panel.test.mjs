import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { after, test } from 'node:test';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';

registerHooks({
  load(url, context, next) {
    if (url.endsWith('.css'))
      return {
        format: 'module',
        shortCircuit: true,
        source: 'export default new Proxy({}, {get: (_, key) => key});',
      };
    return next(url, context);
  },
});
const dom = new JSDOM('<!doctype html><div id="root"></div>', {
  url: 'http://127.0.0.1:3000',
});
for (const key of [
  'window',
  'document',
  'HTMLElement',
  'Element',
  'Event',
  'MouseEvent',
])
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import('react-dom/client');
const { GridShadowPanel } =
  await import('../src/features/grid-shadow/grid-shadow-panel.tsx');
const { ReviewerAccessLauncher } =
  await import('../src/features/reviewer-access/reviewer-access-launcher.tsx');
after(() => dom.window.close());
const settle = () =>
  act(async () => new Promise((resolve) => setTimeout(resolve, 5)));
const button = (text) =>
  [...document.querySelectorAll('button')].find((node) =>
    node.textContent.includes(text),
  );
const click = async (node) => {
  assert.ok(node);
  await act(async () =>
    node.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })),
  );
  await settle();
};

function fakeApi(overrides = {}) {
  const calls = { reviews: [], starts: [] };
  return {
    calls,
    api: {
      listImageGridReviews: async (query) => {
        calls.reviews.push(query);
        return {
          data: {
            items: [
              { sourceImageId: 's', sequenceNumber: 1 },
              { sourceImageId: 's', sequenceNumber: 2 },
            ],
          },
        };
      },
      listGridShadowResults: async () => ({
        data: { items: [], nextCursor: null },
      }),
      startGridShadowJob: async (command) => {
        calls.starts.push(command);
        return {
          error: {
            message: 'Grid comparison is disabled.',
            code: 'GRID_SHADOW_DISABLED',
          },
        };
      },
      ...overrides,
    },
  };
}
async function render(api) {
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(React.createElement(GridShadowPanel, { api, gameId: 'g' })),
  );
  await settle();
  return root;
}

test('opening the panel is read-only, deduplicates sources and displays disabled-feature refusal', async () => {
  const { api, calls } = fakeApi();
  const root = await render(api);
  try {
    assert.equal(calls.starts.length, 0);
    assert.deepEqual(calls.reviews[0], {
      gameId: 'g',
      view: 'all',
      limit: 100,
    });
    assert.equal(document.querySelectorAll('input[type="checkbox"]').length, 1);
    await click(document.querySelector('input'));
    await click(button('Porównaj wybrane'));
    assert.equal(calls.starts.length, 1);
    assert.deepEqual(calls.starts[0].sourceImageIds, ['s']);
    assert.match(
      document.querySelector('[role="alert"]').textContent,
      /wyłączony/,
    );
  } finally {
    await act(async () => root.unmount());
  }
});

test('a lost response reuses its request ID, explicit new run after receipt uses a fresh ID', async () => {
  dom.window.localStorage.clear();
  const starts = [];
  const { api } = fakeApi({
    startGridShadowJob: async (command) => {
      starts.push(command);
      if (starts.length === 1) throw new Error('lost response');
      return { data: { id: 'j', status: 'completed' } };
    },
  });
  let root = await render(api);
  try {
    await click(document.querySelector('input'));
    await click(button('Porównaj wybrane'));
    assert.match(document.body.textContent, /odzyska to samo zadanie/);
    await act(async () => root.unmount());
    root = await render(api);
    await click(document.querySelector('input'));
    await click(button('Porównaj wybrane'));
    assert.equal(starts[0].requestId, starts[1].requestId);
    await click(button('Nowe porównanie'));
    assert.notEqual(starts[1].requestId, starts[2].requestId);
  } finally {
    await act(async () => root.unmount());
  }
});

test('stale detail has both full meshes but no correction; broken source hides the overlays', async () => {
  const nodes = Array.from({ length: 24 }, (_, i) => ({
    x: (i % 6) * 10,
    y: Math.floor(i / 6) * 10,
  }));
  nodes[7] = { x: 12, y: 11 };
  const result = {
    id: 'r',
    createdAt: '2026-10-05T12:00:00Z',
    gameId: 'g',
    jobId: 'j',
    stale: true,
    status: 'needs_review',
    sourceWidth: 100,
    sourceHeight: 100,
    sourceChecksumSha256: 'a'.repeat(64),
    sourceAssetReviewItemId: 'asset',
    sourceGeometryRevision: 1,
    modelProfile: 'mumie',
    modelVersion: 'v1',
    baselineEngineName: 'source-frame-engine',
    baselineEngineVersion: 'source-frozen-v12',
    baselineGeometrySource: 'source-geometry-revision',
    reasons: [],
    output: {
      slots: [
        {
          positionIndex: 0,
          sequenceNumber: 1,
          state: 'needs_review',
          baselineNodes24: nodes,
          baselineEngineName: 'board-grid-engine',
          baselineEngineVersion: 'board-frozen-v19',
          neuralNodes24: nodes,
          reviewItem: null,
          cellVisibility: Array(15).fill('full'),
          reasonCodes: [],
        },
      ],
      unassignedDetections: [],
    },
  };
  const { api } = fakeApi({
    listGridShadowResults: async () => ({
      data: { items: [result], nextCursor: null },
    }),
    getGridShadowResult: async () => ({ data: result }),
    imageGridReviewSourceAssetUrl: () => '/asset',
  });
  const root = await render(api);
  try {
    await click(button('Porównanie z'));
    assert.equal(document.querySelectorAll('polyline').length, 20);
    assert.equal(document.querySelectorAll('circle').length, 24);
    assert.ok(
      [...document.querySelectorAll('polyline')].some((line) =>
        line.getAttribute('points').includes('12,11'),
      ),
    );
    assert.equal(button('Otwórz korektę').disabled, true);
    const details = document.querySelector('details');
    assert.match(details.textContent, /Model sieci: mumie · v1/);
    assert.match(
      details.textContent,
      /source-frame-engine · source-frozen-v12/,
    );
    assert.match(
      details.textContent,
      /Plansza 1: board-grid-engine · board-frozen-v19/,
    );
    await act(async () =>
      document
        .querySelector('image')
        .dispatchEvent(new dom.window.Event('error')),
    );
    assert.equal(document.querySelector('svg'), null);
    assert.match(document.body.textContent, /Nakładka siatek jest ukryta/);
  } finally {
    await act(async () => root.unmount());
  }
});

test('existing Admin correction entry exposes shadow for the real client and keeps reduced legacy clients intact', async () => {
  const { api, calls } = fakeApi({
    getGridShadowResult: async () => ({ data: null }),
    imageGridReviewSourceAssetUrl: () => '/asset',
    getJob: async () => ({ data: null }),
    listGames: async () => ({ data: [] }),
    listJobs: async () => ({ data: [] }),
    listReadyBrowserImageSelections: async () => ({ data: [] }),
    listPendingBoardCellGeometry: async () => ({ data: { items: [] } }),
    startLocalReviewer: async () => ({ data: null }),
  });
  const root = createRoot(document.getElementById('root'));
  try {
    await act(async () =>
      root.render(
        React.createElement(ReviewerAccessLauncher, {
          apiBaseUrl: 'http://127.0.0.1:8000/api/v1',
          gameId: 'g',
          client: api,
        }),
      ),
    );
    await settle();
    assert.ok(document.querySelector('[aria-label="Porównanie siatek sieci"]'));
    assert.equal(calls.starts.length, 0);
    const legacy = { ...api };
    delete legacy.startGridShadowJob;
    delete legacy.listGridShadowResults;
    delete legacy.getGridShadowResult;
    await act(async () =>
      root.render(
        React.createElement(ReviewerAccessLauncher, {
          apiBaseUrl: 'http://127.0.0.1:8000/api/v1',
          gameId: 'g',
          client: legacy,
        }),
      ),
    );
    await settle();
    assert.equal(
      document.querySelector('[aria-label="Porównanie siatek sieci"]'),
      null,
    );
    assert.ok(document.getElementById('operational-reviews'));
  } finally {
    await act(async () => root.unmount());
  }
});

test('an explicit comparison accepts at most twenty distinct selected sources', async () => {
  const commands = [];
  const { api } = fakeApi({
    listImageGridReviews: async () => ({
      data: {
        items: Array.from({ length: 21 }, (_, i) => ({
          sourceImageId: `source-${i}`,
          sequenceNumber: i * 9 + 1,
        })),
      },
    }),
    startGridShadowJob: async (command) => {
      commands.push(command);
      return { data: { id: 'job', status: 'processing' } };
    },
  });
  const root = await render(api);
  try {
    const checkboxes = [...document.querySelectorAll('input[type="checkbox"]')];
    for (const checkbox of checkboxes.slice(0, 20)) await click(checkbox);
    assert.equal(checkboxes[20].disabled, true);
    await click(button('Porównaj wybrane'));
    assert.equal(commands[0].sourceImageIds.length, 20);
    assert.equal(new Set(commands[0].sourceImageIds).size, 20);
  } finally {
    await act(async () => root.unmount());
  }
});

test('a late detail response from a previous game cannot repopulate the new game panel', async () => {
  let resolveRead;
  const pending = new Promise((resolve) => {
    resolveRead = resolve;
  });
  const summary = {
    id: 'old-result',
    sourceImageId: 'old-source',
    status: 'needs_review',
    modelVersion: 'v1',
    stale: false,
    createdAt: '2026-10-05T12:00:00Z',
  };
  const { api } = fakeApi({
    listGridShadowResults: async ({ gameId }) => ({
      data: { items: gameId === 'g' ? [summary] : [], nextCursor: null },
    }),
    getGridShadowResult: () => pending,
  });
  const root = await render(api);
  try {
    await click(button('Porównanie z'));
    await act(async () =>
      root.render(
        React.createElement(GridShadowPanel, { api, gameId: 'other' }),
      ),
    );
    await settle();
    await act(async () =>
      resolveRead({
        data: {
          ...summary,
          gameId: 'g',
          reasons: [],
          output: { slots: [], unassignedDetections: [] },
        },
      }),
    );
    await settle();
    assert.equal(
      document.querySelector('[aria-label="Wynik porównania"]'),
      null,
    );
    assert.equal(button('Porównanie z'), undefined);
  } finally {
    await act(async () => root.unmount());
  }
});

test('slow source and history requests show loading rather than falsely reporting missing data', async () => {
  let resolveSources, resolveHistory;
  const sources = new Promise((resolve) => {
    resolveSources = resolve;
  });
  const history = new Promise((resolve) => {
    resolveHistory = resolve;
  });
  const { api } = fakeApi({
    listImageGridReviews: () => sources,
    listGridShadowResults: () => history,
  });
  const root = await render(api);
  try {
    assert.match(document.body.textContent, /Wczytywanie listy zdjęć/);
    assert.match(document.body.textContent, /Wczytywanie historii porównań/);
    assert.doesNotMatch(
      document.body.textContent,
      /Brak zmaterializowanych|Nie ma jeszcze wyników/,
    );
    await act(async () => {
      resolveSources({ data: { items: [] } });
      resolveHistory({ data: { items: [], nextCursor: null } });
    });
    await settle();
    assert.match(document.body.textContent, /Brak zmaterializowanych zdjęć/);
    assert.match(document.body.textContent, /Nie ma jeszcze wyników porównań/);
    assert.doesNotMatch(
      document.body.textContent,
      /Wczytywanie listy|Wczytywanie historii/,
    );
  } finally {
    await act(async () => root.unmount());
  }
});

test('a delayed detail request exposes its loading state until the result arrives', async () => {
  let resolveDetail;
  const pending = new Promise((resolve) => {
    resolveDetail = resolve;
  });
  const result = {
    id: 'r',
    gameId: 'g',
    createdAt: '2026-10-05T12:00:00Z',
    stale: false,
    status: 'needs_review',
    sourceChecksumSha256: 'a'.repeat(64),
    reasons: [],
    output: { slots: [], unassignedDetections: [] },
  };
  const { api } = fakeApi({
    listGridShadowResults: async () => ({
      data: { items: [result], nextCursor: null },
    }),
    getGridShadowResult: () => pending,
  });
  const root = await render(api);
  try {
    await click(button('Porównanie z'));
    assert.match(document.body.textContent, /Wczytywanie wyniku porównania/);
    assert.equal(
      document.querySelector('[aria-label="Wynik porównania"]'),
      null,
    );
    await act(async () => resolveDetail({ data: result }));
    await settle();
    assert.doesNotMatch(
      document.body.textContent,
      /Wczytywanie wyniku porównania/,
    );
    assert.ok(document.querySelector('[aria-label="Wynik porównania"]'));
  } finally {
    await act(async () => root.unmount());
  }
});
