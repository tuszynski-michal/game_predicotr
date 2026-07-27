import assert from 'node:assert/strict';
import test from 'node:test';

import {
  generateMockDataset,
  getDatasetValidationReport,
} from '../src/features/datasets/dataset-actions.ts';

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

test('loads the canonical validation report and preserves stable errors', async () => {
  const report = {
    actualLayoutCount: 1000,
    checks: [],
    datasetVersion: 1,
    datasetVersionId: 'dataset-1',
    declaredLayoutCount: 1000,
    duplicateSignatureAffectedLayoutCount: 12,
    duplicateSignatureExcessLayoutCount: 6,
    duplicateSignatureGroupCount: 6,
    duplicateSignatures: [],
    duplicateSignaturesTruncated: false,
    maxSequenceNumber: 1000,
    minSequenceNumber: 1,
    readyForPublication: true,
  };
  const success = await getDatasetValidationReport(
    {
      getDatasetValidationReport: async (datasetId) => {
        assert.equal(datasetId, 'dataset-1');
        return { data: report };
      },
    },
    'dataset-1',
  );
  assert.deepEqual(success, { ok: true, report });

  const failure = await getDatasetValidationReport(
    {
      getDatasetValidationReport: async () => ({
        error: {
          code: 'DATASET_VALIDATION_REQUIRES_JOB',
          details: {},
          message: 'Worker validation required.',
        },
      }),
    },
    'dataset-2',
  );
  assert.deepEqual(failure, {
    error: 'Worker validation required. (DATASET_VALIDATION_REQUIRES_JOB)',
    ok: false,
  });
});
