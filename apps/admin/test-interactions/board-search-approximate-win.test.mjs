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
    },
    sequenceNumber,
    status: 'pending',
    ...overrides,
  };
}

function approximateWinResponse(startSequenceNumber, overrides = {}) {
  return {
    completeness: { completeBoardCount: 0, missingBoardCount: 1000, partialBoardCount: 0 },
    dataFingerprintSha256: 'a'.repeat(64),
    dataSource: 'operational_review',
    evaluatedSpinCount: 1000,
    gameId,
    requestedSpinCount: 1000,
    rows: [],
    rules: {
      algorithmVersion: 'payout-v3-unknown-prefix-stop',
      rulesVersion: 1,
      rulesVersionId: 'rules-1',
      spinCost: 20,
    },
    sequenceLength: 500000,
    startBoardStatus: null,
    startSequenceNumber,
    summary: { balanceCredits: -20000, recognizedPayoutCredits: 0, spinCostCredits: 20000 },
    wrappedAtSequenceEnd: false,
    ...overrides,
  };
}

function deferred() {
  let resolve;
  const promise = new Promise((nextResolve) => {
    resolve = nextResolve;
  });
  return { promise, resolve };
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

function searchButton() {
  const current = [...document.querySelectorAll('button')].find((node) =>
    node.textContent.includes('Szukaj plansz'),
  );
  assert.ok(current);
  return current;
}

function approximateWinDetails() {
  const current = document.querySelector('.boardSearchApproximateWin');
  assert.ok(current);
  return current;
}

function rangeInput() {
  const current = document.querySelector(
    'input[aria-label="Zakres wygranej — liczba kolejnych spinów"]',
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

async function toggleDetails(details, open) {
  await act(async () => {
    details.open = open;
    details.dispatchEvent(new dom.window.Event('toggle'));
  });
}

function makeClient({ searchImpl, approximateWinImpl }) {
  return {
    archivedBoardSearchAssetUrl: () => 'http://127.0.0.1:8000/archive.jpg',
    getBoardSearchApproximateWin: approximateWinImpl,
    // No quad in `geometry`: the crop-preview feature (TASK-0655) falls back
    // to showing the full image, which is all these tests care about.
    getOperationalImageReviewItem: async () => ({ data: { geometry: {} } }),
    listSymbols: async () => ({ data: [symbol] }),
    operationalImageReviewBoardAssetUrl: () =>
      'http://127.0.0.1:8000/board.jpg',
    searchGameBoards: searchImpl,
    symbolImageAssetUrl: () => 'http://127.0.0.1:8000/symbol.jpg',
  };
}

async function renderWorkspaceWithResults(client) {
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
  await click(symbolButton());
  await click(searchButton());
  await eventually(
    () => document.querySelector('.boardSearchResults') !== null,
    'search results should render',
  );
  return root;
}

test('collapsed section issues no requests even while switching candidates', async () => {
  const approximateWinCalls = [];
  const client = makeClient({
    approximateWinImpl: async (_gameId, options) => {
      approximateWinCalls.push(options);
      return { data: approximateWinResponse(options.startSequenceNumber) };
    },
    searchImpl: async () => ({
      data: { results: [boardResult(10), boardResult(19)] },
    }),
  });
  const root = await renderWorkspaceWithResults(client);

  const details = approximateWinDetails();
  assert.equal(details.open, false);

  await click(
    [...document.querySelectorAll('button')].find((node) =>
      node.textContent.includes('Następna'),
    ),
  );
  await settle();

  assert.equal(approximateWinCalls.length, 0);
  await act(async () => root.unmount());
});

test('first expansion calculates for the currently selected board with the default range', async () => {
  const approximateWinCalls = [];
  const client = makeClient({
    approximateWinImpl: async (_gameId, options) => {
      approximateWinCalls.push(options);
      return { data: approximateWinResponse(options.startSequenceNumber) };
    },
    searchImpl: async () => ({ data: { results: [boardResult(10)] } }),
  });
  const root = await renderWorkspaceWithResults(client);

  await toggleDetails(approximateWinDetails(), true);
  await eventually(() => approximateWinCalls.length === 1, 'should calculate once');

  assert.deepEqual(approximateWinCalls[0], {
    spinCount: 1000,
    startSequenceNumber: 10,
  });
  await act(async () => root.unmount());
});

test('changing the selected board while open refreshes the result', async () => {
  const approximateWinCalls = [];
  const client = makeClient({
    approximateWinImpl: async (_gameId, options) => {
      approximateWinCalls.push(options);
      return { data: approximateWinResponse(options.startSequenceNumber) };
    },
    searchImpl: async () => ({
      data: { results: [boardResult(10), boardResult(19)] },
    }),
  });
  const root = await renderWorkspaceWithResults(client);

  await toggleDetails(approximateWinDetails(), true);
  await eventually(() => approximateWinCalls.length === 1, 'initial calculation');
  assert.equal(approximateWinCalls[0].startSequenceNumber, 10);

  await click(
    [...document.querySelectorAll('button')].find((node) =>
      node.textContent.includes('Następna'),
    ),
  );
  await eventually(() => approximateWinCalls.length === 2, 'refreshed calculation');
  assert.equal(approximateWinCalls[1].startSequenceNumber, 19);

  await act(async () => root.unmount());
});

test('typing in the range input does not send a request; committing it does', async () => {
  const approximateWinCalls = [];
  const client = makeClient({
    approximateWinImpl: async (_gameId, options) => {
      approximateWinCalls.push(options);
      return { data: approximateWinResponse(options.startSequenceNumber) };
    },
    searchImpl: async () => ({ data: { results: [boardResult(10)] } }),
  });
  const root = await renderWorkspaceWithResults(client);

  await toggleDetails(approximateWinDetails(), true);
  await eventually(() => approximateWinCalls.length === 1, 'initial calculation');

  await act(async () => setInputValue(rangeInput(), '2'));
  await act(async () => setInputValue(rangeInput(), '25'));
  await settle();
  assert.equal(approximateWinCalls.length, 1, 'typing alone must not request');

  await act(async () => pressEnter(rangeInput()));
  await eventually(() => approximateWinCalls.length === 2, 'commit should request');
  assert.equal(approximateWinCalls[1].spinCount, 25);

  await act(async () => root.unmount());
});

test('a stale response for a superseded board never overwrites the current result', async () => {
  const firstBoard = deferred();
  const secondBoard = deferred();
  const calls = [];
  const client = makeClient({
    approximateWinImpl: async (_gameId, options) => {
      calls.push(options);
      if (options.startSequenceNumber === 10) return await firstBoard.promise;
      return await secondBoard.promise;
    },
    searchImpl: async () => ({
      data: { results: [boardResult(10), boardResult(19)] },
    }),
  });
  const root = await renderWorkspaceWithResults(client);

  await toggleDetails(approximateWinDetails(), true);
  await eventually(() => calls.length === 1, 'first request in flight');

  await click(
    [...document.querySelectorAll('button')].find((node) =>
      node.textContent.includes('Następna'),
    ),
  );
  await eventually(() => calls.length === 2, 'second request in flight');

  // Resolve the newer (second) request first, then the stale first one.
  secondBoard.resolve({ data: approximateWinResponse(19) });
  await eventually(
    () => document.body.textContent.includes('Plansza startowa #19'),
    'second board result should render',
  );
  firstBoard.resolve({ data: approximateWinResponse(10) });
  await settle();

  assert.ok(document.body.textContent.includes('Plansza startowa #19'));
  assert.ok(!document.body.textContent.includes('Plansza startowa #10'));

  await act(async () => root.unmount());
});

test('collapsing while loading does not crash; reopening with the same key reuses the result without refetching', async () => {
  const pending = deferred();
  const calls = [];
  const client = makeClient({
    approximateWinImpl: async (_gameId, options) => {
      calls.push(options);
      return await pending.promise;
    },
    searchImpl: async () => ({ data: { results: [boardResult(10)] } }),
  });
  const root = await renderWorkspaceWithResults(client);

  const details = approximateWinDetails();
  await toggleDetails(details, true);
  await eventually(() => calls.length === 1, 'request started');

  await toggleDetails(details, false);
  pending.resolve({ data: approximateWinResponse(10) });
  await settle();

  await toggleDetails(details, true);
  await settle();
  // Same (board, range) key as before: no new network call, but the
  // previously resolved result is shown from memory (no server-side cache
  // exists — TASK-0651/0652 — this is the client's own in-memory reuse).
  assert.equal(calls.length, 1);
  await eventually(
    () => document.body.textContent.includes('Plansza startowa #10'),
    'cached result should render on reopen',
  );

  await act(async () => root.unmount());
});

test('without a selected result, opening shows a message and issues no request', async () => {
  const approximateWinCalls = [];
  const client = makeClient({
    approximateWinImpl: async (_gameId, options) => {
      approximateWinCalls.push(options);
      return { data: approximateWinResponse(options.startSequenceNumber) };
    },
    searchImpl: async () => ({ data: { results: [] } }),
  });
  const root = await renderWorkspaceWithResults(client);

  await toggleDetails(approximateWinDetails(), true);
  await settle();

  assert.equal(approximateWinCalls.length, 0);
  assert.ok(
    document.body.textContent.includes('Najpierw wybierz wynik wyszukiwania'),
  );
  await act(async () => root.unmount());
});

test('a technical error shows an alert without fabricating zero metrics', async () => {
  const client = makeClient({
    approximateWinImpl: async () => ({
      error: { code: 'APPROXIMATE_WIN_RULES_NOT_PUBLISHED', message: 'no rules' },
    }),
    searchImpl: async () => ({ data: { results: [boardResult(10)] } }),
  });
  const root = await renderWorkspaceWithResults(client);

  await toggleDetails(approximateWinDetails(), true);
  await eventually(
    () =>
      approximateWinDetails().querySelector('.feedbackBannerError') !== null,
    'error banner should render',
  );

  assert.equal(
    document.body.textContent.includes('Rozpoznane wypłaty'),
    false,
  );
  await act(async () => root.unmount());
});
