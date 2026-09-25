import assert from 'node:assert/strict';
import test from 'node:test';

import {
  applySingleSymbolReviewDecision,
  setSymbolImageFromReviewCell,
} from '../src/features/symbol-reviews/symbol-review-mutation-actions.ts';

const target = {
  cellReviewId: 'cell-1',
  expectedCropChecksumSha256: 'a'.repeat(64),
  expectedCropSampleId: 'b'.repeat(64),
  expectedGeometryRevision: 3,
  expectedRevision: 7,
};

test('applies one exact crop directly without starting a bulk operation', async () => {
  const calls = [];
  const api = {
    async applySymbolCellReviewDecision(gameId, cellReviewId, body) {
      calls.push({ body, cellReviewId, gameId });
      return {
        data: {
          assignedSymbolId: 'symbol-2',
          boardReopened: false,
          boardResolutionAction: null,
          boardStatus: 'pending',
          catalogRevision: 9,
          cellReviewId,
          cellRevision: 8,
          hasGridIssue: false,
          reviewItemId: 'review-1',
          reviewState: 'approved',
          sequenceNumber: 10,
        },
      };
    },
  };

  const result = await applySingleSymbolReviewDecision(
    api,
    'game-1',
    'reassign',
    target,
    'symbol-2',
  );

  assert.equal(result.ok, true);
  assert.deepEqual(calls, [
    {
      body: {
        action: 'reassign',
        expectedCropChecksumSha256: 'a'.repeat(64),
        expectedCropSampleId: 'b'.repeat(64),
        expectedGeometryRevision: 3,
        expectedRevision: 7,
        targetSymbolId: 'symbol-2',
      },
      cellReviewId: 'cell-1',
      gameId: 'game-1',
    },
  ]);
});

test('rejects reassignment without a target before calling the API', async () => {
  let called = false;
  const result = await applySingleSymbolReviewDecision(
    {
      async applySymbolCellReviewDecision() {
        called = true;
        return {};
      },
    },
    'game-1',
    'reassign',
    target,
    null,
  );

  assert.equal(result.ok, false);
  assert.equal(called, false);
});

test('sends an unreadable decision without inventing a target symbol', async () => {
  const calls = [];
  const result = await applySingleSymbolReviewDecision(
    {
      async applySymbolCellReviewDecision(gameId, cellReviewId, body) {
        calls.push({ body, cellReviewId, gameId });
        return {
          data: {
            assignedSymbolId: 'symbol-1',
            boardReopened: true,
            boardResolutionAction: null,
            boardStatus: 'pending',
            catalogRevision: 10,
            cellReviewId,
            cellRevision: 8,
            hasGridIssue: false,
            qualityIssue: 'unreadable',
            reviewItemId: 'review-1',
            reviewState: 'pending',
            sequenceNumber: 10,
          },
        };
      },
    },
    'game-1',
    'mark_unreadable',
    target,
    null,
  );

  assert.equal(result.ok, true);
  assert.equal(calls[0].body.action, 'mark_unreadable');
  assert.equal('targetSymbolId' in calls[0].body, false);
});

test('sends a blurry quality decision without changing the recognized symbol', async () => {
  const calls = [];
  const result = await applySingleSymbolReviewDecision(
    {
      async applySymbolCellReviewDecision(gameId, cellReviewId, body) {
        calls.push({ body, cellReviewId, gameId });
        return {
          data: {
            assignedSymbolId: 'symbol-1',
            boardReopened: false,
            boardResolutionAction: null,
            boardStatus: 'accepted',
            catalogRevision: 11,
            cellReviewId,
            cellRevision: 8,
            hasGridIssue: false,
            qualityIssue: 'blurry',
            reviewItemId: 'review-1',
            reviewState: 'approved',
            sequenceNumber: 10,
          },
        };
      },
    },
    'game-1',
    'mark_blurry',
    target,
    null,
  );

  assert.equal(result.ok, true);
  assert.equal(calls[0].body.action, 'mark_blurry');
  assert.equal('targetSymbolId' in calls[0].body, false);
});

test('sends one atomic blurry decision with a corrected target symbol', async () => {
  const calls = [];
  const result = await applySingleSymbolReviewDecision(
    {
      async applySymbolCellReviewDecision(gameId, cellReviewId, body) {
        calls.push({ body, cellReviewId, gameId });
        return {
          data: {
            assignedSymbolId: 'symbol-2',
            boardReopened: false,
            boardResolutionAction: null,
            boardStatus: 'corrected',
            catalogRevision: 12,
            cellReviewId,
            cellRevision: 8,
            hasGridIssue: false,
            qualityIssue: 'blurry',
            reviewItemId: 'review-1',
            reviewState: 'approved',
            sequenceNumber: 10,
          },
        };
      },
    },
    'game-1',
    'mark_blurry',
    target,
    'symbol-2',
  );

  assert.equal(result.ok, true);
  assert.equal(calls[0].body.action, 'mark_blurry');
  assert.equal(calls[0].body.targetSymbolId, 'symbol-2');
});

function decisionApi(calls, referenceResult) {
  return {
    async applySymbolCellReviewDecision(gameId, cellReviewId, body) {
      calls.push({ body, cellReviewId, gameId, kind: 'decision' });
      return {
        data: {
          assignedSymbolId: body.targetSymbolId ?? 'symbol-1',
          boardReopened: false,
          boardResolutionAction: null,
          boardStatus: 'pending',
          catalogRevision: 11,
          cellReviewId,
          cellRevision: 8,
          hasGridIssue: false,
          reviewItemId: 'review-1',
          reviewState: 'approved',
          sequenceNumber: 10,
        },
      };
    },
    async selectSymbolReferenceFromCellReview(gameId, cellReviewId, body) {
      calls.push({ body, cellReviewId, gameId, kind: 'reference' });
      return referenceResult;
    },
  };
}

test('approves the current symbol and then sets the crop as its image', async () => {
  const calls = [];
  const result = await setSymbolImageFromReviewCell(
    decisionApi(calls, { data: { name: 'Cytryna' } }),
    'game-1',
    target,
    null,
  );

  assert.equal(result.ok, true);
  assert.equal(result.symbolName, 'Cytryna');
  assert.deepEqual(
    calls.map((call) => [call.kind, call.body.action ?? null]),
    [
      ['decision', 'approve'],
      ['reference', null],
    ],
  );
  assert.deepEqual(calls[1].body, {
    expectedChecksumSha256: 'a'.repeat(64),
    selectedBy: 'admin-local',
  });
});

test('reassigns to the chosen symbol before setting the image', async () => {
  const calls = [];
  const result = await setSymbolImageFromReviewCell(
    decisionApi(calls, { data: { name: 'Siódemka' } }),
    'game-1',
    target,
    'symbol-7',
  );

  assert.equal(result.ok, true);
  assert.equal(calls[0].body.action, 'reassign');
  assert.equal(calls[0].body.targetSymbolId, 'symbol-7');
  assert.equal(calls[1].cellReviewId, 'cell-1');
});

test('reports an image failure after a saved approval', async () => {
  const calls = [];
  const result = await setSymbolImageFromReviewCell(
    decisionApi(calls, {
      error: {
        code: 'SYMBOL_REFERENCE_CELL_NOT_ELIGIBLE',
        message: 'Not eligible.',
      },
    }),
    'game-1',
    target,
    null,
  );

  assert.equal(result.ok, false);
  assert.notEqual(result.decision, null);
  assert.match(result.error, /Crop zatwierdzono/);
});

test('does not set an image when the approval fails', async () => {
  let referenceCalled = false;
  const result = await setSymbolImageFromReviewCell(
    {
      async applySymbolCellReviewDecision() {
        return { error: { code: 'X', message: 'Nope.' } };
      },
      async selectSymbolReferenceFromCellReview() {
        referenceCalled = true;
        return {};
      },
    },
    'game-1',
    target,
    null,
  );

  assert.equal(result.ok, false);
  assert.equal(result.decision, null);
  assert.equal(referenceCalled, false);
});