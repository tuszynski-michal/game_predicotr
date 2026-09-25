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
  'Node',
]) {
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const { createRoot } = await import('react-dom/client');
const { BoardSearchWorkspace } =
  await import('../src/features/board-search/board-search-workspace.tsx');

after(() => dom.window.close());

const gameId = '11111111-1111-4111-8111-111111111111';
function makeSymbol(code, name, displayOrder) {
  return {
    code,
    displayOrder,
    id: `symbol-${code}`,
    imagePath: null,
    mobileCode: displayOrder + 1,
    name,
    status: 'active',
  };
}
// Deliberately out of catalog order: shortcuts follow displayOrder.
const symbols = [
  makeSymbol('bell', 'Dzwonek', 1),
  makeSymbol('cherry', 'Wiśnia', 0),
];

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

async function press(key, target = document.body, init = {}) {
  let notCancelled = true;
  await act(async () => {
    notCancelled = target.dispatchEvent(
      new dom.window.KeyboardEvent('keydown', {
        bubbles: true,
        cancelable: true,
        key,
        ...init,
      }),
    );
  });
  return notCancelled;
}

function cellLabels() {
  return [...document.querySelectorAll('.boardSearchCell')].map((node) =>
    node.getAttribute('aria-label'),
  );
}

async function renderWorkspace(searchImpl) {
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(BoardSearchWorkspace, {
        apiBaseUrl: 'http://127.0.0.1:8000',
        client: {
          archivedBoardSearchAssetUrl: () => 'http://127.0.0.1:8000/a.jpg',
          getOperationalImageReviewItem: async () => ({
            data: { geometry: {} },
          }),
          listSymbols: async () => ({ data: symbols }),
          operationalImageReviewBoardAssetUrl: () =>
            'http://127.0.0.1:8000/board.jpg',
          searchGameBoards: searchImpl,
          symbolImageAssetUrl: () => 'http://127.0.0.1:8000/symbol.jpg',
        },
        gameId,
      }),
    ),
  );
  await eventually(
    () => document.querySelector('.boardSearchSymbolButton') !== null,
    'palette should render',
  );
  return root;
}

test('digits place symbols in catalog order, 0 places ?, Backspace undoes', async () => {
  const root = await renderWorkspace(async () => ({ data: { results: [] } }));
  const badges = [
    ...document.querySelectorAll('.boardSearchSymbolShortcut'),
  ].map((node) => node.textContent);
  assert.deepEqual(badges, ['1', '2', '0']);

  assert.equal(await press('1'), false);
  assert.equal(await press('2'), false);
  assert.equal(await press('0'), false);
  // Column entry order: top-to-bottom in column 1.
  const labels = cellLabels();
  assert.equal(labels[0], 'Wiersz 1, kolumna 1: Wiśnia');
  assert.equal(labels[5], 'Wiersz 2, kolumna 1: Dzwonek');
  assert.equal(labels[10], 'Wiersz 3, kolumna 1: nieznany symbol, bez dowodu');

  await press('Backspace');
  assert.equal(cellLabels()[10], 'Wiersz 3, kolumna 1, puste');
  // A digit without a symbol and modified keys do nothing.
  assert.equal(await press('7'), true);
  assert.equal(await press('1', document.body, { ctrlKey: true }), true);
  await act(async () => root.unmount());
});

test('Enter searches, but typing in the limit field keeps native keys', async () => {
  const calls = [];
  const root = await renderWorkspace(async (_gameId, options) => {
    calls.push(options);
    return { data: { results: [] } };
  });
  const limit = document.querySelector(
    'input[aria-label="Liczba wyników wyszukiwania"]',
  );
  assert.equal(await press('1', limit), true);
  assert.ok(cellLabels()[0].endsWith(', puste'));

  await press('Enter');
  assert.equal(calls.length, 0, 'empty pattern must not search');

  await press('1');
  assert.equal(await press('Enter'), false);
  await eventually(() => calls.length === 1, 'Enter should run the search');
  assert.deepEqual(calls[0].cells, [{ cellIndex: 0, symbolCode: 'cherry' }]);
  await act(async () => root.unmount());
});
