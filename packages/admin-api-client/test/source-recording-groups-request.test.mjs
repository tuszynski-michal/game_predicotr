import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

const gameId = '11111111-1111-4111-8111-111111111111';
const groupId = '22222222-2222-4222-8222-222222222222';
const familyId = '33333333-3333-4333-8333-333333333333';

test('recording requests use own game, bounded keyset page and exact typed command', async () => {
  const requests = [];
  const api = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      requests.push({
        url: new URL(request.url),
        method: request.method,
        body: request.method === 'GET' ? null : await request.json(),
      });
      return Response.json({ items: [], nextCursor: null });
    },
  });
  await api.listSourceRecordingGroups(gameId, {
    familyId,
    after: groupId,
    limit: 100,
  });
  const command = {
    kind: 'attach',
    idempotencyKey: familyId,
    groupId,
    expectedRevision: 7,
    manifestId: gameId,
    pageIndex: 3,
  };
  await api.commandSourceRecordingGroups(gameId, command);
  assert.equal(
    requests[0].url.pathname,
    `/api/v1/admin/games/${gameId}/source-recording-groups`,
  );
  assert.equal(requests[0].method, 'GET');
  assert.equal(requests[0].url.searchParams.get('familyId'), familyId);
  assert.equal(requests[0].url.searchParams.get('after'), groupId);
  assert.equal(requests[0].url.searchParams.get('limit'), '100');
  assert.equal(
    requests[1].url.pathname,
    `${requests[0].url.pathname}/commands`,
  );
  assert.equal(requests[1].method, 'POST');
  assert.deepEqual(requests[1].body, command);
  const preparation = {
    kind: 'prepare',
    idempotencyKey: groupId,
    expectedRevision: 0,
    selection: { importJobId: familyId },
  };
  await api.commandSourceRecordingGroups(gameId, preparation);
  assert.deepEqual(requests[2].body, preparation);
  await api.listSourceRecordingGroups(gameId, { groupId, familyId, limit: 1 });
  assert.equal(requests[3].url.searchParams.get('groupId'), groupId);
  assert.equal(requests[3].url.searchParams.get('limit'), '1');
  await api.listJobs({ gameId, jobType: 'import', limit: 200 });
  assert.equal(requests[4].url.searchParams.get('game_id'), gameId);
  assert.equal(requests[4].url.searchParams.get('job_type'), 'import');
  assert.equal(requests[4].url.searchParams.get('limit'), '200');
});

test('typed refusal leaves the same body available for receipt replay', async () => {
  const sent = [];
  const receipt = {
    commandKind: 'assign_role',
    idempotencyKey: familyId,
    statusCode: 409,
    reasonCode: 'RECORDING_PROTECTED',
  };
  const api = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      sent.push(await request.json());
      return Response.json(
        { code: 'RECORDING_PROTECTED', details: { receipt } },
        { status: 409 },
      );
    },
  });
  const command = {
    kind: 'assign_role',
    idempotencyKey: familyId,
    expectedRevision: 7,
    groupId,
    familyId,
    role: 'TRAIN',
  };
  const first = await api.commandSourceRecordingGroups(gameId, command);
  const retry = await api.commandSourceRecordingGroups(gameId, command);
  assert.equal(first.response.status, 409);
  assert.deepEqual(retry.error.details.receipt, receipt);
  assert.deepEqual(sent, [command, command]);
});
