import assert from 'node:assert/strict';
import test from 'node:test';
import {
  loadSymbolReviewSourceContext,
  symbolReviewSourceCells,
} from '../src/features/symbol-reviews/symbol-review-source-context.ts';
import {
  createPartialReviewClient,
  partialReviewItem,
} from '../test-interactions/fixtures/symbol-review-partial-client.mjs';

const quad = (x = 0) => [
  { x, y: 0 },
  { x: x + 500, y: 0 },
  { x: x + 500, y: 300 },
  { x, y: 300 },
];

test('source overlay prefers saved cell footprints, then the corrected lattice, without synthetic fallback', () => {
  const actual = quad(-1000);
  const cells = symbolReviewSourceCells({
    quad: quad(1000),
    latticeBoundsQuad: quad(),
    cells: [{ rowIndex: 0, columnIndex: 1, sourceQuad: actual }],
  });
  assert.equal(cells.length, 15);
  assert.deepEqual(cells[1], actual);
  assert.deepEqual(cells[0][0], { x: 0, y: 0 });
  assert.equal(symbolReviewSourceCells({ symbolGridQuad: quad() }).length, 15);
  assert.deepEqual(symbolReviewSourceCells({}), []);
  assert.deepEqual(
    symbolReviewSourceCells({
      quad: quad(),
      cells: [{ rowIndex: 3, columnIndex: 0, sourceQuad: actual }],
    }),
    [],
  );
  assert.deepEqual(
    symbolReviewSourceCells({
      quad: quad(),
      cells: [
        { rowIndex: 0, columnIndex: 0, sourceQuad: actual },
        { rowIndex: 0, columnIndex: 0, sourceQuad: actual },
      ],
    }),
    [],
  );
});

test('source context accepts zero crop images and retains signed outside geometry', async () => {
  const { api, calls } = await createPartialReviewClient();
  const result = await loadSymbolReviewSourceContext(
    api,
    'game-1',
    partialReviewItem(),
  );
  assert.equal(result.ok, true);
  assert.equal(result.cells.length, 15);
  assert.ok(result.cells[0].every((p) => p.x < 0));
  assert.equal(calls.source, 1);
});

test('stale geometry or owner never requests a source image', async () => {
  const { api, calls } = await createPartialReviewClient();
  for (const change of [
    { geometryRevision: 3 },
    { recognizedBoardId: 'other' },
    { reviewItemId: 'other' },
  ]) {
    const result = await loadSymbolReviewSourceContext(
      api,
      'game-1',
      partialReviewItem(change),
    );
    assert.equal(result.ok, false);
    assert.match(result.error, /Geometria pola zmieniła się/);
  }
  assert.equal(calls.source, 0);
});

test('changed source bytes fail closed; read errors remain recoverable', async () => {
  const { api } = await createPartialReviewClient();
  api.getOperationalImageReviewSourceAsset = async () => ({
    data: new Blob(['changed']),
  });
  assert.match(
    (await loadSymbolReviewSourceContext(api, 'game-1', partialReviewItem()))
      .error,
    /Zdjęcie źródłowe zmieniło się/,
  );
  api.getOperationalImageReviewItem = async () => {
    throw new Error('offline');
  };
  assert.equal(
    (await loadSymbolReviewSourceContext(api, 'game-1', partialReviewItem()))
      .ok,
    false,
  );
});
