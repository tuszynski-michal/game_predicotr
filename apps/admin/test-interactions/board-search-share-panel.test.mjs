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
  'HTMLInputElement',
  'HTMLSelectElement',
  'Element',
  'Event',
  'MouseEvent',
  'KeyboardEvent',
  'localStorage',
  'navigator',
]) {
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const { createRoot } = await import('react-dom/client');
const { BoardSearchSharePanel } =
  await import('../src/features/board-search/board-search-share-panel.tsx');

after(() => dom.window.close());

const gameId = '11111111-1111-4111-8111-111111111111';
const future = new Date(Date.now() + 8 * 60 * 60 * 1000).toISOString();

function session(sessionId, overrides = {}) {
  return {
    createdAt: new Date().toISOString(),
    expiresAt: future,
    failedAttempts: 0,
    gameId,
    label: null,
    lastUnlockedAt: null,
    lockedAt: null,
    ready: true,
    revokedAt: null,
    sessionId,
    shareUrl: `https://share.trycloudflare.com/board-search?share=${sessionId}`,
    status: 'active',
    ...overrides,
  };
}

async function settle() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

async function eventually(predicate, label) {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    if (predicate()) return;
    await settle();
  }
  assert.fail(label);
}

async function click(node) {
  assert.ok(node, 'button exists');
  await act(async () =>
    node.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })),
  );
}

function button(text) {
  return [...document.querySelectorAll('button')].find(
    (node) => node.textContent.trim() === text,
  );
}

async function render(client, onReplay = () => {}) {
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(BoardSearchSharePanel, { client, gameId, onReplay }),
    ),
  );
  return root;
}

test('creating a link shows the link and the code, lists it and keeps the code locally', async (context) => {
  context.after(() => dom.window.localStorage.clear());
  const sessions = [
    session('22222222-2222-4222-8222-222222222222', { status: 'revoked' }),
  ];
  const created = [];
  const copied = [];
  Object.defineProperty(dom.window.navigator, 'clipboard', {
    configurable: true,
    value: { writeText: async (text) => copied.push(text) },
  });
  const client = {
    createBoardSearchShareSession: async (body) => {
      created.push(body);
      const fresh = session('33333333-3333-4333-8333-333333333333', {
        label: body.label,
      });
      sessions.unshift(fresh);
      return { data: { accessCode: 'ABCD-EFGH', session: fresh } };
    },
    listBoardSearchShareSessions: async (options) => {
      assert.deepEqual(options, { gameId });
      return { data: { sessions: [...sessions] } };
    },
    revokeBoardSearchShareSession: async () => ({ data: {} }),
  };
  const root = await render(client);
  assert.equal(
    document.querySelector('.boardSearchSharePanel'),
    null,
    'closed at first',
  );
  await click(button('Udostępnij online'));
  await eventually(
    () => document.querySelector('.boardSearchShareEmpty'),
    'empty list',
  );

  const label = document.querySelector('.boardSearchShareCreate input');
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(
      dom.window.HTMLInputElement.prototype,
      'value',
    ).set;
    setter.call(label, 'Dla Ani');
    label.dispatchEvent(new dom.window.Event('input', { bubbles: true }));
  });
  assert.equal(
    document.querySelector('.boardSearchShareCreate select').value,
    '480',
  );
  await click(button('Utwórz link'));
  await eventually(
    () => document.querySelector('.boardSearchShareItemFresh') !== null,
    'the new link is listed',
  );
  assert.deepEqual(created, [
    { gameId, label: 'Dla Ani', lifetimeMinutes: 480 },
  ]);
  const fresh = document.querySelector('.boardSearchShareItemFresh');
  assert.match(fresh.textContent, /ABCD-EFGH/);
  assert.match(fresh.textContent, /board-search\?share=3333/);
  assert.match(
    dom.window.localStorage.getItem(
      'game-predictor-board-search-share-codes-v1',
    ),
    /ABCD-EFGH/,
  );
  await click(button('Kopiuj kod'));
  await click(button('Kopiuj link'));
  assert.deepEqual(copied, [
    'ABCD-EFGH',
    'https://share.trycloudflare.com/board-search?share=33333333-3333-4333-8333-333333333333',
  ]);
  assert.match(
    document.querySelector('.boardSearchShareEnded summary').textContent,
    /Zakończone linki \(1\)/,
  );
  await act(async () => root.unmount());
});

test('stopping a link needs a second click and forgets its code', async (context) => {
  context.after(() => dom.window.localStorage.clear());
  const id = '44444444-4444-4444-8444-444444444444';
  dom.window.localStorage.setItem(
    'game-predictor-board-search-share-codes-v1',
    JSON.stringify({ [id]: { accessCode: 'WXYZ-2345', expiresAt: future } }),
  );
  let current = session(id);
  const revoked = [];
  const client = {
    createBoardSearchShareSession: async () => {
      throw new Error('not in this test');
    },
    listBoardSearchShareSessions: async () => ({
      data: { sessions: [current] },
    }),
    revokeBoardSearchShareSession: async (sessionId) => {
      revoked.push(sessionId);
      current = session(id, {
        status: 'revoked',
        shareUrl: null,
        ready: false,
      });
      return { data: current };
    },
  };
  const root = await render(client);
  await click(button('Udostępnij online'));
  await eventually(
    () => /WXYZ-2345/.test(document.body.textContent),
    'cached code shown',
  );
  await click(button('Zatrzymaj'));
  assert.deepEqual(revoked, [], 'the first click only asks for confirmation');
  await click(button('Anuluj'));
  await click(button('Zatrzymaj'));
  await click(button('Potwierdź zatrzymanie'));
  await eventually(() => revoked.length === 1, 'revoked');
  await eventually(
    () => /Brak aktywnych linków/.test(document.body.textContent),
    'no active links',
  );
  assert.deepEqual(revoked, [id]);
  assert.equal(
    dom.window.localStorage.getItem(
      'game-predictor-board-search-share-codes-v1',
    ),
    null,
  );
  await act(async () => root.unmount());
});

test('a failed public ingress is explained and creates nothing', async () => {
  const client = {
    createBoardSearchShareSession: async () => ({
      error: { code: 'REVIEWER_INGRESS_NOT_READY', message: 'x' },
    }),
    listBoardSearchShareSessions: async () => ({ data: { sessions: [] } }),
    revokeBoardSearchShareSession: async () => ({ data: {} }),
  };
  const root = await render(client);
  await click(button('Udostępnij online'));
  await eventually(() => button('Utwórz link') !== undefined, 'form');
  await click(button('Utwórz link'));
  await eventually(
    () =>
      document.querySelector('.boardSearchSharePanel [role="alert"]') !== null,
    'error shown',
  );
  assert.match(
    document.querySelector('.boardSearchSharePanel [role="alert"]').textContent,
    /publicznego adresu Reviewera/,
  );
  assert.equal(document.querySelector('.boardSearchShareItem'), null);
  await act(async () => root.unmount());
});

test("another game's panel keeps this game's codes", async (context) => {
  context.after(() => dom.window.localStorage.clear());
  const otherGameLink = '55555555-5555-4555-8555-555555555555';
  dom.window.localStorage.setItem(
    'game-predictor-board-search-share-codes-v1',
    JSON.stringify({
      [otherGameLink]: { accessCode: 'KEEP-2345', expiresAt: future },
    }),
  );
  const client = {
    createBoardSearchShareSession: async () => ({ data: undefined }),
    listBoardSearchShareSessions: async () => ({
      data: {
        sessions: [
          session('66666666-6666-4666-8666-666666666666', {
            status: 'revoked',
          }),
        ],
      },
    }),
    revokeBoardSearchShareSession: async () => ({ data: {} }),
  };
  const root = await render(client);
  await click(button('Udostępnij online'));
  await eventually(
    () => document.querySelector('.boardSearchShareEnded') !== null,
    'list',
  );
  assert.match(
    dom.window.localStorage.getItem(
      'game-predictor-board-search-share-codes-v1',
    ),
    /KEEP-2345/,
  );
  await act(async () => root.unmount());
});

test('a code created while the panel unmounts is still stored', async (context) => {
  context.after(() => dom.window.localStorage.clear());
  let resolveCreate;
  const client = {
    createBoardSearchShareSession: () =>
      new Promise((resolve) => {
        resolveCreate = resolve;
      }),
    listBoardSearchShareSessions: async () => ({ data: { sessions: [] } }),
    revokeBoardSearchShareSession: async () => ({ data: {} }),
  };
  const root = await render(client);
  await click(button('Udostępnij online'));
  await eventually(() => button('Utwórz link') !== undefined, 'form');
  await click(button('Utwórz link'));
  await act(async () => root.unmount());
  const id = '77777777-7777-4777-8777-777777777777';
  await act(async () => {
    resolveCreate({ data: { accessCode: 'LATE-2345', session: session(id) } });
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
  assert.match(
    dom.window.localStorage.getItem(
      'game-predictor-board-search-share-codes-v1',
    ) ?? '',
    /LATE-2345/,
  );
});

test('a link shows its grouped query log with the pattern and replays an entry', async () => {
  const id = '88888888-8888-4888-8888-888888888888';
  const eventId = '99999999-9999-4999-8999-999999999999';
  const replayed = [];
  const pages = [];
  const deleted = [];
  const client = {
    createBoardSearchShareSession: async () => ({ data: undefined }),
    deleteBoardSearchShareQuery: async (entryId, options) => {
      deleted.push([entryId, options]);
      return { data: undefined };
    },
    listBoardSearchShareQueries: async (sessionId, options) => {
      pages.push([sessionId, options]);
      return {
        data: {
          entries: [
            {
              gameId,
              id: eventId,
              kind: 'search',
              occurredAt: '2026-10-02T12:30:00Z',
              occurrenceTimes: ['2026-10-02T12:30:00Z', '2026-10-01T08:05:00Z'],
              outcomeCode: 'ok',
              request: {
                cells: ['0:cherry', '3:?'],
                limit: 5,
                scope: 'all_searchable',
              },
              resultSummary: { firstSequenceNumbers: [7], resultCount: 1 },
              sessionId,
            },
          ],
          nextCursor: null,
        },
      };
    },
    listBoardSearchShareSessions: async () => ({
      data: { sessions: [session(id)] },
    }),
    listSymbols: async () => ({
      data: [
        {
          code: 'cherry',
          id: 'symbol-cherry',
          imagePath: null,
          name: 'Wiśnia',
        },
      ],
    }),
    revokeBoardSearchShareSession: async () => ({ data: {} }),
    symbolImageAssetUrl: () => 'http://127.0.0.1:8000/symbol.png',
  };
  const root = await render(client, (event) => replayed.push(event));
  await click(button('Udostępnij online'));
  await eventually(
    () => button('Dziennik zapytań') !== undefined,
    'log toggle',
  );
  await click(button('Dziennik zapytań'));
  await eventually(
    () => document.querySelector('.boardSearchShareQuery') !== null,
    'log entry',
  );
  // TASK-0816: one entry per pattern, with every time it was searched.
  assert.deepEqual(pages, [
    [id, { groupByPattern: true, kind: 'search', limit: 10 }],
  ]);
  const entry = document.querySelector('.boardSearchShareQuery');
  const times = [...entry.querySelectorAll('.boardSearchShareQueryTimes time')];
  assert.deepEqual(
    times.map((time) => time.getAttribute('datetime')),
    ['2026-10-02T12:30:00Z', '2026-10-01T08:05:00Z'],
  );
  assert.match(
    entry.querySelector('.boardSearchShareQueryTimes').textContent,
    /\d, \d/,
  );
  const cells = [...entry.querySelectorAll('.boardSearchShareMiniCell')];
  assert.equal(cells.length, 15);
  assert.equal(cells[0].title, 'Wiśnia');
  assert.equal(cells[3].textContent, '?');
  await click(button('Odtwórz w wyszukiwarce'));
  assert.deepEqual(replayed, [eventId]);
  await click(button('Usuń'));
  await click(button('Usuń wszystkie (2)'));
  await eventually(
    () => document.querySelector('.boardSearchShareQuery') === null,
    'entry removed',
  );
  assert.deepEqual(deleted, [[eventId, { wholePattern: true }]]);
  await act(async () => root.unmount());
});
