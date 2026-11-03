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
]) {
  Object.defineProperty(globalThis, name, {
    configurable: true,
    value: dom.window[name],
  });
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import('react-dom/client');
const { SourceReplacementPanel } =
  await import('../src/features/cleanup/source-replacement-panel.tsx');
after(() => dom.window.close());
const button = (text) =>
  [...document.querySelectorAll('button')].find(
    (node) => node.textContent === text,
  );
const click = async (node) =>
  act(async () => {
    node.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  });

test('whole source preview saves only planned, lost response retries original key after reload', async () => {
  localStorage.clear();
  const commands = [];
  const manifest = {
    mode: 'replace_preserve_history',
    selectedSourceIds: ['11111111-1111-4111-8111-111111111111'],
    previewToken: 'a'.repeat(64),
    status: 'preview',
    revision: 0,
    entries: [
      {
        sourceIds: ['11111111-1111-4111-8111-111111111111', 'alias'],
        sequenceNumbers: [8, 9],
        reasons: [],
        boards: [],
        dependencies: {},
        blockers: [],
      },
    ],
  };
  const client = {
    listSourceReplacementCandidates: async () => ({
      data: {
        items: [
          {
            id: '11111111-1111-4111-8111-111111111111',
            relativePath: 'seq_8-9.jpg',
            firstSequence: 8,
            lastSequence: 9,
          },
        ],
        nextOffset: null,
      },
    }),
    listSourceReplacementBatches: async () => ({ data: [] }),
    previewSourceReplacement: async (game, body) => {
      assert.deepEqual(body.sourceIds, [
        '11111111-1111-4111-8111-111111111111',
      ]);
      return { data: manifest };
    },
    planSourceReplacement: async (game, body) => {
      commands.push(body);
      if (commands.length === 1) throw new Error('lost response');
      return {
        data: { ...manifest, id: 'batch', status: 'planned', revision: 1 },
      };
    },
    exportSourceReplacementUrl: (game, id, format) =>
      `/board-sources/${id}/export?format=${format}`,
  };
  let root = createRoot(document.getElementById('root'));
  const render = () =>
    root.render(
      React.createElement(SourceReplacementPanel, {
        gameId: 'game',
        apiBaseUrl: 'http://localhost',
        client,
      }),
    );
  await act(async () => render());
  await click(document.querySelector('input'));
  await click(button('Podgląd całych zdjęć'));
  assert.match(
    document.body.textContent,
    /11111111-1111-4111-8111-111111111111, alias/,
  );
  await click(button('Zapisz plan wymiany'));
  assert.equal(commands.length, 1);
  assert.ok(localStorage.getItem('source-replacement-plan:game'));
  await act(async () => root.unmount());
  root = createRoot(document.getElementById('root'));
  await act(async () => render());
  await click(button('Ponów zapis planu'));
  assert.deepEqual(commands[1], commands[0]);
  assert.equal(commands[0].expectedRevision, 0);
  assert.equal(localStorage.getItem('source-replacement-plan:game'), null);
  assert.match(document.body.textContent, /Zdjęcia nadal są aktywne/);
  assert.equal(document.querySelectorAll('a').length, 2);
  await act(async () => root.unmount());
});

test('corrupt saved command blocks new writes instead of overwriting recovery evidence', async () => {
  localStorage.setItem('source-replacement-plan:game', '{corrupt');
  const root = createRoot(document.getElementById('root'));
  const client = {
    listSourceReplacementCandidates: async () => ({
      data: { items: [], nextOffset: null },
    }),
    listSourceReplacementBatches: async () => ({ data: [] }),
  };
  await act(async () =>
    root.render(
      React.createElement(SourceReplacementPanel, {
        gameId: 'game',
        apiBaseUrl: 'http://localhost',
        client,
      }),
    ),
  );
  assert.match(document.body.textContent, /Nie można odczytać/);
  assert.equal(button('Podgląd całych zdjęć').disabled, true);
  assert.equal(
    localStorage.getItem('source-replacement-plan:game'),
    '{corrupt',
  );
  await act(async () => root.unmount());
});
