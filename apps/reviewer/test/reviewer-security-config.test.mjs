import assert from 'node:assert/strict';
import test from 'node:test';

import nextConfig from '../next.config.ts';

test('CSP permits Next bootstrap while keeping scripts same-origin', async () => {
  const rules = await nextConfig.headers();
  const policy = rules
    .find((rule) => rule.source.includes('?!manual-selection'))
    ?.headers.find((header) => header.key === 'Content-Security-Policy')?.value;

  assert.equal(typeof policy, 'string');
  assert.match(policy, /script-src 'self' 'unsafe-inline'/);
  assert.doesNotMatch(policy, /https:\/\//);
  assert.match(policy, /frame-ancestors 'none'/);
  assert.match(policy, /connect-src 'self' http:\/\/127\.0\.0\.1:8000/);
  assert.match(policy, /img-src 'self' http:\/\/127\.0\.0\.1:8000/);
  assert.doesNotMatch(policy, /connect-src[^;]*https?:\/\/(?!127\.0\.0\.1)/);
});

test('remote manual selection CSP permits only same-origin transport', async () => {
  const rules = await nextConfig.headers();
  const globalRule = rules.find((rule) =>
    rule.source.includes('?!manual-selection'),
  );
  assert.match(globalRule?.source ?? '', /selection-api/);
  for (const source of ['/manual-selection', '/selection-api/:path*']) {
    const ruleIndex = rules.findIndex(
      (candidate) => candidate.source === source,
    );
    const rule = rules[ruleIndex];
    assert.ok(ruleIndex >= 0, `${source} must have a dedicated CSP`);
    const policy = rule?.headers.find(
      (header) => header.key === 'Content-Security-Policy',
    )?.value;
    assert.equal(typeof policy, 'string');
    assert.match(policy, /connect-src 'self'/);
    assert.doesNotMatch(policy, /127\.0\.0\.1:8000/);
    assert.match(policy, /frame-ancestors 'none'/);
    assert.match(policy, /form-action 'self'/);
    assert.equal(
      rule?.headers.find((header) => header.key === 'X-Frame-Options')?.value,
      'DENY',
    );
  }
});
