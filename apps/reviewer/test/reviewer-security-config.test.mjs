import assert from 'node:assert/strict';
import test from 'node:test';

import nextConfig from '../next.config.ts';

test('CSP permits Next bootstrap while keeping scripts same-origin', async () => {
  const rules = await nextConfig.headers();
  const policy = rules[0]?.headers.find(
    (header) => header.key === 'Content-Security-Policy',
  )?.value;

  assert.equal(typeof policy, 'string');
  assert.match(policy, /script-src 'self' 'unsafe-inline'/);
  assert.doesNotMatch(policy, /https:\/\//);
  assert.match(policy, /frame-ancestors 'none'/);
  assert.match(policy, /connect-src 'self' http:\/\/127\.0\.0\.1:8000/);
  assert.match(policy, /img-src 'self' http:\/\/127\.0\.0\.1:8000/);
  assert.doesNotMatch(policy, /connect-src[^;]*https?:\/\/(?!127\.0\.0\.1)/);
});
