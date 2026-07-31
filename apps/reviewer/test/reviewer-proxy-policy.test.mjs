import assert from 'node:assert/strict';
import test from 'node:test';

import { reviewerProxyTarget } from '../src/security/reviewer-proxy-policy.ts';

const sessionId = '11111111-1111-4111-8111-111111111111';
const itemId = '22222222-2222-4222-8222-222222222222';

test('exposes only unlock, scoped context and operational review routes', () => {
  assert.equal(
    reviewerProxyTarget(
      'POST',
      `/api/v1/reviewer/sessions/${sessionId}/unlock`,
    ),
    `/api/v1/reviewer/sessions/${sessionId}/unlock`,
  );
  assert.equal(
    reviewerProxyTarget('GET', '/api/v1/admin/games'),
    '/api/v1/reviewer/context/games',
  );
  assert.equal(
    reviewerProxyTarget(
      'GET',
      `/api/v1/admin/image-review-items/${itemId}/assets/board`,
    ),
    `/api/v1/admin/image-review-items/${itemId}/assets/board`,
  );
  assert.equal(
    reviewerProxyTarget(
      'POST',
      `/api/v1/admin/image-review-items/${itemId}/resolution`,
    ),
    `/api/v1/admin/image-review-items/${itemId}/resolution`,
  );
});

test('rejects Admin CRUD, jobs mutations, exports and releases', () => {
  for (const [method, path] of [
    ['POST', '/api/v1/admin/games'],
    ['POST', `/api/v1/admin/jobs/${sessionId}/retry`],
    ['GET', '/api/v1/admin/image-review-cohort-exports'],
    ['POST', '/api/v1/admin/mobile-releases'],
    ['GET', '/api/v1/admin/image-storage'],
    ['GET', '/api/v1/admin/reviewer-ingress'],
    ['POST', '/api/v1/admin/reviewer-ingress/start'],
    ['POST', '/api/v1/admin/reviewer-ingress/stop'],
  ]) {
    assert.equal(reviewerProxyTarget(method, path), null, `${method} ${path}`);
  }
});
