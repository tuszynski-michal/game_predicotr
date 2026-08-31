import assert from 'node:assert/strict';
import test from 'node:test';

import { loadSymbolReviewPreviewAtlases } from '../src/features/symbol-reviews/symbol-review-virtual-previews.ts';

function items(count) {
  return Array.from({ length: count }, (_, index) => ({
    cropChecksumSha256: index.toString(16).padStart(64, '0'),
    id: `cell-${index}`,
    renderSpecChecksumSha256: index % 2 === 0 ? 'a'.repeat(64) : null,
    revision: index,
  }));
}

test('loads at most five stable atlases for five hundred cells', async () => {
  const requests = [];
  const progress = [];
  const api = {
    createSymbolCellPreviewBatch: async (_gameId, body) => {
      requests.push(body);
      return {
        data: {
          atlasChecksumSha256: 'a'.repeat(64),
          atlasUrl: `/atlas/batch-${requests.length}`,
          availableCount: body.cells.length,
          batchKey: `batch-${requests.length}`,
          expiresAt: '2026-09-02T00:00:00Z',
          rendererFingerprintSha256: 'b'.repeat(64),
          rendererMode: body.rendererMode,
          rendererVersion: 'renderer-v1',
          tiles: body.cells.map((cell, index) => ({
            cellReviewId: cell.cellReviewId,
            height: 100,
            width: 100,
            x: index * 100,
            y: 0,
          })),
          unavailableCellReviewIds: [],
        },
      };
    },
    symbolCellPreviewAtlasUrl: (_gameId, batchKey) => `/atlas/${batchKey}`,
  };

  const result = await loadSymbolReviewPreviewAtlases(
    api,
    'game-1',
    items(500),
    'cell-245',
    'current',
    (tiles) => progress.push(Object.keys(tiles).length),
  );

  assert.equal(result.ok, true);
  assert.equal(requests.length, 5);
  assert.deepEqual(
    requests.map((request) => request.cells[0].cellReviewId),
    ['cell-200', 'cell-300', 'cell-400', 'cell-0', 'cell-100'],
  );
  assert.deepEqual(progress, [100, 200, 300, 400, 500]);
  assert.equal(requests[0].cells[0].expectedCropChecksumSha256.length, 64);
  assert.equal(requests[0].rendererMode, 'current');
});

test('stops the sequential queue after an atlas error', async () => {
  let calls = 0;
  const result = await loadSymbolReviewPreviewAtlases(
    {
      createSymbolCellPreviewBatch: async () => {
        calls += 1;
        return calls === 2
          ? { error: { code: 'BROKEN_ATLAS' } }
          : {
              data: {
                atlasChecksumSha256: 'a'.repeat(64),
                atlasUrl: '/atlas/first',
                availableCount: 0,
                batchKey: 'first',
                expiresAt: '2026-09-02T00:00:00Z',
                rendererFingerprintSha256: 'b'.repeat(64),
                rendererMode: 'current',
                rendererVersion: 'renderer-v1',
                tiles: [],
                unavailableCellReviewIds: [],
              },
            };
      },
      symbolCellPreviewAtlasUrl: () => '/atlas/first',
    },
    'game-1',
    items(250),
    'cell-0',
    'current',
    () => undefined,
  );

  assert.equal(result.ok, false);
  assert.equal(calls, 2);
});

test('reports unavailable structured v0.10 cells without a legacy fallback', async () => {
  let atlasUrlCalls = 0;
  const result = await loadSymbolReviewPreviewAtlases(
    {
      createSymbolCellPreviewBatch: async (_gameId, body) => ({
        data: {
          atlasChecksumSha256: null,
          atlasUrl: null,
          availableCount: 0,
          batchKey: null,
          expiresAt: null,
          rendererFingerprintSha256: 'c'.repeat(64),
          rendererMode: body.rendererMode,
          rendererVersion: 'structured-v0.10-v1',
          tiles: [],
          unavailableCellReviewIds: body.cells.map((cell) => cell.cellReviewId),
        },
      }),
      symbolCellPreviewAtlasUrl: () => {
        atlasUrlCalls += 1;
        return '/must-not-be-used';
      },
    },
    'game-1',
    items(2),
    'cell-0',
    'structured_v0_10',
    () => undefined,
  );

  assert.equal(result.ok, true);
  assert.equal(atlasUrlCalls, 0);
  assert.deepEqual(
    [...result.availability.unavailableCellReviewIds],
    ['cell-0', 'cell-1'],
  );
});
