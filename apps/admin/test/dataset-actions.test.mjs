import assert from 'node:assert/strict';
import test from 'node:test';

import { generateMockDataset } from '../src/features/datasets/dataset-actions.ts';

const dataset = {
  columns: 5,
  createdAt: '2026-07-27T10:00:00Z',
  gameId: 'game-1',
  generationSeed: 71401,
  generatorVersion: 'mock-v1',
  id: 'dataset-1',
  layoutCount: 1000,
  publishedAt: null,
  rows: 3,
  signatureCellWidth: 2,
  sourceJobId: null,
  status: 'staging',
  version: 1,
};

test('sends rules provenance and seed through the typed boundary', async () => {
  let received;
  const result = await generateMockDataset(
    {
      generateMockDataset: async (gameId, body) => {
        received = { body, gameId };
        return { data: dataset };
      },
    },
    'game-1',
    'rules-1',
    71401,
  );

  assert.deepEqual(received, {
    body: { rulesVersionId: 'rules-1', seed: 71401 },
    gameId: 'game-1',
  });
  assert.deepEqual(result, { dataset, ok: true });
});

test('preserves a stable generator conflict', async () => {
  const result = await generateMockDataset(
    {
      generateMockDataset: async () => ({
        error: {
          code: 'INSUFFICIENT_ACTIVE_SYMBOLS',
          details: { activeSymbolCount: 1 },
          message: 'At least two symbols are required.',
        },
      }),
    },
    'game-1',
    'rules-1',
    1,
  );

  assert.deepEqual(result, {
    error: 'At least two symbols are required. (INSUFFICIENT_ACTIVE_SYMBOLS)',
    ok: false,
  });
});
