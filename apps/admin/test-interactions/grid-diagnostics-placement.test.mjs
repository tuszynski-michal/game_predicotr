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
const button = (name) =>
  [...document.querySelectorAll('button')].find(
    (element) => element.textContent.trim() === name,
  );
function fixture(overrides = {}) {
  const calls = { reports: [], jobs: [], started: 0 };
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
    // TASK-0964: a game-wide count is expensive, so the launcher never asks.
    listImageGridReviews: async () => {
      assert.fail('the launcher must not count boards per import');
    },
    listPendingBoardCellGeometry: async () => {
      assert.fail('the launcher must not count deferred geometry');
    },
    startLocalReviewer: async () => {
      calls.started += 1;
      return {
        data: {
          state: 'running',
          reviewerReady: true,
          publicOrigin: null,
          target: 'http://127.0.0.1:3001/',
        },
      };
    },
    getImageGeometryCompleteness: async (request) => {
      calls.reports.push(request);
      return { data: report(request.gameId) };
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

test('correction renders counters and the Reviewer button without a photo list or import selector', async () => {
  const { api, calls } = fixture();
  const { root } = await mount(api);
  try {
    const text = document.body.textContent;
    assert.match(text, /Diagnostyka siatek zdjęć/);
    assert.match(
      text,
      /1 zdjęć z realnymi brakami · 0 z niepotwierdzoną siatką/,
    );
    assert.doesNotMatch(text, /A-missing.jpg/);
    assert.doesNotMatch(text, /Gotowy import plansz/);
    assert.doesNotMatch(text, /Stan plansz importu/);
    assert.equal(document.querySelector('svg'), null);
    assert.equal(button('Pokaż zdjęcie pod siatkami'), undefined);
    assert.equal(button('Otwórz lokalnie').disabled, false);
    assert.equal(button('Otwórz braki w Reviewerze').disabled, false);
    assert.deepEqual(calls.reports, [{ gameId: 'A' }]);
    await act(async () => button('Wybrany import').click());
    assert.deepEqual(calls.reports.at(-1), {
      gameId: 'A',
      importJobId: 'import-A',
    });
  } finally {
    await act(async () => root.unmount());
  }
});

test('both buttons start the local Reviewer and open it scoped to the game only', async () => {
  const { api, calls } = fixture();
  const opened = [];
  const originalOpen = dom.window.open;
  dom.window.open = (url, target) => {
    opened.push([url, target]);
    return { close() {}, location: { href: '' }, opener: {} };
  };
  const { root } = await mount(api);
  try {
    await act(async () => button('Otwórz lokalnie').click());
    await act(async () => button('Otwórz braki w Reviewerze').click());
    assert.equal(calls.started, 2);
    assert.deepEqual(opened, [
      ['http://127.0.0.1:3001/?mode=local&gameId=A', '_blank'],
      ['http://127.0.0.1:3001/?mode=local&gameId=A', '_blank'],
    ]);
  } finally {
    dom.window.open = originalOpen;
    await act(async () => root.unmount());
  }
});

test('refresh reloads the game and diagnostics without counting boards', async () => {
  const { api, calls } = fixture();
  const { root } = await mount(api);
  try {
    const reportsBefore = calls.reports.length;
    await act(async () => button('Odśwież kolejkę').click());
    assert.equal(calls.jobs.length, 2);
    assert.ok(calls.reports.length > reportsBefore);
    assert.equal(button('Otwórz lokalnie').disabled, false);
  } finally {
    await act(async () => root.unmount());
  }
});

test('a game without any image import shows the prerequisite panel', async () => {
  const { api } = fixture({ listJobs: async () => ({ data: [] }) });
  const { root } = await mount(api);
  try {
    assert.match(
      document.body.textContent,
      /Brak uruchomionego importu plansz dla tej gry/,
    );
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
    assert.match(document.body.textContent, /1 zdjęć z realnymi brakami/);
  } finally {
    await act(async () => root.unmount());
  }
});

test('refresh preserves the game selected in the uncontrolled launcher', async () => {
  const { api, calls } = fixture({
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
    assert.deepEqual(calls.reports.at(-1), { gameId: 'B' });
    await act(async () => button('Odśwież kolejkę').click());
    assert.equal(select.value, 'B');
    assert.deepEqual(calls.reports.at(-1), { gameId: 'B' });
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
    assert.match(document.body.textContent, /1 zdjęć z realnymi brakami/);
  } finally {
    await act(async () => mounted.root.unmount());
  }
});

test('late response from the previous game cannot populate current diagnostics', async () => {
  let finishA;
  const waiting = new Promise((resolve) => {
    finishA = resolve;
  });
  const withMissing = (gameId, missing) => {
    const value = report(gameId);
    return {
      ...value,
      images: {
        ...value.images,
        incomplete: missing,
        incompleteMissing: missing,
      },
    };
  };
  const { api } = fixture({
    getImageGeometryCompleteness: async ({ gameId }) =>
      gameId === 'A' ? waiting : { data: withMissing(gameId, 7) },
  });
  const { root, render } = await mount(api);
  try {
    assert.match(document.body.textContent, /Ładowanie kompletności siatek/);
    await render('B');
    assert.match(document.body.textContent, /7 zdjęć z realnymi brakami/);
    await act(async () => finishA({ data: withMissing('A', 3) }));
    assert.match(document.body.textContent, /7 zdjęć z realnymi brakami/);
    assert.doesNotMatch(document.body.textContent, /3 zdjęć z realnymi/);
  } finally {
    await act(async () => root.unmount());
  }
});
