import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
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
])
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
dom.window.HTMLDialogElement.prototype.showModal = function () {
  this.setAttribute('open', '');
};
dom.window.HTMLDialogElement.prototype.close = function () {
  this.removeAttribute('open');
};
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import('react-dom/client');
const { BoardSearchBoardLinesModal } =
  await import('../src/board-search-board-lines-modal.tsx');
after(() => dom.window.close());
async function click(node) {
  assert.ok(node);
  await act(async () =>
    node.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })),
  );
}
async function eventually(predicate) {
  for (let i = 0; i < 40; i++) {
    if (predicate()) return;
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 2));
    });
  }
  assert.fail('Missing UI state');
}
const button = (text) =>
  [...document.querySelectorAll('button')].find(
    (node) => node.textContent.trim() === text,
  );

test('opaque public cells use the online port and recover an uncertain write without losing the edit', async () => {
  let pending = false;
  let saved = false;
  let reads = 0;
  const writes = [];
  const closed = [];
  const symbols = ['A', 'B'].map((code, displayOrder) => ({
    id: code,
    code,
    name: code,
    status: 'active',
    displayOrder,
    mobileCode: displayOrder + 1,
    imagePath: null,
  }));
  const api = {
    getBoardSearchBoardDetail: async () => {
      reads++;
      return {
        data: {
          gameId: 'shared',
          sequenceNumber: 100001,
          boardStatus: 'accepted',
          boardChecksumSha256: 'c'.repeat(64),
          dataSource: 'operational_review',
          documentStale: false,
          view: null,
          rules: { rulesVersionId: 'rules', spinCost: 20 },
          matches: [],
          payoutCredits: 0,
          payoutKind: 'none',
          symbolCodes: Array(15).fill(saved ? 'B' : 'A'),
          cells: Array.from({ length: 15 }, (_, cellIndex) => ({
            cellIndex,
            assignedSymbolCode: saved ? 'B' : 'A',
            qualityIssue: null,
            reviewState: 'approved',
            cellVersion: (saved ? 'b' : 'a').repeat(64),
          })),
        },
      };
    },
    boardSearchBoardViewUrl: () => '',
    symbolImageAssetUrl: () => '',
    correctBoardSearchCell: async (...args) => {
      writes.push(args);
      pending = true;
      throw new Error('Lost response');
    },
    hasPendingBoardSearchCell: () => pending,
    retryBoardSearchCell: async () => {
      pending = false;
      saved = true;
      return {
        data: {
          saved: true,
          changed: true,
          sequenceNumber: 100001,
          cellIndex: 0,
          cellVersion: 'b'.repeat(64),
        },
      };
    },
  };
  const context = {
    startSequenceNumber: 1,
    spinCount: 100000,
    stakeGrosze: 500,
  };
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(BoardSearchBoardLinesModal, {
        api,
        gameId: 'shared',
        sequenceNumber: 100001,
        row: null,
        rulesVersionId: null,
        symbols,
        formatAmount: String,
        onClose: (edited) => closed.push(edited),
        onRecalculate: () => {},
        startInEditMode: true,
        correctionContext: context,
      }),
    ),
  );
  await eventually(() => document.querySelector('.boardSearchBoardCellTarget'));
  await click(document.querySelector('.boardSearchBoardCellTarget'));
  await click(document.querySelector('button[title="B"]'));
  await eventually(() => button('Sprawdź ostatni zapis'));
  assert.deepEqual(writes, [
    [
      'shared',
      100001,
      0,
      {
        ...context,
        expectedCellVersion: 'a'.repeat(64),
        action: 'reassign',
        targetSymbolCode: 'B',
      },
    ],
  ]);
  assert.equal(reads, 1, 'an uncertain write retains the exact observed cell');
  await click(button('Sprawdź ostatni zapis'));
  await eventually(
    () =>
      reads === 2 && document.body.textContent.includes('Zapis potwierdzony'),
  );
  await click(button('Zamknij'));
  assert.deepEqual(closed, [true]);
  await act(async () => root.unmount());
});
