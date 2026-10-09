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
  'KeyboardEvent',
  'MouseEvent',
  'Image',
])
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
dom.window.HTMLDialogElement.prototype.showModal = function () {
  this.setAttribute('open', '');
};
dom.window.HTMLDialogElement.prototype.close = function () {
  this.removeAttribute('open');
};
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.React = React;
const { createRoot } = await import('react-dom/client');
const { SuperGameSeriesWorkspace } =
  await import('../src/features/super-games/super-game-series-workspace.tsx');
after(() => dom.window.close());

const FRESH = { fresh: true, generationInputVersion: 1, inputVersion: 1 };
const STALE = { fresh: false, generationInputVersion: 0, inputVersion: 1 };

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
const press = async (key, target = document.body, init = {}) => {
  await act(async () =>
    target.dispatchEvent(
      new dom.window.KeyboardEvent('keydown', {
        bubbles: true,
        cancelable: true,
        key,
        ...init,
      }),
    ),
  );
  await settle();
};
const symbolSelect = () =>
  [...document.querySelectorAll('select')].find((node) =>
    [...node.options].some((option) => option.textContent.includes('Symbol 1')),
  );

function series(overrides = {}) {
  return {
    completeness: 'complete',
    definedAt: null,
    definedBy: null,
    endSequenceNumber: 120,
    gameId: 'game-1',
    id: 'series-100',
    length: 20,
    retriggerSequenceNumbers: [105],
    revision: 3,
    runVerification: 'verified',
    startSequenceNumber: 101,
    superSymbolId: null,
    triggerSequenceNumber: 100,
    updatedAt: '2026-10-09T10:00:00Z',
    ...overrides,
  };
}

function boardsResponse(seriesOverrides = {}) {
  const boards = [];
  for (let n = 100; n <= 120; n += 1) {
    const missing = n === 103;
    boards.push({
      assetMode: missing ? null : 'operational_review',
      boardChecksumSha256: missing ? null : `checksum-${n}`,
      importJobId: missing ? null : 'job-1',
      missing,
      recognizedBoardId: null,
      reviewItemId: missing ? null : `item-${n}`,
      role: n === 100 ? 'trigger' : n === 105 ? 'retrigger' : 'spin',
      sequenceNumber: n,
      spinIndex: n === 100 ? null : n - 100,
      status: missing ? null : 'accepted',
    });
  }
  return {
    boards,
    series: series(seriesOverrides),
    superGameState: FRESH,
  };
}

function symbol(id, order, overrides = {}) {
  return {
    code: id.toUpperCase(),
    displayOrder: order,
    gameId: 'game-1',
    id,
    imagePath: null,
    isWildcard: false,
    mobileCode: order,
    name: id === 'mumia' ? 'Mumia' : `Symbol ${order + 1}`,
    nameEn: null,
    namePl: null,
    status: 'active',
    superGameTriggerCount: null,
    ...overrides,
  };
}

const SYMBOLS = [
  ...Array.from({ length: 9 }, (_, index) => symbol(`s${index + 1}`, index)),
  symbol('mumia', 9, { superGameTriggerCount: 3 }),
  symbol('wild', 10, { isWildcard: true }),
];

function fakeClient(overrides = {}) {
  const calls = { derive: 0, lists: [], saves: [] };
  const triggerBoard = [
    'S1',
    'MUMIA',
    'S2',
    'S3',
    'S4',
    'S5',
    'MUMIA',
    'S6',
    'S7',
    'S8',
    'S9',
    'S1',
    'S2',
    'MUMIA',
    'S3',
  ];
  return {
    calls,
    client: {
      boardSearchBoardViewUrl: (gameId, sequence, checksum) =>
        `http://127.0.0.1:8000/${gameId}/${sequence}/${checksum}`,
      deriveSuperGameSeries: async () => {
        calls.derive += 1;
        return {
          data: {
            deduplicated: false,
            jobId: 'job-derive',
            superGameState: STALE,
          },
        };
      },
      getBoardSearchBoardDetail: async (gameId, sequence) => ({
        data: {
          boardChecksumSha256: `checksum-${sequence}`,
          sequenceNumber: sequence,
          symbolCodes: triggerBoard,
          view: null,
        },
      }),
      getSuperGameSeriesState: async () => ({ data: STALE }),
      listRulesVersions: async () => ({ data: [] }),
      listSuperGameSeries: async (gameId, query) => {
        calls.lists.push(query);
        return {
          data: {
            items: [series()],
            nextCursor: null,
            superGameKind: 'wild_super_spins',
            superGameState: FRESH,
          },
        };
      },
      listSuperGameSeriesBoards: async () => ({ data: boardsResponse() }),
      listSymbols: async () => ({ data: SYMBOLS }),
      setSuperGameSeriesSuperSymbol: async (gameId, seriesId, body) => {
        calls.saves.push({ body, gameId, seriesId });
        return {
          data: series({
            revision: body.expectedRevision + 1,
            superSymbolId: body.symbolId,
          }),
        };
      },
      symbolImageAssetUrl: () => 'http://127.0.0.1:8000/symbol.png',
      ...overrides,
    },
  };
}

async function mount(client, props = {}) {
  const container = document.getElementById('root');
  container.replaceChildren();
  const root = createRoot(container);
  const seriesChanges = [];
  await act(async () =>
    root.render(
      React.createElement(SuperGameSeriesWorkspace, {
        apiBaseUrl: 'http://127.0.0.1:8000',
        client,
        gameId: 'game-1',
        onSeriesChange: (id) => seriesChanges.push(id),
        seriesId: null,
        ...props,
      }),
    ),
  );
  await settle();
  await settle();
  return { root, seriesChanges };
}

test('lists the series with the counter and queues a derivation on demand', async () => {
  const { calls, client } = fakeClient();
  const { root, seriesChanges } = await mount(client);
  assert.ok(document.body.textContent.includes('#100 → #101–120'));
  assert.equal(
    document.querySelector('[data-testid="undefined-series-count"] strong')
      .textContent,
    '1',
  );
  assert.ok(
    calls.lists.some((query) => query.defined === false && query.limit === 200),
  );
  const badges = [...document.querySelectorAll('[data-badge]')].map(
    (node) => node.textContent,
  );
  assert.deepEqual(badges, [
    'Kompletna',
    'Do zdefiniowania',
    'Przebieg zweryfikowany',
  ]);

  await click(button('Przelicz serie'));
  assert.equal(calls.derive, 1);
  assert.ok(document.body.textContent.includes('Zakolejkowano przeliczanie'));
  assert.ok(document.body.textContent.includes('Serie w trakcie przeliczania'));

  await click(button('Otwórz'));
  assert.deepEqual(seriesChanges, ['series-100']);
  await act(async () => root.unmount());
});

test('the series view walks the carousel with arrows and shows missing and retrigger cards', async () => {
  const { client } = fakeClient();
  const { root } = await mount(client, { seriesId: 'series-100' });
  const heading = () =>
    document.querySelector('section[aria-label="Karuzela pozycji serii"] h4')
      .textContent;
  assert.equal(heading(), 'Wyzwalacz · #100');
  assert.equal(
    document.querySelectorAll('ol[aria-label="Pozycje serii"] li').length,
    21,
  );
  // The three trigger-symbol cells of the trigger board are marked.
  assert.equal(
    document.querySelectorAll(
      'ol[aria-label="Układ symboli planszy #100"] li[title="Symbol uruchamiający"]',
    ).length,
    3,
  );

  await press('ArrowRight');
  assert.equal(heading(), 'Spin 1 · #101');
  await press('ArrowRight');
  await press('ArrowRight');
  assert.equal(heading(), 'Spin 3 · #103');
  assert.ok(document.querySelector('[data-testid="missing-card"]'));
  assert.ok(document.body.textContent.includes('brak planszy'));
  await press('ArrowRight');
  await press('ArrowRight');
  assert.equal(heading(), 'Retrigger · pozycja 5 · #105');
  await press('ArrowLeft');
  assert.equal(heading(), 'Spin 4 · #104');
  await act(async () => root.unmount());
});

test('digits pick a symbol from the ordinary list, Enter saves with the revision, Escape cancels', async () => {
  const { calls, client } = fakeClient();
  const { root } = await mount(client, { seriesId: 'series-100' });
  const options = [...symbolSelect().options].map((option) => option.value);
  // Neither the trigger symbol nor Wild is offered.
  assert.ok(!options.includes('mumia'));
  assert.ok(!options.includes('wild'));
  assert.equal(options.length, 10);

  await press('3');
  assert.equal(symbolSelect().value, 's3');
  await press('Escape');
  assert.equal(symbolSelect().value, '');
  // `0` has no tenth ordinary symbol, so nothing is picked.
  await press('0');
  assert.equal(symbolSelect().value, '');

  await press('4');
  assert.equal(symbolSelect().value, 's4');
  await press('Enter');
  assert.deepEqual(calls.saves, [
    {
      body: { expectedRevision: 3, symbolId: 's4' },
      gameId: 'game-1',
      seriesId: 'series-100',
    },
  ]);
  assert.ok(document.body.textContent.includes('Zapisano super symbol'));
  const badges = [...document.querySelectorAll('[data-badge]')].map(
    (node) => node.textContent,
  );
  assert.deepEqual(badges, [
    'Kompletna',
    'Symbol: Symbol 4',
    'Przebieg zweryfikowany',
  ]);
  await act(async () => root.unmount());
});

test('shortcuts are ignored in a select and with modifiers', async () => {
  const { calls, client } = fakeClient();
  const { root } = await mount(client, { seriesId: 'series-100' });
  await press('2', symbolSelect());
  assert.equal(symbolSelect().value, '');
  await press('2', document.body, { ctrlKey: true });
  assert.equal(symbolSelect().value, '');
  await press('Enter', document.body, { metaKey: true });
  assert.equal(calls.saves.length, 0);
  await press('2');
  assert.equal(symbolSelect().value, 's2');
  await act(async () => root.unmount());
});

test('a revision conflict writes nothing and shows the current series', async () => {
  let reads = 0;
  const { calls, client } = fakeClient({
    listSuperGameSeriesBoards: async () => {
      reads += 1;
      return {
        data:
          reads === 1
            ? boardsResponse()
            : boardsResponse({ revision: 4, superSymbolId: 's7' }),
      };
    },
    setSuperGameSeriesSuperSymbol: async (gameId, seriesId, body) => {
      calls.saves.push({ body, gameId, seriesId });
      return {
        error: {
          code: 'SUPER_GAME_SERIES_REVISION_CONFLICT',
          details: {},
          message: 'conflict',
        },
      };
    },
  });
  const { root } = await mount(client, { seriesId: 'series-100' });
  await press('ArrowRight');
  await press('5');
  await press('Enter');
  assert.equal(calls.saves.length, 1);
  assert.equal(calls.saves[0].body.expectedRevision, 3);
  assert.ok(document.body.textContent.includes('Nic nie zapisano'));
  // The refreshed series replaces the shown one; the stale choice is dropped.
  assert.equal(reads, 2);
  assert.equal(symbolSelect().value, 's7');
  assert.equal(
    document.querySelector('section[aria-label="Karuzela pozycji serii"] h4')
      .textContent,
    'Spin 1 · #101',
  );
  await act(async () => root.unmount());
});

test('an API refusal of the symbol is surfaced and nothing changes', async () => {
  const { client } = fakeClient({
    setSuperGameSeriesSuperSymbol: async () => ({
      error: {
        code: 'SUPER_SYMBOL_NOT_ORDINARY',
        details: {},
        message: 'not ordinary',
      },
    }),
  });
  const { root } = await mount(client, { seriesId: 'series-100' });
  await press('1');
  await press('Enter');
  assert.ok(document.body.textContent.includes('SUPER_SYMBOL_NOT_ORDINARY'));
  assert.equal(symbolSelect().value, 's1');
  await act(async () => root.unmount());
});

// --- audit round 1: late answers, filters, load generations, symbols ------

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, reject, resolve };
}

function seriesAt(trigger, overrides = {}) {
  return series({
    endSequenceNumber: trigger + 20,
    id: `series-${trigger}`,
    retriggerSequenceNumbers: [],
    startSequenceNumber: trigger + 1,
    triggerSequenceNumber: trigger,
    ...overrides,
  });
}

function boardsFor(item) {
  const boards = [];
  for (
    let n = item.triggerSequenceNumber;
    n <= item.endSequenceNumber;
    n += 1
  ) {
    boards.push({
      assetMode: 'operational_review',
      boardChecksumSha256: `checksum-${n}`,
      importJobId: 'job-1',
      missing: false,
      recognizedBoardId: null,
      reviewItemId: `item-${n}`,
      role: n === item.triggerSequenceNumber ? 'trigger' : 'spin',
      sequenceNumber: n,
      spinIndex:
        n === item.triggerSequenceNumber
          ? null
          : n - item.triggerSequenceNumber,
      status: 'accepted',
    });
  }
  return { boards, series: item, superGameState: FRESH };
}

/** A fake client backed by a small in-memory series store. */
function storeClient(initial, overrides = {}, pageSize = 50) {
  const store = new Map(initial.map((item) => [item.id, item]));
  const calls = { boards: 0, lists: [], saves: [], symbols: 0 };
  const base = fakeClient().client;
  return {
    calls,
    store,
    client: {
      ...base,
      listSuperGameSeries: async (gameId, query) => {
        calls.lists.push(query);
        let items = [...store.values()].sort(
          (a, b) => a.triggerSequenceNumber - b.triggerSequenceNumber,
        );
        if (query.defined === true)
          items = items.filter((item) => item.superSymbolId !== null);
        if (query.defined === false)
          items = items.filter((item) => item.superSymbolId === null);
        if (query.cursor)
          items = items.filter(
            (item) => item.triggerSequenceNumber > Number(query.cursor),
          );
        const limit = Math.min(query.limit ?? 50, pageSize);
        const pageItems = items.slice(0, limit);
        return {
          data: {
            items: pageItems,
            nextCursor:
              items.length > limit
                ? String(pageItems.at(-1).triggerSequenceNumber)
                : null,
            superGameKind: 'wild_super_spins',
            superGameState: FRESH,
          },
        };
      },
      listSuperGameSeriesBoards: async (gameId, id) => {
        calls.boards += 1;
        return { data: boardsFor(store.get(id)) };
      },
      listSymbols: async () => {
        calls.symbols += 1;
        return { data: SYMBOLS };
      },
      setSuperGameSeriesSuperSymbol: async (gameId, id, body) => {
        calls.saves.push({ body, id });
        const current = store.get(id);
        const updated = {
          ...current,
          revision: current.revision + 1,
          superSymbolId: body.symbolId,
        };
        store.set(id, updated);
        return { data: updated };
      },
      ...overrides,
    },
  };
}

function Harness({ client, controller, initialSeriesId }) {
  const [seriesId, setSeriesId] = React.useState(initialSeriesId);
  // Lets a test change the opened series like browser history does.
  controller.setSeriesId = setSeriesId;
  return React.createElement(SuperGameSeriesWorkspace, {
    apiBaseUrl: 'http://127.0.0.1:8000',
    client,
    gameId: 'game-1',
    onSeriesChange: setSeriesId,
    seriesId,
  });
}

async function mountHarness(client, initialSeriesId = null, controller = {}) {
  const container = document.getElementById('root');
  container.replaceChildren();
  const root = createRoot(container);
  await act(async () =>
    root.render(
      React.createElement(Harness, { client, controller, initialSeriesId }),
    ),
  );
  await settle();
  await settle();
  return root;
}

const heading = () =>
  document.querySelector('section[aria-label="Karuzela pozycji serii"] h4')
    ?.textContent;
const openButtons = () =>
  [...document.querySelectorAll('button')].filter(
    (node) => node.textContent.trim() === 'Otwórz',
  );
const rowTriggers = () =>
  [...document.querySelectorAll('tbody tr td:first-child')].map(
    (node) => node.textContent,
  );

async function choose(node, value) {
  const setter = Object.getOwnPropertyDescriptor(
    dom.window.HTMLSelectElement.prototype,
    'value',
  ).set;
  await act(async () => {
    setter.call(node, value);
    node.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
  });
  await settle();
}
const definedFilter = () =>
  [...document.querySelectorAll('select')].find((node) =>
    [...node.options].some((option) => option.value === 'undefined'),
  );

for (const variant of ['success', 'conflict', 'network error']) {
  test(`a delayed save of series A (${variant}) never touches the opened series B`, async () => {
    const pending = deferred();
    const { calls, client, store } = storeClient(
      [seriesAt(100), seriesAt(200)],
      { setSuperGameSeriesSuperSymbol: () => pending.promise },
    );
    const root = await mountHarness(client, 'series-100');
    await press('4');
    await press('Enter');
    // The save of A is in flight: leave A and open B.
    await click(button('Lista serii'));
    await click(openButtons()[1]);
    assert.equal(heading(), 'Wyzwalacz · #200');
    const boardReads = calls.boards;

    await act(async () => {
      if (variant === 'success') {
        pending.resolve({
          data: {
            ...store.get('series-100'),
            revision: 4,
            superSymbolId: 's4',
          },
        });
      } else if (variant === 'conflict') {
        pending.resolve({
          error: {
            code: 'SUPER_GAME_SERIES_REVISION_CONFLICT',
            details: {},
            message: 'conflict',
          },
        });
      } else {
        pending.reject(new Error('network'));
      }
    });
    await settle();
    await settle();

    // B is intact: still B, interactive, no message and no extra series read.
    assert.equal(heading(), 'Wyzwalacz · #200');
    assert.ok(!document.body.textContent.includes('Wczytuję serię'));
    assert.ok(!document.body.textContent.includes('Zapisano super symbol'));
    assert.ok(!document.body.textContent.includes('Nic nie zapisano'));
    assert.ok(!document.body.textContent.includes('przerwane'));
    assert.equal(symbolSelect().value, '');
    assert.equal(calls.boards, boardReads);
    await press('ArrowRight');
    assert.equal(heading(), 'Spin 1 · #201');
    await press('2');
    assert.equal(symbolSelect().value, 's2');
    await act(async () => root.unmount());
  });
}

test('setting a symbol removes the series from the "Do zdefiniowania" list and the list is read again', async () => {
  const { calls, client } = storeClient([seriesAt(100), seriesAt(200)]);
  const root = await mountHarness(client);
  await choose(definedFilter(), 'undefined');
  assert.deepEqual(rowTriggers(), ['#100', '#200']);
  const listReadsBefore = calls.lists.length;

  await click(openButtons()[0]);
  await press('2');
  await press('Enter');
  assert.equal(calls.saves.length, 1);
  await click(button('Lista serii'));
  await settle();
  assert.deepEqual(rowTriggers(), ['#200']);
  assert.equal(
    document.querySelector('[data-testid="undefined-series-count"] strong')
      .textContent,
    '1',
  );
  // The success path read the list (and the counter) again with its filters.
  assert.ok(calls.lists.length >= listReadsBefore + 2);
  await act(async () => root.unmount());
});

test('clearing a symbol removes the series from the "Z super symbolem" list', async () => {
  const { client } = storeClient([
    seriesAt(100, { superSymbolId: 's1' }),
    seriesAt(200, { superSymbolId: 's2' }),
  ]);
  const root = await mountHarness(client);
  await choose(definedFilter(), 'defined');
  assert.deepEqual(rowTriggers(), ['#100', '#200']);
  await click(openButtons()[0]);
  await click(button('Wyczyść symbol'));
  await press('Enter');
  assert.ok(document.body.textContent.includes('Wyczyszczono super symbol'));
  await click(button('Lista serii'));
  await settle();
  assert.deepEqual(rowTriggers(), ['#200']);
  await act(async () => root.unmount());
});

test('a late "Wczytaj kolejne" page from before a refresh is not appended', async () => {
  const late = deferred();
  const base = storeClient(
    [seriesAt(100), seriesAt(200), seriesAt(300)],
    {},
    2,
  );
  const inner = base.client.listSuperGameSeries;
  let moreRequests = 0;
  base.client.listSuperGameSeries = (gameId, query) => {
    if (query.cursor) {
      moreRequests += 1;
      return late.promise;
    }
    return inner(gameId, query);
  };
  const root = await mountHarness(base.client);
  assert.deepEqual(rowTriggers(), ['#100', '#200']);

  await click(button('Wczytaj kolejne'));
  assert.equal(moreRequests, 1);
  await click(button('Odśwież listę'));
  assert.deepEqual(rowTriggers(), ['#100', '#200']);

  await act(async () =>
    late.resolve({
      data: {
        items: [seriesAt(300)],
        nextCursor: null,
        superGameKind: 'wild_super_spins',
        superGameState: STALE,
      },
    }),
  );
  await settle();
  assert.deepEqual(rowTriggers(), ['#100', '#200']);
  assert.ok(button('Wczytaj kolejne'));
  // The stale page's generation state was not applied either.
  assert.ok(
    !document.body.textContent.includes('Serie w trakcie przeliczania'),
  );
  await act(async () => root.unmount());
});

test('a late failed "Wczytaj kolejne" after a refresh shows no error', async () => {
  const late = deferred();
  const base = storeClient(
    [seriesAt(100), seriesAt(200), seriesAt(300)],
    {},
    2,
  );
  const inner = base.client.listSuperGameSeries;
  base.client.listSuperGameSeries = (gameId, query) =>
    query.cursor ? late.promise : inner(gameId, query);
  const root = await mountHarness(base.client);
  await click(button('Wczytaj kolejne'));
  await click(button('Odśwież listę'));
  await act(async () => late.reject(new Error('network')));
  await settle();
  assert.ok(!document.body.textContent.includes('przerwane'));
  assert.deepEqual(rowTriggers(), ['#100', '#200']);
  await act(async () => root.unmount());
});

test('a failed symbol catalog is shown, can be retried and is retried by the list refresh', async () => {
  let attempts = 0;
  const { client } = storeClient([seriesAt(100)], {
    listSymbols: async () => {
      attempts += 1;
      return attempts <= 2
        ? {
            error: {
              code: 'BOOM',
              details: {},
              message: 'Katalog niedostępny',
            },
          }
        : { data: SYMBOLS };
    },
  });
  const root = await mountHarness(client, 'series-100');
  const alert = () =>
    [...document.querySelectorAll('[role="alert"]')].find((node) =>
      node.textContent.includes('Katalog niedostępny'),
    );
  assert.ok(alert());
  assert.equal(attempts, 1);

  await click(button('Spróbuj ponownie'));
  assert.equal(attempts, 2);
  assert.ok(alert());
  // From the list, "Odśwież listę" retries the symbols too.
  await click(button('Lista serii'));
  await click(button('Odśwież listę'));
  assert.equal(attempts, 3);
  assert.equal(alert(), undefined);
  await act(async () => root.unmount());
});

test('the board image is bound to the reading checksum and view revision', async () => {
  const polygon = [
    { x: 0, y: 0 },
    { x: 1, y: 0 },
    { x: 1, y: 1 },
  ];
  const codes = Array.from({ length: 15 }, () => 'S1');
  codes[0] = 'MUMIA';
  codes[6] = 'MUMIA';
  codes[14] = 'MUMIA';
  const { client } = storeClient([seriesAt(100)], {
    boardSearchBoardViewUrl: (gameId, sequence, checksum, revision) =>
      `http://127.0.0.1:8000/${sequence}/${checksum}?rev=${revision ?? ''}`,
    getBoardSearchBoardDetail: async (gameId, sequence) => ({
      data: {
        boardChecksumSha256: `reading-${sequence}`,
        sequenceNumber: sequence,
        symbolCodes: codes,
        view: {
          cellPolygons: Array.from({ length: 15 }, () => polygon),
          height: 300,
          revision: 'rev-9',
          width: 500,
        },
      },
    }),
  });
  const root = await mountHarness(client, 'series-100');
  const image = document.querySelector('img');
  assert.ok(image.src.includes('/100/reading-100?rev=rev-9'), image.src);
  assert.equal(document.querySelectorAll('svg polygon[data-cell]').length, 3);
  await act(async () => root.unmount());
});

// --- audit round 2: history navigation and retrying a failed page ----------

for (const variant of ['conflict', 'refusal', 'success']) {
  test(`a delayed save of A (${variant}) after the series changed through history leaves B alone`, async () => {
    const pending = deferred();
    const controller = {};
    const { calls, client } = storeClient([seriesAt(100), seriesAt(200)], {
      setSuperGameSeriesSuperSymbol: () => pending.promise,
    });
    const root = await mountHarness(client, 'series-100', controller);
    await press('4');
    await press('Enter');

    // Browser history changes the `seriesId` prop without openSeries/closeSeries.
    await act(async () => controller.setSeriesId('series-200'));
    await settle();
    await settle();
    assert.equal(heading(), 'Wyzwalacz · #200');
    await press('5');
    assert.equal(symbolSelect().value, 's5');
    const boardReads = calls.boards;

    await act(async () => {
      if (variant === 'conflict') {
        pending.resolve({
          error: {
            code: 'SUPER_GAME_SERIES_REVISION_CONFLICT',
            details: {},
            message: 'conflict',
          },
        });
      } else if (variant === 'refusal') {
        pending.resolve({
          error: {
            code: 'SUPER_SYMBOL_NOT_ORDINARY',
            details: {},
            message: 'not ordinary',
          },
        });
      } else {
        pending.resolve({
          data: { ...seriesAt(100), revision: 4, superSymbolId: 's4' },
        });
      }
    });
    await settle();
    await settle();

    // B keeps its unsaved candidate, was not re-read and shows no message.
    assert.equal(heading(), 'Wyzwalacz · #200');
    assert.equal(symbolSelect().value, 's5');
    assert.equal(calls.boards, boardReads);
    assert.ok(!document.body.textContent.includes('Nic nie zapisano'));
    assert.ok(!document.body.textContent.includes('NOT_ORDINARY'));
    assert.ok(!document.body.textContent.includes('Zapisano super symbol'));
    await act(async () => root.unmount());
  });
}

test('a failed "Wczytaj kolejne" can be retried for the same cursor', async () => {
  let failures = 1;
  const base = storeClient(
    [seriesAt(100), seriesAt(200), seriesAt(300)],
    {},
    2,
  );
  const inner = base.client.listSuperGameSeries;
  const cursors = [];
  base.client.listSuperGameSeries = async (gameId, query) => {
    if (query.cursor) {
      cursors.push(query.cursor);
      if (failures > 0) {
        failures -= 1;
        return {
          error: { code: 'BOOM', details: {}, message: 'Strona niedostępna' },
        };
      }
    }
    return inner(gameId, query);
  };
  const root = await mountHarness(base.client);
  assert.deepEqual(rowTriggers(), ['#100', '#200']);

  await click(button('Wczytaj kolejne'));
  assert.ok(document.body.textContent.includes('Strona niedostępna'));
  assert.deepEqual(rowTriggers(), ['#100', '#200']);

  await click(button('Ponów wczytanie'));
  assert.deepEqual(cursors, ['200', '200']);
  assert.deepEqual(rowTriggers(), ['#100', '#200', '#300']);
  assert.ok(!document.body.textContent.includes('Strona niedostępna'));
  await act(async () => root.unmount());
});
