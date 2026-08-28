import assert from 'node:assert/strict';
import test from 'node:test';

import {
  retryPayoutComputation,
  startPayoutComputation,
} from '../src/features/rules/payout-computation-actions.ts';

const gameId = '11111111-1111-4111-8111-111111111111';
const datasetId = '22222222-2222-4222-8222-222222222222';
const rulesId = '33333333-3333-4333-8333-333333333333';
const job = {
  id: '44444444-4444-4444-8444-444444444444',
  status: 'created',
};

test('starts an explicitly versioned payout job through the typed client', async () => {
  let request;
  const result = await startPayoutComputation(
    {
      createJob: async (body) => {
        request = body;
        return { data: job };
      },
    },
    gameId,
    datasetId,
    rulesId,
  );

  assert.equal(result.ok, true);
  assert.deepEqual(request, {
    gameId,
    inputPayload: {
      algorithmVersion: 'payout-v3-unknown-prefix-stop',
      datasetVersionId: datasetId,
      rulesVersionId: rulesId,
      schemaVersion: 1,
    },
    jobType: 'payout',
  });
});

test('retries the same failed job and preserves stable API errors', async () => {
  let retriedId;
  const success = await retryPayoutComputation(
    {
      retryJob: async (jobId) => {
        retriedId = jobId;
        return { data: { ...job, status: 'created' } };
      },
    },
    job.id,
  );
  const failure = await startPayoutComputation(
    {
      createJob: async () => ({
        error: {
          code: 'PAYOUT_DATASET_INCOMPLETE',
          details: { expectedLayoutCount: 50, layoutCount: 49 },
          message: 'Dataset is incomplete.',
        },
      }),
    },
    gameId,
    datasetId,
    rulesId,
  );

  assert.equal(retriedId, job.id);
  assert.equal(success.ok, true);
  assert.deepEqual(failure, {
    error: 'Dataset is incomplete. (PAYOUT_DATASET_INCOMPLETE)',
    ok: false,
  });
});
