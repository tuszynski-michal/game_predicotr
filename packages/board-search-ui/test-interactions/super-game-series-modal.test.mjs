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
  'Node',
]) {
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
}
dom.window.HTMLDialogElement.prototype.showModal = function () {
  this.setAttribute('open', '');
};
dom.window.HTMLDialogElement.prototype.close = function () {
  this.removeAttribute('open');
};
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const { createRoot } = await import('react-dom/client');
const { BoardSearchWorkspace } =
  await import('../src/board-search-workspace.tsx');

after(() => dom.window.close());
afterEach(() => dom.window.localStorage.clear());

const gameId = 'shared';
const seriesId = '33333333-3333-4333-8333-333333333333';
const nextSeriesId = '44444444-4444-4444-8444-444444444444';
const FRESH = { fresh: true, generationInputVersion: 7, inputVersion: 7 };
const STALE = { fresh: false, generationInputVersion: 7, inputVersion: 9 };

const symbols = [
  symbol('cherry', 0),
  symbol('lemon', 1),
  symbol('mumia', 2, { superGameTriggerCount: 3 }),
];

function symbol(code, order, overrides = {}) {
  return {
    code: code.toUpperCase(),
    displayOrder: order,
    gameId,
    id: `symbol-${code}`,
    imagePath: null,
    isWildcard: false,
    mobileCode: order + 1,
    name: `Symbol ${code}`,
    nameEn: null,
    namePl: null,
    status: 'active',
    superGameTriggerCount: null,
    ...overrides,
  };
}

function marker(overrides = {}) {
  return {
    completeness: 'complete',
    kind: 'in_series',
    runVerification: 'verified',
    seriesId,
    seriesLength: 10,
    spinIndex: 3,
    superSymbolCode: null,
    ...overrides,
  };
}

function boardResult(sequenceNumber, superGame) {
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
    ...(superGame === undefined ? {} : { superGame }),
  };
}

function series(overrides = {}) {
  return {
    completeness: 'complete',
    definedAt: null,
    definedBy: null,
    endSequenceNumber: 110,
    gameId,
    id: seriesId,
    length: 10,
    retriggerSequenceNumbers: [],
    revision: 2,
    runVerification: 'verified',
    startSequenceNumber: 101,
    superSymbolId: null,
    triggerSequenceNumber: 100,
    updatedAt: '2026-10-18T10:00:00Z',
    ...overrides,
  };
}

function boardsOf(record) {
  const boards = [];
  for (
    let n = record.triggerSequenceNumber;
    n <= record.endSequenceNumber;
    n += 1
  ) {
    boards.push({
      assetMode: 'operational_review',
      boardChecksumSha256: `checksum-${n}`,
      importJobId: null,
      missing: false,
      recognizedBoardId: null,
      reviewItemId: null,
      role: n === record.triggerSequenceNumber ? 'trigger' : 'spin',
      sequenceNumber: n,
      spinIndex: n === record.triggerSequenceNumber ? null : n - 100,
      status: 'accepted',
    });
  }
  return boards;
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
    spinNumber: sequenceNumber - 102,
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
    startSequenceNumber: 103,
    summary: {
      balanceCredits: 30,
      recognizedPayoutCredits: 50,
      spinCostCredits: 20,
    },
    wrappedAtSequenceEnd: false,
    superGameState,
  };
}

/** The marker of a board as the search and the range see the store. */
function markerOf(record, spinIndex) {
  return marker({
    seriesId: record.id,
    spinIndex,
    superSymbolCode:
      record.superSymbolId === null
        ? null
        : symbols.find((symbol) => symbol.id === record.superSymbolId).code,
  });
}

function makeClient({
  state = FRESH,
  states = [],
  withRange = false,
  gate = null,
} = {}) {
  const calls = {
    corrections: [],
    next: [],
    ranges: 0,
    saves: [],
    searches: 0,
    series: [],
    states: 0,
  };
  const store = {
    [seriesId]: series(),
    [nextSeriesId]: series({
      endSequenceNumber: 210,
      id: nextSeriesId,
      startSequenceNumber: 201,
      triggerSequenceNumber: 200,
    }),
  };
  let corrected = false;
  return {
    calls,
    client: {
      boardSearchBoardViewUrl: () => 'http://127.0.0.1:8000/view.webp',
      correctBoardSearchCell: async (_gameId, sequence, cellIndex, body) => {
        calls.corrections.push({ body, cellIndex, sequence });
        corrected = true;
        return {
          data: {
            cellIndex,
            cellVersion: 'b'.repeat(64),
            changed: true,
            saved: true,
            sequenceNumber: sequence,
          },
        };
      },
      getBoardSearchApproximateWin: async () =>
        withRange
          ? ((calls.ranges += 1),
            {
              data: approximateWinResponse(
                [
                  row(103, markerOf(store[seriesId], 3)),
                  row(104, markerOf(store[seriesId], 4)),
                  row(130),
                ],
                state,
              ),
            })
          : { error: { message: 'no range in this test' } },
      getBoardSearchBoardDetail: async (_gameId, sequence) => ({
        data: {
          boardChecksumSha256: `checksum-${sequence}`,
          boardStatus: 'accepted',
          cells: Array.from({ length: 15 }, (_, cellIndex) => ({
            assignedSymbolCode: corrected ? 'LEMON' : 'CHERRY',
            cellIndex,
            cellVersion: (corrected ? 'b' : 'a').repeat(64),
            qualityIssue: null,
            reviewState: 'approved',
          })),
          countMatches: [],
          dataSource: 'operational_review',
          documentStale: false,
          gameId,
          matches: [],
          mode: 'base',
          payoutCredits: 0,
          payoutKind: 'none',
          rules: {
            algorithmVersion: 'payout-v3-unknown-prefix-stop',
            rulesVersion: 1,
            rulesVersionId: 'rules-1',
            spinCost: 20,
          },
          sequenceNumber: sequence,
          symbolCodes: Array(15).fill(corrected ? 'LEMON' : 'CHERRY'),
          view: null,
        },
      }),
      getSuperGameSeriesState: async () => {
        calls.states += 1;
        return { data: states.shift() ?? state };
      },
      listNextUndefinedSuperGameSeries: async (_gameId, query) => {
        calls.next.push(query.afterTrigger);
        return {
          data: {
            items: query.afterTrigger === 100 ? [store[nextSeriesId]] : [],
          },
        };
      },
      listSuperGameSeriesBoards: async (_gameId, id) => {
        calls.series.push(id);
        return {
          data: {
            boards: boardsOf(store[id]),
            series: store[id],
            superGameState: state,
          },
        };
      },
      listSymbols: async () => ({ data: symbols }),
      searchGameBoards: async () => {
        calls.searches += 1;
        return {
          data: {
            gameId,
            queryCellCount: 1,
            results: [
              boardResult(103, markerOf(store[seriesId], 3)),
              boardResult(130),
            ],
            scope: 'all_searchable',
            superGameState: state,
          },
        };
      },
      setSuperGameSeriesSuperSymbol: async (_gameId, id, body) => {
        calls.saves.push({ body, id });
        if (gate !== null) await gate.promise;
        store[id] = {
          ...store[id],
          revision: body.expectedRevision + 1,
          superSymbolId: body.symbolId,
        };
        return { data: store[id] };
      },
      symbolImageAssetUrl: () => 'http://127.0.0.1:8000/symbol.jpg',
    },
  };
}

async function settle() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 15));
  });
}

async function eventually(predicate, label, attempts = 40) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    if (predicate()) return;
    await settle();
  }
  assert.fail(label);
}

/** The freshness poll runs every 5 s: waits up to ~12 s. */
async function eventuallyPolled(predicate, label) {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    if (predicate()) return;
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 200));
    });
  }
  assert.fail(label);
}

async function click(node) {
  assert.ok(node);
  await act(async () =>
    node.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })),
  );
  await settle();
}

async function press(key, target = document.body, init = {}) {
  await act(async () =>
    target.dispatchEvent(
      new dom.window.KeyboardEvent('keydown', {
        bubbles: true,
        cancelable: true,
        key,
        ...init,
      }),
    ),
  );
  await settle();
}

function button(text, scope = document) {
  return [...scope.querySelectorAll('button')].find((node) =>
    node.textContent.includes(text),
  );
}

const dialog = () => document.querySelector('dialog.superGameSeriesModal');
const notice = () =>
  [...document.querySelectorAll('[role="status"], [role="alert"]')]
    .map((node) => node.textContent)
    .join(' | ');
const linesDialog = () =>
  document.querySelector('dialog:not(.superGameSeriesModal)');
const card = () => document.querySelector('.boardSearchResults');
const resultLabel = () =>
  card().querySelector('.boardSearchSuperGameLabel')?.textContent;

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
const pattern = () =>
  [...document.querySelectorAll('.boardSearchPatternCell')].map(
    (cell) => cell.textContent,
  );

async function renderWithResults(client, props = {}) {
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(BoardSearchWorkspace, {
        client,
        gameId,
        superGameSeries: { client },
        ...props,
      }),
    ),
  );
  await eventually(
    () => document.querySelector('.boardSearchSymbolButton') !== null,
    'palette should render',
  );
  await click(document.querySelector('.boardSearchSymbolButton'));
  await click(button('Szukaj plansz'));
  await eventually(() => card() !== null, 'search results should render');
  return root;
}

test('a marker is a button that opens the series view in a modal at the marked board', async () => {
  const { calls, client } = makeClient();
  const root = await renderWithResults(client);
  const open = card().querySelector('button.boardSearchSuperGameLink');
  assert.ok(open, 'the marker is a button with the share client');
  assert.equal(open.textContent, 'Zdefiniuj super symbol');
  assert.equal(card().querySelector('a.boardSearchSuperGameLink'), null);

  open.focus();
  await click(open);
  await eventually(() => dialog() !== null, 'the modal opens');
  assert.ok(dialog().hasAttribute('open'));
  assert.deepEqual(calls.series, [seriesId]);
  await eventually(
    () => dialog().querySelector('h4')?.textContent === 'Spin 3 · #103',
    'the carousel opens at the marked board',
  );
  assert.equal(button('Lista serii', dialog()), undefined);
  assert.equal(button('Przelicz serie', dialog()), undefined);
  assert.ok(dialog().querySelector('[aria-label="Karuzela pozycji serii"]'));

  // Closing without a change re-runs nothing.
  const searches = calls.searches;
  await click(button('Zamknij', dialog()));
  assert.equal(dialog(), null);
  assert.equal(calls.searches, searches);
  assert.equal(document.activeElement, open, 'the focus returns to the marker');
  await act(async () => root.unmount());
});

test('shortcuts in the modal belong to the series view, Esc does not close it, and a save re-runs the search', async () => {
  const { calls, client } = makeClient();
  const root = await renderWithResults(client);
  const before = pattern();
  await click(card().querySelector('button.boardSearchSuperGameLink'));
  await eventually(() => dialog() !== null, 'the modal opens');
  await eventually(
    () => dialog().querySelector('select') !== null,
    'the symbol select renders',
  );

  await press('2');
  assert.equal(dialog().querySelector('select').value, 'symbol-lemon');
  assert.deepEqual(pattern(), before, 'the digit did not touch the pattern');
  await press('Escape');
  assert.ok(dialog(), 'Esc cancels the choice, the modal stays');
  assert.equal(dialog().querySelector('select').value, '');
  await act(async () =>
    dialog().dispatchEvent(
      new dom.window.Event('cancel', { bubbles: false, cancelable: true }),
    ),
  );
  assert.ok(dialog(), 'the dialog cancel is blocked');

  const searches = calls.searches;
  await press('1');
  await press('Enter');
  await eventually(() => calls.saves.length === 1, 'the symbol is saved');
  assert.deepEqual(calls.saves[0], {
    body: { expectedRevision: 2, symbolId: 'symbol-cherry' },
    id: seriesId,
  });
  assert.equal(calls.searches, searches, 'no search while the modal is open');
  // TASK-1061: the modal stays on the saved series; `N` moves on by hand.
  await eventually(
    () => notice().includes('Zapisano super symbol Symbol cherry'),
    'the saved symbol is confirmed in place',
  );
  assert.equal(dialog().querySelector('select').value, 'symbol-cherry');
  assert.ok(!calls.series.includes(nextSeriesId), 'no automatic jump');
  await press('n');
  await eventually(
    () => dialog().querySelector('h4')?.textContent === 'Wyzwalacz · #200',
    'N opens the next series without a symbol',
  );
  await click(button('Zamknij', dialog()));
  await eventually(
    () => calls.searches === searches + 1,
    'the results are read again after the save',
  );
  assert.equal(dialog(), null);
  await act(async () => root.unmount());
});

test('a stale generation is polled in the modal and a fresh one re-reads the series', async () => {
  const { calls, client } = makeClient({
    state: STALE,
    states: [STALE, FRESH],
  });
  const root = await renderWithResults(client);
  await click(card().querySelector('button.boardSearchSuperGameLink'));
  await eventually(() => dialog() !== null, 'the modal opens');
  await eventually(
    () => dialog().querySelector('.boardSearchSuperGameStale') !== null,
    'the stale banner shows in the modal',
  );
  const reads = calls.series.length;
  await eventuallyPolled(() => calls.states >= 2, 'the state is polled');
  await eventuallyPolled(
    () => calls.series.length === reads + 1,
    'the fresh answer re-reads the series',
  );
  await click(button('Zamknij', dialog()));
  await act(async () => root.unmount());
});

test('without the share client the marker stays a label', async () => {
  const { client } = makeClient();
  const root = await renderWithResults(client, { superGameSeries: undefined });
  assert.ok(card().querySelector('.boardSearchSuperGameLabel'));
  assert.equal(card().querySelector('button.boardSearchSuperGameLink'), null);
  await act(async () => root.unmount());
});

test('a marked range row opens its board; after a save the results and the range show the new symbol', async () => {
  const { calls, client } = makeClient({ withRange: true });
  const root = await renderWithResults(client);
  await chooseBaseStake();
  const rows = () => [
    ...document.querySelectorAll('.boardSearchApproximateWin tbody tr'),
  ];
  assert.equal(
    rows()[1].querySelector('.boardSearchSuperGameLabel').textContent,
    'Supergra: super symbol do zdefiniowania',
  );
  const open = rows()[1].querySelector('button.boardSearchSuperGameLink');
  assert.ok(open, 'the range row marker is a button');
  open.focus();
  await click(open);
  await eventually(() => dialog() !== null, 'the modal opens');
  await eventually(
    () => dialog().querySelector('h4')?.textContent === 'Spin 4 · #104',
    'the carousel opens at the row board',
  );
  const ranges = calls.ranges;
  await press('2');
  await press('Enter');
  await eventually(() => calls.saves.length === 1, 'the symbol is saved');
  await eventually(
    () => notice().includes('Zapisano super symbol Symbol lemon'),
    'the saved symbol is confirmed in place',
  );
  assert.equal(dialog().querySelector('h4')?.textContent, 'Spin 4 · #104');
  await click(button('Zamknij', dialog()));
  assert.equal(dialog(), null);
  await eventually(
    () => resultLabel() === 'Supergra: spin 3/10, symbol LEMON',
    'the results carry the saved symbol',
  );
  // The refreshed range starts from a new stake choice (D-476), as after a
  // correction in the lines window.
  await chooseBaseStake();
  await eventually(() => calls.ranges > ranges, 'the range is read again');
  await eventually(
    () =>
      rows()[1]?.querySelector('.boardSearchSuperGameLabel')?.textContent ===
      'Supergra: spin 4/10, symbol LEMON',
    'the range rows carry the saved symbol',
  );
  await act(async () => root.unmount());
});

test('the modal cannot be closed while a save is in flight; the late success is still read back', async () => {
  let release;
  const gate = { promise: new Promise((resolve) => (release = resolve)) };
  const { calls, client } = makeClient({ gate });
  const root = await renderWithResults(client);
  await click(card().querySelector('button.boardSearchSuperGameLink'));
  await eventually(() => dialog() !== null, 'the modal opens');
  await eventually(
    () => dialog().querySelector('select') !== null,
    'the symbol select renders',
  );
  const searches = calls.searches;
  await press('1');
  await press('Enter');
  await eventually(() => calls.saves.length === 1, 'the save started');
  const close = button('Zapisuję…', dialog());
  assert.ok(close, 'the close button says the save is in flight');
  assert.equal(close.disabled, true);
  await click(close);
  assert.ok(dialog(), 'the modal stays open');
  release();
  await eventually(
    () => button('Zamknij', dialog()) !== undefined,
    'the close button returns after the answer',
  );
  await click(button('Zamknij', dialog()));
  assert.equal(dialog(), null);
  await eventually(
    () => calls.searches === searches + 1,
    'the results are read again after the save',
  );
  await act(async () => root.unmount());
});

test('Esc in the lines window closes only that window; a cell correction there re-runs the search', async () => {
  const { calls, client } = makeClient();
  const root = await renderWithResults(client);
  await click(card().querySelector('button.boardSearchSuperGameLink'));
  await eventually(() => dialog() !== null, 'the modal opens');
  await eventually(
    () => button('Pokaż planszę z liniami', dialog()) !== undefined,
    'the board renders in the carousel',
  );
  await click(button('Pokaż planszę z liniami', dialog()));
  await eventually(() => linesDialog() !== null, 'the lines window opens');
  // The browser turns Esc on the top-most dialog into its `cancel` event.
  await act(async () =>
    linesDialog().dispatchEvent(
      new dom.window.Event('cancel', { bubbles: false, cancelable: true }),
    ),
  );
  await eventually(() => linesDialog() === null, 'Esc closes the lines window');
  assert.ok(dialog(), 'the series modal stays');
  assert.equal(
    document.activeElement,
    button('Pokaż planszę z liniami', dialog()),
    'the focus returns to the lines button',
  );

  const searches = calls.searches;
  await click(button('Pokaż planszę z liniami', dialog()));
  await eventually(() => linesDialog() !== null, 'the lines window opens');
  await eventually(
    () => button('Popraw symbole', linesDialog()) !== undefined,
    'the correction mode is offered',
  );
  await click(button('Popraw symbole', linesDialog()));
  await eventually(
    () => linesDialog().querySelector('.boardSearchBoardCellTarget') !== null,
    'cells become targets',
  );
  await click(linesDialog().querySelector('.boardSearchBoardCellTarget'));
  await eventually(
    () => linesDialog().querySelector('button[title="Symbol lemon"]') !== null,
    'the symbol palette renders',
  );
  await click(linesDialog().querySelector('button[title="Symbol lemon"]'));
  await eventually(() => calls.corrections.length === 1, 'the cell is saved');
  assert.equal(calls.corrections[0].body.targetSymbolCode, 'LEMON');
  await click(button('Zamknij', linesDialog()));
  await eventually(() => linesDialog() === null, 'the lines window closes');
  assert.ok(dialog(), 'the series modal stays after the correction');
  assert.equal(calls.searches, searches, 'no search while the modal is open');
  await click(button('Zamknij', dialog()));
  await eventually(
    () => calls.searches === searches + 1,
    'the results are read again after the correction',
  );
  await act(async () => root.unmount());
});
