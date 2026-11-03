import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { after, test } from 'node:test';
import React, { act } from 'react';
import { JSDOM } from 'jsdom';
const reactUrl = import.meta.resolve('react');
registerHooks({
  resolve(specifier, context, next) {
    return next(specifier === 'react' ? reactUrl : specifier, context);
  },
});
const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost' });
for (const name of [
  'window',
  'document',
  'HTMLElement',
  'HTMLInputElement',
  'Event',
  'MouseEvent',
  'localStorage',
])
  Object.defineProperty(globalThis, name, {
    configurable: true,
    value: dom.window[name],
  });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import('react-dom/client');
const { SourceRetirementActions } =
  await import('../src/features/cleanup/source-retirement-actions.tsx');
after(() => dom.window.close());
const find = (text) =>
  [...document.querySelectorAll('button')].find((node) =>
    node.textContent.startsWith(text),
  );
const click = async (node) =>
  act(async () => {
    node.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  });
const batch = '11111111-1111-4111-8111-111111111111',
  entry = '22222222-2222-4222-8222-222222222222';
const manifest = {
  id: batch,
  entries: [
    {
      id: entry,
      phase: 'planned',
      revision: 1,
      sourceIds: ['source', 'alias'],
      sourceSha256: 'b'.repeat(64),
      sequenceNumbers: [1, 2, 3],
    },
  ],
};

test('confirmation and reload retry keep the exact photo command after a lost response', async () => {
  localStorage.clear();
  const commands = [];
  const refreshed = [];
  const api = {
    previewSourceRetirement: async () => ({
      data: {
        batchId: batch,
        entryId: entry,
        revision: 1,
        previewToken: 'a'.repeat(64),
        entry: manifest.entries[0],
      },
    }),
    executeSourceRetirement: async (game, command) => {
      commands.push(command);
      if (commands.length === 1) throw new Error('lost response');
      return { data: { phase: 'gap_open' } };
    },
  };
  let root = createRoot(document.getElementById('root'));
  const render = () =>
    root.render(
      React.createElement(SourceRetirementActions, {
        gameId: 'game',
        manifest,
        api,
        refresh: async (id) => refreshed.push(id),
      }),
    );
  await act(async () => render());
  await click(find('Świeży podgląd'));
  assert.equal(find('Wycofaj całe zdjęcie').disabled, true);
  await click(document.querySelector('input[type=checkbox]'));
  await click(find('Wycofaj całe zdjęcie'));
  assert.equal(commands.length, 1);
  assert.equal(commands[0].confirmed, true);
  await act(() => root.unmount());
  root = createRoot(document.getElementById('root'));
  await act(async () => render());
  await click(find('Ponów zapisane polecenie'));
  assert.deepEqual(commands[0], commands[1]);
  assert.deepEqual(refreshed, [batch]);
  assert.equal(localStorage.getItem('source-retirement-command:game'), null);
  await act(() => root.unmount());
});

test('corrupt persisted command fails closed and planned has no gap export selection', async () => {
  localStorage.setItem('source-retirement-command:game', '{"bad":true}');
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(SourceRetirementActions, {
        gameId: 'game',
        manifest,
        api: {},
        refresh: async () => {},
      }),
    ),
  );
  assert.equal(find('Świeży podgląd').disabled, true);
  assert.equal(find('Pobierz wybrane luki').disabled, true);
  assert.match(
    document.querySelector('[role=alert]').textContent,
    /zablokowana/,
  );
  await act(() => root.unmount());
});
