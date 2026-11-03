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
globalThis.React = React;
const { createRoot } = await import('react-dom/client');
const { SourceReplacementWorking } =
  await import('../src/features/cleanup/source-replacement-working.tsx');
after(() => dom.window.close());
const button = (text) =>
  [...document.querySelectorAll('button')].find(
    (node) => node.textContent === text,
  );
const click = (node) =>
  act(async () =>
    node.dispatchEvent(new MouseEvent('click', { bubbles: true })),
  );
const base = {
  gameId: 'game',
  batchId: 'batch',
  entryId: 'entry',
  revision: 4,
  phase: 'awaiting_review',
  sourceId: 'new-source',
  importJobId: 'job',
  slots: [],
  readability: [
    {
      cellId: 'cell',
      reviewItemId: 'review',
      sequenceNumber: 101,
      cellIndex: 2,
      identity: 'new-pixels',
      revision: 7,
    },
  ],
  readyToRestore: true,
};

test('restore requires actual new crop load and explicit judgment; lost response replays durable exact command after reload', async () => {
  localStorage.clear();
  const sent = [];
  let restored = false;
  const client = {
    getSourceReplacementWorking: async () => ({
      data: restored
        ? { ...base, phase: 'restored', readability: [], readyToRestore: false }
        : base,
    }),
    listGeometryCorrections: async () => ({ data: { items: [] } }),
    restoreSourceReplacementEntry: async (game, body) => {
      sent.push(body);
      if (sent.length === 1) throw new Error('lost');
      restored = true;
      return { data: { phase: 'restored' } };
    },
  };
  const render = async () => {
    const root = createRoot(document.getElementById('root'));
    await act(async () =>
      root.render(
        React.createElement(SourceReplacementWorking, {
          apiBaseUrl: 'http://localhost',
          gameId: 'game',
          batchId: 'batch',
          entryId: 'entry',
          client,
        }),
      ),
    );
    return root;
  };
  let root = await render();
  const input = document.querySelector('input[type=checkbox]');
  const img = document.querySelector('img');
  assert.equal(input.checked, false);
  assert.equal(input.disabled, true);
  assert.match(img.src, /image-review-items\/review\/assets\/cells\/2/);
  assert.match(img.src, /v=new-pixels/);
  assert.equal(button('Potwierdź czytelność i zakończ wymianę').disabled, true);
  await act(async () => img.dispatchEvent(new Event('load')));
  await click(input);
  assert.equal(
    button('Potwierdź czytelność i zakończ wymianę').disabled,
    false,
  );
  await click(button('Potwierdź czytelność i zakończ wymianę'));
  assert.equal(sent.length, 1);
  assert.deepEqual(sent[0].readability, [
    { cellId: 'cell', identity: 'new-pixels', revision: 7, readable: true },
  ]);
  assert.ok(localStorage.getItem('replacement-restore:game:batch:entry'));
  assert.doesNotMatch(
    document.body.textContent,
    /Wymiana potwierdzona na serwerze/,
  );
  await act(async () => root.unmount());
  root = await render();
  await click(button('Ponów zapisane potwierdzenie'));
  assert.deepEqual(sent[1], sent[0]);
  assert.match(document.body.textContent, /Wymiana potwierdzona na serwerze/);
  assert.equal(
    localStorage.getItem('replacement-restore:game:batch:entry'),
    null,
  );
  await act(async () => root.unmount());
});

test('partial import stays open with refresh/error states and no restoration control', async () => {
  localStorage.clear();
  let calls = 0;
  const client = {
    getSourceReplacementWorking: async () => {
      if (!calls++) throw new Error('offline');
      return {
        data: {
          ...base,
          slots: [
            {
              sequenceNumber: 101,
              status: 'pending',
              canonical: false,
              reviewItemId: null,
              pendingGeometryId: null,
            },
          ],
          readability: [],
          readyToRestore: false,
        },
      };
    },
    listGeometryCorrections: async () => ({ data: { items: [] } }),
  };
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(SourceReplacementWorking, {
        apiBaseUrl: 'http://localhost',
        gameId: 'game',
        batchId: 'batch',
        entryId: 'entry',
        client,
      }),
    ),
  );
  assert.match(
    document.querySelector('[role=alert]').textContent,
    /Odśwież stan/,
  );
  await click(button('Odśwież nowe plansze'));
  assert.match(document.body.textContent, /tego samego nowego zdjęcia/);
  assert.equal(button('Potwierdź czytelność i zakończ wymianę'), undefined);
  assert.ok(button('Plansza 101 — wymaga sprawdzenia'));
  await act(async () => root.unmount());
});

test('new source approvals use ordinary fifteen-cell command after actual crops load', async () => {
  localStorage.clear();
  const sent = [];
  const cells = Array.from({ length: 15 }, (_, cellIndex) => ({
    cellIndex,
    cropSampleId: `crop-${cellIndex}`,
    cropChecksumSha256: `sha-${cellIndex}`,
    currentSymbolCode: 'A',
    predictedSymbolCode: 'A',
  }));
  const item = {
    id: 'review',
    gameId: 'game',
    status: 'pending',
    geometryRevision: 3,
    resolutionRevision: 2,
    suggestedSequenceNumber: 101,
    sequenceNumber: 101,
    sourceWidth: 500,
    sourceHeight: 300,
    cells,
  };
  const client = {
    getSourceReplacementWorking: async () => ({
      data: {
        ...base,
        readability: [],
        readyToRestore: false,
        slots: [
          {
            sequenceNumber: 101,
            reviewItemId: 'review',
            pendingGeometryId: null,
            status: 'pending',
            canonical: false,
          },
        ],
      },
    }),
    listGeometryCorrections: async () => ({ data: { items: [] } }),
    getOperationalImageReviewItem: async () => ({ data: item }),
    listSymbols: async () => ({
      data: [{ id: 'symbol-A', code: 'A', name: 'As' }],
    }),
    resolveOperationalImageReviewItem: async (id, scope, body) => {
      sent.push(body);
      return { data: { status: 'accepted' } };
    },
  };
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(SourceReplacementWorking, {
        apiBaseUrl: 'http://localhost',
        gameId: 'game',
        batchId: 'batch',
        entryId: 'entry',
        client,
      }),
    ),
  );
  await click(button('Plansza 101 — wymaga sprawdzenia'));
  assert.equal(button('Zatwierdź sprawdzone symbole planszy').disabled, true);
  assert.equal(document.querySelectorAll('img').length, 15);
  await act(async () => {
    for (const image of document.querySelectorAll('img'))
      image.dispatchEvent(new Event('load'));
  });
  await click(button('Zatwierdź sprawdzone symbole planszy'));
  assert.equal(sent.length, 1);
  assert.equal(sent[0].action, 'accepted');
  assert.equal(sent[0].sequenceNumber, 101);
  assert.equal(sent[0].geometryRevision, 3);
  assert.equal(sent[0].expectedRevision, 2);
  assert.equal(sent[0].cells.length, 15);
  assert.equal(sent[0].cells[0].cropSampleId, 'crop-0');
  await act(async () => root.unmount());
});

test('corrupt restoration receipt is preserved and blocks a new command', async () => {
  localStorage.setItem('replacement-restore:game:batch:entry', '{broken');
  const client = {
    getSourceReplacementWorking: async () => ({ data: base }),
    listGeometryCorrections: async () => ({ data: { items: [] } }),
  };
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(SourceReplacementWorking, {
        apiBaseUrl: 'http://localhost',
        gameId: 'game',
        batchId: 'batch',
        entryId: 'entry',
        client,
      }),
    ),
  );
  await act(async () =>
    document.querySelector('img').dispatchEvent(new Event('load')),
  );
  await click(document.querySelector('input[type=checkbox]'));
  assert.equal(button('Potwierdź czytelność i zakończ wymianę').disabled, true);
  assert.equal(
    localStorage.getItem('replacement-restore:game:batch:entry'),
    '{broken',
  );
  await act(async () => root.unmount());
  localStorage.clear();
});
