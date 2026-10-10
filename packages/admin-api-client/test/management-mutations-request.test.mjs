import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';
import { createManagementPublicApiClient } from '../src/management.ts';

for (const publicPanel of [false, true]) {
  test(`generated mutation requests preserve JSON token and identity: public=${publicPanel}`, async () => {
    const calls = [];
    const fetch = async (request) => {
      calls.push({
        url: request.url,
        method: request.method,
        body: await request.json(),
        actor: request.headers.get(
          publicPanel ? 'X-Management-Session' : 'X-Admin-Intent',
        ),
      });
      return new Response('{}', {
        headers: { 'Content-Type': 'application/json' },
      });
    };
    const client = publicPanel
      ? createManagementPublicApiClient({
          baseUrl: 'https://panel.example',
          sessionId: 'session',
          fetch,
        })
      : createAdminApiClient({ baseUrl: 'http://127.0.0.1:8000', fetch });
    const preview = { expectedRevision: 3 };
    const command = {
      operationId: 'operation',
      expectedRevision: 3,
      previewToken: 'p'.repeat(43),
      confirmed: true,
    };
    const machine = {
      operationId: 'edit-operation',
      expectedRevision: 3,
      name: 'M',
      gameIds: [],
    };
    await client.previewManagementPointDeletion('point', preview);
    await client.deleteManagementPoint('point', command);
    await client.previewManagementMachineDeletion('point', 'machine', preview);
    await client.deleteManagementMachine('point', 'machine', command);
    await client.previewManagementMachineUpdate('machine', {
      command: machine,
    });
    assert(
      calls.every(
        (call) => call.method === 'POST' && new URL(call.url).search === '',
      ),
    );
    assert.deepEqual(calls[1].body, command);
    assert.deepEqual(calls[3].body, command);
    assert.deepEqual(calls[4].body, { command: machine });
    assert(
      calls.every(
        (call) => call.actor === (publicPanel ? 'session' : 'local-owner'),
      ),
    );
    const prefix = publicPanel
      ? '/api/v1/management-public'
      : '/api/v1/admin/management';
    assert.deepEqual(
      calls.map((call) => new URL(call.url).pathname),
      [
        `${prefix}/points/point/delete-preview`,
        `${prefix}/points/point/delete`,
        `${prefix}/points/point/machines/machine/delete-preview`,
        `${prefix}/points/point/machines/machine/delete`,
        `${prefix}/machines/machine/update-preview`,
      ],
    );
  });
}
