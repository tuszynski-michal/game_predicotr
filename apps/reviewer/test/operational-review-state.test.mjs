import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildOperationalReviewResolutionCommand,
  buildOperationalReviewGeometryCommand,
  buildOperationalReviewGeometryPreviewCommand,
  buildOperationalReviewSymbolShortcuts,
  formatOperationalConfidence,
  isOperationalReviewDraftChangedFromCurrent,
  isOperationalReviewTypingTarget,
  operationalReviewAssetUrl,
  operationalReviewKeyboardAction,
  operationalReviewGeometryCorners,
  operationalReviewResolutionAction,
  operationalReviewSequence,
  operationalReviewStatusLabel,
  operationalReviewSymbolForKey,
  updateOperationalReviewCounts,
} from '../src/features/operational-reviews/operational-review-state.ts';

function symbol(index, status = 'active') {
  return {
    code: `symbol-${index}`,
    displayOrder: index,
    gameId: 'game-1',
    id: `id-${index}`,
    imagePath: null,
    isWildcard: false,
    mobileCode: index,
    name: `Symbol ${index}`,
    status,
  };
}

function reviewItem() {
  return {
    cells: Array.from({ length: 15 }, (_, cellIndex) => ({
      alternatives: [],
      cellIndex,
      columnIndex: cellIndex % 5,
      confidence: 0.9,
      cropChecksumSha256: `${cellIndex}`.padStart(64, '0'),
      cropSampleId: `sample-${cellIndex}`,
      currentSymbolCode: 'symbol-1',
      observationId: `observation-${cellIndex}`,
      predictedSymbolCode: 'symbol-1',
      rowIndex: Math.floor(cellIndex / 5),
    })),
    gameId: 'game-1',
    geometryRevision: 2,
    id: 'review-1',
    importJobId: 'job-1',
    resolutionRevision: 3,
    sequenceNumber: null,
    suggestedSequenceNumber: 29,
  };
}

test('builds scope-bound asset URLs and validates cell indexes', () => {
  const url = new URL(
    operationalReviewAssetUrl(
      'http://127.0.0.1:8000',
      { gameId: 'game one', importJobId: 'job/one' },
      'item/one',
      'cell',
      14,
    ),
  );
  assert.equal(
    url.pathname,
    '/api/v1/admin/image-review-items/item%2Fone/assets/cells/14',
  );
  assert.equal(url.searchParams.get('gameId'), 'game one');
  assert.equal(url.searchParams.get('importJobId'), 'job/one');
  assert.throws(
    () =>
      operationalReviewAssetUrl(
        'http://127.0.0.1:8000',
        { gameId: 'game', importJobId: 'job' },
        'item',
        'cell',
        15,
      ),
    /between 0 and 14/,
  );
});

test('prefers accepted sequence and formats textual status and confidence', () => {
  assert.equal(
    operationalReviewSequence({
      sequenceNumber: 92,
      suggestedSequenceNumber: 91,
    }),
    92,
  );
  assert.equal(
    operationalReviewSequence({
      sequenceNumber: null,
      suggestedSequenceNumber: 91,
    }),
    91,
  );
  assert.equal(operationalReviewStatusLabel('corrected'), 'Poprawiona');
  assert.equal(
    operationalReviewStatusLabel('future'),
    'Nieznany status: future',
  );
  assert.equal(formatOperationalConfidence(0.875), '87,5%');
});

test('maps active symbols through digits and then QWERTY in stable order', () => {
  const symbols = [
    symbol(12),
    symbol(11, 'archived'),
    ...Array.from({ length: 10 }, (_, index) => symbol(index + 1)),
  ];
  const shortcuts = buildOperationalReviewSymbolShortcuts(symbols);
  assert.deepEqual(
    shortcuts.slice(0, 11).map(({ key, symbol: value }) => [key, value.code]),
    [
      ['1', 'symbol-1'],
      ['2', 'symbol-2'],
      ['3', 'symbol-3'],
      ['4', 'symbol-4'],
      ['5', 'symbol-5'],
      ['6', 'symbol-6'],
      ['7', 'symbol-7'],
      ['8', 'symbol-8'],
      ['9', 'symbol-9'],
      ['0', 'symbol-10'],
      ['q', 'symbol-12'],
    ],
  );
  assert.equal(
    operationalReviewSymbolForKey(shortcuts, 'Q')?.code,
    'symbol-12',
  );
});

test('ignores editable keyboard targets', () => {
  assert.equal(isOperationalReviewTypingTarget({ tagName: 'INPUT' }), true);
  assert.equal(isOperationalReviewTypingTarget({ tagName: 'select' }), true);
  assert.equal(isOperationalReviewTypingTarget({ tagName: 'TEXTAREA' }), true);
  assert.equal(
    isOperationalReviewTypingTarget({ isContentEditable: true }),
    true,
  );
  assert.equal(isOperationalReviewTypingTarget({ tagName: 'BUTTON' }), false);
});

test('submits on Enter or ArrowRight and ignores repeat, typing and open dialogs', () => {
  const shortcuts = buildOperationalReviewSymbolShortcuts([symbol(1)]);
  const base = {
    hasPrevious: true,
    key: 'Enter',
    otherDialogOpen: false,
    repeat: false,
    saving: false,
    shortcuts,
    typingTarget: false,
  };
  assert.deepEqual(operationalReviewKeyboardAction(base), {
    type: 'submit',
  });
  assert.deepEqual(operationalReviewKeyboardAction({ ...base, repeat: true }), {
    type: 'none',
  });
  assert.deepEqual(
    operationalReviewKeyboardAction({ ...base, typingTarget: true }),
    { type: 'none' },
  );
  assert.deepEqual(
    operationalReviewKeyboardAction({ ...base, otherDialogOpen: true }),
    { type: 'none' },
  );
  assert.deepEqual(
    operationalReviewKeyboardAction({ ...base, key: 'ArrowLeft' }),
    { type: 'previous' },
  );
  assert.deepEqual(
    operationalReviewKeyboardAction({ ...base, key: 'ArrowRight' }),
    { type: 'submit' },
  );
  assert.deepEqual(operationalReviewKeyboardAction({ ...base, key: '1' }), {
    symbolCode: 'symbol-1',
    type: 'set-symbol',
  });
});

test('updates counts when the last visible board changes status', () => {
  const counts = {
    accepted: 2,
    completed: 3,
    corrected: 1,
    pending: 4,
    rejected: 1,
    total: 8,
  };
  assert.deepEqual(
    updateOperationalReviewCounts(counts, 'pending', 'accepted'),
    {
      accepted: 3,
      completed: 4,
      corrected: 1,
      pending: 3,
      rejected: 1,
      total: 8,
    },
  );
  assert.deepEqual(
    updateOperationalReviewCounts(counts, 'accepted', 'corrected'),
    {
      accepted: 1,
      completed: 3,
      corrected: 2,
      pending: 4,
      rejected: 1,
      total: 8,
    },
  );
  assert.equal(
    updateOperationalReviewCounts(counts, 'accepted', 'accepted'),
    counts,
  );
});

test('builds accepted or corrected whole-board commands without empty revisions', () => {
  const item = reviewItem();
  const predicted = Array(15).fill('symbol-1');
  assert.equal(
    operationalReviewResolutionAction(item, 29, predicted),
    'accepted',
  );
  assert.equal(
    isOperationalReviewDraftChangedFromCurrent(item, 29, predicted),
    false,
  );

  const corrected = [...predicted];
  corrected[4] = 'symbol-4';
  const command = buildOperationalReviewResolutionCommand(
    item,
    30,
    corrected,
    '11111111-1111-4111-8111-111111111111',
  );
  assert.equal(command.action, 'corrected');
  assert.equal(command.cells.length, 15);
  assert.deepEqual(command.cells[4], {
    cellIndex: 4,
    cropSampleId: 'sample-4',
    symbolCode: 'symbol-4',
  });
  assert.equal(command.expectedRevision, 3);
  assert.equal(command.geometryRevision, 2);
  assert.equal(command.sequenceNumber, 30);
  assert.equal(
    isOperationalReviewDraftChangedFromCurrent(item, 30, corrected),
    true,
  );
});

test('parses manual geometry corners and binds preview/save to both revisions', () => {
  const item = {
    ...reviewItem(),
    geometry: {
      sourceQuad: [
        { x: 10, y: 20 },
        { x: 510, y: 25 },
        { x: 520, y: 320 },
        { x: 5, y: 315 },
      ],
    },
  };
  const corners = operationalReviewGeometryCorners(item, 600, 400);
  assert.deepEqual(corners, item.geometry.sourceQuad);
  assert.deepEqual(
    buildOperationalReviewGeometryPreviewCommand(item, corners),
    {
      corners,
      expectedGeometryRevision: 2,
      expectedResolutionRevision: 3,
    },
  );
  assert.deepEqual(
    buildOperationalReviewGeometryCommand(
      item,
      corners,
      '11111111-1111-4111-8111-111111111111',
    ),
    {
      corners,
      correctedBy: 'local-admin',
      expectedGeometryRevision: 2,
      expectedResolutionRevision: 3,
      idempotencyKey: '11111111-1111-4111-8111-111111111111',
    },
  );
});
