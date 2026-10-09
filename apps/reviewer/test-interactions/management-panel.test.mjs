import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { registerHooks } from 'node:module';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
const reactUrl = import.meta.resolve('react'),
  jsxUrl = import.meta.resolve('react/jsx-runtime');
registerHooks({
  resolve(specifier, context, next) {
    if (specifier === 'react') return { url: reactUrl, shortCircuit: true };
    if (specifier === 'react/jsx-runtime')
      return { url: jsxUrl, shortCircuit: true };
    return next(specifier, context);
  },
});
globalThis.React = React;
const dom = new JSDOM('<!doctype html><div id="root"></div>', {
  url: 'https://panel.example/management?share=11111111-1111-4111-8111-111111111111',
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
Object.defineProperty(dom.window, 'innerWidth', { value: 390 });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
dom.window.confirm = () => true;
dom.window.HTMLDialogElement.prototype.showModal = function () {
  this.setAttribute('open', '');
};
dom.window.HTMLDialogElement.prototype.close = function () {
  this.removeAttribute('open');
};
const { createRoot } = await import('react-dom/client');
const { ManagementGate } =
  await import('../src/features/management/management-gate.tsx');
const { createManagementPublicAdapter } =
  await import('../src/features/management/management-public-adapter.ts');
const { managementAccessMessage, managementStorageNamespace } =
  await import('../src/features/management/management-access-state.ts');
const { ManagementSlotRecovery, managementSlotPendingKey } =
  await import('../../../packages/board-search-ui/src/management/management-slot-operation.ts');
const { managementPendingKey } =
  await import('../../../packages/board-search-ui/src/management/management-operation.ts');
const { createManagementDataSource } =
  await import('../../../packages/board-search-ui/src/management/management-data-source.ts');
const { managementActorLabel } =
  await import('../../../packages/board-search-ui/src/management/management-journal.tsx');
after(() => dom.window.close());
const sessionId = '11111111-1111-4111-8111-111111111111';
const otherSession = '22222222-2222-4222-8222-222222222222';
const stakes = [2000, 1000, 600, 400, 200, 120];

test('new structural ports preserve the public identity fence before and after session end', async () => {
  const server = backend();
  const calls = [];
  const adapter = createManagementPublicAdapter({
    sessionId,
    fetchImplementation: async (request) => {
      if (new URL(request.url).pathname.endsWith('/context'))
        return server.fetch(request);
      calls.push({
        path: new URL(request.url).pathname,
        session: request.headers.get('X-Management-Session'),
        body: await request.json(),
      });
      return new Response('{}', {
        headers: { 'Content-Type': 'application/json' },
      });
    },
  });
  await adapter.context();
  const preview = { expectedRevision: 1 };
  const deletion = {
    operationId: 'operation',
    expectedRevision: 1,
    previewToken: 'p'.repeat(43),
    confirmed: true,
  };
  const actions = [
    () => adapter.client.previewManagementPointDeletion('point', preview),
    () => adapter.client.deleteManagementPoint('point', deletion),
    () =>
      adapter.client.previewManagementMachineDeletion(
        'point',
        'machine',
        preview,
      ),
    () => adapter.client.deleteManagementMachine('point', 'machine', deletion),
    () =>
      adapter.client.previewManagementMachineUpdate('machine', {
        command: {
          operationId: 'edit',
          expectedRevision: 1,
          name: 'M',
          gameIds: [],
        },
      }),
  ];
  for (const action of actions) await action();
  assert.equal(calls.length, 5);
  assert(
    calls.every(
      (call) =>
        call.session === sessionId && call.path.includes('/management-public/'),
    ),
  );
  assert.deepEqual(calls[1].body, deletion);
  adapter.end();
  for (const action of actions) {
    const result = await action();
    assert.equal(result.data, undefined);
    assert.match(result.error.message, /zakończony/);
  }
  assert.equal(calls.length, 5);
});
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

const text = () => document.body.textContent;
const button = (label, within = document) =>
  [...within.querySelectorAll('button')].find(
    (node) => node.textContent.trim() === label,
  );
const card = (stake = 2000) =>
  document.querySelector(
    `button[aria-label="Stawka ${(stake / 100).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} zł"]`,
  );
async function settle() {
  await act(async () => new Promise((r) => setTimeout(r, 10)));
}
async function until(predicate) {
  for (let i = 0; i < 180; i++) {
    if (predicate()) return;
    await settle();
  }
  assert.fail('Missing rendered state: ' + text().slice(-1000));
}
async function expand(label) {
  const summary = [...document.querySelectorAll('summary')].find(
    (node) => node.textContent === label,
  );
  assert.ok(summary, `Missing disclosure: ${label}`);
  await act(async () => {
    summary.parentElement.open = true;
    summary.parentElement.dispatchEvent(new Event('toggle'));
  });
  await settle();
}
async function openSavedResult() {
  if (!button('Zamknij szkic')) await click(card());
  await click(button('Zamknij szkic'));
  await expand('Pełny zapisany wynik');
}
async function click(node) {
  assert.ok(node);
  await act(async () =>
    node.dispatchEvent(new MouseEvent('click', { bubbles: true })),
  );
  await settle();
}
async function input(node, value) {
  assert.ok(node);
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      dom.window.HTMLInputElement.prototype,
      'value',
    ).set.call(node, String(value));
    node.dispatchEvent(new Event('input', { bubbles: true }));
  });
}
async function submit(form) {
  await act(async () =>
    form.dispatchEvent(
      new Event('submit', { bubbles: true, cancelable: true }),
    ),
  );
  await settle();
}
async function range(value) {
  const node = document.querySelector(
    'input[aria-label="Zakres wygranej — liczba kolejnych spinów"]',
  );
  await input(node, value);
  await act(async () =>
    node.dispatchEvent(
      new KeyboardEvent('keydown', { bubbles: true, key: 'Enter' }),
    ),
  );
  await settle();
}
async function mount(adapter, id = sessionId) {
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(ManagementGate, { sessionId: id, adapter }),
    ),
  );
  await settle();
  return root;
}
async function unmount(root) {
  await act(async () => root.unmount());
}
function backend({ existing = true, locked = false } = {}) {
  const assignment = {
    gameId: 'game',
    gameName: 'Gra',
    gameStatus: 'active',
    attached: true,
  };
  const machine = {
    id: 'machine',
    pointId: 'point',
    name: 'Maszyna',
    archived: false,
    revision: 1,
    assignments: existing ? [assignment] : [],
  };
  const point = {
    id: 'point',
    name: 'Punkt',
    city: 'Miasto',
    street: 'Ulica',
    archived: false,
    revision: 1,
    machines: existing ? [machine] : [],
  };
  const state = {
    points: existing ? [point] : [],
    activeGames: [{ id: 'game', name: 'Gra' }],
    slots: stakes.map((s) => (existing && s === 2000 ? slot(s) : empty(s))),
    entries: [],
    calls: [],
    lost: false,
    lostCorrection: false,
    deny: false,
    contextDenied: locked,
  };
  const receipt = new Map();
  const context = {
    sessionId,
    label: 'Odbiorca',
    expiresAt: '2099-01-01T00:00:00Z',
  };
  const json = (value, status = 200) =>
    new Response(JSON.stringify(value), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });
  state.fetch = async (request) => {
    const url = new URL(request.url),
      path = url.pathname.replace(
        '/management-api/api/v1/management-public',
        '',
      );
    const body = request.method === 'GET' ? null : await request.json();
    state.calls.push({
      path,
      method: request.method,
      body,
      session: request.headers.get('X-Management-Session'),
    });
    if (path === '/context')
      return state.contextDenied
        ? json({ code: 'MANAGEMENT_TOKEN_INVALID' }, 401)
        : json(context);
    if (path.endsWith('/unlock')) {
      state.contextDenied = false;
      return json(context);
    }
    if (state.deny) return json({ code: 'MANAGEMENT_TOKEN_INVALID' }, 401);
    if (path === '')
      return json({ points: state.points, activeGames: state.activeGames });
    if (path === '/points' && body) {
      Object.assign(point, body);
      state.points = [point];
      return json(point);
    }
    if (path === '/points/point' && body) {
      Object.assign(point, body, { revision: point.revision + 1 });
      return json(point);
    }
    if (path === '/points/point/machines' && body) {
      Object.assign(machine, body);
      machine.assignments = (body.gameIds ?? []).map(() => assignment);
      point.machines = [machine];
      return json(machine);
    }
    if (path === '/points/point/machines/machine' && body) {
      Object.assign(machine, body, { revision: machine.revision + 1 });
      return json(machine);
    }
    if (path === '/machines/machine/assignments') {
      machine.assignments = body.gameIds.map(() => assignment);
      machine.revision++;
      return json(machine);
    }
    if (path === '/machines/machine/journal')
      return json({ entries: state.entries, nextCursor: null });
    if (path.endsWith('/symbols'))
      return json([{ ...symbol, imageRevision: 'b'.repeat(64) }]);
    if (path.endsWith('/search'))
      return json({
        searchContextId: 'context',
        search: {
          queryCellCount: body.cells.length,
          scope: body.scope ?? 'all_searchable',
          results: [
            {
              sequenceNumber: 9,
              boardChecksumSha256: 'a'.repeat(64),
              status: 'accepted',
              score: { score: 100 },
            },
          ],
        },
      });
    if (path.endsWith('/approximate-win'))
      return json(
        calc(
          Number(url.searchParams.get('startSequenceNumber')),
          Number(url.searchParams.get('spinCount')),
        ),
      );
    if (path.endsWith('/stakes') && request.method === 'GET')
      return json({ slots: state.slots });
    if (path.includes('/results/')) return json(result(path.split('/').at(-1)));
    if (path.endsWith('/cells/0/decision')) {
      if (receipt.has(body.operationId))
        return json(receipt.get(body.operationId));
      state.entries.push({
        id: body.operationId,
        createdAt: '2026-10-08T00:00:00Z',
        action: 'symbol.correct',
        actor: `management-share:${sessionId}:Odbiorca`,
        stakeGrosze: 2000,
        before: { symbolCode: null, cellIndex: 0 },
        after: { symbolCode: 'cherry', cellIndex: 0 },
        beforeResultId: null,
        afterResultId: null,
      });
      const saved = {
        saved: true,
        changed: true,
        sequenceNumber: 9,
        cellIndex: 0,
        cellVersion: 'c'.repeat(64),
      };
      receipt.set(body.operationId, saved);
      if (state.lostCorrection) {
        state.lostCorrection = false;
        throw new Error('Lost committed correction');
      }
      return json(saved);
    }
    const stakeMatch = /\/stakes\/(\d+)(?:\/(.*))?$/.exec(path);
    if (stakeMatch) {
      const stake = Number(stakeMatch[1]),
        suffix = stakeMatch[2],
        old = state.slots.find((s) => s.stakeGrosze === stake);
      if (request.method === 'GET') return json(old);
      if (suffix === 'refresh')
        return json({ slot: old, status: 'current', changed: false });
      if (receipt.has(body.operationId))
        return json(receipt.get(body.operationId));
      if (body.expectedRevision !== old.revision)
        return json(
          { code: 'MANAGEMENT_REVISION_CONFLICT', message: 'Konflikt rewizji' },
          409,
        );
      const saved =
        suffix === 'clear'
          ? { ...empty(stake), revision: old.revision + 1 }
          : {
              ...slot(stake, old.revision + 1),
              spinCount: body.spinCount,
              pinnedSpinPositions: body.pinnedSpinPositions,
            };
      state.slots = state.slots.map((s) =>
        s.stakeGrosze === stake ? saved : s,
      );
      state.entries.push({
        id: body.operationId,
        createdAt: '2026-10-08T00:00:00Z',
        action: suffix === 'clear' ? 'stake.clear' : 'stake.save',
        actor: `management-share:${sessionId}:Odbiorca`,
        stakeGrosze: stake,
        before: old,
        after: saved,
        beforeResultId: old.resultVersionId,
        afterResultId: saved.resultVersionId,
      });
      receipt.set(body.operationId, saved);
      if (state.lost) {
        state.lost = false;
        throw new Error('Lost committed response');
      }
      return json(saved);
    }
    if (path.includes('/boards/'))
      return json({
        gameId: 'game',
        sequenceNumber: 9,
        boardStatus: 'accepted',
        boardChecksumSha256: 'a'.repeat(64),
        dataSource: 'operational_review',
        rules: calc().rules,
        symbolCodes: Array(15).fill(
          state.entries.some((e) => e.action === 'symbol.correct')
            ? 'cherry'
            : null,
        ),
        payoutCredits: 0,
        payoutKind: 'none',
        matches: [],
        view: null,
        documentStale: false,
        cells: Array.from({ length: 15 }, (_, cellIndex) => ({
          cellIndex,
          cellVersion: 'b'.repeat(64),
          assignedSymbolCode: null,
          reviewState: 'pending',
          qualityIssue: null,
        })),
      });
    assert.fail('Unexpected public route ' + path);
  };
  return state;
}

test('phone-width public gate completes point/machine assignment, search, independent stake Save, history and confirmed Clear', async () => {
  dom.window.sessionStorage.clear();
  const server = backend({ existing: false, locked: true });
  const adapter = createManagementPublicAdapter({
    sessionId,
    fetchImplementation: server.fetch,
  });
  const root = await mount(adapter);
  assert.match(text(), /Podaj kod/);
  assert.ok(document.querySelector('.management-access-gate'));
  await input(document.querySelector('input'), 'ABCD-EFGH');
  await submit(document.querySelector('form'));
  await until(() => button('Dodaj punkt'));
  assert.equal(button('Udostępnij panel online'), undefined);
  await click(button('Dodaj punkt'));
  const pointForm = document.querySelector('form[aria-label="Edycja punktu"]');
  for (const [i, value] of ['Punkt', 'Miasto', 'Ulica'].entries())
    await input(pointForm.querySelectorAll('input')[i], value);
  await submit(pointForm);
  await until(() => document.querySelector('.management-tile > button'));
  await click(document.querySelector('.management-tile > button'));
  await click(button('Dodaj maszynę'));
  const machineForm = document.querySelector(
    'form[aria-label="Edycja maszyny"]',
  );
  await input(machineForm.querySelector('input'), 'Maszyna');
  await click(machineForm.querySelector('input[type="checkbox"]'));
  await submit(machineForm);
  await click(
    [...document.querySelectorAll('.management-tile-choice')].find((node) =>
      node.textContent.includes('Maszyna'),
    ),
  );
  await until(() => card());
  assert.equal(
    document.querySelectorAll('.management-stake-cards > button').length,
    6,
  );
  await click(card());
  await until(() => document.querySelector('.boardSearchPaletteGrid button'));
  await click(
    [...document.querySelectorAll('.boardSearchPaletteGrid button')].find((n) =>
      n.textContent.includes('Wiśnia'),
    ),
  );
  await click(button('Szukaj plansz'));
  await until(() =>
    document.querySelector(
      'input[aria-label="Zakres wygranej — liczba kolejnych spinów"]',
    ),
  );
  await range(10);
  await click(button('Zapisz układ'));
  await until(() => server.entries.length === 1);
  assert.equal(server.slots.find((s) => s.stakeGrosze === 1000).empty, true);
  assert.equal(server.slots.find((s) => s.stakeGrosze === 2000).empty, false);
  await openSavedResult();
  await until(() => text().includes('Ostatni zapisany wynik'));
  assert.match(text(), /Odbiorca/);
  assert.doesNotMatch(text(), new RegExp(sessionId));
  await click(card());
  await click(button('Usuń zapisany układ'));
  await until(() => server.entries.length === 2);
  assert.equal(server.slots.find((s) => s.stakeGrosze === 2000).empty, true);
  assert.equal(server.entries[1].action, 'stake.clear');
  assert.ok(server.calls.every((call) => call.session === sessionId));
  assert.ok(server.calls.every((call) => !call.path.includes('/admin')));
  await unmount(root);
});

test('lost committed response survives reload; identical UUID/body retries once and local snapshot sees save', async () => {
  dom.window.sessionStorage.clear();
  const server = backend();
  const namespace = managementStorageNamespace(sessionId);
  let adapter = createManagementPublicAdapter({
    sessionId,
    fetchImplementation: server.fetch,
  });
  let root = await mount(adapter);
  await click(document.querySelector('.management-tile > button'));
  await click(
    [...document.querySelectorAll('.management-tile-choice')].find((node) =>
      node.textContent.includes('Maszyna'),
    ),
  );
  await until(() => card());
  await click(card());
  await range(11);
  server.lost = true;
  await click(button('Zapisz zmiany'));
  const pending = JSON.parse(
    dom.window.sessionStorage.getItem(managementSlotPendingKey(namespace)),
  );
  assert.ok(pending);
  assert.equal(server.entries.length, 1);
  assert.equal(server.slots[0].spinCount, 11);
  await unmount(root);
  adapter = createManagementPublicAdapter({
    sessionId,
    fetchImplementation: server.fetch,
  });
  root = await mount(adapter);
  await until(() => button('Sprawdź ostatni zapis stawki'));
  await click(button('Sprawdź ostatni zapis stawki'));
  const saves = server.calls.filter(
    (c) => c.path.endsWith('/stakes/2000') && c.method === 'PUT',
  );
  assert.equal(saves.length, 2);
  assert.deepEqual(saves[0].body, saves[1].body);
  assert.equal(server.entries.length, 1);
  assert.equal(
    dom.window.sessionStorage.getItem(managementSlotPendingKey(namespace)),
    null,
  );
  await unmount(root);
});

test('401 termination retains mounted dirty draft, loaded history and exact pending; stale callbacks make no new fetches', async () => {
  dom.window.sessionStorage.clear();
  const server = backend();
  const adapter = createManagementPublicAdapter({
    sessionId,
    fetchImplementation: server.fetch,
  });
  const root = await mount(adapter);
  await click(document.querySelector('.management-tile > button'));
  await click(
    [...document.querySelectorAll('.management-tile-choice')].find((node) =>
      node.textContent.includes('Maszyna'),
    ),
  );
  await until(() => card());
  await openSavedResult();
  await until(() => text().includes('Ostatni zapisany wynik'));
  await click(card());
  await click(
    document.querySelector('.boardSearchPaletteGrid button[title=\"Wiśnia\"]'),
  );
  await click(button('Szukaj plansz'));
  await range(11);
  const draftCell = document.querySelector(
    '.boardSearchGrid button[aria-label=\"Wiersz 1, kolumna 1: Wiśnia\"]',
  );
  assert.ok(draftCell);
  server.deny = true;
  await click(button('Zapisz zmiany'));
  await until(() => document.querySelector('.management-draft')?.disabled);
  assert.match(text(), /Dostęp zakończony/);
  assert.ok(
    document.querySelector(
      '.boardSearchGrid button[aria-label=\"Wiersz 1, kolumna 1: Wiśnia\"]',
    ),
  );
  assert.match(text(), /Twój wzór/);
  assert.ok(document.querySelector('[aria-label="Ostatni zapisany wynik"]'));
  assert.equal(
    document.querySelector(
      'input[aria-label="Zakres wygranej — liczba kolejnych spinów"]',
    ).value,
    '11',
  );
  assert.ok(
    dom.window.sessionStorage.getItem(
      managementSlotPendingKey(managementStorageNamespace(sessionId)),
    ),
  );
  const before = server.calls.length;
  await adapter
    .forMachine('machine')
    .getManagementApproximateWin('machine', 'game', {
      startSequenceNumber: 9,
      spinCount: 12,
    });
  assert.equal(server.calls.length, before);
  await unmount(root);
});

test('two tab stores recover independently; concurrent CAS rejects stale tab without overwriting first save', async () => {
  const a = new JSDOM('', { url: 'https://panel.example' }),
    b = new JSDOM('', { url: 'https://panel.example' });
  const server = backend();
  const one = createManagementPublicAdapter({
      sessionId,
      fetchImplementation: server.fetch,
    }),
    two = createManagementPublicAdapter({
      sessionId,
      fetchImplementation: server.fetch,
    });
  await one.context();
  await two.context();
  const body = {
    expectedRevision: 1,
    searchContextId: 'context',
    startSequenceNumber: 9,
    spinCount: 11,
    pinnedSpinPositions: [],
  };
  const operation = (id) => ({
    kind: 'save',
    machineId: 'machine',
    gameId: 'game',
    stake: 2000,
    body: { ...body, operationId: id },
  });
  const recoveryA = new ManagementSlotRecovery(
      a.window.sessionStorage,
      sessionId,
      () => {},
    ),
    recoveryB = new ManagementSlotRecovery(
      b.window.sessionStorage,
      sessionId,
      () => {},
    );
  const opA = operation('tab-a'),
    opB = operation('tab-b');
  await recoveryA.run(opA, () =>
    one
      .forMachine('machine')
      .saveManagementStake('machine', 'game', 2000, opA.body),
  );
  await assert.rejects(
    recoveryB.run(opB, () =>
      two
        .forMachine('machine')
        .saveManagementStake('machine', 'game', 2000, opB.body),
    ),
    /Konflikt rewizji/,
  );
  assert.equal(server.entries.length, 1);
  assert.equal(server.slots[0].revision, 2);
  assert.equal(recoveryB.pending, null);
  a.window.close();
  b.window.close();
});

test('old tab expected identity remains unchanged after another link unlocks; pending401/403 retained and no late receipt accepted', async () => {
  const a = new JSDOM('', { url: 'https://panel.example' });
  let valid = sessionId,
    calls = 0;
  const adapter = createManagementPublicAdapter({
    sessionId,
    fetchImplementation: async (req) => {
      calls++;
      const matches = req.headers.get('X-Management-Session') === valid;
      return new Response(
        JSON.stringify(
          matches
            ? {
                sessionId,
                label: 'Same name',
                expiresAt: '2099-01-01T00:00:00Z',
              }
            : { code: 'MANAGEMENT_TOKEN_INVALID' },
        ),
        {
          status: matches ? 200 : 401,
          headers: { 'Content-Type': 'application/json' },
        },
      );
    },
  });
  await adapter.context();
  valid = otherSession;
  const recovery = new ManagementSlotRecovery(
    a.window.sessionStorage,
    sessionId,
    () => {},
  );
  const operation = {
    kind: 'clear',
    machineId: 'machine',
    gameId: 'game',
    stake: 2000,
    body: { operationId: 'original', expectedRevision: 1, confirmed: true },
  };
  await assert.rejects(
    recovery.run(operation, () =>
      adapter
        .forMachine('machine')
        .clearManagementStake('machine', 'game', 2000, operation.body),
    ),
  );
  assert.deepEqual(recovery.pending, operation);
  const count = calls;
  await adapter.client.getManagementSnapshot();
  assert.equal(calls, count);
  const another = new ManagementSlotRecovery(
    a.window.sessionStorage,
    otherSession,
    () => {},
  );
  assert.equal(another.pending, null);
  await assert.rejects(
    recovery.run(operation, async () => ({
      error: { message: 'Denied' },
      response: { status: 403 },
    })),
  );
  assert.deepEqual(recovery.pending, operation);
  a.window.close();
});

test('ending during body download refuses 200 receipt; image URLs bind identity and become inert after expiry', async () => {
  let clock = 0,
    release,
    waiting;
  const delay = new Promise((r) => (waiting = r));
  const adapter = createManagementPublicAdapter({
    sessionId,
    now: () => clock,
    fetchImplementation: async (req) => {
      if (new URL(req.url).pathname.endsWith('/context'))
        return new Response(
          JSON.stringify({
            sessionId,
            label: 'Actor',
            expiresAt: '2099-01-01T00:00:00Z',
          }),
          { headers: { 'Content-Type': 'application/json' } },
        );
      return new Response(
        new ReadableStream({
          start(controller) {
            release = () => {
              controller.enqueue(new TextEncoder().encode('{}'));
              controller.close();
            };
            waiting();
          },
        }),
      );
    },
  });
  await adapter.context();
  const game = adapter.forMachine('machine');
  const url = game.boardSearchBoardViewUrl(
    'game',
    9,
    'a'.repeat(64),
    'b'.repeat(64),
  );
  assert.equal(new URL(url).searchParams.get('expectedSessionId'), sessionId);
  const late = adapter.client.getManagementSnapshot();
  await delay;
  adapter.end();
  release();
  const response = await late;
  assert.equal(response.data, undefined);
  assert.match(
    game.boardSearchBoardViewUrl('game', 9, 'a'.repeat(64)),
    /^data:/,
  );
});

test('code errors and actor labels use actual backend values; common responsive CSS imported by both apps', async () => {
  assert.match(
    managementAccessMessage({ code: 'MANAGEMENT_CODE_INVALID' }),
    /Nieprawidłowy kod/,
  );
  assert.match(
    managementAccessMessage({ code: 'MANAGEMENT_CODE_LOCKED' }),
    /pięciu/,
  );
  assert.equal(
    managementActorLabel(`management-share:${sessionId}:Nazwa: odbiorca`),
    'Nazwa: odbiorca',
  );
  assert.equal(managementActorLabel('local-owner'), 'Administrator lokalny');
  const css = await readFile(
    new URL(
      '../../../packages/board-search-ui/src/management/management.css',
      import.meta.url,
    ),
    'utf8',
  );
  assert.match(css, /overflow-wrap: anywhere/);
  assert.match(css, /min-height: 44px/);
  assert.match(
    css,
    /\.management-access-gate input,\s*\.management-access-gate button\s*\{\s*min-height: 44px;/,
  );
  assert.match(css, /@media \(max-width: 640px\)/);
  for (const path of [
    '../../admin/src/app/layout.tsx',
    '../src/app/management/page.tsx',
  ])
    assert.match(
      await readFile(new URL(path, import.meta.url), 'utf8'),
      /board-search-ui\/management.css/,
    );
  assert.notEqual(
    managementPendingKey(managementStorageNamespace(sessionId)),
    managementPendingKey(managementStorageNamespace(otherSession)),
  );
});

test('public modal writes current symbol immediately with opaque version, fixed stake and named before/after journal', async () => {
  dom.window.sessionStorage.clear();
  const server = backend();
  const adapter = createManagementPublicAdapter({
    sessionId,
    fetchImplementation: server.fetch,
  });
  const root = await mount(adapter);
  await click(document.querySelector('.management-tile > button'));
  await click(
    [...document.querySelectorAll('.management-tile-choice')].find((node) =>
      node.textContent.includes('Maszyna'),
    ),
  );
  await until(() => card());
  await openSavedResult();
  await until(() => button('Edytuj bieżącą planszę startową'));
  await click(button('Edytuj bieżącą planszę startową'));
  await until(() => document.querySelector('.boardSearchBoardCellTarget'));
  await click(document.querySelector('.boardSearchBoardCellTarget'));
  await click(
    document.querySelector(
      '.boardSearchBoardCellPalette button[title="Wiśnia"]',
    ),
  );
  const call = server.calls.find((c) => c.path.endsWith('/cells/0/decision'));
  assert.equal(call.body.expectedCellVersion, 'b'.repeat(64));
  assert.equal(typeof call.body.operationId, 'string');
  assert.equal(call.body.targetSymbolCode, 'cherry');
  assert.equal(call.body.expectedRevision, 1);
  assert.match(call.path, /stakes\/2000/);
  await expand('Dziennik');
  await until(() => text().includes('Korekta symbolu'));
  assert.match(text(), /Przed:.*Symbol: nieznany/);
  assert.match(text(), /Po:.*Symbol: cherry/);
  assert.match(text(), /Odbiorca/);
  assert.doesNotMatch(text(), new RegExp(sessionId));
  assert.equal(server.slots[0].startSequenceNumber, 9);
  assert.equal(server.entries.length, 1);
  await unmount(root);
});

test('server expiry clock retains loaded points and rejects all further reads', async () => {
  dom.window.sessionStorage.clear();
  const server = backend();
  let now = Date.now();
  const adapter = createManagementPublicAdapter({
    sessionId,
    fetchImplementation: server.fetch,
    now: () => now,
  });
  const root = await mount(adapter);
  assert.match(text(), /Punkt/);
  const count = server.calls.length;
  now = Date.parse('2099-01-01T00:00:01Z');
  await until(() => text().includes('Dostęp zakończony'));
  assert.match(text(), /Punkt/);
  assert.equal(button('Dodaj punkt').disabled, true);
  await adapter.client.getManagementSnapshot();
  assert.equal(server.calls.length, count);
  await unmount(root);
});

test('aborted source rejects new reads and corrections and fences late callbacks', async () => {
  const storage = new JSDOM('', { url: 'https://panel.example' });
  let calls = 0,
    committed = 0,
    release;
  const recovery = new ManagementSlotRecovery(
    storage.window.sessionStorage,
    'aborted',
    () => {},
  );
  const source = createManagementDataSource({
    api: {
      correctManagementBoardCell: async () => {
        calls++;
        return new Promise((resolve) => {
          release = () => resolve({ data: {} });
        });
      },
      listSymbols: async () => {
        calls++;
        return { data: [] };
      },
    },
    machineId: 'machine',
    gameId: 'game',
    stake: 2000,
    recovery,
    getRevision: () => 1,
    onCommitted: () => committed++,
    onConflict: () => {},
    canAccess: () => true,
  });
  const correction = source.client.correctBoardSearchCell('game', 9, 0, {
    expectedCellVersion: 'b'.repeat(64),
    targetSymbolCode: 'cherry',
  });
  assert.equal(calls, 1);
  source.abort();
  release();
  await correction;
  assert.equal(committed, 0);
  assert.equal(recovery.pending.kind, 'correction');
  await assert.rejects(
    source.client.correctBoardSearchCell('game', 9, 0, {
      expectedCellVersion: 'b'.repeat(64),
      targetSymbolCode: 'cherry',
    }),
  );
  await assert.rejects(source.client.listSymbols('game'));
  assert.equal(calls, 1);
  storage.window.close();
});

test('unmounted structural mutation cannot retire a newer operation after reload and retry', async () => {
  dom.window.sessionStorage.clear();
  const server = backend({ existing: false });
  const delayed = [];
  let hold = true;
  const fetchImplementation = async (request) => {
    const response = await server.fetch(request);
    if (
      hold &&
      request.method === 'POST' &&
      new URL(request.url).pathname.endsWith('/points')
    ) {
      return new Promise((resolve) => delayed.push(() => resolve(response)));
    }
    return response;
  };
  let root = await mount(
    createManagementPublicAdapter({ sessionId, fetchImplementation }),
  );
  await click(button('Dodaj punkt'));
  await input(document.querySelector('form input'), 'Pierwszy');
  await submit(document.querySelector('form'));
  assert.equal(delayed.length, 1);
  const key = managementPendingKey(managementStorageNamespace(sessionId));
  const original = JSON.parse(dom.window.sessionStorage.getItem(key));
  await unmount(root);
  hold = false;
  root = await mount(
    createManagementPublicAdapter({ sessionId, fetchImplementation }),
  );
  await click(button('Ponów ten sam zapis'));
  assert.equal(dom.window.sessionStorage.getItem(key), null);
  hold = true;
  await click(button('Dodaj punkt'));
  await input(document.querySelector('form input'), 'Nowszy');
  await submit(document.querySelector('form'));
  assert.equal(delayed.length, 2);
  const newer = dom.window.sessionStorage.getItem(key);
  assert.notEqual(
    JSON.parse(newer).body.operationId,
    original.body.operationId,
  );
  await act(async () => {
    delayed[0]();
  });
  await settle();
  assert.equal(dom.window.sessionStorage.getItem(key), newer);
  await act(async () => {
    delayed[1]();
  });
  await settle();
  assert.equal(dom.window.sessionStorage.getItem(key), null);
  await unmount(root);
});

test('unlock renders actual invalid and locked code errors; capability denial fences while game eligibility does not', async () => {
  for (const [code, message] of [
    ['MANAGEMENT_CODE_INVALID', 'Nieprawidłowy kod'],
    ['MANAGEMENT_CODE_LOCKED', 'pięciu'],
  ]) {
    dom.window.sessionStorage.clear();
    const server = backend({ locked: true });
    const adapter = createManagementPublicAdapter({
      sessionId,
      fetchImplementation: async (request) =>
        new URL(request.url).pathname.endsWith('/unlock')
          ? new Response(JSON.stringify({ code }), {
              status: 401,
              headers: { 'Content-Type': 'application/json' },
            })
          : server.fetch(request),
    });
    const root = await mount(adapter);
    await input(document.querySelector('input'), 'ABCD-EFGH');
    await submit(document.querySelector('form'));
    assert.match(
      document.querySelector('[role="alert"]').textContent,
      new RegExp(message),
    );
    await unmount(root);
  }
  let failure = 'MANAGEMENT_GAME_INACTIVE';
  const server = backend();
  const adapter = createManagementPublicAdapter({
    sessionId,
    fetchImplementation: async (request) =>
      new URL(request.url).pathname.endsWith('/context')
        ? server.fetch(request)
        : new Response(JSON.stringify({ code: failure }), {
            status: 403,
            headers: { 'Content-Type': 'application/json' },
          }),
  });
  await adapter.context();
  await adapter.client.getManagementSnapshot();
  assert.equal(adapter.active(), true);
  failure = 'MANAGEMENT_PROXY_REQUIRED';
  await adapter.client.getManagementSnapshot();
  assert.equal(adapter.active(), false);
});

test('public correction lost response reload retries original opaque request and keeps one named journal entry', async () => {
  dom.window.sessionStorage.clear();
  const server = backend();
  let root = await mount(
    createManagementPublicAdapter({
      sessionId,
      fetchImplementation: server.fetch,
    }),
  );
  await click(document.querySelector('.management-tile > button'));
  await click(
    [...document.querySelectorAll('.management-tile-choice')].find((node) =>
      node.textContent.includes('Maszyna'),
    ),
  );
  await until(() => card());
  await openSavedResult();
  await until(() => button('Edytuj bieżącą planszę startową'));
  await click(button('Edytuj bieżącą planszę startową'));
  await until(() => document.querySelector('.boardSearchBoardCellTarget'));
  server.lostCorrection = true;
  await click(document.querySelector('.boardSearchBoardCellTarget'));
  await click(
    document.querySelector(
      '.boardSearchBoardCellPalette button[title="Wiśnia"]',
    ),
  );
  const key = managementSlotPendingKey(managementStorageNamespace(sessionId));
  const pending = JSON.parse(dom.window.sessionStorage.getItem(key));
  assert.equal(pending.kind, 'correction');
  assert.equal(server.entries.length, 1);
  await unmount(root);
  root = await mount(
    createManagementPublicAdapter({
      sessionId,
      fetchImplementation: server.fetch,
    }),
  );
  await until(() => button('Sprawdź ostatni zapis stawki'));
  await click(button('Sprawdź ostatni zapis stawki'));
  const writes = server.calls.filter((call) =>
    call.path.endsWith('/cells/0/decision'),
  );
  assert.equal(writes.length, 2);
  assert.deepEqual(writes[0].body, writes[1].body);
  assert.equal(server.entries.length, 1);
  assert.equal(dom.window.sessionStorage.getItem(key), null);
  assert.match(text(), /Odbiorca/);
  await unmount(root);
});
