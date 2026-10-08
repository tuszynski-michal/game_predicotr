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
async function mount(client) {
  const root = createRoot(document.getElementById('root'));
  await act(async () => {
    root.render(
      React.createElement(ManagementWorkspace, {
        apiBaseUrl: 'http://127.0.0.1:8000',
        client,
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

test('unrelated assignment preserves attached inactive history and prevents double submit', async () => {
  dom.window.sessionStorage.clear();
  const calls = [];
  let resolveWrite;
  const client = {
    ...clientFor(snapshot),
    updateManagementAssignments: (id, body) => {
      calls.push({ id, body });
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
  const checkbox = document.querySelector('fieldset input');
  await click(checkbox);
  assert.deepEqual([...calls[0].body.gameIds].sort(), ['new-game', 'old-game']);
  assert.equal(document.querySelector('fieldset').disabled, true);
  await click(checkbox);
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

test('point create, rename, archive and restore preserve the selected hierarchy', async () => {
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
  await click(button('Edytuj punkt'));
  await input(0, 'Zmieniony punkt');
  await click(button('Zapisz'));
  assert.equal(server.points[0].name, 'Zmieniony punkt');
  dom.window.confirm = () => true;
  await click(button('Archiwizuj punkt'));
  assert.equal(server.points[0].archived, true);
  await click(document.querySelector('.management-actions input'));
  await click(button('Przywróć punkt'));
  assert.equal(server.points[0].archived, false);
  assert.equal(server.points.length, 1);
  await unmount(root);
});
