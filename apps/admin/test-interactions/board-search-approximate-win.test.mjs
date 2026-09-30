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
const { BoardSearchWorkspace } =
  await import('../src/features/board-search/board-search-workspace.tsx');

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
    completeness: {
      completeBoardCount: 0,
      missingBoardCount: 2500,
      partialBoardCount: 0,
    },
    dataFingerprintSha256: 'a'.repeat(64),
    dataSource: 'operational_review',
    evaluatedSpinCount: 2500,
    gameId,
    requestedSpinCount: 2500,
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
    summary: {
      balanceCredits: -50000,
      recognizedPayoutCredits: 0,
      spinCostCredits: 50000,
    },
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
  const current = [
    ...document.querySelectorAll('.boardSearchSymbolButton'),
  ].find((node) => node.title === symbol.name);
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

function minimumPayoutInput() {
  const current = document.querySelector(
    'input[aria-label="Minimalna wypłata w tabeli"]',
  );
  assert.ok(current);
  return current;
}

function selectByLabel(text) {
  const label = [...document.querySelectorAll('label')].find(
    (node) => node.querySelector('span')?.textContent === text,
  );
  const select = label?.querySelector('select');
  assert.ok(select, `select labelled ${text} should render`);
  return select;
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
  await eventually(
    () => approximateWinCalls.length === 1,
    'should calculate once',
  );

  assert.deepEqual(approximateWinCalls[0], {
    spinCount: 2500,
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
  await eventually(
    () => approximateWinCalls.length === 1,
    'initial calculation',
  );
  assert.equal(approximateWinCalls[0].startSequenceNumber, 10);

  await click(
    [...document.querySelectorAll('button')].find((node) =>
      node.textContent.includes('Następna'),
    ),
  );
  await eventually(
    () => approximateWinCalls.length === 2,
    'refreshed calculation',
  );
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
  await eventually(
    () => approximateWinCalls.length === 1,
    'initial calculation',
  );

  await act(async () => setInputValue(rangeInput(), '2'));
  await act(async () => setInputValue(rangeInput(), '25'));
  await settle();
  assert.equal(approximateWinCalls.length, 1, 'typing alone must not request');

  await act(async () => pressEnter(rangeInput()));
  await eventually(
    () => approximateWinCalls.length === 2,
    'commit should request',
  );
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

test('collapsing while loading does not crash; reopening recalculates from current data', async () => {
  const pending = deferred();
  const calls = [];
  const client = makeClient({
    approximateWinImpl: async (_gameId, options) => {
      calls.push(options);
      return calls.length === 1
        ? await pending.promise
        : { data: approximateWinResponse(10) };
    },
    searchImpl: async () => ({ data: { results: [boardResult(10)] } }),
  });
  const root = await renderWorkspaceWithResults(client);

  const details = approximateWinDetails();
  await toggleDetails(details, true);
  await eventually(() => calls.length === 1, 'request started');

  await toggleDetails(details, false);
  // The discarded in-flight response describes another board; it must never
  // render after the section was collapsed.
  pending.resolve({ data: approximateWinResponse(99) });
  await settle();

  await toggleDetails(details, true);
  // D-462: symbols verified meanwhile can change the payout for the same
  // (board, range) key, so reopening always issues a fresh request.
  await eventually(() => calls.length === 2, 'reopening recalculates');
  await eventually(
    () => document.body.textContent.includes('Plansza startowa #10'),
    'fresh result should render on reopen',
  );
  await settle();
  assert.equal(calls.length, 2);
  assert.ok(!document.body.textContent.includes('Plansza startowa #99'));

  await act(async () => root.unmount());
});

test('reopening after a ready result recalculates exactly once', async () => {
  const calls = [];
  const client = makeClient({
    approximateWinImpl: async (_gameId, options) => {
      calls.push(options);
      return { data: approximateWinResponse(10) };
    },
    searchImpl: async () => ({ data: { results: [boardResult(10)] } }),
  });
  const root = await renderWorkspaceWithResults(client);

  const details = approximateWinDetails();
  await toggleDetails(details, true);
  await eventually(
    () => document.body.textContent.includes('Plansza startowa #10'),
    'first result renders',
  );
  await toggleDetails(details, false);
  await toggleDetails(details, true);
  await eventually(() => calls.length === 2, 'reopening recalculates');
  await settle();
  assert.equal(calls.length, 2);

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

test('renders every payout row in one scrollable table and shows its cumulative-balance chart', async () => {
  const rows = Array.from({ length: 25 }, (_, index) => ({
    boardStatus: 'accepted',
    cumulativeBalanceCredits:
      ((index + 1) * (index + 2) * 100) / 2 - (index + 1) * 20,
    cumulativeCostCredits: (index + 1) * 20,
    cumulativePayoutCredits: ((index + 1) * (index + 2) * 100) / 2,
    payoutCredits: (index + 1) * 100,
    payoutKind: 'exact',
    sequenceNumber: index + 1,
    spinNumber: index + 1,
  }));
  let approximateWinCalls = 0;
  const client = makeClient({
    approximateWinImpl: async (_gameId, options) => {
      approximateWinCalls += 1;
      return {
        data: approximateWinResponse(options.startSequenceNumber, {
          completeness: {
            completeBoardCount: 25,
            missingBoardCount: 0,
            partialBoardCount: 0,
          },
          rows,
          // 2 500 evaluated spins at 20 credits; the last payout is spin 25.
          summary: {
            balanceCredits: -17500,
            recognizedPayoutCredits: 32500,
            spinCostCredits: 50000,
          },
        }),
      };
    },
    searchImpl: async () => ({ data: { results: [boardResult(10)] } }),
  });
  const root = await renderWorkspaceWithResults(client);

  await toggleDetails(approximateWinDetails(), true);
  await eventually(
    () =>
      document.querySelectorAll('.boardSearchApproximateWin tbody tr')
        .length === 25,
    'all payout rows should render in the single table',
  );

  assert.equal(
    document.querySelector(
      '.boardSearchApproximateWin .boardSearchResultNavigation',
    ),
    null,
  );
  assert.ok(document.querySelector('.boardSearchApproximateWinChart svg'));
  assert.match(
    document.querySelector('.boardSearchApproximateWinChart').textContent,
    /Bilans według liczby spinów/,
  );
  assert.deepEqual(
    [...document.querySelectorAll('.boardSearchApproximateWin thead th')].map(
      (node) => node.textContent,
    ),
    ['Spin', 'Plansza', 'Wypłata', 'Bilans narastająco', 'Akcje'],
  );

  const summaryBefore = document.querySelector(
    '.boardSearchApproximateWin .importMetrics',
  ).textContent;
  const chartBefore = document
    .querySelector('.boardSearchApproximateWinChartSeries')
    .getAttribute('points');
  const callsBefore = approximateWinCalls;
  await act(async () => setInputValue(minimumPayoutInput(), '1000'));
  await eventually(
    () =>
      document.querySelectorAll('.boardSearchApproximateWin tbody tr')
        .length === 16,
    'the slider should filter visible payout rows locally',
  );
  await settle();
  // The filter is local: no new calculation, same summary and chart.
  assert.equal(approximateWinCalls, callsBefore);
  assert.equal(
    document.querySelector('.boardSearchApproximateWin .importMetrics')
      .textContent,
    summaryBefore,
  );
  assert.equal(
    document
      .querySelector('.boardSearchApproximateWinChartSeries')
      .getAttribute('points'),
    chartBefore,
  );
  assert.ok(
    document.querySelector('.boardSearchApproximateWinChartZero'),
    'a balance crossing zero shows the zero line',
  );

  const chart = document.querySelector('.boardSearchApproximateWinChart svg');
  Object.defineProperty(chart, 'getBoundingClientRect', {
    value: () => ({ left: 0, width: 800 }),
  });
  assert.ok(
    document.querySelectorAll('.boardSearchApproximateWinChartGrid line')
      .length >= 6,
    'the chart draws horizontal and vertical grid lines',
  );
  await act(async () =>
    chart.dispatchEvent(
      new dom.window.MouseEvent('pointermove', {
        bubbles: true,
        clientX: 800,
      }),
    ),
  );
  await eventually(
    () =>
      document.querySelector('.boardSearchApproximateWinChartLabel') !== null,
    'hovering the chart should show a label in the band above the plot',
  );
  assert.match(
    document.querySelector('.boardSearchApproximateWinChartLabel').textContent,
    /2500 spinów.*Bilans: -17/,
  );
  assert.ok(
    document.querySelector('.boardSearchApproximateWinChartLeader'),
    'the label is connected to its point by a dotted leader line',
  );

  // Clicking pins the nearest point; the pinned label stays without hover.
  await act(async () =>
    chart.dispatchEvent(
      new dom.window.MouseEvent('click', { bubbles: true, clientX: 800 }),
    ),
  );
  // Escape clears the hover highlight (as leaving the chart would).
  await act(async () =>
    chart.dispatchEvent(
      new dom.window.KeyboardEvent('keydown', {
        bubbles: true,
        cancelable: true,
        key: 'Escape',
      }),
    ),
  );
  await settle();
  assert.equal(
    document.querySelectorAll('.boardSearchApproximateWinChartLabelPinned')
      .length,
    1,
  );
  assert.match(
    document.querySelector('.boardSearchApproximateWinChartPins').textContent,
    /2500 spinów/,
  );

  // Keyboard: ArrowRight from nothing highlights the first point; Enter pins it.
  await act(async () =>
    chart.dispatchEvent(
      new dom.window.KeyboardEvent('keydown', {
        bubbles: true,
        cancelable: true,
        key: 'ArrowRight',
      }),
    ),
  );
  await act(async () =>
    chart.dispatchEvent(
      new dom.window.KeyboardEvent('keydown', {
        bubbles: true,
        cancelable: true,
        key: 'Enter',
      }),
    ),
  );
  await settle();
  assert.equal(
    document.querySelectorAll('.boardSearchApproximateWinChartLabelPinned')
      .length,
    2,
  );

  // "×" on a pinned label unpins it; "Wyczyść punkty" clears the rest.
  await click(
    document.querySelector(
      '.boardSearchApproximateWinChartLabelPinned .boardSearchApproximateWinChartUnpin',
    ),
  );
  assert.equal(
    document.querySelectorAll('.boardSearchApproximateWinChartLabelPinned')
      .length,
    1,
  );
  const clear = [
    ...document.querySelectorAll('.boardSearchApproximateWinChart button'),
  ].find((node) => node.textContent === 'Wyczyść punkty');
  assert.ok(clear);
  await click(clear);
  assert.equal(
    document.querySelectorAll('.boardSearchApproximateWinChartLabelPinned')
      .length,
    0,
  );
  assert.equal(
    document.querySelector('.boardSearchApproximateWinChartPins'),
    null,
  );
  await act(async () => root.unmount());
});

test('a technical error shows an alert without fabricating zero metrics', async () => {
  const client = makeClient({
    approximateWinImpl: async () => ({
      error: {
        code: 'APPROXIMATE_WIN_RULES_NOT_PUBLISHED',
        message: 'no rules',
      },
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

  assert.equal(document.body.textContent.includes('Rozpoznane wypłaty'), false);
  await act(async () => root.unmount());
});

test('shows an explicit empty chart state when the range has no payouts', async () => {
  const client = makeClient({
    approximateWinImpl: async (_gameId, options) => ({
      data: approximateWinResponse(options.startSequenceNumber),
    }),
    searchImpl: async () => ({ data: { results: [boardResult(10)] } }),
  });
  const root = await renderWorkspaceWithResults(client);

  await toggleDetails(approximateWinDetails(), true);
  await eventually(
    () => document.querySelector('.boardSearchApproximateWinChart') !== null,
    'the empty chart state should render',
  );

  assert.match(
    document.querySelector('.boardSearchApproximateWinChart').textContent,
    /Wykres pojawi się po rozpoznaniu pierwszej wypłaty/,
  );
  await act(async () => root.unmount());
});

test('stake and unit re-scale every amount locally without a new request', async (context) => {
  context.after(() => dom.window.localStorage.clear());
  const rows = [
    {
      boardStatus: 'accepted',
      cumulativeBalanceCredits: 80,
      cumulativeCostCredits: 20,
      cumulativePayoutCredits: 100,
      payoutCredits: 100,
      payoutKind: 'exact',
      sequenceNumber: 11,
      spinNumber: 1,
    },
    {
      boardStatus: 'accepted',
      cumulativeBalanceCredits: 1040,
      cumulativeCostCredits: 60,
      cumulativePayoutCredits: 1100,
      payoutCredits: 1000,
      payoutKind: 'exact',
      sequenceNumber: 13,
      spinNumber: 3,
    },
  ];
  let calls = 0;
  const client = makeClient({
    approximateWinImpl: async (_gameId, options) => {
      calls += 1;
      return {
        data: approximateWinResponse(options.startSequenceNumber, {
          evaluatedSpinCount: 10,
          requestedSpinCount: 10,
          rows,
          summary: {
            balanceCredits: 900,
            recognizedPayoutCredits: 1100,
            spinCostCredits: 200,
          },
        }),
      };
    },
    searchImpl: async () => ({ data: { results: [boardResult(10)] } }),
  });
  const root = await renderWorkspaceWithResults(client);
  await toggleDetails(approximateWinDetails(), true);
  await eventually(
    () =>
      document.querySelectorAll('.boardSearchApproximateWin tbody tr')
        .length === 2,
    'rows should render',
  );
  const firstPayout = () =>
    document.querySelector(
      '.boardSearchApproximateWin tbody tr td:nth-child(3)',
    ).textContent;
  const metrics = () =>
    [
      ...document.querySelectorAll(
        '.boardSearchApproximateWin .importMetric dd',
      ),
    ].map((node) => node.textContent);
  // Base stake (spin cost 20 credits = 2 zł) in credits: unchanged view.
  assert.equal(firstPayout(), '100');
  assert.deepEqual(metrics(), ['1100', '200', '900']);

  await act(async () => setInputValue(minimumPayoutInput(), '500'));
  await eventually(
    () =>
      document.querySelectorAll('.boardSearchApproximateWin tbody tr')
        .length === 1,
    'threshold filters the first row',
  );

  const stakeSelect = selectByLabel('Stawka');
  const unitSelect = selectByLabel('Jednostka');
  assert.ok(stakeSelect && unitSelect);
  const choose = async (select, value) => {
    await act(async () => {
      select.value = value;
      select.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
    });
  };
  await choose(stakeSelect, '600');
  // 6 zł / 2 zł = multiplier 3; the threshold (base credits) is kept.
  assert.equal(
    document.querySelectorAll('.boardSearchApproximateWin tbody tr').length,
    1,
  );
  assert.equal(firstPayout(), '3000');
  assert.deepEqual(metrics(), ['3300', '600', '2700']);
  assert.match(
    document.querySelector('.boardSearchApproximateWinDisplay').textContent,
    /mnożnik 3/,
  );
  await choose(unitSelect, 'pln');
  assert.equal(firstPayout(), '300,00 zł');
  assert.equal(
    document.querySelectorAll('.boardSearchApproximateWin tbody tr').length,
    1,
    'the threshold survives a unit change',
  );
  assert.deepEqual(metrics(), ['330,00 zł', '60,00 zł', '270,00 zł']);
  assert.match(
    document.querySelector('.boardSearchApproximateWinChartGrid')?.parentElement
      .textContent ?? '',
    /zł/,
  );
  assert.equal(calls, 1, 'changing stake or unit sends no request');
  assert.equal(
    JSON.parse(
      dom.window.localStorage.getItem(
        'game-predictor-approximate-win-display-v1',
      ),
    ).unit,
    'pln',
  );
  // Choosing the base option stores `null`, so it follows the spin cost.
  await choose(stakeSelect, '200');
  assert.equal(
    JSON.parse(
      dom.window.localStorage.getItem(
        'game-predictor-approximate-win-display-v1',
      ),
    ).stakeGrosze,
    null,
  );
  await act(async () => root.unmount());
});

test('a zero spin cost disables the stake and keeps złote at credits / 10', async (context) => {
  context.after(() => dom.window.localStorage.clear());
  const client = makeClient({
    approximateWinImpl: async (_gameId, options) => ({
      data: approximateWinResponse(options.startSequenceNumber, {
        rows: [
          {
            boardStatus: 'accepted',
            cumulativeBalanceCredits: 500,
            cumulativeCostCredits: 0,
            cumulativePayoutCredits: 500,
            payoutCredits: 500,
            payoutKind: 'exact',
            sequenceNumber: 11,
            spinNumber: 1,
          },
        ],
        rules: {
          algorithmVersion: 'payout-v3-unknown-prefix-stop',
          rulesVersion: 1,
          rulesVersionId: 'rules-1',
          spinCost: 0,
        },
        summary: {
          balanceCredits: 500,
          recognizedPayoutCredits: 500,
          spinCostCredits: 0,
        },
      }),
    }),
    searchImpl: async () => ({ data: { results: [boardResult(10)] } }),
  });
  const root = await renderWorkspaceWithResults(client);
  await toggleDetails(approximateWinDetails(), true);
  await eventually(
    () =>
      document.querySelector('.boardSearchApproximateWin tbody tr') !== null,
    'row should render',
  );
  assert.equal(selectByLabel('Stawka').disabled, true);
  assert.match(
    document.querySelector('.boardSearchApproximateWinDisplay').textContent,
    /Koszt spinu opublikowanych reguł wynosi 0/,
  );
  const unit = selectByLabel('Jednostka');
  await act(async () => {
    unit.value = 'pln';
    unit.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
  });
  assert.equal(
    document.querySelector(
      '.boardSearchApproximateWin tbody tr td:nth-child(3)',
    ).textContent,
    '50,00 zł',
  );
  await act(async () => root.unmount());
});

function withDialogSupport() {
  const proto = dom.window.HTMLDialogElement.prototype;
  if (typeof proto.showModal !== 'function') {
    proto.showModal = function showModal() {
      this.setAttribute('open', '');
    };
    proto.close = function close() {
      this.removeAttribute('open');
    };
  }
}

function linesDetail(sequenceNumber, overrides = {}) {
  const polygons = Array.from({ length: 15 }, (_, index) => {
    const x = (index % 5) / 5;
    const y = Math.floor(index / 5) / 3;
    return [
      { x, y },
      { x: x + 0.2, y },
      { x: x + 0.2, y: y + 1 / 3 },
      { x, y: y + 1 / 3 },
    ];
  });
  return {
    boardChecksumSha256: 'c'.repeat(64),
    boardStatus: 'accepted',
    dataSource: 'operational_review',
    gameId,
    matches: [
      {
        jokerCells: [],
        matchedCells: [0, 1, 2, 3],
        matchedLength: 4,
        paylineCode: 'L1',
        paylineDisplayOrder: 0,
        paylineId: 'top',
        paylineName: 'Górna',
        payoutCredits: 60,
        rowPath: [0, 0, 0, 0, 0],
        symbolCode: 'cherry',
      },
      {
        jokerCells: [5],
        matchedCells: [5, 6, 7],
        matchedLength: 3,
        paylineCode: 'L2',
        paylineDisplayOrder: 1,
        paylineId: 'middle',
        paylineName: 'Środkowa',
        payoutCredits: 40,
        rowPath: [1, 1, 1, 1, 1],
        symbolCode: 'cherry',
      },
    ],
    payoutCredits: 100,
    payoutKind: 'confirmed_minimum',
    rules: {
      algorithmVersion: 'payout-v3-unknown-prefix-stop',
      rulesVersion: 1,
      rulesVersionId: 'rules-1',
      spinCost: 20,
    },
    sequenceNumber,
    symbolCodes: [
      'cherry',
      'cherry',
      'cherry',
      'cherry',
      null,
      'cherry',
      'cherry',
      'cherry',
      null,
      null,
      null,
      null,
      null,
      null,
      null,
    ],
    view: {
      cellPolygons: polygons,
      height: 300,
      revision: 'd'.repeat(64),
      width: 500,
    },
    ...overrides,
  };
}

function dialogButton(text) {
  return [
    ...document.querySelectorAll('.boardSearchBoardLinesDialog button'),
  ].find((node) => node.textContent === text);
}

test('the action column opens a board modal with toggleable payline legend', async (context) => {
  withDialogSupport();
  context.after(() => dom.window.localStorage.clear());
  const detailCalls = [];
  let detailImpl = async (_gameId, sequenceNumber) => ({
    data: linesDetail(sequenceNumber),
  });
  let rangeCalls = 0;
  const client = {
    ...makeClient({
      approximateWinImpl: async (_gameId, options) => {
        rangeCalls += 1;
        return {
          data: approximateWinResponse(options.startSequenceNumber, {
            evaluatedSpinCount: 10,
            requestedSpinCount: 10,
            rows: [
              {
                boardStatus: 'accepted',
                cumulativeBalanceCredits: 80,
                cumulativeCostCredits: 20,
                cumulativePayoutCredits: 100,
                payoutCredits: 100,
                payoutKind: 'confirmed_minimum',
                sequenceNumber: 11,
                spinNumber: 1,
              },
            ],
          }),
        };
      },
      searchImpl: async () => ({ data: { results: [boardResult(10)] } }),
    }),
    boardSearchBoardViewUrl: (_gameId, sequenceNumber, checksum, revision) =>
      'http://127.0.0.1:8000/view/' +
      sequenceNumber +
      '?c=' +
      checksum +
      '&r=' +
      revision,
    getBoardSearchBoardDetail: (gameIdArgument, sequenceNumber) => {
      detailCalls.push([gameIdArgument, sequenceNumber]);
      return detailImpl(gameIdArgument, sequenceNumber);
    },
  };
  const root = await renderWorkspaceWithResults(client);
  await toggleDetails(approximateWinDetails(), true);
  await eventually(
    () =>
      document.querySelector('.boardSearchApproximateWin tbody tr') !== null,
    'row should render',
  );
  assert.equal(
    document.querySelectorAll('.boardSearchApproximateWin thead th').length,
    5,
  );
  const open = document.querySelector(
    'button[aria-label="Pokaż planszę #11 z liniami wypłat"]',
  );
  assert.ok(open);
  await click(open);
  await eventually(
    () => document.querySelectorAll('.boardSearchBoardLinesMatch').length === 2,
    'both lines should be drawn',
  );
  assert.deepEqual(detailCalls, [[gameId, 11]]);
  assert.ok(
    document
      .querySelector('.boardSearchBoardLinesCanvas image')
      .getAttribute('href')
      .endsWith('r=' + 'd'.repeat(64)),
  );
  // Unknown cells carry the "?" overlay; the joker cell a "J" marker.
  assert.equal(
    document.querySelectorAll('.boardSearchBoardLinesUnknown').length,
    8,
  );
  assert.equal(
    document.querySelectorAll('.boardSearchBoardLinesJoker').length,
    1,
  );

  const toggles = [
    ...document.querySelectorAll(
      '.boardSearchBoardLinesLegend input[type="checkbox"]',
    ),
  ];
  assert.equal(toggles.length, 2);
  await click(toggles[0]);
  assert.deepEqual(
    [...document.querySelectorAll('.boardSearchBoardLinesMatch')].map((node) =>
      node.getAttribute('data-line'),
    ),
    ['middle:cherry'],
  );
  const legendButton = (text) =>
    [...document.querySelectorAll('.boardSearchBoardLinesLegend button')].find(
      (node) => node.textContent === text,
    );
  await click(legendButton('Ukryj wszystkie'));
  assert.equal(
    document.querySelectorAll('.boardSearchBoardLinesMatch').length,
    0,
  );
  await click(legendButton('Pokaż wszystkie'));
  assert.equal(
    document.querySelectorAll('.boardSearchBoardLinesMatch').length,
    2,
  );

  // A broken image falls back to the 3 x 5 schema with the same lines.
  await act(async () =>
    document
      .querySelector('.boardSearchBoardLinesCanvas image')
      .dispatchEvent(new dom.window.Event('error')),
  );
  assert.equal(
    document.querySelectorAll('.boardSearchBoardLinesSchemaCell').length,
    15,
  );
  assert.equal(
    document.querySelectorAll('.boardSearchBoardLinesMatch').length,
    2,
  );

  await click(dialogButton('Zamknij'));
  assert.equal(document.querySelector('.boardSearchBoardLinesDialog'), null);
  assert.equal(document.activeElement, open, 'focus returns to the row button');

  // Reopening starts with every line visible again, even after hiding one.
  await click(open);
  await eventually(
    () => document.querySelectorAll('.boardSearchBoardLinesMatch').length === 2,
    'modal redraws both lines',
  );
  await click(
    document.querySelectorAll(
      '.boardSearchBoardLinesLegend input[type="checkbox"]',
    )[1],
  );
  assert.equal(
    document.querySelectorAll('.boardSearchBoardLinesMatch').length,
    1,
  );
  // Esc (the dialog "cancel" event) closes the modal as well.
  await act(async () =>
    document
      .querySelector('.boardSearchBoardLinesDialog')
      .dispatchEvent(new dom.window.Event('cancel', { cancelable: true })),
  );
  assert.equal(document.querySelector('.boardSearchBoardLinesDialog'), null);
  await click(open);
  await eventually(
    () => document.querySelectorAll('.boardSearchBoardLinesMatch').length === 2,
    'reopened modal draws both lines',
  );
  await click(dialogButton('Zamknij'));

  // A board without a view falls back to the schema with the same lines.
  detailImpl = async (_gameId, sequenceNumber) => ({
    data: linesDetail(sequenceNumber, { view: null }),
  });
  await click(open);
  await eventually(
    () =>
      document.querySelectorAll('.boardSearchBoardLinesSchemaCell').length ===
      15,
    'schema fallback for a board without a view',
  );
  assert.equal(
    document.querySelectorAll('.boardSearchBoardLinesMatch').length,
    2,
  );
  assert.match(
    document.querySelector('.boardSearchBoardLinesNote').textContent,
    /niedostępne/,
  );
  await click(dialogButton('Zamknij'));

  // Error with retry.
  detailImpl = async () => ({ error: { code: 'X', message: 'boom' } });
  await click(open);
  await eventually(
    () => dialogButton('Spróbuj ponownie') !== undefined,
    'error offers a retry',
  );
  detailImpl = async (_gameId, sequenceNumber) => ({
    data: linesDetail(sequenceNumber, { payoutCredits: 90 }),
  });
  await click(dialogButton('Spróbuj ponownie'));
  // Payout changed since the table: no lines, only "Przelicz ponownie".
  await eventually(
    () => dialogButton('Przelicz ponownie') !== undefined,
    'inconsistent detail offers a recalculation',
  );
  assert.equal(
    document.querySelectorAll('.boardSearchBoardLinesMatch').length,
    0,
  );
  const callsBefore = rangeCalls;
  await click(dialogButton('Przelicz ponownie'));
  await settle();
  assert.equal(rangeCalls, callsBefore + 1);
  assert.equal(document.querySelector('.boardSearchBoardLinesDialog'), null);
  await act(async () => root.unmount());
});
