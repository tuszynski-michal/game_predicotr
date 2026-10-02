import assert from 'node:assert/strict';
import test from 'node:test';

import nextConfig from '../next.config.ts';

test('Admin CSP blocks framing and permits only its loopback API', async () => {
  const rules = await nextConfig.headers();
  const headers = new Map(
    rules[0]?.headers.map((header) => [header.key, header.value]),
  );
  const policy = headers.get('Content-Security-Policy');

  assert.equal(typeof policy, 'string');
  assert.match(policy, /connect-src 'self' http:\/\/127\.0\.0\.1:8000/);
  assert.match(policy, /frame-ancestors 'none'/);
  assert.doesNotMatch(policy, /https:\/\//);
  assert.equal(headers.get('X-Frame-Options'), 'DENY');
  assert.equal(headers.get('Referrer-Policy'), 'no-referrer');
});

async function policyWith(apiBaseUrl) {
  const previous = process.env.NEXT_PUBLIC_ADMIN_API_BASE_URL;
  process.env.NEXT_PUBLIC_ADMIN_API_BASE_URL = apiBaseUrl;
  try {
    const configModule = await import(
      `../next.config.ts?api=${encodeURIComponent(apiBaseUrl)}`
    );
    const rules = await configModule.default.headers();
    return rules[0]?.headers.find(
      (header) => header.key === 'Content-Security-Policy',
    )?.value;
  } finally {
    if (previous === undefined)
      delete process.env.NEXT_PUBLIC_ADMIN_API_BASE_URL;
    else process.env.NEXT_PUBLIC_ADMIN_API_BASE_URL = previous;
  }
}

test('Admin CSP also allows a configured loopback API origin, never a remote one', async () => {
  const local = await policyWith('http://127.0.0.1:8010');
  assert.match(
    local,
    /connect-src 'self' http:\/\/127\.0\.0\.1:8000 http:\/\/localhost:8000 http:\/\/127\.0\.0\.1:8010;/,
  );
  assert.match(
    local,
    /img-src 'self' data: blob: [^;]*http:\/\/127\.0\.0\.1:8010/,
  );
  const remote = await policyWith('http://example.com:8010');
  assert.doesNotMatch(remote, /example\.com/);
  const secure = await policyWith('https://127.0.0.1:8010');
  assert.doesNotMatch(secure, /8010/);
});
