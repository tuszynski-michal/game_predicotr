import assert from 'node:assert/strict';
import test from 'node:test';

import { applySingleSymbolReviewDecision } from '../src/features/symbol-reviews/symbol-review-mutation-actions.ts';

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
