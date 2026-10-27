import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
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
  'Element',
  'Node',
  'Event',
  'MouseEvent',
  'KeyboardEvent',
  'Image',
])
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
dom.window.HTMLDialogElement.prototype.showModal = function () {
  this.setAttribute('open', '');
};
dom.window.HTMLDialogElement.prototype.close = function () {
  this.removeAttribute('open');
};
const { createRoot } = await import('react-dom/client');
const { BoardSearchWorkspace } =
  await import('../src/board-search-workspace.tsx');
after(() => dom.window.close());
beforeEach(() => window.localStorage.clear());
let liveRoot = null;
afterEach(async () => {
  if (liveRoot !== null) await unmount(liveRoot);
});
const pattern = (code) => ({ cells: [{ cellIndex: 0, symbolCode: code }] });
const symbols = ['A', 'B'].map((code, index) => ({
  id: code,
  code,
  name: code,
  mobileCode: index + 1,
  displayOrder: index,
  imagePath: null,
  status: 'active',
}));
const board = (sequenceNumber) => ({
  assetMode: 'operational_review',
  boardChecksumSha256: String(sequenceNumber).padStart(64, 'a'),
  reviewItemId: null,
  importJobId: null,
  recognizedBoardId: null,
  sequenceNumber,
  status: 'pending',
  score: {
    score: 100,
    exactMatchCount: 1,
    alternativeMatchCount: 0,
    mismatchCount: 0,
    unknownCount: 0,
  },
});
const single = (results = [board(6), board(2)]) => ({
  gameId: 'g',
  scope: 'all_searchable',
  queryCellCount: 1,
  results,
});
const multi = (count) => ({
  gameId: 'g',
  scope: 'all_searchable',
  queryCellCount: count,
  patternCount: count,
  results: [6, 2].map((start) => ({
    startSequenceNumber: start,
    endSequenceNumber: ((start + count - 2) % 6) + 1,
    score: { ...board(1).score, score: 87.5 },
    boards: Array.from({ length: count }, (_, index) =>
      board(((start + index - 1) % 6) + 1),
    ),
  })),
});
const range = (options) => ({
  gameId: 'g',
  dataSource: 'operational_review',
  dataFingerprintSha256: 'a'.repeat(64),
  startSequenceNumber: options.startSequenceNumber,
  requestedSpinCount: options.spinCount,
  evaluatedSpinCount: options.spinCount,
  sequenceLength: 6,
  wrappedAtSequenceEnd: true,
  startBoardStatus: null,
  rules: { rulesVersionId: 'r', rulesVersion: 1, spinCost: 0 },
  completeness: {
    completeBoardCount: 0,
    missingBoardCount: options.spinCount,
    partialBoardCount: 0,
  },
  rows: [],
  summary: {
    balanceCredits: 0,
    recognizedPayoutCredits: 0,
    spinCostCredits: 0,
  },
});
function fixture(overrides = {}) {
  const calls = {
    single: [],
    multi: [],
    range: [],
    detail: [],
    correction: [],
  };
  const api = {
    listSymbols: async () => ({ data: symbols }),
    symbolImageAssetUrl: () => '',
    boardSearchBoardViewUrl: (_game, number) => `/view/${number}`,
    searchGameBoards: async (_id, request) => {
      calls.single.push(request);
      return { data: single(), searchContextId: 'single-context' };
    },
    searchGameBoardSequence: async (_id, request) => {
      calls.multi.push(request);
      return {
        data: multi(request.patterns.length),
        searchContextId: 'full-context',
      };
    },
    getBoardSearchApproximateWin: async (_id, request) => {
      calls.range.push(request);
      return { data: range(request) };
    },
    getBoardSearchBoardDetail: async (_id, number) => {
      calls.detail.push(number);
      return {
        data: {
          gameId: 'g',
          sequenceNumber: number,
          boardStatus: 'accepted',
          boardChecksumSha256: 'c'.repeat(64),
          dataSource: 'operational_review',
          documentStale: false,
          view: null,
          rules: { rulesVersionId: 'r', spinCost: 0 },
          matches: [],
          countMatches: [],
          payoutCredits: 0,
          payoutKind: 'none',
          symbolCodes: Array(15).fill('A'),
          cells: Array.from({ length: 15 }, (_, cellIndex) => ({
            cellIndex,
            assignedSymbolCode: 'A',
            qualityIssue: null,
            reviewState: 'approved',
            cellVersion: 'a'.repeat(64),
          })),
        },
      };
    },
    correctBoardSearchCell: async (...args) => {
      calls.correction.push(args);
      return {
        data: {
          saved: true,
          changed: true,
          sequenceNumber: args[1],
          cellIndex: args[2],
          cellVersion: 'b'.repeat(64),
        },
      };
    },
    ...overrides,
  };
  return { api, calls };
}
const button = (text) =>
  [...document.querySelectorAll('button')].find(
    (node) => node.textContent.trim() === text,
  );
async function click(node) {
  assert.ok(node, 'button exists');
  assert.notEqual(node.disabled, true, `enabled: ${node.textContent}`);
  await act(async () =>
    node.dispatchEvent(new MouseEvent('click', { bubbles: true })),
  );
}
async function waitFor(predicate, label = 'UI state') {
  for (let index = 0; index < 150; index++) {
    if (predicate()) return;
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 5));
    });
  }
  assert.fail(label);
}
async function mount(api, props = {}) {
  const root = createRoot(document.getElementById('root'));
  liveRoot = root;
  await act(async () =>
    root.render(
      props.strict
        ? React.createElement(
            React.StrictMode,
            null,
            React.createElement(BoardSearchWorkspace, {
              client: api,
              gameId: 'g',
              ...props,
            }),
          )
        : React.createElement(BoardSearchWorkspace, {
            client: api,
            gameId: 'g',
            ...props,
          }),
    ),
  );
  await waitFor(() => document.querySelector('.boardSearchSymbolButton'));
  return root;
}
async function unmount(root) {
  await act(async () => root.unmount());
  if (liveRoot === root) liveRoot = null;
}
async function search() {
  await waitFor(
    () => button('Szukaj plansz')?.disabled === false,
    'search enabled',
  );
  await click(button('Szukaj plansz'));
  await waitFor(
    () =>
      button('Szukaj plansz')?.disabled === false ||
      button('Trwa obliczanie wygranej…'),
    'search settled',
  );
}
const symbol = (code) =>
  document.querySelector(`.boardSearchSymbolButton[title^="${code}"]`) ??
  [...document.querySelectorAll('.boardSearchSymbolButton')].find(
    (node) => node.querySelector('strong')?.textContent === code,
  );
const key = 'board-search-sequence:v1:admin:g';
const saved = (
  patterns,
  {
    submitted = patterns,
    activeIndex = patterns.length - 1,
    selected = 6,
  } = {},
) => ({
  version: 1,
  scope: 'admin:g',
  patterns: patterns.map(({ cells }) =>
    Array.from({ length: 15 }, (_, index) => {
      const cell = cells.find((cell) => cell.cellIndex === index);
      return cell === undefined ? null : (cell.symbolCode ?? '?');
    }),
  ),
  activeIndex,
  entryOrder: 'columns',
  lastSubmitted:
    submitted === null
      ? null
      : { patterns: submitted, scope: 'all_searchable', limit: 15 },
  selectedStartSequenceNumber: selected,
});

for (const scopeKey of [undefined, 'share:test', 'panel:test:g']) {
  test(`prepare four patterns before one search: ${scopeKey ?? 'admin'}`, async () => {
    const { api, calls } = fixture();
    let root = await mount(api, { scopeKey });
    assert.equal(button('Dodaj układ').disabled, true);
    for (let index = 0; index < 4; index++) {
      await click(symbol(index % 2 ? 'B' : 'A'));
      if (index < 3) await click(button('Dodaj układ'));
    }
    assert.equal(calls.single.length, 0);
    assert.equal(calls.multi.length, 0);
    assert.equal(button('Dodaj układ').disabled, true);
    await unmount(root);
    root = await mount(api, { scopeKey });
    assert.equal(button('Układ 4').getAttribute('aria-pressed'), 'true');
    assert.equal(
      calls.multi.length,
      0,
      'unsubmitted drafts do not search on restore',
    );
    await search();
    assert.equal(calls.single.length, 0);
    assert.equal(calls.multi.length, 1);
    assert.equal(calls.multi[0].limit, 40);
    assert.deepEqual(
      calls.multi[0].patterns,
      ['A', 'B', 'A', 'B'].map(pattern),
    );
    await unmount(root);
  });
}

const photo = () =>
  document.querySelector('[aria-label="Przegląd zdjęć dopasowania"]');
const photoNumber = () =>
  Number(
    photo()
      .querySelector('[role="status"]')
      .textContent.match(/Zdjęcie #(\d+)/)[1],
  );

test('four matched photos, fifteen before and fifteen after, same ranking and win anchor', async () => {
  const { api, calls } = fixture({
    searchGameBoardSequence: async () => ({
      data: {
        ...multi(4),
        results: [240, 100].map((start) => ({
          startSequenceNumber: start,
          endSequenceNumber: start + 3,
          score: board(1).score,
          boards: Array.from({ length: 4 }, (_, index) => board(start + index)),
        })),
      },
    }),
  });
  const root = await mount(api, {
    replay: {
      id: 'four',
      cells: pattern('A').cells,
      patterns: Array(4).fill(pattern('A')),
      scope: 'all_searchable',
      limit: 15,
    },
  });
  await waitFor(() => photo());
  await waitFor(() => calls.range.length > 0);
  const rangeCount = calls.range.length;
  assert.equal(calls.range.at(-1).startSequenceNumber, 243);
  assert.equal(photoNumber(), 240);
  assert.equal(button('Poprzedni układ').disabled, false);
  for (let number = 241; number <= 258; number++) {
    await click(button('Następny układ'));
    await waitFor(() => photoNumber() === number);
    assert.ok(photo().querySelector(`img[src="/view/${number}"]`));
  }
  assert.equal(button('Następny układ').disabled, true);
  assert.deepEqual(
    calls.detail,
    Array.from({ length: 15 }, (_, index) => 244 + index),
  );
  assert.equal(calls.range.length, rangeCount);
  assert.match(
    document.querySelector('.boardSearchResultMetrics').textContent,
    /#240 → #243/,
  );
  for (let number = 257; number >= 240; number--) {
    await click(button('Poprzedni układ'));
    assert.equal(photoNumber(), number);
  }
  assert.equal(button('Poprzedni układ').disabled, false);
  assert.equal(calls.detail.length, 15, 'backtracking uses the loaded photos');
  for (let number = 239; number >= 225; number--) {
    await click(button('Poprzedni układ'));
    await waitFor(() => photoNumber() === number);
    assert.ok(photo().querySelector(`img[src="/view/${number}"]`));
  }
  assert.equal(button('Poprzedni układ').disabled, true);
  assert.match(photo().textContent, /Przed dopasowanym ciągiem/);
  assert.deepEqual(
    calls.detail.slice(15),
    Array.from({ length: 15 }, (_, index) => 239 - index),
  );
  for (let number = 226; number <= 258; number++) {
    await click(button('Następny układ'));
    assert.equal(photoNumber(), number);
  }
  assert.equal(
    calls.detail.length,
    30,
    'both directions reuse the loaded photos',
  );
  assert.equal(button('Następny układ').disabled, true);
  assert.equal(calls.range.length, rangeCount);
  assert.match(
    document.querySelector('.boardSearchResultMetrics').textContent,
    /#240 → #243/,
  );
  await click(button('Następna →'));
  assert.equal(
    photoNumber(),
    100,
    'another ranked match starts at its first photo',
  );
  await unmount(root);
});

for (const scopeKey of [undefined, 'share:previous', 'panel:previous:g']) {
  test(`earlier photos stop at sequence one and return to the match: ${scopeKey ?? 'admin'}`, async () => {
    const { api, calls } = fixture();
    const root = await mount(api, { scopeKey });
    await click(symbol('A'));
    await search();
    assert.equal(photoNumber(), 6);
    for (let number = 5; number >= 1; number--) {
      await click(button('Poprzedni układ'));
      await waitFor(() => photoNumber() === number);
    }
    assert.equal(button('Poprzedni układ').disabled, true);
    assert.deepEqual(calls.detail, [5, 4, 3, 2, 1]);
    for (let number = 2; number <= 6; number++) {
      await click(button('Następny układ'));
      assert.equal(photoNumber(), number);
    }
    assert.equal(calls.detail.length, 5);
    assert.equal(calls.single.length, 1);
    await unmount(root);
  });
}

test('earlier photo errors retry the same number and a late backward read cannot change another match', async () => {
  const { api } = fixture();
  const original = api.getBoardSearchBoardDetail;
  let mode = 'missing';
  let finish;
  const attempts = [];
  api.getBoardSearchBoardDetail = async (id, number) => {
    attempts.push(number);
    if (mode === 'missing')
      return { error: { code: 'NOT_FOUND', message: 'Brak planszy' } };
    if (mode === 'pending')
      return new Promise((resolve) => {
        finish = resolve;
      });
    const result = await original(id, number);
    if (mode === 'stale') result.data.documentStale = true;
    return result;
  };
  const root = await mount(api);
  await click(symbol('A'));
  await search();
  await click(button('Poprzedni układ'));
  assert.equal(photoNumber(), 6);
  assert.match(photo().textContent, /Brak planszy.*Poprzedni układ/s);
  mode = 'stale';
  await click(button('Poprzedni układ'));
  assert.equal(photoNumber(), 6);
  assert.match(photo().textContent, /nieaktualny/);
  mode = 'ok';
  await click(button('Poprzedni układ'));
  await waitFor(() => photoNumber() === 5);
  assert.deepEqual(attempts, [5, 5, 5]);
  mode = 'pending';
  await click(button('Poprzedni układ'));
  assert.equal(button('Poprzedni układ').disabled, true);
  assert.equal(button('Następny układ').disabled, true);
  await click(button('Następna →'));
  assert.equal(photoNumber(), 2);
  await act(async () => finish(await original('g', 4)));
  assert.equal(photoNumber(), 2);
  await unmount(root);
});

test('an earlier photo opens and corrects its own position without moving the win anchor', async () => {
  const { api, calls } = fixture();
  const root = await mount(api, { scopeKey: 'share:earlier-correction' });
  await click(symbol('A'));
  await search();
  await click(button('Poprzedni układ'));
  await waitFor(() => photoNumber() === 5);
  await click(button('Pokaż planszę'));
  await waitFor(() => button('Popraw symbole'));
  await click(button('Popraw symbole'));
  await click(document.querySelector('.boardSearchBoardCellTarget'));
  await click(
    document.querySelector('.boardSearchBoardCellPalette button[title="B"]'),
  );
  await waitFor(() => calls.correction.length === 1);
  assert.equal(calls.correction[0][1], 5);
  assert.equal(calls.correction[0][3].startSequenceNumber, 5);
  assert.equal(calls.correction[0][3].searchContextId, 'single-context');
  await waitFor(() => calls.range.length > 0);
  assert.equal(calls.range.at(-1).startSequenceNumber, 6);
  await unmount(root);
});

test('single pattern permits fifteen extra photos; failed or stale reads retain position and retry the same number', async () => {
  const { api, calls } = fixture();
  const original = api.getBoardSearchBoardDetail;
  let mode = 'missing';
  const attempts = [];
  api.getBoardSearchBoardDetail = async (id, number) => {
    attempts.push(number);
    if (mode === 'missing')
      return { error: { code: 'NOT_FOUND', message: 'Brak planszy' } };
    const response = await original(id, number);
    if (mode === 'stale') response.data.documentStale = true;
    return response;
  };
  const root = await mount(api);
  await click(symbol('A'));
  await search();
  assert.equal(photoNumber(), 6);
  await click(button('Następny układ'));
  assert.equal(photoNumber(), 6);
  assert.match(photo().textContent, /Brak planszy/);
  mode = 'stale';
  await click(button('Następny układ'));
  assert.equal(photoNumber(), 6);
  assert.match(photo().textContent, /nieaktualny/);
  mode = 'ok';
  for (let number = 7; number <= 21; number++) {
    await click(button('Następny układ'));
    await waitFor(() => photoNumber() === number);
  }
  assert.deepEqual(attempts.slice(0, 3), [7, 7, 7]);
  assert.equal(button('Następny układ').disabled, true);
  assert.equal(calls.single.length, 1);
  await click(button('Pokaż planszę'));
  await waitFor(() => button('Popraw symbole'));
  await click(button('Popraw symbole'));
  await waitFor(() => document.querySelector('.boardSearchBoardCellTarget'));
  await click(document.querySelector('.boardSearchBoardCellTarget'));
  await click(
    document.querySelector('.boardSearchBoardCellPalette button[title="B"]'),
  );
  await waitFor(() => calls.correction.length === 1);
  assert.equal(calls.correction[0][1], 21);
  assert.equal(calls.correction[0][3].startSequenceNumber, 21);
  assert.equal(calls.correction[0][3].searchContextId, 'single-context');
  await unmount(root);
});

test('late photo read cannot overwrite a different ranked match', async () => {
  const { api } = fixture();
  const original = api.getBoardSearchBoardDetail;
  let finish;
  api.getBoardSearchBoardDetail = () =>
    new Promise((resolve) => {
      finish = resolve;
    });
  const root = await mount(api);
  await click(symbol('A'));
  await search();
  await click(button('Następny układ'));
  assert.equal(button('Następny układ').disabled, true);
  await click(button('Następna →'));
  assert.equal(photoNumber(), 2);
  await act(async () => finish(await original('g', 7)));
  assert.equal(photoNumber(), 2);
  assert.ok(photo().querySelector('img[src="/view/2"]'));
  await unmount(root);
});

test('matched photos follow the cyclic order returned by the API', async () => {
  const { api, calls } = fixture();
  const root = await mount(api);
  await click(symbol('A'));
  await click(button('Dodaj układ'));
  await click(symbol('B'));
  await search();
  assert.equal(photoNumber(), 6);
  await click(button('Następny układ'));
  assert.equal(photoNumber(), 1);
  assert.equal(calls.detail.length, 0);
  await click(button('Następny układ'));
  assert.equal(photoNumber(), 2);
  assert.deepEqual(calls.detail, [2]);
  await unmount(root);
});

test('four badges, shared ranking, gaps, trailing slots, per-badge undo and complete reset', async () => {
  const { api, calls } = fixture();
  const root = await mount(api);
  await click(symbol('A'));
  await search();
  assert.equal(calls.single.length, 1);
  assert.equal(calls.multi.length, 0);
  await click(button('Dodaj układ'));
  assert.equal(button('Układ 2').getAttribute('aria-pressed'), 'true');
  assert.ok(
    document.querySelector('.boardSearchResults'),
    'empty tail keeps the previous effective query',
  );
  await click(symbol('B'));
  assert.match(document.body.textContent, /Wzór zmieniony/);
  await search();
  assert.deepEqual(calls.multi[0].patterns, [pattern('A'), pattern('B')]);
  assert.match(
    document.querySelector('.boardSearchResultMetrics').textContent,
    /87.5%.*#6 → #1/s,
  );
  await click(button('Układ 1'));
  assert.match(
    document.querySelector('.boardSearchResultMetrics').textContent,
    /#6 → #1/,
  );
  const rangeCount = calls.range.length;
  await click(button('Układ 2'));
  assert.equal(calls.range.length, rangeCount, 'badge sends no calculation');
  await click(button('Dodaj układ'));
  await click(symbol('A'));
  await search();
  await click(button('Dodaj układ'));
  await click(symbol('B'));
  await search();
  assert.equal(calls.multi.at(-1).patterns.length, 4);
  assert.equal(button('Dodaj układ').disabled, true);
  await click(button('Układ 2'));
  await click(symbol('A'));
  await click(button('Cofnij'));
  assert.equal(
    document.querySelectorAll('.boardSearchGrid .boardSearchCell strong')[5]
      .textContent,
    '—',
    'undo belongs to badge 2',
  );
  await click(button('Resetuj'));
  assert.equal(button('Szukaj plansz').disabled, true);
  assert.match(document.body.textContent, /Uzupełnij układ 2/);
  await click(symbol('B'));
  assert.equal(button('Szukaj plansz').disabled, false);
  await click(button('Układ 4'));
  await click(button('Resetuj'));
  await search();
  assert.equal(calls.multi.at(-1).patterns.length, 3, 'empty tail ignored');
  await click(button('Nowe szukanie'));
  assert.equal(button('Układ 2'), undefined);
  assert.equal(document.querySelector('.boardSearchResults'), null);
  assert.equal(
    JSON.parse(window.localStorage.getItem(key)).lastSubmitted,
    null,
  );
  await unmount(root);
});

test('only unknown is invalid; zero results still permit the next pattern', async () => {
  const { api } = fixture({
    searchGameBoards: async () => ({ data: single([]) }),
  });
  const root = await mount(api);
  await click(document.querySelector('.boardSearchUnknownButton'));
  assert.equal(button('Szukaj plansz').disabled, true);
  await click(symbol('A'));
  await search();
  assert.equal(button('Dodaj układ').disabled, false);
  await click(button('Dodaj układ'));
  await unmount(root);
});

test('late search cannot resurrect a cleared set or overwrite a new scope', async () => {
  let resolve;
  const { api } = fixture({
    searchGameBoards: () =>
      new Promise((done) => {
        resolve = done;
      }),
  });
  const root = await mount(api);
  await click(symbol('A'));
  await click(button('Szukaj plansz'));
  await click(button('Nowe szukanie'));
  await act(async () => resolve({ data: single() }));
  assert.equal(document.querySelector('.boardSearchResults'), null);
  assert.equal(
    JSON.parse(window.localStorage.getItem(key)).lastSubmitted,
    null,
  );
  await click(symbol('A'));
  await click(button('Szukaj plansz'));
  const old = resolve;
  await act(async () =>
    root.render(
      React.createElement(BoardSearchWorkspace, {
        client: api,
        gameId: 'g',
        scopeKey: 'share:other',
      }),
    ),
  );
  await act(async () => old({ data: single() }));
  assert.equal(document.querySelector('.boardSearchResults'), null);
  await unmount(root);
});

test('rehydrates dirty editor separately, searches last submitted snapshot and preserves selected start', async () => {
  window.localStorage.setItem(
    key,
    JSON.stringify(
      saved([pattern('B'), pattern(null)], {
        submitted: [pattern('A'), pattern('B')],
        activeIndex: 1,
        selected: 2,
      }),
    ),
  );
  const { api, calls } = fixture();
  let root = await mount(api);
  await waitFor(() => calls.multi.length === 1);
  await waitFor(() => document.querySelector('.boardSearchResults'));
  assert.deepEqual(calls.multi[0].patterns, [pattern('A'), pattern('B')]);
  assert.match(
    document.querySelector('.boardSearchResultMetrics').textContent,
    /#2 → #3/,
  );
  assert.match(document.body.textContent, /Wzór zmieniony/);
  assert.equal(
    document.querySelector('.boardSearchGrid .boardSearchCell strong')
      .textContent,
    '?',
  );
  const raw = window.localStorage.getItem(key);
  assert.doesNotMatch(
    raw,
    /full-context|searchContextId|Checksum|results|credential/,
  );
  await unmount(root);
  root = await mount(api);
  await waitFor(() => calls.multi.length === 2);
  assert.equal(button('Układ 2').getAttribute('aria-pressed'), 'true');
  await unmount(root);
});

test('replay wins over storage, preserves all patterns and consumes once', async () => {
  window.localStorage.setItem(key, JSON.stringify(saved([pattern('A')])));
  const { api, calls } = fixture();
  const consumed = [];
  const replay = {
    id: 'event',
    cells: pattern('B').cells,
    patterns: [pattern('B'), pattern('A')],
    scope: 'approved_only',
    limit: 7,
    approximateWin: null,
    boardSequenceNumber: null,
  };
  const root = await mount(api, {
    replay,
    onReplayApplied: (id) => consumed.push(id),
  });
  await waitFor(() => calls.multi.length === 1);
  assert.equal(calls.single.length, 0);
  assert.deepEqual(calls.multi[0], {
    patterns: replay.patterns,
    scope: 'approved_only',
    limit: 7,
  });
  assert.deepEqual(consumed, ['event']);
  assert.equal(button('Układ 2').getAttribute('aria-pressed'), 'true');
  await unmount(root);
});

test('corrupt/unavailable storage and archived codes are visible without losing the draft', async () => {
  window.localStorage.setItem(key, '{');
  let { api, calls } = fixture();
  let root = await mount(api);
  await waitFor(() => document.body.textContent.includes('inną wersję'));
  assert.equal(calls.single.length, 0);
  await unmount(root);
  window.localStorage.setItem(
    key,
    JSON.stringify(saved([pattern('archived')])),
  );
  ({ api, calls } = fixture());
  root = await mount(api);
  await waitFor(() =>
    document.body.textContent.includes('nie jest już aktywny'),
  );
  assert.equal(calls.single.length, 0);
  assert.match(
    document.querySelector('.boardSearchGrid').textContent,
    /archived/,
  );
  await unmount(root);
  const original = dom.window.Storage.prototype.setItem;
  dom.window.Storage.prototype.setItem = function () {
    throw new Error('quota');
  };
  try {
    ({ api } = fixture());
    window.localStorage.clear();
    root = await mount(api);
    await click(symbol('A'));
    await waitFor(() =>
      document.body.textContent.includes('poprzedni zestaw może wrócić'),
    );
    await search();
    await unmount(root);
  } finally {
    dom.window.Storage.prototype.setItem = original;
  }
});

test('calculator blocks search until every in-flight request settles, search suspends debounce', async () => {
  const pending = [];
  let finishSearch;
  const { api, calls } = fixture({
    getBoardSearchApproximateWin: (_id, options) =>
      new Promise((resolve) =>
        pending.push(() => resolve({ data: range(options) })),
      ),
  });
  const root = await mount(api);
  await click(symbol('A'));
  await search();
  await waitFor(() => pending.length === 1, 'first calculation');
  await click(button('Następna →'));
  await waitFor(() => pending.length === 2, 'second calculation');
  assert.ok(button('Trwa obliczanie wygranej…')?.disabled);
  await act(async () => pending[1]());
  assert.ok(
    button('Trwa obliczanie wygranej…')?.disabled,
    'stale first request still holds slot',
  );
  await act(async () => pending[0]());
  await waitFor(() => button('Szukaj plansz')?.disabled === false);
  api.searchGameBoards = () =>
    new Promise((resolve) => {
      finishSearch = resolve;
    });
  await click(button('Szukaj plansz'));
  await click(button('← Poprzednia'));
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 450));
  });
  assert.equal(pending.length, 2, 'no calculation during search');
  await act(async () => finishSearch({ data: single() }));
  await unmount(root);
  assert.equal(calls.single.length, 1);
});

test('earlier board correction uses its own position and full search receipt; win stays at the end', async () => {
  const { api, calls } = fixture();
  const replay = {
    id: 'two',
    cells: pattern('A').cells,
    patterns: [pattern('A'), pattern('B')],
    scope: 'all_searchable',
    limit: 15,
    approximateWin: null,
    boardSequenceNumber: null,
  };
  const root = await mount(api, { replay });
  await waitFor(() => document.querySelector('.boardSearchSequenceResults'));
  await click(button('Układ 1: #6 · 100.0%'));
  await waitFor(() => button('Popraw symbole'));
  await click(button('Popraw symbole'));
  await waitFor(() => document.querySelector('.boardSearchBoardCellTarget'));
  await click(document.querySelector('.boardSearchBoardCellTarget'));
  await click(
    document.querySelector('.boardSearchBoardCellPalette button[title="B"]'),
  );
  await waitFor(() => calls.correction.length === 1);
  assert.equal(calls.correction[0][1], 6);
  assert.equal(calls.correction[0][3].startSequenceNumber, 6);
  assert.equal(calls.correction[0][3].spinCount, undefined);
  assert.equal(calls.correction[0][3].searchContextId, 'full-context');
  await waitFor(() => calls.range.length > 0);
  assert.equal(calls.range[0].startSequenceNumber, 1);
  await unmount(root);
});

test('429 keeps previous results and typed patterns for a manual retry', async () => {
  let reject = false;
  const { api, calls } = fixture({
    searchGameBoardSequence: async () =>
      reject
        ? {
            error: {
              code: 'BOARD_SEARCH_SHARE_RATE_LIMITED',
              message: 'limit',
            },
          }
        : { data: multi(2), searchContextId: 'context' },
  });
  const root = await mount(api);
  await click(symbol('A'));
  await search();
  await click(button('Dodaj układ'));
  await click(symbol('B'));
  reject = true;
  await search();
  assert.match(
    document.body.textContent,
    /Trwa inne obliczenie lub przekroczono limit/,
  );
  assert.match(document.body.textContent, /poprzedniego udanego/);
  assert.equal(
    JSON.parse(window.localStorage.getItem(key)).selectedStartSequenceNumber,
    null,
    'the previous query selection is not attached to a different failed query',
  );
  assert.ok(document.querySelector('.boardSearchResults'));
  reject = false;
  await search();
  assert.match(
    document.querySelector('.boardSearchResultMetrics').textContent,
    /#6 → #1/,
  );
  assert.equal(calls.single.length, 1);
  await unmount(root);
});

test('management ignores sequence capability and local restore; ordinary edits retain its old receipt rules', async () => {
  window.localStorage.setItem(
    key,
    JSON.stringify(saved([pattern('A'), pattern('B')])),
  );
  const { api, calls } = fixture();
  const root = await mount(api, { fixedStakeGrosze: 500 });
  assert.equal(button('Układ 1'), undefined);
  assert.equal(calls.multi.length, 0);
  assert.equal(calls.single.length, 0);
  await click(symbol('A'));
  await search();
  assert.equal(calls.single.length, 1);
  assert.equal(calls.multi.length, 0);
  await click(symbol('B'));
  assert.equal(
    document.querySelector('.boardSearchResults'),
    null,
    'management edit invalidates old results',
  );
  assert.equal(
    JSON.parse(window.localStorage.getItem(key)).lastSubmitted.patterns.length,
    2,
    'management did not write sequence storage',
  );
  await unmount(root);
});

test('expired public access removes visible results while preserving the local draft for later access', async () => {
  let ended = false;
  const { api } = fixture({
    searchGameBoards: async () =>
      ended
        ? {
            error: {
              code: 'BOARD_SEARCH_SHARE_TOKEN_INVALID',
              message: 'expired',
            },
          }
        : { data: single() },
  });
  const root = await mount(api, { scopeKey: 'share:expired' });
  await click(symbol('A'));
  await search();
  ended = true;
  await search();
  assert.equal(document.querySelector('.boardSearchResults'), null);
  assert.match(document.querySelector('.boardSearchGrid').textContent, /A/);
  await unmount(root);
});

test('StrictMode restores once; another tab does not replace the active draft', async () => {
  window.localStorage.setItem(
    key,
    JSON.stringify(saved([pattern('A'), pattern('B')])),
  );
  const { api, calls } = fixture();
  const root = await mount(api, { strict: true });
  await waitFor(() => calls.multi.length === 1);
  await waitFor(() => document.querySelector('.boardSearchResults'));
  await act(async () =>
    window.dispatchEvent(
      new window.StorageEvent('storage', {
        key,
        newValue: JSON.stringify(saved([pattern('B')])),
      }),
    ),
  );
  assert.equal(calls.multi.length, 1);
  assert.ok(button('Układ 2'));
  await unmount(root);
});

test('v2 follow-up replay selects by end board but persists the matching start identity', async () => {
  const { api, calls } = fixture();
  const replay = {
    id: 'follow-up',
    cells: pattern('A').cells,
    patterns: [pattern('A'), pattern('B')],
    scope: 'all_searchable',
    limit: 15,
    approximateWin: { startSequenceNumber: 3, spinCount: 50 },
    boardSequenceNumber: null,
  };
  const root = await mount(api, { replay });
  await waitFor(() => calls.range.length === 1);
  assert.equal(calls.range[0].startSequenceNumber, 3);
  assert.equal(calls.range[0].spinCount, 50);
  assert.equal(
    JSON.parse(window.localStorage.getItem(key)).selectedStartSequenceNumber,
    2,
  );
  await unmount(root);
});

test('earlier sequence boards retain super game actions and the generation warning', async () => {
  const data = multi(2);
  data.superGameState = { fresh: false };
  data.results[0].boards[0].superGame = {
    completeness: 'complete',
    kind: 'in_series',
    runVerification: 'verified',
    seriesId: 'series',
    seriesLength: 10,
    spinIndex: 3,
    superSymbolCode: 'K',
  };
  const { api } = fixture({
    searchGameBoardSequence: async () => ({ data }),
    superGameSeriesHref: () => '/series',
  });
  const replay = {
    id: 'super',
    cells: pattern('A').cells,
    patterns: [pattern('A'), pattern('B')],
    scope: 'all_searchable',
    limit: 15,
    approximateWin: null,
    boardSequenceNumber: null,
  };
  const root = await mount(api, { replay });
  await waitFor(() =>
    document.querySelector('.boardSearchSequenceBoard .boardSearchSuperGame'),
  );
  assert.equal(
    document.querySelector('.boardSearchSequenceBoard a').getAttribute('href'),
    '/series',
  );
  assert.ok(document.querySelector('.boardSearchSuperGameStale'));
  await unmount(root);
});

test('a correction refresh keeps selection and recalculates the same end position after busy finishes', async () => {
  let finishRange;
  const { api, calls } = fixture({
    getBoardSearchApproximateWin: (_id, options) => {
      calls.range.push(options);
      return new Promise((resolve) => {
        finishRange = () => resolve({ data: range(options) });
      });
    },
  });
  const replay = {
    id: 'same',
    cells: pattern('A').cells,
    patterns: [pattern('A'), pattern('B')],
    scope: 'all_searchable',
    limit: 15,
    approximateWin: null,
    boardSequenceNumber: null,
  };
  const root = await mount(api, { replay });
  await waitFor(() => calls.range.length === 1);
  await click(button('Układ 1: #6 · 100.0%'));
  await waitFor(() => button('Popraw symbole'));
  await click(button('Popraw symbole'));
  await click(document.querySelector('.boardSearchBoardCellTarget'));
  await click(
    document.querySelector('.boardSearchBoardCellPalette button[title="B"]'),
  );
  await waitFor(() => calls.correction.length === 1);
  await click(button('Zamknij'));
  assert.equal(calls.multi.length, 1, 'refresh waits for in-flight calculator');
  await act(async () => finishRange());
  await waitFor(() => calls.multi.length === 2);
  await waitFor(() => calls.range.length === 2);
  assert.equal(
    calls.range[1].startSequenceNumber,
    1,
    'same position was recalculated',
  );
  await act(async () => finishRange());
  await unmount(root);
});

test('TASK-1092 P2-3 correction capabilities change without reloading details or preloading old results', async () => {
  const { api, calls } = fixture();
  const originalSearch = api.searchGameBoards;
  let finish;
  let holdSearch = false;
  api.searchGameBoards = (id, request) => {
    if (!holdSearch) return originalSearch(id, request);
    calls.single.push(request);
    return new Promise((resolve) => {
      finish = () =>
        resolve({ data: single(), searchContextId: 'new-context' });
    });
  };
  const root = await mount(api);
  await click(symbol('A'));
  await search();
  await click(button('Pokaż planszę'));
  await waitFor(() => button('Popraw symbole'));
  assert.equal(calls.detail.length, 1);
  let preloads = 0;
  const originalImage = globalThis.Image;
  Object.defineProperty(globalThis, 'Image', {
    configurable: true,
    value: class {
      set src(_value) {
        preloads++;
      }
    },
  });
  const replay = {
    id: 'new-receipt',
    cells: pattern('A').cells,
    scope: 'all_searchable',
    limit: 15,
    approximateWin: null,
    boardSequenceNumber: null,
  };
  try {
    holdSearch = true;
    await act(async () =>
      root.render(
        React.createElement(BoardSearchWorkspace, {
          client: api,
          gameId: 'g',
          replay,
        }),
      ),
    );
    await waitFor(() => finish !== undefined);
    assert.equal(
      button('Popraw symbole'),
      undefined,
      'corrections are unavailable during search',
    );
    assert.equal(
      calls.detail.length,
      1,
      'loading capability change does not reload the board',
    );
    assert.equal(
      preloads,
      0,
      'loading does not preload the unchanged result list',
    );
    await act(async () => finish());
    await waitFor(() => button('Popraw symbole'));
    assert.equal(
      calls.detail.length,
      1,
      'new correction context does not reload the same board',
    );
    assert.equal(
      preloads,
      1,
      'the fresh result list still preloads its neighbour',
    );
    await click(button('Popraw symbole'));
    await click(document.querySelector('.boardSearchBoardCellTarget'));
    await click(
      document.querySelector('.boardSearchBoardCellPalette button[title="B"]'),
    );
    await waitFor(() => calls.correction.length === 1);
    assert.equal(calls.correction[0][3].searchContextId, 'new-context');
    await waitFor(() => calls.detail.length === 2);
    const originalRead = api.getBoardSearchBoardDetail;
    const nextApi = {
      ...api,
      getBoardSearchBoardDetail: (...args) => originalRead(...args),
    };
    await act(async () =>
      root.render(
        React.createElement(BoardSearchWorkspace, {
          client: nextApi,
          gameId: 'g',
          replay,
        }),
      ),
    );
    await waitFor(() => calls.detail.length === 3);
    assert.equal(
      preloads,
      1,
      'changing only the detail reader does not preload images',
    );
  } finally {
    Object.defineProperty(globalThis, 'Image', {
      configurable: true,
      value: originalImage,
    });
    await unmount(root);
  }
});

test('P1-1 approved-only replay and restore are one-shot; manual searches and New Search always use all searchable', async () => {
  const replay = {
    id: 'approved',
    cells: pattern('A').cells,
    patterns: [pattern('A'), pattern('B')],
    scope: 'approved_only',
    limit: 15,
    approximateWin: null,
    boardSequenceNumber: null,
  };
  let { api, calls } = fixture();
  let root = await mount(api, { replay });
  await waitFor(() => calls.multi.length === 1);
  assert.equal(calls.multi[0].scope, 'approved_only');
  await click(button('Nowe szukanie'));
  await click(symbol('A'));
  await search();
  assert.equal(calls.single.at(-1).scope, 'all_searchable');
  await unmount(root);
  const record = saved([pattern('A')]);
  record.lastSubmitted.scope = 'approved_only';
  window.localStorage.setItem(key, JSON.stringify(record));
  ({ api, calls } = fixture());
  root = await mount(api);
  await waitFor(() => calls.single.length === 1);
  assert.equal(calls.single[0].scope, 'approved_only');
  await click(symbol('B'));
  await search();
  assert.equal(calls.single.at(-1).scope, 'all_searchable');
  await unmount(root);
});

test('clean limit refresh preserves the submitted pattern and waits for the calculator', async () => {
  let finish;
  const { api, calls } = fixture({
    getBoardSearchApproximateWin: (_id, options) =>
      new Promise((resolve) => {
        finish = () => resolve({ data: range(options) });
      }),
  });
  const root = await mount(api);
  await click(symbol('A'));
  await search();
  await waitFor(() => finish !== undefined);
  const input = document.querySelector(
    'input[aria-label="Liczba wyników wyszukiwania"]',
  );
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      'value',
    ).set.call(input, '7');
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await act(async () =>
    input.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }),
    ),
  );
  assert.equal(calls.single.length, 1, 'queued until calculator settles');
  await act(async () => finish());
  await waitFor(() => calls.single.length === 2);
  assert.deepEqual(calls.single[1].cells, pattern('A').cells);
  assert.equal(calls.single[1].limit, 7);
  assert.doesNotMatch(document.body.textContent, /Wzór zmieniony/);
  assert.match(
    document.querySelector('.boardSearchResultMetrics').textContent,
    /#6/,
  );
  await unmount(root);
});

test('TASK-1093 P2-1 editing a clean draft cancels a limit refresh queued during calculation', async () => {
  let finish;
  const { api, calls } = fixture({
    getBoardSearchApproximateWin: (_id, options) =>
      new Promise((resolve) => {
        finish = () => resolve({ data: range(options) });
      }),
  });
  const root = await mount(api);
  await click(symbol('A'));
  await search();
  await waitFor(() => finish !== undefined);
  const input = document.querySelector(
    'input[aria-label="Liczba wyników wyszukiwania"]',
  );
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      'value',
    ).set.call(input, '7');
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await act(async () =>
    input.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }),
    ),
  );
  assert.equal(calls.single.length, 1, 'clean refresh waits for calculation');
  await click(symbol('B'));
  await act(async () => finish());
  await waitFor(() => button('Szukaj plansz')?.disabled === false);
  assert.equal(calls.single.length, 1, 'editing cancels the old queued query');
  await search();
  assert.equal(calls.single.length, 2);
  assert.deepEqual(calls.single[1], {
    cells: [...pattern('A').cells, { cellIndex: 5, symbolCode: 'B' }],
    limit: 7,
    scope: 'all_searchable',
  });
  await unmount(root);
});

test('TASK-1093 P2-1 correction refresh survives a dirty draft while calculation is busy', async () => {
  let finish;
  const { api, calls } = fixture({
    getBoardSearchApproximateWin: (_id, options) => {
      calls.range.push(options);
      return new Promise((resolve) => {
        finish = () => resolve({ data: range(options) });
      });
    },
  });
  const root = await mount(api, {
    replay: {
      id: 'dirty-correction',
      cells: pattern('A').cells,
      patterns: [pattern('A'), pattern('B')],
      scope: 'all_searchable',
      limit: 15,
      approximateWin: null,
      boardSequenceNumber: null,
    },
  });
  await waitFor(() => calls.range.length === 1);
  await click(symbol('A'));
  await click(button('Układ 1: #6 · 100.0%'));
  await waitFor(() => button('Popraw symbole'));
  await click(button('Popraw symbole'));
  await click(document.querySelector('.boardSearchBoardCellTarget'));
  await click(
    document.querySelector('.boardSearchBoardCellPalette button[title="B"]'),
  );
  await waitFor(() => calls.correction.length === 1);
  await click(button('Zamknij'));
  assert.equal(calls.multi.length, 1, 'correction waits for calculation');
  await act(async () => finish());
  await waitFor(() => calls.multi.length === 2);
  assert.deepEqual(calls.multi[1].patterns, [pattern('A'), pattern('B')]);
  await waitFor(() => calls.range.length === 2);
  assert.equal(calls.range[1].startSequenceNumber, 1);
  assert.match(document.body.textContent, /Wzór zmieniony/);
  await act(async () => finish());
  await unmount(root);
});

for (const order of ['correction-first', 'limit-first', 'draft-before-limit']) {
  test(`TASK-1094 P2-1 ${order}: later limits preserve a queued correction through draft edits`, async () => {
    let finish;
    const { api, calls } = fixture({
      getBoardSearchApproximateWin: (_id, options) => {
        calls.range.push(options);
        return new Promise((resolve) => {
          finish = () => resolve({ data: range(options) });
        });
      },
    });
    const root = await mount(api, {
      replay: {
        id: order,
        cells: pattern('A').cells,
        patterns: [pattern('A'), pattern('B')],
        scope: 'all_searchable',
        limit: 15,
        approximateWin: null,
        boardSequenceNumber: null,
      },
    });
    await waitFor(() => calls.range.length === 1);
    const commitLimit = async (value) => {
      const input = document.querySelector(
        'input[aria-label="Liczba wyników wyszukiwania"]',
      );
      await act(async () => {
        Object.getOwnPropertyDescriptor(
          HTMLInputElement.prototype,
          'value',
        ).set.call(input, String(value));
        input.dispatchEvent(new Event('input', { bubbles: true }));
      });
      await act(async () =>
        input.dispatchEvent(
          new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }),
        ),
      );
    };
    if (order === 'limit-first') await commitLimit(7);
    await click(button('Układ 1: #6 · 100.0%'));
    await waitFor(() => button('Popraw symbole'));
    await click(button('Popraw symbole'));
    await click(document.querySelector('.boardSearchBoardCellTarget'));
    await click(
      document.querySelector('.boardSearchBoardCellPalette button[title="B"]'),
    );
    await waitFor(() => calls.correction.length === 1);
    await click(button('Zamknij'));
    if (order === 'correction-first') await commitLimit(7);
    if (order === 'draft-before-limit') await click(symbol('A'));
    await commitLimit(9);
    if (order !== 'draft-before-limit') await click(symbol('A'));
    assert.equal(calls.multi.length, 1, 'all refreshes wait for calculation');
    await act(async () => finish());
    assert.equal(
      calls.multi.length,
      2,
      'correction was not cancelled as a limit',
    );
    assert.deepEqual(calls.multi[1], {
      patterns: [pattern('A'), pattern('B')],
      limit: order === 'draft-before-limit' ? 15 : 9,
      scope: 'all_searchable',
    });
    await waitFor(() => calls.range.length === 2);
    assert.equal(calls.range[1].startSequenceNumber, 1);
    assert.match(document.body.textContent, /Wzór zmieniony/);
    await act(async () => finish());
    assert.equal(calls.multi.length, 2, 'exactly one correction refresh');
    if (order === 'draft-before-limit') {
      await search();
      assert.deepEqual(calls.multi[2], {
        patterns: [pattern('A'), pattern('A')],
        limit: 9,
        scope: 'all_searchable',
      });
      await waitFor(() => calls.range.length === 3);
      await act(async () => finish());
    }
    await unmount(root);
  });
}

test('P2-4 dirty limit commit never queues the previous query, even while the calculator is busy', async () => {
  let finish;
  const { api, calls } = fixture({
    getBoardSearchApproximateWin: (_id, options) =>
      new Promise((resolve) => {
        finish = () => resolve({ data: range(options) });
      }),
  });
  const root = await mount(api);
  await click(symbol('A'));
  await search();
  await waitFor(() => finish !== undefined);
  await click(symbol('B'));
  const input = document.querySelector(
    'input[aria-label="Liczba wyników wyszukiwania"]',
  );
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      'value',
    ).set.call(input, '7');
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await act(async () =>
    input.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }),
    ),
  );
  assert.equal(calls.single.length, 1);
  await act(async () => finish());
  await waitFor(() => button('Szukaj plansz')?.disabled === false);
  assert.equal(
    calls.single.length,
    1,
    'committing the new limit did not enqueue the previous snapshot',
  );
  assert.match(document.body.textContent, /Wzór zmieniony/);
  await search();
  assert.equal(calls.single.length, 2);
  assert.deepEqual(calls.single[1], {
    cells: [...pattern('A').cells, { cellIndex: 5, symbolCode: 'B' }],
    limit: 7,
    scope: 'all_searchable',
  });
  await unmount(root);
});

test('P2-2 inactive replay reports the replay validation error rather than the previous empty draft', async () => {
  const { api, calls } = fixture();
  const replay = {
    id: 'archived',
    cells: pattern('archived').cells,
    patterns: [pattern('archived')],
    scope: 'all_searchable',
    limit: 15,
    approximateWin: null,
    boardSequenceNumber: null,
  };
  const root = await mount(api, { replay });
  await waitFor(() =>
    document.body.textContent.includes('nie jest już aktywny'),
  );
  assert.equal(calls.single.length, 0);
  assert.doesNotMatch(document.body.textContent, /Uzupełnij układ 1/);
  await unmount(root);
});

test('wildcard evidence warning includes earlier sequence boards', async () => {
  const data = multi(2);
  data.results[0].score.unknownMatchesAll = true;
  data.results[0].score.unknownCount = 3;
  const { api } = fixture({ searchGameBoardSequence: async () => ({ data }) });
  const replay = {
    id: 'unknown',
    cells: pattern('A').cells,
    patterns: [pattern('A'), pattern('B')],
    scope: 'all_searchable',
    limit: 15,
    approximateWin: null,
    boardSequenceNumber: null,
  };
  const root = await mount(api, { replay });
  await waitFor(() => document.querySelector('.boardSearchUnknownWarning'));
  assert.match(
    document.querySelector('.boardSearchUnknownWarning').textContent,
    /Nierozpoznane symbole: 3/,
  );
  await unmount(root);
});
