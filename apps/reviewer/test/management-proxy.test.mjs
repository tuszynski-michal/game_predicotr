import assert from 'node:assert/strict';
import test from 'node:test';
import {
  managementPublicRoute,
  proxyManagementRequest,
} from '../src/security/management-proxy.ts';

const SESSION = '11111111-1111-4111-8111-111111111111';
const OTHER = '22222222-2222-4222-8222-222222222222';
const MACHINE = '33333333-3333-4333-8333-333333333333';
const GAME = '44444444-4444-4444-8444-444444444444';
const API = '/api/v1/management-public';
const TOKEN = 'b'.repeat(48);
function request(path, method = 'GET', body) {
  return new Request(`https://panel.example/management-api${API}${path}`, {
    method,
    headers: {
      'X-Management-Session': SESSION,
      Cookie: `gp_management_token=${TOKEN}; gp_board_search_token=${'a'.repeat(48)}`,
      Origin: 'https://panel.example',
      'Sec-Fetch-Site': 'same-origin',
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
}
const options = (response, seen = []) => ({
  fetchImplementation: async (url, init) => {
    seen.push({ url: String(url), init });
    return response;
  },
});

test('only explicit panel routes including methods and stake/cell positions', () => {
  assert(
    managementPublicRoute(
      'PUT',
      `${API}/machines/${MACHINE}/game/${GAME}/stakes/120`,
    ),
  );
  for (const path of [
    '/api/v1/admin/management',
    '/api/v1/admin/games',
    `${API}/sessions`,
    `${API}/sessions/${SESSION}/revoke`,
    `${API}/machines/${MACHINE}/game/${GAME}/stakes/999`,
    `${API}/machines/${MACHINE}/game/${GAME}/stakes/120/boards/1/cells/15/decision`,
  ])
    assert.equal(managementPublicRoute('POST', path), null);
});
test('expected identity cookie and intent are narrowly forwarded, old cookie ignored', async () => {
  const seen = [];
  const result = await proxyManagementRequest(
    request(''),
    options(Response.json({ points: [], activeGames: [] }), seen),
  );
  assert.equal(result.status, 200);
  assert.equal(
    seen[0].init.headers.get('cookie'),
    `gp_management_token=${TOKEN}`,
  );
  assert.equal(seen[0].init.headers.get('X-Management-Session'), SESSION);
  assert.equal(seen[0].init.headers.get('X-Admin-Intent'), null);
  assert.equal(
    seen[0].init.headers.get('X-Management-Public-Proxy'),
    'reviewer-management-v1',
  );
});
test('old tab A late mismatch401 never clears current session B cookie', async () => {
  const result = await proxyManagementRequest(
    request('/context'),
    options(
      Response.json({ code: 'MANAGEMENT_TOKEN_INVALID' }, { status: 401 }),
    ),
  );
  assert.equal(result.status, 401);
  assert.equal(result.headers.get('set-cookie'), null);
});
test('missing expected identity and cross-origin cannot reach backend', async () => {
  const req = request('/points', 'POST', { name: 'x' });
  req.headers.delete('X-Management-Session');
  assert.equal(
    (
      await proxyManagementRequest(req, {
        fetchImplementation: () => assert.fail('forwarded'),
      })
    ).status,
    401,
  );
  const cross = request('/points', 'POST', {});
  cross.headers.set('Origin', 'https://evil.example');
  assert.equal(
    (
      await proxyManagementRequest(cross, {
        fetchImplementation: () => assert.fail('forwarded'),
      })
    ).status,
    403,
  );
});
test('image URL binds expected session and machine/game, authenticates even304', async () => {
  const seen = [];
  const result = await proxyManagementRequest(
    request(
      `/machines/${MACHINE}/game/${GAME}/boards/1/view?expectedBoardChecksumSha256=${'a'.repeat(64)}&expectedSessionId=${OTHER}`,
    ),
    options(
      new Response('image', { headers: { 'Content-Type': 'image/jpeg' } }),
      seen,
    ),
  );
  assert.equal(result.status, 200);
  assert.equal(seen[0].init.headers.get('X-Management-Session'), OTHER);
  assert.equal(result.headers.get('cache-control'), 'private, no-cache');
  assert.equal(
    (
      await proxyManagementRequest(
        request(
          `/machines/${MACHINE}/game/${GAME}/boards/1/view?expectedBoardChecksumSha256=${'a'.repeat(64)}`,
        ),
      )
    ).status,
    403,
  );
});
test('bounded chunked request cancels before excess allocation, no Content-Length', async () => {
  let cancelled = false;
  let reads = 0;
  const stream = new ReadableStream({
    pull(controller) {
      reads++;
      controller.enqueue(new Uint8Array(9000));
    },
    cancel() {
      cancelled = true;
    },
  });
  const base = request('/points', 'POST', {});
  const req = new Request(base.url, {
    method: 'POST',
    headers: base.headers,
    body: stream,
    duplex: 'half',
  });
  assert.equal(
    (
      await proxyManagementRequest(req, {
        fetchImplementation: () => assert.fail('forwarded'),
      })
    ).status,
    413,
  );
  assert(cancelled);
  assert(reads <= 4);
});
test('recursive public payload checker rejects frozen rules secrets', async () => {
  assert.equal(
    (
      await proxyManagementRequest(
        request('/context'),
        options(
          Response.json({
            rulesSnapshot: { symbols: [{ imagePath: 'private' }] },
          }),
        ),
      )
    ).status,
    502,
  );
});
test('72h unlock retains lifetime and separate protected cookie', async () => {
  const expires = new Date(Date.now() + 72 * 3600000).toISOString();
  const upstream = Response.json(
    { sessionId: SESSION, label: 'Recipient', expiresAt: expires },
    {
      headers: {
        'Set-Cookie': `gp_management_token=${TOKEN}; Path=/management-api; HttpOnly`,
      },
    },
  );
  const result = await proxyManagementRequest(
    request(`/sessions/${SESSION}/unlock`, 'POST', { accessCode: 'ABCD-EFGH' }),
    options(upstream),
  );
  assert.equal(result.status, 200);
  const cookie = result.headers.get('set-cookie');
  assert.match(cookie, /Max-Age=25919\d/);
  assert.match(
    cookie,
    /Path=\/management-api; HttpOnly; Secure; SameSite=Strict/,
  );
});
test('expanded100000-row contract fits dedicated bounded JSON budget', () => {
  const row = {
    spinNumber: 100000,
    sequenceNumber: 100000,
    payoutCredits: 999999999999,
    cumulativePayoutCredits: 999999999999,
    cumulativeCostCredits: 999999999999,
    cumulativeBalanceCredits: -999999999999,
    payoutKind: 'confirmed_minimum',
    boardStatus: 'complete',
  };
  assert(Buffer.byteLength(JSON.stringify(row)) * 100000 < 64 * 1024 * 1024);
  assert(Buffer.byteLength(JSON.stringify(row)) * 100000 > 16 * 1024 * 1024);
});
