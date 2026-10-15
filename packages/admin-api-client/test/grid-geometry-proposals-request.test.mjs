import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../dist/index.js';

test('proposal wrapper binds all path IDs, scope and unmodified commands', async () => {
  const calls = [];
  const api = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      calls.push({
        url: new URL(request.url),
        method: request.method,
        body: request.method === 'GET' ? null : await request.json(),
        intent: request.headers.get('X-Admin-Intent'),
      });
      return Response.json({ receipt: {}, current: null });
    },
  });
  const review = '11111111-1111-4111-8111-111111111111';
  const proposal = '22222222-2222-4222-8222-222222222222';
  const scope = { gameId: review, importJobId: proposal };
  const create = { targetResultId: proposal, idempotencyKey: review };
  const accept = {
    idempotencyKey: review,
    expectedProposalRevision: 1,
    expectedGeometryRevision: 0,
    expectedResolutionRevision: 0,
    mode: 'model',
    originalCandidateSha256: 'a'.repeat(64),
  };
  await api.listOperationalGridGeometryProposals(review, scope);
  await api.getOperationalGridGeometryProposal(review, proposal, scope);
  await api.createOperationalGridGeometryProposal(review, scope, create);
  await api.acceptOperationalGridGeometryProposal(
    review,
    proposal,
    scope,
    accept,
  );
  await api.rejectOperationalGridGeometryProposal(review, proposal, scope, {
    idempotencyKey: review,
    expectedProposalRevision: 1,
  });
  const base = `/api/v1/admin/image-review-items/${review}/grid-geometry-proposals`;
  assert.deepEqual(
    calls.map((c) => c.url.pathname),
    [
      base,
      `${base}/${proposal}`,
      base,
      `${base}/${proposal}/accept`,
      `${base}/${proposal}/reject`,
    ],
  );
  assert.deepEqual(calls[2].body, create);
  assert.deepEqual(calls[3].body, accept);
  assert.ok(
    calls.every(
      (c) =>
        c.url.searchParams.get('gameId') === review &&
        c.url.searchParams.get('importJobId') === proposal,
    ),
  );
  assert.equal(calls[3].intent, 'local-owner');
});
