import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { registerHooks } from 'node:module';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
globalThis.React = React;
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
const panelId = '11111111-1111-4111-8111-111111111111';
const children = [
  '22222222-2222-4222-8222-222222222222',
  '33333333-3333-4333-8333-333333333333',
];
const secret = 'a'.repeat(43);
const dom = new JSDOM('<!doctype html><div id="root"></div>', {
  url: `https://share.example/board-search-panel?share=${panelId}#key=${secret}`,
});
for (const name of [
  'window',
  'document',
  'HTMLElement',
  'HTMLInputElement',
  'HTMLSelectElement',
  'Element',
  'Node',
  'Event',
  'MouseEvent',
  'KeyboardEvent',
  'sessionStorage',
  'navigator',
])
  Object.defineProperty(globalThis, name, {
    configurable: true,
    value: dom.window[name],
  });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import('react-dom/client');
const { BoardSearchPanelGate } =
  await import('../src/features/board-search-panel/board-search-panel-gate.tsx');
after(() => dom.window.close());
const context = {
  panelId,
  label: 'Gry',
  expiresAt: new Date(Date.now() + 3600000).toISOString(),
  games: children.map((sessionId, index) => ({
    sessionId,
    gameName: ['777', 'Mumie'][index],
  })),
};
const calls = [];
function backend(input, init) {
  const path = String(input);
  calls.push({ path, init });
  if (path.endsWith('/open') || path.endsWith('/context'))
    return Promise.resolve(Response.json(context));
  if (path.endsWith('/symbols')) {
    const second = path.includes(children[1]);
    return Promise.resolve(
      Response.json([
        {
          id: children[second ? 1 : 0],
          code: second ? 'B' : 'A',
          name: second ? 'Beta' : 'Alfa',
          namePl: null,
          nameEn: null,
          displayOrder: 1,
          isWildcard: false,
          mobileCode: 1,
          status: 'active',
          imageRevision: null,
        },
      ]),
    );
  }
  throw new Error('Unexpected route: ' + path);
}
async function settle() {
  await act(async () => new Promise((r) => setTimeout(r, 0)));
}
async function render() {
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(React.createElement(BoardSearchPanelGate, { panelId })),
  );
  for (let i = 0; i < 5; i++) await settle();
  return root;
}

test('link opens without a code, scrubs the secret, changes the real search palette and reloads through its cookie', async () => {
  globalThis.fetch = backend;
  let root = await render();
  assert.equal(calls[0].init.method, 'POST');
  assert.equal(JSON.parse(calls[0].init.body).linkKey, secret);
  assert.equal(dom.window.location.hash, '');
  assert.equal(
    document.querySelector('input[autocomplete="one-time-code"]'),
    null,
  );
  assert.ok(document.body.textContent.includes('Alfa'));
  const select = document.querySelector('select[aria-label="Gra"]');
  await act(async () => {
    select.value = children[1];
    select.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
  });
  for (let i = 0; i < 5; i++) await settle();
  assert.ok(document.body.textContent.includes('Beta'));
  assert.equal(document.body.textContent.includes('Alfa'), false);
  assert.ok(
    calls.some(
      (call) =>
        call.path.includes(`/games/${children[1]}/`) &&
        call.path.endsWith('/symbols'),
    ),
  );
  assert.ok(calls.every((call) => !call.path.includes(secret)));
  await act(async () => root.unmount());
  calls.length = 0;
  root = await render();
  assert.ok(calls[0].path.endsWith('/context'));
  assert.equal(calls[0].init.method, 'GET');
  await act(async () => root.unmount());
});

test('a wrong panel context never opens a game', async () => {
  calls.length = 0;
  globalThis.fetch = async (input) => {
    calls.push({ path: String(input) });
    return Response.json({ ...context, panelId: children[0] });
  };
  const root = await render();
  assert.ok(document.querySelector('[role=alert]'));
  assert.equal(document.querySelector('select[aria-label="Gra"]'), null);
  assert.equal(calls.length, 1);
  await act(async () => root.unmount());
});
