import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import React, { act } from 'react';
import { JSDOM } from 'jsdom';
import { SourceReplacementPanel } from '../src/features/cleanup/source-replacement-panel.tsx';
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
globalThis.React = React;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import('react-dom/client');
after(() => dom.window.close());
const game = '11111111-1111-4111-8111-111111111111',
  batch = '22222222-2222-4222-8222-222222222222',
  entry = '33333333-3333-4333-8333-333333333333',
  source = '44444444-4444-4444-8444-444444444444';
const numbers = [1, 2, 3, 4, 5, 6, 7, 8, 9];
const planned = {
  mode: 'replace_delete_source',
  gameId: game,
  id: batch,
  previewToken: 'a'.repeat(64),
  selectedSourceIds: [source],
  status: 'planned',
  revision: 1,
  entries: [
    {
      id: entry,
      phase: 'planned',
      revision: 1,
      sourceIds: [source],
      sequenceNumbers: numbers,
      reasons: [],
      boards: [],
      dependencies: {},
      blockers: [],
      retainedMetadata: { quality: 2 },
    },
  ],
};
const preview = {
  gameId: game,
  batchId: batch,
  entryId: entry,
  revision: 1,
  previewToken: 'b'.repeat(64),
  sourceIds: [source],
  sequenceNumbers: numbers,
  fileCount: 4,
  bytesToDelete: 4096,
  sharedFileCount: 2,
  missingFileCount: 1,
  retainedMetadata: { quality: 2 },
  recordCounts: { boards: 9, cells: 135 },
};
const command = {
  mode: 'replace_delete_source',
  action: 'purge',
  batchId: batch,
  entryId: entry,
  expectedRevision: 1,
  previewToken: preview.previewToken,
  idempotencyKey: '55555555-5555-4555-8555-555555555555',
  confirmed: true,
};
const purge = (command, fileStatus) => ({
  operationType: 'source_replacement_purge',
  sourceIds: [source],
  fileCount: 4,
  bytesToDelete: 4096,
  sharedFileCount: 2,
  missingFileCount: 1,
  retainedMetadata: { quality: 2 },
  deletedRecords: { boards: 9, cells: 135 },
  command,
  fileStatus,
  deletedBytes: fileStatus === 'finalized' ? 4096 : 0,
});
const withPurge = (body, status) => ({
  ...planned,
  entries: [
    {
      ...planned.entries[0],
      phase: 'gap_open',
      revision: 2,
      purge: purge(body, status),
    },
  ],
});
const button = (text) =>
  [...document.querySelectorAll('button')].find(
    (node) => node.textContent === text,
  );
const click = (node) =>
  act(async () =>
    node.dispatchEvent(new MouseEvent('click', { bubbles: true })),
  );
async function mount(client) {
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(SourceReplacementPanel, {
        gameId: game,
        apiBaseUrl: 'http://localhost',
        client,
      }),
    ),
  );
  await click(button(`${batch} — planned`));
  return root;
}
function api(get, extra = {}) {
  return {
    listSourceReplacementCandidates: async () => ({
      data: { items: [], nextOffset: null },
    }),
    listSourceReplacementBatches: async () => ({
      data: [{ id: batch, status: 'planned' }],
    }),
    getSourceReplacementBatch: async () => ({ data: get() }),
    exportSourceReplacementUrl: () => '/manifest',
    ...extra,
  };
}

test('physical purge needs fresh preview and explicit whole-photo confirmation; server receipt recovers after local storage loss', async () => {
  localStorage.clear();
  let state = planned;
  const sent = [],
    previews = [];
  const client = api(() => state, {
    previewSourcePurge: async (g, body) => {
      previews.push(body);
      return { data: preview };
    },
    executeSourcePurge: async (g, body) => {
      sent.push(body);
      state = withPurge(body, sent.length === 1 ? 'pending' : 'finalized');
      if (sent.length === 1) throw new Error('lost response');
      return {
        data: {
          gameId: game,
          batchId: batch,
          entryId: entry,
          phase: 'gap_open',
          revision: 2,
          scopeDigest: 'scope',
          purge: state.entries[0].purge,
        },
      };
    },
  });
  let root = await mount(client);
  assert.equal(button('Usuń całe zdjęcie i pozostaw luki'), undefined);
  await click(button(`Świeży podgląd usunięcia ${numbers.join(', ')}`));
  assert.deepEqual(previews, [
    {
      mode: 'replace_delete_source',
      action: 'purge',
      batchId: batch,
      entryId: entry,
      expectedRevision: 1,
    },
  ]);
  assert.equal(button('Usuń całe zdjęcie i pozostaw luki').disabled, true);
  assert.match(document.body.textContent, /dane 9 plansz/);
  assert.match(document.body.textContent, /Współdzielone pliki pozostaną: 2/);
  assert.equal(sent.length, 0);
  await click(document.querySelector('fieldset input[type=checkbox]'));
  await click(button('Usuń całe zdjęcie i pozostaw luki'));
  assert.equal(sent.length, 1);
  assert.equal(sent[0].action, 'purge');
  assert.equal(sent[0].confirmed, true);
  assert.equal(sent[0].previewToken, preview.previewToken);
  assert.ok(localStorage.getItem(`source-replacement-purge:${game}:${batch}`));
  await act(async () => root.unmount());
  localStorage.clear();
  root = await mount(client);
  assert.match(
    document.body.textContent,
    /usuwanie plików jeszcze niezakończone/,
  );
  assert.match(document.body.textContent, /Potwierdzone usunięte bajty: 0 B/);
  assert.doesNotMatch(document.body.textContent, /Usuwanie plików zakończone/);
  await click(button(`Dokończ zapisane usunięcie ${numbers.join(', ')}`));
  assert.deepEqual(sent[1], sent[0]);
  assert.match(document.body.textContent, /Usuwanie plików zakończone/);
  assert.match(
    document.body.textContent,
    /Potwierdzone usunięte bajty: 4\s?096 B/,
  );
  assert.match(document.body.textContent, /Uzupełnij luki z manifestu/);
  assert.equal(
    button(`Świeży podgląd usunięcia ${numbers.join(', ')}`),
    undefined,
  );
  await act(async () => root.unmount());
});

test('recovery required retains proof and never offers another physical command', async () => {
  localStorage.clear();
  const sent = [];
  const state = withPurge(command, 'recovery_required');
  const root = await mount(
    api(() => state, {
      executeSourcePurge: async (g, body) => {
        sent.push(body);
        return {
          error: {
            code: 'SOURCE_REPLACEMENT_PURGE_RECOVERY_REQUIRED',
            message: 'conflict',
          },
          response: { status: 409 },
        };
      },
    }),
  );
  assert.match(
    document.body.textContent,
    /plik zmienił się lub jest współdzielony/,
  );
  assert.equal(
    button(`Świeży podgląd usunięcia ${numbers.join(', ')}`),
    undefined,
  );
  await click(button(`Dokończ zapisane usunięcie ${numbers.join(', ')}`));
  await click(button('Ponów zapisane polecenie usunięcia'));
  assert.deepEqual(sent, [command, command]);
  assert.match(document.body.textContent, /Zachowaj zapisane polecenie/);
  await act(async () => root.unmount());
});

test('unfinished import points to the existing completion workflow before any delete', async () => {
  localStorage.clear();
  const root = await mount(
    api(() => planned, {
      previewSourcePurge: async () => ({
        error: {
          code: 'SOURCE_REPLACEMENT_PURGE_IMPORT_UNFINISHED',
          message: 'busy',
        },
      }),
      executeSourcePurge: async () => assert.fail('must not delete'),
    }),
  );
  await click(button(`Świeży podgląd usunięcia ${numbers.join(', ')}`));
  assert.match(document.body.textContent, /otwórz „Import plansz”/);
  assert.match(document.body.textContent, /zakończ import i jego weryfikację/);
  assert.equal(button('Usuń całe zdjęcie i pozostaw luki'), undefined);
  await act(async () => root.unmount());
});

test('a stored legacy manifest still uses history-preserving retirement', async () => {
  localStorage.clear();
  const state = { ...planned, mode: 'replace_preserve_history' };
  const root = await mount(api(() => state));
  assert.ok(button(`Świeży podgląd wycofania ${numbers.join(', ')}`));
  assert.equal(
    button(`Świeży podgląd usunięcia ${numbers.join(', ')}`),
    undefined,
  );
  await act(async () => root.unmount());
});
