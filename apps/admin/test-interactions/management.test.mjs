import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
globalThis.React = React;

import { registerHooks } from 'node:module';
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
const { ManagementWorkspace } =
  await import('../src/features/management/management-workspace.tsx');
import {
  MANAGEMENT_PENDING_KEY,
  readManagementOperation,
} from '../src/features/management/management-operation.ts';

const dom = new JSDOM('<!doctype html><div id="root"></div>', {
  url: 'http://127.0.0.1:3000/?workspace=management',
});
for (const key of [
  'window',
  'document',
  'HTMLElement',
  'Element',
  'Event',
  'MouseEvent',
])
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import('react-dom/client');
after(() => dom.window.close());

const point = {
  id: 'point-1',
  name: 'Punkt',
  city: 'Miasto',
  street: 'Ulica',
  archived: false,
  revision: 1,
  updatedAt: '2026-10-07T00:00:00Z',
  machines: [],
};
const machine = {
  id: 'machine-1',
  pointId: point.id,
  name: 'Maszyna',
  archived: false,
  revision: 1,
  updatedAt: point.updatedAt,
  assignments: [
    {
      gameId: 'old-game',
      gameName: 'Stara gra',
      gameStatus: 'archived',
      attached: true,
    },
  ],
};
const snapshot = {
  points: [{ ...point, machines: [machine] }],
  activeGames: [{ id: 'new-game', name: 'Nowa gra' }],
};
const text = () => document.body.textContent;
const button = (label) =>
  [...document.querySelectorAll('button')].find(
    (item) => item.textContent.trim() === label,
  );
async function click(item) {
  assert.ok(item);
  await act(async () => {
    item.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
  });
}
async function mount(client, props = {}) {
  const root = createRoot(document.getElementById('root'));
  await act(async () => {
    root.render(
      React.createElement(ManagementWorkspace, {
        apiBaseUrl: 'http://127.0.0.1:8000',
        client,
        ...props,
      }),
    );
  });
  return root;
}
async function unmount(root) {
  await act(async () => root.unmount());
}
function clientFor(value) {
  return { getManagementSnapshot: async () => ({ data: value }) };
}

test('empty, error and retry states render with functional controls', async () => {
  dom.window.sessionStorage.clear();
  let fail = true;
  const root = await mount({
    getManagementSnapshot: async () => {
      if (fail) throw new Error('API niedostępne');
      return { data: { points: [], activeGames: [] } };
    },
  });
  assert.match(text(), /API niedostępne/);
  fail = false;
  await click(button('Odśwież'));
  assert.match(text(), /Brak punktów/);
  await click(button('Dodaj punkt'));
  assert.equal(button('Zapisz').disabled, true);
  await unmount(root);
});

test('machine modal saves name and games atomically; legacy assignment remains selected', async () => {
  dom.window.sessionStorage.clear();
  const calls = [];
  let resolveWrite;
  const client = {
    ...clientFor(snapshot),
    updateManagementMachine: (pointId, machineId, body) => {
      calls.push({ pointId, machineId, body });
      return new Promise((resolve) => {
        resolveWrite = resolve;
      });
    },
  };
  const root = await mount(client);
  await click(
    [...document.querySelectorAll('button')].find((item) =>
      item.textContent.includes('PunktMiasto'),
    ),
  );
  await click(
    document.querySelector('button[aria-label="Edytuj maszynę Maszyna"]'),
  );
  const checkbox = [
    ...document.querySelectorAll('.management-modal input[type="checkbox"]'),
  ].find((node) => node.parentElement.textContent.includes('Nowa gra'));
  await click(checkbox);
  await click(button('Zapisz'));
  assert.deepEqual([...calls[0].body.gameIds].sort(), ['new-game', 'old-game']);
  assert.equal(button('Zapisz').disabled, true);
  await click(button('Zapisz'));
  assert.equal(calls.length, 1);
  await act(async () => resolveWrite({ data: machine }));
  assert.equal(dom.window.sessionStorage.getItem(MANAGEMENT_PENDING_KEY), null);
  await unmount(root);
});

test('lost response and 5xx retain exact command across remount; each tab has independent recovery', async () => {
  dom.window.sessionStorage.clear();
  const operation = {
    kind: 'point',
    body: {
      operationId: 'lost-operation',
      expectedRevision: 0,
      name: 'Nowy',
      city: 'M',
      street: 'U',
    },
  };
  dom.window.sessionStorage.setItem(
    MANAGEMENT_PENDING_KEY,
    JSON.stringify(operation),
  );
  const calls = [];
  let retry = 0;
  const client = {
    ...clientFor({ points: [], activeGames: [] }),
    createManagementPoint: async (body) => {
      calls.push(body);
      retry++;
      if (retry === 1)
        return {
          error: { message: 'Nieznany wynik' },
          response: { status: 500 },
        };
      if (retry === 2) throw new Error('Utracona odpowiedź');
      return { data: point };
    },
  };
  let root = await mount(client);
  assert.equal(button('Dodaj punkt').disabled, true);
  await click(button('Ponów ten sam zapis'));
  assert.deepEqual(
    readManagementOperation(dom.window.sessionStorage),
    operation,
  );
  await unmount(root);
  root = await mount(client);
  await click(button('Ponów ten sam zapis'));
  await unmount(root);
  root = await mount(client);
  await click(button('Ponów ten sam zapis'));
  assert.deepEqual(calls, [operation.body, operation.body, operation.body]);
  assert.equal(dom.window.sessionStorage.getItem(MANAGEMENT_PENDING_KEY), null);
  const tabB = new JSDOM('', { url: 'http://127.0.0.1:3000/' });
  dom.window.sessionStorage.setItem(
    MANAGEMENT_PENDING_KEY,
    JSON.stringify(operation),
  );
  tabB.window.sessionStorage.setItem(
    MANAGEMENT_PENDING_KEY,
    JSON.stringify({
      ...operation,
      body: { ...operation.body, operationId: 'tab-b' },
    }),
  );
  tabB.window.sessionStorage.removeItem(MANAGEMENT_PENDING_KEY);
  assert.deepEqual(
    readManagementOperation(dom.window.sessionStorage),
    operation,
  );
  tabB.window.close();
  await unmount(root);
});

test('point create, rename and preview-bound deletion preserve the selected hierarchy', async () => {
  dom.window.sessionStorage.clear();
  const server = { points: [], activeGames: [] };
  const calls = [];
  const client = {
    ...clientFor(server),
    createManagementPoint: async (body) => {
      calls.push(body);
      const saved = { ...point, ...body, machines: [] };
      server.points = [saved];
      return { data: saved };
    },
    updateManagementPoint: async (id, body) => {
      calls.push(body);
      server.points = [
        { ...server.points[0], ...body, revision: body.expectedRevision + 1 },
      ];
      return { data: server.points[0] };
    },
    previewManagementPointDeletion: async () => ({
      data: {
        previewToken: 'preview-1',
        expiresAt: '2030-01-01',
        counts: { points: 1, machines: 0, slots: 0 },
      },
    }),
    deleteManagementPoint: async (id, body) => {
      calls.push(body);
      server.points = [];
      return {
        data: {
          operationId: body.operationId,
          pointId: id,
          counts: { points: 1 },
        },
      };
    },
  };
  const root = await mount(client);
  await click(button('Dodaj punkt'));
  async function input(index, value) {
    const node = document.querySelectorAll('form input')[index];
    await act(async () => {
      Object.getOwnPropertyDescriptor(
        dom.window.HTMLInputElement.prototype,
        'value',
      ).set.call(node, value);
      node.dispatchEvent(new dom.window.Event('input', { bubbles: true }));
    });
  }
  await input(0, 'Nowy punkt');
  await input(1, 'Łódź');
  await input(2, 'Długa 1');
  await click(button('Zapisz'));
  assert.equal(server.points[0].name, 'Nowy punkt');
  assert.equal(calls[0].expectedRevision, 0);
  await click(
    document.querySelector('button[aria-label="Edytuj punkt Nowy punkt"]'),
  );
  await input(0, 'Zmieniony punkt');
  await click(button('Zapisz'));
  assert.equal(server.points[0].name, 'Zmieniony punkt');
  await click(
    document.querySelector('button[aria-label="Usuń punkt Zmieniony punkt"]'),
  );
  assert.match(text(), /Trwale usunąć punkt/);
  assert.match(text(), /Punkty: 1/);
  await click(button('Potwierdź usunięcie'));
  assert.equal(calls.at(-1).previewToken, 'preview-1');
  assert.equal(server.points.length, 0);
  await unmount(root);
});

test('removing a legacy detached game previews the exact machine command and keeps modal draft on conflict', async () => {
  dom.window.sessionStorage.clear();
  dom.window.history.replaceState(null, '', '/?workspace=management');
  const detached = {
    ...machine,
    assignments: [{ ...machine.assignments[0], attached: false }],
  };
  const data = {
    points: [{ ...point, machines: [detached] }],
    activeGames: [],
  };
  const previews = [];
  const writes = [];
  const client = {
    ...clientFor(data),
    previewManagementMachineUpdate: async (id, body) => {
      previews.push({ id, command: structuredClone(body.command) });
      return {
        data: {
          previewToken: 'bound-token',
          counts: { assignments: 1, slots: 1 },
          expiresAt: '2030-01-01',
        },
      };
    },
    updateManagementMachine: async (...args) => {
      writes.push(args);
      return {
        response: { status: 409 },
        error: { message: 'Podgląd wygasł' },
      };
    },
  };
  const root = await mount(client);
  await click(
    [...document.querySelectorAll('.management-tile-choice')].find((node) =>
      node.textContent.includes('Punkt'),
    ),
  );
  await click(
    document.querySelector('button[aria-label="Edytuj maszynę Maszyna"]'),
  );
  const input = document.querySelector(
    '.management-modal input:not([type="checkbox"])',
  );
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      dom.window.HTMLInputElement.prototype,
      'value',
    ).set.call(input, 'Nowa nazwa');
    input.dispatchEvent(new dom.window.Event('input', { bubbles: true }));
  });
  await click(
    document.querySelector('.management-modal input[type="checkbox"]'),
  );
  dom.window.confirm = () => true;
  await click(button('Zapisz'));
  assert.equal(previews.length, 1);
  assert.deepEqual(previews[0].command.gameIds, []);
  assert.equal(writes[0][2].operationId, previews[0].command.operationId);
  assert.equal(writes[0][2].previewToken, 'bound-token');
  assert.equal(input.value, 'Nowa nazwa');
  assert.match(text(), /Podgląd wygasł/);
  await unmount(root);
});

test('lost delete response retains exact UUID and body; reload never retries without a click', async () => {
  dom.window.sessionStorage.clear();
  dom.window.history.replaceState(null, '', '/?workspace=management');
  const calls = [];
  const client = {
    ...clientFor({ points: [point], activeGames: [] }),
    previewManagementPointDeletion: async () => ({
      data: {
        previewToken: 'delete-token',
        counts: { points: 1 },
        expiresAt: '2030-01-01',
      },
    }),
    deleteManagementPoint: async (_id, body) => {
      calls.push(structuredClone(body));
      if (calls.length === 1) throw new Error('Utracona odpowiedź');
      return {
        data: {
          operationId: body.operationId,
          pointId: point.id,
          counts: { points: 1 },
        },
      };
    },
  };
  let root = await mount(client);
  await click(document.querySelector('button[aria-label="Usuń punkt Punkt"]'));
  await click(button('Potwierdź usunięcie'));
  const stored = readManagementOperation(dom.window.sessionStorage);
  assert.equal(stored.kind, 'delete-point');
  assert.equal(calls.length, 1);
  await unmount(root);
  root = await mount(client);
  assert.equal(calls.length, 1);
  await click(button('Ponów ten sam zapis'));
  assert.deepEqual(calls[1], calls[0]);
  assert.equal(dom.window.sessionStorage.getItem(MANAGEMENT_PENDING_KEY), null);
  await unmount(root);
});

test('edited modal refuses Home, popstate and close when discard is cancelled', async () => {
  dom.window.sessionStorage.clear();
  dom.window.history.replaceState(null, '', '/?workspace=management');
  const validPoint = { ...point, id: '11111111-1111-4111-8111-111111111111' };
  const root = await mount(
    clientFor({ points: [validPoint], activeGames: [] }),
  );
  await click(
    document.querySelector('button[aria-label="Edytuj punkt Punkt"]'),
  );
  const input = document.querySelector('.management-modal input');
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      dom.window.HTMLInputElement.prototype,
      'value',
    ).set.call(input, 'Niezapisane');
    input.dispatchEvent(new dom.window.Event('input', { bubbles: true }));
  });
  let prompts = 0;
  dom.window.confirm = () => {
    prompts++;
    return false;
  };
  await click(button('Punkty'));
  await click(button('Anuluj'));
  await act(async () => {
    dom.window.history.pushState(
      null,
      '',
      `/?workspace=management&mpPoint=${validPoint.id}`,
    );
    dom.window.dispatchEvent(new dom.window.PopStateEvent('popstate'));
  });
  assert.equal(prompts, 3);
  assert.equal(input.value, 'Niezapisane');
  assert.ok(document.querySelector('.management-modal'));
  await unmount(root);
});

test('focus detects concurrent point edit and save retains the opening revision', async () => {
  dom.window.sessionStorage.clear();
  dom.window.history.replaceState(null, '', '/?workspace=management');
  let server = { ...point, id: '11111111-1111-4111-8111-111111111111' };
  const sent = [];
  const root = await mount({
    getManagementSnapshot: async () => ({
      data: { points: [server], activeGames: [] },
    }),
    updateManagementPoint: async (_id, body) => {
      sent.push(body);
      return {
        error: { message: 'Konflikt rewizji' },
        response: { status: 409 },
      };
    },
  });
  await click(
    document.querySelector('button[aria-label="Edytuj punkt Punkt"]'),
  );
  const input = document.querySelector('.management-modal input');
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      dom.window.HTMLInputElement.prototype,
      'value',
    ).set.call(input, 'Moja zmiana');
    input.dispatchEvent(new dom.window.Event('input', { bubbles: true }));
  });
  server = { ...server, name: 'Cudza zmiana', revision: 2 };
  await act(async () =>
    dom.window.dispatchEvent(new dom.window.Event('focus')),
  );
  assert.match(text(), /zmieniły się w innym oknie/i);
  await click(button('Zapisz'));
  assert.equal(sent[0].expectedRevision, 1);
  assert.equal(input.value, 'Moja zmiana');
  assert.ok(document.querySelector('.management-modal'));
  await unmount(root);
});

test('pending operation restores once per namespace and focus does not reopen after Home', async () => {
  dom.window.sessionStorage.clear();
  dom.window.history.replaceState(null, '', '/?workspace=management');
  const operation = {
    kind: 'machine',
    pointId: point.id,
    machineId: machine.id,
    body: {
      operationId: 'restore-once',
      expectedRevision: 1,
      name: machine.name,
      archived: false,
      gameIds: [],
    },
  };
  dom.window.sessionStorage.setItem(
    MANAGEMENT_PENDING_KEY,
    JSON.stringify(operation),
  );
  const root = await mount(clientFor(snapshot));
  assert.match(dom.window.location.search, /mpMachine=machine-1/);
  await click(button('Punkty'));
  assert.doesNotMatch(dom.window.location.search, /mpMachine/);
  await act(async () =>
    dom.window.dispatchEvent(new dom.window.Event('focus')),
  );
  assert.doesNotMatch(dom.window.location.search, /mpMachine/);
  await unmount(root);
});

test('structural recovery preserves a valid game and stake in the same machine', async () => {
  dom.window.sessionStorage.clear();
  const pointId = '11111111-1111-4111-8111-111111111111';
  const machineId = '22222222-2222-4222-8222-222222222222';
  const gameId = '33333333-3333-4333-8333-333333333333';
  dom.window.history.replaceState(
    null,
    '',
    `/?workspace=management&mpPoint=${pointId}&mpMachine=${machineId}&mpGame=${gameId}&mpStake=2000`,
  );
  dom.window.sessionStorage.setItem(
    MANAGEMENT_PENDING_KEY,
    JSON.stringify({
      kind: 'machine',
      pointId,
      machineId,
      body: {
        operationId: 'recover-with-game',
        expectedRevision: 1,
        name: 'Maszyna',
        archived: false,
        gameIds: [gameId],
      },
    }),
  );
  const selectedMachine = {
    ...machine,
    id: machineId,
    pointId,
    assignments: [
      { gameId, gameName: 'Gra', gameStatus: 'active', attached: true },
    ],
  };
  const root = await mount(
    clientFor({
      points: [{ ...point, id: pointId, machines: [selectedMachine] }],
      activeGames: [{ id: gameId, name: 'Gra' }],
    }),
  );
  assert.match(dom.window.location.search, new RegExp(`mpGame=${gameId}`));
  assert.match(dom.window.location.search, /mpStake=2000/);
  await unmount(root);
});

test('pending operation from a different namespace cannot restore into this session', async () => {
  dom.window.sessionStorage.clear();
  dom.window.history.replaceState(null, '', '/?workspace=management');
  dom.window.sessionStorage.setItem(
    MANAGEMENT_PENDING_KEY,
    JSON.stringify({
      kind: 'machine',
      pointId: point.id,
      machineId: machine.id,
      body: {
        operationId: 'other-session',
        expectedRevision: 1,
        name: machine.name,
        archived: false,
        gameIds: [],
      },
    }),
  );
  const root = await mount(clientFor(snapshot), {
    storageNamespace: 'public-session-b',
  });
  assert.doesNotMatch(dom.window.location.search, /mpMachine/);
  assert.equal(button('Ponów ten sam zapis'), undefined);
  await unmount(root);
});

test('changing the public session namespace drops the previous modal draft', async () => {
  dom.window.sessionStorage.clear();
  dom.window.history.replaceState(null, '', '/?workspace=management');
  const validPoint = { ...point, id: '11111111-1111-4111-8111-111111111111' };
  const client = clientFor({ points: [validPoint], activeGames: [] });
  const root = await mount(client, { storageNamespace: 'public-session-a' });
  await click(
    document.querySelector('button[aria-label="Edytuj punkt Punkt"]'),
  );
  const input = document.querySelector('.management-modal input');
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      dom.window.HTMLInputElement.prototype,
      'value',
    ).set.call(input, 'Stary szkic');
    input.dispatchEvent(new dom.window.Event('input', { bubbles: true }));
  });
  await act(async () =>
    root.render(
      React.createElement(ManagementWorkspace, {
        client,
        storageNamespace: 'public-session-b',
      }),
    ),
  );
  assert.equal(document.querySelector('.management-modal'), null);
  assert.doesNotMatch(text(), /Stary szkic/);
  await unmount(root);
});

test('focus replaces a deleted machine and point URL with the nearest existing ancestor', async () => {
  dom.window.sessionStorage.clear();
  const pointId = '11111111-1111-4111-8111-111111111111';
  const machineId = '22222222-2222-4222-8222-222222222222';
  dom.window.history.replaceState(
    null,
    '',
    `/?workspace=management&mpPoint=${pointId}&mpMachine=${machineId}`,
  );
  let server = {
    points: [
      {
        ...point,
        id: pointId,
        machines: [{ ...machine, id: machineId, pointId }],
      },
    ],
    activeGames: [],
  };
  const root = await mount({
    getManagementSnapshot: async () => ({ data: server }),
  });
  server = { ...server, points: [{ ...server.points[0], machines: [] }] };
  await act(async () =>
    dom.window.dispatchEvent(new dom.window.Event('focus')),
  );
  assert.match(dom.window.location.search, /mpPoint=/);
  assert.doesNotMatch(dom.window.location.search, /mpMachine=/);
  server = { ...server, points: [] };
  await act(async () =>
    dom.window.dispatchEvent(new dom.window.Event('focus')),
  );
  assert.doesNotMatch(dom.window.location.search, /mpPoint=/);
  await unmount(root);
});
