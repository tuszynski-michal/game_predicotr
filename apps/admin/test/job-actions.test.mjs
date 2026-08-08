import assert from 'node:assert/strict';
import test from 'node:test';

import {
  cancelJob,
  createImageDiagnosticExport,
  downloadImageDiagnosticExport,
  loadImageDiagnosticExports,
  loadImageJobOperations,
  loadImageStorageInventory,
  loadJobs,
  loadWorkerLanes,
  retryImageJobFile,
  retryJob,
} from '../src/features/jobs/job-actions.ts';

test('loads both worker lanes independently from job filters', async () => {
  const lanes = [
    {
      heartbeatAt: '2026-08-05T12:00:00Z',
      lane: 'general',
      startedAt: '2026-08-05T11:00:00Z',
      state: 'running',
      threadBudget: 2,
      workerVersion: 'worker-v10-general',
    },
    {
      heartbeatAt: null,
      lane: 'image_selection',
      startedAt: null,
      state: 'stopped',
      threadBudget: null,
      workerVersion: null,
    },
  ];
  const result = await loadWorkerLanes({
    listWorkerLanes: async () => ({ data: lanes }),
  });

  assert.deepEqual(result, { lanes, ok: true });
});

const job = {
  attemptCount: 1,
  cancelRequestedAt: null,
  createdAt: '2026-07-27T10:00:00Z',
  error: null,
  finishedAt: null,
  gameId: 'game-1',
  heartbeatAt: null,
  id: 'job-1',
  inputPayload: {
    schemaVersion: 1,
    datasetVersionId: 'dataset-1',
  },
  jobType: 'validate',
  leaseExpiresAt: null,
  progress: {
    current: 0,
    failed: 0,
    review: 0,
    stage: null,
    succeeded: 0,
    total: null,
  },
  startedAt: null,
  status: 'created',
  updatedAt: '2026-07-27T10:00:00Z',
  workerVersion: null,
};

test('loads a bounded server-filtered jobs list', async () => {
  let received;
  const result = await loadJobs(
    {
      listJobs: async (filters) => {
        received = filters;
        return { data: [job] };
      },
    },
    { jobType: 'validate', status: 'created' },
  );

  assert.deepEqual(received, {
    jobType: 'validate',
    limit: 50,
    status: 'created',
  });
  assert.deepEqual(result, { jobs: [job], ok: true });
});

test('cancels and retries the same durable record', async () => {
  const cancelled = { ...job, status: 'cancelled' };
  const cancelResult = await cancelJob(
    {
      cancelJob: async (jobId) => {
        assert.equal(jobId, job.id);
        return { data: cancelled };
      },
    },
    job.id,
  );
  assert.deepEqual(cancelResult, { job: cancelled, ok: true });

  const failed = {
    ...job,
    error: { code: 'JOB_EXECUTION_FAILED', message: 'Handler failed.' },
    status: 'failed',
  };
  const retried = { ...failed, error: null, status: 'created' };
  const retryResult = await retryJob(
    {
      retryJob: async (jobId) => {
        assert.equal(jobId, job.id);
        return { data: retried };
      },
    },
    job.id,
  );
  assert.deepEqual(retryResult, { job: retried, ok: true });
});

test('preserves stable API errors and hides transport exceptions', async () => {
  const conflict = await retryJob(
    {
      retryJob: async () => ({
        error: {
          code: 'INVALID_JOB_STATUS_TRANSITION',
          details: {},
          message: 'Job cannot transition.',
        },
      }),
    },
    job.id,
  );
  assert.deepEqual(conflict, {
    error: 'Job cannot transition. (INVALID_JOB_STATUS_TRANSITION)',
    ok: false,
  });

  const transport = await loadJobs(
    {
      listJobs: async () => {
        throw new Error('sensitive transport details');
      },
    },
    {},
  );
  assert.deepEqual(transport, {
    error: 'Połączenie z lokalnym Admin API zostało przerwane.',
    ok: false,
  });
});

test('loads image operations and retries the exact failed file stage', async () => {
  const operations = {
    elapsedSeconds: 120,
    failed: 1,
    fileLimit: 100,
    files: [],
    filesPerMinute: 10,
    hasMoreFiles: false,
    jobId: job.id,
    review: 0,
    stageCounts: [],
    succeeded: 19,
    total: 20,
    waiting: 0,
  };
  let receivedRetry;

  const loaded = await loadImageJobOperations(
    {
      getImageJobOperations: async (jobId, limit) => {
        assert.equal(jobId, job.id);
        assert.equal(limit, 100);
        return { data: operations };
      },
    },
    job.id,
  );
  assert.deepEqual(loaded, { ok: true, operations });

  const retried = await retryImageJobFile(
    {
      retryImageJobFile: async (jobId, fileExecutionKey, body, limit) => {
        receivedRetry = { body, fileExecutionKey, jobId, limit };
        return { data: { ...operations, failed: 0, waiting: 1 } };
      },
    },
    job.id,
    'b'.repeat(64),
    'manual_review',
  );

  assert.deepEqual(receivedRetry, {
    body: { expectedStage: 'manual_review' },
    fileExecutionKey: 'b'.repeat(64),
    jobId: job.id,
    limit: 100,
  });
  assert.equal(retried.ok, true);
  assert.equal(retried.operations.failed, 0);
  assert.equal(retried.operations.waiting, 1);
});

test('loads storage and creates, lists and downloads diagnostic exports', async () => {
  const checksum = 'c'.repeat(64);
  const diagnosticExport = {
    checksumSha256: checksum,
    errorCount: 1,
    exportedErrorCount: 1,
    jobId: job.id,
    relativePath: `data/exports/image-jobs/${job.id}/${checksum}/diagnostics.json`,
    sizeBytes: 100,
    sourceUpdatedAt: '2026-07-29T12:00:00Z',
    truncated: false,
  };
  const inventory = {
    automaticDeletion: false,
    namespaces: [],
    rootName: 'data',
    totalFileCount: 0,
    totalSizeBytes: 0,
  };
  const artifact = new Blob(['{}\n'], {
    type: 'application/octet-stream',
  });
  const api = {
    createImageDiagnosticExport: async () => ({
      data: { created: true, export: diagnosticExport },
    }),
    downloadImageDiagnosticExport: async () => ({ data: artifact }),
    getImageStorageInventory: async () => ({ data: inventory }),
    listImageDiagnosticExports: async () => ({ data: [diagnosticExport] }),
  };

  assert.deepEqual(await loadImageStorageInventory(api), {
    inventory,
    ok: true,
  });
  assert.deepEqual(await loadImageDiagnosticExports(api, job.id), {
    exports: [diagnosticExport],
    ok: true,
  });
  assert.deepEqual(await createImageDiagnosticExport(api, job.id), {
    creation: { created: true, export: diagnosticExport },
    ok: true,
  });
  assert.deepEqual(await downloadImageDiagnosticExport(api, job.id, checksum), {
    artifact,
    ok: true,
  });
});
