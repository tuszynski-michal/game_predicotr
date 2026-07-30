import assert from 'node:assert/strict';
import test from 'node:test';

import {
  canConfirmStagingRejection,
  completedLayoutFileImports,
  completedLayoutImportValidations,
  firstPreviewableRow,
  formatBoundedSample,
  layoutImportCheckStatusLabel,
  rowMajorCellLabel,
  validateImportSourcePath,
} from '../src/features/imports/manual-import-state.ts';

const baseJob = {
  attemptCount: 1,
  cancelRequestedAt: null,
  createdAt: '2026-07-28T08:00:00Z',
  error: null,
  finishedAt: '2026-07-28T08:01:00Z',
  gameId: 'game-1',
  heartbeatAt: null,
  leaseExpiresAt: null,
  progress: {
    current: 2,
    failed: 0,
    review: 0,
    stage: 'completed',
    succeeded: 2,
    total: 2,
  },
  startedAt: '2026-07-28T08:00:01Z',
  status: 'completed',
  updatedAt: '2026-07-28T08:01:00Z',
  workerVersion: 'worker-v4',
};

const importJob = {
  ...baseJob,
  id: 'import-1',
  inputPayload: {
    contractVersion: 1,
    fileFormat: 'jsonl',
    importKind: 'layout_file',
    schemaVersion: 1,
    sourceChecksum: 'a'.repeat(64),
    sourcePath: 'game/layouts.jsonl',
    sourceSizeBytes: 120,
  },
  jobType: 'import',
};

const validationJob = {
  ...baseJob,
  id: 'validation-1',
  inputPayload: {
    importJobId: 'import-1',
    rulesVersionId: 'rules-1',
    schemaVersion: 1,
    validationKind: 'layout_import',
  },
  jobType: 'validate',
};

test('selects only completed layout import jobs and validations', () => {
  assert.deepEqual(
    completedLayoutFileImports(
      [importJob, { ...importJob, id: 'other', gameId: 'game-2' }],
      'game-1',
    ).map((job) => job.id),
    ['import-1'],
  );
  assert.deepEqual(
    completedLayoutImportValidations([
      validationJob,
      { ...validationJob, id: 'active', status: 'processing' },
      {
        ...validationJob,
        id: 'dataset-validation',
        inputPayload: { datasetVersionId: 'dataset-1', schemaVersion: 1 },
      },
    ]).map((job) => job.id),
    ['validation-1'],
  );
});

test('validates safe local import paths before calling the API', () => {
  assert.deepEqual(validateImportSourcePath('game/layouts.csv'), {
    valid: true,
    value: 'game/layouts.csv',
  });
  assert.equal(validateImportSourcePath('../layouts.csv').valid, false);
  assert.equal(validateImportSourcePath('C:\\layouts.csv').valid, false);
  assert.equal(validateImportSourcePath('layouts.json').valid, false);
});

test('communicates bounded diagnostics and row-major coordinates textually', () => {
  assert.equal(
    formatBoundedSample([1, 2, 3], true),
    '1, 2, 3 … (próbka obcięta)',
  );
  assert.equal(
    layoutImportCheckStatusLabel('warning'),
    'Ostrzeżenie — publikacja dozwolona',
  );
  assert.equal(rowMajorCellLabel(7, 5), 'Wiersz 2, kolumna 3');
});

test('requires the exact import id and previews only a valid row', () => {
  const report = { importJobId: 'import-1' };
  assert.equal(canConfirmStagingRejection('import-1', report), true);
  assert.equal(canConfirmStagingRejection('validation-1', report), false);

  const invalid = {
    cells: [1, 99],
    errorCode: 'import_symbol_not_in_rules',
    errorMessage: 'Foreign symbol.',
    lineNumber: 1,
    sequenceNumber: 1,
    signature: null,
  };
  const valid = {
    cells: [1, 2],
    errorCode: null,
    errorMessage: null,
    lineNumber: 2,
    sequenceNumber: 2,
    signature: '0102',
  };
  assert.equal(firstPreviewableRow([invalid, valid]), valid);
});
