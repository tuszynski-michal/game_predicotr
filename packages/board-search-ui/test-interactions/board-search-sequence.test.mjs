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
]) {
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
}
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

test('ordinary search has no adjacent photos and corrections still target the ranked board', async () => {
  const { api, calls } = fixture();
  const root = await mount(api);
  await click(symbol('A'));
  await search();
  assert.equal(button('Poprzedni układ'), undefined);
  assert.equal(button('Następny układ'), undefined);
  assert.ok(document.querySelector('.boardSearchResults img[src="/view/6"]'));
  assert.equal(calls.detail.length, 0, 'no adjacent-board requests');
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
  assert.equal(calls.correction[0][1], 6);
  assert.equal(calls.correction[0][3].startSequenceNumber, 6);
  assert.equal(calls.correction[0][3].searchContextId, 'single-context');
  await unmount(root);
});

test('reset cancels a pending search and its cleared state survives remount', async () => {
  const { api, calls } = fixture();
  let finish;
  let root = await mount(api);
  await click(symbol('A'));
  await search();
  api.searchGameBoards = () =>
    new Promise((resolve) => {
      finish = resolve;
    });
  await click(symbol('B'));
  await click(button('Szukaj plansz'));
  assert.equal(document.querySelector('.boardSearchResults'), null);
  await click(button('Resetuj'));
  await act(async () => finish({ data: single([board(9)]) }));
  assert.equal(document.querySelector('.boardSearchResults'), null);
  assert.equal(button('Szukaj plansz').disabled, true);
  const record = JSON.parse(
    window.localStorage.getItem('board-search-single:v2:admin:g'),
  );
  assert.ok(record.cells.every((value) => value === null));
  assert.equal(record.lastSubmitted, null);
  await unmount(root);
  root = await mount(api);
  assert.equal(document.querySelector('.boardSearchResults'), null);
  assert.equal(button('Szukaj plansz').disabled, true);
  assert.equal(calls.single.length, 1);
  await unmount(root);
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
  assert.equal(document.querySelector('.boardSearchResults'), null);
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 450));
  });
  assert.equal(pending.length, 2, 'no calculation during search');
  await act(async () => finishSearch({ data: single() }));
  await unmount(root);
  assert.equal(calls.single.length, 1);
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
    document.querySelector('.boardSearchResultSummary').textContent,
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
    cells: pattern('B').cells,
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
      patterns: [pattern('A')],
      scope: 'all_searchable',
      limit: 15,
      approximateWin: null,
      boardSequenceNumber: null,
    },
  });
  await waitFor(() => calls.range.length === 1);
  await click(symbol('B'));
  await click(button('Pokaż planszę'));
  await waitFor(() => button('Popraw symbole'));
  await click(button('Popraw symbole'));
  await click(document.querySelector('.boardSearchBoardCellTarget'));
  await click(
    document.querySelector('.boardSearchBoardCellPalette button[title="B"]'),
  );
  await waitFor(() => calls.correction.length === 1);
  await click(button('Zamknij'));
  assert.equal(calls.single.length, 1, 'correction waits for calculation');
  await act(async () => finish());
  await waitFor(() => calls.single.length === 2);
  assert.deepEqual(calls.single[1].cells, pattern('A').cells);
  await waitFor(() => calls.range.length === 2);
  assert.equal(calls.range[1].startSequenceNumber, 6);
  assert.match(document.body.textContent, /Wzór zmieniony/);
  await act(async () => finish());
  await unmount(root);
});
test('ranked next and previous matches remain available and move the win anchor', async () => {
  const { api, calls } = fixture();
  const root = await mount(api);
  assert.equal(button('Dodaj układ'), undefined);
  assert.equal(document.querySelector('.boardSearchSequenceBadges'), null);
  await click(symbol('A'));
  await search();
  assert.match(
    document.querySelector('.boardSearchResultSummary').textContent,
    /Układ #6.*1 z 2/,
  );
  await click(button('Następna →'));
  assert.match(
    document.querySelector('.boardSearchResultSummary').textContent,
    /Układ #2.*2 z 2/,
  );
  assert.ok(document.querySelector('.boardSearchResults img[src="/view/2"]'));
  assert.equal(button('Następna →').disabled, true);
  await waitFor(() =>
    calls.range.some((request) => request.startSequenceNumber === 2),
  );
  await click(button('← Poprzednia'));
  assert.match(
    document.querySelector('.boardSearchResultSummary').textContent,
    /Układ #6.*1 z 2/,
  );
  assert.equal(button('← Poprzednia').disabled, true);
  assert.equal(calls.single.length, 1);
  assert.equal(calls.multi.length, 0);
  await unmount(root);
});
test('old multi storage and direct replay never execute, including StrictMode', async () => {
  const original = JSON.stringify(saved([pattern('A'), pattern('B')]));
  window.localStorage.setItem(key, original);
  const { api, calls } = fixture();
  let root = await mount(api, { strict: true });
  assert.equal(calls.single.length + calls.multi.length, 0);
  assert.match(document.body.textContent, /zostało usunięte/);
  assert.equal(window.localStorage.getItem(key), original);
  await unmount(root);
  root = await mount(api, {
    replay: {
      id: 'multi',
      patterns: [pattern('A'), pattern('B')],
      cells: pattern('A').cells,
      scope: 'all_searchable',
      limit: 40,
      approximateWin: null,
      boardSequenceNumber: null,
    },
  });
  assert.equal(calls.single.length + calls.multi.length, 0);
  assert.match(document.body.textContent, /zostało usunięte/);
  await unmount(root);
});
test('one legacy pattern restores and new single record survives remount', async () => {
  window.localStorage.setItem(key, JSON.stringify(saved([pattern('A')])));
  const { api, calls } = fixture();
  let root = await mount(api, { strict: true });
  await waitFor(() => calls.single.length === 1);
  await unmount(root);
  const record = JSON.parse(
    window.localStorage.getItem('board-search-single:v2:admin:g'),
  );
  assert.equal(record.version, 2);
  assert.equal(record.patterns, undefined);
  assert.equal(record.cells.length, 15);
  root = await mount(api);
  await waitFor(() => calls.single.length === 2);
  assert.equal(calls.multi.length, 0);
  await waitFor(() => document.querySelector('.boardSearchResults'));
  await click(symbol('B'));
  const next = JSON.parse(
    window.localStorage.getItem('board-search-single:v2:admin:g'),
  );
  assert.deepEqual(
    next.cells.filter(Boolean),
    ['B'],
    'a restored searched pattern also starts fresh',
  );
  await unmount(root);
});

test('the first symbol after Search starts one fresh pattern and Undo never restores the old one', async () => {
  const { api, calls } = fixture();
  const root = await mount(api, { strict: true });
  await click(symbol('A'));
  await click(symbol('B'));
  await search();
  assert.equal(calls.single[0].cells.length, 2);
  await click(symbol('B'));
  await click(symbol('A'));
  const record = () =>
    JSON.parse(window.localStorage.getItem('board-search-single:v2:admin:g'));
  assert.deepEqual(record().cells.filter(Boolean), ['B', 'A']);
  assert.equal(record().cells[0], 'B');
  assert.equal(record().cells[5], 'A');
  await click(button('Cofnij'));
  assert.deepEqual(record().cells.filter(Boolean), ['B']);
  await click(button('Cofnij'));
  assert.deepEqual(record().cells.filter(Boolean), []);
  assert.equal(button('Cofnij').disabled, true);
  await click(button('Resetuj'));
  assert.equal(document.querySelector('.boardSearchResults'), null);
  await unmount(root);
});

test('a started new pattern survives remount and continues without clearing again', async () => {
  const { api, calls } = fixture();
  let root = await mount(api);
  await click(symbol('A'));
  await search();
  await click(symbol('B'));
  await click(symbol('A'));
  await unmount(root);
  root = await mount(api, { strict: true });
  await waitFor(() => calls.single.length === 2);
  await click(symbol('B'));
  const record = JSON.parse(
    window.localStorage.getItem('board-search-single:v2:admin:g'),
  );
  assert.equal(record.cells[0], 'B');
  assert.equal(record.cells[5], 'A');
  assert.equal(record.cells[10], 'B');
  assert.deepEqual(
    calls.single[1].cells,
    pattern('A').cells,
    'restored response belongs to the old submitted snapshot',
  );
  await unmount(root);
});

test('typing while a saved clean search restores already starts a new pattern', async () => {
  window.localStorage.setItem(key, JSON.stringify(saved([pattern('A')])));
  let finish;
  const { api } = fixture({
    searchGameBoards: () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  });
  const root = await mount(api, { strict: true });
  await waitFor(() => finish !== undefined);
  await click(symbol('B'));
  const record = JSON.parse(
    window.localStorage.getItem('board-search-single:v2:admin:g'),
  );
  assert.deepEqual(record.cells.filter(Boolean), ['B']);
  await act(async () => finish({ data: single() }));
  assert.deepEqual(
    JSON.parse(
      window.localStorage.getItem('board-search-single:v2:admin:g'),
    ).cells.filter(Boolean),
    ['B'],
  );
  await unmount(root);
});

test('an identical newly started pattern remains a draft after remount', async () => {
  const { api, calls } = fixture();
  let root = await mount(api);
  await click(symbol('A'));
  await search();
  await click(symbol('A'));
  await unmount(root);
  root = await mount(api, { strict: true });
  await waitFor(() => calls.single.length === 2);
  await click(symbol('B'));
  const record = JSON.parse(
    window.localStorage.getItem('board-search-single:v2:admin:g'),
  );
  assert.equal(record.nextSymbolStartsPattern, false);
  assert.equal(record.cells[0], 'A');
  assert.equal(record.cells[5], 'B');
  await unmount(root);
});

test('new search hides the old board and calculation through loading and error, then shows an empty result', async () => {
  const { api } = fixture();
  const root = await mount(api);
  await click(symbol('A'));
  await search();
  assert.ok(document.querySelector('.boardSearchResults'));
  let finish;
  api.searchGameBoards = () =>
    new Promise((resolve) => {
      finish = resolve;
    });
  await click(symbol('B'));
  await click(button('Szukaj plansz'));
  assert.equal(document.querySelector('.boardSearchResults'), null);
  assert.ok(
    document.querySelector('.boardSearchApproximateWin').closest('[hidden]'),
  );
  await act(async () =>
    finish({ error: { code: 'FAILED', message: 'Błąd szukania' } }),
  );
  await waitFor(() => document.querySelector('[role="alert"]'));
  assert.equal(document.querySelector('.boardSearchResults'), null);
  assert.ok(
    document.querySelector('.boardSearchApproximateWin').closest('[hidden]'),
  );
  api.searchGameBoards = async () => ({ data: single([]) });
  await search();
  assert.match(
    document.querySelector('.boardSearchResults').textContent,
    /Żadna plansza/,
  );
  assert.equal(document.querySelector('.boardSearchResults img'), null);
  await unmount(root);
});

test('ordinary search is compact while the management editor retains its default controls', async () => {
  const { api } = fixture();
  let root = await mount(api);
  const actions = document.querySelector('.boardSearchSubmitActions');
  assert.deepEqual(
    [...actions.querySelectorAll('button')].map((item) =>
      item.textContent.trim(),
    ),
    ['Cofnij', 'Resetuj', 'Szukaj plansz'],
  );
  assert.ok(
    document.querySelector(
      '.boardSearchEntryOrder .boardSearchResultLimit input[aria-label="Liczba wyników wyszukiwania"]',
    ),
  );
  assert.ok(
    [...document.querySelectorAll('.boardSearchPalette header p')].every(
      (node) => node.hidden,
    ),
  );
  assert.equal(
    document.querySelector('.boardSearchPattern > header').hidden,
    true,
  );
  assert.equal(
    document.querySelector('.boardSearchEntryOrder legend').hidden,
    true,
  );
  assert.equal(
    document.querySelector('.boardSearchUnknownButton').hidden,
    true,
  );
  assert.equal(button('Nowe szukanie'), undefined);
  await click(symbol('A'));
  await search();
  assert.equal(document.querySelector('.boardSearchEvidence'), null);
  assert.equal(
    document.querySelectorAll('.boardSearchResultSummary').length,
    1,
  );
  await waitFor(() =>
    document.querySelector('.boardSearchApproximateWinChart'),
  );
  const body = document.querySelector('.boardSearchApproximateWinBody');
  assert.ok(
    body
      .querySelector('.boardSearchApproximateWinControls')
      .nextElementSibling.classList.contains('boardSearchApproximateWinChart'),
  );
  assert.equal(document.getElementById('approximateWinHeading').hidden, true);
  assert.equal(
    document
      .querySelector('.boardSearchApproximateWin .importSubsectionHeader')
      .textContent.trim(),
    '0 częściowych, 2500 brakujących',
  );
  assert.equal(
    document.querySelector('.boardSearchResults footer > span').hidden,
    true,
  );
  await unmount(root);
  root = await mount(api, { fixedStakeGrosze: 500 });
  assert.equal(document.querySelector('.boardSearchWorkspaceSimplified'), null);
  assert.equal(
    document.querySelector('.boardSearchPattern > header').hidden,
    false,
  );
  assert.equal(
    document.querySelector('.boardSearchUnknownButton').hidden,
    false,
  );
  assert.equal(
    document.querySelector('.boardSearchEntryOrder legend').hidden,
    false,
  );
  await unmount(root);
});
