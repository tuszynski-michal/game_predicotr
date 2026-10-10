import assert from 'node:assert/strict';
import test from 'node:test';

import {
  BOARD_SEARCH_SHARE_COOKIE,
  BOARD_SEARCH_SHARE_PROXY_INTENT,
  boardSearchShareRoute,
  cappedCacheControl,
  isBoardSearchShareEnabled,
  proxyBoardSearchShareRequest,
} from '../src/security/board-search-share-proxy.ts';
import { proxyRemoteSelectionRequest } from '../src/security/remote-selection-proxy.ts';

const sessionId = '11111111-1111-4111-8111-111111111111';
const token = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNO_123456789';
const sha = 'a'.repeat(64);
const origin = 'https://share.trycloudflare.com';
const expiresAt = new Date(Date.now() + 60 * 60 * 1000).toISOString();

function stub(respond) {
  const calls = [];
  return {
    calls,
    fetch: async (url, init) => {
      calls.push({
        headers: new Headers(init.headers),
        init,
        url: String(url),
      });
      return respond(String(url), init);
    },
  };
}

function json(body, init = {}) {
  return new Response(JSON.stringify(body), {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
  });
}

function request(path, init = {}) {
  const headers = new Headers(init.headers ?? {});
  if (init.cookie !== false) {
    headers.set('Cookie', `${BOARD_SEARCH_SHARE_COOKIE}=${token}`);
  }
  headers.set('Host', 'share.trycloudflare.com');
  return new Request(
    `${origin}/board-search-api/api/v1/board-search-shares${path}`,
    {
      body: init.body,
      headers,
      method: init.method ?? 'GET',
    },
  );
}

async function proxy(req, respond = () => json({ ok: true })) {
  const upstream = stub(respond);
  const response = await proxyBoardSearchShareRequest(req, {
    fetchImplementation: upstream.fetch,
    shareEnabled: true,
  });
  return { response, upstream };
}

test('only the read-only share routes and the unlock are public', () => {
  const allowed = [
    ['POST', `/api/v1/board-search-shares/sessions/${sessionId}/unlock`],
    ['GET', '/api/v1/board-search-shares/context'],
    ['GET', '/api/v1/board-search-shares/symbols'],
    ['GET', `/api/v1/board-search-shares/symbols/${sessionId}/image`],
    ['GET', '/api/v1/board-search-shares/search'],
    ['GET', '/api/v1/board-search-shares/approximate-win'],
    ['GET', '/api/v1/board-search-shares/approximate-win/stake'],
    ['GET', '/api/v1/board-search-shares/boards/42'],
    ['GET', '/api/v1/board-search-shares/boards/42/view'],
  ];
  for (const [method, path] of allowed) {
    assert.notEqual(
      boardSearchShareRoute(method, path),
      null,
      `${method} ${path}`,
    );
  }
  const refused = [
    ['GET', `/api/v1/board-search-shares/sessions/${sessionId}/unlock`],
    ['POST', '/api/v1/board-search-shares/search'],
    ['DELETE', '/api/v1/board-search-shares/context'],
    ['GET', '/api/v1/admin/board-search-shares/sessions'],
    ['POST', `/api/v1/admin/board-search-shares/sessions/${sessionId}/revoke`],
    ['GET', '/api/v1/admin/games'],
    ['GET', '/api/v1/board-search-shares/boards/0'],
    ['GET', '/api/v1/board-search-shares/boards/42/refresh'],
    ['POST', '/api/v1/board-search-shares/boards/42/refresh'],
    ['GET', '/api/v1/board-search-shares/../admin/games'],
    ['GET', '/api/v1/remote-manual-selections/context'],
  ];
  for (const [method, path] of refused) {
    assert.equal(
      boardSearchShareRoute(method, path),
      null,
      `${method} ${path}`,
    );
  }
});

test('routes outside the allowlist or with extra parameters are 403 without an upstream call', async () => {
  for (const path of [
    '/boards/42/refresh',
    '/search?cell=0:A&gameId=x',
    '/search?cell=0:A&limit=101',
    '/search?cell=15:A',
    '/search',
    '/context?x=1',
    `/symbols/${sessionId}/image`,
    `/symbols/${sessionId}/image?revision=${sha}&x=1`,
    '/approximate-win?startSequenceNumber=1',
    '/approximate-win/stake?startSequenceNumber=1&stakeGrosze=200',
    '/approximate-win/stake?startSequenceNumber=1&spinCount=5&stakeGrosze=0',
    '/approximate-win/stake?startSequenceNumber=1&spinCount=5&unit=pln',
    '/boards/42/view',
    `/boards/42/view?expectedBoardChecksumSha256=${sha}&expectedBoardChecksumSha256=${sha}`,
  ]) {
    const { response, upstream } = await proxy(request(path));
    assert.equal(response.status, 403, path);
    assert.equal(upstream.calls.length, 0, path);
  }
});

test('data requests need the share cookie; other surfaces cookies do not count', async () => {
  for (const cookie of [
    'gp_remote_selection_token=' + token,
    'gp_reviewer_token=' + token,
    'remote_manual_selection_access=' + token,
  ]) {
    const { response, upstream } = await proxy(
      request('/context', { cookie: false, headers: { Cookie: cookie } }),
    );
    assert.equal(response.status, 401);
    assert.equal(
      (await response.json()).code,
      'BOARD_SEARCH_SHARE_TOKEN_REQUIRED',
    );
    assert.match(response.headers.get('set-cookie') ?? '', /Max-Age=0/);
    assert.equal(upstream.calls.length, 0);
  }
});

test('the share cookie does not authorize the remote selection surface', async () => {
  const calls = [];
  const response = await proxyRemoteSelectionRequest(
    new Request(
      'https://share.trycloudflare.com/selection-api/api/v1/remote-manual-selections/context',
      {
        headers: {
          Cookie: `${BOARD_SEARCH_SHARE_COOKIE}=${token}`,
          Host: 'share.trycloudflare.com',
        },
      },
    ),
    {
      fetchImplementation: async (...args) => {
        calls.push(args);
        return json({});
      },
      remoteSelectionEnabled: true,
    },
  );
  assert.equal(response.status, 401);
  assert.equal(calls.length, 0);
});

test('a data request forwards the intent header and the share cookie only', async () => {
  const { response, upstream } = await proxy(
    request(`/search?cell=0:A&cell=3:%3F&scope=approved_only&limit=5`, {
      headers: {
        'Sec-Fetch-Site': 'same-origin',
        'X-Forwarded-For': '1.2.3.4',
      },
    }),
    () => json({ queryCellCount: 1, results: [], scope: 'approved_only' }),
  );
  assert.equal(response.status, 200);
  const [call] = upstream.calls;
  assert.equal(
    new URL(call.url).pathname + new URL(call.url).search,
    '/api/v1/board-search-shares/search?cell=0:A&cell=3:%3F&scope=approved_only&limit=5',
  );
  assert.equal(new URL(call.url).origin, 'http://127.0.0.1:8000');
  assert.equal(
    call.headers.get('x-board-search-share-proxy'),
    BOARD_SEARCH_SHARE_PROXY_INTENT,
  );
  assert.equal(
    call.headers.get('cookie'),
    `${BOARD_SEARCH_SHARE_COOKIE}=${token}`,
  );
  assert.equal(call.headers.get('x-forwarded-for'), null);
  assert.equal(call.init.redirect, 'error');
  assert.equal(response.headers.get('cache-control'), 'no-store');
});

test('responses carrying internal identities or paths are refused', async () => {
  for (const body of [
    { results: [{ reviewItemId: 'x' }] },
    { cells: [{ cellReviewId: 'x' }] },
    { imageRelativePath: 'data/a.png' },
    { message: 'C:\\Users\\owner\\secret.png' },
  ]) {
    const { response } = await proxy(request('/context'), () => json(body));
    assert.equal(response.status, 502);
    assert.equal(
      (await response.json()).code,
      'BOARD_SEARCH_SHARE_UPSTREAM_INVALID',
    );
  }
});

test('unlock re-emits a strict cookie scoped to the share prefix', async () => {
  const { response, upstream } = await proxy(
    request(`/sessions/${sessionId}/unlock`, {
      body: JSON.stringify({ accessCode: 'ABCD-EFGH' }),
      cookie: false,
      headers: {
        'Content-Type': 'application/json',
        Origin: origin,
        'Sec-Fetch-Site': 'same-origin',
      },
      method: 'POST',
    }),
    () =>
      json(
        { expiresAt, gameName: 'Gra', label: null, sessionId },
        {
          headers: {
            'Set-Cookie': `${BOARD_SEARCH_SHARE_COOKIE}=${token}; Path=/board-search-api; HttpOnly; Secure; SameSite=strict`,
          },
        },
      ),
  );
  assert.equal(response.status, 200);
  const cookie = response.headers.get('set-cookie');
  assert.match(cookie, new RegExp(`^${BOARD_SEARCH_SHARE_COOKIE}=${token};`));
  for (const attribute of [
    'HttpOnly',
    'Secure',
    'SameSite=Strict',
    'Path=/board-search-api',
  ]) {
    assert.ok(cookie.includes(attribute), attribute);
  }
  assert.equal(upstream.calls[0].headers.get('cookie'), null);
  assert.equal((await upstream.calls[0].init.body.byteLength) > 0, true);
});

test('unlock needs a same-origin JSON POST', async () => {
  const cases = [
    {
      'Content-Type': 'application/json',
      'Sec-Fetch-Site': 'cross-site',
      Origin: origin,
    },
    {
      'Content-Type': 'application/json',
      'Sec-Fetch-Site': 'same-origin',
      Origin: 'https://evil.example',
    },
    {
      'Content-Type': 'text/plain',
      'Sec-Fetch-Site': 'same-origin',
      Origin: origin,
    },
  ];
  for (const headers of cases) {
    const { response, upstream } = await proxy(
      request(`/sessions/${sessionId}/unlock`, {
        body: '{"accessCode":"ABCD-EFGH"}',
        cookie: false,
        headers,
        method: 'POST',
      }),
    );
    assert.ok([403, 415].includes(response.status), JSON.stringify(headers));
    assert.equal(upstream.calls.length, 0);
  }
});

test('images pass with a checked type, a size limit and a capped cache', async () => {
  const view = `/boards/42/view?expectedBoardChecksumSha256=${sha}&viewRevision=${sha}`;
  const ok = await proxy(
    request(view),
    () =>
      new Response(new Uint8Array([1, 2, 3]), {
        headers: {
          'Cache-Control': 'private, immutable, max-age=31536000',
          'Content-Type': 'image/webp',
          ETag: `"${sha}"`,
        },
      }),
  );
  assert.equal(ok.response.status, 200);
  assert.equal(ok.response.headers.get('content-type'), 'image/webp');
  assert.equal(
    ok.response.headers.get('cache-control'),
    'private, immutable, max-age=86400',
  );
  assert.equal(ok.response.headers.get('etag'), `"${sha}"`);
  const html = await proxy(
    request(view),
    () => new Response('<html>', { headers: { 'Content-Type': 'text/html' } }),
  );
  assert.equal(html.response.status, 502);
  const huge = await proxy(
    request(view),
    () =>
      new Response(new Uint8Array(1), {
        headers: {
          'Content-Length': String(9 * 1024 * 1024),
          'Content-Type': 'image/webp',
        },
      }),
  );
  assert.equal(huge.response.status, 502);
  const notModified = await proxy(
    request(view, { headers: { 'If-None-Match': `"${sha}"` } }),
    () => new Response(null, { headers: { ETag: `"${sha}"` }, status: 304 }),
  );
  assert.equal(notModified.response.status, 304);
  assert.equal(
    notModified.upstream.calls[0].headers.get('if-none-match'),
    `"${sha}"`,
  );
});

test('an upstream 401 clears the cookie and the flag disables the surface', async () => {
  const expired = await proxy(request('/context'), () =>
    json(
      { code: 'BOARD_SEARCH_SHARE_TOKEN_INVALID', message: 'x' },
      { status: 401 },
    ),
  );
  assert.equal(expired.response.status, 401);
  assert.match(expired.response.headers.get('set-cookie') ?? '', /Max-Age=0/);

  const disabled = await proxyBoardSearchShareRequest(request('/context'), {
    fetchImplementation: async () => json({}),
    shareEnabled: false,
  });
  assert.equal(disabled.status, 404);
  assert.equal(isBoardSearchShareEnabled(undefined), true);
  assert.equal(isBoardSearchShareEnabled('false'), false);
  assert.equal(isBoardSearchShareEnabled('yes'), false);
});

test('cache control is capped at one day and only for immutable images', () => {
  assert.equal(
    cappedCacheControl('private, immutable, max-age=31536000'),
    'private, immutable, max-age=86400',
  );
  assert.equal(
    cappedCacheControl('private, immutable, max-age=600'),
    'private, immutable, max-age=600',
  );
  assert.equal(cappedCacheControl('private, no-cache'), 'private, no-cache');
  assert.equal(cappedCacheControl(null), 'private, no-cache');
});

test('owner-typed names that look like paths are not mistaken for storage paths', async () => {
  const { response } = await proxy(request('/context'), () =>
    json({
      expiresAt,
      gameName: 'Gra C:/test',
      label: 'dla //zespołu',
      sessionId,
    }),
  );
  assert.equal(response.status, 200);
});

test('the Admin-only rules version choice is refused without an upstream call', async () => {
  // TASK-0932: the draft preview (`rulesVersionId`) never reaches the API
  // through the online share; the API refuses it as well.
  for (const path of [
    `/boards/42?rulesVersionId=${sessionId}`,
    `/approximate-win?startSequenceNumber=1&spinCount=5&rulesVersionId=${sessionId}`,
  ]) {
    const { response, upstream } = await proxy(request(path));
    assert.equal(response.status, 403, path);
    assert.equal(upstream.calls.length, 0, path);
  }
});
