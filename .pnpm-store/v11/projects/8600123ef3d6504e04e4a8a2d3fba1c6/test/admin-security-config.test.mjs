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
