import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import { registerHooks } from 'node:module';
const reactUrl = import.meta.resolve('react');
const jsxUrl = import.meta.resolve('react/jsx-runtime');
registerHooks({
  resolve(specifier, context, next) {
    if (specifier === 'react') return { url: reactUrl, shortCircuit: true };
    if (specifier === 'react/jsx-runtime')
      return { url: jsxUrl, shortCircuit: true };
    return next(specifier, context);
  },
  load(url, context, next) {
    if (url.endsWith('.css'))
      return {
        format: 'module',
        shortCircuit: true,
        source: 'export default {};',
      };
    return next(url, context);
  },
});
globalThis.React = React;

const dom = new JSDOM('<!doctype html><div id="root"></div>', {
  url: 'http://127.0.0.1:3000/?workspace=management',
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
  'PopStateEvent',
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
const { ManagementGameWorkspace } =
  await import('../src/features/management/management-game-workspace.tsx');
const { ManagementWorkspace } =
  await import('../src/features/management/management-workspace.tsx');
const { ManagementResultView } =
  await import('../src/features/management/management-result-view.tsx');
const { ManagementJournal } =
  await import('../src/features/management/management-journal.tsx');
const {
  applyManagementRefresh,
  managementSavedSelection,
  refreshManagementQueue,
} = await import('../src/features/management/management-slot-state.ts');
const { ManagementSlotRecovery, managementSlotPendingKey } =
  await import('../src/features/management/management-slot-operation.ts');
after(() => dom.window.close());
const { createManagementDataSource } =
  await import('../src/features/management/management-data-source.ts');
const stakes = [2000, 1000, 600, 400, 200, 120];
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
const slot = (stake = 2000, revision = 1) => ({
  machineId: 'machine',
  gameId: 'game',
  stakeGrosze: stake,
  revision,
  empty: false,
  searchContextId: 'context',
  query,
  startSequenceNumber: 9,
  spinCount: 10,
  pinnedSpinPositions: [0, 3, 12],
  unavailablePinPositions: [12],
  resultVersionId: `v${revision}`,
  startSymbolCodes: Array(15).fill('OLD'),
  summary: {
    recognizedPayoutCredits: 100,
    spinCostCredits: 100,
    balanceCredits: 0,
  },
  chartPoints: [
    { spinNumber: 0, balanceCredits: 0 },
    { spinNumber: 10, balanceCredits: 0 },
  ],
  pinnedPoints: [
    { spinNumber: 3, balanceCredits: -30, available: true },
    { spinNumber: 12, balanceCredits: -120, available: false },
  ],
  spinCost: 10,
  savedAt: '2026-10-07T00:00:00Z',
});
const calc = (start = 9, count = 10, cost = 10) => ({
  gameId: 'game',
  startSequenceNumber: start,
  requestedSpinCount: count,
  evaluatedSpinCount: count,
  sequenceLength: 1000,
  dataFingerprintSha256: 'a'.repeat(64),
  dataSource: 'operational_review',
  startBoardStatus: 'accepted',
  wrappedAtSequenceEnd: false,
  rows: [
    {
      spinNumber: 3,
      sequenceNumber: 12,
      payoutCredits: 100,
      cumulativePayoutCredits: 100,
      cumulativeCostCredits: 3 * cost,
      cumulativeBalanceCredits: 100 - 3 * cost,
      payoutKind: 'exact',
      boardStatus: 'accepted',
    },
  ],
  rules: {
    algorithmVersion: 'payout-v3-unknown-prefix-stop',
    rulesVersion: 1,
    rulesVersionId: 'rules-old',
    spinCost: cost,
  },
  summary: {
    recognizedPayoutCredits: 100,
    spinCostCredits: count * cost,
    balanceCredits: 100 - count * cost,
  },
  completeness: {
    completeBoardCount: count,
    partialBoardCount: 0,
    missingBoardCount: 0,
  },
});
const result = (id = 'v1') => ({
  id,
  contentSha256: 'b'.repeat(64),
  createdAt: '2026-10-07T00:00:00Z',
  calculation: calc(),
  rulesSnapshot: { immutable: 'OLD RULES' },
  startSymbolCodes: Array(15).fill(id),
});
const empty = (stake) => ({
  ...slot(stake, 0),
  empty: true,
  resultVersionId: null,
  startSequenceNumber: null,
  spinCount: null,
  searchContextId: null,
  query: null,
});
function client(overrides = {}) {
  return {
    listManagementStakes: async () => ({
      data: {
        slots: stakes.map((stake) =>
          stake === 2000 ? slot(stake) : empty(stake),
        ),
      },
    }),
    getManagementStake: async (_m, _g, s) => ({ data: slot(s) }),
    refreshManagementStake: async (_m, _g, s) => ({
      data: { slot: slot(s), status: 'current', changed: false },
    }),
    getManagementResult: async (_m, _g, id) => ({ data: result(id) }),
    listManagementJournal: async () => ({
      data: { entries: [], nextCursor: null },
    }),
    listSymbols: async () => ({ data: [symbol] }),
    symbolImageAssetUrl: () => '/symbol',
    boardSearchBoardViewUrl: () => '/board',
    getManagementApproximateWin: async (_m, _g, o) => ({
      data: calc(o.startSequenceNumber, o.spinCount),
    }),
    getManagementBoardDetail: async () => ({
      error: { message: 'Plansza niedostępna' },
    }),
    ...overrides,
  };
}
function deferred() {
  let resolve, reject;
  const promise = new Promise((a, b) => {
    resolve = a;
    reject = b;
  });
  return { promise, resolve, reject };
}
const text = () => document.body.textContent;
const button = (label, within = document) =>
  [...within.querySelectorAll('button')].find(
    (node) => node.textContent.trim() === label,
  );
const card = (stake = 2000) =>
  document.querySelector(
    `article[aria-label="Stawka ${(stake / 100).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} zł"]`,
  );
async function click(node) {
  assert.ok(node);
  await act(async () =>
    node.dispatchEvent(new MouseEvent('click', { bubbles: true })),
  );
}
async function settle(ms = 15) {
  await act(async () => new Promise((r) => setTimeout(r, ms)));
}
async function until(predicate) {
  for (let i = 0; i < 65; i++) {
    if (predicate()) return;
    await settle();
  }
  assert.fail('Expected rendered state');
}
async function mount(api, extra = {}) {
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(ManagementGameWorkspace, {
        api,
        machineId: 'machine',
        gameId: 'game',
        writeAllowed: true,
        ...extra,
      }),
    ),
  );
  return root;
}
async function unmount(root) {
  await act(async () => root.unmount());
}
async function range(value) {
  const node = document.querySelector(
    'input[aria-label="Zakres wygranej — liczba kolejnych spinów"]',
  );
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

test('refresh queue never exceeds two; aborted navigation stops additional requests', async () => {
  const controller = new AbortController(),
    gates = [],
    started = [];
  let active = 0,
    max = 0;
  const work = refreshManagementQueue(stakes, controller.signal, async (s) => {
    started.push(s);
    active++;
    max = Math.max(max, active);
    const gate = deferred();
    gates.push(gate);
    await gate.promise;
    active--;
  });
  await Promise.resolve();
  assert.equal(started.length, 2);
  gates[0].resolve();
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(started.length, 3);
  controller.abort();
  for (const gate of gates) gate.resolve();
  await work;
  assert.equal(max, 2);
  assert.equal(started.length, 3);
});

test('slot decoder validates recorded query and CAS ignores other scopes or later revisions', () => {
  const old = slot(),
    cards = [{ slot: old, status: 'checking' }];
  assert.equal(managementSavedSelection(old).startSequenceNumber, 9);
  assert.throws(() =>
    managementSavedSelection({
      ...old,
      query: { cells: [{ cellIndex: 99, symbolCode: 'x' }] },
    }),
  );
  const newer = { slot: slot(2000, 3), status: 'current' };
  assert.equal(
    applyManagementRefresh([newer], old, {
      slot: slot(2000, 2),
      status: 'current',
    })[0],
    newer,
  );
  assert.equal(
    applyManagementRefresh(cards, old, {
      slot: { ...slot(2000, 2), machineId: 'other' },
      status: 'current',
    }),
    cards,
  );
});

test('six compact cards load selected scope only; last result stays checking and failure is stale, never zero', async () => {
  dom.window.sessionStorage.clear();
  const gate = deferred(),
    full = [];
  let signal;
  const api = client({
    refreshManagementStake: (_m, _g, _s, _b, passed) => {
      signal = passed;
      return gate.promise;
    },
    getManagementResult: async (...args) => {
      full.push(args);
      return { data: result() };
    },
  });
  const root = await mount(api);
  assert.equal(
    document.querySelectorAll('.management-stake-cards article').length,
    6,
  );
  assert.match(card().textContent, /Sprawdzanie/);
  assert.match(card().textContent, /Plansza #9/);
  assert.match(text(), /Spin 12: niedostępny/);
  assert.equal(full.length, 0);
  await act(async () => gate.reject(new Error('Brak aktualnych reguł')));
  assert.match(card().textContent, /Wynik nieaktualny/);
  assert.match(card().textContent, /OLD/);
  assert.match(text(), /Brak aktualnych reguł/);
  await unmount(root);
  assert.equal(signal.aborted, true);
});

test('late refresh cannot revert saved card OR opened result after successful Save; draft survives background updates', async () => {
  dom.window.sessionStorage.clear();
  const gate = deferred(),
    versions = [],
    saves = [];
  const api = client({
    refreshManagementStake: () => gate.promise,
    getManagementResult: async (_m, _g, id) => {
      versions.push(id);
      return { data: result(id) };
    },
    saveManagementStake: async (_m, _g, _s, body) => {
      saves.push(body);
      return { data: { ...slot(2000, 3), spinCount: body.spinCount } };
    },
  });
  const root = await mount(api);
  await click(button('Otwórz', card()));
  await click(button('Szukaj ponownie', card()));
  await until(() =>
    document.querySelector(
      'input[aria-label="Zakres wygranej — liczba kolejnych spinów"]',
    ),
  );
  await range(11);
  await click(button('Zapisz układ'));
  assert.equal(saves[0].expectedRevision, 1);
  assert.equal(saves[0].spinCount, 11);
  assert.ok(versions.includes('v3'));
  await act(async () =>
    gate.resolve({
      data: { slot: slot(2000, 2), status: 'current', changed: true },
    }),
  );
  assert.equal(versions.includes('v2'), false);
  assert.match(card().textContent, /11 spinów/);
  assert.equal(
    document.querySelector(
      'input[aria-label="Zakres wygranej — liczba kolejnych spinów"]',
    ).value,
    '11',
  );
  await unmount(root);
});

test('uncertain Save blocks fresh operation, retries exact UUID/body after remount and preserves edited draft', async () => {
  dom.window.sessionStorage.clear();
  const calls = [];
  let fail = true;
  const api = client({
    saveManagementStake: async (_m, _g, _s, body) => {
      calls.push(body);
      if (fail) throw new Error('Utracona odpowiedź');
      return { data: { ...slot(2000, 2), spinCount: body.spinCount } };
    },
  });
  let root = await mount(api);
  await click(button('Szukaj ponownie', card()));
  await range(11);
  await click(button('Zapisz układ'));
  assert.match(text(), /Nieznany wynik ostatniej operacji/);
  assert.equal(button('Szukaj ponownie', card()).disabled, true);
  const stored = JSON.parse(
    dom.window.sessionStorage.getItem(managementSlotPendingKey('local-owner')),
  );
  assert.deepEqual(stored.body, calls[0]);
  await range(12);
  fail = false;
  await click(button('Sprawdź ostatni zapis stawki'));
  assert.deepEqual(calls[1], calls[0]);
  assert.equal(
    document.querySelector(
      'input[aria-label="Zakres wygranej — liczba kolejnych spinów"]',
    ).value,
    '12',
  );
  assert.match(text(), /Niezapisane zmiany układu/);
  await unmount(root);
  dom.window.sessionStorage.setItem(
    managementSlotPendingKey('local-owner'),
    JSON.stringify(stored),
  );
  root = await mount(api);
  await click(button('Sprawdź ostatni zapis stawki'));
  assert.deepEqual(calls[2], calls[0]);
  assert.equal(
    dom.window.sessionStorage.getItem(managementSlotPendingKey('local-owner')),
    null,
  );
  await unmount(root);
});

test('CAS conflict preserves draft and explicit next Save uses refreshed baseline', async () => {
  dom.window.sessionStorage.clear();
  const calls = [];
  const api = client({
    getManagementStake: async () => ({ data: slot(2000, 7) }),
    saveManagementStake: async (_m, _g, _s, body) => {
      calls.push(body);
      return calls.length === 1
        ? { error: { message: 'Konflikt rewizji' }, response: { status: 409 } }
        : { data: { ...slot(2000, 8), spinCount: body.spinCount } };
    },
  });
  const root = await mount(api);
  await click(button('Szukaj ponownie', card()));
  await range(11);
  await click(button('Zapisz układ'));
  assert.equal(calls[0].expectedRevision, 1);
  assert.match(text(), /Twój szkic pozostał zachowany/);
  assert.equal(
    document.querySelector(
      'input[aria-label="Zakres wygranej — liczba kolejnych spinów"]',
    ).value,
    '11',
  );
  await click(button('Zapisz układ'));
  assert.equal(calls[1].expectedRevision, 7);
  assert.notEqual(calls[1].operationId, calls[0].operationId);
  await unmount(root);
});

test('confirmed Clear targets only chosen slot and retries uncertain response without deleting history', async () => {
  dom.window.sessionStorage.clear();
  const calls = [];
  let ok = false;
  const api = client({
    listManagementStakes: async () => ({
      data: { slots: stakes.map((s) => slot(s)) },
    }),
    clearManagementStake: async (m, g, s, body) => {
      calls.push({ m, g, s, body });
      if (!ok) throw new Error('timeout');
      return { data: { ...empty(s), revision: 2 } };
    },
  });
  const root = await mount(api);
  dom.window.confirm = () => false;
  await click(button('Wyczyść', card()));
  assert.equal(calls.length, 0);
  dom.window.confirm = () => true;
  await click(button('Wyczyść', card()));
  assert.equal(calls[0].s, 2000);
  assert.equal(calls[0].body.confirmed, true);
  ok = true;
  await click(button('Sprawdź ostatni zapis stawki'));
  assert.deepEqual(calls[1], calls[0]);
  assert.match(card().textContent, /Brak zapisanego układu/);
  assert.match(card(1000).textContent, /Plansza #9/);
  assert.ok(document.querySelector('[aria-label="Dziennik maszyny"]'));
  await unmount(root);
});

test('journal uses real action names, pages20, retains prior rows and opens frozen versions only on demand', async () => {
  dom.window.sessionStorage.clear();
  const calls = [],
    history = [];
  const entry = {
    id: 'e1',
    action: 'stake.recalculate',
    actor: 'local-owner',
    pointId: 'point',
    machineId: 'machine',
    gameId: 'game',
    stakeGrosze: 2000,
    beforeResultId: 'old',
    afterResultId: 'new',
    before: { startSequenceNumber: 9, pinnedSpinPositions: [3] },
    after: { startSequenceNumber: 9 },
    createdAt: '2026-10-07T00:00:00Z',
  };
  const api = client({
    listManagementJournal: async (_m, o) => {
      calls.push(o);
      return {
        data: {
          entries: o.before
            ? [
                {
                  ...entry,
                  id: 'e2',
                  action: 'search',
                  after: { resultCount: 0, query },
                },
              ]
            : [entry],
          nextCursor: o.before ? null : 'cursor-1',
        },
      };
    },
  });
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(ManagementJournal, {
        api,
        machineId: 'machine',
        gameId: 'game',
        revision: 0,
        onHistory: (...args) => history.push(args),
      }),
    ),
  );
  assert.equal(calls[0].limit, 20);
  assert.match(text(), /Zmiana wyniku/);
  assert.equal(history.length, 0);
  await click(button('Wynik przed zmianą'));
  assert.deepEqual(history, [['old', 2000, [3]]]);
  await click(button('Starsze wpisy'));
  assert.equal(calls[1].before, 'cursor-1');
  assert.equal(calls[1].limit, 20);
  assert.equal(document.querySelectorAll('.management-journal li').length, 2);
  assert.match(text(), /Wyniki: 0/);
  await unmount(root);
});

test('journal readable before/after preserves address, archive, attached games, quality and numeric result evidence', async () => {
  const cases = [
    [
      'point.write',
      { name: 'Punkt', city: 'Kraków', street: 'Krótka 1', archived: false },
      { name: 'Punkt', city: 'Warszawa', street: 'Długa 2', archived: true },
      /Kraków.*Krótka 1.*Aktywny/,
      /Warszawa.*Długa 2.*Zarchiwizowany/,
    ],
    [
      'assignments.write',
      { assignments: [{ gameName: 'Gra A', attached: true }] },
      { assignments: [{ gameName: 'Gra A', attached: false }] },
      /Gra A: przypisana/,
      /Gra A: odłączona/,
    ],
    [
      'symbol.correct',
      {
        cellIndex: 1,
        symbolCode: 'cherry',
        reviewState: 'pending',
        qualityIssue: 'unreadable',
      },
      {
        cellIndex: 1,
        symbolCode: 'cherry',
        reviewState: 'approved',
        qualityIssue: null,
      },
      /Nieczytelny symbol.*Symbol do weryfikacji/,
      /Brak problemów jakości.*Symbol zatwierdzony/,
    ],
    [
      'symbol.correct',
      {
        cellIndex: 1,
        symbolCode: 'cherry',
        reviewState: 'approved',
        qualityIssue: null,
      },
      {
        cellIndex: 1,
        symbolCode: 'cherry',
        reviewState: 'pending',
        qualityIssue: 'grid_issue',
      },
      /Brak problemów jakości.*Symbol zatwierdzony/,
      /Błąd siatki.*Symbol do weryfikacji/,
    ],
    [
      'symbol.correct',
      { qualityIssue: 'blurry' },
      { qualityIssue: 'partial_visibility' },
      /Rozmyty symbol/,
      /Częściowo widoczny symbol/,
    ],
    [
      'symbol.correct',
      { qualityIssue: 'future-quality-code' },
      { qualityIssue: null },
      /Problem jakości/,
      /Brak problemów jakości/,
    ],
    [
      'stake.recalculate',
      {
        stakeGrosze: 2000,
        spinCost: 10,
        summary: {
          recognizedPayoutCredits: 100,
          spinCostCredits: 100,
          balanceCredits: 0,
        },
      },
      {
        stakeGrosze: 2000,
        spinCost: 20,
        summary: {
          recognizedPayoutCredits: 100,
          spinCostCredits: 200,
          balanceCredits: -100,
        },
      },
      /Wypłaty: 200,00 zł.*Koszt spinów: 200,00 zł.*Bilans: 0,00 zł/,
      /Wypłaty: 100,00 zł.*Koszt spinów: 200,00 zł.*Bilans: -100,00 zł/,
    ],
    [
      'search',
      {},
      { resultCount: 0, query: { ...query, scope: 'approved_only' } },
      /Brak zapisanego układu/,
      /Wzór: pole 1: cherry.*Limit wyników: 15.*Tylko zaakceptowane plansze/,
    ],
  ];
  const entries = cases.map(([action, before, after], index) => ({
    id: `readable-${index}`,
    action,
    before,
    after,
    actor: 'local-owner',
    stakeGrosze: 2000,
    beforeResultId: null,
    afterResultId: null,
    createdAt: '2026-10-07T00:00:00Z',
  }));
  const api = client({
    listManagementJournal: async () => ({
      data: { entries, nextCursor: null },
    }),
  });
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(ManagementJournal, {
        api,
        machineId: 'machine',
        gameId: 'game',
        revision: 0,
        onHistory: () => {},
      }),
    ),
  );
  const rows = document.querySelectorAll('.management-journal li');
  cases.forEach(([, , , before, after], index) => {
    const states = rows[index].querySelectorAll('details p');
    assert.match(states[0].textContent, before);
    assert.match(states[1].textContent, after);
  });
  assert.equal(document.querySelectorAll('.management-journal pre').length, 0);
  await unmount(root);
});

test('historical result stays frozen while editor uses CURRENT symbols/rules and fixed stake', async () => {
  dom.window.sessionStorage.clear();
  let calculations = 0,
    corrections = 0;
  const detail = {
    gameId: 'game',
    sequenceNumber: 9,
    boardStatus: 'accepted',
    boardChecksumSha256: 'a'.repeat(64),
    dataSource: 'operational_review',
    rules: {
      rulesVersionId: 'rules-current',
      rulesVersion: 2,
      spinCost: 20,
      algorithmVersion: 'payout-v3-unknown-prefix-stop',
    },
    symbolCodes: Array(15).fill('cherry'),
    payoutCredits: 100,
    payoutKind: 'exact',
    matches: [
      {
        jokerCells: [],
        matchedCells: [0, 1, 2],
        matchedLength: 3,
        paylineCode: 'top',
        paylineDisplayOrder: 0,
        paylineId: 'top',
        paylineName: 'Górna linia',
        payoutCredits: 100,
        rowPath: [0, 0, 0, 0, 0],
        symbolCode: 'cherry',
      },
    ],
    view: null,
    documentStale: false,
    cells: Array.from({ length: 15 }, (_, cellIndex) => ({
      cellIndex,
      cellVersion: 'version',
      reviewState: 'approved',
      qualityIssue: null,
      assignedSymbolCode: 'cherry',
    })),
  };
  const api = client({
    getManagementApproximateWin: async () => {
      calculations++;
      return { data: calc() };
    },
  });
  const boardClient = {
    listSymbols: api.listSymbols,
    symbolImageAssetUrl: () => '/symbol',
    boardSearchBoardViewUrl: () => '/board',
    getBoardSearchBoardDetail: async () => ({ data: detail }),
    correctBoardSearchCell: async () => {
      corrections++;
      return { data: { changed: true, cellVersion: 'new' } };
    },
  };
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(ManagementResultView, {
        api,
        machineId: 'machine',
        gameId: 'game',
        versionId: 'old',
        stake: 2000,
        historical: true,
        pins: [3],
        boardClient,
        writeAllowed: true,
      }),
    ),
  );
  assert.match(text(), /Historyczny wynik/);
  assert.equal(calculations, 0);
  assert.match(document.querySelector('table').textContent, /200,00 zł/);
  await click(button('Edytuj bieżącą planszę startową'));
  await until(() => document.querySelector('dialog'));
  assert.match(document.querySelector('dialog').textContent, /100,00 zł/);
  assert.match(text(), /Edytujesz bieżące dane gry/);
  await click(document.querySelector('.boardSearchBoardCellTarget'));
  await click(
    document.querySelector(
      '.boardSearchBoardCellPalette button[title="Wiśnia"]',
    ),
  );
  assert.equal(corrections, 1);
  assert.match(document.querySelector('table').textContent, /200,00 zł/);
  assert.match(
    document.querySelector('[aria-label="Historyczny wynik"]').textContent,
    /Reguły 1/,
  );
  assert.doesNotMatch(text(), /fingerprint|OLD RULES/);
  assert.equal(calculations, 0);
  await unmount(root);
});

test('archived/detached saves remain readable; no recalculation or new search', async () => {
  dom.window.sessionStorage.clear();
  let refreshes = 0,
    results = 0;
  const api = client({
    refreshManagementStake: async () => {
      refreshes++;
      return {};
    },
    getManagementResult: async () => {
      results++;
      return { data: result() };
    },
  });
  const root = await mount(api, { writeAllowed: false });
  assert.equal(refreshes, 0);
  assert.equal(button('Szukaj ponownie', card()).disabled, true);
  await click(button('Otwórz', card()));
  assert.equal(results, 1);
  assert.match(text(), /tylko do odczytu/);
  assert.equal(button('Edytuj bieżącą planszę startową'), undefined);
  await unmount(root);
});

test('durable recovery refuses a new body and definitive conflict retires the old UUID', async () => {
  dom.window.sessionStorage.clear();
  const original = {
    kind: 'save',
    machineId: 'machine',
    gameId: 'game',
    stake: 2000,
    body: {
      operationId: 'same',
      expectedRevision: 1,
      searchContextId: 'context',
      startSequenceNumber: 9,
      spinCount: 10,
    },
  };
  const recovery = new ManagementSlotRecovery(
    dom.window.sessionStorage,
    'test',
    () => {},
  );
  await assert.rejects(
    recovery.run(original, async () => {
      throw new Error('response lost');
    }),
  );
  const remount = new ManagementSlotRecovery(
    dom.window.sessionStorage,
    'test',
    () => {},
  );
  assert.deepEqual(remount.pending, original);
  await assert.rejects(
    remount.run(
      { ...original, body: { ...original.body, operationId: 'different' } },
      async () => ({ data: {} }),
    ),
    /Najpierw sprawdź/,
  );
  await assert.rejects(
    remount.run(original, async () => ({
      error: { message: 'conflict' },
      response: { status: 409 },
    })),
  );
  assert.equal(remount.pending, null);
});

test('point catalog does not load cards; internal machine/game navigation warns and cancelled discard retains draft', async () => {
  dom.window.sessionStorage.clear();
  const point = {
    id: 'point',
    name: 'Punkt',
    city: 'Miasto',
    street: 'Ulica',
    archived: false,
    revision: 1,
    updatedAt: '2026-10-07T00:00:00Z',
    machines: [
      {
        id: 'machine',
        pointId: 'point',
        name: 'Maszyna',
        archived: false,
        revision: 1,
        updatedAt: '2026-10-07T00:00:00Z',
        assignments: [
          {
            gameId: 'game',
            gameName: 'Gra',
            gameStatus: 'active',
            attached: true,
          },
          {
            gameId: 'other',
            gameName: 'Druga',
            gameStatus: 'active',
            attached: true,
          },
        ],
      },
    ],
  };
  let reads = 0;
  const api = {
    ...client({
      listManagementStakes: async () => {
        reads++;
        return {
          data: { slots: stakes.map((s) => (s === 2000 ? slot() : empty(s))) },
        };
      },
    }),
    getManagementSnapshot: async () => ({
      data: { points: [point], activeGames: [{ id: 'game', name: 'Gra' }] },
    }),
  };
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(ManagementWorkspace, {
        apiBaseUrl: 'http://127.0.0.1:8000',
        client: api,
      }),
    ),
  );
  assert.equal(reads, 0);
  await click(
    [...document.querySelectorAll('button')].find((n) =>
      n.textContent.includes('PunktMiasto'),
    ),
  );
  await click(button('Otwórz gry maszyny Maszyna'));
  await click(button('Szukaj ponownie', card()));
  await range(11);
  let confirms = 0;
  dom.window.confirm = () => {
    confirms++;
    return false;
  };
  const select = document.querySelector('select[aria-label="Gra maszyny"]');
  await act(async () => {
    select.value = 'other';
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });
  assert.equal(confirms, 1);
  assert.equal(select.value, 'game');
  assert.equal(
    document.querySelector(
      'input[aria-label="Zakres wygranej — liczba kolejnych spinów"]',
    ).value,
    '11',
  );
  assert.equal(reads, 1);
  await unmount(root);
});

test('acknowledged retry advances own revision while the later edited draft remains unsaved', async () => {
  dom.window.sessionStorage.clear();
  const calls = [];
  let lost = true;
  const api = client({
    saveManagementStake: async (_m, _g, _s, body) => {
      calls.push(body);
      if (lost) throw new Error('lost');
      return {
        data: {
          ...slot(2000, body.expectedRevision + 1),
          spinCount: body.spinCount,
        },
      };
    },
  });
  const root = await mount(api);
  await click(button('Szukaj ponownie', card()));
  await range(11);
  await click(button('Zapisz układ'));
  await range(12);
  lost = false;
  await click(button('Sprawdź ostatni zapis stawki'));
  assert.match(text(), /Niezapisane zmiany/);
  await click(button('Zapisz układ'));
  assert.equal(calls[2].expectedRevision, 2);
  assert.equal(calls[2].spinCount, 12);
  assert.notEqual(calls[2].operationId, calls[0].operationId);
  await unmount(root);
});

test('capability changes preserve dirty draft and remove current mutation controls', async () => {
  dom.window.sessionStorage.clear();
  const api = client();
  const changed = [];
  const root = await mount(api, { onDirtyChange: (d) => changed.push(d) });
  await click(button('Szukaj ponownie', card()));
  await range(11);
  await act(async () =>
    root.render(
      React.createElement(ManagementGameWorkspace, {
        api,
        machineId: 'machine',
        gameId: 'game',
        writeAllowed: false,
        onDirtyChange: (d) => changed.push(d),
      }),
    ),
  );
  assert.equal(
    document.querySelector(
      'input[aria-label="Zakres wygranej — liczba kolejnych spinów"]',
    ).value,
    '11',
  );
  assert.equal(button('Zapisz układ'), undefined);
  assert.equal(changed.at(-1), true);
  assert.match(text(), /tylko do odczytu/);
  await unmount(root);
});

test('late refresh after Clear cannot reopen cleared result', async () => {
  dom.window.sessionStorage.clear();
  const gate = deferred(),
    versions = [];
  const api = client({
    refreshManagementStake: () => gate.promise,
    getManagementResult: async (_m, _g, id) => {
      versions.push(id);
      return { data: result(id) };
    },
    clearManagementStake: async () => ({
      data: { ...empty(2000), revision: 3 },
    }),
  });
  const root = await mount(api);
  await click(button('Otwórz', card()));
  dom.window.confirm = () => true;
  await click(button('Wyczyść', card()));
  await act(async () =>
    gate.resolve({
      data: { slot: slot(2000, 2), status: 'current', changed: true },
    }),
  );
  assert.equal(
    document.querySelector('[aria-label="Ostatni zapisany wynik"]'),
    null,
  );
  assert.equal(versions.includes('v2'), false);
  assert.match(card().textContent, /Brak zapisanego układu/);
  await unmount(root);
});

test('refresh lost-response receipt retries exact body after reload without leaving newer save checking forever', async () => {
  dom.window.sessionStorage.clear();
  const calls = [];
  let fail = true;
  const api = client({
    listManagementStakes: async () => ({
      data: {
        slots: stakes.map((s) =>
          s === 2000 ? slot(s, fail ? 1 : 3) : empty(s),
        ),
      },
    }),
    getManagementStake: async () => ({ data: slot(2000, 3) }),
    refreshManagementStake: async (_m, _g, _s, body) => {
      calls.push(body);
      if (fail) throw new Error('response lost');
      return {
        data: { slot: slot(2000, 2), status: 'current', changed: true },
      };
    },
  });
  let root = await mount(api);
  assert.match(card().textContent, /Wynik nieaktualny/);
  await unmount(root);
  fail = false;
  root = await mount(api);
  assert.deepEqual(calls[1], calls[0]);
  assert.match(card().textContent, /Wynik nieaktualny/);
  assert.doesNotMatch(card().textContent, /Sprawdzanie bieżących/);
  assert.match(text(), /Nowszy zapis pozostaje zachowany/);
  await unmount(root);
});

test('management adapter journals zero-hit search and corrections, exact retry survives fresh adapter and read aborts are scoped', async () => {
  dom.window.sessionStorage.clear();
  const searches = [],
    corrections = [],
    reads = [],
    commits = [];
  let fail = true;
  const api = client({
    searchManagementBoards: async (_m, _g, body, signal) => {
      searches.push(body);
      reads.push(signal);
      return {
        data: {
          searchContextId: 'trusted-context',
          search: {
            gameId: 'game',
            queryCellCount: 1,
            scope: 'all_searchable',
            results: [],
          },
        },
      };
    },
    correctManagementBoardCell: async (_m, _g, _s, sequence, cell, body) => {
      corrections.push({ sequence, cell, body });
      if (fail) throw new Error('response lost');
      return { data: { changed: true, cellVersion: 'new-version' } };
    },
    getManagementBoardDetail: async (_m, _g, _seq, signal) => {
      reads.push(signal);
      return { error: {} };
    },
  });
  const recovery = new ManagementSlotRecovery(
    dom.window.sessionStorage,
    'adapter',
    () => {},
  );
  let adapter = createManagementDataSource({
    api,
    machineId: 'machine',
    gameId: 'game',
    stake: 2000,
    recovery,
    getRevision: () => 1,
    onCommitted: () => commits.push('correct'),
    onSearchCommitted: () => commits.push('search'),
    onConflict: () => {},
  });
  const search = await adapter.client.searchGameBoards('game', query);
  assert.equal(search.searchContextId, 'trusted-context');
  assert.deepEqual(search.data.results, []);
  await adapter.client.correctBoardSearchCell('game', 9, 0, {
    expectedCellVersion: 'old',
    action: 'approve',
    startSequenceNumber: 9,
    spinCount: 10,
    stakeGrosze: 2000,
  });
  assert.equal(recovery.pending.kind, 'correction');
  assert.equal(corrections[0].body.searchContextId, 'trusted-context');
  adapter.abort();
  assert.equal(reads[0].aborted, true);
  const restored = new ManagementSlotRecovery(
    dom.window.sessionStorage,
    'adapter',
    () => {},
  );
  adapter = createManagementDataSource({
    api,
    machineId: 'machine',
    gameId: 'game',
    stake: 2000,
    recovery: restored,
    getRevision: () => 9,
    onCommitted: () => commits.push('correct'),
    onConflict: () => {},
  });
  fail = false;
  await adapter.client.retryBoardSearchCell('game', 9);
  assert.deepEqual(corrections[1], corrections[0]);
  assert.deepEqual(commits, ['search', 'correct']);
  assert.equal(restored.pending, null);
  adapter.abort();
});

test('outer Admin workspace click and popstate both guard dirty management draft', async () => {
  dom.window.sessionStorage.clear();
  dom.window.history.replaceState(null, '', '/?workspace=management');
  const { CatalogWorkspace } =
    await import('../src/features/catalog/catalog-workspace.tsx');
  const machine = {
    id: 'machine',
    pointId: 'point',
    name: 'Maszyna',
    archived: false,
    revision: 1,
    updatedAt: '2026-10-07T00:00:00Z',
    assignments: [
      { gameId: 'game', gameName: 'Gra', gameStatus: 'active', attached: true },
    ],
  };
  const point = {
    id: 'point',
    name: 'Punkt',
    city: 'Miasto',
    street: 'Ulica',
    archived: false,
    revision: 1,
    updatedAt: machine.updatedAt,
    machines: [machine],
  };
  const api = {
    ...client(),
    getManagementSnapshot: async () => ({
      data: { points: [point], activeGames: [] },
    }),
  };
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () =>
    new Response('[]', {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  const root = createRoot(document.getElementById('root'));
  try {
    await act(async () =>
      root.render(
        React.createElement(CatalogWorkspace, {
          apiBaseUrl: 'http://127.0.0.1:8000',
          managementClient: api,
        }),
      ),
    );
    await click(
      [...document.querySelectorAll('button')].find((n) =>
        n.textContent.includes('PunktMiasto'),
      ),
    );
    await click(button('Otwórz gry maszyny Maszyna'));
    await click(button('Szukaj ponownie', card()));
    await range(11);
    let prompts = 0;
    dom.window.confirm = () => {
      prompts++;
      return false;
    };
    await click(button('Zarządzanie grami'));
    assert.equal(prompts, 1);
    assert.ok(document.querySelector('[aria-label="Szkic układu"]'));
    await act(async () => {
      dom.window.history.pushState(null, '', '/?workspace=games');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    assert.equal(prompts, 2);
    assert.match(dom.window.location.search, /workspace=management/);
    assert.equal(
      document.querySelector(
        'input[aria-label="Zakres wygranej — liczba kolejnych spinów"]',
      ).value,
      '11',
    );
  } finally {
    await unmount(root);
    globalThis.fetch = originalFetch;
  }
});
