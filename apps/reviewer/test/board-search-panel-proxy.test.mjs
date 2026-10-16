import assert from 'node:assert/strict';
import test from 'node:test';
import {
  panelChildToken,
  proxyBoardSearchPanelRequest,
} from '../src/security/board-search-panel-proxy.ts';
import nextConfig from '../next.config.ts';

const panel = '11111111-1111-4111-8111-111111111111';
const child = '22222222-2222-4222-8222-222222222222';
const secret = 'a'.repeat(43);
const origin = 'https://share.trycloudflare.com';
const expiry = new Date(Date.now() + 3600000).toISOString();

test('panel pages and proxy use a same-origin CSP and never send referrers', async () => {
  const rules = await nextConfig.headers();
  for (const source of [
    '/board-search-panel',
    '/board-search-panel-api/:path*',
  ]) {
    const headers = rules.find((rule) => rule.source === source).headers;
    assert.match(
      headers.find((header) => header.key === 'Content-Security-Policy').value,
      /connect-src 'self';/,
    );
    assert.equal(
      headers.find((header) => header.key === 'Referrer-Policy').value,
      'no-referrer',
    );
  }
});

function request(suffix, options = {}) {
  return new Request(
    `${origin}/board-search-panel-api/panels/${panel}/${suffix}`,
    {
      method: options.method ?? 'GET',
      body: options.body,
      headers: {
        host: 'share.trycloudflare.com',
        cookie: `gp_board_search_panel=${panel}.${secret}`,
        ...(options.method === 'POST'
          ? {
              origin,
              'sec-fetch-site': 'same-origin',
              'content-type': 'application/json',
            }
          : {}),
        ...options.headers,
      },
    },
  );
}
function json(data, options = {}) {
  return new Response(JSON.stringify(data), {
    ...options,
    headers: { 'content-type': 'application/json', ...options.headers },
  });
}

test('opening sets a separate per-panel HttpOnly cookie and never returns the key', async () => {
  const response = await proxyBoardSearchPanelRequest(
    request('open', {
      method: 'POST',
      body: JSON.stringify({ linkKey: secret }),
    }),
    {
      fetchImplementation: async (url, init) => {
        assert.equal(
          String(url),
          `http://127.0.0.1:8000/api/v1/board-search-panels/${panel}/open`,
        );
        assert.equal(new Headers(init.headers).get('cookie'), null);
        return json(
          {
            panelId: panel,
            expiresAt: expiry,
            games: [{ sessionId: child, gameName: '777' }],
          },
          {
            headers: {
              'set-cookie': `gp_board_search_panel=${panel}.${secret}; HttpOnly; Secure`,
            },
          },
        );
      },
    },
  );
  assert.equal(response.status, 200);
  assert.match(
    response.headers.get('set-cookie'),
    new RegExp(`Path=/board-search-panel-api/panels/${panel}`),
  );
  assert.match(
    response.headers.get('set-cookie'),
    /HttpOnly; Secure; SameSite=Strict/,
  );
  assert.equal((await response.text()).includes(secret), false);
});

test('game requests translate only the derived child credential into the existing allowlist', async () => {
  const response = await proxyBoardSearchPanelRequest(
    request(
      `games/${child}/api/v1/board-search-shares/search?cell=0:A&limit=10`,
    ),
    {
      fetchImplementation: async (url, init) => {
        assert.equal(
          String(url),
          'http://127.0.0.1:8000/api/v1/board-search-shares/search?cell=0:A&limit=10',
        );
        const cookie = new Headers(init.headers).get('cookie');
        assert.equal(
          cookie,
          `gp_board_search_token=${panelChildToken(secret, panel, child)}`,
        );
        assert.equal(cookie.includes(secret), false);
        return json({ results: [] });
      },
    },
  );
  assert.equal(response.status, 200);
});

test('a different panel cookie fails before upstream and is never cleared', async () => {
  let calls = 0;
  const response = await proxyBoardSearchPanelRequest(
    request('context', {
      headers: { cookie: `gp_board_search_panel=${child}.${secret}` },
    }),
    {
      fetchImplementation: async () => {
        calls++;
        return json({});
      },
    },
  );
  assert.equal(response.status, 401);
  assert.equal(calls, 0);
  assert.equal(response.headers.get('set-cookie'), null);
});

test('capability binds both parent and child IDs; no swap authorizes a foreign game', () => {
  assert.notEqual(
    panelChildToken(secret, panel, child),
    panelChildToken(secret, child, child),
  );
  assert.notEqual(
    panelChildToken(secret, panel, child),
    panelChildToken(secret, panel, panel),
  );
  assert.equal(
    panelChildToken(secret, panel.toUpperCase(), child),
    panelChildToken(secret, panel, child),
  );
});

test('arbitrary APIs, game queries, child unlock and cross-origin mutations are denied', async () => {
  const paths = [
    'games/' + child + '/api/v1/admin/jobs',
    `games/${child}/api/v1/board-search-shares/context?gameId=${child}`,
    `games/${child}/api/v1/board-search-shares/sessions/${child}/unlock`,
  ];
  for (const path of paths) {
    let calls = 0;
    const response = await proxyBoardSearchPanelRequest(request(path), {
      fetchImplementation: async () => {
        calls++;
        return json({});
      },
    });
    assert.equal(response.status, 403);
    assert.equal(calls, 0);
  }
  const response = await proxyBoardSearchPanelRequest(
    request('open', {
      method: 'POST',
      body: '{}',
      headers: { origin: 'https://foreign.example' },
    }),
  );
  assert.equal(response.status, 403);
});

test('oversized bodies and credential-bearing upstream JSON fail closed', async () => {
  const tooLarge = await proxyBoardSearchPanelRequest(
    request('open', { method: 'POST', body: 'a'.repeat(4097) }),
  );
  assert.equal(tooLarge.status, 413);
  const leaked = await proxyBoardSearchPanelRequest(request('context'), {
    fetchImplementation: async () => json({ tokenHash: secret }),
  });
  assert.equal(leaked.status, 502);
});

test('upstream expiry/401 does not clear another family cookie; disabled flag denies every route', async () => {
  const rejected = await proxyBoardSearchPanelRequest(
    request(`games/${child}/api/v1/board-search-shares/context`),
    {
      fetchImplementation: async () =>
        json(
          { error: { code: 'BOARD_SEARCH_SHARE_TOKEN_INVALID' } },
          { status: 401 },
        ),
    },
  );
  assert.equal(rejected.status, 401);
  assert.equal(rejected.headers.get('set-cookie'), null);
  assert.equal(
    (
      await proxyBoardSearchPanelRequest(request('context'), {
        shareEnabled: false,
      })
    ).status,
    404,
  );
});
