import assert from 'node:assert/strict';
import test from 'node:test';

import {
  datasetValidationCheckLabel,
  datasetValidationStatusLabel,
  formatDiagnosticNumbers,
  publishedRulesVersions,
  upsertDatasetVersion,
  validateDatasetSeed,
} from '../src/features/datasets/dataset-state.ts';

const baseDataset = {
  columns: 5,
  createdAt: '2026-07-27T10:00:00Z',
  gameId: 'game-1',
  generationSeed: 1,
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

test('accepts only a bounded integer seed', () => {
  assert.deepEqual(validateDatasetSeed('71401'), {
    valid: true,
    value: 71401,
  });
  assert.equal(validateDatasetSeed('-1').valid, false);
  assert.equal(validateDatasetSeed('1.5').valid, false);
  assert.equal(validateDatasetSeed('2147483648').valid, false);
});

test('selects published rules and keeps datasets newest first', () => {
  const rules = [
    { id: 'draft', status: 'draft' },
    { id: 'published', status: 'published' },
    { id: 'archived', status: 'archived' },
  ];
  assert.deepEqual(
    publishedRulesVersions(rules).map((version) => version.id),
    ['published'],
  );

  const next = upsertDatasetVersion([baseDataset], {
    ...baseDataset,
    id: 'dataset-2',
    version: 2,
  });
  assert.deepEqual(
    next.map((dataset) => dataset.id),
    ['dataset-2', 'dataset-1'],
  );
});

test('presents validation codes, statuses and deterministic samples', () => {
  assert.equal(
    datasetValidationCheckLabel('DUPLICATE_SIGNATURE'),
    'Duplikaty sygnatur planszy',
  );
  assert.equal(datasetValidationStatusLabel('blocking'), 'Blokada');
  assert.equal(datasetValidationStatusLabel('warning'), 'Ostrzeżenie');
  assert.equal(formatDiagnosticNumbers([1, 4, 9]), '1, 4, 9');
});
