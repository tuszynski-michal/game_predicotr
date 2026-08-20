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
  operationalReviewGeometryEdgeHandles,
  operationalReviewGeometryViewport,
  operationalReviewNativeContextViewport,
  operationalReviewPointInCanvas,
  operationalReviewPointInGeometryViewport,
  operationalReviewPointInLattice,
  operationalReviewPointInSourceImage,
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
      { cellIndex: 14, usage: 'grid', version: 'crop-sha' },
    ),
  );
  assert.equal(
    url.pathname,
    '/api/v1/admin/image-review-items/item%2Fone/assets/cells/14',
  );
  assert.equal(url.searchParams.get('gameId'), 'game one');
  assert.equal(url.searchParams.get('importJobId'), 'job/one');
  assert.equal(url.searchParams.get('v'), 'crop-sha');
  assert.equal(url.searchParams.get('usage'), 'grid');
  assert.throws(
    () =>
      operationalReviewAssetUrl(
        'http://127.0.0.1:8000',
        { gameId: 'game', importJobId: 'job' },
        'item',
        'cell',
        { cellIndex: 15 },
      ),
    /between 0 and 14/,
  );
});

test('maps pointer coordinates through object-fit letterboxing', () => {
  const topEdge = operationalReviewPointInCanvas(
    { x: 250, y: 125 },
    { height: 500, left: 0, top: 0, width: 500 },
    1000,
    500,
  );
  assert.deepEqual(topEdge, {
    point: { x: 500, y: 0 },
    scale: 0.5,
  });

  const bottomEdge = operationalReviewPointInCanvas(
    { x: 500, y: 375 },
    { height: 500, left: 0, top: 0, width: 500 },
    1000,
    500,
  );
  assert.deepEqual(bottomEdge, {
    point: { x: 1000, y: 500 },
    scale: 0.5,
  });
});

test('native context includes the OCR number quad and uses a safe historical fallback', () => {
  const item = {
    ...reviewItem(),
    geometry: {
      sourceQuad: [
        { x: 200, y: 200 },
        { x: 600, y: 200 },
        { x: 600, y: 400 },
        { x: 200, y: 400 },
      ],
      sequenceLabelQuad: [
        { x: 320, y: 430 },
        { x: 480, y: 430 },
        { x: 480, y: 470 },
        { x: 320, y: 470 },
      ],
    },
  };
  const withLabel = operationalReviewNativeContextViewport(item, 1000, 800);
  const historical = operationalReviewNativeContextViewport(
    { ...item, geometry: { sourceQuad: item.geometry.sourceQuad } },
    1000,
    800,
  );

  assert.ok(withLabel.y < 200);
  assert.ok(withLabel.y + withLabel.height > 470);
  assert.ok(historical.y + historical.height > 500);
});

test('native context keeps retained source bounds after geometry changes', () => {
  const retained = {
    height: 260,
    width: 440,
    x: 180,
    y: 170,
  };
  const item = {
    ...reviewItem(),
    geometry: {
      sourceContextBounds: retained,
      sourceQuad: [
        { x: 400, y: 300 },
        { x: 700, y: 320 },
        { x: 680, y: 500 },
        { x: 380, y: 480 },
      ],
    },
  };

  assert.deepEqual(
    operationalReviewNativeContextViewport(item, 1000, 800),
    retained,
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
    superseded: 0,
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
      superseded: 0,
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
      superseded: 0,
      total: 8,
    },
  );
  assert.deepEqual(
    updateOperationalReviewCounts(counts, 'pending', 'superseded'),
    {
      accepted: 2,
      completed: 3,
      corrected: 1,
      pending: 3,
      rejected: 1,
      superseded: 1,
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

test('prefers v19 lattice bounds and derives four read-only projective edge handles', () => {
  const latticeBoundsQuad = [
    { x: 100, y: 80 },
    { x: 550, y: 110 },
    { x: 500, y: 360 },
    { x: 130, y: 330 },
  ];
  const item = {
    ...reviewItem(),
    geometry: {
      latticeBoundsQuad,
      sourceQuad: [
        { x: 20, y: 20 },
        { x: 580, y: 20 },
        { x: 580, y: 390 },
        { x: 20, y: 390 },
      ],
    },
  };

  const corners = operationalReviewGeometryCorners(item, 600, 400);
  const handles = operationalReviewGeometryEdgeHandles(corners);

  assert.deepEqual(corners, latticeBoundsQuad);
  assert.equal(handles.length, 4);
  assert.deepEqual(operationalReviewPointInLattice(corners, 0, 0), corners[0]);
  assert.deepEqual(operationalReviewPointInLattice(corners, 1, 0), corners[1]);
  assert.deepEqual(operationalReviewPointInLattice(corners, 1, 1), corners[2]);
  assert.deepEqual(operationalReviewPointInLattice(corners, 0, 1), corners[3]);
  const command = buildOperationalReviewGeometryPreviewCommand(item, corners);
  assert.deepEqual(command.corners, latticeBoundsQuad);
  assert.equal(Object.hasOwn(command, 'edgeHandles'), false);
});

test('limits geometry editing to one board viewport and preserves source coordinates', () => {
  const corners = [
    { x: 300, y: 200 },
    { x: 800, y: 210 },
    { x: 810, y: 510 },
    { x: 290, y: 500 },
  ];
  const viewport = operationalReviewGeometryViewport(corners, 1200, 900);

  assert.deepEqual(viewport, {
    height: 466,
    width: 780,
    x: 160,
    y: 122,
  });
  const visiblePoint = operationalReviewPointInGeometryViewport(
    corners[0],
    viewport,
  );
  assert.deepEqual(visiblePoint, { x: 140, y: 78 });
  assert.deepEqual(
    operationalReviewPointInSourceImage(visiblePoint, viewport, 1200, 900),
    corners[0],
  );
});
