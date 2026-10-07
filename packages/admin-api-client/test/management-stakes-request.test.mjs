import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

test('management stake wrappers preserve generated routes, context, CAS and signals', async () => {
  const calls = [];
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      calls.push(request);
      return Response.json({});
    },
  });
  const controller = new AbortController();
  const signal = controller.signal;
  const search = {
    operationId: 'b3dce990-c361-49d3-98c6-e05d9ca8344f',
    stakeGrosze: 2000,
    cells: [
      { cellIndex: 0, symbolCode: 'A' },
      { cellIndex: 1, symbolCode: '?' },
    ],
    scope: 'all_searchable',
    limit: 100,
  };
  const save = {
    operationId: '6c5dabd2-c18e-44c5-a78f-0340d2080fa7',
    expectedRevision: 4,
    searchContextId: search.operationId,
    startSequenceNumber: 98542,
    spinCount: 5000,
    pinnedSpinPositions: [0, 7, 3000],
  };
  const mutation = {
    operationId: 'fdbbfe88-f231-4e2f-9b86-a123d1d38c78',
    expectedRevision: 5,
  };
  const correction = {
    operationId: 'd54c5f52-5e88-45bd-8a62-0b4c7c08992b',
    expectedCellVersion: 'a'.repeat(64),
    action: 'reassign',
    targetSymbolCode: 'B',
    searchContextId: search.operationId,
    startSequenceNumber: 98542,
    spinCount: 5000,
  };
  await client.listManagementStakes('machine', 'game', signal);
  await client.getManagementStake('machine', 'game', 2000, signal);
  await client.getManagementResult('machine', 'game', 'version', signal);
  await client.searchManagementBoards('machine', 'game', search, signal);
  await client.saveManagementStake('machine', 'game', 2000, save, signal);
  await client.refreshManagementStake(
    'machine',
    'game',
    2000,
    mutation,
    signal,
  );
  await client.clearManagementStake(
    'machine',
    'game',
    2000,
    { ...mutation, confirmed: true },
    signal,
  );
  await client.getManagementBoardDetail('machine', 'game', 98542, signal);
  await client.correctManagementBoardCell(
    'machine',
    'game',
    2000,
    98542,
    9,
    correction,
    signal,
  );
  await client.listManagementJournal('machine', {
    gameId: 'game',
    stakeGrosze: 2000,
    before: 'cursor',
    limit: 20,
    signal,
  });
  await client.getManagementApproximateWin('machine', 'game', {
    startSequenceNumber: 98542,
    spinCount: 5000,
    signal,
  });
  const base = '/api/v1/admin/management/machines/machine/game/game';
  assert.deepEqual(
    calls.map((request) => [request.method, new URL(request.url).pathname]),
    [
      ['GET', `${base}/stakes`],
      ['GET', `${base}/stakes/2000`],
      ['GET', `${base}/results/version`],
      ['POST', `${base}/search`],
      ['PUT', `${base}/stakes/2000`],
      ['POST', `${base}/stakes/2000/refresh`],
      ['POST', `${base}/stakes/2000/clear`],
      ['GET', `${base}/boards/98542`],
      ['POST', `${base}/stakes/2000/boards/98542/cells/9/decision`],
      ['GET', '/api/v1/admin/management/machines/machine/journal'],
      ['GET', `${base}/approximate-win`],
    ],
  );
  assert.deepEqual(await calls[3].json(), search);
  assert.deepEqual(await calls[4].json(), save);
  assert.deepEqual(await calls[5].json(), mutation);
  assert.deepEqual(await calls[8].json(), correction);
  assert.deepEqual(Object.fromEntries(new URL(calls[9].url).searchParams), {
    gameId: 'game',
    stakeGrosze: '2000',
    before: 'cursor',
    limit: '20',
  });
  assert.equal(
    new URL(calls[10].url).searchParams.get('startSequenceNumber'),
    '98542',
  );
  assert.ok(
    calls.every(
      (request) => request.headers.get('X-Admin-Intent') === 'local-owner',
    ),
  );
  controller.abort();
  assert.ok(calls.every((request) => request.signal.aborted));
});

test('management mutation errors preserve stable API error code and HTTP response', async () => {
  const error = {
    code: 'MANAGEMENT_REVISION_CONFLICT',
    message: 'Reload the saved stake.',
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async () => Response.json(error, { status: 409 }),
  });
  const result = await client.refreshManagementStake('machine', 'game', 2000, {
    operationId: 'fdbbfe88-f231-4e2f-9b86-a123d1d38c78',
    expectedRevision: 5,
  });
  assert.deepEqual(result.error, error);
  assert.equal(result.response.status, 409);
});
