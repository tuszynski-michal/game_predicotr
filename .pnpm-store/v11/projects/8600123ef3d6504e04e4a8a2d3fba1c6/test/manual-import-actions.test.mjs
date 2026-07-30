import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createLayoutImportJob,
  createLayoutImportValidation,
  loadLayoutImportReport,
  loadLayoutImportRows,
  publishLayoutImportDataset,
  rejectLayoutImportStaging,
} from '../src/features/imports/manual-import-actions.ts';

const job = {
  attemptCount: 0,
  cancelRequestedAt: null,
  createdAt: '2026-07-28T08:00:00Z',
  error: null,
  finishedAt: null,
  gameId: 'game-1',
  heartbeatAt: null,
  id: 'job-1',
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
  leaseExpiresAt: null,
  progress: {
    current: 0,
    failed: 0,
    review: 0,
    stage: null,
    succeeded: 0,
    total: 120,
  },
  startedAt: null,
  status: 'created',
  updatedAt: '2026-07-28T08:00:00Z',
  workerVersion: null,
};

test('creates typed import and layout validation jobs', async () => {
  const requests = [];
  const api = {
    createJob: async (body) => {
      requests.push(body);
      return { data: { ...job, jobType: body.jobType } };
    },
  };

  const imported = await createLayoutImportJob(
    api,
    'game-1',
    'game/layouts.jsonl',
  );
  const validated = await createLayoutImportValidation(
    api,
    'game-1',
    'import-1',
    'rules-1',
  );

  assert.equal(imported.ok, true);
  assert.equal(validated.ok, true);
  assert.deepEqual(requests, [
    {
      gameId: 'game-1',
      inputPayload: {
        contractVersion: 1,
        schemaVersion: 1,
        sourcePath: 'game/layouts.jsonl',
      },
      jobType: 'import',
    },
    {
      gameId: 'game-1',
      inputPayload: {
        importJobId: 'import-1',
        rulesVersionId: 'rules-1',
        schemaVersion: 1,
        validationKind: 'layout_import',
      },
      jobType: 'validate',
    },
  ]);
});

test('loads report and keyset-filtered rows through the typed client', async () => {
  const report = { importJobId: 'import-1', validationJobId: 'validation-1' };
  const page = { items: [], nextAfterLineNumber: null };
  let received;
  const loadedReport = await loadLayoutImportReport(
    {
      getLayoutImportIntegrityReport: async (validationJobId) => {
        assert.equal(validationJobId, 'validation-1');
        return { data: report };
      },
    },
    'validation-1',
  );
  const loadedRows = await loadLayoutImportRows(
    {
      listLayoutImportNormalizedRows: async (validationJobId, options) => {
        received = { options, validationJobId };
        return { data: page };
      },
    },
    'validation-1',
    {
      afterLineNumber: 25,
      errorCode: 'import_record_invalid',
      limit: 25,
      status: 'invalid',
    },
  );

  assert.deepEqual(loadedReport, { ok: true, report });
  assert.deepEqual(loadedRows, { ok: true, page });
  assert.deepEqual(received, {
    options: {
      afterLineNumber: 25,
      errorCode: 'import_record_invalid',
      limit: 25,
      status: 'invalid',
    },
    validationJobId: 'validation-1',
  });
});

test('rejects the exact validation staging and preserves stable errors', async () => {
  const success = await rejectLayoutImportStaging(
    {
      rejectLayoutImportStaging: async (validationJobId) => {
        assert.equal(validationJobId, 'validation-1');
        return {
          data: {
            deletedNormalizedRowCount: 10,
            deletedRawRowCount: 10,
            importJobId: 'import-1',
            validationJobId,
          },
        };
      },
    },
    'validation-1',
  );
  assert.equal(success.ok, true);

  const conflict = await rejectLayoutImportStaging(
    {
      rejectLayoutImportStaging: async () => ({
        error: {
          code: 'LAYOUT_IMPORT_STAGING_IN_USE',
          details: { datasetVersionId: 'dataset-1' },
          message: 'Staging is in use.',
        },
      }),
    },
    'validation-1',
  );
  assert.deepEqual(conflict, {
    error: 'Staging is in use. (LAYOUT_IMPORT_STAGING_IN_USE)',
    ok: false,
  });
});

test('publishes a ready import through the typed client', async () => {
  const dataset = {
    generatorVersion: 'layout-import-v1',
    id: 'dataset-1',
    layoutCount: 500000,
    sourceJobId: 'validation-1',
    status: 'published',
    version: 4,
  };
  const result = await publishLayoutImportDataset(
    {
      publishLayoutImportDataset: async (validationJobId) => {
        assert.equal(validationJobId, 'validation-1');
        return { data: dataset };
      },
    },
    'validation-1',
  );

  assert.deepEqual(result, { dataset, ok: true });
});
