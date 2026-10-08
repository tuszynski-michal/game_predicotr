import assert from 'node:assert/strict';

import { after, test } from 'node:test';

import { JSDOM } from 'jsdom';

import React, { act } from 'react';

import { ManagementSharePanel } from '../src/features/management/management-share-panel.tsx';

const dom = new JSDOM('<!doctype html><div id="root"></div>', {
  url: 'http://127.0.0.1:3000/',
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

const button = (label) =>
  [...document.querySelectorAll('button')].find(
    (item) => item.textContent.trim() === label,
  );

const click = async (item) =>
  act(async () =>
    item.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })),
  );

test('named link controls default to eight hours, retain code after remount and revoke explicitly', async () => {
  let sessions = [];

  const calls = [];

  const record = {
    sessionId: 'session-a',
    label: 'Recipient',
    status: 'active',
    failedAttempts: 0,
    createdAt: new Date().toISOString(),
    expiresAt: new Date(Date.now() + 3600000).toISOString(),
    shareUrl: 'https://review.example/management/session-a',
    onlineReady: true,
  };

  const client = {
    listManagementSessions: async () => ({ data: { sessions } }),

    createManagementSession: async (body) => {
      calls.push(body);
      sessions = [record];
      return { data: { session: record, accessCode: 'AAAA-BBBB' } };
    },

    revokeManagementSession: async (id) => {
      calls.push(id);
      sessions = [{ ...record, status: 'revoked' }];
      return { data: sessions[0] };
    },
  };

  async function mount() {
    const root = createRoot(document.getElementById('root'));
    await act(async () =>
      root.render(
        React.createElement(ManagementSharePanel, {
          apiBaseUrl: 'http://127.0.0.1:8000',
          client,
        }),
      ),
    );
    await click(button('Udostępnij panel online'));
    return root;
  }

  let root = await mount();

  assert.equal(document.querySelector('select').value, '480');

  assert.deepEqual(
    [...document.querySelectorAll('option')].map((o) => o.value),
    ['60', '240', '480', '1440', '2880', '4320'],
  );

  assert.equal(button('Utwórz link').disabled, true);

  const input = document.querySelector('input');

  await act(async () => {
    Object.getOwnPropertyDescriptor(
      dom.window.HTMLInputElement.prototype,
      'value',
    ).set.call(input, 'Recipient');
    input.dispatchEvent(new dom.window.Event('input', { bubbles: true }));
  });

  await click(button('Utwórz link'));

  assert.deepEqual(calls[0], { label: 'Recipient', lifetimeMinutes: 480 });

  assert.match(document.body.textContent, /AAAA-BBBB/);

  await act(async () => root.unmount());

  root = await mount();

  assert.match(document.body.textContent, /AAAA-BBBB/);

  window.confirm = () => false;

  await click(button('Zatrzymaj dostęp'));

  assert.equal(calls.length, 1);

  window.confirm = () => true;

  await click(button('Zatrzymaj dostęp'));

  assert.equal(calls[1], 'session-a');

  assert.doesNotMatch(document.body.textContent, /AAAA-BBBB/);

  assert.match(document.body.textContent, /Zatrzymany/);

  await act(async () => root.unmount());
});

test('late lists cannot hide a created link or reactivate a revoked link', async () => {
  const record = {
    sessionId: 'session-b',
    label: 'Race recipient',
    status: 'active',
    failedAttempts: 0,
    createdAt: new Date().toISOString(),
    expiresAt: new Date(Date.now() + 3600000).toISOString(),
    shareUrl: 'https://review.example/management/session-b',
    onlineReady: true,
  };

  let resolveList;
  let resolveCreate;

  const client = {
    listManagementSessions: () =>
      new Promise((resolve) => {
        resolveList = resolve;
      }),
    createManagementSession: () =>
      new Promise((resolve) => {
        resolveCreate = resolve;
      }),
    revokeManagementSession: async () => ({
      data: { ...record, status: 'revoked' },
    }),
  };

  const root = createRoot(document.getElementById('root'));

  await act(async () =>
    root.render(
      React.createElement(ManagementSharePanel, {
        apiBaseUrl: 'http://127.0.0.1:8000',
        client,
      }),
    ),
  );

  await click(button('Udostępnij panel online'));

  const input = document.querySelector('input');

  await act(async () => {
    Object.getOwnPropertyDescriptor(
      dom.window.HTMLInputElement.prototype,
      'value',
    ).set.call(input, 'Race recipient');
    input.dispatchEvent(new dom.window.Event('input', { bubbles: true }));
  });

  await click(button('Utwórz link'));
  assert.equal(button('Udostępnij panel online').disabled, true);
  await act(async () =>
    resolveCreate({ data: { session: record, accessCode: 'CCCC-DDDD' } }),
  );

  await act(async () => resolveList({ data: { sessions: [] } }));

  assert.match(document.body.textContent, /Race recipient/);

  assert.match(document.body.textContent, /CCCC-DDDD/);

  await click(button('Odśwież linki'));

  window.confirm = () => true;

  await click(button('Zatrzymaj dostęp'));

  await act(async () => resolveList({ data: { sessions: [record] } }));

  assert.match(document.body.textContent, /Zatrzymany/);

  assert.doesNotMatch(document.body.textContent, /CCCC-DDDD/);

  assert.equal(button('Zatrzymaj dostęp'), undefined);

  await act(async () => root.unmount());
});
