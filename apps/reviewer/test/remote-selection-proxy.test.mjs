import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import test from 'node:test';

import {
  REMOTE_SELECTION_MAX_CONTROL_BYTES,
  REMOTE_SELECTION_PROXY_INTENT,
  isRemoteManualSelectionEnabled,
  proxyRemoteSelectionRequest,
} from '../src/security/remote-selection-proxy.ts';

const sessionId = '11111111-1111-4111-8111-111111111111';
const clientId = '22222222-2222-4222-8222-222222222222';
const upstreamToken = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNO_123456789';
const expiresAt = new Date(Date.now() + 60 * 60 * 1000).toISOString();

async function withFakeApi(run) {
  const requests = [];
  const server = createServer((request, response) => {
    const chunks = [];
    request.on('data', (chunk) => chunks.push(chunk));
    request.on('end', () => {
      requests.push({
        body: Buffer.concat(chunks).toString('utf8'),
        headers: request.headers,
        method: request.method,
        url: request.url,
      });
      response.setHeader('Content-Type', 'application/json');
      response.setHeader('Cache-Control', 'private');
      if (request.url?.endsWith('/unlock')) {
        response.setHeader(
          'Set-Cookie',
          `remote_manual_selection_access=${upstreamToken}; Path=/selection-api; HttpOnly; Secure; SameSite=strict`,
        );
      }
      response.end(
        JSON.stringify({
          expiresAt,
          isWriter: true,
          revision: 2,
          sessionId,
          status: 'active',
          writerActive: true,
          writerLeaseExpiresAt: expiresAt,
        }),
      );
    });
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  assert.notEqual(address, null);
  assert.equal(typeof address, 'object');
  try {
    await run(`http://127.0.0.1:${address.port}`, requests);
  } finally {
    await new Promise((resolve, reject) =>
      server.close((error) =>
        error === undefined ? resolve() : reject(error),
      ),
    );
  }
}

function publicRequest(path, init = {}) {
  return new Request(`https://selection.example${path}`, {
    ...init,
    headers: {
      Host: 'selection.example',
      Origin: 'https://selection.example',
      'Sec-Fetch-Site': 'same-origin',
      'X-Forwarded-Proto': 'https',
      ...init.headers,
    },
  });
}

test('unlock translates the host cookie without exposing a token in JSON', async () => {
  await withFakeApi(async (origin, requests) => {
    const response = await proxyRemoteSelectionRequest(
      publicRequest(
        `/selection-api/api/v1/remote-manual-selections/sessions/${sessionId}/unlock`,
        {
          body: JSON.stringify({
            accessCode: 'ABCD-2345',
            clientInstanceId: clientId,
          }),
          headers: { 'Content-Type': 'application/json' },
          method: 'POST',
        },
      ),
      { internalApiOrigin: origin },
    );

    assert.equal(response.status, 200);
    const payload = await response.json();
    assert.equal(payload.sessionId, sessionId);
    assert.equal('accessToken' in payload, false);
    assert.equal('token' in payload, false);
    const cookie = response.headers.get('set-cookie');
    assert.match(cookie, /^gp_remote_selection_token=/);
    assert.match(cookie, /Path=\/selection-api/);
    assert.match(cookie, /HttpOnly/);
    assert.match(cookie, /Secure/);
    assert.match(cookie, /SameSite=Strict/);
    assert.equal(requests.length, 1);
    assert.equal(
      requests[0].headers['x-remote-selection-proxy'],
      REMOTE_SELECTION_PROXY_INTENT,
    );
    assert.equal(requests[0].headers.authorization, undefined);
  });
});

test('warm unlock proxy path stays within the control-plane latency baseline', async () => {
  await withFakeApi(async (origin, requests) => {
    const durations = [];
    for (let index = 0; index < 25; index += 1) {
      const startedAt = performance.now();
      const response = await proxyRemoteSelectionRequest(
        publicRequest(
          `/selection-api/api/v1/remote-manual-selections/sessions/${sessionId}/unlock`,
          {
            body: JSON.stringify({
              accessCode: 'ABCD-2345',
              clientInstanceId: clientId,
            }),
            headers: { 'Content-Type': 'application/json' },
            method: 'POST',
          },
        ),
        { internalApiOrigin: origin },
      );
      durations.push(performance.now() - startedAt);
      assert.equal(response.status, 200);
    }

    durations.sort((left, right) => left - right);
    const p95 = durations[Math.ceil(durations.length * 0.95) - 1];
    assert.equal(requests.length, 25);
    assert.ok(p95 < 250, `warm unlock proxy p95 ${p95.toFixed(2)} ms`);
  });
});

test('context translates only the purpose-scoped cookie and client header', async () => {
  await withFakeApi(async (origin, requests) => {
    const response = await proxyRemoteSelectionRequest(
      publicRequest('/selection-api/api/v1/remote-manual-selections/context', {
        headers: {
          Cookie: `gp_reviewer_token=legacy; gp_remote_selection_token=${upstreamToken}`,
          'X-Remote-Selection-Client': clientId,
        },
      }),
      { internalApiOrigin: origin },
    );

    assert.equal(response.status, 200);
    assert.equal(requests.length, 1);
    assert.equal(
      requests[0].headers.cookie,
      `remote_manual_selection_access=${upstreamToken}`,
    );
    assert.equal(requests[0].headers['x-remote-selection-client'], clientId);
    assert.equal(requests[0].headers.authorization, undefined);
  });
});

test('legacy Reviewer cookie cannot unlock remote selection context', async () => {
  await withFakeApi(async (origin, requests) => {
    const response = await proxyRemoteSelectionRequest(
      publicRequest('/selection-api/api/v1/remote-manual-selections/context', {
        headers: { Cookie: 'gp_reviewer_token=legacy' },
      }),
      { internalApiOrigin: origin },
    );
    assert.equal(response.status, 401);
    assert.equal(requests.length, 0);
  });
});

test('proxy rejects cross-origin, missing-origin, query and oversized control requests', async () => {
  await withFakeApi(async (origin, requests) => {
    const path = `/selection-api/api/v1/remote-manual-selections/sessions/${sessionId}/unlock`;
    const crossOrigin = await proxyRemoteSelectionRequest(
      publicRequest(path, {
        body: '{}',
        headers: {
          'Content-Type': 'application/json',
          Origin: 'https://evil.example',
        },
        method: 'POST',
      }),
      { internalApiOrigin: origin },
    );
    const missingOrigin = await proxyRemoteSelectionRequest(
      new Request(`https://selection.example${path}`, {
        body: '{}',
        headers: {
          Host: 'selection.example',
          'Content-Type': 'application/json',
        },
        method: 'POST',
      }),
      { internalApiOrigin: origin },
    );
    const withQuery = await proxyRemoteSelectionRequest(
      publicRequest(`${path}?admin=true`, {
        body: '{}',
        headers: { 'Content-Type': 'application/json' },
        method: 'POST',
      }),
      { internalApiOrigin: origin },
    );
    const oversized = await proxyRemoteSelectionRequest(
      publicRequest(path, {
        body: 'x'.repeat(REMOTE_SELECTION_MAX_CONTROL_BYTES + 1),
        headers: { 'Content-Type': 'application/json' },
        method: 'POST',
      }),
      { internalApiOrigin: origin },
    );

    assert.equal(crossOrigin.status, 403);
    assert.equal(missingOrigin.status, 403);
    assert.equal(withQuery.status, 403);
    assert.equal(oversized.status, 413);
    assert.equal(requests.length, 0);
  });
});

test('feature flag and negative route matrix fail closed before the API', async () => {
  await withFakeApi(async (origin, requests) => {
    const disabled = await proxyRemoteSelectionRequest(
      publicRequest('/selection-api/api/v1/remote-manual-selections/context'),
      { internalApiOrigin: origin, remoteSelectionEnabled: false },
    );
    const admin = await proxyRemoteSelectionRequest(
      publicRequest('/selection-api/api/v1/admin/games', {
        headers: { Cookie: `gp_remote_selection_token=${upstreamToken}` },
      }),
      { internalApiOrigin: origin },
    );
    const reviewer = await proxyRemoteSelectionRequest(
      publicRequest('/selection-api/api/v1/reviewer/context/games', {
        headers: { Cookie: `gp_remote_selection_token=${upstreamToken}` },
      }),
      { internalApiOrigin: origin },
    );

    assert.equal(disabled.status, 404);
    assert.equal(admin.status, 403);
    assert.equal(reviewer.status, 403);
    assert.equal(requests.length, 0);
  });
});

test('invalid feature flag and oversized upstream response fail closed', async () => {
  assert.equal(isRemoteManualSelectionEnabled('unexpected'), false);
  const response = await proxyRemoteSelectionRequest(
    publicRequest('/selection-api/api/v1/remote-manual-selections/context', {
      headers: { Cookie: `gp_remote_selection_token=${upstreamToken}` },
    }),
    {
      fetchImplementation: async () =>
        new Response('x'.repeat(REMOTE_SELECTION_MAX_CONTROL_BYTES + 1), {
          headers: { 'Content-Type': 'application/json' },
          status: 200,
        }),
    },
  );
  assert.equal(response.status, 502);
  assert.equal(
    (await response.json()).code,
    'REMOTE_SELECTION_UPSTREAM_INVALID',
  );
});
