import assert from 'node:assert/strict';
import test from 'node:test';

import {
  cancelJob,
  loadJobs,
  retryJob,
} from '../src/features/jobs/job-actions.ts';

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
