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

const { createRoot } = await import('react-dom/client');
const { BoardSearchWorkspace } = await import(
  '../src/features/board-search/board-search-workspace.tsx'
);

after(() => dom.window.close());

const gameId = '11111111-1111-4111-8111-111111111111';
const symbol = {
  code: 'cherry',
  displayOrder: 0,
  id: 'symbol-cherry',
  imagePath: null,
  mobileCode: 1,
  name: 'Wiśnia',
  status: 'active',
};

function boardResult(sequenceNumber, overrides = {}) {
  return {
    assetMode: 'operational_review',
    boardChecksumSha256: String(sequenceNumber).padStart(64, '0'),
    importJobId: `job-${sequenceNumber}`,
    recognizedBoardId: `board-${sequenceNumber}`,
    reviewItemId: `review-${sequenceNumber}`,
    score: {
      alternativeMatchCount: 0,
      exactMatchCount: 1,
      mismatchCount: 0,
      score: 100,
      unknownCount: 0,
      weightedAlternativeScore: 0,
    },
    sequenceNumber,
    status: 'pending',
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

function symbolButton() {
  const current = [...document.querySelectorAll('.boardSearchSymbolButton')].find(
    (node) => node.title === symbol.name,
  );
  assert.ok(current);
  return current;
}

function limitInput() {
  const current = document.querySelector(
    'input[aria-label="Liczba wyników wyszukiwania"]',
  );
  assert.ok(current);
  return current;
}

function searchButton() {
  const current = [...document.querySelectorAll('button')].find((node) =>
    node.textContent.includes('Szukaj plansz'),
  );
  assert.ok(current);
  return current;
}

function setInputValue(input, value) {
  Object.getOwnPropertyDescriptor(
    dom.window.HTMLInputElement.prototype,
    'value',
  ).set.call(input, value);
  return input.dispatchEvent(new dom.window.Event('input', { bubbles: true }));
}

function pressEnter(input) {
  return input.dispatchEvent(
    new dom.window.KeyboardEvent('keydown', { bubbles: true, key: 'Enter' }),
  );
}

async function click(node) {
  await act(async () =>
    node.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })),
  );
}

function makeClient(searchImpl) {
  return {
    archivedBoardSearchAssetUrl: () => 'http://127.0.0.1:8000/archive.jpg',
    listSymbols: async () => ({ data: [symbol] }),
    operationalImageReviewBoardAssetUrl: () =>
      'http://127.0.0.1:8000/board.jpg',
    searchGameBoards: searchImpl,
    symbolImageAssetUrl: () => 'http://127.0.0.1:8000/symbol.jpg',
  };
}

async function renderWorkspace(client) {
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(BoardSearchWorkspace, {
        apiBaseUrl: 'http://127.0.0.1:8000',
        client,
        gameId,
      }),
    ),
  );
  await eventually(() => symbolButton() !== null, 'palette should render');
  return root;
}

test('the first search defaults to a limit of 5', async () => {
  const calls = [];
  const client = makeClient(async (_gameId, options) => {
    calls.push(options);
    return { data: { results: [boardResult(1)] } };
  });
  const root = await renderWorkspace(client);

  assert.equal(limitInput().value, '5');
  await click(symbolButton());
  await click(searchButton());
  await eventually(() => calls.length === 1, 'search should have run once');
  assert.equal(calls[0].limit, 5);
  await act(async () => root.unmount());
});

test('committing a new limit re-runs the search and preserves the selected board', async () => {
  const calls = [];
  const client = makeClient(async (_gameId, options) => {
    calls.push(options);
    if (calls.length === 1) {
      return { data: { results: [boardResult(10), boardResult(19)] } };
    }
    return { data: { results: [boardResult(19), boardResult(28)] } };
  });
  const root = await renderWorkspace(client);
  await click(symbolButton());
  await click(searchButton());
  await eventually(() => calls.length === 1, 'first search should run');
  await eventually(
    () => document.querySelector('.boardSearchResults') !== null,
    'results should render',
  );

  // move to the second result (sequence 19) before changing the limit
  await click(
    [...document.querySelectorAll('button')].find((node) =>
      node.textContent.includes('Następna'),
    ),
  );
  await eventually(
    () => document.body.textContent.includes('#19'),
    'second result should be active',
  );

  await act(async () => setInputValue(limitInput(), '10'));
  await act(async () => pressEnter(limitInput()));

  await eventually(() => calls.length === 2, 'limit change should re-run search');
  assert.equal(calls[1].limit, 10);
  // cells/scope stay unchanged when only the limit changes
  assert.deepEqual(calls[1].cells, calls[0].cells);
  assert.equal(calls[1].scope, calls[0].scope);

  await eventually(
    () => document.body.textContent.includes('#19'),
    'selection should be preserved across the limit change',
  );
  await act(async () => root.unmount());
});

test('an out-of-range limit shows an inline error and does not search', async () => {
  const calls = [];
  const client = makeClient(async (_gameId, options) => {
    calls.push(options);
    return { data: { results: [boardResult(1)] } };
  });
  const root = await renderWorkspace(client);

  await act(async () => setInputValue(limitInput(), '101'));
  await act(async () => pressEnter(limitInput()));

  assert.equal(calls.length, 0);
  assert.ok(
    document.body.textContent.includes('Liczba wyników musi być z zakresu'),
  );
  // the invalid text is not silently replaced
  assert.equal(limitInput().value, '101');
  await act(async () => root.unmount());
});

test('changing the limit never changes the query cells or scope, only the count', async () => {
  const calls = [];
  const client = makeClient(async (_gameId, options) => {
    calls.push(options);
    return { data: { results: [boardResult(1)] } };
  });
  const root = await renderWorkspace(client);
  await click(symbolButton());
  await click(searchButton());
  await eventually(() => calls.length === 1, 'first search should run');

  await act(async () => setInputValue(limitInput(), '7'));
  await act(async () => pressEnter(limitInput()));
  await eventually(() => calls.length === 2, 'limit change should re-run search');

  assert.deepEqual(calls[1].cells, calls[0].cells);
  assert.equal(calls[1].scope, calls[0].scope);
  assert.notEqual(calls[1].limit, calls[0].limit);
  await act(async () => root.unmount());
});

test('a fresh pattern search always selects the first result, unaffected by the limit', async () => {
  const calls = [];
  let response = { results: [boardResult(1), boardResult(2)] };
  const client = makeClient(async (_gameId, options) => {
    calls.push(options);
    return { data: response };
  });
  const root = await renderWorkspace(client);
  await click(symbolButton());
  await click(searchButton());
  await eventually(() => calls.length === 1, 'first search should run');
  await eventually(
    () => document.body.textContent.includes('1 z 2'),
    'first result should be active by default',
  );

  await click(
    [...document.querySelectorAll('button')].find((node) =>
      node.textContent.includes('Następna'),
    ),
  );
  await eventually(
    () => document.body.textContent.includes('2 z 2'),
    'second result should now be active',
  );

  response = { results: [boardResult(5), boardResult(6)] };
  await click(searchButton());
  await eventually(() => calls.length === 2, 'new pattern search should run');
  await eventually(
    () => document.body.textContent.includes('1 z 2'),
    'a brand-new search should select the first result again',
  );
  await act(async () => root.unmount());
});
