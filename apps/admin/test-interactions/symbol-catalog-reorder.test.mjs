import assert from 'node:assert/strict';
import { after, afterEach, test } from 'node:test';
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
  'Image',
]) {
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const { createRoot } = await import('react-dom/client');
const { SymbolCatalog } =
  await import('../src/features/symbols/symbol-catalog.tsx');

after(() => dom.window.close());

const gameId = '11111111-1111-4111-8111-111111111111';

function catalogSymbol(id, name, displayOrder, mobileCode) {
  return {
    code: id.toUpperCase(),
    displayOrder,
    gameId,
    id,
    imagePath: null,
    isWildcard: false,
    mobileCode,
    name,
    nameEn: null,
    namePl: null,
    status: 'active',
  };
}

const initialSymbols = [
  catalogSymbol('cherry', 'Wiśnia', 0, 1),
  catalogSymbol('star', 'Gwiazda', 1, 7),
  catalogSymbol('seven', '7', 2, 8),
];

function makeClient(updateSymbol, listCalls) {
  return {
    approvedSymbolReferenceCandidateAssetUrl: () => '',
    createSymbol: async () => ({ data: undefined }),
    deleteSymbol: async () => ({ data: undefined }),
    listApprovedSymbolReferenceCandidates: async () => ({ data: undefined }),
    listGames: async () => ({
      data: [{ code: 'g777', id: gameId, name: '777', status: 'active' }],
    }),
    listSymbols: async () => {
      listCalls.push(gameId);
      return { data: initialSymbols };
    },
    selectApprovedSymbolReferenceCandidate: async () => ({ data: undefined }),
    symbolImageAssetUrl: () => '',
    updateSymbol,
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

function button(testId) {
  return document.querySelector(`[data-testid="${testId}"]`);
}

function renderedOrder() {
  return [...document.querySelectorAll('[data-testid^="symbol-row-"]')].map(
    (row) => row.getAttribute('data-testid').replace('symbol-row-', ''),
  );
}

let root = null;

afterEach(async () => {
  if (root !== null) {
    await act(async () => root.unmount());
    root = null;
  }
});

async function renderCatalog(client) {
  root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(SymbolCatalog, {
        apiBaseUrl: 'http://127.0.0.1:8000',
        client,
      }),
    ),
  );
  await eventually(
    () => button('symbol-move-up-seven') !== null,
    'symbol list should render',
  );
}

async function click(element) {
  await act(async () => {
    element.dispatchEvent(
      new dom.window.MouseEvent('click', { bubbles: true }),
    );
  });
}

test('move buttons are disabled at the list edges', async () => {
  await renderCatalog(makeClient(async () => ({ data: undefined }), []));

  assert.equal(button('symbol-move-up-cherry').disabled, true);
  assert.equal(button('symbol-move-down-cherry').disabled, false);
  assert.equal(button('symbol-move-up-seven').disabled, false);
  assert.equal(button('symbol-move-down-seven').disabled, true);
});

test('moving a symbol up saves displayOrder and locks controls until done', async () => {
  const requests = [];
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  const client = makeClient(async (_gameId, symbolId, body) => {
    requests.push({ body, symbolId });
    await gate;
    return { data: initialSymbols.find((item) => item.id === symbolId) };
  }, []);
  await renderCatalog(client);

  await click(button('symbol-move-up-seven'));

  assert.equal(button('symbol-move-down-cherry').disabled, true);
  assert.equal(button('symbol-move-up-star').disabled, true);
  assert.equal(document.getElementById('symbol-game-selector').disabled, true);

  release();
  await eventually(
    () => renderedOrder().join(',') === 'cherry,seven,star',
    'catalog should show the new order',
  );
  assert.deepEqual(requests, [
    { body: { displayOrder: 1 }, symbolId: 'seven' },
    { body: { displayOrder: 2 }, symbolId: 'star' },
  ]);
  assert.equal(button('symbol-move-up-star').disabled, false);
  assert.equal(document.getElementById('symbol-game-selector').disabled, false);
  assert.match(document.body.textContent, /Przesunięto symbol „7” wyżej/);
});

test('a failed reorder shows the error and reloads the persisted order', async () => {
  const listCalls = [];
  const client = makeClient(
    async () => ({
      error: { code: 'VALIDATION_ERROR', details: {}, message: 'Odrzucono.' },
    }),
    listCalls,
  );
  await renderCatalog(client);
  const loadsBeforeMove = listCalls.length;

  await click(button('symbol-move-up-seven'));

  await eventually(
    () => document.querySelector('[role="alert"]') !== null,
    'error banner should render',
  );
  await eventually(
    () => button('symbol-move-up-seven') !== null,
    'reloaded list should render',
  );
  assert.equal(listCalls.length, loadsBeforeMove + 1);
  assert.deepEqual(renderedOrder(), ['cherry', 'star', 'seven']);
});
