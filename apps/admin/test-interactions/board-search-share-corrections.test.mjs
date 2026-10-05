import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import { register } from 'node:module';
register('./shared-react-loader.mjs', import.meta.url);

const dom = new JSDOM('<!doctype html><div id="root"></div>', {
  url: 'http://localhost',
});
for (const key of [
  'window',
  'document',
  'HTMLElement',
  'Element',
  'Event',
  'MouseEvent',
  'navigator',
]) {
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
}
dom.window.HTMLDialogElement.prototype.showModal = function () {
  this.setAttribute('open', '');
};
dom.window.HTMLDialogElement.prototype.close = function () {
  this.removeAttribute('open');
};
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.React = React;
const { createRoot } = await import('react-dom/client');
const { BoardSearchShareCorrections } =
  await import('../src/features/board-search/board-search-share-corrections.tsx');
after(() => dom.window.close());
const symbols = ['A', 'B'].map((code, index) => ({
  id: code,
  code,
  name: code === 'A' ? 'Wiśnia' : 'Siódemka',
  status: 'active',
  displayOrder: index,
  mobileCode: index + 1,
  imagePath: null,
}));

function button(text) {
  return [...document.querySelectorAll('button')].find(
    (node) => node.textContent.trim() === text,
  );
}
async function click(node) {
  assert.ok(node);
  await act(async () =>
    node.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })),
  );
}
async function eventually(predicate) {
  for (let attempt = 0; attempt < 50; attempt++) {
    if (predicate()) return;
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 2));
    });
  }
  assert.fail('Expected UI state did not arrive');
}

test('queue is lazy, close leaves pending, local correction works and review checks the observed revision', async () => {
  let pending = true;
  let revision = 1;
  let version = 'a'.repeat(64);
  let assigned = 'B';
  let boardReads = 0;
  const writes = [];
  const reviews = [];
  const board = () => ({
    sequenceNumber: 100001,
    revision,
    pending,
    changedCellCount: 1,
    lastChangedAt: '2026-10-05T12:00:00Z',
    lastEventId: 'event',
    stakeGrosze: 500,
    startSequenceNumber: 1,
  });
  const client = {
    listBoardSearchShareCorrections: async () => ({
      data: {
        entries: pending ? [board()] : [],
        totalCount: 1,
        pendingCount: pending ? 1 : 0,
        nextCursor: null,
      },
    }),
    getBoardSearchShareCorrection: async () => ({
      data: {
        board: board(),
        boardVersion: version,
        nextCursor: null,
        changes: [
          {
            id: 'change',
            cellIndex: 0,
            beforeSymbolCode: 'A',
            afterSymbolCode: 'B',
            beforeQualityIssue: null,
            afterQualityIssue: null,
            beforeReviewState: 'approved',
            afterReviewState: 'approved',
            occurredAt: '2026-10-05T12:00:00Z',
          },
        ],
      },
    }),
    reviewBoardSearchShareCorrection: async (_sid, _sequence, body) => {
      reviews.push(body);
      if (
        body.expectedRevision !== revision ||
        body.expectedBoardVersion !== version
      )
        return {
          error: {
            code: 'BOARD_SEARCH_SHARE_CORRECTION_CONFLICT',
            message: 'Nowa poprawka',
          },
        };
      pending = false;
      return { data: board() };
    },
    getBoardSearchBoardDetail: async () => {
      boardReads++;
      return {
        data: {
          gameId: 'game',
          sequenceNumber: 100001,
          boardStatus: 'accepted',
          dataSource: 'operational_review',
          documentStale: false,
          view: null,
          boardChecksumSha256: 'c'.repeat(64),
          rules: { rulesVersionId: 'rules', spinCost: 20 },
          matches: [],
          payoutCredits: 0,
          payoutKind: 'none',
          symbolCodes: [assigned, ...Array(14).fill('A')],
          cells: Array.from({ length: 15 }, (_, cellIndex) => ({
            cellIndex,
            cellReviewId: `cell-${cellIndex}`,
            assignedSymbolCode: cellIndex === 0 ? assigned : 'A',
            cropChecksumSha256: 'd'.repeat(64),
            cropSampleId: 'e'.repeat(64),
            geometryRevision: 1,
            revision: 1,
          })),
        },
      };
    },
    boardSearchBoardViewUrl: () => '',
    symbolImageAssetUrl: () => '',
    applySymbolCellReviewDecision: async (_game, cellId, body) => {
      writes.push({ cellId, body });
      assigned = 'A';
      version = 'b'.repeat(64);
      return { data: {} };
    },
  };
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(BoardSearchShareCorrections, {
        client,
        gameId: 'game',
        sessionId: 'share',
        symbols,
      }),
    ),
  );
  await eventually(() => button('Sprawdź poprawki'));
  assert.equal(
    boardReads,
    0,
    'listing does not calculate ranges or fetch board data',
  );
  assert.match(document.body.textContent, /dalsza plansza od #1/);
  await click(button('Sprawdź poprawki'));
  await eventually(
    () =>
      document.querySelectorAll('.boardSearchBoardCellTarget').length === 15,
  );
  assert.ok(button('Zakończ poprawianie'), 'editor opens in correction mode');
  assert.match(
    document.querySelector('dialog').textContent,
    /Wiśnia.*Siódemka/,
  );
  assert.ok(document.querySelector('polygon[aria-label="Zmienione pole 1"]'));
  await click(button('Zamknij'));
  assert.equal(reviews.length, 0);
  await click(button('Sprawdź poprawki'));
  await eventually(
    () =>
      document.querySelectorAll('.boardSearchBoardCellTarget').length === 15,
  );
  await click(document.querySelector('.boardSearchBoardCellTarget'));
  await click(document.querySelector('button[title="Wiśnia"]'));
  await eventually(
    () => writes.length === 1 && !button('Oznacz jako przejrzane').disabled,
  );
  assert.equal(writes[0].cellId, 'cell-0');
  assert.equal(writes[0].body.targetSymbolId, 'A');
  revision = 2;
  version = 'c'.repeat(64);
  await click(button('Oznacz jako przejrzane'));
  await eventually(() => document.querySelector('[role="alert"]'));
  assert.deepEqual(reviews[0], {
    expectedRevision: 1,
    expectedBoardVersion: 'b'.repeat(64),
  });
  assert.equal(pending, true);
  assert.equal(button('Oznacz jako przejrzane').disabled, true);
  await click(button('Odśwież zmiany'));
  await eventually(
    () =>
      button('Oznacz jako przejrzane') &&
      !button('Oznacz jako przejrzane').disabled,
  );
  await click(button('Oznacz jako przejrzane'));
  await eventually(() => document.querySelector('dialog') === null);
  assert.deepEqual(reviews[1], {
    expectedRevision: 2,
    expectedBoardVersion: 'c'.repeat(64),
  });
  assert.equal(pending, false);
  await act(async () => root.unmount());
});
