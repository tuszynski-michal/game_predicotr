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
const { BoardSearchWorkspace } =
  await import('../src/board-search-workspace.tsx');
const { superGameSeriesAdminHref } =
  await import('../src/board-search-super-game.ts');

after(() => dom.window.close());
afterEach(() => dom.window.localStorage.clear());

const gameId = '11111111-1111-4111-8111-111111111111';
const seriesId = '33333333-3333-4333-8333-333333333333';
const symbol = {
  code: 'cherry',
  displayOrder: 0,
  id: 'symbol-cherry',
  imagePath: null,
  mobileCode: 1,
  name: 'Wiśnia',
  status: 'active',
};

function marker(overrides = {}) {
  return {
    completeness: 'complete',
    kind: 'in_series',
    runVerification: 'verified',
    seriesId,
    seriesLength: 10,
    spinIndex: 3,
    superSymbolCode: 'K',
    ...overrides,
  };
}

function boardResult(sequenceNumber, superGame) {
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
    ...(superGame === undefined ? {} : { superGame }),
  };
}

function row(sequenceNumber, superGame) {
  return {
    boardStatus: 'accepted',
    countMatches: [],
    cumulativeBalanceCredits: 30,
    cumulativeCostCredits: 20,
    cumulativePayoutCredits: 50,
    payoutCredits: 50,
    payoutKind: 'exact',
    sequenceNumber,
    spinNumber: sequenceNumber - 99,
    ...(superGame === undefined ? {} : { superGame }),
  };
}

function approximateWinResponse(rows, superGameState) {
  return {
    completeness: {
      completeBoardCount: rows.length,
      missingBoardCount: 0,
      partialBoardCount: 0,
    },
    dataFingerprintSha256: 'a'.repeat(64),
    dataSource: 'operational_review',
    evaluatedSpinCount: 60,
    gameId,
    requestedSpinCount: 60,
    rows,
    rules: {
      algorithmVersion: 'payout-v3-unknown-prefix-stop',
      rulesVersion: 1,
      rulesVersionId: 'rules-1',
      spinCost: 20,
    },
    sequenceLength: 500000,
    startBoardStatus: null,
    startSequenceNumber: 99,
    summary: {
      balanceCredits: 30,
      recognizedPayoutCredits: 50,
      spinCostCredits: 20,
    },
    wrappedAtSequenceEnd: false,
    ...(superGameState === undefined ? {} : { superGameState }),
  };
}

const FRESH = { fresh: true, generationInputVersion: 7, inputVersion: 7 };
const STALE = { fresh: false, generationInputVersion: 7, inputVersion: 9 };

async function settle() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 15));
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
  await act(async () =>
    node.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })),
  );
}

function button(text) {
  return [...document.querySelectorAll('button')].find((node) =>
    node.textContent.includes(text),
  );
}

function makeClient({ results, searchState, rows, rangeState, withLinks }) {
  return {
    boardSearchBoardViewUrl: () => 'http://127.0.0.1:8000/view.webp',
    getBoardSearchApproximateWin: async () => ({
      data: approximateWinResponse(rows, rangeState),
    }),
    getOperationalImageReviewItem: async () => ({ data: { geometry: {} } }),
    listSymbols: async () => ({ data: [symbol] }),
    operationalImageReviewBoardAssetUrl: () =>
      'http://127.0.0.1:8000/board.jpg',
    searchGameBoards: async () => ({
      data: {
        gameId,
        queryCellCount: 1,
        results,
        scope: 'all_searchable',
        ...(searchState === undefined ? {} : { superGameState: searchState }),
      },
    }),
    symbolImageAssetUrl: () => 'http://127.0.0.1:8000/symbol.jpg',
    ...(withLinks ? { superGameSeriesHref: superGameSeriesAdminHref } : {}),
  };
}

async function renderWithResults(client) {
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(React.createElement(BoardSearchWorkspace, { client, gameId })),
  );
  await eventually(
    () => document.querySelector('.boardSearchSymbolButton') !== null,
    'palette should render',
  );
  await click(document.querySelector('.boardSearchSymbolButton'));
  await click(button('Szukaj plansz'));
  await eventually(
    () => document.querySelector('.boardSearchResults') !== null,
    'search results should render',
  );
  return root;
}

async function chooseBaseStake() {
  await eventually(() => {
    const stake = document.querySelector('select[aria-label="Stawka"]');
    return stake !== null && !stake.disabled;
  }, 'the stake select should enable');
  const stake = document.querySelector('select[aria-label="Stawka"]');
  const base = [...stake.options].find((option) =>
    option.textContent.includes('(bazowa)'),
  );
  assert.ok(base, 'a base stake option exists');
  await act(async () => {
    stake.value = base.value;
    stake.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
  });
  await eventually(
    () =>
      document.querySelector('.boardSearchApproximateWin tbody tr') !== null,
    'rows should render',
  );
}

function card() {
  return document.querySelector('.boardSearchResults');
}

test('a trigger board and a spin board get the gold marker and their labels', async () => {
  const client = makeClient({
    results: [
      boardResult(100, marker({ kind: 'trigger', spinIndex: null })),
      boardResult(103, marker()),
      boardResult(130),
    ],
    rows: [],
  });
  const root = await renderWithResults(client);

  assert.ok(card().classList.contains('boardSearchResultsSuperGame'));
  assert.equal(
    card().querySelector('.boardSearchSuperGameLabel').textContent,
    'Supergra: trigger',
  );
  await click(button('Następna'));
  assert.ok(card().classList.contains('boardSearchResultsSuperGame'));
  assert.equal(
    card().querySelector('.boardSearchSuperGameLabel').textContent,
    'Supergra: spin 3/10, symbol K',
  );
  await click(button('Następna'));
  // A board outside every series stays unmarked.
  assert.ok(!card().classList.contains('boardSearchResultsSuperGame'));
  assert.equal(card().querySelector('.boardSearchSuperGame'), null);
  await act(async () => root.unmount());
});

test('a series without a super symbol says it is still to be defined', async () => {
  const client = makeClient({
    results: [
      boardResult(105, marker({ spinIndex: 5, superSymbolCode: null })),
    ],
    rows: [],
  });
  const root = await renderWithResults(client);

  assert.equal(
    card().querySelector('.boardSearchSuperGameLabel').textContent,
    'Supergra: super symbol do zdefiniowania',
  );
  assert.equal(
    card().querySelector('.boardSearchSuperGameSpin').textContent,
    '(spin 5/10)',
  );
  await act(async () => root.unmount());
});

test('the warning covers the whole result, boards without a marker included', async () => {
  const client = makeClient({
    results: [boardResult(130)],
    searchState: STALE,
    rows: [],
  });
  const root = await renderWithResults(client);

  const banner = card().querySelector('.boardSearchSuperGameStale');
  assert.ok(banner, 'the stale banner is shown');
  assert.match(banner.textContent, /Serie w trakcie przeliczania/);
  assert.equal(card().querySelector('.boardSearchSuperGame'), null);
  await act(async () => root.unmount());
});

test('an empty result still shows the warning next to the empty message', async () => {
  const client = makeClient({ results: [], searchState: STALE, rows: [] });
  const root = await renderWithResults(client);

  assert.match(card().textContent, /Żadna plansza nie ma dodatniego/);
  assert.ok(card().querySelector('.boardSearchSuperGameStale'));
  assert.match(card().textContent, /Serie w trakcie przeliczania/);
  await act(async () => root.unmount());
});

test('a fresh generation shows no warning', async () => {
  const client = makeClient({
    results: [boardResult(103, marker())],
    searchState: FRESH,
    rows: [],
  });
  const root = await renderWithResults(client);

  assert.equal(document.querySelector('.boardSearchSuperGameStale'), null);
  await act(async () => root.unmount());
});

test('the series link exists only with the Admin capability', async () => {
  const undefinedSymbol = marker({ spinIndex: 5, superSymbolCode: null });
  const withLink = await renderWithResults(
    makeClient({
      results: [boardResult(105, undefinedSymbol)],
      rows: [],
      withLinks: true,
    }),
  );
  const link = card().querySelector('a.boardSearchSuperGameLink');
  assert.ok(link, 'the Admin gets the link');
  assert.equal(link.textContent, 'Zdefiniuj super symbol');
  assert.equal(
    link.getAttribute('href'),
    `?workspace=games&game=${gameId}&section=super-games&series=${seriesId}`,
  );
  await act(async () => withLink.unmount());

  const labelOnly = await renderWithResults(
    makeClient({
      results: [boardResult(105, undefinedSymbol)],
      rows: [],
    }),
  );
  assert.ok(card().querySelector('.boardSearchSuperGameLabel'));
  assert.equal(card().querySelector('a'), null, 'Reviewer and panel: no link');
  await act(async () => labelOnly.unmount());
});

test('a public marker without a series identity never renders a link', async () => {
  const publicMarker = marker({ spinIndex: 5, superSymbolCode: null });
  delete publicMarker.seriesId;
  const root = await renderWithResults(
    makeClient({
      results: [boardResult(105, publicMarker)],
      rows: [],
      withLinks: true,
    }),
  );
  assert.ok(card().querySelector('.boardSearchSuperGameLabel'));
  assert.equal(card().querySelector('a'), null);
  await act(async () => root.unmount());
});

test('approximate-win rows carry the gold marker, the link and the warning', async () => {
  const client = makeClient({
    results: [boardResult(99)],
    rows: [
      row(100, marker({ kind: 'trigger', spinIndex: null })),
      row(105, marker({ spinIndex: 5, superSymbolCode: null })),
      row(150),
    ],
    rangeState: STALE,
    withLinks: true,
  });
  const root = await renderWithResults(client);
  await chooseBaseStake();

  const rows = [
    ...document.querySelectorAll('.boardSearchApproximateWin tbody tr'),
  ];
  assert.equal(rows.length, 3);
  assert.deepEqual(
    rows.map((item) => item.classList.contains('boardSearchSuperGameRow')),
    [true, true, false],
  );
  assert.equal(
    rows[0].querySelector('.boardSearchSuperGameLabel').textContent,
    'Supergra: trigger',
  );
  assert.equal(
    rows[1].querySelector('.boardSearchSuperGameLabel').textContent,
    'Supergra: super symbol do zdefiniowania',
  );
  assert.equal(
    rows[1].querySelector('a.boardSearchSuperGameLink').textContent,
    'Zdefiniuj super symbol',
  );
  assert.equal(rows[2].querySelector('.boardSearchSuperGame'), null);
  assert.ok(
    document.querySelector(
      '.boardSearchApproximateWin .boardSearchSuperGameStale',
    ),
    'the range warns while the series are being recalculated',
  );
  await act(async () => root.unmount());
});

test('approximate-win rows of a label-only source show no link', async () => {
  const client = makeClient({
    results: [boardResult(99)],
    rows: [row(105, marker({ spinIndex: 5 }))],
    rangeState: FRESH,
  });
  const root = await renderWithResults(client);
  await chooseBaseStake();

  const item = document.querySelector('.boardSearchApproximateWin tbody tr');
  assert.equal(
    item.querySelector('.boardSearchSuperGameLabel').textContent,
    'Supergra: spin 5/10, symbol K',
  );
  assert.equal(item.querySelector('.boardSearchSuperGameLink'), null);
  assert.equal(
    document.querySelector(
      '.boardSearchApproximateWin .boardSearchSuperGameStale',
    ),
    null,
  );
  await act(async () => root.unmount());
});
