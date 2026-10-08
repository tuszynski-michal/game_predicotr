import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { JSDOM } from 'jsdom';
import React, { act, useState } from 'react';

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
const { ApproximateWinBalanceChart } =
  await import('../src/board-search-approximate-win.tsx');
const { confirmBoardSearchDiscardDraft } =
  await import('../src/board-search-saved-selection.ts');
after(() => dom.window.close());
const symbol = {
  code: 'cherry',
  displayOrder: 0,
  id: 'cherry',
  imagePath: null,
  mobileCode: 1,
  name: 'Wiśnia',
  status: 'active',
};
const query = {
  cells: [{ cellIndex: 0, symbolCode: 'cherry' }],
  limit: 15,
  scope: 'all_searchable',
};
function board(sequenceNumber) {
  return {
    assetMode: 'operational_review',
    boardChecksumSha256: 'a'.repeat(64),
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
function calculation(sequence = 999, spins = 10, rows = []) {
  return {
    gameId: 'game',
    startSequenceNumber: sequence,
    requestedSpinCount: spins,
    evaluatedSpinCount: spins,
    sequenceLength: 1000,
    dataFingerprintSha256: 'a'.repeat(64),
    dataSource: 'operational_review',
    startBoardStatus: null,
    wrappedAtSequenceEnd: false,
    rows,
    rules: {
      algorithmVersion: 'payout-v3-unknown-prefix-stop',
      rulesVersion: 1,
      rulesVersionId: 'rules',
      spinCost: 20,
    },
    summary: {
      recognizedPayoutCredits: rows.at(-1)?.cumulativePayoutCredits ?? 0,
      spinCostCredits: spins * 20,
      balanceCredits: (rows.at(-1)?.cumulativePayoutCredits ?? 0) - spins * 20,
    },
    completeness: {
      completeBoardCount: 0,
      partialBoardCount: 0,
      missingBoardCount: spins,
    },
  };
}
function saved(overrides = {}) {
  return {
    id: 'slot',
    query,
    searchContextId: 'context-original',
    startSequenceNumber: 999,
    spinCount: 10,
    pinnedSpinPositions: [0, 3, 10, 12],
    ...overrides,
  };
}
function client(overrides = {}) {
  const calls = { search: [], calc: [], detail: [] };
  return {
    calls,
    value: {
      listSymbols: async () => ({ data: [symbol] }),
      searchGameBoards: async (g, options) => {
        calls.search.push(options);
        return {
          data: {
            gameId: g,
            scope: options.scope,
            queryCellCount: 1,
            results: [board(1), board(2)],
          },
          searchContextId: 'context-new',
        };
      },
      getBoardSearchApproximateWin: async (g, o) => {
        calls.calc.push(o);
        return { data: calculation(o.startSequenceNumber, o.spinCount) };
      },
      getBoardSearchBoardDetail: async (g, s) => {
        calls.detail.push(s);
        return { error: { code: 'ABSENT' } };
      },
      symbolImageAssetUrl: () => '/symbol',
      boardSearchBoardViewUrl: () => '/board',
      ...overrides,
    },
  };
}
async function settle(ms = 15) {
  await act(async () => {
    await new Promise((r) => setTimeout(r, ms));
  });
}
async function eventually(predicate) {
  for (let i = 0; i < 60; i++) {
    if (predicate()) return;
    await settle();
  }
  assert.fail('Expected rendered state');
}
async function render(props) {
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(React.createElement(BoardSearchWorkspace, props)),
  );
  return root;
}
async function click(node) {
  assert.ok(node);
  await act(async () =>
    node.dispatchEvent(new MouseEvent('click', { bubbles: true })),
  );
}
function button(text) {
  return [...document.querySelectorAll('button')].find(
    (n) => n.textContent === text,
  );
}
async function input(label, value) {
  const node = document.querySelector(`input[aria-label="${label}"]`);
  assert.ok(node);
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      dom.window.HTMLInputElement.prototype,
      'value',
    ).set.call(node, String(value));
    node.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await act(async () =>
    node.dispatchEvent(
      new KeyboardEvent('keydown', { bubbles: true, key: 'Enter' }),
    ),
  );
}
function pressChart(key) {
  return document
    .querySelector(
      'svg[aria-label="Wykres kasy na czysto według liczby spinów"]',
    )
    .dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, key }));
}

test('trusted saved start restores outside all search hits; no-win numeric pins and unavailable positions remain', async () => {
  const api = client(),
    drafts = [],
    dirty = [];
  const props = {
    client: api.value,
    gameId: 'game',
    scopeKey: 'machine/game/2000',
    fixedStakeGrosze: 2000,
    savedSelection: saved(),
    onDraftChange: (d) => drafts.push(d),
    onDirtyChange: (d) => dirty.push(d),
    onSave: async () => assert.fail('No autosave'),
  };
  const root = await render(props);
  try {
    await eventually(() =>
      document.querySelector('svg[aria-roledescription="wykres"]'),
    );
    assert.equal(api.calls.search.length, 0);
    assert.deepEqual(api.calls.detail, [999]);
    assert.deepEqual(api.calls.calc, [
      { startSequenceNumber: 999, spinCount: 10 },
    ]);
    assert.equal(
      document.querySelector('output[aria-label="Stawka"]').textContent,
      '20,00 zł',
    );
    assert.match(
      document.querySelector('[aria-label="Przypięte punkty wykresu"]')
        .textContent,
      /3 spinów.*-60 zł/s,
    );
    assert.match(
      document.querySelector('[aria-label="Niedostępne przypięte punkty"]')
        .textContent,
      /12.*niedostępny/s,
    );
    assert.equal(drafts.at(-1).searchContextId, 'context-original');
    assert.equal(dirty.at(-1), false);
    await click(button('Odepnij niedostępny punkt 12'));
    assert.deepEqual(drafts.at(-1).pinnedSpinPositions, [0, 3, 10]);
    assert.equal(dirty.at(-1), true);
    await act(async () =>
      root.render(
        React.createElement(BoardSearchWorkspace, {
          ...props,
          savedSelection: saved({
            id: 'background-revision',
            startSequenceNumber: 2,
            spinCount: 99,
          }),
        }),
      ),
    );
    assert.equal(drafts.at(-1).startSequenceNumber, 999);
    assert.equal(drafts.at(-1).spinCount, 10);
    assert.deepEqual(drafts.at(-1).pinnedSpinPositions, [0, 3, 10]);
  } finally {
    await act(async () => root.unmount());
  }
});

test('explicit Save locks duplicates and failed/lost response retains complete draft for identical retry', async () => {
  const api = client(),
    calls = [],
    dirty = [];
  let fail = true,
    resolve;
  const onSave = (d) => {
    calls.push(d);
    return new Promise((r, j) => {
      resolve = () => (fail ? j(new Error('response lost')) : r());
    });
  };
  const root = await render({
    client: api.value,
    gameId: 'game',
    scopeKey: 'slot',
    fixedStakeGrosze: 120,
    savedSelection: saved(),
    onDirtyChange: (d) => dirty.push(d),
    onSave,
  });
  try {
    await input('Zakres wygranej — liczba kolejnych spinów', 8);
    await click(button('Zapisz układ'));
    assert.equal(button('Zapisywanie…').disabled, true);
    await click(button('Zapisywanie…'));
    assert.equal(calls.length, 1);
    await act(async () => resolve());
    assert.match(
      document.querySelector('[role="alert"]').textContent,
      /Nie udało się zapisać układu/,
    );
    assert.equal(dirty.at(-1), true);
    assert.equal(
      document.querySelector(
        'input[aria-label="Zakres wygranej — liczba kolejnych spinów"]',
      ).value,
      '8',
    );
    fail = false;
    await click(button('Zapisz układ'));
    assert.deepEqual(calls[1], calls[0]);
    assert.deepEqual(calls[1], {
      query,
      searchContextId: 'context-original',
      startSequenceNumber: 999,
      spinCount: 8,
      pinnedSpinPositions: [0, 3, 10, 12],
    });
    await act(async () => resolve());
    assert.equal(dirty.at(-1), false);
  } finally {
    if (resolve) await act(async () => resolve());
    await act(async () => root.unmount());
  }
});

test('first composed symbol marks empty slot dirty; query edits and committed limit invalidate search receipt', async () => {
  const api = client(),
    drafts = [],
    dirty = [];
  const root = await render({
    client: api.value,
    gameId: 'game',
    fixedStakeGrosze: 600,
    onDraftChange: (d) => drafts.push(d),
    onDirtyChange: (d) => dirty.push(d),
    onSave: async () => {},
  });
  try {
    await eventually(() => document.querySelector('[title="Wiśnia"]'));
    await click(document.querySelector('[title="Wiśnia"]'));
    assert.equal(dirty.at(-1), true);
    assert.deepEqual(drafts.at(-1).query.cells, query.cells);
    const event = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(event);
    assert.equal(event.defaultPrevented, true);
    const confirm = window.confirm;
    window.confirm = () => false;
    assert.equal(confirmBoardSearchDiscardDraft(true), false);
    assert.equal(confirmBoardSearchDiscardDraft(false), true);
    window.confirm = confirm;
    await click(button('Szukaj plansz'));
    await eventually(() => drafts.at(-1).searchContextId === 'context-new');
    assert.equal(drafts.at(-1).startSequenceNumber, 1);
    await click(button('Następna →'));
    assert.equal(drafts.at(-1).startSequenceNumber, 2);
    await input('Liczba wyników wyszukiwania', 9);
    assert.equal(drafts.at(-1).searchContextId, null);
    assert.equal(drafts.at(-1).query.limit, 9);
    assert.equal(button('Zapisz układ').disabled, true);
    await click(button('Szukaj plansz'));
    await eventually(() => api.calls.search.length === 2);
    await eventually(() =>
      document.querySelector('svg[aria-roledescription="wykres"]'),
    );
    assert.equal(
      document.querySelector('output[aria-label="Stawka"]').textContent,
      '6,00 zł',
    );
    assert.deepEqual(api.calls.search[1].cells, query.cells);
  } finally {
    await act(async () => root.unmount());
  }
});

test('late search/calculation/save completions cannot leak across slot or game scope', async () => {
  let resolveSearch, resolveCalc, resolveSave;
  const dirty = [],
    drafts = [];
  const api = client({
    searchGameBoards: () => new Promise((r) => (resolveSearch = r)),
    getBoardSearchApproximateWin: () => new Promise((r) => (resolveCalc = r)),
  });
  const base = {
    client: api.value,
    gameId: 'game',
    scopeKey: 'old',
    fixedStakeGrosze: 200,
    savedSelection: saved(),
    onDirtyChange: (d) => dirty.push(d),
    onDraftChange: (d) => drafts.push(d),
    onSave: () => new Promise((r) => (resolveSave = r)),
  };
  const root = await render(base);
  try {
    await eventually(() => resolveCalc);
    await input('Zakres wygranej — liczba kolejnych spinów', 9);
    await click(button('Zapisz układ'));
    await click(button('Szukaj plansz'));
    await act(async () =>
      root.render(
        React.createElement(BoardSearchWorkspace, {
          ...base,
          gameId: 'newgame',
          scopeKey: 'new',
          savedSelection: null,
        }),
      ),
    );
    const count = drafts.length;
    await act(async () => {
      resolveSearch({
        data: {
          gameId: 'game',
          scope: 'all_searchable',
          queryCellCount: 1,
          results: [board(1)],
        },
        searchContextId: 'old',
      });
      resolveCalc({ data: calculation() });
      resolveSave();
    });
    assert.equal(drafts.length, count);
    assert.equal(drafts.at(-1).startSequenceNumber, null);
    assert.equal(dirty.at(-1), false);
    assert.equal(document.querySelector('.boardSearchApproximateWin'), null);
  } finally {
    await act(async () => root.unmount());
  }
});

test('controlled arbitrary losing spin pins recompute on current result and enforce six without autosave', async () => {
  const root = createRoot(document.getElementById('root'));
  const changes = [];
  const first = calculation(1, 10, [
    {
      spinNumber: 5,
      payoutCredits: 200,
      cumulativePayoutCredits: 200,
      cumulativeBalanceCredits: 100,
    },
  ]);
  function View({ result }) {
    const [pins, setPins] = useState([0, 1, 2, 3, 4, 5]);
    return React.createElement(ApproximateWinBalanceChart, {
      display: { unit: 'credits', stakeGrosze: 200 },
      result,
      pinnedSpinPositions: pins,
      onPinsChange: (p) => {
        changes.push(p);
        setPins(p);
      },
    });
  }
  await act(async () =>
    root.render(React.createElement(View, { result: first })),
  );
  try {
    await act(async () => pressChart('ArrowRight'));
    // Move to arbitrary losing spin6 with sequential keyboard commits.
    for (let i = 0; i < 6; i++) await act(async () => pressChart('ArrowRight'));
    await act(async () => pressChart('Enter'));
    assert.equal(changes.length, 0);
    assert.match(
      document.querySelector('[role="status"]').textContent,
      /najwyżej 6/,
    );
    await click(button('Odepnij'));
    await act(async () => pressChart('Enter'));
    assert.ok(changes.at(-1).includes(6));
    const second = calculation(1, 10, []);
    await act(async () =>
      root.render(React.createElement(View, { result: second })),
    );
    assert.match(
      document.querySelector('[aria-label="Przypięte punkty wykresu"]')
        .textContent,
      /6 spinów.*-120/s,
    );
    assert.match(document.querySelector('svg').textContent, /6 spinów.*-120/s);
  } finally {
    await act(async () => root.unmount());
  }
});

test('saved start modal scales with its fresh published spin cost', async () => {
  let reads = 0;
  const api = client({
    getBoardSearchBoardDetail: async (g, s) => ({
      data: {
        boardChecksumSha256: 'a'.repeat(64),
        boardStatus: 'pending',
        cells: null,
        dataSource: 'operational_review',
        documentStale: false,
        gameId: g,
        matches: [],
        payoutCredits: 100,
        payoutKind: 'exact',
        rules: { ...calculation().rules, spinCost: ++reads === 1 ? 20 : 100 },
        sequenceNumber: s,
        symbolCodes: Array(15).fill(null),
        view: null,
      },
    }),
  });
  const root = await render({
    client: api.value,
    gameId: 'game',
    scopeKey: 'slot',
    fixedStakeGrosze: 2000,
    savedSelection: saved(),
    onSave: async () => {},
  });
  try {
    await eventually(() => reads === 1);
    await click(button('Pokaż zapisaną planszę'));
    await eventually(() =>
      document.querySelector('dialog')?.textContent.includes('20,00 zł'),
    );
    assert.doesNotMatch(document.querySelector('dialog').textContent, /zł zł/);
    assert.doesNotMatch(
      document.querySelector('dialog').textContent,
      /100,00 zł/,
    );
  } finally {
    await act(async () => root.unmount());
  }
});

test('late symbol loading and background snapshots preserve an already edited saved range', async () => {
  let resolveSymbols;
  const drafts = [];
  const api = client({
    listSymbols: () => new Promise((r) => (resolveSymbols = r)),
  });
  const base = {
    client: api.value,
    gameId: 'game',
    scopeKey: 'stable-slot',
    fixedStakeGrosze: 200,
    savedSelection: saved(),
    onDraftChange: (d) => drafts.push(d),
    onSave: async () => {},
  };
  const root = await render(base);
  try {
    await input('Zakres wygranej — liczba kolejnych spinów', 7);
    await act(async () =>
      root.render(
        React.createElement(BoardSearchWorkspace, {
          ...base,
          savedSelection: saved({
            id: 'new-revision',
            query: {
              ...query,
              cells: [{ cellIndex: 3, symbolCode: 'cherry' }],
            },
            spinCount: 100,
          }),
        }),
      ),
    );
    await act(async () => resolveSymbols({ data: [symbol] }));
    assert.equal(drafts.at(-1).spinCount, 7);
    assert.deepEqual(drafts.at(-1).query.cells, query.cells);
    assert.equal(
      document.querySelector(
        'input[aria-label="Zakres wygranej — liczba kolejnych spinów"]',
      ).value,
      '7',
    );
  } finally {
    await act(async () => root.unmount());
  }
});

test('payout-row modal also scales the fixed stake with freshly changed published rules', async () => {
  const row = {
    boardStatus: 'pending',
    spinNumber: 1,
    sequenceNumber: 1000,
    payoutCredits: 100,
    cumulativePayoutCredits: 100,
    cumulativeCostCredits: 20,
    cumulativeBalanceCredits: 80,
    payoutKind: 'exact',
  };
  const api = client({
    getBoardSearchApproximateWin: async (g, o) => ({
      data: calculation(o.startSequenceNumber, o.spinCount, [row]),
    }),
    getBoardSearchBoardDetail: async (g, s) => ({
      data: {
        boardChecksumSha256: 'a'.repeat(64),
        boardStatus: 'pending',
        cells: null,
        dataSource: 'operational_review',
        documentStale: false,
        gameId: g,
        matches: [],
        payoutCredits: 100,
        payoutKind: 'exact',
        rules: {
          ...calculation().rules,
          spinCost: 100,
          rulesVersionId: 'new-rules',
        },
        sequenceNumber: s,
        symbolCodes: Array(15).fill(null),
        view: null,
      },
    }),
  });
  const root = await render({
    client: api.value,
    gameId: 'game',
    scopeKey: 'slot',
    fixedStakeGrosze: 2000,
    savedSelection: saved(),
    onSave: async () => {},
  });
  try {
    await eventually(() =>
      document.querySelector(
        'button[aria-label="Pokaż planszę #1000 z liniami wypłat"]',
      ),
    );
    await click(
      document.querySelector(
        'button[aria-label="Pokaż planszę #1000 z liniami wypłat"]',
      ),
    );
    await eventually(() =>
      document.querySelector('dialog')?.textContent.includes('20,00 zł'),
    );
    assert.doesNotMatch(
      document.querySelector('dialog').textContent,
      /100,00 zł/,
    );
    assert.match(
      document.querySelector('dialog').textContent,
      /Reguły wypłat zmieniły się/,
    );
  } finally {
    await act(async () => root.unmount());
  }
});

test('current-data correction preserves trusted saved context/start and recalculates pins after closing the editor', async () => {
  const decisions = [],
    drafts = [];
  const cells = Array.from({ length: 15 }, (_, cellIndex) => ({
    assignedSymbolCode: 'cherry',
    cellIndex,
    cellVersion: 'b'.repeat(64),
    qualityIssue: null,
    reviewState: 'pending',
  }));
  const api = client({
    getBoardSearchBoardDetail: async (g, s) => ({
      data: {
        boardChecksumSha256: 'a'.repeat(64),
        boardStatus: 'pending',
        cells,
        dataSource: 'operational_review',
        documentStale: false,
        gameId: g,
        matches: [],
        payoutCredits: 0,
        payoutKind: 'none',
        rules: calculation().rules,
        sequenceNumber: s,
        symbolCodes: Array(15).fill('cherry'),
        view: null,
      },
    }),
    correctBoardSearchCell: async (g, s, c, body) => {
      decisions.push({ g, s, c, body });
      return { data: {} };
    },
  });
  const root = await render({
    client: api.value,
    gameId: 'game',
    scopeKey: 'slot',
    fixedStakeGrosze: 2000,
    savedSelection: saved(),
    onDraftChange: (d) => drafts.push(d),
    onSave: async () => {},
  });
  try {
    await eventually(() => api.calls.calc.length === 1);
    await click(button('Pokaż zapisaną planszę'));
    await eventually(() => button('Popraw symbole'));
    await click(button('Popraw symbole'));
    await click(document.querySelector('.boardSearchBoardCellTarget'));
    await click(
      document.querySelector(
        '.boardSearchBoardCellPalette button[title="Wiśnia"]',
      ),
    );
    await eventually(() => decisions.length === 1);
    assert.deepEqual(decisions[0], {
      g: 'game',
      s: 999,
      c: 0,
      body: {
        startSequenceNumber: 999,
        spinCount: 10,
        stakeGrosze: 2000,
        expectedCellVersion: 'b'.repeat(64),
        action: 'approve',
      },
    });
    await eventually(() => button('Zamknij')?.disabled === false);
    await click(button('Zamknij'));
    await eventually(() => api.calls.calc.length === 2);
    assert.deepEqual(api.calls.calc[1], {
      startSequenceNumber: 999,
      spinCount: 10,
    });
    assert.equal(api.calls.search.length, 0);
    assert.equal(drafts.at(-1).searchContextId, 'context-original');
    assert.deepEqual(drafts.at(-1).pinnedSpinPositions, [0, 3, 10, 12]);
  } finally {
    await act(async () => root.unmount());
  }
});

test('inline host callbacks can store draft state without render loops or repeated draft notification', async () => {
  const api = client();
  let calls = 0;
  function Host() {
    const [draft, setDraft] = useState(null);
    return React.createElement(
      'div',
      null,
      React.createElement(
        'output',
        { 'aria-label': 'Host draft' },
        draft?.startSequenceNumber ?? 'none',
      ),
      React.createElement(BoardSearchWorkspace, {
        client: api.value,
        gameId: 'game',
        scopeKey: 'slot',
        fixedStakeGrosze: 120,
        savedSelection: saved(),
        onSave: async () => {},
        onDraftChange: (d) => {
          calls++;
          setDraft(d);
        },
      }),
    );
  }
  const root = createRoot(document.getElementById('root'));
  await act(async () => root.render(React.createElement(Host)));
  try {
    assert.equal(calls, 1);
    assert.equal(
      document.querySelector('[aria-label="Host draft"]').textContent,
      '999',
    );
    await input('Zakres wygranej — liczba kolejnych spinów', 7);
    assert.equal(calls, 2);
  } finally {
    await act(async () => root.unmount());
  }
});
