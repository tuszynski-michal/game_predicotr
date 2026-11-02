import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { after, test } from 'node:test';
import React, { act } from 'react';
import { JSDOM } from 'jsdom';

const reactUrl = import.meta.resolve('react');
registerHooks({
  resolve(specifier, context, nextResolve) {
    return nextResolve(specifier === 'react' ? reactUrl : specifier, context);
  },
  load(url, context, nextLoad) {
    if (url.endsWith('.css'))
      return {
        format: 'module',
        shortCircuit: true,
        source: 'export default new Proxy({}, { get: (_, key) => key });',
      };
    return nextLoad(url, context);
  },
});
const dom = new JSDOM('<div id="root"></div>', {
  url: 'http://localhost',
  pretendToBeVisual: true,
});
for (const name of [
  'window',
  'document',
  'HTMLElement',
  'HTMLInputElement',
  'HTMLSelectElement',
  'HTMLDialogElement',
  'Event',
  'MouseEvent',
])
  Object.defineProperty(globalThis, name, {
    configurable: true,
    value: dom.window[name],
  });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
dom.window.HTMLDialogElement.prototype.showModal = function () {
  this.setAttribute('open', '');
};
dom.window.HTMLDialogElement.prototype.close = function () {
  this.removeAttribute('open');
};
const { createRoot } = await import('react-dom/client');
const { ReadabilityWorkspace } =
  await import('../src/features/readability/readability-workspace.tsx');
after(() => dom.window.close());

const item = (extra = {}) => ({
  cellId: 'cell-1',
  reviewItemId: 'review-1',
  recognizedBoardId: 'board-1',
  importJobId: 'job-1',
  sourceId: 'source-1',
  sequenceNumber: 19,
  cellIndex: 0,
  rowIndex: 0,
  columnIndex: 0,
  geometryRevision: 1,
  cropChecksumSha256: 'c'.repeat(64),
  renderSpecChecksumSha256: null,
  identity: 'a'.repeat(64),
  revision: 3,
  state: 'pending',
  overlap: null,
  sharp: false,
  similarReadable: false,
  historicalUnreadable: false,
  sampleKind: 'pilot',
  overlapScore: null,
  unreadableScore: null,
  candidate: false,
  reasons: [],
  ...extra,
});
const run = {
  id: 'run-1',
  kind: 'pilot',
  status: 'completed',
  revision: 4,
  itemCount: 3,
  processedCount: 3,
  errorCode: null,
  errorMessage: null,
};
const model = (extra = {}) => ({
  id: 'model-1',
  status: 'completed',
  revision: 2,
  accepted: false,
  report: { status: 'PASS' },
  ...extra,
});
function fixture(extra = {}) {
  const calls = [];
  const api = {
    getReadabilityWorkspace: async () => ({
      data: { runs: [run], models: [] },
    }),
    listReadabilityItems: async (...args) => {
      calls.push(['list', ...args]);
      return {
        data: {
          items: [
            item(),
            item({
              cellId: 'cell-2',
              cellIndex: 1,
              state: 'stale',
              overlap: true,
              historicalUnreadable: true,
              reasons: ['GEOMETRY_CHANGED'],
            }),
          ],
          nextOffset: null,
          fields: 2,
          boards: 1,
          sources: 1,
          confirmedFields: 0,
          confirmedBoards: 0,
          confirmedSources: 0,
        },
      };
    },
    startReadabilityRun: async (...args) => {
      calls.push(['start', ...args]);
      return { data: run };
    },
    labelReadabilityItems: async (...args) => {
      calls.push(['labels', ...args]);
      return { data: {} };
    },
    fitReadabilityPilot: async (...args) => {
      calls.push(['fit', ...args]);
      return { data: model() };
    },
    acceptReadabilityModel: async (...args) => {
      calls.push(['accept', ...args]);
      return { data: model({ accepted: true }) };
    },
    exportReadabilityCsvUrl: () => '/report.csv',
    symbolCellReviewAssetUrl: () => '/crop.png',
    ...extra,
  };
  return { api, calls };
}
async function flush() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}
const button = (title) => {
  const found = [...document.querySelectorAll('button')].find(
    (node) => node.textContent.trim() === title,
  );
  assert.ok(found, title);
  return found;
};
async function click(node) {
  await act(async () => node.click());
  await flush();
}
async function choose(title, value) {
  const label = [...document.querySelectorAll('label')].find(
    (node) => node.firstChild?.textContent.trim() === title,
  );
  const node = label?.querySelector('select');
  assert.ok(node, title);
  await act(async () => {
    node.value = value;
    node.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await flush();
}
async function mount(api, gameId = 'game-1', clear = true) {
  if (clear) window.localStorage.clear();
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(ReadabilityWorkspace, {
        apiBaseUrl: '',
        gameId,
        client: api,
      }),
    ),
  );
  await flush();
  await flush();
  return root;
}
async function unmount(root) {
  await act(async () => root.unmount());
}

test('pilot works without a model; uncertain labels and stale fields remain distinct; readable never calls symbol approval', async () => {
  const { api, calls } = fixture();
  const root = await mount(api);
  assert.equal(button('Przygotuj pilot').disabled, false);
  await click(button('Przygotuj pilot'));
  assert.equal(calls.find(([kind]) => kind === 'start')[2].kind, 'pilot');
  assert.equal(calls.find(([kind]) => kind === 'start')[2].modelId, null);
  assert.match(
    document.body.textContent,
    /Niepewna czytelność · nałożenie: niepewne/,
  );
  assert.match(document.body.textContent, /GEOMETRY_CHANGED/);
  const fields = document.querySelectorAll('article input[type=checkbox]');
  assert.equal(fields[1].disabled, true);
  await click(fields[0]);
  await choose('Czytelność', 'readable');
  await choose('Nałożenie', 'yes');
  await click(button('Zapisz oceny'));
  const request = calls.find(([kind]) => kind === 'labels')[3];
  assert.equal(request.state, 'readable');
  assert.equal(request.overlap, true);
  assert.deepEqual(request.targets, [
    { cellId: 'cell-1', expectedIdentity: 'a'.repeat(64), expectedRevision: 3 },
  ]);
  assert.match(document.body.textContent, /nie zatwierdza nazwy symbolu/);
  assert.ok(document.querySelector('a[href="/report.csv"]'));
  await choose('Historia', 'old');
  await choose('Typ problemu', 'overlap');
  assert.equal(
    calls.filter(([kind]) => kind === 'list').at(-1)[3].historical,
    true,
  );
  assert.equal(
    calls.filter(([kind]) => kind === 'list').at(-1)[3].problem,
    'overlap',
  );
  await unmount(root);
});

test('fit, acceptance and scan are separate actions; only accepted PASS enables scan', async () => {
  let currentModel = model({ report: { status: 'STOP' } });
  const { api, calls } = fixture({
    getReadabilityWorkspace: async () => ({
      data: { runs: [run], models: [currentModel] },
    }),
  });
  const root = await mount(api);
  assert.equal(button('Odbierz model po PASS').disabled, true);
  assert.equal(button('Rozpocznij pełny skan').disabled, true);
  await click(button('Zamroź etykiety i dopasuj model'));
  assert.equal(calls.filter(([kind]) => kind === 'fit').length, 1);
  assert.equal(calls.filter(([kind]) => kind === 'start').length, 0);
  currentModel = model();
  await click(button('Odśwież przegląd'));
  assert.equal(button('Odbierz model po PASS').disabled, false);
  assert.equal(button('Rozpocznij pełny skan').disabled, true);
  await click(button('Odbierz model po PASS'));
  assert.equal(calls.filter(([kind]) => kind === 'accept').length, 1);
  assert.equal(calls.filter(([kind]) => kind === 'start').length, 0);
  currentModel = model({ accepted: true });
  await click(button('Odśwież przegląd'));
  await click(button('Rozpocznij pełny skan'));
  assert.equal(calls.find(([kind]) => kind === 'start')[2].kind, 'scan');
  assert.equal(calls.find(([kind]) => kind === 'start')[2].modelId, 'model-1');
  await unmount(root);
});

test('lost response survives a cold mount and replays original revisions with the original key', async () => {
  const received = [];
  let fail = true;
  const { api } = fixture({
    labelReadabilityItems: async (...args) => {
      received.push(args);
      if (fail) throw new Error('Lost response');
      return { data: {} };
    },
  });
  let root = await mount(api);
  await click(document.querySelector('article input[type=checkbox]'));
  await choose('Czytelność', 'unreadable');
  await click(button('Zapisz oceny'));
  assert.match(
    document.querySelector('[role=alert]').textContent,
    /Lost response/,
  );
  await unmount(root);
  fail = false;
  const oldList = api.listReadabilityItems;
  api.listReadabilityItems = async (...args) => {
    const response = await oldList(...args);
    response.data.items = response.data.items.map((field) => ({
      ...field,
      revision: 99,
    }));
    return response;
  };
  root = await mount(api, 'game-1', false);
  await click(button('Ponów zapisaną komendę'));
  assert.deepEqual(received[1], received[0]);
  assert.equal(window.localStorage.getItem('readability-command:game-1'), null);
  await unmount(root);
});

test('explicit validation errors release the intent for correction', async () => {
  const { api } = fixture({
    fitReadabilityPilot: async () => ({
      error: { message: 'STOP: incomplete labels' },
      response: { status: 409 },
    }),
  });
  const root = await mount(api);
  await click(button('Zamroź etykiety i dopasuj model'));
  assert.match(document.querySelector('[role=alert]').textContent, /STOP/);
  assert.equal(window.localStorage.getItem('readability-command:game-1'), null);
  await unmount(root);
});

test('late responses from the old game cannot populate the new game', async () => {
  let resolveOld;
  const { api } = fixture({
    getReadabilityWorkspace: async (gameId) =>
      gameId === 'old'
        ? new Promise((resolve) => {
            resolveOld = resolve;
          })
        : { data: { runs: [], models: [] } },
  });
  const root = await mount(api, 'old');
  await act(async () =>
    root.render(
      React.createElement(ReadabilityWorkspace, {
        apiBaseUrl: '',
        gameId: 'new',
        client: api,
      }),
    ),
  );
  await flush();
  await act(async () => resolveOld({ data: { runs: [run], models: [] } }));
  await flush();
  assert.match(document.body.textContent, /Brak uruchomień/);
  assert.equal(document.querySelector('article'), null);
  await unmount(root);
});

test('uncertain readability and overlap save independently; crop zoom closes without changing a label', async () => {
  const { api, calls } = fixture();
  const root = await mount(api);
  await click(
    document.querySelector('button[aria-label="Powiększ pole 1 planszy 19"]'),
  );
  assert.ok(document.querySelector('dialog[open] img'));
  await click(button('Zamknij powiększenie'));
  assert.equal(document.querySelector('dialog'), null);
  assert.equal(
    calls.some(([kind]) => kind === 'labels'),
    false,
  );
  await click(document.querySelector('article input[type=checkbox]'));
  await click(button('Zapisz oceny'));
  const request = calls.find(([kind]) => kind === 'labels')[3];
  assert.equal(request.state, 'pending');
  assert.equal(request.overlap, null);
  await unmount(root);
});

test('loading, empty pages and fetch errors are recoverable through refresh', async () => {
  let resolveWorkspace;
  let fail = true;
  const { api } = fixture({
    getReadabilityWorkspace: () =>
      new Promise((resolve) => {
        resolveWorkspace = resolve;
      }),
    listReadabilityItems: async () => {
      if (fail) throw new Error('Read failed');
      return {
        data: {
          items: [],
          nextOffset: null,
          fields: 0,
          boards: 0,
          sources: 0,
          confirmedFields: 0,
          confirmedBoards: 0,
          confirmedSources: 0,
        },
      };
    },
  });
  const root = await mount(api);
  assert.match(document.body.textContent, /Wczytywanie przeglądu/);
  await act(async () =>
    resolveWorkspace({ data: { runs: [run], models: [] } }),
  );
  await flush();
  assert.match(
    document.querySelector('[role=alert]').textContent,
    /Read failed/,
  );
  fail = false;
  // Refresh reloads the workspace as well as the selected page.
  await click(button('Odśwież przegląd'));
  await act(async () =>
    resolveWorkspace({ data: { runs: [run], models: [] } }),
  );
  await flush();
  assert.match(document.body.textContent, /Brak pól dla wybranych filtrów/);
  assert.equal(document.querySelector('[role=alert]'), null);
  await unmount(root);
});
