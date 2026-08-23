import assert from 'node:assert/strict';
import test from 'node:test';

import {
  remoteSelectionProxyTarget,
  reviewerProxyTarget,
} from '../src/security/reviewer-proxy-policy.ts';

const sessionId = '11111111-1111-4111-8111-111111111111';
const itemId = '22222222-2222-4222-8222-222222222222';
const gameId = '33333333-3333-4333-8333-333333333333';
const importJobId = '44444444-4444-4444-8444-444444444444';

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
  for (const [method, suffix] of [
    ['GET', 'correction-context'],
    ['GET', 'source'],
    ['POST', 'geometry-preview'],
    ['POST', 'manual-resolution'],
  ]) {
    const path =
      `/api/v1/admin/games/${gameId}/image-imports/${importJobId}/` +
      `board-cell-geometry-pending/${itemId}/${suffix}`;
    assert.equal(reviewerProxyTarget(method, path), path);
  }
  const pendingCollection =
    `/api/v1/admin/games/${gameId}/image-imports/${importJobId}/` +
    'board-cell-geometry-pending';
  assert.equal(
    reviewerProxyTarget('GET', pendingCollection),
    pendingCollection,
  );
  assert.equal(
    reviewerProxyTarget('GET', `${pendingCollection}/${itemId}`),
    `${pendingCollection}/${itemId}`,
  );
});

test('rejects Admin CRUD, jobs mutations, exports and releases', () => {
  for (const [method, path] of [
    ['POST', '/api/v1/admin/games'],
    ['POST', `/api/v1/admin/jobs/${sessionId}/retry`],
    ['GET', '/api/v1/admin/image-review-cohort-exports'],
    ['POST', '/api/v1/admin/mobile-releases'],
    ['GET', '/api/v1/admin/image-storage'],
    ['GET', `/api/v1/admin/games/${sessionId}/reviewer-work-assignments`],
    [
      'POST',
      `/api/v1/admin/games/${sessionId}/imports/${itemId}/reviewer-work-assignments/online`,
    ],
    ['GET', '/api/v1/admin/image-imports/browser-selections'],
    [
      'POST',
      `/api/v1/admin/image-imports/browser-selections/${sessionId}/start`,
    ],
    ['GET', '/api/v1/admin/reviewer-ingress'],
    ['POST', '/api/v1/admin/reviewer-ingress/start'],
    ['POST', '/api/v1/admin/reviewer-ingress/stop'],
    [
      'DELETE',
      `/api/v1/admin/games/${gameId}/image-imports/${importJobId}/` +
        `board-cell-geometry-pending/${itemId}`,
    ],
  ]) {
    assert.equal(reviewerProxyTarget(method, path), null, `${method} ${path}`);
  }
});

test('remote selection has a separate closed control-plane allowlist', () => {
  for (const [method, path] of [
    ['POST', `/api/v1/remote-manual-selections/sessions/${sessionId}/unlock`],
    ['GET', '/api/v1/remote-manual-selections/context'],
    [
      'POST',
      `/api/v1/remote-manual-selections/sessions/${sessionId}/writer-lease/heartbeat`,
    ],
    [
      'POST',
      `/api/v1/remote-manual-selections/sessions/${sessionId}/writer-lease/takeover`,
    ],
  ]) {
    assert.equal(remoteSelectionProxyTarget(method, path), path);
  }
});

test('remote selection rejects Reviewer, Admin, binary and malformed routes', () => {
  for (const [method, path] of [
    ['POST', `/api/v1/reviewer/sessions/${sessionId}/unlock`],
    ['GET', '/api/v1/reviewer/context/games'],
    ['GET', '/api/v1/admin/games'],
    ['GET', '/api/v1/admin/jobs'],
    ['POST', '/api/v1/admin/reviewer-ingress/start'],
    ['GET', `/api/v1/remote-manual-selections/sessions/${sessionId}`],
    [
      'PUT',
      `/api/v1/remote-manual-selections/sessions/${sessionId}/files/${itemId}/content`,
    ],
    [
      'POST',
      '/api/v1/remote-manual-selections/sessions/11111111-1111-1111-1111-111111111111/unlock',
    ],
    ['DELETE', '/api/v1/remote-manual-selections/context'],
  ]) {
    assert.equal(
      remoteSelectionProxyTarget(method, path),
      null,
      `${method} ${path}`,
    );
  }
});
