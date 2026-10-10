import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  createManagementLinkClient,
  createManagementPublicApiClient,
} from '../src/index.ts';

test('local link wrappers carry exact confirmation targets and generated routes', async () => {
  const calls = [];
  const client = createManagementLinkClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      calls.push(request);
      return new Response('{}', {
        headers: { 'Content-Type': 'application/json' },
      });
    },
  });
  await client.createManagementSession({
    label: 'Recipient',
    lifetimeMinutes: 4320,
  });
  await client.listManagementSessions();
  await client.revokeManagementSession('session-a');
  assert.deepEqual(
    calls.map((r) => [r.method, new URL(r.url).pathname]),
    [
      ['POST', '/api/v1/admin/management/sessions'],
      ['GET', '/api/v1/admin/management/sessions'],
      ['POST', '/api/v1/admin/management/sessions/session-a/revoke'],
    ],
  );
  assert.ok(
    calls.every((r) => r.headers.get('X-Admin-Intent') === 'local-owner'),
  );
  assert.equal(calls[0].headers.get('X-Admin-Confirmation'), 'confirmed');
  assert.equal(
    calls[0].headers.get('X-Admin-Target'),
    'management-session:new',
  );
  assert.equal(
    calls[2].headers.get('X-Admin-Target'),
    'management-session:session-a',
  );
  assert.deepEqual(await calls[0].json(), {
    label: 'Recipient',
    lifetimeMinutes: 4320,
  });
});

test('public generated requests bind session identity, retain status and bind both image URLs', async () => {
  const calls = [];
  const client = createManagementPublicApiClient({
    baseUrl: 'https://review.example/management-api',
    sessionId: 'session-a',
    fetch: async (request) => {
      calls.push(request);
      return new Response('{}', {
        status: 409,
        headers: { 'Content-Type': 'application/json' },
      });
    },
  });
  await client.unlockManagementSession('AAAA-BBBB');
  await client.getManagementSessionContext();
  const response = await client.createManagementPoint({
    operationId: 'op',
    expectedRevision: 0,
    name: 'P',
    city: 'C',
    street: 'S',
  });
  await client.listPublicSymbols('machine', 'game');
  await client.listManagementJournal('machine', { gameId: 'game' });
  assert.equal(response.response.status, 409);
  assert.ok(
    calls.every(
      (r) =>
        r.headers.get('X-Management-Session') === 'session-a' &&
        r.credentials === 'same-origin',
    ),
  );
  assert.ok(
    calls.every((r) =>
      new URL(r.url).pathname.startsWith(
        '/management-api/api/v1/management-public',
      ),
    ),
  );
  assert.equal(calls[2].headers.get('X-Admin-Intent'), null);
  for (const url of [
    client.symbolImageUrl('machine', 'game', 'symbol', 'revision'),
    client.boardImageUrl('machine', 'game', 1, 'checksum', 'revision'),
  ]) {
    assert.equal(
      new URL(url).searchParams.get('expectedSessionId'),
      'session-a',
    );
    assert.ok(url.includes('/machines/machine/game/game/'));
  }
});
