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
const dom = new JSDOM('<!doctype html><div id="root"></div>', {
  url: 'https://localhost/sharing',
});
for (const name of [
  'window',
  'document',
  'HTMLElement',
  'HTMLInputElement',
  'HTMLSelectElement',
  'Element',
  'Event',
  'MouseEvent',
  'navigator',
  'localStorage',
])
  Object.defineProperty(globalThis, name, {
    configurable: true,
    value: dom.window[name],
  });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import('react-dom/client');
const { BoardSearchSharingWorkspace } =
  await import('../src/features/sharing/board-search-sharing-workspace.tsx');
after(() => dom.window.close());
const ids = [
  '11111111-1111-4111-8111-111111111111',
  '22222222-2222-4222-8222-222222222222',
];
const panelId = '33333333-3333-4333-8333-333333333333';
const expiresAt = new Date(Date.now() + 3600000).toISOString();
const linkKey = 'a'.repeat(43);
const games = ids.map((id, index) => ({
  id,
  name: ['777', 'Mumie'][index],
  status: 'active',
}));
const panel = {
  panelId,
  label: 'Odbiorca',
  status: 'active',
  createdAt: new Date().toISOString(),
  expiresAt,
  ready: true,
  shareUrl: `https://old.trycloudflare.com/board-search-panel?share=${panelId}`,
  games: games.map((game) => ({
    gameId: game.id,
    gameName: game.name,
    sessionId: game.id,
  })),
};
const button = (label) =>
  [...document.querySelectorAll('button')].find(
    (node) => node.textContent.trim() === label,
  );
async function click(node) {
  assert.ok(node);
  await act(async () => node.click());
}
async function settle() {
  await act(async () => new Promise((r) => setTimeout(r, 0)));
}
async function render(client) {
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(BoardSearchSharingWorkspace, {
        client,
        onReplay() {},
      }),
    ),
  );
  await settle();
  return root;
}

test('selects only available games, creates one code-free link, restores a new tunnel URL and stops the whole panel', async () => {
  dom.window.localStorage.clear();
  let panels = [],
    creates = [],
    logs = [],
    stops = [];
  const client = {
    listGames: async () => ({
      data: [
        ...games,
        { id: 'archived', name: 'Archiwum', status: 'archived' },
      ],
    }),
    listBoardSearchPanels: async () => ({ data: { panels } }),
    createBoardSearchPanel: async (body) => {
      creates.push(body);
      panels = [panel];
      return { data: { panel, linkKey } };
    },
    revokeBoardSearchPanel: async (id) => {
      stops.push(id);
      panels = [
        { ...panels[0], status: 'revoked', ready: false, shareUrl: null },
      ];
      return { data: panels[0] };
    },
    listSymbols: async () => ({ data: [] }),
    listBoardSearchShareQueries: async (id) => {
      logs.push(id);
      return { data: { entries: [], nextCursor: null } };
    },
    listBoardSearchShareCorrections: async () => ({
      data: { entries: [], totalCount: 0, pendingCount: 0, nextCursor: null },
    }),
  };
  let root = await render(client);
  const checkboxes = [...document.querySelectorAll('input[type=checkbox]')];
  assert.equal(checkboxes.length, 2);
  assert.equal(button('Utwórz link').disabled, true);
  await click(checkboxes[0]);
  await click(checkboxes[1]);
  await act(async () => {
    const select = document.querySelector('fieldset select');
    select.value = '4320';
    select.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
  });
  await click(button('Utwórz link'));
  await settle();
  assert.deepEqual(creates, [
    { gameIds: ids, label: null, lifetimeMinutes: 4320 },
  ]);
  assert.match(
    document.querySelector('input[aria-label="Link do panelu"]').value,
    /#key=a{43}$/,
  );
  assert.equal(document.body.textContent.includes('kod dostępu'), false);
  const logSelect = document.querySelector(
    'select[aria-label^="Dziennik gry"]',
  );
  await act(async () => {
    logSelect.value = ids[1];
    logSelect.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
  });
  await settle();
  assert.deepEqual(logs, [ids[1]]);
  await act(async () => root.unmount());
  panels = [{ ...panel, shareUrl: panel.shareUrl.replace('old.', 'new.') }];
  root = await render(client);
  assert.match(
    document.querySelector('input[aria-label="Link do panelu"]').value,
    /^https:\/\/new\.trycloudflare\.com/,
  );
  await click(button('Zatrzymaj link'));
  await click(button('Potwierdź zatrzymanie'));
  await settle();
  assert.deepEqual(stops, [panelId]);
  assert.equal(
    document.querySelector('input[aria-label="Link do panelu"]'),
    null,
  );
  assert.equal(
    dom.window.localStorage.getItem(
      'game-predictor:board-search-panel-keys:v1',
    ),
    '{}',
  );
  await act(async () => root.unmount());
});

test('a failed create preserves the chosen games and displays a retryable error', async () => {
  const client = {
    listGames: async () => ({ data: games }),
    listBoardSearchPanels: async () => ({ data: { panels: [] } }),
    createBoardSearchPanel: async () => ({
      error: { code: 'BOARD_SEARCH_SHARE_ACTIVE_LIMIT' },
    }),
  };
  const root = await render(client);
  await click(document.querySelector('input[type=checkbox]'));
  await click(button('Utwórz link'));
  await settle();
  assert.ok(document.querySelector('[role=alert]'));
  assert.equal(document.querySelector('input[type=checkbox]').checked, true);
  assert.equal(button('Utwórz link').disabled, false);
  await act(async () => root.unmount());
});
