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
  'Element',
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

const proto = dom.window.HTMLDialogElement.prototype;
if (typeof proto.showModal !== 'function') {
  proto.showModal = function showModal() {
    this.setAttribute('open', '');
  };
  proto.close = function close() {
    this.removeAttribute('open');
  };
}

const { createRoot } = await import('react-dom/client');
const { BoardSearchWorkspace } =
  await import('../src/board-search-workspace.tsx');

after(() => dom.window.close());

const gameId = '11111111-1111-4111-8111-111111111111';
const symbols = ['cherry', 'lemon'].map((code, index) => ({
  code,
  displayOrder: index,
  id: `symbol-${code}`,
  imagePath: null,
  mobileCode: index + 1,
  name: code,
  status: 'active',
}));

function result(sequenceNumber) {
  return {
    assetMode: 'operational_review',
    boardChecksumSha256: String(sequenceNumber).padStart(64, '0'),
    importJobId: null,
    recognizedBoardId: null,
    reviewItemId: null,
    score: {
      alternativeMatchCount: 0,
      exactMatchCount: 1,
      mismatchCount: 0,
      score: 100,
      unknownCount: 0,
    },
    sequenceNumber,
    status: 'pending',
  };
}

function range(startSequenceNumber, spinCount, rows = []) {
  return {
    completeness: {
      completeBoardCount: 0,
      missingBoardCount: spinCount,
      partialBoardCount: 0,
    },
    dataFingerprintSha256: 'a'.repeat(64),
    dataSource: 'operational_review',
    evaluatedSpinCount: spinCount,
    gameId,
    requestedSpinCount: spinCount,
    rows,
    rules: {
      algorithmVersion: 'payout-v3-unknown-prefix-stop',
      rulesVersion: 1,
      rulesVersionId: 'rules-1',
      spinCost: 20,
    },
    sequenceLength: 500000,
    startBoardStatus: null,
    startSequenceNumber,
    summary: {
      balanceCredits: 0,
      recognizedPayoutCredits: 0,
      spinCostCredits: 0,
    },
    wrappedAtSequenceEnd: false,
  };
}

async function settle() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

async function eventually(predicate, label) {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    if (predicate()) return;
    await settle();
  }
  assert.fail(label);
}

function client(overrides = {}) {
  const calls = { detail: [], range: [], search: [] };
  return {
    calls,
    value: {
      boardSearchBoardViewUrl: () => 'http://127.0.0.1:8000/view.webp',
      getBoardSearchApproximateWin: async (_gameId, options) => {
        calls.range.push(options);
        return {
          data: range(options.startSequenceNumber, options.spinCount, [
            {
              boardStatus: 'pending',
              cumulativeBalanceCredits: 80,
              cumulativeCostCredits: 20,
              cumulativePayoutCredits: 100,
              payoutCredits: 100,
              payoutKind: 'confirmed_minimum',
              sequenceNumber: 13,
              spinNumber: 1,
            },
          ]),
        };
      },
      getBoardSearchBoardDetail: async (_gameId, sequenceNumber) => {
        calls.detail.push(sequenceNumber);
        return {
          error: { code: 'BOARD_SEARCH_BOARD_NOT_FOUND', message: 'x' },
        };
      },
      listSymbols: async () => ({ data: symbols }),
      searchGameBoards: async (_gameId, options) => {
        calls.search.push(options);
        return {
          data: {
            gameId,
            queryCellCount: 1,
            results: [result(10), result(12)],
            scope: options.scope,
          },
        };
      },
      symbolImageAssetUrl: () => 'http://127.0.0.1:8000/symbol.png',
      ...overrides,
    },
  };
}

async function render(value, replay, onReplayApplied) {
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(BoardSearchWorkspace, {
        client: value,
        gameId,
        onReplayApplied,
        replay,
      }),
    ),
  );
  return root;
}

test('a search replay sets the same pattern, scope and limit and searches once', async () => {
  const { calls, value } = client();
  const root = await render(value, {
    approximateWin: null,
    boardSequenceNumber: null,
    cells: [
      { cellIndex: 6, symbolCode: 'lemon' },
      { cellIndex: 0, symbolCode: 'cherry' },
      { cellIndex: 3, symbolCode: null },
    ],
    id: 'event-1:a',
    limit: 7,
    scope: 'approved_only',
  });
  await eventually(() => calls.search.length === 1, 'one search');
  await settle();
  assert.equal(calls.search.length, 1);
  assert.deepEqual(calls.search[0], {
    cells: [
      { cellIndex: 0, symbolCode: 'cherry' },
      { cellIndex: 3, symbolCode: null },
      { cellIndex: 6, symbolCode: 'lemon' },
    ],
    limit: 7,
    scope: 'approved_only',
  });
  assert.equal(
    document.querySelector('input[aria-label="Liczba wyników wyszukiwania"]')
      .value,
    '7',
  );
  assert.equal(
    document
      .querySelector('input[name="board-search-scope"]:checked')
      .parentElement.textContent.trim(),
    'Tylko zatwierdzone',
  );
  assert.ok(
    document.querySelector(
      'button[aria-label="Wiersz 1, kolumna 4: nieznany symbol, bez dowodu"]',
    ),
    'the recorded ? cell is restored',
  );
  assert.ok(
    document.querySelector('button[aria-label="Wiersz 1, kolumna 1: cherry"]'),
  );
  assert.ok(
    document.querySelector('button[aria-label="Wiersz 2, kolumna 2: lemon"]'),
  );
  await act(async () => root.unmount());
});

test('a range replay selects the start board and opens the range; a detail opens its board', async () => {
  const { calls, value } = client();
  const root = await render(value, {
    approximateWin: { spinCount: 250, startSequenceNumber: 12 },
    boardSequenceNumber: 13,
    cells: [{ cellIndex: 0, symbolCode: 'cherry' }],
    id: 'event-2:a',
    limit: 5,
    scope: 'all_searchable',
  });
  await eventually(() => calls.range.length === 1, 'range calculated');
  assert.deepEqual(calls.range[0], { spinCount: 250, startSequenceNumber: 12 });
  assert.equal(document.querySelector('.boardSearchApproximateWin').open, true);
  assert.equal(
    document.querySelector(
      'input[aria-label="Zakres wygranej — liczba kolejnych spinów"]',
    ).value,
    '250',
  );
  assert.match(
    document.querySelector('.boardSearchResults').textContent,
    /#12/,
  );
  await eventually(() => calls.detail.length === 1, 'board modal opened');
  assert.deepEqual(calls.detail, [13]);
  assert.ok(document.querySelector('.boardSearchBoardLinesDialog'));
  await act(async () => root.unmount());
});

test('a missing start board or an inactive symbol is reported instead of guessed', async () => {
  const { calls, value } = client();
  const root = await render(value, {
    approximateWin: { spinCount: 250, startSequenceNumber: 99 },
    boardSequenceNumber: null,
    cells: [
      { cellIndex: 0, symbolCode: 'cherry' },
      { cellIndex: 1, symbolCode: 'retired' },
    ],
    id: 'event-3:a',
    limit: 5,
    scope: 'all_searchable',
  });
  await eventually(
    () => /Planszy startowej #99/.test(document.body.textContent),
    'missing start board notice',
  );
  assert.match(
    document.body.textContent,
    /Symbol „retired” nie jest już aktywny/,
  );
  assert.deepEqual(calls.search[0].cells, [
    { cellIndex: 0, symbolCode: 'cherry' },
    { cellIndex: 1, symbolCode: null },
  ]);
  assert.equal(calls.range.length, 0);
  assert.equal(
    document.querySelector('.boardSearchApproximateWin').open,
    false,
  );
  await act(async () => root.unmount());
});

test('a manual search also sends unknown cells so the share log keeps the pattern', async () => {
  const { calls, value } = client();
  const root = await render(value, null);
  await eventually(
    () => document.querySelectorAll('.boardSearchSymbolButton').length > 0,
    'palette',
  );
  const buttons = [...document.querySelectorAll('.boardSearchSymbolButton')];
  const clickNode = (node) =>
    act(async () =>
      node.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })),
    );
  await clickNode(buttons.find((node) => node.title === 'cherry'));
  await clickNode(
    buttons.find((node) => node.classList.contains('boardSearchUnknownButton')),
  );
  await clickNode(
    [...document.querySelectorAll('button')].find((node) =>
      node.textContent.includes('Szukaj plansz'),
    ),
  );
  await eventually(() => calls.search.length === 1, 'search');
  assert.deepEqual(calls.search[0].cells, [
    { cellIndex: 0, symbolCode: 'cherry' },
    { cellIndex: 5, symbolCode: null },
  ]);
  await act(async () => root.unmount());
});

test('the host is told once that the replay was taken over', async () => {
  const { calls, value } = client();
  const applied = [];
  const replay = {
    approximateWin: null,
    boardSequenceNumber: 13,
    cells: [{ cellIndex: 0, symbolCode: 'cherry' }],
    id: 'event-4:a',
    limit: 5,
    scope: 'all_searchable',
  };
  const root = await render(value, replay, (id) => applied.push(id));
  await eventually(() => calls.search.length === 1, 'search');
  await settle();
  assert.deepEqual(applied, ['event-4:a']);
  // A board detail without an earlier range explains why no board opened.
  assert.match(document.body.textContent, /okna planszy #13 nie otwarto/);
  await act(async () => root.unmount());
});
