import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

test('cohort wrapper sends bounded exact bodies and scoped metadata routes', async () => {
  const calls = [];
  const facts = {
    qualification: 'unresolved',
    reasons: ['LABEL_STALE'],
    manifestSha256: null,
    humanLabelWithdrawn: null,
    liveSourceLinked: false,
    snapshotBytesAvailable: null,
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      calls.push({
        url: request.url,
        method: request.method,
        headers: request.headers,
        body: request.method === 'POST' ? await request.json() : null,
      });
      return new Response(
        JSON.stringify(request.url.endsWith('/eligibility') ? facts : {}),
        {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        },
      );
    },
  });
  const game = '11111111-1111-4111-8111-111111111111',
    cohort = '22222222-2222-4222-8222-222222222222';
  const key = '33333333-3333-4333-8333-333333333333';
  const body = { idempotencyKey: key, expectedRevision: 7, cursor: 200 };
  await client.listGridTrainingCohorts(game, { limit: 20 });
  await client.getGridTrainingCohort(game, cohort);
  await client.getGridTrainingCohortMembers(game, cohort, {
    cursor: 200,
    limit: 200,
  });
  const eligibility = await client.getGridTrainingCohortEligibility(
    game,
    cohort,
  );
  assert.deepEqual(eligibility.data, facts);
  await client.prepareGridTrainingCohortPage(game, cohort, body);
  await client.materializeGridTrainingCohortPage(game, cohort, body);
  const freeze = {
    idempotencyKey: key,
    expectedRevision: 7,
    expectedPreviewSha256: 'a'.repeat(64),
    expectedManifestSha256: 'b'.repeat(64),
  };
  await client.freezeGridTrainingCohort(game, cohort, freeze);
  await client.cancelGridTrainingCohort(game, cohort, {
    idempotencyKey: key,
    expectedRevision: 7,
  });
  const prepare = {
    idempotencyKey: key,
    familyId: cohort,
    baseVersionId: cohort,
    mode: 'grid-only',
    selector: { sourceIds: [cohort] },
    recordings: [{ groupId: cohort, role: 'TRAIN' }],
  };
  await client.prepareGridTrainingCohort(game, prepare);
  const complete = {
    idempotencyKey: key,
    sources: [
      {
        sourceId: cohort,
        expectedSourceSha256: 'a'.repeat(64),
        expectedSourceGeometryRevisionId: cohort,
        expectedGeometrySha256: 'b'.repeat(64),
      },
    ],
  };
  await client.completeGridSourceIdentities(game, complete);
  assert.equal(calls.length, 10);
  assert.ok(
    calls.every((c) =>
      new URL(c.url).pathname.startsWith(`/api/v1/admin/games/${game}/`),
    ),
  );
  assert.ok(
    calls.every((c) => c.headers.get('X-Admin-Intent') === 'local-owner'),
  );
  assert.ok(
    calls.slice(0, 4).every((c) => c.method === 'GET' && c.body === null),
  );
  assert.deepEqual(calls[4].body, body);
  assert.deepEqual(calls[5].body, body);
  assert.deepEqual(calls[6].body, freeze);
  assert.deepEqual(calls[8].body, prepare);
  assert.deepEqual(calls[9].body, complete);
  assert.ok(calls[9].url.endsWith('/grid-source-identities/complete'));
  // TASK-1000: recordings of several named imports form one exact selection.
  const several = {
    ...prepare,
    selector: { importJobIds: [cohort, game] },
  };
  await client.prepareGridTrainingCohort(game, several);
  assert.deepEqual(calls[10].body, several);
  assert.ok(calls[10].url.endsWith('/grid-training-cohorts/prepare'));
});
