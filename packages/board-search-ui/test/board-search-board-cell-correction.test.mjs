import assert from 'node:assert/strict';
import test from 'node:test';

import {
  applyBoardCellCorrection,
  boardCellCorrectionPalette,
  boardCellCorrectionRequest,
} from '../src/board-search-board-cell-correction.ts';

const symbols = [
  {
    code: 'arbuz',
    displayOrder: 2,
    id: 'id-arbuz',
    mobileCode: 3,
    name: 'Arbuz',
    status: 'active',
  },
  {
    code: 'seven',
    displayOrder: 1,
    id: 'id-seven',
    mobileCode: 7,
    name: '7',
    status: 'active',
  },
  {
    code: 'old',
    displayOrder: 0,
    id: 'id-old',
    mobileCode: 9,
    name: 'Stary',
    status: 'archived',
  },
];

const cell = {
  assignedSymbolCode: 'arbuz',
  cellIndex: 13,
  cellReviewId: 'cell-13',
  cropChecksumSha256: 'b'.repeat(64),
  cropSampleId: 'a'.repeat(64),
  geometryRevision: 2,
  qualityIssue: null,
  reviewState: 'pending',
  revision: 4,
};

const expected = {
  expectedCropChecksumSha256: 'b'.repeat(64),
  expectedCropSampleId: 'a'.repeat(64),
  expectedGeometryRevision: 2,
  expectedRevision: 4,
};

test('another symbol rewrites the cell, the assigned one confirms it', () => {
  // Operator example: the "7" read as Arbuz on a winning line.
  assert.deepEqual(
    boardCellCorrectionRequest(
      cell,
      { kind: 'symbol', symbolCode: 'seven' },
      symbols,
    ),
    { ...expected, action: 'reassign', targetSymbolId: 'id-seven' },
  );
  assert.deepEqual(
    boardCellCorrectionRequest(
      cell,
      { kind: 'symbol', symbolCode: 'arbuz' },
      symbols,
    ),
    { ...expected, action: 'approve' },
  );
});

test('unreadable and bad grid map to their existing decisions', () => {
  assert.deepEqual(
    boardCellCorrectionRequest(cell, { kind: 'unreadable' }, symbols),
    {
      ...expected,
      action: 'mark_unreadable',
    },
  );
  assert.deepEqual(
    boardCellCorrectionRequest(cell, { kind: 'grid_issue' }, symbols),
    {
      ...expected,
      action: 'mark_grid_issue',
    },
  );
});

test('an unknown symbol is refused before any request', async () => {
  assert.equal(
    boardCellCorrectionRequest(
      cell,
      { kind: 'symbol', symbolCode: 'nope' },
      symbols,
    ),
    null,
  );
  let calls = 0;
  const result = await applyBoardCellCorrection(
    {
      applySymbolCellReviewDecision: async () => {
        calls += 1;
        return { data: {} };
      },
    },
    'game',
    cell,
    { kind: 'symbol', symbolCode: 'nope' },
    symbols,
  );
  assert.equal(result.ok, false);
  assert.equal(result.conflict, false);
  assert.equal(calls, 0);
});

test('the palette offers active symbols in catalogue order', () => {
  assert.deepEqual(
    boardCellCorrectionPalette(symbols).map((symbol) => symbol.code),
    ['seven', 'arbuz'],
  );
});

test('an API conflict is reported, not swallowed', async () => {
  const result = await applyBoardCellCorrection(
    {
      applySymbolCellReviewDecision: async () => ({
        error: {
          code: 'SYMBOL_CELL_REVIEW_REVISION_CONFLICT',
          message: 'changed',
        },
      }),
    },
    'game',
    cell,
    { kind: 'symbol', symbolCode: 'seven' },
    symbols,
  );
  assert.equal(result.ok, false);
  assert.equal(result.conflict, true);
});
