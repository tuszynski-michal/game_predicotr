import assert from 'node:assert/strict';
import test from 'node:test';

import {
  PAYOUT_ALGORITHM_VERSION,
  assessPayoutReadiness,
  payoutProgressPercent,
  selectPayoutDataset,
  selectPayoutJob,
} from '../src/features/rules/payout-computation-state.ts';

const gameId = '11111111-1111-4111-8111-111111111111';
const rules = {
  columns: 5,
  createdAt: '2026-08-01T09:00:00Z',
  gameId,
  id: 'rules-2',
  publishedAt: '2026-08-01T09:05:00Z',
  rows: 3,
  spinCost: 10,
  status: 'published',
  version: 2,
};
const dataset = {
  columns: 5,
  createdAt: '2026-08-01T08:00:00Z',
  expectedLayoutCount: 50,
  gameId,
  generationSeed: 17,
  generatorVersion: 'test-v1',
  id: 'dataset-3',
  layoutCount: 50,
  publishedAt: '2026-08-01T08:05:00Z',
  rows: 3,
  signatureCellWidth: 2,
  sourceJobId: null,
  status: 'published',
  version: 3,
};

function payoutJob(overrides = {}) {
  return {
    attemptCount: 1,
    cancelRequestedAt: null,
    createdAt: '2026-08-01T10:00:00Z',
    error: null,
    finishedAt: null,
    gameId,
    heartbeatAt: null,
    id: 'job-1',
    inputPayload: {
      algorithmVersion: PAYOUT_ALGORITHM_VERSION,
      datasetVersionId: dataset.id,
      rulesVersionId: rules.id,
      schemaVersion: 1,
    },
    jobType: 'payout',
    leaseExpiresAt: null,
    progress: {
      current: 25,
      failed: 0,
      review: 0,
      stage: 'calculating_payouts',
      succeeded: 25,
      total: 50,
    },
    startedAt: '2026-08-01T10:00:01Z',
    status: 'processing',
    updatedAt: '2026-08-01T10:00:02Z',
    workerVersion: 'worker-v4',
    ...overrides,
  };
}

test('selects newest matching published dataset and blocks incomplete data', () => {
  const older = { ...dataset, id: 'dataset-2', version: 2 };
  const wrongDimensions = {
    ...dataset,
    columns: 6,
    id: 'dataset-4',
    version: 4,
  };
  assert.equal(
    selectPayoutDataset([older, wrongDimensions, dataset], rules)?.id,
    dataset.id,
  );
  assert.deepEqual(assessPayoutReadiness(rules, [dataset]), {
    dataset,
    ready: true,
  });
  assert.equal(
    assessPayoutReadiness(rules, [{ ...dataset, layoutCount: 49 }]).ready,
    false,
  );
  assert.equal(
    assessPayoutReadiness({ ...rules, status: 'draft' }, [dataset]).ready,
    false,
  );
});

test('binds progress to the exact dataset rules and algorithm tuple', () => {
  const exact = payoutJob();
  const otherRules = payoutJob({
    createdAt: '2026-08-01T11:00:00Z',
    id: 'job-other',
    inputPayload: {
      ...exact.inputPayload,
      rulesVersionId: 'rules-other',
    },
  });

  assert.equal(
    selectPayoutJob([otherRules, exact], dataset.id, rules.id)?.id,
    exact.id,
  );
  assert.equal(payoutProgressPercent(exact), 50);
  assert.equal(
    payoutProgressPercent(
      payoutJob({ progress: { ...exact.progress, total: null } }),
    ),
    null,
  );
});
